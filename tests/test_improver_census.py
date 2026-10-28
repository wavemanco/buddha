"""Finite owner census work depends on owners, not every retained owner file."""

import copy
import hashlib
import unittest
from collections import Counter
from unittest.mock import patch

import test_source_screen as fixtures

from buddha import doctor, improver_study, source_screen
from buddha.native_evidence import NativeEvidence


class ImproverCensusTests(unittest.TestCase):
    def fixture(self):
        h = fixtures.SourceScreenTests("runTest")
        h.setUp()
        self.addCleanup(h.doCleanups)
        screen = h.screen()
        directory = h.root / "study"
        screen_root = directory / "common/0/0/screen"
        screen_root.parent.mkdir(parents=True)
        _, authority = h.prepare(screen, screen_root)
        # Genuine supplied workers create both generation and native owners;
        # no selected program executes on the host or in a real container.
        self.assertEqual(h.run_screen(screen_root)["status"], "complete")
        record = {
            "format": "buddha.improver-study.v1",
            "starts": [{"screen": screen.to_record()}],
            "repetitions": 1,
            "descendant_opportunities": 1,
            "limits": {"study": {"budget_microusd": 1_000_000, "max_calls": 1000}},
        }
        return h, directory, screen, authority, record

    @staticmethod
    def observation(directory, screen, authority, record):
        reader = NativeEvidence(
            directory, authority.path, error_type=improver_study.ImproverStudyError
        )
        return reader, {"record": record, "screens": [screen]}

    @staticmethod
    def snapshot(h, directory, authority):
        return (
            h.files(directory),
            hashlib.sha256(authority.path.read_bytes()).hexdigest(),
            (
                h.engine.physical_sends,
                h.engine.workers,
                h.engine.native_workers,
            ),
        )

    def measured_census(self, directory, screen, authority, record):
        work = Counter()
        original_tasks = source_screen.SourceScreen.tasks.fget
        original_record = source_screen.SourceScreen.to_record
        original_match = improver_study.re.fullmatch

        def tasks(value):
            work["task_population"] += 1
            return original_tasks(value)

        def to_record(value):
            work["screen_json"] += 1
            return original_record(value)

        def fullmatch(pattern, text, *args, **kwargs):
            if pattern.startswith(("common/", "cells/", "screen/tasks/", "witness/")):
                work["schedule_pattern"] += 1
            return original_match(pattern, text, *args, **kwargs)

        reader, state = self.observation(directory, screen, authority, record)
        with (
            patch.object(source_screen.SourceScreen, "tasks", property(tasks)),
            patch.object(source_screen.SourceScreen, "to_record", to_record),
            patch.object(improver_study.re, "fullmatch", side_effect=fullmatch),
        ):
            improver_study._census(reader, state)
        reader.capture.finish()
        return state, work

    def test_extra_owner_files_do_not_repeat_population_decoding_or_schedule_validation(self):
        h, directory, screen, authority, record = self.fixture()
        before = self.snapshot(h, directory, authority)
        with h.readonly():
            initial, small_work = self.measured_census(directory, screen, authority, record)
        self.assertEqual(before, self.snapshot(h, directory, authority))
        owners = initial["owner_paths"]
        self.assertTrue(owners)
        # Owner-internal leaves add no new owner. Each still enters the real
        # bounded directory census; no inventory or owner/funding read is mocked.
        added = []
        try:
            for owner in sorted(owners):
                for index in range(20):
                    path = owner / f"extra-{index}.txt"
                    path.write_text("opaque diagnostic", encoding="utf-8")
                    added.append(path)
            expanded = self.snapshot(h, directory, authority)
            with h.readonly():
                repeated, large_work = self.measured_census(directory, screen, authority, record)
            self.assertEqual(expanded, self.snapshot(h, directory, authority))
            self.assertEqual(repeated, initial)
            self.assertEqual(large_work, small_work)
            self.assertEqual(large_work["task_population"], 1)
        finally:
            for path in added:
                path.unlink()
        self.assertEqual(before, self.snapshot(h, directory, authority))

    def test_late_foreign_or_orphan_owner_paths_are_not_hidden_by_prefix_deduplication(self):
        h, directory, screen, authority, record = self.fixture()
        before = self.snapshot(h, directory, authority)
        invalid = [
            "foreign/owners/0/manifest.json",
            "COMMON/0/0/screen/tasks/0/generation/owners/0",
            "common/0/0/screen/TASKS/0/generation/owners/0",
            "common/1/0/screen/tasks/0/generation/owners/0/manifest.json",
            "common/0/1/screen/tasks/0/generation/owners/0/manifest.json",
            "cells/0/0/2/0/proposal/owners/0/manifest.json",
            "cells/0/0/0/1/proposal/owners/0/manifest.json",
            "common/0/0/screen/tasks/2/generation/owners/0/manifest.json",
            "common/0/0/screen/tasks/0/generation/owners/1/manifest.json",
            "common/0/0/screen/tasks/0/evaluation/owners/4/manifest.json",
            "common/0/0/screen/tasks/0/generation/owners/00/manifest.json",
            "common/0/0/unknown/owners/0/manifest.json",
            "cells/0/0/0/0/proposal/owners/0/report.json",
        ]
        for name in invalid:
            with self.subTest(path=name), h.readonly():
                reader, state = self.observation(directory, screen, authority, record)
                # Explicit post-inventory fault seam: append invalid owner
                # metadata after all genuine leaves. No saved file/SQL is forged.
                reader.capture.entries[name] = (0, 0, 0, 0, 0)
                with self.assertRaises(improver_study.ImproverStudyError):
                    improver_study._census(reader, state)
        self.assertEqual(before, self.snapshot(h, directory, authority))

    def test_complete_funding_bijection_and_owner_identity_remain_required(self):
        h, directory, screen, authority, record = self.fixture()
        before = self.snapshot(h, directory, authority)
        original_authority = improver_study._authority

        def missing(rows):
            rows.pop()

        def changed_id(rows):
            rows[-1]["run_id"] = "different-original-owner"

        def extra(rows):
            row = copy.deepcopy(rows[-1])
            row["directory"] = str(directory / "foreign/owners/0")
            rows.append(row)

        for change in (missing, changed_id, extra):

            def altered(*args, change=change, **kwargs):
                # Full real authority validation happens before the seam.
                funding = copy.deepcopy(original_authority(*args, **kwargs))
                change(funding["auth_runs"])
                return funding

            with (
                self.subTest(change=change.__name__),
                h.readonly(),
                patch.object(improver_study, "_authority", side_effect=altered),
            ):
                reader, state = self.observation(directory, screen, authority, record)
                with self.assertRaisesRegex(improver_study.ImproverStudyError, "bijective"):
                    improver_study._census(reader, state)
        self.assertEqual(before, self.snapshot(h, directory, authority))

    def test_census_receipts_still_detect_late_bytes_and_database_sidecars(self):
        h, directory, screen, authority, record = self.fixture()
        before = self.snapshot(h, directory, authority)
        for kind in ("bytes", "sidecar"):
            with self.subTest(kind=kind), h.readonly():
                reader, state = self.observation(directory, screen, authority, record)
                improver_study._census(reader, state)
                owner = sorted(state["owner_paths"])[0]
                path = owner / ("manifest.json" if kind == "bytes" else "operations.sqlite3-wal")
                original = path.read_bytes() if kind == "bytes" else None
                try:
                    path.write_bytes(
                        bytes([original[0] ^ 1]) + original[1:]
                        if original is not None
                        else b"late external writer"
                    )
                    with patch.object(doctor, "_entries", return_value=reader.capture.entries):
                        with self.assertRaises(doctor._Busy):
                            reader.capture.finish()
                finally:
                    if original is None:
                        path.unlink()
                    else:
                        path.write_bytes(original)
        self.assertEqual(before, self.snapshot(h, directory, authority))


if __name__ == "__main__":
    unittest.main()
