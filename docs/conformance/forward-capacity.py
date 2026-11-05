"""Prepare/check one offline capacity observation; execution needs separate approval."""

import argparse
import hashlib
import json
import os
import platform
import re
import shutil
import stat

# Only fixed read-only Git or the pinned Python recipe is run; never a shell.
import subprocess  # nosec B404
import sys
import tempfile
import time
import traceback
from pathlib import Path

PROJECT = Path(__file__).resolve().parents[2]
PROTOCOL = "docs/conformance/forward-capacity-protocol.json"
RECIPE = "docs/conformance/forward-capacity.py"


def plain(path):
    path = Path(path)
    if not path.is_absolute() or ".." in path.parts:
        raise ValueError("an absolute nontraversing path is required")
    for member in (path, *path.parents):
        if not os.path.lexists(member):
            continue
        info = member.lstat()
        if member.is_symlink() or getattr(info, "st_file_attributes", 0) & 0x400:
            raise ValueError("links and reparse points are refused")
        if not (stat.S_ISDIR(info.st_mode) or stat.S_ISREG(info.st_mode)):
            raise ValueError("special files are refused")
        if stat.S_ISREG(info.st_mode) and info.st_nlink != 1:
            raise ValueError("file aliases are refused")
    if path.resolve() != path:
        raise ValueError("paths require their resolved spelling")
    return path


def sha(path):
    path = plain(path)
    before = path.stat()
    if not stat.S_ISREG(before.st_mode) or before.st_size > 512 * 1024**2:
        raise ValueError("file is absent or exceeds the existing ledger ceiling")
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024**2), b""):
            digest.update(block)
    after = path.stat()
    if (before.st_dev, before.st_ino, before.st_size, before.st_mtime_ns, before.st_ctime_ns) != (
        after.st_dev,
        after.st_ino,
        after.st_size,
        after.st_mtime_ns,
        after.st_ctime_ns,
    ):
        raise ValueError("file changed while hashed")
    return digest.hexdigest()


def load(path):
    if plain(path).stat().st_size > 32 * 1024**2:
        raise ValueError("JSON exceeds the existing manifest ceiling")
    return json.loads(path.read_bytes())


def write(path, record):
    plain(path.parent)
    with path.open("x", encoding="utf-8") as stream:
        json.dump(record, stream, sort_keys=True, allow_nan=False)
        stream.write("\n")
        stream.flush()
        os.fsync(stream.fileno())


def source_snapshot(project):
    project = plain(project)
    paths = [
        path for name in ("buddha", "agents", "tests") for path in (project / name).rglob("*.py")
    ]
    paths += [project / "ci_test_shard.py", project / RECIPE, project / PROTOCOL]
    return {path.relative_to(project).as_posix(): sha(path) for path in sorted(paths)}


def clean_environment():
    result = {
        key: os.environ[key]
        for key in (
            "PATH",
            "SystemRoot",
            "WINDIR",
            "PROCESSOR_ARCHITECTURE",
            "PROCESSOR_IDENTIFIER",
            "PROCESSOR_ARCHITEW6432",
        )
        if key in os.environ
    }
    result["GIT_OPTIONAL_LOCKS"] = "0"
    return result


def checked_binding(path, expected, output, *, git_check=True):
    path, output = plain(path), plain(output)
    if not re.fullmatch("[0-9a-f]{64}", expected) or sha(path) != expected:
        raise ValueError("external binding differs from the supplied SHA256")
    record = load(path)
    if set(record) != {"format", "project", "head", "tree", "sources"} or (
        record["format"] != "buddha.forward-capacity-binding.v1"
    ):
        raise ValueError("unsupported source binding")
    project = plain(record["project"])
    if project != PROJECT or output.is_relative_to(project) or project.is_relative_to(output):
        raise ValueError("recipe/source identity or separate output scope differs")
    if path.is_relative_to(output) or not output.parent.is_dir():
        raise ValueError("output overlaps the binding or lacks its existing parent")
    if source_snapshot(project) != record["sources"]:
        raise ValueError("current public source/recipe/protocol closure differs")
    if git_check:
        git = shutil.which("git")
        if git is None:
            raise ValueError("Git is required for checked source identity")
        git = str(Path(git).resolve(strict=True))
        for args, wanted in (
            (["rev-parse", "HEAD"], record["head"]),
            (["rev-parse", "HEAD^{tree}"], record["tree"]),
            (["status", "--porcelain", "--untracked-files=normal"], ""),
        ):
            # Absolute Git with fixed read-only arguments; binding values are compared only.
            actual = subprocess.run(  # nosec B603
                [git, "--no-optional-locks", *args],
                cwd=project,
                env=clean_environment(),
                check=True,
                capture_output=True,
                text=True,
                timeout=30,
            ).stdout.strip()
            if actual != wanted:
                raise ValueError("selected Git head/tree/clean status differs")
    protocol = load(project / PROTOCOL)
    if protocol["format"] != "buddha.forward-capacity-protocol.v1" or (
        protocol["total_seconds"],
        protocol["reader_seconds"],
        protocol["reporting_seconds"],
        protocol["peak_working_set_bytes"],
    ) != (16800, 1800, 600, 4 * 1024**3):
        raise ValueError("capacity limits differ from this reviewed recipe")
    return record, protocol


