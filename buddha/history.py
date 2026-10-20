"""Read operator-sealed historical receipts without migrating or changing evidence.

Seals establish consistency with preserved local bytes, not provider origin or
permission to spend. An unknown receipt remains uncertain even when it has text.
"""

import hashlib
import sqlite3
import stat
from contextlib import closing
from dataclasses import dataclass
from pathlib import Path

from buddha.common import ValidationError, _canonical, _hex, _integer, _object, _parse, _text
from buddha.ledger import (
    _BINDING_SCHEMA,
    _SCHEMA,
    _SCHEMA_V2,
    _expected_schema,
    _schema_signature,
)
from buddha.provider import Reply

MAX_MANIFEST_BYTES = 32 * 1024**2
MAX_LEDGER_BYTES = 512 * 1024**2


@dataclass(frozen=True)
class HistoricalOperation:
    operation_id: str
    request_sha256: str
    reserve_microusd: int
    status: str
    reply: Reply | None
    actual_microusd: int | None
    provider_request_id: str | None
    uncertainty_reply: Reply | None = None
    uncertainty_request_id: str | None = None


@dataclass(frozen=True)
class History:
    run_id: str
    manifest_sha256: str
    ledger_sha256: str
    budget_microusd: int
    max_calls: int
    operations: tuple[HistoricalOperation, ...]
    manifest_json: str

    @property
    def manifest(self) -> dict[str, object]:
        """Each access returns an independent copy, including nested objects."""
        return _object(_parse(self.manifest_json.encode("utf-8")))

    def totals(self) -> dict[str, int]:
        spent = sum(
            item.actual_microusd or 0 for item in self.operations if item.status == "completed"
        )
        reserved = sum(
            item.reserve_microusd for item in self.operations if item.status != "completed"
        )
        return {
            "committed_microusd": spent + reserved,
            "spent_microusd": spent,
            "reserved_microusd": reserved,
            "operation_count": len(self.operations),
        }


def _amount(value: object, name: str) -> int:
    result = _integer(value, name, 0)
    if result > 2**63 - 1:
        raise ValidationError(f"{name} exceeds SQLite's integer range")
    return result


def _plain(path: Path) -> None:
    """Reject links before resolving any component, including Windows junctions."""
    for component in (path, *path.parents):
        information = component.lstat()
        if stat.S_ISLNK(information.st_mode) or (
            getattr(information, "st_file_attributes", 0)
            & getattr(stat, "FILE_ATTRIBUTE_REPARSE_POINT", 0x400)
        ):
            raise ValidationError(
                "historical evidence paths must not contain links or reparse points"
            )


def _inactive(directory: Path) -> None:
    lock = directory / ".search.lock"
    if lock.exists() or lock.is_symlink():
        raise ValidationError("historical source has a search lock; review its writer first")
    for suffix in ("-wal", "-journal", "-shm"):
        path = directory / ("operations.sqlite3" + suffix)
        if path.exists() or path.is_symlink():
            _plain(path)
            if not path.is_file() or path.stat().st_size:
                raise ValidationError("historical source has an active SQLite sidecar")


def _bounded_read(path: Path, maximum: int) -> bytes:
    if path.stat().st_size > maximum:
        raise ValidationError("historical evidence exceeds its byte ceiling")
    with path.open("rb") as stream:
        raw = stream.read(maximum + 1)
    if len(raw) > maximum:
        raise ValidationError("historical evidence exceeds its byte ceiling")
    return raw


def _reply(value: object) -> Reply | None:
    if value is None:
        return None
    if not isinstance(value, str):
        raise ValidationError("historical reply must be stored JSON text")
    return Reply.from_record(_parse(value.encode("utf-8")))


def _operation(row: sqlite3.Row) -> HistoricalOperation:
    operation_id = _text(row["operation_id"], "historical operation ID")
    request_hash = row["request_sha256"]
    _hex(request_hash, "historical request hash")
    request_hash = _text(request_hash, "historical request hash")
    reserve = _amount(row["reserve_microusd"], "historical reservation")
    status = row["status"]
    if status not in {"reserved", "dispatched", "completed", "unknown"}:
        raise ValidationError("unsupported historical operation state")
    reply = _reply(row["response_json"])
    uncertainty_reply = _reply(row["uncertainty_json"])
    request_id = row["provider_request_id"]
    if request_id is not None:
        request_id = _text(request_id, "historical provider request ID")
    uncertainty_id = row["uncertainty_request_id"]
    if uncertainty_id is not None:
        uncertainty_id = _text(uncertainty_id, "historical uncertainty request ID")
    actual = row["actual_microusd"]
    if status == "completed":
        actual = _amount(actual, "historical actual cost")
        if reply is None or not request_id or reply.provider_request_id != request_id:
            raise ValidationError("completed historical receipt identity is inconsistent")
    elif actual is not None or reply is not None or request_id is not None:
        raise ValidationError("unfinished historical operation has completed fields")
    if row["unknown_operation_id"] is not None:
        if status not in {"unknown", "completed"}:
            raise ValidationError("unknown receipt is attached to another operation state")
        if uncertainty_reply is None and uncertainty_id is None:
            raise ValidationError("unknown historical receipt contains no evidence")
    if status == "unknown":
        reply, request_id = uncertainty_reply, uncertainty_id
    return HistoricalOperation(
        operation_id,
        request_hash,
        reserve,
        status,
        reply,
        actual,
        request_id,
        uncertainty_reply,
        uncertainty_id,
    )


