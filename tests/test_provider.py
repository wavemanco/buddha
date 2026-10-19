"""Paid-call boundaries exercised without SDKs, credentials, or network."""

import json
import unittest
from dataclasses import replace
from pathlib import Path
from tempfile import TemporaryDirectory
from types import SimpleNamespace
from unittest.mock import Mock, patch

from buddha.evaluation import ValidationError
from buddha.ledger import BudgetExceeded, Ledger
from buddha.provider import (
    BoundBreach,
    BudgetBroker,
    Call,
    HTTPTransport,
    ModelSpec,
    PendingOperation,
    ProviderUncertain,
    Reply,
)


def spec(**changes):
    values = dict(
        provider="openai",
        model="test-model",
        input_token_ceiling=100,
        max_output_tokens=10,
        input_microusd_per_million=1_000_000,
        output_microusd_per_million=2_000_000,
        bounds_source="https://example.org/verified-maximums",
    )
    return ModelSpec(**(values | changes))


def call(selected=None, **changes):
    selected = selected or spec()
    body = {
        "model": selected.model,
        "messages": [{"role": "user", "content": "hello"}],
        "max_tokens": selected.max_output_tokens,
        "service_tier": "standard_only" if selected.provider == "anthropic" else "default",
    }
    return Call(selected, json.dumps(body | changes))


def reply(**changes):
    return Reply(
        **(
            dict(
                text="{malformed judge JSON",
                model="test-model",
                provider_request_id="req-test",
                input_tokens=5,
                output_tokens=3,
                finish_reason="stop",
            )
            | changes
        )
    )


class MemoryLedger:
    def __init__(self):
        self.operation = None

    def reserve(self, operation_id, request_sha256, reserve_microusd):
        if self.operation is None:
            self.operation = SimpleNamespace(
                operation_id=operation_id,
                request_sha256=request_sha256,
                reserve_microusd=reserve_microusd,
                status="reserved",
                response=None,
                actual_microusd=None,
                provider_request_id=None,
            )
        return self.operation

    def get(self, operation_id):
        return self.operation

    def dispatch(self, operation_id):
        if self.operation.status != "reserved":
            return False
        self.operation.status = "dispatched"
        return True

    def complete(self, operation_id, *, response, actual_microusd, provider_request_id):
        self.operation.status = "completed"
        self.operation.response = response
        self.operation.actual_microusd = actual_microusd
        self.operation.provider_request_id = provider_request_id
        return self.operation

    def mark_unknown(self, operation_id, *, response=None, provider_request_id=None):
        self.operation.status = "unknown"
        if response is not None:
            self.operation.response = response
            self.operation.provider_request_id = provider_request_id


