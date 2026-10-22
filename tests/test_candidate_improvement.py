"""Improvement contracts through fake channels; returned source never executes here."""

import hashlib
import io
import json
import os
import sys
import unittest
from unittest.mock import patch

import test_candidate_run as generation_fixtures
import test_gateway as gateway_fixtures

from buddha.answers import TaskSet
from buddha.executor import ExecutionResult, ExecutorError
from buddha.releases import Release, _json, inventory, prepare_selection


def sha(raw):
    return hashlib.sha256(raw).hexdigest()


class ImprovementTests(unittest.TestCase):
    def setUp(self):
        self.h = h = generation_fixtures.CandidateSessionTests("runTest")
        h.setUp()
        self.addCleanup(h.doCleanups)
        f = h.fixture
        dataset = _json({"id": "a", "prompt": "development task"}) + b"\n"
        dataset += _json({"id": "validation", "prompt": "VALIDATION_SECRET"}) + b"\n"
        dataset += _json({"id": "final", "prompt": "FINAL_SECRET"}) + b"\n"
        (f.roots["official"] / "data/tasks.jsonl").write_bytes(dataset)
        f.release_record["source"] = inventory(f.roots["official"])
        h.release = Release.from_record(f.release_record)
        self.source = TaskSet.from_dataset(h.release, dataset)
        self.source_path = f.root / "source.json"
        self.source_path.write_bytes(self.source.to_bytes())
        self.split = {
            "release_sha256": self.source.release_sha256,
            "dataset_sha256": self.source.dataset_sha256,
            "partitions": {"development": ["a"], "validation": ["validation"], "final": ["final"]},
            "families": [{"id": task.id, "family": str(task.id)} for task in self.source.tasks],
        }
        self.split_path = f.root / "split.json"
        self.feedback_path = f.root / "feedback.json"
        self.feedback = {
            "format": "buddha.candidate-development-feedback.v1",
            "source": {"path": str(self.source_path), "sha256": sha(self.source_path.read_bytes())},
            "split": {"path": str(self.split_path), "sha256": ""},
            "records": [{"task_id": "a", "note": "Change the actual generation procedure."}],
        }
        h.record.pop("tasks")
        h.record.update(
            format="buddha.candidate-improvement.v1",
            parent_agent_sha256="",
            feedback={"path": str(self.feedback_path), "sha256": ""},
        )
        self.freeze()

    def freeze(self, *, omit=(), parent_sha=None):
        h, f = self.h, self.h.fixture
        self.split_path.write_bytes(_json(self.split))
        self.feedback["split"]["sha256"] = sha(self.split_path.read_bytes())
        self.feedback_path.write_bytes(_json(self.feedback))
        h.record["feedback"]["sha256"] = sha(self.feedback_path.read_bytes())
        f.selection = prepare_selection(
            h.release, f.roots, capabilities={gateway_fixtures.CAPABILITY: "profiles/openai.json"}
        )
        h.record["parent_agent_sha256"] = parent_sha or f.selection.agent_sha256
        h.descriptor.write_bytes(_json(h.record))
        h.preparations += 1
        inputs = [
            h.descriptor,
            h.runtime_path,
            self.source_path,
            self.split_path,
            self.feedback_path,
            *[h.package / (name + ".py") for name in (*h.host_names, "policy_study")],
        ]
        h.directory = f.prepare(
            "improvement-" + str(h.preparations),
            input_files=[p for p in inputs if p not in omit],
        )
        h.gateway = f.gateway(directory=h.directory)
        h.output = f.root / ("improvement-output-" + str(h.preparations))

    def capture(self, value):
        raw = _json(value)
        return {"status": "captured", "value": value, "sha256": sha(raw), "bytes": len(raw)}

    def execute(
        self,
        session,
        value,
        *,
        cleanup="removed",
        exit_code=0,
        capture=None,
        status="complete",
        reason="complete",
        callbacks=0,
        timeout=False,
        after_done=None,
        worker_error=None,
        ignore_stop=False,
    ):
        def worker(spec, *, initial, handle, limits, docker_endpoint):
            self.assertEqual(initial["format"], "buddha.candidate-improvement-worker.v1")
            self.assertNotIn(b"FINAL_SECRET", _json(initial))
            self.assertNotIn(b"VALIDATION_SECRET", _json(initial))
            self.assertNotIn(b"dataset_base64", _json(initial))
            handle(
                {
                    "type": "ready",
                    "agent_sha256": initial["agent_sha256"],
                    "feedback_sha256": sha(_json(initial["feedback"])),
                    "runtime_sha256": self.h.expected_runtime,
                }
            )
            final_status, final_reason = status, reason
            for sequence in range(callbacks):
                reply = handle(self.h.request(sequence))
                if reply["type"] == "stop":
                    if not ignore_stop:
                        final_status, final_reason = "stopped", reply["reason"]
                    break
            handle(
                {
                    "type": "done",
                    "status": final_status,
                    "reason": final_reason,
                    "proposal": self.capture(value) if capture is None else capture,
                }
            )
            if after_done is not None:
                after_done()
            if worker_error is not None:
                raise worker_error
            return ExecutionResult(
                exit_code,
                "f" * 64,
                self.h.runtime["image_id"],
                0,
                0,
                sha(b""),
                2,
                0.01,
                _json({"fixture": "fake channel; no source executed"}),
                cleanup,
            )

        with (
            patch("buddha.candidate_run.executor.run_container", side_effect=worker),
            patch("http.client.HTTPSConnection", return_value=self.h.connection(timeout=timeout)),
            patch.dict(os.environ, {"OPENAI_API_KEY": gateway_fixtures.KEY}, clear=True),
        ):
            return session.run()

    def child(self):
        return {
            "source": "def generate(task, config, complete): return ['changed']\n",
            "hypothesis": "Change the actual procedure.",
        }

    def worker_return(self, value, *, source=None):
        """Exercise dispatch/result code with exec intercepted, never run source on this host."""
        from buddha.candidate_worker import CandidateWorker

        worker = CandidateWorker(self.h.session().worker, io.BytesIO(), io.BytesIO())

        def fake_load(code, namespace):
            self.loaded_sources += 1
            namespace["generate"] = lambda *args: []
            namespace["propose_improvement"] = lambda *args: value

        self.loaded_sources = 0
        with (
            patch.object(worker, "_sources"),
            patch.object(worker, "_runtime"),
            patch(
                "buddha.candidate_worker._consume",
                return_value=(self.h.source.read_bytes() if source is None else source),
            ),
            patch("builtins.exec", side_effect=fake_load),
            patch.dict(sys.modules),
        ):
            return worker.run()

    def test_worker_rejects_returned_string_subclasses_without_losing_capture(self):
        class Source(str):
            pass

        value = self.child()
        value["source"] = Source(value["source"])
        done = self.worker_return(value)
        self.assertEqual((done["status"], done["reason"]), ("failed", "invalid_proposal"))
        self.assertEqual(done["proposal"]["status"], "captured")

    def test_worker_rejects_oversized_parent_before_loading_it(self):
        done = self.worker_return(self.child(), source=b"#" * (1024**2 + 1))
        self.assertNotEqual(done["status"], "complete")
        self.assertEqual(self.loaded_sources, 0)

    def test_capture_omission_and_serialization_failure_are_not_fabricated_raw_values(self):
        from buddha.releases import MAX_PROPOSAL_BYTES, _proposal_capture

        class BrokenMapping(dict):
            def items(self):
                raise RuntimeError("untrusted mapping cannot serialize")

        recursive = []
        recursive.append(recursive)
        for value in [recursive, {"value": float("nan")}, object(), BrokenMapping(value=1)]:
            capture = _proposal_capture(value)
            self.assertEqual(
                capture, {"status": "unavailable", "value": None, "sha256": None, "bytes": None}
            )
        text = "x" * MAX_PROPOSAL_BYTES
        capture = _proposal_capture(text)
        self.assertEqual(capture["status"], "oversized")
        self.assertIsNone(capture["value"])
        self.assertEqual(capture["bytes"], len(text) + 2)
        self.assertEqual(capture["sha256"], sha(json.dumps(text).encode()))

    def test_worker_omits_serialized_value_that_cannot_fit_wrapped_channel_depth(self):
        value = []
        for _ in range(64):
            value = [value]
        done = self.worker_return(value)
        self.assertEqual((done["status"], done["reason"]), ("failed", "proposal_unavailable"))
        self.assertIsNone(done["proposal"]["value"])

    def test_materializes_literal_child_without_host_execution(self):
        child = (
            "raise RuntimeError('returned source must never execute on the host')\n"
            "def generate(task, config, complete): return []\n"
            "def propose_improvement(parent, feedback, config, complete): return {}\n"
        )
        report = self.execute(
            self.h.session(), {"source": child, "hypothesis": "Procedure change."}
        )
        self.assertEqual(report["status"], "complete")
        self.assertEqual((self.h.output / "child/candidate.py").read_bytes(), child.encode())
        lineage = json.loads((self.h.output / "lineage.json").read_bytes())
        self.assertEqual(lineage["parent"]["agent_sha256"], self.h.fixture.selection.agent_sha256)
        self.assertEqual(lineage["child"]["source_sha256"], sha(child.encode()))
        self.assertEqual(
            report["artifacts"]["lineage.json"], sha((self.h.output / "lineage.json").read_bytes())
        )
        self.assertFalse((self.h.output / "answers.json").exists())

    def test_child_selection_changes_only_agent_and_lineage_binds_original_inputs(self):
        session = self.h.session()
        self.execute(session, self.child())
        original = self.h.fixture.selection.to_record()
        roots = self.h.fixture.roots | {"agent": self.h.output / "child"}
        child = prepare_selection(
            self.h.release, roots, capabilities=original["capabilities"]
        ).to_record()
        self.assertEqual(child["release"], original["release"])
        self.assertEqual(child["capabilities"], original["capabilities"])
        for name in original["components"]:
            if name != "agent":
                self.assertEqual(child["components"][name], original["components"][name])
        self.assertNotEqual(child["components"]["agent"], original["components"]["agent"])
        lineage = json.loads((self.h.output / "lineage.json").read_bytes())
        self.assertEqual(lineage["descriptor_sha256"], sha(self.h.descriptor.read_bytes()))
        self.assertEqual(lineage["feedback"]["file_sha256"], sha(self.feedback_path.read_bytes()))
        self.assertEqual(
            lineage["feedback"]["input_sha256"], sha(_json(session.worker["feedback"]))
        )

    def test_bounded_invalid_values_are_preserved_without_materialization(self):
        cases = [
            {},
            {"source": 3, "hypothesis": "reason"},
            {"source": "x", "hypothesis": " "},
            {"source": "\ud800", "hypothesis": "invalid UTF-8"},
            {"source": "x" * (1024**2 + 1), "hypothesis": "oversized source"},
            {"source": "x", "hypothesis": "x" * 4097},
            self.child() | {"executor": {"role": "evaluator"}},
            {"source": self.h.source.read_text(), "hypothesis": "unchanged"},
        ]
        for index, value in enumerate(cases):
            with self.subTest(index=index):
                output = self.h.fixture.root / ("invalid-" + str(index))
                report = self.execute(self.h.session(output=output), value)
                self.assertEqual(report["status"], "failed")
                saved = json.loads((output / "proposal.json").read_bytes())
                self.assertEqual(saved["proposal"]["value"], value)
                self.assertFalse((output / "child").exists())

    def test_bad_capture_metadata_is_preserved_but_never_trusted(self):
        good = self.capture(self.child())
        cases = [
            good | {"sha256": "a" * 64},
            good | {"bytes": True},
            good | {"status": []},
            good | {"unexpected": 1},
        ]
        for index, capture in enumerate(cases):
            with self.subTest(index=index):
                output = self.h.fixture.root / ("capture-" + str(index))
                report = self.execute(self.h.session(output=output), None, capture=capture)
                self.assertNotEqual(report["status"], "complete")
                self.assertEqual(
                    json.loads((output / "proposal.json").read_bytes())["proposal"], capture
                )
                self.assertFalse((output / "child").exists())

    def test_worker_declared_invalid_or_unavailable_capture_stays_explicit(self):
        cases = [
            ("invalid_proposal", self.capture({"wrong": "still retained"})),
            (
                "proposal_unavailable",
                {"status": "unavailable", "value": None, "sha256": None, "bytes": None},
            ),
            (
                "proposal_oversized",
                {
                    "status": "oversized",
                    "value": None,
                    "sha256": "a" * 64,
                    "bytes": 8 * 1024**2 + 1,
                },
            ),
        ]
        for index, (reason, capture) in enumerate(cases):
            with self.subTest(reason=reason):
                output = self.h.fixture.root / ("declared-" + str(index))
                report = self.execute(
                    self.h.session(output=output),
                    None,
                    capture=capture,
                    status="failed",
                    reason=reason,
                )
                self.assertEqual((report["status"], report["reason"]), ("failed", reason))
                self.assertIn("worker-declared", report["proposal_evidence"])
                self.assertEqual(
                    json.loads((output / "proposal.json").read_bytes())["proposal"], capture
                )
                self.assertFalse((output / "child").exists())

    def test_cleanup_failure_and_nonzero_exit_keep_proposal_without_child(self):
        for index, changes in enumerate(
            [{"cleanup": "failed"}, {"exit_code": 1}, {"worker_error": ExecutorError("timeout")}]
        ):
            with self.subTest(changes=changes):
                output = self.h.fixture.root / ("cleanup-" + str(index))
                report = self.execute(self.h.session(output=output), self.child(), **changes)
                self.assertNotEqual(report["status"], "complete")
                self.assertEqual(
                    json.loads((output / "proposal.json").read_bytes())["proposal"]["value"],
                    self.child(),
                )
                self.assertFalse((output / "child").exists())

    def test_cancellation_after_received_proposal_saves_observation_and_original_evidence(self):
        with self.assertRaises(KeyboardInterrupt):
            self.execute(self.h.session(), self.child(), worker_error=KeyboardInterrupt())
        report = json.loads((self.h.output / "report.json").read_bytes())
        self.assertEqual((report["status"], report["reason"]), ("stopped", "cancelled"))
        self.assertTrue((self.h.output / "proposal.json").exists())
        self.assertFalse((self.h.output / "child").exists())

    def test_existing_child_destination_is_never_overwritten(self):
        def existing():
            (self.h.output / "child").mkdir()
            (self.h.output / "child/candidate.py").write_bytes(b"original")

        report = self.execute(self.h.session(), self.child(), after_done=existing)
        self.assertEqual((report["status"], report["reason"]), ("failed", "materialization"))
        self.assertEqual((self.h.output / "child/candidate.py").read_bytes(), b"original")
        self.assertFalse((self.h.output / "lineage.json").exists())

    def test_only_source_bound_unique_development_ids_are_accepted(self):
        for identifier in ["validation", "final", "unknown", True]:
            with self.subTest(identifier=identifier):
                self.feedback["records"] = [{"task_id": identifier, "note": "not eligible"}]
                self.freeze()
                with self.assertRaises(self.h.Error):
                    self.h.session()
                self.assertFalse(self.h.output.exists())
        self.feedback["records"] = [{"task_id": "a", "note": "one"}] * 2
        self.freeze()
        with self.assertRaises(self.h.Error):
            self.h.session()

    def test_split_membership_and_family_source_joins_are_mandatory(self):
        for change in ["hash", "family", "coverage"]:
            with self.subTest(change=change):
                original = json.loads(_json(self.split))
                if change == "hash":
                    self.split["dataset_sha256"] = "a" * 64
                elif change == "family":
                    self.split["families"][1]["family"] = self.split["families"][0]["family"]
                else:
                    self.split["partitions"]["final"] = ["validation"]
                self.freeze()
                with self.assertRaises(self.h.Error):
                    self.h.session()
                self.split = original

    def test_improvement_helper_and_feedback_references_must_be_original_bound_inputs(self):
        for path in [
            self.h.package / "policy_study.py",
            self.source_path,
            self.split_path,
            self.feedback_path,
        ]:
            with self.subTest(path=path.name):
                self.freeze(omit=[path])
                with self.assertRaises(self.h.Error):
                    self.h.session()
                self.assertFalse(self.h.output.exists())

    def test_wrong_parent_identity_and_loaded_split_helper_origin_fail(self):
        self.freeze(parent_sha="a" * 64)
        with self.assertRaises(self.h.Error):
            self.h.session()
        self.freeze()
        from buddha import policy_study

        with patch.object(policy_study, "__file__", str(self.h.fixture.root / "foreign.py")):
            with self.assertRaises(self.h.Error):
                self.h.session()

    def test_feedback_drift_after_return_keeps_proposal_but_blocks_child(self):
        report = self.execute(
            self.h.session(),
            self.child(),
            after_done=lambda: self.feedback_path.write_bytes(b"changed"),
        )
        self.assertNotEqual(report["status"], "complete")
        self.assertTrue((self.h.output / "proposal.json").exists())
        self.assertFalse((self.h.output / "child").exists())

    def test_model_callbacks_account_once_and_replay_on_same_original_owner(self):
        first = self.execute(self.h.session(), self.child(), callbacks=2)
        self.assertEqual(first["status"], "complete")
        before = self.h.gateway.ledger.totals()
        resumed = self.h.session(output=self.h.fixture.root / "replayed-child")
        # A new network send would produce a different receipt and fail this guard.
        with patch(
            "buddha.gateway.RawHTTPTransport.send_prepared", side_effect=AssertionError("new send")
        ):
            replay = self.execute(resumed, self.child(), callbacks=2)
        self.assertEqual(replay["status"], "complete")
        self.assertEqual(self.h.gateway.ledger.totals(), before)
        self.assertEqual(before["operation_count"], 2)

    def test_recovery_cannot_skip_original_completed_or_unknown_prefix(self):
        self.execute(self.h.session(), self.child(), callbacks=1)
        before = self.h.gateway.ledger.totals()
        output = self.h.fixture.root / "skipped-prefix"
        report = self.execute(self.h.session(output=output), self.child())
        self.assertNotEqual(report["status"], "complete")
        self.assertFalse(report["owner_operation_coverage_complete"])
        self.assertFalse((output / "child").exists())
        self.assertEqual(self.h.gateway.ledger.totals(), before)

    def test_unknown_and_quota_stops_cannot_be_caught_into_success(self):
        unknown = self.execute(
            self.h.session(), self.child(), callbacks=1, timeout=True, ignore_stop=True
        )
        self.assertEqual(unknown["status"], "stopped")
        self.assertEqual(unknown["reason"], "unknown")
        self.assertGreater(unknown["gateway_totals"]["reserved_microusd"], 0)
        self.assertFalse((self.h.output / "child").exists())
        before = self.h.gateway.ledger.totals()
        output = self.h.fixture.root / "skip-unknown"
        report = self.execute(self.h.session(output=output), self.child())
        self.assertNotEqual(report["status"], "complete")
        self.assertEqual(self.h.gateway.ledger.totals(), before)

    def test_quota_stop_creates_no_extra_operation_or_child(self):
        self.h.record["max_callbacks"] = 0
        self.freeze()
        report = self.execute(self.h.session(), self.child(), callbacks=1, ignore_stop=True)
        self.assertEqual((report["status"], report["reason"]), ("stopped", "quota"))
        self.assertEqual(report["gateway_totals"]["operation_count"], 0)
        self.assertFalse((self.h.output / "child").exists())

    def test_worker_projection_rejects_boolean_duplicate_and_full_source_inputs(self):
        from buddha.candidate_worker import CandidateWorker, CandidateWorkerError

        initial = self.h.session().worker
        for kind in ["boolean", "duplicate", "source"]:
            with self.subTest(kind=kind):
                value = json.loads(_json(initial))
                if kind == "boolean":
                    value["feedback"][0]["task"]["id"] = True
                elif kind == "duplicate":
                    value["feedback"] *= 2
                else:
                    value["feedback"][0]["dataset_base64"] = "not allowed"
                with self.assertRaises(CandidateWorkerError):
                    CandidateWorker(value, io.BytesIO(), io.BytesIO())

    def test_changed_body_at_original_improvement_slot_conflicts_without_send(self):
        first = self.execute(self.h.session(), self.child(), callbacks=1)
        self.assertEqual(first["status"], "complete")
        before = self.h.gateway.ledger.totals()
        original = self.h.request
        with patch.object(
            self.h,
            "request",
            side_effect=lambda sequence: original(sequence, text="changed original request body"),
        ):
            report = self.execute(
                self.h.session(output=self.h.fixture.root / "conflicting-replay"),
                self.child(),
                callbacks=1,
            )
        self.assertEqual((report["status"], report["reason"]), ("stopped", "protocol"))
        self.assertEqual(self.h.gateway.ledger.totals(), before)

    def test_new_logical_domain_names_parent_feedback_and_original_ordinal(self):
        from buddha.gateway import GatewayCall

        session = self.h.session()
        self.execute(session, self.child(), callbacks=1)
        import base64

        logical = sha(
            _json(
                [
                    "buddha.candidate-improvement-call.v1",
                    sha(self.h.descriptor.read_bytes()),
                    self.h.fixture.selection.agent_sha256,
                    sha(_json(session.worker["feedback"])),
                    0,
                ]
            )
        )
        call = GatewayCall(
            gateway_fixtures.CAPABILITY,
            "primary",
            logical,
            0,
            base64.b64decode(self.h.request()["body_base64"]),
        )
        operation = self.h.gateway.ledger.get(self.h.gateway.operation_id(call))
        self.assertIsNotNone(operation)
        self.assertEqual(operation.status, "completed")

    def test_operation_added_after_done_blocks_materialization_without_losing_money(self):
        import base64

        from buddha.gateway import GatewayCall

        def added():
            self.h.gateway.execute(
                GatewayCall(
                    gateway_fixtures.CAPABILITY,
                    "primary",
                    "different-host-operation",
                    0,
                    base64.b64decode(self.h.request()["body_base64"]),
                )
            )

        report = self.execute(self.h.session(), self.child(), after_done=added)
        self.assertNotEqual(report["status"], "complete")
        self.assertEqual(report["gateway_totals"]["operation_count"], 1)
        self.assertGreater(report["gateway_totals"]["spent_microusd"], 0)
        self.assertFalse(report["owner_operation_coverage_complete"])
        self.assertTrue((self.h.output / "proposal.json").exists())
        self.assertFalse((self.h.output / "child").exists())

    def test_nonfitting_frame_cannot_claim_captured_proposal_or_discard_charge(self):
        value = []
        for _ in range(64):
            value = [value]
        report = self.execute(self.h.session(), value, callbacks=1)
        self.assertNotEqual(report["status"], "complete")
        self.assertIn("unavailable", report["proposal_evidence"])
        self.assertEqual(report["gateway_totals"]["operation_count"], 1)
        self.assertGreater(report["gateway_totals"]["spent_microusd"], 0)
        self.assertFalse((self.h.output / "proposal.json").exists())

    def test_no_received_frame_has_no_fabricated_proposal(self):
        with patch(
            "buddha.candidate_run.executor.run_container", side_effect=ExecutorError("launch")
        ):
            report = self.h.session().run()
        self.assertEqual((report["status"], report["reason"]), ("failed", "execution"))
        self.assertIn("unavailable", report["proposal_evidence"])
        self.assertNotIn("proposal.json", report["artifacts"])


if __name__ == "__main__":
    unittest.main()
