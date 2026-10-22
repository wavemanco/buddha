"""SRC02 synthetic inherited-source competence probe.

The caller supplies a reviewed source-map file and SHA, this script's SHA, a NEW
absolute fixture directory and a NEW proof output. Only synthetic HTTP replies
and a separate synthetic authority are used. No evaluator or returned program
executes on the host. This proves bounded procedure/interface competence only.
"""

if not __debug__:
    raise RuntimeError("SRC02_COMPETENCE_REQUIRES_ORDINARY_PYTHON")

import argparse
import hashlib
import json
import os
import re
import shutil
import sqlite3
import sys
from contextlib import closing
from dataclasses import asdict
from datetime import UTC, datetime
from pathlib import Path
from types import ModuleType
from unittest.mock import patch

SCRIPT = Path(__file__).resolve()
ROOT = SCRIPT.parents[2]
HELPER = ROOT / "docs/conformance/src01-candidate-probe.py"
HELPER_SHA = "2cb5543adbf1dfdb736887ac4ed856ae6bd9cddd27e598720accf0ba482d5074"
ENV_PATH = ROOT / "docs/conformance/src01-runtime-environment.json"
ENV_SHA = "a7311f68ab4deb2eed770d0454ddd2877250a86b8a72716abac45b4ff6d43951"
IMAGE = "sha256:757f5ffd3125ae10a83a7fb7eed05afe5e047442e4063d21bf995c03db1d0f04"
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
MODEL = "src02-synthetic-model"
CAPABILITY = "openai.chat-completions.v1"
NOTE = "Change generation control flow; preserve the literal task."
FORBIDDEN = (
    b"SRC02_VALIDATION_SENTINEL",
    b"SRC02_FINAL_SENTINEL",
    b"SELECTED_METADATA_SENTINEL",
    b"PROFILE_METADATA_SENTINEL",
    b"dataset_base64",
    b'"partitions"',
    b'"price_source"',
    b'"input_microusd_per_million"',
    b'"output_microusd_per_million"',
)

# Literal fixture programs are never compiled, imported or called on this host.
# One exact improvement procedure is physically inherited into all three files.
COMMON = """import json
def request(config, complete, payload):
    body = json.dumps({"model": config["model"],
        "max_completion_tokens": config["max_output_tokens"],
        "messages": [{"role": "user", "content": json.dumps(payload,
        sort_keys=True, separators=(",", ":"))}]}, sort_keys=True,
        separators=(",", ":")).encode()
    return complete(config["provider"], body)["choices"][0]["message"]["content"]
"""
IMPROVER = """
def propose_improvement(parent_bundle, feedback, config, complete):
    reply = request(config, complete, {"phase": "improve",
        "parent": parent_bundle, "feedback": feedback})
    return json.loads(reply)
"""
PARENT = (
    COMMON
    + """
def generate(task, config, complete):
    return [request(config, complete, {"phase": "draft", "prompt": task["prompt"],
        "index": i}) for i in range(task["count"])]
"""
    + IMPROVER
)
CHILD = (
    COMMON
    + """
def generate(task, config, complete):
    return json.loads(request(config, complete, {"phase": "batch",
        "prompt": task["prompt"], "count": task["count"]}))
"""
    + IMPROVER
)
GRANDCHILD = (
    COMMON
    + """
def generate(task, config, complete):
    plan = request(config, complete, {"phase": "plan", "prompt": task["prompt"]})
    return [request(config, complete, {"phase": "draft", "prompt": task["prompt"],
        "plan": plan, "index": i}) for i in range(task["count"])]
"""
    + IMPROVER
)


def require(value, label):
    if not value:
        raise RuntimeError(label)


def sha(raw):
    return hashlib.sha256(raw).hexdigest()


def read(path, maximum=16 * 1024**2):
    with path.open("rb") as stream:
        raw = stream.read(maximum + 1)
    require(len(raw) <= maximum, "proof input exceeds bound")
    return raw


