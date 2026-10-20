"""Confined frozen-seed -> official partition/score/summary, synthetic HTTPS only.

Run once using the recipe in FROZEN-SEED.md. Existing sealed A/B images and
the B installed inventory are prerequisites. No official or agent source runs
on the host; the unchanged research oracles execute only inside confinement.
"""

import base64
import hashlib
import json
import os
import shutil
import sqlite3
import sys
import tempfile
from collections import Counter
from contextlib import closing
from dataclasses import asdict
from datetime import UTC, datetime
from pathlib import Path
from unittest.mock import patch

if sys.flags.optimize:
    raise RuntimeError("This proof requires ordinary Python with assertions enabled")

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from buddha.agent_run import HOST_FILES as AGENT_HOST  # noqa: E402
from buddha.agent_run import RUNNER_FILES as AGENT_RUNNER  # noqa: E402
from buddha.answers import Answers, TaskSet  # noqa: E402
from buddha.authorization import Authorization  # noqa: E402
from buddha.baseline import prepare_baseline, run_baseline  # noqa: E402
from buddha.executor import (  # noqa: E402
    OWNER_LABEL,
    ContainerSpec,
    Limits,
    _control,
    _endpoint,
    run_container,
)
from buddha.gateway import Gateway, RawHTTPTransport, ReceivedReply, _core_sources  # noqa: E402
from buddha.native_run import RUNNER_FILES as NATIVE_RUNNER  # noqa: E402
from buddha.provider import ModelSpec  # noqa: E402
from buddha.releases import Release, _json, inventory, prepare_selection  # noqa: E402

SCRIPT = Path(__file__).resolve()
PIN = "64a23be6b18ec1dacc298830aab276061b6e143c"
SOURCE = ROOT / "runs/references/noveltybench-conformance" / PIN
SEED = ROOT / "agents/frozen_seed.py"
SEED_SHA = "2b87bfe0d3c97ee45db2d45260985ffe0234eca93967f4689fb7c59f82603921"
ENV_A = ROOT / "docs/conformance/nb02c3-runtime-environment.json"
ENV_B = ROOT / "docs/conformance/nb02c3b-runtime-environment.json"
PROOF_B = ROOT / "docs/conformance/nb02c3b-funded-native-evidence.json"
HELPER_A = ROOT / "docs/conformance/nb02c3-direct-worker.py"
HELPER_B = ROOT / "docs/conformance/nb02c3b-direct-worker.py"
SEALED = {
    ENV_A: "dc58b658821a536d13c300b6b1f756aa8dc3b2adcc5699627a4827f8361f7d9a",
    ENV_B: "90e905e2fc381e62adc0553a8e195b7d120886fa597743297e5032dbbfd0eedf",
    PROOF_B: "260e3396983b01ba6333d5e5bac7f41e45685eb51f342593c376558fa8d26205",
    HELPER_A: "286b1b564f4095532b95c509aedd85001275b54b0da8a57dd72a506a23b96c63",
    HELPER_B: "4a666e511387566738c65826717ea9f40fb54ed1ba4d7d28347a7a264d40c543",
    SEED: SEED_SHA,
}
UPSTREAM = {
    "src/judge.py": "4decf04790b90a03368eb792dfe29045435914a73ab83a52185d9dd0d1613902",
    "src/score.py": "418985a40e9e159cfeffe9a43ab2c727010d7a7a29407f4e14cab3c81b77cbae",
    "src/common.py": "ba60bf0f2a409c3774d75880f305325a28ed34320610667542a4596c41f424af",
    "src/evaluation_io.py": "8a34e01308677469d984dd59e36412c2994baf2554fd3a5f026be9ef98a3a5c7",
    "src/summarize.py": "0a8bd1eb7f317584f579eaa827e580f9cefe4177a1abdc35b2cb06ef96eeea9e",
    "src/partition.py": "263970891ff3ee1cc8df369a33beefe5cb5de618b5dd146a5234536d97954aca",
    "LICENSE": "14e69e7fbb2f8fd0aa8ccf17d7d4ddd54665555c613a0336767f7a5fa477895c",
    "uv.lock": "ff6d5b15b77e4ca46a33604586eb7d99666d2802752ab962af9baa2924a50758",
    "data/curated.jsonl": "ca9b6f470e5d7f7e34a281e2fdaa6f6e51c38bdae075ea580d184139ec391fa7",
}
CAPS = {"openai": "openai.chat-completions.v1", "anthropic": "anthropic.messages.v1"}
KEYS = {name: "offline-baseline-not-a-real-" + name + "-key" for name in CAPS}
STAGES = ["generation", "partition", "score", "summary"]
MODULES = ["src.score", "src.summarize", "src.common", "src.judge", "src.evaluation_io"]


