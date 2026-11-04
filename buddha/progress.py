"""Best-effort, read-only console observation, separate from frozen execution code.

Only aggregate accounting reaches the console. A saved completion marker is a
local consistency check, not independent scientific verification of the results.
Observer failures never change execution, request retries, or ledger state.
"""

import math
import sys
import threading
import time
from pathlib import Path
from types import TracebackType
from typing import TextIO, cast

from buddha.history import _plain


def snapshot(directory: Path, *, authorization: Path | None = None) -> dict[str, object]:
    """Project read-only observations; readable accounting never proves a writer."""
    from buddha.doctor import observe

    observed = observe(directory, authorization=authorization)
    accounting = observed["accounting"]
    result: dict[str, object] = {
        "status": observed["status"],
        "completed_count": None,
        "reserved_count": None,
        "dispatched_count": None,
        "pending_count": None,
        "unknown_count": None,
        "operation_count": None,
        "spent_microusd": None,
        "held_microusd": None,
        "budget_microusd": None,
        "candidate_count": observed["candidate_count"],
        "lock": observed["lock"],
        "writer": observed["writer"],
        "completion": observed["completion"],
    }
    if not isinstance(accounting, dict):
        if observed["status"] == "unavailable":
            try:
                root = Path(directory).absolute()
                _plain(root)
                for name in ("operations.sqlite3", "context.json"):
                    try:
                        (root / name).lstat()
                        break
                    except FileNotFoundError:
                        continue
                else:
                    result["status"] = "waiting"
            except FileNotFoundError:
                result["status"] = "waiting"
            except (OSError, ValueError):
                pass
        return result
    result.update(
        completed_count=accounting["completed_count"],
        reserved_count=accounting["reserved_count"],
        dispatched_count=accounting["dispatched_count"],
        pending_count=accounting["reserved_count"] + accounting["dispatched_count"],
        unknown_count=accounting["unknown_count"],
        operation_count=accounting["operation_count"],
        spent_microusd=accounting["spent_microusd"],
        held_microusd=accounting["reserved_microusd"],
        budget_microusd=accounting["budget_microusd"],
    )
    if observed["needs_review"]:
        result["status"] = "needs_review"
    elif cast(dict[str, object], observed["completion"])["status"] == "stored_completion_observed":
        result["status"] = "complete"
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
        authorization: Path | None = None,
    ) -> None:
        self.directory = Path(directory)
        self.stream = sys.stderr if stream is None else stream
        self.poll_seconds = _interval(poll_seconds)
        self.heartbeat_seconds = _interval(heartbeat_seconds)
        self.authorization = authorization
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
            current = snapshot(self.directory, authorization=self.authorization)
        except Exception:
            current = {"status": "unavailable"}
        now = time.monotonic()
        changed = current != self._last
        if initial or changed or now - self._emitted >= self.heartbeat_seconds:
            if current["status"] in {"unavailable", "busy_or_changing", "unsupported"}:
                message = "Progress data temporarily unavailable; waiting for next update."
            elif current["status"] == "waiting":
                message = "Waiting for run ledger; still waiting for next update."
            else:
                recorded = "already recorded" if initial else "recorded"
                spent = cast(int, current["spent_microusd"]) / 1_000_000
                held = cast(int, current["held_microusd"]) / 1_000_000
                cap = current["budget_microusd"]
                cap_text = (
                    "per-stage caps" if cap is None else f"cap ${cast(int, cap) / 1_000_000:.6f}"
                )
                message = (
                    f"Progress: {current['completed_count']} API replies {recorded}; "
                    f"{current['pending_count']} pending; {current['unknown_count']} unknown; "
                    f"recorded cost ${spent:.6f}; held ${held:.6f}; {cap_text}; "
                    f"{current['candidate_count']} candidate evaluations published."
                )
                message += " Writer identity unknown."
                if not changed and not initial:
                    message += " Still waiting for next update."
                if current["status"] == "needs_review":
                    message += " Recorded state needs review; reservations stay held."
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
        current: dict[str, object] = {"status": "unavailable"}
        try:
            current = self._observe()
        except Exception:
            self._write("Progress data temporarily unavailable; execution continues.")
        self._write(
            "Run stopped; check error output."
            if exc_type is not None
            else "Run complete (saved local completion record)."
            if current["status"] == "complete"
            else "Execution returned; saved completion not observed."
        )


def watch_run(
    directory: Path,
    *,
    stream: TextIO | None = None,
    poll_seconds: float = 1.0,
    heartbeat_seconds: float = 10.0,
    authorization: Path | None = None,
) -> dict[str, object]:
    """Watch an existing run without credentials, provider calls, or ledger writes."""
    progress = Progress(
        directory,
        stream=stream,
        poll_seconds=poll_seconds,
        heartbeat_seconds=heartbeat_seconds,
        authorization=authorization,
    )
    initial = True
    while True:
        current = progress._observe(initial=initial)
        initial = False
        if current["status"] in {"complete", "needs_review"}:
            progress._write(
                "Run complete (saved local completion record)."
                if current["status"] == "complete"
                else "Watch stopped: recorded state needs review; reservations stay held."
            )
            return current
        time.sleep(progress.poll_seconds)
