"""Two source programs, two development tasks and real confined official stages.

Use only after review, with a caller-pinned source map and NEW synthetic outputs.
All provider replies are engineering fixtures. No real grant or key is consumed.
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
PREVIOUS = ROOT / "docs/conformance/src02-candidate-native-probe.py"
PREVIOUS_SHA = "1e25ec9c889791140cc721238f72281921d0042077838bed54971878b04b0c08"


def require(condition, label):
    if not condition:
        raise RuntimeError(label)


def definitions(args):
    """Consume only pinned, reviewed engineering definitions; never their main."""
    require(PREVIOUS.is_file() and not PREVIOUS.is_symlink(), "reviewed helper is not regular")
    with PREVIOUS.open("rb") as stream:
        raw = stream.read(1024**2 + 1)
    require(len(raw) <= 1024**2, "reviewed engineering helper exceeds bound")
    require(hashlib.sha256(raw).hexdigest() == PREVIOUS_SHA, "reviewed probe changed")
    module = ModuleType("_src02_screen_reviewed_probe")
    module.__file__ = str(PREVIOUS)
    sys.modules[module.__name__] = module
    exec(compile(raw, str(PREVIOUS), "exec"), vars(module))  # nosec B102
    # The existing source check includes every current Python source/test/probe.
    # Its caller script approval must refer to this driver, not the older driver.
    module.SCRIPT = SCRIPT
    raw_map, pins = module.source_check(args)
    require(pins.get(str(PREVIOUS)) == PREVIOUS_SHA, "source map omits reviewed probe pin")
    return module, raw_map, pins


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
    require(not args.directory.exists() and not args.out.exists(), "outputs must be NEW")
    require(args.directory.parent.is_dir() and args.out.parent.is_dir(), "parents must exist")
    require(not args.out.is_relative_to(args.directory), "receipt must be outside fixture")
    previous, map_raw, pins = definitions(args)
    sha, read, save = previous.sha, previous.read, previous.save
    require(
        not any(Path(name).is_relative_to(args.directory) for name in pins),
        "fixture overlaps approved original inputs",
    )
    h = previous.helper(args)
    from buddha import candidate_run, executor, source_screen
    from buddha.gateway import _read_manifest
    from buddha.gateway_history import read_gateway_history
    from buddha.releases import _path, _root

    _root(args.directory.parent)
    _root(args.out.parent)
    _path(args.directory.name)
    _path(args.out.name)
    runtime = json.loads(read(previous.RUNTIME))
    env_a, env_b = json.loads(read(h.ENV_A)), json.loads(read(h.ENV_B))
    require(runtime["image_id"] == previous.SOURCE_IMAGE, "source runtime image changed")
    require(env_b["image"].split("@")[-1] == previous.NATIVE_IMAGE, "native image changed")
    inherited = args.inherited_directory / "parent-improvement-output"
    child_raw, lineage_raw = (
        read(inherited / "child/candidate.py"),
        read(inherited / "lineage.json"),
    )
    old, lineage = json.loads(read(args.inherited_evidence)), json.loads(lineage_raw)
    matching = [row for row in old["cases"] if row["label"] == "parent-improvement-output"]
    require(
        old["status"] == "pass"
        and len(matching) == 1
        and matching[0]["lineage"] == lineage
        and matching[0]["report"]["artifacts"]["child/candidate.py"] == sha(child_raw)
        and lineage["child"]["agent_sha256"] == previous.CHILD_AGENT,
        "saved source does not join its original proof and lineage",
    )
    ordinary = {name: os.environ[name] for name in previous.SAFE_OS if name in os.environ}
    fake_environment = ordinary | {
        name.upper() + "_API_KEY": value for name, value in h.KEYS.items()
    }
    args.directory.mkdir()
    evidence = {
        "format": "buddha.src02-source-screen-native-proof.v1",
        "status": "running",
        "fixture": str(args.directory),
        "script_sha256": args.script_sha256,
        "reviewed_probe_sha256": PREVIOUS_SHA,
        "source_map_path": str(args.sources),
        "source_map_sha256": sha(map_raw),
        "source_sha256": pins,
        "source_image": previous.SOURCE_IMAGE,
        "native_image": previous.NATIVE_IMAGE,
        "inherited_proof_sha256": previous.OLD_PROOF_SHA,
        "saved_child_source_sha256": sha(child_raw),
        "saved_lineage_sha256": sha(lineage_raw),
        "real_provider_calls": 0,
        "host_candidate_execution": False,
        "host_official_execution": False,
        "workers": [],
        "phases": [],
    }
    try:
        with (
            patch.dict(os.environ, fake_environment, clear=True),
            patch("socket.create_connection", side_effect=RuntimeError("real network forbidden")),
            patch("socket.socket", side_effect=RuntimeError("real socket forbidden")),
            patch("buddha.agent_run.AgentSession.run", side_effect=RuntimeError("seed forbidden")),
        ):
            f = h.Fixture(args.directory, env_a, env_b)

            def history(path):
                manifest = _read_manifest(path)
                return read_gateway_history(
                    path,
                    manifest_sha256=h.sha(h._json(manifest)),
                    ledger_sha256=sha(read(path / "operations.sqlite3")),
                )

            scaffold = history(f.baseline / "owners/0")
            require(not scaffold.operations, "unused scaffold unexpectedly dispatched")
            f.authority.deactivate(scaffold.run_id, "unused zero-call fixture scaffold; never run")
            evidence["unused_scaffold"] = {
                "owner": str(f.baseline / "owners/0"),
                "run_id": scaffold.run_id,
                "authority": f.authority.summary(),
                "separate_from_screen_authority": True,
                "generation_executed": False,
            }
            shared = f.roots["generation"] | {
                name: args.directory / ("source-" + name)
                for name in ("runner", "environment", "host")
            }
            for name in ("runner", "environment", "host"):
                shared[name].mkdir()
            h.runner_copy(shared["runner"], candidate_run.RUNNER_FILES)
            runtime_path = shared["environment"] / "runtime.json"
            runtime_path.write_bytes(read(previous.RUNTIME))
            profiles = json.loads(read(f.roots["generation"]["host"] / "profiles.json"))
            profiles["profiles"]["candidate"] = profiles["profiles"].pop("seed")
            profile = profiles["profiles"]["candidate"]
            profile["spec"].update(model=previous.MODEL, max_output_tokens=4096)
            profile["response_models"] = [previous.MODEL]
            (shared["host"] / "profiles.json").write_bytes(h._json(profiles))
            neutral = args.directory / "neutral-native-agent"
            neutral.mkdir()
            (neutral / "identity.txt").write_bytes(
                b"Native evaluation does not execute the producer.\n"
            )
            native_roots = f.roots["native"] | {"agent": neutral}
            native_selection = h.prepare_selection(
                f.release,
                native_roots,
                capabilities={cap: "profiles.json" for cap in h.CAPS.values()},
            )
            template = json.loads(read(f.descriptor))
            native = template["native"] | {
                "selection": native_selection.to_record(),
                "roots": {name: str(path) for name, path in native_roots.items()},
            }
            full = h.TaskSet.from_file(f.release, native_roots["official"] / "data/curated.jsonl")
            ids = [task.id for task in full.tasks]
            selected_ids = ["curated-9", "curated-0"]
            require(
                len(ids) == 100 and set(selected_ids) <= set(ids[:-2]), "wrong source population"
            )
            selected = full.select(selected_ids)
            split = {
                "release_sha256": full.release_sha256,
                "dataset_sha256": full.dataset_sha256,
                "partitions": {
                    "development": ids[:-2],
                    "validation": ids[-2:-1],
                    "final": ids[-1:],
                },
                "families": [
                    {"id": task.id, "family": "synthetic-custody-" + str(i)}
                    for i, task in enumerate(full.tasks)
                ],
            }
            config = {
                "provider": "openai",
                "model": previous.MODEL,
                "max_output_tokens": 4096,
                "instructions": "",
                "sampling": "regenerate",
            }
            literal = json.dumps(previous.WEAK, ensure_ascii=False)
            synthetic_raw = (
                "import json\ndef generate(task, config, complete):\n"
                "    # Controlled engineering source: zero model callbacks.\n"
                "    return json.loads(" + repr(literal) + ")\n"
            ).encode("utf-8")
            screens, source_roots = [], []
            for index, raw in enumerate((child_raw, synthetic_raw)):
                agent = args.directory / ("source-agent-" + str(index))
                agent.mkdir()
                (agent / "candidate.py").write_bytes(raw)
                roots = shared | {"agent": agent}
                selection = h.prepare_selection(
                    f.release, roots, capabilities={cap: "profiles.json" for cap in h.CAPS.values()}
                )
                record = {
                    "format": "buddha.source-screen.v1",
                    "source": full.to_record(),
                    "split": split,
                    "selected_ids": selected_ids,
                    "generation": {
                        "selection": selection.to_record(),
                        "roots": {name: str(path) for name, path in roots.items()},
                        "config": config,
                        "entrypoint": "candidate.py",
                        "max_callbacks": 1,
                        "executor": {
                            "image_id": previous.SOURCE_IMAGE,
                            "role": "agent",
                            "runner_entrypoint": "buddha/candidate_worker.py",
                            "image_environment": [
                                value.split("=", 1) for value in runtime["config"]["Env"]
                            ],
                            "limits": asdict(h.Limits(wall_seconds=180, memory_mib=2048)),
                            "docker_endpoint": f.endpoint,
                            "mounts": [["/agent", str(agent)], ["/runner", str(roots["runner"])]],
                        },
                        "profile": {"capability": h.CAPS["openai"], "profile_id": "candidate"},
                        "runtime": {"path": str(runtime_path), "sha256": previous.RUNTIME_SHA},
                        "budget_microusd": 5_000_000,
                        "max_calls": 30,
                    },
                    "native": native,
                    "stages": template["stages"],
                    "projection": "noveltybench-1.1",
                    "lineage": {
                        "path": str(inherited / "lineage.json"),
                        "sha256": previous.LINEAGE_SHA,
                    }
                    if index == 0
                    else None,
                }
                screen = source_screen.SourceScreen.from_bytes(h._json(record))
                require(
                    screen.candidate_id == selection.agent_sha256,
                    "selected source identity changed",
                )
                screens.append(screen)
                source_roots.append(roots)
            require(
                screens[0].candidate_id == previous.CHILD_AGENT, "saved child inventory changed"
            )
            require(
                screens[0].candidate_id != screens[1].candidate_id,
                "source programs are not distinct",
            )
            require(
                screens[0].comparison_key() == screens[1].comparison_key(),
                "screen artifacts are not compatible",
            )
            authority = h.Authorization.create(
                args.directory / "screen-authorization.sqlite3",
                authorization_id="synthetic-source-screen-proof",
                budget_microusd=100_000_000,
                max_calls=200,
                scope="source screen: " + screens[0].comparison_key(),
            )
            review = {
                "checked_on": datetime.now(UTC).date().isoformat(),
                "credential_sha256": {name: sha(value.encode()) for name, value in h.KEYS.items()},
                "account_scope": "offline synthetic replies only",
            }
            # The original caller-approved full map is itself an immutable invocation
            # input. Every mapped source/asset is rechecked before and after phases.
            controls = {
                args.sources: sha(map_raw),
                SCRIPT: args.script_sha256,
                PREVIOUS: PREVIOUS_SHA,
            }
            directories = [args.directory / ("screen-" + str(i)) for i in range(2)]
            for directory, screen in zip(directories, screens, strict=True):
                source_screen.prepare_source_screen(
                    directory,
                    screen=screen,
                    authorization=authority,
                    review=review,
                    expected_runtime_sha256=previous.RUNTIME_SHA,
                    input_bindings=controls,
                )
            real_execute, current = executor.run_container, {}

            def observed_execute(spec, **kwargs):
                require(
                    previous.source_check(args) == (map_raw, pins),
                    "approved source changed before worker",
                )
                owner = kwargs["handle"].__self__.gateway.directory
                matches = [
                    (i, owner.relative_to(path))
                    for i, path in enumerate(directories)
                    if owner.is_relative_to(path)
                ]
                require(len(matches) == 1, "worker owner is outside the planned screens")
                screen_index, relative = matches[0]
                parts = relative.parts
                require(
                    len(parts) == 5 and parts[0] == "tasks" and parts[3] == "owners",
                    "unplanned worker owner",
                )
                task_index, role, stage = int(parts[1]), parts[2], int(parts[4])
                current.update(screen=screen_index, task=task_index, role=role, stage=stage)
                initial = kwargs["initial"]
                require(
                    all(value.encode() not in h._json(initial) for value in h.KEYS.values()),
                    "key crossed worker channel",
                )
                if spec.role == "agent":
                    require(
                        spec.image_id == previous.SOURCE_IMAGE
                        and role == "generation"
                        and stage == 0,
                        "wrong source worker",
                    )
                    require(
                        set(dict(spec.mounts)) == {"/agent", "/runner"}, "source mounts expanded"
                    )
                    require(
                        initial["task"] == selected.tasks[task_index].to_record()
                        and initial["config"] == config,
                        "source task/config differs",
                    )
                    require(
                        set(initial["roots"]) == {"agent", "runner"}
                        and initial["max_callbacks"] == 1,
                        "source interface expanded",
                    )
                    require(
                        not (
                            {"source", "split", "release", "profiles", "authorization", "review"}
                            & initial.keys()
                        ),
                        "host controls crossed source configure",
                    )
                    for task in full.tasks:
                        if task.id not in selected_ids:
                            require(
                                task.prompt.encode() not in h._json(initial),
                                "unselected task text crossed source channel",
                            )
                else:
                    require(
                        spec.image_id == previous.NATIVE_IMAGE
                        and role == "evaluation"
                        and stage in {1, 2, 3},
                        "wrong native worker",
                    )
                    require(
                        set(dict(spec.mounts)) == {"/official", "/runner", "/inputs"},
                        "native mounts expanded",
                    )
                record = {
                    "screen": screen_index,
                    "task_index": task_index,
                    "stage": role,
                    "stage_index": stage,
                    "role": spec.role,
                    "image_id": spec.image_id,
                }
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
                            key: value
                            for key, value in asdict(result).items()
                            if key != "_configuration"
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
                        "owned worker cleanup not proven",
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
                        headers["Authorization"] == "Bearer " + h.KEYS["openai"],
                        "not the fixture key",
                    )
                    request = json.loads(body)
                    self.model = request["model"]
                    self.stage = (
                        "generation"
                        if self.model == previous.MODEL
                        else (
                            "partition"
                            if request["response_format"]["json_schema"]["name"] == "Partition"
                            else "score"
                        )
                    )
                    if self.stage == "generation":
                        require(
                            current["screen"] == 0 and current["role"] == "generation",
                            "zero-callback source dispatched",
                        )
                        require(
                            request["max_completion_tokens"] == 4096
                            and json.loads(request["messages"][0]["content"])
                            == {
                                "phase": "batch",
                                "prompt": selected.tasks[current["task"]].prompt,
                                "count": 10,
                            },
                            "saved child request changed",
                        )
                    else:
                        require(
                            self.model == "test-model" and current["role"] == "evaluation",
                            "native model mapping differs",
                        )
                    self.index = len(f.sends)
                    f.sends.append(
                        dict(current)
                        | {"stage": self.stage, "model": self.model, "body_sha256": sha(body)}
                    )
                    print(
                        json.dumps(
                            {
                                "mocked_reply": len(f.sends),
                                "stage": self.stage,
                                "screen": current["screen"],
                                "task_index": current["task"],
                            }
                        ),
                        flush=True,
                    )

                def read(self, maximum):
                    literal = (
                        json.dumps(previous.WEAK, ensure_ascii=False)
                        if self.stage == "generation"
                        else (
                            json.dumps({"groups": [[i] for i in range(10)]})
                            if self.stage == "partition"
                            else '{"score":7}'
                        )
                    )
                    raw = h._json(
                        {
                            "id": "cmpl-source-screen-fixture",
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
                    require(len(raw) < maximum, "fixture response exceeds read bound")
                    return raw

            def tree(path):
                return {
                    str(item.relative_to(path)): sha(read(item))
                    for item in path.rglob("*")
                    if item.is_file()
                }

            def phase(name, callback, *, keyless=False, passive=False):
                require(
                    previous.source_check(args) == (map_raw, pins),
                    "approved bytes changed before phase",
                )
                before = len(f.sends), len(evidence["workers"])
                if keyless or passive:
                    before_tree, before_authority = tree(args.directory), authority.summary()
                    with (
                        patch.dict(os.environ, ordinary, clear=True),
                        patch(
                            "http.client.HTTPSConnection",
                            side_effect=RuntimeError("read/replay HTTPS forbidden"),
                        ),
                        patch(
                            "buddha.executor.run_container",
                            side_effect=RuntimeError("read/replay worker forbidden"),
                        ),
                        patch(
                            "buddha.native_pipeline._write",
                            side_effect=RuntimeError("read/replay publication forbidden"),
                        ),
                    ):
                        if passive:
                            with (
                                patch(
                                    "buddha.gateway.Gateway.__init__",
                                    side_effect=RuntimeError("passive Gateway forbidden"),
                                ),
                                patch(
                                    "buddha.authorization.Authorization.__init__",
                                    side_effect=RuntimeError("passive authority forbidden"),
                                ),
                            ):
                                result = callback()
                        else:
                            result = callback()
                    require(
                        tree(args.directory) == before_tree
                        and authority.summary() == before_authority,
                        "passive/replay persistent state changed",
                    )
                else:
                    result = callback()
                evidence["phases"].append(
                    {
                        "name": name,
                        "new_sends": len(f.sends) - before[0],
                        "new_workers": len(evidence["workers"]) - before[1],
                        "result": result,
                    }
                )
                return result

            reports, references = [], []
            transport = h.RawHTTPTransport(allow_paid=True, timeout_seconds=15)
            with (
                patch(
                    "http.client.HTTPSConnection",
                    side_effect=lambda host, **options: Connection(f, host, **options),
                ),
                patch("buddha.executor.run_container", side_effect=observed_execute),
            ):
                for index, directory in enumerate(directories):
                    report = phase(
                        "source-screen-" + str(index),
                        lambda directory=directory: source_screen.run_source_screen(
                            directory, transport=transport
                        ),
                    )
                    require(
                        report["status"] == "complete" and report["admission"]["eligible"] is True,
                        "native screen did not finish with usable controls",
                    )
                    reports.append(report)
                    references.append(
                        {
                            "directory": str(directory),
                            "authorization": str(authority.path),
                            "report_sha256": sha(read(directory / "report.json")),
                        }
                    )
                require(
                    reports[0]["controls_sha256"] == reports[1]["controls_sha256"],
                    "original host/control compatibility differs",
                )
                for index, (directory, report, reference) in enumerate(
                    zip(directories, reports, references, strict=True)
                ):
                    for task_index, task in enumerate(selected.tasks):
                        generation = directory / "tasks" / str(task_index) / "generation"
                        seal = json.loads(read(generation / "completed/0.json"))
                        answers = h.Answers.from_bytes(
                            read(generation / seal["attempt"] / "answers.json")
                        )
                        native_rows = [
                            json.loads(line) for line in answers.native_bytes().splitlines()
                        ]
                        require(
                            len(native_rows) == 1
                            and native_rows[0]["id"] == task.id
                            and native_rows[0]["generations"] == previous.WEAK,
                            "literal answers or task ordering changed",
                        )
                        owner_history = history(generation / "owners/0")
                        require(
                            len(owner_history.operations) == (1 if index == 0 else 0),
                            "callbacks were confused with answer count",
                        )
                    replay = phase(
                        "keyless-screen-" + str(index),
                        lambda directory=directory: source_screen.run_source_screen(
                            directory, transport=h.RawHTTPTransport(allow_paid=False)
                        ),
                        keyless=True,
                    )
                    require(replay == report, "replay changed original completion snapshot")
                    observed = phase(
                        "passive-screen-" + str(index),
                        lambda reference=reference: source_screen.inspect_source_screen(
                            Path(reference["directory"]),
                            authorization=authority.path,
                            expected_report_sha256=reference["report_sha256"],
                        ),
                        passive=True,
                    )
                    require(observed == report, "passive publication differs")
                selections = {}
                for method in ("archive", "latest", "uninformed"):
                    result = phase(
                        "parent-" + method,
                        lambda method=method: source_screen.select_source_parent(
                            references, method=method, max_active=2, seed=7, iteration=0
                        ),
                        passive=True,
                    )
                    require(
                        result["selected_id"] in {screen.candidate_id for screen in screens},
                        "parent rule selected an unadmitted source",
                    )
                    selections[method] = result
                require(
                    selections["latest"]["selected_id"] == screens[1].candidate_id
                    and selections["uninformed"]["selected_id"] == screens[0].candidate_id,
                    "existing history rules changed",
                )
                retired, moved = args.directory / "retired-producer-programs", {}
                retired.mkdir()
                for name, original in (
                    ("agent-0", source_roots[0]["agent"]),
                    ("agent-1", source_roots[1]["agent"]),
                    ("runner", shared["runner"]),
                ):
                    original, fixture_root = (
                        original.resolve(strict=True),
                        args.directory.resolve(strict=True),
                    )
                    destination = retired / name
                    retired_root, target = (
                        retired.resolve(strict=True),
                        destination.resolve(strict=False),
                    )
                    require(
                        original.is_relative_to(fixture_root)
                        and original != fixture_root
                        and retired_root.is_relative_to(fixture_root)
                        and retired_root != fixture_root
                        and target.is_relative_to(retired_root)
                        and target != retired_root
                        and not destination.exists(),
                        "retirement source/destination escaped fixture",
                    )
                    before = tree(original)
                    shutil.move(str(original), str(destination))
                    require(
                        tree(destination) == before and not original.exists(),
                        "retired bytes changed",
                    )
                    moved[name] = {
                        "original": str(original),
                        "retained": str(destination),
                        "files": before,
                    }
                for index, (reference, report) in enumerate(zip(references, reports, strict=True)):
                    observed = phase(
                        "retired-passive-screen-" + str(index),
                        lambda reference=reference: source_screen.inspect_source_screen(
                            Path(reference["directory"]),
                            authorization=authority.path,
                            expected_report_sha256=reference["report_sha256"],
                        ),
                        passive=True,
                    )
                    require(observed == report, "retirement changed passive native evidence")
                owners = [
                    directory / "tasks" / str(task) / role / "owners" / str(stage)
                    for directory in directories
                    for task in range(2)
                    for role, stages in (("generation", (0,)), ("evaluation", (1, 2, 3)))
                    for stage in stages
                ]
                histories = [history(owner) for owner in owners]
                operations = [operation for item in histories for operation in item.operations]
                totals = authority.summary()
                require(
                    len(histories) == 16 and len({item.run_id for item in histories}) == 16,
                    "productive owner population differs",
                )
                require(
                    len(evidence["workers"]) == 16
                    and len({item["container_id"] for item in evidence["workers"]}) == 16,
                    "actual worker population differs",
                )
                require(
                    len(operations) == 46
                    and len({operation.operation_id for operation in operations}) == 46
                    and all(operation.status == "completed" for operation in operations),
                    "synthetic operation population differs",
                )
                require(
                    Counter(item["stage"] for item in f.sends)
                    == {"generation": 2, "partition": 4, "score": 40},
                    "mocked reply counts differ",
                )
                require(
                    totals["operation_count"] == 46
                    and totals["reserved_microusd"] == 0
                    and len(totals["runs"]) == 16
                    and all(not row["active"] for row in totals["runs"]),
                    "shared authority did not close every planned owner",
                )
                require(
                    sum(item.totals()["spent_microusd"] for item in histories)
                    == totals["spent_microusd"],
                    "owner/global charges differ",
                )
                for task in range(2):
                    requests = [
                        Counter(
                            (item["stage"], item["model"], item["body_sha256"])
                            for item in f.sends
                            if item["screen"] == screen
                            and item["task"] == task
                            and item["stage"] != "generation"
                        )
                        for screen in range(2)
                    ]
                    require(
                        requests[0] == requests[1],
                        "same literal answers reached different native bodies",
                    )
                require(
                    previous.source_check(args) == (map_raw, pins),
                    "original approved inputs changed",
                )
                evidence.update(
                    status="pass",
                    physical_mocked_replies=len(f.sends),
                    productive_owners=len(owners),
                    actual_workers=len(evidence["workers"]),
                    authority=totals,
                    comparison_key=screens[0].comparison_key(),
                    controls_sha256=reports[0]["controls_sha256"],
                    selected_ids=selected_ids,
                    full_tasks_sha256=full.fingerprint(),
                    selected_tasks_sha256=selected.fingerprint(),
                    source_programs=[
                        {
                            "candidate_id": screen.candidate_id,
                            "source_sha256": sha(raw),
                            "kind": "saved synthetic child"
                            if index == 0
                            else "controlled synthetic zero-callback program",
                        }
                        for index, (screen, raw) in enumerate(
                            zip(screens, (child_raw, synthetic_raw), strict=True)
                        )
                    ],
                    references=references,
                    parent_selections=selections,
                    sends=f.sends,
                    retired_producer_programs=moved,
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
                    keyless_replay_and_passive_persistent_bytes_unchanged=True,
                )
    except BaseException as error:
        evidence.update(status="failed", exception_type=type(error).__name__)
        raise
    finally:
        evidence["limits"] = [
            "Synthetic replies, usage and prices; no real providers, keys or funding allocation.",
            "Saved synthetic child and literal-answer control; no new authorship or science claim.",
            "Singleton groups and score-seven replies are controls, not semantic ratings.",
            "One native occasion per source/task; no judge-stability or unseen-task claim.",
            "Programs run in separate sealed containers; no independent metric oracle.",
            "Replay may create transient locks; persistent bytes and accounting stay checked.",
            "Cleanup queries only reported owned IDs; unrelated containers are not enumerated.",
            "Unused zero-call scaffold is retired under a separate synthetic authority.",
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
