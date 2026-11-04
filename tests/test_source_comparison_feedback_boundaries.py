"""Fixed improvers retain their identity across complete comparison packets.

One genuine measured parent and failed edge support both the empty-history and
retained-failure controls. Workers and HTTPS replies are supplied fixtures;
selected improver bytes and returned source never execute on the host.
"""

import copy
import json
import unittest
from pathlib import Path

import test_frozen_failure_feedback as frozen_fixtures

from buddha.answers import TaskSet
from buddha.releases import _json, prepare_selection
from buddha.source_feedback import (
    SourceFeedbackError,
    build_source_feedback,
    write_source_feedback,
)


class SourceComparisonFeedbackBoundaryTests(unittest.TestCase):
    def fixture(self):
        frozen = frozen_fixtures.FrozenFailureFeedbackTests("runTest")
        self.addCleanup(frozen.doCleanups)
        frozen.fixture()
        self.frozen, self.h, self.seam = frozen, frozen.h, frozen.seam
        self.actor_id = frozen.improver_id
        self.actor_source = frozen.improver_source
        f = self.seam.case("same-fixed-I-complete-child", self.actor_source)
        f.prepare()
        returned = f.child()
        proposal = self.seam.run_stage(returned, callbacks=1)
        self.assertEqual(proposal["disposition"], "materialized")
        self.assertEqual(proposal["improver_agent_sha256"], self.actor_id)
        proposal_directory = f.directory
        self.current_record = copy.deepcopy(frozen.parent_record)
        generation = self.current_record["generation"]
        roots = {name: Path(path) for name, path in generation["roots"].items()}
        roots["agent"] = Path(proposal["child"]["directory"])
        generation.update(
            selection=prepare_selection(
                self.h.engine.candidate.release,
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
        current = self.h.screen(self.current_record)
        self.current_id = current.candidate_id
        self.current_answers = ["COMPLETE CURRENT \\ \u96ea late ending  ", ""]
        self.h.programs[current.candidate_id].update(
            answers=self.current_answers, distinct=1, utility=4
        )
        directory, _ = self.h.prepare(
            current, self.h.root / "same-fixed-I-complete-screen", frozen.authority
        )
        report = self.h.run_screen(directory)
        self.assertEqual(report["disposition"], "screened")
        self.reference = self.h.reference(directory, frozen.authority)
        self.comparison = {
            "parent": frozen.reference,
            "proposal": self.h.reference(proposal_directory, frozen.authority),
            "screen": self.reference,
        }

    def next_case(self, name, actor, destination, written, bundle):
        """Retarget the existing detached worker fixture to the measured child."""
        seam = self.seam
        generation = self.current_record["generation"]
        seam.parent_roots = {name: Path(path) for name, path in generation["roots"].items()}
        seam.parent_selection = copy.deepcopy(generation["selection"])
        seam.parent_path = seam.parent_roots["agent"] / "candidate.py"
        seam.parent_raw = seam.parent_path.read_bytes()
        seam.parent_id = self.current_id
        f = seam.case(name, actor)
        f.packet, f.written = destination, written
        f.record["feedback"] = written["feedback"]
        f.descriptor.write_bytes(_json(f.record))
        tasks = {task.id: task for task in TaskSet.from_bytes(_json(bundle["source"])).tasks}
        seam.projected = [
            {"task": tasks[row["task_id"]].to_record(), "note": row["note"]}
            for row in bundle["feedback"]["records"]
        ]
        return f

    def test_frozen_comparison_preserves_both_bases_and_binds_next_protected_actor(self):
        self.fixture()
        frozen, h = self.frozen, self.h
        original_files = h.files(h.root)
        authority_name = frozen.authority.path.relative_to(h.root).as_posix()
        # Creating new original owners changes this shared accounting database.
        # Their predecessor evidence and all original owner ledgers stay fixed.
        for suffix in ("", "-wal", "-shm", "-journal"):
            original_files.pop(authority_name + suffix, None)
        parent_notes = [json.loads(row["note"]) for row in self.seam.projected]
        for name, history, base_version in (
            ("without-failures", [], 3),
            ("with-full-failure", frozen.history, 5),
        ):
            destination = h.root / ("fixed-comparison-" + name)
            before = frozen.snapshot()
            with self.subTest(history=name), frozen.f.feedback.passive():
                bundle = build_source_feedback(
                    destination,
                    reference=self.reference,
                    comparison=self.comparison,
                    failure_history=history,
                    improver_agent_sha256=self.actor_id,
                )
            self.assertFalse(destination.exists())
            self.assertEqual(frozen.snapshot(), before)
            provenance = bundle["provenance"]
            self.assertEqual(provenance["format"], "buddha.source-screen-feedback.v6")
            self.assertEqual(
                provenance["base_format"], "buddha.source-screen-feedback.v" + str(base_version)
            )
            self.assertEqual(provenance["candidate_id"], self.current_id)
            self.assertEqual(provenance["parent_candidate_id"], self.comparison_parent_id)
            self.assertEqual(provenance["improver_agent_sha256"], self.actor_id)
            self.assertEqual(provenance["comparison"], self.comparison)
            for row, parent_note in zip(bundle["feedback"]["records"], parent_notes, strict=True):
                note = json.loads(row["note"])
                self.assertEqual(note["parent_measurements"], parent_note)
                self.assertEqual(note["comparison"]["distinct_delta"], -1)
                self.assertEqual(note["comparison"]["utility_delta"], -3)
                current_note = note["measurements"]
                if history:
                    self.assertEqual(
                        current_note["newest_failure"]["source"], frozen.returned["source"]
                    )
                    self.assertEqual(
                        current_note["newest_failure"]["hypothesis"], frozen.returned["hypothesis"]
                    )
                    self.assertEqual(current_note["failures"][0]["improver_id"], self.actor_id)
                    self.assertEqual(current_note["newest_failure"]["source_omitted_utf8_bytes"], 0)
                    current_note = current_note["measurements"]
                self.assertEqual(
                    [answer["text"] for answer in current_note["answers"]], self.current_answers
                )
                self.assertEqual(current_note["omitted_answer_positions"], 0)
            with frozen.f.feedback.passive():
                written = write_source_feedback(
                    destination,
                    reference=self.reference,
                    comparison=self.comparison,
                    failure_history=history,
                    improver_agent_sha256=self.actor_id,
                )
            frozen.inspect_packet(destination, bundle)
            self.assertEqual(frozen.authority.summary(), before[1])
            f = self.next_case(
                "same-fixed-I-next-" + name, self.actor_source, destination, written, bundle
            )
            f.prepare(expected_feedback_provenance_sha256=written["provenance"]["sha256"])
            observed_before = len(self.seam.observed)
            next_proposal = f.child()
            next_proposal["source"] += "# A supplied subsequent child.\n"
            report = self.seam.run_stage(next_proposal)
            self.assertEqual(report["disposition"], "materialized", report)
            self.assertEqual(report["improver_agent_sha256"], self.actor_id)
            self.assertEqual(report["parent_agent_sha256"], self.current_id)
            self.assertEqual(len(self.seam.observed), observed_before + 1)
            self.assertEqual(self.seam.observed[-1][2], self.seam.projected)
            self.seam.passive(report)
            actual_files = h.files(h.root)
            self.assertEqual(
                {
                    path: (digest, actual_files.get(path))
                    for path, digest in original_files.items()
                    if actual_files.get(path) != digest
                },
                {},
            )

        other_source = self.seam.operator_source("genuinely-different-fixed-arm-I")
        f = self.next_case("other-fixed-I-next", other_source, destination, written, bundle)
        other_id = self.seam.operator_id
        self.assertNotEqual(other_id, self.actor_id)
        before = frozen.snapshot()
        connections = len(self.seam.connections)
        with self.assertRaises(f.Error):
            f.prepare(expected_feedback_provenance_sha256=written["provenance"]["sha256"])
        self.assertFalse(f.directory.exists())
        self.assertEqual(frozen.snapshot(), before)
        self.assertEqual(len(self.seam.connections), connections)
        refused = h.root / "wrong-fixed-comparison"
        for actor in (None, other_id):
            with (
                self.subTest(actor=actor),
                frozen.f.feedback.passive(),
                self.assertRaises(SourceFeedbackError),
            ):
                write_source_feedback(
                    refused,
                    reference=self.reference,
                    comparison=self.comparison,
                    improver_agent_sha256=actor,
                )
            self.assertFalse(refused.exists())
        self.assertEqual(frozen.snapshot(), before)

    @property
    def comparison_parent_id(self):
        return self.frozen.proposal["parent_agent_sha256"]


if __name__ == "__main__":
    unittest.main()
