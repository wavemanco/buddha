"""Independent actual-file checks of invocation-local constructor reuse."""

import tempfile
import unittest
from contextlib import nullcontext
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from buddha import doctor, launch_common


def observation():
    # Measure the historical duplicate walks before the private API exists.
    return getattr(doctor, "_passive_tree_observation", nullcontext)()


class PassiveTreeObservationReviewTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name).resolve()
        self.data = self.root / "data.bin"
        self.data.write_bytes(b"original")

    def test_real_duplicate_constructor_walks_reduce_while_every_finish_stays_strict(self):
        with patch.object(doctor, "_entries", wraps=doctor._entries) as walks:
            baseline = [doctor._Capture(self.root) for _ in range(4)]
            for capture in baseline:
                capture.read(self.data)
                capture.finish()
            self.assertEqual(walks.call_count, 8)
        with patch.object(doctor, "_entries", wraps=doctor._entries) as walks:
            with observation():
                captures = [doctor._Capture(self.root) for _ in range(4)]
                for capture in captures:
                    capture.read(self.data)
                    capture.finish()
                self.assertEqual(walks.call_count, 5)
            self.assertEqual(walks.call_count, 6)
        for capture in captures:
            self.assertEqual(capture.fingerprints(), baseline[0].fingerprints())
        self.assertIsNot(captures[0].entries, captures[1].entries)

    def test_public_adopt_remains_immediately_fresh_inside_shared_scope(self):
        class CompletedProbe(Exception):
            pass

        with self.assertRaises(CompletedProbe), observation():
            source, target = doctor._Capture(self.root), doctor._Capture(self.root)
            source.read(self.data)
            self.data.write_bytes(b"modified")
            with self.assertRaises(doctor._Busy):
                target.adopt(source)
            self.assertEqual(target.total, 0)
            self.assertEqual(dict(target.raw), {})
            # An existing failure must remain primary when the scope discards work.
            raise CompletedProbe

    def test_exception_discards_metadata_before_the_next_invocation(self):
        class ExpectedFailure(Exception):
            pass

        with self.assertRaises(ExpectedFailure), observation():
            doctor._Capture(self.root).read(self.data)
            raise ExpectedFailure
        added = self.root / "new.bin"
        added.write_bytes(b"new")
        with observation():
            fresh = doctor._Capture(self.root)
            self.assertIn("new.bin", fresh.entries)
            fresh.read(added)
            fresh.finish()

    def test_unrelated_ancestor_lock_does_not_reject_an_unchanged_observation(self):
        parent = self.root / "unrelated-parent"
        observed = parent / "observation"
        observed.mkdir(parents=True)
        (observed / "data.bin").write_bytes(b"unchanged")
        ordinary = doctor._Capture(observed)
        with observation():
            shared = doctor._Capture(observed)
            (parent / ".search.lock").write_bytes(b"unrelated work")
            ordinary.finish()
            shared.finish()

    def test_held_trial_accepts_directory_metadata_changes_only(self):
        trial = self.root / "trial"
        study = trial / "search" / "study"
        branch = study / "common"
        branch.mkdir(parents=True)
        report = branch / "report.json"
        report.write_bytes(b"sealed")
        ledger = study / "operations.sqlite3"
        ledger.write_bytes(b"ledger")
        strict = doctor._Capture(trial)
        ordinary_lstat = Path.lstat

        def directory_size(path, *args, **kwargs):
            info = ordinary_lstat(path, *args, **kwargs)
            if path != branch:
                return info
            return SimpleNamespace(
                st_mode=info.st_mode,
                st_dev=info.st_dev,
                st_ino=info.st_ino,
                st_size=info.st_size + 1,
                st_mtime_ns=info.st_mtime_ns,
                st_ctime_ns=info.st_ctime_ns,
            )

        token = launch_common._HELD_RECOVERY.set({"trial": trial})
        try:
            with observation():
                outer, nested = doctor._Capture(trial), doctor._Capture(study)
                nested.read(report)
                nested.database(ledger)
                with patch.object(Path, "lstat", directory_size):
                    with self.assertRaises(doctor._TreeChanged) as changed:
                        strict.finish()
                    self.assertEqual(changed.exception.details["entries"][0]["fields"], ["size"])
                    outer.adopt(nested)
                    outer.finish()
            report.write_bytes(b"edited")
            with self.assertRaises(doctor._Busy):
                outer.finish()
            report.write_bytes(b"sealed")
            with self.assertRaises(doctor._TreeChanged):
                with observation():
                    current = doctor._Capture(study)
                    empty = study / "empty"
                    empty.mkdir()
                    current.finish()
            replacement = study / "empty"
            current = doctor._Capture(study)
            replacement.rename(trial / "old-empty")
            replacement.mkdir()
            with self.assertRaises(doctor._TreeChanged):
                current.finish()
            current = doctor._Capture(study)
            current.database(ledger)
            ledger.with_name(ledger.name + "-wal").touch()
            with self.assertRaises(doctor._Busy):
                current.finish()
        finally:
            launch_common._HELD_RECOVERY.reset(token)


if __name__ == "__main__":
    unittest.main()
