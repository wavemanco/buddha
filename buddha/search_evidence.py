"""Explicit sealed inputs for read-only legacy search verification.

Every consumed byte belongs to a caller-listed file. Filesystem observations
bracket verification; archived programs and recorded authority paths stay data.
"""

import hashlib
import os
import sqlite3
import stat
from collections.abc import Mapping
from contextlib import closing
from dataclasses import dataclass, field
from pathlib import Path, PurePosixPath, PureWindowsPath
from types import MappingProxyType

from buddha.authorization import _totals, _validate
from buddha.common import ValidationError, _canonical, _hex, _object, _parse, _text
from buddha.history import _plain
from buddha.ledger import _amount
from buddha.releases import _paths, _signature

MAX_RUNS = 64
MAX_FILES = 10_000
MAX_TOTAL_BYTES = 1024**3
MAX_FILE_BYTES = 64 * 1024**2
MAX_MANIFEST_BYTES = 32 * 1024**2
MAX_LEDGER_BYTES = 512 * 1024**2
MAX_ROWS = 100_000
_SIDECARS = ("-wal", "-shm", "-journal")


def _absolute(value: object) -> Path:
    text = _text(value, "explicit evidence path")
    path = Path(text)
    if text.startswith(("//", "\\\\")) or not path.is_absolute() or ".." in path.parts:
        raise ValidationError("evidence paths must be local absolute paths without traversal")
    _plain(path)
    return path.resolve()


def _regular(path: Path) -> os.stat_result:
    _plain(path)
    information = path.lstat()
    if not stat.S_ISREG(information.st_mode) or information.st_nlink != 1:
        raise ValidationError("evidence files must be regular without hard-link aliases")
    return information


def _read(path: Path, maximum: int) -> bytes:
    before = _regular(path)
    if before.st_size > maximum:
        raise ValidationError("evidence file exceeds its byte ceiling")
    chunks = bytearray()
    with path.open("rb") as stream:
        opened = os.fstat(stream.fileno())
        if (opened.st_dev, opened.st_ino) != (before.st_dev, before.st_ino):
            raise ValidationError("opened evidence differs from its selected file")
        while block := stream.read(min(1024**2, maximum - len(chunks) + 1)):
            chunks.extend(block)
            if len(chunks) > maximum:
                raise ValidationError("consumed evidence exceeds its byte ceiling")
        if _signature(os.fstat(stream.fileno()))[:4] != _signature(opened)[:4]:
            raise ValidationError("opened evidence changed during observation")
    if _signature(_regular(path)) != _signature(before):
        raise ValidationError("evidence file changed during observation")
    return bytes(chunks)


def _sidecars(path: Path) -> None:
    for suffix in _SIDECARS:
        sidecar = path.with_name(path.name + suffix)
        try:
            sidecar.lstat()
        except FileNotFoundError:
            continue
        if _read(sidecar, 0):
            raise ValidationError("evidence has an active SQLite sidecar")


def _tree(
    directory: Path, expected: Mapping[str, object], maximum_entries: int
) -> tuple[tuple[str, ...], tuple[str, ...], int]:
    _plain(directory)
    if not directory.is_dir():
        raise ValidationError("evidence run is not a directory")
    pending, files, folders = [directory], [], []
    entries = 0
    while pending:
        parent = pending.pop()
        _plain(parent)
        with os.scandir(parent) as children:
            for entry in children:
                entries += 1
                if entries > maximum_entries:
                    raise ValidationError("evidence directory entry ceiling exceeded")
                path = parent / entry.name
                _plain(path)
                information = path.lstat()
                name = path.relative_to(directory).as_posix()
                if entry.name.casefold() == ".search.lock":
                    raise ValidationError("evidence run has a search lock; review its writer first")
                if stat.S_ISDIR(information.st_mode):
                    folders.append(name)
                    pending.append(path)
                elif stat.S_ISREG(information.st_mode) and information.st_nlink == 1:
                    if name.casefold() in {"operations.sqlite3" + s for s in _SIDECARS}:
                        if name != name.lower():
                            raise ValidationError("SQLite sidecar name has a portable alias")
                        _read(path, 0)
                        if name not in expected:
                            continue
                    files.append(name)
                    if len(files) > MAX_FILES:
                        raise ValidationError("evidence file ceiling exceeded")
                else:
                    raise ValidationError("evidence tree contains a link or nonregular member")
    # The existing portable inventory validator accepts leaf paths, not a list
    # containing both a directory and its descendants. Include empty leaves too.
    parents = {str(parent) for name in (*files, *folders) for parent in PurePosixPath(name).parents}
    _paths([*files, *(name for name in folders if name not in parents)])
    if set(files) != set(expected):
        raise ValidationError("evidence file inventory differs from its explicit seals")
    return tuple(sorted(files)), tuple(sorted(folders)), entries