def remaining_seconds(started, total, phase=None):
    value = total - (time.monotonic() - started)
    if value <= 0:
        raise TimeoutError("shared total deadline exhausted")
    return value if phase is None else min(value, phase)


def whole_child_peak_memory():
    observation = {
        "collected": False,
        "peak_working_set_bytes": None,
        "scope": "through final validation before terminal report writing",
    }
    try:
        import ctypes
        from ctypes import wintypes

        class Counters(ctypes.Structure):
            _fields_ = [("cb", wintypes.DWORD), ("PageFaultCount", wintypes.DWORD)] + [
                (name, ctypes.c_size_t)
                for name in (
                    "PeakWorkingSetSize",
                    "WorkingSetSize",
                    "QuotaPeakPagedPoolUsage",
                    "QuotaPagedPoolUsage",
                    "QuotaPeakNonPagedPoolUsage",
                    "QuotaNonPagedPoolUsage",
                    "PagefileUsage",
                    "PeakPagefileUsage",
                )
            ]

        kernel = ctypes.WinDLL("kernel32", use_last_error=True)
        kernel.GetCurrentProcess.restype = wintypes.HANDLE
        psapi = ctypes.WinDLL("psapi", use_last_error=True)
        psapi.GetProcessMemoryInfo.argtypes = [
            wintypes.HANDLE,
            ctypes.POINTER(Counters),
            wintypes.DWORD,
        ]
        psapi.GetProcessMemoryInfo.restype = wintypes.BOOL
        counters = Counters()
        counters.cb = ctypes.sizeof(counters)
        if not psapi.GetProcessMemoryInfo(
            kernel.GetCurrentProcess(), ctypes.byref(counters), counters.cb
        ):
            raise ctypes.WinError(ctypes.get_last_error())
        observation.update(collected=True, peak_working_set_bytes=counters.PeakWorkingSetSize)
    except (AttributeError, OSError) as error:
        observation["error_type"] = type(error).__name__
    return observation


def phase_passes(result, protocol):
    memory = result.get("memory", {})
    peak = memory.get("peak_working_set_bytes")
    return (
        result.get("status") == "complete"
        and result.get("sources_unchanged") is True
        and (
            memory.get("collected") is True
            and type(peak) is int
            and 0 < peak <= protocol["peak_working_set_bytes"]
        )
    )


def tree_snapshot(root):
    root = plain(root)
    paths = sorted(root.rglob("*"))
    if len(paths) > 100000:
        raise ValueError("retained tree exceeds the existing entry ceiling")
    return {
        path.relative_to(root).as_posix() + ("/" if plain(path).is_dir() else ""): None
        if path.is_dir()
        else sha(path)
        for path in paths
    }


def origins(project, sources):
    fixtures = {
        Path(relative).stem: project / relative
        for relative in sources
        if Path(relative).parent == Path("tests") and Path(relative).suffix == ".py"
    }
    for name, module in list(sys.modules.items()):
        fixture = name.removeprefix("tests.")
        if module is None or not (
            name == "buddha" or name.startswith("buddha.") or fixture in fixtures
        ):
            continue
        filename = getattr(module, "__file__", None)
        if not isinstance(filename, str):
            raise ValueError("loaded source module has no concrete file origin")
        path = plain(Path(filename).resolve())
        expected = project / (
            name.replace(".", "/") + ".py"
            if name.startswith("buddha.")
            else "buddha/__init__.py"
            if name == "buddha"
            else fixtures[fixture].relative_to(project)
        )
        if path != expected:
            raise ValueError("loaded application/fixture origin differs")


