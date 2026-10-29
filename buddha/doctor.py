"""Bounded read-only observation of saved work, never permission to resume it.

No external seal is supplied: stable consumed bytes are observations, not an
atomic live snapshot or authenticated history. Current lock formats cannot
establish writer identity, container cleanup, or remote request completion.
"""

import hashlib
import os
import re
import sqlite3
import stat
import threading
from collections.abc import Callable, Iterator, Mapping
from contextlib import contextmanager
from contextvars import ContextVar
from dataclasses import dataclass
from pathlib import Path
from typing import cast

from buddha.authorization import _signature as _legacy_signature
from buddha.common import ValidationError, _canonical, _hex, _object, _parse, _text
from buddha.gateway import FORMAT as GATEWAY_FORMAT
from buddha.gateway_history import (
    HistoricalGatewayOperation,
)
from buddha.gateway_history import (
    _database as _gateway_database,
)
from buddha.gateway_history import (
    _manifest as _gateway_manifest,
)
from buddha.history import HistoricalOperation, _amount, _plain, _read_database
from buddha.ledger import _response_json
from buddha.process_observation import observe_pid
from buddha.releases import _path, _paths, _signature
from buddha.search_evidence import (
    MAX_FILE_BYTES,
    MAX_FILES,
    MAX_LEDGER_BYTES,
    MAX_MANIFEST_BYTES,
    MAX_TOTAL_BYTES,
    EvidenceFieldLimitError,
    EvidencePathLimitError,
    EvidenceTotalLimitError,
    _absolute,
    _read,
    _regular,
    _total_read,
    read_authority,
)

_LEGACY = {"buddha.baseline.v1", "buddha.policy-search.v1", "buddha.policy-search-continuation.v1"}
_LIMITATIONS = [
    "Observed bytes, not an atomic live snapshot, sealed verification or provider attestation.",
    "Existing locks do not identify their writer; PID presence does not prove ownership or health.",
    "Absent locks or diagnostics do not cancel requests, establish cleanup or release holds.",
    "No retry, lock removal, reconciliation, owner replacement or permission to spend.",
]
_STATES = ("completed", "reserved", "dispatched", "unknown")


class _Busy(Exception):
    pass


class _Unsupported(Exception):
    pass