def sha(raw):
    return hashlib.sha256(raw).hexdigest()


def save(path, value):
    path.write_bytes((json.dumps(value, indent=2, sort_keys=True) + "\n").encode())


def sample(index):
    # Literal expectations, never an agent invocation in the host process.
    return (
        ("poor duplicate", "poor duplicate", None, "stop"),
        ("poor duplicate", "poor duplicate", None, "stop"),
        (" \n", "[empty]", None, "stop"),
        ("raw refusal content", "[refused]", "declined", "stop"),
        (" unfinished JSON {", " unfinished JSON {", None, "length"),
    )[index % 5]


def official_copy(target):
    for name, expected in UPSTREAM.items():
        raw = (SOURCE / name).read_bytes()
        assert sha(raw) == expected, name
        destination = target / name
        destination.parent.mkdir(parents=True, exist_ok=True)
        destination.write_bytes(raw)


def runner_copy(target, names):
    for name in names:
        destination = target / "buddha" / (name + ".py")
        destination.parent.mkdir(parents=True, exist_ok=True)
        destination.write_bytes((ROOT / "buddha" / (name + ".py")).read_bytes())


def installed_environment(env):
    raw = (ROOT / "runs/reviews/nb02c3b-runtime-installed.json").read_bytes()
    assert sha(raw) == env["installed_manifest"]["sha256"]
    return {
        "helper_sha256": env["audit_helper"]["sha256"],
        "manifest_sha256": env["installed_manifest"]["sha256"],
        "inventory": json.loads(raw)["inventory"],
        "synthetic_modules": env["synthetic_modules"],
        "derived_modules": env["derived_modules"],
    }


def arguments(module):
    result = ["--eval-dir", "{artifacts}", "--version", "1.1"]
    if module == "src.partition":
        result += [
            "--alg",
            "llm",
            "--judge-model",
            "test-model",
            "--seed",
            "7",
            "--concurrency",
            "2",
        ]
    elif module == "src.score":
        result += [
            "--scorer",
            "llm",
            "--judge-model",
            "test-model",
            "--fallback-judge",
            "claude-fallback",
            "--patience",
            "0.8",
            "--concurrency",
            "2",
        ]
    return result


def hooks():
    return {
        "modules": MODULES + ["src.partition"],
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
    }