def source_check(args):
    require(sha(read(SCRIPT)) == args.script_sha256, "caller script approval differs")
    raw = read(args.sources, 1024**2)
    require(sha(raw) == args.sources_sha256, "caller source-map approval differs")
    pins = json.loads(raw)
    require(type(pins) is dict and 1 <= len(pins) <= 1024, "invalid source-map inventory")
    required = {SCRIPT, HELPER, ENV_PATH, *ROOT.joinpath("buddha").glob("*.py")}
    require({str(p) for p in required} <= set(pins), "source map omits installed proof sources")
    for name, digest in pins.items():
        path = Path(name)
        require(path.is_absolute() and ".." not in path.parts, "source pin path differs")
        require(type(digest) is str and re.fullmatch(r"[0-9a-f]{64}", digest), "bad source hash")
        require(sha(read(path)) == digest, "reviewed source bytes changed")
    require(
        sha(read(HELPER)) == HELPER_SHA and sha(read(ENV_PATH)) == ENV_SHA,
        "reviewed legacy helper or runtime changed",
    )
    return raw, pins


def load_helper():
    sys.path.insert(0, str(ROOT))
    sys.dont_write_bytecode = True
    module = ModuleType("_src02_reviewed_src01_helper")
    module.__file__ = str(HELPER)
    sys.modules[module.__name__] = module
    # Trusted, hash-checked engineering helper only; no candidate program is executed.
    code = compile(read(HELPER), str(HELPER), "exec")
    namespace = vars(module)
    exec(code, namespace)  # nosec B102
    return module


