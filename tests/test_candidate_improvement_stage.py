"""Durable improvement stages through real sessions and saved measured feedback."""

import copy
import hashlib
import json
import os
import shutil
import sqlite3
import unittest
from contextlib import closing
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

import test_candidate_improvement as improvement_fixtures
import test_source_feedback as feedback_fixtures

from buddha.gateway import RawHTTPTransport
from buddha.gateway_history import read_gateway_history
from buddha.releases import Selection, _json, prepare_selection


def sha(raw):
    return hashlib.sha256(raw).hexdigest()


class CandidateImprovementStageTests(unittest.TestCase):
    def fixture(self):
        if not hasattr(self, "feedback"):
            self.feedback = feedback_fixtures.SourceFeedbackTests("runTest")
            self.feedback.setUp()
            self.addCleanup(self.feedback.doCleanups)
            self.screen, _, reference = self.feedback.completed()
            self.root = self.feedback.h.root
            self.packet = self.root / "measured-packet"
            self.written = self.feedback.write_api(self.packet, reference=reference)
            self.h = self.feedback.h.engine.candidate
            self.f = self.h.fixture
            generation = self.feedback.h.record["generation"]
            self.selection = Selection.from_bytes(_json(generation["selection"]))
            self.roots = {name: Path(path) for name, path in generation["roots"].items()}
            self.record = {
                key: copy.deepcopy(generation[key])
                for key in (
                    "config",
                    "entrypoint",
                    "executor",
                    "profile",
                    "runtime",
                    "max_callbacks",
                )
            }
            self.record.update(
                format="buddha.candidate-improvement.v1",
                parent_agent_sha256=self.selection.agent_sha256,
                feedback=self.written["feedback"],
            )
            self.descriptor = self.root / "improvement.json"
            self.descriptor.write_bytes(_json(self.record))
            self.directory = self.root / "improvement-stage"
            # Reuse only this fixture's worker/HTTPS helper, not a second setUp/dataset.
            self.worker = improvement_fixtures.ImprovementTests("runTest")
            self.worker.h = self.h
        return self

    def api(self):
        from buddha.candidate_improvement import (
            CandidateImprovementError,
            inspect_candidate_improvement,
            prepare_candidate_improvement,
            run_candidate_improvement,
        )

        self.Error = CandidateImprovementError
        self.prepare_api = prepare_candidate_improvement
        self.run_api = run_candidate_improvement
        self.inspect_api = inspect_candidate_improvement

    def prepare(self, **changes):
        self.fixture()
        values = {
            "descriptor": self.descriptor,
            "selection": self.selection,
            "roots": self.roots,
            "authorization": self.f.authority,
            "review": self.f.review,
            "budget_microusd": 10_000,
            "max_calls": 20,
            "expected_runtime_sha256": self.h.expected_runtime,
            "expected_feedback_provenance_sha256": self.written["provenance"]["sha256"],
        }
        return self.prepare_api(self.directory, **(values | changes))

    def child(self):
        return {
            "source": (
                "raise RuntimeError('returned source must never run on the host')\n"
                "def generate(task, config, complete): return ['', 'changed']\n"
                "def propose_improvement(parent, feedback, config, complete): return {}\n"
            ),
            "hypothesis": "Change the generation procedure; retain the inherited entrypoint.",
        }

    def run_stage(self, value=None, *, paid=True, **changes):
        proxy = SimpleNamespace(
            run=lambda: self.run_api(self.directory, transport=RawHTTPTransport(allow_paid=paid))
        )
        return self.worker.execute(proxy, self.child() if value is None else value, **changes)

    def owner_history(self):
        owner = self.directory / "owners/0"
        manifest = json.loads((owner / "manifest.json").read_bytes())
        return read_gateway_history(
            owner,
            manifest_sha256=manifest["record_sha256"],
            ledger_sha256=sha((owner / "operations.sqlite3").read_bytes()),
        )

    def partial(self, report):
        self.assertEqual(report["status"], "incomplete")
        observed = json.loads((self.directory / report["observation"]).read_bytes())
        self.assertEqual(
            {key: value for key, value in observed.items() if key != "observation"},
            {key: value for key, value in report.items() if key != "observation"},
        )
        self.assertEqual(Path(report["owner"]), self.directory / "owners/0")
        self.assertFalse((self.directory / "completed/0.json").exists())
        self.assertFalse((self.directory / "report.json").exists())

    def replay(self):
        with (
            patch.dict(os.environ, {}, clear=True),
            patch(
                "buddha.candidate_run.CandidateSession", side_effect=AssertionError("new session")
            ),
            patch("buddha.executor.run_container", side_effect=AssertionError("new worker")),
            patch("http.client.HTTPSConnection", side_effect=AssertionError("new HTTPS")),
        ):
            return self.run_api(self.directory, transport=RawHTTPTransport(allow_paid=False))

    def test_existing_measured_quad_inspects_without_reopening_public_writes(self):
        # Import failure is setup evidence before any genuine fixture is created.
        from buddha.source_feedback import SourceFeedbackError, inspect_source_feedback

        self.fixture()
        before = self.feedback.h.files(self.root), self.f.authority.summary()
        with self.feedback.passive():
            result = inspect_source_feedback(
                self.packet,
                expected_provenance_sha256=self.written["provenance"]["sha256"],
            )
        self.assertEqual(set(result), {"source", "split", "feedback", "provenance"})
        for name, record in result.items():
            self.assertEqual((self.packet / (name + ".json")).read_bytes(), _json(record))
        reference = result["provenance"]["reference"]
        for operation in (self.feedback.build_api, self.feedback.write_api):
            with self.assertRaises(SourceFeedbackError):
                operation(self.packet, reference=reference)
        self.assertEqual((self.feedback.h.files(self.root), self.f.authority.summary()), before)

    def test_materialized_stage_preserves_real_session_child_lineage_and_anchor(self):
        self.api()
        self.assertEqual(self.prepare(), self.directory)
        report = self.run_stage(callbacks=1)
        self.assertEqual((report["status"], report["disposition"]), ("complete", "materialized"))
        self.assertEqual(report["parent_agent_sha256"], self.selection.agent_sha256)
        seal_path = self.directory / "completed/0.json"
        seal = json.loads(seal_path.read_bytes())
        attempt = self.directory / seal["attempt"]
        session = attempt / "session"
        raw = json.loads((session / "report.json").read_bytes())
        self.assertEqual(raw["format"], "buddha.candidate-improvement-report.v1")
        self.assertEqual((raw["status"], raw["reason"]), ("complete", "complete"))
        self.assertEqual(report["improvement"], raw)
        self.assertEqual(raw["calls"], {"requested": 1, "completed": 1, "stopped": 0})
        self.assertEqual(
            (session / "child/candidate.py").read_bytes(), self.child()["source"].encode()
        )
        lineage = json.loads((session / "lineage.json").read_bytes())
        self.assertEqual(lineage["parent"]["agent_sha256"], self.selection.agent_sha256)
        self.assertEqual(lineage["descriptor_sha256"], sha(self.descriptor.read_bytes()))
        self.assertEqual(lineage["feedback"]["file_sha256"], self.written["feedback"]["sha256"])
        owner = json.loads((self.directory / "owners/0/manifest.json").read_bytes())
        self.assertEqual(lineage["owner"]["manifest_sha256"], owner["record_sha256"])
        funded = next(
            row for row in self.f.authority.summary()["runs"] if row["run_id"] == owner["run_id"]
        )
        self.assertFalse(funded["active"])
        with closing(sqlite3.connect(self.f.authority.path)) as connection:
            reason = connection.execute(
                "SELECT reason FROM auth_deactivations WHERE run_id=?", (owner["run_id"],)
            ).fetchone()[0]
        self.assertEqual(reason, "candidate improvement completed: " + sha(seal_path.read_bytes()))
        self.assertEqual(report["stage_seal_sha256"], sha(seal_path.read_bytes()))
        self.assertFalse((session / "answers.json").exists())

    def test_forward_fixed_improver_composes_full_feedback_and_child_screen_without_restore(self):
        import test_frozen_improver

        from buddha import candidate_improvement, source_screen
        from buddha.source_search import _child_screen_for

        self.api()
        answers = [
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
        measured = []

        def complete_parent(feedback):
            feedback.source(count=10)
            h = feedback.h
            h.record["selected_ids"] = [1]
            parent = h.screen()
            h.programs[parent.candidate_id]["answers"] = answers
            directory, authority = h.prepare(parent)
            self.assertEqual(h.run_screen(directory)["status"], "complete")
            measured.append((parent, authority))
            return directory, authority, h.reference(directory, authority)

        with (
            patch("buddha.source_search._restore", side_effect=AssertionError("search restore")),
            patch("buddha.improver_study._restore", side_effect=AssertionError("study restore")),
            patch(
                "buddha.improver_study._restore_observed",
                side_effect=AssertionError("observed study restore"),
            ),
            patch.object(feedback_fixtures.SourceFeedbackTests, "completed", complete_parent),
        ):
            self.fixture()
            h, engine = self.feedback.h, self.feedback.h.engine
            parent, authority = measured[0]
            self.f.authority = authority
            packet = json.loads((self.packet / "feedback.json").read_bytes())
            self.assertEqual(packet["format"], "buddha.candidate-development-feedback.v2")
            self.assertEqual([row["task_id"] for row in packet["records"]], [1])
            note = json.loads(packet["records"][0]["note"])
            self.assertEqual(
                note["answers"],
                [{"position": position, "text": text} for position, text in enumerate(answers)],
            )
            self.assertEqual(note["omitted_answer_positions"], 0)

            # Reuse the existing protected-v2 worker seam; supplied Python stays data.
            seam = test_frozen_improver.FrozenImproverTests("runTest")
            seam.f = self
            seam.parent_selection = self.selection.to_record()
            seam.parent_roots = dict(self.roots)
            seam.parent_path = self.roots["agent"] / self.record["entrypoint"]
            seam.parent_raw = seam.parent_path.read_bytes()
            seam.parent_id = parent.candidate_id
            seam.base_recipe = copy.deepcopy(self.record)
            seam.projected = [
                {"task": parent.tasks.tasks[0].to_record(), "note": packet["records"][0]["note"]}
            ]
            seam.observed, seam.connections = [], []
            seam.case("forward-fixed", seam.operator_source("forward-fixed"))
            self.prepare()
            child_answers = list(reversed(answers))
            returned = {
                "source": "def generate(task, config, complete):\n    return "
                + repr(child_answers)
                + "\ndef propose_improvement(parent, feedback, config, complete): return {}\n",
                "hypothesis": "Supplied one-edge composition; no measured improvement claim.",
            }
            proposal = seam.run_stage(returned, callbacks=1)
            self.assertEqual(
                (proposal["status"], proposal["disposition"]), ("complete", "materialized")
            )
            verified = self.inspect_api(
                self.directory,
                authorization=authority.path,
                expected_report_sha256=sha((self.directory / "report.json").read_bytes()),
            )
            self.assertEqual(verified, proposal)
            self.assertEqual(proposal["improver_agent_sha256"], seam.operator_id)
            self.assertEqual(len(seam.observed), 1)
            self.assertEqual(seam.observed[0][2], seam.projected)
            child = verified["child"]
            self.assertEqual(
                (Path(child["directory"]) / "candidate.py").read_bytes(),
                returned["source"].encode(),
            )
            lineage = json.loads(Path(child["lineage"]["path"]).read_bytes())
            self.assertEqual(lineage["parent"]["agent_sha256"], parent.candidate_id)
            self.assertEqual(lineage["improver"]["agent_sha256"], seam.operator_id)
            self.assertEqual(lineage["child"]["agent_sha256"], child["agent_sha256"])

            record = _child_screen_for(
                parent, verified, self.root / "forward-child", source_copy=False
            ).to_record()
            child_screen = h.screen(record)
            h.programs[child_screen.candidate_id]["answers"] = child_answers
            self.assertEqual(child_screen.comparison_key(), parent.comparison_key())
            destination, _ = h.prepare(child_screen, self.root / "forward-child-screen", authority)
            child_report = h.run_screen(destination)
            parent_report = json.loads((self.screen / "report.json").read_bytes())
            self.assertEqual(child_report["status"], "complete")
            self.assertEqual(child_report["parent_id"], parent.candidate_id)
            self.assertEqual(child_report["candidate_id"], child["agent_sha256"])
            self.assertEqual(child_report["controls_sha256"], parent_report["controls_sha256"])
            for metric in ("distinct", "utility"):
                self.assertEqual(
                    child_report["tasks"][0][metric], parent_report["tasks"][0][metric]
                )
            funding = authority.summary()
            self.assertEqual(
                (len(funding["runs"]), funding["operation_count"], funding["reserved_microusd"]),
                (9, 5, 0),
            )
            self.assertFalse(any(row["active"] for row in funding["runs"]))
            for key in ("operation_count", "spent_microusd", "reserved_microusd"):
                self.assertEqual(sum(row[key] for row in funding["runs"]), funding[key])
            self.assertEqual((engine.workers, engine.physical_sends), (8, 4))
            self.assertEqual(
                sum(connection.request.call_count for connection in seam.connections), 1
            )

            before = h.files(self.root), funding, engine.workers, engine.physical_sends
            with (
                patch.dict(os.environ, {}, clear=True),
                patch(
                    "buddha.candidate_run.CandidateSession",
                    side_effect=AssertionError("new session"),
                ),
                patch(
                    "buddha.native_run.NativeSession",
                    side_effect=AssertionError("new native session"),
                ),
                patch("buddha.executor.run_container", side_effect=AssertionError("new worker")),
                patch("http.client.HTTPSConnection", side_effect=AssertionError("new HTTPS")),
            ):
                transport = RawHTTPTransport(allow_paid=False)
                self.assertEqual(
                    candidate_improvement.run_candidate_improvement(
                        self.directory, transport=transport
                    ),
                    proposal,
                )
                self.assertEqual(
                    source_screen.run_source_screen(destination, transport=transport), child_report
                )
            self.assertEqual(
                (h.files(self.root), authority.summary(), engine.workers, engine.physical_sends),
                before,
            )

    def test_clean_failed_worker_outcomes_are_terminal_rejections_without_child_claims(self):
        self.api()
        self.fixture()
        cases = [
            ({}, "invalid_proposal", None),
            # A Python subclass can be rejected before its normalized JSON reaches the host.
            (self.child(), "invalid_proposal", None),
            (
                None,
                "proposal_unavailable",
                {"status": "omitted", "value": None, "sha256": "a" * 64, "bytes": 12},
            ),
            (
                None,
                "proposal_unavailable",
                {"status": "unavailable", "value": None, "sha256": None, "bytes": None},
            ),
            (
                None,
                "proposal_oversized",
                {
                    "status": "oversized",
                    "value": None,
                    "sha256": "b" * 64,
                    "bytes": 8 * 1024**2 + 1,
                },
            ),
            (
                None,
                "agent_error",
                {"status": "not_returned", "value": None, "sha256": None, "bytes": None},
            ),
        ]
        for index, (value, reason, capture) in enumerate(cases):
            with self.subTest(reason=reason, capture=capture):
                self.directory = self.root / ("rejected-stage-" + str(index))
                self.prepare()
                report = self.run_stage(
                    value,
                    status="failed",
                    reason=reason,
                    capture=capture,
                    callbacks=int(index == 0),
                )
                self.assertEqual(
                    (report["status"], report["disposition"]), ("complete", "rejected")
                )
                self.assertEqual(report["reason"], reason)
                self.assertIsNone(report["child"])
                raw = report["improvement"]
                self.assertEqual((raw["status"], raw["reason"]), ("failed", reason))
                seal = json.loads((self.directory / "completed/0.json").read_bytes())
                session = self.directory / seal["attempt"] / "session"
                self.assertEqual(json.loads((session / "report.json").read_bytes()), raw)
                saved = json.loads((session / "proposal.json").read_bytes())
                self.assertEqual(saved["proposal"], capture or self.worker.capture(value))
                self.assertFalse((session / "child").exists())
                self.assertFalse((session / "lineage.json").exists())
                before = self.feedback.h.files(self.root), self.f.authority.summary()
                self.assertEqual(self.replay(), report)
                self.assertEqual(
                    (self.feedback.h.files(self.root), self.f.authority.summary()), before
                )

    def test_known_reply_and_shortened_failed_prefix_recover_on_original_owner(self):
        from buddha.executor import ExecutorError

        self.api()
        self.prepare()
        first = self.run_stage(callbacks=1, worker_error=ExecutorError("synthetic after reply"))
        self.partial(first)
        original_files = self.feedback.h.files(self.directory / "attempts")
        original_owner = (self.directory / "owners/0/manifest.json").read_bytes()
        original = self.owner_history()
        self.assertEqual(len(original.operations), 1)
        self.assertEqual(original.operations[0].status, "completed")
        with patch(
            "buddha.gateway.RawHTTPTransport.send_prepared", side_effect=AssertionError("new send")
        ):
            short = self.run_stage({}, status="failed", reason="invalid_proposal")
            self.partial(short)
            recovered = self.run_stage(callbacks=1)
        self.assertEqual(
            (recovered["status"], recovered["disposition"]), ("complete", "materialized")
        )
        self.assertEqual((self.directory / "owners/0/manifest.json").read_bytes(), original_owner)
        self.assertEqual(self.owner_history().totals(), original.totals())
        for relative, digest in original_files.items():
            self.assertEqual(sha((self.directory / "attempts" / relative).read_bytes()), digest)
        self.assertEqual(len(list((self.directory / "owners").iterdir())), 1)

    def test_owned_worker_timeout_after_known_callbacks_counts_one_failed_opportunity(self):
        from buddha.executor import ExecutorError

        self.api()
        self.prepare()
        observed = []
        connection = self.h.connection()
        response = connection.getresponse.return_value

        def reply_after_watchdog():
            observed.append("watchdog expired before authoritative reply")
            return response

        connection.getresponse.side_effect = reply_after_watchdog
        error = ExecutorError(
            "timeout",
            cleanup_status="removed",
            container_id="f" * 64,
            pre_cleanup_failure=("watchdog", "timeout"),
        )
        with patch.object(self.h, "connection", return_value=connection):
            report = self.run_stage(callbacks=3, before_done_error=error)
        self.assertEqual(
            (report["status"], report.get("disposition"), report["reason"]),
            ("complete", "rejected", "worker_timeout"),
        )
        self.assertEqual(len(observed), 3)
        self.assertIsNone(report["child"])
        raw = report["improvement"]
        self.assertEqual((raw["status"], raw["reason"]), ("failed", "execution"))
        self.assertEqual(raw["execution"], error.to_record())
        self.assertNotIn("exit_code", raw["execution"])
        self.assertNotIn("image_id", raw["execution"])
        terminal = report["outcome"]["terminal"]
        self.assertTrue(
            all(terminal[key] is None for key in ("done_sha256", "done_status", "done_reason"))
        )
        history = self.owner_history()
        self.assertEqual([op.status for op in history.operations], ["completed"] * 3)
        totals = history.totals()
        self.assertEqual(totals["operation_count"], 3)
        self.assertGreater(totals["spent_microusd"], 0)
        self.assertEqual(totals["reserved_microusd"], 0)
        self.assertEqual(totals["committed_microusd"], totals["spent_microusd"])
        self.assertEqual(raw["gateway_totals"], totals)
        seal = json.loads((self.directory / "completed/0.json").read_bytes())
        session = self.directory / seal["attempt"] / "session"
        self.assertFalse((session / "proposal.json").exists())
        self.assertFalse((session / "child").exists())
        self.assertFalse((session / "lineage.json").exists())
        owners = [
            row
            for row in self.f.authority.summary()["runs"]
            if row["directory"] == str(self.directory / "owners/0")
        ]
        self.assertEqual(len(owners), 1)
        self.assertFalse(owners[0]["active"])
        before = self.feedback.h.files(self.root), self.f.authority.summary()
        self.assertEqual(self.replay(), report)
        self.assertEqual((self.feedback.h.files(self.root), self.f.authority.summary()), before)

    def test_unproven_or_unclean_timeouts_and_unknown_billing_stay_incomplete(self):
        from buddha.executor import ExecutorError

        self.api()
        self.fixture()
        proven = {
            "cleanup_status": "removed",
            "container_id": "f" * 64,
            "pre_cleanup_failure": ("watchdog", "timeout"),
        }
        cases = [
            ("cleanup", "cleanup", proven | {"cleanup_status": "unknown"}, {}),
            ("missing_provenance", "timeout", proven | {"pre_cleanup_failure": None}, {}),
            (
                "wrong_stage",
                "timeout",
                proven | {"pre_cleanup_failure": ("exchange", "timeout")},
                {},
            ),
            ("wrong_cause", "timeout", proven | {"pre_cleanup_failure": ("watchdog", "host")}, {}),
            ("missing_container", "timeout", proven | {"container_id": None}, {}),
            ("generic_failure", "host", proven, {}),
            ("unknown_billing", "timeout", proven, {"timeout": True, "ignore_stop": True}),
        ]
        for name, reason, values, changes in cases:
            with self.subTest(name=name):
                self.directory = self.root / ("unproven-timeout-" + name)
                self.prepare()
                error = ExecutorError(reason, **values)
                self.partial(self.run_stage(callbacks=1, before_done_error=error, **changes))
                history = self.owner_history()
                if name == "unknown_billing":
                    self.assertEqual([op.status for op in history.operations], ["unknown"])
                    self.assertGreater(history.totals()["reserved_microusd"], 0)
                else:
                    self.assertEqual([op.status for op in history.operations], ["completed"])
                    self.assertEqual(history.totals()["reserved_microusd"], 0)

    def test_timeout_after_done_or_source_drift_cannot_become_a_failed_opportunity(self):
        from buddha.executor import ExecutorError

        self.api()
        self.prepare()
        error = ExecutorError(
            "timeout",
            cleanup_status="removed",
            container_id="f" * 64,
            pre_cleanup_failure=("watchdog", "timeout"),
        )
        self.partial(self.run_stage(callbacks=1, worker_error=error))
        self.directory = self.root / "timeout-source-drift"
        self.prepare()
        connection = self.h.connection()
        response = connection.getresponse.return_value
        original = self.h.source.read_bytes()

        def reply_after_drift():
            self.h.source.write_bytes(original + b"\n# changed during callback\n")
            return response

        connection.getresponse.side_effect = reply_after_drift
        try:
            with patch.object(self.h, "connection", return_value=connection):
                with self.assertRaises(self.Error):
                    self.run_stage(callbacks=1, before_done_error=error)
            self.assertFalse((self.directory / "completed/0.json").exists())
            self.assertFalse((self.directory / "report.json").exists())
            observations = list((self.directory / "observations").glob("*.json"))
            self.assertEqual(len(observations), 1)
            self.assertEqual(json.loads(observations[0].read_bytes())["status"], "incomplete")
            self.assertEqual([op.status for op in self.owner_history().operations], ["completed"])
        finally:
            self.h.source.write_bytes(original)

    def test_unknown_hold_blocks_new_dispatch_and_cannot_become_a_rejected_terminal(self):
        self.api()
        self.prepare()
        first = self.run_stage(callbacks=1, timeout=True, ignore_stop=True)
        self.partial(first)
        original = self.owner_history()
        self.assertEqual([op.status for op in original.operations], ["unknown"])
        self.assertGreater(original.totals()["reserved_microusd"], 0)
        owner = (self.directory / "owners/0/manifest.json").read_bytes()
        with patch(
            "buddha.gateway.RawHTTPTransport.send_prepared", side_effect=AssertionError("new send")
        ):
            resumed = self.run_stage({}, status="failed", reason="invalid_proposal")
        self.partial(resumed)
        self.assertEqual(self.owner_history().totals(), original.totals())
        self.assertEqual((self.directory / "owners/0/manifest.json").read_bytes(), owner)

    def test_quota_stop_remains_incomplete_and_creates_no_operation(self):
        self.api()
        self.fixture()
        self.record["max_callbacks"] = 0
        self.descriptor.write_bytes(_json(self.record))
        self.prepare()
        stopped = self.run_stage(callbacks=1, ignore_stop=True)
        self.partial(stopped)
        self.assertEqual(stopped["reason"], "quota")
        self.assertEqual(len(self.owner_history().operations), 0)

    def test_bad_protocol_cleanup_and_materialization_failures_stay_incomplete(self):
        from buddha.candidate_run import CandidateRunError, CandidateSession

        self.api()
        self.fixture()
        for index, changes in enumerate([{"cleanup": "failed"}, {"exit_code": 1}]):
            with self.subTest(changes=changes):
                self.directory = self.root / ("failed-execution-" + str(index))
                self.prepare()
                self.partial(self.run_stage(**changes))
        self.directory = self.root / "broken-after-done"
        self.prepare()
        captured, original = [], CandidateSession.handle

        def observe(session, frame):
            if not captured:
                captured.append(session)
            return original(session, frame)

        def caught_protocol_error():
            with self.assertRaises(CandidateRunError):
                captured[0].handle({"type": "unexpected"})

        with patch.object(CandidateSession, "handle", observe):
            self.partial(
                self.run_stage(
                    {}, status="failed", reason="invalid_proposal", after_done=caught_protocol_error
                )
            )
        self.assertTrue(captured[0].broken)
        self.assertIsNotNone(captured[0].done)
        raw = json.loads((captured[0].output / "report.json").read_bytes())
        self.assertEqual(raw["execution"]["exit_code"], 0)
        self.assertEqual(raw["reason"], "invalid_proposal")
        self.directory = self.root / "materialization-collision"
        self.prepare()
        captured.clear()

        def collision():
            child = captured[0].output / "child"
            child.mkdir()
            (child / "candidate.py").write_bytes(b"original file")

        with patch.object(CandidateSession, "handle", observe):
            stopped = self.run_stage(after_done=collision)
        self.partial(stopped)
        self.assertEqual((captured[0].output / "child/candidate.py").read_bytes(), b"original file")
        self.assertEqual(
            json.loads((captured[0].output / "report.json").read_bytes())["reason"],
            "materialization",
        )

    def test_cancellation_preserves_received_proposal_and_observation_then_reraises(self):
        self.api()
        self.prepare()
        with self.assertRaises(KeyboardInterrupt):
            self.run_stage(worker_error=KeyboardInterrupt())
        observed = json.loads((self.directory / "observations/0.json").read_bytes())
        self.assertEqual((observed["status"], observed["reason"]), ("incomplete", "cancelled"))
        self.assertEqual(Path(observed["attempt"]), self.directory / "attempts/0-0")
        session = Path(observed["attempt"]) / "session"
        self.assertEqual(json.loads((session / "report.json").read_bytes())["reason"], "cancelled")
        self.assertEqual(
            json.loads((session / "proposal.json").read_bytes())["proposal"]["value"], self.child()
        )
        self.assertFalse((self.directory / "completed/0.json").exists())

    def test_edited_measured_notes_provenance_and_other_parent_reject_before_owner(self):
        self.api()
        self.fixture()
        original = {
            name: (self.packet / name).read_bytes() for name in ("feedback.json", "provenance.json")
        }
        original_descriptor = self.descriptor.read_bytes()
        mutations = [
            (
                "feedback.json",
                lambda value: value["records"][0].update(note="unmeasured edited note"),
            ),
            ("provenance.json", lambda value: value.update(candidate_id="f" * 64)),
        ]
        for index, (name, mutate) in enumerate(mutations):
            with self.subTest(name=name):
                self.directory = self.root / ("edited-packet-" + str(index))
                value = json.loads(original[name])
                mutate(value)
                (self.packet / name).write_bytes(_json(value))
                if name == "feedback.json":
                    # A self-consistent descriptor cannot authorize unmeasured replacement notes.
                    record = copy.deepcopy(self.record)
                    record["feedback"]["sha256"] = sha((self.packet / name).read_bytes())
                    self.descriptor.write_bytes(_json(record))
                before = self.f.authority.summary()
                try:
                    with self.assertRaises(self.Error):
                        self.prepare()
                    self.assertFalse((self.directory / "owners/0").exists())
                    self.assertEqual(self.f.authority.summary(), before)
                finally:
                    (self.packet / name).write_bytes(original[name])
                    self.descriptor.write_bytes(original_descriptor)
        other = self.root / "other-parent"
        other.mkdir()
        (other / "candidate.py").write_bytes(b"def generate(*args): return ['other']\n")
        roots = self.roots | {"agent": other}
        selected = prepare_selection(
            self.h.release, roots, capabilities=self.selection.to_record()["capabilities"]
        )
        record = copy.deepcopy(self.record)
        record["parent_agent_sha256"] = selected.agent_sha256
        record["executor"]["mounts"] = [["/agent", str(other)], ["/runner", str(roots["runner"])]]
        self.descriptor.write_bytes(_json(record))
        self.directory = self.root / "other-parent-stage"
        before = self.f.authority.summary()
        with self.assertRaises(self.Error):
            self.prepare(selection=selected, roots=roots)
        self.assertFalse((self.directory / "owners/0").exists())
        self.assertEqual(self.f.authority.summary(), before)

    def test_original_expected_input_hashes_and_prepared_feedback_cannot_be_replaced(self):
        self.api()
        self.fixture()
        control = self.root / "reviewed-extra.json"
        control.write_bytes(b"reviewed original")
        original = sha(control.read_bytes())
        control.write_bytes(b"changed publication")
        before = self.f.authority.summary()
        with self.assertRaises(self.Error):
            self.prepare(input_files=[control], expected_input_hashes={control: original})
        self.assertFalse((self.directory / "owners/0").exists())
        self.assertEqual(self.f.authority.summary(), before)
        self.directory = self.root / "prepared-feedback-drift"
        self.prepare()
        owner = (self.directory / "owners/0/manifest.json").read_bytes()
        feedback = json.loads((self.packet / "feedback.json").read_bytes())
        feedback["records"][0]["note"] = "new note after owner preparation"
        (self.packet / "feedback.json").write_bytes(_json(feedback))
        with (
            patch(
                "buddha.executor.run_container", side_effect=AssertionError("worker after drift")
            ),
            patch("http.client.HTTPSConnection", side_effect=AssertionError("send after drift")),
            self.assertRaises(self.Error),
        ):
            self.run_api(self.directory, transport=RawHTTPTransport(allow_paid=False))
        self.assertEqual((self.directory / "owners/0/manifest.json").read_bytes(), owner)
        self.assertEqual(len(self.owner_history().operations), 0)

    def test_changed_stored_session_report_cannot_be_sealed_as_actual_return(self):
        from buddha.candidate_run import CandidateSession

        self.api()
        self.prepare()
        original = CandidateSession.run

        def altered(session):
            report = original(session)
            path = session.output / "report.json"
            forged = json.loads(path.read_bytes())
            self.assertEqual(forged["gateway_totals"]["reserved_microusd"], 0)
            forged["gateway_totals"]["reserved_microusd"] = False
            path.write_bytes(_json(forged) + b"\n")
            return report

        with patch.object(CandidateSession, "run", altered), self.assertRaises(self.Error):
            self.run_stage(callbacks=1)
        self.assertFalse((self.directory / "completed/0.json").exists())
        observed = json.loads((self.directory / "observations/0.json").read_bytes())
        self.assertEqual(observed["reason"], "protocol")
        self.assertEqual(len(self.owner_history().operations), 1)

    def test_completed_replay_and_passive_inspection_preserve_original_shared_snapshot(self):
        self.api()
        self.prepare()
        first_directory = self.directory
        first = self.run_stage(callbacks=1)
        original = (first_directory / "report.json").read_bytes()
        self.directory = self.root / "second-improvement"
        self.prepare()
        self.assertEqual(self.run_stage(callbacks=1)["status"], "complete")
        self.directory = first_directory
        self.assertEqual(self.replay(), first)
        self.assertEqual((first_directory / "report.json").read_bytes(), original)
        for name in ("agent", "runner"):
            source = self.roots[name].resolve()
            self.assertTrue(source.is_relative_to(self.root.resolve()))
            destination = source.with_name("retired-" + source.name)
            self.assertTrue(destination.is_relative_to(self.root.resolve()))
            shutil.move(str(source), str(destination))
        before = self.feedback.h.files(self.root)
        with self.feedback.passive():
            inspected = self.inspect_api(
                self.directory,
                authorization=self.f.authority.path,
                expected_report_sha256=sha(original),
            )
        self.assertEqual(inspected, first)
        self.assertEqual(self.feedback.h.files(self.root), before)

    def test_passive_inspection_rejects_forged_publication_child_bytes_and_seal_anchor(self):
        self.api()
        self.prepare()
        report = self.run_stage(callbacks=1)
        report_path = self.directory / "report.json"
        seal_path = self.directory / "completed/0.json"
        child_path = Path(report["child"]["directory"]) / report["child"]["entrypoint"]
        original = {path: path.read_bytes() for path in (report_path, seal_path, child_path)}
        baseline = self.feedback.h.files(self.root)
        with self.feedback.passive():
            self.assertEqual(
                self.inspect_api(
                    self.directory,
                    authorization=self.f.authority.path,
                    expected_report_sha256=sha(original[report_path]),
                ),
                report,
            )
        self.assertEqual(self.feedback.h.files(self.root), baseline)
        for boundary in ("publication", "sealed-child", "independent-anchor"):
            with self.subTest(boundary=boundary):
                try:
                    changed = copy.deepcopy(report)
                    if boundary == "publication":
                        changed["child"]["source_sha256"] = "f" * 64
                    elif boundary == "sealed-child":
                        child_raw = original[child_path] + b"# controlled changed source\n"
                        child_path.write_bytes(child_raw)
                        changed["child"]["source_sha256"] = sha(child_raw)
                        changed["child"]["agent_sha256"] = sha(
                            _json({"candidate.py": sha(child_raw)})
                        )
                    else:
                        seal_raw = original[seal_path] + b"\n"
                        seal_path.write_bytes(seal_raw)
                        changed["stage_seal_sha256"] = sha(seal_raw)
                        changed["provenance"]["seals"]["completed/0.json"] = sha(seal_raw)
                    report_raw = _json(changed)
                    report_path.write_bytes(report_raw)
                    # New caller pins cannot replace the independently anchored original evidence.
                    before = self.feedback.h.files(self.root)
                    with self.feedback.passive(), self.assertRaises(self.Error):
                        self.inspect_api(
                            self.directory,
                            authorization=self.f.authority.path,
                            expected_report_sha256=sha(report_raw),
                        )
                    self.assertEqual(self.feedback.h.files(self.root), before)
                finally:
                    for path, raw in original.items():
                        path.write_bytes(raw)
        with self.feedback.passive():
            self.assertEqual(
                self.inspect_api(
                    self.directory,
                    authorization=self.f.authority.path,
                    expected_report_sha256=sha(original[report_path]),
                ),
                report,
            )
        self.assertEqual(self.feedback.h.files(self.root), baseline)


if __name__ == "__main__":
    unittest.main()
