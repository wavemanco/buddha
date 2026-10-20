"""Diagnostic sidecars retain safe failure metadata without another dispatch."""

import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import Mock, patch

from authorization_helpers import authorized_run

from buddha.diagnostics import DiagnosticHTTPTransport, failure_summary
from buddha.evaluation import ValidationError
from buddha.ledger import Ledger
from buddha.provider import BudgetBroker, Call, HTTPTransport, ModelSpec, ProviderUncertain


class DiagnosticsTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.directory = Path(temporary.name) / "run"
        self.spec = ModelSpec(
            "openai", "test-model", 100, 10, 1_000_000, 2_000_000, "https://example.org/bounds"
        )
        self.call = Call(
            self.spec,
            json.dumps(
                {
                    "model": "test-model",
                    "max_tokens": 10,
                    "messages": [{"role": "user", "content": "PROMPT-CANARY"}],
                    "service_tier": "default",
                }
            ),
        )
        self.authority, self.ledger = authorized_run(
            self.directory, budget_microusd=10_000, max_calls=20
        )
        self.transport = DiagnosticHTTPTransport(self.directory, allow_paid=True)
        self.operation = "a" * 64

    def envelope(self):
        return {
            "model": "test-model",
            "usage": {"prompt_tokens": 5, "completion_tokens": 3},
            "choices": [{"finish_reason": "stop", "message": {"content": "ANSWER-CANARY"}}],
            "service_tier": "default",
        }

    def connection(self, *, status=200, raw=None, request_id="req_12345678"):
        response = Mock(status=status)
        response.read.return_value = (
            raw if raw is not None else json.dumps(self.envelope()).encode()
        )
        response.getheader.return_value = request_id
        connection = Mock()
        connection.getresponse.return_value = response
        return connection, response

    def execute(self, connection):
        with (
            patch("buddha.diagnostics.http.client.HTTPSConnection", return_value=connection),
            patch.dict("os.environ", {"OPENAI_API_KEY": "KEY-CANARY"}),
        ):
            return BudgetBroker(self.ledger, self.transport).execute(self.operation, self.call)

    def outcome(self):
        return json.loads(
            (self.directory / "diagnostics" / self.operation / "outcome.json").read_text(
                encoding="utf-8"
            )
        )

    def test_http429_retains_status_and_request_id_without_retry(self):
        connection, _ = self.connection(
            status=429,
            raw=json.dumps(
                {"error": {"code": "rate_limit_exceeded", "message": "ERROR-BODY-CANARY"}}
            ).encode(),
        )
        with self.assertRaises(ProviderUncertain):
            self.execute(connection)
        saved = self.outcome()
        self.assertEqual(saved["http_status"], 429)
        self.assertEqual(saved["provider_request_id"], "req_12345678")
        self.assertEqual(saved["error_code"], "rate_limit_exceeded")
        self.assertEqual(self.ledger.get(self.operation).status, "unknown")
        self.assertEqual(self.ledger.totals()["reserved_microusd"], 120)
        connection.request.assert_called_once()
        self.assertEqual(failure_summary(self.directory)["http_status"], 429)

    def test_headers_are_captured_before_body_failure(self):
        connection, response = self.connection()
        observed = []
        response.getheader.side_effect = lambda *_: observed.append("header") or "req_12345678"

        def fail_read(*_):
            observed.append("read")
            raise OSError("BODY-READ-CANARY")

        response.read.side_effect = fail_read
        with self.assertRaises(ProviderUncertain):
            self.execute(connection)
        self.assertEqual(observed, ["header", "read"])
        self.assertEqual(self.outcome()["provider_request_id"], "req_12345678")
        self.assertEqual(self.outcome()["phase"], "read_body")

    def test_invalid_json_is_safe_and_known_status_remains(self):
        connection, _ = self.connection(raw=b"INVALID-JSON-CANARY")
        with self.assertRaises(ProviderUncertain):
            self.execute(connection)
        self.assertEqual(self.outcome()["error_category"], "invalid_response")
        self.assertEqual(self.outcome()["http_status"], 200)

    def test_success_preserves_reply_and_binds_exact_request(self):
        connection, _ = self.connection()
        result = self.execute(connection)
        self.assertEqual(result.text, "ANSWER-CANARY")
        request = json.loads(
            (self.directory / "diagnostics" / self.operation / "request.json").read_text(
                encoding="utf-8"
            )
        )
        self.assertEqual(request["operation_id"], self.operation)
        self.assertEqual(request["request_sha256"], self.call.fingerprint())
        self.assertEqual(request["host"], "api.openai.com")
        self.assertEqual(len(request["adapter_sha256"]), 64)
        sent = connection.request.call_args
        self.assertEqual(sent.args, ("POST", "/v1/chat/completions"))
        self.assertEqual(sent.kwargs["body"], self.call.body_json.encode())
        self.assertEqual(
            sent.kwargs["headers"]["X-Client-Request-Id"], request["client_request_id"]
        )
        self.assertEqual(self.outcome()["outcome"], "response_received")
        self.assertIsNone(failure_summary(self.directory))
        self.assertIsInstance(self.transport, HTTPTransport)

    def test_metadata_excludes_secrets_and_unvalidated_headers(self):
        connection, _ = self.connection(
            status=400,
            request_id="sk-HEADER-CANARY",
            raw=json.dumps(
                {"error": {"code": "UNTRUSTED-CODE-CANARY", "message": "ERROR-BODY-CANARY"}}
            ).encode(),
        )
        with self.assertRaises(ProviderUncertain):
            self.execute(connection)
        saved = "".join(p.read_text() for p in (self.directory / "diagnostics").rglob("*.json"))
        for canary in (
            "PROMPT-CANARY",
            "ANSWER-CANARY",
            "KEY-CANARY",
            "HEADER-CANARY",
            "UNTRUSTED-CODE-CANARY",
            "ERROR-BODY-CANARY",
        ):
            self.assertNotIn(canary, saved)
        self.assertIsNone(self.outcome()["provider_request_id"])

    def test_timeout_exception_message_is_not_persisted(self):
        connection, _ = self.connection()
        connection.getresponse.side_effect = TimeoutError("TIMEOUT-SECRET-CANARY")
        with self.assertRaises(ProviderUncertain):
            self.execute(connection)
        saved = self.outcome()
        self.assertEqual(saved["error_category"], "timeout")
        self.assertNotIn("TIMEOUT-SECRET-CANARY", json.dumps(saved))
        connection.request.assert_called_once()

    def test_ambiguous_dispatched_fingerprint_blocks_http(self):
        # Legacy input can contain multiple dispatches; current authority prevents
        # creating this state. Exercise the transport's defensive reader directly.
        config = self.ledger.config
        legacy = Ledger(
            self.ledger.path,
            run_id=config[0],
            manifest_sha256=config[1],
            budget_microusd=config[2],
            max_calls=config[3],
        )
        for operation in (self.operation, "b" * 64):
            legacy.reserve(operation, self.call.fingerprint(), 120)
            legacy.dispatch(operation)
        with (
            patch("buddha.diagnostics.http.client.HTTPSConnection") as connection,
            patch.dict("os.environ", {"OPENAI_API_KEY": "KEY-CANARY"}),
        ):
            with self.assertRaises(ValidationError):
                self.transport.send(self.call)
        connection.assert_not_called()
        self.assertFalse((self.directory / "diagnostics").exists())

    def test_no_dispatched_operation_or_missing_database_cannot_create_or_send(self):
        with tempfile.TemporaryDirectory() as other:
            transport = DiagnosticHTTPTransport(Path(other), allow_paid=True)
            with (
                patch("buddha.diagnostics.http.client.HTTPSConnection") as connection,
                patch.dict("os.environ", {"OPENAI_API_KEY": "KEY-CANARY"}),
            ):
                for selected in (self.transport, transport):
                    with self.assertRaises(ValidationError):
                        selected.send(self.call)
            connection.assert_not_called()
            self.assertFalse((Path(other) / "operations.sqlite3").exists())

    def test_request_journal_failure_prevents_http(self):
        connection, _ = self.connection()
        with patch("buddha.diagnostics._put", side_effect=OSError("WRITE-SECRET-CANARY")):
            with self.assertRaises(ProviderUncertain):
                self.execute(connection)
        connection.request.assert_not_called()

    def test_outcome_journal_failure_does_not_discard_billable_reply(self):
        from buddha.search import _put

        connection, _ = self.connection()

        def put(path, value):
            if path.name == "outcome.json":
                raise OSError("WRITE-SECRET-CANARY")
            _put(path, value)

        with patch("buddha.diagnostics._put", side_effect=put), self.assertWarns(RuntimeWarning):
            result = self.execute(connection)
        self.assertEqual(result.text, "ANSWER-CANARY")
        self.assertEqual(self.ledger.get(self.operation).status, "completed")

    def test_keyboard_interrupt_records_uncertainty_and_propagates(self):
        connection, response = self.connection()
        response.read.side_effect = KeyboardInterrupt
        with self.assertRaises(KeyboardInterrupt):
            self.execute(connection)
        self.assertEqual(self.outcome()["error_category"], "interrupted")
        self.assertEqual(self.ledger.get(self.operation).status, "unknown")

    def test_summary_rejects_tampered_and_extra_fields(self):
        from buddha.search import _put

        connection, _ = self.connection(status=500)
        with self.assertRaises(ProviderUncertain):
            self.execute(connection)
        path = self.directory / "diagnostics" / self.operation / "outcome.json"
        saved = self.outcome()
        saved["http_status"] = 429
        path.write_text(json.dumps(saved), encoding="utf-8")
        self.assertIsNone(failure_summary(self.directory))
        path.unlink()
        saved.pop("record_sha256")
        saved["UNTRUSTED-FIELD-CANARY"] = "SECRET-CANARY"
        _put(path, saved)
        self.assertIsNone(failure_summary(self.directory))

    def test_transport_does_not_write_ledger_or_dispatch_twice(self):
        self.ledger.reserve(self.operation, self.call.fingerprint(), 120)
        self.ledger.dispatch(self.operation)
        before = self.ledger.events()
        connection, _ = self.connection()
        with (
            patch("buddha.diagnostics.http.client.HTTPSConnection", return_value=connection),
            patch.dict("os.environ", {"OPENAI_API_KEY": "KEY-CANARY"}),
        ):
            self.transport.send(self.call)
            with self.assertRaises(ValidationError):
                self.transport.send(self.call)
        self.assertEqual(self.ledger.events(), before)
        self.assertEqual(self.ledger.get(self.operation).status, "dispatched")
        connection.request.assert_called_once()

    def test_outcome_journal_failure_does_not_mask_original_interruption(self):
        from buddha.search import _put

        connection, response = self.connection()
        response.read.side_effect = KeyboardInterrupt

        def put(path, value):
            if path.name == "outcome.json":
                raise OSError("WRITE-SECRET-CANARY")
            _put(path, value)

        with (
            patch("buddha.diagnostics._put", side_effect=put),
            self.assertWarns(RuntimeWarning),
            self.assertRaises(KeyboardInterrupt),
        ):
            self.execute(connection)
        self.assertEqual(self.ledger.get(self.operation).status, "unknown")

    def test_anthropic_preserves_request_and_omits_openai_correlation_header(self):
        self.spec = ModelSpec(
            "anthropic",
            "test-model",
            100,
            10,
            1_000_000,
            2_000_000,
            "https://example.org/bounds",
        )
        self.call = Call(
            self.spec,
            json.dumps(
                {
                    "model": "test-model",
                    "max_tokens": 10,
                    "messages": [{"role": "user", "content": "PROMPT-CANARY"}],
                    "service_tier": "standard_only",
                }
            ),
        )
        connection, _ = self.connection(
            raw=json.dumps(
                {
                    "model": "test-model",
                    "usage": {"input_tokens": 5, "output_tokens": 3},
                    "content": [{"type": "text", "text": "ANSWER-CANARY"}],
                    "stop_reason": "end_turn",
                }
            ).encode()
        )
        with (
            patch("buddha.diagnostics.http.client.HTTPSConnection", return_value=connection),
            patch.dict("os.environ", {"ANTHROPIC_API_KEY": "KEY-CANARY"}),
        ):
            result = BudgetBroker(self.ledger, self.transport).execute(self.operation, self.call)
        self.assertEqual(result.text, "ANSWER-CANARY")
        self.assertEqual(connection.request.call_args.args, ("POST", "/v1/messages"))
        self.assertNotIn("X-Client-Request-Id", connection.request.call_args.kwargs["headers"])
        self.assertEqual(connection.request.call_args.kwargs["body"], self.call.body_json.encode())

    def test_latest_success_supersedes_old_uncertain_summary(self):
        from buddha.search import _put

        connection, _ = self.connection(status=500)
        with self.assertRaises(ProviderUncertain):
            self.execute(connection)
        saved = self.outcome()
        saved.pop("record_sha256")
        saved.update(
            {
                "operation_id": "b" * 64,
                "at": "2099-01-01T00:00:00+00:00",
                "outcome": "response_received",
                "phase": "complete",
                "http_status": 200,
                "error_category": None,
                "error_code": None,
            }
        )
        _put(self.directory / "diagnostics" / ("b" * 64) / "outcome.json", saved)
        self.assertIsNone(failure_summary(self.directory))

    def test_summary_requires_unknown_ledger_operation_with_matching_fingerprint(self):
        from buddha.search import _put

        connection, _ = self.connection(status=429)
        with self.assertRaises(ProviderUncertain):
            self.execute(connection)
        self.assertIsNotNone(failure_summary(self.directory))
        base = self.directory / "diagnostics" / self.operation
        for name in ("request.json", "outcome.json"):
            path = base / name
            saved = json.loads(path.read_text(encoding="utf-8"))
            saved.pop("record_sha256")
            saved["request_sha256"] = "b" * 64
            path.unlink()
            _put(path, saved)
        self.assertIsNone(failure_summary(self.directory))

    def test_summary_rejects_reconciled_completed_operation(self):
        connection, _ = self.connection(status=429)
        with self.assertRaises(ProviderUncertain):
            self.execute(connection)
        self.ledger.complete(
            self.operation,
            response={"text": "known receipt"},
            actual_microusd=11,
            provider_request_id="req_12345678",
        )
        self.assertIsNone(failure_summary(self.directory))

    def test_summary_requires_correlated_request_record(self):
        from buddha.search import _put

        connection, _ = self.connection(status=429)
        with self.assertRaises(ProviderUncertain):
            self.execute(connection)
        path = self.directory / "diagnostics" / self.operation / "request.json"
        saved = json.loads(path.read_text(encoding="utf-8"))
        saved.pop("record_sha256")
        saved["client_request_id"] = "00000000-0000-0000-0000-000000000000"
        path.unlink()
        _put(path, saved)
        self.assertIsNone(failure_summary(self.directory))

    def test_summary_without_ledger_returns_none_without_creating_database(self):
        connection, _ = self.connection(status=429)
        with self.assertRaises(ProviderUncertain):
            self.execute(connection)
        self.ledger.path.unlink()
        self.assertIsNone(failure_summary(self.directory))
        self.assertFalse(self.ledger.path.exists())


if __name__ == "__main__":
    unittest.main()
