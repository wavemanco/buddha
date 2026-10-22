"""Review candidate: saved SRC child -> literal C1 -> two official native occasions.

Run only after source-map review, in a NEW explicitly synthetic directory. This
executes the saved candidate and official modules only inside the two previously
sealed images, with fake HTTPS responses. It grants no real spending authority.
"""

import argparse
import hashlib
import json
import os
import re
import shutil
import sys
from collections import Counter
from dataclasses import asdict
from datetime import UTC, datetime
from pathlib import Path
from types import ModuleType
from unittest.mock import patch

if not __debug__:
    raise RuntimeError("This proof requires ordinary Python with assertions enabled")

SCRIPT = Path(__file__).resolve()
ROOT = SCRIPT.parents[2]
HELPER = ROOT / "docs/conformance/nb02c3c3-baseline-probe.py"
HELPER_SHA = "d4eb66a332e6d54365cd30be0ea1189492e1742327dc828c5d60855b1fb4c1ea"
RUNTIME = ROOT / "docs/conformance/src01-runtime-environment.json"
RUNTIME_SHA = "a7311f68ab4deb2eed770d0454ddd2877250a86b8a72716abac45b4ff6d43951"
SOURCE_IMAGE = "sha256:757f5ffd3125ae10a83a7fb7eed05afe5e047442e4063d21bf995c03db1d0f04"
NATIVE_IMAGE = "sha256:969cbc318ec2d05502665b8ef2b4020307e4335b75e5d17584910aa51e31bf83"
OLD_PROOF_SHA = "1e9ae8cc163400a5c3f897f69aa0791d19aa7b8a6f7c169093dfdcade1ea9057"
CHILD_SHA = "3f28e7b45ae45a23f5c70989e2e89a79d6bab5d213f9e9d70f00a5213334022f"
LINEAGE_SHA = "067b5268ba324aaba49cf6f7db0391e45254129a7cf8bbac28c1b0f680ff427e"
CHILD_AGENT = "a6fb5cad443177608635f67523494bdcfca83034ba694d3efdb9e70be87a7d1c"
INSTALLED_SHA = "b6b8ab4d349926577905b95b0784c622d6e443f34ea2b73625e09e72b497cf4b"
SAFE_OS = (
    "PATH",
    "SYSTEMROOT",
    "WINDIR",
    "TEMP",
    "TMP",
    "COMSPEC",
    "PATHEXT",
    "PROGRAMFILES",
    "PROGRAMFILES(X86)",
    "PROGRAMW6432",
    "LOCALAPPDATA",
    "APPDATA",
    "USERPROFILE",
)
MODEL = "source-child-fixture"
WEAK = [
    "poor duplicate",
    "poor duplicate",
    "",
    " \n",
    "[refused]",
    "unfinished {",
    "literal \u00e9 and \u96ea",
    "not a story",
    "short",
    "  final unchanged  ",
]


def require(condition, label):
    if not condition:
        raise RuntimeError(label)


def sha(raw):
    return hashlib.sha256(raw).hexdigest()


def read(path, maximum=16 * 1024**2):
    require(path.is_file() and not path.is_symlink(), "proof input must be a regular file")
    with path.open("rb") as stream:
        raw = stream.read(maximum + 1)
    require(len(raw) <= maximum, "proof input exceeds bound")
    return raw


def encoded(value):
    return (
        json.dumps(value, ensure_ascii=False, sort_keys=True, indent=2, allow_nan=False) + "\n"
    ).encode()


def save(path, value):
    with path.open("xb") as stream:
        stream.write(encoded(value))
        stream.flush()
        os.fsync(stream.fileno())


def historical_paths(args):
    output = args.inherited_directory / "parent-improvement-output"
    return {
        args.inherited_evidence: OLD_PROOF_SHA,
        output / "child/candidate.py": CHILD_SHA,
        output / "lineage.json": LINEAGE_SHA,
    }


