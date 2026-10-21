"""Actual candidate containers with synthetic HTTPS; never call a model provider.

Run once from PowerShell with:
  python -B docs/conformance/src01-candidate-probe.py --out runs/reviews/src01-candidate-proof.json
This creates only separate synthetic fixtures/authorizations, runs the installed
SRC runtime, and creates the NEW requested proof file. It spends no API money.
Fixtures are retained under runs/reviews for inspection. Ctrl+C stops the proof;
the executor attempts cleanup only of its own containers. Existing outputs are
never overwritten. This is channel/confinement integration, not model evaluation.
"""

if not __debug__:
    raise RuntimeError("SRC_CANDIDATE_PROOF_REQUIRES_ORDINARY_PYTHON")

import argparse
import base64
import hashlib
import json
import os
import shutil
import sqlite3
import sys
import tempfile
from contextlib import closing
from dataclasses import asdict
from datetime import UTC, datetime
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
sys.dont_write_bytecode = True

from buddha.answers import Answers, TaskSet  # noqa: E402
from buddha.authorization import Authorization  # noqa: E402
from buddha.candidate_run import HOST_FILES, RUNNER_FILES, CandidateSession  # noqa: E402
from buddha.executor import OWNER_LABEL, Limits, _control, _endpoint  # noqa: E402
from buddha.gateway import (  # noqa: E402
    Gateway,
    RawHTTPTransport,
    ReceivedReply,
    _core_sources,
    prepare_gateway,
)
from buddha.provider import ModelSpec  # noqa: E402
from buddha.releases import Release, _json, _root, inventory, prepare_selection  # noqa: E402

SCRIPT = Path(__file__).resolve()
ENV_PATH = ROOT / "docs/conformance/src01-runtime-environment.json"
ENV_SHA = "a7311f68ab4deb2eed770d0454ddd2877250a86b8a72716abac45b4ff6d43951"
CAPS = {"openai": "openai.chat-completions.v1", "anthropic": "anthropic.messages.v1"}
KEYS = {name: "offline-src-candidate-not-real-" + name + "-key" for name in CAPS}

# Reviewed fixture data only. These programs are never compiled/imported on the
# host: the selected production worker consumes them inside the actual container.
PROGRAM = """import json
print("candidate stdout noise")
def generate(task, config, complete):
    if CALL_COUNT == 0:
        choices = [" local \\n", "", "poor duplicate", "poor duplicate"]
        return [choices[i % len(choices)] for i in range(task["count"])]
    last = None
    body = None
    try:
        for ordinal in range(CALL_COUNT):
            content = task["prompt"]
            if NONCE:
                import secrets
                content += secrets.token_hex(16)
            cap = "max_tokens" if config["provider"] == "anthropic" else "max_completion_tokens"
            body = json.dumps({"model":config["model"],cap:max(10,100//(ordinal+1)),
                               "messages":[{"role":"user","content":content}]},
                              sort_keys=True,separators=(",",":")).encode()
            last = complete(config["provider"], body)
    except BaseException:
        if HOSTILE:
            import base64, os
            worker = complete.__self__
            request = {"type":"request","sequence":worker.sequence,
                       "provider":config["provider"],
                       "body_base64":base64.b64encode(body).decode()}
            worker.writer.write((json.dumps(request)+"\\n").encode()); worker.writer.flush()
            worker.reader.readline()
            done = {"type":"done","status":"complete","reason":"complete",
                    "answers":["forged"]*task["count"]}
            worker.writer.write((json.dumps(done)+"\\n").encode()); worker.writer.flush()
            os._exit(0)
        raise
    text = (last["content"][0]["text"] if config["provider"] == "anthropic" else
            last["choices"][0]["message"]["content"])
    return [text for _ in range(task["count"])]
"""


def require(value, label):
    if not value:
        raise RuntimeError(label)


def sha(raw):
    return hashlib.sha256(raw).hexdigest()


def save(path, value):
    with path.open("xb") as stream:
        stream.write((json.dumps(value, indent=2, sort_keys=True, allow_nan=False) + "\n").encode())


def literal(index):
    return (" raw literal \n", "", "poor duplicate")[index % 3]


