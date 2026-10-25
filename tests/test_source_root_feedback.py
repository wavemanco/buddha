"""Root-treatment input bounds and original search-custody publication."""

import hashlib
import json
import tempfile
import unittest
from contextlib import contextmanager
from pathlib import Path
from unittest.mock import patch

import test_source_mutation_witness as witness_fixtures

from buddha import source_feedback, trial_fence
from buddha.releases import _json


class SourceRootFeedbackTests(unittest.TestCase):
    def test_public_root_packet_replays_original_custody_and_refuses_late_manifest_drift(self):
        harness = witness_fixtures._Harness(self, iterations=1)
        case = harness.case
        case.prepare(source_copy=True, feedback_comparison=True)
        seed = case.directory / "seed"
        self.assertEqual(case.h.run_screen(seed)["status"], "complete")
        self.assertFalse((case.directory / "seed-witness").exists())
        self.assertFalse((case.directory / "iterations/0").exists())
        manifest = case.directory / "manifest.json"
        manifest_raw = manifest.read_bytes()
        self.assertEqual(json.loads(manifest_raw)["format"], "buddha.source-search-manifest.v6")
        reference = case.h.reference(seed, case.authority)
        root = {
            "directory": str(case.directory),
            "authorization": str(case.authority.path),
            "manifest_sha256": hashlib.sha256(manifest_raw).hexdigest(),
        }
        comparison = {"root": root}
        packet = case.root / "public-root-feedback"
        original = (
            case.h.files(case.directory),
            case.authority.summary(),
            case.authority.path.read_bytes(),
            case.engine.physical_sends,
        )
        with case.h.readonly():
            expected = source_feedback.build_source_feedback(
                packet, reference=reference, comparison=comparison
            )
            written = source_feedback.write_source_feedback(
                packet, reference=reference, comparison=comparison
            )
            restored = source_feedback.inspect_source_feedback(
                packet, expected_provenance_sha256=written["provenance"]["sha256"]
            )
        self.assertEqual(_json(restored), _json(expected))
        self.assertEqual(restored["provenance"]["comparison"], comparison)
        self.assertEqual(restored["provenance"]["root_declaration"]["reference"], reference)
        self.assertEqual(restored["provenance"]["base_format"], "buddha.source-screen-feedback.v3")
        for row in restored["feedback"]["records"]:
            note = json.loads(row["note"])
            self.assertEqual(
                note["measurements"]["answers"],
                [
                    {"position": 0, "text": witness_fixtures.LONG_ANSWER},
                    {"position": 1, "text": ""},
                ],
            )
            self.assertEqual(note["measurements"]["omitted_answer_positions"], 0)
            self.assertIsNone(note["parent_measurements"])
            self.assertEqual(note["comparison"]["status"], "unavailable")
            self.assertEqual(note["comparison"]["reason"], "no_counted_parent_in_this_search")
            self.assertEqual(note["comparison"]["current_id"], case.seed.candidate_id)
            for key in (
                "parent_id",
                "distinct_delta",
                "utility_delta",
                "recorded_cost_delta_microusd",
            ):
                self.assertIsNone(note["comparison"][key])
        self.assertEqual(
            (
                case.h.files(case.directory),
                case.authority.summary(),
                case.authority.path.read_bytes(),
                case.engine.physical_sends,
            ),
            original,
        )

        destination = case.root / "unwritten-root-feedback"
        wrong_references = (
            reference | {"directory": str(case.directory / "iterations/0/screen")},
            reference | {"report_sha256": "0" * 64},
        )
        wrong_roots = (
            root | {"manifest_sha256": "0" * 64},
            root | {"authorization": str(case.root / "another-authorization.sqlite3")},
            root | {"directory": str(case.root)},
        )
        before = case.h.files(case.root), case.authority.summary(), case.engine.physical_sends
        with case.h.readonly():
            for changed in wrong_references:
                with (
                    self.subTest(reference=changed),
                    self.assertRaises(source_feedback.SourceFeedbackError),
                ):
                    source_feedback.write_source_feedback(
                        destination, reference=changed, comparison=comparison
                    )
            for changed in wrong_roots:
                with (
                    self.subTest(root=changed),
                    self.assertRaises(source_feedback.SourceFeedbackError),
                ):
                    source_feedback.write_source_feedback(
                        destination, reference=reference, comparison={"root": changed}
                    )
        self.assertFalse(destination.exists())

        original_work = trial_fence.work
        drifted = False

        @contextmanager
        def changed_at_destination(authority, terms, *, directory, kind="gateway"):
            nonlocal drifted
            with original_work(authority, terms, directory=directory, kind=kind) as controls:
                if directory == destination:
                    self.assertFalse(drifted)
                    drifted = True
                    manifest.write_bytes(manifest_raw + b" ")
                yield controls

        try:
            with (
                case.h.readonly(),
                patch.object(trial_fence, "work", side_effect=changed_at_destination),
                self.assertRaises(source_feedback.SourceFeedbackError),
            ):
                source_feedback.write_source_feedback(
                    destination, reference=reference, comparison=comparison
                )
        finally:
            manifest.write_bytes(manifest_raw)
        self.assertTrue(drifted)
        self.assertFalse(destination.exists())
        self.assertEqual(
            (case.h.files(case.root), case.authority.summary(), case.engine.physical_sends), before
        )
        self.assertEqual(case.authority.path.read_bytes(), original[2])

        # Retain the genuine base walk, then change one literal answer leaf
        # before the root declaration is observed. Publication must still bind
        # the outputs it actually read, not merely the later tree metadata.
        answers = seed / "tasks/0/generation/attempts/0-0/session/answers.json"
        self.assertTrue(answers.is_file())
        answers_raw = answers.read_bytes()
        answers_destination = case.root / "answers-drift-root-feedback"
        original_build = source_feedback._build
        answers_drifted = False

        def changed_after_base(*args, **kwargs):
            nonlocal answers_drifted
            result = original_build(*args, **kwargs)
            self.assertFalse(answers_drifted)
            answers_drifted = True
            answers.write_bytes(answers_raw + b" ")
            return result

        try:
            with (
                case.h.readonly(),
                patch.object(source_feedback, "_build", side_effect=changed_after_base),
                self.assertRaises(source_feedback.SourceFeedbackError),
            ):
                source_feedback.write_source_feedback(
                    answers_destination, reference=reference, comparison=comparison
                )
        finally:
            answers.write_bytes(answers_raw)
            self.assertEqual(case.authority.path.read_bytes(), original[2])
            self.assertEqual(case.engine.physical_sends, original[3])
        self.assertTrue(answers_drifted)
        self.assertFalse(answers_destination.exists())
        self.assertEqual(
            (case.h.files(case.root), case.authority.summary(), case.engine.physical_sends), before
        )
        self.assertEqual(case.authority.path.read_bytes(), original[2])

    def test_root_rejects_fixed_improver_and_extra_fields_before_observing_evidence(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary).resolve()
            destination = root / "new-feedback"
            reference = {}
            comparison = {
                "root": {
                    "directory": str(root),
                    "authorization": str(root / "authorization.sqlite3"),
                    "manifest_sha256": "a" * 64,
                }
            }
            with patch.object(
                source_feedback, "_build", side_effect=AssertionError("evidence read")
            ):
                with self.assertRaisesRegex(
                    source_feedback.SourceFeedbackError, "inherited search"
                ):
                    source_feedback.build_source_feedback(
                        destination,
                        reference=reference,
                        comparison=comparison,
                        improver_agent_sha256="b" * 64,
                    )
                with self.assertRaises(source_feedback.SourceFeedbackError):
                    source_feedback.build_source_feedback(
                        destination,
                        reference=reference,
                        comparison=comparison | {"parent": {}},
                    )
            self.assertFalse(destination.exists())

    def test_root_work_ceiling_is_capacity_but_cycle_is_corruption(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary).resolve()
            destination = root / "new-feedback"
            comparison = {
                "root": {
                    "directory": str(root),
                    "authorization": str(root / "authorization.sqlite3"),
                    "manifest_sha256": "a" * 64,
                }
            }
            depth = source_feedback._ComparisonObservation(
                active={root / str(index) for index in range(16)}
            )
            with (
                patch.object(source_feedback, "_ComparisonObservation", return_value=depth),
                patch.object(
                    source_feedback, "_build", side_effect=AssertionError("evidence read")
                ),
                self.assertRaisesRegex(
                    source_feedback.SourceFeedbackReconstructionLimit, "depth 16"
                ),
            ):
                source_feedback.build_source_feedback(
                    destination, reference={}, comparison=comparison
                )
            self.assertIsNone(source_feedback._COMPARISON_OBSERVATION.get())
            cycle = source_feedback._ComparisonObservation(active={destination})
            with (
                patch.object(source_feedback, "_ComparisonObservation", return_value=cycle),
                patch.object(
                    source_feedback, "_build", side_effect=AssertionError("evidence read")
                ),
                self.assertRaisesRegex(source_feedback.SourceFeedbackError, "repeats") as raised,
            ):
                source_feedback.build_source_feedback(
                    destination, reference={}, comparison=comparison
                )
            self.assertNotIsInstance(raised.exception, source_feedback.SourceFeedbackTooLarge)
            self.assertEqual(cycle.active, {destination})
            self.assertIsNone(source_feedback._COMPARISON_OBSERVATION.get())
            self.assertFalse(destination.exists())


if __name__ == "__main__":
    unittest.main()
