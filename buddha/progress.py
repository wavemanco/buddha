"""Best-effort, read-only console observation, separate from frozen execution code.

Only aggregate accounting reaches the console. A saved completion marker is a
local consistency check, not independent scientific verification of the results.
Observer failures never change execution, request retries, or ledger state.
"""

import hashlib
import json
import math
import sqlite3
import sys
import threading
import time
from contextlib import closing
from pathlib import Path
from types import TracebackType
from typing import TextIO, cast


def _canonical(value: object) -> bytes:
    return json.dumps(
        value, sort_keys=True, separators=(",", ":"), ensure_ascii=True, allow_nan=False
    ).encode("utf-8")


def _object(pairs: list[tuple[str, object]]) -> dict[str, object]:
    result: dict[str, object] = {}
    for key, value in pairs:
        if key in result:
            raise ValueError("duplicate metadata field")
        result[key] = value
    return result


def _read(path: Path, *, checksummed: bool = False) -> dict[str, object]:
    with path.open("rb") as stream:
        raw = stream.read(4_000_001)
    if len(raw) > 4_000_000:
        raise ValueError("progress metadata exceeds limit")
    value = json.loads(raw.decode("utf-8"), object_pairs_hook=_object)
    if not isinstance(value, dict):
        raise ValueError("progress metadata must be an object")
    result = cast(dict[str, object], value)
    if checksummed:
        checksum = result.pop("record_sha256", None)
        if checksum != hashlib.sha256(_canonical(result)).hexdigest():
            raise ValueError("progress metadata checksum differs")
    return result


def _amount(value: object) -> int:
    if type(value) is not int or value < 0:
        raise ValueError("invalid progress accounting")
    return value


def _manifest(directory: Path, run_id: object, manifest_hash: object) -> dict[str, object]:
    manifest = _read(directory / "manifest.json")
    if "record_sha256" in manifest:
        checksum = manifest.pop("record_sha256")
        if checksum != hashlib.sha256(_canonical(manifest)).hexdigest():
            raise ValueError("manifest checksum differs")
    if (
        manifest.get("run_id") != run_id
        or hashlib.sha256(_canonical(manifest)).hexdigest() != manifest_hash
    ):
        raise ValueError("manifest differs from observed ledger")
    return manifest


def _published(directory: Path, manifest: dict[str, object]) -> int:
    candidates: set[str] = set()
    for path in (directory / "decisions").glob("*.json"):
        decision = _read(path, checksummed=True)
        candidate = decision.get("candidate_id")
        if (
            decision.get("status") == "admitted"
            and decision.get("comparison_key") == manifest.get("comparison_key")
            and type(candidate) is str
            and len(candidate) == 64
            and all(character in "0123456789abcdef" for character in candidate)
        ):
            candidates.add(candidate)
    return len(candidates)


def _complete(directory: Path, manifest: dict[str, object]) -> bool:
    if manifest.get("format") in (
        "buddha.policy-search.v1",
        "buddha.policy-search-continuation.v1",
    ):
        report = _read(directory / "report.json", checksummed=True)
        report_format = (
            "buddha.policy-search-report.v1"
            if manifest["format"] == "buddha.policy-search.v1"
            else "buddha.policy-search-report.v2"
        )
        return (
            report.get("format") == report_format
            and report.get("status") == "complete"
            and report.get("run_id") == manifest.get("run_id")
            and report.get("comparison_key") == manifest.get("comparison_key")
        )
    if manifest.get("format") != "buddha.baseline.v1":
        return False
    provenance = _read(directory / "evaluation" / "provenance.json")
    checksum = provenance.pop("provenance_sha256", None)
    hashes = provenance.get("artifact_hashes")
    if (
        checksum != hashlib.sha256(_canonical(provenance)).hexdigest()
        or provenance.get("format") != "buddha.noveltybench.v1"
        or provenance.get("origin") != "buddha-local"
        or provenance.get("protocol") != manifest.get("protocol")
        or not isinstance(hashes, dict)
        or set(hashes)
        != {"generations.jsonl", "v1.1/partitions.jsonl", "v1.1/scores.jsonl", "v1.1/summary.json"}
    ):
        return False
    for name, expected in hashes.items():
        digest = hashlib.sha256()
        with (directory / "evaluation" / name).open("rb") as stream:
            while chunk := stream.read(65_536):
                digest.update(chunk)
        if digest.hexdigest() != expected:
            return False
    return True


