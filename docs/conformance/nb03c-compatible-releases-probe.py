"""Actual configuration-only upgrade and retirement, with synthetic HTTPS.

The parent copies an explicit neutral host closure. A fresh isolated child runs
both baselines, unchanged generic direct oracles and sealed read-only history.
No legacy evaluator, host SDK, original agent execution or paid traffic is used.
"""

import base64
import hashlib
import json
import os
import shutil
import sqlite3

# Used only for the fixed isolated interpreter and copied trusted proof driver.
import subprocess  # nosec B404
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

MODULES = (
    "__init__",
    "common",
    "gateway",
    "gateway_history",
    "authorization",
    "history",
    "ledger",
    "provider",
    "releases",
    "wire",
    "agent_run",
    "agent_worker",
    "answers",
    "channel",
    "executor",
    "native_run",
    "native_worker",
    "native_context",
    "native_transport",
    "baseline",
)
FORBIDDEN = ("benchmark", "evaluation", "run", "search", "policy")
ENV_SHA = "dc58b658821a536d13c300b6b1f756aa8dc3b2adcc5699627a4827f8361f7d9a"
SDK_PROOF_SHA = "fbea43d8d3b34dd683bc34e1a7220ed601a2dfb7eba1f0a71ee52f5b49c68c7b"
SEED_SHA = "2b87bfe0d3c97ee45db2d45260985ffe0234eca93967f4689fb7c59f82603921"


def sha(raw):
    return hashlib.sha256(raw).hexdigest()


def save(path, value):
    path.write_bytes((json.dumps(value, indent=2, sort_keys=True) + "\n").encode())


def launch():
    repository = Path(__file__).resolve().parents[2]
    fixture = Path(
        tempfile.mkdtemp(prefix="nb03c-compatible-", dir=repository / "runs/reviews")
    ).resolve()
    active = fixture / "host"
    (active / "buddha").mkdir(parents=True)
    (active / "agents").mkdir()
    sources = {}
    for name in MODULES:
        source = repository / "buddha" / (name + ".py")
        raw = source.read_bytes()
        (active / "buddha" / source.name).write_bytes(raw)
        sources[str(source.relative_to(repository))] = sha(raw)
    seed = (repository / "agents/frozen_seed.py").read_bytes()
    assert sha(seed) == SEED_SHA
    (active / "agents/frozen_seed.py").write_bytes(seed)
    helper = repository / "docs/conformance/nb03c-direct-worker.py"
    (active / "oracle.py").write_bytes(helper.read_bytes())
    driver = active / "probe.py"
    driver.write_bytes(Path(__file__).read_bytes())
    env_path = repository / "docs/conformance/nb02c3-runtime-environment.json"
    sdk_path = repository / "docs/conformance/nb02c3-funded-native-evidence.json"
    assert sha(env_path.read_bytes()) == ENV_SHA
    assert sha(sdk_path.read_bytes()) == SDK_PROOF_SHA
    installed = repository / "runs/reviews/nb02c3-runtime-installed.json"
    watched = [
        Path(__file__).resolve(),
        helper,
        env_path,
        sdk_path,
        installed,
        repository / "agents/frozen_seed.py",
    ]
    sources.update({str(path.relative_to(repository)): sha(path.read_bytes()) for path in watched})
    context = fixture / "context.json"
    save(
        context, {"repository": str(repository), "fixture": str(fixture), "source_sha256": sources}
    )
    environment = {
        name: value
        for name, value in os.environ.items()
        if name not in {"OPENAI_API_KEY", "ANTHROPIC_API_KEY", "PYTHONPATH"}
    }
    print(json.dumps({"fixture_directory": str(fixture)}), flush=True)
    # Fixed interpreter, copied trusted driver and literal data arguments; no shell.
    result = subprocess.run(  # nosec B603
        [
            sys.executable,
            "-I",
            "-S",
            "-B",
            "-X",
            "pycache_prefix=" + str(fixture / "absent-cache"),
            str(driver),
            "--child",
            str(context),
        ],
        cwd=fixture,
        env=environment,
        # Explicit stream handles also work for a hidden child on Windows.
        stdout=sys.stdout,
        stderr=sys.stderr,
        check=False,
        creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0) if os.name == "nt" else 0,
    )
    if result.returncode:
        raise SystemExit(result.returncode)
    for name, expected in sources.items():
        assert sha((repository / name).read_bytes()) == expected, name


if len(sys.argv) != 3 or sys.argv[1] != "--child":
    launch()
    raise SystemExit(0)

CONTEXT = json.loads(Path(sys.argv[2]).read_bytes())
REPOSITORY, FIXTURE = Path(CONTEXT["repository"]), Path(CONTEXT["fixture"])
ACTIVE = Path(__file__).resolve().parent
sys.path.insert(0, str(ACTIVE))

from oracle import synthetic_reply  # noqa: E402

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
from buddha.gateway import (  # noqa: E402
    Gateway,
    GatewayCall,
    GatewayError,
    RawHTTPTransport,
    _core_sources,
    prepare_gateway,
)
from buddha.gateway_history import read_gateway_history  # noqa: E402
from buddha.native_run import RUNNER_FILES as NATIVE_RUNNER  # noqa: E402
from buddha.provider import ModelSpec, ProviderUncertain  # noqa: E402
from buddha.releases import (  # noqa: E402
    Release,
    ReleaseError,
    _json,
    inventory,
    prepare_selection,
    verify_selection,
)