def _overlap(first: Path, second: Path) -> bool:
    a, b = (path.as_posix().casefold().rstrip("/") for path in (first, second))
    return a == b or a.startswith(b + "/") or b.startswith(a + "/")


def _recorded_path(value: object) -> None:
    """Validate native local path syntax without opening a recorded old owner."""
    text = _text(value, "recorded authority owner path")
    paths = (PurePosixPath(text), PureWindowsPath(text))
    if (
        text.startswith(("//", "\\\\"))
        or "\x00" in text
        or not any(path.is_absolute() for path in paths)
        or any(".." in path.parts for path in paths)
    ):
        raise ValidationError("recorded authority owner path is not local absolute syntax")


def _authority_rows(records: Mapping[str, list[sqlite3.Row]]) -> None:
    for run in records["auth_runs"]:
        _text(run["run_id"], "recorded authority run ID")
        _hex(run["manifest_sha256"], "recorded authority manifest seal")
        _recorded_path(run["directory"])
        _recorded_path(run["ledger_path"])
        if type(run["historical"]) is not int or run["historical"] not in {0, 1}:
            raise ValidationError("invalid recorded historical owner flag")
        if run["historical"]:
            _hex(run["historical_ledger_sha256"], "recorded historical ledger seal")
            if run["runtime_sha256"] is not None:
                raise ValidationError("historical owner has an executing runtime binding")
        else:
            _hex(run["runtime_sha256"], "recorded executing runtime seal")
            if run["historical_ledger_sha256"] is not None:
                raise ValidationError("executing owner has a historical ledger binding")
    for operation in records["auth_operations"]:
        _text(operation["run_id"], "recorded operation owner")
        _text(operation["operation_id"], "recorded operation ID")
        _hex(operation["request_sha256"], "recorded request seal")
        _amount(operation["reserve_microusd"], "recorded authority reservation")
        status = operation["status"]
        if status not in {"reserved", "dispatched", "unknown", "completed"}:
            raise ValidationError("invalid recorded authority operation state")
        response = operation["response_json"]
        if response is not None:
            if type(response) is not str:
                raise ValidationError("recorded authority receipt is not JSON text")
            # Authority stores multiple receipt codecs. Validate their common
            # JSON boundary; selected legacy identity is checked against History.
            _object(_parse(response.encode("utf-8")))
        request_id = operation["provider_request_id"]
        if request_id is not None:
            _text(request_id, "recorded provider request ID")
        if status == "completed":
            _amount(operation["actual_microusd"], "recorded authority charge")
            if response is None or request_id is None:
                raise ValidationError("completed authority operation lacks its receipt identity")
        elif operation["actual_microusd"] is not None:
            raise ValidationError("unfinished authority operation has a terminal charge")
    for acceptance in records["auth_acceptances"]:
        for key in ("source_run_id", "operation_id", "continuation_run_id", "reason"):
            _text(acceptance[key], "recorded acceptance " + key)
        _hex(acceptance["evidence_sha256"], "recorded acceptance evidence seal")
    for deactivation in records["auth_deactivations"]:
        _text(deactivation["run_id"], "recorded deactivated run ID")
        _text(deactivation["reason"], "recorded deactivation reason")