def build(output, protocol, sources):
    import unittest
    from unittest.mock import patch

    import scale_replay_fixture as fixture

    from buddha import improver_study

    origins(PROJECT, sources)
    original_temporary = tempfile.TemporaryDirectory

    def retained(*args, **kwargs):
        temporary = original_temporary(
            *args, **(kwargs | {"dir": output / "workspace", "delete": False})
        )
        return temporary

    case = unittest.TestCase("runTest")
    print(
        json.dumps(
            {"event": "preparing_fixture", "elapsed_seconds": time.monotonic() - PHASE_START}
        ),
        flush=True,
    )
    with patch.object(tempfile, "TemporaryDirectory", side_effect=retained):
        f, declaration = fixture.prepare_forward(case)
    origins(PROJECT, sources)
    expected, screen = protocol["expected"], f.base.to_record()
    dimensions = {
        "source_rows": len(f.h.source.tasks),
        "selected_tasks": len(f.base.tasks.tasks),
        "answers_per_task": f.answer_count,
        "starts": len(declaration["starts"]),
        "arms": len(declaration["improvers"]),
        "repetitions": declaration["repetitions"],
        "opportunities_per_arm": declaration["descendant_opportunities"],
        "generation_callbacks": f.generation_callbacks,
        "partition_callbacks": f.engine.native_callback_counts[0],
        "quality_callbacks": f.engine.native_callback_counts[1],
        "dataset_bytes": len(
            (f.engine.fixture.roots["official"] / "data/tasks.jsonl").read_bytes()
        ),
        "task_source_bytes": len(f.h.source.to_bytes()),
        "native_inventory_rows": len(screen["native"]["environment"]["inventory"]),
    }
    print(json.dumps({"event": "dimensions", "observed": dimensions}), flush=True)
    if any(value != expected[key] for key, value in dimensions.items()) or (
        any(task.count != expected["answers_per_task"] for task in f.base.tasks.tasks)
        or len(f.base.to_bytes()) < expected["screen_bytes_floor"]
        or len(
            json.dumps(
                screen["native"]["environment"], sort_keys=True, separators=(",", ":")
            ).encode()
        )
        < expected["native_environment_bytes_floor"]
        or declaration["limits"]["study"]["max_calls"] != expected["declared_max_calls"]
        or screen["projection"] != "noveltybench-1.1"
        or any(
            len(answer.encode("utf-8")) != expected["answer_utf8_bytes"]
            for answer in f.answer_values()
        )
    ):
        raise AssertionError("prospective fixture dimensions differ")
    directory, _, authority = f.prepare_study("forward-capacity", declaration)
    ordinary = improver_study._advance_action

    def advance(reader, state, funded, transport):
        print(
            json.dumps(
                {
                    "event": "action",
                    "elapsed_seconds": time.monotonic() - PHASE_START,
                    "kind": state["action"]["kind"],
                    "position": state["action"]["position"],
                    "owners_before": len(state["owner_paths"]),
                    "operations_before": state["authorization"]["operation_count"],
                }
            ),
            flush=True,
        )
        return ordinary(reader, state, funded, transport)

    with patch.object(improver_study, "_advance_action", side_effect=advance):
        result = f.run_study(directory)
    if result["status"] != "complete":
        return {
            "study_outcome": result,
            "directory": str(directory),
            "authorization": str(authority.path),
        }
    coverage = {
        "expected_common": 4,
        "completed_common": 4,
        "expected_cells": 8,
        "completed_cells": 8,
        "expected_opportunities": 16,
        "attempted_opportunities": 16,
        "completed_opportunities": 16,
        "in_flight_opportunities": 0,
        "unattempted_opportunities": 0,
    }
    summary = authority.summary()
    if (
        result["status"] != "complete"
        or result["coverage"] != coverage
        or (
            len(result["decisions"]) != expected["admitted_children"]
            or any(row["status"] != "admitted" for row in result["decisions"])
            or len(result["provenance"]["owners"]) != expected["owners"]
            or len(summary["runs"]) != expected["owners"]
            or summary["operation_count"] != expected["operations"]
            or summary["reserved_microusd"] != 0
            or any(row["active"] for row in summary["runs"])
        )
    ):
        raise AssertionError("ordinary writer did not complete the exact declared workload")
    f.assert_accounting(directory, authority, result, declaration)
    common_screens = list(directory.glob("common/*/*/screen"))
    screens = common_screens + [Path(row["screen"]["directory"]) for row in result["decisions"]]
    task_rows = [row for screen in screens for row in load(screen / "report.json")["tasks"]]
    if (
        len(common_screens) != expected["common_screens"]
        or len(screens) != expected["screens"]
        or len(task_rows) != expected["task_assessments"]
        or (
            sum(len(row["diagnostics"]["score"]["generation_scores"]) for row in task_rows)
            != expected["scored_answers"]
            or len(f.generated) * expected["answers_per_task"]
            != expected["total_generated_answers"]
        )
    ):
        raise AssertionError("generation/assessment/score population differs")
    witnesses = list(directory.rglob("witness/report.json"))
    checkpoints = list(directory.rglob("proposal-capacity.json"))
    if (
        len(witnesses) != expected["witnesses"]
        or any(load(path)["status"] != "passed" for path in witnesses)
        or (
            len(checkpoints) != expected["capacity_checkpoints"]
            or any(load(path)["decision"] != "pass" for path in checkpoints)
        )
    ):
        raise AssertionError("witness or capacity work is missing or failed")
    for decision in result["decisions"]:
        location = (
            directory
            / "cells"
            / "/".join(str(decision[name]) for name in ("start", "repetition", "arm", "slot"))
        )
        feedback_rows = load(location / "feedback/feedback.json")["records"]
        if len(feedback_rows) != expected["selected_tasks"]:
            raise AssertionError("complete feedback task count differs")
        for row in feedback_rows:
            measured = json.loads(row["note"])["measurements"]
            if measured["omitted_answer_positions"] != 0 or measured["answers"] != [
                {"position": index, "text": text} for index, text in enumerate(f.answer_values())
            ]:
                raise AssertionError("literal full feedback differs")
    answer_counts, answer_bytes = {"scored": 0, "witness": 0}, {"scored": 0, "witness": 0}
    for completion in directory.rglob("generation/completed/0.json"):
        root = completion.parent.parent
        attempt = root / load(completion)["attempt"]
        if attempt != root / "attempts/0-0":
            raise AssertionError("generation retried or changed its original attempt")
        outputs = load(attempt / "session/answers.json")["outputs"]
        role = "witness" if "witness" in root.relative_to(directory).parts else "scored"
        if len(outputs) != 1 or outputs[0]["answers"] != f.answer_values():
            raise AssertionError("retained literal C1 differs from the supplied byte envelope")
        answer_counts[role] += len(outputs[0]["answers"])
        answer_bytes[role] += sum(len(value.encode("utf-8")) for value in outputs[0]["answers"])
    if sum(answer_counts.values()) != expected["total_generated_answers"] or (
        answer_counts["scored"] != expected["scored_answers"]
        or answer_bytes["scored"] != expected["scored_answer_utf8_bytes"]
        or answer_bytes["witness"] != expected["witness_answer_utf8_bytes"]
    ):
        raise AssertionError("actual generated answer population/bytes differ")
    return {
        "directory": str(directory),
        "authorization": str(authority.path),
        "report_sha256": sha(directory / "report.json"),
        "authority_sha256": sha(authority.path),
        "tree": tree_snapshot(directory),
        "dimensions": dimensions,
        "owners": expected["owners"],
        "operations": expected["operations"],
        "coverage": coverage,
        "answer_counts": answer_counts,
        "answer_bytes": answer_bytes,
    }


