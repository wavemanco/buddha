"""Partition the complete ordinary unittest census without changing test semantics."""

import argparse
import hashlib
import json
import math
import os
import signal

# Launch only this same trusted helper with the active interpreter, without a shell.
import subprocess  # nosec B404
import sys
import tempfile
import time
import unittest
from functools import partial
from pathlib import Path
from typing import Any, BinaryIO

if sys.platform == "win32":

    class _WindowsJob:
        """Contain the gated worker and its descendants before any discovery runs."""

        def __init__(self) -> None:
            import ctypes
            from ctypes import wintypes

            class Basic(ctypes.Structure):
                _fields_ = [
                    ("process_time", ctypes.c_longlong),
                    ("job_time", ctypes.c_longlong),
                    ("flags", wintypes.DWORD),
                    ("minimum", ctypes.c_size_t),
                    ("maximum", ctypes.c_size_t),
                    ("processes", wintypes.DWORD),
                    ("affinity", ctypes.c_size_t),
                    ("priority", wintypes.DWORD),
                    ("scheduling", wintypes.DWORD),
                ]

            class Extended(ctypes.Structure):
                _fields_ = [
                    ("basic", Basic),
                    ("io", ctypes.c_ulonglong * 6),
                    ("process_memory", ctypes.c_size_t),
                    ("job_memory", ctypes.c_size_t),
                    ("peak_process_memory", ctypes.c_size_t),
                    ("peak_job_memory", ctypes.c_size_t),
                ]

            self.kernel = ctypes.WinDLL("kernel32", use_last_error=True)
            for name, arguments, result in (
                ("CreateJobObjectW", [ctypes.c_void_p, wintypes.LPCWSTR], wintypes.HANDLE),
                (
                    "SetInformationJobObject",
                    [wintypes.HANDLE, ctypes.c_int, ctypes.c_void_p, wintypes.DWORD],
                    wintypes.BOOL,
                ),
                ("OpenProcess", [wintypes.DWORD, wintypes.BOOL, wintypes.DWORD], wintypes.HANDLE),
                ("AssignProcessToJobObject", [wintypes.HANDLE, wintypes.HANDLE], wintypes.BOOL),
                ("TerminateJobObject", [wintypes.HANDLE, wintypes.UINT], wintypes.BOOL),
                ("CloseHandle", [wintypes.HANDLE], wintypes.BOOL),
            ):
                function = getattr(self.kernel, name)
                function.argtypes, function.restype = arguments, result
            self.handle = self.kernel.CreateJobObjectW(None, None)
            if not self.handle:
                raise ctypes.WinError(ctypes.get_last_error())
            limits = Extended()
            limits.basic.flags = 0x2000  # JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE.
            if not self.kernel.SetInformationJobObject(
                self.handle, 9, ctypes.byref(limits), ctypes.sizeof(limits)
            ):
                self.kernel.CloseHandle(self.handle)
                raise ctypes.WinError(ctypes.get_last_error())

        def assign(self, process: subprocess.Popen[bytes]) -> None:
            import ctypes

            handle = self.kernel.OpenProcess(0x0101, False, process.pid)
            if not handle:
                raise ctypes.WinError(ctypes.get_last_error())
            try:
                if not self.kernel.AssignProcessToJobObject(self.handle, handle):
                    raise ctypes.WinError(ctypes.get_last_error())
            finally:
                self.kernel.CloseHandle(handle)

        def close(self) -> None:
            import ctypes

            try:
                if not self.kernel.TerminateJobObject(self.handle, 1):
                    raise ctypes.WinError(ctypes.get_last_error())
            finally:
                if not self.kernel.CloseHandle(self.handle):
                    raise ctypes.WinError(ctypes.get_last_error())


