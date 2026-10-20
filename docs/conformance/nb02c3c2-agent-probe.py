"""Actual confined fixed-seed generation with synthetic HTTPS and no host seed execution.

Run once as documented in FROZEN-SEED.md after preparing the sealed C3A image.
Only reviewed seed bytes are copied; the production worker loads them in Docker.
"""

import base64
import hashlib
import json
import os
import shutil
import sqlite3
import sys
import tempfile
import time
from collections import Counter
from contextlib import closing
from dataclasses import asdict
from datetime import UTC, datetime
from pathlib import Path
from unittest.mock import patch

if sys.flags.optimize:
    raise RuntimeError("Run this proof with ordinary Python; optimized assertions are disabled")

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from buddha.agent_run import HOST_FILES, RUNNER_FILES, AgentSession  # noqa: E402
from buddha.answers import Answers, TaskSet  # noqa: E402
from buddha.authorization import Authorization  # noqa: E402
from buddha.executor import OWNER_LABEL, Limits, _control, _endpoint  # noqa: E402
from buddha.gateway import (  # noqa: E402
    Gateway,
    RawHTTPTransport,
    ReceivedReply,
    _core_sources,
    prepare_gateway,
)
from buddha.provider import ModelSpec  # noqa: E402
from buddha.releases import Release, _json, inventory, prepare_selection  # noqa: E402

IMAGE = "sha256:d9476e5c6baf21ba4e70709b96100bdc7fe30637e59a377432690088c8dc77c1"
ENV_PATH = ROOT / "docs/conformance/nb02c3-runtime-environment.json"
ENV_SHA = "dc58b658821a536d13c300b6b1f756aa8dc3b2adcc5699627a4827f8361f7d9a"
SEED_PATH = ROOT / "agents/frozen_seed.py"
SEED_SHA = "2b87bfe0d3c97ee45db2d45260985ffe0234eca93967f4689fb7c59f82603921"
CAPS = {"openai": "openai.chat-completions.v1", "anthropic": "anthropic.messages.v1"}
KEYS = {name: "offline-c3c2-not-a-real-" + name + "-key" for name in CAPS}
SCRIPT = Path(__file__).resolve()


def sha(raw):
    return hashlib.sha256(raw).hexdigest()


def save(path, value):
    path.write_bytes((json.dumps(value, indent=2, sort_keys=True) + "\n").encode())


def sample(index):
    # Expected effective strings are fixture declarations, not host seed execution.
    return (
        ("poor duplicate", "poor duplicate", "ordinary"),
        ("poor duplicate", "poor duplicate", "ordinary"),
        (" \n", "[empty]", "ordinary"),
        ("raw declined content", "[refused]", "refusal"),
        (" unfinished JSON {", " unfinished JSON {", "truncated"),
    )[index % 5]


