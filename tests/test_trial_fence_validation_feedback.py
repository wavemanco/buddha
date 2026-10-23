"""Validation and feedback writers consume the original trial before effects."""

import json
import unittest
from unittest.mock import patch

import test_source_feedback as feedback_fixtures
import test_validation_study as validation_fixtures
from test_trial_fence import MARKER, TrialFixture, file_bytes

from buddha import trial_fence
from buddha.releases import ReleaseError


class TrialFenceValidationFeedbackTests(unittest.TestCase):
    def validation(self):
        case = validation_fixtures.ValidationStudyTests("runTest")
        case.setUp()
        self.addCleanup(case.doCleanups)
        return case

    def feedback(self):
        case = feedback_fixtures.SourceFeedbackTests("runTest")
        case.setUp()
        self.addCleanup(case.doCleanups)
        return case

    def test_poisoned_validation_prepare_refuses_before_destination(self):
        case = self.validation()
        root = case.root / "poisoned"
        root.mkdir()
        (root / MARKER).write_bytes(b"{")
        case.directory = root / "study"
        before = file_bytes(case.root)
        with self.assertRaises(ReleaseError):
            case.prepare()
        self.assertFalse(case.directory.exists())
        self.assertEqual(file_bytes(case.root), before)

    def test_poisoned_validation_run_refuses_before_local_lock(self):
        case = self.validation()
        root = case.root / "later-poisoned"
        root.mkdir()
        case.directory = root / "study"
        case.prepare()
        authority = case.authority()
        (root / MARKER).write_bytes(b"{")
        before = file_bytes(case.root)
        with patch(
            "buddha.native_pipeline._exclusive",
            side_effect=trial_fence.TrialFenceError("local lock was reached"),
        ) as local_lock:
            with self.assertRaises(ReleaseError):
                case.run_occasion(authority)
        local_lock.assert_not_called()
        self.assertEqual(file_bytes(case.root), before)

    def test_trial_validation_preparation_requires_explicit_original_grant(self):
        case = self.validation()
        trial = TrialFixture(self)
        case.directory = trial.root / "validation" / "study"
        before = trial.bytes()
        with self.assertRaises(ReleaseError):
            case.prepare()
        self.assertFalse(case.directory.exists())
        self.assertEqual(trial.bytes(), before)

    def test_structured_validation_round_trip_and_completed_frozen_replay(self):
        case = self.validation()
        trial = TrialFixture(
            self,
            purposes={
                "search": "synthetic fixed search comparison",
                "validation": "validation study: "
                + validation_fixtures.sha(case.declaration.read_bytes()),
                "final": "synthetic reserved final confirmation",
            },
        )
        case.directory = trial.root / "validation" / "study"
        authority = trial.authorities["validation"]
        case.prepare(authorization=authority)
        with case.offline():
            result = case.run_occasion(authority)
        self.assertEqual(result["status"], "complete")
        owners = 0
        for path in case.directory.rglob("manifest.json"):
            record = json.loads(path.read_bytes())
            if record.get("format") != "buddha.gateway-run.v1":
                continue
            owners += 1
            self.assertEqual(record["authorization_path"], str(authority.path))
            pins = {row["path"]: row["sha256"] for row in record["invocation"]["inputs"]}
            for control, digest in trial.pins.items():
                self.assertEqual(pins.get(str(control)), digest)
        self.assertEqual(owners, 16)
        with trial_fence.lease(authority.path, authority._terms(), directory=case.directory):
            trial.freeze()
        before = trial.bytes()
        with (
            patch("buddha.native_pipeline._exclusive", side_effect=AssertionError("writer lock")),
            patch("buddha.gateway._credential", side_effect=AssertionError("key lookup")),
        ):
            self.assertEqual(case.run_occasion(authority), result)
        self.assertEqual(trial.bytes(), before)

    def test_poisoned_feedback_destination_refuses_before_any_file(self):
        case = self.feedback()
        _, _, reference = case.completed()
        root = case.h.root / "poisoned"
        root.mkdir()
        (root / MARKER).write_bytes(b"{")
        destination = root / "feedback"
        before = file_bytes(case.h.root)
        with case.passive(), self.assertRaises(ReleaseError):
            case.write_api(destination, reference=reference)
        self.assertFalse(destination.exists())
        self.assertEqual(file_bytes(case.h.root), before)

    def test_frozen_screen_is_readable_but_cannot_write_new_feedback_elsewhere(self):
        case = self.feedback()
        screen = case.h.screen()
        trial = TrialFixture(
            self,
            purposes={
                "search": "source screen: " + screen.comparison_key(),
                "validation": "synthetic fixed validation comparison",
                "final": "synthetic reserved final confirmation",
            },
        )
        authority = trial.authorities["search"]
        original, _ = case.h.prepare(
            screen, directory=trial.root / "search" / "screen", authority=authority
        )
        self.assertEqual(case.h.run_screen(original)["status"], "complete")
        reference = case.h.reference(original, authority)
        first = trial.root / "search" / "feedback"
        with case.passive():
            case.write_api(first, reference=reference)
        with trial_fence.lease(authority.path, authority._terms(), directory=original):
            trial.freeze()
        # An outside destination must not turn frozen source evidence into new work.
        destination = case.h.root / "outside-feedback"
        before = trial.bytes(), file_bytes(case.h.root)
        with case.passive():
            bundle = case.build_api(destination, reference=reference)
            self.assertEqual(bundle["provenance"]["format"], "buddha.source-screen-feedback.v3")
            with self.assertRaises(ReleaseError):
                case.write_api(destination, reference=reference)
        self.assertFalse(destination.exists())
        self.assertEqual((trial.bytes(), file_bytes(case.h.root)), before)
