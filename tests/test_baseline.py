"""Composed baseline ownership and artifact handoffs with mocked container execution."""

import base64
import copy
import hashlib
import json
import os
import shutil
import unittest
from pathlib import Path
from unittest.mock import patch

import test_agent_run as agent_fixtures
import test_gateway as gateway_fixtures

from agents import frozen_seed
from buddha import baseline as baseline_module
from buddha.answers import Answers
from buddha.authorization import Authorization
from buddha.baseline import BaselineError, prepare_baseline, run_baseline
from buddha.executor import ExecutorError
from buddha.gateway import RawHTTPTransport
from buddha.ledger import OperationConflict
from buddha.native_run import CHUNK_BYTES
from buddha.releases import ReleaseError, _json, inventory, prepare_selection


def sha(raw):
    return hashlib.sha256(raw).hexdigest()


class BaselineTests(unittest.TestCase):
    def setUp(self):
        self.agent = agent = agent_fixtures.AgentSessionTests("runTest")
        agent.setUp()
        self.addCleanup(agent.doCleanups)
        self.fixture = fixture = agent.fixture
        self.root = fixture.root.resolve()
        self.authority = Authorization.create(
            self.root / "baseline-authorization.sqlite3",
            authorization_id="baseline-synthetic-scope",
            budget_microusd=100_000,
            max_calls=100,
            scope="composed portable baseline checks; no real provider calls",
        )
        modules = ["src.partition", "src.score", "src.summarize"]
        for module in modules:
            fixture.write("official", module.replace(".", "/") + ".py", "def main():\n    pass\n")
        fixture.release_record["source"] = inventory(fixture.roots["official"])
        fixture.release_record["commands"] = [
            {"module": module, "argv": ["{artifacts}"]} for module in modules
        ]
        fixture.release_record["artifacts"] = {
            "answers": "generations.jsonl",
            "results": ["partitions.jsonl", "scores.jsonl"],
            "summary": "summary.json",
        }
        agent.config.update(instructions="", sampling="regenerate")
        agent.configure_tasks()
        agent.descriptor.write_bytes(_json(agent.record))
        self.generation_roots = dict(fixture.roots)
        self.native_roots = dict(fixture.roots) | {"runner": self.root / "native-runner"}
        package = self.native_roots["runner"] / "buddha"
        package.mkdir(parents=True)
        for name in (
            "__init__",
            "channel",
            "native_worker",
            "native_context",
            "native_transport",
            "releases",
            "wire",
        ):
            shutil.copyfile(agent.package / (name + ".py"), package / (name + ".py"))
        selections = [
            prepare_selection(
                agent.release,
                roots,
                capabilities={gateway_fixtures.CAPABILITY: "profiles/openai.json"},
            )
            for roots in (self.generation_roots, self.native_roots)
        ]
        self.agent_selection = selections[0]
        executor = copy.deepcopy(agent.record["executor"])
        executor.pop("mounts")
        executor.update(role="evaluator", runner_entrypoint="buddha/native_worker.py")
        self.record = {
            "format": "buddha.native-baseline.v1",
            "tasks": str(agent.tasks_path),
            "generation": {
                "selection": selections[0].to_record(),
                "roots": {name: str(path) for name, path in self.generation_roots.items()},
                "descriptor": str(agent.descriptor),
                "budget_microusd": 10_000,
                "max_calls": 20,
            },
            "native": {
                "selection": selections[1].to_record(),
                "roots": {name: str(path) for name, path in self.native_roots.items()},
                "environment": {
                    "helper_sha256": "d" * 64,
                    "manifest_sha256": "e" * 64,
                    "inventory": {
                        "lib/python3.13/site-packages/fixture.py": {"sha256": "f" * 64, "bytes": 1}
                    },
                },
                "hooks": {"modules": modules, "cache": None, "calls": [], "sdk": []},
                "executor": executor,
                "profiles": {"openai": {"test-model": "primary"}},
                "budget_microusd": 10_000,
                "max_calls": 20,
            },
            "stages": [
                {
                    "inputs": ["generations.jsonl"],
                    "outputs": [{"path": "partitions.jsonl", "id_field": "qid"}],
                    "allow_model": True,
                },
                {
                    "inputs": ["partitions.jsonl"],
                    "outputs": [{"path": "scores.jsonl", "id_field": "qid"}],
                    "allow_model": True,
                },
                {
                    "inputs": ["scores.jsonl"],
                    "outputs": [{"path": "summary.json", "id_field": None}],
                    "allow_model": False,
                },
            ],
        }
        self.descriptor = self.root / "baseline.json"
        self.directory = self.root / "baseline"
        self.events, self.physical_sends = [], 0
        self.fail_generation_once = self.fail_native_once = self.timeout_native_once = False
        self.halt_native_once = False
        self.summary_attack = False
        self.override_outputs = None
        self.summary_bytes = b'{"utility":NaN,"literal":"  unchanged  "}\n'

    def prepare(self, directory=None):
        self.descriptor.write_bytes(_json(self.record))
        return prepare_baseline(
            directory or self.directory,
            descriptor=self.descriptor,
            authorization=self.authority,
            review=self.fixture.review,
        )

    def manifest(self, index):
        return json.loads((self.directory / f"owners/{index}/manifest.json").read_bytes())

    def owner_state(self, index):
        run_id = self.manifest(index)["run_id"]
        return next(row for row in self.authority.summary()["runs"] if row["run_id"] == run_id)

    def exchange(self, handle, frame, *, timeout=False):
        connection = self.agent.connection(timeout=timeout)
        with patch("http.client.HTTPSConnection", return_value=connection):
            response = handle(frame)
        self.physical_sends += connection.request.call_count
        return response

    def execute(self, spec, *, initial, handle, **kwargs):
        try:
            return self.execute_worker(spec, initial=initial, handle=handle, **kwargs)
        except ReleaseError:
            # The real executor owns cleanup when the host rejects a worker frame.
            raise ExecutorError(
                "protocol", cleanup_status="removed", container_id="f" * 64
            ) from None

    def execute_worker(self, spec, *, initial, handle, **kwargs):
        session = handle.__self__
        self.events.append(
            {"role": spec.role, "initial": copy.deepcopy(initial), "session": session}
        )
        if spec.role == "agent":
            self.assertEqual({target for target, _ in spec.mounts}, {"/agent", "/runner"})
            self.assertNotIn(b"UNSELECTED_SOURCE_SENTINEL", _json(initial))
            handle(
                {
                    "type": "ready",
                    "agent_sha256": self.agent_selection.agent_sha256,
                    "task_sha256": sha(_json(initial["task"])),
                }
            )
            answers = []
            for index in range(initial["task"]["count"]):
                response = self.exchange(
                    handle,
                    {
                        "type": "request",
                        "sequence": index,
                        "provider": "openai",
                        "body_base64": base64.b64encode(
                            frozen_seed.request(self.agent.config, initial["task"], answers)
                        ).decode(),
                    },
                )
                if response["type"] == "stop":
                    handle(self.agent.done([], status="stopped", reason=response["reason"]))
                    return self.agent.execution()
                raw = json.loads(base64.b64decode(response["envelope"]["body_base64"]))
                answers.append(frozen_seed.normalize("openai", raw))
                if self.fail_generation_once and initial["task_index"] == 1:
                    self.fail_generation_once = False
                    handle(self.agent.done([], status="failed", reason="agent_error"))
                    return self.agent.execution()
            handle(self.agent.done(answers))
            return self.agent.execution()

        index = initial["command"]["index"]
        inputs = dict(spec.mounts)["/inputs"]
        self.events[-1]["inputs"] = inputs
        self.assertEqual(set(inventory(inputs)), {item["source"] for item in initial["inputs"]})
        for item in initial["inputs"]:
            self.assertEqual(sha((inputs / item["source"]).read_bytes()), item["sha256"])
        self.assertEqual(
            [item["destination"] for item in initial["inputs"]],
            self.record["stages"][index]["inputs"],
        )
        if self.halt_native_once:
            self.halt_native_once = False
            return self.agent.execution(exit_code=1)
        audit = {
            module: {
                "kind": "official",
                "path": "/official/" + module.replace(".", "/") + ".py",
                "sha256": initial["inventories"]["official"][module.replace(".", "/") + ".py"],
            }
            for module in initial["hooks"]["modules"]
        }
        handle({"type": "ready", "aliases": [], "audit": audit})
        if index < 2 or self.summary_attack:
            if index == 2:
                self.assertEqual(session.profiles, {})
                self.assertFalse(session.gateway.transport.allow_paid)
                no_execute = patch.object(
                    session.gateway, "execute", side_effect=AssertionError("summary dispatched")
                )
            else:
                no_execute = patch.object(session.gateway, "execute", wraps=session.gateway.execute)
            with no_execute:
                response = self.exchange(
                    handle,
                    {
                        "type": "request",
                        "seq": 0,
                        "request": {
                            "provider": "openai",
                            "method": "POST",
                            "url": "https://api.openai.com/v1/chat/completions",
                            "body_base64": base64.b64encode(self.fixture.body).decode(),
                            "headers": [],
                            "logical_id": sha(_json(["baseline-fixture", index])),
                            "attempt": 0,
                        },
                    },
                    timeout=self.timeout_native_once,
                )
            self.timeout_native_once = False
            if response["type"] == "stop":
                handle(
                    {
                        "type": "done",
                        "status": "stopped",
                        "reason": response["reason"],
                        "audit": audit,
                    }
                )
                return self.agent.execution()
            if self.fail_native_once:
                self.fail_native_once = False
                handle(
                    {"type": "done", "status": "failed", "reason": "native_error", "audit": audit}
                )
                return self.agent.execution()
        else:
            self.assertEqual(session.profiles, {})
            self.assertFalse(session.gateway.transport.allow_paid)
        rows = [
            json.loads(line)
            for line in (inputs / initial["inputs"][0]["source"]).read_bytes().splitlines()
        ]
        if index < 2:
            for row in rows:
                row["partition" if index == 0 else "score"] = [0, 1] if index == 0 else 7.0
            outputs = {
                "partitions.jsonl" if index == 0 else "scores.jsonl": b"".join(
                    _json(row) + b"\n" for row in rows
                )
            }
        else:
            outputs = {"summary.json": self.summary_bytes}
        if self.override_outputs is not None and index == 0:
            outputs = self.override_outputs
        for name, body in outputs.items():
            for offset in range(0, max(1, len(body)), CHUNK_BYTES):
                chunk = body[offset : offset + CHUNK_BYTES]
                handle(
                    {
                        "type": "file",
                        "path": name,
                        "offset": offset,
                        "eof": offset + CHUNK_BYTES >= len(body),
                        "data_base64": base64.b64encode(chunk).decode(),
                    }
                )
        handle({"type": "done", "status": "complete", "reason": "complete", "audit": audit})
        return self.agent.execution()

    def run_pipeline(self, *, paid=True, directory=None):
        with (
            patch.dict(
                os.environ, {"OPENAI_API_KEY": gateway_fixtures.KEY} if paid else {}, clear=True
            ),
            patch("buddha.executor.run_container", side_effect=self.execute),
        ):
            return run_baseline(
                directory or self.directory, transport=RawHTTPTransport(allow_paid=paid)
            )

    def test_prepare_binds_only_first_owner_without_keys_calls_or_replacing_existing_data(self):
        with (
            patch.dict(os.environ, {}, clear=True),
            patch("http.client.HTTPSConnection") as connection,
        ):
            self.assertEqual(self.prepare(), self.directory)
        connection.assert_not_called()
        self.assertEqual(self.authority.summary()["operation_count"], 0)
        self.assertEqual(len(self.authority.summary()["runs"]), 1)
        self.assertFalse((self.directory / "owners/1").exists())
        bound = {item["path"] for item in self.manifest(0)["invocation"]["inputs"]}
        self.assertTrue(
            {
                str(self.descriptor),
                str(self.agent.tasks_path),
                str(self.agent.descriptor),
                str(self.agent.package / "baseline.py"),
            }
            <= bound
        )
        before = (self.directory / "owners/0/manifest.json").read_bytes()
        with self.assertRaises(BaselineError):
            self.prepare()
        self.assertEqual((self.directory / "owners/0/manifest.json").read_bytes(), before)

    def test_additional_control_inputs_are_bound_to_every_generation_and_native_owner(self):
        control = self.root / "external-study-control.json"
        control.write_bytes(b'{"frozen":"study-control"}')
        self.descriptor.write_bytes(_json(self.record))
        prepare_baseline(
            self.directory,
            descriptor=self.descriptor,
            authorization=self.authority,
            review=self.fixture.review,
            input_files=(control,),
        )
        self.assertEqual(self.run_pipeline()["status"], "complete")
        expected = {"path": str(control), "sha256": sha(control.read_bytes())}
        for index in range(4):
            with self.subTest(index=index):
                self.assertIn(expected, self.manifest(index)["invocation"]["inputs"])

    def test_completed_report_reuse_survives_other_completed_baseline_on_shared_grant(self):
        self.prepare()
        first = self.run_pipeline()
        stored = (self.directory / "report.json").read_bytes()
        second = self.root / "another-complete-baseline"
        self.prepare(directory=second)
        self.assertEqual(self.run_pipeline(directory=second)["status"], "complete")
        sent = self.physical_sends
        self.assertEqual(self.run_pipeline(paid=False), first)
        self.assertEqual((self.directory / "report.json").read_bytes(), stored)
        self.assertEqual(self.physical_sends, sent)

    def test_changed_external_control_cannot_be_adopted_when_a_later_owner_is_bound(self):
        control = self.root / "external-control-race.json"
        control.write_bytes(b'{"frozen":"original"}')
        self.descriptor.write_bytes(_json(self.record))
        prepare_baseline(
            self.directory,
            descriptor=self.descriptor,
            authorization=self.authority,
            review=self.fixture.review,
            input_files=(control,),
        )
        original_prepare = baseline_module.prepare_gateway

        def change_before_new_binding(directory, **kwargs):
            if directory == self.directory / "owners/1":
                control.write_bytes(b'{"frozen":"changed-between-check-and-binding"}')
            return original_prepare(directory, **kwargs)

        with (
            patch.object(baseline_module, "prepare_gateway", side_effect=change_before_new_binding),
            self.assertRaises(BaselineError),
        ):
            self.run_pipeline()
        self.assertEqual(self.physical_sends, 4)
        self.assertFalse(any(event["role"] == "evaluator" for event in self.events))

    def test_complete_composes_distinct_owners_c1_links_typed_ids_and_literal_summary(self):
        self.prepare()
        report = self.run_pipeline()
        self.assertEqual(
            (report["format"], report["status"]), ("buddha.native-baseline-report.v1", "complete")
        )
        self.assertEqual(len(report["stages"]), 4)
        self.assertEqual(
            [event["role"] for event in self.events],
            ["agent", "agent", "evaluator", "evaluator", "evaluator"],
        )
        self.assertEqual((self.physical_sends, self.authority.summary()["operation_count"]), (6, 6))
        generation = self.events[0]["session"]
        answers_path = generation.output / "answers.json"
        answers = Answers.from_bytes(answers_path.read_bytes())
        self.assertEqual(answers.to_record()["metadata"], {})
        self.assertEqual([row["task_id"] for row in answers.to_record()["outputs"]], ["1", 1])
        first_native = self.events[2]
        source = first_native["initial"]["inputs"][0]["source"]
        self.assertEqual((first_native["inputs"] / source).read_bytes(), answers.native_bytes())
        self.assertNotEqual(sha(answers_path.read_bytes()), answers.fingerprint())
        for event in self.events[2:]:
            self.assertEqual(event["initial"]["answers_sha256"], sha(answers_path.read_bytes()))
        self.assertEqual(Path(report["summary"]["path"]).read_bytes(), self.summary_bytes)
        self.assertEqual(json.loads((self.directory / "report.json").read_bytes()), report)
        owners = [self.manifest(index) for index in range(4)]
        self.assertEqual(len({item["run_id"] for item in owners}), 4)
        self.assertEqual(
            {item["authorization_path"] for item in owners}, {str(self.authority.path)}
        )
        self.assertTrue(all(not self.owner_state(index)["active"] for index in range(4)))
        self.assertEqual(self.owner_state(3)["operation_count"], 0)

    def test_completed_pipeline_reuses_all_stages_without_keys_new_calls_or_execution(self):
        self.prepare()
        expected = self.run_pipeline()
        before = self.authority.summary()
        report_bytes = (self.directory / "report.json").read_bytes()
        with (
            patch.dict(os.environ, {}, clear=True),
            patch(
                "buddha.executor.run_container",
                side_effect=AssertionError("completed stage executed"),
            ),
            patch("http.client.HTTPSConnection", side_effect=AssertionError("cached stage sent")),
        ):
            actual = run_baseline(self.directory, transport=RawHTTPTransport(allow_paid=False))
        self.assertEqual(actual, expected)
        self.assertEqual(self.authority.summary(), before)
        self.assertEqual((self.directory / "report.json").read_bytes(), report_bytes)

    def test_generation_failure_replays_original_owner_receipts_in_a_fresh_attempt(self):
        self.prepare()
        self.fail_generation_once = True
        first = self.run_pipeline()
        self.assertEqual(first["status"], "incomplete")
        owner = (self.directory / "owners/0/manifest.json").read_bytes()
        output = self.events[0]["session"].output
        old_report = (output / "report.json").read_bytes()
        self.assertEqual(self.authority.summary()["operation_count"], 3)
        self.assertTrue(self.owner_state(0)["active"])
        self.assertFalse((self.directory / "owners/1").exists())
        self.assertFalse((self.directory / "report.json").exists())
        self.assertEqual(self.run_pipeline()["status"], "complete")
        self.assertEqual((self.directory / "owners/0/manifest.json").read_bytes(), owner)
        self.assertEqual((output / "report.json").read_bytes(), old_report)
        self.assertNotEqual(self.events[2]["session"].output, output)
        self.assertEqual((self.physical_sends, self.authority.summary()["operation_count"]), (6, 6))

    def test_native_failure_reuses_generation_and_same_native_owner_without_double_billing(self):
        self.prepare()
        self.fail_native_once = True
        self.assertEqual(self.run_pipeline()["status"], "incomplete")
        owner = (self.directory / "owners/1/manifest.json").read_bytes()
        first_output = self.events[-1]["session"].output
        old_report = (first_output / "report.json").read_bytes()
        self.assertTrue(self.owner_state(1)["active"])
        self.assertFalse((self.directory / "owners/2").exists())
        before = len(self.events)
        self.assertEqual(self.run_pipeline()["status"], "complete")
        self.assertTrue(all(event["role"] == "evaluator" for event in self.events[before:]))
        self.assertNotEqual(first_output, self.events[before]["session"].output)
        self.assertEqual((first_output / "report.json").read_bytes(), old_report)
        self.assertEqual((self.directory / "owners/1/manifest.json").read_bytes(), owner)
        self.assertEqual((self.physical_sends, self.authority.summary()["operation_count"]), (6, 6))

    def test_output_population_rejects_missing_duplicate_foreign_and_boolean_ids_before_next_owner(
        self,
    ):
        for index, ids in enumerate([["1"], ["1", "1"], ["1", "foreign"], ["1", True]]):
            directory = self.root / f"bad-population-{index}"
            self.directory = directory
            self.prepare()
            self.override_outputs = {
                "partitions.jsonl": b"".join(_json({"qid": value}) + b"\n" for value in ids)
            }
            before = self.physical_sends
            with self.subTest(ids=ids), self.assertRaises(BaselineError):
                self.run_pipeline()
            self.assertEqual(self.physical_sends - before, 5)
            self.assertFalse((directory / "owners/2").exists())
            self.assertFalse((directory / "report.json").exists())

    def test_missing_declared_artifact_prevents_downstream_owner_or_final_report(self):
        self.prepare()
        self.override_outputs = {}
        with self.assertRaises(BaselineError):
            self.run_pipeline()
        self.assertEqual(self.authority.summary()["operation_count"], 5)
        self.assertFalse((self.directory / "owners/2").exists())
        self.assertFalse((self.directory / "report.json").exists())

    def test_descriptor_tasks_and_selected_source_drift_are_denied_before_spending(self):
        self.prepare()
        for path in [
            self.descriptor,
            self.agent.tasks_path,
            self.fixture.roots["official"] / "src/partition.py",
        ]:
            original = path.read_bytes()
            path.write_bytes(original + b"\n")
            try:
                with self.subTest(path=path), self.assertRaises(BaselineError):
                    self.run_pipeline(paid=False)
            finally:
                path.write_bytes(original)
        self.assertEqual(self.physical_sends, 0)
        self.assertEqual(self.events, [])

    def test_altered_c1_artifact_or_derived_native_bytes_cannot_resume_downstream(self):
        for index, kind in enumerate(("c1", "native")):
            self.directory = self.root / f"bad-link-{index}"
            self.prepare()
            self.halt_native_once = True
            self.assertEqual(self.run_pipeline()["status"], "incomplete")
            first_native = self.events[-1]
            if kind == "c1":
                path = self.events[-3]["session"].output / "answers.json"
                record = json.loads(path.read_bytes())
                record["tasks_sha256"] = "0" * 64
                path.write_bytes(_json(record))
            else:
                path = first_native["inputs"] / first_native["initial"]["inputs"][0]["source"]
                path.write_bytes(path.read_bytes() + b"\n")
            before = self.physical_sends
            with self.subTest(kind=kind), self.assertRaises(BaselineError):
                self.run_pipeline(paid=False)
            self.assertEqual(self.physical_sends, before)
            self.assertFalse((self.directory / "owners/2").exists())

    def test_unknown_native_attempt_retains_shared_hold_and_same_owner_stops_on_resume(self):
        self.prepare()
        self.timeout_native_once = True
        self.assertEqual(self.run_pipeline()["status"], "incomplete")
        before = self.authority.summary()
        self.assertEqual((before["operation_count"], before["reserved_microusd"]), (5, 300))
        owner = (self.directory / "owners/1/manifest.json").read_bytes()
        self.assertEqual(self.run_pipeline(paid=False)["status"], "incomplete")
        after = self.authority.summary()
        for key in ("operation_count", "spent_microusd", "reserved_microusd", "committed_microusd"):
            self.assertEqual(after[key], before[key])
        self.assertEqual((self.directory / "owners/1/manifest.json").read_bytes(), owner)
        self.assertFalse((self.directory / "owners/2").exists())

    def test_shared_call_cap_refuses_sixth_attempt_without_summary_allocation(self):
        self.authority = Authorization.create(
            self.root / "small-authorization.sqlite3",
            authorization_id="small-baseline-scope",
            budget_microusd=10_000,
            max_calls=5,
            scope="five synthetic physical calls only",
        )
        self.record["generation"]["max_calls"] = 4
        self.record["native"]["max_calls"] = 2
        self.prepare()
        self.assertEqual(self.run_pipeline()["status"], "incomplete")
        self.assertEqual((self.physical_sends, self.authority.summary()["operation_count"]), (5, 5))
        self.assertFalse((self.directory / "owners/3").exists())
        self.assertFalse((self.directory / "report.json").exists())

    def test_summary_has_no_model_mapping_and_cannot_reach_gateway_or_https(self):
        self.prepare()
        self.summary_attack = True
        self.assertEqual(self.run_pipeline()["status"], "incomplete")
        self.assertEqual(self.physical_sends, 6)
        self.assertEqual(self.owner_state(3)["operation_count"], 0)
        self.assertFalse((self.directory / "report.json").exists())

    def test_invalid_stage_flows_reject_before_allocation_or_spending(self):
        original = copy.deepcopy(self.record)
        changes = [
            (0, "inputs", ["scores.jsonl"]),
            (0, "outputs", [{"path": "partitions.jsonl", "id_field": None}]),
            (0, "outputs", [{"path": "summary.json", "id_field": None}]),
            (1, "outputs", [{"path": "partitions.jsonl", "id_field": "qid"}]),
            (2, "allow_model", True),
            (0, "allow_model", None),
        ]
        for index, (stage, field, value) in enumerate(changes):
            self.record = copy.deepcopy(original)
            self.record["stages"][stage][field] = value
            with (
                self.subTest(stage=stage, field=field, value=value),
                self.assertRaises(BaselineError),
            ):
                self.prepare(self.root / f"invalid-flow-{index}")
        self.assertEqual(self.authority.summary()["runs"], [])
        self.assertEqual(self.physical_sends, 0)

    def test_foreign_authority_cannot_attach_the_prepared_stage_owner(self):
        self.prepare()
        foreign = Authorization.create(
            self.root / "foreign-authorization.sqlite3",
            authorization_id="different-scope",
            budget_microusd=100_000,
            max_calls=100,
            scope="must not attach another baseline's stage",
        )
        before = self.authority.summary()
        with self.assertRaises(OperationConflict):
            foreign.for_run(self.directory / "owners/0")
        self.assertEqual(self.authority.summary(), before)
        self.assertEqual(foreign.summary()["runs"], [])

    def test_existing_completion_with_still_active_owner_cannot_be_blessed_on_resume(self):
        self.prepare()
        with (
            patch.object(
                Authorization, "deactivate", side_effect=OSError("synthetic interruption")
            ),
            self.assertRaises(BaselineError),
        ):
            self.run_pipeline()
        self.assertTrue((self.directory / "completed/0.json").exists())
        self.assertTrue(self.owner_state(0)["active"])
        before = self.authority.summary()
        with (
            patch(
                "buddha.executor.run_container", side_effect=AssertionError("unanchored stage ran")
            ),
            self.assertRaises(BaselineError),
        ):
            run_baseline(self.directory, transport=RawHTTPTransport(allow_paid=False))
        self.assertEqual(self.authority.summary(), before)
        self.assertFalse((self.directory / "owners/1").exists())
        self.assertFalse((self.directory / "report.json").exists())

    def test_temporary_definition_replacement_cannot_hide_behind_restored_bound_bytes(self):
        self.prepare()
        original = self.descriptor.read_bytes()
        altered = copy.deepcopy(self.record)
        altered["native"]["max_calls"] = 77
        definition = baseline_module._definition
        injected = False

        def consume(path, *args, **kwargs):
            nonlocal injected
            if path == self.descriptor and not injected:
                injected = True
                self.descriptor.write_bytes(_json(altered))
                try:
                    return definition(path, *args, **kwargs)
                finally:
                    self.descriptor.write_bytes(original)
            return definition(path, *args, **kwargs)

        with (
            patch.object(baseline_module, "_definition", side_effect=consume),
            self.assertRaises(BaselineError),
        ):
            self.run_pipeline()
        self.assertTrue(injected)
        self.assertEqual(self.descriptor.read_bytes(), original)
        self.assertEqual(self.physical_sends, 0)
        self.assertFalse((self.directory / "owners/1").exists())

    def test_summary_change_after_deactivation_cannot_receive_a_new_final_digest(self):
        self.prepare()
        deactivate = Authorization.deactivate
        changed = False

        def finish(authority, run_id, reason):
            nonlocal changed
            result = deactivate(authority, run_id, reason)
            if (self.directory / "owners/3/manifest.json").exists() and run_id == self.manifest(3)[
                "run_id"
            ]:
                changed = True
                summary = self.events[-1]["session"].output / "artifacts/summary.json"
                summary.write_bytes(b'{"utility":999,"changed":true}\n')
            return result

        with (
            patch.object(Authorization, "deactivate", new=finish),
            self.assertRaises(BaselineError),
        ):
            self.run_pipeline()
        self.assertTrue(changed)
        self.assertFalse(self.owner_state(3)["active"])
        self.assertEqual(self.owner_state(3)["operation_count"], 0)
        self.assertFalse((self.directory / "report.json").exists())

    def test_consumed_seal_and_report_replacements_fail_even_when_original_files_are_restored(self):
        for kind in ("seal", "report"):
            self.directory = self.root / f"consumed-{kind}"
            self.prepare()
            self.assertEqual(self.run_pipeline()["status"], "complete")
            # Model an interruption after stage completion, before final publication.
            (self.directory / "report.json").unlink()
            target = self.directory / "completed/0.json"
            if kind == "report":
                target = self.directory / json.loads(target.read_bytes())["attempt"] / "report.json"
            original = target.read_bytes()
            if kind == "seal":
                replacement = b" " + original  # Same JSON value, different authority-bound bytes.
            else:
                value = json.loads(original)
                value["controlled_unsealed_claim"] = "FORGED"
                replacement = _json(value) + b"\n"
            read = baseline_module._read
            injected = False

            def consume(
                path,
                *args,
                target=target,
                replacement=replacement,
                read=read,
                original=original,
                **kwargs,
            ):
                nonlocal injected
                if path == target and not injected:
                    injected = True
                    target.write_bytes(replacement)
                    try:
                        return read(path, *args, **kwargs)
                    finally:
                        target.write_bytes(original)
                return read(path, *args, **kwargs)

            before = self.physical_sends
            with (
                self.subTest(kind=kind),
                patch.object(baseline_module, "_read", side_effect=consume),
                self.assertRaises(BaselineError),
            ):
                self.run_pipeline(paid=False)
            self.assertTrue(injected)
            self.assertEqual(target.read_bytes(), original)
            self.assertEqual(self.physical_sends, before)
            self.assertFalse((self.directory / "report.json").exists())


if __name__ == "__main__":
    unittest.main()
