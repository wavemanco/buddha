"""Prospective checked generation failures; existing v1 stays strict."""

import hashlib
import json
import os
import shutil
import sys
import unittest
from pathlib import Path
from unittest.mock import patch

import test_candidate_generation as generation_fixtures
import test_candidate_run as session_fixtures
import test_executor as executor_fixtures

from buddha.answers import Answers
from buddha.executor import ContainerSpec, ExecutorError, Limits
from buddha.gateway import RawHTTPTransport
from buddha.releases import _json


class CandidateGenerationOutcomeTests(unittest.TestCase):
    def test_real_executor_cleanup_sidecar_survives_c1_sealing_and_passive_replay(self):
        h = self.prepare_v2()
        settings = h.candidate.record["executor"]
        spec = ContainerSpec(
            settings["image_id"],
            settings["role"],
            tuple((target, Path(path)) for target, path in settings["mounts"]),
            settings["runner_entrypoint"],
            tuple(tuple(pair) for pair in settings["image_environment"]),
        )
        fixture = executor_fixtures.DockerFixture(
            spec,
            Limits(**settings["limits"]),
            stdout=_json(h.candidate.ready())
            + b"\n"
            + _json(h.candidate.done(h.weak_answers))
            + b"\n",
        )
        with (
            patch.object(executor_fixtures, "IMAGE", settings["image_id"]),
            patch.object(executor_fixtures, "ENDPOINT", settings["docker_endpoint"]),
            patch("buddha.executor.shutil.which", return_value=sys.executable),
            patch("subprocess.run", side_effect=fixture.control),
            patch("subprocess.Popen", side_effect=fixture.popen),
        ):
            report = h.run_api(h.directory, transport=RawHTTPTransport(allow_paid=False))
        self.assertEqual(report["status"], "complete")
        self.assertEqual(report["disposition"], "generated")
        seal = json.loads((h.directory / "completed/0.json").read_bytes())
        cleanup = list((h.directory / "owners/0").glob("executor-cleanup-*.json"))
        self.assertEqual(len(cleanup), 1)
        self.assertEqual(
            set(seal["files"]),
            {"report.json", "session/report.json", "session/done.json", "session/answers.json"},
        )
        evidence = json.loads(cleanup[0].read_bytes())
        self.assertEqual(evidence["cleanup_status"], "removed")
        self.assertEqual(evidence["container_id"], executor_fixtures.CONTAINER)
        self.assertEqual(
            evidence["intent"]["attempt"], str(h.directory / seal["attempt"] / "session")
        )
        self.assertFalse(list(h.root.glob("*.executor-pending.json")))
        self.assertEqual(self.inspect(h), report)
        with (
            patch("buddha.executor.run_container", side_effect=AssertionError("replay worker")),
            patch("http.client.HTTPSConnection", side_effect=AssertionError("replay network")),
        ):
            self.assertEqual(
                h.run_api(h.directory, transport=RawHTTPTransport(allow_paid=False)), report
            )
            h.prepare_native(reference=report["source_generation"])

    def prepare_v2(self, **changes):
        h = self.fixture()
        h.candidate.record.update(format="buddha.candidate-generation.v2", **changes)
        h.candidate.descriptor.write_bytes(_json(h.candidate.record))
        h.prepare()
        return h

    def run_worker(self, h, worker, *, paid=False):
        with (
            patch.dict(
                os.environ,
                {"OPENAI_API_KEY": generation_fixtures.gateway_fixtures.KEY} if paid else {},
                clear=True,
            ),
            patch("buddha.executor.run_container", side_effect=worker),
        ):
            return h.run_api(h.directory, transport=RawHTTPTransport(allow_paid=paid))

    @staticmethod
    def tree(directory):
        return {
            str(path.relative_to(directory)): hashlib.sha256(path.read_bytes()).hexdigest()
            for path in directory.rglob("*")
            if path.is_file()
        }

    def inspect(self, h):
        from buddha.candidate_generation import inspect_candidate_generation

        return inspect_candidate_generation(
            h.directory,
            authorization=h.fixture.authority.path,
            expected_report_sha256=hashlib.sha256(
                (h.directory / "report.json").read_bytes()
            ).hexdigest(),
        )

    def fixture(self):
        fixture = generation_fixtures.CandidateGenerationTests("runTest")
        fixture.setUp()
        self.addCleanup(fixture.doCleanups)
        return fixture

    def session_fixture(self):
        h = session_fixtures.CandidateSessionTests("runTest")
        h.setUp()
        self.addCleanup(h.doCleanups)
        h.record["format"] = "buddha.candidate-generation.v2"
        h.freeze()
        return h

    def test_v2_host_accepts_only_zero_prefix_agent_error_before_ready(self):
        h = self.session_fixture()
        session = h.session()
        self.assertIsNone(session.handle(h.done([], "failed", "agent_error")))
        self.assertFalse(session.ready)
        self.assertFalse(session.broken)
        self.assertEqual(session.done, h.done([], "failed", "agent_error"))

    def test_v2_host_keeps_other_pre_ready_frames_invalid(self):
        h = self.session_fixture()
        for index, frame in enumerate(
            (
                h.done([], "failed", "protocol"),
                h.done(["", ""]),
                h.request(),
                h.done(["unexpected"], "failed", "agent_error"),
            )
        ):
            with self.subTest(frame=frame["type"], index=index):
                session = h.session(output=h.fixture.root / ("invalid-" + str(index)))
                with self.assertRaises(h.Error):
                    session.handle(frame)
                self.assertTrue(session.broken)
                self.assertIsNone(session.done)

    def test_v2_pre_ready_bool_counters_are_not_literal_zero_prefix(self):
        h = self.session_fixture()
        for name in ("sequence", "requested"):
            with self.subTest(counter=name):
                session = h.session(output=h.fixture.root / ("bool-" + name))
                if name == "sequence":
                    session.sequence = False
                else:
                    session.calls["requested"] = False
                with self.assertRaises(h.Error):
                    session.handle(h.done([], "failed", "agent_error"))
                self.assertTrue(session.broken)

    def test_v2_pre_ready_agent_error_is_checked_terminal_without_c1(self):
        h = self.prepare_v2()

        def worker(spec, *, handle, **kwargs):
            handle(h.candidate.done([], "failed", "agent_error"))
            return h.execution(spec)

        with patch("buddha.executor.run_container", side_effect=worker):
            report = h.run_api(h.directory, transport=RawHTTPTransport(allow_paid=False))
        self.assertEqual(report["status"], "complete")
        self.assertEqual(report["disposition"], "candidate_execution_failed")
        self.assertEqual(report["reason"], "agent_error")
        self.assertEqual(report["generation"]["status"], "failed")
        self.assertEqual(report["generation"]["reason"], "agent_error")
        self.assertEqual(
            report["generation"]["calls"], {"requested": 0, "completed": 0, "stopped": 0}
        )
        self.assertEqual(report["generation"]["artifacts"], {})
        self.assertFalse(report["outcome"]["terminal"]["ready_seen"])
        self.assertTrue((h.directory / "completed/0.json").is_file())
        self.assertFalse(any(h.directory.rglob("answers.json")))
        self.assertEqual(h.fixture.authority.summary()["operation_count"], 0)
        self.assertEqual(self.inspect(h), report)
        from buddha.candidate_generation import (
            CandidateGenerationError,
            read_candidate_generation_source,
        )

        with self.assertRaises(CandidateGenerationError):
            read_candidate_generation_source(report["source_generation"], h.fixture.authority.path)

    def test_v2_generated_zero_one_three_callbacks_keep_literal_c1(self):
        from buddha.candidate_generation import read_candidate_generation_source

        for callbacks in (0, 1, 3):
            with self.subTest(callbacks=callbacks):
                h = self.prepare_v2()
                h.callbacks = callbacks
                report = h.run_generation(paid=True)
                self.assertEqual(report["disposition"], "generated")
                self.assertEqual(report["generation"]["calls"]["completed"], callbacks)
                tasks, answers, path, _, _ = read_candidate_generation_source(
                    report["source_generation"], h.fixture.authority.path
                )
                self.assertEqual(tasks.fingerprint(), h.candidate.tasks.fingerprint())
                self.assertEqual(answers.to_record()["outputs"][0]["answers"], h.weak_answers)
                self.assertEqual(path.parent.name, "session")
                self.assertEqual(
                    Answers.from_bytes(path.read_bytes()).to_bytes(), answers.to_bytes()
                )
                self.assertEqual(self.inspect(h), report)

    def test_passive_c1_is_interpreted_once_with_fresh_reads_and_publication_parity(self):
        from buddha.candidate_generation import read_candidate_generation_source
        from buddha.doctor import _Capture

        for prospective in (False, True):
            with self.subTest(prospective=prospective):
                h = self.prepare_v2() if prospective else self.fixture()
                if not prospective:
                    h.prepare()
                report = h.run_generation()
                path = h.attempt() / ("session/answers.json" if prospective else "answers.json")
                raw = path.read_bytes()
                before = self.tree(h.directory)
                authority_before = h.fixture.authority.path.read_bytes()
                original_read = _Capture.read
                reads = []

                def read(
                    capture,
                    filename,
                    *args,
                    path=path,
                    reads=reads,
                    original_read=original_read,
                    **kwargs,
                ):
                    if filename == path:
                        reads.append(filename)
                    return original_read(capture, filename, *args, **kwargs)

                with (
                    patch.object(_Capture, "read", new=read),
                    patch.object(Answers, "from_bytes", wraps=Answers.from_bytes) as parse,
                    patch(
                        "buddha.candidate_generation.Gateway", side_effect=AssertionError("passive")
                    ),
                    patch(
                        "buddha.candidate_run.CandidateSession",
                        side_effect=AssertionError("passive"),
                    ),
                    patch("buddha.executor.run_container", side_effect=AssertionError("passive")),
                    patch("http.client.HTTPSConnection", side_effect=AssertionError("passive")),
                ):
                    tasks, answers, returned_path, files, _ = read_candidate_generation_source(
                        report["source_generation"] if prospective else h.source_reference(),
                        h.fixture.authority.path,
                    )
                self.assertEqual(len(reads), 5 if prospective else 3)
                self.assertEqual(parse.call_count, 1)
                self.assertEqual(tasks.fingerprint(), h.candidate.tasks.fingerprint())
                self.assertEqual(returned_path, path)
                self.assertEqual(files[path], hashlib.sha256(raw).hexdigest())
                self.assertEqual(answers.to_bytes(), Answers.from_bytes(raw).to_bytes())
                if prospective:
                    with patch.object(Answers, "from_bytes", wraps=Answers.from_bytes) as parse:
                        self.assertEqual(self.inspect(h), report)
                    self.assertEqual(parse.call_count, 1)
                self.assertEqual(self.tree(h.directory), before)
                self.assertEqual(h.fixture.authority.path.read_bytes(), authority_before)

    def test_c1_change_after_initial_validation_or_before_finish_is_rejected(self):
        from buddha import candidate_generation
        from buddha.doctor import _Capture

        h = self.prepare_v2()
        report = h.run_generation()
        path = h.attempt() / "session/answers.json"
        raw = path.read_bytes()
        changed = json.loads(raw)
        changed["outputs"][0]["answers"][0] = "different valid literal answer"
        replacement = Answers.from_bytes(_json(changed)).to_bytes()
        for boundary in ("initial", "finish"):
            with self.subTest(boundary=boundary):
                original = (
                    candidate_generation._outputs if boundary == "initial" else _Capture.finish
                )

                def replace(*args, boundary=boundary, original=original, **kwargs):
                    if boundary == "initial":
                        result = original(*args, **kwargs)
                        path.write_bytes(replacement)
                        return result
                    path.write_bytes(replacement)
                    return original(*args, **kwargs)

                target = candidate_generation if boundary == "initial" else _Capture
                method = "_outputs" if boundary == "initial" else "finish"
                try:
                    with patch.object(target, method, new=replace):
                        with self.assertRaises(candidate_generation.CandidateGenerationError):
                            candidate_generation.read_candidate_generation_source(
                                report["source_generation"], h.fixture.authority.path
                            )
                finally:
                    path.write_bytes(raw)

    def test_checked_c1_binds_original_noncanonical_bytes_and_exact_path(self):
        from buddha import candidate_generation

        h = self.prepare_v2()
        report = h.run_generation()
        original = candidate_generation._outputs
        with patch.object(candidate_generation, "_outputs", wraps=original) as outputs:
            _, expected, path, _, _ = candidate_generation.read_candidate_generation_source(
                report["source_generation"], h.fixture.authority.path
            )
        args = outputs.call_args.args
        raw = path.read_bytes()
        noncanonical = json.dumps(json.loads(raw), indent=2).encode()
        self.assertNotEqual(noncanonical, expected.to_bytes())
        amended_report = args[1] | {
            "artifacts": {"answers.json": hashlib.sha256(noncanonical).hexdigest()}
        }
        try:
            path.write_bytes(noncanonical)
            checked = original(args[0], amended_report, *args[2:])
            parsed = checked.checked(path, path.read_bytes())
            self.assertEqual(parsed.to_bytes(), expected.to_bytes())
            self.assertEqual(parsed.native_bytes(), expected.native_bytes())
            self.assertIs(checked.checked(path, noncanonical), parsed)
            for other_path, other_raw in (
                (path.with_name("other.json"), noncanonical),
                (path, raw),
                (path, noncanonical + b"\n"),
            ):
                with self.subTest(path=other_path, raw_size=len(other_raw)):
                    with self.assertRaises(candidate_generation.CandidateGenerationError):
                        checked.checked(other_path, other_raw)
        finally:
            path.write_bytes(raw)

    def test_post_ready_agent_error_after_known_reply_is_terminal_and_passive(self):
        h = self.prepare_v2()

        def worker(spec, *, handle, **kwargs):
            handle(h.candidate.ready())
            self.assertEqual(h.exchange(handle, h.candidate.request())["type"], "response")
            handle(h.candidate.done([], "failed", "agent_error"))
            return h.execution(spec)

        report = self.run_worker(h, worker, paid=True)
        self.assertEqual(report["disposition"], "candidate_execution_failed")
        terminal = report["outcome"]["terminal"]
        self.assertTrue(terminal["ready_seen"])
        self.assertEqual(terminal["operation_count"], 1)
        self.assertEqual(
            terminal["recorded_cost_microusd"],
            report["generation"]["gateway_totals"]["spent_microusd"],
        )
        self.assertEqual(h.physical_sends, 1)
        before = self.tree(h.directory)
        with patch("buddha.executor.run_container", side_effect=AssertionError("no new worker")):
            self.assertEqual(
                h.run_api(h.directory, transport=RawHTTPTransport(allow_paid=False)), report
            )
        retired = h.root / "retired"
        retired.mkdir()
        for name in ("agent", "runner"):
            self.assertTrue(h.fixture.roots[name].resolve().is_relative_to(h.root.resolve()))
            self.assertTrue((retired / name).resolve().is_relative_to(h.root.resolve()))
            shutil.move(str(h.fixture.roots[name]), str(retired / name))
        with (
            patch("buddha.candidate_generation.Gateway", side_effect=AssertionError("passive")),
            patch(
                "buddha.candidate_generation.Authorization", side_effect=AssertionError("passive")
            ),
            patch("buddha.candidate_run.CandidateSession", side_effect=AssertionError("passive")),
            patch("http.client.HTTPSConnection", side_effect=AssertionError("passive")),
            patch("socket.socket", side_effect=AssertionError("passive")),
        ):
            self.assertEqual(self.inspect(h), report)
        self.assertEqual(self.tree(h.directory), before)

    def test_known_prefix_cannot_be_shortened_then_replays_original_reply(self):
        h = self.prepare_v2()

        def interrupted(spec, *, handle, **kwargs):
            handle(h.candidate.ready())
            self.assertEqual(h.exchange(handle, h.candidate.request())["type"], "response")
            raise ExecutorError("protocol", cleanup_status="removed", container_id="f" * 64)

        first = self.run_worker(h, interrupted, paid=True)
        self.assertEqual(first["status"], "incomplete")
        owner = first["owner"]

        def shortened(spec, *, handle, **kwargs):
            handle(h.candidate.ready())
            handle(h.candidate.done([], "failed", "agent_error"))
            return h.execution(spec)

        second = self.run_worker(h, shortened)
        self.assertEqual(second["status"], "incomplete")
        self.assertEqual(second["reason"], "owner_prefix")
        self.assertEqual(second["owner"], owner)
        self.assertFalse((h.directory / "completed/0.json").exists())

        def recovered(spec, *, handle, **kwargs):
            handle(h.candidate.ready())
            self.assertEqual(h.exchange(handle, h.candidate.request())["type"], "response")
            handle(h.candidate.done([], "failed", "agent_error"))
            return h.execution(spec)

        final = self.run_worker(h, recovered)
        self.assertEqual(final["disposition"], "candidate_execution_failed")
        self.assertEqual(final["generation"]["gateway_totals"]["operation_count"], 1)
        self.assertEqual(h.physical_sends, 1)
        self.assertEqual(self.inspect(h), final)

    def test_unknown_quota_and_cleanup_remain_incomplete_original_owner(self):
        for kind in ("unknown", "quota", "cleanup", "bool_exit", "missing_done"):
            with self.subTest(kind=kind):
                h = self.prepare_v2(**({"max_callbacks": 0} if kind == "quota" else {}))

                def worker(spec, *, handle, h=h, kind=kind, **kwargs):
                    if kind in {"unknown", "quota"}:
                        handle(h.candidate.ready())
                        stop = h.exchange(handle, h.candidate.request(), timeout=kind == "unknown")
                        self.assertEqual(stop["type"], "stop")
                        handle(h.candidate.done([], "stopped", stop["reason"]))
                    elif kind != "missing_done":
                        handle(h.candidate.done([], "failed", "agent_error"))
                    if kind == "cleanup":
                        h.cleanup = "retained"
                    result = h.execution(spec)
                    if kind == "bool_exit":
                        from dataclasses import replace

                        result = replace(result, exit_code=False)
                    return result

                report = self.run_worker(h, worker, paid=True)
                self.assertEqual(report["status"], "incomplete")
                self.assertFalse((h.directory / "completed/0.json").exists())
                self.assertTrue((h.directory / report["observation"]).is_file())
                if kind == "unknown":
                    self.assertGreater(report["authorization"]["reserved_microusd"], 0)
                if kind == "quota":
                    self.assertEqual(report["authorization"]["operation_count"], 0)

    def test_cancelled_attempt_keeps_raw_session_and_observation(self):
        h = self.prepare_v2()

        def worker(spec, *, handle, **kwargs):
            handle(h.candidate.ready())
            raise KeyboardInterrupt

        with self.assertRaises(KeyboardInterrupt):
            self.run_worker(h, worker)
        observations = list((h.directory / "observations").glob("*.json"))
        self.assertEqual(len(observations), 1)
        observation = json.loads(observations[0].read_bytes())
        self.assertEqual(observation["reason"], "cancelled")
        self.assertEqual(observation["generation"]["reason"], "cancelled")
        self.assertIsNone(observation["outcome"])
        self.assertFalse((h.directory / "completed/0.json").exists())

    def test_passive_publication_and_independent_seal_forgeries_reject(self):
        from buddha.candidate_generation import CandidateGenerationError

        h = self.prepare_v2()

        def worker(spec, *, handle, **kwargs):
            handle(h.candidate.done([], "failed", "agent_error"))
            return h.execution(spec)

        report = self.run_worker(h, worker)
        self.assertEqual(self.inspect(h), report)
        path = h.directory / "report.json"
        raw = path.read_bytes()
        seal = h.directory / "completed/0.json"
        seal_raw = seal.read_bytes()
        try:
            changed = json.loads(raw)
            changed["outcome"]["terminal"]["sequence"] = False
            path.write_bytes(_json(changed))
            with self.assertRaises(CandidateGenerationError):
                self.inspect(h)
            changed = json.loads(raw)
            seal.write_bytes(seal_raw + b"\n")
            digest = hashlib.sha256(seal.read_bytes()).hexdigest()
            changed["stage_seal_sha256"] = digest
            changed["source_generation"]["stage_seal_sha256"] = digest
            path.write_bytes(_json(changed))
            with self.assertRaises(CandidateGenerationError):
                self.inspect(h)
        finally:
            path.write_bytes(raw)
            seal.write_bytes(seal_raw)
        self.assertEqual(self.inspect(h), report)

    def test_v1_pre_ready_agent_error_keeps_original_strict_protocol(self):
        h = session_fixtures.CandidateSessionTests("runTest")
        h.setUp()
        self.addCleanup(h.doCleanups)
        session = h.session()

        def worker(spec, *, handle, **kwargs):
            with self.assertRaises(h.Error):
                handle(h.done([], "failed", "agent_error"))
            self.assertTrue(session.broken)
            raise ExecutorError("protocol", cleanup_status="removed", container_id="f" * 64)

        with patch("buddha.executor.run_container", side_effect=worker):
            report = session.run()
        self.assertEqual(report["status"], "failed")
        self.assertEqual(report["reason"], "execution")
        self.assertIsNone(session.done)
        self.assertFalse(h.output.joinpath("answers.json").exists())
        self.assertEqual(json.loads(h.output.joinpath("report.json").read_bytes()), report)
