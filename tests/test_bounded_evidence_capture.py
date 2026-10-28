"""Finite, read-only observations need not retain their complete byte history."""

import hashlib
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from buddha import doctor
from buddha.common import ValidationError
from buddha.native_evidence import _adopt_capture


def policy(maximum):
    return {
        "format": "buddha.evidence-observation-policy.v1",
        "max_total_bytes": maximum,
        "max_resident_bytes": 0,
    }


class BoundedEvidenceCaptureTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.base = Path(temporary.name).resolve()
        self.root = self.base / "observation"
        self.root.mkdir()
        self.files = [self.base / (str(index) + ".bin") for index in range(3)]
        for index, path in enumerate(self.files):
            path.write_bytes(bytes([65 + index]) * 4)

    def test_default_logical_bound_is_unchanged_and_failed_reads_do_not_consume_it(self):
        with patch.object(doctor, "MAX_TOTAL_BYTES", 8):
            capture = doctor._Capture(self.root)
            capture.read(self.files[0])
            capture.read(self.files[1])
            with self.assertRaises(ValidationError):
                capture.read(self.files[2])
        self.assertEqual(capture.total, 8)
        self.assertNotIn(self.files[2], capture.raw)

    def test_opt_in_reads_more_than_legacy_bound_without_persistent_raw_cache(self):
        with patch.object(doctor, "MAX_TOTAL_BYTES", 8):
            with doctor._observation_policy(policy(12)):
                capture = doctor._Capture(self.root)
            for path in self.files:
                self.assertEqual(capture.read(path), path.read_bytes())
            with patch.object(doctor, "_read", wraps=doctor._read) as reads:
                self.assertEqual(capture.raw[self.files[0]], b"AAAA")
                self.assertEqual(capture.raw[self.files[0]], b"AAAA")
                self.assertEqual(reads.call_count, 2)
            self.assertEqual(capture.total, 12)
            self.assertEqual(
                capture.fingerprints(),
                {str(path): hashlib.sha256(path.read_bytes()).hexdigest() for path in self.files},
            )
            with self.assertRaises(ValidationError):
                doctor._Capture(self.root).read(self.files[0], 3)

    def test_nested_policy_is_frozen_on_construction_and_resets_after_exit(self):
        with patch.object(doctor, "MAX_TOTAL_BYTES", 4):
            original = doctor._Capture(self.root)
            with doctor._observation_policy(policy(8)):
                outer = doctor._Capture(self.root)
                with doctor._observation_policy(policy(12)):
                    inner = doctor._Capture(self.root)
                restored = doctor._Capture(self.root)
            default = doctor._Capture(self.root)
        for capture, count in ((original, 1), (outer, 2), (inner, 3), (restored, 2), (default, 1)):
            for path in self.files[:count]:
                capture.read(path)
            if count < 3:
                with self.assertRaises(ValidationError):
                    capture.read(self.files[count])

    def test_policy_refuses_invalid_versions_fields_and_integer_limits(self):
        invalid = [None, {}, policy(0), policy(-1), policy(True), policy(64 * 1024**3 + 1)]
        for field, value in (
            ("format", "other"),
            ("max_resident_bytes", 1),
            ("max_resident_bytes", False),
        ):
            invalid.append(policy(8) | {field: value})
        invalid.append(policy(8) | {"extra": 0})
        for value in invalid:
            with self.subTest(value=value), self.assertRaises(ValidationError):
                with doctor._observation_policy(value):
                    self.fail("invalid observation policy was accepted")
        with doctor._observation_policy(policy(64 * 1024**3)):
            self.assertEqual(doctor._Capture(self.root).read(self.files[0]), b"AAAA")

    def test_known_receipt_preserves_field_bound_and_read_only_mapping(self):
        capture = doctor._Capture(self.root)
        capture.read(self.files[0], 4)
        with self.assertRaises(ValidationError):
            capture.read(self.files[0], 3)
        self.assertEqual(capture.raw.get(self.files[0]), b"AAAA")
        self.assertIsNone(capture.raw.get(self.files[1]))
        self.assertEqual(dict(capture.raw.items()), {self.files[0]: b"AAAA"})
        with self.assertRaises(TypeError):
            capture.raw[self.files[0]] = b"BBBB"

    def test_reread_and_finish_reject_same_size_byte_drift_with_metadata_held_constant(self):
        capture = doctor._Capture(self.root)
        capture.read(self.files[0])
        snapshot = capture.entries
        self.files[0].write_bytes(b"ZZZZ")
        with patch.object(doctor, "_entries", return_value=snapshot):
            with self.assertRaises(doctor._Busy):
                capture.read(self.files[0])
            with self.assertRaises(doctor._Busy):
                capture.finish()
        self.files[0].write_bytes(b"AAAA")
        self.assertEqual(capture.raw[self.files[0]], b"AAAA")

    def test_external_receipts_have_the_same_finite_path_count_bound(self):
        with patch.object(doctor, "MAX_FILES", 2):
            capture = doctor._Capture(self.root)
            for path in self.files[:2]:
                capture.read(path)
            with self.assertRaises(ValidationError):
                capture.read(self.files[2])
        self.assertEqual(set(capture.raw), set(self.files[:2]))
        self.assertEqual(capture.total, 8)

    def test_adoption_uses_declared_aggregate_and_retains_sibling_tree_checks(self):
        sibling = self.base / "sibling"
        sibling.mkdir()
        source = doctor._Capture(sibling)
        source.read(self.files[0])
        with patch.object(doctor, "MAX_TOTAL_BYTES", 4):
            with doctor._observation_policy(policy(12)):
                target = doctor._Capture(self.root)
            for path in self.files[1:]:
                target.read(path)
            _adopt_capture(source, target)
        self.assertEqual(target.total, 12)
        self.assertEqual(set(target.raw), set(self.files))
        target.finish()
        self.files[0].write_bytes(b"XXXX")
        with self.assertRaises(doctor._Busy):
            _adopt_capture(source, target)

    def test_finish_rechecks_database_sidecars_after_final_byte_read(self):
        capture = doctor._Capture(self.root)
        ledger = self.files[0]
        capture.database(ledger)
        original_read = doctor._read

        def changed(path, maximum):
            raw = original_read(path, maximum)
            if path == ledger:
                ledger.with_name(ledger.name + "-wal").write_bytes(b"late writer")
            return raw

        with patch.object(doctor, "_read", side_effect=changed):
            with self.assertRaises(doctor._Busy):
                capture.finish()

    def test_finish_still_refuses_late_local_tree_entries(self):
        capture = doctor._Capture(self.root)
        capture.read(self.files[0])
        (self.root / "late.bin").write_bytes(b"late")
        with self.assertRaises(doctor._Busy):
            capture.finish()


if __name__ == "__main__":
    unittest.main()