class _Progress:
    def __init__(self, path: Path) -> None:
        self.stream = path.open("ab", buffering=0)
        self.sequence = 0

    def record(self, test: unittest.TestCase, kind: str) -> None:
        self.sequence += 1
        raw = (
            json.dumps(
                {
                    "sequence": self.sequence,
                    "kind": kind,
                    "test_id": test.id(),
                    "time_ns": time.monotonic_ns(),
                }
            ).encode()
            + b"\n"
        )
        while raw:
            written = self.stream.write(raw)
            if not written:
                raise OSError("test progress channel made no write progress")
            raw = raw[written:]


class _ProgressResult(unittest.TextTestResult):
    def __init__(self, *args: Any, progress: _Progress, **kwargs: Any) -> None:
        super().__init__(*args, **kwargs)
        self.progress = progress

    def startTest(self, test: unittest.TestCase) -> None:
        super().startTest(test)
        self.progress.record(test, "start")

    def addSuccess(self, test: unittest.TestCase) -> None:
        super().addSuccess(test)
        self.progress.record(test, "success")

    def addFailure(self, test: unittest.TestCase, err: Any) -> None:
        super().addFailure(test, err)
        self.progress.record(test, "failure")

    def addError(self, test: unittest.TestCase, err: Any) -> None:
        super().addError(test, err)
        self.progress.record(test, "error")

    def addSkip(self, test: unittest.TestCase, reason: str) -> None:
        super().addSkip(test, reason)
        self.progress.record(test, "skip")

    def addExpectedFailure(self, test: unittest.TestCase, err: Any) -> None:
        super().addExpectedFailure(test, err)
        self.progress.record(test, "expected_failure")

    def addUnexpectedSuccess(self, test: unittest.TestCase) -> None:
        super().addUnexpectedSuccess(test)
        self.progress.record(test, "unexpected_success")

    def addSubTest(self, test: unittest.TestCase, subtest: unittest.TestCase, err: Any) -> None:
        super().addSubTest(test, subtest, err)
        self.progress.record(test, "subtest_success" if err is None else "subtest_failure")


class _ProgressReader:
    def __init__(self, started: int) -> None:
        self.last_progress = self.last_event = started
        self.sequence = self.completed = 0
        self.pending = b""
        self.current: str | None = None

    def read(self, stream: BinaryIO) -> None:
        kinds = {
            "start",
            "success",
            "failure",
            "error",
            "skip",
            "expected_failure",
            "unexpected_success",
            "subtest_success",
            "subtest_failure",
        }
        while chunk := stream.read(65536):
            lines = (self.pending + chunk).split(b"\n")
            self.pending = lines.pop()
            if len(self.pending) > 65536:
                raise ValueError("test progress record is too large")
            for line in lines:
                value = json.loads(line)
                if (
                    type(value) is not dict
                    or set(value) != {"sequence", "kind", "test_id", "time_ns"}
                    or type(value["sequence"]) is not int
                    or value["sequence"] != self.sequence + 1
                    or type(value["kind"]) is not str
                    or value["kind"] not in kinds
                    or type(value["test_id"]) is not str
                    or not value["test_id"]
                    or type(value["time_ns"]) is not int
                    or not self.last_event <= value["time_ns"] <= time.monotonic_ns()
                ):
                    raise ValueError("invalid test progress record")
                self.sequence = value["sequence"]
                self.last_event = value["time_ns"]
                self.current = value["test_id"]
                if value["kind"] != "start":
                    self.last_progress = value["time_ns"]
                    self.completed += 1
                    print(
                        json.dumps({"format": "buddha.ci-test-progress.v1", **value}),
                        file=sys.stderr,
                        flush=True,
                    )


def _terminal_bytes(args: argparse.Namespace, code: int) -> bytes:
    return json.dumps(
        {
            "format": "buddha.ci-test-shard-terminal.v1",
            "count": args.count,
            "index": args.index,
            "isolate": args.isolate,
            "mode": "inventory" if args.list_only else "tests",
            "idle_seconds": float(args.idle_seconds),
            "exit_code": code,
        },
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    ).encode()