CAPS = {"openai": "openai.chat-completions.v1", "anthropic": "anthropic.messages.v1"}
KEYS = {name: "offline-mod03-not-a-real-" + name + "-key" for name in CAPS}
ENV = json.loads((REPOSITORY / "docs/conformance/nb02c3-runtime-environment.json").read_bytes())
INSTALLED_RAW = (REPOSITORY / "runs/reviews/nb02c3-runtime-installed.json").read_bytes()
assert sha(INSTALLED_RAW) == ENV["installed_manifest"]["sha256"]
NATIVE_ENV = {
    "helper_sha256": ENV["audit_helper"]["sha256"],
    "manifest_sha256": ENV["installed_manifest"]["sha256"],
    "inventory": json.loads(INSTALLED_RAW)["inventory"],
    "synthetic_modules": ["_cython_3_1_0", "_cython_3_1_3", "cython_runtime", "six.moves"],
}

# These are two ORIGINAL canned evaluator implementations. They execute only in
# Docker, both directly and through the unchanged production worker. The host
# installs these bytes as data, never imports/compiles the evaluator functions.
INSTRUMENT = r"""
import argparse
import asyncio
import hashlib
import json
from pathlib import Path
from openai import AsyncOpenAI
from anthropic import AsyncAnthropic

SPEC = @@SPEC@@
DEPENDENCY = json.loads((Path(__file__).parent / "support/schema.json").read_text())

class Refused(Exception):
    pass

def evaluation_key(instance, config):
    return hashlib.sha256(json.dumps([instance, config], sort_keys=True).encode()).hexdigest()

async def map_rows(instances, output_file, key_field, config, compute, concurrency=1):
    rows = []
    for instance in instances:
        fields = await compute(instance)
        rows.append(instance | fields | {key_field: evaluation_key(instance, config)})
    output = Path(output_file)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text("".join(json.dumps(row) + "\n" for row in rows))

async def judge(provider, model, text):
    if provider == "openai":
        async with AsyncOpenAI(max_retries=8) as client:
            response = await client.chat.completions.create(
                model=model, messages=[{"role": "user", "content": text}], max_completion_tokens=32)
        message = response.choices[0]
        if message.message.refusal:
            raise Refused()
        if message.finish_reason == "length":
            raise ValueError("truncated judgment")
        value = json.loads(message.message.content)["value"]
    else:
        async with AsyncAnthropic(max_retries=8) as client:
            response = await client.messages.create(
                model=model, messages=[{"role": "user", "content": text}], max_tokens=32)
        value = json.loads(response.content[0].text)["value"]
    if (SPEC["kind"] == "integer" and type(value) is not int) or (
        SPEC["kind"] == "text" and type(value) is not str):
        raise ValueError("wrong native judgment shape")
    return value

async def main():
    parser = argparse.ArgumentParser()
    for flag, destination in zip(SPEC["flags"], ["root", "action", "input", "output"], strict=True):
        parser.add_argument(flag, dest=destination, required=True)
    args = parser.parse_args()
    rows = [json.loads(line) for line in (Path(args.root) / args.input).read_text().splitlines()]
    target = Path(args.root) / args.output
    if args.action == SPEC["evaluate"]:
        async def compute(row):
            text = json.dumps({"judge_kind": SPEC["kind"], "row": row}, sort_keys=True)
            for attempt in range(3):
                try:
                    value = await judge("openai", "fixture-judge", text)
                    break
                except Refused:
                    value = await judge("anthropic", "claude-fixture", text)
                    break
                except ValueError:
                    if attempt == 2:
                        raise
            return {SPEC["metric"]: value, "outer_count": len(row[SPEC["answers"]])}
        await map_rows(rows, target, "native_key", SPEC, compute, 1)
    elif args.action == SPEC["summarize"]:
        target.parent.mkdir(parents=True, exist_ok=True)
        if SPEC["kind"] == "integer":
            mean_grade = sum(row[SPEC["metric"]] for row in rows) / len(rows)
            target.write_text(json.dumps({"schema": DEPENDENCY["tag"], "rows": len(rows),
                                          "mean_grade": mean_grade}))
        else:
            target.write_text("instrument,labels\n" + DEPENDENCY["tag"] + "," +
                              "|".join(row[SPEC["metric"]] for row in rows) + "\n")
    else:
        raise ValueError("unknown original evaluator action")
"""

SPECS = {
    "A": {
        "module": "alpha",
        "count": 2,
        "id": "id",
        "prompt": "prompt",
        "answers": "generations",
        "kind": "integer",
        "metric": "grade",
        "flags": ["--root", "--step", "--input", "--output"],
        "evaluate": "evaluate",
        "summarize": "summary",
        "generation_path": "generations.jsonl",
        "result_path": "vA/marks.jsonl",
        "summary_path": "vA/summary.json",
        "controls": ["malformed", "ordinary"],
    },
    "B": {
        "module": "nested.beta",
        "count": 3,
        "id": "case",
        "prompt": "question",
        "answers": "replies",
        "kind": "text",
        "metric": "ribbon",
        "flags": ["--workspace", "--action", "--source", "--target"],
        "evaluate": "measure",
        "summarize": "publish",
        "generation_path": "texts/ordered.ndjson",
        "result_path": "revision2/findings.jsonl",
        "summary_path": "revision2/report.csv",
        "controls": ["refusal", "truncated"],
    },
}


