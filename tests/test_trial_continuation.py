"""Original roots and grants through development, final and both plain modes.

Workers and HTTPS responses are supplied. Literal actor source never executes
on the host; these checks establish engineering custody, not scientific gains.
"""

import base64
import hashlib
import json
import os
import shutil
import subprocess
import sys
import tempfile
import threading
import unittest
from contextlib import contextmanager
from pathlib import Path
from unittest.mock import patch

import test_study_continuation as study_fixture

from buddha import executor, unified_continuation
from buddha.releases import _json


def sha(raw):
    return hashlib.sha256(raw).hexdigest()


def descriptor(destination):
    path = study_fixture.descriptor(destination)
    record = json.loads(path.read_bytes())
    record.update(
        format="buddha.trial-continuation.v1",
        remaining_phases=list(unified_continuation._REMAINING),
    )
    path.write_bytes(_json(record))
    return path


@contextmanager
def supplied(metadata):
    """Reuse candidate/native frames; plain generation uses the real seed request."""
    import test_cell_witness_continuation as cell_fixture
    import test_improver_study as improver_fixture
    from test_agent_run import AgentSessionTests
    from test_gateway import GatewayTests

    from agents import frozen_seed

    helper = GatewayTests("runTest")
    agent = AgentSessionTests("runTest")
    literal_source = improver_fixture.source
    study = Path(metadata["study"])

    def source_for_owner(label):
        owner = Path(trace[-1]["owner"])
        root = study if owner.is_relative_to(study) else study.parent.parent
        relative = owner.relative_to(root).as_posix()
        return literal_source(label + "-" + sha(relative.encode())[:12])

    with (
        patch.object(improver_fixture, "source", side_effect=source_for_owner),
        cell_fixture.supplied_workers(metadata["runtime"]) as (sends, trace),
    ):
        original = executor.run_container

        def worker(spec, *, initial, handle, **options):
            if initial["format"] != "buddha.agent-worker.v1":
                return original(spec, initial=initial, handle=handle, **options)
            trace.append(
                {
                    "role": "plain-generation",
                    "owner": str(handle.__self__.gateway.directory),
                    "format": initial["format"],
                }
            )
            handle(
                {
                    "type": "ready",
                    "agent_sha256": initial["agent_sha256"],
                    "task_sha256": sha(_json(initial["task"])),
                }
            )
            answers = []
            for index in range(initial["task"]["count"]):
                body = frozen_seed.request(initial["config"], initial["task"], answers)
                connection = helper.connection(
                    helper.response(
                        choices=[
                            {
                                "finish_reason": "stop",
                                "message": {"content": "plain fixture answer"},
                            }
                        ]
                    )
                )
                with patch("http.client.HTTPSConnection", return_value=connection):
                    reply = handle(
                        {
                            "type": "request",
                            "sequence": index,
                            "provider": initial["config"]["provider"],
                            "body_base64": base64.b64encode(body).decode(),
                        }
                    )
                assert reply["type"] == "response"
                sends.append(connection.request.call_count)
                raw = json.loads(base64.b64decode(reply["envelope"]["body_base64"]))
                answers.append(frozen_seed.normalize(initial["config"]["provider"], raw))
            handle(agent.done(answers))
            return agent.execution()

        with patch.object(executor, "run_container", side_effect=worker):
            yield sends, trace


class TrialProjectionTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        root = Path(self.temporary.name).resolve()
        self.trial, self.study = root / "trial", root / "trial/search/study"
        self.old, self.new = root / "old/buddha/doctor.py", root / "new/buddha/doctor.py"
        self.data, self.anchor = root / "data.json", root / "continuation.json"
        self.before = {self.old: "a" * 64, self.data: "c" * 64}
        self.after = {self.new: "b" * 64, self.data: "c" * 64, self.anchor: "d" * 64}
        self.checked = unified_continuation.CheckedTrialContinuation(
            path=self.anchor,
            sha256="d" * 64,
            study=self.study,
            witness=self.study / "cells/0/0/1/0/witness",
            _parent=self.study / "cells/0/0/1/0/screen",
            runtime_sha256="e" * 64,
            _before=tuple(self.before.items()),
            _after=tuple(self.after.items()),
            _screen_sha256="f" * 64,
            _policy=b"{}",
            _summary=b"{}",
            _pid=os.getpid(),
            _thread=threading.get_ident(),
            _old_owners=frozenset(),
            _cells=(),
            _screens=frozenset(),
            _authorization=root / "search.sqlite3",
            _profiles=("1" * 64, "2" * 64),
            _trial=self.trial,
            _launch=(root / "original.json", "3" * 64),
            _roles=(("buddha/doctor.py", self.old, "a" * 64, self.new, "b" * 64),),
        )

    def test_source_projection_keeps_old_identity_and_checks_actual_installed_digest(self):
        self.assertEqual(
            self.checked._historical_sources({str(self.new): "b" * 64}, relative=False),
            {str(self.old): "a" * 64},
        )
        self.assertEqual(
            self.checked._historical_sources({"buddha/doctor.py": "b" * 64}, relative=True),
            {"buddha/doctor.py": "a" * 64},
        )
        for supplied_map in (
            {str(self.new): "a" * 64},
            {str(self.new.with_name("unknown.py")): "b" * 64},
        ):
            with (
                self.subTest(value=supplied_map),
                self.assertRaises(unified_continuation.WitnessContinuationError),
            ):
                self.checked._historical_sources(supplied_map, relative=False)

    def test_complete_union_projects_once_without_mutating_original_or_extra_evidence(self):
        extra = self.trial / "search/study/report.json"
        collected = self.before | {extra: "f" * 64}
        frozen = self.checked._phase_controls(self.trial, "final", collected)
        self.assertEqual(frozen, self.after | {extra: "f" * 64})
        self.assertEqual(collected, self.before | {extra: "f" * 64})
        self.assertEqual(self.checked._phase_controls(self.trial, "plain", frozen), frozen)
        for root, phase, values in (
            (self.trial.parent / "other", "final", collected),
            (self.trial, "search", collected),
            (self.trial, "final", collected | {self.old: "e" * 64}),
            (self.trial, "final", collected | {self.new: "e" * 64}),
        ):
            with (
                self.subTest(root=root, phase=phase),
                self.assertRaises(unified_continuation.WitnessContinuationError),
            ):
                self.checked._phase_controls(root, phase, values)