def _sha(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()


def _json(raw: bytes, *, checksum: bool = False) -> dict[str, object]:
    record = _object(_parse(raw))
    if checksum and record.pop("record_sha256", None) != _sha(_canonical(record)):
        raise ValidationError("observed record checksum differs")
    return record


def _entries(
    root: Path, *, maximum: int | None = None
) -> dict[str, tuple[int, int, int, int, int]]:
    """Inspect bounded local metadata; never traverse a link or recorded path."""
    if maximum is not None and (type(maximum) is not int or not 1 <= maximum <= 100_000):
        raise ValidationError("unsupported observation tree-entry ceiling")
    maximum = MAX_FILES if maximum is None else maximum
    _plain(root)
    if not root.is_dir():
        raise ValidationError("observation requires a local directory")
    pending, files = [root], []
    result: dict[str, tuple[int, int, int, int, int]] = {}
    while pending:
        parent = pending.pop()
        _plain(parent)
        with os.scandir(parent) as children:
            for entry in children:
                if len(result) >= maximum:
                    raise EvidencePathLimitError("observation directory entry ceiling exceeded")
                path = parent / entry.name
                information = path.lstat()
                name = path.relative_to(root).as_posix()
                _path(name)
                if stat.S_ISDIR(information.st_mode):
                    pending.append(path)
                else:
                    _regular(path)
                    files.append(name)
                result[name] = _signature(information)
    if files:
        _paths(files)
    return result


_OBSERVATION_LIMIT: ContextVar[tuple[int, int | None, int | None] | None] = ContextVar(
    "evidence_observation_limit", default=None
)


@contextmanager
def _observation_policy(value: object) -> Iterator[None]:
    """Select finite observation limits, never an RSS or spending allowance.

    Version one keeps legacy count limits; version two explicitly selects them.
    Both retain no raw-byte cache and keep individual field limits. Captures
    freeze selected limits, including after this context exits.
    """
    record = _object(value)
    v2 = record.get("format") == "buddha.evidence-observation-policy.v2"
    fields = {"format", "max_total_bytes", "max_resident_bytes"}
    if v2:
        fields |= {"max_tree_entries", "max_consumed_paths"}
    if (
        set(record) != fields
        or type(record["format"]) is not str
        or record["format"]
        not in {"buddha.evidence-observation-policy.v1", "buddha.evidence-observation-policy.v2"}
        or type(record["max_total_bytes"]) is not int
        or not 1 <= record["max_total_bytes"] <= 64 * 1024**3
        or type(record["max_resident_bytes"]) is not int
        or record["max_resident_bytes"] != 0
    ):
        raise ValidationError("unsupported bounded evidence observation policy")
    counts: tuple[int | None, int | None] = (None, None)
    if v2:
        for key, maximum in (("max_tree_entries", 100_000), ("max_consumed_paths", 65_536)):
            if type(record[key]) is not int or not 1 <= cast(int, record[key]) <= maximum:
                raise ValidationError("unsupported bounded evidence observation policy")
        counts = (cast(int, record["max_tree_entries"]), cast(int, record["max_consumed_paths"]))
    token = _OBSERVATION_LIMIT.set((record["max_total_bytes"], counts[0], counts[1]))
    try:
        yield
    finally:
        _OBSERVATION_LIMIT.reset(token)


def _observation_limits() -> tuple[int, int, int]:
    selected = _OBSERVATION_LIMIT.get()
    total, entries, paths = (MAX_TOTAL_BYTES, None, None) if selected is None else selected
    return total, MAX_FILES if entries is None else entries, MAX_FILES if paths is None else paths


def _tree_context(root: Path) -> tuple[tuple[object, ...], object] | None:
    """Observe local locks and the actual held lease, never unrelated ancestors."""
    from buddha import trial_fence

    held = trial_fence._HELD.get()
    identity: tuple[object, ...] = ()
    if held is not None:
        if not held.active or held.pid != os.getpid() or held.thread != threading.get_ident():
            return None
        try:
            trial_fence._assert_held(held.binding)
        except trial_fence.TrialFenceError:
            return None
        identity = (
            id(held),
            str(held.binding.root),
            held.binding.definition_sha256,
            held.binding.version,
            held.device,
            held.inode,
        )
    paths = [root / name for name in (".trial-running.lock", "running.lock", ".search.lock")]
    if held is not None:
        paths.append(held.binding.root / trial_fence._LOCK)
    locks = []
    try:
        for path in paths:
            try:
                information = path.lstat()
            except FileNotFoundError:
                continue
            locks.append((str(path), _signature(information), information.st_nlink))
    except OSError:
        return None  # Strict construction needs no optimization-only lock metadata.
    return (identity, tuple(locks)), held


class _TreeObservation:
    """Bounded constructor metadata only; all receipt verification stays fresh."""

    def __init__(self) -> None:
        self.owner = os.getpid(), threading.get_ident()
        _, self.maximum_entries, self.maximum_roots = _observation_limits()
        self.roots: dict[
            tuple[object, ...],
            tuple[Path, int, dict[str, tuple[int, int, int, int, int]], object],
        ] = {}
        self.count = 0

    def entries(self, capture: "_Capture") -> dict[str, tuple[int, int, int, int, int]]:
        if self.owner != (os.getpid(), threading.get_ident()):
            return capture._tree_entries()
        context = _tree_context(capture.root)
        if context is None:
            return capture._tree_entries()
        key = (
            str(capture.root),
            capture._maximum,
            capture._maximum_entries,
            capture._maximum_paths,
            context[0],
        )
        if key in self.roots:
            _plain(capture.root)
            if not capture.root.is_dir():
                raise ValidationError("observation requires a local directory")
            return dict(self.roots[key][2])
        entries = capture._tree_entries()
        if (
            len(self.roots) < self.maximum_roots
            and self.count + len(entries) <= self.maximum_entries
        ):
            self.roots[key] = capture.root, capture._maximum_entries, dict(entries), context[1]
            self.count += len(entries)
        return entries

    def finish(self) -> None:
        for key, (root, maximum, entries, _) in self.roots.items():
            context = _tree_context(root)
            if context is None or context[0] != key[-1]:
                raise _Busy("observed local tree or writer lease changed")
            current = _entries(root) if maximum == MAX_FILES else _entries(root, maximum=maximum)
            if current != entries:
                raise _Busy("observed local tree or writer lease changed")


_PASSIVE_TREES: ContextVar[_TreeObservation | None] = ContextVar(
    "evidence_passive_tree_observation", default=None
)


@contextmanager
def _passive_tree_observation() -> Iterator[None]:
    """Share initial metadata within one trusted passive call, never raw bytes.

    Finite registry exhaustion falls back to ordinary construction. Every
    capture finish/adoption remains strict, and successful exit freshly checks
    shared roots and their lease context. A failed call discards the registry.
    """
    current = _PASSIVE_TREES.get()
    if current is not None and current.owner == (os.getpid(), threading.get_ident()):
        yield
        return
    observation = _TreeObservation()
    token = _PASSIVE_TREES.set(observation)
    try:
        yield
        observation.finish()
    finally:
        _PASSIVE_TREES.reset(token)


class _CapturedBytes(Mapping[Path, bytes]):
    """Read-only access to original receipts, with verified bounded rereads."""

    def __init__(self, capture: "_Capture") -> None:
        self.capture = capture

    def __getitem__(self, path: Path) -> bytes:
        size, _ = self.capture._receipts[path]
        return self.capture.read(path, size)

    def __iter__(self) -> Iterator[Path]:
        return iter(self.capture._receipts)

    def __len__(self) -> int:
        return len(self.capture._receipts)

    def __contains__(self, path: object) -> bool:
        return path in self.capture._receipts


class _Capture:
    """Retain size/digest receipts, not raw bytes; default logical limit is 1 GiB.

    Each returned file remains bounded separately. The consumed-byte ceiling is
    frozen at construction and includes external inputs and nested adoption.
    It is not a process-memory limit or a total archive-size allowance.
    """

    def __init__(self, root: Path) -> None:
        self.root = root
        self._maximum, self._maximum_entries, self._maximum_paths = _observation_limits()
        observation = _PASSIVE_TREES.get()
        self.entries = self._tree_entries() if observation is None else observation.entries(self)
        self._receipts: dict[Path, tuple[int, str]] = {}
        self.raw: Mapping[Path, bytes] = _CapturedBytes(self)
        self.total = 0
        self.databases: set[Path] = set()

    def _tree_entries(self) -> dict[str, tuple[int, int, int, int, int]]:
        if self._maximum_entries == MAX_FILES:
            return _entries(self.root)
        return _entries(self.root, maximum=self._maximum_entries)

    def read(self, path: Path, maximum: int = MAX_MANIFEST_BYTES) -> bytes:
        if path in self._receipts:
            size, digest = self._receipts[path]
            if size > maximum:
                raise EvidenceFieldLimitError("observed input exceeds this field's ceiling", size)
            raw = _read(path, size)
            if len(raw) != size or _sha(raw) != digest:
                raise _Busy("consumed input changed")
            return raw
        if len(self._receipts) >= self._maximum_paths:
            raise EvidencePathLimitError("consumed evidence path ceiling exceeded")
        raw = _total_read(path, maximum, self._maximum - self.total, read=_read)
        self.total += len(raw)
        self._receipts[path] = (len(raw), _sha(raw))
        return raw

    def sidecars(self, path: Path) -> None:
        for suffix in ("-journal", "-wal", "-shm"):
            sidecar = path.with_name(path.name + suffix)
            try:
                information = _regular(sidecar)
            except FileNotFoundError:
                continue
            if information.st_size:
                raise _Busy("SQLite sidecar prevents a stable observation")
            self.read(sidecar, 0)

    def database(self, path: Path) -> bytes:
        self.sidecars(path)
        self.databases.add(path)
        return self.read(path, MAX_LEDGER_BYTES)

    def callback(self, directory: Path) -> Callable[[str, int], bytes]:
        def read(name: str, maximum: int) -> bytes:
            return self.read(directory / _path(name), maximum)

        return read

    def finish(self) -> dict[str, str]:
        for path in self.databases:
            self.sidecars(path)
        for path in tuple(self._receipts):
            self.raw[path]
        for path in self.databases:
            self.sidecars(path)
        if self._tree_entries() != self.entries:
            raise _Busy("observed local tree changed")
        return {
            path.relative_to(self.root).as_posix()
            if path.is_relative_to(self.root)
            else "authorization": digest
            for path, (_, digest) in self._receipts.items()
        }

    def fingerprints(self) -> dict[str, str]:
        self.finish()
        return {str(path): digest for path, (_, digest) in self._receipts.items()}

    def adopt(self, source: "_Capture") -> None:
        """Merge original receipts at a fresh source observation cut.

        This is not an atomic file snapshot. The receiver's final fresh finish
        remains necessary before active work, including for newly adopted paths.
        """
        if type(self) is not _Capture or type(source) is not _Capture or source is self:
            raise ValidationError("capture adoption needs two original bounded observations")
        source.finish()
        # Preserve the legacy database/sidecar insertion order without rereads.
        ordered = {}
        for database in source.databases:
            receipt = source._receipts.get(database)
            if receipt is None:
                raise ValidationError("database observation lacks its original byte receipt")
            if receipt[0] > MAX_LEDGER_BYTES:
                raise EvidenceFieldLimitError(
                    "observed input exceeds this field's ceiling", receipt[0]
                )
            for suffix in ("-journal", "-wal", "-shm"):
                sidecar = database.with_name(database.name + suffix)
                if sidecar in source._receipts:
                    ordered[sidecar] = source._receipts[sidecar]
            ordered[database] = receipt
        ordered.update(source._receipts)
        receipts = dict(self._receipts)
        for path, receipt in ordered.items():
            if path in receipts and receipts[path] != receipt:
                raise _Busy("consumed input changed")
            receipts[path] = receipt
        if len(receipts) > self._maximum_paths:
            raise EvidencePathLimitError("consumed evidence path ceiling exceeded")
        total = sum(size for size, _ in receipts.values())
        if total > self._maximum:
            raise EvidenceTotalLimitError("evidence observation exceeds its total byte ceiling")
        self._receipts, self.total, self.databases = (
            receipts,
            total,
            self.databases | source.databases,
        )


@dataclass(frozen=True)
class _Owner:
    directory: Path
    manifest: dict[str, object]
    manifest_sha256: str
    ledger_sha256: str
    operations: tuple[HistoricalOperation | HistoricalGatewayOperation, ...]

    @property
    def run_id(self) -> str:
        return _text(self.manifest["run_id"], "observed run ID")

    def accounting(self) -> dict[str, int]:
        settings = _object(self.manifest["settings"])
        spent = sum(op.actual_microusd or 0 for op in self.operations if op.status == "completed")
        held = sum(op.reserve_microusd for op in self.operations if op.status != "completed")
        return {
            "committed_microusd": spent + held,
            "spent_microusd": spent,
            "reserved_microusd": held,
            "operation_count": len(self.operations),
            "budget_microusd": _amount(settings["budget_microusd"], "observed budget"),
            "max_calls": _amount(settings["max_calls"], "observed call cap"),
            **{
                state + "_count": sum(op.status == state for op in self.operations)
                for state in _STATES
            },
        }

    def rows(self) -> list[dict[str, object]]:
        return [
            {
                "operation_id": op.operation_id,
                "request_sha256": op.request_sha256,
                "status": op.status,
                "reserve_microusd": op.reserve_microusd,
                "actual_microusd": op.actual_microusd,
            }
            for op in self.operations
        ]


def _owner(capture: _Capture, directory: Path) -> _Owner:
    raw = capture.read(directory / "manifest.json")
    record = _json(raw)
    kind = record.get("format")
    if kind not in _LEGACY | {GATEWAY_FORMAT}:
        raise _Unsupported("unsupported stored owner format")
    checksum = record.pop("record_sha256", None)
    digest = _sha(_canonical(record))
    if (kind != "buddha.baseline.v1" or checksum is not None) and checksum != digest:
        raise ValidationError("observed manifest checksum differs")
    run_id = _text(record.get("run_id"), "observed run ID")
    if not re.fullmatch(r"[A-Za-z0-9_-]{1,128}", run_id, re.ASCII):
        raise ValidationError("invalid observed run ID")
    settings = _object(record.get("settings"))
    budget = _amount(settings.get("budget_microusd"), "observed budget")
    calls = _amount(settings.get("max_calls"), "observed call cap")
    ledger = capture.database(directory / "operations.sqlite3")
    operations = (
        _gateway_database(ledger, _gateway_manifest(raw, digest), digest)
        if kind == GATEWAY_FORMAT
        else _read_database(ledger, run_id, digest, budget, calls)
    )
    return _Owner(directory, record, digest, _sha(ledger), operations)


def _lock(capture: _Capture) -> tuple[dict[str, object], dict[str, object]]:
    lock: dict[str, object] = {"status": "absent", "name": None, "pid": None}
    writer: dict[str, object] = {"identity": "unknown", "pid_observation": None}
    names = [name for name in (".search.lock", "running.lock") if name in capture.entries]
    if not names:
        return lock, writer
    if len(names) != 1:
        return lock | {"status": "invalid"}, writer
    name = names[0]
    try:
        if name == ".search.lock":
            # This exclusion has no content. A Windows read handle can prevent
            # its writer unlinking it; the tree's metadata bracket checks drift.
            empty = _regular(capture.root / name).st_size == 0
            return lock | {"status": "legacy_empty" if empty else "invalid", "name": name}, writer
        raw = capture.read(capture.root / name, 128)
        text = raw.decode("ascii")
        if name != "running.lock" or not re.fullmatch(r"[1-9][0-9]{0,9}", text):
            raise ValidationError("invalid lock record")
        pid = int(text)
        observation = observe_pid(pid)
        return lock | {"status": "pid_only", "name": name, "pid": pid}, writer | {
            "pid_observation": observation
        }
    except (OSError, ValueError):
        return lock | {"status": "invalid", "name": name}, writer


def _diagnostics(capture: _Capture, owner: _Owner) -> list[dict[str, object]]:
    if owner.manifest["format"] == GATEWAY_FORMAT:
        return []  # Raw Gateway receipts do not use legacy HTTP diagnostic records.
    from buddha.diagnostics import failure_summaries

    outstanding = {
        op.operation_id: (op.request_sha256, op.status)
        for op in owner.operations
        if op.status in {"unknown", "dispatched"} and re.fullmatch(r"[0-9a-f]{64}", op.operation_id)
    }
    return list(failure_summaries(outstanding, read=capture.callback(owner.directory)))


def _completion(
    status: str = "no_completion_observed", digest: str | None = None
) -> dict[str, object]:
    return {"status": status, "record_sha256": digest}


def _legacy_completion(capture: _Capture, owner: _Owner) -> dict[str, object]:
    root, kind = owner.directory, owner.manifest["format"]
    marker = "evaluation/provenance.json" if kind == "buddha.baseline.v1" else "report.json"
    if marker not in capture.entries or kind == GATEWAY_FORMAT:
        return _completion()
    raw = capture.read(root / marker)
    digest = _sha(raw)
    try:
        if any(op.status != "completed" for op in owner.operations):
            return _completion()
        if kind == "buddha.baseline.v1":
            provenance = _json(raw)
            if provenance.pop("provenance_sha256", None) != _sha(_canonical(provenance)):
                raise ValidationError("completion provenance checksum differs")
            hashes = _object(provenance["artifact_hashes"])
            if (
                provenance.get("format") != "buddha.noveltybench.v1"
                or provenance.get("origin") != "buddha-local"
                or provenance.get("protocol") != owner.manifest.get("protocol")
                or set(hashes)
                != {
                    "generations.jsonl",
                    "v1.1/partitions.jsonl",
                    "v1.1/scores.jsonl",
                    "v1.1/summary.json",
                }
            ):
                raise ValidationError("completion provenance differs")
            for name, expected in hashes.items():
                if _sha(capture.read(root / "evaluation" / name, MAX_FILE_BYTES)) != expected:
                    raise ValidationError("completion artifact differs")
        else:
            report = _json(raw, checksum=True)
            expected_format = (
                "buddha.policy-search-report.v2"
                if kind == "buddha.policy-search-continuation.v1"
                else "buddha.policy-search-report.v1"
            )
            if (
                report.get("format") != expected_format
                or report.get("status") != "complete"
                or report.get("run_id") != owner.run_id
                or report.get("comparison_key") != owner.manifest.get("comparison_key")
            ):
                raise ValidationError("completion marker differs")
        return _completion("stored_completion_observed", digest)
    except (OSError, ValueError, KeyError, TypeError):
        return _completion("invalid_completion", digest)


def _candidate_count(capture: _Capture, owner: _Owner) -> int:
    candidates = set()
    for name in capture.entries:
        if not re.fullmatch(r"decisions/[^/]+\.json", name):
            continue
        try:
            row = _json(capture.read(owner.directory / name), checksum=True)
            candidate = row.get("candidate_id")
            if row.get("status") == "admitted" and row.get("comparison_key") == owner.manifest.get(
                "comparison_key"
            ):
                _hex(candidate, "observed candidate")
                candidates.add(cast(str, candidate))
        except (OSError, ValueError):
            continue
    return len(candidates)


def _mirror_signature(op: HistoricalOperation | HistoricalGatewayOperation) -> tuple[object, ...]:
    if isinstance(op, HistoricalOperation):
        return _legacy_signature(op)
    receipt = op.checkpoint if op.status == "unknown" else op.receipt
    request_id = op.checkpoint_request_id if op.status == "unknown" else op.provider_request_id
    return (
        op.request_sha256,
        op.reserve_microusd,
        op.status,
        None if receipt is None else _response_json(receipt),
        op.actual_microusd,
        request_id,
    )


def _authority(
    capture: _Capture, path: Path | None, owners: list[_Owner]
) -> dict[str, object] | None:
    if path is None:
        return None
    from buddha.search_evidence import _local_binding

    authority_path = _absolute(str(path.absolute()))
    authority = read_authority(capture.database(authority_path))
    config = _object(authority["config"])
    rows = cast(list[dict[str, object]], authority["auth_runs"])
    operations = cast(list[dict[str, object]], authority["auth_operations"])
    fields = (
        "request_sha256",
        "reserve_microusd",
        "status",
        "response_json",
        "actual_microusd",
        "provider_request_id",
    )
    for owner in owners:
        matches = [row for row in rows if row["run_id"] == owner.run_id]
        if len(matches) != 1:
            raise ValidationError("explicit authority lacks the observed owner")
        row = matches[0]
        if (
            row["directory"] != str(owner.directory)
            or row["ledger_path"] != str(owner.directory / "operations.sqlite3")
            or row["manifest_sha256"] != owner.manifest_sha256
        ):
            raise ValidationError("explicit authority owner identity differs")
        if row["historical"]:
            if row["historical_ledger_sha256"] != owner.ledger_sha256:
                raise ValidationError("imported ledger differs from the observed history")
        else:
            binding = _local_binding(capture.raw[owner.directory / "operations.sqlite3"])
            expected = {
                "authorization_id": config["authorization_id"],
                "authority_path": str(authority_path),
                "terms_sha256": _sha(_canonical(config)),
            }
            if binding is None or any(binding[key] != value for key, value in expected.items()):
                raise ValidationError("explicit authority differs from the local binding")
        saved = {
            str(op["operation_id"]): tuple(op[key] for key in fields)
            for op in operations
            if op["run_id"] == owner.run_id
        }
        if saved != {op.operation_id: _mirror_signature(op) for op in owner.operations}:
            raise ValidationError("explicit authority operation mirror differs")
    return authority


def _native_stage(
    capture: _Capture, owner: _Owner, index: int, authority: dict[str, object] | None
) -> tuple[dict[str, object], dict[str, object] | None]:
    name = f"completed/{index}.json"
    if name not in capture.entries:
        return _completion(), None
    raw = capture.read(capture.root / name)
    digest = _sha(raw)
    try:
        seal = _json(raw)
        if (
            set(seal) != {"format", "index", "owner_sha256", "attempt", "files"}
            or seal["format"] != "buddha.baseline-stage.v1"
            or type(seal["index"]) is not int
            or seal["index"] != index
            or seal["owner_sha256"] != owner.manifest_sha256
        ):
            raise ValidationError("native completion identity differs")
        attempt = _path(seal["attempt"])
        if not re.fullmatch(rf"attempts/{index}-(?:0|[1-9][0-9]*)", attempt):
            raise ValidationError("native attempt path differs")
        files = _object(seal["files"])
        _paths(list(files))
        actual = {
            name[len(attempt) + 1 :]
            for name in capture.entries
            if name.startswith(attempt + "/")
            and stat.S_ISREG((capture.root / name).lstat().st_mode)
        }
        if set(files) != actual or "report.json" not in files:
            raise ValidationError("native attempt inventory differs")
        for name, expected in files.items():
            _hex(expected, "observed completion file digest")
            if _sha(capture.read(capture.root / attempt / name, MAX_FILE_BYTES)) != expected:
                raise ValidationError("native attempt content differs")
        report = _json(capture.read(capture.root / attempt / "report.json"))
        if (
            report.get("format")
            != ("buddha.generation-report.v1" if index == 0 else "buddha.native-command-report.v1")
            or report.get("status") != "complete"
            or report.get("gateway_manifest_sha256") != owner.manifest_sha256
            or report.get("gateway_totals")
            != {
                key: owner.accounting()[key]
                for key in (
                    "committed_microusd",
                    "spent_microusd",
                    "reserved_microusd",
                    "operation_count",
                )
            }
        ):
            raise ValidationError("native completion report differs")
        for name, expected in _object(report["artifacts"]).items():
            relative = _path(name) if index == 0 else "artifacts/" + _path(name)
            if files.get(relative) != expected:
                raise ValidationError("native report artifact differs")
        if any(op.status != "completed" for op in owner.operations):
            return _completion("invalid_completion", digest), report
        if authority is None:
            return _completion("anchor_not_observed", digest), report
        rows = cast(list[dict[str, object]], authority["auth_deactivations"])
        anchors = [row for row in rows if row["run_id"] == owner.run_id]
        if not anchors:
            return _completion("unanchored_completion_needs_review", digest), report
        if len(anchors) != 1 or anchors[0]["reason"] != "baseline completed: " + digest:
            return _completion("anchor_mismatch", digest), report
        return _completion("stored_completion_observed", digest), report
    except (OSError, ValueError, KeyError, TypeError):
        return _completion("invalid_completion", digest), None


def _native(
    capture: _Capture, authority_path: Path | None, result: dict[str, object]
) -> list[_Owner]:
    context = _json(capture.read(capture.root / "context.json"))
    if context.get("format") != "buddha.baseline-context.v1":
        raise _Unsupported("unsupported baseline context")
    # The descriptor path is recorded data; no selected driver/runtime is loaded.
    if set(context) != {"format", "descriptor"} or not isinstance(context["descriptor"], str):
        raise ValidationError("invalid baseline context")
    indices = sorted(
        int(name.split("/")[1])
        for name in capture.entries
        if re.fullmatch(r"owners/(?:0|[1-9][0-9]*)/manifest.json", name)
    )
    if not indices or indices != list(range(len(indices))) or len(indices) > 34:
        raise ValidationError("native owner population is incomplete or oversized")
    directories = {name for name in capture.entries if re.fullmatch(r"owners/[^/]+", name)}
    if directories != {f"owners/{index}" for index in indices}:
        raise ValidationError("native owner directory lacks its original manifest")
    completions = {name for name in capture.entries if name.startswith("completed/")}
    if not completions <= {f"completed/{index}.json" for index in indices}:
        raise ValidationError("native completion names lack an original owner")
    owners = [_owner(capture, capture.root / "owners" / str(index)) for index in indices]
    if len({owner.run_id for owner in owners}) != len(owners) or any(
        owner.manifest["format"] != GATEWAY_FORMAT for owner in owners
    ):
        raise ValidationError("native stages require raw Gateway owners")
    selection = _object(owners[0].manifest["selection"])
    release = _object(selection["release"])
    agent = _object(selection["components"])["agent"]
    for owner in owners:
        selected = _object(owner.manifest["selection"])
        if selected["release"] != release or _object(selected["components"])["agent"] != agent:
            raise ValidationError("native owner source lineage differs")
    authority = _authority(capture, authority_path, owners)
    stages, reports, completion_records = [], [], []
    for index, owner in zip(indices, owners, strict=True):
        completion, report = _native_stage(capture, owner, index, authority)
        stages.append(
            {
                "index": index,
                "run_id": owner.run_id,
                "accounting": owner.accounting(),
                "operations": owner.rows(),
                "diagnostics": [],
                "completion": completion,
            }
        )
        reports.append(report)
        completion_records.append(completion)
    accounting: dict[str, object] = {
        key: sum(owner.accounting()[key] for owner in owners)
        for key in owners[0].accounting()
        if key not in {"budget_microusd", "max_calls"}
    }
    accounting.update(budget_microusd=None, max_calls=None)
    result.update(
        input_format="buddha.baseline-context.v1",
        accounting=accounting,
        stages=stages,
        shared_accounting=None if authority is None else authority["totals"],
    )
    bad = {"unanchored_completion_needs_review", "anchor_mismatch", "invalid_completion"}
    completion = next((item for item in completion_records if item["status"] in bad), _completion())
    if "report.json" in capture.entries and completion["status"] not in bad:
        raw = capture.read(capture.root / "report.json")
        try:
            report = _json(raw)
            commands = release["commands"]
            if (
                not isinstance(commands, list)
                or len(owners) != len(commands) + 1
                or report.get("format") != "buddha.native-baseline-report.v1"
                or report.get("status") != "complete"
                or report.get("stages") != reports
                or report.get("release_sha256") != _sha(_canonical(release))
                or report.get("tasks_sha256") != _object(reports[0]).get("tasks_sha256")
            ):
                raise ValidationError("native final report differs")
            seals = _object(report["stage_seals"])
            expected_seals = {
                f"completed/{index}.json": _sha(
                    capture.read(capture.root / f"completed/{index}.json")
                )
                for index in indices
            }
            windows_seals = {
                name.replace("/", "\\"): digest for name, digest in expected_seals.items()
            }
            if seals not in (expected_seals, windows_seals):
                raise ValidationError("native final stage seals differ")
            summary = _object(report["summary"])
            path = Path(_text(summary.get("path"), "native summary path"))
            last_seal = _json(capture.read(capture.root / f"completed/{indices[-1]}.json"))
            summary_name = _path(_object(release["artifacts"])["summary"])
            expected_path = capture.root / _path(last_seal["attempt"]) / "artifacts" / summary_name
            expected_digest = _object(_object(reports[-1])["artifacts"])[summary_name]
            if path != expected_path or summary.get("sha256") != expected_digest:
                raise ValidationError("native final summary differs from its sealed final stage")
            if _sha(capture.read(expected_path, MAX_FILE_BYTES)) != expected_digest:
                raise ValidationError("native final summary differs")
            state = (
                "stored_completion_observed"
                if all(
                    item["status"] == "stored_completion_observed" for item in completion_records
                )
                else "anchor_not_observed"
            )
            completion = _completion(state, _sha(raw))
        except (OSError, ValueError, KeyError, TypeError):
            completion = _completion("invalid_completion", _sha(raw))
    elif completion["status"] not in bad and any(
        item["status"] == "anchor_not_observed" for item in completion_records
    ):
        completion = _completion("anchor_not_observed")
    result["completion"] = completion
    return owners


def observe(directory: Path, *, authorization: Path | None = None) -> dict[str, object]:
    """Observe bounded local records without a writer, runtime replay or credentials."""
    if (
        not isinstance(directory, Path)
        or authorization is not None
        and not isinstance(authorization, Path)
    ):
        raise ValidationError("doctor paths must be filesystem Paths")
    result: dict[str, object] = {
        "format": "buddha.doctor.v1",
        "status": "unavailable",
        "needs_review": None,
        "input_format": None,
        "run_id": None,
        "accounting": None,
        "operations": [],
        "lock": {"status": "unavailable", "name": None, "pid": None},
        "writer": {"identity": "unknown", "pid_observation": None},
        "diagnostics": [],
        "completion": _completion(),
        "candidate_count": 0,
        "stages": [],
        "shared_accounting": None,
        "observed_sha256": {},
        "limitations": list(_LIMITATIONS),
    }
    try:
        root = _absolute(str(directory.absolute()))
        capture = _Capture(root)
        result["lock"], result["writer"] = _lock(capture)
        if "context.json" in capture.entries:
            _native(capture, authorization, result)
        else:
            owner = _owner(capture, root)
            authority = _authority(capture, authorization, [owner])
            result.update(
                input_format=owner.manifest["format"],
                run_id=owner.run_id,
                accounting=owner.accounting(),
                operations=owner.rows(),
                diagnostics=_diagnostics(capture, owner),
                completion=_legacy_completion(capture, owner),
                candidate_count=_candidate_count(capture, owner),
                shared_accounting=None if authority is None else authority["totals"],
            )
        result["observed_sha256"] = capture.finish()
        accounting = _object(result["accounting"])
        result.update(
            status="observed",
            needs_review=bool(accounting["unknown_count"])
            or _object(result["completion"])["status"]
            in {"invalid_completion", "anchor_mismatch", "unanchored_completion_needs_review"}
            or _object(result["lock"])["status"] == "invalid",
        )
    except _Unsupported:
        result["status"] = "unsupported"
    except _Busy:
        result["status"] = "busy_or_changing"
    except (OSError, ValueError, TypeError, KeyError, RecursionError, sqlite3.Error):
        result["status"] = "unavailable"
    if result["status"] != "observed":
        result.update(
            accounting=None,
            operations=[],
            diagnostics=[],
            stages=[],
            shared_accounting=None,
            needs_review=None,
            completion=_completion(),
            observed_sha256={},
        )
    return result