def _limit(name: str) -> int:
    if name == "operations.sqlite3":
        return MAX_LEDGER_BYTES
    return MAX_MANIFEST_BYTES if name == "manifest.json" else MAX_FILE_BYTES


@dataclass(frozen=True)
class SealedRun:
    directory: Path
    files: Mapping[str, bytes] = field(repr=False)
    _directories: tuple[str, ...] = field(repr=False)

    def __post_init__(self) -> None:
        object.__setattr__(self, "files", MappingProxyType(dict(self.files)))

    def blob(self, name: str) -> bytes:
        if type(name) is not str or name not in self.files:
            raise ValidationError("requested evidence file is not explicitly sealed")
        return self.files[name]


@dataclass(frozen=True)
class SealedEvidence:
    runs: tuple[SealedRun, ...]
    authorization: bytes | None = field(repr=False)
    authorization_path: Path | None

    def run(self, directory: Path) -> SealedRun:
        if not isinstance(directory, Path) or not directory.is_absolute():
            raise ValidationError("run lookup requires an explicitly listed absolute path")
        for run in self.runs:
            if str(run.directory) == str(directory):
                return run
        raise ValidationError("requested run is not explicitly sealed")

    def finish(self) -> None:
        """Reject changed trees or bytes before returning a verification result."""
        try:
            total, entries = 0, 0
            for run in self.runs:
                names, folders, count = _tree(run.directory, run.files, 2 * MAX_FILES - entries)
                entries += count
                if folders != run._directories:
                    raise ValidationError("evidence directories changed during verification")
                for name in names:
                    raw = _read(run.directory / name, min(_limit(name), MAX_TOTAL_BYTES - total))
                    total += len(raw)
                    if raw != run.files[name]:
                        raise ValidationError("evidence bytes changed during verification")
            if self.authorization_path is not None:
                _sidecars(self.authorization_path)
                raw = _read(self.authorization_path, min(MAX_LEDGER_BYTES, MAX_TOTAL_BYTES - total))
                if raw != self.authorization:
                    raise ValidationError("authorization bytes changed during verification")
                _sidecars(self.authorization_path)
        except (OSError, ValueError, TypeError, RecursionError) as error:
            if isinstance(error, ValidationError):
                raise
            raise ValidationError("sealed evidence changed or could not be observed") from None


