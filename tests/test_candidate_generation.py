"""Candidate C1 completion and native judging; mocked containers, real custody."""

import base64
import copy
import hashlib
import json
import os
import shutil
import sqlite3
import unittest
from contextlib import closing
from pathlib import Path
from unittest.mock import patch

import test_candidate_run as candidate_fixtures
import test_gateway as gateway_fixtures

from buddha.answers import Answers
from buddha.executor import ExecutionResult, ExecutorError
from buddha.gateway import Gateway, RawHTTPTransport
from buddha.native_evaluation import EvaluationError, prepare_evaluation, run_evaluation
from buddha.native_run import CHUNK_BYTES
from buddha.releases import Release, ReleaseError, Selection, _json, inventory, prepare_selection


def sha(raw):
    return hashlib.sha256(raw).hexdigest()


class CandidateGenerationTests(unittest.TestCase):
    def setUp(self):
        # Keep missing-API RED independent of synthetic fixture preparation.
        from buddha.candidate_generation import (
            prepare_candidate_generation,
            run_candidate_generation,
        )

        self.prepare_api = prepare_candidate_generation
        self.run_api = run_candidate_generation
        self.candidate = candidate_fixtures.CandidateSessionTests("runTest")
        self.candidate.setUp()
        self.addCleanup(self.candidate.doCleanups)
        self.fixture = self.candidate.fixture
        self.root = self.fixture.root.resolve()
        self.directory = self.root / "completed-candidate"
        self.weak_answers = ["  unchanged weak text  ", ""]
        self.workers = 0
        self.callbacks = 0
        self.request_text = "offline candidate call"
        self.physical_sends = 0
        self.native_workers = 0
        self.native_fail_once = False
        self.native_timeout_once = False
        self.generation_timeout_once = False
        self.generation_interrupt_once = False
        self.cleanup = "removed"
        self.summary_attack = False
        self.configure_native()

    def configure_native(self):
        """Reuse the existing fixture's components, never generate a fixed baseline."""
        f = self.fixture
        modules = ["src.partition", "src.score", "src.summarize"]
        for module in modules:
            f.write("official", module.replace(".", "/") + ".py", "def main():\n    pass\n")
        f.release_record["source"] = inventory(f.roots["official"])
        f.release_record["commands"] = [
            {"module": module, "argv": ["{artifacts}"]} for module in modules
        ]
        f.release_record["artifacts"] = {
            "answers": "generations.jsonl",
            "results": ["partitions.jsonl", "scores.jsonl"],
            "summary": "summary.json",
        }
        release = Release.from_record(f.release_record)
        dataset = (f.roots["official"] / "data/tasks.jsonl").read_bytes()
        from buddha.answers import TaskSet

        self.candidate.release = release
        self.candidate.tasks = TaskSet.from_dataset(release, dataset).select(["a"])
        self.candidate.task_path.write_bytes(self.candidate.tasks.to_bytes())
        f.selection = prepare_selection(
            release, f.roots, capabilities={gateway_fixtures.CAPABILITY: "profiles/openai.json"}
        )
        runner = self.root / "native-runner"
        package = runner / "buddha"
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
            shutil.copyfile(self.candidate.package / (name + ".py"), package / (name + ".py"))
        neutral = self.root / "native-agent"
        neutral.mkdir()
        (neutral / "identity.txt").write_text("not the source candidate", encoding="utf-8")
        roots = f.roots | {"runner": runner, "agent": neutral}
        selected = prepare_selection(
            release, roots, capabilities={gateway_fixtures.CAPABILITY: "profiles/openai.json"}
        )
        spec = copy.deepcopy(self.candidate.record["executor"])
        spec.pop("mounts")
        spec.update(role="evaluator", runner_entrypoint="buddha/native_worker.py")
        self.native = {
            "selection": selected.to_record(),
            "roots": {name: str(path) for name, path in roots.items()},
            "environment": {
                "helper_sha256": "d" * 64,
                "manifest_sha256": "e" * 64,
                "inventory": {
                    "lib/python3.13/site-packages/fixture.py": {"sha256": "f" * 64, "bytes": 1}
                },
            },
            "hooks": {"modules": modules, "cache": None, "calls": [], "sdk": []},
            "executor": spec,
            "profiles": {"openai": {"test-model": "primary"}},
            "budget_microusd": 10_000,
            "max_calls": 20,
        }
        self.stages = [
            {
                "inputs": ["generations.jsonl"],
                "outputs": [{"path": "partitions.jsonl", "id_field": "id"}],
                "allow_model": True,
            },
            {
                "inputs": ["partitions.jsonl"],
                "outputs": [{"path": "scores.jsonl", "id_field": "id"}],
                "allow_model": True,
            },
            {
                "inputs": ["scores.jsonl"],
                "outputs": [{"path": "summary.json", "id_field": None}],
                "allow_model": False,
            },
        ]
        self.summary = b'{"utility":NaN,"literal":"  unchanged  "}\n'

    def prepare(self, **changes):
        values = {
            "descriptor": self.candidate.descriptor,
            "selection": self.fixture.selection,
            "roots": self.fixture.roots,
            "authorization": self.fixture.authority,
            "review": self.fixture.review,
            "budget_microusd": 10_000,
            "max_calls": 20,
            "expected_runtime_sha256": self.candidate.expected_runtime,
        }
        return self.prepare_api(self.directory, **(values | changes))

    def execute(self, spec, *, initial, handle, **kwargs):
        try:
            return self.execute_worker(spec, initial=initial, handle=handle, **kwargs)
        except ReleaseError:
            # Match the existing native fixture: the executor owns frame-error cleanup.
            raise ExecutorError(
                "protocol", cleanup_status="removed", container_id="f" * 64
            ) from None

    def execute_worker(self, spec, *, initial, handle, **kwargs):
        self.workers += 1
        if spec.role == "evaluator":
            return self.execute_native(spec, initial, handle)
        self.assertEqual(spec.role, "agent")
        self.assertEqual(initial["task"], self.candidate.tasks.tasks[0].to_record())
        self.assertEqual(initial["config"], self.candidate.record["config"])
        self.assertNotIn(b"UNSELECTED_SOURCE_SENTINEL", _json(initial))
        handle(self.candidate.ready())
        for sequence in range(self.callbacks):
            reply = self.exchange(
                handle,
                self.candidate.request(sequence, text=self.request_text),
                timeout=self.generation_timeout_once,
            )
            self.generation_timeout_once = False
            if reply["type"] == "stop":
                handle(self.candidate.done([], "stopped", reply["reason"]))
                return self.execution(spec)
            if self.generation_interrupt_once:
                self.generation_interrupt_once = False
                raise KeyboardInterrupt
        handle(self.candidate.done(self.weak_answers))
        return self.execution(spec)

    def execution(self, spec):
        return ExecutionResult(
            0,
            "f" * 64,
            spec.image_id,
            0,
            0,
            sha(b""),
            1,
            0.01,
            _json({"fixture": "mock container, not confinement evidence"}),
            self.cleanup,
        )

    def exchange(self, handle, frame, *, timeout=False):
        connection = self.candidate.connection(timeout=timeout)
        with patch("http.client.HTTPSConnection", return_value=connection):
            reply = handle(frame)
        self.physical_sends += connection.request.call_count
        return reply

    def native_row(self, row, index):
        return row

    def execute_native(self, spec, initial, handle):
        self.native_workers += 1
        index = initial["command"]["index"]
        inputs = dict(spec.mounts)["/inputs"]
        self.assertEqual(
            inventory(inputs), {item["source"]: item["sha256"] for item in initial["inputs"]}
        )
        self.assertEqual(
            [item["destination"] for item in initial["inputs"]], self.stages[index]["inputs"]
        )
        if index == 0:
            self.assertEqual(
                (inputs / initial["inputs"][0]["source"]).read_bytes(),
                self.answers().native_bytes(),
            )
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
                self.assertEqual(handle.__self__.profiles, {})
                self.assertFalse(handle.__self__.gateway.transport.allow_paid)
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
                        "logical_id": sha(_json(["candidate-native", index])),
                        "attempt": 0,
                    },
                },
                timeout=self.native_timeout_once,
            )
            self.native_timeout_once = False
            if response["type"] == "stop":
                handle(
                    {
                        "type": "done",
                        "status": "stopped",
                        "reason": response["reason"],
                        "audit": audit,
                    }
                )
                return self.execution(spec)
            if self.native_fail_once:
                self.native_fail_once = False
                handle(
                    {"type": "done", "status": "failed", "reason": "native_error", "audit": audit}
                )
                return self.execution(spec)
        else:
            self.assertEqual(handle.__self__.profiles, {})
            self.assertFalse(handle.__self__.gateway.transport.allow_paid)
        if index < 2:
            rows = [
                json.loads(line)
                for line in (inputs / initial["inputs"][0]["source"]).read_bytes().splitlines()
            ]
            for row in rows:
                row["partition" if index == 0 else "score"] = [0, 1] if index == 0 else 7.0
            # Preserve native diagnostic NaN controls formerly inserted by SourceScreen._file.
            # Application finite-JSON and native framing guards remain unchanged.
            outputs = {
                "partitions.jsonl" if index == 0 else "scores.jsonl": b"".join(
                    json.dumps(
                        self.native_row(row, index),
                        sort_keys=True,
                        separators=(",", ":"),
                        allow_nan=True,
                    ).encode()
                    + b"\n"
                    for row in rows
                )
            }
        else:
            outputs = {"summary.json": self.summary}
        for name, body in outputs.items():
            for offset in range(0, len(body) or 1, CHUNK_BYTES):
                part = body[offset : offset + CHUNK_BYTES]
                handle(
                    {
                        "type": "file",
                        "path": name,
                        "offset": offset,
                        "eof": offset + len(part) == len(body),
                        "data_base64": base64.b64encode(part).decode(),
                    }
                )
        handle({"type": "done", "status": "complete", "reason": "complete", "audit": audit})
        return self.execution(spec)

    def run_generation(self, *, paid=False):
        with (
            patch.dict(os.environ, {"OPENAI_API_KEY": gateway_fixtures.KEY}, clear=True),
            patch("buddha.executor.run_container", side_effect=self.execute),
            patch(
                "buddha.agent_run.AgentSession", side_effect=AssertionError("fixed seed forbidden")
            ),
        ):
            return self.run_api(self.directory, transport=RawHTTPTransport(allow_paid=paid))

    def attempt(self):
        seal = json.loads((self.directory / "completed/0.json").read_bytes())
        return self.directory / seal["attempt"]

    def answers(self):
        return Answers.from_bytes((self.attempt() / "answers.json").read_bytes())

    def prepare_native(self, name="evaluation", *, reference=None, **changes):
        record = {
            "format": "buddha.native-evaluation.v1",
            "source_generation": reference or self.source_reference(),
            "native": self.native,
            "stages": self.stages,
        }
        descriptor = self.root / (name + ".json")
        descriptor.write_bytes(_json(record))
        directory = self.root / name
        values = {
            "descriptor": descriptor,
            "authorization": self.fixture.authority,
            "review": self.fixture.review,
        }
        prepare_evaluation(directory, **(values | changes))
        return directory

    def run_native(self, directory, *, paid=True):
        with (
            patch.dict(
                os.environ, {"OPENAI_API_KEY": gateway_fixtures.KEY} if paid else {}, clear=True
            ),
            patch("buddha.executor.run_container", side_effect=self.execute),
            patch("buddha.agent_run.AgentSession", side_effect=AssertionError("seed forbidden")),
            patch(
                "buddha.candidate_run.CandidateSession", side_effect=AssertionError("regeneration")
            ),
        ):
            return run_evaluation(directory, transport=RawHTTPTransport(allow_paid=paid))

    def check_partial(self, result, directory):
        self.assertEqual(result["status"], "incomplete")
        stored = json.loads((directory / result["observation"]).read_bytes())
        # The returned locator may be external to the saved observation body.
        self.assertEqual(
            {k: v for k, v in stored.items() if k != "observation"},
            {k: v for k, v in result.items() if k != "observation"},
        )
        self.assertFalse((directory / "report.json").exists())

    def source_reference(self):
        owner = self.directory / "owners/0"
        manifest = json.loads((owner / "manifest.json").read_bytes())
        return {
            "format": "buddha.candidate-generation-source.v1",
            "generation_directory": str(self.directory),
            "stage_seal_sha256": sha((self.directory / "completed/0.json").read_bytes()),
            "owner_manifest_sha256": manifest["record_sha256"],
            "owner_ledger_sha256": sha((owner / "operations.sqlite3").read_bytes()),
        }

    def test_zero_call_candidate_publishes_its_own_c1_seal_and_authority_anchor(self):
        self.assertEqual(self.prepare(), self.directory)
        self.assertEqual(self.fixture.authority.summary()["operation_count"], 0)
        report = self.run_generation()
        self.assertEqual(report["status"], "complete")
        self.assertEqual(self.workers, 1)
        reference = self.source_reference()
        seal = json.loads((self.directory / "completed/0.json").read_bytes())
        self.assertEqual(seal["format"], "buddha.candidate-generation-stage.v1")
        self.assertIs(type(seal["index"]), int)
        self.assertEqual(seal["index"], 0)
        attempt = self.directory / seal["attempt"]
        session_report = json.loads((attempt / "report.json").read_bytes())
        self.assertEqual(session_report["format"], "buddha.candidate-generation-report.v1")
        answers = Answers.from_bytes((attempt / "answers.json").read_bytes())
        self.assertEqual(
            answers.to_record()["outputs"], [{"task_id": "a", "answers": self.weak_answers}]
        )
        self.assertEqual(answers.to_record()["agent_sha256"], self.fixture.selection.agent_sha256)
        self.assertEqual(session_report["calls"], {"requested": 0, "completed": 0, "stopped": 0})
        owner = json.loads((self.directory / "owners/0/manifest.json").read_bytes())
        funded = next(
            row
            for row in self.fixture.authority.summary()["runs"]
            if row["run_id"] == owner["run_id"]
        )
        self.assertFalse(funded["active"])
        with closing(sqlite3.connect(self.fixture.authority.path)) as connection:
            reason = connection.execute(
                "SELECT reason FROM auth_deactivations WHERE run_id=?", (owner["run_id"],)
            ).fetchone()[0]
        self.assertEqual(
            reason, "candidate generation completed: " + reference["stage_seal_sha256"]
        )

    def test_long_valid_candidate_request_is_passively_accepted_for_native_assessment(self):
        self.callbacks = 1
        self.request_text = "x" * 6000
        self.prepare()
        self.assertEqual(self.run_generation(paid=True)["status"], "complete")
        self.assertEqual(self.physical_sends, 1)
        with patch("buddha.executor.run_container", side_effect=AssertionError("prepare executed")):
            self.assertEqual(self.prepare_native("long-request"), self.root / "long-request")
        self.assertEqual(self.physical_sends, 1)

    def test_short_valid_candidate_request_has_a_positive_passive_reader_control(self):
        self.callbacks = 1
        self.prepare()
        self.assertEqual(self.run_generation(paid=True)["status"], "complete")
        self.assertEqual(self.prepare_native("short-request"), self.root / "short-request")
        self.assertEqual((self.native_workers, self.physical_sends), (0, 1))

    def test_runtime_image_and_environment_match_external_approval_before_owner(self):
        for field in ["image_id", "image_environment"]:
            with self.subTest(field=field):
                recipe = copy.deepcopy(self.candidate.record)
                if field == "image_id":
                    recipe["executor"][field] = "sha256:" + "b" * 64
                else:
                    recipe["executor"][field][0][1] += "-changed"
                self.candidate.descriptor.write_bytes(_json(recipe))
                self.directory = self.root / ("bad-runtime-" + field)
                with self.assertRaises(ReleaseError):
                    self.prepare()
                self.assertFalse((self.directory / "owners/0/manifest.json").exists())
        self.assertEqual(self.physical_sends, 0)

    def test_one_callback_produces_two_answers_without_seed_semantics(self):
        self.callbacks = 1
        self.prepare()
        self.assertEqual(self.run_generation(paid=True)["status"], "complete")
        self.assertEqual(self.answers().to_record()["outputs"][0]["answers"], self.weak_answers)
        report = json.loads((self.attempt() / "report.json").read_bytes())
        self.assertEqual(report["calls"], {"requested": 1, "completed": 1, "stopped": 0})
        self.assertEqual(self.physical_sends, 1)

    def test_three_callbacks_produce_two_duplicate_literal_answers(self):
        self.callbacks = 3
        self.weak_answers = ["same", "same"]
        self.prepare()
        self.assertEqual(self.run_generation(paid=True)["status"], "complete")
        self.assertEqual(self.answers().to_record()["outputs"][0]["answers"], ["same", "same"])
        report = json.loads((self.attempt() / "report.json").read_bytes())
        self.assertEqual(report["calls"], {"requested": 3, "completed": 3, "stopped": 0})
        self.assertEqual(
            (self.physical_sends, self.fixture.authority.summary()["operation_count"]), (3, 3)
        )

    def test_runtime_and_expected_external_hashes_reject_before_owner_creation(self):
        control = self.root / "reviewed-control.json"
        control.write_bytes(b'{"frozen":true}\n')
        for name, changes in [
            ("wrong-runtime", {"expected_runtime_sha256": "0" * 64}),
            (
                "wrong-expected-control",
                {"input_files": [control], "expected_input_hashes": {control: "0" * 64}},
            ),
            ("boolean-ceiling", {"max_calls": False}),
        ]:
            with self.subTest(name=name):
                self.directory = self.root / name
                with (
                    patch("buddha.executor.run_container", side_effect=AssertionError("worker")),
                    patch("http.client.HTTPSConnection", side_effect=AssertionError("HTTPS")),
                    self.assertRaises(ReleaseError),
                ):
                    self.prepare(**changes)
                self.assertFalse((self.directory / "owners/0/manifest.json").exists())
        self.assertEqual(self.fixture.authority.summary()["operation_count"], 0)

    def test_original_control_change_is_not_adopted_by_producer_resume(self):
        control = self.root / "study-control.json"
        control.write_bytes(b'{"frozen":true}\n')
        self.prepare(
            input_files=[control], expected_input_hashes={control: sha(control.read_bytes())}
        )
        original = (self.directory / "owners/0/manifest.json").read_bytes()
        control.write_bytes(b'{"frozen":false}\n')
        with self.assertRaises(ReleaseError):
            self.run_generation(paid=True)
        self.assertEqual((self.workers, self.physical_sends), (0, 0))
        self.assertEqual((self.directory / "owners/0/manifest.json").read_bytes(), original)
        self.assertFalse((self.directory / "completed/0.json").exists())

    def test_complete_replay_is_keyless_without_worker_or_publication_changes(self):
        self.callbacks = 1
        self.prepare()
        first = self.run_generation(paid=True)
        report = (self.directory / "report.json").read_bytes()
        original = self.source_reference()
        before = self.fixture.authority.summary()
        with (
            patch.dict(os.environ, {}, clear=True),
            patch("buddha.executor.run_container", side_effect=AssertionError("replay worker")),
            patch("http.client.HTTPSConnection", side_effect=AssertionError("replay HTTPS")),
        ):
            replay = self.run_api(self.directory, transport=RawHTTPTransport(allow_paid=False))
        self.assertEqual(replay, first)
        self.assertEqual((self.directory / "report.json").read_bytes(), report)
        self.assertEqual(self.source_reference(), original)
        self.assertEqual(self.fixture.authority.summary(), before)
        self.assertEqual((self.workers, self.physical_sends), (1, 1))

    def test_candidate_c1_runs_full_fresh_native_occasions_with_neutral_agent(self):
        self.callbacks = 1
        self.prepare()
        self.run_generation(paid=True)
        original = self.source_reference()
        generation_report = (self.directory / "report.json").read_bytes()
        self.assertNotEqual(
            Selection.from_bytes(_json(self.native["selection"])).agent_sha256,
            self.fixture.selection.agent_sha256,
        )
        first_dir = self.prepare_native("first-occasion")
        first = self.run_native(first_dir)
        self.assertEqual(first["status"], "complete")
        self.assertEqual(Path(first["summary"]["path"]).read_bytes(), self.summary)
        self.assertEqual(
            first["answers_file_sha256"], sha((self.attempt() / "answers.json").read_bytes())
        )
        second_dir = self.prepare_native("second-occasion")
        self.assertEqual(self.run_native(second_dir)["status"], "complete")
        first_owner = json.loads((first_dir / "owners/1/manifest.json").read_bytes())
        second_owner = json.loads((second_dir / "owners/1/manifest.json").read_bytes())
        self.assertNotEqual(first_owner["run_id"], second_owner["run_id"])
        stored = (first_dir / "report.json").read_bytes()
        before = self.fixture.authority.summary()
        with (
            patch.dict(os.environ, {}, clear=True),
            patch("buddha.executor.run_container", side_effect=AssertionError("replay worker")),
            patch("http.client.HTTPSConnection", side_effect=AssertionError("replay HTTPS")),
        ):
            self.assertEqual(
                run_evaluation(first_dir, transport=RawHTTPTransport(allow_paid=False)), first
            )
        self.assertEqual((first_dir / "report.json").read_bytes(), stored)
        self.assertEqual(self.fixture.authority.summary(), before)
        self.assertEqual(self.source_reference(), original)
        self.assertEqual((self.directory / "report.json").read_bytes(), generation_report)
        self.assertEqual((self.native_workers, self.physical_sends), (6, 5))

    def test_native_known_reply_failure_resumes_original_owner_without_regeneration(self):
        self.callbacks = 1
        self.prepare()
        self.run_generation(paid=True)
        original = self.source_reference()
        directory = self.prepare_native()
        owner = (directory / "owners/1/manifest.json").read_bytes()
        self.native_fail_once = True
        stopped = self.run_native(directory)
        self.check_partial(stopped, directory)
        self.assertEqual(stopped["reason"], "native_error")
        observation = (directory / stopped["observation"]).read_bytes()
        self.assertEqual(self.physical_sends, 2)
        self.assertEqual(self.run_native(directory)["status"], "complete")
        self.assertEqual((directory / "owners/1/manifest.json").read_bytes(), owner)
        self.assertEqual((directory / stopped["observation"]).read_bytes(), observation)
        self.assertEqual(self.source_reference(), original)
        self.assertEqual((self.workers - self.native_workers, self.physical_sends), (1, 3))

    def test_unknown_generation_retains_hold_and_cannot_publish_eligible_source(self):
        self.callbacks = 1
        self.generation_timeout_once = True
        self.prepare()
        stopped = self.run_generation(paid=True)
        self.check_partial(stopped, self.directory)
        self.assertEqual(stopped["reason"], "unknown")
        self.assertFalse((self.directory / "completed/0.json").exists())
        before = self.fixture.authority.summary()
        self.assertGreater(before["reserved_microusd"], 0)
        self.assertEqual(self.physical_sends, 1)
        again = self.run_generation(paid=True)
        self.assertEqual(again["status"], "incomplete")
        after = self.fixture.authority.summary()
        for name in ("operation_count", "spent_microusd", "reserved_microusd"):
            self.assertEqual(after[name], before[name])
        self.assertEqual(self.physical_sends, 1)
        self.assertFalse((self.directory / "completed/0.json").exists())

    def test_native_unknown_stops_shared_fresh_work_without_releasing_hold(self):
        self.prepare()
        self.run_generation()
        original = self.source_reference()
        directory = self.prepare_native()
        self.native_timeout_once = True
        stopped = self.run_native(directory)
        self.check_partial(stopped, directory)
        self.assertEqual(stopped["reason"], "unknown")
        before = self.fixture.authority.summary()
        self.assertGreater(before["reserved_microusd"], 0)
        self.assertEqual(self.run_native(directory)["status"], "incomplete")
        try:
            other = self.prepare_native("blocked-fresh-occasion")
        except ReleaseError:
            pass
        else:
            self.assertEqual(self.run_native(other)["status"], "incomplete")
        after = self.fixture.authority.summary()
        for name in ("operation_count", "spent_microusd", "reserved_microusd"):
            self.assertEqual(after[name], before[name])
        self.assertEqual(self.physical_sends, 1)
        self.assertEqual(self.source_reference(), original)

    def test_cancelled_generation_keeps_actual_attempt_and_reuses_known_reply(self):
        self.callbacks = 1
        self.generation_interrupt_once = True
        self.prepare()
        owner = (self.directory / "owners/0/manifest.json").read_bytes()
        with self.assertRaises(KeyboardInterrupt):
            self.run_generation(paid=True)
        self.assertFalse((self.directory / "completed/0.json").exists())
        observations = list((self.directory / "observations").glob("*.json"))
        self.assertEqual(len(observations), 1)
        saved = observations[0].read_bytes()
        stopped = json.loads(saved)
        self.assertEqual((stopped["status"], stopped["reason"]), ("incomplete", "cancelled"))
        self.assertIsNotNone(stopped["attempt"])
        actual = json.loads((Path(stopped["attempt"]) / "report.json").read_bytes())
        self.assertEqual(actual["reason"], "cancelled")
        self.assertEqual(self.run_generation(paid=True)["status"], "complete")
        self.assertEqual((self.directory / "owners/0/manifest.json").read_bytes(), owner)
        self.assertEqual(observations[0].read_bytes(), saved)
        self.assertEqual(
            (self.physical_sends, self.fixture.authority.summary()["operation_count"]), (1, 1)
        )

    def test_failed_cleanup_preserves_attempt_but_never_seals_c1(self):
        self.prepare()
        self.cleanup = "unknown"
        stopped = self.run_generation()
        self.check_partial(stopped, self.directory)
        self.assertFalse((self.directory / "completed/0.json").exists())
        report = json.loads((Path(stopped["attempt"]) / "report.json").read_bytes())
        self.assertNotEqual(report["status"], "complete")
        self.assertEqual(report["execution"]["cleanup_status"], "unknown")
        self.assertFalse((Path(stopped["attempt"]) / "answers.json").exists())

    def test_wrong_source_hashes_and_changed_literal_c1_reject_before_native_owner(self):
        self.prepare()
        self.run_generation()
        for field in ["stage_seal_sha256", "owner_manifest_sha256", "owner_ledger_sha256"]:
            with self.subTest(field=field):
                reference = self.source_reference()
                reference[field] = "0" * 64
                with self.assertRaises(EvaluationError):
                    self.prepare_native("bad-" + field, reference=reference)
                self.assertFalse((self.root / ("bad-" + field) / "owners/1/manifest.json").exists())
        path = self.attempt() / "answers.json"
        original = path.read_bytes()
        path.write_bytes(original + b" ")
        with self.assertRaises(EvaluationError):
            self.prepare_native("changed-raw-c1")
        self.assertEqual((self.native_workers, self.physical_sends), (0, 0))

    def test_passive_candidate_dispatch_survives_retired_agent_and_keeps_old_reader_strict(self):
        self.prepare()
        self.run_generation()
        original = self.source_reference()
        for role in ["agent", "runner"]:
            source = self.fixture.roots[role].resolve()
            target = self.root / ("retired-" + role)
            self.assertTrue(source.is_relative_to(self.root))
            self.assertTrue(target.is_relative_to(self.root))
            source.rename(target)
        with patch(
            "buddha.gateway.Gateway.__init__", side_effect=AssertionError("passive Gateway")
        ):
            directory = self.prepare_native("retired-source")
        self.assertEqual(self.run_native(directory)["status"], "complete")
        old = {k: v for k, v in original.items() if k not in ["format", "generation_directory"]}
        old["baseline_directory"] = original["generation_directory"]
        with self.assertRaises(EvaluationError):
            self.prepare_native("not-a-baseline", reference=old)
        self.assertFalse((self.root / "not-a-baseline/owners/1/manifest.json").exists())

    def test_active_source_with_self_asserted_seal_is_not_authority_anchored(self):
        from buddha.candidate_run import CandidateSession

        self.prepare()
        owner = self.directory / "owners/0"
        attempt = self.directory / "attempts/0-0"
        session = CandidateSession(
            Gateway(owner, transport=RawHTTPTransport(allow_paid=False)),
            descriptor=self.candidate.descriptor,
            output=attempt,
            expected_runtime_sha256=self.candidate.expected_runtime,
        )
        with patch("buddha.executor.run_container", side_effect=self.execute):
            self.assertEqual(session.run()["status"], "complete")
        manifest = json.loads((owner / "manifest.json").read_bytes())
        (self.directory / "completed/0.json").write_bytes(
            _json(
                {
                    "format": "buddha.candidate-generation-stage.v1",
                    "index": 0,
                    "owner_sha256": manifest["record_sha256"],
                    "attempt": "attempts/0-0",
                    "files": inventory(attempt),
                }
            )
            + b"\n"
        )
        with self.assertRaises(EvaluationError):
            self.prepare_native("unanchored")
        self.assertFalse((self.root / "unanchored/owners/1/manifest.json").exists())
        self.assertEqual(self.native_workers, 0)

    def test_boolean_zero_callback_counter_cannot_be_sealed(self):
        from buddha.candidate_run import CandidateSession

        self.prepare()
        original = CandidateSession.run

        def changed(session):
            result = original(session)
            result["calls"]["completed"] = False
            (session.output / "report.json").write_bytes(_json(result) + b"\n")
            return result

        with patch.object(CandidateSession, "run", changed):
            try:
                result = self.run_generation()
            except ReleaseError:
                pass
            else:
                self.assertNotEqual(result["status"], "complete")
        self.assertFalse((self.directory / "completed/0.json").exists())

    def test_post_session_protocol_failure_preserves_actual_report_and_observation(self):
        from buddha.candidate_run import CandidateSession

        self.callbacks = 1
        self.prepare()
        original = CandidateSession.run
        actual_reports = []

        def changed(session):
            result = original(session)
            actual_reports.append((session.output, (session.output / "report.json").read_bytes()))
            # The genuine stored report stays intact; a mismatched handoff is invalid.
            return result | {"descriptor_sha256": "0" * 64}

        with patch.object(CandidateSession, "run", changed), self.assertRaises(ReleaseError):
            self.run_generation(paid=True)
        self.assertEqual(len(actual_reports), 1)
        attempt, raw = actual_reports[0]
        self.assertEqual((attempt / "report.json").read_bytes(), raw)
        self.assertFalse((self.directory / "completed/0.json").exists())
        observations = list((self.directory / "observations").glob("*.json"))
        self.assertEqual(len(observations), 1)
        stopped = json.loads(observations[0].read_bytes())
        self.assertEqual((stopped["status"], stopped["reason"]), ("incomplete", "protocol"))
        self.assertEqual(Path(stopped["attempt"]), attempt)
        self.assertEqual(stopped["generation"], json.loads(raw))
        self.assertEqual(self.physical_sends, 1)

    def test_summary_attempt_cannot_dispatch_and_native_controls_keep_original_hashes(self):
        control = self.root / "reviewed-experiment.json"
        control.write_bytes(b'{"frozen":true}\n')
        pin = sha(control.read_bytes())
        self.prepare(input_files=[control], expected_input_hashes={control: pin})
        self.run_generation()
        directory = self.prepare_native(input_files=[control], expected_input_hashes={control: pin})
        self.summary_attack = True
        stopped = self.run_native(directory)
        self.check_partial(stopped, directory)
        self.assertEqual(self.physical_sends, 2)
        for index in (1, 2, 3):
            manifest = json.loads((directory / f"owners/{index}/manifest.json").read_bytes())
            inputs = {row["path"]: row["sha256"] for row in manifest["invocation"]["inputs"]}
            self.assertEqual(inputs[str(control)], pin)
        self.assertFalse((directory / "report.json").exists())


if __name__ == "__main__":
    unittest.main()
