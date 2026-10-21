"""Resume validates original pointer and owner bindings before consuming new data."""

import copy
import json
import shutil
import sqlite3
import unittest
from contextlib import closing
from unittest.mock import patch

import test_meas02_native_audit as fixtures

from buddha.releases import _json


class NativeAuditBindingTests(unittest.TestCase):
    def setUp(self):
        self.fixture = fixtures.NativeAuditTests("runTest")
        self.fixture.setUp()
        self.addCleanup(self.fixture.doCleanups)

    def refused_without_unlisted_reads(self, paths):
        fixture = self.fixture
        consumed = []
        original = fixtures.audit._read

        def tracked(path, *args, **kwargs):
            consumed.append(path.absolute())
            return original(path, *args, **kwargs)

        with patch.object(fixtures.audit, "_read", side_effect=tracked):
            with self.assertRaises(fixtures.audit.NativeAuditError):
                fixture.run_study()
        self.assertTrue(all(path.absolute() not in consumed for path in paths))
        self.assertEqual(fixture.connection.request.call_count, 0)

    def test_changed_context_cannot_dereference_an_unlisted_descriptor(self):
        fixture = self.fixture
        fixture.prepare()
        unlisted = fixture.root / "unlisted-pack.json"
        unlisted.write_bytes(b"[]")
        alternate = fixture.root / "unlisted-descriptor.json"
        changed = copy.deepcopy(fixture.record)
        changed["pack"] = str(unlisted)
        alternate.write_bytes(_json(changed))
        context = fixture.directory / "context.json"
        record = json.loads(context.read_bytes())
        record["descriptor"] = str(alternate)
        context.write_bytes(_json(record))
        self.refused_without_unlisted_reads([alternate, unlisted])

    def test_changed_descriptor_cannot_read_an_unlisted_pack(self):
        fixture = self.fixture
        fixture.prepare()
        unlisted = fixture.root / "unlisted-pack.json"
        unlisted.write_bytes(b"[]")
        changed = copy.deepcopy(fixture.record)
        changed["pack"] = str(unlisted)
        fixture.descriptor.write_bytes(_json(changed))
        self.refused_without_unlisted_reads([unlisted])

    def test_copied_later_owner_is_rejected_before_an_earlier_owner_spends(self):
        fixture = self.fixture
        fixture.prepare()
        later = fixture.directory / "owners/3"
        retained = fixture.root / "retained-owner-3"
        self.assertTrue(later.resolve().is_relative_to(fixture.root.resolve()))
        self.assertTrue(retained.resolve().is_relative_to(fixture.root.resolve()))
        later.rename(retained)
        shutil.copytree(fixture.directory / "owners/0", later)
        with self.assertRaises(fixtures.audit.NativeAuditError):
            fixture.run_study()
        self.assertEqual(fixture.connection.request.call_count, 0)
        self.assertEqual(fixture.authority.summary()["operation_count"], 0)

    def test_corrupt_later_ledger_is_rejected_before_an_earlier_owner_spends(self):
        fixture = self.fixture
        fixture.prepare()
        path = fixture.directory / "owners/3/operations.sqlite3"
        with closing(sqlite3.connect(path)) as connection:
            connection.execute("PRAGMA user_version=999")
        with self.assertRaises(fixtures.audit.NativeAuditError):
            fixture.run_study()
        self.assertEqual(fixture.connection.request.call_count, 0)
        self.assertEqual(fixture.authority.summary()["operation_count"], 0)

    def test_unknown_completion_filename_prevents_any_dispatch(self):
        fixture = self.fixture
        fixture.prepare()
        (fixture.directory / "completed/4.json").write_bytes(b"{}")
        with self.assertRaises(fixtures.audit.NativeAuditError):
            fixture.run_study()
        self.assertEqual(fixture.connection.request.call_count, 0)

    def test_final_report_without_complete_seals_prevents_any_dispatch(self):
        fixture = self.fixture
        fixture.prepare()
        (fixture.directory / "report.json").write_bytes(
            _json({"format": "buddha.meas02-native-study-report.v1", "status": "complete"})
        )
        with self.assertRaises(fixtures.audit.NativeAuditError):
            fixture.run_study()
        self.assertEqual(fixture.connection.request.call_count, 0)

    def test_later_unanchored_completion_is_rejected_before_first_batch_dispatch(self):
        fixture = self.fixture
        fixture.prepare()
        (fixture.directory / "completed/3.json").write_bytes(b"{}")
        with self.assertRaises(fixtures.audit.NativeAuditError):
            fixture.run_study()
        self.assertEqual(fixture.connection.request.call_count, 0)


if __name__ == "__main__":
    unittest.main()
