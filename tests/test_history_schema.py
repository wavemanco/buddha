"""Only exact native legacy ledger schemas are admissible sealed history."""

import hashlib
import sqlite3
import unittest
from contextlib import closing
from unittest.mock import patch

import test_history

import buddha.history as history_module
from buddha.authorization import _BINDING_SCHEMA, Authorization
from buddha.common import ValidationError
from buddha.ledger import _SCHEMA as LEDGER_SCHEMA
from buddha.ledger import _SCHEMA_V2 as LEDGER_SCHEMA_V2
from buddha.ledger import Ledger, _expected_schema, _schema_signature


class HistorySchemaTests(unittest.TestCase):
    setUp = test_history.HistoryTests.setUp
    write_manifest = test_history.HistoryTests.write_manifest
    read = test_history.HistoryTests.read
    corrupt = test_history.HistoryTests.corrupt
    files = test_history.HistoryTests.files

    def mutate_schema(self, *statements):
        with closing(sqlite3.connect(self.path)) as connection, connection:
            for statement in statements:
                connection.execute(statement)

    def add_binding(self):
        """Native optional DDL; its absent authority stays opaque historical data."""
        with closing(sqlite3.connect(self.path)) as connection, connection:
            for statement in _BINDING_SCHEMA:
                connection.execute(statement)
            connection.execute(
                "INSERT INTO authorization_binding VALUES (1,1,?,?,?)",
                (
                    "former-authority",
                    str(self.directory.parent / "absent-authority.sqlite3"),
                    "a" * 64,
                ),
            )

    def test_benign_view_in_place_of_operations_is_rejected_without_writes(self):
        self.mutate_schema(
            "ALTER TABLE operations RENAME TO saved_operations",
            "CREATE VIEW operations AS SELECT * FROM saved_operations",
        )
        before = self.files()
        with self.assertRaises(ValidationError):
            self.read()
        self.assertEqual(before, self.files())

    def test_exact_native_versions_one_and_two_reach_receipt_parsers_without_migration(self):
        original = self.path.read_bytes()
        for version in (1, 2):
            with self.subTest(version=version):
                self.path.write_bytes(original)
                if version == 1:
                    self.corrupt("DROP TABLE unknown_receipts")
                    self.corrupt("PRAGMA user_version=1")
                expected = tuple(LEDGER_SCHEMA) + (tuple(LEDGER_SCHEMA_V2) if version == 2 else ())
                with closing(sqlite3.connect(self.path)) as connection:
                    self.assertEqual(_schema_signature(connection), _expected_schema(expected))
                before = self.files()
                with patch.object(
                    history_module.Reply, "from_record", wraps=history_module.Reply.from_record
                ) as parser:
                    history = self.read()
                self.assertEqual(parser.call_count, 9)
                self.assertEqual(history.totals()["spent_microusd"], 1710)
                self.assertEqual(history.totals()["reserved_microusd"], 532373)
                self.assertEqual(before, self.files())

    def test_altered_missing_and_extra_native_ddl_fail_before_receipt_parsing(self):
        original = self.path.read_bytes()
        mutations = [
            "ALTER TABLE operations ADD COLUMN unreviewed TEXT",
            "DROP TRIGGER events_no_delete",
            "CREATE TABLE unrelated (value TEXT)",
            "CREATE INDEX extra_operation_index ON operations(status)",
            "CREATE VIEW harmless_view AS SELECT 1 AS value",
            "CREATE VIEW sqliteXuntrusted AS SELECT 1 AS value",
        ]
        for statement in mutations:
            with self.subTest(statement=statement):
                self.path.write_bytes(original)
                self.mutate_schema(statement)
                before = self.files()
                with (
                    patch.object(
                        history_module,
                        "_operation",
                        side_effect=AssertionError("unreviewed schema reached receipt parsing"),
                    ),
                    self.assertRaises(ValidationError),
                ):
                    self.read()
                self.assertEqual(before, self.files())

    def test_genuine_schema_with_foreign_key_violation_is_rejected_before_receipts(self):
        self.mutate_schema(
            "INSERT INTO events(event_type,operation_id) VALUES ('orphan','absent-operation')"
        )
        with closing(sqlite3.connect(self.path)) as connection:
            self.assertEqual(
                _schema_signature(connection),
                _expected_schema(tuple(LEDGER_SCHEMA) + tuple(LEDGER_SCHEMA_V2)),
            )
            self.assertTrue(connection.execute("PRAGMA foreign_key_check").fetchall())
        before = self.files()
        with (
            patch.object(
                history_module,
                "_operation",
                side_effect=AssertionError("foreign-key violation reached receipt parsing"),
            ),
            self.assertRaises(ValidationError),
        ):
            self.read()
        self.assertEqual(before, self.files())

    def test_valid_optional_binding_is_data_only_for_both_native_versions(self):
        original = self.path.read_bytes()
        for version in (1, 2):
            with self.subTest(version=version):
                self.path.write_bytes(original)
                if version == 1:
                    self.corrupt("DROP TABLE unknown_receipts")
                    self.corrupt("PRAGMA user_version=1")
                self.add_binding()
                before = self.files()
                with patch(
                    "buddha.authorization.runtime_fingerprint",
                    side_effect=AssertionError("historical binding cannot execute runtime"),
                ):
                    history = self.read()
                self.assertEqual(history.totals()["operation_count"], 10)
                self.assertEqual(before, self.files())
                self.assertFalse((self.directory.parent / "absent-authority.sqlite3").exists())

    def test_optional_binding_requires_exact_native_ddl(self):
        self.add_binding()
        original = self.path.read_bytes()
        for statement in (
            "DROP TRIGGER authorization_binding_no_delete",
            "ALTER TABLE authorization_binding ADD COLUMN unreviewed TEXT",
        ):
            with self.subTest(statement=statement):
                self.path.write_bytes(original)
                self.mutate_schema(statement)
                before = self.files()
                with self.assertRaises(ValidationError):
                    self.read()
                self.assertEqual(before, self.files())

    def test_optional_binding_row_shape_is_checked_without_opening_authority(self):
        self.add_binding()
        original = self.path.read_bytes()
        cases = [
            ("DELETE FROM authorization_binding", ()),
            ("UPDATE authorization_binding SET singleton=2", ()),
            ("UPDATE authorization_binding SET schema_version=2", ()),
            ("UPDATE authorization_binding SET authorization_id=''", ()),
            ("UPDATE authorization_binding SET authority_path=''", ()),
            ("UPDATE authorization_binding SET terms_sha256='not-a-seal'", ()),
            (
                "INSERT INTO authorization_binding VALUES (2,1,?,?,?)",
                ("second", str(self.directory.parent / "another.sqlite3"), "b" * 64),
            ),
        ]
        for statement, arguments in cases:
            with self.subTest(statement=statement):
                self.path.write_bytes(original)
                self.corrupt(statement, arguments)
                before = self.files()
                with self.assertRaises(ValidationError):
                    self.read()
                self.assertEqual(before, self.files())

    def test_data_corruption_keeps_native_triggers_and_still_reaches_reply_validation(self):
        self.corrupt(
            "UPDATE operations SET response_json=? WHERE operation_id=?",
            ('{"text":"not a complete reply"}', self.ids[0]),
        )
        with closing(sqlite3.connect(self.path)) as connection:
            self.assertEqual(
                _schema_signature(connection),
                _expected_schema(tuple(LEDGER_SCHEMA) + tuple(LEDGER_SCHEMA_V2)),
            )
        before = self.files()
        with patch.object(
            history_module.Reply, "from_record", wraps=history_module.Reply.from_record
        ) as parser:
            with self.assertRaises(ValidationError):
                self.read()
        self.assertGreater(parser.call_count, 0)
        self.assertEqual(before, self.files())

    def test_authority_import_rejects_a_resealed_non_native_schema_before_mirroring(self):
        self.mutate_schema("CREATE VIEW sqliteXuntrusted AS SELECT 1")
        authority = Authorization.create(
            self.directory.parent / "authority.sqlite3",
            authorization_id="schema-boundary",
            budget_microusd=50_000_000,
            max_calls=128,
            scope="temporary historical-schema check",
        )
        source_before, authority_before = self.files(), authority.path.read_bytes()
        with self.assertRaises(ValidationError):
            authority.import_history(
                self.directory,
                manifest_sha256=self.manifest_hash,
                ledger_sha256=hashlib.sha256(self.path.read_bytes()).hexdigest(),
            )
        self.assertEqual(source_before, self.files())
        self.assertEqual(authority_before, authority.path.read_bytes())

    def test_sqlite_like_prefix_cannot_hide_user_objects_in_main_or_funding(self):
        with closing(sqlite3.connect(":memory:")) as connection:
            connection.execute("ATTACH DATABASE ':memory:' AS funding")
            for schema in ("main", "funding"):
                with self.subTest(schema=schema):
                    connection.execute(f"CREATE VIEW {schema}.sqliteXuntrusted AS SELECT 1")
                    self.assertTrue(_schema_signature(connection, schema))

    def test_native_initialization_rejects_unversioned_user_object_without_changes(self):
        path = self.directory.parent / "unversioned.sqlite3"
        with closing(sqlite3.connect(path)) as connection, connection:
            connection.execute("CREATE VIEW sqliteXuntrusted AS SELECT 1")
        before = path.read_bytes()
        with self.assertRaises(ValidationError):
            Ledger(
                path,
                run_id="must-not-initialize",
                manifest_sha256="a" * 64,
                budget_microusd=100,
                max_calls=1,
            )
        self.assertEqual(before, path.read_bytes())


if __name__ == "__main__":
    unittest.main()