class Connection:
    def __init__(self, owner, host, **options):
        assert host in {"api.openai.com", "api.anthropic.com"}
        assert options == {"timeout": 15}
        self.owner, self.provider = owner, "openai" if host == "api.openai.com" else "anthropic"

    def request(self, method, path, *, body, headers):
        assert self.provider == "openai" and method == "POST" and path == "/v1/chat/completions"
        assert headers["Authorization"] == "Bearer " + KEYS[self.provider]
        record = json.loads(body)
        self.model = record["model"]
        self.stage = (
            "generation"
            if self.model == "seed-fixture"
            else (
                "partition"
                if record["response_format"]["json_schema"]["name"] == "Partition"
                else "score"
            )
        )
        self.index = sum(item["stage"] == self.stage for item in self.owner.sends)
        if not self.owner.sends or self.owner.sends[-1]["stage"] != self.stage:
            print(json.dumps({"physical_stage": self.stage}), flush=True)
        self.owner.sends.append(
            {
                "stage": self.stage,
                "provider": self.provider,
                "model": self.model,
                "body_sha256": sha(body),
                "headers": {
                    key.lower(): value
                    for key, value in headers.items()
                    if key.lower() not in {"authorization", "x-api-key"}
                },
            }
        )

    def getresponse(self):
        return self

    status = 200

    def read(self, maximum):
        if self.stage == "generation":
            literal, _, refusal, finish = sample(self.index)
            usage = {"prompt_tokens": 5, "completion_tokens": 3, "total_tokens": 8}
        else:
            literal = (
                '{"groups":[[0,2,4,6,8],[1,3,5,7,9]]}'
                if self.stage == "partition"
                else '{"score":7}'
            )
            refusal, finish = None, "stop"
            usage = {"prompt_tokens": 1, "completion_tokens": 2, "total_tokens": 3}
        value = {
            "id": "cmpl-baseline-fixture",
            "object": "chat.completion",
            "created": 0,
            "model": self.model,
            "service_tier": "default",
            "choices": [
                {
                    "index": 0,
                    "message": {"role": "assistant", "content": literal, "refusal": refusal},
                    "finish_reason": finish,
                }
            ],
            "usage": usage,
        }
        raw = _json(value)
        assert len(raw) < maximum
        return raw

    def getheaders(self):
        return [
            ("content-type", "application/json"),
            ("x-request-id", "synthetic-baseline-" + self.stage + "-" + str(self.index)),
        ]

    def close(self):
        pass


