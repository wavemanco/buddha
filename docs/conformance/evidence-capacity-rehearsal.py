"""Rehearse a finite opaque storage envelope; never execute an experiment.

Run with --workspace and a NEW --output below its runs/checks directory.
Without --materialize, print exact proposed counts, bytes and the layout hash;
this creates nothing. --materialize creates and retains the opaque fixture,
then checks every byte through the bounded capture and adoption primitives.
Neither mode reads study contents, opens SQLite, calls providers or containers.
Runs once. Ctrl+C retains partial output. Progress prints every ten seconds.
The fixture is retained for review; this script never deletes any directory.
"""

import argparse
import hashlib
import json
import os
import shutil
import sys
import threading
import time
from contextlib import contextmanager
from pathlib import Path, PurePosixPath

if __package__ is None:
    sys.path.insert(0, str(Path(__file__).absolute().parents[2]))

from buddha.doctor import _Capture, _observation_policy
from buddha.launch_common import _stop_reason
from buddha.releases import _paths
from buddha.search_evidence import _absolute

MIB = 1024**2
GIB = 1024**3
POLICY = {
    "format": "buddha.evidence-observation-policy.v2",
    "max_total_bytes": 32 * GIB,
    "max_tree_entries": 100_000,
    "max_consumed_paths": 65_536,
    "max_resident_bytes": 0,
}


def canonical(value):
    return json.dumps(value, sort_keys=True, separators=(",", ":")).encode("utf-8")


def digest(value):
    return hashlib.sha256(canonical(value)).hexdigest()