def _read_database(
    raw: bytes, run_id: str, manifest_hash: str, budget: int, max_calls: int
) -> tuple[HistoricalOperation, ...]:
    # Query the exact sealed bytes rather than reopening an unlocked file that
    # could transiently change and be restored before the final seal check.
    with closing(sqlite3.connect(":memory:")) as connection:
        connection.deserialize(raw)
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA query_only=ON")
        connection.execute("PRAGMA trusted_schema=OFF")
        connection.execute("BEGIN")
        version = connection.execute("PRAGMA user_version").fetchone()[0]
        if version not in {1, 2}:
            raise ValidationError("unsupported historical ledger schema")
        binding = connection.execute(
            "SELECT 1 FROM sqlite_master WHERE type='table' AND name='authorization_binding'"
        ).fetchone()
        statements = (
            *_SCHEMA,
            *(_SCHEMA_V2 if version == 2 else ()),
            *(_BINDING_SCHEMA if binding else ()),
        )
        if _schema_signature(connection) != _expected_schema(statements):
            raise ValidationError("historical ledger schema differs from its trusted definition")
        if connection.execute("PRAGMA foreign_key_check").fetchone():
            raise ValidationError("historical ledger contains orphan evidence")
        if binding:
            rows = connection.execute("SELECT * FROM authorization_binding").fetchall()
            if len(rows) != 1 or rows[0]["singleton"] != 1 or rows[0]["schema_version"] != 1:
                raise ValidationError("invalid historical authority binding")
            _text(rows[0]["authorization_id"], "historical authorization ID")
            _text(rows[0]["authority_path"], "historical authority path")
            _hex(rows[0]["terms_sha256"], "historical authority terms")
        config = connection.execute(
            "SELECT singleton,run_id,manifest_sha256,budget_microusd,max_calls FROM run_config"
        ).fetchall()
        if len(config) != 1 or tuple(config[0]) != (1, run_id, manifest_hash, budget, max_calls):
            raise ValidationError("historical ledger does not match the sealed manifest")
        if version == 2:
            query = (
                "SELECT o.*,r.operation_id AS unknown_operation_id,"
                "r.response_json AS uncertainty_json,"
                "r.provider_request_id AS uncertainty_request_id "
                "FROM operations o LEFT JOIN unknown_receipts r USING(operation_id) "
                "ORDER BY o.operation_id"
            )
        else:
            query = (
                "SELECT *,NULL AS unknown_operation_id,NULL AS uncertainty_json,"
                "NULL AS uncertainty_request_id FROM operations ORDER BY operation_id"
            )
        operations = tuple(_operation(row) for row in connection.execute(query))
        if len({item.operation_id for item in operations}) != len(operations):
            raise ValidationError("duplicate historical operation identity")
        connection.rollback()
        return operations


def read_history(directory: Path, *, manifest_sha256: str, ledger_sha256: str) -> History:
    """Read a stable sealed snapshot, independent of the currently installed source.

    The manifest seal is its canonical content hash, excluding record_sha256;
    the ledger seal is the SHA256 of the complete SQLite file. Neither is inferred
    from the source when missing: a caller must supply both preserved seals.
    """
    _hex(manifest_sha256, "expected historical manifest hash")
    _hex(ledger_sha256, "expected historical ledger hash")
    if not isinstance(directory, Path):
        raise ValidationError("historical directory must be a filesystem Path")
    try:
        directory = directory.absolute()
        _plain(directory)
        if not directory.is_dir():
            raise ValidationError("historical source is not a directory")
        manifest_path, ledger_path = directory / "manifest.json", directory / "operations.sqlite3"
        for path in (manifest_path, ledger_path):
            _plain(path)
            if not path.is_file():
                raise ValidationError("historical evidence must be regular files")
        _inactive(directory)
        manifest_bytes = _bounded_read(manifest_path, MAX_MANIFEST_BYTES)
        manifest = _object(_parse(manifest_bytes))
        checksum = manifest.pop("record_sha256", None)
        canonical = _canonical(manifest)
        if checksum != manifest_sha256 or hashlib.sha256(canonical).hexdigest() != manifest_sha256:
            raise ValidationError("historical manifest seal differs")
        if manifest.get("format") != "buddha.policy-search.v1":
            raise ValidationError("unsupported historical manifest")
        run_id = _text(manifest.get("run_id"), "historical run ID")
        settings = _object(manifest.get("settings"))
        budget = _amount(settings.get("budget_microusd"), "historical budget")
        max_calls = _amount(settings.get("max_calls"), "historical call cap")
        ledger_bytes = _bounded_read(ledger_path, MAX_LEDGER_BYTES)
        if hashlib.sha256(ledger_bytes).hexdigest() != ledger_sha256:
            raise ValidationError("historical ledger seal differs")
        operations = _read_database(ledger_bytes, run_id, manifest_sha256, budget, max_calls)
        _inactive(directory)
        for path in (directory, manifest_path, ledger_path):
            _plain(path)
        if _bounded_read(manifest_path, MAX_MANIFEST_BYTES) != manifest_bytes or (
            hashlib.sha256(_bounded_read(ledger_path, MAX_LEDGER_BYTES)).hexdigest()
            != ledger_sha256
        ):
            raise ValidationError("historical evidence changed during observation")
        return History(
            run_id,
            manifest_sha256,
            ledger_sha256,
            budget,
            max_calls,
            operations,
            canonical.decode("utf-8"),
        )
    except (OSError, sqlite3.Error, UnicodeError, ValueError, TypeError, RecursionError) as error:
        if isinstance(error, ValidationError):
            raise
        raise ValidationError("historical evidence could not be read consistently") from None