class Fixture:
    def __init__(self, directory, env_a, env_b):
        self.directory = directory
        self.sends = []
        self.docker = shutil.which("docker")
        assert self.docker
        self.endpoint = _endpoint(self.docker)
        self.env_a, self.env_b = env_a, env_b
        self.native_environment = installed_environment(env_b)
        shared = {name: directory / name for name in ("official", "agent", "host")}
        for path in shared.values():
            path.mkdir(parents=True)
        official_copy(shared["official"])
        (shared["agent"] / "frozen_seed.py").write_bytes(SEED.read_bytes())
        profiles, observed = {}, json.loads(PROOF_B.read_bytes())["observed_linux_sdk_headers"]
        for name, provider, model, maximum in (
            ("seed", "openai", "seed-fixture", 100),
            ("judge", "openai", "test-model", 128_000),
            ("fallback", "anthropic", "claude-fallback", 128_000),
        ):
            profiles[name] = {
                "spec": asdict(
                    ModelSpec(
                        provider,
                        model,
                        2_000_000,
                        maximum,
                        1_000_000,
                        2_000_000,
                        "https://example.org/offline-synthetic-only",
                    )
                ),
                "response_models": [model],
                "request_tiers": ["auto", "default"],
                "response_tiers": ["", "default"],
                "allow_omitted_tier": True,
                "headers": {} if name == "seed" else observed[provider],
                "account_headers": {},
            }
        (shared["host"] / "profiles.json").write_bytes(
            _json({"format": "buddha.gateway-profiles.v2", "profiles": profiles})
        )
        commands = [
            {"module": name, "argv": arguments(name)}
            for name in ("src.partition", "src.score", "src.summarize")
        ]
        self.release = Release.from_record(
            {
                "format": "buddha.benchmark-release.v1",
                "benchmark": "noveltybench",
                "release": "1.1-curated-offline-baseline-fixture",
                "upstream": {
                    "url": "https://github.com/novelty-bench/novelty-bench",
                    "revision": PIN,
                },
                "source": inventory(shared["official"]),
                "dependency_lock": "uv.lock",
                "task": {
                    "dataset": "data/curated.jsonl",
                    "id_field": "id",
                    "prompt_field": "prompt",
                    "answers_field": "generations",
                    "count": 10,
                },
                "commands": commands,
                "artifacts": {
                    "answers": "generations.jsonl",
                    "results": ["v1.1/partitions.jsonl", "v1.1/scores.jsonl"],
                    "summary": "v1.1/summary.json",
                },
                "requires": sorted(CAPS.values()),
            }
        )
        self.tasks = TaskSet.from_file(
            self.release, shared["official"] / "data/curated.jsonl"
        ).select(["curated-9", "curated-0"])
        tasks_path = directory / "tasks.json"
        tasks_path.write_bytes(self.tasks.to_bytes())
        selections, role_roots = {}, {}
        for role, names, env in (
            ("generation", AGENT_RUNNER, env_a),
            ("native", NATIVE_RUNNER, env_b),
        ):
            roots = shared | {
                key: directory / (role + "-" + key) for key in ("runner", "environment")
            }
            for key in ("runner", "environment"):
                roots[key].mkdir()
            runner_copy(roots["runner"], names)
            (roots["environment"] / "environment.json").write_bytes(_json(env))
            selections[role] = prepare_selection(
                self.release, roots, capabilities={cap: "profiles.json" for cap in CAPS.values()}
            )
            role_roots[role] = roots
        self.selections, self.roots = selections, role_roots
        self.generation_descriptor = directory / "generation.json"
        self.generation_descriptor.write_bytes(
            _json(
                {
                    "format": "buddha.frozen-generation.v1",
                    "tasks": str(tasks_path),
                    "config": {
                        "provider": "openai",
                        "model": "seed-fixture",
                        "max_output_tokens": 100,
                        "instructions": "Follow every literal requirement.",
                        "sampling": "regenerate",
                    },
                    "entrypoint": "frozen_seed.py",
                    "executor": self.executor("agent", env_a)
                    | {
                        "mounts": [
                            ["/agent", str(shared["agent"])],
                            ["/runner", str(role_roots["generation"]["runner"])],
                        ]
                    },
                    "profile": {"capability": CAPS["openai"], "profile_id": "seed"},
                }
            )
        )
        descriptor = {
            "format": "buddha.native-baseline.v1",
            "tasks": str(tasks_path),
            "generation": {
                "selection": selections["generation"].to_record(),
                "roots": {key: str(value) for key, value in role_roots["generation"].items()},
                "descriptor": str(self.generation_descriptor),
                "budget_microusd": 5_000_000,
                "max_calls": 30,
            },
            "native": {
                "selection": selections["native"].to_record(),
                "roots": {key: str(value) for key, value in role_roots["native"].items()},
                "environment": self.native_environment,
                "hooks": hooks(),
                "executor": self.executor("evaluator", env_b),
                "profiles": {
                    "openai": {"test-model": "judge"},
                    "anthropic": {"claude-fallback": "fallback"},
                },
                "budget_microusd": 5_000_000,
                "max_calls": 30,
            },
            "stages": [
                {
                    "inputs": ["generations.jsonl"],
                    "outputs": [{"path": "v1.1/partitions.jsonl", "id_field": "id"}],
                    "allow_model": True,
                },
                {
                    "inputs": ["v1.1/partitions.jsonl"],
                    "outputs": [{"path": "v1.1/scores.jsonl", "id_field": "id"}],
                    "allow_model": True,
                },
                {
                    "inputs": ["v1.1/scores.jsonl"],
                    "outputs": [{"path": "v1.1/summary.json", "id_field": None}],
                    "allow_model": False,
                },
            ],
        }
        self.descriptor = directory / "baseline.json"
        self.descriptor.write_bytes(_json(descriptor))
        self.authority = Authorization.create(
            directory / "authorization.sqlite3",
            authorization_id="baseline-proof",
            budget_microusd=10_000_000,
            max_calls=50,
            scope="offline actual baseline proof; fake HTTPS only",
        )
        self.baseline = prepare_baseline(
            directory / "baseline",
            descriptor=self.descriptor,
            authorization=self.authority,
            review={
                "checked_on": datetime.now(UTC).date().isoformat(),
                "credential_sha256": {name: sha(key.encode()) for name, key in KEYS.items()},
                "account_scope": "offline synthetic replies only",
            },
        )

    def executor(self, role, env):
        return {
            "image_id": env["image"].split("@")[-1],
            "role": role,
            "runner_entrypoint": "buddha/agent_worker.py"
            if role == "agent"
            else "buddha/native_worker.py",
            "image_environment": [item.split("=", 1) for item in env["config"]["Env"]],
            "limits": asdict(Limits(wall_seconds=180, memory_mib=2048)),
            "docker_endpoint": self.endpoint,
        }

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

    def run(self, *, interrupt=False, keyless=False):
        original, fired = RawHTTPTransport.send_prepared, False

        def received(transport, prepared):
            nonlocal fired
            reply = original(transport, prepared)
            if interrupt and not fired and self.sends[-1]["stage"] == "score":
                fired = True
                raise ReceivedReply(reply, KeyboardInterrupt())
            return reply

        keys = {
            key: value
            for key, value in os.environ.items()
            if key not in {"OPENAI_API_KEY", "ANTHROPIC_API_KEY"}
        }
        if not keyless:
            keys.update(OPENAI_API_KEY=KEYS["openai"], ANTHROPIC_API_KEY=KEYS["anthropic"])
        before, previous = self.containers(), len(self.sends)
        report, stopped = None, False
        with (
            patch.dict(os.environ, keys, clear=True),
            patch("socket.create_connection", side_effect=AssertionError("real network forbidden")),
            patch(
                "http.client.HTTPSConnection",
                side_effect=AssertionError("keyless send")
                if keyless
                else lambda host, **options: Connection(self, host, **options),
            ),
            patch.object(RawHTTPTransport, "send_prepared", received),
        ):
            try:
                report = run_baseline(
                    self.baseline,
                    transport=RawHTTPTransport(allow_paid=not keyless, timeout_seconds=15),
                )
            except KeyboardInterrupt:
                assert interrupt and fired
                stopped = True
        after = self.containers()
        assert not set(after) - set(before)
        result = {
            "interrupted": stopped,
            "keyless": keyless,
            "report": report,
            "new_sends": self.sends[previous:],
            "owned_containers_before": before,
            "owned_containers_after": after,
            "authority": self.authority.summary(),
        }
        print(
            json.dumps(
                {"interrupted": stopped, "keyless": keyless, "new_sends": len(result["new_sends"])}
            ),
            flush=True,
        )
        return result

    def owners(self):
        result = []
        for index in range(4):
            directory = self.baseline / "owners" / str(index)
            if not directory.exists():
                continue
            gateway = Gateway(directory, transport=RawHTTPTransport(allow_paid=False))
            manifest = json.loads((directory / "manifest.json").read_bytes())
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
                        "actual_microusd": operation.actual_microusd,
                        "receipt_sha256": None if receipt is None else sha(_json(receipt)),
                        "request": None if receipt is None else receipt["request"],
                    }
                )
            result.append(
                {
                    "index": index,
                    "manifest_sha256": gateway.manifest_sha256,
                    "selection_sha256": manifest["selection_sha256"],
                    "authorization_path": manifest["authorization_path"],
                    "ledger": gateway.ledger.totals(),
                    "operations": operations,
                }
            )
        return result


