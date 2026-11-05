"""One forward edge through original custody with supplied workers and replies.

The existing fixtures simulate generation, native scores, source loading and
HTTPS. They do not execute selected source, an official scorer or a real model.
This is not the three-development/26-final comparison or a replay-capacity proof.
"""

import copy
import hashlib
import json
import os
import unittest
from contextlib import contextmanager
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

import test_frozen_improver
import test_gateway
import test_source_feedback

from buddha.authorization import Authorization
from buddha.gateway import RawHTTPTransport
from buddha.releases import _json, prepare_selection


def sha(raw):
    return hashlib.sha256(raw).hexdigest()


class SourceForwardTests(unittest.TestCase):
    @contextmanager
    def no_history_restore(self):
        with (
            patch("buddha.source_search._restore", side_effect=AssertionError("search restore")),
            patch("buddha.improver_study._restore", side_effect=AssertionError("study restore")),
            patch(
                "buddha.improver_study._restore_observed",
                side_effect=AssertionError("observed study restore"),
            ),
        ):
            yield

    def fixture(self):
        from buddha import candidate_improvement
        from buddha.source_forward import (
            SourceForwardError,
            prepare_source_edge,
            run_source_edge,
        )
        from buddha.source_forward_results import inspect_source_edge

        self.Error = SourceForwardError
        self.prepare_api, self.run_api = prepare_source_edge, run_source_edge
        self.inspect_api = inspect_source_edge
        self.feedback = test_source_feedback.SourceFeedbackTests("runTest")
        self.feedback.setUp()
        self.addCleanup(self.feedback.doCleanups)
        self.feedback.source(count=10)
        self.h = h = self.feedback.h
        h.record["selected_ids"] = [1]
        self.parent = h.screen()
        self.answers = [
            "A supplied opening longer than the old excerpt. " * 3 + "\u96ea\u03b1 LATE_END",
            "",
            "\u96ea\u03b1",
            "  literal spaces  ",
            "repeat",
            "repeat",
            "six",
            "seven",
            "eight",
            "last output \u96ea",
        ]
        h.programs[self.parent.candidate_id]["answers"] = self.answers
        self.parent_directory, self.authority = h.prepare(self.parent)
        self.root, self.edge = h.root, h.root / "forward-edge"
        generation = self.parent.to_record()["generation"]
        parent_roots = {name: Path(path) for name, path in generation["roots"].items()}
        self.parent_source = parent_roots["agent"] / generation["entrypoint"]
        self.parent_raw = self.parent_source.read_bytes()
        actor = self.root / "fixed-improver"
        actor.mkdir()
        self.actor_source = actor / "candidate.py"
        self.seam = seam = test_frozen_improver.FrozenImproverTests("runTest")
        seam.operator_raw = seam.operator_source("forward-edge")
        self.actor_source.write_bytes(seam.operator_raw)
        roots = parent_roots | {"agent": actor}
        selected = prepare_selection(
            h.engine.candidate.release,
            roots,
            capabilities=generation["selection"]["capabilities"],
        )
        self.improver = copy.deepcopy(generation)
        self.improver.update(
            selection=selected.to_record(), roots={name: str(path) for name, path in roots.items()}
        )
        self.improver["executor"]["mounts"] = [
            ["/agent", str(actor)],
            ["/runner", str(roots["runner"])],
        ]
        seam.parent_id, seam.operator_id = self.parent.candidate_id, selected.agent_sha256
        seam.parent_raw, seam.parent_roots = self.parent_raw, parent_roots
        seam.observed, seam.connections = [], []
        seam.f = SimpleNamespace(
            h=h.engine.candidate,
            roots=roots,
            record=self.improver,
            directory=self.edge / "proposal",
            run_api=candidate_improvement.run_candidate_improvement,
        )
        self.child_answers = list(reversed(self.answers))
        self.returned = {
            "source": "def generate(task, config, complete):\n    return "
            + repr(self.child_answers)
            + "\ndef propose_improvement(parent, feedback, config, complete): return {}\n",
            "hypothesis": "Supplied forward edge; no measured improvement claim.",
        }
        self.proposals = []

    def prepare(self):
        with self.no_history_restore():
            self.assertEqual(
                self.prepare_api(
                    self.edge,
                    parent=self.parent_directory,
                    improver=self.improver,
                    authorization=self.authority,
                ),
                self.edge,
            )
        self.definition_sha256 = sha((self.edge / "edge.json").read_bytes())

    def run_edge(self, proposal=None):
        def stage(directory, *, transport):
            self.assertEqual(directory, self.edge / "proposal")
            self.assertTrue(transport.allow_paid)
            packet = json.loads((self.edge / "feedback/feedback.json").read_bytes())
            self.seam.projected = [
                {"task": self.parent.tasks.tasks[0].to_record(), "note": row["note"]}
                for row in packet["records"]
            ]
            result = self.seam.run_stage(
                self.returned if proposal is None else proposal, callbacks=1
            )
            self.proposals.append(result)
            return result

        def worker(spec, *, initial, handle, **kwargs):
            if spec.role == "agent" and initial["agent_sha256"] not in self.h.programs:
                # Register supplied outputs from the actual production-written child declaration.
                record = json.loads((self.edge / "child/screen/screen.json").read_bytes())
                child = self.h.screen(record)
                self.assertEqual(initial["agent_sha256"], child.candidate_id)
                self.h.programs[child.candidate_id]["answers"] = self.child_answers
            return self.h.execute(spec, initial=initial, handle=handle, **kwargs)

        with (
            self.no_history_restore(),
            patch.dict(os.environ, {"OPENAI_API_KEY": test_gateway.KEY}, clear=True),
            patch("buddha.executor.run_container", side_effect=worker),
            patch("http.client.HTTPSConnection", side_effect=AssertionError("unexpected HTTPS")),
            patch("buddha.candidate_improvement.run_candidate_improvement", side_effect=stage),
        ):
            return self.run_api(
                self.edge,
                expected_definition_sha256=self.definition_sha256,
                transport=RawHTTPTransport(allow_paid=True),
            )

    def assert_keyless_replay(self, report):
        before = self.h.files(self.root), self.authority.summary()
        with (
            patch.dict(os.environ, {}, clear=True),
            self.h.readonly(),
            self.no_history_restore(),
        ):
            self.assertEqual(
                self.inspect_api(
                    self.edge,
                    expected_definition_sha256=self.definition_sha256,
                    expected_report_sha256=sha((self.edge / "report.json").read_bytes()),
                ),
                report,
            )
            self.assertEqual(
                self.run_api(
                    self.edge,
                    expected_definition_sha256=self.definition_sha256,
                    transport=RawHTTPTransport(allow_paid=False),
                ),
                report,
            )
        self.assertEqual((self.h.files(self.root), self.authority.summary()), before)

    def test_prepared_parent_full_feedback_fixed_proposal_private_child_and_keyless_replay(self):
        from buddha import source_forward_results as results

        self.fixture()
        self.assertEqual(self.authority.summary()["operation_count"], 0)
        self.prepare()
        report = self.run_edge()
        self.assertEqual((report["status"], report["disposition"]), ("complete", "evaluated"))
        self.assertEqual(report["failed_opportunities"], 0)
        for name, directory in (
            ("parent", self.parent_directory),
            ("proposal", self.edge / "proposal"),
            ("child", self.edge / "child/screen"),
        ):
            self.assertEqual(report[name], self.h.reference(directory, self.authority))
        packet = json.loads((self.edge / "feedback/feedback.json").read_bytes())
        self.assertEqual(packet["format"], "buddha.candidate-development-feedback.v2")
        self.assertEqual([row["task_id"] for row in packet["records"]], [1])
        note = json.loads(packet["records"][0]["note"])
        self.assertEqual(
            note["answers"],
            [{"position": index, "text": text} for index, text in enumerate(self.answers)],
        )
        self.assertEqual(note["omitted_answer_positions"], 0)
        self.assertEqual(len(self.seam.observed), 1)
        self.assertEqual(self.seam.observed[0][2], self.seam.projected)
        proposal = self.proposals[0]
        self.assertEqual(proposal["improver_agent_sha256"], self.seam.operator_id)
        original = Path(proposal["child"]["directory"]) / "candidate.py"
        copied = self.edge / "child/agent/candidate.py"
        self.assertEqual(original.read_bytes(), self.returned["source"].encode())
        self.assertEqual(copied.read_bytes(), original.read_bytes())
        self.assertFalse(copied.samefile(original))
        self.assertEqual(copied.stat().st_nlink, 1)
        child_record = json.loads((self.edge / "child/screen/screen.json").read_bytes())
        self.assertEqual(child_record["generation"]["roots"]["agent"], str(copied.parent))
        child_screen = self.h.Screen.from_bytes(_json(child_record))
        self.assertEqual(child_screen.comparison_key(), self.parent.comparison_key())
        lineage = json.loads(Path(proposal["child"]["lineage"]["path"]).read_bytes())
        self.assertEqual(lineage["parent"]["agent_sha256"], self.parent.candidate_id)
        self.assertEqual(lineage["improver"]["agent_sha256"], self.seam.operator_id)
        self.assertEqual(lineage["child"]["agent_sha256"], child_screen.candidate_id)
        parent = json.loads((self.parent_directory / "report.json").read_bytes())
        child = json.loads((self.edge / "child/screen/report.json").read_bytes())
        self.assertEqual(child["controls_sha256"], parent["controls_sha256"])
        self.assertEqual(
            report["measurements"],
            {"parent": parent["admission"], "child": child["admission"]},
        )
        self.assertEqual(self.parent_source.read_bytes(), self.parent_raw)
        self.assertEqual(self.actor_source.read_bytes(), self.seam.operator_raw)
        funding = self.authority.summary()
        self.assertEqual(
            (len(funding["runs"]), funding["operation_count"], funding["reserved_microusd"]),
            (9, 5, 0),
        )
        self.assertFalse(any(row["active"] for row in funding["runs"]))
        for key in ("operation_count", "spent_microusd", "reserved_microusd"):
            self.assertEqual(sum(row[key] for row in funding["runs"]), funding[key])
        self.assertEqual((self.h.engine.workers, self.h.engine.physical_sends), (8, 4))
        self.assertEqual(sum(c.request.call_count for c in self.seam.connections), 1)

        definition = json.loads((self.edge / "edge.json").read_bytes())
        owner_directory = self.edge / "proposal/owners/0"
        read_manifest = results._read_manifest
        owner = read_manifest(owner_directory)
        results._proposal_binding(self.edge, definition, self.parent, self.definition_sha256)
        source_pin = next(iter(definition["source_pins"]))
        self.assertIn(source_pin, [row["path"] for row in owner["invocation"]["inputs"]])
        for mutation in ("larger_budget", "wrong_review", "missing_source_pin"):
            forged = copy.deepcopy(owner)
            if mutation == "larger_budget":
                forged["settings"]["budget_microusd"] += 1
            elif mutation == "wrong_review":
                forged["review"]["account_scope"] += "-other"
            else:
                forged["invocation"]["inputs"] = [
                    row for row in forged["invocation"]["inputs"] if row["path"] != source_pin
                ]

            def altered_owner(location, *, changed=forged):
                return changed if location == owner_directory else read_manifest(location)

            with (
                self.subTest(proposal_owner=mutation),
                patch.object(results, "_read_manifest", side_effect=altered_owner) as reading,
                self.assertRaisesRegex(self.Error, "proposal differs"),
            ):
                results._proposal_binding(
                    self.edge, definition, self.parent, self.definition_sha256
                )
            reading.assert_any_call(owner_directory)

        self.assertEqual(
            results._result(
                self.edge, self.definition_sha256, definition, self.parent, parent, proposal, child
            ),
            report,
        )
        child_path = self.edge / "child/screen/screen.json"
        read = results.pipeline._read
        for mutation in ("wrong_lineage", "wrong_private_root"):
            forged = copy.deepcopy(child_record)
            if mutation == "wrong_lineage":
                forged["lineage"]["sha256"] = "0" * 64
            else:
                other = str(self.root / "another-private-source")
                forged["generation"]["roots"]["agent"] = other
                forged["generation"]["executor"]["mounts"][0] = ["/agent", other]

            changed_raw = _json(forged)

            def altered_child(path, *args, changed=changed_raw, **kwargs):
                return changed if path == child_path else read(path, *args, **kwargs)

            with (
                self.subTest(child_metadata=mutation),
                patch.object(results.pipeline, "_read", side_effect=altered_child) as reading,
                self.assertRaisesRegex(self.Error, "private source and lineage"),
            ):
                results._result(
                    self.edge,
                    self.definition_sha256,
                    definition,
                    self.parent,
                    parent,
                    proposal,
                    child,
                )
            reading.assert_called_once_with(child_path, child["screen_sha256"])
        self.assert_keyless_replay(report)

    def test_late_parent_report_change_retains_complete_leaves_and_refuses_publication(self):
        from buddha import source_forward

        self.fixture()
        self.prepare()
        result = source_forward._result
        changed = []

        def late_change(*args, **kwargs):
            complete = result(*args, **kwargs)
            path = self.parent_directory / "report.json"
            original = path.read_bytes()
            path.write_bytes(original + b"\n")
            changed.append(original)
            return complete

        with (
            patch.object(source_forward, "_result", side_effect=late_change) as assembled,
            self.assertRaises(self.Error),
        ):
            self.run_edge()
        assembled.assert_called_once()
        self.assertEqual((self.parent_directory / "report.json").read_bytes(), changed[0] + b"\n")
        self.assertFalse((self.edge / "report.json").exists())
        observations = list((self.edge / "observations").glob("*.json"))
        self.assertEqual(len(observations), 1)
        observation = json.loads(observations[0].read_bytes())
        self.assertEqual(
            (observation["status"], observation["stage"], observation["reason"]),
            ("incomplete", "child", "protocol"),
        )
        for directory in (
            self.parent_directory,
            self.edge / "proposal",
            self.edge / "child/screen",
        ):
            self.assertEqual(
                json.loads((directory / "report.json").read_bytes())["status"], "complete"
            )
        funding = self.authority.summary()
        self.assertEqual(
            (len(funding["runs"]), funding["operation_count"], funding["reserved_microusd"]),
            (9, 5, 0),
        )
        self.assertFalse(any(row["active"] for row in funding["runs"]))

    def test_changed_improver_overlaps_and_trial_grant_refuse_before_parent_spending(self):
        from buddha import trial_fence

        self.fixture()
        before = self.authority.summary()
        original = self.actor_source.read_bytes()
        self.actor_source.write_bytes(original + b"# changed after selection\n")
        with self.no_history_restore(), self.assertRaises(self.Error):
            self.prepare_api(
                self.edge,
                parent=self.parent_directory,
                improver=self.improver,
                authorization=self.authority,
            )
        self.actor_source.write_bytes(original)
        for output in (self.parent_directory / "edge", self.actor_source.parent / "edge"):
            with (
                self.subTest(output=output),
                self.no_history_restore(),
                self.assertRaises(self.Error),
            ):
                self.prepare_api(
                    output,
                    parent=self.parent_directory,
                    improver=self.improver,
                    authorization=self.authority,
                )
            self.assertFalse(output.exists())
        trial = Authorization.create(
            self.root / "trial-authority.sqlite3",
            authorization_id="offline-trial-denial",
            budget_microusd=1_000_000,
            max_calls=1000,
            scope=trial_fence._scope_text(trial_fence._TrialScope(self.root, "a" * 64, "search")),
        )
        with self.no_history_restore(), self.assertRaisesRegex(self.Error, "trial"):
            self.prepare_api(
                self.edge,
                parent=self.parent_directory,
                improver=self.improver,
                authorization=trial,
            )
        self.assertFalse(self.edge.exists())
        self.assertEqual(self.authority.summary(), before)
        self.assertEqual(trial.summary()["runs"], [])
        self.assertEqual((self.h.engine.workers, self.h.engine.physical_sends), (0, 0))

    def test_definition_pin_and_late_improver_drift_refuse_before_parent_dispatch(self):
        self.fixture()
        self.prepare()
        before = self.authority.summary()
        with (
            self.no_history_restore(),
            patch("buddha.executor.run_container", side_effect=AssertionError("new worker")),
            patch("http.client.HTTPSConnection", side_effect=AssertionError("new HTTPS")),
        ):
            with self.assertRaises(self.Error):
                self.run_api(
                    self.edge,
                    expected_definition_sha256="0" * 64,
                    transport=RawHTTPTransport(allow_paid=True),
                )
            self.actor_source.write_bytes(self.seam.operator_raw + b"# late drift\n")
            with self.assertRaises(self.Error):
                self.run_api(
                    self.edge,
                    expected_definition_sha256=self.definition_sha256,
                    transport=RawHTTPTransport(allow_paid=True),
                )
        self.assertEqual(self.authority.summary(), before)
        self.assertFalse((self.parent_directory / "report.json").exists())
        self.assertFalse((self.edge / "proposal").exists())

    def test_accounted_bad_proposal_is_failed_opportunity_without_child_screen(self):
        self.fixture()
        self.prepare()
        report = self.run_edge(proposal={})
        self.assertEqual((report["status"], report["disposition"]), ("complete", "rejected"))
        self.assertEqual(report["failed_opportunities"], 1)
        self.assertIsNone(report["child"])
        self.assertIsNone(report["measurements"]["child"])
        self.assertFalse((self.edge / "child/screen").exists())
        self.assertFalse((self.edge / "child/agent").exists())
        self.assertEqual(self.proposals[0]["disposition"], "rejected")
        self.assertEqual(
            report["proposal"], self.h.reference(self.edge / "proposal", self.authority)
        )
        funding = self.authority.summary()
        self.assertEqual(
            (len(funding["runs"]), funding["operation_count"], funding["reserved_microusd"]),
            (5, 3, 0),
        )
        self.assertFalse(any(row["active"] for row in funding["runs"]))
        self.assertEqual((self.h.engine.workers, self.h.engine.physical_sends), (4, 2))
        self.assertEqual(sum(c.request.call_count for c in self.seam.connections), 1)
        self.assert_keyless_replay(report)

    def test_unknown_parent_keeps_original_owner_hold_and_stops_without_replacement(self):
        self.fixture()
        self.h.programs[self.parent.candidate_id]["callbacks"] = 1
        self.h.engine.generation_timeout_once = True
        self.prepare()
        owner = self.parent_directory / "tasks/0/generation/owners/0/manifest.json"
        original = owner.read_bytes()
        first = self.run_edge()
        self.assertEqual(
            (first["status"], first["stage"], first["reason"]),
            ("incomplete", "parent", "unknown"),
        )
        self.assertEqual(json.loads((self.edge / first["observation"]).read_bytes()), first)
        self.assertFalse((self.edge / "report.json").exists())
        self.assertFalse((self.edge / "proposal").exists())
        before = self.authority.summary()
        self.assertEqual((len(before["runs"]), before["operation_count"]), (1, 1))
        self.assertGreater(before["reserved_microusd"], 0)
        self.assertEqual(self.h.engine.physical_sends, 1)
        with patch(
            "buddha.gateway.RawHTTPTransport.send_prepared",
            side_effect=AssertionError("retrying an unknown request"),
        ):
            second = self.run_edge()
        self.assertEqual((second["status"], second["stage"]), ("incomplete", "parent"))
        after = self.authority.summary()
        for key in ("operation_count", "spent_microusd", "reserved_microusd"):
            self.assertEqual(after[key], before[key])
        self.assertEqual(
            [row["run_id"] for row in after["runs"]],
            [row["run_id"] for row in before["runs"]],
        )
        self.assertEqual(owner.read_bytes(), original)
        self.assertEqual(self.h.engine.physical_sends, 1)
        self.assertEqual(self.proposals, [])


if __name__ == "__main__":
    unittest.main()
