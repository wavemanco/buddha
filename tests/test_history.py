"""Sealed historical snapshots never dispatch, migrate or alter source evidence."""

import hashlib
import json
import sqlite3
import tempfile
import unittest
from contextlib import closing
from dataclasses import FrozenInstanceError
from pathlib import Path
from unittest.mock import patch

from buddha.benchmark import _canonical
from buddha.evaluation import ValidationError
from buddha.history import read_history
from buddha.ledger import _SCHEMA as LEDGER_SCHEMA
from buddha.ledger import Ledger, _expected_schema, _schema_signature
from buddha.provider import Reply
from buddha.run import _sha


class HistoryTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.directory = Path(temporary.name) / "original"
        self.directory.mkdir()
        self.path = self.directory / "operations.sqlite3"
        self.manifest = {
            "format": "buddha.policy-search.v1",
            "run_id": "original-run",
            "settings": {"budget_microusd": 10_000_000, "max_calls": 128},
            "contracts": {"historical-source": "preserved, not current source"},
        }
        self.manifest_hash = _sha(self.manifest)
        self.write_manifest()
        self.ledger = Ledger(
            self.path,
            run_id=self.manifest["run_id"],
            manifest_sha256=self.manifest_hash,
            budget_microusd=10_000_000,
            max_calls=128,
        )
        self.ids = [hashlib.sha256(str(index).encode()).hexdigest() for index in range(10)]
        self.request_hash = hashlib.sha256(b"the exact request").hexdigest()
        for index, operation_id in enumerate(self.ids):
            self.ledger.reserve(operation_id, self.request_hash, 532373)
            self.ledger.dispatch(operation_id)
            if index < 9:
                reply = Reply(
                    f"Saved answer {index}",
                    "generator",
                    f"request-{index}",
                    20,
                    100,
                    "stop",
                    service_tier="default",
                )
                self.ledger.complete(
                    operation_id,
                    response=reply.to_record(),
                    actual_microusd=190,
                    provider_request_id=reply.provider_request_id,
                )
            else:
                self.ledger.mark_unknown(operation_id)

    def write_manifest(self):
        record = self.manifest | {"record_sha256": _sha(self.manifest)}
        (self.directory / "manifest.json").write_bytes(_canonical(record) + b"\n")

    def read(self, **changes):
        arguments = {
            "manifest_sha256": self.manifest_hash,
            "ledger_sha256": (
                hashlib.sha256(self.path.read_bytes()).hexdigest()
                if "ledger_sha256" not in changes
                else changes["ledger_sha256"]
            ),
        }
        arguments.update(changes)
        return read_history(self.directory, **arguments)

    def corrupt(self, sql, arguments=()):
        with closing(sqlite3.connect(self.path)) as connection, connection:
            triggers = connection.execute(
                "SELECT name,tbl_name,sql FROM sqlite_master WHERE type='trigger'"
            ).fetchall()
            for name, _, _ in triggers:
                connection.execute(f'DROP TRIGGER "{name}"')
            connection.execute("PRAGMA ignore_check_constraints=ON")
            connection.execute(sql, arguments)
            for _, table, statement in triggers:
                if connection.execute(
                    "SELECT 1 FROM sqlite_master WHERE type='table' AND name=?", (table,)
                ).fetchone():
                    connection.execute(statement)

    def files(self):
        return {
            str(path.relative_to(self.directory)): path.read_bytes()
            for path in self.directory.rglob("*")
            if path.is_file()
        }

    def test_nine_authentic_receipts_and_unknown_liability_are_read_without_writes(self):
        before = self.files()
        history = self.read()
        self.assertEqual(history.run_id, "original-run")
        self.assertEqual(history.manifest_sha256, self.manifest_hash)
        self.assertEqual(history.budget_microusd, 10_000_000)
        self.assertEqual(history.max_calls, 128)
        self.assertEqual(
            history.totals(),
            {
                "committed_microusd": 534083,
                "spent_microusd": 1710,
                "reserved_microusd": 532373,
                "operation_count": 10,
            },
        )
        by_id = {item.operation_id: item for item in history.operations}
        self.assertEqual(by_id[self.ids[0]].reply.text, "Saved answer 0")
        self.assertEqual(by_id[self.ids[0]].provider_request_id, "request-0")
        self.assertEqual(by_id[self.ids[0]].request_sha256, self.request_hash)
        self.assertEqual(by_id[self.ids[9]].status, "unknown")
        self.assertIsNone(by_id[self.ids[9]].reply)
        self.assertEqual(before, self.files())

    def test_nested_manifest_reply_operations_and_totals_are_immutable_or_defensive(self):
        history = self.read()
        history.manifest["settings"]["max_calls"] = 999
        self.assertEqual(history.manifest["settings"]["max_calls"], 128)
        history.totals()["reserved_microusd"] = 0
        self.assertEqual(history.totals()["reserved_microusd"], 532373)
        operation = next(item for item in history.operations if item.reply is not None)
        for instance, attribute, value in [
            (history, "run_id", "changed"),
            (operation, "status", "completed"),
            (operation.reply, "text", "changed"),
        ]:
            with self.subTest(attribute=attribute), self.assertRaises(FrozenInstanceError):
                setattr(instance, attribute, value)
        self.assertIsInstance(history.operations, tuple)

    def test_missing_database_is_not_created(self):
        self.path.unlink()
        before = self.files()
        with self.assertRaises(ValidationError):
            self.read(ledger_sha256="a" * 64)
        self.assertEqual(before, self.files())
        self.assertFalse(self.path.exists())

    def test_both_external_seals_and_manifest_record_checksum_are_required(self):
        for field in ("manifest_sha256", "ledger_sha256"):
            with self.subTest(field=field), self.assertRaises(ValidationError):
                self.read(**{field: "a" * 64})
        record = json.loads((self.directory / "manifest.json").read_bytes())
        record["contracts"]["historical-source"] = "tampered"
        (self.directory / "manifest.json").write_text(json.dumps(record))
        with self.assertRaises(ValidationError):
            self.read()

    def test_configuration_must_match_sealed_manifest_identity_and_caps(self):
        for field, value in [
            ("run_id", "another-run"),
            ("manifest_sha256", "a" * 64),
            ("budget_microusd", 999),
            ("max_calls", 127),
        ]:
            with self.subTest(field=field):
                original = self.path.read_bytes()
                self.corrupt(f"UPDATE run_config SET {field}=?", (value,))
                with self.assertRaises(ValidationError):
                    self.read()
                self.path.write_bytes(original)

    def test_foreign_and_unsupported_schema_are_rejected(self):
        self.corrupt("PRAGMA user_version=77")
        with self.assertRaises(ValidationError):
            self.read()
        self.path.unlink()
        with closing(sqlite3.connect(self.path)) as connection, connection:
            connection.execute("CREATE TABLE foreign_data (value TEXT)")
            connection.execute("PRAGMA user_version=2")
        with self.assertRaises(ValidationError):
            self.read()

    def test_schema_one_snapshot_is_read_without_upgrade(self):
        self.corrupt("DROP TABLE unknown_receipts")
        with closing(sqlite3.connect(self.path)) as connection, connection:
            connection.execute("PRAGMA user_version=1")
            self.assertEqual(_schema_signature(connection), _expected_schema(tuple(LEDGER_SCHEMA)))
        before = self.files()
        self.assertEqual(self.read().totals()["operation_count"], 10)
        self.assertEqual(before, self.files())

    def test_completed_receipt_and_ledger_request_identity_must_agree(self):
        self.corrupt(
            "UPDATE operations SET provider_request_id='other' WHERE operation_id=?", (self.ids[0],)
        )
        with self.assertRaises(ValidationError):
            self.read()

    def test_malformed_completed_receipt_is_rejected(self):
        for response in ['{"text":"not a full reply"}', '{"text":NaN}', '{"text":1,"text":2}']:
            with self.subTest(response=response):
                original = self.path.read_bytes()
                self.corrupt(
                    "UPDATE operations SET response_json=? WHERE operation_id=?",
                    (response, self.ids[0]),
                )
                with self.assertRaises(ValidationError):
                    self.read()
                self.path.write_bytes(original)

    def test_invalid_operation_fields_fail_even_with_resealed_file(self):
        for field, value in [
            ("request_sha256", "invalid"),
            ("response_json", None),
            ("status", "failed"),
            ("reserve_microusd", -1),
        ]:
            with self.subTest(field=field):
                original = self.path.read_bytes()
                self.corrupt(
                    f"UPDATE operations SET {field}=? WHERE operation_id=?", (value, self.ids[0])
                )
                with self.assertRaises(ValidationError):
                    self.read()
                self.path.write_bytes(original)

    def test_reserved_and_dispatched_work_remains_held(self):
        for index, dispatch in [(10, False), (11, True)]:
            operation_id = hashlib.sha256(str(index).encode()).hexdigest()
            self.ledger.reserve(operation_id, self.request_hash, 20)
            if dispatch:
                self.ledger.dispatch(operation_id)
        history = self.read()
        self.assertEqual(history.totals()["reserved_microusd"], 532413)
        self.assertEqual(
            {item.status for item in history.operations},
            {"reserved", "dispatched", "completed", "unknown"},
        )

    def test_unknown_mismatched_receipt_remains_evidence_and_reserved_liability(self):
        reply = Reply("uncertain answer", "unexpected-model", "reply-id", 1, 2, "stop")
        self.ledger.mark_unknown(
            self.ids[9], response=reply.to_record(), provider_request_id="different-ledger-id"
        )
        history = self.read()
        operation = next(item for item in history.operations if item.operation_id == self.ids[9])
        self.assertEqual(operation.reply, reply)
        self.assertEqual(operation.provider_request_id, "different-ledger-id")
        self.assertIsNone(operation.actual_microusd)
        self.assertEqual(history.totals()["reserved_microusd"], 532373)

    def test_active_search_lock_and_nonempty_sqlite_sidecars_prevent_sealing(self):
        for name in (".search.lock", "operations.sqlite3-wal", "operations.sqlite3-journal"):
            with self.subTest(name=name):
                sidecar = self.directory / name
                sidecar.write_bytes(b"potentially active")
                before = self.files()
                with self.assertRaises(ValidationError):
                    self.read()
                self.assertEqual(before, self.files())
                sidecar.unlink()

    def test_source_symlink_is_rejected_without_following_it(self):
        target = self.directory.parent / "linked"
        try:
            target.symlink_to(self.directory, target_is_directory=True)
        except OSError:
            self.skipTest("host does not permit creating symlinks")
        with self.assertRaises(ValidationError):
            read_history(
                target,
                manifest_sha256=self.manifest_hash,
                ledger_sha256=hashlib.sha256(self.path.read_bytes()).hexdigest(),
            )

    def test_change_during_read_is_rejected(self):
        import buddha.history as history_module

        original = history_module.Reply.from_record

        def alter_after_read(record):
            result = original(record)
            with self.path.open("ab") as stream:
                stream.write(b"changed during observation")
            return result

        with patch.object(history_module.Reply, "from_record", side_effect=alter_after_read):
            with self.assertRaises(ValidationError):
                self.read()


if __name__ == "__main__":
    unittest.main()
