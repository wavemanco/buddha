"""Confined actual-starter chain using supplied children and synthetic replies.

No real keys, provider calls, official scoring or model-authorship claim.
The existing reviewed competence helper supplies only common validation and
the existing candidate/Gateway/runtime APIs. Historical helpers stay unchanged.
"""

import argparse
import json
import os
import shutil
import sys
from dataclasses import asdict
from datetime import UTC, datetime
from pathlib import Path
from types import ModuleType
from unittest.mock import patch

if not __debug__:
    raise RuntimeError("SOURCE_SEED_PROOF_REQUIRES_ORDINARY_PYTHON")

SCRIPT = Path(__file__).resolve()
ROOT = SCRIPT.parents[2]
PREVIOUS = ROOT / "docs/conformance/src02-competence-probe.py"
PREVIOUS_SHA = "cf4b4092fbf00bf2eb5ff248cf3b16e6c525db20b83c2c67ce7fbecfda5bc394"
sys.dont_write_bytecode = True


def main(args):
    import hashlib

    raw = PREVIOUS.read_bytes()
    if hashlib.sha256(raw).hexdigest() != PREVIOUS_SHA:
        raise RuntimeError("reviewed competence helper changed")
    previous = ModuleType("_source_seed_reviewed_competence_helper")
    previous.__file__ = str(PREVIOUS)
    exec(compile(raw, str(PREVIOUS), "exec"), vars(previous))  # nosec B102
    previous.SCRIPT = SCRIPT
    require, sha, read = previous.require, previous.sha, previous.read
    map_raw, pins = previous.source_check(args)
    require(pins.get(str(PREVIOUS)) == PREVIOUS_SHA, "source map omits reviewed helper")
    frozen_path = ROOT / "agents/frozen_seed.py"
    require(str(frozen_path) in pins, "source map omits frozen generation input")
    for path in (args.directory, args.out, args.sources):
        require(path.is_absolute() and ".." not in path.parts, "absolute paths required")
        require(path.parent.is_dir(), "output parents must exist")
    require(
        not args.directory.exists()
        and not args.directory.is_symlink()
        and not args.out.exists()
        and not args.out.is_symlink(),
        "fixture and receipt must be NEW",
    )
    require(not args.out.is_relative_to(args.directory), "receipt must be outside fixture")
    require(not any(Path(p).is_relative_to(args.directory) for p in pins), "input overlap")
    h = previous.load_helper()
    h._root(args.directory.parent)
    h._root(args.out.parent)
    from buddha.source_seed import FRAGMENT, compose_source_seed

    parent_raw = compose_source_seed(read(frozen_path))
    parent = parent_raw.decode()
    start, end = parent.index("def generate("), parent.index("# buddha.source-seed-improver.v1")

    def changed(body):
        # Trusted supplied controls, not a host repair of model-authored code.
        return parent[:start] + body + "\n\n" + parent[end:]

    child = changed("""def generate(task, config, complete):
    item, selected = _task(task), _config(config)
    drafts = []
    for _ in range(item["count"] + 1):
        drafts.append(normalize(selected["provider"], complete(
            selected["provider"], request(selected, item, drafts))))
    return (drafts[::2] + drafts[1::2])[:item["count"]]
""")
    grandchild = changed("""def generate(task, config, complete):
    item, selected = _task(task), _config(config)
    planning = dict(item, prompt=(
        "Plan contrasting central content for this task: " + item["prompt"]))
    plan = normalize(selected["provider"], complete(
        selected["provider"], request(selected, planning)))
    drafting = dict(item, prompt=item["prompt"] + "\\nPrivate planning input: " + plan)
    answers = []
    for _ in range(item["count"]):
        answers.append(normalize(selected["provider"], complete(
            selected["provider"], request(selected, drafting, answers))))
    return answers
""")
    programs = [parent, child, grandchild]
    candidate_hashes = {sha(value.encode()) for value in programs}
    require(len(candidate_hashes) == 3, "source controls must differ")
    require(all(value.endswith(FRAGMENT) for value in programs), "improver body differs")

    def audit(event, arguments):
        if event == "compile" and isinstance(arguments[0], (str, bytes)):
            value = arguments[0].encode() if isinstance(arguments[0], str) else arguments[0]
            require(sha(value) not in candidate_hashes, "candidate compiled on host")
        if event == "exec":
            name = arguments[0].co_filename
            require(not Path(name).is_relative_to(args.directory), "candidate executed on host")

    sys.addaudithook(audit)
    fixture = args.directory
    fixture.mkdir()
    environment = json.loads(read(previous.ENV_PATH))
    ordinary = {name: os.environ[name] for name in previous.SAFE_OS if name in os.environ}
    evidence = {
        "format": "buddha.source-seed-confined-proof.v1",
        "status": "running",
        "fixture": str(fixture),
        "source_map_sha256": sha(map_raw),
        "source_sha256": pins,
        "script_sha256": args.script_sha256,
        "source_bytes": [len(value.encode()) for value in programs],
        "source_hashes": [sha(value.encode()) for value in programs],
        "fragment_sha256": sha(FRAGMENT.encode()),
        "real_provider_calls": 0,
        "host_candidate_execution": False,
        "cases": [],
        "limits": [
            "Supplied children and synthetic usage; no model-authorship or token-capacity claim.",
            "Actual starter chain only; no universal admission, official scoring or quality claim.",
            "The unchanged inherited improver does not establish edited-improver efficacy.",
        ],
    }
    roots = {
        name: fixture / name for name in ("official", "runner", "agent", "environment", "host")
    }
    for path in roots.values():
        path.mkdir()
    for name in h.RUNNER_FILES:
        path = roots["runner"] / "buddha" / (name + ".py")
        path.parent.mkdir(exist_ok=True)
        path.write_bytes(read(ROOT / "buddha" / (name + ".py")))
    (roots["agent"] / "candidate.py").write_bytes(parent_raw)
    runtime = roots["environment"] / "runtime.json"
    runtime.write_bytes(read(previous.ENV_PATH))
    rows = [
        {
            "qid": "1",
            "question": "Give two contrasting fictional situations.",
            "metadata": "SELECTED_METADATA_SENTINEL",
        },
        {"qid": 1, "question": "SRC02_VALIDATION_SENTINEL"},
        {"qid": "final", "question": "SRC02_FINAL_SENTINEL"},
    ]
    dataset = b"".join(h._json(row) + b"\n" for row in rows)
    (roots["official"] / "tasks.jsonl").write_bytes(dataset)
    (roots["official"] / "unused.py").write_bytes(b"raise RuntimeError('no evaluator')\n")
    (roots["official"] / "fixture.lock").write_bytes(b"synthetic; no dependencies\n")
    release = h.Release.from_record(
        {
            "format": "buddha.benchmark-release.v1",
            "benchmark": "source-seed-interface-fixture",
            "release": "two-answer-chain",
            "upstream": {"url": "https://example.org/offline-fixture", "revision": "a" * 40},
            "source": h.inventory(roots["official"]),
            "dependency_lock": "fixture.lock",
            "task": {
                "dataset": "tasks.jsonl",
                "id_field": "qid",
                "prompt_field": "question",
                "answers_field": "answers",
                "count": 2,
            },
            "commands": [{"module": "unused", "argv": ["{artifacts}"]}],
            "artifacts": {
                "answers": "answers.jsonl",
                "results": ["unused.jsonl"],
                "summary": "summary.json",
            },
            "requires": [previous.CAPABILITY],
        }
    )
    source = h.TaskSet.from_dataset(release, dataset)
    selected = source.select(["1"])
    source_path, selected_path, split_path, feedback_path = [
        fixture / name for name in ("source.json", "selected.json", "split.json", "feedback.json")
    ]
    source_path.write_bytes(source.to_bytes())
    selected_path.write_bytes(selected.to_bytes())
    split_path.write_bytes(
        h._json(
            {
                "release_sha256": source.release_sha256,
                "dataset_sha256": source.dataset_sha256,
                "partitions": {"development": ["1"], "validation": [1], "final": ["final"]},
                "families": [
                    {"id": task.id, "family": "family-" + str(i)}
                    for i, task in enumerate(source.tasks)
                ],
            }
        )
    )

    def ref(path):
        return {"path": str(path), "sha256": sha(read(path))}

    feedback_path.write_bytes(
        h._json(
            {
                "format": "buddha.candidate-development-feedback.v1",
                "source": ref(source_path),
                "split": ref(split_path),
                "records": [{"task_id": "1", "note": previous.NOTE}],
            }
        )
    )
    spec = h.ModelSpec(
        "openai",
        previous.MODEL,
        100000,
        16384,
        1_000_000,
        2_000_000,
        "https://example.org/PROFILE_METADATA_SENTINEL",
    )
    (roots["host"] / "profiles.json").write_bytes(
        h._json(
            {
                "format": "buddha.gateway-profiles.v1",
                "profiles": {
                    "candidate": {
                        "spec": asdict(spec),
                        "response_models": [previous.MODEL],
                        "request_tiers": ["auto", "default"],
                        "response_tiers": ["", "default"],
                        "allow_omitted_tier": True,
                    }
                },
            }
        )
    )
    config = {
        "provider": "openai",
        "model": previous.MODEL,
        "max_output_tokens": 16384,
        "instructions": "Follow the literal task.",
        "sampling": "in-context",
    }
    controls = [
        args.sources,
        *map(Path, pins),
        source_path,
        selected_path,
        split_path,
        feedback_path,
        runtime,
    ]
    expected = {path: sha(read(path)) for path in controls}
    review = {
        "checked_on": datetime.now(UTC).date().isoformat(),
        "credential_sha256": {"openai": sha(h.KEYS["openai"].encode())},
        "account_scope": "synthetic actual source-seed chain only; no live account",
    }
    state = type("SyntheticState", (), {})()
    state.provider, state.model, state.mode, state.sends = "openai", previous.MODEL, "valid", []
    texts = [
        "parent one",
        "parent two",
        h._json(
            {"source": child, "hypothesis": "Overgenerate and select alternating drafts."}
        ).decode(),
        "child one",
        "discarded middle",
        "child two",
        h._json({"source": grandchild, "hypothesis": "Plan once before drafting."}).decode(),
        "Contrasting plan",
        "grandchild one",
        "grandchild two",
    ]

    class Connection(h.Connection):
        def request(self, method, path, *, body, headers):
            require(
                all(
                    value not in body for value in (*previous.FORBIDDEN, h.KEYS["openai"].encode())
                ),
                "private data crossed callback",
            )
            super().request(method, path, body=body, headers=headers)
            require(self.index < len(texts), "unexpected extra physical send")
            if self.index in (2, 6):
                prompt = json.loads(body)["messages"][-1]["content"]
                packet = json.loads(prompt.split("\n\nINPUT_JSON\n", 1)[1])
                require(
                    packet["parent"]["source"] == programs[0 if self.index == 2 else 1],
                    "wrong literal proposing parent",
                )
                require(
                    packet["development_feedback"]
                    == [{"task": selected.tasks[0].to_record(), "note": previous.NOTE}],
                    "wrong feedback projection",
                )
            state.sends[-1]["request_bytes"] = len(body)

        def read(self, maximum):
            raw = h._json(
                {
                    "model": previous.MODEL,
                    "service_tier": "default",
                    "choices": [
                        {
                            "message": {"content": texts[self.index], "refusal": None},
                            "finish_reason": "stop",
                        }
                    ],
                    "usage": {"prompt_tokens": 5, "completion_tokens": 3},
                }
            )
            require(len(raw) < maximum, "response exceeds capture ceiling")
            state.sends[self.index]["reply_bytes"] = len(raw)
            return raw

    try:
        with (
            patch.dict(os.environ, ordinary | {"OPENAI_API_KEY": h.KEYS["openai"]}, clear=True),
            patch(
                "http.client.HTTPSConnection",
                side_effect=lambda host, **kw: Connection(state, host, **kw),
            ),
            patch(
                "socket.create_connection",
                side_effect=RuntimeError("real provider network forbidden"),
            ),
        ):
            docker = shutil.which("docker")
            require(docker is not None, "Docker unavailable")
            endpoint = h._endpoint(docker)
            authority = h.Authorization.create(
                fixture / "authorization.sqlite3",
                authorization_id="source-seed-synthetic-chain",
                budget_microusd=10_000_000,
                max_calls=16,
                scope="synthetic actual-starter chain; never live",
            )
            agents, owners, protected = [], [], {}

            def run(label, agent, *, improve=False, quota, replay=None):
                require(previous.source_check(args) == (map_raw, pins), "source drift")
                selection = h.prepare_selection(
                    release,
                    roots | {"agent": agent},
                    capabilities={previous.CAPABILITY: "profiles.json"},
                )
                if agents:
                    before, after = agents[0].to_record(), selection.to_record()
                    require(
                        all(
                            before["components"][role] == after["components"][role]
                            for role in roots
                            if role != "agent"
                        ),
                        "protected selection changed",
                    )
                agents.append(selection)
                descriptor = fixture / (label + ".json") if replay is None else replay[1]
                if replay is None:
                    record = {
                        "format": "buddha.candidate-improvement.v1"
                        if improve
                        else "buddha.candidate-generation.v1",
                        "entrypoint": "candidate.py",
                        "config": config,
                        "max_callbacks": quota,
                        "runtime": {"path": str(runtime), "sha256": previous.ENV_SHA},
                        "profile": {"capability": previous.CAPABILITY, "profile_id": "candidate"},
                        "executor": {
                            "image_id": previous.IMAGE,
                            "role": "agent",
                            "mounts": [["/agent", str(agent)], ["/runner", str(roots["runner"])]],
                            "runner_entrypoint": "buddha/candidate_worker.py",
                            "limits": asdict(h.Limits(wall_seconds=45, memory_mib=256)),
                            "image_environment": [
                                value.split("=", 1) for value in environment["config"]["Env"]
                            ],
                            "docker_endpoint": endpoint,
                        },
                    }
                    record.update(
                        {
                            "parent_agent_sha256": selection.agent_sha256,
                            "feedback": ref(feedback_path),
                        }
                        if improve
                        else {"tasks": str(selected_path)}
                    )
                    descriptor.write_bytes(h._json(record))
                    bindings = expected | {
                        descriptor: sha(read(descriptor)),
                        agent / "candidate.py": sha(read(agent / "candidate.py")),
                    }
                    owner = h.prepare_gateway(
                        fixture / (label + "-owner"),
                        selection=selection,
                        roots=roots | {"agent": agent},
                        authorization=authority,
                        budget_microusd=10_000_000,
                        max_calls=16,
                        input_files=list(bindings),
                        expected_input_hashes=bindings,
                        review=review,
                        run_id=label,
                    )
                    owners.append(owner)
                else:
                    owner = replay[0]
                output = fixture / (label + "-output")
                gateway = h.Gateway(
                    owner,
                    transport=h.RawHTTPTransport(allow_paid=replay is None, timeout_seconds=15),
                )
                session = h.CandidateSession(
                    gateway,
                    descriptor=descriptor,
                    output=output,
                    expected_runtime_sha256=previous.ENV_SHA,
                )
                require(
                    all(
                        value not in h._json(session.worker)
                        for value in (*previous.FORBIDDEN, h.KEYS["openai"].encode())
                    ),
                    "private worker input",
                )
                count, totals = len(state.sends), authority.summary()
                print(
                    json.dumps({"phase": label, "status": "starting", "new_sends_so_far": count}),
                    flush=True,
                )
                with patch.dict(
                    os.environ,
                    ordinary
                    if replay is not None
                    else ordinary | {"OPENAI_API_KEY": h.KEYS["openai"]},
                    clear=True,
                ):
                    report = session.run()
                require(
                    report["status"] == "complete"
                    and report["execution"]["cleanup_status"] == "removed",
                    "session incomplete",
                )
                identity = report["execution"]["container_id"]
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
                            "id=" + identity,
                            "--format",
                            "{{.ID}}",
                        ],
                    ).strip(),
                    "owned worker remains",
                )
                if replay is not None:
                    require(
                        len(state.sends) == count and authority.summary() == totals,
                        "replay changed authority",
                    )
                case = {
                    "phase": label,
                    "report": report,
                    "owner": str(owner),
                    "output": str(output),
                    "new_sends": len(state.sends) - count,
                }
                if improve:
                    lineage = json.loads(read(output / "lineage.json"))
                    require(
                        lineage["parent"]["agent_sha256"] == selection.agent_sha256
                        and lineage["child"]["source_sha256"]
                        == sha(read(output / "child/candidate.py")),
                        "lineage differs",
                    )
                    case["lineage"] = lineage
                else:
                    answers = h.Answers.from_bytes(read(output / "answers.json"))
                    case["answers"] = answers.to_record()["outputs"][0]["answers"]
                for path in output.rglob("*"):
                    if path.is_file():
                        protected[str(path)] = sha(read(path))
                evidence["cases"].append(case)
                return output, (owner, descriptor)

            run("parent-generate", roots["agent"], quota=2)
            child_output, parent_owner = run(
                "parent-improve", roots["agent"], improve=True, quota=1
            )
            require(
                read(child_output / "child/candidate.py") == child.encode(), "literal child altered"
            )
            run("child-generate", child_output / "child", quota=3)
            grand_output, _ = run("child-improve", child_output / "child", improve=True, quota=1)
            require(
                read(grand_output / "child/candidate.py") == grandchild.encode(),
                "literal grandchild altered",
            )
            run("grandchild-generate", grand_output / "child", quota=3)
            replay, _ = run(
                "parent-replay", roots["agent"], improve=True, quota=1, replay=parent_owner
            )
            require(
                read(replay / "lineage.json") == read(child_output / "lineage.json"),
                "replay changed lineage",
            )
            require(
                [case["new_sends"] for case in evidence["cases"]] == [2, 1, 3, 1, 3, 0],
                "procedure callback counts differ",
            )
            require(
                [case["answers"] for case in evidence["cases"] if "answers" in case]
                == [
                    ["parent one", "parent two"],
                    ["child one", "child two"],
                    ["grandchild one", "grandchild two"],
                ],
                "literal answers differ",
            )
            require(
                all(sha(read(Path(path))) == digest for path, digest in protected.items()),
                "earlier outputs changed",
            )
            require(previous.source_check(args) == (map_raw, pins), "final source drift")
            evidence.update(
                status="pass",
                physical_mocked_replies=len(state.sends),
                workers=len(evidence["cases"]),
                owners=len(owners),
                authority=authority.summary(),
                request_bytes=[row["request_bytes"] for row in state.sends],
                reply_bytes=[row["reply_bytes"] for row in state.sends],
                prior_outputs_unchanged=True,
            )
    except BaseException as error:
        evidence.update(status="failed", exception_type=type(error).__name__)
        raise
    finally:
        h.save(args.out, evidence)
        print(
            json.dumps(
                {
                    "status": evidence["status"],
                    "receipt": str(args.out),
                    "sha256": sha(read(args.out)),
                }
            ),
            flush=True,
        )


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--directory", type=Path, required=True)
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--sources", type=Path, required=True)
    parser.add_argument("--sources-sha256", required=True)
    parser.add_argument("--script-sha256", required=True)
    main(parser.parse_args())