class Connection:
    def __init__(self, owner, host, **options):
        assert host == ("api.openai.com" if owner.provider == "openai" else "api.anthropic.com")
        assert options == {"timeout": 15}
        self.owner = owner

    def request(self, method, path, *, body, headers):
        owner = self.owner
        assert method == "POST"
        assert path == ("/v1/chat/completions" if owner.provider == "openai" else "/v1/messages")
        assert (
            headers.get("Authorization") == "Bearer " + KEYS[owner.provider]
            if owner.provider == "openai"
            else headers.get("x-api-key") == KEYS[owner.provider]
        )
        self.index = len(owner.sends)
        owner.sends.append(
            {"body_sha256": sha(body), "model": json.loads(body)["model"], "at": time.monotonic()}
        )

    def getresponse(self):
        if self.owner.mode == "timeout":
            raise TimeoutError("synthetic timeout after physical attempt")
        if self.owner.mode == "wall":
            self.owner.callback_entered = time.monotonic()
            time.sleep(9)
            self.owner.callback_finished = time.monotonic()
        return self

    status = 200

    def read(self, maximum):
        owner = self.owner
        literal, _, kind = sample(self.index)
        if owner.provider == "openai":
            payload = {
                "model": owner.model,
                "service_tier": "default",
                "choices": [
                    {
                        "message": {
                            "content": literal,
                            "refusal": "declined" if kind == "refusal" else None,
                        },
                        "finish_reason": "length" if kind == "truncated" else "stop",
                    }
                ],
                "usage": {"prompt_tokens": 5, "completion_tokens": 3},
            }
        else:
            payload = {
                "model": owner.model,
                "content": [{"type": "text", "text": literal}],
                "stop_reason": "refusal"
                if kind == "refusal"
                else "max_tokens"
                if kind == "truncated"
                else "end_turn",
                "usage": {"input_tokens": 5, "output_tokens": 3},
            }
        if owner.mode == "unknown":
            payload.pop("usage")
        elif owner.mode == "malformed":
            payload["choices"] = []
        raw = _json(payload)
        assert len(raw) < maximum
        return raw

    def getheaders(self):
        return [
            (
                "x-request-id" if self.owner.provider == "openai" else "request-id",
                "synthetic-generation-" + str(self.index),
            ),
            ("content-type", "application/json"),
        ]

    def close(self):
        pass


class ObservedSession(AgentSession):
    def __init__(self, *args, **kwargs):
        self.requests, self.initial_tasks = [], []
        super().__init__(*args, **kwargs)

    def handle(self, frame):
        if frame.get("type") == "ready":
            initial = self.worker
            assert set(initial) == {
                "type",
                "format",
                "roots",
                "inventories",
                "entrypoint",
                "agent_sha256",
                "config",
                "task",
                "task_index",
            }
            assert set(initial["inventories"]) == {"agent", "runner"}
            assert initial["roots"] == {"agent": "/agent", "runner": "/runner"}
            assert set(initial["task"]) == {"id", "prompt", "count"}
            for forbidden in (
                b"HIDDEN_ROW_SENTINEL",
                b"SELECTED_METADATA_SENTINEL",
                b"dataset_base64",
                *[key.encode() for key in KEYS.values()],
            ):
                assert forbidden not in _json(initial)
            self.initial_tasks.append(initial["task"])
        elif frame.get("type") == "request":
            raw = base64.b64decode(frame["body_base64"], validate=True)
            self.requests.append(
                {
                    "task_index": self.task_index,
                    "task": self.worker["task"],
                    "sequence": frame["sequence"],
                    "body_sha256": sha(raw),
                    "body": json.loads(raw),
                }
            )
        return super().handle(frame)


