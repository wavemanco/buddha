"""Offline full-module differential and real funded-boundary proof in Docker.

Run once from the checkout with Python. This creates temporary synthetic ledgers,
uses fake credentials and mocked host HTTPS, and removes every owned container.
No actual provider API is called. Requires the separately prepared pinned image
and installed-runtime evidence; see CONFINED-NATIVE-EVALUATION.md.
"""

import base64
import hashlib
import json
import os
import shutil
import socket
import sqlite3
import sys
import tempfile
from collections import Counter
from contextlib import closing
from dataclasses import asdict
from datetime import UTC, datetime
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
from buddha.answers import Answers, TaskSet  # noqa: E402
from buddha.authorization import Authorization  # noqa: E402
from buddha.executor import ContainerSpec, Limits, _endpoint, run_container  # noqa: E402
from buddha.gateway import Gateway, GatewayError, RawHTTPTransport, prepare_gateway  # noqa: E402
from buddha.native_run import NativeRunError, NativeSession  # noqa: E402
from buddha.provider import ModelSpec  # noqa: E402
from buddha.releases import Release, _json, inventory, prepare_selection  # noqa: E402

PIN = "64a23be6b18ec1dacc298830aab276061b6e143c"
ENV = json.loads((ROOT / "docs/conformance/nb02c3-runtime-environment.json").read_bytes())
INSTALLED = json.loads((ROOT / "runs/reviews/nb02c3-runtime-installed.json").read_bytes())
SOURCE = ROOT / "runs/references/noveltybench-conformance" / PIN
RUNNER = (
    "__init__",
    "channel",
    "native_worker",
    "native_context",
    "native_transport",
    "releases",
    "wire",
)
MODULES = ["src.score", "src.summarize", "src.common", "src.judge", "src.evaluation_io"]
CAPS = {"openai": "openai.chat-completions.v1", "anthropic": "anthropic.messages.v1"}
KEYS = {provider: "offline-only-not-a-real-" + provider + "-key" for provider in CAPS}
PINNED = {
    "src/judge.py": "4decf04790b90a03368eb792dfe29045435914a73ab83a52185d9dd0d1613902",
    "src/score.py": "418985a40e9e159cfeffe9a43ab2c727010d7a7a29407f4e14cab3c81b77cbae",
    "src/common.py": "ba60bf0f2a409c3774d75880f305325a28ed34320610667542a4596c41f424af",
    "src/evaluation_io.py": "8a34e01308677469d984dd59e36412c2994baf2554fd3a5f026be9ef98a3a5c7",
    "src/summarize.py": "0a8bd1eb7f317584f579eaa827e580f9cefe4177a1abdc35b2cb06ef96eeea9e",
    "LICENSE": "14e69e7fbb2f8fd0aa8ccf17d7d4ddd54665555c613a0336767f7a5fa477895c",
    "uv.lock": "ff6d5b15b77e4ca46a33604586eb7d99666d2802752ab962af9baa2924a50758",
}


def sha(raw):
    return hashlib.sha256(raw).hexdigest()


def official_copy(target):
    # Only sealed upstream assets enter the fixture; local caches stay unselected.
    for relative, expected in PINNED.items():
        raw = (SOURCE / relative).read_bytes()
        assert sha(raw) == expected, relative
        destination = target / relative
        destination.parent.mkdir(parents=True, exist_ok=True)
        destination.write_bytes(raw)