def read(output, protocol, sources):
    from buddha import improver_study
    from buddha.releases import _json

    origins(PROJECT, sources)
    built = load(output / "build-result.json")
    if not phase_passes(built, protocol):
        raise ValueError("writer did not pass its complete checked phase")
    data = built["data"]
    directory, authority = plain(data["directory"]), plain(data["authorization"])
    workspace = output / "workspace"
    if not directory.is_relative_to(workspace) or not authority.is_relative_to(workspace):
        raise ValueError("fresh read would leave this attempt's synthetic workspace")
    if tree_snapshot(directory) != data["tree"] or sha(authority) != data["authority_sha256"]:
        raise ValueError("retained synthetic evidence changed before fresh inspection")
    observed = improver_study.inspect_improver_study(
        directory, authorization=authority, expected_report_sha256=data["report_sha256"]
    )
    origins(PROJECT, sources)
    raw = _json(observed)
    if (
        raw != (directory / "report.json").read_bytes()
        or tree_snapshot(directory) != data["tree"]
        or sha(authority) != data["authority_sha256"]
    ):
        raise AssertionError(
            "fresh passive inspection changed or disagreed with the complete report"
        )
    return {
        "owners": data["owners"],
        "operations": data["operations"],
        "report_sha256": data["report_sha256"],
        "strict_inspection": True,
        "tree_and_authority_unchanged": True,
    }


