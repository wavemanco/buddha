"""Supplied protocol workers for the bounded two-package cell-witness fixture.

No selected Python runs here. Existing host sessions, Gateway identity,
authorization and stage seals remain real; container and HTTPS replies are
supplied. The caller owns preparation, scheduling and cut validation.
"""

import base64
import hashlib
import json
import os
import shutil
import subprocess
import sys
import tempfile
import unittest
from contextlib import contextmanager
from pathlib import Path
from unittest.mock import patch


def _sha(raw):
    return hashlib.sha256(raw).hexdigest()


@contextmanager
def supplied_workers(runtime_sha256, *, interrupt_role=None):
    """Yield (send counts, role trace); keep the real host environment intact.

    An interruption happens only after a durable response, before DONE. Calling
    again without interrupt_role exercises the ordinary same-operation replay.
    """
    from test_gateway import KEY, GatewayTests
    from test_improver_study import LITERAL, source

    from buddha.executor import ExecutionResult, ExecutorError
    from buddha.native_run import CHUNK_BYTES
    from buddha.releases import _json, inventory

    sends, trace = [], []
    helper = GatewayTests("runTest")

    def exchange(handle, frame, role, content="supplied fixture reply"):
        response = helper.response(
            choices=[{"finish_reason": "stop", "message": {"content": content}}]
        )
        connection = helper.connection(response)
        with patch("http.client.HTTPSConnection", return_value=connection):
            reply = handle(frame)
        sends.append(connection.request.call_count)
        assert reply is not None and reply["type"] == "response"
        if role == interrupt_role:
            raise ExecutorError(
                "supplied interruption after durable reply",
                cleanup_status="removed",
                container_id="f" * 64,
            )

    def worker(spec, *, initial, handle, **kwargs):
        improvement = "candidate-improvement-worker" in initial["format"]
        role = (
            "proposal"
            if improvement
            else "generation"
            if spec.role == "agent"
            else "native-" + str(initial["command"]["index"])
        )
        trace.append(
            {
                "role": role,
                "owner": str(handle.__self__.gateway.directory),
                "format": initial["format"],
            }
        )
        if role.startswith("native-"):
            index = initial["command"]["index"]
            inputs = dict(spec.mounts)["/inputs"]
            assert inventory(inputs) == {
                item["source"]: item["sha256"] for item in initial["inputs"]
            }
            audit = {
                module: {
                    "kind": "official",
                    "path": "/official/" + module.replace(".", "/") + ".py",
                    "sha256": initial["inventories"]["official"][module.replace(".", "/") + ".py"],
                }
                for module in initial["hooks"]["modules"]
            }
            handle({"type": "ready", "aliases": [], "audit": audit})
            if index < 2:
                body = _json(
                    {
                        "model": "test-model",
                        "max_completion_tokens": 100,
                        "messages": [{"role": "user", "content": role + " supplied callback"}],
                    }
                )
                exchange(
                    handle,
                    {
                        "type": "request",
                        "seq": 0,
                        "request": {
                            "provider": "openai",
                            "method": "POST",
                            "url": "https://api.openai.com/v1/chat/completions",
                            "body_base64": base64.b64encode(body).decode(),
                            "headers": [],
                            "logical_id": _sha(_json(["cell-fixture-native", index])),
                            "attempt": 0,
                        },
                    },
                    role,
                )
                rows = [
                    json.loads(line)
                    for line in (inputs / initial["inputs"][0]["source"]).read_bytes().splitlines()
                ]
                for row in rows:
                    row.update(partition=[0, 1], distinct=2)
                    row.pop("score", None)
                    if index == 1:
                        row.update(generation_scores=[7, 7], partition_scores=[7, 7], utility=7)
                outputs = {
                    "partitions.jsonl" if index == 0 else "scores.jsonl": b"".join(
                        _json(row) + b"\n" for row in rows
                    )
                }
            else:
                assert index == 2 and not handle.__self__.profiles
                outputs = {"summary.json": b'{"utility":7}\n'}
            for name, raw in outputs.items():
                for offset in range(0, len(raw) or 1, CHUNK_BYTES):
                    part = raw[offset : offset + CHUNK_BYTES]
                    handle(
                        {
                            "type": "file",
                            "path": name,
                            "offset": offset,
                            "eof": offset + len(part) == len(raw),
                            "data_base64": base64.b64encode(part).decode(),
                        }
                    )
            handle({"type": "done", "status": "complete", "reason": "complete", "audit": audit})
        else:
            ready = {
                "type": "ready",
                "agent_sha256": initial["agent_sha256"],
                "runtime_sha256": runtime_sha256,
            }
            ready["feedback_sha256" if improvement else "task_sha256"] = _sha(
                _json(initial["feedback"] if improvement else initial["task"])
            )
            if initial["format"] == "buddha.candidate-improvement-worker.v3":
                ready["parent_agent_sha256"] = initial["parent_bundle"]["agent_sha256"]
            handle(ready)
            label = "witness" if "witness" in handle.__self__.gateway.directory.parts else "counted"
            value = {
                "source": source(label + "-" + initial["agent_sha256"]).decode(),
                "hypothesis": "Supplied bounded fixture source.",
            }
            content = _json(value).decode() if improvement else "supplied generation reply"
            body = _json(
                {
                    "model": "test-model",
                    "max_completion_tokens": 32_768,
                    "messages": [{"role": "user", "content": role + " supplied callback"}],
                }
            )
            exchange(
                handle,
                {
                    "type": "request",
                    "sequence": 0,
                    "provider": "openai",
                    "body_base64": base64.b64encode(body).decode(),
                },
                role,
                content,
            )
            if improvement:
                handle(
                    {
                        "type": "done",
                        "status": "complete",
                        "reason": "complete",
                        "proposal": {
                            "status": "captured",
                            "value": value,
                            "sha256": _sha(_json(value)),
                            "bytes": len(_json(value)),
                        },
                    }
                )
            else:
                assert initial["task"]["count"] == 2
                handle(
                    {
                        "type": "done",
                        "status": "complete",
                        "reason": "complete",
                        "answers": [LITERAL, ""],
                    }
                )
        return ExecutionResult(
            0,
            "f" * 64,
            spec.image_id,
            0,
            0,
            _sha(b""),
            1,
            0.01,
            _json({"fixture": "supplied protocol worker; no confinement evidence"}),
            "removed",
        )

    with (
        patch.dict(os.environ, {"OPENAI_API_KEY": KEY}),
        patch("buddha.executor.run_container", side_effect=worker),
        patch("http.client.HTTPSConnection", side_effect=AssertionError("unsupplied HTTPS")),
    ):
        yield sends, trace