class ProviderTests(unittest.TestCase):
    def test_bounds_are_strict_and_rounded_up(self):
        self.assertEqual(spec().reserve_microusd(), 120)
        self.assertEqual(
            spec(input_microusd_per_million=1, output_microusd_per_million=1).reserve_microusd(), 1
        )
        for changes in (
            {"input_token_ceiling": True},
            {"max_output_tokens": 0},
            {"input_microusd_per_million": 0},
            {"provider": "other"},
            {"bounds_source": "http://example.org"},
            {"provider": []},
        ):
            with self.subTest(changes=changes), self.assertRaises(ValidationError):
                spec(**changes)

    def test_call_fingerprint_canonicalizes_and_binds_bounds(self):
        first = call()
        reordered = Call(first.spec, json.dumps(json.loads(first.body_json), indent=2))
        self.assertEqual(first.fingerprint(), reordered.fingerprint())
        changed = replace(first.spec, max_output_tokens=11)
        self.assertNotEqual(first.fingerprint(), call(changed).fingerprint())

    def test_request_boundary_rejects_hidden_paid_features(self):
        for changes in (
            {"max_tokens": 9},
            {"model": "different"},
            {"n": 2},
            {"stream": True},
            {"tools": []},
            {"service_tier": "priority"},
            {"messages": [{"role": "tool", "content": "x"}]},
        ):
            with self.subTest(changes=changes), self.assertRaises(ValidationError):
                call(**changes)
        with self.assertRaises(ValidationError):
            Call(spec(), '{"model":"x","model":"test-model"}')

    def test_live_requests_cannot_inherit_project_pricing_tier(self):
        body = json.loads(call().body_json)
        del body["service_tier"]
        with self.assertRaises(ValidationError):
            Call(spec(), json.dumps(body))
        for tier in ("auto", "priority", "fast", "flex"):
            with self.subTest(tier=tier), self.assertRaises(ValidationError):
                call(service_tier=tier)

    def test_completed_malformed_judgment_is_billed_and_replayed(self):
        ledger = MemoryLedger()
        transport = Mock()
        transport.send.return_value = reply()
        broker = BudgetBroker(ledger, transport)
        result = broker.execute("op", call())
        self.assertEqual(result.text, "{malformed judge JSON")
        self.assertEqual(ledger.operation.status, "completed")
        self.assertEqual(ledger.operation.actual_microusd, 11)
        self.assertEqual(broker.execute("op", call()), result)
        transport.send.assert_called_once()

    def test_timeout_keeps_unknown_liability_and_never_retries(self):
        ledger = MemoryLedger()
        transport = Mock()
        transport.send.side_effect = TimeoutError("secret-sentinel")
        broker = BudgetBroker(ledger, transport)
        with self.assertRaises(ProviderUncertain) as error:
            broker.execute("op", call())
        self.assertNotIn("secret-sentinel", str(error.exception))
        self.assertEqual(ledger.operation.status, "unknown")
        self.assertEqual(ledger.operation.reserve_microusd, 120)
        with self.assertRaises(PendingOperation):
            broker.execute("op", call())
        transport.send.assert_called_once()

    def test_interruption_is_unknown(self):
        ledger = MemoryLedger()
        transport = Mock()
        transport.send.side_effect = KeyboardInterrupt
        with self.assertRaises(KeyboardInterrupt):
            BudgetBroker(ledger, transport).execute("op", call())
        self.assertEqual(ledger.operation.status, "unknown")

    def test_durable_ledger_reopens_without_second_dispatch(self):
        with TemporaryDirectory() as directory:
            path = Path(directory) / "ledger.sqlite"
            settings = dict(
                run_id="test", manifest_sha256="a" * 64, budget_microusd=1000, max_calls=3
            )
            transport = Mock()
            transport.send.return_value = reply()
            expected = BudgetBroker(Ledger(path, **settings), transport).execute("op", call())
            reopened = Ledger(path, **settings)
            self.assertEqual(BudgetBroker(reopened, transport).execute("op", call()), expected)
            self.assertEqual(reopened.totals()["spent_microusd"], 11)
            transport.send.assert_called_once()

    def test_cost_overrun_is_durable_before_ledger_rejects_it(self):
        with TemporaryDirectory() as directory:
            ledger = Ledger(
                Path(directory) / "ledger.sqlite",
                run_id="test",
                manifest_sha256="b" * 64,
                budget_microusd=1000,
                max_calls=3,
            )
            transport = Mock()
            transport.send.return_value = reply(input_tokens=200, output_tokens=0)
            with self.assertRaises(BudgetExceeded):
                BudgetBroker(ledger, transport).execute("op", call())
            self.assertEqual(ledger.get("op").status, "completed")
            self.assertEqual(ledger.totals()["spent_microusd"], 200)

    def test_token_bound_breach_is_billed_even_below_reserved_cost(self):
        ledger = MemoryLedger()
        transport = Mock()
        transport.send.return_value = reply(input_tokens=101, output_tokens=0)
        broker = BudgetBroker(ledger, transport)
        with self.assertRaises(BoundBreach):
            broker.execute("op", call())
        self.assertEqual(ledger.operation.status, "completed")
        self.assertEqual(ledger.operation.actual_microusd, 101)
        with self.assertRaises(BoundBreach):
            broker.execute("op", call())
        transport.send.assert_called_once()

    def test_unexpected_pricing_tier_holds_reservation_and_preserves_receipt(self):
        ledger = MemoryLedger()
        transport = Mock()
        transport.send.return_value = reply(service_tier="priority")
        broker = BudgetBroker(ledger, transport)
        with self.assertRaises(BoundBreach):
            broker.execute("op", call())
        with self.assertRaises(PendingOperation):
            broker.execute("op", call())
        self.assertEqual(ledger.operation.status, "unknown")
        self.assertEqual(ledger.operation.response["service_tier"], "priority")
        self.assertIsNone(ledger.operation.actual_microusd)
        self.assertEqual(ledger.operation.reserve_microusd, 120)
        transport.send.assert_called_once()

    def test_unexpected_tier_receipt_is_durable_in_real_ledger(self):
        with TemporaryDirectory() as directory:
            path = Path(directory) / "ledger.sqlite"
            settings = dict(
                run_id="test", manifest_sha256="c" * 64, budget_microusd=1000, max_calls=3
            )
            transport = Mock()
            transport.send.return_value = reply(service_tier="priority", provider_request_id="")
            with self.assertRaises(BoundBreach):
                BudgetBroker(Ledger(path, **settings), transport).execute("op", call())
            ledger = Ledger(path, **settings)
            self.assertEqual(ledger.get("op").status, "unknown")
            self.assertEqual(ledger.get("op").response["service_tier"], "priority")
            self.assertEqual(ledger.totals()["reserved_microusd"], 120)
            self.assertEqual(ledger.totals()["spent_microusd"], 0)
            with self.assertRaises(PendingOperation):
                BudgetBroker(ledger, transport).execute("op", call())
            transport.send.assert_called_once()

    def test_unmapped_response_model_keeps_unknown_receipt_and_liability(self):
        ledger = MemoryLedger()
        transport = Mock()
        transport.send.return_value = reply(model="different-priced-model")
        broker = BudgetBroker(ledger, transport)
        with self.assertRaises(BoundBreach):
            broker.execute("op", call())
        self.assertEqual(ledger.operation.status, "unknown")
        self.assertEqual(ledger.operation.response["model"], "different-priced-model")
        self.assertIsNone(ledger.operation.actual_microusd)
        with self.assertRaises(PendingOperation):
            broker.execute("op", call())
        transport.send.assert_called_once()

    def test_missing_provider_id_keeps_the_received_response(self):
        ledger = MemoryLedger()
        transport = Mock()
        transport.send.return_value = reply(provider_request_id="")
        with self.assertRaises(BoundBreach):
            BudgetBroker(ledger, transport).execute("op", call())
        self.assertEqual(ledger.operation.status, "unknown")
        self.assertEqual(ledger.operation.response["text"], reply().text)
        self.assertIsNone(ledger.operation.actual_microusd)

    def test_paid_dispatch_is_explicit(self):
        with self.assertRaises(ValidationError):
            HTTPTransport().send(call())

    def test_missing_credential_fails_before_reservation_or_dispatch(self):
        ledger = MemoryLedger()
        with (
            patch.dict("os.environ", {}, clear=True),
            patch("buddha.provider.http.client.HTTPSConnection") as connection,
        ):
            with self.assertRaises(ValidationError):
                BudgetBroker(ledger, HTTPTransport(allow_paid=True)).execute("op", call())
        self.assertIsNone(ledger.operation)
        connection.assert_not_called()

    def test_completed_http_replay_requires_no_credentials_or_live_permission(self):
        ledger = MemoryLedger()
        transport = Mock()
        transport.send.return_value = reply()
        expected = BudgetBroker(ledger, transport).execute("op", call())
        with (
            patch.dict("os.environ", {}, clear=True),
            patch("buddha.provider.http.client.HTTPSConnection") as connection,
        ):
            actual = BudgetBroker(ledger, HTTPTransport()).execute("op", call())
        self.assertEqual(actual, expected)
        connection.assert_not_called()

    def send_envelope(self, envelope, selected=None):
        response = Mock(status=200)
        response.read.return_value = json.dumps(envelope).encode()
        response.getheader.return_value = "req-test"
        connection = Mock()
        connection.getresponse.return_value = response
        with (
            patch("buddha.provider.http.client.HTTPSConnection", return_value=connection),
            patch.dict(
                "os.environ",
                {"OPENAI_API_KEY": "secret-sentinel", "ANTHROPIC_API_KEY": "secret-sentinel"},
            ),
        ):
            result = HTTPTransport(allow_paid=True).send(call(selected))
        connection.request.assert_called_once()
        return result, connection

    def test_openai_inclusive_usage_and_reasoning_are_not_double_counted(self):
        result, connection = self.send_envelope(
            {
                "model": "test-model",
                "usage": {
                    "prompt_tokens": 30,
                    "completion_tokens": 10,
                    "prompt_tokens_details": {"cached_tokens": 12, "cache_write_tokens": 8},
                    "completion_tokens_details": {"reasoning_tokens": 6},
                },
                "choices": [{"finish_reason": "stop", "message": {"content": "ok"}}],
            }
        )
        self.assertEqual((result.input_tokens, result.output_tokens), (30, 10))
        self.assertEqual(connection.request.call_args.args[:2], ("POST", "/v1/chat/completions"))

    def test_anthropic_adds_disjoint_input_usage_and_preserves_refusal(self):
        result, connection = self.send_envelope(
            {
                "model": "test-model",
                "stop_reason": "refusal",
                "content": [],
                "usage": {
                    "input_tokens": 3,
                    "cache_creation_input_tokens": 4,
                    "cache_read_input_tokens": 5,
                    "output_tokens": 10,
                },
            },
            spec(provider="anthropic"),
        )
        self.assertEqual((result.input_tokens, result.output_tokens), (12, 10))
        self.assertTrue(result.refused)
        self.assertEqual(connection.request.call_args.args[:2], ("POST", "/v1/messages"))

    def test_missing_usage_and_network_errors_are_sanitized(self):
        for envelope in (
            {"error": {"message": "secret-sentinel"}},
            {"usage": {"prompt_tokens": True, "completion_tokens": 1}},
        ):
            with self.subTest(envelope=envelope), self.assertRaises(ProviderUncertain) as error:
                self.send_envelope(envelope)
            self.assertNotIn("secret-sentinel", str(error.exception))
        with (
            patch(
                "buddha.provider.http.client.HTTPSConnection",
                side_effect=OSError("secret-sentinel"),
            ),
            patch.dict("os.environ", {"OPENAI_API_KEY": "key"}),
        ):
            with self.assertRaises(ProviderUncertain) as error:
                HTTPTransport(allow_paid=True).send(call())
        self.assertNotIn("secret-sentinel", str(error.exception))

    def test_socket_timeout_attempts_exactly_once_and_does_not_log_secrets(self):
        connection = Mock()
        connection.getresponse.side_effect = TimeoutError("secret-sentinel")
        with (
            patch("buddha.provider.http.client.HTTPSConnection", return_value=connection),
            patch.dict("os.environ", {"OPENAI_API_KEY": "secret-sentinel"}),
            patch("builtins.print") as printed,
        ):
            with self.assertRaises(ProviderUncertain) as error:
                HTTPTransport(allow_paid=True).send(call())
        connection.request.assert_called_once()
        connection.close.assert_called_once()
        printed.assert_not_called()
        self.assertNotIn("secret-sentinel", str(error.exception))

    def test_reply_record_is_strict(self):
        self.assertEqual(Reply.from_record(reply().to_record()), reply())
        with self.assertRaises(ValidationError):
            Reply.from_record(reply().to_record() | {"output_tokens": True})


if __name__ == "__main__":
    unittest.main()