def direct(parent, label, module, mode, primary, inputs):
    directory = parent / label
    roots = {name: directory / name for name in ("official", "runner", "inputs")}
    for path in roots.values():
        path.mkdir(parents=True)
    official_copy(roots["official"])
    for name in (
        "__init__",
        "channel",
        "native_worker",
        "native_context",
        "native_transport",
        "releases",
        "wire",
    ):
        target = roots["runner"] / "buddha" / (name + ".py")
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes((ROOT / "buddha" / (name + ".py")).read_bytes())
    helper = ROOT / "docs/conformance/nb02c3-direct-worker.py"
    (roots["runner"] / "direct.py").write_bytes(helper.read_bytes())
    descriptions = []
    for index, (destination, raw) in enumerate(inputs.items()):
        name = str(index) + ".bin"
        (roots["inputs"] / name).write_bytes(raw)
        descriptions.append({"source": name, "destination": destination, "sha256": sha(raw)})
    argv = ["--eval-dir", "/scratch/artifacts", "--version", "1.1"]
    if module == "src.score":
        argv += [
            "--scorer",
            "llm",
            "--judge-model",
            primary,
            "--concurrency",
            "2",
            "--fallback-judge",
            "claude-fallback",
        ]
    command = {"index": 0, "module": module, "argv": argv}
    command["sha256"] = sha(json.dumps(command, sort_keys=True, separators=(",", ":")).encode())
    config = {
        "type": "configure",
        "format": "buddha.direct-native-worker.v1",
        "fixture": {"mode": mode, "primary_model": primary},
        "command": command,
        "release_sha256": "a" * 64,
        "answers_sha256": "b" * 64,
        "roots": {
            "official": "/official",
            "runner": "/runner",
            "environment": "/opt/venv",
            "inputs": "/inputs",
            "artifacts": "/scratch/artifacts",
        },
        "inventories": {
            "official": inventory(roots["official"]),
            "runner": inventory(roots["runner"]),
            "environment": {
                "helper_sha256": ENV["audit_helper"]["sha256"],
                "manifest_sha256": ENV["installed_manifest"]["sha256"],
                "inventory": INSTALLED["inventory"],
                "synthetic_modules": [
                    "_cython_3_1_0",
                    "_cython_3_1_3",
                    "cython_runtime",
                    "six.moves",
                ],
            },
        },
        "inputs": descriptions,
        "hooks": {
            "modules": [
                "src.score",
                "src.summarize",
                "src.common",
                "src.judge",
                "src.evaluation_io",
            ],
            "cache": None,
            "calls": [],
            "sdk": [],
        },
    }
    frames, files, finished = [], {}, set()

    def handle(frame):
        assert frame["type"] in {"ready", "capture", "file", "done"}, frame["type"]
        frames.append(frame)
        if frame["type"] == "file":
            path = frame["path"]
            assert path not in finished
            body = files.setdefault(path, bytearray())
            assert frame["offset"] == len(body)
            body.extend(base64.b64decode(frame["data_base64"], validate=True))
            if frame["eof"]:
                finished.add(path)
        return None

    spec = ContainerSpec(
        ENV["image"].split("@")[-1],
        "evaluator",
        tuple(("/" + name, path) for name, path in roots.items()),
        runner_entrypoint="direct.py",
        image_environment=tuple(tuple(item.split("=", 1)) for item in ENV["config"]["Env"]),
    )
    result = run_container(spec, initial=config, handle=handle)
    assert result.exit_code == 0 and result.cleanup_status == "removed"
    assert frames[0]["type"] == "ready" and frames[-1]["type"] == "done", frames
    assert set(files) == finished
    bodies = {name: bytes(raw) for name, raw in files.items()}
    captures = [frame for frame in frames if frame["type"] == "capture"]
    for frame in captures:
        assert frame["sdk_max_retries"] == 8
        assert sha(base64.b64decode(frame["body_base64"], validate=True)) == frame["body_sha256"]
    evidence = {
        "label": label,
        "mode": mode,
        "primary": primary,
        "command": command,
        "outcome": {
            "status": frames[-1]["status"],
            "reason": frames[-1]["reason"],
            "audit_sha256": sha(_json(frames[-1]["audit"])),
            "audit_module_count": len(frames[-1]["audit"]),
        },
        "ready_audit_sha256": sha(_json(frames[0]["audit"])),
        "ready_audit_module_count": len(frames[0]["audit"]),
        "captures": captures,
        "files": {name: {"sha256": sha(raw), "bytes": len(raw)} for name, raw in bodies.items()},
        "stderr_bytes": result.stderr_bytes,
        "stderr_sha256": result.stderr_sha256,
        "configuration": result.configuration,
        "cleanup_status": result.cleanup_status,
        "helper_sha256": sha(helper.read_bytes()),
    }
    print(
        json.dumps(
            {
                "label": label,
                "status": frames[-1]["status"],
                "captures": len(captures),
                "files": sorted(files),
            }
        ),
        flush=True,
    )
    return evidence, bodies