def _watch(args: argparse.Namespace) -> int:
    with tempfile.TemporaryDirectory(prefix="buddha-ci-watchdog-") as temporary:
        directory = Path(temporary)
        channel = directory / "progress.jsonl"
        channel.touch()
        command = [
            sys.executable,
            str(Path(__file__).resolve()),
            "--count",
            str(args.count),
            "--index",
            str(args.index),
            "--idle-seconds",
            str(args.idle_seconds),
            "--_worker",
            temporary,
        ]
        if args.isolate is not None:
            command.extend(["--isolate", args.isolate])
        if args.list_only:
            command.append("--list-only")
        if sys.platform == "win32":
            job = _WindowsJob()
        else:
            job = None
        process: subprocess.Popen[bytes] | None = None
        started = time.monotonic_ns()
        progress = _ProgressReader(started)
        reason: str | None = None
        code = 125
        assigned = False
        try:
            process = subprocess.Popen(command, start_new_session=sys.platform != "win32")  # nosec B603
            if job is not None:
                job.assign(process)
                assigned = True
            (directory / "start").touch()
            with channel.open("rb", buffering=0) as stream:
                while True:
                    progress.read(stream)
                    if (
                        time.monotonic_ns() - progress.last_progress
                        >= args.idle_seconds * 1_000_000_000
                    ):
                        reason, code = "no_genuine_test_progress", 124
                        break
                    # WNOWAIT retains the POSIX leader's identity until group cleanup.
                    if sys.platform == "win32":
                        finished = process.poll() is not None
                    else:
                        finished = (
                            os.waitid(os.P_PID, process.pid, os.WEXITED | os.WNOHANG | os.WNOWAIT)
                            is not None
                        )
                    if finished:
                        progress.read(stream)
                        if progress.pending:
                            raise ValueError("unfinished test progress record")
                        break
                    time.sleep(min(0.05, args.idle_seconds / 10))
        except KeyboardInterrupt:
            reason, code = "cancelled", 130
        except (OSError, ValueError):
            reason, code = "progress_or_containment_failure", 125
        finally:
            try:
                if job is not None:
                    try:
                        job.close()
                    finally:
                        if process is not None and not assigned:
                            # The unreleased gate guarantees this child has no descendants.
                            process.terminate()
                elif process is not None and sys.platform != "win32":
                    try:
                        os.killpg(process.pid, signal.SIGKILL)
                    except ProcessLookupError:
                        pass
            except OSError:
                reason, code = "process_tree_cleanup_failure", 125
            if process is not None:
                try:
                    actual = process.wait(timeout=10)
                    if reason is None:
                        code = actual
                except (OSError, subprocess.TimeoutExpired):
                    reason, code = "process_tree_cleanup_failure", 125
            if reason is None and code == 0:
                expected = _terminal_bytes(args, 0)
                try:
                    with (directory / "terminal.json").open("rb") as terminal:
                        if terminal.read(len(expected) + 1) != expected:
                            raise ValueError("terminal receipt does not match this shard")
                except (OSError, ValueError):
                    reason, code = "missing_or_invalid_terminal_receipt", 125
            if reason is not None:
                print(
                    json.dumps(
                        {
                            "format": "buddha.ci-test-watchdog.v1",
                            "status": "incomplete",
                            "reason": reason,
                            "idle_seconds": args.idle_seconds,
                            "seconds_without_progress": (
                                time.monotonic_ns() - progress.last_progress
                            )
                            / 1_000_000_000,
                            "completed_events": progress.completed,
                            "last_test_id": progress.current,
                        }
                    ),
                    file=sys.stderr,
                    flush=True,
                )
        return code


def _collect(node: object) -> list[unittest.TestCase]:
    if isinstance(node, unittest.TestSuite):
        if type(node) is not unittest.TestSuite:
            raise ValueError("custom test suites need an explicit compatibility review")
        return [case for child in node for case in _collect(child)]
    if isinstance(node, unittest.TestCase):
        return [node]
    raise ValueError("collection contains an unsupported test object")