def normalize(raw, path):
    if not path.endswith(".jsonl"):
        return raw
    return _json(
        sorted(
            [json.loads(line) for line in raw.splitlines()],
            key=lambda row: (type(row["id"]).__name__, str(row["id"])),
        )
    )


def direct(fixture, index, inputs):
    directory = fixture.directory / ("direct-" + str(index))
    roots = {role: directory / role for role in ("official", "runner", "inputs")}
    for path in roots.values():
        path.mkdir(parents=True)
    official_copy(roots["official"])
    runner_copy(roots["runner"], NATIVE_RUNNER)
    # shortcut: retain the two sealed research workers instead of refactoring
    # historical proofs. Extract common engineering staging only if reused again.
    for path, name in ((HELPER_A, "direct_score.py"), (HELPER_B, "direct_partition.py")):
        (roots["runner"] / name).write_bytes(path.read_bytes())
    descriptions = []
    for ordinal, (destination, raw) in enumerate(inputs.items()):
        name = str(ordinal) + ".bin"
        (roots["inputs"] / name).write_bytes(raw)
        descriptions.append({"source": name, "destination": destination, "sha256": sha(raw)})
    command = fixture.release.to_record()["commands"][index]
    command = {
        "index": index,
        "module": command["module"],
        "argv": [
            "/scratch/artifacts" if value == "{artifacts}" else value for value in command["argv"]
        ],
    }
    command["sha256"] = sha(_json(command))
    config = {
        "type": "configure",
        "format": "buddha.direct-partition-worker.v1"
        if index == 0
        else "buddha.direct-native-worker.v1",
        "fixture": {"mode": "valid", "primary_model": "test-model"},
        "command": command,
        "release_sha256": fixture.release.fingerprint(),
        "answers_sha256": fixture.answers_digest,
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
            "environment": fixture.native_environment,
        },
        "inputs": descriptions,
        "hooks": {
            "modules": MODULES + (["src.partition"] if index == 0 else []),
            "cache": None,
            "calls": [],
            "sdk": [],
        },
    }
    frames, files, finished = [], {}, set()

    def handle(frame):
        assert frame["type"] in {"ready", "capture", "file", "done"}
        frames.append(frame)
        if frame["type"] == "file":
            name = frame["path"]
            assert name not in finished
            data = files.setdefault(name, bytearray())
            assert len(data) == frame["offset"]
            data.extend(base64.b64decode(frame["data_base64"], validate=True))
            if frame["eof"]:
                finished.add(name)

    result = run_container(
        ContainerSpec(
            fixture.env_b["image"],
            "evaluator",
            tuple(("/" + role, root) for role, root in roots.items()),
            "direct_partition.py" if index == 0 else "direct_score.py",
            tuple(tuple(value.split("=", 1)) for value in fixture.env_b["config"]["Env"]),
        ),
        initial=config,
        handle=handle,
        limits=Limits(wall_seconds=180, memory_mib=2048),
    )
    assert result.exit_code == 0 and result.cleanup_status == "removed"
    assert frames[0]["type"] == "ready" and frames[-1]["type"] == "done"
    assert frames[-1]["status"] == "complete" and set(files) == finished
    captures = [frame for frame in frames if frame["type"] == "capture"]
    assert all(frame["sdk_max_retries"] == 8 for frame in captures)
    print(json.dumps({"direct_stage": index, "captures": len(captures)}), flush=True)
    return (
        {
            "command": command,
            "captures": captures,
            "outcome": {
                "status": frames[-1]["status"],
                "reason": frames[-1]["reason"],
                "audit_sha256": sha(_json(frames[-1]["audit"])),
                "audit_module_count": len(frames[-1]["audit"]),
            },
            "configuration": result.configuration,
            "cleanup_status": result.cleanup_status,
        },
        {name: bytes(raw) for name, raw in files.items()},
    )


