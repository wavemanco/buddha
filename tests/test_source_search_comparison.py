"""Opt-in comparison reaches counted and pre-decision witness workers."""

import json
import unittest
from unittest.mock import patch

import test_source_mutation_witness as witness_fixtures
import test_source_search as search_fixtures

from buddha import source_feedback, source_search
from buddha.native_evidence import NativeEvidence
from buddha.releases import MAX_FEEDBACK_BYTES, _json


class SourceSearchComparisonTests(unittest.TestCase):
    def test_explicit_comparison_preparation_declares_new_manifest_before_any_send(self):
        h = witness_fixtures._Harness(self, iterations=1)
        case = h.case
        case.prepare(source_copy=True, feedback_comparison=True)
        manifest = json.loads((case.directory / "manifest.json").read_bytes())
        self.assertEqual(manifest["format"], "buddha.source-search-manifest.v6")
        self.assertEqual(manifest["feedback_comparison"], source_search.FEEDBACK_COMPARISON_POLICY)
        self.assertEqual(case.engine.physical_sends, 0)

    def test_invalid_comparison_flags_refuse_before_search_or_owner_preparation(self):
        h = witness_fixtures._Harness(self, iterations=1)
        case = h.case
        before = case.authority.summary()
        for invalid in (None, 0, 1, "true", {}):
            with self.subTest(value=invalid), self.assertRaises(case.Error):
                case.prepare(source_copy=True, feedback_comparison=invalid)
            self.assertFalse(case.directory.exists())
            self.assertEqual(case.authority.summary(), before)

    def test_comparison_requires_witnessed_verified_copies_before_search_preparation(self):
        h = witness_fixtures._Harness(self, iterations=1)
        case = h.case
        before = case.authority.summary()
        for changes in (
            {"mutation_witness": False, "source_copy": False},
            {"mutation_witness": True, "source_copy": False},
            {"mutation_witness": False, "source_copy": True},
        ):
            with self.subTest(changes=changes), self.assertRaises(case.Error):
                case.prepare(feedback_comparison=True, **changes)
            self.assertFalse(case.directory.exists())
            self.assertEqual(case.authority.summary(), before)

    def test_omitted_and_explicit_false_preserve_the_same_legacy_manifest_bytes(self):
        h = witness_fixtures._Harness(self, iterations=1)
        case = h.case
        case.prepare(source_copy=True)
        old = (case.directory / "manifest.json").read_bytes()
        self.assertEqual(json.loads(old)["format"], "buddha.source-search-manifest.v4")
        self.assertNotIn("feedback_comparison", json.loads(old))
        case.directory = case.root / "explicit-false-search"
        case.prepare(source_copy=True, feedback_comparison=False)
        self.assertEqual((case.directory / "manifest.json").read_bytes(), old)
        self.assertEqual(case.engine.physical_sends, 0)

    def lower_child_fixture(self):
        h = witness_fixtures._Harness(self, iterations=2)
        case = h.case
        h.normal_sources = [search_fixtures.REPAIRED, search_fixtures.GRANDCHILD]
        # These supplied proposals need the original protected worker/owner,
        # rather than another echoed provider request. Charged proposal callback
        # custody has separate composed coverage in test_source_comparison_feedback.
        h.normal_callbacks = 0
        original = case.h.execute
        improve = case.execute_improvement

        def measured(spec, *, initial, handle, **kwargs):
            if spec.role == "agent":
                program = case.h.programs[initial["agent_sha256"]]
                lower = initial["agent_sha256"] != case.seed.candidate_id
                # Supplied native measurements exercise host evidence transport;
                # this fixture does not claim real judge accuracy or confinement.
                program.update(distinct=1 if lower else 2, utility=4 if lower else 7)
            return original(spec, initial=initial, handle=handle, **kwargs)

        case.h.execute = measured

        def observed(spec, initial, handle, source):
            witness = h.witness_root(handle.__self__.gateway.directory)
            decision_present = (
                (witness.parent / "decision.json").exists() if witness is not None else None
            )
            result = improve(spec, initial, handle, source)
            h.improvements[-1]["counted_decision_present"] = decision_present
            return result

        case.execute_improvement = observed
        return h

    @staticmethod
    def notes(event):
        return [json.loads(row["note"]) for row in event["feedback"]]

    @staticmethod
    def run_checked(h, *, paid=True):
        with search_fixtures._synthetic_recovery_errors():
            try:
                return h.run(paid=paid)
            except source_search.SourceSearchStopped as error:
                error.add_note("Synthetic search partial: " + _json(error.partial).decode())
                raise

    def test_actual_root_and_child_comparison_reach_predecision_and_counted_workers(self):
        h = self.lower_child_fixture()
        case = h.case
        original_source = (case.engine.fixture.roots["agent"] / "candidate.py").read_bytes()
        case.prepare(source_copy=True, feedback_comparison=True)
        result = self.run_checked(h)
        self.assertEqual(result["status"], "complete")
        self.assertEqual([row["status"] for row in result["decisions"]], ["admitted"] * 2)
        self.assertEqual(result["selection"]["frontier_ids"], [case.seed.candidate_id])
        child_id = witness_fixtures.agent(search_fixtures.REPAIRED)
        counted = [event for event in h.improvements if event["witness"] is None]
        self.assertEqual(
            [event["parent_id"] for event in counted], [case.seed.candidate_id, child_id]
        )
        child_witness = [
            event
            for event in h.improvements
            if event["witness"] is not None and event["parent_id"] == child_id
        ]
        self.assertEqual(len(child_witness), 1)
        # This witness's original proposal executes before its child's counted
        # decision exists. A lookup restricted to published decisions loses it.
        self.assertIs(child_witness[0]["counted_decision_present"], False)
        self.assertEqual(child_witness[0]["source"], search_fixtures.REPAIRED.encode())
        expected_answers = [
            {"position": 0, "text": witness_fixtures.LONG_ANSWER},
            {"position": 1, "text": ""},
        ]
        root_events = [
            event for event in h.improvements if event["parent_id"] == case.seed.candidate_id
        ]
        self.assertEqual(len(root_events), 2)
        for event in root_events:
            provenance = json.loads(
                (event["owner"].parents[2] / "feedback/provenance.json").read_bytes()
            )
            self.assertEqual(provenance["format"], "buddha.source-screen-feedback.v7")
            for note in self.notes(event):
                self.assertEqual(note["measurements"]["answers"], expected_answers)
                self.assertEqual(note["measurements"]["omitted_answer_positions"], 0)
                self.assertIsNone(note["parent_measurements"])
                self.assertEqual(note["comparison"]["status"], "unavailable")
                self.assertEqual(note["comparison"]["reason"], "no_counted_parent_in_this_search")
                self.assertIsNone(note["comparison"]["utility_delta"])
                self.assertIsNone(note["comparison"]["distinct_delta"])
                self.assertIsNone(note["comparison"]["recorded_cost_delta_microusd"])
        expected_edge = {
            "parent": case.h.reference(case.directory / "seed", case.authority),
            "proposal": case.h.reference(case.directory / "iterations/0/proposal", case.authority),
            "screen": case.h.reference(case.directory / "iterations/0/screen", case.authority),
        }
        for event in [child_witness[0], counted[1]]:
            self.assertEqual(_json([row["task"]["id"] for row in event["feedback"]]), b'["1",1]')
            provenance = json.loads(
                (event["owner"].parents[2] / "feedback/provenance.json").read_bytes()
            )
            self.assertEqual(provenance["format"], "buddha.source-screen-feedback.v6")
            self.assertEqual(provenance["comparison"], expected_edge)
            for note in self.notes(event):
                self.assertEqual(note["measurements"]["answers"], expected_answers)
                self.assertEqual(note["parent_measurements"]["answers"], expected_answers)
                self.assertEqual(note["measurements"]["omitted_answer_positions"], 0)
                self.assertEqual(note["parent_measurements"]["omitted_answer_positions"], 0)
                self.assertEqual(note["comparison"]["parent_id"], case.seed.candidate_id)
                self.assertEqual(note["comparison"]["current_id"], child_id)
                self.assertEqual(note["comparison"]["delta_direction"], "current_minus_parent")
                self.assertEqual(note["comparison"]["distinct_delta"], -1)
                self.assertEqual(note["comparison"]["utility_delta"], -3)
            for private in (
                b"VALIDATION-ONLY-SENTINEL",
                b"FINAL-ONLY-SENTINEL",
                b"dataset_base64",
                b"operations.sqlite3",
                str(case.directory).encode(),
            ):
                self.assertNotIn(private, _json(event["feedback"]))
        self.assertEqual(
            (case.engine.fixture.roots["agent"] / "candidate.py").read_bytes(), original_source
        )
        before = (
            case.h.files(case.directory),
            case.authority.summary(),
            case.engine.physical_sends,
            len(h.improvements),
            len(h.generations),
        )
        with case.h.readonly():
            reader = NativeEvidence(case.directory, case.authority.path, error_type=case.Error)
            state = source_search._restore(
                case.directory, case.authority.path, complete=True, reader=reader
            )
            # The latest decision now belongs to G. Selecting older C must still
            # resolve C's original P-to-C edge, never the latest C-to-G edge.
            self.assertNotEqual(result["decisions"][-1]["screen"], expected_edge["screen"])
            self.assertEqual(
                source_search._comparison_for(reader, state, expected_edge["screen"]),
                expected_edge,
            )
            for changed in (
                expected_edge["screen"] | {"report_sha256": "0" * 64},
                expected_edge["screen"]
                | {"directory": result["decisions"][-1]["screen"]["directory"]},
                expected_edge["screen"] | {"authorization": str(case.root / "another.sqlite3")},
            ):
                with self.subTest(changed=changed), self.assertRaises(case.Error):
                    source_search._comparison_for(reader, state, changed)
            reader.finish()
        with patch.object(case, "execute", side_effect=AssertionError("new worker during replay")):
            self.assertEqual(self.run_checked(h, paid=False), result)
        self.assertEqual(
            (
                case.h.files(case.directory),
                case.authority.summary(),
                case.engine.physical_sends,
                len(h.improvements),
                len(h.generations),
            ),
            before,
        )

    def test_root_comparison_preserves_complete_failed_child_history(self):
        h = witness_fixtures._Harness(self, iterations=2)
        case = h.case
        h.normal_sources = [search_fixtures.BROKEN, search_fixtures.REPAIRED]
        h.normal_callbacks = 0
        case.prepare(source_copy=True, feedback_comparison=True)
        result = self.run_checked(h)
        self.assertEqual(result["status"], "complete")
        self.assertEqual(
            [row["status"] for row in result["decisions"]],
            ["candidate_execution_failed", "admitted"],
        )
        self.assertEqual(len(result["failures"]), 1)
        counted = [event for event in h.improvements if event["witness"] is None]
        self.assertEqual(len(counted), 2)
        for note in self.notes(counted[1]):
            self.assertEqual(note["comparison"]["status"], "unavailable")
            self.assertEqual(note["comparison"]["reason"], "no_counted_parent_in_this_search")
            retained = note["measurements"]
            self.assertEqual(retained["kind"], "saved_native_measurements_and_failed_children")
            self.assertEqual(retained["newest_failure"]["source"], search_fixtures.BROKEN)
            self.assertEqual(
                retained["newest_failure"]["hypothesis"], "Supplied bounded witness mutation."
            )
            self.assertEqual(len(retained["failures"]), 1)
            self.assertEqual(retained["failures"][0]["reason"], "agent_error")
            self.assertEqual(
                retained["measurements"]["answers"],
                [
                    {"position": 0, "text": witness_fixtures.LONG_ANSWER},
                    {"position": 1, "text": ""},
                ],
            )
        provenance = json.loads(
            (case.directory / "iterations/1/feedback/provenance.json").read_bytes()
        )
        self.assertEqual(provenance["format"], "buddha.source-screen-feedback.v7")
        self.assertEqual(provenance["base_format"], "buddha.source-screen-feedback.v4")
        self.assertEqual(provenance["failure_history"], result["failures"])

    def test_parent_addition_capacity_stops_before_child_witness_owner_without_truncation(self):
        h = witness_fixtures._Harness(self, iterations=2)
        case = h.case
        h.normal_sources = [search_fixtures.REPAIRED, search_fixtures.GRANDCHILD]
        h.normal_callbacks = 0
        literal = "x" * 280_000
        case.prepare(source_copy=True, feedback_comparison=True)
        with patch.object(witness_fixtures, "LONG_ANSWER", literal):
            with self.assertRaises(source_search.SourceSearchStopped) as stopped:
                self.run_checked(h)
        partial = stopped.exception.partial
        case.partial(partial)
        self.assertEqual(partial["reason"], "feedback_capacity")
        self.assertEqual(partial["stage"], "witness_feedback")
        self.assertEqual(partial["iteration"], 0)
        self.assertFalse((case.directory / "iterations/0/witness/proposal").exists())
        self.assertFalse((case.directory / "iterations/0/witness/feedback").exists())
        self.assertFalse((case.directory / "iterations/0/decision.json").exists())
        self.assertFalse((case.directory / "iterations/1").exists())
        self.assertTrue((case.directory / "iterations/0/screen/report.json").is_file())
        self.assertGreater(partial["authorization"]["spent_microusd"], 0)
        self.assertEqual(partial["authorization"]["reserved_microusd"], 0)
        before = case.h.files(case.root), case.authority.summary(), case.engine.physical_sends
        for name, screen in (
            ("parent", case.directory / "seed"),
            ("current", case.directory / "iterations/0/screen"),
        ):
            reference = case.h.reference(screen, case.authority)
            with case.h.readonly():
                bundle = source_feedback.build_source_feedback(
                    case.root / ("unwritten-" + name), reference=reference
                )
            self.assertLess(len(_json(bundle["feedback"])), MAX_FEEDBACK_BYTES)
            for row in bundle["feedback"]["records"]:
                note = json.loads(row["note"])
                self.assertEqual(note["answers"][0]["text"], literal)
                self.assertEqual(note["omitted_answer_positions"], 0)
            self.assertFalse((case.root / ("unwritten-" + name)).exists())
        self.assertEqual(
            (case.h.files(case.root), case.authority.summary(), case.engine.physical_sends), before
        )


if __name__ == "__main__":
    unittest.main()