def layout():
    files, directories, owners = {}, set(), set()
    unit_bases = []

    def directory(name):
        path = PurePosixPath(name)
        for parent in (path, *path.parents):
            if str(parent) != ".":
                directories.add(str(parent))

    def file(name, size=0):
        if name in files and files[name] != size:
            raise ValueError("conflicting opaque layout file")
        files[name] = size
        parent = str(PurePosixPath(name).parent)
        if parent != ".":
            directory(parent)

    def owner(stage, index, native=False):
        key = stage + "/owners/" + str(index)
        if key in owners:
            raise ValueError("duplicate actual-owner topology")
        owners.add(key)
        file(key + "/manifest.json")
        file(key + "/operations.sqlite3")
        file(stage + "/context.json")
        file(stage + "/report.json")
        file(stage + "/completed/" + str(index) + ".json")
        file(stage + "/observations/0.json")
        if native:
            file(stage + "/command-" + str(index) + ".json")
            file(stage + "/staging/" + str(index) + "/input.bin")
        for attempt in range(2):
            prefix = stage + "/attempts/" + str(index) + "-" + str(attempt)
            file(prefix + "/report.json")
            if native:
                file(prefix + "/imports-ready.json")
                file(prefix + "/imports-final.json")
                file(prefix + "/artifacts/output.bin")
            else:
                for name in ("report.json", "answers.json", "done.json"):
                    file(prefix + "/session/" + name)

    def pad(prefix, file_count, directory_count):
        current_files = sum(name.startswith(prefix + "/") for name in files)
        current_dirs = sum(name == prefix or name.startswith(prefix + "/") for name in directories)
        if current_files > file_count or current_dirs > directory_count:
            raise ValueError("normal topology exceeds its declared count quota")
        for index in range(file_count - current_files):
            file(prefix + "/capacity-file-" + str(index) + ".bin")
        for index in range(directory_count - current_dirs):
            directory(prefix + "/capacity-dir-" + str(index))

    def assessment(prefix, actual_owners=True):
        directory(prefix)
        if actual_owners:
            owner(prefix + "/generation", 0)
            for stage in range(1, 4):
                owner(prefix + "/evaluation", stage, native=True)
        for name in ("task.json", "generation.json", "evaluation.json", "native-answers.jsonl"):
            file(prefix + "/" + name)
        for role, size in (
            ("generation", 4 * MIB),
            ("native-1", 12 * MIB),
            ("native-2", 12 * MIB),
            ("native-3", 12 * MIB),
            ("shared", 12 * MIB),
        ):
            file(prefix + "/capacity-" + role + ".bin", size)
        unit_bases.append(
            {
                "files": sum(name.startswith(prefix + "/") for name in files),
                "directories": sum(
                    name == prefix or name.startswith(prefix + "/") for name in directories
                ),
            }
        )
        # Two 45-file/32-directory geometry quotas include the extra attempt.
        pad(prefix, 90, 64)

    def standalone(prefix):
        directory(prefix)
        owner(prefix, 0)
        file(prefix + "/capacity-role.bin", 4 * MIB)
        pad(prefix, 16, 12)

    for start in range(2):
        for repetition in range(2):
            common = "trial/search/study/common/" + str(start) + "/" + str(repetition)
            for task in range(3):
                assessment(common + "/screen/tasks/" + str(task))
            for role in ("proposal", "generation"):
                standalone(common + "/witness/" + role)
            for arm in range(2):
                for slot in range(2):
                    cell = "trial/search/study/cells/" + "/".join(
                        map(str, (start, repetition, arm, slot))
                    )
                    standalone(cell + "/proposal")
                    for task in range(3):
                        assessment(cell + "/screen/tasks/" + str(task))
                    for role in ("proposal", "generation"):
                        standalone(cell + "/witness/" + role)
    for arm in range(12):
        for task in range(26):
            assessment("trial/final/arms/" + str(arm) + "/tasks/" + str(task) + "/repetitions/0")
    for mode in ("regenerate", "in-context"):
        prefix = "plain/" + mode
        for stage in range(4):
            owner(prefix, stage, native=stage > 0)
        for task in range(26):
            # Plain tasks share four owners per mode. These are storage proxies.
            assessment(prefix + "/task-envelopes/" + str(task), actual_owners=False)
    if len(owners) != 1552 or len(unit_bases) != 424:
        raise ValueError("full-workload owner or task-proxy arithmetic differs")
    # Exactly 3,723 opaque entries represent the retained prefix, without copying it.
    for index in range(3722):
        file("retained-prefix/" + str(index) + ".bin", 16 * MIB if index < 80 else 0)
    for index in range(64):
        file("capacity-shared/" + str(index) + ".bin", 16 * MIB)
    for name in ("definition.json", "context.json", "funding.json", "freeze/schedule.json"):
        file("trial/" + name)
    for index in range(48_000 - len(files)):
        file("capacity-padding/file-" + str(index) + ".bin")
    for index in range(81_920 - len(files) - len(directories)):
        directory("capacity-padding/dir-" + str(index))
    _paths(list(files))
    if (
        len(files) != 48_000
        or len(files) + len(directories) != 81_920
        or sum(files.values()) != 24 * GIB
        or max(files.values()) > 32 * MIB
        or set(files) & directories
    ):
        raise ValueError("opaque envelope exceeds or differs from its declared layout")
    manifest = {"directories": sorted(directories), "files": dict(sorted(files.items()))}
    summary = {
        "format": "buddha.opaque-capacity-layout.v1",
        "policy": POLICY,
        "owner_counts": {"development": 296, "final": 1248, "plain_shared": 8, "total": 1552},
        "task_proxy_counts": {"development": 60, "final": 312, "plain": 52, "total": 424},
        "tree_entries": 81_920,
        "regular_files": 48_000,
        "directories": len(directories),
        "logical_bytes": sum(files.values()),
        "largest_file_bytes": max(files.values()),
        "prior_prefix_opaque_entries": 3723,
        "prior_prefix_allowance_bytes": 1280 * MIB,
        "other_shared_reserve_bytes": GIB,
        "largest_unpadded_assessment_files": max(row["files"] for row in unit_bases),
        "largest_unpadded_assessment_directories": max(row["directories"] for row in unit_bases),
        "layout_sha256": digest(manifest),
        "scope": (
            "Finite raw-capture stress envelope, not valid study records or a universal run bound."
        ),
        "attempt_scope": "One additional attempt tree per actual owner is inside the fixed quotas.",
    }
    return manifest, summary


def exclusive_json(path, value):
    with path.open("xb") as stream:
        stream.write(canonical(value) + b"\n")
        stream.flush()
        os.fsync(stream.fileno())