def source_check(args):
    require(sha(read(SCRIPT)) == args.script_sha256, "caller script approval differs")
    raw = read(args.sources, 1024**2)
    require(sha(raw) == args.sources_sha256, "caller source-map approval differs")
    pins = json.loads(raw)
    require(type(pins) is dict and 1 <= len(pins) <= 1024, "invalid source-map inventory")
    required = {SCRIPT, HELPER, RUNTIME, *historical_paths(args)}
    for prefix in ("buddha", "agents", "tests", "docs/conformance"):
        required.update(ROOT.joinpath(prefix).rglob("*.py"))
    required.update(
        ROOT / "docs/conformance" / name
        for name in (
            "nb02c3-runtime-environment.json",
            "nb02c3b-runtime-environment.json",
            "nb02c3b-funded-native-evidence.json",
        )
    )
    required.add(args.assets_root / "runs/reviews/nb02c3b-runtime-installed.json")
    official = (
        args.assets_root
        / "runs/references/noveltybench-conformance"
        / ("64a23be6b18ec1dacc298830aab276061b6e143c")
    )
    required.update(
        official / name
        for name in (
            "src/judge.py",
            "src/score.py",
            "src/common.py",
            "src/evaluation_io.py",
            "src/summarize.py",
            "src/partition.py",
            "LICENSE",
            "uv.lock",
            "data/curated.jsonl",
        )
    )
    require({str(path) for path in required} <= set(pins), "approval omits proof sources/assets")
    for name, expected in pins.items():
        path = Path(name)
        require(path.is_absolute() and ".." not in path.parts, "source pin is not absolute")
        require(type(expected) is str and re.fullmatch("[0-9a-f]{64}", expected), "invalid pin")
        require(sha(read(path)) == expected, "caller-approved bytes changed")
    fixed = {HELPER: HELPER_SHA, RUNTIME: RUNTIME_SHA} | historical_paths(args)
    for path, digest in fixed.items():
        require(sha(read(path)) == digest, "historical source/runtime seal differs")
    return raw, pins


def helper(args):
    sys.path.insert(0, str(ROOT))
    sys.dont_write_bytecode = True
    module = ModuleType("_src02_reviewed_native_helper")
    module.__file__ = str(HELPER)
    sys.modules[module.__name__] = module
    raw = read(HELPER)
    require(sha(raw) == HELPER_SHA, "consumed helper differs")
    # Trusted, reviewed engineering definitions only, never official/candidate code.
    exec(compile(raw, str(HELPER), "exec"), vars(module))  # nosec B102
    module.SOURCE = args.assets_root / "runs/references/noveltybench-conformance" / module.PIN
    for name, digest in module.UPSTREAM.items():
        require(sha(read(module.SOURCE / name)) == digest, "pinned official input differs")
    for path, digest in module.SEALED.items():
        require(sha(read(path)) == digest, "helper's sealed prerequisite differs")
    installed_path = args.assets_root / "runs/reviews/nb02c3b-runtime-installed.json"
    installed = read(installed_path)
    require(sha(installed) == INSTALLED_SHA, "installed B inventory differs")

    def installed_environment(environment):
        require(environment["installed_manifest"]["sha256"] == INSTALLED_SHA, "B pin differs")
        return {
            "helper_sha256": environment["audit_helper"]["sha256"],
            "manifest_sha256": INSTALLED_SHA,
            "inventory": json.loads(installed)["inventory"],
            "synthetic_modules": environment["synthetic_modules"],
            "derived_modules": environment["derived_modules"],
        }

    # Explicit asset-location adapter; current WT still supplies all executing code.
    module.installed_environment = installed_environment
    return module


