"""One actual inherited improver consumes saved synthetic measured feedback.

Use only after review with pinned inputs and NEW fixture/receipt paths. One
container and one mocked HTTPS reply are expected; no generation or judging is
rerun. No real provider, credential, funding or scientific result is involved.
"""

import argparse
import hashlib
import json
import os
import re
import shutil
import stat
import sys
from dataclasses import asdict
from datetime import UTC, datetime
from pathlib import Path
from types import ModuleType, SimpleNamespace
from unittest.mock import patch

if not __debug__:
    raise RuntimeError("This proof requires ordinary Python with assertions enabled")

SCRIPT = Path(__file__).resolve()
ROOT = SCRIPT.parents[2]
HELPER = ROOT / "docs/conformance/src01-candidate-probe.py"
HELPER_SHA = "2cb5543adbf1dfdb736887ac4ed856ae6bd9cddd27e598720accf0ba482d5074"
COMPETENCE = ROOT / "docs/conformance/src02-competence-probe.py"
COMPETENCE_SHA = "cf4b4092fbf00bf2eb5ff248cf3b16e6c525db20b83c2c67ce7fbecfda5bc394"
RUNTIME = ROOT / "docs/conformance/src01-runtime-environment.json"
RUNTIME_SHA = "a7311f68ab4deb2eed770d0454ddd2877250a86b8a72716abac45b4ff6d43951"
OLD_PROOF_SHA = "6b70cb3ffcbe7a386dcd963dfaf33fbef4ff44cfed194db64a587b2220e2fad5"
OLD_EXIT_SHA = "2bc7f1eac964ed08db7bcbaf94cde0482015b7d129240a3bb272bbbc24856b67"
PARENT_SHA = "3f28e7b45ae45a23f5c70989e2e89a79d6bab5d213f9e9d70f00a5213334022f"
PARENT_ID = "a6fb5cad443177608635f67523494bdcfca83034ba694d3efdb9e70be87a7d1c"
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


def require(value, label):
    if not value:
        raise RuntimeError(label)


def synthetic_database(value, directory):
    if type(value) is type(directory):
        value = str(value)
    if type(value) is not str:
        return False
    authority = directory / "synthetic-authorization.sqlite3"
    ledger = directory / "proposal-stage/owners/0/operations.sqlite3"
    return value in {
        ":memory:",
        str(authority),
        str(ledger),
        authority.as_uri() + "?mode=rw",
        authority.as_uri() + "?mode=ro",
        ledger.as_uri() + "?mode=rw",
    }


def sha(raw):
    return hashlib.sha256(raw).hexdigest()


def read(path, maximum=32 * 1024**2):
    information = path.lstat()
    require(
        stat.S_ISREG(information.st_mode)
        and information.st_nlink == 1
        and not getattr(information, "st_file_attributes", 0) & 0x400,
        "proof input is not an unaliased regular file",
    )
    require(information.st_size <= maximum, "proof input exceeds its byte ceiling")
    with path.open("rb") as stream:
        raw = stream.read(maximum + 1)
    require(len(raw) == information.st_size and len(raw) <= maximum, "proof input changed")
    after = path.lstat()
    require(
        (information.st_dev, information.st_ino, information.st_size, information.st_mtime_ns)
        == (after.st_dev, after.st_ino, after.st_size, after.st_mtime_ns),
        "proof input identity changed",
    )
    return raw


def decode(raw):
    def pairs(items):
        result = {}
        for key, value in items:
            require(key not in result, "duplicate proof JSON key")
            result[key] = value
        return result

    return json.loads(raw, object_pairs_hook=pairs)


def tree(directory, capture_type):
    capture = capture_type(directory)
    result = {}
    for relative in capture.entries:
        path = directory / relative
        if stat.S_ISDIR(path.lstat().st_mode):
            result[relative] = {"kind": "directory"}
        else:
            raw = capture.read(path)
            result[relative] = {"kind": "file", "bytes": len(raw), "sha256": sha(raw)}
    capture.finish()
    return result


def module(path, expected, name):
    raw = read(path, 1024**2)
    require(sha(raw) == expected, "reviewed engineering helper differs")
    result = ModuleType(name)
    result.__file__ = str(path)
    sys.modules[name] = result
    exec(compile(raw, str(path), "exec"), vars(result))  # nosec B102
    return result


