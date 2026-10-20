"""Sealed legacy history must consume the checked bytes, never a reopened file."""

import hashlib
import json
import os
import sqlite3
import unittest
from contextlib import closing, contextmanager
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

import test_history

import buddha.history as history_module
from buddha.authorization import Authorization
from buddha.common import ValidationError
from buddha.provider import Reply


class HistorySnapshotTests(unittest.TestCase):
    # Reuse the original nine-receipt/one-unknown fixture without inheriting its tests.
    setUp = test_history.HistoryTests.setUp
    write_manifest = test_history.HistoryTests.write_manifest
    read = test_history.HistoryTests.read
    corrupt = test_history.HistoryTests.corrupt
    files = test_history.HistoryTests.files

    @contextmanager
    def transient_file_query(self):
        """Swap only this temporary ledger after its seal check; restore on close."""
        sealed = self.path.read_bytes()
        replacement = Reply("UNSEALED transient answer", "generator", "request-0", 20, 100, "stop")
        self.corrupt(
            "UPDATE operations SET response_json=?,actual_microusd=? WHERE operation_id=?",
            (json.dumps(replacement.to_record()), 123456, self.ids[0]),
        )
        transient = self.path.read_bytes()
        self.path.write_bytes(sealed)
        self.assertNotEqual(sealed, transient)
        original_connect = sqlite3.connect
        ledger_path = self.path

        class RestoreOnClose(sqlite3.Connection):
            def close(connection):
                try:
                    super().close()
                finally:
                    ledger_path.write_bytes(sealed)

        def connect(database, *args, **kwargs):
            if str(database).startswith(ledger_path.as_uri() + "?"):
                ledger_path.write_bytes(transient)
                kwargs["factory"] = RestoreOnClose
            return original_connect(database, *args, **kwargs)

        try:
            with patch("buddha.history.sqlite3.connect", side_effect=connect):
                yield hashlib.sha256(sealed).hexdigest()
        finally:
            self.path.write_bytes(sealed)

    def test_transient_unsealed_database_cannot_replace_checked_receipt_or_charge(self):
        before = self.files()
        with self.transient_file_query() as seal:
            history = self.read(ledger_sha256=seal)
        self.assertEqual(before, self.files())
        self.assertEqual(history.ledger_sha256, seal)
        operation = next(item for item in history.operations if item.operation_id == self.ids[0])
        self.assertEqual(operation.reply.text, "Saved answer 0")
        self.assertEqual(operation.actual_microusd, 190)
        self.assertEqual(history.totals()["spent_microusd"], 1710)

    def test_historical_authorization_import_cannot_mirror_a_transient_unsealed_charge(self):
        authority = Authorization.create(
            self.directory.parent / "authorization.sqlite3",
            authorization_id="sealed-import",
            budget_microusd=50_000_000,
            max_calls=128,
            scope="local temporary history only",
        )
        before = self.files()
        with (
            self.transient_file_query() as seal,
            patch.dict(os.environ, {}, clear=True),
            patch("socket.create_connection", side_effect=AssertionError("network forbidden")),
            patch(
                "buddha.provider.HTTPTransport.send",
                side_effect=AssertionError("provider forbidden"),
            ),
            patch(
                "buddha.authorization.runtime_fingerprint",
                side_effect=AssertionError("runtime reconstruction forbidden"),
            ),
        ):
            authority.import_history(
                self.directory, manifest_sha256=self.manifest_hash, ledger_sha256=seal
            )
        self.assertEqual(before, self.files())
        summary = authority.summary()
        self.assertEqual(summary["spent_microusd"], 1710)
        self.assertEqual(summary["reserved_microusd"], 532373)
        self.assertEqual(summary["operation_count"], 10)
        with closing(sqlite3.connect(authority.path)) as connection:
            response, actual = connection.execute(
                "SELECT response_json,actual_microusd FROM auth_operations "
                "WHERE run_id=? AND operation_id=?",
                (self.manifest["run_id"], self.ids[0]),
            ).fetchone()
        self.assertEqual(json.loads(response)["text"], "Saved answer 0")
        self.assertEqual(actual, 190)

    def test_sqlite_queries_only_an_in_memory_copy_of_the_exact_sealed_bytes(self):
        sealed = self.path.read_bytes()
        before = self.files()
        destinations, snapshots, query_guards = [], [], []
        original_connect = sqlite3.connect

        class AuditConnection(sqlite3.Connection):
            consumed_snapshot = False

            def deserialize(connection, data, /, *, name="main"):
                snapshots.append(data)
                connection.consumed_snapshot = True
                return super().deserialize(data, name=name)

            def execute(connection, sql, *args, **kwargs):
                if connection.consumed_snapshot and sql.lstrip().upper().startswith("SELECT"):
                    query_guards.append(
                        (
                            super().execute("PRAGMA query_only").fetchone()[0],
                            super().execute("PRAGMA trusted_schema").fetchone()[0],
                        )
                    )
                return super().execute(sql, *args, **kwargs)

        def connect(database, *args, **kwargs):
            destinations.append(database)
            kwargs["factory"] = AuditConnection
            return original_connect(database, *args, **kwargs)

        with patch("buddha.history.sqlite3.connect", side_effect=connect):
            history = self.read(ledger_sha256=hashlib.sha256(sealed).hexdigest())
        self.assertTrue(destinations)
        self.assertEqual(set(destinations), {":memory:"})
        self.assertEqual(snapshots, [sealed])
        self.assertTrue(query_guards)
        self.assertEqual(set(query_guards), {(1, 0)})
        self.assertEqual(history.totals()["spent_microusd"], 1710)
        self.assertEqual(before, self.files())

    def test_post_snapshot_source_drift_still_prevents_returning_history(self):
        sealed = self.path.read_bytes()
        original_connect = sqlite3.connect

        def connect(database, *args, **kwargs):
            self.path.write_bytes(sealed + b"post-snapshot drift")
            return original_connect(database, *args, **kwargs)

        try:
            with (
                patch("buddha.history.sqlite3.connect", side_effect=connect),
                self.assertRaises(ValidationError),
            ):
                self.read(ledger_sha256=hashlib.sha256(sealed).hexdigest())
        finally:
            self.path.write_bytes(sealed)

    def test_wrong_seal_is_rejected_before_any_sqlite_connection(self):
        before = self.files()
        with (
            patch("buddha.history.sqlite3.connect", side_effect=AssertionError("unsealed query")),
            self.assertRaises(ValidationError),
        ):
            self.read(ledger_sha256="a" * 64)
        self.assertEqual(before, self.files())

    def test_snapshot_limits_bound_actual_reads_even_when_stat_reports_small_files(self):
        before = self.files()
        sealed = hashlib.sha256(self.path.read_bytes()).hexdigest()
        original_stat, original_open = Path.stat, Path.open
        maximum = 4

        for name, target in (
            ("MAX_MANIFEST_BYTES", self.directory / "manifest.json"),
            ("MAX_LEDGER_BYTES", self.path),
        ):
            reads = []

            class BoundedReader:
                def __init__(reader, stream):
                    reader.stream = stream

                def __enter__(reader):
                    reader.stream.__enter__()
                    return reader

                def __exit__(reader, *arguments):
                    return reader.stream.__exit__(*arguments)

                def read(reader, size=-1, *, observed=reads):
                    observed.append(size)
                    self.assertGreaterEqual(size, 0, "history attempted an unbounded read")
                    self.assertLessEqual(size, maximum + 1)
                    return reader.stream.read(size)

            def stat(path, *args, selected=target, **kwargs):
                information = original_stat(path, *args, **kwargs)
                if path == selected:
                    attributes = {
                        key: getattr(information, key)
                        for key in dir(information)
                        if key.startswith("st_")
                    }
                    return SimpleNamespace(**(attributes | {"st_size": 0}))
                return information

            def open_file(path, *args, selected=target, reader_type=BoundedReader, **kwargs):
                stream = original_open(path, *args, **kwargs)
                return reader_type(stream) if path == selected else stream

            with (
                self.subTest(limit=name),
                patch.object(history_module, name, maximum, create=True),
                patch.object(Path, "stat", stat),
                patch.object(Path, "open", open_file),
                patch(
                    "buddha.history.sqlite3.connect",
                    side_effect=AssertionError("oversized database must not be queried"),
                ),
                self.assertRaises(ValidationError),
            ):
                self.read(ledger_sha256=sealed)
            self.assertTrue(reads, "the consumed bytes must be bounded independently of stat")
            self.assertEqual(before, self.files())


if __name__ == "__main__":
    unittest.main()