def main(args):
    for path in (
        args.directory,
        args.out,
        args.sources,
        args.assets_root,
        args.inherited_directory,
        args.inherited_evidence,
    ):
        require(path.is_absolute() and ".." not in path.parts, "absolute proof paths required")
    require(not args.directory.exists() and not args.out.exists(), "proof outputs must be NEW")
    require(
        args.directory.parent.is_dir() and args.out.parent.is_dir(), "existing parents required"
    )
    require(not args.out.is_relative_to(args.directory), "receipt must be outside fixture")
    map_raw, pins = source_check(args)
    require(
        not any(Path(path).is_relative_to(args.directory) for path in pins),
        "fixture overlaps approved original inputs",
    )
    h = helper(args)
    from buddha import candidate_generation, candidate_run, executor, native_evaluation
    from buddha.gateway import _read_manifest
    from buddha.gateway_history import read_gateway_history
    from buddha.releases import _path, _root

    runtime = json.loads(read(RUNTIME))
    _root(args.directory.parent)
    _root(args.out.parent)
    _path(args.directory.name)
    _path(args.out.name)
    env_a, env_b = json.loads(read(h.ENV_A)), json.loads(read(h.ENV_B))
    require(runtime["image_id"] == SOURCE_IMAGE, "source image differs")
    require(env_b["image"].split("@")[-1] == NATIVE_IMAGE, "native image differs")
    old = json.loads(read(args.inherited_evidence))
    original_output = args.inherited_directory / "parent-improvement-output"
    child_raw = read(original_output / "child/candidate.py")
    lineage = json.loads(read(original_output / "lineage.json"))
    matching = [case for case in old["cases"] if case["label"] == "parent-improvement-output"]
    require(old["status"] == "pass" and len(matching) == 1, "original competence proof missing")
    require(matching[0]["lineage"] == lineage, "original child lineage differs")
    require(
        matching[0]["report"]["artifacts"]["child/candidate.py"] == CHILD_SHA
        and matching[0]["report"]["artifacts"]["lineage.json"] == LINEAGE_SHA
        and lineage["child"]["source_sha256"] == CHILD_SHA
        and lineage["child"]["agent_sha256"] == CHILD_AGENT,
        "child is not the original materialized descendant",
    )
    ordinary = {key: os.environ[key] for key in SAFE_OS if key in os.environ}
    fake_environment = ordinary | {
        name.upper() + "_API_KEY": value for name, value in h.KEYS.items()
    }
    args.directory.mkdir()
    evidence = {
        "format": "buddha.src02-candidate-native-competence.v1",
        "status": "running",
        "fixture": str(args.directory),
        "script_sha256": args.script_sha256,
        "source_map_path": str(args.sources),
        "source_map_sha256": sha(map_raw),
        "source_sha256": pins,
        "source_image": SOURCE_IMAGE,
        "native_image": NATIVE_IMAGE,
        "old_competence_sha256": OLD_PROOF_SHA,
        "child_source_sha256": CHILD_SHA,
        "child_agent_sha256": CHILD_AGENT,
        "lineage_sha256": LINEAGE_SHA,
        "real_provider_calls": 0,
        "host_official_execution": False,
        "host_candidate_execution": False,
        "workers": [],
        "phases": [],
    }
    try:
        with (
            patch.dict(os.environ, fake_environment, clear=True),
            patch("socket.create_connection", side_effect=RuntimeError("real network forbidden")),
            patch("socket.socket", side_effect=RuntimeError("real socket forbidden")),
            patch(
                "buddha.agent_run.AgentSession.run", side_effect=RuntimeError("seed run forbidden")
            ),
        ):
            f = h.Fixture(args.directory, env_a, env_b)
            review = {
                "checked_on": datetime.now(UTC).date().isoformat(),
                "credential_sha256": {name: sha(value.encode()) for name, value in h.KEYS.items()},
                "account_scope": "offline synthetic replies only",
            }

            def history(path):
                manifest = _read_manifest(path)
                return read_gateway_history(
                    path,
                    manifest_sha256=h.sha(h._json(manifest)),
                    ledger_sha256=sha(read(path / "operations.sqlite3")),
                )

            scaffold = history(f.baseline / "owners/0")
            require(not scaffold.operations, "scaffold unexpectedly dispatched")
            f.authority.deactivate(
                scaffold.run_id, "unused zero-call fixture scaffold; never executed"
            )
            evidence["unused_scaffold"] = {
                "owner": str(f.baseline / "owners/0"),
                "run_id": scaffold.run_id,
                "operation_count": 0,
                "completed_generation": False,
            }
            source_roots = f.roots["generation"] | {
                name: args.directory / ("source-" + name)
                for name in ("agent", "runner", "environment", "host")
            }
            for name in ("agent", "runner", "environment", "host"):
                source_roots[name].mkdir()
            (source_roots["agent"] / "candidate.py").write_bytes(child_raw)
            h.runner_copy(source_roots["runner"], candidate_run.RUNNER_FILES)
            runtime_path = source_roots["environment"] / "runtime.json"
            runtime_path.write_bytes(read(RUNTIME))
            profiles = json.loads(read(f.roots["generation"]["host"] / "profiles.json"))
            profiles["profiles"]["candidate"] = profiles["profiles"].pop("seed")
            profile = profiles["profiles"]["candidate"]
            profile["spec"].update(model=MODEL, max_output_tokens=4096)
            profile["response_models"] = [MODEL]
            (source_roots["host"] / "profiles.json").write_bytes(h._json(profiles))
            source_selection = h.prepare_selection(
                f.release,
                source_roots,
                capabilities={cap: "profiles.json" for cap in h.CAPS.values()},
            )
            require(source_selection.agent_sha256 == CHILD_AGENT, "copied child identity differs")
            selected = h.TaskSet.from_file(
                f.release, f.roots["native"]["official"] / "data/curated.jsonl"
            ).select(["curated-0"])
            task_path = args.directory / "source-tasks.json"
            task_path.write_bytes(selected.to_bytes())
            config = {
                "provider": "openai",
                "model": MODEL,
                "max_output_tokens": 4096,
                "instructions": "",
                "sampling": "regenerate",
            }
            descriptor = args.directory / "source-generation.json"
            descriptor.write_bytes(
                h._json(
                    {
                        "format": "buddha.candidate-generation.v1",
                        "tasks": str(task_path),
                        "config": config,
                        "entrypoint": "candidate.py",
                        "max_callbacks": 1,
                        "executor": {
                            "image_id": SOURCE_IMAGE,
                            "role": "agent",
                            "runner_entrypoint": "buddha/candidate_worker.py",
                            "image_environment": [
                                value.split("=", 1) for value in runtime["config"]["Env"]
                            ],
                            "limits": asdict(h.Limits(wall_seconds=180, memory_mib=2048)),
                            "docker_endpoint": f.endpoint,
                            "mounts": [
                                ["/agent", str(source_roots["agent"])],
                                ["/runner", str(source_roots["runner"])],
                            ],
                        },
                        "profile": {"capability": h.CAPS["openai"], "profile_id": "candidate"},
                        "runtime": {"path": str(runtime_path), "sha256": RUNTIME_SHA},
                    }
                )
            )
            controls = {Path(path): digest for path, digest in pins.items()}
            controls[args.sources] = sha(map_raw)
            producer = args.directory / "candidate-generation"
            candidate_generation.prepare_candidate_generation(
                producer,
                descriptor=descriptor,
                selection=source_selection,
                roots=source_roots,
                authorization=f.authority,
                review=review,
                budget_microusd=5_000_000,
                max_calls=30,
                expected_runtime_sha256=RUNTIME_SHA,
                input_files=list(controls),
                expected_input_hashes=controls,
            )
            real_execute = executor.run_container

            def observed_execute(spec, **kwargs):
                require(source_check(args) == (map_raw, pins), "source changed before execution")
                initial = kwargs["initial"]
                require(
                    all(key.encode() not in h._json(initial) for key in h.KEYS.values()),
                    "credential crossed worker configure",
                )
                if spec.role == "agent":
                    require(spec.image_id == SOURCE_IMAGE, "wrong candidate image")
                    require(
                        set(dict(spec.mounts)) == {"/agent", "/runner"}, "source mounts expanded"
                    )
                    require(initial["task"] == selected.tasks[0].to_record(), "wrong source task")
                    require(initial["config"] == config, "source config differs")
                    require(
                        set(initial["roots"]) == {"agent", "runner"}, "source input roots expanded"
                    )
                else:
                    require(spec.image_id == NATIVE_IMAGE, "wrong evaluator image")
                    require(
                        set(dict(spec.mounts)) == {"/official", "/runner", "/inputs"},
                        "native mounts expanded",
                    )
                record = {"role": spec.role, "image_id": spec.image_id}
                try:
                    result = real_execute(spec, **kwargs)
                except executor.ExecutorError as error:
                    record.update(
                        container_id=error.container_id,
                        cleanup_status=error.cleanup_status,
                        failure_reason=error.reason,
                    )
                    raise
                else:
                    record.update(
                        {
                            name: value
                            for name, value in asdict(result).items()
                            if name != "_configuration"
                        }
                    )
                    record["configuration"] = result.configuration
                    return result
                finally:
                    evidence["workers"].append(record)
                    identity = record.get("container_id")
                    require(
                        type(identity) is str
                        and re.fullmatch("[0-9a-f]{64}", identity)
                        and record.get("cleanup_status") == "removed",
                        "executor did not report owned removal",
                    )
                    require(
                        not h._control(
                            f.docker,
                            [
                                "--host",
                                f.endpoint,
                                "container",
                                "ls",
                                "-a",
                                "--no-trunc",
                                "--filter",
                                "id=" + identity,
                                "--format",
                                "{{.ID}}",
                            ],
                        ).strip(),
                        "reported owned worker remains",
                    )

            class Connection(h.Connection):
                def request(self, method, path, *, body, headers):
                    require(
                        self.provider == "openai"
                        and method == "POST"
                        and path == "/v1/chat/completions",
                        "unexpected synthetic route",
                    )
                    require(
                        headers["Authorization"] == "Bearer " + h.KEYS["openai"], "not fixture key"
                    )
                    record = json.loads(body)
                    self.model = record["model"]
                    self.stage = (
                        "generation"
                        if self.model == MODEL
                        else (
                            "partition"
                            if record["response_format"]["json_schema"]["name"] == "Partition"
                            else "score"
                        )
                    )
                    if self.stage == "generation":
                        require(record["max_completion_tokens"] == 4096, "wrong source cap")
                        require(
                            json.loads(record["messages"][0]["content"])
                            == {
                                "phase": "batch",
                                "prompt": selected.tasks[0].prompt,
                                "count": 10,
                            },
                            "child changed its literal batch request",
                        )
                    else:
                        require(self.model == "test-model", "unexpected native model")
                    self.index = sum(item["stage"] == self.stage for item in f.sends)
                    f.sends.append(
                        {"stage": self.stage, "model": self.model, "body_sha256": sha(body)}
                    )
                    print(
                        json.dumps({"mocked_reply": len(f.sends), "stage": self.stage}), flush=True
                    )

                def read(self, maximum):
                    literal = (
                        json.dumps(WEAK, ensure_ascii=False)
                        if self.stage == "generation"
                        else (
                            json.dumps({"groups": [[index] for index in range(10)]})
                            if self.stage == "partition"
                            else '{"score":7}'
                        )
                    )
                    raw = h._json(
                        {
                            "id": "cmpl-src02-synthetic",
                            "object": "chat.completion",
                            "created": 0,
                            "model": self.model,
                            "service_tier": "default",
                            "choices": [
                                {
                                    "index": 0,
                                    "message": {
                                        "role": "assistant",
                                        "content": literal,
                                        "refusal": None,
                                    },
                                    "finish_reason": "stop",
                                }
                            ],
                            "usage": {
                                "prompt_tokens": 1,
                                "completion_tokens": 2,
                                "total_tokens": 3,
                            },
                        }
                    )
                    require(len(raw) < maximum, "synthetic envelope exceeds requested bound")
                    return raw

            def tree(directory):
                return {
                    str(path.relative_to(directory)): sha(read(path))
                    for path in directory.rglob("*")
                    if path.is_file()
                }

            def phase(name, callback, *, keyless=False):
                require(
                    source_check(args) == (map_raw, pins), "approved source changed before phase"
                )
                before = (len(f.sends), len(evidence["workers"]))
                if keyless:
                    before_tree, before_auth = tree(args.directory), f.authority.summary()
                    with (
                        patch.dict(os.environ, ordinary, clear=True),
                        patch(
                            "http.client.HTTPSConnection",
                            side_effect=RuntimeError("keyless HTTPS forbidden"),
                        ),
                        patch(
                            "buddha.executor.run_container",
                            side_effect=RuntimeError("keyless worker forbidden"),
                        ),
                        patch(
                            "buddha.native_pipeline._write",
                            side_effect=RuntimeError("keyless publication forbidden"),
                        ),
                    ):
                        result = callback()
                    require(tree(args.directory) == before_tree, "keyless persistent bytes changed")
                    require(f.authority.summary() == before_auth, "keyless accounting changed")
                else:
                    result = callback()
                item = {
                    "name": name,
                    "new_sends": len(f.sends) - before[0],
                    "new_workers": len(evidence["workers"]) - before[1],
                    "report": result,
                }
                evidence["phases"].append(item)
                return result

            transport = h.RawHTTPTransport(allow_paid=True, timeout_seconds=15)
            with (
                patch(
                    "http.client.HTTPSConnection",
                    side_effect=lambda host, **options: Connection(f, host, **options),
                ),
                patch("buddha.executor.run_container", side_effect=observed_execute),
            ):
                generated = phase(
                    "source-generation",
                    lambda: candidate_generation.run_candidate_generation(
                        producer, transport=transport
                    ),
                )
                require(generated["status"] == "complete", "source generation incomplete")
                source_owner = history(producer / "owners/0")
                require(
                    len(source_owner.operations) == 1
                    and source_owner.operations[0].status == "completed",
                    "one batch callback did not complete",
                )
                source_seal = json.loads(read(producer / "completed/0.json"))
                answers_path = producer / source_seal["attempt"] / "answers.json"
                answers = h.Answers.from_bytes(read(answers_path))
                native_rows = [json.loads(line) for line in answers.native_bytes().splitlines()]
                require(
                    len(native_rows) == 1 and native_rows[0]["generations"] == WEAK,
                    "literal C1 answers/order changed",
                )
                require(native_rows[0]["id"] == "curated-0", "typed C1 ID changed")
                source_reference = {
                    "format": "buddha.candidate-generation-source.v1",
                    "generation_directory": str(producer),
                    "stage_seal_sha256": sha(read(producer / "completed/0.json")),
                    "owner_manifest_sha256": source_owner.manifest_sha256,
                    "owner_ledger_sha256": source_owner.ledger_sha256,
                }
                producer_before = tree(producer)
                neutral = args.directory / "neutral-native-agent"
                neutral.mkdir()
                (neutral / "identity.txt").write_bytes(
                    b"Native judging does not execute the source producer.\n"
                )
                native_roots = f.roots["native"] | {"agent": neutral}
                native_selection = h.prepare_selection(
                    f.release,
                    native_roots,
                    capabilities={cap: "profiles.json" for cap in h.CAPS.values()},
                )
                require(native_selection.agent_sha256 != CHILD_AGENT, "native agent is not neutral")
                template = json.loads(read(f.descriptor))
                native = template["native"] | {
                    "selection": native_selection.to_record(),
                    "roots": {key: str(value) for key, value in native_roots.items()},
                }
                occasions, reports = [], []

                def prepare(ordinal):
                    path = args.directory / ("native-occasion-" + str(ordinal))
                    recipe = args.directory / ("evaluation-" + str(ordinal) + ".json")
                    recipe.write_bytes(
                        h._json(
                            {
                                "format": "buddha.native-evaluation.v1",
                                "source_generation": source_reference,
                                "native": native,
                                "stages": template["stages"],
                            }
                        )
                    )
                    with (
                        patch(
                            "buddha.candidate_run.CandidateSession",
                            side_effect=RuntimeError("producer loading forbidden"),
                        ),
                        patch(
                            "buddha.executor.run_container",
                            side_effect=RuntimeError("prepare worker forbidden"),
                        ),
                    ):
                        native_evaluation.prepare_evaluation(
                            path,
                            descriptor=recipe,
                            authorization=f.authority,
                            review=review,
                            input_files=list(controls),
                            expected_input_hashes=controls,
                        )
                    require(
                        read(path / "native-answers.jsonl") == answers.native_bytes(),
                        "native C1 bytes differ",
                    )
                    occasions.append(path)
                    return path

                first = prepare(1)
                real_call, fired = h.Gateway.execute, False

                def interrupt_after_reply(gateway, call):
                    nonlocal fired
                    reply = real_call(gateway, call)
                    if f.sends[-1]["stage"] == "score" and not fired:
                        fired = True
                        # The original Gateway has already durably completed this
                        # receipt; interrupt only before delivery to the native worker.
                        raise RuntimeError("synthetic completed-reply host interruption")
                    return reply

                with patch.object(h.Gateway, "execute", interrupt_after_reply):
                    stopped = phase(
                        "first-native-known-reply-stop",
                        lambda: native_evaluation.run_evaluation(first, transport=transport),
                    )
                require(
                    fired and stopped["status"] == "incomplete" and stopped["stopped_stage"] == 2,
                    "known-reply interruption did not retain its native stage",
                )
                interrupted_history = history(first / "owners/2")
                require(
                    len(interrupted_history.operations) == 1
                    and interrupted_history.operations[0].status == "completed",
                    "received reply not completed",
                )
                retained = interrupted_history.operations[0]
                stopped_raw = read(first / stopped["observation"])
                reports.append(
                    phase(
                        "first-native-same-owner-resume",
                        lambda: native_evaluation.run_evaluation(first, transport=transport),
                    )
                )
                resumed = history(first / "owners/2")
                require(
                    resumed.run_id == interrupted_history.run_id and retained in resumed.operations,
                    "native recovery replaced owner/receipt",
                )
                require(
                    read(first / stopped["observation"]) == stopped_raw,
                    "old stop observation changed",
                )
                require(reports[0]["status"] == "complete", "first native occasion incomplete")
                replayed = phase(
                    "source-keyless-after-shared-growth",
                    lambda: candidate_generation.run_candidate_generation(
                        producer, transport=h.RawHTTPTransport(allow_paid=False)
                    ),
                    keyless=True,
                )
                require(
                    replayed == generated and tree(producer) == producer_before,
                    "source replay changed original snapshot",
                )
                retired = args.directory / "retired-producer-programs"
                retired.mkdir()
                retired_sources = {}
                for role in ("agent", "runner"):
                    original = source_roots[role].resolve(strict=True)
                    require(
                        original.is_relative_to(args.directory.resolve(strict=True))
                        and original != args.directory.resolve(strict=True),
                        "retirement target escaped fixture",
                    )
                    before = tree(original)
                    destination = retired / role
                    retired_root = retired.resolve(strict=True)
                    resolved_destination = destination.resolve(strict=False)
                    require(
                        retired_root.is_relative_to(args.directory.resolve(strict=True))
                        and retired_root != args.directory.resolve(strict=True)
                        and resolved_destination.is_relative_to(retired_root)
                        and resolved_destination != retired_root
                        and not destination.exists(),
                        "retirement destination escaped its owned fixture subtree",
                    )
                    shutil.move(str(original), str(destination))
                    require(
                        tree(destination) == before and not original.exists(),
                        "retired bytes changed",
                    )
                    retired_sources[role] = {
                        "original": str(original),
                        "retained": str(destination),
                        "files": before,
                    }
                second = prepare(2)
                reports.append(
                    phase(
                        "second-fresh-native-after-producer-retirement",
                        lambda: native_evaluation.run_evaluation(second, transport=transport),
                    )
                )
                require(reports[1]["status"] == "complete", "second native occasion incomplete")
                require(
                    tree(producer) == producer_before,
                    "native assessment changed original producer evidence",
                )
                for index, (path, report) in enumerate(zip(occasions, reports, strict=True)):
                    replay = phase(
                        "native-keyless-" + str(index + 1),
                        lambda path=path: native_evaluation.run_evaluation(
                            path, transport=h.RawHTTPTransport(allow_paid=False)
                        ),
                        keyless=True,
                    )
                    require(
                        replay == report,
                        "native replay rewrote historical authorization observation",
                    )
                # Resolve output files from original seals, never guessed latest attempts.
                normalized = []
                for path in occasions:
                    current = {}
                    for index in range(1, 4):
                        seal = json.loads(read(path / "completed" / (str(index) + ".json")))
                        attempt = path / seal["attempt"]
                        for output in template["stages"][index - 1]["outputs"]:
                            output_name = output["path"]
                            relative = "artifacts/" + output_name
                            require(relative in seal["files"], "declared output is not sealed")
                            raw = read(attempt / relative)
                            require(
                                sha(raw) == seal["files"][relative], "native sealed output changed"
                            )
                            current[output_name] = sha(h.normalize(raw, output_name))
                    normalized.append(current)
                    require(
                        json.loads(read(path / "command-3.json"))["profiles"] == {},
                        "summary can dispatch",
                    )
                require(
                    normalized[0] and normalized[0] == normalized[1],
                    "same native recipe artifacts differ",
                )
                owners = [producer / "owners/0"] + [
                    path / "owners" / str(index) for path in occasions for index in range(1, 4)
                ]
                histories = [history(owner) for owner in owners]
                operations = [operation for item in histories for operation in item.operations]
                totals = f.authority.summary()
                require(
                    len({item.run_id for item in histories}) == 7,
                    "fresh occasions reused a productive owner",
                )
                require(
                    Counter(
                        (item["stage"], item["model"], item["body_sha256"])
                        for item in f.sends[1:12]
                    )
                    == Counter(
                        (item["stage"], item["model"], item["body_sha256"])
                        for item in f.sends[12:23]
                    ),
                    "fresh native occasions changed scientific request bodies",
                )
                require(
                    len(operations) == 23 and len({op.operation_id for op in operations}) == 23,
                    "unexpected or repeated physical operations",
                )
                require(
                    all(op.status == "completed" for op in operations),
                    "unfinished synthetic operations",
                )
                require(
                    totals["operation_count"] == 23 and totals["reserved_microusd"] == 0,
                    "global accounting/hold mismatch",
                )
                require(
                    len(totals["runs"]) == 8 and all(not row["active"] for row in totals["runs"]),
                    "productive or scaffold owner still active",
                )
                require(
                    sum(item.totals()["spent_microusd"] for item in histories)
                    == totals["spent_microusd"],
                    "owner/global charges do not reconcile",
                )
                require(
                    Counter(item["stage"] for item in f.sends)
                    == {"generation": 1, "partition": 2, "score": 20},
                    "physical reply population differs",
                )
                require(
                    [item["new_sends"] for item in evidence["phases"]] == [1, 2, 9, 0, 11, 0, 0],
                    "physical recovery/replay counts differ",
                )
                require(
                    [item["new_workers"] for item in evidence["phases"]] == [1, 2, 2, 0, 3, 0, 0],
                    "actual recovery/replay worker counts differ",
                )
                require(
                    len(evidence["workers"]) == 8
                    and len({item["container_id"] for item in evidence["workers"]}) == 8,
                    "worker identity population differs",
                )
                require(source_check(args) == (map_raw, pins), "original approved inputs changed")
                evidence.update(
                    status="pass",
                    physical_mocked_replies=len(f.sends),
                    actual_workers=8,
                    productive_owners=7,
                    total_owners=8,
                    authority=totals,
                    source_generation=source_reference,
                    tasks_sha256=selected.fingerprint(),
                    answers_sha256=answers.fingerprint(),
                    native_answers_sha256=sha(answers.native_bytes()),
                    retired_source_components=retired_sources,
                    normalized_native_artifacts=normalized,
                    sends=f.sends,
                    owners=[
                        {
                            "directory": str(path),
                            "run_id": item.run_id,
                            "manifest_sha256": item.manifest_sha256,
                            "ledger_sha256": item.ledger_sha256,
                            "totals": item.totals(),
                        }
                        for path, item in zip(owners, histories, strict=True)
                    ],
                    retained_known_reply={
                        "operation_id": retained.operation_id,
                        "receipt_sha256": sha(h._json(retained.receipt)),
                        "original_observation": stopped["observation"],
                    },
                    keyless_replay_persistent_bytes_unchanged=True,
                )
    except BaseException as error:
        evidence.update(status="failed", exception_type=type(error).__name__)
        raise
    finally:
        evidence["limits"] = [
            "Synthetic replies, prices and usage only; zero real providers or funding allocation.",
            "One saved synthetic child; no new model-authored source, improvement or search claim.",
            "Completed-reply host interruption is RuntimeError/ExecutorError, not Ctrl+C evidence.",
            "Singleton partitions/score-seven replies are controls, not semantic judgments.",
            "Full official entrypoints run only in B; no independent numerical oracle.",
            "Opaque summaries are preserved; no host metrics or scientific ranking.",
            "Keyless replay can create transient locks; no persistent byte/accounting changes.",
            "Cleanup checks only reported owned IDs; unrelated containers are not enumerated.",
        ]
        save(args.out, evidence)
        print(
            json.dumps(
                {
                    "status": evidence["status"],
                    "proof": str(args.out),
                    "sha256": sha(read(args.out)),
                }
            ),
            flush=True,
        )


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    for name in (
        "directory",
        "out",
        "sources",
        "assets-root",
        "inherited-directory",
        "inherited-evidence",
    ):
        parser.add_argument("--" + name, type=Path, required=True)
    parser.add_argument("--sources-sha256", required=True)
    parser.add_argument("--script-sha256", required=True)
    main(parser.parse_args())