def copied_runner(root, names):
    for name in names:
        target = root / "buddha" / (name + ".py")
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes((ACTIVE / "buddha" / target.name).read_bytes())


def executor(role):
    return {
        "image_id": ENV["image_id"],
        "role": role,
        "runner_entrypoint": "buddha/agent_worker.py"
        if role == "agent"
        else "buddha/native_worker.py",
        "image_environment": [item.split("=", 1) for item in ENV["config"]["Env"]],
        "limits": asdict(Limits(wall_seconds=120)),
        "docker_endpoint": ENDPOINT,
    }


def configured_hooks(module):
    return {
        "modules": [module],
        "cache": {
            "target": module + ":map_rows",
            "key_target": module + ":evaluation_key",
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
        "calls": [{"target": module + ":judge", "label": "judge"}],
        "sdk": [
            {
                "provider": provider,
                "constructor": package + ":" + constructor,
                "module_slots": [module + ":" + constructor],
            }
            for provider, package, constructor in (
                ("openai", "openai", "AsyncOpenAI"),
                ("anthropic", "anthropic", "AsyncAnthropic"),
            )
        ],
    }


DOCKER = shutil.which("docker")
assert DOCKER
ENDPOINT = _endpoint(DOCKER)


class Server:
    def __init__(self):
        self.release, self.unknown, self.sends, self.counts = "", False, [], {}


class Connection:
    def __init__(self, owner, host, **options):
        assert host in {"api.openai.com", "api.anthropic.com"} and options == {"timeout": 15}
        self.owner, self.provider = owner, "openai" if host == "api.openai.com" else "anthropic"

    def request(self, method, path, *, body, headers):
        assert method == "POST" and path == (
            "/v1/chat/completions" if self.provider == "openai" else "/v1/messages"
        )
        assert (
            headers.get("Authorization") == "Bearer " + KEYS[self.provider]
            if self.provider == "openai"
            else headers.get("x-api-key") == KEYS[self.provider]
        )
        self.body, self.model = body, json.loads(body)["model"]
        self.phase = "generation" if self.model == "seed-fixture" else "native"
        self.index = sum(
            row["release"] == self.owner.release and row["phase"] == "generation"
            for row in self.owner.sends
        )
        self.owner.sends.append(
            {
                "release": self.owner.release,
                "phase": self.phase,
                "provider": self.provider,
                "model": self.model,
                "body_sha256": sha(body),
            }
        )

    def getresponse(self):
        return self

    status = 200

    def read(self, maximum):
        if self.phase == "generation":
            text, _, refusal, finish = seed_sample(self.owner.release, self.index)
            payload = {
                "id": "cmpl-compatible-seed",
                "object": "chat.completion",
                "created": 0,
                "model": self.model,
                "service_tier": "default",
                "choices": [
                    {
                        "index": 0,
                        "message": {"role": "assistant", "content": text, "refusal": refusal},
                        "finish_reason": finish,
                    }
                ],
                "usage": {"prompt_tokens": 5, "completion_tokens": 3, "total_tokens": 8},
            }
        else:
            payload = synthetic_reply(self.provider, self.body, self.owner.counts)
        if self.owner.unknown:
            payload.pop("usage")
        raw = _json(payload)
        assert len(raw) < maximum
        return raw

    def getheaders(self):
        return [
            ("content-type", "application/json"),
            ("x-request-id" if self.provider == "openai" else "request-id", "compatible-mock"),
        ]

    def close(self):
        pass


def seed_sample(release, index):
    values = (
        (
            ("wrong digit", "wrong digit", None, "stop"),
            ("wrong digit", "wrong digit", None, "stop"),
            ("{invalid task JSON", "{invalid task JSON", None, "stop"),
            (" \n", "[empty]", None, "stop"),
        )
        if release == "A"
        else (
            ("wrong digit", "wrong digit", None, "stop"),
            ("wrong digit", "wrong digit", None, "stop"),
            ("declined content", "[refused]", "declined", "stop"),
            (" \n", "[empty]", None, "stop"),
            (" unfinished {", " unfinished {", None, "length"),
            ("{invalid task JSON", "{invalid task JSON", None, "stop"),
        )
    )
    return values[index % len(values)]


def shared_roots():
    shared = {
        name: FIXTURE / "shared" / name
        for name in ("agent", "host", "environment", "generation-runner", "native-runner")
    }
    for path in shared.values():
        path.mkdir(parents=True)
    (shared["agent"] / "frozen_seed.py").write_bytes(
        (ACTIVE / "agents/frozen_seed.py").read_bytes()
    )
    (shared["environment"] / "environment.json").write_bytes(_json(ENV))
    copied_runner(shared["generation-runner"], AGENT_RUNNER)
    copied_runner(shared["native-runner"], NATIVE_RUNNER)
    observed = json.loads(
        (REPOSITORY / "docs/conformance/nb02c3-funded-native-evidence.json").read_bytes()
    )["observed_linux_sdk_headers"]
    profiles = {}
    for name, provider, model, maximum in (
        ("seed", "openai", "seed-fixture", 100),
        ("judge", "openai", "fixture-judge", 32),
        ("fallback", "anthropic", "claude-fixture", 32),
    ):
        profiles[name] = {
            "spec": asdict(
                ModelSpec(
                    provider,
                    model,
                    100_000,
                    maximum,
                    1_000_000,
                    2_000_000,
                    "https://example.org/synthetic-only-model-bounds",
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
    return shared


class Compatible:
    def __init__(self, label, shared, authority):
        self.label, self.spec = label, SPECS[label]
        spec = self.spec
        self.active = FIXTURE / "active" / label
        self.official = self.active / "official"
        self.official.mkdir(parents=True)
        module_path = self.official / (spec["module"].replace(".", "/") + ".py")
        module_path.parent.mkdir(parents=True, exist_ok=True)
        original = INSTRUMENT.replace("@@SPEC@@", repr(spec)).encode()
        module_path.write_bytes(original)
        dependency = module_path.parent / "support/schema.json"
        dependency.parent.mkdir()
        dependency.write_bytes(_json({"tag": "native-instrument-" + label}))
        self.nested = dependency
        (self.official / "fixture.lock").write_bytes(
            _json({"image": ENV["image_id"], "release": label})
        )
        identifiers = (1, "1") if label == "A" else ("1", 1)
        self.rows = [
            {
                spec["id"]: identifier,
                spec["prompt"]: prompt,
                "control": control,
                "metadata": {"literal": [False, None, "unseen-original-metadata"]},
            }
            for identifier, prompt, control in zip(
                identifiers,
                ("Return exactly one digit.", "Return exactly one valid JSON object."),
                spec["controls"],
                strict=True,
            )
        ]
        dataset_name = "data/tasks.jsonl" if label == "A" else "source/cases.ndjson"
        dataset = self.official / dataset_name
        dataset.parent.mkdir()
        dataset.write_bytes(b"".join(_json(row) + b"\n" for row in self.rows))
        commands = []
        for action, input_name, output_name in (
            (spec["evaluate"], spec["generation_path"], spec["result_path"]),
            (spec["summarize"], spec["result_path"], spec["summary_path"]),
        ):
            commands.append(
                {
                    "module": spec["module"],
                    "argv": [
                        value
                        for pair in zip(
                            spec["flags"],
                            ("{artifacts}", action, input_name, output_name),
                            strict=True,
                        )
                        for value in pair
                    ],
                }
            )
        self.release = Release.from_record(
            {
                "format": "buddha.benchmark-release.v1",
                "benchmark": "explicit-canned-compatibility-instrument",
                "release": label,
                "upstream": {
                    "url": "https://example.org/canned-compatibility-fixture",
                    "revision": sha(original),
                },
                "source": inventory(self.official),
                "dependency_lock": "fixture.lock",
                "task": {
                    "dataset": dataset_name,
                    "id_field": spec["id"],
                    "prompt_field": spec["prompt"],
                    "answers_field": spec["answers"],
                    "count": spec["count"],
                },
                "commands": commands,
                "artifacts": {
                    "answers": spec["generation_path"],
                    "results": [spec["result_path"]],
                    "summary": spec["summary_path"],
                },
                "requires": sorted(CAPS.values()),
            }
        )
        self.tasks = TaskSet.from_file(self.release, dataset).select(
            [self.rows[1][spec["id"]], self.rows[0][spec["id"]]]
        )
        tasks_path = self.active / "tasks.json"
        tasks_path.write_bytes(self.tasks.to_bytes())
        common = {name: shared[name] for name in ("agent", "host", "environment")} | {
            "official": self.official
        }
        self.roots = {
            role: common | {"runner": shared[role + "-runner"]} for role in ("generation", "native")
        }
        self.selections = {
            role: prepare_selection(
                self.release, roots, capabilities={cap: "profiles.json" for cap in CAPS.values()}
            )
            for role, roots in self.roots.items()
        }
        recipe = self.active / "generation.json"
        recipe.write_bytes(
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
                    "profile": {"capability": CAPS["openai"], "profile_id": "seed"},
                    "executor": executor("agent")
                    | {
                        "mounts": [
                            ["/agent", str(shared["agent"])],
                            ["/runner", str(shared["generation-runner"])],
                        ]
                    },
                }
            )
        )
        hook_data = configured_hooks(spec["module"])
        hook_data["cache"]["id_field"] = spec["id"]
        self.descriptor = self.active / "baseline.json"
        self.descriptor.write_bytes(
            _json(
                {
                    "format": "buddha.native-baseline.v1",
                    "tasks": str(tasks_path),
                    "generation": {
                        "selection": self.selections["generation"].to_record(),
                        "roots": {
                            name: str(path) for name, path in self.roots["generation"].items()
                        },
                        "descriptor": str(recipe),
                        "budget_microusd": 5_000_000,
                        "max_calls": 40,
                    },
                    "native": {
                        "selection": self.selections["native"].to_record(),
                        "roots": {name: str(path) for name, path in self.roots["native"].items()},
                        "environment": NATIVE_ENV,
                        "hooks": hook_data,
                        "executor": executor("evaluator"),
                        "profiles": {
                            "openai": {"fixture-judge": "judge"},
                            "anthropic": {"claude-fixture": "fallback"},
                        },
                        "budget_microusd": 5_000_000,
                        "max_calls": 40,
                    },
                    "stages": [
                        {
                            "inputs": [spec["generation_path"]],
                            "outputs": [{"path": spec["result_path"], "id_field": spec["id"]}],
                            "allow_model": True,
                        },
                        {
                            "inputs": [spec["result_path"]],
                            "outputs": [{"path": spec["summary_path"], "id_field": None}],
                            "allow_model": False,
                        },
                    ],
                }
            )
        )
        self.records = FIXTURE / "records" / label
        self.records.parent.mkdir(exist_ok=True)
        self.baseline = prepare_baseline(
            self.records, descriptor=self.descriptor, authorization=authority, review=review()
        )


def review():
    return {
        "checked_on": datetime.now(UTC).date().isoformat(),
        "credential_sha256": {name: sha(key.encode()) for name, key in KEYS.items()},
        "account_scope": "synthetic compatibility proof only",
    }


def containers():
    return sorted(
        _control(
            DOCKER,
            [
                "--host",
                ENDPOINT,
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


def owners(baseline):
    result = []
    for directory in sorted((baseline / "owners").iterdir()):
        gateway = Gateway(directory, transport=RawHTTPTransport(allow_paid=False))
        with closing(sqlite3.connect(gateway.ledger.path)) as connection:
            identifiers = [
                row[0]
                for row in connection.execute(
                    "SELECT operation_id FROM operations ORDER BY operation_id"
                )
            ]
        operations = [gateway.ledger.get(identifier) for identifier in identifiers]
        result.append(
            {
                "directory": str(directory),
                "manifest_sha256": gateway.manifest_sha256,
                "ledger_sha256": sha(gateway.ledger.path.read_bytes()),
                "totals": gateway.ledger.totals(),
                "requests": [operation.response["request"] for operation in operations],
            }
        )
    return result


def direct(fixture, index, inputs, answers_digest):
    root = FIXTURE / "direct" / (fixture.label + "-" + str(index))
    roots = {name: root / name for name in ("official", "runner", "inputs")}
    for path in roots.values():
        path.mkdir(parents=True)
    for name in inventory(fixture.official):
        path = roots["official"] / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes((fixture.official / name).read_bytes())
    copied_runner(roots["runner"], NATIVE_RUNNER)
    (roots["runner"] / "oracle.py").write_bytes((ACTIVE / "oracle.py").read_bytes())
    staged = []
    for ordinal, (name, raw) in enumerate(inputs.items()):
        source = str(ordinal) + ".bin"
        (roots["inputs"] / source).write_bytes(raw)
        staged.append({"source": source, "destination": name, "sha256": sha(raw)})
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
        "format": "buddha.compatible-direct.v1",
        "command": command,
        "release_sha256": fixture.release.fingerprint(),
        "answers_sha256": answers_digest,
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
            "environment": NATIVE_ENV,
        },
        "inputs": staged,
        "hooks": {"modules": [fixture.spec["module"]], "cache": None, "calls": [], "sdk": []},
    }
    frames, files, finished = [], {}, set()

    def handle(frame):
        assert frame["type"] in {"ready", "capture", "file", "done"}
        frames.append(frame)
        if frame["type"] == "file":
            name = frame["path"]
            assert name not in finished
            raw = files.setdefault(name, bytearray())
            assert len(raw) == frame["offset"]
            raw.extend(base64.b64decode(frame["data_base64"], validate=True))
            if frame["eof"]:
                finished.add(name)

    execution = run_container(
        ContainerSpec(
            ENV["image_id"],
            "evaluator",
            tuple(("/" + name, path) for name, path in roots.items()),
            "oracle.py",
            tuple(tuple(value.split("=", 1)) for value in ENV["config"]["Env"]),
        ),
        initial=config,
        handle=handle,
        limits=Limits(wall_seconds=120),
    )
    assert execution.exit_code == 0 and execution.cleanup_status == "removed"
    assert frames[0]["type"] == "ready" and frames[-1]["type"] == "done"
    assert frames[-1]["status"] == "complete" and set(files) == finished
    print(json.dumps({"direct_release": fixture.label, "stage": index}), flush=True)
    return (
        {
            "command": command,
            "captures": [frame for frame in frames if frame["type"] == "capture"],
            "configuration": execution.configuration,
            "cleanup_status": execution.cleanup_status,
            "audit_sha256": sha(_json(frames[-1]["audit"])),
        },
        {name: bytes(raw) for name, raw in files.items()},
    )


def complete(fixture, report):
    assert report["status"] == "complete"
    completed = [
        json.loads((fixture.baseline / "completed" / (str(index) + ".json")).read_bytes())
        for index in range(3)
    ]
    attempts = [fixture.baseline / item["attempt"] for item in completed]
    raw_answers = (attempts[0] / "answers.json").read_bytes()
    answers = Answers.from_bytes(raw_answers)
    record = answers.to_record()
    assert record["metadata"] == {} and record["tasks_sha256"] == fixture.tasks.fingerprint()
    assert record["agent_sha256"] == fixture.selections["generation"].agent_sha256
    expected = [
        {
            "task_id": task.id,
            "answers": [
                seed_sample(fixture.label, index * task.count + position)[1]
                for position in range(task.count)
            ],
        }
        for index, task in enumerate(fixture.tasks.tasks)
    ]
    assert record["outputs"] == expected
    generations = (fixture.baseline / "native-answers.jsonl").read_bytes()
    assert generations == answers.native_bytes()
    source = {row[fixture.spec["id"]]: row for row in fixture.rows}
    assert [json.loads(line) for line in generations.splitlines()] == [
        source[output["task_id"]] | {fixture.spec["answers"]: output["answers"]}
        for output in expected
    ]
    owned = owners(fixture.baseline)
    assert owned[0]["totals"]["operation_count"] == 2 * fixture.spec["count"]
    assert owned[1]["totals"]["operation_count"] == (3 if fixture.label == "A" else 4)
    assert owned[2]["totals"]["operation_count"] == 0
    for owner in owned:
        logical = [request["logical_id"] for request in owner["requests"]]
        assert len(set(logical)) == len(logical)
        assert owner["totals"]["reserved_microusd"] == 0
    inputs, comparisons = {fixture.spec["generation_path"]: generations}, []
    for index, path in enumerate((fixture.spec["result_path"], fixture.spec["summary_path"])):
        oracle, files = direct(fixture, index, inputs, sha(raw_answers))
        native = {
            name: (attempts[index + 1] / "artifacts" / name).read_bytes()
            for name in report["stages"][index + 1]["artifacts"]
        }
        assert native == files
        assert Counter(frame["body_sha256"] for frame in oracle["captures"]) == Counter(
            sha(base64.b64decode(request["body_base64"], validate=True))
            for request in owned[index + 1]["requests"]
        )
        comparisons.append(
            {
                "direct": oracle,
                "artifacts": {name: sha(raw) for name, raw in files.items()},
                "literal_artifacts_equal": True,
                "request_body_multiset_equal": True,
            }
        )
        inputs = {path: files[path]}
    summary_raw = Path(report["summary"]["path"]).read_bytes()
    assert sha(summary_raw) == report["summary"]["sha256"]
    if fixture.label == "B":
        assert summary_raw.startswith(b"instrument,labels\n")
    return {
        "report": report,
        "owners": owned,
        "comparisons": comparisons,
        "outputs": expected,
        "native_answers_sha256": sha(generations),
        "native_summary_base64": base64.b64encode(summary_raw).decode(),
        "selection_sha256": {
            name: selected.fingerprint() for name, selected in fixture.selections.items()
        },
    }


def history_snapshot(owner):
    directory = Path(owner["directory"])
    before = {
        name: sha((directory / name).read_bytes())
        for name in ("manifest.json", "operations.sqlite3")
    }
    history = read_gateway_history(
        directory, manifest_sha256=owner["manifest_sha256"], ledger_sha256=owner["ledger_sha256"]
    )
    operations = [
        {
            "operation_id": item.operation_id,
            "request_sha256": item.request_sha256,
            "reserve_microusd": item.reserve_microusd,
            "status": item.status,
            "actual_microusd": item.actual_microusd,
            "provider_request_id": item.provider_request_id,
            "receipt": item.receipt,
            "checkpoint": item.checkpoint,
            "checkpoint_request_id": item.checkpoint_request_id,
        }
        for item in history.operations
    ]
    assert before == {name: sha((directory / name).read_bytes()) for name in before}
    return {
        "run_id": history.run_id,
        "manifest": history.manifest,
        "totals": history.totals(),
        "operations": operations,
        "literal_files": before,
    }


def assert_active():
    import importlib.util

    for name in FORBIDDEN:
        assert not (ACTIVE / "buddha" / (name + ".py")).exists()
        assert "buddha." + name not in sys.modules
        assert importlib.util.find_spec("buddha." + name) is None
    assert "openai" not in sys.modules and "anthropic" not in sys.modules
    assert importlib.util.find_spec("openai") is None
    assert importlib.util.find_spec("anthropic") is None
    assert "agents.frozen_seed" not in sys.modules and "_buddha_frozen_seed" not in sys.modules
    for name, module in list(sys.modules.items()):
        if name == "buddha" or name.startswith("buddha."):
            assert Path(module.__file__).resolve().is_relative_to(ACTIVE / "buddha")


def main():
    assert_active()
    frozen = inventory(ACTIVE)
    core = _core_sources()
    assert len(core) == 9 and not any(
        name in core for name in ("buddha.benchmark", "buddha.evaluation")
    )
    shared = shared_roots()
    authority = Authorization.create(
        FIXTURE / "authorization.sqlite3",
        authorization_id="upgrade-retire-proof",
        budget_microusd=50_000_000,
        max_calls=100,
        scope="offline compatibility proof; fake HTTPS only",
    )
    fixtures = {label: Compatible(label, shared, authority) for label in ("A", "B")}
    baseline = fixtures["B"]
    b_identity = baseline.selections["native"].fingerprint()
    nested_raw = baseline.nested.read_bytes()
    baseline.nested.write_bytes(nested_raw + b" ")
    try:
        verify_selection(
            baseline.selections["native"], baseline.roots["native"], expected_sha256=b_identity
        )
    except ReleaseError:
        pass
    else:
        raise AssertionError("selected nested dependency drift was accepted")
    finally:
        baseline.nested.write_bytes(nested_raw)
    guards = ["selected nested dependency rejected"]
    for kind in ("count", "path"):
        changed = baseline.release.to_record()
        if kind == "count":
            changed["task"]["count"] = 1001
        elif kind == "path":
            changed["artifacts"]["summary"] = "../escape"
        try:
            candidate = Release.from_record(changed)
            prepare_selection(
                candidate,
                baseline.roots["native"],
                capabilities={cap: "profiles.json" for cap in CAPS.values()},
            )
        except ReleaseError:
            guards.append("unsupported " + kind + " rejected")
        else:
            raise AssertionError("unsupported outer contract was accepted: " + kind)
    changed = baseline.release.to_record()
    changed["requires"] = ["unreviewed.image-api.v1"]
    candidate = Release.from_record(changed)
    opaque_selection = prepare_selection(
        candidate,
        baseline.roots["native"],
        capabilities={"unreviewed.image-api.v1": "profiles.json"},
    )
    prior_authority = authority.summary()
    rejected = FIXTURE / "rejected-unsupported-capability"
    with (
        patch.dict(
            os.environ,
            {
                name: value
                for name, value in os.environ.items()
                if name not in {"OPENAI_API_KEY", "ANTHROPIC_API_KEY"}
            },
            clear=True,
        ),
        patch(
            "http.client.HTTPSConnection",
            side_effect=AssertionError("unsupported capability sent HTTPS"),
        ),
    ):
        try:
            prepare_gateway(
                rejected,
                selection=opaque_selection,
                roots=baseline.roots["native"],
                authorization=authority,
                budget_microusd=5_000_000,
                max_calls=10,
                input_files=[Path(__file__).resolve()],
                review=review(),
            )
        except GatewayError:
            pass
        else:
            raise AssertionError("unsupported paid capability reached an active Gateway")
    assert not rejected.exists() and prior_authority == authority.summary()
    guards.append("opaque unsupported capability rejected by actual Gateway before binding")
    server, results = Server(), {}
    keys = {
        name: value
        for name, value in os.environ.items()
        if name not in {"OPENAI_API_KEY", "ANTHROPIC_API_KEY"}
    }
    keys.update(OPENAI_API_KEY=KEYS["openai"], ANTHROPIC_API_KEY=KEYS["anthropic"])
    initial_containers = containers()
    with (
        patch.dict(os.environ, keys, clear=True),
        patch(
            "http.client.HTTPSConnection",
            side_effect=lambda host, **options: Connection(server, host, **options),
        ),
        patch("socket.create_connection", side_effect=AssertionError("real network forbidden")),
    ):
        for label, fixture in fixtures.items():
            server.release = label
            report = run_baseline(
                fixture.baseline, transport=RawHTTPTransport(allow_paid=True, timeout_seconds=15)
            )
            results[label] = complete(fixture, report)
            print(json.dumps({"baseline": label, "status": report["status"]}), flush=True)
            assert frozen == inventory(ACTIVE) and core == _core_sources()
        assert len(server.sends) == 17
        before_reuse = authority.summary()
        with (
            patch.dict(
                os.environ,
                {
                    name: value
                    for name, value in os.environ.items()
                    if name not in {"OPENAI_API_KEY", "ANTHROPIC_API_KEY"}
                },
                clear=True,
            ),
            patch(
                "http.client.HTTPSConnection",
                side_effect=AssertionError("keyless reuse sent HTTPS"),
            ),
        ):
            assert (
                run_baseline(baseline.baseline, transport=RawHTTPTransport(allow_paid=False))[
                    "status"
                ]
                == "complete"
            )
        assert before_reuse == authority.summary() and len(server.sends) == 17
        old = fixtures["A"]
        unknown_dir = prepare_gateway(
            FIXTURE / "records/old-A-unknown",
            selection=old.selections["generation"],
            roots=old.roots["generation"],
            authorization=authority,
            budget_microusd=5_000_000,
            max_calls=5,
            input_files=[Path(__file__).resolve(), old.descriptor],
            review=review(),
        )
        gateway = Gateway(
            unknown_dir, transport=RawHTTPTransport(allow_paid=True, timeout_seconds=15)
        )
        server.release, server.unknown = "old-A-unknown", True
        try:
            gateway.execute(
                GatewayCall(
                    CAPS["openai"],
                    "seed",
                    sha(b"retained-old-A-unknown"),
                    0,
                    _json(
                        {
                            "model": "seed-fixture",
                            "messages": [{"role": "user", "content": "held old A"}],
                            "max_completion_tokens": 100,
                        }
                    ),
                )
            )
        except ProviderUncertain:
            pass
        else:
            raise AssertionError("missing usage did not retain unknown liability")
        server.unknown = False
        authority.deactivate(
            gateway.ledger.run_id, "retired A; unresolved provider liability retained"
        )
        unknown = {
            "directory": str(unknown_dir),
            "manifest_sha256": gateway.manifest_sha256,
            "ledger_sha256": sha(gateway.ledger.path.read_bytes()),
        }
        old_owners = results["A"]["owners"] + [unknown]
        old_history = [history_snapshot(owner) for owner in old_owners]
        assert old_history[-1]["totals"]["reserved_microusd"] > 0
        assert old_history[-1]["operations"][0]["status"] == "unknown"
        assert old_history[-1]["operations"][0]["checkpoint"] is not None
        archive = FIXTURE / "archive/A"
        archive.parent.mkdir()
        target, destination = old.active.resolve(), archive.resolve()
        assert target.is_relative_to(FIXTURE.resolve()) and destination.is_relative_to(
            FIXTURE.resolve()
        )
        assert target == (FIXTURE / "active/A").resolve() and not destination.exists()
        assert not baseline.active.resolve().is_relative_to(target)
        old_inventory = inventory(target)
        target.rename(destination)
        assert not target.exists() and inventory(destination) == old_inventory
        assert [history_snapshot(owner) for owner in old_owners] == old_history
        retired_creation = FIXTURE / "rejected-retired-A"
        authority_before_retired_creation = authority.summary()
        with (
            patch.dict(
                os.environ,
                {
                    name: value
                    for name, value in os.environ.items()
                    if name not in {"OPENAI_API_KEY", "ANTHROPIC_API_KEY"}
                },
                clear=True,
            ),
            patch(
                "http.client.HTTPSConnection", side_effect=AssertionError("retired A sent HTTPS")
            ),
        ):
            try:
                prepare_gateway(
                    retired_creation,
                    selection=old.selections["generation"],
                    roots=old.roots["generation"],
                    authorization=authority,
                    budget_microusd=5_000_000,
                    max_calls=10,
                    input_files=[Path(__file__).resolve()],
                    review=review(),
                )
            except ReleaseError:
                pass
            else:
                raise AssertionError("retired A roots still created a new paid owner")
        assert not retired_creation.exists()
        assert authority.summary() == authority_before_retired_creation
        guards.append("retired A original selection/roots rejected before new owner creation")
        verify_selection(
            baseline.selections["native"], baseline.roots["native"], expected_sha256=b_identity
        )
        assert baseline.selections["native"].fingerprint() == b_identity
        server.release = "B-next"
        next_baseline = prepare_baseline(
            FIXTURE / "records/B-next",
            descriptor=baseline.descriptor,
            authorization=authority,
            review=review(),
        )
        held_before = authority.summary()
        assert held_before["available_microusd"] > 5_000_000 and held_before["remaining_calls"] > 10
        with (
            patch.dict(
                os.environ,
                {
                    name: value
                    for name, value in os.environ.items()
                    if name not in {"OPENAI_API_KEY", "ANTHROPIC_API_KEY"}
                },
                clear=True,
            ),
            patch(
                "http.client.HTTPSConnection",
                side_effect=AssertionError("held A allowed a new B send"),
            ),
        ):
            blocked = run_baseline(
                next_baseline, transport=RawHTTPTransport(allow_paid=True, timeout_seconds=15)
            )
        assert blocked["status"] == "incomplete" and blocked["stopped_stage"] == 0
        assert len(server.sends) == 18
        assert authority.summary()["reserved_microusd"] == held_before["reserved_microusd"]
        assert authority.summary()["operation_count"] == held_before["operation_count"]
        assert [history_snapshot(owner) for owner in old_owners] == old_history
    final_containers = containers()
    assert not set(final_containers) - set(initial_containers)
    assert_active()
    assert frozen == inventory(ACTIVE) and core == _core_sources()
    evidence = {
        "format": "buddha.review.nb03c-compatible-releases.v1",
        "fixture_directory": str(FIXTURE),
        "actual_provider_calls": 0,
        "actual_keys_used": False,
        "host_agent_execution": False,
        "host_official_execution": False,
        "host_sdk_imports": False,
        "legacy_host_modules_absent": list(FORBIDDEN),
        "source_sha256": CONTEXT["source_sha256"],
        "active_copy_inventory": frozen,
        "core_sha256": core,
        "pre_spend_guards": guards,
        "baselines": results,
        "mocked_sends": server.sends,
        "sealed_old_history": old_history,
        "archived_A_inventory": old_inventory,
        "B_identity_unchanged": b_identity,
        "blocked_B": blocked,
        "authorization": authority.summary(),
        "owned_containers_before": initial_containers,
        "owned_containers_after": final_containers,
        "limits": [
            "two declared canned releases do not certify unknown future releases",
            "same already-reviewed SDK image, no new dependencies or provider capabilities",
            "native contents preserved without optimizer projection or improvement claim",
            "retirement archives only fixture-owned A active roots; financial evidence retained",
            "read-only history establishes sealed-byte consistency, not provider authenticity",
        ],
    }
    output = REPOSITORY / "runs/reviews/nb03c-compatible-releases-evidence.json"
    save(output, evidence)
    print(
        json.dumps(
            {"mocked_sends": len(server.sends), "actual_provider_calls": 0, "evidence": str(output)}
        ),
        flush=True,
    )


main()
