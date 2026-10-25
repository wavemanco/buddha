"""Shared passive launch checks and observer-only progress reporting."""

import sys
import threading
import time
from collections.abc import Callable, Iterator
from contextlib import contextmanager
from pathlib import Path
from typing import cast

from buddha import gateway
from buddha import native_pipeline as pipeline
from buddha.gateway_history import MAX_LEDGER_BYTES
from buddha.provider import ModelSpec
from buddha.releases import ReleaseError, Selection, _digest, _json, _load, _object, _root, _text
from buddha.search_evidence import _read, _sidecars, read_authority


def _path(value: object, *, error: type[ReleaseError] = ReleaseError) -> Path:
    # Leaves need not exist yet; callers separately check input reads/parents.
    path = pipeline._absolute(value)
    if str(path) != value or ".." in path.parts or str(value).startswith(("//", "\\\\")):
        raise error("launch paths must have one canonical spelling")
    return path


def _snapshot(path: Path) -> tuple[dict[str, object], bytes]:
    _sidecars(path)
    raw = _read(path, MAX_LEDGER_BYTES)
    result = read_authority(raw)
    _sidecars(path)
    return result, raw


def _finish_snapshot(path: Path, raw: bytes, *, error: type[ReleaseError] = ReleaseError) -> None:
    _sidecars(path)
    if _read(path, len(raw)) != raw:
        raise error("funding changed while checking")
    _sidecars(path)


def _notice(prefix: str, message: str) -> None:
    print("[" + prefix + "] " + message, file=sys.stderr, flush=True)


def _emit(notice: Callable[[str], None], message: str) -> None:
    try:
        notice(message)
    except Exception:
        # Observer failures must not change execution or emit a background trace.
        return


@contextmanager
def _heartbeat(
    notice: Callable[[str], None],
    phase: list[str],
    authority: list[Path | None],
    seconds: float,
    *,
    thread_name: str = "launch-progress",
) -> Iterator[None]:
    stop = threading.Event()
    started = time.monotonic()

    def accounting() -> str:
        if authority[0] is None:
            return "recorded accounting unknown"
        try:
            funding, raw = _snapshot(authority[0])
            _finish_snapshot(authority[0], raw)
            config, totals = _object(funding["config"]), _object(funding["totals"])
            return (
                f"recorded attempts {totals['operation_count']}; "
                f"recorded cost ${cast(int, totals['spent_microusd']) / 1_000_000:.6f}; "
                f"held ${cast(int, totals['reserved_microusd']) / 1_000_000:.6f}; "
                f"cap ${cast(int, config['budget_microusd']) / 1_000_000:.6f}"
            )
        except Exception:
            return "recorded accounting unavailable"

    def tick() -> None:
        while not stop.wait(seconds):
            if phase[0] != "keys":
                _emit(
                    notice,
                    f"Phase: {phase[0]}; elapsed {int(time.monotonic() - started)}s; "
                    + accounting(),
                )

    worker = threading.Thread(target=tick, name=thread_name, daemon=True)
    worker.start()
    try:
        yield
    finally:
        stop.set()
        worker.join(timeout=0.5)


def _receipt_path(path: Path, *, error: type[ReleaseError] = ReleaseError) -> Path:
    if not isinstance(path, Path):
        raise error("receipt needs an explicit new Path")
    result = _path(str(path.absolute()), error=error)
    _root(result.parent)
    if result.exists():
        raise error("receipt already exists; nothing overwritten")
    return result


def _receipt_roots(path: Path, expected_sha256: str) -> list[Path]:
    """Derive exclusions from trusted bytes before arming even a failure receipt.

    No funding/state/credential checks or writes. Only known pinned descriptor
    references are opened; other declared paths are exclusions, never reads.
    A wrong pin or malformed descriptor cannot authorize any receipt write.
    """
    references = {
        "buddha.source-launch.v1": ("proposal", "approval"),
        "buddha.policy-launch.v1": ("proposal", "approval", "execution"),
        "buddha.policy-handoff.v1": ("study", "baseline"),
        "buddha.policy-execution.v1": ("study", "baseline"),
        "buddha.improver-launch.v1": ("proposal", "approval"),
        "buddha.improver-handoff.v1": ("assessment",),
        "buddha.improver-assessment-trial.v4": (
            "development",
            "tasks",
            "custody",
            "analysis_plan",
            "improvement_rule",
        ),
    }
    path, expected_sha256 = _path(str(path.absolute())), _digest(expected_sha256)
    first = _load(pipeline._read(path, expected_sha256))
    if _text(first["format"]) not in {
        "buddha.source-launch.v1",
        "buddha.policy-launch.v1",
        "buddha.improver-launch.v1",
    }:
        raise ReleaseError("receipt exclusions require a known pinned launch")
    roots, seen = {path}, {path: expected_sha256}
    pending = [first]
    while pending:
        record = pending.pop()
        nodes: list[object] = [record]
        while nodes:
            value = nodes.pop()
            if type(value) is list:
                nodes.extend(value)
            elif type(value) is dict:
                item = _object(value)
                nodes.extend(item.values())
                for name in ("directory", "review", "authorization_path", "path"):
                    if name in item:
                        candidate = item[name]
                        if type(candidate) is str and Path(candidate).is_absolute():
                            roots.add(_path(candidate))
                for name in ("roots", "source_sha256"):
                    if name in item:
                        values = _object(item[name])
                        for candidate in values.values() if name == "roots" else values:
                            roots.add(_path(candidate))
        for name in references.get(cast(str, record.get("format")), ()):
            reference = _object(record[name], {"path", "sha256"})
            source, digest = _path(reference["path"]), _digest(reference["sha256"])
            roots.add(source)
            if source in seen:
                if seen[source] != digest:
                    raise ReleaseError("conflicting receipt exclusion references")
                continue
            if len(seen) >= 16:
                raise ReleaseError("receipt descriptor closure exceeds its boundary")
            seen[source] = digest
            pending.append(_load(pipeline._read(source, digest)))
    return sorted(roots)


def _model_specs(
    generation: dict[str, object],
    native: dict[str, object],
    template: dict[str, object] | None = None,
) -> dict[str, list[ModelSpec]]:
    selected = {
        name: gateway._profiles(
            Selection.from_bytes(_json(section["selection"])),
            {name: pipeline._absolute(path) for name, path in _object(section["roots"]).items()},
        )
        for name, section in (("generation", generation), ("native", native))
    }

    def choice(section: dict[str, object]) -> ModelSpec:
        role = _object(section["profile"])
        choices = _object(
            _object(selected["generation"][cast(str, role["capability"])])["profiles"]
        )
        return gateway._spec(_object(choices[cast(str, role["profile_id"])])["spec"])

    result = {"generation": [choice(generation)], "native": []}
    if template is not None:
        result["proposal"] = [choice(template)]
    for provider, models in _object(native["profiles"]).items():
        capability = next(
            key for key, value in gateway.CAPABILITIES.items() if value[0] == provider
        )
        choices = _object(_object(selected["native"][capability])["profiles"])
        for profile_id in _object(models).values():
            spec = gateway._spec(_object(choices[_text(profile_id)])["spec"])
            if spec not in result["native"]:
                result["native"].append(spec)
    return result
