"""One actual three-iteration inherited loop with canned HTTPS measurements.

Review and pin all inputs before running in a NEW synthetic directory. This
executes candidate and official Python only in their existing sealed images.
No real funding, provider key, model or improvement claim is involved.
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
from types import ModuleType, SimpleNamespace
from unittest.mock import patch

if not __debug__:
    raise RuntimeError("This proof requires ordinary Python with assertions enabled")

SCRIPT = Path(__file__).resolve()
ROOT = SCRIPT.parents[2]
PREVIOUS = ROOT / "docs/conformance/src02-source-proposal-stage-probe.py"
PREVIOUS_SHA = "d592d9ba0fbd3bd86712f8545a7590096cd2f9ceaf05ee182aa1146f64659635"
SCREEN_SHA = "1e4b2d2aa89717a8600f5ad7b2e4b3ff1bf9e1513d9623e69f9762f2ea5d0943"
MODEL = "source-child-fixture"


def planned_owners(directory):
    search = directory / "search"
    owners = []
    for screen in (search / "seed", search / "iterations/1/screen", search / "iterations/2/screen"):
        for task in range(2):
            owners.append(screen / "tasks" / str(task) / "generation/owners/0")
            owners.extend(
                screen / "tasks" / str(task) / "evaluation/owners" / str(stage)
                for stage in range(1, 4)
            )
    owners.append(search / "iterations/0/screen/tasks/0/generation/owners/0")
    owners.extend(search / "iterations" / str(index) / "proposal/owners/0" for index in range(3))
    return owners


def database_whitelist(directory):
    authority = directory / "synthetic-authorization.sqlite3"
    paths = [authority, *(owner / "operations.sqlite3" for owner in planned_owners(directory))]
    return frozenset(
        {":memory:", authority.as_uri() + "?mode=ro"}
        | {value for path in paths for value in (str(path), path.as_uri() + "?mode=rw")}
    )


def synthetic_database(value, allowed):
    if type(value) is type(Path()):
        value = str(value)
    return type(value) is str and value in allowed


def definitions(args):
    with PREVIOUS.open("rb") as stream:
        raw = stream.read(1024**2 + 1)
    if len(raw) > 1024**2 or hashlib.sha256(raw).hexdigest() != PREVIOUS_SHA:
        raise RuntimeError("reviewed proposal probe differs")
    module = ModuleType("_source_loop_reviewed_proposal_probe")
    module.__file__ = str(PREVIOUS)
    sys.modules[module.__name__] = module
    exec(compile(raw, str(PREVIOUS), "exec"), vars(module))  # nosec B102
    module.SCRIPT = SCRIPT
    map_raw, pins = module.source_check(args)
    module.require(pins.get(str(PREVIOUS)) == PREVIOUS_SHA, "source map omits reviewed helper")
    return module, map_raw, pins


def programs():
    common = """import json
def request(config, complete, payload):
    body = {"model": config["model"], "max_completion_tokens": config["max_output_tokens"],
            "messages": [{"role": "user", "content": json.dumps(payload)}]}
    reply = complete(config["provider"], json.dumps(body).encode("utf-8"))
    return json.loads(reply["choices"][0]["message"]["content"])
"""
    seed = (
        common
        + """def generate(task, config, complete):
    return request(config, complete, {"phase": "generate", "version": "seed", "task": task})
def propose_improvement(parent, feedback, config, complete):
    return request(config, complete, {"phase": "propose", "parent": parent, "feedback": feedback})
"""
    )
    improved = """def propose_improvement(parent, feedback, config, complete):
    notes = [json.loads(row["note"]) for row in feedback]
    measured = [note.get("measurements", note) for note in notes]
    utilities = [row["utility"] for row in measured]
    target_index = min(range(len(feedback)), key=lambda i: (utilities[i], i))
    failures = notes[0]["failures"]
    if not failures or any(note["failures"] != failures for note in notes):
        raise ValueError("verified common failure history required")
    return request(config, complete, {"phase": "propose", "parent": parent, "feedback": feedback,
        "target_task_id": feedback[target_index]["task"]["id"],
        "measured_utilities": utilities, "failed_child_ids": [row["child_id"] for row in failures]})
"""
    repaired = (
        common
        + """def generate(task, config, complete):
    answers = request(config, complete, {"phase": "generate", "version": "repaired", "task": task})
    return answers[1:] + answers[:1]
"""
        + improved
    )
    grandchild = (
        common
        + """def generate(task, config, complete):
    payload = {"phase": "generate", "version": "grandchild", "task": task}
    answers = request(config, complete, payload)
    return answers[::2] + answers[1::2]
