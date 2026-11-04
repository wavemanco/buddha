"""A complete parent comparison preserves separate inherited failure history."""

import copy
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import test_source_comparison_feedback as comparison_fixtures
import test_source_screen_outcome as outcome_fixtures

from buddha import source_feedback
from buddha.releases import _json, prepare_selection
from buddha.source_feedback import (
    build_source_feedback,
    inspect_source_feedback,
    write_source_feedback,
)


class SourceComparisonHistoryTests(unittest.TestCase):
    def test_nested_comparison_ceiling_refuses_before_evidence_reads_and_resets(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary).resolve()
            ancestors = {root / str(index) for index in range(16)}
            observation = source_feedback._ComparisonObservation(active=set(ancestors))
            with (
                patch.object(source_feedback, "_ComparisonObservation", return_value=observation),
                self.assertRaisesRegex(source_feedback.SourceFeedbackError, "depth 16"),
            ):
                build_source_feedback(
                    root / "feedback",
                    reference={},
                    comparison={"parent": {}, "proposal": {}, "screen": {}},
                )
            self.assertEqual(observation.active, ancestors)
            self.assertIsNone(source_feedback._COMPARISON_OBSERVATION.get())
            self.assertFalse((root / "feedback").exists())

    def test_inherited_comparison_keeps_complete_failure_history_and_both_answer_sets(self):
        fixture = comparison_fixtures.SourceComparisonFeedbackTests("runTest")
        self.addCleanup(fixture.doCleanups)
        fixture.fixture()
        h = fixture.h
        # This subsequent original proposal itself consumes v6. Its failed
        # screen then enters another v6 packet through the v4 base, exercising
        # real nested reconstruction rather than only an injected recursion.
        measured = write_source_feedback(
            h.root / "current-comparison",
            reference=fixture.reference,
            comparison=fixture.comparison,
        )
        returned = {
            "source": "# full failed source\n" + "def generate(:\n" * 100,
            "hypothesis": "A changed failed procedure. " * 30 + "LAST_HYPOTHESIS",
        }
        proposal, directory = fixture.propose(
            "failed-proposal", fixture.current_record, measured, returned
        )
        record = copy.deepcopy(fixture.current_record)
        generation = record["generation"]
        roots = {key: Path(value) for key, value in generation["roots"].items()}
        roots["agent"] = Path(proposal["child"]["directory"])
        generation.update(
            roots={key: str(value) for key, value in roots.items()},
            selection=prepare_selection(
                h.engine.candidate.release,
                roots,
                capabilities=generation["selection"]["capabilities"],
            ).to_record(),
        )
        generation["executor"]["mounts"] = [
            ["/agent", str(roots["agent"])],
            ["/runner", str(roots["runner"])],
        ]
        record["lineage"] = proposal["child"]["lineage"]
        failed = h.screen(record)
        failed_directory, _ = h.prepare(failed, h.root / "failed-screen", fixture.authority)
        with patch.object(
            h,
            "execute",
            side_effect=outcome_fixtures.SourceScreenOutcomeTests.failed_worker(h, "1", h.execute),
        ):
            self.assertEqual(
                h.run_screen(failed_directory)["disposition"], "candidate_execution_failed"
            )
        history = [
            {
                "parent": fixture.reference,
                "proposal": h.reference(directory, fixture.authority),
                "screen": h.reference(failed_directory, fixture.authority),
            }
        ]
        before = fixture.snapshot()
        destination = h.root / "comparison-with-history"
        with h.readonly():
            base = build_source_feedback(
                destination, reference=fixture.reference, failure_history=history
            )
            bundle = build_source_feedback(
                destination,
                reference=fixture.reference,
                failure_history=history,
                comparison=fixture.comparison,
            )
        self.assertEqual(fixture.snapshot(), before)
        self.assertEqual(bundle["provenance"]["base_format"], "buddha.source-screen-feedback.v4")
        self.assertEqual(
            bundle["provenance"]["base_provenance_sha256"],
            comparison_fixtures.sha(_json(base["provenance"])),
        )
        self.assertEqual(bundle["provenance"]["failure_history"], history)
        self.assertEqual(bundle["provenance"]["failures"], base["provenance"]["failures"])
        for row, original in zip(
            bundle["feedback"]["records"], base["feedback"]["records"], strict=True
        ):
            note = json.loads(row["note"])
            self.assertEqual(note["measurements"], json.loads(original["note"]))
            self.assertEqual(note["measurements"]["newest_failure"]["source"], returned["source"])
            self.assertEqual(
                note["measurements"]["newest_failure"]["hypothesis"], returned["hypothesis"]
            )
            self.assertEqual(
                note["comparison"]["distinct_delta"], -1 if type(row["task_id"]) is str else 0
            )
        written = write_source_feedback(
            destination,
            reference=fixture.reference,
            failure_history=history,
            comparison=fixture.comparison,
        )
        before = fixture.snapshot()
        with h.readonly():
            self.assertEqual(
                inspect_source_feedback(
                    destination, expected_provenance_sha256=written["provenance"]["sha256"]
                ),
                bundle,
            )
        self.assertEqual(fixture.snapshot(), before)


if __name__ == "__main__":
    unittest.main()
