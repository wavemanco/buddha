"""Original finite-cell comparisons with supplied workers and no selected-code execution.

One task, start and repetition keep the genuine controller fixture bounded.
Counted proposals use no model callbacks; existing frozen-improver tests retain
separate charged-callback coverage. Generation/native owners remain genuine.
"""

import copy
import json
import os
import unittest
from unittest.mock import patch

import test_improver_study as fixtures
from test_improver_comparison_contract import COMPARISON_POLICY

from buddha import improver_study, source_feedback
from buddha.gateway import RawHTTPTransport
from buddha.releases import _json


class ImproverComparisonLifecycleTests(unittest.TestCase):
    def fixture(self):
        f = fixtures.FiniteImproverStudyTests("runTest")
        self.addCleanup(f.doCleanups)
        f.fixture_before_new_api()
        fixtures.observe_fixture_workers(f, self)
        f.api = improver_study
        record = f.declaration(improver_study)
        record.update(
            format="buddha.improver-study.v3",
            starts=record["starts"][:1],
            repetitions=1,
            descendant_opportunities=2,
            feedback_comparison=dict(COMPARISON_POLICY),
        )
        record["selection"]["finalist_iteration"] = 2
        f.recompute_limits(record)
        f.outcomes = {(0, 0, 0, 1): "rejected", (0, 0, 1, 0): "failed"}
        f.baseline_utility = 7
        self.counted = []
        original_improve, original_generation = f.improve, f.original_execute

        def measured(spec, *, initial, handle, **kwargs):
            if spec.role == "agent":
                raw = (dict(spec.mounts)["/agent"] / "candidate.py").read_bytes()
                lower = raw.startswith(b"# supplied source: OWN-C-")
                f.h.programs[initial["agent_sha256"]].update(
                    distinct=1 if lower else 2, utility=4 if lower else 7
                )
            return original_generation(spec, initial=initial, handle=handle, **kwargs)

        def improve(spec, initial, handle):
            owner = handle.__self__.gateway.directory
            if "cells" not in owner.parts or "witness" in owner.parts:
                return original_improve(spec, initial, handle)
            suffix = owner.parts[owner.parts.index("cells") + 1 :]
            cell = tuple(int(value) for value in suffix[:4])
            start, repetition, arm, slot = cell
            self.assertEqual((start, repetition), (0, 0))
            self.assertEqual(initial["format"], "buddha.candidate-improvement-worker.v3")
            self.assertEqual(initial["agent_sha256"], f.actor_id(f.fixed[arm]))
            raw = (dict(spec.mounts)["/agent"] / "candidate.py").read_bytes()
            self.assertEqual(raw, (f.root / ("I" + str(arm)) / "candidate.py").read_bytes())
            parent = initial["parent_bundle"]
            self.assertEqual(
                parent["agent_sha256"],
                fixtures.sha(_json({"candidate.py": fixtures.sha(parent["source"].encode())})),
            )
            self.assertEqual([row["task"]["id"] for row in initial["feedback"]], [fixtures.TASK_ID])
            for row in initial["feedback"]:
                note = json.loads(row["note"])
                while "answers" not in note:
                    note = note["measurements"]
                self.assertEqual(
                    note["answers"],
                    [{"position": 0, "text": fixtures.LITERAL}, {"position": 1, "text": ""}],
                )
                self.assertEqual(note["omitted_answer_positions"], 0)
            for private in (
                b"VALIDATION-ONLY-SENTINEL",
                b"FINAL-ONLY-SENTINEL",
                b"dataset_base64",
                b"operations.sqlite3",
            ):
                self.assertNotIn(private, _json(initial["feedback"]))
            outcome = f.outcomes.get(cell, "valid")
            label = "checked-generation-failure-" if outcome == "failed" else "OWN-C-"
            child = fixtures.source(label + "-".join(map(str, cell)))
            value = (
                {}
                if outcome == "rejected"
                else {
                    "source": child.decode(),
                    "hypothesis": "Supplied own-cell comparison mutation.",
                }
            )
            self.counted.append(
                {
                    "owner": owner,
                    "cell": cell,
                    "agent_id": initial["agent_sha256"],
                    "parent": copy.deepcopy(parent),
                    "feedback": copy.deepcopy(initial["feedback"]),
                    "source": raw,
                }
            )
            f.engine.workers += 1
            handle(
                {
                    "type": "ready",
                    "agent_sha256": initial["agent_sha256"],
                    "parent_agent_sha256": parent["agent_sha256"],
                    "feedback_sha256": fixtures.sha(_json(initial["feedback"])),
                    "runtime_sha256": f.engine.candidate.expected_runtime,
                }
            )
            handle(
                {
                    "type": "done",
                    "status": "failed" if outcome == "rejected" else "complete",
                    "reason": "invalid_proposal" if outcome == "rejected" else "complete",
                    "proposal": {
                        "status": "captured",
                        "value": value,
                        "sha256": fixtures.sha(_json(value)),
                        "bytes": len(_json(value)),
                    },
                }
            )
            return f.engine.execution(spec)

        f.original_execute, f.improve = measured, improve
        return f, record

    @staticmethod
    def note(event):
        return json.loads(event["feedback"][0]["note"])

    @staticmethod
    def packet(event):
        return event["owner"].parents[2] / "feedback"

    def test_actual_fixed_operators_receive_own_cell_roots_edges_failures_and_keyless_replay(self):
        f, record = self.fixture()
        # The first prospective v3 operation follows genuine legacy screen and
        # detached-proposal setup. Before implementation this valid declaration
        # is refused before any counted study worker or proposal owner exists.
        directory, declaration, authority = f.prepare_study("comparison-study", record)
        stopped_owners = []

        def limited_once(scope, state, action, authorization):
            # This supplied resource stop checks the real catch/publication and
            # resume path; it does not claim actual ancestry-depth exhaustion.
            self.assertEqual(action["coordinate"], (0, 0, 0, 0))
            self.assertEqual(state["coverage"]["completed_common"], 1)
            self.assertEqual(
                json.loads((scope / "common/0/0/witness/report.json").read_bytes())["status"],
                "passed",
            )
            self.assertFalse(stopped_owners)
            stopped_owners.append(f.owner_paths(scope))
            raise source_feedback.SourceFeedbackReconstructionLimit("supplied resource stop")

        with patch.object(improver_study, "_write_plan", side_effect=limited_once):
            partial = f.run_study(directory)
        self.assertEqual(partial["status"], "incomplete")
        self.assertEqual(partial["reason"], "feedback_reconstruction_limit")
        self.assertIsNone(partial["child"])
        self.assertEqual(
            partial["position"],
            {"start": 0, "repetition": 0, "arm": 0, "slot": 0, "stage": "feedback"},
        )
        self.assertEqual(
            partial["coverage"],
            {
                "expected_common": 1,
                "completed_common": 1,
                "expected_cells": 2,
                "completed_cells": 0,
                "expected_opportunities": 4,
                "attempted_opportunities": 0,
                "completed_opportunities": 0,
                "in_flight_opportunities": 0,
                "unattempted_opportunities": 4,
            },
        )
        self.assertEqual(partial["authorization"]["reserved_microusd"], 0)
        self.assertEqual(f.owner_paths(directory), stopped_owners[0])
        self.assertFalse((directory / "cells").exists())
        self.assertEqual(self.counted, [])
        observation = directory / "observations/0.json"
        saved_partial = observation.read_bytes()
        self.assertEqual(saved_partial, _json(partial))
        report = f.run_study(directory)
        self.assertEqual(observation.read_bytes(), saved_partial)
        self.assertEqual(
            report["provenance"]["observations"],
            {"observations/0.json": fixtures.sha(saved_partial)},
        )
        self.assertEqual(report["status"], "complete", _json(report).decode())
        self.assertEqual(report["coverage"]["completed_opportunities"], 4)
        decisions = {
            tuple(row[key] for key in fixtures.COORDINATES): row for row in report["decisions"]
        }
        self.assertEqual(
            {key: row["status"] for key, row in decisions.items()},
            {
                (0, 0, 0, 0): "admitted",
                (0, 0, 0, 1): "rejected",
                (0, 0, 1, 0): "candidate_execution_failed",
                (0, 0, 1, 1): "admitted",
            },
        )
        events = {event["cell"]: event for event in self.counted}
        self.assertEqual(set(events), set(decisions))
        for event in events.values():
            packet = self.packet(event)
            plan = json.loads((packet.parent / "plan.json").read_bytes())
            provenance = json.loads((packet / "provenance.json").read_bytes())
            self.assertEqual(plan["format"], "buddha.improver-study-plan.v2")
            self.assertEqual(plan["feedback_comparison"], provenance["comparison"])
        witnesses = [event for event in f.improvements if event["witness"]]
        self.assertEqual(len(witnesses), 3)
        for event in witnesses:
            self.assertNotIn("comparison", json.loads(event["feedback"][0]["note"]))
        common_ref = f.h.reference(directory / "common/0/0/screen", authority)
        root_events = [events[key] for key in ((0, 0, 0, 0), (0, 0, 1, 0), (0, 0, 1, 1))]
        for event in root_events:
            note = self.note(event)
            self.assertEqual(note["comparison"]["status"], "unavailable")
            self.assertEqual(note["comparison"]["reason"], "no_counted_parent_in_this_cell")
            self.assertEqual(note["comparison"]["current_id"], f.base.candidate_id)
            for key in (
                "parent_id",
                "utility_delta",
                "distinct_delta",
                "recorded_cost_delta_microusd",
            ):
                self.assertIsNone(note["comparison"][key])
            self.assertIsNone(note["parent_measurements"])
            provenance = json.loads((self.packet(event) / "provenance.json").read_bytes())
            self.assertEqual(provenance["format"], "buddha.source-screen-feedback.v8")
            self.assertEqual(provenance["improver_agent_sha256"], event["agent_id"])
            self.assertEqual(provenance["reference"], common_ref)
            self.assertEqual(
                provenance["comparison"],
                {
                    "study_root": {
                        "directory": str(directory),
                        "authorization": str(authority.path),
                        "declaration_sha256": fixtures.sha(declaration.read_bytes()),
                        "start": 0,
                        "repetition": 0,
                        "arm": event["cell"][2],
                    }
                },
            )
        lower = decisions[(0, 0, 0, 0)]
        edge = {name: lower[name] for name in ("parent", "proposal", "screen")}
        compared = events[(0, 0, 0, 1)]
        note = self.note(compared)
        self.assertEqual(note["comparison"]["parent_id"], f.base.candidate_id)
        self.assertEqual(note["comparison"]["current_id"], lower["candidate_id"])
        self.assertEqual(note["comparison"]["delta_direction"], "current_minus_parent")
        self.assertEqual(note["comparison"]["utility_delta"], -3)
        self.assertEqual(note["comparison"]["distinct_delta"], -1)
        for key in ("measurements", "parent_measurements"):
            self.assertEqual(
                note[key]["answers"],
                [{"position": 0, "text": fixtures.LITERAL}, {"position": 1, "text": ""}],
            )
            self.assertEqual(note[key]["omitted_answer_positions"], 0)
        provenance = json.loads((self.packet(compared) / "provenance.json").read_bytes())
        self.assertEqual(provenance["format"], "buddha.source-screen-feedback.v6")
        self.assertEqual(provenance["comparison"], edge)
        failed = decisions[(0, 0, 1, 0)]
        repaired = events[(0, 0, 1, 1)]
        retained = self.note(repaired)["measurements"]
        self.assertEqual(retained["kind"], "saved_native_measurements_and_failed_children")
        self.assertEqual(len(retained["failures"]), 1)
        self.assertEqual(retained["failures"][0]["improver_id"], repaired["agent_id"])
        self.assertEqual(retained["failures"][0]["reason"], "agent_error")
        self.assertIn("checked-generation-failure-0-0-1-0", retained["newest_failure"]["source"])
        self.assertEqual(retained["newest_failure"]["source_omitted_utf8_bytes"], 0)
        self.assertEqual(
            retained["measurements"]["answers"],
            [{"position": 0, "text": fixtures.LITERAL}, {"position": 1, "text": ""}],
        )
        provenance = json.loads((self.packet(repaired) / "provenance.json").read_bytes())
        self.assertEqual(provenance["failure_history"], [{name: failed[name] for name in edge}])
        self.assertEqual(provenance["base_format"], "buddha.source-screen-feedback.v5")
        # Even the starter dominates the admitted lower child: descendant-only
        # final selection must retain the original child instead of hiding it.
        selected = {row["arm"]: row for row in report["selections"]}
        self.assertEqual(selected[0]["candidate_id"], lower["candidate_id"])
        self.assertNotEqual(selected[0]["candidate_id"], f.base.candidate_id)
        f.assert_accounting(directory, authority, report, record)
        before = f.h.files(directory), authority.summary(), f.engine.physical_sends, len(f.events)
        with f.h.readonly(), patch.dict(os.environ, {}, clear=True):
            reader, state = improver_study._restore(directory, authority.path)
            previous = state["cell_decisions"][(0, 0, 0)][:1]
            coordinate = (0, 0, 0, 1)
            self.assertEqual(
                improver_study._comparison_for(
                    reader, state, coordinate, lower["screen"], previous
                ),
                edge,
            )
            wrong = [
                decisions[(0, 0, 1, 1)]["screen"],
                lower["screen"] | {"report_sha256": "0" * 64},
                lower["screen"] | {"authorization": str(f.root / "other.sqlite3")},
            ]
            for reference in wrong:
                with (
                    self.subTest(reference=reference),
                    self.assertRaises(improver_study.ImproverStudyError),
                ):
                    improver_study._comparison_for(reader, state, coordinate, reference, previous)
            reader.finish()
            self.assertEqual(
                improver_study.run_improver_study(
                    directory, transport=RawHTTPTransport(allow_paid=False)
                ),
                report,
            )
        self.assertEqual(
            (f.h.files(directory), authority.summary(), f.engine.physical_sends, len(f.events)),
            before,
        )


if __name__ == "__main__":
    unittest.main()
