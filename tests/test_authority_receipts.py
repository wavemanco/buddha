"""In-flight receipt evidence survives source drift without authorizing more work."""

import hashlib
import json
import sqlite3
import tempfile
import unittest
from contextlib import closing
from pathlib import Path
from unittest.mock import patch

from authorization_helpers import authorized_run

from buddha.authorization import runtime_fingerprint
from buddha.benchmark import _canonical
from buddha.evaluation import ValidationError
from buddha.ledger import Ledger
from buddha.provider import BudgetBroker, Call, ModelSpec, Reply


class AuthorityReceiptTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.directory = Path(temporary.name) / "active"
        self.authority, self.ledger = authorized_run(self.directory)
        self.call = Call(
            ModelSpec(
                "openai",
                "model",
                100,
                10,
                1_000_000,
                1_000_000,
                "https://example.org/offline-fixture",
            ),
            json.dumps(
                {
                    "model": "model",
                    "messages": [{"role": "user", "content": "test"}],
                    "max_completion_tokens": 10,
                    "service_tier": "default",
                }
            ),
        )

    def drift(self, kind):
        if kind == "runtime":
            replacement = patch("buddha.authorization.runtime_fingerprint", return_value="a" * 64)
            replacement.start()
            self.addCleanup(replacement.stop)
        else:
            path = self.directory / "manifest.json"
            manifest = json.loads(path.read_bytes())
            manifest.pop("record_sha256")
            manifest["changed_after_dispatch"] = True
            manifest["record_sha256"] = hashlib.sha256(_canonical(manifest)).hexdigest()
            path.write_bytes(_canonical(manifest) + b"\n")

    def stored(self):
        with closing(sqlite3.connect(self.directory / "operations.sqlite3")) as connection:
            return connection.execute(
                "SELECT status,actual_microusd,provider_request_id,response_json "
                "FROM operations WHERE operation_id='operation'"
            ).fetchone()

    def completed_after_drift(self, kind):
        owner = self

        class Transport:
            calls = 0

            def send(self, call):
                self.calls += 1
                owner.drift(kind)
                return Reply("answer", "model", "authentic-receipt", 1, 1, "stop")

        transport = Transport()
        reply = BudgetBroker(self.ledger, transport).execute("operation", self.call)
        self.assertEqual(reply.provider_request_id, "authentic-receipt")
        state, actual, request_id, response = self.stored()
        self.assertEqual((state, actual, request_id), ("completed", 2, "authentic-receipt"))
        self.assertEqual(json.loads(response), reply.to_record())
        self.assertEqual(self.authority.summary()["spent_microusd"], 2)
        with self.assertRaises(ValidationError):
            BudgetBroker(self.ledger, transport).execute("new-work", self.call)
        self.assertEqual(transport.calls, 1)

    def interrupted_after_drift(self, kind):
        owner = self

        class Transport:
            calls = 0

            def send(self, call):
                self.calls += 1
                owner.drift(kind)
                raise KeyboardInterrupt

        transport = Transport()
        with self.assertRaises(KeyboardInterrupt):
            BudgetBroker(self.ledger, transport).execute("operation", self.call)
        self.assertEqual(self.stored(), ("unknown", None, None, None))
        summary = self.authority.summary()
        self.assertEqual(summary["reserved_microusd"], self.call.spec.reserve_microusd())
        self.assertEqual(summary["spent_microusd"], 0)
        with self.assertRaises(ValidationError):
            BudgetBroker(self.ledger, transport).execute("new-work", self.call)
        self.assertEqual(transport.calls, 1)

    def test_returned_receipt_after_runtime_drift_is_recorded(self):
        self.completed_after_drift("runtime")

    def test_returned_receipt_after_manifest_drift_is_recorded(self):
        self.completed_after_drift("manifest")

    def test_interruption_after_runtime_drift_retains_unknown(self):
        self.interrupted_after_drift("runtime")

    def test_interruption_after_manifest_drift_retains_unknown(self):
        self.interrupted_after_drift("manifest")

    def reset_dispatch_trigger(self, directory):
        with closing(sqlite3.connect(directory / "operations.sqlite3")) as connection:
            connection.execute(
                "CREATE TRIGGER reset_dispatch AFTER UPDATE OF status ON operations "
                "WHEN NEW.status='dispatched' BEGIN UPDATE operations SET status='reserved' "
                "WHERE operation_id=NEW.operation_id; END"
            )
            connection.commit()

    def test_foreign_run_trigger_is_rejected_before_binding(self):
        directory = self.directory.parent / "unbound"
        directory.mkdir()
        manifest = {
            "format": "buddha.policy-search.v1",
            "run_id": "unbound",
            "settings": {"budget_microusd": 1000, "max_calls": 3},
        }
        digest = hashlib.sha256(_canonical(manifest)).hexdigest()
        (directory / "manifest.json").write_bytes(
            _canonical(manifest | {"record_sha256": digest}) + b"\n"
        )
        Ledger(
            directory / "operations.sqlite3",
            run_id="unbound",
            manifest_sha256=digest,
            budget_microusd=1000,
            max_calls=3,
        )
        self.reset_dispatch_trigger(directory)
        with self.assertRaises(ValidationError):
            self.authority.bind_run(directory, runtime_sha256=runtime_fingerprint())
        self.assertEqual(len(self.authority.summary()["runs"]), 1)
        with closing(sqlite3.connect(directory / "operations.sqlite3")) as connection:
            self.assertIsNone(
                connection.execute(
                    "SELECT 1 FROM sqlite_master WHERE name='authorization_binding'"
                ).fetchone()
            )

    def test_foreign_run_trigger_after_binding_is_rejected_before_send(self):
        self.reset_dispatch_trigger(self.directory)
        self.assert_schema_denial_before_send()
        self.assertEqual(self.authority.summary()["operation_count"], 0)

    def test_modified_authority_trigger_is_rejected_before_send(self):
        with closing(sqlite3.connect(self.authority.path)) as connection:
            connection.execute("DROP TRIGGER auth_operations_identity")
            connection.execute(
                "CREATE TRIGGER auth_operations_identity BEFORE UPDATE OF "
                "run_id,operation_id,request_sha256,reserve_microusd ON auth_operations "
                "BEGIN SELECT 1; END"
            )
            connection.commit()
        self.assert_schema_denial_before_send()

    def assert_schema_denial_before_send(self):
        class Transport:
            calls = 0

            def send(self, call):
                self.calls += 1
                return Reply("answer", "model", "receipt", 1, 1, "stop")

        transport = Transport()
        with self.assertRaises(ValidationError):
            BudgetBroker(self.ledger, transport).execute("operation", self.call)
        self.assertEqual(transport.calls, 0)


if __name__ == "__main__":
    unittest.main()
