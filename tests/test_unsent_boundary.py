"""The actual paid broker separates recoverable preparation from transmission."""

import json
import tempfile
import unittest
from concurrent.futures import ThreadPoolExecutor
from contextlib import contextmanager
from pathlib import Path
from threading import Barrier
from unittest.mock import Mock, patch

from authorization_helpers import authorized_run

from buddha.diagnostics import DiagnosticHTTPTransport
from buddha.evaluation import ValidationError
from buddha.ledger import BudgetExceeded
from buddha.provider import (
    BudgetBroker,
    Call,
    HTTPTransport,
    ModelSpec,
    PendingOperation,
    ProviderUncertain,
)
from buddha.search import _put


class UnsentBoundaryTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.directory = Path(temporary.name) / "run"
        self.authority, self.ledger = authorized_run(
            self.directory, budget_microusd=10_000, max_calls=20
        )
        self.spec = ModelSpec(
            "openai",
            "test-model",
            100,
            10,
            1_000_000,
            2_000_000,
            "https://example.org/offline-bounds",
        )
        self.call = Call(
            self.spec,
            json.dumps(
                {
                    "model": "test-model",
                    "max_tokens": 10,
                    "service_tier": "default",
                    "messages": [{"role": "user", "content": "PREPARED-BODY-CANARY"}],
                }
            ),
        )
        self.operation = "a" * 64
        self.transport = DiagnosticHTTPTransport(self.directory, allow_paid=True)

    def connection(self):
        response = Mock(status=200)
        response.getheader.return_value = "req_12345678"
        response.read.return_value = json.dumps(
            {
                "model": "test-model",
                "usage": {"prompt_tokens": 5, "completion_tokens": 3},
                "choices": [{"finish_reason": "stop", "message": {"content": "answer"}}],
                "service_tier": "default",
            }
        ).encode()
        connection = Mock()
        connection.getresponse.return_value = response
        return connection

    @contextmanager
    def http(self, connection):
        with (
            patch(
                "buddha.provider.http.client.HTTPSConnection", return_value=connection
            ) as constructor,
            patch.dict("os.environ", {"OPENAI_API_KEY": "PREPARED-KEY-CANARY"}),
        ):
            yield constructor

    def execute(self, *, transport=None, operation=None):
        return BudgetBroker(self.ledger, transport or self.transport).execute(
            operation or self.operation, self.call
        )

    def request_path(self):
        return self.directory / "diagnostics" / self.operation / "request.json"

    def assert_reserved(self):
        self.assertEqual(self.ledger.get(self.operation).status, "reserved")
        summary = self.authority.summary()
        self.assertEqual(summary["operation_count"], 1)
        self.assertEqual(summary["spent_microusd"], 0)
        self.assertEqual(summary["reserved_microusd"], self.spec.reserve_microusd())
        self.assertNotIn("dispatched", [event["event_type"] for event in self.ledger.events()])

    def test_required_request_write_failure_is_reserved_and_retries_once(self):
        connection = self.connection()
        with (
            self.http(connection) as constructor,
            patch("buddha.diagnostics._put", side_effect=OSError("LOCAL-WRITE-CANARY")),
        ):
            with self.assertRaises(ValidationError):
                self.execute()
            constructor.assert_not_called()
        self.assert_reserved()
        with self.http(connection):
            result = self.execute()
            cached = self.execute()
        self.assertEqual(result, cached)
        connection.request.assert_called_once()
        summary = self.authority.summary()
        self.assertEqual(summary["operation_count"], 1)
        self.assertEqual(summary["spent_microusd"], 11)
        self.assertEqual(summary["reserved_microusd"], 0)

    def test_published_request_then_local_failure_reuses_uuid_and_bytes(self):
        connection = self.connection()

        def publish_then_fail(path, value):
            _put(path, value)
            if path.name == "request.json":
                raise OSError("AFTER-PUBLICATION-CANARY")

        with (
            self.http(connection) as constructor,
            patch("buddha.diagnostics._put", side_effect=publish_then_fail),
        ):
            with self.assertRaises(ValidationError):
                self.execute()
            constructor.assert_not_called()
        original = self.request_path().read_bytes()
        saved = json.loads(original)
        self.assert_reserved()
        with self.http(connection):
            self.execute()
        self.assertEqual(self.request_path().read_bytes(), original)
        self.assertEqual(
            connection.request.call_args.kwargs["headers"]["X-Client-Request-Id"],
            saved["client_request_id"],
        )
        connection.request.assert_called_once()

    def test_malformed_existing_request_is_preserved_and_blocked_before_dispatch(self):
        connection = self.connection()
        with (
            self.http(connection),
            patch("buddha.diagnostics._put", side_effect=OSError("LOCAL-WRITE-CANARY")),
        ):
            with self.assertRaises(ValidationError):
                self.execute()
        path = self.request_path()
        path.parent.mkdir(parents=True, exist_ok=True)
        malformed = b'{"record_sha256":"MALFORMED-RECORD-CANARY"}'
        path.write_bytes(malformed)
        with self.http(connection) as constructor:
            with self.assertRaises(ValidationError):
                self.execute()
            constructor.assert_not_called()
        self.assertEqual(path.read_bytes(), malformed)
        self.assert_reserved()

    def test_plain_http_constructor_failure_is_reserved_without_uncertainty(self):
        transport = HTTPTransport(allow_paid=True)
        with (
            patch(
                "buddha.provider.http.client.HTTPSConnection",
                side_effect=RuntimeError("LOCAL-CANARY"),
            ),
            patch.dict("os.environ", {"OPENAI_API_KEY": "PREPARED-KEY-CANARY"}),
        ):
            with self.assertRaises(ValidationError):
                self.execute(transport=transport)
        self.assert_reserved()
        connection = self.connection()
        with self.http(connection):
            self.execute(transport=transport)
        connection.request.assert_called_once()
        self.assertEqual(self.authority.summary()["spent_microusd"], 11)

    def test_deactivation_after_preparation_closes_without_request(self):
        connection = self.connection()
        prepare = self.transport.prepare

        def deactivate(operation_id, call):
            prepared = prepare(operation_id, call)
            self.authority.deactivate(self.directory.name, "inactive before dispatch")
            return prepared

        with self.http(connection), patch.object(self.transport, "prepare", side_effect=deactivate):
            with self.assertRaises(ValidationError):
                self.execute()
        connection.request.assert_not_called()
        connection.close.assert_called_once()
        self.assert_reserved()

    def test_lost_dispatch_cas_closes_without_request(self):
        connection = self.connection()
        with self.http(connection), patch.object(self.ledger, "dispatch", return_value=False):
            with self.assertRaises(PendingOperation):
                self.execute()
        connection.request.assert_not_called()
        connection.close.assert_called_once()
        self.assert_reserved()

    def test_genuine_timeout_remains_unknown_and_blocks_other_work(self):
        connection = self.connection()
        connection.getresponse.side_effect = TimeoutError("SECRET-TIMEOUT-CANARY")
        with self.http(connection) as constructor:
            with self.assertRaises(ProviderUncertain):
                self.execute()
            with self.assertRaises(BudgetExceeded):
                self.execute(operation="b" * 64)
            constructor.assert_called_once()
        connection.request.assert_called_once()
        self.assertEqual(self.ledger.get(self.operation).status, "unknown")
        summary = self.authority.summary()
        self.assertEqual(summary["operation_count"], 1)
        self.assertEqual(summary["reserved_microusd"], self.spec.reserve_microusd())
        saved = "".join(
            path.read_text() for path in (self.directory / "diagnostics").rglob("*.json")
        )
        self.assertNotIn("SECRET-TIMEOUT-CANARY", saved)

    def test_optional_outcome_runtime_failure_keeps_authentic_reply_completed(self):
        connection = self.connection()

        def fail_outcome(path, value):
            if path.name == "outcome.json":
                raise RuntimeError("OPTIONAL-OUTCOME-CANARY")
            _put(path, value)

        with self.http(connection), patch("buddha.diagnostics._put", side_effect=fail_outcome):
            result = self.execute()
        self.assertEqual(result.text, "answer")
        self.assertEqual(self.ledger.get(self.operation).status, "completed")
        self.assertEqual(self.authority.summary()["spent_microusd"], 11)
        connection.request.assert_called_once()

    def test_plain_http_close_runtime_failure_keeps_authentic_reply_completed(self):
        connection = self.connection()
        connection.close.side_effect = RuntimeError("OPTIONAL-CLOSE-CANARY")
        with self.http(connection):
            result = self.execute(transport=HTTPTransport(allow_paid=True))
        self.assertEqual(result.text, "answer")
        self.assertEqual(self.ledger.get(self.operation).status, "completed")
        self.assertEqual(self.authority.summary()["spent_microusd"], 11)
        connection.request.assert_called_once()

    def test_outcome_keyboard_interrupt_records_reply_then_propagates(self):
        self.assert_outcome_interrupt_preserves_reply(KeyboardInterrupt("OUTCOME-INTERRUPT-CANARY"))

    def test_outcome_system_exit_records_reply_then_propagates(self):
        self.assert_outcome_interrupt_preserves_reply(SystemExit(17))

    def test_direct_diagnostic_send_propagates_original_optional_interrupt(self):
        self.ledger.reserve(self.operation, self.call.fingerprint(), self.spec.reserve_microusd())
        self.ledger.dispatch(self.operation)
        connection = self.connection()
        interruption = KeyboardInterrupt("DIRECT-INTERRUPT-CANARY")

        def interrupt_outcome(path, value):
            if path.name == "outcome.json":
                raise interruption
            _put(path, value)

        with self.http(connection), patch("buddha.diagnostics._put", side_effect=interrupt_outcome):
            with self.assertRaises(KeyboardInterrupt) as caught:
                self.transport.send(self.call)
        self.assertIs(caught.exception, interruption)
        self.assertEqual(self.ledger.get(self.operation).status, "dispatched")
        connection.request.assert_called_once()
        connection.close.assert_called_once()

    def test_received_interrupt_repr_omits_reply_and_interrupt_contents(self):
        from buddha.provider import Reply, _ReceivedInterrupt

        interruption = KeyboardInterrupt("INTERRUPT-SECRET-CANARY")
        reply = Reply("REPLY-SECRET-CANARY", "test-model", "req_12345678", 5, 3, "stop")
        carried = _ReceivedInterrupt(reply, interruption)
        self.assertNotIn("REPLY-SECRET-CANARY", repr(carried))
        self.assertNotIn("INTERRUPT-SECRET-CANARY", repr(carried))
        self.assertIs(carried.reply, reply)
        self.assertIs(carried.interruption, interruption)

    def assert_outcome_interrupt_preserves_reply(self, interruption):
        connection = self.connection()

        def interrupt_outcome(path, value):
            if path.name == "outcome.json":
                raise interruption
            _put(path, value)

        with (
            self.http(connection) as constructor,
            patch("buddha.diagnostics._put", side_effect=interrupt_outcome),
        ):
            with self.assertRaises(type(interruption)) as caught:
                self.execute()
            self.assertIs(caught.exception, interruption)
            self.assert_completed_charge()
            self.assertEqual(self.execute().text, "answer")
            constructor.assert_called_once()
        connection.request.assert_called_once()
        connection.close.assert_called_once()

    def test_close_keyboard_interrupt_records_reply_then_propagates(self):
        connection = self.connection()
        interruption = KeyboardInterrupt("CLOSE-INTERRUPT-CANARY")
        connection.close.side_effect = interruption
        with self.http(connection) as constructor:
            with self.assertRaises(KeyboardInterrupt) as caught:
                self.execute()
            self.assertIs(caught.exception, interruption)
            self.assert_completed_charge()
            self.assertEqual(self.execute().text, "answer")
            constructor.assert_called_once()
        connection.request.assert_called_once()
        connection.close.assert_called_once()

    def test_close_interruption_after_timeout_keeps_unknown_and_held(self):
        connection = self.connection()
        connection.getresponse.side_effect = TimeoutError("TIMEOUT-CANARY")
        connection.close.side_effect = KeyboardInterrupt
        with self.http(connection):
            with self.assertRaises(KeyboardInterrupt):
                self.execute()
        self.assertEqual(self.ledger.get(self.operation).status, "unknown")
        summary = self.authority.summary()
        self.assertEqual(summary["spent_microusd"], 0)
        self.assertEqual(summary["reserved_microusd"], self.spec.reserve_microusd())
        connection.request.assert_called_once()

    def assert_completed_charge(self):
        saved = self.ledger.get(self.operation)
        self.assertEqual(saved.status, "completed")
        self.assertEqual(saved.provider_request_id, "req_12345678")
        self.assertEqual(saved.actual_microusd, 11)
        self.assertEqual(saved.response["text"], "answer")
        summary = self.authority.summary()
        self.assertEqual(summary["operation_count"], 1)
        self.assertEqual(summary["spent_microusd"], 11)
        self.assertEqual(summary["reserved_microusd"], 0)

    def test_prepared_repr_omits_secret_and_body_canaries(self):
        self.ledger.reserve(self.operation, self.call.fingerprint(), self.spec.reserve_microusd())
        connection = self.connection()
        with self.http(connection):
            prepared = self.transport.prepare(self.operation, self.call)
        self.assertNotIn("PREPARED-KEY-CANARY", repr(prepared))
        self.assertNotIn("PREPARED-BODY-CANARY", repr(prepared))
        connection.request.assert_not_called()
        connection.close()

    def test_concurrent_preparation_of_same_operation_sends_once(self):
        self.ledger.reserve(self.operation, self.call.fingerprint(), self.spec.reserve_microusd())
        initial = self.connection()
        with self.http(initial):
            self.transport.prepare(self.operation, self.call).close()
        connections = [self.connection(), self.connection()]
        barrier = Barrier(2, timeout=5)
        prepare = self.transport.prepare

        def synchronized(operation_id, call):
            prepared = prepare(operation_id, call)
            barrier.wait()
            return prepared

        def attempt():
            try:
                self.execute()
                return "completed"
            except PendingOperation:
                return "lost-dispatch"

        with (
            patch("buddha.provider.http.client.HTTPSConnection", side_effect=connections),
            patch.dict("os.environ", {"OPENAI_API_KEY": "PREPARED-KEY-CANARY"}),
            patch.object(self.transport, "prepare", side_effect=synchronized),
            ThreadPoolExecutor(max_workers=2) as pool,
        ):
            futures = [pool.submit(attempt) for _ in connections]
            self.assertCountEqual(
                [future.result(timeout=10) for future in futures],
                ["completed", "lost-dispatch"],
            )
        self.assertEqual(sum(connection.request.call_count for connection in connections), 1)
        for connection in connections:
            connection.close.assert_called_once()
        summary = self.authority.summary()
        self.assertEqual(summary["operation_count"], 1)
        self.assertEqual(summary["spent_microusd"], 11)
        self.assertEqual(summary["reserved_microusd"], 0)

    def test_one_transport_keeps_sequential_prepared_calls_separate(self):
        second_body = json.loads(self.call.body_json)
        second_body["messages"][0]["content"] = "SECOND-BODY-CANARY"
        second_call = Call(self.spec, json.dumps(second_body))
        connections = [self.connection(), self.connection()]
        with (
            patch("buddha.provider.http.client.HTTPSConnection", side_effect=connections),
            patch.dict("os.environ", {"OPENAI_API_KEY": "PREPARED-KEY-CANARY"}),
        ):
            broker = BudgetBroker(self.ledger, self.transport)
            broker.execute(self.operation, self.call)
            broker.execute("b" * 64, second_call)
        for operation, call, connection in zip(
            (self.operation, "b" * 64), (self.call, second_call), connections, strict=True
        ):
            record = json.loads(
                (self.directory / "diagnostics" / operation / "request.json").read_bytes()
            )
            self.assertEqual(connection.request.call_args.kwargs["body"], call.body_json.encode())
            self.assertEqual(record["request_sha256"], call.fingerprint())
            self.assertEqual(
                connection.request.call_args.kwargs["headers"]["X-Client-Request-Id"],
                record["client_request_id"],
            )
            connection.close.assert_called_once()
        self.assertEqual(self.authority.summary()["operation_count"], 2)
        self.assertEqual(self.authority.summary()["spent_microusd"], 22)


if __name__ == "__main__":
    unittest.main()