def read_search_evidence(directory: Path, *, evidence: dict[str, object]) -> SealedEvidence:
    """Consume a complete caller-sealed inventory once, with no inferred seals."""
    try:
        record = _object(evidence)
        if set(record) != {"format", "runs", "authorization"} or (
            record["format"] != "buddha.search-verification-input.v1"
        ):
            raise ValidationError("unsupported search verification input")
        if len(_canonical(record)) > MAX_MANIFEST_BYTES:
            raise ValidationError("verification input record exceeds its byte ceiling")
        runs = record["runs"]
        if type(runs) is not list or not 1 <= len(runs) <= MAX_RUNS:
            raise ValidationError("expected a bounded nonempty run list")
        selected: list[tuple[Path, dict[str, object]]] = []
        file_count = 0
        for value in runs:
            run = _object(value)
            if set(run) != {"directory", "files"}:
                raise ValidationError("invalid sealed run input")
            path = _absolute(run["directory"])
            files = _object(run["files"])
            file_count += len(files)
            if file_count > MAX_FILES or not {"manifest.json", "operations.sqlite3"} <= set(files):
                raise ValidationError("run inventory lacks required files or exceeds its ceiling")
            _paths(list(files))
            for digest in files.values():
                _hex(digest, "external file seal")
            selected.append((path, dict(files)))
        if not isinstance(directory, Path) or _absolute(str(directory)) != selected[0][0]:
            raise ValidationError("main run differs from the first explicitly sealed root")
        for index, (path, _) in enumerate(selected):
            for prior, _ in selected[:index]:
                if _overlap(path, prior):
                    raise ValidationError("evidence run roots overlap or alias")
        authority_path = None
        authority_seal = None
        if record["authorization"] is not None:
            authority = _object(record["authorization"])
            if set(authority) != {"path", "sha256"}:
                raise ValidationError("authorization requires an explicit path and seal")
            authority_path = _absolute(authority["path"])
            _hex(authority["sha256"], "external authorization seal")
            authority_seal = authority["sha256"]
            if any(_overlap(authority_path, root) for root, _ in selected):
                raise ValidationError("authorization must be separate from sealed run trees")
        snapshots, total, entries = [], 0, 0
        for path, seals in selected:
            names, folders, count = _tree(path, seals, 2 * MAX_FILES - entries)
            entries += count
            blobs = {}
            for name in names:
                raw = _read(path / name, min(_limit(name), MAX_TOTAL_BYTES - total))
                if hashlib.sha256(raw).hexdigest() != seals[name]:
                    raise ValidationError("consumed evidence differs from its external seal")
                total += len(raw)
                blobs[name] = raw
            snapshots.append(SealedRun(path, blobs, folders))
        authority_raw = None
        if authority_path is not None:
            _sidecars(authority_path)
            authority_raw = _read(authority_path, min(MAX_LEDGER_BYTES, MAX_TOTAL_BYTES - total))
            if hashlib.sha256(authority_raw).hexdigest() != authority_seal:
                raise ValidationError("consumed authorization differs from its external seal")
            _sidecars(authority_path)
        result = SealedEvidence(tuple(snapshots), authority_raw, authority_path)
        result.finish()
        return result
    except (OSError, ValueError, TypeError, RecursionError) as error:
        if isinstance(error, ValidationError):
            raise
        raise ValidationError("search evidence could not be read consistently") from None


def read_authority(raw: bytes) -> dict[str, object]:
    """Decode only supplied authority bytes; recorded source paths remain data."""
    try:
        if type(raw) is not bytes or len(raw) > MAX_LEDGER_BYTES:
            raise ValidationError("authorization snapshot is not bounded bytes")
        with closing(sqlite3.connect(":memory:")) as connection:
            connection.deserialize(raw)
            connection.row_factory = sqlite3.Row
            connection.execute("PRAGMA query_only=ON")
            connection.execute("PRAGMA trusted_schema=OFF")
            connection.execute("BEGIN")
            config = _validate(connection, "main")
            if connection.execute("PRAGMA foreign_key_check").fetchone():
                raise ValidationError("authorization snapshot contains orphan records")
            count = 0
            records = {}
            for table, query in (
                ("auth_runs", "SELECT * FROM auth_runs LIMIT ?"),
                ("auth_operations", "SELECT * FROM auth_operations LIMIT ?"),
                ("auth_acceptances", "SELECT * FROM auth_acceptances LIMIT ?"),
                ("auth_deactivations", "SELECT * FROM auth_deactivations LIMIT ?"),
            ):
                rows = connection.execute(query, (MAX_ROWS + 1,)).fetchall()
                count += len(rows)
                if count > MAX_ROWS:
                    raise ValidationError("authorization snapshot exceeds its row ceiling")
                records[table] = rows
            _authority_rows(records)
            result = {
                "config": dict(config),
                **{table: [dict(row) for row in rows] for table, rows in records.items()},
                "totals": _totals(records["auth_operations"]),
            }
            connection.rollback()
        # Only JSON-valued rows leave the connection, with no live storage object.
        return _object(_parse(_canonical(result)))
    except (OSError, sqlite3.Error, ValueError, TypeError, RecursionError, OverflowError) as error:
        if isinstance(error, ValidationError):
            raise
        raise ValidationError("authorization snapshot could not be decoded consistently") from None
