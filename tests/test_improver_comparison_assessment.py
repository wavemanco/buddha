"""Prospective v3 development and sealed assessment with supplied workers/replies.

The small original fixture keeps one start, repetition and opportunity per arm,
then assesses three frozen roles on two typed final tasks. Selected programs
are host-execution canaries; this exercises controller custody, not scientific
effectiveness, real judge accuracy or model capacity.
"""

import copy
import json
import os
import unittest
from contextlib import ExitStack
from fractions import Fraction
from pathlib import Path
from unittest.mock import patch

import test_improver_assessment as fixtures
from test_improver_study import LITERAL, TOTALS

from buddha import improver_study
from buddha.releases import Selection, _json


class ImproverComparisonAssessmentTests(unittest.TestCase):
    def test_prospective_comparison_trial_freezes_and_scores_original_six_cell_grid(self):
        f = fixtures.ImproverAssessmentTests("runTest")
        self.addCleanup(f.doCleanups)
        f.setUp()
        f.fixture(observer=self)
        # The reused fixture creates unused zero-owner v1 grants during setup.
        # They remain outside the new prospective v3 trial and never fund it.
        unused_root, unused = f.trial, f.authorities
        unused_summaries = {name: authority.summary() for name, authority in unused.items()}
        self.assertFalse(unused_root.exists())
        self.assertTrue(all(summary["runs"] == [] for summary in unused_summaries.values()))
        f.finite.update(
            format="buddha.improver-study.v3",
            feedback_comparison=dict(improver_study.FEEDBACK_COMPARISON_POLICY),
        )
        for key in ("budget_microusd", "max_calls"):
            f.finite["limits"]["study"][key] -= 1
            f.definition["phase_limits"]["final"][key] -= 1
        f.definition["format"] = "buddha.improver-assessment-trial.v3"
        f.definition["development"] = f.write("comparison-development.json", f.finite)
        f.definition["phase_limits"]["search"] = copy.deepcopy(f.finite["limits"]["study"])
        self.assertEqual(
            f.plan["counts"],
            {
                "starts": 1,
                "development_repetitions": 1,
                "m": 1,
                "tasks": 2,
                "sealed_repetitions": 1,
            },
        )
        f.bind("comparison-sealed-v3")
        self.assertFalse(f.trial.exists())
        self.assertTrue(
            all(authority.summary()["runs"] == [] for authority in f.authorities.values())
        )
        before_prepare = f.engine.physical_sends, len(f.f.events)
        self.assertEqual(f.prepare(), f.trial)
        self.assertEqual((f.engine.physical_sends, len(f.f.events)), before_prepare)
        development = f.develop()
        self.assertEqual([row["status"] for row in development["decisions"]], ["admitted"] * 2)
        f.f.assert_accounting(f.study, f.authorities["search"], development, f.finite)
        expected_answers = [{"position": 0, "text": LITERAL}, {"position": 1, "text": ""}]
        for arm in range(2):
            packet = f.study / "cells/0/0" / str(arm) / "0/feedback"
            provenance = json.loads((packet / "provenance.json").read_bytes())
            self.assertEqual(provenance["format"], "buddha.source-screen-feedback.v8")
            self.assertEqual(provenance["comparison"]["study_root"]["arm"], arm)
            note = json.loads(
                json.loads((packet / "feedback.json").read_bytes())["records"][0]["note"]
            )
            self.assertEqual(note["comparison"]["reason"], "no_counted_parent_in_this_cell")
            self.assertEqual(note["measurements"]["answers"], expected_answers)
        schedule = f.freeze()
        self.assertEqual(
            schedule["counts"],
            {
                "cells": 6,
                "maximum_cells": 6,
                "conditions": 1,
                "descendant_slots": 2,
                "no_valid_descendant_slots": 0,
            },
        )
        self.assertEqual(_json(schedule["selected_ids"]), b'[1,"final"]')
        self.assertEqual(
            [arm["role"] for arm in schedule["arms"]], ["starter", "initial", "evolved"]
        )
        self.assertEqual(schedule["arms"][1]["sha256"], schedule["arms"][2]["sha256"])
        common_packet = f.study / "common/0/0/witness/feedback"
        common = json.loads((common_packet / "provenance.json").read_bytes())
        self.assertEqual(common["format"], "buddha.source-screen-feedback.v3")
        common_note = json.loads(
            json.loads((common_packet / "feedback.json").read_bytes())["records"][0]["note"]
        )
        self.assertNotIn("comparison", common_note)
        self.assertEqual(common_note["answers"], expected_answers)
        common_refs = {
            name: {
                "path": str(common_packet / (name + ".json")),
                "sha256": fixtures.sha((common_packet / (name + ".json")).read_bytes()),
            }
            for name in ("source", "split", "feedback", "provenance")
        }
        selected = {row["arm"]: row for row in development["selections"]}
        for slot in schedule["slots"]:
            self.assertEqual(slot["status"], "selected")
            self.assertEqual(slot["common"]["feedback"], common_refs)
            self.assertEqual(slot["candidate_id"], selected[slot["arm"]]["candidate_id"])
            self.assertNotEqual(slot["candidate_id"], slot["starter_agent_sha256"])
        for arm in schedule["arms"]:
            raw = Path(arm["path"]).read_bytes()
            self.assertEqual(raw, Path(arm["origin"]).read_bytes())
            self.assertEqual(fixtures.sha(raw), arm["sha256"])
            self.assertIn(b"selected-module host-exec canary:", raw)
        improvements = len(f.f.improvements)
        with f.supplied():
            result = f.run_assessment()
        self.assertEqual(result["status"], "complete", _json(result).decode())
        self.assertEqual(result["coverage"], {"expected": 6, "generated": 6, "evaluated": 6})
        self.assertEqual(result["slots"], schedule["slots"])
        self.assertEqual(result["arms"], schedule["arms"])
        self.assertEqual(result["development_costs"], development["costs"])
        self.assertTrue(result["analysis"]["coverage"]["complete"])
        self.assertEqual(result["analysis"]["coverage"]["maximum_rows"], 6)
        self.assertEqual(
            result["analysis"]["contrasts"]["improver_effect"]["utility"]["point"],
            fixtures.ratio(Fraction(2)),
        )
        self.assertEqual(len(f.f.improvements), improvements, "sealed work starts no new search")
        for _, _, _, initial in f.final_events:
            self.assertNotIn("feedback", initial)
        outer = {f.declaration: fixtures.sha(f.declaration.read_bytes())}
        outer.update(
            {
                f.trial / name: fixtures.sha((f.trial / name).read_bytes())
                for name in (
                    ".buddha-evaluation-trial.json",
                    "definition.json",
                    "context.json",
                    "funding.json",
                )
            }
        )
        final_pins = {
            f.trial / "freeze" / name: fixtures.sha((f.trial / "freeze" / name).read_bytes())
            for name in ("schedule.json", "ready.json")
        } | {Path(ref["path"]): ref["sha256"] for ref in common_refs.values()}
        for phase in ("search", "final"):
            owners = f.f.owner_paths(f.trial / phase)
            self.assertTrue(owners)
            for owner in owners:
                manifest = json.loads((owner / "manifest.json").read_bytes())
                bindings = {row["path"]: row["sha256"] for row in manifest["invocation"]["inputs"]}
                required = outer | (final_pins if phase == "final" else {})
                self.assertTrue(
                    all(bindings.get(str(path)) == digest for path, digest in required.items())
                )
        self.assertEqual(len(f.f.owner_paths(f.trial / "final")), 24)
        for arm in schedule["arms"]:
            for task in range(2):
                owner = (
                    f.trial
                    / "final/arms"
                    / str(arm["arm_index"])
                    / "tasks"
                    / str(task)
                    / "repetitions/0/generation/owners/0"
                )
                manifest = json.loads((owner / "manifest.json").read_bytes())
                selected_source = Selection.from_bytes(_json(manifest["selection"]))
                self.assertEqual(selected_source.agent_sha256, arm["agent_sha256"])
        for phase in ("search", "final"):
            summary = f.authorities[phase].summary()
            self.assertEqual(summary["reserved_microusd"], 0)
            self.assertFalse(any(row["active"] for row in summary["runs"]))
            self.assertLessEqual(
                summary["committed_microusd"],
                f.definition["phase_limits"][phase]["budget_microusd"],
            )
            self.assertLessEqual(
                summary["operation_count"], f.definition["phase_limits"][phase]["max_calls"]
            )
        final_summary = f.authorities["final"].summary()
        for key in TOTALS:
            self.assertEqual(result["authorization"][key], final_summary[key])
        self.assertEqual(f.authorities["validation"].summary()["runs"], [])
        self.assertFalse(unused_root.exists())
        self.assertEqual(
            {name: authority.summary() for name, authority in unused.items()}, unused_summaries
        )
        before = (
            fixtures.files(f.root),
            f.engine.physical_sends,
            len(f.f.events),
            len(f.final_events),
        )
        with ExitStack() as stack:
            stack.enter_context(patch.dict(os.environ, {}, clear=True))
            stack.enter_context(f.f.h.readonly())
            stack.enter_context(
                patch(
                    "buddha.trial_fence.lease", side_effect=AssertionError("passive writer lease")
                )
            )
            self.assertEqual(f.inspect(), result)
        self.assertEqual(
            (fixtures.files(f.root), f.engine.physical_sends, len(f.f.events), len(f.final_events)),
            before,
        )
        # An external observer can retain these original bytes after cleanup.
        # They are a bounded observation, not a replacement replay inventory.
        retained = [f.declaration]
        retained += [
            f.trial / name
            for name in (
                ".buddha-evaluation-trial.json",
                "definition.json",
                "context.json",
                "funding.json",
                "freeze/schedule.json",
                "freeze/ready.json",
                "final/report.json",
            )
        ]
        retained += [
            f.study / name
            for name in (
                "declaration.json",
                "context.json",
                "report.json",
                "freeze/selections.json",
                "freeze/confirmation.json",
            )
        ]
        retained += [common_packet / (name + ".json") for name in common_refs]
        for arm in range(2):
            packet = f.study / "cells/0/0" / str(arm) / "0/feedback"
            retained += [packet / name for name in ("feedback.json", "provenance.json")]
        for arm in schedule["arms"]:
            for task in range(2):
                generation = (
                    f.trial
                    / "final/arms"
                    / str(arm["arm_index"])
                    / "tasks"
                    / str(task)
                    / "repetitions/0/generation"
                )
                seal = generation / "completed/0.json"
                completion = json.loads(seal.read_bytes())
                answers = generation / completion["attempt"] / "session/answers.json"
                self.assertEqual(
                    fixtures.sha(answers.read_bytes()), completion["files"]["session/answers.json"]
                )
                retained += [seal, answers]
        self.retained_evidence = {
            path.relative_to(f.root).as_posix(): path.read_bytes() for path in retained
        }
        self.observation = {
            "qualification": "supplied workers and replies; no scientific or model-capacity claim",
            "fixture_root": str(f.root),
            "trial": str(f.trial),
            "study_format": f.finite["format"],
            "assessment_format": f.definition["format"],
            "development_coverage": development["coverage"],
            "schedule_counts": schedule["counts"],
            "final_coverage": result["coverage"],
            "analysis": result["analysis"],
            "accounting": {
                "search": development["costs"]["totals"],
                "final": {key: final_summary[key] for key in TOTALS},
            },
            "consumer_sources": f.definition["consumer_sources"],
            "source_joins": schedule["arms"],
            "artifact_sha256": {
                name: fixtures.sha(raw) for name, raw in self.retained_evidence.items()
            },
            "keyless_replay_unchanged": True,
        }


if __name__ == "__main__":
    unittest.main()
