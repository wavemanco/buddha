"""Opt-in parent comparisons use real saved source/proposal custody.

Reuse one small two-task lineage per meaningful method. Executor/HTTP replies
are supplied; neither selected source nor returned source executes on the host.
"""

import copy
import hashlib
import json
import os
import tempfile
import unittest
from contextlib import contextmanager
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

import test_candidate_improvement as improvement_fixtures
import test_source_screen_outcome as outcome_fixtures

from buddha import candidate_improvement, executor, source_feedback
from buddha.gateway import RawHTTPTransport
from buddha.releases import MAX_FEEDBACK_BYTES, Selection, _json, prepare_selection
from buddha.source_feedback import (
    SourceFeedbackError,
    SourceFeedbackTooLarge,
    build_source_feedback,
    inspect_source_feedback,
    write_source_feedback,
)

LITERAL = "  BEGIN literal\n" + "snow 雪 alpha α \\ \x01  " * 150 + "\nLATE ENDING  "
CHILD = (
    "raise RuntimeError('comparison fixture source must never run on host')\n"
    "def generate(task, config, complete): return []\n"
    "def propose_improvement(parent, feedback, config, complete): return {}\n"
)


def sha(raw):
    return hashlib.sha256(raw).hexdigest()


class SourceComparisonFeedbackTests(unittest.TestCase):
    def fixture(self, *, literal=LITERAL, invalid_current=False):
        outcome = outcome_fixtures.SourceScreenOutcomeTests("runTest")
        self.h = h = outcome.fixture()
        self.addCleanup(outcome.doCleanups)
        h.record["format"] = "buddha.source-screen.v2"
        self.parent_record = copy.deepcopy(h.record)
        self.parent_answers = {"1": [literal + " P", ""], 1: [literal + " P", " \n"]}
        self.current_answers = {
            "1": [literal + " C", literal + " C"],
            1: [literal + " C", " \n"],
        }
        parent = h.screen(self.parent_record)
        self.parent_id = parent.candidate_id
        original_execute = h.execute

        def execute(spec, *, initial, handle, **kwargs):
            if spec.role == "agent":
                is_parent = initial["agent_sha256"] == self.parent_id
                task_id = initial["task"]["id"]
                changed = not is_parent and type(task_id) is str
                h.programs[initial["agent_sha256"]].update(
                    answers=(self.parent_answers if is_parent else self.current_answers)[task_id],
                    callbacks=0 if changed else 1,
                    distinct=1 if changed else 2,
                    utility=4 if changed else 7,
                )
                h.unusable_task = "1" if invalid_current and not is_parent else None
            return original_execute(spec, initial=initial, handle=handle, **kwargs)

        h.execute = execute
        parent_directory, self.authority = h.prepare(parent)
        self.assertEqual(h.run_screen(parent_directory)["disposition"], "screened")
        self.parent_ref = h.reference(parent_directory, self.authority)
        parent_packet = h.root / "parent-feedback"
        parent_written = write_source_feedback(parent_packet, reference=self.parent_ref)
        self.hypothesis = (
            "  Full hypothesis 雪 with unchanged spaces.\n" * 30 + "FINAL HYPOTHESIS  "
        )
        proposal, proposal_directory = self.propose(
            "original-proposal",
            self.parent_record,
            parent_written,
            {"source": CHILD, "hypothesis": self.hypothesis},
        )
        self.proposal = proposal
        self.current_record = copy.deepcopy(self.parent_record)
        generation = self.current_record["generation"]
        roots = {name: Path(path) for name, path in generation["roots"].items()}
        roots["agent"] = Path(proposal["child"]["directory"])
        generation.update(
            selection=prepare_selection(
                h.engine.candidate.release,
                roots,
                capabilities=generation["selection"]["capabilities"],
            ).to_record(),
            roots={name: str(path) for name, path in roots.items()},
        )
        generation["executor"]["mounts"] = [
            ["/agent", str(roots["agent"])],
            ["/runner", str(roots["runner"])],
        ]
        self.current_record["lineage"] = proposal["child"]["lineage"]
        current = h.screen(self.current_record)
        self.current_id = current.candidate_id
        current_directory, _ = h.prepare(current, h.root / "current-screen", self.authority)
        self.current_report = h.run_screen(current_directory)
        self.assertEqual(self.current_report["disposition"], "screened")
        self.reference = h.reference(current_directory, self.authority)
        self.comparison = {
            "parent": self.parent_ref,
            "proposal": h.reference(proposal_directory, self.authority),
            "screen": self.reference,
        }
        self.destination = h.root / "comparison-feedback"
        return self

    def propose(self, name, record, written, returned, observed=None):
        h = self.h
        generation = record["generation"]
        selection = Selection.from_bytes(_json(generation["selection"]))
        descriptor = h.root / (name + ".json")
        descriptor.write_bytes(
            _json(
                {
                    **{
                        key: generation[key]
                        for key in (
                            "config",
                            "entrypoint",
                            "executor",
                            "profile",
                            "runtime",
                            "max_callbacks",
                        )
                    },
                    "format": "buddha.candidate-improvement.v1",
                    "parent_agent_sha256": selection.agent_sha256,
                    "feedback": written["feedback"],
                }
            )
        )
        directory = h.root / name
        candidate_improvement.prepare_candidate_improvement(
            directory,
            descriptor=descriptor,
            selection=selection,
            roots={key: Path(path) for key, path in generation["roots"].items()},
            authorization=self.authority,
            review=h.engine.fixture.review,
            budget_microusd=10_000,
            max_calls=20,
            expected_runtime_sha256=h.engine.candidate.expected_runtime,
            expected_feedback_provenance_sha256=written["provenance"]["sha256"],
        )

        def run():
            # The existing helper installs the supplied executor before invoking run.
            supplied = executor.run_container

            def observe(spec, *, initial, **kwargs):
                if observed is not None:
                    observed.append(copy.deepcopy(initial))
                self.assertEqual(set(dict(spec.mounts)), {"/agent", "/runner"})
                self.assertEqual(dict(spec.mounts)["/agent"], Path(generation["roots"]["agent"]))
                return supplied(spec, initial=initial, **kwargs)

            with patch.object(executor, "run_container", side_effect=observe):
                return candidate_improvement.run_candidate_improvement(
                    directory, transport=RawHTTPTransport(allow_paid=True)
                )

        worker = improvement_fixtures.ImprovementTests("runTest")
        worker.h = h.engine.candidate
        result = worker.execute(SimpleNamespace(run=run), returned, callbacks=1)
        self.assertEqual(result["disposition"], "materialized")
        return result, directory

    def snapshot(self):
        return self.h.files(self.h.root), self.authority.summary(), self.h.engine.physical_sends

    def build(self, *, reference=None, comparison=None):
        with self.h.readonly():
            return build_source_feedback(
                self.destination,
                reference=self.reference if reference is None else reference,
                comparison=self.comparison if comparison is None else comparison,
            )

    @staticmethod
    def notes(bundle):
        return [json.loads(row["note"]) for row in bundle["feedback"]["records"]]

    def test_comparison_keyword_rejects_invalid_shape_before_any_fixture(self):
        with tempfile.TemporaryDirectory() as temporary:
            destination = Path(temporary).resolve() / "comparison-feedback"
            with self.assertRaises(SourceFeedbackError):
                build_source_feedback(destination, reference={}, comparison={})
            self.assertFalse(destination.exists())

    def test_complete_regression_reaches_next_protected_worker_and_replays_without_new_sends(self):
        self.fixture()
        h = self.h
        before = self.snapshot()
        plain_current = build_source_feedback(self.destination, reference=self.reference)
        plain_parent = build_source_feedback(h.root / "unused-parent", reference=self.parent_ref)
        result = self.build()
        self.assertEqual(self.snapshot(), before)
        self.assertFalse(self.destination.exists())
        self.assertEqual(result["provenance"]["format"], "buddha.source-screen-feedback.v6")
        self.assertEqual(result["provenance"]["comparison"], self.comparison)
        self.assertEqual(result["feedback"]["format"], "buddha.candidate-development-feedback.v2")
        self.assertTrue(self.current_report["admission"]["eligible"])
        self.assertEqual([row["task_id"] for row in result["feedback"]["records"]], ["1", 1])
        for task_id, note, current, parent, expected in zip(
            ("1", 1),
            self.notes(result),
            self.notes(plain_current),
            self.notes(plain_parent),
            ((-1, -3, -11), (0, 0, 0)),
            strict=True,
        ):
            self.assertEqual(note["kind"], "saved_native_measurements_and_parent_comparison")
            self.assertEqual(note["measurements"], current)
            self.assertEqual(note["parent_measurements"], parent)
            self.assertEqual(
                [answer["text"] for answer in current["answers"]], self.current_answers[task_id]
            )
            self.assertEqual(
                [answer["text"] for answer in parent["answers"]], self.parent_answers[task_id]
            )
            self.assertEqual(current["omitted_answer_positions"], 0)
            self.assertEqual(parent["omitted_answer_positions"], 0)
            self.assertEqual(
                note["comparison"],
                {
                    "parent_id": self.parent_id,
                    "current_id": self.current_id,
                    "delta_direction": "current_minus_parent",
                    "distinct_delta": expected[0],
                    "utility_delta": expected[1],
                    "recorded_cost_delta_microusd": expected[2],
                    "unavailable": {"distinct": None, "utility": None},
                    "cost_scope": "original_task_generation_and_native_owners",
                    "proposal_hypothesis": self.hypothesis,
                    "proposal_cost_microusd": 11,
                    "proposal_cost_scope": "original_proposal_owner_excluded_from_task_cost_delta",
                },
            )
        written = write_source_feedback(
            self.destination, reference=self.reference, comparison=self.comparison
        )
        self.assertEqual(self.authority.summary(), before[1])
        with h.readonly():
            self.assertEqual(
                inspect_source_feedback(
                    self.destination,
                    expected_provenance_sha256=written["provenance"]["sha256"],
                ),
                result,
            )
        observed = []
        report, stage = self.propose(
            "next-protected-proposal",
            self.current_record,
            written,
            {"source": CHILD + "# next child\n", "hypothesis": "A supplied next proposal."},
            observed,
        )
        self.assertEqual(len(observed), 1)
        initial = observed[0]
        self.assertEqual(initial["format"], "buddha.candidate-improvement-worker.v2")
        self.assertEqual(initial["agent_sha256"], self.current_id)
        for row, saved in zip(initial["feedback"], result["feedback"]["records"], strict=True):
            self.assertEqual(row["task"]["id"], saved["task_id"])
            self.assertEqual(row["note"], saved["note"])
        for private in (
            b"VALIDATION-ONLY-SENTINEL",
            b"FINAL-ONLY-SENTINEL",
            b"dataset_base64",
            b"operations.sqlite3",
        ):
            self.assertNotIn(private, _json(initial))
        owner = json.loads((stage / "owners/0/manifest.json").read_bytes())
        bindings = {row["path"]: row["sha256"] for row in owner["invocation"]["inputs"]}
        for name in ("source", "split", "feedback", "provenance"):
            path = self.destination / (name + ".json")
            self.assertEqual(bindings[str(path)], sha(path.read_bytes()))
        before = self.snapshot()
        with (
            h.readonly(),
            patch.dict(os.environ, {}, clear=True),
            patch("socket.socket", side_effect=AssertionError("passive network")),
        ):
            self.assertEqual(
                candidate_improvement.inspect_candidate_improvement(
                    stage,
                    authorization=self.authority.path,
                    expected_report_sha256=sha((stage / "report.json").read_bytes()),
                ),
                report,
            )
            # Old v3 packets retain their original reconstruction and bytes.
            legacy_packet = h.root / "parent-feedback"
            old_pin = sha((legacy_packet / "provenance.json").read_bytes())
            old = inspect_source_feedback(legacy_packet, expected_provenance_sha256=old_pin)
            self.assertEqual(old["provenance"]["format"], "buddha.source-screen-feedback.v3")
        # The completed controller reads original authority terms before its
        # passive result path; its existing replay contract forbids new execution.
        with (
            patch.dict(os.environ, {}, clear=True),
            patch(
                "buddha.candidate_run.CandidateSession", side_effect=AssertionError("new session")
            ),
            patch("buddha.executor.run_container", side_effect=AssertionError("new worker")),
            patch("http.client.HTTPSConnection", side_effect=AssertionError("new HTTPS")),
        ):
            self.assertEqual(
                candidate_improvement.run_candidate_improvement(
                    stage, transport=RawHTTPTransport(allow_paid=False)
                ),
                report,
            )
        self.assertEqual(self.snapshot(), before)

    def test_wrong_parent_occasion_and_changed_common_conditions_refuse_without_writes(self):
        self.fixture()
        h = self.h
        same_parent = h.screen(self.parent_record)
        parent_directory, _ = h.prepare(
            same_parent, h.root / "another-parent-occasion", self.authority
        )
        self.assertEqual(h.run_screen(parent_directory)["disposition"], "screened")
        replacement = h.reference(parent_directory, self.authority)
        self.assertEqual(same_parent.candidate_id, self.parent_id)
        self.assertNotEqual(replacement, self.parent_ref)
        control = h.root / "separate-screen-control.txt"
        control.write_bytes(b"a genuinely different common external control")
        changed = h.screen(self.current_record)
        changed_directory, _ = h.prepare(
            changed,
            h.root / "changed-common-control-screen",
            self.authority,
            input_bindings={control: sha(control.read_bytes())},
        )
        changed_report = h.run_screen(changed_directory)
        self.assertEqual(changed_report["disposition"], "screened")
        self.assertEqual(changed_report["comparison_key"], self.current_report["comparison_key"])
        self.assertNotEqual(
            changed_report["controls_sha256"], self.current_report["controls_sha256"]
        )
        changed_ref = h.reference(changed_directory, self.authority)
        before = self.snapshot()
        cases = [
            (self.reference, self.comparison | {"parent": replacement}),
            (changed_ref, self.comparison | {"screen": changed_ref}),
            (self.reference, self.comparison | {"screen": changed_ref}),
            (
                self.reference,
                self.comparison
                | {"proposal": self.comparison["proposal"] | {"report_sha256": "0" * 64}},
            ),
        ]
        for reference, comparison in cases:
            with self.subTest(reference=reference, comparison=comparison), h.readonly():
                with self.assertRaises(SourceFeedbackError):
                    write_source_feedback(
                        self.destination, reference=reference, comparison=comparison
                    )
            self.assertFalse(self.destination.exists())
        self.assertEqual(self.snapshot(), before)

    def test_rehashed_comparison_scalar_cannot_replace_original_derivation(self):
        self.fixture()
        written = write_source_feedback(
            self.destination, reference=self.reference, comparison=self.comparison
        )
        before = self.snapshot()
        packet_path = self.destination / "feedback.json"
        provenance_path = self.destination / "provenance.json"
        original_packet, original_provenance = (
            packet_path.read_bytes(),
            provenance_path.read_bytes(),
        )
        packet, provenance = json.loads(original_packet), json.loads(original_provenance)
        note = json.loads(packet["records"][0]["note"])
        note["comparison"]["utility_delta"] = 99
        packet["records"][0]["note"] = _json(note).decode()
        provenance["feedback_sha256"] = sha(_json(packet))
        provenance["tasks"][0]["note_sha256"] = sha(packet["records"][0]["note"].encode())
        provenance["tasks"][0]["note_utf8_bytes"] = len(packet["records"][0]["note"].encode())
        try:
            packet_path.write_bytes(_json(packet))
            provenance_path.write_bytes(_json(provenance))
            new_pin = sha(provenance_path.read_bytes())
            self.assertNotEqual(new_pin, written["provenance"]["sha256"])
            with self.h.readonly(), self.assertRaises(SourceFeedbackError):
                inspect_source_feedback(self.destination, expected_provenance_sha256=new_pin)
        finally:
            packet_path.write_bytes(original_packet)
            provenance_path.write_bytes(original_provenance)
        self.assertEqual(self.snapshot(), before)

    def test_complete_comparison_refuses_capacity_without_shortening_either_answer_set(self):
        self.fixture(literal="x" * 220_000)
        current = build_source_feedback(self.destination, reference=self.reference)
        parent = build_source_feedback(self.h.root / "unused-parent", reference=self.parent_ref)
        self.assertLess(len(_json(current["feedback"])), MAX_FEEDBACK_BYTES)
        self.assertLess(len(_json(parent["feedback"])), MAX_FEEDBACK_BYTES)
        literal_bytes = sum(
            len(answer["text"].encode())
            for bundle in (current, parent)
            for note in self.notes(bundle)
            for answer in note["answers"]
        )
        self.assertGreater(literal_bytes, MAX_FEEDBACK_BYTES)
        before = self.snapshot()
        with self.h.readonly(), self.assertRaises(SourceFeedbackTooLarge):
            write_source_feedback(
                self.destination, reference=self.reference, comparison=self.comparison
            )
        self.assertFalse(self.destination.exists())
        self.assertEqual(self.snapshot(), before)

    def test_invalid_current_metric_has_no_fabricated_zero_delta(self):
        self.fixture(invalid_current=True)
        bundle = self.build()
        changed, unchanged = self.notes(bundle)
        self.assertIsNone(changed["measurements"]["utility"])
        self.assertIsNone(changed["comparison"]["utility_delta"])
        self.assertIsInstance(changed["comparison"]["unavailable"]["utility"], str)
        self.assertTrue(changed["comparison"]["unavailable"]["utility"])
        self.assertEqual(changed["comparison"]["distinct_delta"], -1)
        self.assertIsNone(changed["comparison"]["unavailable"]["distinct"])
        self.assertEqual(changed["comparison"]["recorded_cost_delta_microusd"], -11)
        self.assertEqual(unchanged["comparison"]["utility_delta"], 0)
        self.assertNotIn(b"NaN", _json(bundle))

    def test_recursive_and_exhausted_comparison_observations_refuse_then_reset(self):
        self.fixture()
        before = self.snapshot()
        # A recursive consumer callback injects a repeated observation, without
        # fabricating another original lineage or executing any selected source.
        with (
            patch.object(
                candidate_improvement,
                "inspect_candidate_improvement",
                side_effect=lambda *args, **kwargs: self.build(),
            ),
            self.assertRaisesRegex(SourceFeedbackError, "comparison ancestry"),
        ):
            self.build()
        self.assertIsNone(source_feedback._COMPARISON_OBSERVATION.get())
        self.assertEqual(self.snapshot(), before)

        exhausted = source_feedback._ComparisonObservation(remaining_edges=0)
        with (
            patch.object(source_feedback, "_ComparisonObservation", return_value=exhausted),
            self.assertRaisesRegex(SourceFeedbackError, "64 edge checks"),
        ):
            self.build()
        self.assertEqual(exhausted.active, set())
        self.assertIsNone(source_feedback._COMPARISON_OBSERVATION.get())
        self.assertEqual(self.snapshot(), before)
        self.assertFalse(self.destination.exists())
        # Both error exits must release the context; a new genuine public read
        # gets its full independent budget and verifies the original edge.
        result = self.build()
        self.assertEqual(result["provenance"]["comparison"], self.comparison)
        self.assertIsNone(source_feedback._COMPARISON_OBSERVATION.get())
        self.assertEqual(self.snapshot(), before)

    def test_saved_comparison_inspects_after_original_producer_roots_retire(self):
        self.fixture()
        expected = self.build()
        written = write_source_feedback(
            self.destination, reference=self.reference, comparison=self.comparison
        )
        root = self.h.root.resolve()
        # Retire only synthetic producer trees, never checkout program files or
        # the retained proposal/answer evidence needed for passive replay.
        for role in ("agent", "runner"):
            source = Path(self.parent_record["generation"]["roots"][role]).resolve(strict=True)
            retired = root / ("retired-original-" + role)
            self.assertTrue(source.is_relative_to(root) and source != root)
            self.assertTrue(retired.is_relative_to(root) and retired != root)
            self.assertFalse(retired.exists())
            source.rename(retired)
        before = self.snapshot()
        with (
            self.h.readonly(),
            patch.dict(os.environ, {}, clear=True),
            patch("socket.socket", side_effect=AssertionError("retired replay network")),
        ):
            inspected = inspect_source_feedback(
                self.destination,
                expected_provenance_sha256=written["provenance"]["sha256"],
            )
        self.assertEqual(inspected, expected)
        self.assertEqual(self.snapshot(), before)

    def test_late_original_proposal_seal_or_ledger_drift_refuses_before_publication(self):
        self.fixture()
        proposal_directory = Path(self.comparison["proposal"]["directory"])
        targets = (
            proposal_directory / "completed/0.json",
            proposal_directory / "owners/0/operations.sqlite3",
        )
        original_work = source_feedback.trial_fence.work
        before = self.snapshot()
        for target in targets:
            original = target.read_bytes()
            reached = []

            @contextmanager
            def late_drift(
                *args, directory, target=target, original=original, reached=reached, **kwargs
            ):
                with original_work(*args, directory=directory, **kwargs) as controls:
                    if directory == self.destination:
                        # This real writer boundary follows completed derivation
                        # and precedes directory creation/publication.
                        reached.append(target)
                        target.write_bytes(original + b" ")
                    yield controls

            try:
                with (
                    self.subTest(original_proposal_file=target.name),
                    self.h.readonly(),
                    patch.object(source_feedback.trial_fence, "work", side_effect=late_drift),
                    self.assertRaises(SourceFeedbackError),
                ):
                    write_source_feedback(
                        self.destination, reference=self.reference, comparison=self.comparison
                    )
                self.assertEqual(reached, [target])
                self.assertFalse(self.destination.exists())
                self.assertIsNone(source_feedback._COMPARISON_OBSERVATION.get())
            finally:
                target.write_bytes(original)
            self.assertEqual(self.snapshot(), before)


if __name__ == "__main__":
    unittest.main()