def old_step(destination):
    """One original scheduled action per process; never change its declaration."""
    from test_unified_continuation import save_cut

    from buddha import (
        candidate_improvement,
        improver_study,
        source_screen,
        source_search,
        trial_fence,
    )
    from buddha import native_pipeline as pipeline
    from buddha.authorization import Authorization
    from buddha.gateway import RawHTTPTransport

    metadata = json.loads((destination / "old-bootstrap.json").read_bytes())
    study = Path(metadata["study"])
    target = study / "cells/0/0/0/0/witness"
    authority = Authorization(Path(metadata["grants"]["search"]["path"]))
    at_cut = False
    with (
        supplied_workers(metadata["runtime"]) as (sends, trace),
        trial_fence.work(authority.path, authority._terms(), directory=study, kind="search"),
        pipeline._exclusive(study),
    ):
        reader, state = improver_study._restore(study, authority.path)
        improver_study._check_current(state)
        reader.finish()
        action = state["action"]
        kind, location = action["kind"], action["directory"]
        result = None
        transport = RawHTTPTransport(allow_paid=True)
        if kind == "witness" and location == target:
            at_cut = True
        elif kind == "screen":
            result = source_screen.run_source_screen(location, transport=transport)
        elif kind == "witness":
            result = source_search._advance_witness(
                reader, action["treatment"], authorization=authority, transport=transport
            )
        elif kind == "plan":
            improver_study._write_plan(study, state, action, authority.path)
        elif kind == "prepare_proposal":
            improver_study._prepare_proposal(state, action, authority)
        elif kind == "proposal":
            result = candidate_improvement.run_candidate_improvement(location, transport=transport)
        elif kind == "proposal_capacity":
            source_search._publish_capacity(
                study,
                authority.path,
                location,
                state["record"]["proposal_capacity"],
                child_directory=location / "screen",
            )
        elif kind == "prepare_child":
            source_search._materialize_child_source_for(
                state["screens"][action["position"]["start"]],
                action["proposal"],
                location,
                owner_directory=location / "screen",
                source_copy=True,
            )
            source_screen.prepare_source_screen(
                location / "screen",
                screen=action["child"],
                authorization=authority,
                review=state["review"],
                expected_runtime_sha256=state["runtime"],
                input_bindings=state["controls"],
            )
        else:
            raise AssertionError("unexpected old action " + kind)
        if result is not None:
            assert result.get("status") != "incomplete" and result.get("action") != "incomplete", (
                result
            )
    if at_cut:
        save_cut(destination, metadata, target)
    return {
        "at_cut": at_cut,
        "action": kind,
        "position": action["position"],
        "sends": sends,
        "roles": [r["role"] for r in trace],
    }