def source_check(args):
    require(sha(read(SCRIPT)) == args.script_sha256, "caller driver approval differs")
    raw = read(args.sources, 1024**2)
    require(sha(raw) == args.sources_sha256, "caller source-map approval differs")
    pins = decode(raw)
    require(type(pins) is dict and 1 <= len(pins) <= 1024, "invalid source-map inventory")
    required = {SCRIPT, HELPER, COMPETENCE, RUNTIME, args.screen_proof, args.screen_exit}
    for name in ("buddha", "agents", "tests", "docs/conformance"):
        required.update((ROOT / name).rglob("*.py"))
    require({str(path) for path in required} <= set(pins), "approval omits proof sources/assets")
    for name, expected in pins.items():
        path = Path(name)
        require(path.is_absolute() and ".." not in path.parts, "source pin must be absolute")
        require(type(expected) is str and re.fullmatch("[0-9a-f]{64}", expected), "invalid pin")
        require(sha(read(path)) == expected, "caller-approved source changed")
    for path, expected in (
        (HELPER, HELPER_SHA),
        (COMPETENCE, COMPETENCE_SHA),
        (RUNTIME, RUNTIME_SHA),
        (args.screen_proof, OLD_PROOF_SHA),
        (args.screen_exit, OLD_EXIT_SHA),
    ):
        require(sha(read(path)) == expected, "historical prerequisite differs")
    return raw, pins


