"""Retained uncertainty evidence survives a legal terminal Ledger transition."""

import hashlib
import sqlite3
import tempfile
import unittest
from contextlib import closing
from dataclasses import FrozenInstanceError
from pathlib import Path
from unittest.mock import patch

import test_history as history_fixtures

from buddha.authorization import Authorization
from buddha.common import ValidationError, _canonical, _parse
from buddha.history import read_history
from buddha.ledger import _SCHEMA as LEDGER_SCHEMA
from buddha.ledger import (
    BudgetExceeded,
    Ledger,
    OperationConflict,
    _expected_schema,
    _schema_signature,
)
from buddha.provider import Reply


class ReconciledHistoryTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)
        self.directory = self.root / "historical"
        self.directory.mkdir()
        self.path = self.directory / "operations.sqlite3"
        manifest = {
            "format": "buddha.policy-search.v1",
            "run_id": "retained-receipt-run",
            "settings": {"budget_microusd": 10_000, "max_calls": 8},
        }
        self.manifest_hash = hashlib.sha256(_canonical(manifest)).hexdigest()
        (self.directory / "manifest.json").write_bytes(
            _canonical(manifest | {"record_sha256": self.manifest_hash}) + b"\n"
        )
        self.ledger = Ledger(
            self.path,
            run_id=manifest["run_id"],
            manifest_sha256=self.manifest_hash,
            budget_microusd=10_000,
            max_calls=8,
        )
        self.operation_id = "received-then-completed"
        self.ledger.reserve(self.operation_id, hashlib.sha256(b"request").hexdigest(), 900)
        self.ledger.dispatch(self.operation_id)
        self.earlier = Reply("uncertain text", "unexpected-model", "body-id", 20, 30, "stop")
        self.terminal = Reply(
            "verified terminal text", "expected-model", "final-id", 21, 31, "stop"
        )

    def unknown(self, *, response=True, request_id="header-id"):
        self.ledger.mark_unknown(
            self.operation_id,
            response=self.earlier.to_record() if response else None,
            provider_request_id=request_id,
        )

    def complete(self, actual=123):
        self.ledger.complete(
            self.operation_id,
            response=self.terminal.to_record(),
            actual_microusd=actual,
            provider_request_id=self.terminal.provider_request_id,
        )

    def seal(self):
        return hashlib.sha256(self.path.read_bytes()).hexdigest()

    def read(self):
        return read_history(
            self.directory, manifest_sha256=self.manifest_hash, ledger_sha256=self.seal()
        )

    def files(self):
        return {
            str(path.relative_to(self.directory)): path.read_bytes()
            for path in self.directory.rglob("*")
            if path.is_file()
        }

    def authority(self):
        return Authorization.create(
            self.root / "authorization.sqlite3",
            authorization_id="test-only",
            budget_microusd=10_000,
            max_calls=8,
            scope="offline terminal history import",
        )

    def corrupt(self, sql, arguments=()):
        """Mutate fixture data while restoring the central helper's native DDL."""
        history_fixtures.HistoryTests.corrupt(self, sql, arguments)

    def test_native_completed_transition_exposes_both_receipts_without_writes(self):
        self.unknown()
        self.complete()
        before = self.files()
        history = self.read()
        (operation,) = history.operations
        self.assertEqual(operation.status, "completed")
        self.assertEqual(operation.reply, self.terminal)
        self.assertEqual(operation.provider_request_id, "final-id")
        self.assertEqual(operation.actual_microusd, 123)
        self.assertEqual(operation.uncertainty_reply, self.earlier)
        # Contradictory earlier identities remain evidence, not a terminal identity claim.
        self.assertEqual(operation.uncertainty_request_id, "header-id")
        self.assertNotEqual(
            operation.uncertainty_reply.provider_request_id, operation.uncertainty_request_id
        )
        self.assertEqual(
            history.totals(),
            {
                "committed_microusd": 123,
                "spent_microusd": 123,
                "reserved_microusd": 0,
                "operation_count": 1,
            },
        )
        for instance, attribute in [
            (operation, "uncertainty_reply"),
            (operation, "uncertainty_request_id"),
            (operation.uncertainty_reply, "text"),
        ]:
            with self.subTest(attribute=attribute), self.assertRaises(FrozenInstanceError):
                setattr(instance, attribute, None)
        self.assertEqual(before, self.files())

    def test_id_only_and_response_only_retained_receipts_survive_completion(self):
        original = self.path.read_bytes()
        for response, request_id in [(False, "header-only"), (True, None)]:
            with self.subTest(response=response):
                self.path.write_bytes(original)
                self.unknown(response=response, request_id=request_id)
                self.complete(actual=0)
                before = self.files()
                (operation,) = self.read().operations
                self.assertEqual(operation.uncertainty_reply, self.earlier if response else None)
                self.assertEqual(operation.uncertainty_request_id, request_id)
                self.assertEqual(operation.actual_microusd, 0)
                self.assertEqual(before, self.files())

    def test_native_retained_evidence_stays_immutable_and_terminal_replay_is_idempotent(self):
        self.unknown()
        self.complete()
        before = self.files()
        with self.assertRaises(OperationConflict):
            self.ledger.mark_unknown(self.operation_id, provider_request_id="replacement-id")
        with closing(sqlite3.connect(self.path)) as connection, connection:
            with self.assertRaises(sqlite3.IntegrityError):
                connection.execute(
                    "UPDATE unknown_receipts SET provider_request_id='replacement-id'"
                )
        self.complete()
        self.assertEqual(self.read().operations[0].uncertainty_reply, self.earlier)
        self.assertEqual(before, self.files())

    def test_unknown_exposes_retained_evidence_without_changing_existing_fields(self):
        self.unknown()
        before = self.files()
        history = self.read()
        (operation,) = history.operations
        self.assertEqual(operation.reply, self.earlier)
        self.assertEqual(operation.provider_request_id, "header-id")
        self.assertIsNone(operation.actual_microusd)
        self.assertEqual(operation.uncertainty_reply, operation.reply)
        self.assertEqual(operation.uncertainty_request_id, operation.provider_request_id)
        self.assertEqual(history.totals()["reserved_microusd"], 900)
        self.assertEqual(before, self.files())

    def test_receiptless_unknown_and_plain_completion_have_no_retained_receipt(self):
        self.unknown(response=False, request_id=None)
        (unknown,) = self.read().operations
        self.assertIsNone(unknown.uncertainty_reply)
        self.assertIsNone(unknown.uncertainty_request_id)
        self.complete()
        (completed,) = self.read().operations
        self.assertIsNone(completed.uncertainty_reply)
        self.assertIsNone(completed.uncertainty_request_id)
        self.assertEqual(completed.reply, self.terminal)

    def test_schema_one_completion_has_no_retained_receipt_or_migration(self):
        self.complete()
        self.corrupt("DROP TABLE unknown_receipts")
        self.corrupt("PRAGMA user_version=1")
        with closing(sqlite3.connect(self.path)) as connection:
            self.assertEqual(_schema_signature(connection), _expected_schema(tuple(LEDGER_SCHEMA)))
        before = self.files()
        (operation,) = self.read().operations
        self.assertIsNone(operation.uncertainty_reply)
        self.assertIsNone(operation.uncertainty_request_id)
        self.assertEqual(operation.reply, self.terminal)
        self.assertEqual(before, self.files())

    def test_import_uses_one_terminal_charge_and_is_idempotent(self):
        self.unknown()
        self.complete()
        source_before = self.files()
        authority = self.authority()
        seals = {"manifest_sha256": self.manifest_hash, "ledger_sha256": self.seal()}
        authority.import_history(self.directory, **seals)
        first = authority.summary()
        self.assertEqual(first["spent_microusd"], 123)
        self.assertEqual(first["committed_microusd"], 123)
        self.assertEqual(first["reserved_microusd"], 0)
        self.assertEqual(first["operation_count"], 1)
        self.assertEqual(first["remaining_calls"], 7)
        self.assertEqual(first["available_microusd"], 9877)
        with closing(sqlite3.connect(authority.path)) as connection:
            (response, actual, request_id) = connection.execute(
                "SELECT response_json,actual_microusd,provider_request_id FROM auth_operations"
            ).fetchone()
        self.assertEqual(response, _canonical(self.terminal.to_record()).decode())
        self.assertEqual((actual, request_id), (123, "final-id"))
        authority_before = authority.path.read_bytes()
        authority.import_history(self.directory, **seals)
        self.assertEqual(first, authority.summary())
        self.assertEqual(authority_before, authority.path.read_bytes())
        self.assertEqual(source_before, self.files())
        self.assertEqual(self.read().operations[0].uncertainty_reply, self.earlier)

    def test_changed_source_seal_cannot_replace_prior_import_or_add_another_charge(self):
        self.unknown()
        self.complete()
        authority = self.authority()
        seals = {"manifest_sha256": self.manifest_hash, "ledger_sha256": self.seal()}
        authority.import_history(self.directory, **seals)
        first = authority.summary()
        authority_before = authority.path.read_bytes()
        # A new legal ledger operation changes the physical seal without altering DDL.
        # Import must refuse updating its existing historical binding automatically.
        self.ledger.reserve("later-standalone-operation", hashlib.sha256(b"later").hexdigest(), 10)
        self.assertNotEqual(self.seal(), seals["ledger_sha256"])
        source_before = self.files()
        with self.assertRaises(OperationConflict):
            authority.import_history(
                self.directory, manifest_sha256=self.manifest_hash, ledger_sha256=self.seal()
            )
        self.assertEqual(first, authority.summary())
        self.assertEqual(authority_before, authority.path.read_bytes())
        self.assertEqual(source_before, self.files())

    def test_retained_receipt_overrun_records_and_imports_true_terminal_charge_once(self):
        self.unknown()
        with self.assertRaises(BudgetExceeded):
            self.complete(actual=950)
        before = self.files()
        history = self.read()
        (operation,) = history.operations
        self.assertEqual(operation.reserve_microusd, 900)
        self.assertEqual(operation.actual_microusd, 950)
        self.assertEqual(operation.reply, self.terminal)
        self.assertEqual(operation.uncertainty_reply, self.earlier)
        self.assertEqual(
            history.totals(),
            {
                "committed_microusd": 950,
                "spent_microusd": 950,
                "reserved_microusd": 0,
                "operation_count": 1,
            },
        )
        authority = self.authority()
        authority.import_history(
            self.directory, manifest_sha256=self.manifest_hash, ledger_sha256=self.seal()
        )
        summary = authority.summary()
        self.assertEqual(summary["spent_microusd"], 950)
        self.assertEqual(summary["committed_microusd"], 950)
        self.assertEqual(summary["reserved_microusd"], 0)
        self.assertEqual(summary["operation_count"], 1)
        self.assertEqual(before, self.files())

    def test_malformed_or_empty_retained_receipts_rejected_even_after_completion(self):
        self.unknown()
        self.complete()
        original = self.path.read_bytes()
        for response, request_id in [
            ("{}", "header-id"),
            (None, None),
            ("not JSON", None),
            ('{"text":NaN}', "header-id"),
            ('{"text":1,"text":2}', "header-id"),
        ]:
            with self.subTest(response=response, request_id=request_id):
                self.path.write_bytes(original)
                self.corrupt(
                    "UPDATE unknown_receipts SET response_json=?,provider_request_id=?",
                    (response, request_id),
                )
                before = self.files()
                with patch("buddha.history._parse", wraps=_parse) as parser:
                    with self.assertRaises(ValidationError):
                        self.read()
                if response is not None:
                    # Prove malformed receipt data reached its parser under native DDL.
                    parser.assert_any_call(response.encode())
                self.assertEqual(before, self.files())

    def test_deep_manifest_or_retained_receipt_has_typed_error_without_source_or_auth_writes(self):
        self.unknown()
        self.complete()
        authority = self.authority()
        authority_before = authority.path.read_bytes()
        summary_before = authority.summary()
        manifest_path = self.directory / "manifest.json"
        original_manifest, original_ledger = manifest_path.read_bytes(), self.path.read_bytes()
        # About 40 KiB: well inside input bounds, beyond this CPython JSON decoder's depth.
        nested = "[" * 20_000 + "0" + "]" * 20_000
        for target in ("manifest", "earlier-receipt"):
            with self.subTest(target=target):
                manifest_path.write_bytes(original_manifest)
                self.path.write_bytes(original_ledger)
                if target == "manifest":
                    manifest_path.write_bytes(
                        original_manifest.rstrip()[:-1] + b',"depth":' + nested.encode() + b"}\n"
                    )
                else:
                    self.corrupt("UPDATE unknown_receipts SET response_json=?", (nested,))
                source_before = self.files()
                with self.assertRaises(ValidationError):
                    self.read()
                with self.assertRaises(ValidationError):
                    authority.import_history(
                        self.directory,
                        manifest_sha256=self.manifest_hash,
                        ledger_sha256=self.seal(),
                    )
                self.assertEqual(source_before, self.files())
                self.assertEqual(authority_before, authority.path.read_bytes())
                self.assertEqual(summary_before, authority.summary())

    def test_reserved_or_dispatched_retained_evidence_is_still_rejected(self):
        self.unknown()
        original = self.path.read_bytes()
        for status in ("reserved", "dispatched"):
            with self.subTest(status=status):
                self.path.write_bytes(original)
                self.corrupt("UPDATE operations SET status=?", (status,))
                with self.assertRaises(ValidationError):
                    self.read()

    def test_orphan_retained_receipt_is_still_rejected(self):
        self.unknown()
        self.complete()
        self.corrupt("DELETE FROM operations")
        with self.assertRaises(ValidationError):
            self.read()

    def test_terminal_identity_mismatch_remains_rejected_with_retained_evidence(self):
        self.unknown()
        self.complete()
        self.corrupt("UPDATE operations SET provider_request_id='wrong-terminal-id'")
        with self.assertRaises(ValidationError):
            self.read()


if __name__ == "__main__":
    unittest.main()