class Connection:
    def __init__(self, fixture, host, **options):
        self.fixture = fixture
        require(
            host == ("api.openai.com" if fixture.provider == "openai" else "api.anthropic.com"),
            "provider host changed",
        )
        require(options == {"timeout": 15}, "transport timeout changed")

    def request(self, method, path, *, body, headers):
        f = self.fixture
        require(method == "POST", "method changed")
        require(
            path == ("/v1/chat/completions" if f.provider == "openai" else "/v1/messages"),
            "provider endpoint changed",
        )
        credential = (
            headers.get("Authorization") if f.provider == "openai" else headers.get("x-api-key")
        )
        require(
            credential == ("Bearer " if f.provider == "openai" else "") + KEYS[f.provider],
            "synthetic credential differs",
        )
        self.index = len(f.sends)
        f.sends.append({"body_sha256": sha(body), "body": json.loads(body)})

    def getresponse(self):
        if self.fixture.mode == "timeout":
            raise TimeoutError("synthetic uncertain HTTP outcome")
        return self

    status = 200

    def read(self, maximum):
        f = self.fixture
        if f.provider == "openai":
            body = {
                "model": f.model,
                "service_tier": "default",
                "choices": [
                    {
                        "message": {"content": literal(self.index), "refusal": None},
                        "finish_reason": "stop",
                    }
                ],
                "usage": {"prompt_tokens": 5, "completion_tokens": 3},
            }
        else:
            body = {
                "model": f.model,
                "content": [{"type": "text", "text": literal(self.index)}],
                "stop_reason": "end_turn",
                "usage": {"input_tokens": 5, "output_tokens": 3},
            }
        if f.mode == "unknown":
            body.pop("usage")
        raw = _json(body)
        require(len(raw) < maximum, "response exceeds capture ceiling")
        return raw

    def getheaders(self):
        return [
            ("content-type", "application/json"),
            (
                "x-request-id" if self.fixture.provider == "openai" else "request-id",
                "synthetic-src-candidate-" + str(self.index),
            ),
        ]

    def close(self):
        pass


class ObservedSession(CandidateSession):
    def __init__(self, *args, **kwargs):
        self.frames = []
        super().__init__(*args, **kwargs)

    def handle(self, frame):
        self.frames.append(json.loads(_json(frame)))
        initial = _json(self.worker)
        require(set(self.worker["task"]) == {"id", "prompt", "count"}, "unsanitized task")
        require(set(self.worker["roots"]) == {"agent", "runner"}, "extra selected mount")
        for forbidden in (
            b"HIDDEN_ROW_SENTINEL",
            b"SELECTED_METADATA_SENTINEL",
            b"dataset_base64",
            *(value.encode() for value in KEYS.values()),
        ):
            require(forbidden not in initial, "private input or credential crossed channel")
        return super().handle(frame)