def new_step(destination, operation):
    from test_unified_continuation import ref

    from buddha import unified_continuation as api
    from buddha.doctor import _Capture, _owner
    from buddha.gateway import RawHTTPTransport

    path = destination / "continuation.json"
    checked = api.check_witness_continuation(path, expected_sha256=ref(path)["sha256"])
    if operation == "check":
        return checked.summary()
    interruption = (
        operation.removeprefix("interrupt-") if operation.startswith("interrupt-") else None
    )
    with supplied_workers(checked.runtime_sha256, interrupt_role=interruption) as (sends, trace):
        result = api.advance_witness(checked, transport=RawHTTPTransport(allow_paid=True))
    owners = {}
    capture = _Capture(checked.study)
    for role in ("proposal", "generation"):
        owner_path = checked.witness / role / "owners/0"
        if owner_path.exists():
            owner = _owner(capture, owner_path)
            owners[role] = {
                "run_id": owner.run_id,
                "manifest_raw_sha256": _sha((owner_path / "manifest.json").read_bytes()),
                "operation_ids": [op.operation_id for op in owner.operations],
                "accounting": owner.accounting(),
            }
    capture.finish()
    child = result.get("result")
    return {
        "action": result["action"],
        "role": result["role"],
        "sends": sends,
        "roles": [r["role"] for r in trace],
        "owners": owners,
        "witness_status": child.get("status") if isinstance(child, dict) else None,
    }


class CountedCellContinuationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        from test_unified_continuation import descriptor

        cls.temporary = tempfile.TemporaryDirectory()
        cls.addClassCleanup(cls.temporary.cleanup)
        cls.root = Path(cls.temporary.name).resolve()
        cls.project = Path(__file__).absolute().parents[1]
        cls.old = cls.root / "old-host"
        for name in ("buddha", "tests", "docs/conformance"):
            shutil.copytree(
                cls.project / name, cls.old / name, ignore=shutil.ignore_patterns("__pycache__")
            )
        (cls.old / "agents").mkdir()
        shutil.copyfile(cls.project / "agents/frozen_seed.py", cls.old / "agents/frozen_seed.py")
        with (cls.old / "buddha/doctor.py").open("ab") as stream:
            stream.write(b"\n# Literal old-process cell fixture identity.\n")
        cls.payload = cls.root / "payload"
        cls.payload.mkdir()
        cls.run_child("old-setup", old=True)
        cls.old_steps = []
        for _ in range(24):
            result = cls.run_child("old-step", old=True)
            cls.old_steps.append(result)
            if result["at_cut"]:
                break
        else:
            raise AssertionError("bounded old fixture did not reach the counted-cell cut")
        cls.path = descriptor(cls.payload)

    @classmethod
    def run_child(cls, operation, *, old=False):
        source = cls.old if old else cls.project
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
                str(cls.payload),
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

    def test_counted_child_lineage_both_witness_roles_resume_and_complete_without_decision(self):
        from test_unified_continuation import ref

        cut = json.loads(
            Path(json.loads((self.payload / "old.json").read_bytes())["cut"]["path"]).read_bytes()
        )
        parent = json.loads((Path(cut["parent"]["directory"]) / "screen.json").read_bytes())
        self.assertIsNotNone(parent["lineage"])
        self.assertEqual(
            cut["position"],
            {"start": 0, "repetition": 0, "arm": 0, "slot": 0, "stage": "witness_feedback"},
        )
        initial = self.run_child("check")
        self.assertEqual(initial["old_owner_count"], 11)
        self.assertEqual(self.run_child("step")["action"], "prepared")
        interrupted = self.run_child("interrupt-proposal")
        resumed = self.run_child("step")
        self.assertEqual(interrupted["sends"], [1])
        self.assertEqual(resumed["sends"], [0])
        self.assertEqual(interrupted["owners"]["proposal"], resumed["owners"]["proposal"])
        self.assertEqual(self.run_child("step")["action"], "assessed")
        self.assertEqual(self.run_child("step")["action"], "prepared")
        interrupted = self.run_child("interrupt-generation")
        resumed = self.run_child("step")
        self.assertEqual(interrupted["sends"], [1])
        self.assertEqual(resumed["sends"], [0])
        self.assertEqual(interrupted["owners"]["generation"], resumed["owners"]["generation"])
        publication = self.run_child("step")
        self.assertEqual(publication["action"], "published")
        self.assertEqual(publication["witness_status"], "passed")
        complete = self.run_child("check")
        self.assertTrue(complete["witness_complete"])
        report = Path(cut["witness"]) / "report.json"
        saved = ref(report)
        replay = self.run_child("step")
        self.assertEqual(replay["action"], "complete")
        self.assertEqual(replay["sends"], [])
        self.assertEqual(ref(report), saved)
        self.assertFalse((Path(cut["witness"]).parent / "decision.json").exists())


if __name__ == "__main__":
    if len(sys.argv) > 1 and sys.argv[1] == "--fixture":
        destination, operation, source = Path(sys.argv[2]), sys.argv[3], Path(sys.argv[4])
        sys.path[:1] = [str(source / "tests"), str(source)]
        if operation == "old-setup":
            from test_unified_continuation import old_fixture

            old_fixture(destination, setup_only=True, starting_count=1)
            result = {"status": "old_setup_ready"}
        elif operation == "old-step":
            result = old_step(destination)
        else:
            result = new_step(destination, operation)
        print(json.dumps(result), flush=True)
    else:
        unittest.main()
