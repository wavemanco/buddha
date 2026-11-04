"""Versioned measured feedback retains checked failed-child history."""

import copy
import hashlib
import json
import shutil
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

import test_candidate_improvement as improvement_fixtures
import test_source_screen_outcome as outcome_fixtures

from buddha.gateway import RawHTTPTransport
from buddha.releases import Selection, _json, prepare_selection
from buddha.source_feedback import (
    SourceFeedbackError,
    build_source_feedback,
    inspect_source_feedback,
    write_source_feedback,
)


def sha(raw):
    return hashlib.sha256(raw).hexdigest()


class SourceFailureFeedbackTests(unittest.TestCase):
    def edge(self):
        """Real owners and passive receipts; existing mock channel, never host source exec."""
        from buddha.candidate_improvement import (
            prepare_candidate_improvement,
            run_candidate_improvement,
        )

        self.outcome = outcome_fixtures.SourceScreenOutcomeTests("runTest")
        h = self.h = self.outcome.fixture()
        self.addCleanup(self.outcome.doCleanups)
        record = copy.deepcopy(h.record)
        record["format"] = "buddha.source-screen.v2"
        self.parent_record = record
        parent = h.screen(record)
        parent_directory, authority = h.prepare(parent)
        self.assertEqual(h.run_screen(parent_directory)["disposition"], "screened")
        self.authority = authority
        self.reference = h.reference(parent_directory, authority)
        packet = write_source_feedback(h.root / "parent-feedback", reference=self.reference)
        generation = record["generation"]
        selection = Selection.from_bytes(_json(generation["selection"]))
        roots = {name: Path(path) for name, path in generation["roots"].items()}
        descriptor_record = {
            key: copy.deepcopy(generation[key])
            for key in ("config", "entrypoint", "executor", "profile", "runtime", "max_callbacks")
        }
        descriptor_record.update(
            format="buddha.candidate-improvement.v1",
            parent_agent_sha256=parent.candidate_id,
            feedback=packet["feedback"],
        )
        descriptor = h.root / "proposal.json"
        descriptor.write_bytes(_json(descriptor_record))
        proposal_directory = h.root / "proposal"
        prepare_candidate_improvement(
            proposal_directory,
            descriptor=descriptor,
            selection=selection,
            roots=roots,
            authorization=authority,
            review=h.engine.fixture.review,
            budget_microusd=10_000,
            max_calls=20,
            expected_runtime_sha256=h.engine.candidate.expected_runtime,
            expected_feedback_provenance_sha256=packet["provenance"]["sha256"],
        )
        self.returned = {
            "source": "# literal failed child 🐢\n" + "def generate(:\n" * 100,
            "hypothesis": "Try a changed procedure 🐢 " * 20,
        }
        worker = improvement_fixtures.ImprovementTests("runTest")
        worker.h = h.engine.candidate
        proxy = SimpleNamespace(
            run=lambda: run_candidate_improvement(
                proposal_directory, transport=RawHTTPTransport(allow_paid=True)
            )
        )
        self.proposal = worker.execute(proxy, self.returned, callbacks=1)
        self.assertEqual(self.proposal["disposition"], "materialized")
        child_record = copy.deepcopy(record)
        child_roots = roots | {"agent": Path(self.proposal["child"]["directory"])}
        child_record["generation"].update(
            selection=prepare_selection(
                h.engine.candidate.release,
                child_roots,
                capabilities=selection.to_record()["capabilities"],
            ).to_record(),
            roots={name: str(path) for name, path in child_roots.items()},
        )
        child_record["generation"]["executor"]["mounts"] = [
            ["/agent", str(child_roots["agent"])],
            ["/runner", str(child_roots["runner"])],
        ]
        child_record["lineage"] = self.proposal["child"]["lineage"]
        child = h.screen(child_record)
        child_directory, _ = h.prepare(child, h.root / "failed-screen", authority)
        with patch.object(
            h,
            "execute",
            side_effect=self.outcome.failed_worker(h, "1", h.execute),
        ):
            self.failed = h.run_screen(child_directory)
        self.assertEqual(self.failed["disposition"], "candidate_execution_failed")
        self.history = [
            {
                "parent": self.reference,
                "proposal": h.reference(proposal_directory, authority),
                "screen": h.reference(child_directory, authority),
            }
        ]
        return h.root / "failure-feedback"

    def another_edge(self, *, controls=None):
        from buddha.candidate_improvement import (
            prepare_candidate_improvement,
            run_candidate_improvement,
        )

        h = self.h
        generation = self.parent_record["generation"]
        selection = Selection.from_bytes(_json(generation["selection"]))
        roots = {name: Path(path) for name, path in generation["roots"].items()}
        descriptor = h.root / "proposal.json"
        provenance = h.root / "parent-feedback/provenance.json"
        directory = h.root / "second-proposal"
        prepare_candidate_improvement(
            directory,
            descriptor=descriptor,
            selection=selection,
            roots=roots,
            authorization=self.authority,
            review=h.engine.fixture.review,
            budget_microusd=10_000,
            max_calls=20,
            expected_runtime_sha256=h.engine.candidate.expected_runtime,
            expected_feedback_provenance_sha256=sha(provenance.read_bytes()),
        )
        returned = {
            "source": "# second literal failed source 🦉\n" + "def generate(:\n" * 120,
            "hypothesis": "A different proposed procedure.",
        }
        worker = improvement_fixtures.ImprovementTests("runTest")
        worker.h = h.engine.candidate
        proposal = worker.execute(
            SimpleNamespace(
                run=lambda: run_candidate_improvement(
                    directory, transport=RawHTTPTransport(allow_paid=True)
                )
            ),
            returned,
        )
        child_record = copy.deepcopy(self.parent_record)
        roots["agent"] = Path(proposal["child"]["directory"])
        child_record["generation"].update(
            roots={name: str(path) for name, path in roots.items()},
            selection=prepare_selection(
                h.engine.candidate.release,
                roots,
                capabilities=selection.to_record()["capabilities"],
            ).to_record(),
        )
        child_record["generation"]["executor"]["mounts"][0][1] = str(roots["agent"])
        child_record["lineage"] = proposal["child"]["lineage"]
        child = h.screen(child_record)
        child_directory, _ = h.prepare(
            child, h.root / "second-failed-screen", self.authority, **(controls or {})
        )
        with patch.object(h, "execute", side_effect=self.outcome.failed_worker(h, "1", h.execute)):
            self.assertEqual(
                h.run_screen(child_directory)["disposition"], "candidate_execution_failed"
            )
        return {
            "parent": self.reference,
            "proposal": h.reference(directory, self.authority),
            "screen": h.reference(child_directory, self.authority),
        }, returned

    def test_explicit_history_keyword_keeps_typed_prewrite_validation(self):
        # This API RED needs no source screen, owner, worker or provider fixture.
        with tempfile.TemporaryDirectory() as temporary:
            destination = Path(temporary) / "feedback"
            with self.assertRaises(SourceFeedbackError):
                build_source_feedback(destination, reference={}, failure_history=())
            self.assertFalse(destination.exists())

    def test_history_shape_and_eight_edge_ceiling_fail_before_any_destination(self):
        with tempfile.TemporaryDirectory() as temporary:
            destination = Path(temporary) / "feedback"
            for value in (None, True, {}, "not ordered", [None] * 9):
                with self.subTest(value=value), self.assertRaises(SourceFeedbackError):
                    write_source_feedback(destination, reference={}, failure_history=value)
                self.assertFalse(destination.exists())

    def test_original_failed_child_reaches_each_task_note_and_rebuilds_passively(self):
        """Inspect historical v2/v1 prefix extraction; public builders remain full-only."""
        from buddha.source_feedback import _build_failures

        destination = self.edge()
        h = self.h
        before = h.files(h.root), self.authority.summary(), h.engine.physical_sends
        with h.readonly():
            result = _build_failures(destination, self.reference, self.history, full_answers=False)
        self.assertEqual(
            (h.files(h.root), self.authority.summary(), h.engine.physical_sends), before
        )
        self.assertFalse(destination.exists())
        self.assertEqual(result["provenance"]["format"], "buddha.source-screen-feedback.v2")
        self.assertEqual(result["feedback"]["format"], "buddha.candidate-development-feedback.v1")
        self.assertEqual(result["provenance"]["failure_history"], self.history)
        self.assertEqual([row["task_id"] for row in result["feedback"]["records"]], ["1", 1])
        for row in result["feedback"]["records"]:
            note = json.loads(row["note"])
            self.assertLessEqual(len(row["note"].encode()), 4096)
            self.assertEqual(note["measurements"]["utility"], 7)
            failure = note["failures"][0]
            self.assertEqual(failure["parent_id"], result["provenance"]["candidate_id"])
            self.assertEqual(failure["child_id"], self.failed["candidate_id"])
            self.assertEqual(failure["task_id"], "1")
            self.assertEqual(failure["reason"], "agent_error")
            self.assertFalse(failure["ready_seen"])
            self.assertEqual(failure["completed_callbacks"], 0)
            self.assertEqual(failure["recorded_cost_microusd"], 0)
            self.assertEqual(
                failure["proposal_cost_microusd"],
                self.proposal["improvement"]["gateway_totals"]["spent_microusd"],
            )
            newest = note["newest_failure"]
            self.assertEqual(newest["source_sha256"], sha(self.returned["source"].encode()))
            self.assertTrue(self.returned["source"].startswith(newest["source"]))
            self.assertGreaterEqual(len(newest["source"].encode()), 128)
            self.assertEqual(
                newest["source_omitted_utf8_bytes"],
                len(self.returned["source"].encode()) - len(newest["source"].encode()),
            )
        # This is a synthetic historical packet, not a new public writer result.
        provenance_pin = sha(_json(result["provenance"]))
        destination.mkdir()
        for name in ("source", "split", "feedback", "provenance"):
            (destination / (name + ".json")).write_bytes(_json(result[name]))
        with h.readonly():
            inspected = inspect_source_feedback(
                destination, expected_provenance_sha256=provenance_pin
            )
        self.assertEqual(inspected, result)

    def test_two_true_edges_keep_order_and_every_older_omission_explicit(self):
        destination = self.edge()
        second, returned = self.another_edge()
        history = self.history + [second]
        with self.h.readonly():
            bundle = build_source_feedback(
                destination, reference=self.reference, failure_history=history
            )
            reversed_bundle = build_source_feedback(
                destination, reference=self.reference, failure_history=list(reversed(history))
            )
        self.assertNotEqual(bundle, reversed_bundle)
        self.assertEqual(bundle["provenance"]["failure_history"], history)
        for row in bundle["feedback"]["records"]:
            note = json.loads(row["note"])
            self.assertEqual([edge["ordinal"] for edge in note["failures"]], [0, 1])
            self.assertEqual([edge["task_id"] for edge in note["failures"]], ["1", "1"])
            self.assertEqual(note["older_failure_excerpts_omitted"], 1)
            self.assertEqual(
                note["newest_failure"]["source_sha256"], sha(returned["source"].encode())
            )
            self.assertEqual(note["newest_failure"]["ordinal"], 1)
        older, newest = bundle["provenance"]["failures"]
        for name in ("source", "hypothesis"):
            self.assertEqual(older[name]["excerpt_utf8_bytes"], 0)
            self.assertEqual(older[name]["omitted_utf8_bytes"], older[name]["utf8_bytes"])
            self.assertGreater(newest[name]["excerpt_utf8_bytes"], 0)
        reversed_note = json.loads(reversed_bundle["feedback"]["records"][0]["note"])
        self.assertEqual(
            reversed_note["newest_failure"]["source_sha256"], sha(self.returned["source"].encode())
        )

    def test_custody_partial_recovery_and_retirement_preserve_original_bytes(self):
        from buddha.source_feedback import _build_failures

        destination = self.edge()
        h = self.h
        with h.readonly():
            empty = build_source_feedback(destination, reference=self.reference)
            explicit_empty = build_source_feedback(
                destination, reference=self.reference, failure_history=[]
            )
            self.assertEqual(_json(empty), _json(explicit_empty))
            expected = build_source_feedback(
                destination, reference=self.reference, failure_history=self.history
            )
        bad = [
            [self.history[0], self.history[0]],
            [self.history[0] | {"parent": self.history[0]["screen"]}],
            [
                self.history[0]
                | {"proposal": self.history[0]["proposal"] | {"report_sha256": "0" * 64}}
            ],
            [
                self.history[0]
                | {
                    "screen": self.history[0]["screen"]
                    | {"authorization": str(h.engine.fixture.authority.path)}
                }
            ],
        ]
        for history in bad:
            with self.subTest(edge=history), h.readonly(), self.assertRaises(SourceFeedbackError):
                write_source_feedback(
                    destination, reference=self.reference, failure_history=history
                )
            self.assertFalse(destination.exists())
        source = Path(self.proposal["child"]["directory"]) / "candidate.py"
        original = source.read_bytes()
        try:
            source.write_bytes(original + b"# changed after completed proposal\n")
            with h.readonly(), self.assertRaises(SourceFeedbackError):
                write_source_feedback(
                    destination, reference=self.reference, failure_history=self.history
                )
        finally:
            source.write_bytes(original)
        self.assertFalse(destination.exists())
        destination.mkdir()
        (destination / "source.json").write_bytes(_json(expected["source"]))
        partial_before = h.files(destination)
        with h.readonly():
            self.assertEqual(
                _build_failures(destination, self.reference, self.history, existing=True), expected
            )
        self.assertEqual(h.files(destination), partial_before)
        for operation in (build_source_feedback, write_source_feedback):
            with self.assertRaises(SourceFeedbackError):
                operation(destination, reference=self.reference, failure_history=self.history)
        foreign = destination / "foreign.json"
        foreign.write_bytes(b"not a packet member")
        try:
            with self.assertRaises(SourceFeedbackError):
                _build_failures(destination, self.reference, self.history, existing=True)
        finally:
            foreign.unlink()
        for name in ("split", "feedback", "provenance"):
            (destination / (name + ".json")).write_bytes(_json(expected[name]))
        retired = h.root / "retired-original-inputs"
        retired.mkdir()
        for name in ("agent", "runner"):
            source_root = Path(self.parent_record["generation"]["roots"][name])
            shutil.move(str(source_root), retired / name)
        before = h.files(h.root), self.authority.summary(), h.engine.physical_sends
        with h.readonly():
            inspected = inspect_source_feedback(
                destination, expected_provenance_sha256=sha(_json(expected["provenance"]))
            )
        self.assertEqual(inspected, expected)
        self.assertEqual(
            (h.files(h.root), self.authority.summary(), h.engine.physical_sends), before
        )
        # A newly supplied provenance hash does not license changing frozen note bytes.
        provenance_path = destination / "provenance.json"
        changed = copy.deepcopy(expected["provenance"])
        changed["failures"][0]["task_id"] = 1  # typed development IDs must never collapse.
        provenance_path.write_bytes(_json(changed))
        with h.readonly(), self.assertRaises(SourceFeedbackError):
            inspect_source_feedback(
                destination, expected_provenance_sha256=sha(provenance_path.read_bytes())
            )

    def test_same_parent_source_cannot_substitute_another_measured_screen_occasion(self):
        destination = self.edge()
        h = self.h
        same_parent = h.screen(self.parent_record)
        second_parent, _ = h.prepare(
            same_parent, h.root / "another-parent-occasion", self.authority
        )
        second = h.run_screen(second_parent)
        self.assertEqual(second["disposition"], "screened")
        self.assertEqual(second["candidate_id"], self.proposal["parent_agent_sha256"])
        replacement = h.reference(second_parent, self.authority)
        self.assertNotEqual(replacement, self.reference)
        changed = [self.history[0] | {"parent": replacement}]
        before = h.files(h.root), self.authority.summary(), h.engine.physical_sends
        with h.readonly():
            original = build_source_feedback(
                destination, reference=self.reference, failure_history=self.history
            )
        self.assertEqual(original["provenance"]["failure_history"], self.history)
        self.assertFalse(destination.exists())
        with h.readonly(), self.assertRaises(SourceFeedbackError):
            write_source_feedback(destination, reference=self.reference, failure_history=changed)
        self.assertFalse(destination.exists())
        self.assertEqual(
            (h.files(h.root), self.authority.summary(), h.engine.physical_sends), before
        )


if __name__ == "__main__":
    unittest.main()