@contextmanager
def progress(state):
    stop = threading.Event()
    started = time.monotonic()

    def tick():
        while not stop.wait(10):
            print(
                "[capacity-opaque] "
                + json.dumps({"elapsed_seconds": round(time.monotonic() - started, 1), **state}),
                file=sys.stderr,
                flush=True,
            )

    thread = threading.Thread(target=tick, daemon=True)
    thread.start()
    try:
        yield
    finally:
        stop.set()
        thread.join(timeout=0.5)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--workspace", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--materialize", action="store_true")
    args = parser.parse_args()
    workspace = _absolute(str(args.workspace))
    output_parent = _absolute(str(args.output.parent))
    _paths([args.output.name])
    output = output_parent / args.output.name
    parent = workspace / "runs/checks"
    if (
        not Path(__file__).absolute().is_relative_to(workspace)
        or output.parent != parent
        or not output.name.startswith("evidence-capacity-opaque-")
        or output.exists()
        or not parent.is_dir()
    ):
        raise ValueError("opaque output must be a new dedicated workspace runs/checks child")
    manifest, summary = layout()
    free = shutil.disk_usage(parent).free
    summary |= {"output": str(output), "free_bytes_before": free, "required_free_bytes": 30 * GIB}
    summary["source_sha256"] = {
        str(path): hashlib.sha256(path.read_bytes()).hexdigest()
        for path in (Path(__file__).absolute(), Path(sys.modules[_Capture.__module__].__file__))
    }
    if free < 30 * GIB:
        raise ValueError("opaque materialization needs its 24 GiB plus 6 GiB free headroom")
    if not args.materialize:
        print(json.dumps({"status": "planned", **summary}), flush=True)
        return 0
    output.mkdir()
    fixture = output / "fixture"
    fixture.mkdir()
    exclusive_json(output / "ownership.json", {"format": "buddha.opaque-owned.v1", **summary})
    exclusive_json(output / "plan.json", manifest)
    state = {"phase": "directories", "files": 0, "bytes": 0}
    try:
        with progress(state):
            for name in sorted(
                manifest["directories"], key=lambda value: (value.count("/"), value)
            ):
                (fixture / name).mkdir()
            state["phase"] = "materialize"
            block = bytes(MIB)
            for name, size in manifest["files"].items():
                with (fixture / name).open("xb") as stream:
                    remaining = size
                    while remaining:
                        written = stream.write(block[: min(remaining, len(block))])
                        if not written:
                            raise OSError("opaque write did not advance")
                        remaining -= written
                        state["bytes"] += written
                    if size:
                        stream.flush()
                        os.fsync(stream.fileno())
                state["files"] += 1
            exclusive_json(output / "materialized.json", {"status": "materialized", **summary})
            state.update(phase="capture", files=0, bytes=0)
            with _observation_policy(POLICY):
                source, target = _Capture(fixture), _Capture(fixture)
            expected = {
                size: hashlib.sha256(bytes(size)).hexdigest()
                for size in set(manifest["files"].values())
            }
            for name, size in manifest["files"].items():
                path = fixture / name
                raw = (
                    source.database(path)
                    if name.endswith("/operations.sqlite3")
                    else source.read(path)
                )
                if len(raw) != size or hashlib.sha256(raw).hexdigest() != expected[size]:
                    raise ValueError("opaque bytes differ from the declared envelope")
                state["files"] += 1
                state["bytes"] += size
            state["phase"] = "adopt"
            target.adopt(source)
            state["phase"] = "finish"
            fingerprints = target.finish()
            if len(fingerprints) != 48_000 or target.total != 24 * GIB:
                raise ValueError("opaque capture did not preserve complete declared coverage")
            result = {
                "status": "complete",
                **summary,
                "consumed_bytes": target.total,
                "fingerprints": len(fingerprints),
            }
            exclusive_json(output / "result.json", result)
        print(json.dumps(result), flush=True)
        return 0
    except (Exception, KeyboardInterrupt) as error:
        stopped = {
            "status": "partial",
            "reason": "cancelled" if isinstance(error, KeyboardInterrupt) else _stop_reason(error),
            "error_type": type(error).__name__,
            **state,
        }
        exclusive_json(output / "partial.json", stopped)
        print(json.dumps(stopped), flush=True)
        return 130 if isinstance(error, KeyboardInterrupt) else 2


if __name__ == "__main__":
    raise SystemExit(main())
