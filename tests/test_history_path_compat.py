"""Legacy history paths normalize without bypassing opted-in trial markers."""

import os
import unittest
from pathlib import Path
from unittest.mock import patch

import test_authorization as fixtures

from buddha.common import ValidationError


class HistoryPathCompatibilityTests(unittest.TestCase):
    def fixture(self):
        fixture = fixtures.AuthorizationTests("runTest")
        fixture.setUp()
        self.addCleanup(fixture.doCleanups)
        return fixture

    def spelling(self, directory, kind):
        if kind == "relative":
            return Path(os.path.relpath(directory, Path.cwd()))
        alias = directory.parent / "existing-parent"
        alias.mkdir()
        return alias / ".." / directory.name

    def files(self, directory):
        return {
            path.relative_to(directory).as_posix(): path.read_bytes()
            for path in directory.rglob("*")
            if path.is_file()
        }

    def test_legacy_history_import_normalizes_equivalent_and_relative_paths(self):
        for kind in ("equivalent", "relative"):
            with self.subTest(kind=kind):
                fixture = self.fixture()
                directory, ledger, manifest_hash = fixture.prepare("old", bind=False)
                fixture.reserve(ledger)
                ledger.dispatch("operation")
                fixture.complete(ledger)
                spelling = self.spelling(directory, kind)
                ledger_before = (directory / "operations.sqlite3").read_bytes()

                fixture.seal(spelling, manifest_hash)

                summary = fixture.authority.summary()
                self.assertEqual(len(summary["runs"]), 1)
                self.assertEqual(summary["runs"][0]["directory"], str(directory.resolve()))
                self.assertTrue(summary["runs"][0]["historical"])
                self.assertEqual(summary["operation_count"], 1)
                self.assertEqual(summary["spent_microusd"], 60)
                self.assertEqual(summary["reserved_microusd"], 0)
                self.assertEqual((directory / "operations.sqlite3").read_bytes(), ledger_before)

                before = self.files(fixture.root)
                fixture.seal(directory.resolve(), manifest_hash)
                fixture.seal(spelling, manifest_hash)
                self.assertEqual(fixture.authority.summary(), summary)
                self.assertEqual(self.files(fixture.root), before)

    def test_equivalent_and_relative_history_cannot_launder_poisoned_trial_markers(self):
        for kind in ("equivalent", "relative"):
            for marker in (b"{", b'{"status":"poisoned"}'):
                with self.subTest(kind=kind, marker=marker):
                    fixture = self.fixture()
                    original_root = fixture.root
                    fixture.root = original_root / "trial"
                    fixture.root.mkdir()
                    (fixture.root / ".buddha-evaluation-trial.json").write_bytes(marker)
                    directory, _, manifest_hash = fixture.prepare("old", bind=False)
                    spelling = self.spelling(directory, kind)
                    before = self.files(original_root)

                    with patch("buddha.authorization.read_history") as read_history:
                        with self.assertRaises(ValidationError):
                            fixture.seal(spelling, manifest_hash)
                    read_history.assert_not_called()
                    self.assertEqual(fixture.authority.summary()["runs"], [])
                    self.assertEqual(self.files(original_root), before)


if __name__ == "__main__":
    unittest.main()
