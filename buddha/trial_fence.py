"""Opt-in original grant/tree fencing; no final schedule or scientific attestation.

This host-only helper reads fixed metadata and owns a serial writer lease. It
never opens an authorization database, executes candidate code or creates grants.
Final work remains unavailable until a real final-schedule consumer is added.
"""

import hashlib
import os
import stat
import threading
from collections.abc import Iterator, Mapping
from contextlib import contextmanager
from contextvars import ContextVar
from dataclasses import dataclass
from pathlib import Path

from buddha.common import ValidationError, _canonical
from buddha.releases import (
    MAX_JSON_BYTES,
    ReleaseError,
    _digest,
    _information,
    _json,
    _load,
    _object,
    _path,
    _root,
    _text,
    file_hash,
)

_PREFIX = "buddha.evaluation-trial.v1:"
_MARKER = ".buddha-evaluation-trial.json"
_LOCK = ".trial-running.lock"
_PHASES = {"search", "validation", "final"}
_KINDS = {
    "search": {"gateway", "generation", "native", "improvement", "screen", "search", "feedback"},
    "validation": {"gateway", "generation", "native", "validation"},
    "final": set(),
}
_MAX_INTEGER = 2**63 - 1


class TrialFenceError(ValidationError, ReleaseError):
    """The original trial tree, grant, phase or writer ownership is invalid."""


def _absolute(value: object) -> Path:
    if not isinstance(value, (str, Path)):
        raise TrialFenceError("trial paths require absolute local paths")
    text = _text(str(value))
    path = Path(text)
    if not path.is_absolute() or text.startswith(("\\\\", "//")):
        raise TrialFenceError("trial paths require absolute local paths")
    if str(path) != text or ".." in path.parts:
        raise TrialFenceError("trial paths require their exact normalized spelling")
    for component in path.parts[1:]:
        _path(component)
    return path


def _checked_path(value: object) -> Path:
    path = _absolute(value)
    information: os.stat_result | None
    for parent in path.parents:
        try:
            information = _information(parent)
        except FileNotFoundError:
            continue
        if not stat.S_ISDIR(information.st_mode):
            raise TrialFenceError("trial parent paths must be directories")
    try:
        information = _information(path)
    except FileNotFoundError:
        information = None
    if information is not None and (
        not (stat.S_ISREG(information.st_mode) or stat.S_ISDIR(information.st_mode))
        or (stat.S_ISREG(information.st_mode) and information.st_nlink != 1)
    ):
        raise TrialFenceError("trial paths cannot contain file aliases or special files")
    if str(path.resolve()) != str(path):
        raise TrialFenceError("trial paths require their resolved long spelling")
    return path


@dataclass(frozen=True)
class _TrialScope:
    root: Path
    definition_sha256: str
    phase: str

    def __post_init__(self) -> None:
        try:
            if not isinstance(self.root, Path):
                raise TrialFenceError("trial scope requires an explicit root Path")
            _absolute(self.root)
            _digest(self.definition_sha256)
            if type(self.phase) is not str or self.phase not in _PHASES:
                raise TrialFenceError("unsupported trial grant phase")
        except (ReleaseError, ValueError, TypeError, OSError):
            raise TrialFenceError("invalid trial scope identity") from None


def _scope_text(binding: _TrialScope) -> str:
    if type(binding) is not _TrialScope:
        raise TrialFenceError("trial scope requires its literal immutable identity")
    return _PREFIX + _json(
        {
            "root": str(binding.root),
            "definition_sha256": binding.definition_sha256,
            "phase": binding.phase,
        }
    ).decode("utf-8")


def _parse_scope(scope: str) -> _TrialScope | None:
    try:
        text = _text(scope)
        if not text.startswith(_PREFIX):
            return None
        raw = text[len(_PREFIX) :].encode("utf-8")
        record = _object(_load(raw), {"root", "definition_sha256", "phase"})
        if raw != _json(record):
            raise TrialFenceError("trial scope must be canonical strict JSON")
        return _TrialScope(
            _absolute(record["root"]), _digest(record["definition_sha256"]), _text(record["phase"])
        )
    except (ReleaseError, ValueError, TypeError, OSError, RecursionError):
        raise TrialFenceError("invalid reserved trial scope") from None


def _amount(value: object) -> int:
    if type(value) is not int or not 0 <= value <= _MAX_INTEGER:
        raise TrialFenceError("trial allowances require bounded literal integers")
    return value