def payload(provider, model, mode, primary):
    """Same literal canned judgments as the independent direct transport."""
    text = "{malformed judgment" if mode == "bad" else '{"score":7}'
    refused = mode == "refusal" and model == primary
    if provider == "openai":
        return {
            "id": "cmpl-direct-fixture",
            "object": "chat.completion",
            "created": 0,
            "model": model,
            "choices": [
                {
                    "index": 0,
                    "message": {
                        "role": "assistant",
                        "content": None if refused else text,
                        "refusal": "synthetic refusal" if refused else None,
                    },
                    "finish_reason": "length" if mode == "length" else "stop",
                }
            ],
            "usage": {"prompt_tokens": 1, "completion_tokens": 2, "total_tokens": 3},
        }
    content = [{"type": "text", "text": text}]
    if mode == "multiblock":
        content = [
            {"type": "thinking", "thinking": "fixture", "signature": "fixture"},
            *content,
            {"type": "text", "text": '{"score":1}'},
        ]
    return {
        "id": "msg-direct-fixture",
        "type": "message",
        "role": "assistant",
        "model": model,
        "content": content,
        "stop_sequence": None,
        "stop_reason": "refusal" if refused else "max_tokens" if mode == "length" else "end_turn",
        "usage": {"input_tokens": 1, "output_tokens": 2},
    }


def normalize(raw, path):
    """Only concurrent JSONL row order is ignored, preserving typed IDs and every field."""
    if not path.endswith((".jsonl", ".jsonl.partial")):
        return raw
    rows = [json.loads(line) for line in raw.splitlines()]
    return _json(sorted(rows, key=lambda row: (type(row["id"]).__name__, str(row["id"]))))


class Connection:
    def __init__(self, owner, host, **kwargs):
        assert kwargs["timeout"] == 2
        self.owner, self.host = owner, host

    def request(self, method, path, *, body, headers):
        provider = "openai" if self.host == "api.openai.com" else "anthropic"
        assert self.host in {"api.openai.com", "api.anthropic.com"}
        assert method == "POST" and path == (
            "/v1/chat/completions" if provider == "openai" else "/v1/messages"
        )
        assert (
            headers.get("Authorization") == "Bearer " + KEYS[provider]
            if provider == "openai"
            else headers.get("x-api-key") == KEYS[provider]
        )
        self.provider, self.model = provider, json.loads(body)["model"]
        self.owner.sends.append(
            {
                "provider": provider,
                "model": self.model,
                "body_sha256": sha(body),
                "headers": {
                    name.lower(): value
                    for name, value in headers.items()
                    if name.lower() not in {"authorization", "x-api-key"}
                },
            }
        )

    def getresponse(self):
        if self.owner.mode == "timeout":
            raise TimeoutError("synthetic HTTPS timeout; no actual network")
        return self

    status = 200

    def read(self, limit):
        value = payload(self.provider, self.model, self.owner.mode, self.owner.primary)
        if self.owner.mode == "unknown":
            value.pop("usage")
        raw = _json(value)
        assert len(raw) < limit
        return raw

    def getheaders(self):
        return [
            ("content-type", "application/json"),
            ("x-request-id" if self.provider == "openai" else "request-id", "direct-fixture"),
        ]

    def close(self):
        pass


class ObservedSession(NativeSession):
    def __init__(self, *args, **kwargs):
        self.requests = []
        super().__init__(*args, **kwargs)

    def handle(self, frame):
        if frame.get("type") == "request":
            request = frame["request"]
            body = base64.b64decode(request["body_base64"], validate=True)
            self.requests.append(
                {
                    "provider": request["provider"],
                    "model": json.loads(body)["model"],
                    "logical_id": request["logical_id"],
                    "attempt": request["attempt"],
                    "body_sha256": sha(body),
                    "headers": dict(request["headers"]),
                }
            )
        return super().handle(frame)


