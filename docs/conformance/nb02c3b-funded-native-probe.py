"""Offline full partition CLI conformance through the real funded boundary.

Requires the separately approved C3B immutable image and installed inventory.
All SDKs and unchanged upstream modules run in network-none containers. Host
HTTPS and credentials are synthetic; no actual provider request is permitted.
The earlier C3A helpers and evidence are imported read-only, never rewritten.
"""

import base64
import hashlib
import importlib.util
import json
import shutil
import sys
import tempfile
from collections import Counter
from dataclasses import asdict
from datetime import UTC, datetime
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
# shortcut: sealed C3A research utilities still require their old installed JSON.
# Keep that prerequisite for this proof; extract pure shared fixture utilities
# if more proof versions need reuse. Production never imports these helpers.
HELPER_A = ROOT / "docs/conformance/nb02c3-funded-native-probe.py"
loader = importlib.util.spec_from_file_location("_buddha_score_fixture", HELPER_A)
assert loader is not None and loader.loader is not None
score_fixture = importlib.util.module_from_spec(loader)
raw_helper = HELPER_A.read_bytes()
if hashlib.sha256(raw_helper).hexdigest() != (
    "d9ca38d078b44a2ca670c663118fe0a54e8dc1e30ee3d8b739b429a13c566993"
):
    raise ValueError("C3A funded engineering helper differs from its preserved source")
# Only our sealed engineering fixture executes on the host, never official code.
exec(compile(raw_helper, str(HELPER_A), "exec"), score_fixture.__dict__)  # nosec B102

from buddha.answers import Answers, TaskSet  # noqa: E402
from buddha.authorization import Authorization  # noqa: E402
from buddha.executor import ContainerSpec, Limits, _endpoint, run_container  # noqa: E402
from buddha.gateway import prepare_gateway  # noqa: E402
from buddha.provider import ModelSpec  # noqa: E402
from buddha.releases import Release, _json, inventory, prepare_selection  # noqa: E402

PINNED = score_fixture.PINNED | {
    "src/partition.py": "263970891ff3ee1cc8df369a33beefe5cb5de618b5dd146a5234536d97954aca"
}
MODULES = score_fixture.MODULES + ["src.partition"]
CAPS, KEYS, RUNNER = score_fixture.CAPS, score_fixture.KEYS, score_fixture.RUNNER
ENV = None
INSTALLED = None
SYNTHETIC = None


def sha(raw):
    return hashlib.sha256(raw).hexdigest()


def official_copy(target):
    for relative, expected in PINNED.items():
        raw = (score_fixture.SOURCE / relative).read_bytes()
        assert sha(raw) == expected, relative
        destination = target / relative
        destination.parent.mkdir(parents=True, exist_ok=True)
        destination.write_bytes(raw)


def selected_roots(directory, inputs, *, direct):
    roots = {name: directory / name for name in ("official", "runner", "inputs")}
    for path in roots.values():
        path.mkdir(parents=True)
    official_copy(roots["official"])
    for name in RUNNER:
        target = roots["runner"] / "buddha" / (name + ".py")
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes((ROOT / "buddha" / (name + ".py")).read_bytes())
    if direct:
        for source, target in (
            ("nb02c3-direct-worker.py", "direct_score.py"),
            ("nb02c3b-direct-worker.py", "direct.py"),
        ):
            shutil.copyfile(ROOT / "docs/conformance" / source, roots["runner"] / target)
    descriptions = []
    for index, (destination, raw) in enumerate(inputs.items()):
        name = str(index) + ".bin"
        (roots["inputs"] / name).write_bytes(raw)
        descriptions.append({"source": name, "destination": destination, "sha256": sha(raw)})
    return roots, descriptions


def arguments(model, seed):
    # These are the actual upstream CLI flags; partition has no fallback flag.
    result = [
        "--eval-dir",
        "/scratch/artifacts",
        "--version",
        "1.1",
        "--alg",
        "llm",
        "--judge-model",
        model,
        "--concurrency",
        "2",
    ]
    return result if seed is None else result + ["--seed", str(seed)]