def _read(path: Path) -> tuple[bytes, str]:
    digest = file_hash(path, max_bytes=MAX_JSON_BYTES)
    with path.open("rb") as stream:
        raw = stream.read(MAX_JSON_BYTES + 1)
    if len(raw) > MAX_JSON_BYTES or hashlib.sha256(raw).hexdigest() != digest:
        raise TrialFenceError("trial control changed during observation")
    if file_hash(path, max_bytes=MAX_JSON_BYTES) != digest:
        raise TrialFenceError("trial control changed during observation")
    return raw, digest


def _marker(directory: Path) -> tuple[Path, dict[str, object], str] | None:
    path = _checked_path(directory)
    found: tuple[Path, dict[str, object], str] | None = None
    for parent in (path, *path.parents):
        marker = parent / _MARKER
        try:
            _information(marker)
        except FileNotFoundError:
            continue
        raw, digest = _read(marker)
        record = _object(_load(raw), {"format", "root", "definition_sha256", "funding_sha256"})
        if record["format"] != "buddha.evaluation-trial-root.v1" or (
            _checked_path(record["root"]) != parent
        ):
            raise TrialFenceError("trial marker differs from its containing root")
        _digest(record["definition_sha256"])
        _digest(record["funding_sha256"])
        if found is not None:
            raise TrialFenceError("nested trial root markers conflict")
        found = parent, record, digest
    return found


def _terms_hash(budget: int, calls: int, scope: str) -> str:
    return hashlib.sha256(
        _canonical(
            {
                "currency": "USD",
                "budget_microusd": budget,
                "max_calls": calls,
                "scope": scope,
            }
        )
    ).hexdigest()


def _funding(
    root: Path, marker: dict[str, object], marker_sha256: str
) -> tuple[dict[str, object], dict[Path, str]]:
    definition_path, funding_path = root / "definition.json", root / "funding.json"
    _, definition_digest = _read(definition_path)
    raw, funding_digest = _read(funding_path)
    if (
        definition_digest != marker["definition_sha256"]
        or funding_digest != marker["funding_sha256"]
    ):
        raise TrialFenceError("fixed trial controls differ from their original marker")
    funding = _object(
        _load(raw),
        {
            "format",
            "root",
            "definition_sha256",
            "total_budget_microusd",
            "total_max_calls",
            "phases",
        },
    )
    if funding["format"] != "buddha.evaluation-trial-funding.v1" or (
        _checked_path(funding["root"]) != root or funding["definition_sha256"] != definition_digest
    ):
        raise TrialFenceError("funding differs from the fixed trial identity")
    total_budget = _amount(funding["total_budget_microusd"])
    total_calls = _amount(funding["total_max_calls"])
    phases = _object(funding["phases"], _PHASES)
    budgets = calls = 0
    for phase, value in phases.items():
        row = _object(
            value,
            {
                "authorization_path",
                "authorization_id",
                "terms_sha256",
                "budget_microusd",
                "max_calls",
                "scope",
                "purpose",
            },
        )
        _checked_path(row["authorization_path"])
        _text(row["authorization_id"])
        _text(row["purpose"])
        budget, count, scope = (
            _amount(row["budget_microusd"]),
            _amount(row["max_calls"]),
            _text(row["scope"]),
        )
        binding = _parse_scope(scope)
        if binding != _TrialScope(root, definition_digest, phase) or (
            _digest(row["terms_sha256"]) != _terms_hash(budget, count, scope)
        ):
            raise TrialFenceError("phase grant terms differ from its original trial identity")
        budgets += budget
        calls += count
    if (budgets, calls) != (total_budget, total_calls):
        raise TrialFenceError("phase allowances must exactly match the frozen total")
    return funding, {
        root / _MARKER: marker_sha256,
        definition_path: definition_digest,
        funding_path: funding_digest,
    }


def _actual_terms(terms: Mapping[str, object]) -> tuple[str, str, int, int, str]:
    if not isinstance(terms, Mapping):
        raise TrialFenceError("original grant terms require a mapping")
    identifier, scope = _text(terms["authorization_id"]), _text(terms["scope"])
    budget, calls = _amount(terms["budget_microusd"]), _amount(terms["max_calls"])
    digest = _digest(terms["terms_sha256"])
    if ("currency" in terms and terms["currency"] != "USD") or digest != _terms_hash(
        budget, calls, scope
    ):
        raise TrialFenceError("original grant terms are inconsistent")
    return identifier, digest, budget, calls, scope


