"""Current paid entry points cannot bypass shared authority or prompt for keys first."""

import io
import json
import tempfile
import unittest
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path
from unittest.mock import Mock, patch

from buddha.__main__ import main
from buddha.evaluation import ValidationError
from buddha.ledger import Ledger
from buddha.provider import BudgetBroker, Call, HTTPTransport, ModelSpec, Reply


class PaidAuthorityTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.directory = Path(temporary.name)
        self.ledger = Ledger(
            self.directory / "operations.sqlite3",
            run_id="unbound",
            manifest_sha256="a" * 64,
            budget_microusd=1000,
            max_calls=10,
        )
        spec = ModelSpec(
            "openai",
            "test-model",
            100,
            10,
            1_000_000,
            1_000_000,
            "https://example.org/offline-fixture",
        )
        self.call = Call(
            spec,
            json.dumps(
                {
                    "model": "test-model",
                    "messages": [{"role": "user", "content": "offline canary"}],
                    "max_tokens": 10,
                    "service_tier": "default",
                }
            ),
        )

    def test_unbound_http_broker_fails_before_credentials_or_reservation(self):
        with patch.object(HTTPTransport, "preflight") as preflight:
            with self.assertRaises(ValidationError):
                BudgetBroker(self.ledger, HTTPTransport(allow_paid=True))
        preflight.assert_not_called()
        self.assertEqual(self.ledger.totals()["operation_count"], 0)

    def test_custom_transport_cannot_bypass_authority_for_new_live_model_call(self):
        transport = Mock()
        with self.assertRaises(ValidationError):
            BudgetBroker(self.ledger, transport).execute("operation", self.call)
        transport.send.assert_not_called()
        self.assertEqual(self.ledger.totals()["operation_count"], 0)

    def test_offline_completed_receipt_replay_needs_no_paid_authority(self):
        reply = Reply("saved", "test-model", "request", 2, 3, "stop")
        self.ledger.reserve("operation", self.call.fingerprint(), self.call.spec.reserve_microusd())
        self.ledger.dispatch("operation")
        self.ledger.complete(
            "operation",
            response=reply.to_record(),
            actual_microusd=5,
            provider_request_id="request",
        )
        before = self.ledger.events()
        transport = Mock()
        result = BudgetBroker(self.ledger, transport).execute("operation", self.call)
        self.assertEqual(result, reply)
        transport.send.assert_not_called()
        self.assertEqual(self.ledger.events(), before)

    def test_missing_cli_authority_fails_before_source_loading_or_key_prompt(self):
        for command in ("run", "search-run"):
            with self.subTest(command=command):
                output = io.StringIO()
                with (
                    redirect_stdout(output),
                    redirect_stderr(io.StringIO()),
                    patch("buddha.__main__._key_environment") as keys,
                    patch("buddha.__main__.load_run") as load_baseline,
                    patch("buddha.search.load_search") as load_search,
                ):
                    result = main(
                        [
                            command,
                            "--run",
                            str(self.directory / "missing"),
                            "--live",
                            "--prompt-keys",
                        ]
                    )
                self.assertEqual(result, 2)
                self.assertIn("authorization", json.loads(output.getvalue())["error"])
                keys.assert_not_called()
                load_baseline.assert_not_called()
                load_search.assert_not_called()

    def test_missing_authority_database_is_not_created_and_keys_are_not_requested(self):
        missing = self.directory / "missing-authorization.sqlite3"
        output = io.StringIO()
        with (
            redirect_stdout(output),
            redirect_stderr(io.StringIO()),
            patch("buddha.__main__._key_environment") as keys,
        ):
            result = main(
                [
                    "search-run",
                    "--run",
                    str(self.directory / "missing"),
                    "--live",
                    "--prompt-keys",
                    "--authorization",
                    str(missing),
                ]
            )
        self.assertEqual(result, 2)
        self.assertIn("authorization", json.loads(output.getvalue())["error"])
        self.assertFalse(missing.exists())
        keys.assert_not_called()


if __name__ == "__main__":
    unittest.main()