def child(args):
    binding, protocol = checked_binding(args.binding, args.sha256, args.out, git_check=False)
    platform.uname()
    denials = []

    def guard(event, values):
        if event in {
            "subprocess.Popen",
            "os.system",
            "os.exec",
            "os.posix_spawn",
            "socket.__new__",
            "socket.connect",
            "socket.bind",
            "socket.getaddrinfo",
            "socket.gethostbyname",
        }:
            denials.append(event)
            raise RuntimeError("offline phase denied network or external execution")

    sys.addaudithook(guard)
    sys.path[:0] = [str(PROJECT), str(PROJECT / "tests")]
    status, reason, data, failure_frames = "partial", "phase_failed", {}, []
    try:
        from buddha import doctor

        origins(PROJECT, binding["sources"])
        with doctor._observation_policy(protocol["observation_policy"]):
            data = (
                build(args.out, protocol, binding["sources"])
                if args.phase == "build"
                else read(args.out, protocol, binding["sources"])
            )
        origins(PROJECT, binding["sources"])
        if denials:
            raise AssertionError("offline guard denied an external effect")
        if "study_outcome" in data:
            reason = data["study_outcome"]["reason"]
        else:
            status, reason = "complete", "phase_completed"
    except BaseException as error:
        reason = type(error).__name__ + ": " + str(error)[:400]
        failure_frames = [
            {
                "file": str(Path(frame.filename).resolve().relative_to(PROJECT)),
                "line": frame.lineno,
                "function": frame.name,
            }
            for frame in traceback.extract_tb(error.__traceback__)
            if Path(frame.filename).resolve().is_relative_to(PROJECT)
        ][-8:]
    validation_error = None
    try:
        sources_unchanged = source_snapshot(PROJECT) == binding["sources"]
    except BaseException as error:
        sources_unchanged, validation_error = False, type(error).__name__ + ": " + str(error)[:400]
    record = {
        "status": status,
        "reason": reason,
        "phase": args.phase,
        "data": data,
        "sources_unchanged": sources_unchanged,
        "validation_error": validation_error,
        "guard_denials": denials,
        "public_failure_frames": failure_frames,
    }
    record["memory"] = whole_child_peak_memory()
    record["seconds"] = time.monotonic() - PHASE_START
    if status == "complete" and not phase_passes(record, protocol):
        record.update(status="partial", reason="memory_or_source_acceptance_failed")
    write(args.out / (args.phase + "-result.json"), record)
    return 0 if record["status"] == "complete" else 3