def _original(
    authority_path: Path, terms: Mapping[str, object], directory: Path
) -> tuple[_TrialScope | None, dict[Path, str], dict[str, object] | None]:
    authority_path, directory = _checked_path(authority_path), _checked_path(directory)
    identifier, digest, budget, calls, scope = _actual_terms(terms)
    binding = _parse_scope(scope)
    marker = _marker(directory)
    if binding is None:
        if marker is not None:
            raise TrialFenceError("an opted-in trial tree requires its original phase grant")
        return None, {}, None
    if (
        marker is None
        or marker[0] != binding.root
        or marker[1]["definition_sha256"] != binding.definition_sha256
    ):
        raise TrialFenceError("trial scope requires its original root marker")
    if not directory.is_relative_to(binding.root / binding.phase):
        raise TrialFenceError("work output differs from its original phase tree")
    funding, controls = _funding(*marker)
    row = _object(_object(funding["phases"])[binding.phase])
    expected = (
        _checked_path(row["authorization_path"]),
        row["authorization_id"],
        row["terms_sha256"],
        row["budget_microusd"],
        row["max_calls"],
        row["scope"],
    )
    if (authority_path, identifier, digest, budget, calls, scope) != expected:
        raise TrialFenceError("work grant differs from the exact original phase grant")
    return binding, controls, row


@dataclass
class _Held:
    binding: _TrialScope
    pid: int
    thread: int
    device: int
    inode: int
    active: bool = True


_HELD: ContextVar[_Held | None] = ContextVar("buddha_trial_writer", default=None)


@dataclass
class _FinalEpisode:
    """Private consumed-cell capability; individual owner contracts are immutable bytes."""

    binding: _TrialScope
    cell: bytes
    owners: dict[Path, bytes]
    pid: int
    thread: int
    active: bool = True


_FINAL: ContextVar[_FinalEpisode | None] = ContextVar("buddha_final_cell", default=None)


def _final_current(binding: _TrialScope) -> tuple[_FinalEpisode, dict[str, object]]:
    episode = _FINAL.get()
    if (
        episode is None
        or not episode.active
        or episode.binding != binding
        or episode.pid != os.getpid()
        or episode.thread != threading.get_ident()
    ):
        raise TrialFenceError("final work requires the checked original consumer episode")
    _assert_held(binding)
    cell = _load(episode.cell)
    for name, digest in _object(cell["controls"]).items():
        if _read(_checked_path(name))[1] != _digest(digest):
            raise TrialFenceError("checked final episode inputs changed")
    return episode, cell


def _final_directory(cell: dict[str, object], directory: Path, kind: str) -> None:
    root = _checked_path(cell["directory"])
    role = _text(cell["kind"])
    if kind not in {role, "gateway"} or not directory.is_relative_to(root):
        raise TrialFenceError("final operation differs from its exact current cell")
    relative = directory.relative_to(root).parts
    if relative:
        import re

        if relative[0] == "owners":
            if len(relative) != 2 or not re.fullmatch(r"0|[1-9][0-9]*", relative[1]):
                raise TrialFenceError("final owner path differs from its schedule")
            index = int(relative[1])
            if (role == "generation" and index != 0) or (
                role == "native" and not 1 <= index <= _amount(cell["stage_count"])
            ):
                raise TrialFenceError("final owner stage differs from its schedule")
        elif relative[0] == "attempts":
            if (
                not 2 <= len(relative) <= 3
                or not re.fullmatch(r"(0|[1-9][0-9]*)-(0|[1-9][0-9]*)", relative[1])
                or (len(relative) == 3 and (role != "generation" or relative[2] != "session"))
            ):
                raise TrialFenceError("final session output differs from its original owner")
            stage = int(relative[1].split("-", 1)[0])
            if (role == "generation" and stage != 0) or (
                role == "native" and not 1 <= stage <= _amount(cell["stage_count"])
            ):
                raise TrialFenceError("final session stage differs from its schedule")
        else:
            raise TrialFenceError("final work output is outside its current cell")