def main(args):
    map_raw, pins = source_check(args)
    h = load_helper()
    for path in (args.directory, args.out, args.sources):
        require(
            path.is_absolute() and ".." not in path.parts, "explicit absolute proof paths required"
        )
        h._root(path.parent)
    require(not args.directory.exists() and not args.out.exists(), "proof paths must be NEW")
    require(
        not any(Path(p).is_relative_to(args.directory) for p in pins), "fixture overlaps sources"
    )
    environment = json.loads(read(ENV_PATH))
    require(environment["image_id"] == IMAGE, "reviewed image differs")
    ordinary = {key: os.environ[key] for key in SAFE_OS if key in os.environ}
    fixture = args.directory
    fixture.mkdir()
    evidence = {
        "format": "buddha.src02-inherited-competence.v1",
        "status": "running",
        "fixture": str(fixture),
        "image_id": IMAGE,
        "environment_sha256": ENV_SHA,
        "script_sha256": args.script_sha256,
        "source_map_sha256": sha(map_raw),
        "source_sha256": pins,
        "source_map_path": str(args.sources),
        "real_provider_calls": 0,
        "host_candidate_execution": False,
        "cases": [],
    }
    phases = ["draft", "draft", "improve", "batch", "improve", "plan", "draft", "draft"]
    texts = [
        "parent one \n",
        "parent two",
        h._json(
            {"source": CHILD, "hypothesis": "Batch the two independent drafts in one callback."}
        ).decode(),
        h._json(["child one", "child two \n"]).decode(),
        h._json(
            {
                "source": GRANDCHILD,
                "hypothesis": "Plan contrasting content, then draft two answers.",
            }
        ).decode(),
        "Plan two contrasting approaches.",
        "grandchild one",
        "grandchild two \n",
    ]
    state = type("SyntheticState", (), {})()
    state.provider, state.model, state.mode, state.sends = "openai", MODEL, "valid", []

    class Connection(h.Connection):
        def request(self, method, path, *, body, headers):
            require(
                all(item not in body for item in (*FORBIDDEN, h.KEYS["openai"].encode())),
                "private source/profile/key crossed model channel",
            )
            super().request(method, path, body=body, headers=headers)
            require(self.index < len(phases), "unexpected physical callback")
            payload = json.loads(json.loads(body)["messages"][0]["content"])
            require(payload["phase"] == phases[self.index], "procedure callback order differs")

        def read(self, maximum):
            raw = h._json(
                {
                    "model": MODEL,
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
            require(len(raw) < maximum, "synthetic response exceeds capture")
            return raw

    class ObservedSession(h.CandidateSession):
        def handle(self, frame):
            self.frames.append(json.loads(h._json(frame)))
            return super().handle(frame)

    roots = {
        name: fixture / name for name in ("official", "runner", "agent", "environment", "host")
    }
    for path in roots.values():
        path.mkdir()
    for name in h.RUNNER_FILES:
        path = roots["runner"] / "buddha" / (name + ".py")
        path.parent.mkdir(exist_ok=True)
        path.write_bytes(read(ROOT / "buddha" / (name + ".py")))
    (roots["agent"] / "candidate.py").write_bytes(PARENT.encode())
    runtime = roots["environment"] / "runtime.json"
    runtime.write_bytes(read(ENV_PATH))
    rows = [
        {
            "qid": "1",
            "question": "Return two literal contrasting responses café 🌱.",
            "metadata": "SELECTED_METADATA_SENTINEL",
        },
        {"qid": 1, "question": "SRC02_VALIDATION_SENTINEL"},
        {"qid": "final", "question": "SRC02_FINAL_SENTINEL"},
    ]
    dataset = b"".join(h._json(row) + b"\n" for row in rows)
    (roots["official"] / "tasks.jsonl").write_bytes(dataset)
    (roots["official"] / "unused.py").write_bytes(
        b"raise RuntimeError('never execute evaluator')\n"
    )
    (roots["official"] / "fixture.lock").write_bytes(b"synthetic interface; no dependencies\n")
    release = h.Release.from_record(
        {
            "format": "buddha.benchmark-release.v1",
            "benchmark": "src02-interface-fixture",
            "release": "two-answer-source-chain",
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
            "requires": [CAPABILITY],
        }
    )
    source = h.TaskSet.from_dataset(release, dataset)
    selected = source.select(["1"])
    source_path, selected_path = fixture / "source.json", fixture / "selected.json"
    source_path.write_bytes(source.to_bytes())
    selected_path.write_bytes(selected.to_bytes())
    split_path, feedback_path = fixture / "split.json", fixture / "feedback.json"
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
                "records": [
                    {
                        "task_id": "1",
                        "note": NOTE,
                    }
                ],
            }
        )
    )
    spec = h.ModelSpec(
        "openai",
        MODEL,
        10000,
        4096,
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
                        "response_models": [MODEL],
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
        "model": MODEL,
        "max_output_tokens": 4096,
        "instructions": "Follow the literal selected development task.",
        "sampling": "regenerate",
    }
    controls = [
        SCRIPT,
        args.sources,
        *map(Path, pins),
        source_path,
        selected_path,
        split_path,
        feedback_path,
        runtime,
    ]
    control_pins = {path: sha(read(path)) for path in controls}
    control_pins.update({Path(name): digest for name, digest in pins.items()})
    control_pins[args.sources] = sha(map_raw)
    review = {
        "checked_on": datetime.now(UTC).date().isoformat(),
        "credential_sha256": {"openai": sha(h.KEYS["openai"].encode())},
        "account_scope": "synthetic SRC02 competence only; no real account",
    }
    owners, actual_ids, preserved = [], [], {}

    def snapshot(paths):
        return {
            str(p): sha(read(p)) for root in paths for p in sorted(root.rglob("*")) if p.is_file()
        }

    try:
        with (
            patch.dict(os.environ, ordinary | {"OPENAI_API_KEY": h.KEYS["openai"]}, clear=True),
            patch(
                "http.client.HTTPSConnection",
                side_effect=lambda host, **kw: Connection(state, host, **kw),
            ),
            patch("socket.create_connection", side_effect=RuntimeError("real network forbidden")),
        ):
            docker = shutil.which("docker")
            require(docker is not None, "Docker unavailable")
            endpoint = h._endpoint(docker)
            authority = h.Authorization.create(
                fixture / "authorization.sqlite3",
                authorization_id="src02-engineering-chain",
                budget_microusd=1_000_000,
                max_calls=16,
                scope="synthetic inherited-source competence; never live",
            )

            def prepare(label, selection, agent, *, improve=False, quota=3):
                require(
                    source_check(args) == (map_raw, pins),
                    "approved source changed before preparation",
                )
                own_roots = roots | {"agent": agent}
                descriptor = fixture / (label + ".json")
                record = {
                    "format": "buddha.candidate-improvement.v1"
                    if improve
                    else "buddha.candidate-generation.v1",
                    "entrypoint": "candidate.py",
                    "config": config,
                    "max_callbacks": quota,
                    "runtime": {"path": str(runtime), "sha256": ENV_SHA},
                    "profile": {"capability": CAPABILITY, "profile_id": "candidate"},
                    "executor": {
                        "image_id": IMAGE,
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
                    {"parent_agent_sha256": selection.agent_sha256, "feedback": ref(feedback_path)}
                    if improve
                    else {"tasks": str(selected_path)}
                )
                descriptor.write_bytes(h._json(record))
                inputs = list(dict.fromkeys([*controls, descriptor, agent / "candidate.py"]))
                expected = control_pins | {
                    descriptor: sha(h._json(record)),
                    agent / "candidate.py": selection.to_record()["components"]["agent"][
                        "candidate.py"
                    ],
                }
                owner = h.prepare_gateway(
                    fixture / (label + "-owner"),
                    selection=selection,
                    roots=own_roots,
                    authorization=authority,
                    budget_microusd=1_000_000,
                    max_calls=16,
                    input_files=inputs,
                    expected_input_hashes=expected,
                    review=review,
                    run_id=label,
                )
                owners.append(owner)
                return owner, descriptor

            def run(label, owner, descriptor, selection, *, replay=False):
                require(
                    source_check(args) == (map_raw, pins), "approved source changed before worker"
                )
                gateway = h.Gateway(
                    owner, transport=h.RawHTTPTransport(allow_paid=not replay, timeout_seconds=15)
                )
                output = fixture / label
                session = ObservedSession(
                    gateway, descriptor=descriptor, output=output, expected_runtime_sha256=ENV_SHA
                )
                session.frames = []
                initial = h._json(session.worker)
                require(
                    all(value not in initial for value in (*FORBIDDEN, h.KEYS["openai"].encode())),
                    "private source/profile/key crossed configure",
                )
                require(set(session.worker["roots"]) == {"agent", "runner"}, "extra worker mount")
                require(
                    set(session.worker["config"]) == set(config), "worker configuration expanded"
                )
                if session.improvement:
                    require(
                        session.worker["feedback"]
                        == [
                            {
                                "task": selected.tasks[0].to_record(),
                                "note": NOTE,
                            }
                        ],
                        "feedback projection differs",
                    )
                else:
                    require(
                        session.worker["task"] == selected.tasks[0].to_record(),
                        "task projection differs",
                    )
                before, ledger_before = len(state.sends), gateway.ledger.totals()
                if replay:
                    with (
                        patch.dict(os.environ, ordinary, clear=True),
                        patch(
                            "http.client.HTTPSConnection",
                            side_effect=RuntimeError("keyless replay HTTPS forbidden"),
                        ),
                    ):
                        report = session.run()
                else:
                    report = session.run()
                require(report["status"] == "complete", "source task/improvement did not complete")
                execution = report["execution"]
                require(execution["cleanup_status"] == "removed", "owned worker cleanup missing")
                identity = execution["container_id"]
                require(
                    re.fullmatch(r"[0-9a-f]{64}", identity) and identity not in actual_ids,
                    "actual worker identity missing or repeated",
                )
                actual_ids.append(identity)
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
                    "reported owned worker remains",
                )
                require(
                    set(execution["configuration"]["mounts"]) == {"/agent", "/runner"},
                    "extra source exposure",
                )
                with closing(sqlite3.connect(":memory:")) as db:
                    db.deserialize(gateway.ledger.path.read_bytes())
                    db.execute("PRAGMA query_only=ON")
                    ids = [
                        row[0]
                        for row in db.execute(
                            "SELECT operation_id FROM operations ORDER BY operation_id"
                        )
                    ]
                operations = []
                for identifier in ids:
                    op = gateway.ledger.get(identifier)
                    require(
                        op.status == "completed" and op.response is not None,
                        "incomplete synthetic receipt",
                    )
                    operations.append(
                        {
                            "operation_id": identifier,
                            "actual_microusd": op.actual_microusd,
                            "receipt_sha256": sha(h._json(op.response)),
                        }
                    )
                result = {
                    "label": label,
                    "report": report,
                    "output": str(output),
                    "selection_sha256": selection.fingerprint(),
                    "agent_sha256": selection.agent_sha256,
                    "owner": str(owner),
                    "new_sends": len(state.sends) - before,
                    "ledger": gateway.ledger.totals(),
                    "operations": operations,
                    "configure_sha256": sha(initial),
                    "frame_types": [f["type"] for f in session.frames],
                }
                if not session.improvement:
                    answers = h.Answers.from_bytes(read(output / "answers.json"))
                    result["answers"] = answers.to_record()["outputs"]
                    require(
                        answers.to_record()["agent_sha256"] == selection.agent_sha256,
                        "C1 agent identity differs",
                    )
                    require(
                        json.loads(answers.native_bytes())
                        == rows[0] | {"answers": result["answers"][0]["answers"]},
                        "literal C1/source projection differs",
                    )
                else:
                    lineage = json.loads(read(output / "lineage.json"))
                    result["lineage"] = lineage
                    require(
                        lineage["descriptor_sha256"] == sha(read(descriptor))
                        and lineage["feedback"]
                        == {
                            "file_sha256": sha(read(feedback_path)),
                            "input_sha256": sha(h._json(session.feedback)),
                        }
                        and lineage["proposal_sha256"] == sha(read(output / "proposal.json"))
                        and lineage["owner"]
                        == {"path": str(owner), "manifest_sha256": gateway.manifest_sha256},
                        "lineage original descriptor, feedback or owner differs",
                    )
                    require(
                        lineage["parent"]["agent_sha256"] == selection.agent_sha256
                        and lineage["parent"]["source_sha256"]
                        == sha(read(dict(session.spec.mounts)["/agent"] / "candidate.py")),
                        "lineage parent differs",
                    )
                    require(
                        lineage["child"]["source_sha256"]
                        == sha(read(output / "child/candidate.py"))
                        and lineage["child"]["agent_sha256"]
                        == sha(h._json(h.inventory(output / "child"))),
                        "lineage materialized child differs",
                    )
                if replay:
                    require(
                        result["new_sends"] == 0 and result["ledger"] == ledger_before,
                        "replay changed financial evidence",
                    )
                evidence["cases"].append(result)
                print(
                    json.dumps(
                        {
                            "label": label,
                            "status": report["status"],
                            "new_sends": result["new_sends"],
                        }
                    ),
                    flush=True,
                )
                return output

            parent = h.prepare_selection(release, roots, capabilities={CAPABILITY: "profiles.json"})
            pg, pgd = prepare("parent-generation", parent, roots["agent"], quota=2)
            po = run("parent-generation-output", pg, pgd, parent)
            pi, pid = prepare("parent-improvement", parent, roots["agent"], improve=True, quota=1)
            child_output = run("parent-improvement-output", pi, pid, parent)
            preserved = snapshot([roots["agent"], pg, pi, po, child_output])

            def inherit(output, original, expected):
                agent = output / "child"
                raw = read(agent / "candidate.py")
                require(
                    raw == expected.encode() and raw.endswith(IMPROVER.encode()),
                    "inherited program differs",
                )
                selection = h.prepare_selection(
                    release,
                    roots | {"agent": agent},
                    capabilities=original.to_record()["capabilities"],
                )
                a, b = original.to_record(), selection.to_record()
                require(
                    a["release"] == b["release"]
                    and a["capabilities"] == b["capabilities"]
                    and all(
                        a["components"][role] == b["components"][role]
                        for role in roots
                        if role != "agent"
                    ),
                    "child changed protected selection",
                )
                return selection, agent

            child, child_agent = inherit(child_output, parent, CHILD)
            cg, cgd = prepare("child-generation", child, child_agent, quota=1)
            run("child-generation-output", cg, cgd, child)
            ci, cid = prepare("child-improvement", child, child_agent, improve=True, quota=1)
            grand_output = run("child-improvement-output", ci, cid, child)
            grand, grand_agent = inherit(grand_output, child, GRANDCHILD)
            gg, ggd = prepare("grandchild-generation", grand, grand_agent, quota=3)
            run("grandchild-generation-output", gg, ggd, grand)
            require(
                len(state.sends) == 8 and len(actual_ids) == 5, "five-job competence counts differ"
            )
            total_before = authority.summary()
            replay = run("parent-improvement-replay", pi, pid, parent, replay=True)
            require(
                read(replay / "child/candidate.py") == read(child_output / "child/candidate.py")
                and read(replay / "lineage.json") == read(child_output / "lineage.json"),
                "same-owner child identity differs",
            )
            require(
                authority.summary() == total_before
                and len(state.sends) == 8
                and len(actual_ids) == 6,
                "replay added an owner/call/charge or missed worker",
            )
            require(
                [case["new_sends"] for case in evidence["cases"]] == [2, 1, 1, 1, 3, 0],
                "observed procedure-specific callback counts differ",
            )
            require(
                all(sha(read(Path(p))) == digest for p, digest in preserved.items()),
                "parent evidence changed",
            )
            totals = authority.summary()
            require(
                totals["operation_count"] == 8 and totals["reserved_microusd"] == 0,
                "shared synthetic accounting differs",
            )
            expected_answers = [
                ["parent one \n", "parent two"],
                ["child one", "child two \n"],
                ["grandchild one", "grandchild two \n"],
            ]
            require(
                [c["answers"][0]["answers"] for c in evidence["cases"] if "answers" in c]
                == expected_answers,
                "literal generation outputs changed",
            )
            require("_buddha_candidate" not in sys.modules, "candidate executed on host")
            require(source_check(args) == (map_raw, pins), "approved source map changed")
            evidence.update(
                status="pass",
                physical_mocked_replies=len(state.sends),
                actual_workers=len(actual_ids),
                original_job_workers=5,
                replay_workers=1,
                owned_containers_removed=actual_ids,
                owner_count=len(owners),
                authority=totals,
                inherited_improver_body_sha256=sha(IMPROVER.encode()),
                parent_evidence_unchanged=True,
                selection_sha256=[parent.fingerprint(), child.fingerprint(), grand.fingerprint()],
                agent_sha256=[parent.agent_sha256, child.agent_sha256, grand.agent_sha256],
            )
    except BaseException as error:
        evidence.update(status="failed", exception_type=type(error).__name__)
        raise
    finally:
        evidence["limits"] = [
            "Synthetic replies/usage only; no actual provider or creativity claim.",
            "Five competence jobs and one same-owner replay; not full SRC02, search or admission.",
            "No evaluator execution. The separate SRC01 proof supplies the runtime OS evidence.",
            "Cleanup checks only reported owned container IDs, never unrelated containers.",
        ]
        h.save(args.out, evidence)
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
    parser.add_argument("--directory", type=Path, required=True)
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--sources", type=Path, required=True)
    parser.add_argument("--sources-sha256", required=True)
    parser.add_argument("--script-sha256", required=True)
    main(parser.parse_args())