def parent(args):
    started = time.monotonic()
    binding, protocol = checked_binding(args.binding, args.sha256, args.out)
    if os.path.lexists(args.out):
        raise ValueError("output must be absent; no retry, resume or overwrite")
    args.out.mkdir()
    (args.out / "workspace").mkdir()
    phases, reason, phase, phase_started, seconds = [], "not_started", "setup", started, 0
    env = clean_environment()
    env.update(
        TEMP=str(args.out / "workspace"),
        TMP=str(args.out / "workspace"),
        PYTHONDONTWRITEBYTECODE="1",
    )
    try:
        for phase in ("build", "read"):
            writer_remaining = remaining_seconds(
                started,
                protocol["total_seconds"]
                - protocol["reader_seconds"]
                - protocol["reporting_seconds"],
            )
            seconds = protocol["reader_seconds"] if phase == "read" else writer_remaining
            phase_started = time.monotonic()
            print(
                json.dumps({"phase": phase, "event": "starting", "remaining_seconds": seconds}),
                flush=True,
            )
            with (
                (args.out / (phase + "-stdout.log")).open("xb") as stdout,
                (args.out / (phase + "-stderr.log")).open("xb") as stderr,
            ):
                # Pinned self recipe with validated paths, passed as arguments without a shell.
                result = subprocess.run(  # nosec B603
                    [
                        sys.executable,
                        "-I",
                        "-B",
                        "-X",
                        "utf8",
                        str(PROJECT / RECIPE),
                        "--binding",
                        str(args.binding),
                        "--sha256",
                        args.sha256,
                        "--out",
                        str(args.out),
                        "--phase",
                        phase,
                    ],
                    cwd=args.out,
                    env=env,
                    stdout=stdout,
                    stderr=stderr,
                    timeout=seconds,
                )
            path = args.out / (phase + "-result.json")
            record = load(path) if path.is_file() else {}
            phases.append(
                {
                    "phase": phase,
                    "seconds": time.monotonic() - phase_started,
                    "deadline_seconds": seconds,
                    "timeout": False,
                    "exit_code": result.returncode,
                    "result_sha256": sha(path) if path.is_file() else None,
                }
            )
            if result.returncode != 0 or not phase_passes(record, protocol):
                raise ValueError(
                    "incomplete "
                    + phase
                    + ": "
                    + str(record.get("reason", "terminal record unavailable"))
                )
            checked_binding(args.binding, args.sha256, args.out)
            remaining_seconds(started, protocol["total_seconds"])
        reason = "complete_capacity_and_fresh_inspection"
    except subprocess.TimeoutExpired:
        phases.append(
            {
                "phase": phase,
                "seconds": time.monotonic() - phase_started,
                "deadline_seconds": seconds,
                "timeout": True,
                "exit_code": None,
                "result_sha256": None,
            }
        )
        reason = "deadline_exceeded; child terminal evidence may be unavailable"
    except BaseException as error:
        reason = type(error).__name__ + ": " + str(error)[:400]
    validation_error = None
    try:
        checked_binding(args.binding, args.sha256, args.out)
        sources_unchanged = True
    except (ValueError, OSError, subprocess.SubprocessError) as error:
        sources_unchanged, validation_error = False, type(error).__name__ + ": " + str(error)[:400]
        if reason == "complete_capacity_and_fresh_inspection":
            reason = "final_source_or_git_check_failed"
    deadline_exceeded = time.monotonic() - started >= protocol["total_seconds"]
    if deadline_exceeded and reason == "complete_capacity_and_fresh_inspection":
        reason = "shared_total_deadline_exceeded"
    record = {
        "format": "buddha.forward-capacity-observation.v1",
        "status": "complete" if reason == "complete_capacity_and_fresh_inspection" else "partial",
        "reason": reason,
        "phase": phase,
        "seconds": time.monotonic() - started,
        "total_limit_seconds": protocol["total_seconds"],
        "writer_limit_seconds": protocol["total_seconds"]
        - protocol["reader_seconds"]
        - protocol["reporting_seconds"],
        "reader_limit_seconds": protocol["reader_seconds"],
        "reporting_reserved_seconds": protocol["reporting_seconds"],
        "total_deadline_exceeded": deadline_exceeded,
        "phases": phases,
        "binding_sha256": args.sha256,
        "sources_unchanged": sources_unchanged,
        "validation_error": validation_error,
        "retained_workspace": str(args.out / "workspace"),
        "automatic_retry_resume_extension": False,
        "paid_execution_cleared": False,
        "no_model_or_container_execution": True,
        "python": sys.executable,
        "version": sys.version,
    }
    record["logs"] = {path.name: sha(path) for path in args.out.glob("*.log")}
    write(args.out / "result.json", record)
    print(json.dumps(record), flush=True)
    return 0 if record["status"] == "complete" else 3


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--binding", type=Path, required=True)
    parser.add_argument("--sha256", required=True)
    parser.add_argument("--out", type=Path, required=True)
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument("--check", action="store_true")
    mode.add_argument("--execute", action="store_true")
    parser.add_argument("--phase", choices=("build", "read"), help=argparse.SUPPRESS)
    args = parser.parse_args(argv)
    try:
        if args.phase:
            return child(args)
        if args.execute:
            if os.name != "nt":
                raise ValueError("this measured peak-working-set protocol requires Windows")
            return parent(args)
        checked_binding(args.binding, args.sha256, args.out)
        if os.path.lexists(args.out):
            raise ValueError("output is already present")
        print(
            json.dumps(
                {
                    "status": "checked",
                    "workload_children": 0,
                    "files_written": 0,
                    "execution_authorized": False,
                }
            )
        )
        return 0
    except (
        ValueError,
        TypeError,
        KeyError,
        OSError,
        RecursionError,
        OverflowError,
        subprocess.SubprocessError,
    ) as error:
        print(
            json.dumps(
                {"status": "stopped", "reason": type(error).__name__ + ": " + str(error)[:400]}
            )
        )
        return 2


PHASE_START = time.monotonic()
if __name__ == "__main__":
    raise SystemExit(main())