def _final_projection(record: dict[str, object]) -> dict[str, object]:
    return {
        name: record[name]
        for name in (
            "settings",
            "selection",
            "selection_sha256",
            "roots",
            "profiles",
            "core",
            "runtime",
            "review",
            "authorization_path",
        )
    } | {"inputs": _object(record["invocation"])["inputs"]}


@contextmanager
def _final_episode(
    authority_path: Path,
    terms: Mapping[str, object],
    *,
    cell: dict[str, object],
    owners: Mapping[Path, dict[str, object]],
) -> Iterator[None]:
    """Only the final consumer supplies a fully checked frozen cell and retained owners."""
    directory = _checked_path(cell["directory"])
    binding, _, _ = _original(authority_path, terms, directory)
    if binding is None or binding.phase != "final" or _FINAL.get() is not None:
        raise TrialFenceError("a final episode needs its original final grant")
    _assert_held(binding)
    required = {binding.root / "freeze" / name for name in ("schedule.json", "ready.json")}
    if not required <= {Path(name) for name in _object(cell["controls"])}:
        raise TrialFenceError("final episode omits original confirmed freeze evidence")
    episode = _FinalEpisode(binding, _json(cell), {}, os.getpid(), threading.get_ident())
    token = _FINAL.set(episode)
    try:
        _final_current(binding)
        for path, manifest in owners.items():
            _final_directory(cell, _checked_path(path), "gateway")
            episode.owners[_checked_path(path)] = _json(_final_projection(manifest))
        yield
    finally:
        episode.active = False
        _FINAL.reset(token)


@contextmanager
def _final_owner_contract(
    authority_path: Path,
    terms: Mapping[str, object],
    *,
    directory: Path,
    selection: object,
    roots: object,
    settings: object,
    review: object,
    profiles: object,
    core: object,
    runtime: object,
    inputs: object,
) -> Iterator[None]:
    """Capture validated producer inputs before generic preparation/SQLite begins.

    This private seam is called only by the real generation/native producers,
    after their descriptor/C1/staging checks, within the consumer's checked cell.
    It creates no grant, owner or permission outside that existing episode.
    """
    binding, _, _ = _original(authority_path, terms, directory)
    if binding is not None and binding.phase == "final":
        episode, cell = _final_current(binding)
        _final_directory(cell, directory, "gateway")
        expected = _object(cell["owner"])
        actual = {
            "selection": selection,
            "roots": roots,
            "review": review,
            "profiles": profiles,
            "core": core,
            "runtime": runtime,
        }
        if any(actual[key] != expected[key] for key in actual):
            raise TrialFenceError("final producer changes its frozen owner projection")
        index = int(directory.name)
        allowed = expected["settings"]
        if cell["kind"] == "native" and index == cell["stage_count"]:
            allowed = {"budget_microusd": 1, "max_calls": 1}
        if settings != allowed:
            raise TrialFenceError("final producer changes its frozen owner ceilings")
        if type(inputs) is not list or len(inputs) > 1024:
            raise TrialFenceError("final producer requires bounded literal input records")
        observed = {}
        for value in inputs:
            row = _object(value, {"path", "sha256"})
            path, digest = _checked_path(row["path"]), _digest(row["sha256"])
            if path in observed or file_hash(path, max_bytes=256 * 1024**2) != digest:
                raise TrialFenceError("final producer inputs changed or repeat")
            observed[path] = digest
        if any(observed.get(Path(name)) != pin for name, pin in _object(cell["controls"]).items()):
            raise TrialFenceError("final producer omits frozen cell inputs")
        if observed.get(_checked_path(cell["descriptor_path"])) != cell["descriptor_sha256"]:
            raise TrialFenceError("final producer changes its exact frozen descriptor")
        context_path = _checked_path(cell["directory"]) / "context.json"
        context = {
            "format": "buddha.candidate-generation-context.v2"
            if cell["kind"] == "generation"
            else "buddha.native-evaluation-context.v1",
            "descriptor": cell["descriptor_path"],
        }
        if cell["kind"] == "generation":
            context["expected_runtime_sha256"] = cell["runtime_sha256"]
        context_raw = _json(context)
        if (
            observed.get(context_path) != hashlib.sha256(context_raw).hexdigest()
            or _read(context_path)[0] != context_raw
        ):
            raise TrialFenceError("final producer substituted its active descriptor context")
        projection = actual | {
            "settings": settings,
            "selection_sha256": hashlib.sha256(_json(selection)).hexdigest(),
            "authorization_path": str(authority_path),
            "inputs": inputs,
        }
        raw = _json(projection)
        if directory in episode.owners and episode.owners[directory] != raw:
            raise TrialFenceError("final producer replaces an original owner contract")
        episode.owners[directory] = raw
    yield


