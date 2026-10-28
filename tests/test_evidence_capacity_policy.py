"""Explicit finite observation counts without changing legacy capture defaults."""

import hashlib
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from buddha import doctor
from buddha.common import ValidationError
from buddha.native_evidence import _adopt_capture
from buddha.search_evidence import EvidencePathLimitError, EvidenceTotalLimitError


def policy(*, total=64, entries=8, paths=8):
    return {
        "format": "buddha.evidence-observation-policy.v2",
        "max_total_bytes": total,
        "max_tree_entries": entries,
        "max_consumed_paths": paths,
        "max_resident_bytes": 0,
    }


class EvidenceCapacityPolicyTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.base = Path(temporary.name).resolve()
        self.root = self.base / "observation"
        self.root.mkdir()
        self.files = [self.base / (str(index) + ".bin") for index in range(3)]
        for path in self.files:
            path.write_bytes(b"data")

    def test_v2_requires_exact_fields_and_positive_bounded_integer_limits(self):
        invalid = [policy() | {"format": "unknown"}, policy() | {"extra": 1}]
        invalid.extend(
            {
                "format": value,
                "max_total_bytes": 64,
                "max_resident_bytes": 0,
            }
            for value in (None, True, 1, [], {})
        )
        invalid.extend(
            {key: value for key, value in policy().items() if key != missing}
            for missing in policy()
        )
        for field, ceiling in (
            ("max_total_bytes", 64 * 1024**3),
            ("max_tree_entries", 100_000),
            ("max_consumed_paths", 65_536),
        ):
            for value in (True, False, 0, -1, 1.0, "1", None, ceiling + 1):
                invalid.append(policy() | {field: value})
        invalid.extend(policy() | {"max_resident_bytes": value} for value in (False, True, 1, -1))
        for value in invalid:
            with self.subTest(value=value), self.assertRaises(ValidationError):
                with doctor._observation_policy(value):
                    self.fail("invalid observation policy accepted")
        with doctor._observation_policy(policy(total=64 * 1024**3, entries=100_000, paths=65_536)):
            self.assertEqual(doctor._Capture(self.root).read(self.files[0]), b"data")

    def test_tree_counts_directories_and_files_and_keeps_v1_defaults(self):
        folder = self.root / "nested"
        folder.mkdir()
        for index in range(2):
            (folder / str(index)).write_bytes(b"x")
        v1 = {
            "format": "buddha.evidence-observation-policy.v1",
            "max_total_bytes": 64,
            "max_resident_bytes": 0,
        }
        with patch.object(doctor, "MAX_FILES", 2):
            with self.assertRaises(EvidencePathLimitError):
                doctor._Capture(self.root)
            with doctor._observation_policy(v1), self.assertRaises(EvidencePathLimitError):
                doctor._Capture(self.root)
            with doctor._observation_policy(policy(entries=3)):
                capture = doctor._Capture(self.root)
            self.assertEqual(len(capture.entries), 3)
        capture.finish()

    def test_bytes_and_external_path_allowances_are_frozen_after_nested_policy_reset(self):
        with doctor._observation_policy(policy(total=8, paths=3)):
            byte_limited = doctor._Capture(self.root)
            with doctor._observation_policy(policy(total=64, paths=2)):
                path_limited = doctor._Capture(self.root)
            restored = doctor._Capture(self.root)
        with doctor._observation_policy(policy(total=1024, entries=100, paths=100)):
            for capture in (byte_limited, path_limited, restored):
                for path in self.files[:2]:
                    capture.read(path)
            with self.assertRaises(EvidenceTotalLimitError):
                byte_limited.read(self.files[2])
            with self.assertRaises(EvidenceTotalLimitError):
                restored.read(self.files[2])
            with self.assertRaises(EvidencePathLimitError):
                path_limited.read(self.files[2])
        for capture in (byte_limited, path_limited, restored):
            self.assertEqual(capture.total, 8)
            self.assertEqual(set(capture.raw), set(self.files[:2]))
            capture.finish()

    def test_tree_limit_is_frozen_for_finish_after_context_exit(self):
        for index in range(2):
            (self.root / str(index)).write_bytes(b"x")
        selected = policy(entries=2)
        with doctor._observation_policy(selected):
            selected["max_tree_entries"] = 100_000
            capture = doctor._Capture(self.root)
        (self.root / "late").write_bytes(b"x")
        with doctor._observation_policy(policy(entries=100_000)):
            with self.assertRaises(EvidencePathLimitError):
                capture.finish()

    def test_context_failure_restores_legacy_and_v1_path_limits(self):
        v1 = {
            "format": "buddha.evidence-observation-policy.v1",
            "max_total_bytes": 64,
            "max_resident_bytes": 0,
        }
        with patch.object(doctor, "MAX_FILES", 2):
            with self.assertRaisesRegex(RuntimeError, "synthetic"):
                with doctor._observation_policy(policy(paths=3)):
                    raise RuntimeError("synthetic")
            ordinary = doctor._Capture(self.root)
            with doctor._observation_policy(v1):
                legacy = doctor._Capture(self.root)
            for capture in (ordinary, legacy):
                for path in self.files[:2]:
                    capture.read(path)
                with self.assertRaises(EvidencePathLimitError):
                    capture.read(self.files[2])

    def test_adoption_enforces_the_frozen_external_receipt_union_limit(self):
        source_root = self.base / "sibling"
        source_root.mkdir()
        for selected, error in (
            (policy(paths=2), EvidencePathLimitError),
            (policy(total=10), EvidenceTotalLimitError),
        ):
            with self.subTest(selected=selected):
                with doctor._observation_policy(selected):
                    target = doctor._Capture(self.root)
                with doctor._observation_policy(policy(paths=3)):
                    source = doctor._Capture(source_root)
                target.read(self.files[0])
                for path in self.files[1:]:
                    source.read(path)
                with self.assertRaises(error):
                    _adopt_capture(source, target)
                self.assertEqual(set(target.raw), {self.files[0]})
                self.assertEqual(target.total, 4)

    def test_v2_keeps_hardlink_sidecar_and_changed_byte_guards(self):
        alias = self.root / "alias.bin"
        os.link(self.files[0], alias)
        with doctor._observation_policy(policy()), self.assertRaises(ValidationError):
            doctor._Capture(self.root)
        alias.unlink()
        with doctor._observation_policy(policy()):
            capture = doctor._Capture(self.root)
        capture.database(self.files[0])
        self.files[0].write_bytes(b"DIFF")
        with self.assertRaises(doctor._Busy):
            capture.finish()
        self.files[0].write_bytes(b"data")
        self.files[0].with_name(self.files[0].name + "-wal").write_bytes(b"pending")
        with self.assertRaises(doctor._Busy):
            capture.finish()

    def test_more_than_ten_thousand_opaque_files_require_explicit_v2_counts(self):
        paths = [self.root / (str(index) + ".bin") for index in range(10_001)]
        for path in paths:
            path.write_bytes(b"x")
        with self.assertRaises(EvidencePathLimitError):
            doctor._Capture(self.root)
        with (
            doctor._observation_policy(
                {
                    "format": "buddha.evidence-observation-policy.v1",
                    "max_total_bytes": 32 * 1024**3,
                    "max_resident_bytes": 0,
                }
            ),
            self.assertRaises(EvidencePathLimitError),
        ):
            doctor._Capture(self.root)
        with doctor._observation_policy(policy(total=32 * 1024**3, entries=100_000, paths=65_536)):
            capture = doctor._Capture(self.root)
        for path in paths:
            self.assertEqual(capture.read(path), b"x")
        observed = capture.finish()
        self.assertEqual(len(observed), 10_001)
        self.assertEqual(capture.total, 10_001)
        self.assertEqual(set(observed.values()), {hashlib.sha256(b"x").hexdigest()})


if __name__ == "__main__":
    unittest.main()
