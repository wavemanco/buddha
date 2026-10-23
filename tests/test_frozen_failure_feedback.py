"""Full failure notes preserve frozen-improver and measured task-parent roles.

Compose one existing measured fixture per meaningful method. The same parent
screen is reused for scalar refusals and old packet controls. Workers/replies
are supplied fixtures; no candidate source executes on the host.
"""

import copy
import hashlib
import json
import unittest
from pathlib import Path
from unittest.mock import patch


def sha(raw):
    return hashlib.sha256(raw).hexdigest()


class FrozenFailureFeedbackTests(unittest.TestCase):
    def fixture(self):
        import test_frozen_improver
        import test_source_feedback
        import test_source_screen_outcome

        from buddha.source_feedback import (
            SourceFeedbackError,
            build_source_feedback,
            write_source_feedback,
        )

        self.Error = SourceFeedbackError
        self.build_api, self.write_api = build_source_feedback, write_source_feedback
        self.outcome = test_source_screen_outcome.SourceScreenOutcomeTests("runTest")
        self.addCleanup(self.outcome.doCleanups)
        self.h = h = self.outcome.fixture()
        h.record["format"] = "buddha.source-screen.v2"
        self.parent_record = copy.deepcopy(h.record)

        def reuse_measured_fixture(feedback):
            feedback.Error = SourceFeedbackError
            feedback.build_api, feedback.write_api = build_source_feedback, write_source_feedback
            feedback.h = h

        self.seam = test_frozen_improver.FrozenImproverTests("runTest")
        self.addCleanup(self.seam.doCleanups)
        # The seam's long-answer preparation uses this already-created v2 screen
        # fixture, including SourceScreenOutcomeTests' v2 generation reader.
        with patch.object(
            test_source_feedback.SourceFeedbackTests, "setUp", reuse_measured_fixture
        ):
            self.f = self.seam.fixture()
        self.original_packet = self.f.packet
        self.original_written = copy.deepcopy(self.f.written)
        original = json.loads((self.original_packet / "provenance.json").read_bytes())
        self.reference = original["reference"]
        self.authority = h.authorities[0]
        self.assertEqual(self.reference["authorization"], str(self.authority.path))
        # The existing seam normally uses its separate generic Gateway fixture
        # grant. Failure edges must share their measured screen's actual grant.
        self.f.f.authority = self.authority
        self.improver_source = self.seam.operator_source("fixed-arm-I")
        f = self.seam.case("detached-first", self.improver_source)
        self.improver_id = self.seam.operator_id
        f.prepare()
        self.returned = {
            "source": "# full failed source 雪\n" + "def generate(:\n" * 100 + "# LAST_SOURCE\n",
            "hypothesis": "A supplied failed procedure 雪 " * 30 + "LAST_HYPOTHESIS",
        }
        self.proposal = self.seam.run_stage(self.returned, callbacks=1)
        self.assertEqual(self.proposal["disposition"], "materialized")
        self.seam.assert_roles(self.proposal)
        self.seam.passive(self.proposal)
        self.first_directory = f.directory
        self.history = [self.failed_edge(self.proposal, self.first_directory, "detached")]
        return h.root / "frozen-failure-feedback"

    def failed_edge(self, proposal, directory, name):
        from buddha.releases import _json, prepare_selection

        h = self.h
        record = copy.deepcopy(self.parent_record)
        generation = record["generation"]
        roots = {key: Path(value) for key, value in generation["roots"].items()}
        roots["agent"] = Path(proposal["child"]["directory"])
        generation["selection"] = prepare_selection(
            h.engine.candidate.release,
            roots,
            capabilities=generation["selection"]["capabilities"],
        ).to_record()
        generation["roots"] = {key: str(value) for key, value in roots.items()}
        generation["entrypoint"] = "candidate.py"
        generation["executor"]["mounts"] = [
            ["/agent", str(roots["agent"])],
            ["/runner", str(roots["runner"])],
        ]
        record["lineage"] = proposal["child"]["lineage"]
        screen = h.screen(record)
        failed_directory, _ = h.prepare(screen, h.root / (name + "-failed-screen"), self.authority)
        original_execute = h.execute
        with patch.object(
            h,
            "execute",
            side_effect=self.outcome.failed_worker(h, "1", original_execute),
        ):
            failed = h.run_screen(failed_directory)
        self.assertEqual(failed["disposition"], "candidate_execution_failed")
        self.assertEqual(failed["parent_id"], self.seam.parent_id)
        self.assertEqual(failed["candidate_id"], proposal["child"]["agent_sha256"])
        self.assertEqual(_json(failed["failure"]["task_id"]), b'"1"')
        self.assertEqual(failed["failure"]["terminal"]["done_reason"], "agent_error")
        self.failed = failed
        return {
            "parent": self.reference,
            "proposal": h.reference(directory, self.authority),
            "screen": h.reference(failed_directory, self.authority),
        }

    def snapshot(self):
        return (
            self.h.files(self.h.root),
            self.authority.summary(),
            self.h.engine.physical_sends,
        )

    def inspect_packet(self, directory, expected):
        from buddha.releases import _json
        from buddha.source_feedback import inspect_source_feedback

        before = self.snapshot()
        with self.f.feedback.passive():
            actual = inspect_source_feedback(
                directory,
                expected_provenance_sha256=sha((directory / "provenance.json").read_bytes()),
            )
        self.assertEqual(actual, expected)
        for name, record in expected.items():
            self.assertEqual((directory / (name + ".json")).read_bytes(), _json(record))
        self.assertEqual(self.snapshot(), before)

    def legacy_controls(self):
        """Reuse measured S; one inherited proposal/failure adds no parent screen."""
        from buddha.releases import Selection, _json
        from buddha.source_feedback import _build, _build_failures

        f = self.f
        f.packet, f.written = self.original_packet, self.original_written
        f.roots = dict(self.seam.parent_roots)
        f.selection = Selection.from_bytes(_json(self.seam.parent_selection))
        f.record = copy.deepcopy(self.seam.base_recipe)
        f.descriptor = f.root / "legacy-inherited-descriptor.json"
        f.directory = f.root / "legacy-inherited-stage"
        f.descriptor.write_bytes(_json(f.record))
        f.prepare()
        legacy_proposal = f.run_stage(self.returned, callbacks=1)
        self.assertEqual(legacy_proposal["format"], "buddha.candidate-improvement-stage-report.v1")
        legacy_history = [self.failed_edge(legacy_proposal, f.directory, "legacy")]
        for version in (1, 2, 4):
            destination = f.root / ("legacy-packet-v" + str(version))
            before = self.snapshot()
            with self.f.feedback.passive():
                if version == 1:
                    bundle = _build(destination, self.reference, full_answers=False)
                elif version == 2:
                    bundle = _build_failures(
                        destination, self.reference, legacy_history, full_answers=False
                    )
                else:
                    bundle = self.build_api(
                        destination, reference=self.reference, failure_history=legacy_history
                    )
                    explicit_default = self.build_api(
                        destination,
                        reference=self.reference,
                        failure_history=legacy_history,
                        improver_agent_sha256=None,
                    )
                    self.assertEqual(_json(bundle), _json(explicit_default))
            self.assertEqual(self.snapshot(), before)
            self.assertEqual(
                bundle["provenance"]["format"], "buddha.source-screen-feedback.v" + str(version)
            )
            self.assertEqual(
                bundle["feedback"]["format"],
                "buddha.candidate-development-feedback.v2"
                if version == 4
                else "buddha.candidate-development-feedback.v1",
            )
            self.assertNotIn("improver_agent_sha256", bundle["provenance"])
            for failure in bundle["provenance"].get("failures", []):
                self.assertNotIn("improver_id", failure)
            destination.mkdir()
            for name, record in bundle.items():
                (destination / (name + ".json")).write_bytes(_json(record))
            self.inspect_packet(destination, bundle)
        original = {
            name: json.loads((self.original_packet / (name + ".json")).read_bytes())
            for name in ("source", "split", "feedback", "provenance")
        }
        self.assertEqual(original["provenance"]["format"], "buddha.source-screen-feedback.v3")
        self.inspect_packet(self.original_packet, original)
        self.assertTrue(
            all(path.read_bytes() == raw for path, raw in self.seam.common_files.items())
        )

    def test_same_fixed_improver_gets_checked_full_failure_feedback_and_old_packets_stay_exact(
        self,
    ):
        from buddha.answers import TaskSet
        from buddha.releases import _json
        from buddha.source_feedback import _build, _build_failures

        destination = self.fixture()
        before = self.snapshot()
        # Omitting the new selector must retain the inherited whole-selection
        # guard, rather than silently widening historical v4 to detached I.
        with self.f.feedback.passive(), self.assertRaises(self.Error):
            self.build_api(destination, reference=self.reference, failure_history=self.history)
        self.assertFalse(destination.exists())
        self.assertEqual(self.snapshot(), before)
        with self.f.feedback.passive():
            measured = _build(destination, self.reference)
            bundle = self.build_api(
                destination,
                reference=self.reference,
                failure_history=self.history,
                improver_agent_sha256=self.improver_id,
            )
        self.assertFalse(destination.exists())
        self.assertEqual(self.snapshot(), before)
        provenance = bundle["provenance"]
        self.assertEqual(provenance["format"], "buddha.source-screen-feedback.v5")
        self.assertEqual(
            provenance["policy"]["version"], "complete-outputs-and-frozen-improver-failures-v5"
        )
        self.assertEqual(provenance["improver_agent_sha256"], self.improver_id)
        self.assertEqual(provenance["candidate_id"], self.seam.parent_id)
        self.assertEqual(provenance["measured_base_sha256"], sha(_json(measured["provenance"])))
        self.assertEqual(provenance["failure_history"], self.history)
        self.assertEqual(bundle["feedback"]["format"], "buddha.candidate-development-feedback.v2")
        self.assertEqual(provenance["failures"][0]["improver_id"], self.improver_id)
        self.assertEqual(provenance["failures"][0]["parent_id"], self.seam.parent_id)
        self.assertEqual(
            provenance["failures"][0]["proposal_cost_microusd"],
            self.proposal["improvement"]["gateway_totals"]["spent_microusd"],
        )
        self.assertEqual(
            provenance["failures"][0]["recorded_cost_microusd"],
            self.failed["failure"]["terminal"]["recorded_cost_microusd"],
        )
        for original, row in zip(self.seam.projected, bundle["feedback"]["records"], strict=True):
            note = json.loads(row["note"])
            self.assertEqual(note["measurements"], json.loads(original["note"]))
            self.assertEqual(note["failures"][0]["improver_id"], self.improver_id)
            self.assertEqual(note["failures"][0]["task_id"], "1")
            self.assertEqual(note["newest_failure"]["source"], self.returned["source"])
            self.assertEqual(note["newest_failure"]["hypothesis"], self.returned["hypothesis"])
            self.assertEqual(note["newest_failure"]["source_omitted_utf8_bytes"], 0)
            self.assertEqual(note["newest_failure"]["hypothesis_omitted_utf8_bytes"], 0)
        for bad in (True, "not-a-digest", "0" * 64):
            with (
                self.subTest(improver=bad),
                self.f.feedback.passive(),
                self.assertRaises(self.Error),
            ):
                self.build_api(
                    destination,
                    reference=self.reference,
                    failure_history=self.history,
                    improver_agent_sha256=bad,
                )
            self.assertFalse(destination.exists())
        with (
            self.f.feedback.passive(),
            patch(
                "buddha.source_feedback._build",
                side_effect=AssertionError("empty v5 must stop before base derivation"),
            ),
            self.assertRaises(self.Error),
        ):
            self.build_api(
                destination, reference=self.reference, improver_agent_sha256=self.improver_id
            )
        with (
            self.f.feedback.passive(),
            patch(
                "buddha.source_feedback._build",
                side_effect=AssertionError("v5 cannot derive prefix feedback"),
            ),
            self.assertRaises(self.Error),
        ):
            _build_failures(
                destination,
                self.reference,
                self.history,
                full_answers=False,
                improver_agent_sha256=self.improver_id,
            )
        self.assertEqual(self.snapshot(), before)
        with self.f.feedback.passive():
            written = self.write_api(
                destination,
                reference=self.reference,
                failure_history=self.history,
                improver_agent_sha256=self.improver_id,
            )
        self.inspect_packet(destination, bundle)
        self.assertEqual(self.authority.summary(), before[1])
        f = self.seam.case("same-fixed-I-next", self.improver_source)
        f.packet, f.written = destination, written
        f.record["feedback"] = written["feedback"]
        f.descriptor.write_bytes(_json(f.record))
        tasks = {
            task.id: task
            for task in TaskSet.from_bytes((destination / "source.json").read_bytes()).tasks
        }
        self.seam.projected = [
            {"task": tasks[row["task_id"]].to_record(), "note": row["note"]}
            for row in bundle["feedback"]["records"]
        ]
        f.prepare(expected_feedback_provenance_sha256=written["provenance"]["sha256"])
        resumed = self.seam.run_stage(f.child())
        self.assertEqual(resumed["disposition"], "materialized")
        self.assertEqual(resumed["improver_agent_sha256"], self.improver_id)
        self.assertEqual(len(self.seam.assert_roles(resumed).operations), 0)
        self.seam.passive(resumed)
        self.legacy_controls()

    def test_genuine_other_improver_or_measured_parent_cannot_supply_frozen_arm_history(self):
        from buddha.releases import _json

        destination = self.fixture()
        with self.f.feedback.passive():
            written = self.write_api(
                destination,
                reference=self.reference,
                failure_history=self.history,
                improver_agent_sha256=self.improver_id,
            )
        f = self.seam.case("other-fixed-I", self.seam.operator_source("other-arm-I"))
        other_improver = self.seam.operator_id
        self.assertNotEqual(other_improver, self.improver_id)
        before = self.snapshot()
        with self.f.feedback.passive(), self.assertRaises(self.Error):
            self.build_api(
                f.root / "wrong-improver-packet",
                reference=self.reference,
                failure_history=self.history,
                improver_agent_sha256=other_improver,
            )
        self.assertFalse((f.root / "wrong-improver-packet").exists())
        self.assertEqual(self.snapshot(), before)
        # All four packet files and I2 source/selection are genuine and hashed.
        # The protected consumer, not packet corruption, must reject I1's P5.
        f.record["feedback"] = written["feedback"]
        f.descriptor.write_bytes(_json(f.record))
        before = self.snapshot()
        with self.assertRaises(f.Error):
            f.prepare(expected_feedback_provenance_sha256=written["provenance"]["sha256"])
        self.assertFalse(f.directory.exists())
        self.assertEqual(self.snapshot(), before)
        # A real compatible second S occasion avoids a forged digest/schema
        # refusal; the original I1 proposal still demonstrably belongs to S1.
        other_parent = self.h.screen(self.h.second_source())
        other_directory, _ = self.h.prepare(
            other_parent, f.root / "other-parent-screen", self.authority
        )
        self.assertEqual(self.h.run_screen(other_directory)["disposition"], "screened")
        other_ref = self.h.reference(other_directory, self.authority)
        self.assertNotEqual(other_parent.candidate_id, self.seam.parent_id)
        altered = [self.history[0] | {"parent": other_ref}]
        before = self.snapshot()
        with self.f.feedback.passive(), self.assertRaises(self.Error):
            self.write_api(
                f.root / "wrong-parent-packet",
                reference=self.reference,
                failure_history=altered,
                improver_agent_sha256=self.improver_id,
            )
        self.assertFalse((f.root / "wrong-parent-packet").exists())
        self.assertEqual(self.snapshot(), before)


if __name__ == "__main__":
    unittest.main()