class Funded:
    def __init__(self, parent, label, module, mode, primary, inputs, observed_headers):
        self.mode, self.primary, self.sends = mode, primary, []
        self.directory = directory = parent / label
        directory.mkdir()
        roots = self.roots = {
            name: directory / name
            for name in ("official", "runner", "agent", "environment", "host")
        }
        for path in roots.values():
            path.mkdir()
        official_copy(roots["official"])
        dataset = b"".join(
            _json({"id": identifier, "prompt": "same literal prompt"}) + b"\n"
            for identifier in (1, "1")
        )
        (roots["official"] / "fixture-dataset.jsonl").write_bytes(dataset)
        for name in RUNNER:
            target = roots["runner"] / "buddha" / (name + ".py")
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes((ROOT / "buddha" / (name + ".py")).read_bytes())
        (roots["agent"] / "identity.txt").write_bytes(
            b"canned ordered answers; no agent execution\n"
        )
        shutil.copyfile(
            ROOT / "docs/conformance/nb02c3-runtime-environment.json",
            roots["environment"] / "environment.json",
        )
        profiles = {}
        for model, provider in (
            ("test-model", "openai"),
            ("claude-primary", "anthropic"),
            ("claude-fallback", "anthropic"),
        ):
            profiles[model] = {
                "spec": asdict(
                    ModelSpec(
                        provider,
                        model,
                        2_000_000,
                        128_000,
                        1_000_000,
                        2_000_000,
                        "https://example.org/offline-synthetic-only",
                    )
                ),
                "response_models": [model],
                "request_tiers": ["auto", "default"],
                "response_tiers": ["", "default"],
                "allow_omitted_tier": True,
                "headers": observed_headers[provider],
                "account_headers": {},
            }
        (roots["host"] / "profiles.json").write_bytes(
            _json(
                {
                    "format": "buddha.gateway-profiles.v2",
                    "profiles": profiles,
                }
            )
        )
        argv = ["--eval-dir", "{artifacts}", "--version", "1.1"]
        if module == "src.score":
            argv += [
                "--scorer",
                "llm",
                "--judge-model",
                primary,
                "--concurrency",
                "2",
                "--fallback-judge",
                "claude-fallback",
            ]
        release = Release.from_record(
            {
                "format": "buddha.benchmark-release.v1",
                "benchmark": "noveltybench-native-fixture",
                "release": "1.1-pinned-score-summary-fixture",
                "upstream": {
                    "url": "https://github.com/novelty-bench/novelty-bench",
                    "revision": PIN,
                },
                "source": inventory(roots["official"]),
                "dependency_lock": "uv.lock",
                "task": {
                    "dataset": "fixture-dataset.jsonl",
                    "id_field": "id",
                    "prompt_field": "prompt",
                    "answers_field": "generations",
                    "count": 10,
                },
                "commands": [{"module": module, "argv": argv}],
                "artifacts": {
                    "answers": "generations.jsonl",
                    "results": ["v1.1/scores.jsonl"],
                    "summary": "v1.1/summary.json",
                },
                "requires": sorted(CAPS.values()),
            }
        )
        tasks = TaskSet.from_dataset(release, dataset)
        answers = Answers.from_results(
            release,
            tasks,
            [
                {
                    "task_id": task.id,
                    "answers": ["poor", "poor", "", "", "x", "x", "x", "x", "x", "x"],
                }
                for task in tasks.tasks
            ],
            agent_sha256=sha(_json(inventory(roots["agent"]))),
            metadata={},
        )
        self.answers_path = directory / "answers.json"
        self.answers_path.write_bytes(answers.to_bytes())
        input_root = directory / "inputs"
        input_root.mkdir()
        descriptions = []
        for index, (destination, raw) in enumerate(inputs.items()):
            name = str(index) + ".bin"
            (input_root / name).write_bytes(raw)
            descriptions.append({"source": name, "destination": destination, "sha256": sha(raw)})
        command = {
            "index": 0,
            "module": module,
            "argv": ["/scratch/artifacts" if item == "{artifacts}" else item for item in argv],
        }
        command["sha256"] = sha(_json(command))
        worker = {
            "type": "configure",
            "format": "buddha.native-worker.v1",
            "command": command,
            "release_sha256": release.fingerprint(),
            "answers_sha256": answers.fingerprint(),
            "roots": {
                "official": "/official",
                "runner": "/runner",
                "environment": "/opt/venv",
                "inputs": "/inputs",
                "artifacts": "/scratch/artifacts",
            },
            "inventories": {
                "official": inventory(roots["official"]),
                "runner": inventory(roots["runner"]),
                "environment": {
                    "helper_sha256": ENV["audit_helper"]["sha256"],
                    "manifest_sha256": ENV["installed_manifest"]["sha256"],
                    "inventory": INSTALLED["inventory"],
                    "synthetic_modules": [
                        "_cython_3_1_0",
                        "_cython_3_1_3",
                        "cython_runtime",
                        "six.moves",
                    ],
                },
            },
            "inputs": descriptions,
            "hooks": {
                "modules": MODULES,
                "cache": {
                    "target": "src.evaluation_io:run_cached",
                    "key_target": "src.evaluation_io:evaluation_key",
                    "parameters": {
                        name: name
                        for name in (
                            "instances",
                            "output_file",
                            "key_field",
                            "config",
                            "compute",
                            "concurrency",
                        )
                    },
                    "id_field": "id",
                },
                "calls": [
                    {"target": "src.judge:judge_call", "label": "judge_call"},
                    {"target": "src.judge:judge", "label": "judge"},
                ],
                "sdk": [
                    {
                        "provider": "openai",
                        "constructor": "openai:AsyncOpenAI",
                        "module_slots": ["src.common:AsyncOpenAI"],
                    },
                    {
                        "provider": "anthropic",
                        "constructor": "anthropic:AsyncAnthropic",
                        "module_slots": ["src.judge:anthropic"],
                    },
                ],
            },
        }
        self.descriptor = directory / "native-command.json"
        docker = shutil.which("docker")
        assert docker
        self.descriptor.write_bytes(
            _json(
                {
                    "format": "buddha.native-command.v1",
                    "worker": worker,
                    "executor": {
                        "image_id": ENV["image"].split("@")[-1],
                        "role": "evaluator",
                        "mounts": [
                            ["/" + name, str(path)]
                            for name, path in (
                                ("official", roots["official"]),
                                ("runner", roots["runner"]),
                                ("inputs", input_root),
                            )
                        ],
                        "runner_entrypoint": "buddha/native_worker.py",
                        "limits": asdict(Limits()),
                        "image_environment": [item.split("=", 1) for item in ENV["config"]["Env"]],
                        "docker_endpoint": _endpoint(docker),
                    },
                    "profiles": {
                        "openai": {"test-model": "test-model"},
                        "anthropic": {
                            "claude-primary": "claude-primary",
                            "claude-fallback": "claude-fallback",
                        },
                    },
                }
            )
        )
        selection = prepare_selection(
            release, roots, capabilities={cap: "profiles.json" for cap in CAPS.values()}
        )
        self.authority = Authorization.create(
            directory / "authorization.sqlite3",
            authorization_id="offline-" + label,
            budget_microusd=100_000_000,
            max_calls=40,
            scope="synthetic fixture only; never live authorization",
        )
        host_sources = [
            ROOT / "buddha" / (name + ".py") for name in (*RUNNER, "executor", "native_run")
        ]
        invocation = [
            Path(__file__).resolve(),
            self.descriptor,
            self.answers_path,
            *sorted(input_root.iterdir()),
            *host_sources,
        ]
        self.run_dir = prepare_gateway(
            directory / "run",
            selection=selection,
            roots=roots,
            authorization=self.authority,
            budget_microusd=100_000_000,
            max_calls=40,
            input_files=invocation,
            review={
                "checked_on": datetime.now(UTC).date().isoformat(),
                "credential_sha256": {
                    provider: sha(value.encode()) for provider, value in KEYS.items()
                },
                "account_scope": "synthetic offline accounts",
            },
            run_id="offline-" + label,
        )

    def run(self, *, replay=False):
        gateway = Gateway(
            self.run_dir, transport=RawHTTPTransport(allow_paid=True, timeout_seconds=2)
        )
        output = self.directory / ("replay" if replay else "output")
        session = ObservedSession(gateway, descriptor=self.descriptor, output=output)
        old_sends = len(self.sends)
        environment = {
            name: value
            for name, value in os.environ.items()
            if name not in {"OPENAI_API_KEY", "ANTHROPIC_API_KEY"}
        }
        if not replay:
            environment.update(OPENAI_API_KEY=KEYS["openai"], ANTHROPIC_API_KEY=KEYS["anthropic"])
        with (
            patch.dict("os.environ", environment, clear=True),
            patch(
                "http.client.HTTPSConnection",
                side_effect=(
                    AssertionError("raw replay must not prepare HTTPS")
                    if replay
                    else lambda host, **kwargs: Connection(self, host, **kwargs)
                ),
            ),
            patch.object(
                socket, "create_connection", side_effect=AssertionError("external network denied")
            ),
        ):
            report = session.run()
        files = {
            path.relative_to(output / "artifacts").as_posix(): path.read_bytes()
            for path in (output / "artifacts").rglob("*")
            if path.is_file()
        }
        with closing(sqlite3.connect(gateway.ledger.path)) as connection:
            states = dict(
                connection.execute("SELECT status,COUNT(*) FROM operations GROUP BY status")
            )
        evidence = {
            "label": self.directory.name,
            "replay": replay,
            "report": report,
            "requests": session.requests,
            "sends": self.sends[old_sends:],
            "ledger": gateway.ledger.totals(),
            "states": states,
            "files": {name: {"sha256": sha(raw), "bytes": len(raw)} for name, raw in files.items()},
        }
        print(
            json.dumps(
                {
                    "label": self.directory.name,
                    "replay": replay,
                    "status": report["status"],
                    "requests": len(session.requests),
                    "sends": len(self.sends) - old_sends,
                    "ledger": evidence["ledger"],
                }
            ),
            flush=True,
        )
        return evidence, files