class Fixture:
    def __init__(
        self,
        parent,
        label,
        environment,
        *,
        provider="openai",
        count=2,
        callbacks=3,
        quota=3,
        mode="valid",
        hostile=False,
        nonce=False,
    ):
        self.directory = directory = parent / label
        directory.mkdir()
        self.provider, self.model, self.mode = provider, "candidate-" + provider + "-fixture", mode
        self.sends, self.callbacks, self.count = [], callbacks, count
        roots = {
            name: directory / name
            for name in ("official", "runner", "agent", "environment", "host")
        }
        for root in roots.values():
            root.mkdir()
        for name in RUNNER_FILES:
            path = roots["runner"] / "buddha" / (name + ".py")
            path.parent.mkdir(exist_ok=True)
            path.write_bytes((ROOT / "buddha" / (name + ".py")).read_bytes())
        source = PROGRAM.replace("CALL_COUNT", str(callbacks)).replace("HOSTILE", repr(hostile))
        source = source.replace("NONCE", repr(nonce))
        (roots["agent"] / "candidate.py").write_bytes(source.encode())
        runtime_path = roots["environment"] / "runtime.json"
        runtime_path.write_bytes(ENV_PATH.read_bytes())
        self.rows = [
            {"qid": 1, "question": "HIDDEN_ROW_SENTINEL"},
            {
                "qid": "1",
                "question": "One literal response café 🌱.",
                "metadata": "SELECTED_METADATA_SENTINEL",
            },
        ]
        dataset = b"".join(_json(row) + b"\n" for row in self.rows)
        (roots["official"] / "tasks.jsonl").write_bytes(dataset)
        (roots["official"] / "unused.py").write_bytes(
            b"raise RuntimeError('never execute evaluator')\n"
        )
        (roots["official"] / "fixture.lock").write_bytes(b"synthetic interface, no dependencies\n")
        release = Release.from_record(
            {
                "format": "buddha.benchmark-release.v1",
                "benchmark": "candidate-interface-fixture",
                "release": "single-count-" + str(count),
                "upstream": {"url": "https://example.org/offline-fixture", "revision": "a" * 40},
                "source": inventory(roots["official"]),
                "dependency_lock": "fixture.lock",
                "task": {
                    "dataset": "tasks.jsonl",
                    "id_field": "qid",
                    "prompt_field": "question",
                    "answers_field": "answers",
                    "count": count,
                },
                "commands": [{"module": "unused", "argv": ["{artifacts}"]}],
                "artifacts": {
                    "answers": "answers.jsonl",
                    "results": ["unused.jsonl"],
                    "summary": "summary.json",
                },
                "requires": [CAPS[provider]],
            }
        )
        self.tasks = TaskSet.from_dataset(release, dataset).select(["1"])
        tasks_path = directory / "task.json"
        tasks_path.write_bytes(self.tasks.to_bytes())
        spec = ModelSpec(
            provider,
            self.model,
            10000,
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
                        "candidate": {
                            "spec": asdict(spec),
                            "response_models": [self.model],
                            "request_tiers": ["auto", "default"],
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
            "instructions": "Follow the literal task.",
            "sampling": "regenerate",
        }
        self.docker = shutil.which("docker")
        require(self.docker is not None, "Docker unavailable")
        self.endpoint = _endpoint(self.docker)
        self.descriptor = directory / "candidate.json"
        self.descriptor.write_bytes(
            _json(
                {
                    "format": "buddha.candidate-generation.v1",
                    "tasks": str(tasks_path),
                    "config": self.config,
                    "entrypoint": "candidate.py",
                    "max_callbacks": quota,
                    "runtime": {"path": str(runtime_path), "sha256": ENV_SHA},
                    "profile": {"capability": CAPS[provider], "profile_id": "candidate"},
                    "executor": {
                        "image_id": environment["image_id"],
                        "role": "agent",
                        "mounts": [
                            ["/agent", str(roots["agent"])],
                            ["/runner", str(roots["runner"])],
                        ],
                        "runner_entrypoint": "buddha/candidate_worker.py",
                        "limits": asdict(Limits(wall_seconds=30, memory_mib=256)),
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
            budget_microusd=1_000_000,
            max_calls=40,
            scope="offline synthetic candidate proof only; never live",
        )
        self.run_dir = prepare_gateway(
            directory / "run",
            selection=self.selection,
            roots=roots,
            authorization=self.authority,
            budget_microusd=1_000_000,
            max_calls=40,
            input_files=[
                SCRIPT,
                ENV_PATH,
                self.descriptor,
                tasks_path,
                runtime_path,
                *[ROOT / "buddha" / (name + ".py") for name in HOST_FILES],
            ],
            review={
                "checked_on": datetime.now(UTC).date().isoformat(),
                "credential_sha256": {provider: sha(KEYS[provider].encode())},
                "account_scope": "offline synthetic proof; no real account",
            },
            run_id=label,
        )

    def containers(self):
        return set(
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
            .decode()
            .split()
        )

    def prime(self, count):
        """Create a synthetic host-channel prefix, without executing candidate code."""
        gateway = Gateway(
            self.run_dir, transport=RawHTTPTransport(allow_paid=True, timeout_seconds=15)
        )
        session = ObservedSession(
            gateway,
            descriptor=self.descriptor,
            output=self.directory / "host-prefix-only",
            expected_runtime_sha256=ENV_SHA,
        )
        session.handle(
            {
                "type": "ready",
                "agent_sha256": session.agent_sha256,
                "task_sha256": sha(_json(session.worker["task"])),
                "runtime_sha256": session.runtime_sha256,
            }
        )
        credential = "OPENAI_API_KEY" if self.provider == "openai" else "ANTHROPIC_API_KEY"
        safe = {
            key: os.environ[key]
            for key in ("PATH", "SYSTEMROOT", "WINDIR", "TEMP", "TMP", "PROGRAMFILES")
            if key in os.environ
        }
        safe[credential] = KEYS[self.provider]
        replies = []
        with (
            patch.dict(os.environ, safe, clear=True),
            patch(
                "http.client.HTTPSConnection",
                side_effect=lambda host, **options: Connection(self, host, **options),
            ),
            patch("socket.create_connection", side_effect=RuntimeError("real network forbidden")),
        ):
            for ordinal in range(count):
                cap = "max_tokens" if self.provider == "anthropic" else "max_completion_tokens"
                body = _json(
                    {
                        "model": self.model,
                        cap: 100,
                        "messages": [
                            {"role": "user", "content": "synthetic prefix " + str(ordinal)}
                        ],
                    }
                )
                replies.append(
                    session.handle(
                        {
                            "type": "request",
                            "sequence": ordinal,
                            "provider": self.provider,
                            "body_base64": base64.b64encode(body).decode(),
                        }
                    )
                )
        result = {
            "origin": "synthetic host.handle prefix; no earlier candidate execution",
            "frames": session.frames,
            "replies": replies,
            "ledger": gateway.ledger.totals(),
        }
        save(self.directory / "host-prefix-proof.json", result)
        return result

    def run(self, output="output", *, keyless=False, interrupt=False):
        gateway = Gateway(
            self.run_dir, transport=RawHTTPTransport(allow_paid=not keyless, timeout_seconds=15)
        )
        session = ObservedSession(
            gateway,
            descriptor=self.descriptor,
            output=self.directory / output,
            expected_runtime_sha256=ENV_SHA,
        )
        previous, original, fired = len(self.sends), RawHTTPTransport.send_prepared, False

        def received(transport, prepared):
            nonlocal fired
            envelope = original(transport, prepared)
            if interrupt and not fired:
                fired = True
                raise ReceivedReply(envelope, KeyboardInterrupt())
            return envelope

        # Never read, log or use an operator's model keys or other account secrets.
        safe = {
            key: os.environ[key]
            for key in ("PATH", "SYSTEMROOT", "WINDIR", "TEMP", "TMP", "PROGRAMFILES")
            if key in os.environ
        }
        if not keyless:
            safe["OPENAI_API_KEY" if self.provider == "openai" else "ANTHROPIC_API_KEY"] = KEYS[
                self.provider
            ]
        before = self.containers()
        interrupted, report = False, None
        with (
            patch.dict(os.environ, safe, clear=True),
            patch(
                "http.client.HTTPSConnection",
                side_effect=(
                    lambda *a, **k: (_ for _ in ()).throw(RuntimeError("keyless HTTPS forbidden"))
                )
                if keyless
                else lambda host, **options: Connection(self, host, **options),
            ),
            patch(
                "socket.create_connection",
                side_effect=RuntimeError("real provider network forbidden"),
            ),
            patch.object(RawHTTPTransport, "send_prepared", received),
        ):
            try:
                report = session.run()
            except KeyboardInterrupt:
                require(interrupt and fired, "unexpected cancellation")
                interrupted = True
                report = json.loads((self.directory / output / "report.json").read_bytes())
        after = self.containers()
        require(not after - before, "owned container not removed")
        with closing(sqlite3.connect(":memory:")) as db:
            db.deserialize(gateway.ledger.path.read_bytes())
            db.execute("PRAGMA query_only=ON")
            ids = [
                row[0]
                for row in db.execute("SELECT operation_id FROM operations ORDER BY operation_id")
            ]
        operations = []
        for identifier in ids:
            op = gateway.ledger.get(identifier)
            receipt = op.response
            operations.append(
                {
                    "operation_id": identifier,
                    "status": op.status,
                    "reserve_microusd": op.reserve_microusd,
                    "actual_microusd": op.actual_microusd,
                    "receipt_sha256": None if receipt is None else sha(_json(receipt)),
                    "request": None if receipt is None else receipt["request"],
                }
            )
        result = {
            "label": self.directory.name,
            "fixture": str(self.directory),
            "report": report,
            "interrupted": interrupted,
            "frames": session.frames,
            "new_sends": self.sends[previous:],
            "ledger": gateway.ledger.totals(),
            "operations": operations,
            "owned_containers_before": sorted(before),
            "owned_containers_after": sorted(after),
        }
        if (self.directory / output / "answers.json").exists():
            answers = Answers.from_bytes((self.directory / output / "answers.json").read_bytes())
            result["answers"] = answers.to_record()["outputs"]
            result["native_bytes_sha256"] = sha(answers.native_bytes())
            require(answers.to_record()["metadata"] == {}, "unexpected answer metadata")
            require(
                answers.to_record()["agent_sha256"] == self.selection.agent_sha256,
                "source provenance changed",
            )
            require(
                json.loads(answers.native_bytes())
                == self.rows[1] | {"answers": result["answers"][0]["answers"]},
                "C1 source roundtrip changed",
            )
        save(self.directory / (output + "-proof.json"), result)
        print(
            json.dumps(
                {
                    "label": self.directory.name,
                    "output": output,
                    "status": report["status"],
                    "reason": report["reason"],
                    "new_sends": len(result["new_sends"]),
                }
            ),
            flush=True,
        )
        return result


def main(output):
    output = output.absolute()
    require(output.is_relative_to(ROOT) and ".." not in output.parts, "output outside checkout")
    _root(output.parent)
    require(not output.exists(), "proof output must be new")
    require(sha(ENV_PATH.read_bytes()) == ENV_SHA, "reviewed runtime artifact changed")
    environment = json.loads(ENV_PATH.read_bytes())
    sources = {
        str(path.relative_to(ROOT)): sha(path.read_bytes())
        for path in [SCRIPT, ENV_PATH, *[ROOT / "buddha" / (name + ".py") for name in HOST_FILES]]
    }
    core = _core_sources()
    parent = Path(
        tempfile.mkdtemp(prefix="src01-candidate-proof-", dir=ROOT / "runs/reviews")
    ).resolve()
    evidence = {
        "format": "buddha.src01-candidate-proof.v1",
        "status": "running",
        "fixture_directory": str(parent),
        "image_id": environment["image_id"],
        "environment_sha256": ENV_SHA,
        "real_provider_calls": 0,
        "host_candidate_execution": False,
        "official_evaluator_execution": False,
        "cases": [],
        "checks": [],
    }
    for provider, count, callbacks in (
        ("openai", 2, 0),
        ("openai", 10, 1),
        ("openai", 2, 3),
        ("anthropic", 10, 0),
        ("anthropic", 2, 1),
        ("anthropic", 10, 3),
    ):
        label = provider + "-" + str(callbacks) + "-calls"
        fixture = Fixture(
            parent, label, environment, provider=provider, count=count, callbacks=callbacks
        )
        observed = fixture.run()
        require(observed["report"]["status"] == "complete", "positive candidate did not complete")
        expected = (
            ([" local \n", "", "poor duplicate", "poor duplicate"] * 3)[:count]
            if callbacks == 0
            else [literal(callbacks - 1)] * count
        )
        require(
            observed["answers"] == [{"task_id": "1", "answers": expected}],
            "literal outputs changed",
        )
        require(
            len(observed["new_sends"]) == callbacks
            and observed["ledger"]["operation_count"] == callbacks,
            "callback count coupled to answer count",
        )
        require(observed["ledger"]["reserved_microusd"] == 0, "positive hold retained")
        require(
            observed["report"]["execution"]["cleanup_status"] == "removed",
            "positive cleanup missing",
        )
        require(
            observed["report"]["execution"]["stderr_bytes"] == len(b"candidate stdout noise\n")
            and observed["report"]["execution"]["stderr_sha256"]
            == sha(b"candidate stdout noise\n"),
            "candidate stdout was not isolated as stderr",
        )
        require(
            set(observed["report"]["execution"]["configuration"]["mounts"])
            == {"/agent", "/runner"},
            "dataset or evaluator mounted",
        )
        evidence["cases"].append(observed)
        if provider == "openai" and callbacks == 3:
            fixture.authority.deactivate(label, "completed synthetic candidate proof")
            replay = fixture.run("replay", keyless=True)
            require(
                replay["report"]["status"] == "complete" and not replay["new_sends"],
                "keyless replay failed",
            )
            require(
                replay["ledger"] == observed["ledger"] and replay["answers"] == observed["answers"],
                "replay changed evidence",
            )
            evidence["checks"].append({"kind": "inactive-keyless-receipt-replay", **replay})
    for label, mode, quota, callbacks in (
        ("quota-hostile", "valid", 2, 3),
        ("unknown-hostile", "unknown", 3, 3),
        ("timeout", "timeout", 3, 3),
    ):
        fixture = Fixture(
            parent,
            label,
            environment,
            mode=mode,
            quota=quota,
            callbacks=callbacks,
            hostile=label.endswith("hostile"),
        )
        observed = fixture.run()
        reason = "quota" if label == "quota-hostile" else "unknown"
        require(
            observed["report"]["status"] == "stopped"
            and observed["report"]["host_stop_reason"] == reason,
            "host stop lost after candidate forgery",
        )
        require("answers" not in observed, "failed candidate published answers")
        require(len(observed["new_sends"]) == (2 if reason == "quota" else 1), "post-stop spending")
        if reason == "unknown":
            require(
                observed["ledger"]["reserved_microusd"] > 0
                and observed["operations"][0]["status"] == "unknown",
                "unknown liability lost",
            )
            if mode == "unknown":
                require(
                    observed["operations"][0]["receipt_sha256"] is not None,
                    "raw unknown receipt lost",
                )
        evidence["cases"].append(observed)
    conflict = Fixture(parent, "changed-request-replay", environment, callbacks=1, nonce=True)
    completed = conflict.run()
    rejected = conflict.run("conflicting-replay", keyless=True)
    require(
        completed["report"]["status"] == "complete"
        and rejected["report"]["host_stop_reason"] == "protocol",
        "body conflict accepted",
    )
    require(
        not rejected["new_sends"]
        and rejected["ledger"] == completed["ledger"]
        and "answers" not in rejected,
        "conflict replay billed or published",
    )
    evidence["checks"].append(
        {"kind": "same-owner-body-conflict", "first": completed, "conflict": rejected}
    )
    cancelled = Fixture(parent, "received-interruption", environment, callbacks=3)
    prefix = cancelled.run("interrupted", interrupt=True)
    require(
        prefix["interrupted"]
        and prefix["ledger"]["operation_count"] == 1
        and prefix["operations"][0]["status"] == "completed",
        "received reply lost on cancellation",
    )
    require("answers" not in prefix, "interrupted candidate published answers")
    resumed = cancelled.run("resumed")
    require(
        resumed["report"]["status"] == "complete"
        and len(resumed["new_sends"]) == 2
        and resumed["ledger"]["operation_count"] == 3,
        "original-owner interrupted resume failed",
    )
    evidence["checks"].append(
        {"kind": "received-interruption-same-owner-resume", "prefix": prefix, "resumed": resumed}
    )
    for mode, count in (("unknown", 1), ("valid", 3)):
        skipped = Fixture(
            parent, "skipped-" + mode + "-prefix", environment, callbacks=0, mode=mode
        )
        prefix = skipped.prime(count)
        observed = skipped.run("zero-callback-recovery", keyless=True)
        require(
            observed["report"]["status"] != "complete"
            and observed["report"]["owner_operation_coverage_complete"] is False
            and "answers" not in observed,
            "zero-callback recovery skipped retained operations",
        )
        require(
            not observed["new_sends"] and observed["ledger"] == prefix["ledger"],
            "skipped-prefix recovery changed financial evidence",
        )
        evidence["checks"].append(
            {"kind": "reject-skipped-" + mode + "-prefix", "prefix": prefix, "recovery": observed}
        )
    require(
        all(sha((ROOT / name).read_bytes()) == value for name, value in sources.items()),
        "executing source changed",
    )
    require(_core_sources() == core, "financial core changed")
    require("_buddha_candidate" not in sys.modules, "candidate executed on host")
    evidence.update(
        status="pass",
        source_sha256=sources,
        gateway_core_sha256=core,
        limits=[
            "Synthetic HTTPS and fixture models only; zero real provider calls.",
            "Selected single-file task code only; no inherited bundles/improver/evolution claim.",
            "The separate runtime proof supplies eleven OS confinement cases; "
            "these prove this channel composition.",
            "Random-nonce fixture deliberately changes a request body "
            "to exercise same-owner replay conflict.",
            "No official evaluator, useful-diversity improvement "
            "or universal host/kernel escape claim.",
        ],
    )
    save(output, evidence)
    print(
        json.dumps(
            {
                "status": "pass",
                "cases": len(evidence["cases"]),
                "checks": len(evidence["checks"]),
                "real_provider_calls": 0,
                "output": str(output),
                "sha256": sha(output.read_bytes()),
            }
        ),
        flush=True,
    )


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", type=Path, required=True)
    main(parser.parse_args().out)