def main(args):
    for path in (args.directory, args.out, args.sources, args.screen_proof, args.screen_exit):
        require(path.is_absolute() and ".." not in path.parts, "absolute proof paths required")
    require(
        not args.directory.exists()
        and not args.directory.is_symlink()
        and not args.out.exists()
        and not args.out.is_symlink(),
        "outputs must be NEW",
    )
    require(args.directory.parent.is_dir() and args.out.parent.is_dir(), "parents must exist")
    require(not args.out.is_relative_to(args.directory), "receipt must be outside fixture")
    map_raw, pins = source_check(args)
    old = decode(read(args.screen_proof))
    terminal = decode(read(args.screen_exit))
    require(old["status"] == "pass" and terminal["exit_code"] == 0, "saved proof not terminal")
    require(old["real_provider_calls"] == 0, "original screen is not synthetic")
    original = Path(old["fixture"])
    require(original.is_absolute() and original.is_dir(), "saved synthetic fixture missing")
    require(
        not args.directory.is_relative_to(original)
        and not original.is_relative_to(args.directory)
        and not args.out.is_relative_to(original)
        and not any(Path(name).is_relative_to(args.directory) for name in pins),
        "new fixture overlaps original inputs",
    )
    old_pins = old["source_sha256"]
    require(
        type(old_pins) is dict and len(old_pins) == 208, "original proof pin population differs"
    )
    require(
        all(sha(read(Path(p))) == h for p, h in old_pins.items()), "original proof sources differ"
    )
    reference = old["references"][0]
    screen_path = Path(reference["directory"]) / "screen.json"
    screen = decode(read(screen_path))
    generation = screen["generation"]
    parent_path = Path(old["retired_producer_programs"]["agent-0"]["retained"]) / "candidate.py"
    parent_raw = read(parent_path, 1024**2)
    require(sha(parent_raw) == PARENT_SHA, "retained inherited parent changed")
    require(
        old["source_programs"][0]["candidate_id"] == PARENT_ID, "screen parent identity differs"
    )
    require(screen["selected_ids"] == ["curated-9", "curated-0"], "measured task order differs")
    sys.path.insert(0, str(ROOT))
    sys.dont_write_bytecode = True
    h = module(HELPER, HELPER_SHA, "_proposal_stage_reviewed_helper")
    competence = module(COMPETENCE, COMPETENCE_SHA, "_proposal_stage_reviewed_text")
    from buddha import (
        candidate_improvement,
        candidate_run,
        executor,
        native_pipeline,
        source_feedback,
    )
    from buddha.answers import TaskSet
    from buddha.doctor import _Capture
    from buddha.gateway import RawHTTPTransport
    from buddha.gateway_history import read_gateway_history
    from buddha.provider import ModelSpec
    from buddha.releases import Selection, _json, prepare_selection

    original_tree = tree(original, _Capture)
    proposal = {
        "source": competence.GRANDCHILD,
        "hypothesis": "Plan, then draft distinct positions.",
    }
    require(sha(proposal["source"].encode()) != PARENT_SHA, "controlled child is unchanged")
    selected_parent = Selection.from_bytes(_json(generation["selection"]))
    require(selected_parent.agent_sha256 == PARENT_ID, "saved selection parent differs")
    for path in (args.directory.parent, args.out.parent):
        require(h._root(path) == path, "output parent must be plain and canonical")
    protected_code = {PARENT_SHA, sha(proposal["source"].encode())}

    def audit(event, arguments):
        if event == "compile" and isinstance(arguments[0], (str, bytes)):
            raw = arguments[0].encode() if isinstance(arguments[0], str) else arguments[0]
            require(sha(raw) not in protected_code, "candidate source compiled on host")
        if event == "exec":
            name = arguments[0].co_filename
            if name and not name.startswith("<"):
                path = Path(name).absolute()
                require(
                    not path.is_relative_to(original) and not path.is_relative_to(args.directory),
                    "original or candidate program executed on host",
                )
        if event == "open" and isinstance(arguments[0], (str, bytes, os.PathLike)):
            path = Path(os.fsdecode(arguments[0])).absolute()
            mode, flags = arguments[1], arguments[2]
            writing = (isinstance(mode, str) and any(v in mode for v in "wax+")) or flags & (
                os.O_WRONLY | os.O_RDWR | os.O_CREAT | os.O_TRUNC | os.O_APPEND
            )
            require(not (writing and path.is_relative_to(original)), "original fixture write")
        if event == "sqlite3.connect":
            require(
                synthetic_database(arguments[0], args.directory),
                "non-synthetic database connection attempted",
            )

    sys.addaudithook(audit)
    ordinary = {name: os.environ[name] for name in SAFE_OS if name in os.environ}
    fake_environment = ordinary | {"OPENAI_API_KEY": h.KEYS["openai"]}
    evidence = {
        "format": "buddha.src02-source-proposal-stage-native-proof.v1",
        "status": "running",
        "fixture": str(args.directory),
        "script_sha256": args.script_sha256,
        "source_map_sha256": sha(map_raw),
        "source_sha256": pins,
        "saved_screen_proof_sha256": OLD_PROOF_SHA,
        "saved_screen_reference": reference,
        "original_fixture": str(original),
        "original_fixture_entries": len(original_tree),
        "parent_source_sha256": PARENT_SHA,
        "parent_agent_sha256": PARENT_ID,
        "source_image": IMAGE,
        "real_provider_calls": 0,
        "host_candidate_execution": False,
        "host_official_execution": False,
    }
    phase = "prepare"
    try:
        args.directory.mkdir()
        packet = args.directory / "measured-feedback"
        with (
            patch.dict(os.environ, fake_environment, clear=True),
            patch("socket.socket", side_effect=RuntimeError("real socket forbidden")),
            patch("socket.create_connection", side_effect=RuntimeError("real network forbidden")),
        ):
            written = source_feedback.write_source_feedback(packet, reference=reference)
            bundle = source_feedback.inspect_source_feedback(
                packet, expected_provenance_sha256=written["provenance"]["sha256"]
            )
            require(bundle["provenance"]["candidate_id"] == PARENT_ID, "feedback parent differs")
            tasks = TaskSet.from_bytes(_json(bundle["source"]))
            selected = {task.id: task for task in tasks.tasks}
            projection = [
                {"task": selected[row["task_id"]].to_record(), "note": row["note"]}
                for row in bundle["feedback"]["records"]
            ]
            require(
                [row["task"]["id"] for row in projection] == screen["selected_ids"], "wrong tasks"
            )
            require(all(row["task"]["count"] == 10 for row in projection), "wrong answer count")
            roots = {name: Path(path) for name, path in generation["roots"].items()}
            for role in ("agent", "runner", "environment", "host"):
                target = args.directory / role
                target.mkdir()
                if role == "agent":
                    (target / "candidate.py").write_bytes(parent_raw)
                elif role == "runner":
                    (target / "buddha").mkdir()
                    for name in candidate_run.RUNNER_FILES:
                        (target / "buddha" / (name + ".py")).write_bytes(
                            read(ROOT / "buddha" / (name + ".py"))
                        )
                else:
                    for name in generation["selection"]["components"][role]:
                        destination = target / name
                        destination.parent.mkdir(parents=True, exist_ok=True)
                        destination.write_bytes(read(roots[role] / name))
                roots[role] = target
            selection = prepare_selection(
                h.Release.from_record(selected_parent.to_record()["release"]),
                roots,
                capabilities=generation["selection"]["capabilities"],
            )
            require(selection.to_record() == generation["selection"], "copied selection changed")
            require(selection.agent_sha256 == PARENT_ID, "inherited parent source ID changed")
            runtime = roots["environment"] / "runtime.json"
            require(sha(read(runtime)) == RUNTIME_SHA, "runtime copy changed")
            profiles = decode(read(roots["host"] / "profiles.json"))
            config, profile = generation["config"], generation["profile"]
            spec = ModelSpec(**profiles["profiles"][profile["profile_id"]]["spec"])
            expected_charge = spec.cost_microusd(5, 3)
            require(expected_charge == 11, "synthetic profile arithmetic changed")
            docker = shutil.which("docker")
            require(docker is not None, "Docker unavailable")
            endpoint = h._endpoint(docker)
            descriptor_record = {
                key: generation[key] for key in ("config", "entrypoint", "executor", "profile")
            }
            descriptor_record.update(
                format="buddha.candidate-improvement.v1",
                parent_agent_sha256=PARENT_ID,
                feedback=written["feedback"],
                max_callbacks=1,
                runtime={"path": str(runtime), "sha256": RUNTIME_SHA},
            )
            descriptor_record["executor"] = generation["executor"] | {
                "mounts": [["/agent", str(roots["agent"])], ["/runner", str(roots["runner"])]],
                "docker_endpoint": endpoint,
            }
            descriptor = args.directory / "improvement.json"
            descriptor.write_bytes(_json(descriptor_record))
            authority = h.Authorization.create(
                args.directory / "synthetic-authorization.sqlite3",
                authorization_id="synthetic-durable-proposal-stage",
                budget_microusd=spec.reserve_microusd(),
                max_calls=1,
                scope="offline one-container measured proposal rehearsal; never live",
            )
            directory = args.directory / "proposal-stage"
            evidence["stage_directory"] = str(directory)
            bindings = {
                SCRIPT: args.script_sha256,
                args.sources: args.sources_sha256,
                args.screen_proof: OLD_PROOF_SHA,
                args.screen_exit: OLD_EXIT_SHA,
            }
            candidate_improvement.prepare_candidate_improvement(
                directory,
                descriptor=descriptor,
                selection=selection,
                roots=roots,
                authorization=authority,
                review={
                    "checked_on": datetime.now(UTC).date().isoformat(),
                    "credential_sha256": {"openai": sha(h.KEYS["openai"].encode())},
                    "account_scope": "offline synthetic account only",
                },
                budget_microusd=spec.reserve_microusd(),
                max_calls=1,
                expected_runtime_sha256=RUNTIME_SHA,
                expected_feedback_provenance_sha256=written["provenance"]["sha256"],
                input_files=list(bindings),
                expected_input_hashes=bindings,
            )
            state = SimpleNamespace(
                provider="openai", model=config["model"], mode="valid", sends=[]
            )

            class Connection(h.Connection):
                def request(self, method, path, *, body, headers):
                    super().request(method, path, body=body, headers=headers)
                    require(self.index == 0, "unexpected additional physical callback")
                    payload = decode(decode(body)["messages"][0]["content"])
                    require(set(payload) == {"phase", "parent", "feedback"}, "wrong callback shape")
                    require(payload["phase"] == "improve", "inherited improver did not execute")
                    require(payload["feedback"] == projection, "measured notes were not consumed")
                    require(
                        payload["parent"]
                        == {
                            "source": parent_raw.decode(),
                            "entrypoint": "candidate.py",
                            "agent_sha256": PARENT_ID,
                        },
                        "wrong parent bundle",
                    )
                    require(all(key.encode() not in body for key in h.KEYS.values()), "key in body")

                def read(self, maximum):
                    raw = _json(
                        {
                            "model": config["model"],
                            "service_tier": "default",
                            "choices": [
                                {
                                    "message": {
                                        "content": _json(proposal).decode(),
                                        "refusal": None,
                                    },
                                    "finish_reason": "stop",
                                }
                            ],
                            "usage": {"prompt_tokens": 5, "completion_tokens": 3},
                        }
                    )
                    require(len(raw) < maximum, "synthetic reply exceeds capture")
                    return raw

            executions = []
            actual_run = executor.run_container

            def observed(specification, **kwargs):
                require(not executions, "unexpected additional actual worker")
                initial = kwargs["initial"]
                require(initial["format"] == "buddha.candidate-improvement-worker.v1", "wrong mode")
                require(initial["feedback"] == projection, "worker received different feedback")
                require(set(initial["roots"]) == {"agent", "runner"}, "extra worker roots")
                require(initial["max_callbacks"] == 1, "worker quota changed")
                require(initial["config"] == config, "worker configuration changed")
                require(initial["agent_sha256"] == PARENT_ID, "worker parent changed")
                require(
                    specification.image_id == IMAGE and specification.role == "agent",
                    "worker runtime changed",
                )
                require(
                    {name for name, _ in specification.mounts} == {"/agent", "/runner"},
                    "unexpected mounts",
                )
                result = actual_run(specification, **kwargs)
                executions.append(
                    {key: value for key, value in asdict(result).items() if key != "_configuration"}
                    | {"configuration": result.configuration}
                )
                return result

            phase = "actual-improvement"
            with (
                patch(
                    "http.client.HTTPSConnection",
                    side_effect=lambda host, **kw: Connection(state, host, **kw),
                ),
                patch("buddha.executor.run_container", side_effect=observed),
            ):
                report = candidate_improvement.run_candidate_improvement(
                    directory, transport=RawHTTPTransport(allow_paid=True, timeout_seconds=15)
                )
            evidence["report"] = report
            require(
                report["status"] == "complete" and report["disposition"] == "materialized",
                "proposal did not materialize",
            )
            require(len(executions) == len(state.sends) == 1, "actual work population differs")
            execution = executions[0]
            identity = execution["container_id"]
            require(re.fullmatch("[0-9a-f]{64}", identity), "actual container ID missing")
            require(
                execution["image_id"] == IMAGE and execution["cleanup_status"] == "removed",
                "owned worker did not cleanly finish",
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
                        "id=" + identity,
                        "--format",
                        "{{.ID}}",
                    ],
                ).strip(),
                "owned container remains",
            )
            child = Path(report["child"]["directory"]) / "candidate.py"
            require(
                read(child) == proposal["source"].encode(), "literal materialized child differs"
            )
            owner = directory / "owners/0"
            manifest = decode(read(owner / "manifest.json"))
            history = read_gateway_history(
                owner,
                manifest_sha256=manifest["record_sha256"],
                ledger_sha256=sha(read(owner / "operations.sqlite3")),
            )
            require(
                len(history.operations) == 1 and history.operations[0].status == "completed",
                "original owner not completed",
            )
            totals, funding = history.totals(), authority.summary()
            for amounts in (totals, funding):
                require(
                    amounts["spent_microusd"] == amounts["committed_microusd"] == expected_charge
                    and amounts["reserved_microusd"] == 0,
                    "synthetic cost/hold differs",
                )
            require(
                len(funding["runs"]) == 1 and not funding["runs"][0]["active"],
                "owner not independently inactive",
            )
            require(len(list((directory / "owners").iterdir())) == 1, "unexpected owner")
            before_replay = tree(args.directory, _Capture)
            phase = "keyless-and-passive"
            with (
                patch.dict(os.environ, ordinary, clear=True),
                patch(
                    "buddha.candidate_run.CandidateSession",
                    side_effect=RuntimeError("new session forbidden"),
                ),
                patch(
                    "buddha.executor.run_container",
                    side_effect=RuntimeError("new worker forbidden"),
                ),
                patch(
                    "http.client.HTTPSConnection", side_effect=RuntimeError("new HTTPS forbidden")
                ),
            ):
                require(
                    candidate_improvement.run_candidate_improvement(
                        directory, transport=RawHTTPTransport(allow_paid=False)
                    )
                    == report,
                    "keyless completed replay differs",
                )
                with (
                    patch(
                        "buddha.gateway.Gateway.__init__",
                        side_effect=RuntimeError("Gateway forbidden"),
                    ),
                    patch(
                        "buddha.authorization.Authorization.__init__",
                        side_effect=RuntimeError("authority forbidden"),
                    ),
                    patch(
                        "buddha.native_run.NativeSession",
                        side_effect=RuntimeError("native forbidden"),
                    ),
                ):
                    require(
                        candidate_improvement.inspect_candidate_improvement(
                            directory,
                            authorization=authority.path,
                            expected_report_sha256=sha(read(directory / "report.json")),
                        )
                        == report,
                        "passive inspection differs",
                    )
            require(
                tree(args.directory, _Capture) == before_replay,
                "keyless/passive paths changed persistent bytes",
            )
            require(tree(original, _Capture) == original_tree, "original screen evidence changed")
            require(
                all(sha(read(Path(p))) == v for p, v in old_pins.items()),
                "original proof sources changed",
            )
            require(source_check(args) == (map_raw, pins), "current approved source changed")
            evidence.update(
                status="pass",
                actual_workers=executions,
                productive_owners=1,
                physical_mocked_replies=1,
                expected_synthetic_charge_microusd=expected_charge,
                owner_totals=totals,
                authorization=funding,
                report=report,
                packet=written,
                measured_projection_sha256=sha(_json(projection)),
                sends=state.sends,
                original_entire_fixture_bytes_unchanged=True,
                original_208_source_pins_unchanged=True,
                keyless_and_passive_bytes_unchanged=True,
                limits=[
                    "One actual improver; no new generation/native judging/child execution.",
                    "Synthetic replies and proposals; no authorship or improvement claim.",
                    "No injected stop/recovery; focused tests have separate scopes.",
                    "Cleanup checks only its one reported container ID.",
                ],
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