def compare(direct_result, funded_result):
    direct_evidence, direct_files = direct_result
    funded_evidence, funded_files = funded_result
    assert direct_evidence["outcome"]["status"] == funded_evidence["report"]["status"]
    assert set(direct_files) == set(funded_files)
    for path in direct_files:
        assert normalize(direct_files[path], path) == normalize(funded_files[path], path), path

    def keys(rows):
        return Counter((row["provider"], row["model"], row["body_sha256"]) for row in rows)

    assert keys(direct_evidence["captures"]) == keys(funded_evidence["sends"])
    assert all(row["attempt"] == 0 for row in funded_evidence["requests"])
    assert funded_evidence["ledger"]["reserved_microusd"] == 0
    return {
        "native_status": "equal",
        "native_artifacts": "equal after typed-ID row-order normalization only",
        "serialized_sdk_bodies": "equal exact bytes as SHA256 multisets",
        "physical_attempt_indices": [0],
        "per_artifact_raw_byte_equality": {
            name: direct_files[name] == funded_files[name] for name in direct_files
        },
    }


def main():
    sealed_paths = [
        Path(__file__).resolve(),
        ROOT / "docs/conformance/nb02c3-direct-worker.py",
        *[ROOT / "buddha" / (name + ".py") for name in (*RUNNER, "executor", "native_run")],
    ]
    before = {str(path.relative_to(ROOT)): sha(path.read_bytes()) for path in sealed_paths}
    rows = [
        {
            "id": identifier,
            "prompt": "same literal prompt",
            "generations": ["poor", "poor", "", "", "x", "x", "x", "x", "x", "x"],
            "partition": [0, 0, 1, 1, 1, 1, 1, 1, 1, 1],
        }
        for identifier in (1, "1")
    ]
    partitions = b"".join(json.dumps(row).encode() + b"\n" for row in rows)
    evidence = {
        "format": "buddha.review.nb02c3-funded-full-native.v1",
        "source_revision": PIN,
        "image": ENV["image"],
        "actual_provider_calls": 0,
        "selected_upstream_seals": PINNED,
        "earlier_failed_multihead_observation": {
            "direct_mock_requests": 3,
            "funded_mock_requests": 4,
            "status_and_normalized_artifacts": "equal before body-count comparator failed",
            "interpretation": "native gather failure may leave a peer pending at teardown; "
            "concurrent issuance depends on transport timing",
            "log": "runs/reviews/nb02c3-funded-native-fixture-failure-v3.log",
            "log_sha256": "7a2a0730744720fadeef14dac012c43367619c0e88d8d9238f5c7a53f518f69e",
            "scope": (
                "recorded exploratory fixture observation; no universal failure-count parity claim"
            ),
        },
        "actual_keys_used": False,
        "host_official_execution": False,
        "private_sdk_methods_patched": False,
        "direct_scientific_functions_wrapped": False,
        "scenarios": [],
        "checks": [],
    }
    with tempfile.TemporaryDirectory(dir=ROOT / "runs/reviews") as folder:
        parent = Path(folder)
        prepared_direct = {}
        observed_headers = {provider: {} for provider in CAPS}
        for label, model in (("valid-oai", "test-model"), ("valid-anthropic", "claude-primary")):
            prepared_direct[label] = direct(
                parent,
                "direct-" + label,
                "src.score",
                "valid",
                model,
                {"v1.1/partitions.jsonl": partitions},
            )
            for capture in prepared_direct[label][0]["captures"]:
                for name, value in capture["headers"]:
                    observed_headers[capture["provider"]].setdefault(name.lower(), set()).add(value)
        for headers in observed_headers.values():
            for name, values in headers.items():
                headers[name] = sorted(values)
            headers["x-stainless-retry-count"] = [str(index) for index in range(9)]
        evidence["observed_linux_sdk_headers"] = observed_headers
        drift = Funded(
            parent,
            "descriptor-drift",
            "src.score",
            "valid",
            "test-model",
            {"v1.1/partitions.jsonl": partitions},
            observed_headers,
        )
        drift.descriptor.write_bytes(drift.descriptor.read_bytes() + b"\n")
        try:
            drift.run()
        except (GatewayError, NativeRunError) as error:
            guard = type(error).__name__
        else:
            raise AssertionError("descriptor drift was accepted")
        assert not (drift.directory / "output").exists()
        summary = drift.authority.summary()
        assert summary["operation_count"] == 0 and drift.sends == []
        evidence["checks"].append(
            {
                "label": "descriptor-drift-before-execution",
                "guard": guard,
                "operation_count": 0,
                "sends": 0,
                "output_created": (drift.directory / "output").exists(),
            }
        )
        scores = None
        for label, mode, model in (
            ("valid-oai", "valid", "test-model"),
            ("summary", "valid", "test-model"),
            ("full-cache", "valid", "test-model"),
            ("partial-cache", "valid", "test-model"),
            ("bad-oai", "bad", "test-model"),
            ("length-oai", "length", "test-model"),
            ("refusal-oai", "refusal", "test-model"),
            ("valid-anthropic", "valid", "claude-primary"),
            ("fallback-anthropic", "refusal", "claude-primary"),
            ("multiblock-anthropic", "multiblock", "claude-primary"),
        ):
            module = "src.summarize" if label == "summary" else "src.score"
            # Native multihead gather failures can leave a peer pending at command
            # teardown. One head per failed row makes this comparator deterministic;
            # concurrent two-head valid/cache/fallback cases remain separate controls.
            selected = partitions
            if mode in {"bad", "length"} or label == "refusal-oai":
                selected = b"".join(_json(row | {"partition": [0] * 10}) + b"\n" for row in rows)
            inputs = {"v1.1/partitions.jsonl": selected}
            if label == "summary":
                inputs = {"v1.1/scores.jsonl": scores}
            elif label == "full-cache":
                inputs["v1.1/scores.jsonl"] = scores
            elif label == "partial-cache":
                inputs["v1.1/scores.jsonl.partial"] = scores.splitlines(keepends=True)[0]
            direct_result = prepared_direct.get(label) or direct(
                parent, "direct-" + label, module, mode, model, inputs
            )
            funded = Funded(parent, label, module, mode, model, inputs, observed_headers)
            funded_result = funded.run()
            comparison = compare(direct_result, funded_result)
            evidence["scenarios"].append(
                {
                    "label": label,
                    "direct": direct_result[0],
                    "funded": funded_result[0],
                    "comparison": comparison,
                }
            )
            if label == "valid-oai":
                assert len({row["logical_id"] for row in funded_result[0]["requests"]}) == 4
                scores = funded_result[1]["v1.1/scores.jsonl"]
                replay = funded.run(replay=True)
                assert (
                    replay[0]["sends"] == [] and replay[0]["ledger"] == funded_result[0]["ledger"]
                )
                assert all(
                    normalize(raw, path) == normalize(replay[1][path], path)
                    for path, raw in funded_result[1].items()
                )
                assert Counter(row["logical_id"] for row in replay[0]["requests"]) == Counter(
                    row["logical_id"] for row in funded_result[0]["requests"]
                )
                evidence["checks"].append(
                    {"label": "same-owner-original-input-raw-replay", **replay[0]}
                )
            if label == "partial-cache":
                assert len(funded_result[0]["sends"]) == 2
            if label in {"summary", "full-cache"}:
                assert funded_result[0]["ledger"]["operation_count"] == 0
        for mode in ("unknown", "timeout"):
            for model in ("test-model", "claude-primary"):
                label = mode + ("-oai" if model == "test-model" else "-anthropic")
                funded = Funded(
                    parent,
                    label,
                    "src.score",
                    mode,
                    model,
                    {"v1.1/partitions.jsonl": partitions},
                    observed_headers,
                )
                observed, _ = funded.run()
                assert (
                    observed["report"]["status"] == "stopped"
                    and observed["report"]["worker"]["reason"] == "unknown"
                )
                assert len(observed["sends"]) == len(observed["requests"]) == 1
                assert observed["states"] == {"unknown": 1}
                assert (
                    observed["ledger"]["spent_microusd"]
                    == 0
                    < observed["ledger"]["reserved_microusd"]
                )
                evidence["checks"].append(observed)
    evidence["source_sha256"] = {
        str(path.relative_to(ROOT)): sha(path.read_bytes())
        for path in [
            Path(__file__).resolve(),
            ROOT / "docs/conformance/nb02c3-direct-worker.py",
            *[ROOT / "buddha" / (name + ".py") for name in (*RUNNER, "executor", "native_run")],
        ]
    }
    assert evidence["source_sha256"] == before, "source changed during proof"
    evidence["limits"] = [
        "score and summary complete modules only; partition fixture is declared input",
        "synthetic transport judgments do not establish judge accuracy or semantic diversity",
        "new cache inputs use new frozen invocations; "
        "dynamic checkpoint adoption is not implemented",
        "raw receipt replay reuses one immutable owner and original inputs with fresh scratch",
        "concurrent JSONL order may vary; IDs and row data are never changed for comparison",
        "failed-parser fixtures use one head per row; arbitrary failed multihead "
        "issued-call counts are timing-dependent and are not claimed equal",
    ]
    output = ROOT / "runs/reviews/nb02c3-funded-native-evidence.json"
    output.write_bytes((json.dumps(evidence, indent=2, sort_keys=True) + "\n").encode())
    print(
        json.dumps(
            {
                "scenarios": len(evidence["scenarios"]),
                "checks": len(evidence["checks"]),
                "evidence": str(output),
                "actual_provider_calls": 0,
            }
        ),
        flush=True,
    )


if __name__ == "__main__":
    main()