def main():
    for path, expected in SEALED.items():
        assert sha(path.read_bytes()) == expected, str(path)
    assert "agents.frozen_seed" not in sys.modules and "_buddha_frozen_seed" not in sys.modules
    names = sorted(set(AGENT_HOST) | set(NATIVE_RUNNER) | {"executor", "native_run", "baseline"})
    paths = [
        SCRIPT,
        *SEALED,
        ROOT / "runs/reviews/nb02c3b-runtime-installed.json",
        *[ROOT / "buddha" / (name + ".py") for name in names],
    ]
    before = {str(path.relative_to(ROOT)): sha(path.read_bytes()) for path in paths}
    core = _core_sources()
    env_a, env_b = json.loads(ENV_A.read_bytes()), json.loads(ENV_B.read_bytes())
    # Keep the original owners/receipts and failed attempts as ignored evidence;
    # never manufacture a fresh owner to recover an interrupted paid operation.
    with tempfile.TemporaryDirectory(
        prefix="nb02c3c3-baseline-", dir=ROOT / "runs/reviews", delete=False
    ) as folder:
        print(json.dumps({"fixture_directory": folder}), flush=True)
        fixture = Fixture(Path(folder), env_a, env_b)
        prefix = fixture.run(interrupt=True)
        assert prefix["interrupted"] and len(prefix["new_sends"]) == 23
        prefix["owners"] = fixture.owners()
        assert len(prefix["owners"]) == 3
        assert [item["ledger"]["operation_count"] for item in prefix["owners"]] == [20, 2, 1]
        assert all(
            operation["status"] == "completed"
            for item in prefix["owners"]
            for operation in item["operations"]
        )
        resumed = fixture.run()
        assert resumed["report"]["status"] == "complete" and len(resumed["new_sends"]) == 3
        owners = fixture.owners()
        assert len(owners) == 4 and [item["ledger"]["operation_count"] for item in owners] == [
            20,
            2,
            4,
            0,
        ]
        assert len({item["authorization_path"] for item in owners}) == 1
        assert owners[:2] == prefix["owners"][:2]
        assert owners[2]["manifest_sha256"] == prefix["owners"][2]["manifest_sha256"]
        assert all(
            operation in owners[2]["operations"] for operation in prefix["owners"][2]["operations"]
        )
        reuse = fixture.run(keyless=True)
        assert reuse["report"]["status"] == "complete" and reuse["new_sends"] == []
        assert fixture.owners() == owners
        assert reuse["authority"] == resumed["authority"]
        # Root API's completion seals locate exact required artifacts without
        # guessing which attempt finished after the genuine score interruption.
        completions = [
            json.loads((fixture.baseline / "completed" / (str(index) + ".json")).read_bytes())
            for index in range(4)
        ]
        evidence = {
            "format": "buddha.review.nb02c3c3-baseline.v1",
            "fixture_directory": folder,
            "actual_provider_calls": 0,
            "actual_keys_used": False,
            "host_agent_execution": False,
            "host_official_execution": False,
            "prefix": prefix,
            "resumed": resumed,
            "keyless_reuse": reuse,
            "owners": owners,
            "completions": completions,
            "selections": {key: value.to_record() for key, value in fixture.selections.items()},
        }
        attempts = [fixture.baseline / record["attempt"] for record in completions]
        answer_file = attempts[0] / "answers.json"
        fixture.answers_digest = sha(answer_file.read_bytes())
        answers = Answers.from_bytes(answer_file.read_bytes())
        answer_record = answers.to_record()
        assert answer_record["tasks_sha256"] == fixture.tasks.fingerprint()
        assert answer_record["agent_sha256"] == fixture.selections["generation"].agent_sha256
        assert answer_record["metadata"] == {}
        assert answer_record["outputs"] == [
            {"task_id": task.id, "answers": [sample(index)[1] for index in range(10)]}
            for task in fixture.tasks.tasks
        ]
        generations = (fixture.baseline / "native-answers.jsonl").read_bytes()
        assert generations == answers.native_bytes()
        source_rows = {
            row["id"]: row
            for row in (
                json.loads(line)
                for line in (SOURCE / "data/curated.jsonl").read_bytes().splitlines()
            )
        }
        native_rows = [json.loads(line) for line in generations.splitlines()]
        assert native_rows == [
            source_rows[task.id] | {"generations": output["answers"]}
            for task, output in zip(fixture.tasks.tasks, answer_record["outputs"], strict=True)
        ]
        assert resumed["authority"]["operation_count"] == 26
        assert resumed["authority"]["spent_microusd"] == 250
        assert resumed["authority"]["reserved_microusd"] == 0
        assert len(resumed["authority"]["runs"]) == 4
        assert all(not run["active"] for run in resumed["authority"]["runs"])
        for index, owner in enumerate(owners):
            operations = owner["operations"]
            assert all(operation["status"] == "completed" for operation in operations)
            identifiers = [operation["request"]["logical_id"] for operation in operations]
            assert len(set(identifiers)) == len(identifiers)
            assert all(operation["request"]["attempt"] == 0 for operation in operations)
            assert resumed["report"]["stages"][index]["status"] == "complete"
        generation_execution = resumed["report"]["stages"][0]["executions"]
        assert len(generation_execution) == 2
        for execution in generation_execution:
            configuration = execution["configuration"]
            assert configuration["role"] == "agent"
            assert set(configuration["mounts"]) == {"/agent", "/runner"}
            assert execution["exit_code"] == 0 and execution["cleanup_status"] == "removed"
        summary_descriptor = json.loads((fixture.baseline / "command-3.json").read_bytes())
        assert summary_descriptor["profiles"] == {}
        assert resumed["report"]["stages"][3]["calls"]["requested"] == 0
        direct_inputs, comparisons = {"generations.jsonl": generations}, []
        for index, required in enumerate(
            ("v1.1/partitions.jsonl", "v1.1/scores.jsonl", "v1.1/summary.json")
        ):
            direct_evidence, direct_files = direct(fixture, index, direct_inputs)
            report = resumed["report"]["stages"][index + 1]
            funded_files = {
                name: (attempts[index + 1] / "artifacts" / name).read_bytes()
                for name in report["artifacts"]
            }
            assert set(direct_files) == set(funded_files)
            for name, raw in funded_files.items():
                assert sha(raw) == report["artifacts"][name]
                assert normalize(raw, name) == normalize(direct_files[name], name), name
            actual = Counter(
                sha(base64.b64decode(operation["request"]["body_base64"], validate=True))
                for operation in owners[index + 1]["operations"]
            )
            expected = Counter(capture["body_sha256"] for capture in direct_evidence["captures"])
            assert actual == expected
            if index < 2:
                for row in (json.loads(line) for line in funded_files[required].splitlines()):
                    # Official partition deliberately keeps only INPUT_FIELDS;
                    # score retains that partition row. Extra category metadata
                    # remains in C1, rather than being invented in native results.
                    original = source_rows[row["id"]]
                    assert row["prompt"] == original["prompt"]
                    assert row["prompt_paraphrases"] == original["prompt_paraphrases"]
                    assert row["generations"] == [sample(position)[1] for position in range(10)]
                    assert "category" not in row
            comparisons.append(
                {
                    "stage": index + 1,
                    "required": required,
                    "direct": direct_evidence,
                    "files": {
                        name: {"sha256": sha(raw), "bytes": len(raw)}
                        for name, raw in funded_files.items()
                    },
                    "request_body_multiset_equal": True,
                    "native_artifacts_equal": "typed-ID row-order normalization only",
                }
            )
            direct_inputs = {required: direct_files[required]}
        assert sum(len(item["direct"]["captures"]) for item in comparisons) == 6
        assert len(fixture.sends) == 26
        assert (
            sha(Path(resumed["report"]["summary"]["path"]).read_bytes())
            == (resumed["report"]["summary"]["sha256"])
        )
        evidence.update(
            comparisons=comparisons,
            expected_task_ids=[task.id for task in fixture.tasks.tasks],
            answers_sha256=fixture.answers_digest,
            native_answers_sha256=sha(generations),
            native_answer_rows=native_rows,
            mocked_physical_sends=len(fixture.sends),
            direct_captures=6,
            limits=[
                "synthetic model replies; no semantic or improvement claim",
                "reviewed fixed seed only; arbitrary evolved agents not enabled",
                "summary has no model profile and uses a nonpaying transport",
                "complete reuse validates stored stages; no new containers or sends",
                "source, API and SDK network timing equivalence not claimed",
            ],
        )
    assert before == {str(path.relative_to(ROOT)): sha(path.read_bytes()) for path in paths}
    assert _core_sources() == core
    assert "agents.frozen_seed" not in sys.modules and "_buddha_frozen_seed" not in sys.modules
    evidence.update(source_sha256=before, gateway_core_sha256=core, upstream_sha256=UPSTREAM)
    output = ROOT / "runs/reviews/nb02c3c3-baseline-evidence.json"
    save(output, evidence)
    print(json.dumps({"actual_provider_calls": 0, "evidence": str(output)}), flush=True)


if __name__ == "__main__":
    main()