def _assert_held(binding: _TrialScope) -> None:
    held = _HELD.get()
    if (
        held is None
        or not held.active
        or (
            held.binding.root != binding.root
            or held.binding.definition_sha256 != binding.definition_sha256
            or held.pid != os.getpid()
            or held.thread != threading.get_ident()
        )
    ):
        raise TrialFenceError("scoped work requires its already-held trial writer lease")
    try:
        information = _information(binding.root / _LOCK)
        if (
            not stat.S_ISREG(information.st_mode)
            or information.st_nlink != 1
            or (information.st_dev, information.st_ino) != (held.device, held.inode)
        ):
            raise TrialFenceError("held trial lock no longer has its original owner")
    except (ReleaseError, OSError):
        raise TrialFenceError("held trial lock ownership is unavailable") from None


@contextmanager
def lease(
    authority_path: Path, terms: Mapping[str, object], *, directory: Path, settlement: bool = False
) -> Iterator[None]:
    """Acquire the original root before SQLite; settlement ignores dynamic poison."""
    try:
        if type(settlement) is not bool:
            raise TrialFenceError("settlement must be a literal boolean")
        if settlement:
            _checked_path(authority_path)
            _, _, _, _, scope = _actual_terms(terms)
            binding = _parse_scope(scope)
            if binding is not None and not _checked_path(directory).is_relative_to(binding.root):
                raise TrialFenceError("original scoped settlement is outside its root")
        else:
            binding, _, _ = _original(authority_path, terms, directory)
        if binding is not None:
            _root(_checked_path(binding.root))
            if _HELD.get() is not None:
                _assert_held(binding)
    except (ReleaseError, ValueError, TypeError, KeyError, OSError, RecursionError) as error:
        if isinstance(error, TrialFenceError):
            raise
        raise TrialFenceError("invalid trial writer identity or fixed controls") from None
    if binding is None or _HELD.get() is not None:
        yield
        return
    # shortcut: synchronous serial host ownership; parallel execution needs
    # a separately reviewed lease protocol, not copied ContextVar tokens.
    path = binding.root / _LOCK
    try:
        stream = path.open("xb")
    except OSError:
        raise TrialFenceError("trial writer is running or has a retained lock") from None
    try:
        identity = os.fstat(stream.fileno())
    except OSError:
        stream.close()
        raise TrialFenceError("trial lock identity is unavailable; lock retained") from None
    held = _Held(binding, os.getpid(), threading.get_ident(), identity.st_dev, identity.st_ino)
    token = None
    try:
        try:
            stream.write(str(held.pid).encode("ascii"))
            stream.flush()
        except OSError:
            raise TrialFenceError("trial lock could not record its owner") from None
        token = _HELD.set(held)
        _assert_held(binding)
        yield
    finally:
        held.active = False
        if token is not None:
            _HELD.reset(token)
        try:
            stream.close()
            information = _information(path)
            if (
                not stat.S_ISREG(information.st_mode)
                or information.st_nlink != 1
                or (information.st_dev, information.st_ino) != (identity.st_dev, identity.st_ino)
            ):
                raise TrialFenceError("trial lock ownership changed; foreign lock retained")
            path.unlink()
        except (ReleaseError, OSError) as error:
            if isinstance(error, TrialFenceError):
                raise
            raise TrialFenceError("trial lock ownership could not be safely released") from None


def _manifest_controls(manifest: object, controls: dict[Path, str]) -> None:
    record = _object(manifest)
    if record.get("format") != "buddha.gateway-run.v1":
        raise TrialFenceError("scoped binding requires a Gateway owner manifest")
    inputs = _object(record["invocation"])["inputs"]
    if type(inputs) is not list or not 1 <= len(inputs) <= 1024:
        raise TrialFenceError("scoped owner requires bounded original invocation inputs")
    observed = {}
    for value in inputs:
        row = _object(value, {"path", "sha256"})
        path, digest = _checked_path(row["path"]), _digest(row["sha256"])
        if path in observed:
            raise TrialFenceError("scoped owner repeats an invocation input")
        observed[path] = digest
    if any(observed.get(path) != digest for path, digest in controls.items()):
        raise TrialFenceError("scoped owner omitted or changed fixed trial controls")


