"""Single-task candidate protocol through real funding and mocked container/HTTP."""

import base64
import hashlib
import json
import os
import shutil
import unittest
from dataclasses import asdict
from pathlib import Path
from unittest.mock import patch

import test_gateway as fixtures

from buddha.answers import Answers, TaskSet
from buddha.executor import ExecutionResult, ExecutorError, Limits
from buddha.releases import Release, _json, inventory, prepare_selection


def sha(raw):
    return hashlib.sha256(raw).hexdigest()


class CandidateSessionTests(unittest.TestCase):
    def setUp(self):
        # Import here so the initial missing-boundary RED is an ordinary test error.
        from buddha.candidate_run import CandidateRunError, CandidateSession

        self.Session, self.Error = CandidateSession, CandidateRunError
        self.fixture = f = fixtures.GatewayTests("runTest")
        f.setUp()
        self.addCleanup(f.doCleanups)
        self.package = Path(__file__).resolve().parents[1] / "buddha"
        self.runtime_bytes = (
            self.package.parent / "docs/conformance/src01-runtime-environment.json"
        ).read_bytes()
        self.runtime = json.loads(self.runtime_bytes)
        self.expected_runtime = sha(self.runtime_bytes)
        self.runtime_path = f.roots["environment"] / "runtime.json"
        self.runtime_path.write_bytes(self.runtime_bytes)
        (f.roots["agent"] / "identity.txt").unlink()
        self.source = f.roots["agent"] / "candidate.py"
        self.source.write_bytes(b'def generate(task, config, complete):\n    return ["", ""]\n')
        (f.roots["runner"] / "identity.txt").unlink()
        runner = f.roots["runner"] / "buddha"
        runner.mkdir()
        self.runner_names = ("__init__", "channel", "releases", "wire", "candidate_worker")
        self.host_names = (*self.runner_names, "executor", "answers", "candidate_run")
        for name in self.runner_names:
            shutil.copyfile(self.package / (name + ".py"), runner / (name + ".py"))
        dataset = b'{"id":"a","prompt":"one digit"}\n'
        dataset += b'{"id":"private","prompt":"UNSELECTED_SOURCE_SENTINEL"}\n'
        (f.roots["official"] / "data/tasks.jsonl").write_bytes(dataset)
        f.release_record["source"] = inventory(f.roots["official"])
        f.release_record["task"]["count"] = 2
        self.release = Release.from_record(f.release_record)
        self.tasks = TaskSet.from_dataset(self.release, dataset).select(["a"])
        self.task_path = f.root / "task.json"
        self.task_path.write_bytes(self.tasks.to_bytes())
        self.descriptor = f.root / "candidate.json"
        self.record = {
            "format": "buddha.candidate-generation.v1",
            "tasks": str(self.task_path),
            "config": {
                "provider": "openai",
                "model": "test-model",
                "max_output_tokens": 100,
                "instructions": "",
                "sampling": "regenerate",
            },
            "entrypoint": "candidate.py",
            "max_callbacks": 3,
            "runtime": {"path": str(self.runtime_path), "sha256": self.expected_runtime},
            "profile": {"capability": fixtures.CAPABILITY, "profile_id": "primary"},
            "executor": {
                "image_id": self.runtime["image_id"],
                "role": "agent",
                "mounts": [["/agent", str(f.roots["agent"])], ["/runner", str(f.roots["runner"])]],
                "runner_entrypoint": "buddha/candidate_worker.py",
                "image_environment": [
                    entry.split("=", 1) for entry in self.runtime["config"]["Env"]
                ],
                "limits": asdict(Limits()),
                "docker_endpoint": "unix:///var/run/docker.sock",
            },
        }
        self.preparations = 0
        self.freeze()

    def freeze(self, *, omit=()):
        f = self.fixture
        self.preparations += 1
        self.descriptor.write_bytes(_json(self.record))
        f.selection = prepare_selection(
            self.release, f.roots, capabilities={fixtures.CAPABILITY: "profiles/openai.json"}
        )
        self.bound = [
            self.descriptor,
            self.task_path,
            self.runtime_path,
            *[self.package / (name + ".py") for name in self.host_names],
        ]
        self.directory = f.prepare(
            "candidate-" + str(self.preparations),
            input_files=[path for path in self.bound if path not in omit],
        )
        self.gateway = f.gateway(directory=self.directory)
        self.output = f.root / ("candidate-output-" + str(self.preparations))

    def session(self, *, output=None, expected_runtime=None):
        return self.Session(
            self.gateway,
            descriptor=self.descriptor,
            output=output or self.output,
            expected_runtime_sha256=expected_runtime or self.expected_runtime,
        )

    def ready(self):
        return {
            "type": "ready",
            "agent_sha256": self.fixture.selection.agent_sha256,
            "task_sha256": sha(_json(self.tasks.tasks[0].to_record())),
            "runtime_sha256": self.expected_runtime,
        }

    def request(self, sequence=0, *, text="offline candidate call", body_changes=None, **changes):
        body = {
            "model": "test-model",
            "max_completion_tokens": 100,
            "messages": [{"role": "user", "content": text}],
        }
        body.update(body_changes or {})
        return {
            "type": "request",
            "sequence": sequence,
            "provider": "openai",
            "body_base64": base64.b64encode(_json(body)).decode(),
        } | changes

    @staticmethod
    def done(answers, status="complete", reason="complete"):
        return {"type": "done", "status": status, "reason": reason, "answers": answers}

    def connection(self, *, timeout=False):
        response = self.fixture.response()
        connection = self.fixture.connection(response)
        if timeout:
            connection.getresponse.side_effect = TimeoutError("synthetic unknown")
        return connection

    def execute(
        self, session, *, callbacks=0, answers=None, exit_code=0, cleanup="removed", after_done=None
    ):
        answers = ["  poor literal  ", ""] if answers is None else answers

        def worker(spec, *, initial, handle, limits, docker_endpoint):
            self.assertEqual(spec.role, "agent")
            self.assertEqual({target for target, _ in spec.mounts}, {"/agent", "/runner"})
            self.assertEqual(initial["task"], self.tasks.tasks[0].to_record())
            self.assertNotIn(b"UNSELECTED_SOURCE_SENTINEL", _json(initial))
            self.assertNotIn(b"dataset_base64", _json(initial))
            handle(self.ready())
            for sequence in range(callbacks):
                reply = handle(self.request(sequence))
                if reply["type"] == "stop":
                    handle(self.done([], "stopped", reply["reason"]))
                    break
            else:
                handle(self.done(answers))
            if after_done is not None:
                after_done()
            return ExecutionResult(
                exit_code,
                "f" * 64,
                self.runtime["image_id"],
                0,
                0,
                sha(b""),
                1,
                0.01,
                _json({"fixture": "mock container; not confinement evidence"}),
                cleanup,
            )

        with (
            patch("buddha.candidate_run.executor.run_container", side_effect=worker),
            patch("http.client.HTTPSConnection", return_value=self.connection()),
            patch.dict(os.environ, {"OPENAI_API_KEY": fixtures.KEY}, clear=True),
        ):
            return session.run()

    def test_zero_callbacks_preserves_exact_weak_answers_and_c1_identity(self):
        self.record["max_callbacks"] = 0
        self.freeze()
        with patch.object(self.gateway, "execute", side_effect=AssertionError("unexpected spend")):
            result = self.execute(self.session())
        self.assertEqual(result["status"], "complete")
        answers = Answers.from_bytes((self.output / "answers.json").read_bytes())
        self.assertEqual(
            answers.to_record()["outputs"], [{"task_id": "a", "answers": ["  poor literal  ", ""]}]
        )
        self.assertEqual(answers.to_record()["agent_sha256"], self.fixture.selection.agent_sha256)
        self.assertEqual(self.gateway.ledger.totals()["operation_count"], 0)

    def test_three_callbacks_can_produce_two_answers(self):
        result = self.execute(self.session(), callbacks=3, answers=["same", "same"])
        self.assertEqual(result["status"], "complete")
        self.assertEqual(result["calls"]["completed"], 3)
        self.assertEqual(self.gateway.ledger.totals()["operation_count"], 3)

    def test_per_call_output_allowance_can_be_smaller_than_profile_ceiling(self):
        session = self.session()
        session.handle(self.ready())
        with (
            patch("http.client.HTTPSConnection", return_value=self.connection()),
            patch.dict(os.environ, {"OPENAI_API_KEY": fixtures.KEY}, clear=True),
        ):
            reply = session.handle(self.request(body_changes={"max_completion_tokens": 25}))
        self.assertEqual(reply["type"], "response")
        self.assertEqual(self.gateway.ledger.totals()["operation_count"], 1)

    def test_unfunded_model_and_output_allowances_never_reach_gateway(self):
        for changes in (
            {"model": "other-model"},
            {"max_completion_tokens": 101},
            {"max_completion_tokens": 0},
            {"max_completion_tokens": True},
            {"max_completion_tokens": None},
            {"max_tokens": 100},
        ):
            with self.subTest(changes=changes):
                session = self.session(
                    output=self.fixture.root / ("invalid-body-" + sha(_json(changes))[:8])
                )
                session.handle(self.ready())
                with patch.object(self.gateway, "execute", side_effect=AssertionError("spent")):
                    with self.assertRaises(self.Error):
                        session.handle(self.request(body_changes=changes))

    def host_stop_report(self, *, forged):
        from buddha.executor import ExecutorError

        session = self.session()

        def worker(spec, *, initial, handle, limits, docker_endpoint):
            handle(self.ready())
            self.assertEqual(handle(self.request())["reason"], "unknown")
            if forged:
                handle(self.done(["forged", "complete"]))
            raise ExecutorError("protocol", container_id="synthetic", cleanup_status="removed")

        with (
            patch("buddha.candidate_run.executor.run_container", side_effect=worker),
            patch("http.client.HTTPSConnection", return_value=self.connection(timeout=True)),
            patch.dict(os.environ, {"OPENAI_API_KEY": fixtures.KEY}, clear=True),
        ):
            report = session.run()
        self.assertEqual((report["status"], report["reason"]), ("stopped", "unknown"))
        self.assertEqual(report["host_stop_reason"], "unknown")
        self.assertGreater(report["gateway_totals"]["reserved_microusd"], 0)
        self.assertFalse((self.output / "answers.json").exists())

    def test_host_stop_survives_executor_failure(self):
        self.host_stop_report(forged=False)

    def test_host_stop_survives_forged_completion(self):
        self.host_stop_report(forged=True)

    def test_pre_cleanup_metadata_survives_executor_failure(self):
        error = ExecutorError(
            "cleanup", cleanup_status="unknown", pre_cleanup_failure=("create", "control")
        )
        with patch("buddha.candidate_run.executor.run_container", side_effect=error):
            report = self.session().run()
        self.assertEqual((report["status"], report["reason"]), ("failed", "execution"))
        self.assertEqual(report["execution"], error.to_record())
        self.assertEqual(self.gateway.ledger.totals()["operation_count"], 0)
        self.assertEqual(self.gateway.ledger.totals()["committed_microusd"], 0)
        self.assertFalse((self.output / "answers.json").exists())

    def test_fourth_callback_is_stopped_without_a_fourth_operation(self):
        result = self.execute(self.session(), callbacks=4)
        self.assertEqual(result["status"], "stopped")
        self.assertEqual(result["reason"], "quota")
        self.assertFalse((self.output / "answers.json").exists())
        self.assertEqual(self.gateway.ledger.totals()["operation_count"], 3)

    def test_original_receipts_replay_without_key_or_network(self):
        self.execute(self.session(), callbacks=3)
        before = self.gateway.ledger.totals()
        resumed = self.session(output=self.fixture.root / "replay-output")
        resumed.handle(self.ready())
        with (
            patch.dict(os.environ, {}, clear=True),
            patch("http.client.HTTPSConnection", side_effect=AssertionError("new send")),
        ):
            for index in range(3):
                self.assertEqual(resumed.handle(self.request(index))["type"], "response")
        self.assertEqual(self.gateway.ledger.totals(), before)

    def test_recovery_cannot_skip_completed_original_operation_prefix(self):
        self.execute(self.session(), callbacks=3)
        before = self.gateway.ledger.totals()
        resumed = self.session(output=self.fixture.root / "skipped-completed-prefix")
        result = self.execute(resumed, callbacks=0)
        self.assertNotEqual(result["status"], "complete")
        self.assertFalse(result["owner_operation_coverage_complete"])
        self.assertFalse((resumed.output / "answers.json").exists())
        self.assertEqual(self.gateway.ledger.totals(), before)

    def test_recovery_cannot_skip_unknown_original_operation(self):
        first = self.session()
        first.handle(self.ready())
        with (
            patch("http.client.HTTPSConnection", return_value=self.connection(timeout=True)),
            patch.dict(os.environ, {"OPENAI_API_KEY": fixtures.KEY}, clear=True),
        ):
            self.assertEqual(first.handle(self.request())["reason"], "unknown")
        before = self.gateway.ledger.totals()
        resumed = self.session(output=self.fixture.root / "skipped-unknown-prefix")
        result = self.execute(resumed, callbacks=0)
        self.assertNotEqual(result["status"], "complete")
        self.assertFalse(result["owner_operation_coverage_complete"])
        self.assertFalse((resumed.output / "answers.json").exists())
        self.assertEqual(self.gateway.ledger.totals(), before)

    def test_operation_added_after_done_blocks_final_publication(self):
        from buddha.gateway import GatewayCall

        def added_operation():
            raw = base64.b64decode(self.request()["body_base64"])
            self.gateway.execute(
                GatewayCall(fixtures.CAPABILITY, "primary", "unexpected-host-operation", 0, raw)
            )

        report = self.execute(self.session(), after_done=added_operation)
        self.assertEqual(report["status"], "failed")
        self.assertFalse(report["owner_operation_coverage_complete"])
        self.assertFalse((self.output / "answers.json").exists())
        self.assertEqual(self.gateway.ledger.totals()["operation_count"], 1)

    def test_changed_body_at_same_original_slot_stops_as_conflict(self):
        self.execute(self.session(), callbacks=1)
        before = self.gateway.ledger.totals()
        resumed = self.session(output=self.fixture.root / "conflict-output")
        resumed.handle(self.ready())
        reply = resumed.handle(self.request(text="changed prefix"))
        self.assertEqual(reply["type"], "stop")
        self.assertEqual(reply["reason"], "protocol")
        self.assertEqual(self.gateway.ledger.totals(), before)

    def test_unknown_hold_latches_even_if_worker_keeps_asking(self):
        session = self.session()
        session.handle(self.ready())
        with (
            patch("http.client.HTTPSConnection", return_value=self.connection(timeout=True)),
            patch.dict(os.environ, {"OPENAI_API_KEY": fixtures.KEY}, clear=True),
        ):
            reply = session.handle(self.request())
        self.assertEqual(reply["reason"], "unknown")
        before = self.gateway.ledger.totals()
        with patch.object(self.gateway, "execute", side_effect=AssertionError("extra send")):
            self.assertEqual(session.handle(self.request(1))["reason"], "unknown")
        with self.assertRaises(self.Error):
            session.handle(self.done(["forged", "complete"]))
        self.assertEqual(self.gateway.ledger.totals(), before)
        self.assertGreater(before["reserved_microusd"], 0)

    def test_interrupt_retains_unknown_charge_and_durable_cancelled_report(self):
        session = self.session()
        connection = self.connection()
        connection.getresponse.side_effect = KeyboardInterrupt

        def worker(spec, *, initial, handle, limits, docker_endpoint):
            handle(self.ready())
            handle(self.request())
            self.fail("interrupt was swallowed")

        with (
            patch("buddha.candidate_run.executor.run_container", side_effect=worker),
            patch("http.client.HTTPSConnection", return_value=connection),
            patch.dict(os.environ, {"OPENAI_API_KEY": fixtures.KEY}, clear=True),
        ):
            with self.assertRaises(KeyboardInterrupt):
                session.run()
        report = json.loads((self.output / "report.json").read_bytes())
        self.assertEqual((report["status"], report["reason"]), ("stopped", "cancelled"))
        self.assertGreater(report["gateway_totals"]["reserved_microusd"], 0)
        self.assertFalse((self.output / "answers.json").exists())

    def test_repeated_sequence_cannot_create_a_second_operation(self):
        session = self.session()
        session.handle(self.ready())
        with (
            patch("http.client.HTTPSConnection", return_value=self.connection()),
            patch.dict(os.environ, {"OPENAI_API_KEY": fixtures.KEY}, clear=True),
        ):
            self.assertEqual(session.handle(self.request())["type"], "response")
        before = self.gateway.ledger.totals()
        with patch.object(self.gateway, "execute", side_effect=AssertionError("extra send")):
            with self.assertRaises(self.Error):
                session.handle(self.request())
        self.assertEqual(self.gateway.ledger.totals(), before)

    def test_selected_input_drift_after_construction_fails_before_spending(self):
        for index, path in enumerate(
            [self.source, self.task_path, self.descriptor, self.runtime_path]
            + [self.fixture.roots["runner"] / "buddha/candidate_worker.py"]
        ):
            with self.subTest(path=path):
                session = self.session(output=self.fixture.root / ("drift-" + str(index)))
                original = path.read_bytes()
                try:
                    path.write_bytes(original + b"\n")
                    with patch.object(self.gateway, "execute", side_effect=AssertionError("spent")):
                        with self.assertRaises(self.Error):
                            session.handle(self.ready())
                finally:
                    path.write_bytes(original)

    def test_multiple_selected_tasks_fail_before_output(self):
        self.task_path.write_bytes(
            TaskSet.from_dataset(
                self.release, (self.fixture.roots["official"] / "data/tasks.jsonl").read_bytes()
            ).to_bytes()
        )
        self.freeze()
        with self.assertRaises(self.Error):
            self.session()
        self.assertFalse(self.output.exists())

    def test_invalid_source_or_callback_ceiling_fails_before_output(self):
        for raw in (b"\xff", b"#" * (1024**2 + 1)):
            with self.subTest(source_bytes=len(raw)):
                self.source.write_bytes(raw)
                self.freeze()
                with self.assertRaises(self.Error):
                    self.session()
                self.assertFalse(self.output.exists())
        self.source.write_bytes(b'def generate(task, config, complete): return ["", ""]\n')
        for ceiling in (True, -1, 1001):
            with self.subTest(ceiling=ceiling):
                self.record["max_callbacks"] = ceiling
                self.freeze()
                with self.assertRaises(self.Error):
                    self.session()
                self.assertFalse(self.output.exists())

    def test_incomplete_or_nonliteral_answers_never_publish_c1(self):
        for answers in (["one"], ["one", 2], ["one", "\ud800"]):
            with self.subTest(answers=repr(answers)):
                self.freeze()
                report = self.execute(self.session(), answers=answers)
                self.assertEqual(report["status"], "failed")
                self.assertFalse((self.output / "answers.json").exists())

    def test_output_cannot_overlap_selected_inputs_or_existing_results(self):
        for output in (
            self.source.parent / "new-output",
            self.source.parent,
            self.directory / "new-output",
            self.package / "new-output",
            self.fixture.root,
        ):
            with self.subTest(output=output):
                with self.assertRaises(self.Error):
                    self.session(output=output)

    def test_runtime_and_image_join_fail_before_output(self):
        with self.assertRaises(self.Error):
            self.session(expected_runtime="0" * 64)
        self.assertFalse(self.output.exists())
        self.record["executor"]["image_id"] = "sha256:" + "a" * 64
        self.freeze()
        with self.assertRaises(self.Error):
            self.session()
        self.assertFalse(self.output.exists())

    def test_omitting_executing_host_source_fails_before_output(self):
        self.freeze(omit=[self.package / "candidate_run.py"])
        with self.assertRaises(self.Error):
            self.session()
        self.assertFalse(self.output.exists())

    def test_invalid_or_extra_worker_fields_never_reach_gateway(self):
        for changes in (
            {"sequence": True},
            {"sequence": 1},
            {"provider": "anthropic"},
            {"logical_id": "forged"},
            {"attempt": 1},
            {"headers": []},
        ):
            with self.subTest(changes=changes):
                session = self.session(
                    output=self.fixture.root
                    / ("invalid-" + str(len(changes)) + "-" + sha(_json(changes))[:8])
                )
                session.handle(self.ready())
                with patch.object(self.gateway, "execute", side_effect=AssertionError("spent")):
                    with self.assertRaises(self.Error):
                        session.handle(self.request(**changes))

    def test_done_and_configuration_mutations_fail_closed(self):
        session = self.session()
        session.handle(self.ready())
        session.worker["task"]["prompt"] = "changed"
        with self.assertRaises(self.Error):
            session.handle(self.done(["one", "two"]))

    def test_failed_exit_or_cleanup_never_publishes_answers(self):
        for status in ({"exit_code": 1}, {"cleanup": "unknown"}):
            with self.subTest(status=status):
                self.freeze()
                result = self.execute(self.session(), **status)
                self.assertNotEqual(result["status"], "complete")
                self.assertFalse((self.output / "answers.json").exists())


if __name__ == "__main__":
    unittest.main()