class Fixture:
    def __init__(
        self,
        parent,
        label,
        environment,
        *,
        provider="openai",
        sampling="regenerate",
        count=2,
        mode="valid",
        budget=5_000_000,
    ):
        self.directory = directory = parent / label
        directory.mkdir()
        self.provider, self.model, self.mode = provider, "seed-" + provider + "-fixture", mode
        self.sends = []
        self.callback_entered = self.callback_finished = None
        roots = {
            role: directory / role
            for role in ("official", "runner", "agent", "environment", "host")
        }
        for path in roots.values():
            path.mkdir()
        for name in RUNNER_FILES:
            target = roots["runner"] / "buddha" / (name + ".py")
            target.parent.mkdir(exist_ok=True)
            target.write_bytes((ROOT / "buddha" / (name + ".py")).read_bytes())
        seed = SEED_PATH.read_bytes()
        assert sha(seed) == SEED_SHA
        (roots["agent"] / "frozen_seed.py").write_bytes(seed)
        (roots["environment"] / "image.json").write_bytes(
            _json({"image": IMAGE, "source_environment_sha256": ENV_SHA})
        )
        (roots["official"] / "unused.py").write_bytes(
            b"raise AssertionError('must never be mounted or executed')\n"
        )
        (roots["official"] / "fixture.lock").write_bytes(
            b"synthetic task interface only; no evaluator installed here\n"
        )
        self.rows = [
            {
                "qid": 1,
                "question": "Give one literal digit, numeric task.",
                "category": "SELECTED_METADATA_SENTINEL",
            },
            {
                "qid": "1",
                "question": "Give one literal digit, text task.",
                "prompt_paraphrases": ["retained source wording"],
                "nested": {"literal": [False, None]},
            },
            {"qid": "hidden", "question": "HIDDEN_ROW_SENTINEL", "split": "unselected"},
        ]
        self.dataset = b"".join(_json(row) + b"\n" for row in self.rows)
        (roots["official"] / "tasks.jsonl").write_bytes(self.dataset)
        release = Release.from_record(
            {
                "format": "buddha.benchmark-release.v1",
                "benchmark": "generation-interface-fixture",
                "release": "typed-count-" + str(count),
                "upstream": {
                    "url": "https://example.org/synthetic-interface",
                    "revision": "a" * 40,
                },
                "source": inventory(roots["official"]),
                "dependency_lock": "fixture.lock",
                "task": {
                    "dataset": "tasks.jsonl",
                    "id_field": "qid",
                    "prompt_field": "question",
                    "answers_field": "replies",
                    "count": count,
                },
                "commands": [{"module": "unused", "argv": ["{artifacts}"]}],
                "artifacts": {
                    "answers": "renamed-answers.jsonl",
                    "results": ["unused-result.jsonl"],
                    "summary": "unused-summary.json",
                },
                "requires": [CAPS[provider]],
            }
        )
        self.tasks = TaskSet.from_dataset(release, self.dataset).select(["1", 1])
        self.tasks_path = directory / "tasks.json"
        self.tasks_path.write_bytes(self.tasks.to_bytes())
        spec = ModelSpec(
            provider,
            self.model,
            100_000,
            100,
            1_000_000,
            2_000_000,
            "https://example.org/offline-synthetic-bounds",
        )
        (roots["host"] / "profiles.json").write_bytes(
            _json(
                {
                    "format": "buddha.gateway-profiles.v1",
                    "profiles": {
                        "seed": {
                            "spec": asdict(spec),
                            "response_models": [self.model],
                            "request_tiers": ["default", "standard_only"],
                            "response_tiers": ["", "default"],
                            "allow_omitted_tier": True,
                        }
                    },
                }
            )
        )
        self.config = {
            "provider": provider,
            "model": self.model,
            "max_output_tokens": 100,
            "instructions": "Follow literal requirements.",
            "sampling": sampling,
        }
        self.descriptor = directory / "generation.json"
        docker = shutil.which("docker")
        assert docker
        self.docker, self.endpoint = docker, _endpoint(docker)
        self.descriptor.write_bytes(
            _json(
                {
                    "format": "buddha.frozen-generation.v1",
                    "tasks": str(self.tasks_path),
                    "config": self.config,
                    "entrypoint": "frozen_seed.py",
                    "profile": {"capability": CAPS[provider], "profile_id": "seed"},
                    "executor": {
                        "image_id": IMAGE,
                        "role": "agent",
                        "mounts": [
                            ["/agent", str(roots["agent"])],
                            ["/runner", str(roots["runner"])],
                        ],
                        "runner_entrypoint": "buddha/agent_worker.py",
                        "limits": asdict(Limits(wall_seconds=4 if mode == "wall" else 60)),
                        "image_environment": [
                            item.split("=", 1) for item in environment["config"]["Env"]
                        ],
                        "docker_endpoint": self.endpoint,
                    },
                }
            )
        )
        self.selection = prepare_selection(
            release, roots, capabilities={CAPS[provider]: "profiles.json"}
        )
        self.authority = Authorization.create(
            directory / "authorization.sqlite3",
            authorization_id=label,
            budget_microusd=budget,
            max_calls=40,
            scope="offline confined fixed-seed proof; never live",
        )
        self.run_dir = prepare_gateway(
            directory / "run",
            selection=self.selection,
            roots=roots,
            authorization=self.authority,
            budget_microusd=budget,
            max_calls=40,
            input_files=[
                SCRIPT,
                SEED_PATH,
                self.descriptor,
                self.tasks_path,
                *[ROOT / "buddha" / (name + ".py") for name in HOST_FILES],
            ],
            review={
                "checked_on": datetime.now(UTC).date().isoformat(),
                "credential_sha256": {provider: sha(KEYS[provider].encode())},
                "account_scope": "synthetic fixtures only",
            },
            run_id=label,
        )

    def containers(self):
        return sorted(
            _control(
                self.docker,
                [
                    "--host",
                    self.endpoint,
                    "container",
                    "ls",
                    "-a",
                    "--no-trunc",
                    "--format",
                    "{{.ID}}",
                    "--filter",
                    "label=" + OWNER_LABEL,
                ],
            )
            .decode("ascii")
            .split()
        )

    def run(self, *, output="output", replay=False, interrupt=False):
        gateway = Gateway(
            self.run_dir, transport=RawHTTPTransport(allow_paid=not replay, timeout_seconds=15)
        )
        session = ObservedSession(
            gateway, descriptor=self.descriptor, output=self.directory / output
        )
        previous = len(self.sends)
        original = RawHTTPTransport.send_prepared
        fired = False

        def received(transport, prepared):
            nonlocal fired
            envelope = original(transport, prepared)
            if interrupt and not fired:
                fired = True
                raise ReceivedReply(envelope, KeyboardInterrupt())
            return envelope

        keys = {
            name: value
            for name, value in os.environ.items()
            if name not in {"OPENAI_API_KEY", "ANTHROPIC_API_KEY"}
        }
        if not replay:
            keys.update(
                {
                    "OPENAI_API_KEY" if self.provider == "openai" else "ANTHROPIC_API_KEY": KEYS[
                        self.provider
                    ]
                }
            )
        report, interrupted = None, False
        containers_before = self.containers()
        started = time.monotonic()
        with (
            patch.dict(os.environ, keys, clear=True),
            patch(
                "http.client.HTTPSConnection",
                side_effect=AssertionError("replay prepared HTTPS")
                if replay
                else lambda host, **options: Connection(self, host, **options),
            ),
            patch("socket.create_connection", side_effect=AssertionError("real network forbidden")),
            patch.object(RawHTTPTransport, "send_prepared", received),
        ):
            try:
                report = session.run()
            except KeyboardInterrupt:
                assert interrupt and fired
                interrupted = True
        returned = time.monotonic()
        containers_after = self.containers()
        assert not set(containers_after) - set(containers_before), "owned container left behind"
        with closing(sqlite3.connect(gateway.ledger.path)) as connection:
            ids = [
                row[0]
                for row in connection.execute(
                    "SELECT operation_id FROM operations ORDER BY operation_id"
                )
            ]
        operations = []
        for identifier in ids:
            operation = gateway.ledger.get(identifier)
            receipt = operation.response
            operations.append(
                {
                    "operation_id": identifier,
                    "status": operation.status,
                    "reserve_microusd": operation.reserve_microusd,
                    "actual_microusd": operation.actual_microusd,
                    "receipt_sha256": None if receipt is None else sha(_json(receipt)),
                    "request": None if receipt is None else receipt["request"],
                }
            )
        result = {
            "label": self.directory.name,
            "report": report,
            "interrupted": interrupted,
            "owned_containers_before": containers_before,
            "owned_containers_after": containers_after,
            "requests": session.requests,
            "initial_tasks": session.initial_tasks,
            "new_sends": self.sends[previous:],
            "ledger": gateway.ledger.totals(),
            "operations": operations,
            "elapsed_seconds": returned - started,
            "callback_entered": self.callback_entered,
            "callback_finished": self.callback_finished,
            "returned_after_callback": self.callback_finished is None
            or returned >= self.callback_finished,
        }
        print(
            json.dumps(
                {
                    "label": self.directory.name,
                    "replay": replay,
                    "status": "interrupted" if interrupted else report["status"],
                    "new_sends": len(result["new_sends"]),
                }
            ),
            flush=True,
        )
        return result

    def complete(self, observed):
        report = observed["report"]
        assert (
            report["status"] == "complete"
            and report["completed_tasks"] == report["expected_tasks"] == 2
        )
        outputs = Answers.from_bytes((self.directory / "output/answers.json").read_bytes())
        expected = [
            {
                "task_id": task.id,
                "answers": [
                    sample(index * task.count + position)[1] for position in range(task.count)
                ],
            }
            for index, task in enumerate(self.tasks.tasks)
        ]
        assert outputs.to_record()["outputs"] == expected
        assert outputs.to_record()["metadata"] == {}
        assert outputs.to_record()["tasks_sha256"] == self.tasks.fingerprint()
        assert outputs.to_record()["agent_sha256"] == self.selection.agent_sha256
        native = [json.loads(line) for line in outputs.native_bytes().splitlines()]
        for row, source, expected_row in zip(
            native, [self.rows[1], self.rows[0]], expected, strict=True
        ):
            assert row == source | {"replies": expected_row["answers"]}
        assert [type(row["qid"]) for row in native] == [str, int]
        requests = observed["requests"]
        logical = [
            sha(
                _json(
                    [
                        "buddha.seed-call.v1",
                        self.selection.agent_sha256,
                        sha(_json(self.config)),
                        row["task_index"],
                        row["task"],
                        row["sequence"],
                    ]
                )
            )
            for row in requests
        ]
        stored = [operation["request"]["logical_id"] for operation in observed["operations"]]
        assert Counter(logical) == Counter(stored) and len(set(stored)) == len(stored)
        assert all(operation["request"]["attempt"] == 0 for operation in observed["operations"])
        if self.config["sampling"] == "regenerate":
            assert len({request["body_sha256"] for request in requests}) == 2
            assert len(stored) > 2
        for execution in report["executions"]:
            assert execution["exit_code"] == 0 and execution["cleanup_status"] == "removed"
            configuration = execution["configuration"]
            assert configuration["role"] == "agent" and set(configuration["mounts"]) == {
                "/agent",
                "/runner",
            }
            assert (
                configuration["host"]["NetworkMode"] == "none"
                and configuration["host"]["ReadonlyRootfs"]
            )
        observed["ordered_outputs"] = expected
        observed["native_bytes_sha256"] = sha(outputs.native_bytes())
        assert observed["ledger"]["reserved_microusd"] == 0


