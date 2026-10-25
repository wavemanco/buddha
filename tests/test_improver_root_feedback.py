"""Fixed-study root packets retain original measured custody and actor identity."""

import copy
import json
import unittest
from pathlib import Path
from unittest.mock import patch

import test_improver_phase_budget as fixtures

from buddha import source_feedback
from buddha.releases import Selection, _json

POLICY = {
    "format": "buddha.improver-study-feedback-comparison.v1",
    "measurements": "complete_literal_outputs",
    "parent": "original_immediate_counted_edge_in_same_cell",
    "root": "no_counted_parent_in_this_cell",
    "counted_failures": "complete_original_cell_history",
    "mutation_witness": "complete_absolute_outputs",
}


class ImproverRootFeedbackTests(unittest.TestCase):
    def fixture(self):
        helper = fixtures.ImproverPhaseBudgetTests("runTest")
        self.addCleanup(helper.doCleanups)
        f, record = helper.finite_fixture()
        record.update(format="buddha.improver-study.v3", feedback_comparison=dict(POLICY))
        directory, declaration, authority = f.prepare_study("fixed-root", record)
        seed = directory / "common/0/0/screen"
        self.assertEqual(f.h.run_screen(seed)["status"], "complete")
        reference = f.h.reference(seed, authority)
        root = {
            "directory": str(directory),
            "authorization": str(authority.path),
            "declaration_sha256": fixtures.sha(declaration.read_bytes()),
            "start": 0,
            "repetition": 0,
            "arm": 0,
        }
        return f, directory, authority, reference, root

    def test_fixed_root_public_build_write_replay_and_strict_actor_scope(self):
        f, directory, authority, reference, root = self.fixture()
        actor = f.actor_id(f.fixed[0])
        packet = f.root / "fixed-root-packet"
        comparison = {"study_root": root}
        original = f.h.files(directory), authority.summary(), authority.path.read_bytes()
        sends = f.engine.physical_sends
        with f.h.readonly():
            built = source_feedback.build_source_feedback(
                packet, reference=reference, comparison=comparison, improver_agent_sha256=actor
            )
            written = source_feedback.write_source_feedback(
                packet, reference=reference, comparison=comparison, improver_agent_sha256=actor
            )
            restored = source_feedback.inspect_source_feedback(
                packet, expected_provenance_sha256=written["provenance"]["sha256"]
            )
            self.assertEqual(
                source_feedback.build_source_feedback(
                    packet,
                    reference=reference,
                    comparison=comparison,
                    improver_agent_sha256=actor,
                    existing=True,
                ),
                restored,
            )
        self.assertEqual(built, restored)
        provenance = restored["provenance"]
        self.assertEqual(provenance["format"], "buddha.source-screen-feedback.v8")
        self.assertEqual(provenance["base_format"], "buddha.source-screen-feedback.v3")
        self.assertEqual(provenance["improver_agent_sha256"], actor)
        self.assertEqual(provenance["comparison"], comparison)
        self.assertEqual(provenance["root_declaration"]["reference"], reference)
        for row in restored["feedback"]["records"]:
            note = json.loads(row["note"])
            self.assertEqual(note["measurements"]["answers"][0]["text"], f.literal)
            self.assertEqual(note["measurements"]["answers"][1]["text"], "")
            self.assertEqual(note["measurements"]["omitted_answer_positions"], 0)
            self.assertIsNone(note["parent_measurements"])
            self.assertEqual(note["comparison"]["reason"], "no_counted_parent_in_this_cell")
            for key in (
                "parent_id",
                "distinct_delta",
                "utility_delta",
                "recorded_cost_delta_microusd",
            ):
                self.assertIsNone(note["comparison"][key])
        self.assertEqual(
            (f.h.files(directory), authority.summary(), authority.path.read_bytes()), original
        )
        self.assertEqual(f.engine.physical_sends, sends)
        actor_record = f.fixed[1]
        descriptor = f.root / "wrong-fixed-actor.json"
        recipe = json.loads((f.root / "bootstrap-proposal.json").read_bytes())
        recipe.update(executor=f.actor_executor(actor_record), feedback=written["feedback"])
        descriptor.write_bytes(_json(recipe))
        wrong_stage = f.root / "wrong-fixed-actor"
        before_wrong_actor = authority.summary(), f.engine.physical_sends
        with self.assertRaises(f.lower.CandidateImprovementError):
            f.lower.prepare_candidate_improvement(
                wrong_stage,
                descriptor=descriptor,
                selection=Selection.from_bytes(_json(actor_record["selection"])),
                roots={key: Path(value) for key, value in actor_record["roots"].items()},
                authorization=authority,
                review=f.engine.fixture.review,
                budget_microusd=f.template["budget_microusd"],
                max_calls=f.template["max_calls"],
                expected_runtime_sha256=f.engine.candidate.expected_runtime,
                expected_feedback_provenance_sha256=written["provenance"]["sha256"],
            )
        self.assertFalse(wrong_stage.exists())
        self.assertEqual((authority.summary(), f.engine.physical_sends), before_wrong_actor)
        bad_roots = [
            root | {key: value}
            for key, value in (
                ("declaration_sha256", "0" * 64),
                ("start", True),
                ("start", 1),
                ("repetition", 1),
                ("arm", 1),
                ("directory", str(f.root)),
            )
        ]
        untouched = f.h.files(f.root), authority.summary(), f.engine.physical_sends
        with f.h.readonly():
            for changed in bad_roots:
                with (
                    self.subTest(root=changed),
                    self.assertRaises(source_feedback.SourceFeedbackError),
                ):
                    source_feedback.write_source_feedback(
                        f.root / "unwritten-root",
                        reference=reference,
                        comparison={"study_root": changed},
                        improver_agent_sha256=actor,
                    )
            for changed_actor in (None, f.actor_id(f.fixed[1])):
                with (
                    self.subTest(actor=changed_actor),
                    self.assertRaises(source_feedback.SourceFeedbackError),
                ):
                    source_feedback.write_source_feedback(
                        f.root / "unwritten-root",
                        reference=reference,
                        comparison=comparison,
                        improver_agent_sha256=changed_actor,
                    )
        self.assertEqual(
            (f.h.files(f.root), authority.summary(), f.engine.physical_sends), untouched
        )

    def test_fixed_root_late_answer_change_refuses_before_publication(self):
        f, directory, authority, reference, root = self.fixture()
        packet = f.root / "changed-root-packet"
        original_build = source_feedback._build
        changed = []

        def after_measurements(*args, **kwargs):
            result = original_build(*args, **kwargs)
            generation = directory / "common/0/0/screen/tasks/0/generation"
            answer = generation / "attempts/0-0/session/answers.json"
            if not answer.exists():
                self.fail("fixture must use its genuine original literal answer artifact")
            raw = answer.read_bytes()
            changed.append((answer, raw))
            answer.write_bytes(raw + b" ")
            return result

        try:
            with (
                f.h.readonly(),
                patch.object(source_feedback, "_build", side_effect=after_measurements),
                self.assertRaises(source_feedback.SourceFeedbackError),
            ):
                source_feedback.write_source_feedback(
                    packet,
                    reference=reference,
                    comparison={"study_root": copy.deepcopy(root)},
                    improver_agent_sha256=f.actor_id(f.fixed[0]),
                )
            self.assertTrue(changed)
            self.assertFalse(packet.exists())
        finally:
            for path, raw in changed:
                path.write_bytes(raw)

    def test_existing_mode_requires_literal_boolean_before_reading_evidence(self):
        with patch.object(source_feedback, "_build", side_effect=AssertionError("evidence read")):
            for value in (0, 1, None, "false"):
                with (
                    self.subTest(existing=value),
                    self.assertRaises(source_feedback.SourceFeedbackError),
                ):
                    source_feedback.build_source_feedback(
                        Path("unused"), reference={}, existing=value
                    )


if __name__ == "__main__":
    unittest.main()
