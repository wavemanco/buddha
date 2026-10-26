"""Read original complete baseline evidence without calling its retired producer."""

import hashlib
import json
import os
import sqlite3
import unittest
from contextlib import closing
from unittest.mock import patch

import test_baseline as fixtures

from buddha.releases import MAX_JSON_BYTES, inventory


class BaselineResultsTests(unittest.TestCase):
    def setUp(self):
        from buddha.baseline_results import BaselineResultsError, inspect_baseline

        self.inspect, self.Error = inspect_baseline, BaselineResultsError
        self.case = fixtures.BaselineTests("runTest")
        self.case.setUp()
        self.addCleanup(self.case.doCleanups)
        self.case.prepare()
        self.definition_hash = hashlib.sha256(self.case.descriptor.read_bytes()).hexdigest()

    def read(self):
        return self.inspect(
            self.case.directory,
            authorization=self.case.authority.path,
            expected_report_sha256=hashlib.sha256(
                (self.case.directory / "report.json").read_bytes()
            ).hexdigest(),
            expected_definition_sha256=self.definition_hash,
        )

    def test_original_complete_evidence_is_read_keylessly_after_producer_retirement(self):
        report = self.case.run_pipeline()
        self.assertEqual(report["status"], "complete")
        # Retire only temporary fixture components, never repository source.
        for component in (
            self.case.generation_roots["agent"],
            self.case.generation_roots["runner"],
            self.case.native_roots["runner"],
            self.case.generation_roots["official"],
        ):
            self.assertTrue(component.resolve().is_relative_to(self.case.root.resolve()))
            for path in component.rglob("*.py"):
                path.unlink()
        before = inventory(self.case.directory)
        original_connect = sqlite3.connect

        def memory_only(path, *args, **kwargs):
            self.assertEqual(path, ":memory:", "source database was opened")
            return original_connect(path, *args, **kwargs)

        with (
            patch.dict(os.environ, {}, clear=True),
            patch("buddha.baseline.run_baseline", side_effect=AssertionError("producer called")),
            patch("buddha.gateway.Gateway.__init__", side_effect=AssertionError("owner created")),
            patch("sqlite3.connect", side_effect=memory_only),
        ):
            self.assertEqual(self.read(), report)
        self.assertEqual(inventory(self.case.directory), before)
        self.assertIn(b"NaN", self.case.summary_bytes)

    def test_shared_authority_later_work_does_not_rewrite_original_report(self):
        original = self.case.run_pipeline()
        other = self.case.root / "other-baseline"
        self.case.prepare(other)
        self.assertEqual(self.case.run_pipeline(directory=other)["status"], "complete")
        self.assertEqual(self.read(), original)

    def test_altered_descriptor_or_sealed_output_and_extra_owner_are_rejected(self):
        self.case.run_pipeline()
        descriptor = self.case.descriptor.read_bytes()
        changed = json.loads(descriptor)
        changed["generation"]["max_calls"] += 1
        self.case.descriptor.write_text(json.dumps(changed), encoding="utf-8")
        with self.assertRaises(self.Error):
            self.read()
        self.case.descriptor.write_bytes(descriptor)
        seal = json.loads((self.case.directory / "completed/1.json").read_bytes())
        output = self.case.directory / seal["attempt"] / "artifacts/partitions.jsonl"
        raw = output.read_bytes()
        output.write_bytes(raw + b"\n")
        with self.assertRaises(self.Error):
            self.read()
        output.write_bytes(raw)
        extra = self.case.directory / "owners/extra"
        extra.mkdir()
        (extra / "manifest.json").write_bytes(b"{}")
        with self.assertRaises(self.Error):
            self.read()

    def test_incomplete_baseline_never_creates_a_missing_owner_or_report(self):
        self.case.halt_native_once = True
        result = self.case.run_pipeline()
        self.assertEqual(result["status"], "incomplete")
        before = inventory(self.case.directory)
        with (
            patch("buddha.gateway.Gateway.__init__", side_effect=AssertionError("owner created")),
            self.assertRaises(self.Error),
        ):
            self.inspect(
                self.case.directory,
                authorization=self.case.authority.path,
                expected_report_sha256="0" * 64,
                expected_definition_sha256=self.definition_hash,
            )
        self.assertEqual(inventory(self.case.directory), before)

    def test_foreign_authority_is_not_accepted_for_original_baseline(self):
        self.case.run_pipeline()
        with self.assertRaises(self.Error):
            self.inspect(
                self.case.directory,
                authorization=self.case.fixture.authority.path,
                expected_report_sha256=hashlib.sha256(
                    (self.case.directory / "report.json").read_bytes()
                ).hexdigest(),
                expected_definition_sha256=self.definition_hash,
            )

    def test_valid_generation_ledger_keeps_its_database_size_bound(self):
        path = self.case.directory / "owners/0/operations.sqlite3"
        # Fresh synthetic DB only. Keep harmless free pages, without changing
        # the schema, records or any historical/paid database.
        with closing(sqlite3.connect(path)) as connection:
            connection.execute("CREATE TABLE size_probe (payload BLOB)")
            connection.execute("INSERT INTO size_probe VALUES (zeroblob(?))", (33 * 1024**2,))
            connection.execute("DROP TABLE size_probe")
            connection.commit()
        report = self.case.run_pipeline()
        self.assertEqual(report["status"], "complete")
        self.assertGreater(path.stat().st_size, MAX_JSON_BYTES)
        self.assertEqual(self.read(), report)

    def test_opaque_native_summary_keeps_its_artifact_size_bound(self):
        self.case.summary_bytes += b" " * MAX_JSON_BYTES
        report = self.case.run_pipeline()
        self.assertEqual(report["status"], "complete")
        self.assertGreater(len(self.case.summary_bytes), MAX_JSON_BYTES)
        self.assertEqual(self.read(), report)


if __name__ == "__main__":
    unittest.main()