def main():
    assert sha(ENV_PATH.read_bytes()) == ENV_SHA and sha(SEED_PATH.read_bytes()) == SEED_SHA
    environment = json.loads(ENV_PATH.read_bytes())
    assert environment["image"].split("@")[-1] == IMAGE
    assert "agents.frozen_seed" not in sys.modules
    paths = [
        SCRIPT,
        ENV_PATH,
        SEED_PATH,
        *[ROOT / "buddha" / (name + ".py") for name in HOST_FILES],
    ]
    before = {str(path.relative_to(ROOT)): sha(path.read_bytes()) for path in paths}
    core = _core_sources()
    evidence = {
        "format": "buddha.review.nb02c3c2-agent-proof.v1",
        "image": IMAGE,
        "actual_provider_calls": 0,
        "host_seed_import_or_execution": False,
        "official_evaluator_execution": False,
        "cases": [],
        "checks": [],
    }
    with tempfile.TemporaryDirectory(dir=ROOT / "runs/reviews") as temporary:
        parent = Path(temporary)
        for provider, sampling, count in (
            ("openai", "regenerate", 2),
            ("openai", "in-context", 10),
            ("anthropic", "regenerate", 10),
            ("anthropic", "in-context", 2),
        ):
            fixture = Fixture(
                parent,
                provider + "-" + sampling,
                environment,
                provider=provider,
                sampling=sampling,
                count=count,
            )
            observed = fixture.run()
            fixture.complete(observed)
            assert len(observed["new_sends"]) == count * 2
            evidence["cases"].append(observed)
            if provider == "openai" and sampling == "regenerate":
                fixture.authority.deactivate(fixture.directory.name, "completed fixed-seed proof")
                replay = fixture.run(output="replay", replay=True)
                assert replay["report"]["status"] == "complete" and replay["new_sends"] == []
                assert replay["ledger"] == observed["ledger"]
                assert (fixture.directory / "output/answers.json").read_bytes() == (
                    fixture.directory / "replay/answers.json"
                ).read_bytes()
                evidence["checks"].append({"kind": "inactive-keyless-complete-replay", **replay})
        interrupted = Fixture(parent, "received-interruption", environment)
        prefix = interrupted.run(output="interrupted", interrupt=True)
        assert prefix["interrupted"] and prefix["ledger"]["operation_count"] == 1
        assert prefix["operations"][0]["status"] == "completed"
        resumed = interrupted.run()
        interrupted.complete(resumed)
        assert len(resumed["new_sends"]) == 3 and resumed["ledger"]["operation_count"] == 4
        evidence["cases"].append(
            {"kind": "same-owner-interrupted-continuation", "prefix": prefix, **resumed}
        )
        for mode in ("unknown", "timeout", "malformed", "authority", "wall"):
            fixture = Fixture(
                parent, mode, environment, mode=mode, budget=1 if mode == "authority" else 5_000_000
            )
            observed = fixture.run()
            assert not (fixture.directory / "output/answers.json").exists()
            assert observed["report"]["status"] == (
                "failed" if mode in {"malformed", "wall"} else "stopped"
            )
            if mode in {"unknown", "timeout"}:
                assert (
                    len(observed["new_sends"]) == 1 and observed["ledger"]["reserved_microusd"] > 0
                )
                assert (
                    observed["ledger"]["spent_microusd"] == 0
                    and observed["operations"][0]["status"] == "unknown"
                )
            elif mode == "authority":
                assert observed["new_sends"] == [] and observed["ledger"]["operation_count"] == 0
            else:
                assert (
                    len(observed["new_sends"]) == 1 and observed["ledger"]["spent_microusd"] == 11
                )
                assert (
                    observed["ledger"]["reserved_microusd"] == 0
                    and observed["operations"][0]["status"] == "completed"
                )
            if mode == "wall":
                assert (
                    observed["callback_entered"] is not None
                    and observed["callback_finished"] is not None
                )
                assert observed["returned_after_callback"]
                assert observed["report"]["executions"][0]["cleanup_status"] == "removed"
            evidence["cases"].append(observed)
    evidence["source_sha256"] = {
        str(path.relative_to(ROOT)): sha(path.read_bytes()) for path in paths
    }
    assert evidence["source_sha256"] == before and _core_sources() == core
    assert "agents.frozen_seed" not in sys.modules and "_buddha_frozen_seed" not in sys.modules
    evidence["gateway_core_sha256"] = core
    evidence["limits"] = [
        "reviewed fixed C3C1 seed only; arbitrary/evolved agents are not enabled",
        "C3A sealed image reused without installation; no SDK or official judging in this proof",
        "C1 Answers require full generation; native evaluation/promotion remain separate",
        "27 host/18 worker tests separately cover bundle, extra-data and input denials",
    ]
    output = ROOT / "runs/reviews/nb02c3c2-agent-evidence.json"
    save(output, evidence)
    print(
        json.dumps(
            {
                "cases": len(evidence["cases"]),
                "checks": len(evidence["checks"]),
                "actual_provider_calls": 0,
                "evidence": str(output),
            }
        ),
        flush=True,
    )


if __name__ == "__main__":
    main()