def assert_work(
    authority_path: Path,
    terms: Mapping[str, object],
    *,
    directory: Path,
    kind: str = "gateway",
    manifest: object | None = None,
) -> dict[Path, str]:
    """Check new work without acquiring a lock; original scoped lease is required."""
    try:
        binding, controls, _ = _original(authority_path, terms, directory)
        if binding is None:
            return controls
        _assert_held(binding)
        if binding.phase == "final":
            episode, cell = _final_current(binding)
            _final_directory(cell, _checked_path(directory), kind)
            if manifest is not None:
                record = _object(manifest)
                _manifest_controls(record, controls)
                expected = episode.owners.get(_checked_path(directory))
                if expected is None or _json(_final_projection(record)) != expected:
                    raise TrialFenceError("final owner lacks its exact checked producer contract")
            elif kind == "gateway" and _checked_path(directory) not in episode.owners:
                raise TrialFenceError("direct final gateway work has no checked original owner")
            return controls
        if type(kind) is not str or kind not in _KINDS[binding.phase]:
            raise TrialFenceError("this phase cannot execute the requested work kind")
        try:
            (binding.root / "freeze").lstat()
        except FileNotFoundError:
            pass
        else:
            raise TrialFenceError("freeze has permanently closed adaptive work")
        if manifest is not None:
            _manifest_controls(manifest, controls)
        return controls
    except (ReleaseError, ValueError, TypeError, KeyError, OSError, RecursionError) as error:
        if isinstance(error, TrialFenceError):
            raise
        raise TrialFenceError("invalid original trial work boundary") from None


@contextmanager
def work(
    authority_path: Path, terms: Mapping[str, object], *, directory: Path, kind: str = "gateway"
) -> Iterator[dict[Path, str]]:
    """Own new work; final work requires a checked private consumer episode."""
    with lease(authority_path, terms, directory=directory):
        yield assert_work(authority_path, terms, directory=directory, kind=kind)


def required_controls(directory: Path) -> dict[Path, str]:
    """Passively read fixed root/definition/funding identities without permission."""
    try:
        marker = _marker(directory)
        return {} if marker is None else _funding(*marker)[1]
    except (ReleaseError, ValueError, TypeError, KeyError, OSError, RecursionError) as error:
        if isinstance(error, TrialFenceError):
            raise
        raise TrialFenceError("invalid fixed trial controls") from None


def _include_controls(directory: Path, bindings: Mapping[Path, str]) -> dict[Path, str]:
    """Copy caller pins and add original fixed controls without replacing a pin."""
    result = dict(bindings)
    for path, digest in required_controls(directory).items():
        if path in result and result[path] != digest:
            raise TrialFenceError("supplied pin conflicts with an original trial control")
        result[path] = digest
    return result


def is_closed(directory: Path) -> bool:
    """Passively recognize disabled final paths or irreversible freeze existence."""
    try:
        marker = _marker(directory)
        if marker is None:
            return False
        _funding(*marker)
        relative = _checked_path(directory).relative_to(marker[0])
        if relative.parts and relative.parts[0] == "final":
            episode = _FINAL.get()
            if episode is None:
                return True
            _, cell = _final_current(episode.binding)
            _final_directory(cell, _checked_path(directory), _text(cell["kind"]))
            return False
        try:
            (marker[0] / "freeze").lstat()
        except FileNotFoundError:
            return False
        return True
    except (ReleaseError, ValueError, TypeError, KeyError, OSError, RecursionError) as error:
        if isinstance(error, TrialFenceError):
            raise
        raise TrialFenceError("invalid trial closure boundary") from None


def require_purpose(
    authority_path: Path, terms: Mapping[str, object], *, directory: Path, expected: str
) -> None:
    """Preserve legacy exact scope or require the original funded trial purpose."""
    try:
        expected = _text(expected)
        binding, _, row = _original(authority_path, terms, directory)
        actual = terms["scope"] if binding is None else row["purpose"] if row is not None else None
        if actual != expected:
            raise TrialFenceError("grant purpose differs from the original experiment")
    except (ReleaseError, ValueError, TypeError, KeyError, OSError, RecursionError) as error:
        if isinstance(error, TrialFenceError):
            raise
        raise TrialFenceError("invalid original grant purpose") from None