def _partition(cases: list[unittest.TestCase], count: int, isolate: str | None) -> list[list[int]]:
    if type(count) is not int or not 1 <= count <= len(cases):
        raise ValueError("shard count must be positive and no larger than the test census")
    names = [case.id() for case in cases]
    if any(type(name) is not str or not name for name in names):
        raise ValueError("every test occurrence needs its original string identity")
    if isolate is not None and (count < 2 or names.count(isolate) != 1):
        raise ValueError("isolation requires multiple shards and exactly one matching test")
    groups: list[list[int]] = [[] for _ in range(count)]
    for ordinal, name in enumerate(names):
        digest = int.from_bytes(hashlib.sha256(name.encode()).digest())
        shard = (
            (0 if name == isolate else 1 + digest % (count - 1))
            if isolate is not None
            else digest % count
        )
        groups[shard].append(ordinal)
    if any(not group for group in groups) or sorted(
        ordinal for group in groups for ordinal in group
    ) != list(range(len(cases))):
        raise ValueError("shards must be nonempty and partition every occurrence exactly once")
    return groups


def _execute(args: argparse.Namespace, parser: argparse.ArgumentParser, progress: _Progress) -> int:
    loader = unittest.TestLoader()
    try:
        suite = loader.discover("tests")
        if loader.errors:
            raise ValueError("discovery failed:\n" + "\n".join(map(str, loader.errors)))
        cases = _collect(suite)
        groups = _partition(cases, args.count, args.isolate)
    except (ValueError, ImportError) as error:
        parser.error(str(error))
    assignments = {ordinal: shard for shard, group in enumerate(groups) for ordinal in group}
    rows = [
        {"ordinal": ordinal, "id": case.id(), "shard": assignments[ordinal]}
        for ordinal, case in enumerate(cases)
    ]
    raw = json.dumps(rows, sort_keys=True, separators=(",", ":")).encode()
    print(
        json.dumps(
            {
                "format": "buddha.ci-test-shards.v1",
                "total": len(cases),
                "count": args.count,
                "index": args.index,
                "selected": len(groups[args.index]),
                "counts": [len(group) for group in groups],
                "isolated_test": args.isolate,
                "census_sha256": hashlib.sha256(raw).hexdigest(),
            }
        ),
        flush=True,
    )
    for row in rows:
        print(json.dumps(row), flush=True)
    if args.list_only:
        return 0
    selected = unittest.TestSuite(cases[ordinal] for ordinal in groups[args.index])
    try:
        result = unittest.TextTestRunner(
            verbosity=2,
            durations=30,
            failfast=False,
            resultclass=partial(_ProgressResult, progress=progress),
        ).run(selected)
    except KeyboardInterrupt:
        return 130
    if result.shouldStop:
        print("Shard stopped before full completion.", file=sys.stderr)
    return int(not result.wasSuccessful() or result.shouldStop)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--count", type=int, required=True)
    parser.add_argument("--index", type=int, required=True)
    parser.add_argument("--isolate")
    parser.add_argument("--list-only", action="store_true")
    parser.add_argument("--idle-seconds", type=float, default=3600.0)
    parser.add_argument("--_worker", type=Path, help=argparse.SUPPRESS)
    args = parser.parse_args(argv)
    if not 0 <= args.index < args.count:
        parser.error("shard index must be between zero and count minus one")
    if not math.isfinite(args.idle_seconds) or not 0 < args.idle_seconds <= 3600:
        parser.error("idle deadline must be positive, finite and no more than 3600 seconds")
    if args._worker is None:
        return _watch(args)
    while not (args._worker / "start").is_file():
        time.sleep(0.01)
    progress = _Progress(args._worker / "progress.jsonl")
    try:
        code = _execute(args, parser, progress)
        # Only a normal runner/inventory return can create this completion receipt.
        (args._worker / "terminal.json").write_bytes(_terminal_bytes(args, code))
        return code
    finally:
        progress.stream.close()


if __name__ == "__main__":
    raise SystemExit(main())