def snapshot(directory: Path) -> dict[str, object]:
    """Read aggregate accounting without opening a writer or creating a database."""
    result: dict[str, object] = {
        "status": "waiting",
        "completed_count": 0,
        "pending_count": 0,
        "unknown_count": 0,
        "operation_count": 0,
        "spent_microusd": 0,
        "held_microusd": 0,
        "budget_microusd": None,
        "candidate_count": 0,
    }
    database = Path(directory) / "operations.sqlite3"
    if not database.is_file():
        return result
    try:
        with closing(
            sqlite3.connect(database.resolve().as_uri() + "?mode=ro", timeout=0.1, uri=True)
        ) as db:
            rows = db.execute(
                "SELECT c.run_id,c.manifest_sha256,c.budget_microusd,"
                "o.status,o.reserve_microusd,o.actual_microusd "
                "FROM run_config c LEFT JOIN operations o ON 1=1 WHERE c.singleton=1"
            )
            completed = pending = unknown = spent = held = count = 0
            run_id: object = None
            manifest_hash: object = None
            for row in rows:
                run_id, manifest_hash, budget, status, reserve, actual = row
                result["budget_microusd"] = _amount(budget)
                if status is None:
                    continue
                count += 1
                if status == "completed":
                    completed += 1
                    spent += _amount(actual)
                elif status in {"reserved", "dispatched", "unknown"}:
                    held += _amount(reserve)
                    unknown += status == "unknown"
                    pending += status != "unknown"
                else:
                    raise ValueError("unknown operation status")
            if run_id is None:
                raise ValueError("missing ledger configuration")
        result.update(
            status="needs_review" if unknown else "running",
            completed_count=completed,
            pending_count=pending,
            unknown_count=unknown,
            operation_count=count,
            spent_microusd=spent,
            held_microusd=held,
        )
        try:
            manifest = _manifest(directory, run_id, manifest_hash)
            result["candidate_count"] = _published(directory, manifest)
            if not pending and not unknown and _complete(directory, manifest):
                result["status"] = "complete"
        except (OSError, ValueError, TypeError, RecursionError):
            pass  # Completion is never inferred from receipts alone or invalid artifacts.
    except (sqlite3.Error, OSError, ValueError, TypeError, RecursionError):
        result["status"] = "unavailable"
    return result


def _interval(value: float) -> float:
    if type(value) not in (int, float) or not math.isfinite(value) or not 0 < value <= 60:
        raise ValueError("progress intervals must be finite and between 0 and 60 seconds")
    return value


class Progress:
    """Show flushed stderr updates while the calling thread executes a run."""

    def __init__(
        self,
        directory: Path,
        *,
        stream: TextIO | None = None,
        poll_seconds: float = 1.0,
        heartbeat_seconds: float = 10.0,
    ) -> None:
        self.directory = Path(directory)
        self.stream = sys.stderr if stream is None else stream
        self.poll_seconds = _interval(poll_seconds)
        self.heartbeat_seconds = _interval(heartbeat_seconds)
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None
        self._enabled = True
        self._started = time.monotonic()
        self._last: dict[str, object] | None = None
        self._emitted = 0.0

    def _write(self, message: str) -> None:
        if self._enabled:
            elapsed = int(time.monotonic() - self._started)
            try:
                self.stream.write(f"[{elapsed // 60:02d}:{elapsed % 60:02d}] {message}\n")
                self.stream.flush()
            except Exception:
                self._enabled = False

    def _observe(self, *, initial: bool = False) -> dict[str, object]:
        try:
            current = snapshot(self.directory)
        except Exception:
            current = {"status": "unavailable"}
        now = time.monotonic()
        changed = current != self._last
        if initial or changed or now - self._emitted >= self.heartbeat_seconds:
            if current["status"] == "unavailable":
                message = "Progress data temporarily unavailable; waiting for next update."
            elif current["status"] == "waiting":
                message = "Waiting for run ledger; still waiting for next update."
            else:
                recorded = "already recorded" if initial else "recorded"
                spent = cast(int, current["spent_microusd"]) / 1_000_000
                held = cast(int, current["held_microusd"]) / 1_000_000
                cap = cast(int, current["budget_microusd"]) / 1_000_000
                message = (
                    f"Progress: {current['completed_count']} API replies {recorded}; "
                    f"{current['pending_count']} pending; {current['unknown_count']} unknown; "
                    f"recorded cost ${spent:.6f}; held ${held:.6f}; cap ${cap:.6f}; "
                    f"{current['candidate_count']} candidate evaluations published."
                )
                if not changed and not initial:
                    message += " Still waiting for next update."
                if current["status"] == "needs_review":
                    message += " Uncertain provider outcome needs review; reservation stays held."
            self._write(message)
            self._emitted = now
        self._last = current
        return current

    def _worker(self) -> None:
        while not self._stop.wait(self.poll_seconds):
            try:
                self._observe()
            except Exception:
                self._write("Progress data temporarily unavailable; waiting for next update.")

    def __enter__(self) -> "Progress":
        self._started = time.monotonic()
        self._observe(initial=True)
        try:
            self._thread = threading.Thread(
                target=self._worker, name="buddha-progress", daemon=True
            )
            self._thread.start()
        except Exception:
            self._write("Progress observer unavailable; execution continues.")
        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc_value: BaseException | None,
        traceback: TracebackType | None,
    ) -> None:
        self._stop.set()
        if self._thread is not None and self._thread.is_alive():
            self._thread.join(timeout=0.5)
        try:
            self._observe()
        except Exception:
            self._write("Progress data temporarily unavailable; execution continues.")
        self._write("Run complete." if exc_type is None else "Run stopped; check error output.")


def watch_run(
    directory: Path,
    *,
    stream: TextIO | None = None,
    poll_seconds: float = 1.0,
    heartbeat_seconds: float = 10.0,
) -> dict[str, object]:
    """Watch an existing run without credentials, provider calls, or ledger writes."""
    progress = Progress(
        directory, stream=stream, poll_seconds=poll_seconds, heartbeat_seconds=heartbeat_seconds
    )
    initial = True
    while True:
        current = progress._observe(initial=initial)
        initial = False
        if current["status"] in {"complete", "needs_review"}:
            progress._write(
                "Run complete (saved local completion record)."
                if current["status"] == "complete"
                else "Watch stopped: uncertain provider outcome needs review."
            )
            return current
        time.sleep(progress.poll_seconds)