"""
        + improved
    )
    broken = "def generate(task, config, complete):\n    return [\n"
    return seed, broken, repaired, grandchild


def main(args):
    previous, map_raw, pins = definitions(args)
    require, sha, read, decode = previous.require, previous.sha, previous.read, previous.decode
    for path in (args.directory, args.out, args.sources, args.screen_proof, args.screen_exit):
        require(path.is_absolute() and ".." not in path.parts, "absolute proof paths required")
    require(not args.directory.exists() and not args.directory.is_symlink(), "fixture must be NEW")
    require(not args.out.exists() and not args.out.is_symlink(), "receipt must be NEW")
    require(args.directory.parent.is_dir() and args.out.parent.is_dir(), "parents must exist")
    require(not args.out.is_relative_to(args.directory), "receipt must be outside fixture")
    require(
        not any(Path(path).is_relative_to(args.directory) for path in pins),
        "fixture overlaps inputs",
    )
    # Derive every allowed SQL path before mkdir, owner preparation or app import.
    owner_paths = planned_owners(args.directory)
    allowed_databases = database_whitelist(args.directory)
    require(len(owner_paths) == len(set(owner_paths)) == 28, "owner plan differs")
    require(len(allowed_databases) == 60, "SQL path plan differs")
    old = decode(read(args.screen_proof))
    require(
        old["status"] == "pass" and old["selected_ids"] == ["curated-9", "curated-0"],
        "saved source proof differs",
    )
    original = Path(old["fixture"])
    screen_path = Path(old["references"][0]["directory"]) / "screen.json"
    require(
        pins.get(str(screen_path)) == SCREEN_SHA and sha(read(screen_path)) == SCREEN_SHA,
        "saved screen is not externally pinned",
    )
    require(
        not args.directory.is_relative_to(original) and not args.out.is_relative_to(original),
        "outputs overlap original evidence",
    )
    old_pins = old["source_sha256"]
    require(
        len(old_pins) == 208
        and all(sha(read(Path(path))) == digest for path, digest in old_pins.items()),
        "historical source changed",
    )
    sys.path.insert(0, str(ROOT))
    sys.dont_write_bytecode = True
    h = previous.module(previous.HELPER, previous.HELPER_SHA, "_source_loop_src01_helper")
    from buddha import candidate_run, executor, native_pipeline, source_screen, source_search
    from buddha.answers import Answers, TaskSet
    from buddha.authorization import Authorization
    from buddha.doctor import _Capture
    from buddha.gateway import RawHTTPTransport, _read_manifest
    from buddha.gateway_history import read_gateway_history
    from buddha.provider import ModelSpec
    from buddha.releases import Release, _json, prepare_selection

    for path in (args.directory.parent, args.out.parent):
        require(h._root(path) == path, "output parent must be plain and canonical")
    original_tree = previous.tree(original, _Capture)
    old_screen = source_screen.SourceScreen.from_bytes(read(screen_path)).to_record()
    selected = TaskSet.from_bytes(_json(old_screen["source"])).select(old_screen["selected_ids"])
    require(
        len(selected.tasks) == 2 and all(task.count == 10 for task in selected.tasks),
        "wrong source population",
    )
    seed, broken, repaired, grandchild = programs()
    sources = [seed, broken, repaired, grandchild]
    source_hashes = [sha(value.encode()) for value in sources]
    agent_ids = [sha(_json({"candidate.py": digest})) for digest in source_hashes]
    require(len(set(agent_ids)) == 4, "source controls are not distinct")
    protected_source = set(source_hashes)

    def audit(event, arguments):
        if event == "compile" and isinstance(arguments[0], (str, bytes)):
            raw = arguments[0].encode() if isinstance(arguments[0], str) else arguments[0]
            require(sha(raw) not in protected_source, "candidate compiled on host")
        if event == "exec":
            name = arguments[0].co_filename
            if name and not name.startswith("<"):
                path = Path(name).absolute()
                require(
                    not path.is_relative_to(original) and not path.is_relative_to(args.directory),
                    "candidate or official code executed on host",
                )
        if event == "open" and isinstance(arguments[0], (str, bytes, os.PathLike)):
            path = Path(os.fsdecode(arguments[0])).absolute()
            mode, flags = arguments[1], arguments[2]
            writing = (
                isinstance(mode, str) and any(value in mode for value in "wax+")
            ) or flags & (os.O_WRONLY | os.O_RDWR | os.O_CREAT | os.O_TRUNC | os.O_APPEND)
            require(not (writing and path.is_relative_to(original)), "original fixture write")
        if event == "sqlite3.connect":
            require(
                synthetic_database(arguments[0], allowed_databases),
                "SQL outside exact synthetic plan",
            )

    sys.addaudithook(audit)
    ordinary = {name: os.environ[name] for name in previous.SAFE_OS if name in os.environ}
    synthetic_environment = ordinary | {
        name.upper() + "_API_KEY": value for name, value in h.KEYS.items()
    }
    evidence = {
        "format": "buddha.src02-source-loop-native-proof.v1",
        "status": "running",
        "fixture": str(args.directory),
        "script_sha256": args.script_sha256,
        "source_map_sha256": sha(map_raw),
        "source_sha256": pins,
        "historical_source_pins": len(old_pins),
        "historical_screen_sha256": SCREEN_SHA,
        "historical_proof_sha256": sha(read(args.screen_proof)),
        "started_utc": datetime.now(UTC).isoformat(),
        "phases": [],
        "workers": [],
        "sends": [],
        "real_provider_calls": 0,
        "host_candidate_execution": False,
        "host_official_execution": False,
        "source_program_sha256": dict(
            zip(("seed", "broken", "repaired", "grandchild"), source_hashes, strict=True)
        ),
        "candidate_ids": dict(
            zip(("seed", "broken", "repaired", "grandchild"), agent_ids, strict=True)
        ),
    }
    phase = "prepare"
    args.directory.mkdir()
    try:
        with (
            patch.dict(os.environ, synthetic_environment, clear=True),
            patch(
                "socket.create_connection", side_effect=RuntimeError("real connection forbidden")
            ),
            patch("socket.socket", side_effect=RuntimeError("real socket forbidden")),
            patch(
                "buddha.agent_run.AgentSession", side_effect=RuntimeError("fixed seed forbidden")
            ),
        ):
            record = old_screen
            generation = record["generation"]
            old_roots = {name: Path(path) for name, path in generation["roots"].items()}
            components = generation["selection"]["components"]
            roots = dict(old_roots)
            for role in ("agent", "runner", "environment", "host"):
                destination = args.directory / role
                destination.mkdir()
                if role == "agent":
                    native_pipeline._write(destination / "candidate.py", seed.encode())
                elif role == "runner":
                    (destination / "buddha").mkdir()
                    for name in candidate_run.RUNNER_FILES:
                        native_pipeline._write(
                            destination / "buddha" / (name + ".py"),
                            read(ROOT / "buddha" / (name + ".py")),
                        )
                else:
                    for name in components[role]:
                        target = destination / name
                        target.parent.mkdir(parents=True, exist_ok=True)
                        native_pipeline._write(target, read(old_roots[role] / name))
                roots[role] = destination
            selection = prepare_selection(
                Release.from_record(generation["selection"]["release"]),
                roots,
                capabilities=generation["selection"]["capabilities"],
            )
            runtime_path = roots["environment"] / "runtime.json"
            runtime_sha = sha(read(runtime_path))
            runtime = decode(read(runtime_path))
            require(
                runtime_sha == previous.RUNTIME_SHA and runtime["image_id"] == previous.IMAGE,
                "source runtime differs",
            )
            generation.update(
                selection=selection.to_record(),
                roots={name: str(path) for name, path in roots.items()},
                runtime={"path": str(runtime_path), "sha256": runtime_sha},
                max_callbacks=1,
            )
            generation["executor"]["mounts"] = [
                ["/agent", str(roots["agent"])],
                ["/runner", str(roots["runner"])],
            ]
            record.update(format="buddha.source-screen.v2", lineage=None)
            screen = source_screen.SourceScreen.from_bytes(_json(record))
            require(screen.candidate_id == agent_ids[0], "seed inventory differs")
            require(screen.tasks.to_bytes() == selected.to_bytes(), "selected tasks changed")
            docker = shutil.which("docker")
            require(docker is not None, "Docker unavailable")
            endpoint = h._endpoint(docker)
            require(
                endpoint
                == generation["executor"]["docker_endpoint"]
                == record["native"]["executor"]["docker_endpoint"],
                "declared local Docker endpoint changed",
            )
            template = {
                key: generation[key]
                for key in ("config", "profile", "max_callbacks", "budget_microusd", "max_calls")
            }
            spec = source_search.SourceSearchSpec.from_bytes(
                _json(
                    {
                        "format": "buddha.source-search.v1",
                        "iterations": 3,
                        "method": "latest",
                        "seed": 0,
                        "max_active": 4,
                    }
                )
            )
            authority = Authorization.create(
                args.directory / "synthetic-authorization.sqlite3",
                authorization_id="synthetic-three-iteration-source-loop",
                budget_microusd=100_000_000,
                max_calls=100,
                scope="source screen: " + screen.comparison_key(),
            )
            review = {
                "checked_on": datetime.now(UTC).date().isoformat(),
                "credential_sha256": {
                    provider: sha(value.encode()) for provider, value in h.KEYS.items()
                },
                "account_scope": "offline synthetic account only",
            }
            search = args.directory / "search"
            bindings = {
                SCRIPT: args.script_sha256,
                args.sources: args.sources_sha256,
                screen_path: SCREEN_SHA,
                args.screen_proof: previous.OLD_PROOF_SHA,
                args.screen_exit: previous.OLD_EXIT_SHA,
            }
            for path in source_search._sources():
                require(str(path) in pins, "caller map omits a required host source")
                bindings[path] = pins[str(path)]
            source_search.prepare_source_search(
                search,
                seed_screen=screen,
                proposal_template=template,
                spec=spec,
                authorization=authority,
                review=review,
                expected_runtime_sha256=runtime_sha,
                input_bindings=bindings,
            )
            state = SimpleNamespace(
                provider="openai", model=MODEL, mode="normal", sends=evidence["sends"]
            )
            current = {}
            weak = [
                "poor duplicate",
                "poor duplicate",
                "",
                " \n",
                "[refused]",
                "unfinished {",
                "literal é and 雪",
                "not a story",
                "short",
                "  final unchanged  ",
            ]
            proposals = [
                {"source": broken, "hypothesis": "Deliberately malformed controlled source."},
                {
                    "source": repaired,
                    "hypothesis": "Rotate outputs and target the weakest measured task.",
                },
                {
                    "source": grandchild,
                    "hypothesis": "Interleave answers and inherit the measured-feedback improver.",
                },
            ]

            class Connection(h.Connection):
                def request(self, method, path, *, body, headers):
                    require(len(state.sends) < 75, "additional synthetic reply attempted")
                    super().request(method, path, body=body, headers=headers)
                    request = decode(body)
                    self.model = request["model"]
                    owner = Path(current["owner"])
                    self.task = current.get("task")
                    if current["role"] == "proposal":
                        self.stage = "proposal"
                        ordinal = current["iteration"]
                        payload = decode(request["messages"][0]["content"].encode())
                        expected_parent = sources[0 if ordinal < 2 else 2]
                        expected_agent = agent_ids[0 if ordinal < 2 else 2]
                        require(
                            payload["phase"] == "propose"
                            and payload["parent"]
                            == {
                                "entrypoint": "candidate.py",
                                "source": expected_parent,
                                "agent_sha256": expected_agent,
                            },
                            "actual inherited parent differs",
                        )
                        require(
                            payload["feedback"] == current["feedback"],
                            "inherited improver did not consume exact measured history",
                        )
                        notes = [decode(row["note"].encode()) for row in payload["feedback"]]
                        require(
                            len(notes) == 2
                            and [row["task"]["id"] for row in payload["feedback"]]
                            == screen.to_record()["selected_ids"],
                            "extra or reordered feedback tasks",
                        )
                        if ordinal == 0:
                            require(
                                all(note["kind"] == "saved_native_measurements" for note in notes),
                                "initial feedback unexpectedly contains failures",
                            )
                        else:
                            require(
                                all(
                                    note["kind"] == "saved_native_measurements_and_failed_children"
                                    and len(note["failures"]) == 1
                                    and note["failures"][0]["child_id"] == agent_ids[1]
                                    for note in notes
                                ),
                                "verified failed child was lost",
                            )
                        if ordinal == 2:
                            values = [note["measurements"]["utility"] for note in notes]
                            require(
                                values[1] < values[0],
                                "canned task contrast did not reach actual native notes",
                            )
                            require(
                                payload["target_task_id"] == selected.tasks[1].id
                                and payload["measured_utilities"] == values
                                and payload["failed_child_ids"] == [agent_ids[1]],
                                "changed improver did not compute weakest measured target",
                            )
                            require(
                                current["agent_sha256"] == agent_ids[2],
                                "third proposal did not execute repaired source",
                            )
                        self.literal = json.dumps(proposals[ordinal], ensure_ascii=False)
                        evidence["sends"][self.index].update(
                            iteration=ordinal,
                            target_task_id=payload.get("target_task_id"),
                            parent_agent_sha256=expected_agent,
                            feedback_sha256=sha(_json(payload["feedback"])),
                        )
                    elif current["role"] == "generation":
                        self.stage = "generation"
                        payload = decode(request["messages"][0]["content"].encode())
                        expected_version = {
                            agent_ids[0]: "seed",
                            agent_ids[2]: "repaired",
                            agent_ids[3]: "grandchild",
                        }[current["agent_sha256"]]
                        require(
                            payload
                            == {
                                "phase": "generate",
                                "version": expected_version,
                                "task": selected.tasks[self.task].to_record(),
                            },
                            "generation procedure or task changed",
                        )
                        self.literal = json.dumps(weak, ensure_ascii=False)
                    else:
                        name = request["response_format"]["json_schema"]["name"]
                        self.stage = "partition" if name == "Partition" else "score"
                        require(
                            self.stage == ("partition" if current["command"] == 0 else "score"),
                            "official request stage differs",
                        )
                        self.literal = (
                            json.dumps({"groups": [[i] for i in range(10)]})
                            if self.stage == "partition"
                            else json.dumps({"score": 7 if self.task == 0 else 3})
                        )
                    require(
                        all(key.encode() not in body for key in h.KEYS.values()),
                        "credential in request body",
                    )
                    evidence["sends"][self.index].update(
                        stage=self.stage, owner=str(owner), task_index=self.task, model=self.model
                    )
                    print(
                        json.dumps(
                            {
                                "mocked_reply": self.index + 1,
                                "stage": self.stage,
                                "owner": str(owner.relative_to(search)),
                            }
                        ),
                        flush=True,
                    )

                def read(self, maximum):
                    raw = _json(
                        {
                            "id": "synthetic-source-loop-" + str(self.index),
                            "object": "chat.completion",
                            "created": 0,
                            "model": self.model,
                            "service_tier": "default",
                            "choices": [
                                {
                                    "index": 0,
                                    "message": {
                                        "role": "assistant",
                                        "content": self.literal,
                                        "refusal": None,
                                    },
                                    "finish_reason": "stop",
                                }
                            ],
                            "usage": {
                                "prompt_tokens": 5,
                                "completion_tokens": 3,
                                "total_tokens": 8,
                            },
                        }
                    )
                    require(len(raw) < maximum, "synthetic reply exceeds capture")
                    return raw

            actual_run = executor.run_container
            owners_seen = set()

            def observed(specification, **kwargs):
                require(
                    all(sha(read(Path(path))) == digest for path, digest in pins.items()),
                    "caller-approved sources changed before worker",
                )
                require(len(evidence["workers"]) < 28, "additional worker attempted")
                session = kwargs["handle"].__self__
                owner = session.gateway.directory
                require(
                    owner in owner_paths and owner not in owners_seen,
                    "worker is outside exact plan or replaced",
                )
                owners_seen.add(owner)
                initial = kwargs["initial"]
                relative = owner.relative_to(search)
                parts = relative.parts
                current.clear()
                current.update(owner=str(owner))
                if "proposal" in parts:
                    current.update(
                        role="proposal",
                        iteration=int(parts[1]),
                        feedback=initial["feedback"],
                        agent_sha256=initial["agent_sha256"],
                    )
                    require(
                        initial["format"] == "buddha.candidate-improvement-worker.v1",
                        "wrong proposal worker",
                    )
                elif specification.role == "agent":
                    current.update(
                        role="generation",
                        task=int(parts[parts.index("tasks") + 1]),
                        agent_sha256=initial["agent_sha256"],
                    )
                    require(
                        initial["format"] == "buddha.candidate-worker.v1"
                        and initial["task"] == selected.tasks[current["task"]].to_record(),
                        "source worker task differs",
                    )
                else:
                    current.update(
                        role="native",
                        task=int(parts[parts.index("tasks") + 1]),
                        command=initial["command"]["index"],
                    )
                if specification.role == "agent":
                    require(
                        specification.image_id == previous.IMAGE
                        and set(initial["roots"]) == {"agent", "runner"}
                        and {name for name, _ in specification.mounts} == {"/agent", "/runner"},
                        "source runtime/mounts changed",
                    )
                    require(
                        initial["runtime"]["sha256"] == runtime_sha
                        and initial["max_callbacks"] == 1,
                        "source runtime/quota differs",
                    )
                else:
                    require(
                        specification.image_id == record["native"]["executor"]["image_id"]
                        and {name for name, _ in specification.mounts}
                        == {"/official", "/runner", "/inputs"},
                        "native image/mounts changed",
                    )
                    require(
                        not session.profiles if current["command"] == 2 else bool(session.profiles),
                        "summary paid profile changed",
                    )
                require(
                    all(key.encode() not in _json(initial) for key in h.KEYS.values()),
                    "credential crossed worker frame",
                )
                frames = []
                handle = kwargs["handle"]

                def frame(value):
                    frames.append({"type": value.get("type"), "sha256": sha(_json(value))})
                    return handle(value)

                kwargs["handle"] = frame
                result = actual_run(specification, **kwargs)
                event = {
                    key: value for key, value in asdict(result).items() if key != "_configuration"
                } | {
                    "configuration": result.configuration,
                    "owner": str(owner),
                    "role": current["role"],
                    "frames": frames,
                }
                evidence["workers"].append(event)
                require(
                    type(result.exit_code) is int
                    and result.exit_code == 0
                    and result.cleanup_status == "removed"
                    and result.image_id == specification.image_id,
                    "worker failed or cleanup missing",
                )
                require(
                    re.fullmatch("[0-9a-f]{64}", result.container_id), "missing owned container ID"
                )
                require(
                    not h._control(
                        docker,
                        [
                            "--host",
                            endpoint,
                            "container",
                            "ls",
                            "-a",
                            "--no-trunc",
                            "--filter",
                            "id=" + result.container_id,
                            "--format",
                            "{{.ID}}",
                        ],
                    ).strip(),
                    "reported owned container remains",
                )
                return result

            wrote = native_pipeline._write
            interrupted = False
            decision_path = search / "iterations/0/decision.json"

            def interrupt_after_decision(path, raw):
                nonlocal interrupted
                wrote(path, raw)
                if path == decision_path and not interrupted:
                    interrupted = True
                    raise KeyboardInterrupt

            transport = RawHTTPTransport(allow_paid=True, timeout_seconds=15)
            phase = "interrupted-prefix"
            with (
                patch(
                    "http.client.HTTPSConnection",
                    side_effect=lambda host, **kwargs: Connection(state, host, **kwargs),
                ),
                patch("buddha.executor.run_container", side_effect=observed),
            ):
                try:
                    with patch.object(
                        native_pipeline, "_write", side_effect=interrupt_after_decision
                    ):
                        unexpected = source_search.run_source_search(search, transport=transport)
                        evidence["unexpected_first_return"] = unexpected
                except KeyboardInterrupt:
                    require(
                        interrupted and decision_path.is_file(),
                        "interruption preceded saved decision",
                    )
                else:
                    require(False, "planned host interruption did not occur")
                observations = sorted((search / "observations").glob("*.json"))
                require(len(observations) == 1, "cancel observation population differs")
                cancelled = decode(read(observations[0]))
                require(
                    cancelled["status"] == "incomplete"
                    and cancelled["reason"] == "cancelled"
                    and cancelled["iteration"] == 0,
                    "literal cancel observation missing",
                )
                require(
                    len(evidence["sends"]) == 25 and len(evidence["workers"]) == 10,
                    "interrupted prefix differs",
                )
                prefix = {
                    str(path): sha(read(path))
                    for directory in (search / "seed", search / "iterations/0")
                    for path in directory.rglob("*")
                    if path.is_file()
                }
                evidence["phases"].append(
                    {
                        "phase": phase,
                        "new_replies": 25,
                        "new_workers": 10,
                        "cancel_observation": cancelled,
                        "retained_files": prefix,
                    }
                )
                phase = "same-root-continuation"
                report = source_search.run_source_search(search, transport=transport)
                evidence["report"] = report
                require(report["status"] == "complete", "source loop stopped incomplete")
                require(
                    all(sha(read(Path(path))) == digest for path, digest in prefix.items()),
                    "completed prefix changed during continuation",
                )
                evidence["phases"].append(
                    {
                        "phase": phase,
                        "new_replies": len(evidence["sends"]) - 25,
                        "new_workers": len(evidence["workers"]) - 10,
                    }
                )
            require(
                len(evidence["sends"]) == 75 and len(evidence["workers"]) == 28,
                "actual work count differs",
            )
            require(
                len({row["container_id"] for row in evidence["workers"]}) == 28,
                "actual owned container identities are not distinct",
            )
            require(
                Counter(row["stage"] for row in evidence["sends"])
                == {"generation": 6, "partition": 6, "score": 60, "proposal": 3},
                "reply stage counts differ",
            )
            require(
                [row["status"] for row in report["decisions"]]
                == ["candidate_execution_failed", "admitted", "admitted"],
                "decision sequence differs",
            )
            require(
                [row["parent_id"] for row in report["decisions"]]
                == [agent_ids[0], agent_ids[0], agent_ids[2]],
                "actual inherited parent sequence differs",
            )
            require(
                report["selection"]["selected_id"] == agent_ids[3] and len(report["failures"]) == 1,
                "final parent or failure history differs",
            )
            expected_answers = {
                agent_ids[0]: weak,
                agent_ids[2]: weak[1:] + weak[:1],
                agent_ids[3]: weak[::2] + weak[1::2],
            }
            for ref in report["screens"]:
                screen_report = source_screen.inspect_source_screen(
                    Path(ref["directory"]),
                    authorization=authority.path,
                    expected_report_sha256=ref["report_sha256"],
                )
                if screen_report["disposition"] == "candidate_execution_failed":
                    require(
                        screen_report["failure"]["terminal"]["ready_seen"] is False
                        and screen_report["tasks"] == []
                        and screen_report["admission"]["mean_utility"] is None,
                        "failed source became C1 or a score",
                    )
                    continue
                for task_index in range(2):
                    root = Path(ref["directory"]) / "tasks" / str(task_index) / "generation"
                    seal = decode(read(root / "completed/0.json"))
                    answers = Answers.from_bytes(
                        read(root / seal["attempt"] / "session/answers.json")
                    )
                    require(
                        answers.to_record()["outputs"][0]["answers"]
                        == expected_answers[screen_report["candidate_id"]],
                        "actual changed generation procedure did not reach literal C1",
                    )
            histories = []
            expected_charge = 0
            for owner in owner_paths:
                manifest = _read_manifest(owner)
                history = read_gateway_history(
                    owner,
                    manifest_sha256=sha(_json(manifest)),
                    ledger_sha256=sha(read(owner / "operations.sqlite3")),
                )
                require(
                    all(operation.status == "completed" for operation in history.operations),
                    "owner retains uncertain operation",
                )
                for operation in history.operations:
                    request = operation.receipt["request"]
                    profile = manifest["profiles"][request["capability"]]["profiles"][
                        request["profile_id"]
                    ]
                    charge = ModelSpec(**profile["spec"]).cost_microusd(5, 3)
                    require(
                        operation.actual_microusd == charge,
                        "synthetic charge differs from selected profile",
                    )
                    expected_charge += charge
                histories.append(history)
            productive_owners = sum(bool(history.operations) for history in histories)
            require(productive_owners == 21, "owner operation coverage differs")
            funding = authority.summary()
            require(
                len({history.run_id for history in histories}) == 28
                and len(funding["runs"]) == 28
                and all(not row["active"] for row in funding["runs"]),
                "original owners are missing or not independently inactive",
            )
            require(
                sum(len(history.operations) for history in histories)
                == funding["operation_count"]
                == 75,
                "owner/authority operations differ",
            )
            for amounts in (
                funding,
                {
                    name: sum(history.totals()[name] for history in histories)
                    for name in ("spent_microusd", "committed_microusd", "reserved_microusd")
                },
            ):
                require(
                    amounts["spent_microusd"] == amounts["committed_microusd"] == expected_charge
                    and amounts["reserved_microusd"] == 0,
                    "synthetic totals or holds differ",
                )
            before_reads = previous.tree(args.directory, _Capture)
            phase = "keyless-complete-replay"
            with (
                patch.dict(os.environ, ordinary, clear=True),
                patch(
                    "buddha.executor.run_container",
                    side_effect=RuntimeError("new worker forbidden"),
                ),
                patch(
                    "buddha.candidate_run.CandidateSession",
                    side_effect=RuntimeError("new source session forbidden"),
                ),
                patch(
                    "buddha.native_run.NativeSession",
                    side_effect=RuntimeError("new native session forbidden"),
                ),
                patch(
                    "http.client.HTTPSConnection", side_effect=RuntimeError("new reply forbidden")
                ),
            ):
                require(
                    source_search.run_source_search(
                        search, transport=RawHTTPTransport(allow_paid=False, timeout_seconds=15)
                    )
                    == report,
                    "keyless complete replay differs",
                )
                phase = "passive-inspection"
                with (
                    patch(
                        "buddha.gateway.Gateway.__init__",
                        side_effect=RuntimeError("Gateway forbidden"),
                    ),
                    patch(
                        "buddha.authorization.Authorization.__init__",
                        side_effect=RuntimeError("Authority forbidden"),
                    ),
                ):
                    require(
                        source_search.inspect_source_search(
                            search,
                            authorization=authority.path,
                            expected_report_sha256=sha(read(search / "report.json")),
                        )
                        == report,
                        "passive loop differs",
                    )
            require(
                previous.tree(args.directory, _Capture) == before_reads,
                "keyless/passive paths changed bytes or layout",
            )
            evidence["phases"].extend(
                [
                    {"phase": "keyless-complete-replay", "new_replies": 0, "new_workers": 0},
                    {"phase": "passive-inspection", "new_replies": 0, "new_workers": 0},
                ]
            )
            phase = "retired-producer-passive"
            retired = args.directory / "retired-input-programs"
            retired.mkdir()
            retired_pins = {}
            for role in ("agent", "runner"):
                source, destination = roots[role], retired / role
                require(
                    source.resolve().is_relative_to(args.directory.resolve())
                    and destination.resolve().is_relative_to(args.directory.resolve()),
                    "retirement leaves synthetic fixture",
                )
                retired_pins[role] = {
                    str(path.relative_to(source)): sha(read(path))
                    for path in source.rglob("*")
                    if path.is_file()
                }
                shutil.move(str(source), str(destination))
                require(
                    all(
                        sha(read(destination / path)) == digest
                        for path, digest in retired_pins[role].items()
                    ),
                    "retirement changed program bytes",
                )
            before_retired_read = previous.tree(args.directory, _Capture)
            with (
                patch(
                    "buddha.gateway.Gateway.__init__", side_effect=RuntimeError("Gateway forbidden")
                ),
                patch(
                    "buddha.authorization.Authorization.__init__",
                    side_effect=RuntimeError("Authority forbidden"),
                ),
                patch(
                    "buddha.candidate_run.CandidateSession",
                    side_effect=RuntimeError("producer forbidden"),
                ),
                patch(
                    "buddha.native_run.NativeSession", side_effect=RuntimeError("native forbidden")
                ),
                patch("http.client.HTTPSConnection", side_effect=RuntimeError("HTTPS forbidden")),
            ):
                require(
                    source_search.inspect_source_search(
                        search,
                        authorization=authority.path,
                        expected_report_sha256=sha(read(search / "report.json")),
                    )
                    == report,
                    "retirement changed passive result",
                )
            require(
                previous.tree(args.directory, _Capture) == before_retired_read,
                "retired passive read changed bytes",
            )
            require(
                previous.tree(original, _Capture) == original_tree,
                "original synthetic evidence changed",
            )
            require(
                all(sha(read(Path(path))) == digest for path, digest in old_pins.items()),
                "historical sources changed",
            )
            require(
                previous.source_check(args) == (map_raw, pins), "current approved source changed"
            )
            evidence.update(
                status="pass",
                actual_workers=28,
                original_owners=28,
                productive_owners=productive_owners,
                physical_mocked_replies=75,
                expected_synthetic_charge_microusd=expected_charge,
                authorization=funding,
                owners=[
                    {
                        "directory": str(owner),
                        "run_id": history.run_id,
                        "manifest_sha256": history.manifest_sha256,
                        "ledger_sha256": history.ledger_sha256,
                        "totals": history.totals(),
                    }
                    for owner, history in zip(owner_paths, histories, strict=True)
                ],
                retired_input_programs=retired_pins,
                original_tree_unchanged=True,
                keyless_and_passive_bytes_unchanged=True,
                claim=(
                    "Actual inherited source generation, measured failure feedback, "
                    "durable recovery and unchanged official execution with canned "
                    "measurements only; no scientific or improved-improver claim."
                ),
            )
    except BaseException as error:
        evidence.update(status="failed", failed_phase=phase, failure_type=type(error).__name__)
        raise
    finally:
        evidence["finished_utc"] = datetime.now(UTC).isoformat()
        native_pipeline._write(
            args.out,
            (json.dumps(evidence, sort_keys=True, indent=2, allow_nan=False) + "\n").encode(),
        )


class Parser(argparse.ArgumentParser):
    def error(self, message):
        self.exit(2, "invalid proof arguments\n")


if __name__ == "__main__":
    parser = Parser(description=__doc__)
    for name in ("directory", "out", "sources", "screen-proof", "screen-exit"):
        parser.add_argument("--" + name, type=Path, required=True)
    for name in ("script-sha256", "sources-sha256"):
        parser.add_argument("--" + name, required=True)
    main(parser.parse_args())