class TrialContinuationTests(unittest.TestCase):
    def child(self, operation):
        source = self.old
        environment = {
            k: v for k, v in os.environ.items() if k not in {"OPENAI_API_KEY", "ANTHROPIC_API_KEY"}
        }
        environment["PYTHONPATH"] = os.pathsep.join((str(source), str(source / "tests")))
        result = subprocess.run(
            [
                sys.executable,
                "-B",
                str(Path(__file__).absolute()),
                "--fixture",
                str(self.payload),
                operation,
                str(source),
            ],
            cwd=source,
            env=environment,
            capture_output=True,
            text=True,
            timeout=180,
        )
        if result.returncode:
            raise AssertionError(result.stdout + result.stderr)
        return json.loads(result.stdout.splitlines()[-1])

    def test_original_grants_complete_development_final_and_both_plain_modes_then_replay_keylessly(
        self,
    ):
        from buddha import final_evaluation, improver_study
        from buddha.authorization import Authorization
        from buddha.gateway import RawHTTPTransport

        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        root = Path(temporary.name).resolve()
        project = Path(__file__).absolute().parents[1]
        self.old, self.payload = root / "old-host", root / "payload"
        for name in ("buddha", "tests", "docs/conformance", "agents"):
            shutil.copytree(
                project / name, self.old / name, ignore=shutil.ignore_patterns("__pycache__")
            )
        with (self.old / "buddha/doctor.py").open("ab") as stream:
            stream.write(b"\n# Literal original combined-trial host identity.\n")
        self.payload.mkdir()
        self.child("old-setup")
        for index in range(48):
            step = self.child("old-step")
            with self.subTest(old_action=index):
                self.assertIs(type(step["at_cut"]), bool)
                self.assertIn("action", step)
            print(f"[trial fixture] old action {index + 1}: {step['action']}", flush=True)
            if step["at_cut"]:
                break
        else:
            self.fail("original trial never reached its bounded counted-cell cut")
        path = descriptor(self.payload)
        metadata = json.loads((self.payload / "old.json").read_bytes())
        cut = json.loads(Path(metadata["cut"]["path"]).read_bytes())
        pin = sha(path.read_bytes())
        checked = unified_continuation.check_trial_continuation(path, expected_sha256=pin)
        self.assertEqual(
            dict(checked._after)[Path(metadata["cut"]["path"])], metadata["cut"]["sha256"]
        )
        self.assertEqual(checked.summary()["old_owner_count"], 18)
        self.assertIsNone(checked.summary()["stop_code"])
        outer = json.loads(checked._launch[0].read_bytes())
        primary = json.loads(Path(outer["primary_launch"]["path"]).read_bytes())
        actions, cells = [], []
        advance, episode = improver_study._advance_action, final_evaluation._episode

        def action(*args, **kwargs):
            kind = args[1]["action"]["kind"]
            result = advance(*args, **kwargs)
            with self.subTest(development_action=len(actions), kind=kind):
                self.assertTrue(result is None or result["status"] == "complete")
            actions.append(kind)
            return result

        @contextmanager
        def cell(*args, **kwargs):
            with episode(*args, **kwargs):
                yield
            location, kind = args[4], args[5]
            with self.subTest(final_cell=len(cells)):
                role = "generation" if kind == "generation" else "evaluation"
                self.assertTrue((location / role / "report.json").is_file())
            cells.append((str(location), kind))

        with (
            supplied(metadata) as (sends, trace),
            patch.object(improver_study, "_advance_action", side_effect=action),
            patch.object(final_evaluation, "_episode", side_effect=cell),
        ):
            result = unified_continuation.launch_trial_continuation(
                path,
                expected_sha256=pin,
                live=True,
                confirm_project_keys=True,
                transport=RawHTTPTransport(
                    allow_paid=True, timeout_seconds=primary["timeout_seconds"]
                ),
                notice=lambda message: print("[trial fixture] " + message, flush=True),
            )
        self.assertEqual(result["status"], "complete", result)
        self.assertTrue(sends)
        self.assertTrue(cells)
        self.assertIn("freeze", actions)
        self.assertIn("publish", actions)
        self.assertTrue(any(row["role"] == "plain-generation" for row in trace))
        for name, anchor in cut["files"].items():
            self.assertEqual(sha(Path(name).read_bytes()), anchor["sha256"], name)
        grants = {
            name: Authorization(Path(value["path"])).summary()
            for name, value in metadata["grants"].items()
        }
        self.assertTrue(all(value["reserved_microusd"] == 0 for value in grants.values()))
        saved = Path(result["publication_path"]).read_bytes()
        with (
            patch.dict(os.environ),
            patch("buddha.executor.run_container", side_effect=AssertionError("replay worker")),
            patch("http.client.HTTPSConnection", side_effect=AssertionError("replay network")),
        ):
            os.environ.pop("OPENAI_API_KEY", None)
            os.environ.pop("ANTHROPIC_API_KEY", None)
            replay = unified_continuation.launch_trial_continuation(path, expected_sha256=pin)
        self.assertEqual(replay, result)
        self.assertEqual(Path(result["publication_path"]).read_bytes(), saved)
        self.assertEqual(
            grants,
            {
                name: Authorization(Path(value["path"])).summary()
                for name, value in metadata["grants"].items()
            },
        )


if __name__ == "__main__":
    if len(sys.argv) > 1 and sys.argv[1] == "--fixture":
        destination, operation, source = Path(sys.argv[2]), sys.argv[3], Path(sys.argv[4])
        sys.path[:1] = [str(source / "tests"), str(source)]
        if operation == "old-setup":
            from test_unified_continuation import old_fixture

            old_fixture(destination, setup_only=True, starting_count=1, opportunities=2)
            result = {"status": "old_setup_ready"}
        else:
            import test_study_continuation as helper

            result = helper.old_step(destination)
        print(json.dumps(result), flush=True)
    else:
        unittest.main()
