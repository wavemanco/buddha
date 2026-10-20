"""Frozen generation host supervision through real shared funding; no containers."""

import base64
import copy
import hashlib
import json
import os
import shutil
import unittest
from dataclasses import asdict, replace
from pathlib import Path
from unittest.mock import patch

import test_gateway as fixtures

from agents import frozen_seed
from buddha.agent_run import AgentRunError, AgentSession
from buddha.answers import Answers, TaskSet
from buddha.executor import ExecutionResult, Limits
from buddha.releases import Release, ReleaseError, _json, inventory, prepare_selection


def sha(raw):
    return hashlib.sha256(raw).hexdigest()


class AgentSessionTests(unittest.TestCase):
    def setUp(self):
        network = patch(
            "socket.create_connection", side_effect=AssertionError("external network denied")
        )
        network.start()
        self.addCleanup(network.stop)
        self.fixture = fixture = fixtures.GatewayTests("runTest")
        fixture.setUp()
        self.addCleanup(fixture.doCleanups)
        self.package = Path(__file__).resolve().parents[1] / "buddha"
        self.runner_names = ("__init__", "channel", "releases", "wire", "agent_worker")
        self.host_names = (*self.runner_names, "executor", "answers", "agent_run")
        (fixture.roots["runner"] / "identity.txt").unlink()
        package = fixture.roots["runner"] / "buddha"
        package.mkdir()
        for name in self.runner_names:
            shutil.copyfile(self.package / (name + ".py"), package / (name + ".py"))
        (fixture.roots["agent"] / "identity.txt").unlink()
        self.trusted_seed = self.package.parent / "agents/frozen_seed.py"
        self.seed = fixture.roots["agent"] / "frozen_seed.py"
        self.seed.write_bytes(self.trusted_seed.read_bytes())
        rows = [
            {"qid": 1, "question": "one literal digit, numeric row", "category": "control"},
            {
                "qid": "1",
                "question": "one literal digit, text row",
                "nested": {"keep": [None, False]},
            },
            {"qid": "private", "question": "UNSELECTED_SOURCE_SENTINEL", "secret": "PRIVATE_ROW"},
        ]
        self.dataset = b"".join(_json(row) + b"\n" for row in rows)
        (fixture.roots["official"] / "data/tasks.jsonl").write_bytes(self.dataset)
        fixture.release_record["source"] = inventory(fixture.roots["official"])
        fixture.release_record["task"].update(
            id_field="qid", prompt_field="question", answers_field="responses", count=2
        )
        self.tasks_path = fixture.root / "tasks.json"
        self.descriptor = fixture.root / "generation.json"
        self.config = {
            "provider": "openai",
            "model": "test-model",
            "max_output_tokens": 100,
            "instructions": "Retain literal requirements.",
            "sampling": "regenerate",
        }
        self.record = {
            "format": "buddha.frozen-generation.v1",
            "tasks": str(self.tasks_path),
            "config": self.config,
            "entrypoint": "frozen_seed.py",
            "executor": {
                "image_id": "sha256:" + "a" * 64,
                "role": "agent",
                "mounts": [
                    ["/agent", str(fixture.roots["agent"])],
                    ["/runner", str(fixture.roots["runner"])],
                ],
                "runner_entrypoint": "buddha/agent_worker.py",
                "image_environment": [["PATH", "/opt/venv/bin:/usr/local/bin:/usr/bin:/bin"]],
                "limits": asdict(Limits()),
                "docker_endpoint": "unix:///var/run/docker.sock",
            },
            "profile": {"capability": fixtures.CAPABILITY, "profile_id": "primary"},
        }
        self.preparations = 0
        self.initials = []
        self.configure_tasks()
        self.freeze()

    def configure_tasks(self, count=2):
        self.fixture.release_record["task"]["count"] = count
        self.release = Release.from_record(self.fixture.release_record)
        self.tasks = TaskSet.from_dataset(self.release, self.dataset).select(["1", 1])
        self.tasks_path.write_bytes(self.tasks.to_bytes())

    def configure_anthropic(self):
        fixture = self.fixture
        self.config.update(provider="anthropic", sampling="in-context")
        capability = "anthropic.messages.v1"
        self.record["profile"]["capability"] = capability
        fixture.release_record["requires"] = [capability]
        fixture.profiles["profiles"]["primary"]["spec"] = asdict(
            replace(fixture.spec, provider="anthropic")
        )
        fixture.profiles["profiles"]["primary"]["request_tiers"] += ["standard_only"]
        fixture.write("host", "profiles/openai.json", json.dumps(fixture.profiles))
        fixture.review["credential_sha256"]["anthropic"] = sha(fixtures.KEY.encode())
        self.configure_tasks()
        self.freeze()

    def freeze(self, *, omit=(), **changes):
        fixture = self.fixture
        self.descriptor.write_bytes(_json(self.record))
        fixture.selection = prepare_selection(
            self.release,
            fixture.roots,
            capabilities={self.record["profile"]["capability"]: "profiles/openai.json"},
        )
        self.preparations += 1
        bound = [
            self.descriptor,
            self.tasks_path,
            self.trusted_seed,
            *[self.package / (name + ".py") for name in self.host_names],
        ]
        self.directory = fixture.prepare(
            "generation-" + str(self.preparations),
            input_files=[path for path in bound if path not in omit],
            **changes,
        )
        self.gateway = fixture.gateway(directory=self.directory)
        self.output = fixture.root / ("output-" + str(self.preparations))

    def session(self, *, output=None):
        result = AgentSession(
            self.gateway, descriptor=self.descriptor, output=output or self.output
        )
        self.addCleanup(result.close)
        return result

    def ready(self, task=None):
        return {
            "type": "ready",
            "agent_sha256": self.fixture.selection.agent_sha256,
            "task_sha256": sha(_json(task or self.tasks.tasks[0].to_record())),
        }

    def request(self, sequence=0, *, task=None, previous=(), **changes):
        body = frozen_seed.request(self.config, task or self.tasks.tasks[0].to_record(), previous)
        return {
            "type": "request",
            "sequence": sequence,
            "provider": self.config["provider"],
            "body_base64": base64.b64encode(body).decode(),
        } | changes

    def done(self, answers, *, status="complete", reason="complete"):
        return {"type": "done", "status": status, "reason": reason, "answers": answers}

    def response(self, text="poor answer", *, finish="stop", refusal=None, **changes):
        if self.config["provider"] == "openai":
            raw = {
                "model": "test-model",
                "service_tier": "default",
                "choices": [
                    {"message": {"content": text, "refusal": refusal}, "finish_reason": finish}
                ],
                "usage": {"prompt_tokens": 5, "completion_tokens": 3},
            }
        else:
            raw = {
                "model": "test-model",
                "content": [{"type": "text", "text": text}],
                "stop_reason": finish if finish != "stop" else "end_turn",
                "usage": {"input_tokens": 5, "output_tokens": 3},
            }
        return raw | changes

    def connection(self, raw=None, *, timeout=False):
        response = self.fixture.response()
        response.read.return_value = _json(raw if raw is not None else self.response())
        response.getheaders.return_value = [
            (
                "x-request-id" if self.config["provider"] == "openai" else "request-id",
                "generation-fixture",
            )
        ]
        connection = self.fixture.connection(response)
        if timeout:
            connection.getresponse.side_effect = TimeoutError("synthetic timeout")
        return connection

    def send(self, session, frame=None, *, raw=None, timeout=False):
        connection = self.connection(raw, timeout=timeout)
        key = "OPENAI_API_KEY" if self.config["provider"] == "openai" else "ANTHROPIC_API_KEY"
        with (
            patch.dict(os.environ, {key: fixtures.KEY}, clear=True),
            patch("http.client.HTTPSConnection", return_value=connection),
        ):
            result = session.handle(frame or self.request())
        return result, connection

    def execution(self, *, exit_code=0, cleanup="removed"):
        return ExecutionResult(
            exit_code,
            "f" * 64,
            "sha256:" + "a" * 64,
            0,
            0,
            sha(b""),
            1,
            0.01,
            _json({"fixture": "portable mock executor"}),
            cleanup,
        )

    def run_worker(
        self, session, *, raw_values=None, stop_after_task=None, exit_code=0, cleanup="removed"
    ):
        values = iter(raw_values or [])

        def execute(spec, *, initial, handle, limits, docker_endpoint):
            self.initials.append(copy.deepcopy(initial))
            self.assertEqual(spec.role, "agent")
            self.assertEqual({target for target, _ in spec.mounts}, {"/agent", "/runner"})
            self.assertEqual(spec.runner_entrypoint, "buddha/agent_worker.py")
            self.assertEqual(
                set(initial),
                {
                    "type",
                    "format",
                    "roots",
                    "inventories",
                    "entrypoint",
                    "agent_sha256",
                    "config",
                    "task",
                    "task_index",
                },
            )
            self.assertEqual(initial["format"], "buddha.agent-worker.v1")
            self.assertEqual(initial["roots"], {"agent": "/agent", "runner": "/runner"})
            self.assertEqual(set(initial["inventories"]), {"agent", "runner"})
            self.assertEqual(initial["task"], self.tasks.tasks[initial["task_index"]].to_record())
            self.assertNotIn(b"UNSELECTED_SOURCE_SENTINEL", _json(initial))
            self.assertNotIn(b"dataset_base64", _json(initial))
            self.assertIsNone(handle(self.ready(initial["task"])))
            answers = []
            for sequence in range(initial["task"]["count"]):
                connection = self.connection(next(values, self.response()))
                with patch("http.client.HTTPSConnection", return_value=connection):
                    reply = handle(self.request(sequence, task=initial["task"], previous=answers))
                if reply["type"] == "stop":
                    handle(self.done(answers, status="stopped", reason=reply["reason"]))
                    return self.execution()
                self.assertEqual(reply["sequence"], sequence)
                try:
                    raw = json.loads(base64.b64decode(reply["envelope"]["body_base64"]))
                    answers.append(frozen_seed.normalize(self.config["provider"], raw))
                except (ValueError, KeyError):
                    handle(self.done(answers, status="failed", reason="agent_error"))
                    return self.execution()
            handle(
                self.done([], status="failed", reason="agent_error")
                if stop_after_task == initial["task_index"]
                else self.done(answers)
            )
            last = initial["task_index"] == len(self.tasks.tasks) - 1
            return self.execution(
                exit_code=exit_code if last else 0, cleanup=cleanup if last else "removed"
            )

        key = "OPENAI_API_KEY" if self.config["provider"] == "openai" else "ANTHROPIC_API_KEY"
        with (
            patch.dict(os.environ, {key: fixtures.KEY}, clear=True),
            patch("buddha.agent_run.executor.run_container", side_effect=execute),
        ):
            return session.run()

    def test_real_source_bindings_are_required_before_output_or_dispatch(self):
        self.assertTrue(issubclass(AgentRunError, ReleaseError))
        for path in [
            self.descriptor,
            self.tasks_path,
            *[self.package / (name + ".py") for name in self.host_names],
        ]:
            with self.subTest(missing=path.name):
                self.freeze(omit=(path,))
                with self.assertRaises(AgentRunError):
                    self.session()
                self.assertFalse(self.output.exists())
        self.assertEqual(self.fixture.authority.summary()["operation_count"], 0)

    def test_descriptor_task_and_selected_source_drift_fail_before_dispatch(self):
        for path in [
            self.descriptor,
            self.tasks_path,
            self.seed,
            self.fixture.roots["runner"] / "buddha/channel.py",
        ]:
            before = path.read_bytes()
            try:
                path.write_bytes(before + b"changed")
                with self.subTest(path=path.name), self.assertRaises(AgentRunError):
                    self.session()
            finally:
                path.write_bytes(before)
        self.assertEqual(self.fixture.authority.summary()["operation_count"], 0)

    def test_taskset_from_another_release_is_rejected_even_when_bound(self):
        changed = self.fixture.release_record | {"release": "different"}
        tasks = TaskSet.from_dataset(Release.from_record(changed), self.dataset).select(["1", 1])
        self.tasks_path.write_bytes(tasks.to_bytes())
        self.freeze()
        with self.assertRaises(AgentRunError):
            self.session()

    def test_missing_actual_reviewed_seed_binding_rejects_known_selected_copy(self):
        self.freeze(omit=(self.trusted_seed,))
        with self.assertRaises(AgentRunError):
            self.session()
        self.assertFalse(self.output.exists())
        self.assertEqual(self.fixture.authority.summary()["operation_count"], 0)

    def test_reselected_valid_alternate_seed_or_extra_data_is_outside_frozen_scope(self):
        original = self.seed.read_bytes()
        extra = self.fixture.roots["agent"] / "final-data.txt"
        for variant in ("alternate_seed", "extra_data"):
            if variant == "alternate_seed":
                # Still valid Python with the complete seed interface, but a new treatment.
                self.seed.write_bytes(original + b"\n# alternate valid source\n")
            else:
                extra.write_bytes(b"FINAL_DATA_SENTINEL")
            self.freeze()
            with self.subTest(variant=variant):
                with self.assertRaises(AgentRunError):
                    self.session()
                self.assertFalse(self.output.exists())
            self.seed.write_bytes(original)
            if extra.exists():
                extra.unlink()
        self.assertEqual(self.fixture.authority.summary()["operation_count"], 0)

    def test_descriptor_rejects_role_mount_profile_entrypoint_and_config_changes(self):
        original = copy.deepcopy(self.record)
        changes = [
            lambda r: r.update(extra=True),
            lambda r: r.update(entrypoint="other.py"),
            lambda r: r["executor"].update(role="evaluator"),
            lambda r: r["executor"].update(runner_entrypoint="buddha/channel.py"),
            lambda r: r["executor"]["mounts"].append(
                ["/official", str(self.fixture.roots["official"])]
            ),
            lambda r: r["profile"].update(profile_id="unreviewed"),
            lambda r: r["config"].update(provider="anthropic"),
            lambda r: r["config"].update(model="unreviewed"),
            lambda r: r["config"].update(max_output_tokens=101),
            lambda r: r["config"].update(sampling="unsupported"),
        ]
        for index, change in enumerate(changes):
            self.record = copy.deepcopy(original)
            change(self.record)
            self.freeze()
            with self.subTest(boundary=index), self.assertRaises(AgentRunError):
                self.session()
        self.assertEqual(self.fixture.authority.summary()["operation_count"], 0)

    def test_selected_code_rejects_bytecode_and_changed_installed_runner_copy(self):
        path = self.fixture.roots["runner"] / "buddha/agent_worker.py"
        before = path.read_bytes()
        for variant in ("runner", "bytecode"):
            with self.subTest(variant=variant):
                extra = self.fixture.roots["agent"] / "__pycache__/frozen_seed.cpython-313.pyc"
                if variant == "runner":
                    path.write_bytes(before + b"\n# not installed worker\n")
                else:
                    extra.parent.mkdir()
                    extra.write_bytes(b"executable cache")
                self.freeze()
                with self.assertRaises(AgentRunError):
                    self.session()
                path.write_bytes(before)
                if extra.exists():
                    extra.unlink()
                    extra.parent.rmdir()

    def test_ready_correlates_exact_task_and_agent_and_is_required_once(self):
        for frame in (
            self.request(),
            self.done([]),
            self.ready() | {"agent_sha256": "0" * 64},
            self.ready() | {"task_sha256": "0" * 64},
        ):
            self.freeze()
            with self.subTest(frame=frame), self.assertRaises(AgentRunError):
                self.session().handle(frame)
        self.freeze()
        session = self.session()
        self.assertIsNone(session.handle(self.ready()))
        with self.assertRaises(AgentRunError):
            session.handle(self.ready())

    def test_request_shape_sequence_role_model_and_cap_are_checked_before_gateway(self):
        variants = [
            self.request(1),
            self.request(True),
            self.request(-1),
            self.request(provider="anthropic"),
            self.request(headers=[]),
            self.request(url="https://example.org"),
            self.request(logical_id="chosen"),
            self.request(body_base64="not-base64"),
        ]
        for change in ({"model": "unreviewed"}, {"max_completion_tokens": 101}):
            body = (
                json.loads(frozen_seed.request(self.config, self.tasks.tasks[0].to_record()))
                | change
            )
            variants.append(self.request(body_base64=base64.b64encode(_json(body)).decode()))
        for frame in variants:
            self.freeze()
            session = self.session()
            session.handle(self.ready())
            with (
                self.subTest(frame=frame),
                patch.object(
                    self.gateway,
                    "execute",
                    side_effect=AssertionError("invalid request dispatched"),
                ),
                self.assertRaises(AgentRunError),
            ):
                session.handle(frame)
        self.assertEqual(self.fixture.authority.summary()["operation_count"], 0)

    def test_host_assigns_stable_identity_attempt_zero_and_preserves_raw_reply(self):
        session = self.session()
        session.handle(self.ready())
        original, observed = self.gateway.execute, []

        def execute(call):
            observed.append(call)
            return original(call)

        with patch.object(self.gateway, "execute", side_effect=execute):
            reply, _ = self.send(session, raw=self.response(" literal \n", finish="length"))
        expected = sha(
            _json(
                [
                    "buddha.seed-call.v1",
                    self.fixture.selection.agent_sha256,
                    sha(_json(self.config)),
                    0,
                    self.tasks.tasks[0].to_record(),
                    0,
                ]
            )
        )
        self.assertEqual((observed[0].logical_id, observed[0].attempt), (expected, 0))
        self.assertEqual(
            observed[0].body, frozen_seed.request(self.config, self.tasks.tasks[0].to_record())
        )
        self.assertEqual(observed[0].headers, ())
        raw = json.loads(base64.b64decode(reply["envelope"]["body_base64"]))
        self.assertEqual(raw["choices"][0]["message"]["content"], " literal \n")
        self.assertEqual(raw["choices"][0]["finish_reason"], "length")
        self.assertEqual(self.gateway.ledger.totals()["spent_microusd"], 11)

    def test_completed_replay_reuses_owner_without_keys_charge_or_active_authority(self):
        session = self.session()
        session.handle(self.ready())
        first, _ = self.send(session)
        before = self.gateway.ledger.totals()
        self.fixture.authority.deactivate(self.directory.name, "finished synthetic prefix")
        replay = self.session(output=self.fixture.root / "fresh-replay")
        replay.handle(self.ready())
        with (
            patch.dict(os.environ, {}, clear=True),
            patch(
                "http.client.HTTPSConnection",
                side_effect=AssertionError("cached reply tried HTTPS"),
            ),
        ):
            self.assertEqual(replay.handle(self.request()), first)
        self.assertEqual(self.gateway.ledger.totals(), before)

    def assert_unknown_stop(self, *, timeout=False):
        session = self.session()
        session.handle(self.ready())
        raw = self.response()
        raw.pop("usage")
        reply, connection = self.send(session, raw=raw, timeout=timeout)
        self.assertEqual(reply, {"type": "stop", "sequence": 0, "reason": "unknown"})
        connection.request.assert_called_once()
        totals = self.gateway.ledger.totals()
        self.assertEqual(totals["spent_microusd"], 0)
        self.assertGreater(totals["reserved_microusd"], 0)
        with patch.object(
            self.gateway, "execute", side_effect=AssertionError("stop failed to latch")
        ):
            self.assertEqual(
                session.handle(self.request(1)),
                {"type": "stop", "sequence": 1, "reason": "unknown"},
            )
        self.assertEqual(self.gateway.ledger.totals(), totals)

    def test_unknown_receipt_holds_one_attempt_and_latches_stop(self):
        self.assert_unknown_stop()

    def test_timeout_holds_one_attempt_and_latches_stop(self):
        self.assert_unknown_stop(timeout=True)

    def test_authority_refusal_happens_before_credentials_or_https(self):
        self.freeze(budget_microusd=1)
        session = self.session()
        session.handle(self.ready())
        with (
            patch.dict(os.environ, {}, clear=True),
            patch("http.client.HTTPSConnection") as network,
        ):
            reply = session.handle(self.request())
        self.assertEqual(reply, {"type": "stop", "sequence": 0, "reason": "authority"})
        network.assert_not_called()
        self.assertEqual(self.gateway.ledger.totals()["operation_count"], 0)

    def test_no_answers_before_every_task_and_reply_is_complete(self):
        session = self.session()
        session.handle(self.ready())
        with self.assertRaises(AgentRunError):
            session.handle(self.done(["invented", "invented"]))
        self.assertFalse((self.output / "answers.json").exists())

    def test_excess_request_after_exact_task_count_cannot_dispatch(self):
        session = self.session()
        session.handle(self.ready())
        self.send(session, self.request(0))
        self.send(session, self.request(1))
        before = self.gateway.ledger.totals()
        with patch.object(
            self.gateway, "execute", side_effect=AssertionError("excess call dispatched")
        ):
            with self.assertRaises(AgentRunError):
                session.handle(self.request(2))
        self.assertEqual(self.gateway.ledger.totals(), before)

    def test_done_checks_outer_count_and_literal_utf8_after_billing(self):
        for values in (["short"], ["one", "two", "extra"], ["one", None], ["one", "\ud800"]):
            self.freeze()
            session = self.session()
            session.handle(self.ready())
            self.send(session, self.request(0))
            self.send(session, self.request(1))
            with self.subTest(values=values), self.assertRaises(AgentRunError):
                session.handle(self.done(values))
            self.assertFalse((self.output / "answers.json").exists())
            self.assertEqual(self.gateway.ledger.totals()["spent_microusd"], 22)

    def test_configuration_and_task_mutation_after_ready_fail_before_spend(self):
        for attribute in ("config", "tasks"):
            self.freeze()
            session = self.session()
            session.handle(self.ready())
            if attribute == "config":
                session.config["instructions"] = "silently changed"
            else:
                session.tasks = self.tasks.select([1])
            with patch("http.client.HTTPSConnection") as network:
                with self.subTest(attribute=attribute), self.assertRaises(AgentRunError):
                    session.handle(self.request())
            network.assert_not_called()
            self.assertEqual(self.gateway.ledger.totals()["operation_count"], 0)

    def test_two_answers_preserve_typed_order_metadata_and_weak_literal_content(self):
        raw = [
            self.response("duplicate"),
            self.response(" \n"),
            self.response(None, refusal="declined"),
            self.response(" malformed JSON {", finish="length"),
        ]
        report = self.run_worker(self.session(), raw_values=raw)
        self.assertEqual(report["format"], "buddha.generation-report.v1")
        self.assertEqual(report["status"], "complete")
        self.assertEqual((report["completed_tasks"], report["expected_tasks"]), (2, 2))
        self.assertEqual(report["calls"], {"requested": 4, "completed": 4, "stopped": 0})
        answers = Answers.from_bytes((self.output / "answers.json").read_bytes())
        self.assertEqual(answers.to_record()["agent_sha256"], self.fixture.selection.agent_sha256)
        self.assertEqual(answers.to_record()["metadata"], {})
        rows = [json.loads(line) for line in answers.native_bytes().splitlines()]
        self.assertEqual([row["qid"] for row in rows], ["1", 1])
        self.assertEqual(rows[0]["responses"], ["duplicate", "[empty]"])
        self.assertEqual(rows[1]["responses"], ["[refused]", " malformed JSON {"])
        self.assertEqual(rows[0]["nested"], {"keep": [None, False]})
        self.assertEqual(rows[1]["category"], "control")
        self.assertNotIn(b"UNSELECTED_SOURCE_SENTINEL", _json(self.initials))
        self.assertEqual(report["gateway_totals"]["operation_count"], 4)

    def test_count_ten_comes_from_tasks_without_benchmark_assumptions(self):
        self.configure_tasks(10)
        self.freeze()
        report = self.run_worker(self.session())
        self.assertEqual(report["status"], "complete")
        self.assertEqual(report["calls"]["completed"], 20)
        answers = Answers.from_bytes((self.output / "answers.json").read_bytes())
        self.assertEqual([len(row["answers"]) for row in answers.to_record()["outputs"]], [10, 10])

    def test_anthropic_in_context_retains_empty_refused_and_truncated_text(self):
        self.configure_anthropic()
        values = [
            self.response("same"),
            self.response(" "),
            self.response("ignored", finish="refusal"),
            self.response(" partial ", finish="max_tokens"),
        ]
        report = self.run_worker(self.session(), raw_values=values)
        self.assertEqual(report["status"], "complete")
        answers = Answers.from_bytes((self.output / "answers.json").read_bytes())
        self.assertEqual(
            [row["answers"] for row in answers.to_record()["outputs"]],
            [["same", "[empty]"], ["[refused]", " partial "]],
        )

    def test_partial_failure_preserves_finished_tasks_without_complete_answers(self):
        report = self.run_worker(self.session(), stop_after_task=1)
        self.assertEqual(report["status"], "failed")
        self.assertEqual(report["completed_tasks"], 1)
        self.assertFalse((self.output / "answers.json").exists())
        rows = [
            json.loads(line) for line in (self.output / "partial.jsonl").read_bytes().splitlines()
        ]
        self.assertEqual(rows, [{"task_id": "1", "answers": ["poor answer", "poor answer"]}])
        self.assertEqual(self.gateway.ledger.totals()["operation_count"], 4)

    def test_malformed_seed_reply_is_billed_but_generation_fails(self):
        report = self.run_worker(self.session(), raw_values=[self.response(choices=[])])
        self.assertEqual(report["status"], "failed")
        self.assertFalse((self.output / "answers.json").exists())
        self.assertEqual(self.gateway.ledger.totals()["spent_microusd"], 11)
        self.assertEqual(self.gateway.ledger.totals()["reserved_microusd"], 0)

    def test_failed_container_cannot_publish_complete_answers(self):
        report = self.run_worker(self.session(), exit_code=1)
        self.assertEqual(report["status"], "failed")
        self.assertEqual(report["completed_tasks"], 2)
        self.assertFalse((self.output / "answers.json").exists())

    def test_unknown_cleanup_cannot_publish_complete_answers(self):
        report = self.run_worker(self.session(), cleanup="unknown")
        self.assertEqual(report["status"], "failed")
        self.assertFalse((self.output / "answers.json").exists())

    def test_missing_done_cannot_publish_complete_answers(self):
        with patch("buddha.agent_run.executor.run_container", return_value=self.execution()):
            report = self.session().run()
        self.assertEqual(report["status"], "failed")
        self.assertFalse((self.output / "answers.json").exists())

    def test_existing_output_directory_is_preserved(self):
        self.output.mkdir()
        marker = self.output / "keep.txt"
        marker.write_bytes(b"existing result")
        with self.assertRaises(AgentRunError):
            self.session()
        self.assertEqual(marker.read_bytes(), b"existing result")


if __name__ == "__main__":
    unittest.main()