def worker_config(roots, descriptions, model, seed, *, direct, mode):
    command = {"index": 0, "module": "src.partition", "argv": arguments(model, seed)}
    command["sha256"] = sha(_json(command))
    config = {
        "type": "configure",
        "format": "buddha.native-worker.v1",
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
                "synthetic_modules": SYNTHETIC,
                "derived_modules": ENV.get("derived_modules", {}),
            },
        },
        "inputs": descriptions,
        "hooks": {"modules": MODULES, "cache": None, "calls": [], "sdk": []},
    }
    if direct:
        config.update(
            format="buddha.direct-partition-worker.v1",
            fixture={"mode": mode, "primary_model": model},
        )
    else:
        config["hooks"].update(
            cache={
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
            calls=[
                {"target": "src.judge:judge_call", "label": "judge_call"},
                {"target": "src.judge:judge", "label": "judge"},
            ],
            sdk=[
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
        )
    return config


def direct(parent, label, mode, model, inputs, seed=7):
    roots, descriptions = selected_roots(parent / label, inputs, direct=True)
    config = worker_config(roots, descriptions, model, seed, direct=True, mode=mode)
    frames, files, finished = [], {}, set()

    def handle(frame):
        assert frame["type"] in {"ready", "capture", "file", "done"}
        frames.append(frame)
        if frame["type"] == "file":
            assert frame["path"] not in finished
            body = files.setdefault(frame["path"], bytearray())
            assert len(body) == frame["offset"]
            body.extend(base64.b64decode(frame["data_base64"], validate=True))
            if frame["eof"]:
                finished.add(frame["path"])

    result = run_container(
        ContainerSpec(
            ENV["image"].split("@")[-1],
            "evaluator",
            tuple(("/" + name, path) for name, path in roots.items()),
            runner_entrypoint="direct.py",
            image_environment=tuple(tuple(item.split("=", 1)) for item in ENV["config"]["Env"]),
        ),
        initial=config,
        handle=handle,
        limits=Limits(wall_seconds=180, memory_mib=2048),
    )
    assert result.exit_code == 0 and result.cleanup_status == "removed"
    assert frames[0]["type"] == "ready" and frames[-1]["type"] == "done"
    assert set(files) == finished
    bodies = {name: bytes(raw) for name, raw in files.items()}
    captures = [frame for frame in frames if frame["type"] == "capture"]
    evidence = {
        "label": label,
        "mode": mode,
        "primary": model,
        "seed": seed,
        "command": config["command"],
        "outcome": {
            "status": frames[-1]["status"],
            "reason": frames[-1]["reason"],
            "audit_sha256": sha(_json(frames[-1]["audit"])),
            "audit_module_count": len(frames[-1]["audit"]),
        },
        "captures": captures,
        "files": {name: {"sha256": sha(raw), "bytes": len(raw)} for name, raw in bodies.items()},
        "stderr_bytes": result.stderr_bytes,
        "stderr_sha256": result.stderr_sha256,
        "configuration": result.configuration,
        "cleanup_status": result.cleanup_status,
    }
    print(
        json.dumps({"label": label, "status": frames[-1]["status"], "captures": len(captures)}),
        flush=True,
    )
    return evidence, bodies


class PartitionConnection(score_fixture.Connection):
    def request(self, method, path, *, body, headers):
        super().request(method, path, body=body, headers=headers)
        self.body_key = sha(body)
        self.mixed_failure = b"task with text identifier" in body

    @property
    def status(self):
        return 503 if self.owner.mode == "status" else 200

    def read(self, limit):
        payload = score_fixture.payload(
            self.provider, self.model, self.owner.mode, self.owner.primary
        )
        count = self.owner.reply_counts[self.body_key] = (
            self.owner.reply_counts.get(self.body_key, 0) + 1
        )
        if self.owner.mode == "status":
            payload = {"error": {"type": "overloaded_error", "message": "fixture"}}
        elif self.owner.mode not in {"bad", "refusal", "length"}:
            invalid = self.owner.mode == "persistent" or self.owner.mode == "repair" and count == 1
            groups = [[0, 0], [1, 2]] if invalid else [[0, 2, 4, 6, 8], [1, 3, 5, 7, 9]]
            text = json.dumps({"groups": groups}, separators=(",", ":"))
            if self.owner.mode == "mixed" and self.mixed_failure:
                text = "{malformed judgment"
            if self.provider == "openai":
                payload["choices"][0]["message"]["content"] = text
            else:
                next(block for block in payload["content"] if block["type"] == "text")["text"] = (
                    text
                )
        if self.owner.mode == "unknown":
            payload.pop("usage")
        raw = _json(payload)
        assert len(raw) < limit
        return raw


class Funded(score_fixture.Funded):
    def __init__(self, parent, label, mode, model, inputs, observed_headers, dataset, seed=7):
        self.directory = directory = parent / label
        self.mode, self.primary, self.sends, self.reply_counts = mode, model, [], {}
        roots, descriptions = selected_roots(directory, inputs, direct=False)
        input_root = roots.pop("inputs")
        for role in ("agent", "environment", "host"):
            roots[role] = directory / role
            roots[role].mkdir()
        (roots["agent"] / "identity.txt").write_bytes(
            b"declared canned fixture; no agent execution\n"
        )
        (roots["environment"] / "environment.json").write_bytes(_json(ENV))
        (roots["official"] / "fixture-dataset.jsonl").write_bytes(dataset)
        profiles = {}
        for provider, models in {"openai": ["test-model"], "anthropic": ["claude-primary"]}.items():
            for model_name in models:
                profiles[model_name] = {
                    "spec": asdict(
                        ModelSpec(
                            provider,
                            model_name,
                            2_000_000,
                            128_000,
                            1_000_000,
                            2_000_000,
                            "https://example.org/offline-synthetic-only",
                        )
                    ),
                    "response_models": [model_name],
                    "request_tiers": ["auto", "default"],
                    "response_tiers": ["", "default"],
                    "allow_omitted_tier": True,
                    "headers": observed_headers[provider],
                    "account_headers": {},
                }
        (roots["host"] / "profiles.json").write_bytes(
            _json({"format": "buddha.gateway-profiles.v2", "profiles": profiles})
        )
        argv = [
            "{artifacts}" if item == "/scratch/artifacts" else item
            for item in arguments(model, seed)
        ]
        release = Release.from_record(
            {
                "format": "buddha.benchmark-release.v1",
                "benchmark": "noveltybench-native-fixture",
                "release": "1.1-pinned-partition-fixture",
                "upstream": {
                    "url": "https://github.com/novelty-bench/novelty-bench",
                    "revision": score_fixture.PIN,
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
                "commands": [{"module": "src.partition", "argv": argv}],
                "artifacts": {
                    "answers": "generations.jsonl",
                    "results": ["v1.1/partitions.jsonl"],
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
        assert inputs["generations.jsonl"] == answers.native_bytes()
        self.answers_path = directory / "answers.json"
        self.answers_path.write_bytes(answers.to_bytes())
        config = worker_config(roots, descriptions, model, seed, direct=False, mode=mode)
        config.update(release_sha256=release.fingerprint(), answers_sha256=answers.fingerprint())
        self.descriptor = directory / "native-command.json"
        docker = shutil.which("docker")
        assert docker
        self.descriptor.write_bytes(
            _json(
                {
                    "format": "buddha.native-command.v1",
                    "worker": config,
                    "executor": {
                        "image_id": ENV["image"].split("@")[-1],
                        "role": "evaluator",
                        "mounts": [
                            ["/official", str(roots["official"])],
                            ["/runner", str(roots["runner"])],
                            ["/inputs", str(input_root)],
                        ],
                        "runner_entrypoint": "buddha/native_worker.py",
                        "limits": asdict(Limits(wall_seconds=180, memory_mib=2048)),
                        "image_environment": [item.split("=", 1) for item in ENV["config"]["Env"]],
                        "docker_endpoint": _endpoint(docker),
                    },
                    "profiles": {
                        "openai": {"test-model": "test-model"},
                        "anthropic": {"claude-primary": "claude-primary"},
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
        self.run_dir = prepare_gateway(
            directory / "run",
            selection=selection,
            roots=roots,
            authorization=self.authority,
            budget_microusd=100_000_000,
            max_calls=40,
            input_files=[
                Path(__file__).resolve(),
                HELPER_A,
                self.descriptor,
                self.answers_path,
                *sorted(input_root.iterdir()),
                *host_sources,
            ],
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
        # This replaces only a synthetic host-server fixture, never production
        # transport code, SDK internals or an official scientific function.
        with patch.object(score_fixture, "Connection", PartitionConnection):
            return super().run(replay=replay)


def main():
    global ENV, INSTALLED, SYNTHETIC
    ENV = json.loads((ROOT / "docs/conformance/nb02c3b-runtime-environment.json").read_bytes())
    INSTALLED = json.loads((ROOT / "runs/reviews/nb02c3b-runtime-installed.json").read_bytes())
    SYNTHETIC = ENV["synthetic_modules"]
    sealed = [
        Path(__file__).resolve(),
        HELPER_A,
        ROOT / "docs/conformance/nb02c3-direct-worker.py",
        ROOT / "docs/conformance/nb02c3b-direct-worker.py",
        *[ROOT / "buddha" / (name + ".py") for name in (*RUNNER, "executor", "native_run")],
    ]
    before = {str(path.relative_to(ROOT)): sha(path.read_bytes()) for path in sealed}
    dataset = b"".join(
        _json({"id": identifier, "prompt": prompt}) + b"\n"
        for identifier, prompt in (
            (1, "same literal task with numeric identifier"),
            ("1", "same literal task with text identifier"),
        )
    )
    generations = b"".join(
        _json(
            json.loads(line)
            | {"generations": ["poor", "poor", "", "", "x", "x", "x", "x", "x", "x"]}
        )
        + b"\n"
        for line in dataset.splitlines()
    )
    evidence = {
        "format": "buddha.review.nb02c3b-funded-partition.v1",
        "image": ENV["image"],
        "source_revision": score_fixture.PIN,
        "selected_upstream_seals": PINNED,
        "actual_provider_calls": 0,
        "actual_keys_used": False,
        "direct_scientific_functions_wrapped": False,
        "funded_context_hooks": "configured generic wrappers invoke original native functions",
        "host_official_execution": False,
        "private_sdk_methods_patched": False,
        "scenarios": [],
        "checks": [],
    }
    with tempfile.TemporaryDirectory(dir=ROOT / "runs/reviews") as folder:
        parent = Path(folder)
        controls = {}
        observed_headers = {provider: {} for provider in CAPS}
        for label, model in (("valid-oai", "test-model"), ("valid-anthropic", "claude-primary")):
            controls[label] = direct(
                parent, "direct-" + label, "valid", model, {"generations.jsonl": generations}
            )
            for capture in controls[label][0]["captures"]:
                assert capture["sdk_max_retries"] == 8
                for name, value in capture["headers"]:
                    observed_headers[capture["provider"]].setdefault(name.lower(), set()).add(value)
        for headers in observed_headers.values():
            for name, values in headers.items():
                headers[name] = sorted(values)
            headers["x-stainless-retry-count"] = [str(index) for index in range(9)]
        evidence["observed_linux_sdk_headers"] = observed_headers
        partitions = mixed_partial = None
        for label, mode, model, seed in (
            ("valid-oai", "valid", "test-model", 7),
            ("mixed-oai", "mixed", "test-model", 7),
            ("resume-partial-after-failure", "valid", "test-model", 7),
            ("repair-oai", "repair", "test-model", 7),
            ("persistent-oai", "persistent", "test-model", 7),
            ("bad-oai", "bad", "test-model", 7),
            ("length-oai", "length", "test-model", 7),
            ("refusal-oai", "refusal", "test-model", 7),
            ("valid-anthropic", "valid", "claude-primary", 7),
            ("repair-anthropic", "repair", "claude-primary", 7),
            ("persistent-anthropic", "persistent", "claude-primary", 7),
            ("refusal-anthropic-no-fallback", "refusal", "claude-primary", 7),
            ("multiblock-anthropic", "multiblock", "claude-primary", 7),
            ("full-cache", "valid", "test-model", 7),
            ("partial-cache", "valid", "test-model", 7),
            ("changed-seed-cache", "valid", "test-model", 8),
            ("unshuffled", "valid", "test-model", None),
        ):
            inputs = {"generations.jsonl": generations}
            if label in {"full-cache", "changed-seed-cache"}:
                inputs["v1.1/partitions.jsonl"] = partitions
            elif label == "resume-partial-after-failure":
                inputs["v1.1/partitions.jsonl.partial"] = mixed_partial
            elif label == "partial-cache":
                inputs["v1.1/partitions.jsonl.partial"] = partitions.splitlines(keepends=True)[0]
            direct_result = controls.get(label) or direct(
                parent, "direct-" + label, mode, model, inputs, seed
            )
            funded = Funded(parent, label, mode, model, inputs, observed_headers, dataset, seed)
            funded_result = funded.run()
            expected_status = (
                "failed" if mode in {"mixed", "bad", "length", "refusal"} else "complete"
            )
            assert direct_result[0]["outcome"]["status"] == expected_status
            assert (
                direct_result[0]["outcome"]["reason"]
                == funded_result[0]["report"]["worker"]["reason"]
            )
            comparison = score_fixture.compare(direct_result, funded_result)
            evidence["scenarios"].append(
                {
                    "label": label,
                    "direct": direct_result[0],
                    "funded": funded_result[0],
                    "comparison": comparison,
                }
            )
            expected = (
                0
                if label == "full-cache"
                else 1
                if label in {"partial-cache", "resume-partial-after-failure"}
                else 4
                if mode == "repair"
                else 6
                if mode == "persistent"
                else 2
            )
            assert len(funded_result[0]["sends"]) == expected
            if label == "mixed-oai":
                mixed_partial = funded_result[1]["v1.1/partitions.jsonl.partial"]
                assert len(mixed_partial.splitlines()) == 1
            if label == "valid-oai":
                partitions = funded_result[1]["v1.1/partitions.jsonl"]
                replay = funded.run(replay=True)
                assert replay[0]["report"]["status"] == "complete" and replay[0]["sends"] == []
                assert replay[0]["ledger"] == funded_result[0]["ledger"]
                assert Counter(row["logical_id"] for row in replay[0]["requests"]) == Counter(
                    row["logical_id"] for row in funded_result[0]["requests"]
                )
                evidence["checks"].append({"label": "same-owner-keyless-replay", **replay[0]})
        for mode in ("unknown", "timeout", "status"):
            for model in ("test-model", "claude-primary"):
                label = mode + ("-oai" if model == "test-model" else "-anthropic")
                funded = Funded(
                    parent,
                    label,
                    mode,
                    model,
                    {"generations.jsonl": generations},
                    observed_headers,
                    dataset,
                )
                observed, _ = funded.run()
                assert observed["report"]["status"] == "stopped"
                assert observed["report"]["worker"]["reason"] == "unknown"
                assert len(observed["sends"]) == len(observed["requests"]) == 1
                assert observed["states"] == {"unknown": 1}
                assert (
                    observed["ledger"]["spent_microusd"]
                    == 0
                    < observed["ledger"]["reserved_microusd"]
                )
                if mode == "status":
                    native_retry = direct(
                        parent, "direct-" + label, mode, model, {"generations.jsonl": generations}
                    )
                    assert native_retry[0]["outcome"]["status"] == "failed"
                    assert len(native_retry[0]["captures"]) == 18
                    retries = Counter(
                        dict(frame["headers"])["x-stainless-retry-count"]
                        for frame in native_retry[0]["captures"]
                    )
                    assert retries == {str(index): 2 for index in range(9)}
                    observed["direct_unfunded_http_retry"] = native_retry[0]
                    observed["difference"] = (
                        "original SDK retries eight times after HTTP 503; funded route "
                        "stops on first unknown bill rather than permit unbounded liability"
                    )
                evidence["checks"].append(observed)
    evidence["source_sha256"] = {
        str(path.relative_to(ROOT)): sha(path.read_bytes()) for path in sealed
    }
    assert evidence["source_sha256"] == before, "source changed during proof"
    evidence["limits"] = [
        "official --alg llm full CLI only; classifier/NLI models are not downloaded or run",
        "partition CLI has no fallback option; refusal remains a native failure; "
        "no invented fallback",
        "native fold repair retries are funded; unknown HTTP liability stops SDK physical retries",
        "canned JSON judgments do not establish semantic equivalence accuracy "
        "or creative diversity",
        "changed cache inputs use new frozen owners; "
        "original-input raw replay keeps one immutable owner",
    ]
    output = ROOT / "runs/reviews/nb02c3b-funded-native-evidence.json"
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
