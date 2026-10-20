"""Read sealed raw Gateway records without their retired executing runtime.

Only recorded identity/accounting consistency is checked. No current evaluator,
rate recomputation, credential, source reconstruction or spending permission.
"""

import base64
import hashlib
import re
import sqlite3
from contextlib import closing
from dataclasses import dataclass, field
from pathlib import Path, PurePosixPath, PureWindowsPath
from typing import cast

from buddha.authorization import _BINDING_SCHEMA
from buddha.common import ValidationError, _canonical, _hex, _integer, _object, _parse, _text
from buddha.gateway import CAPABILITIES, FORMAT, GatewayCall
from buddha.history import _inactive, _plain
from buddha.ledger import _SCHEMA, _SCHEMA_V2, _expected_schema, _schema_signature
from buddha.releases import MAX_JSON_BYTES, ROLES, Selection, file_hash
from buddha.wire import MAX_BODY_BYTES, RawEnvelope

MAX_LEDGER_BYTES = 512 * 1024**2
MAX_RECEIPT_BYTES = 64 * 1024**2
MAX_OPERATIONS = 100_000


class GatewayHistoryError(ValidationError):
    """Stored raw evidence is not the supplied stable, bounded, consistent snapshot."""


def _sha(value: object) -> str:
    return hashlib.sha256(_canonical(value)).hexdigest()


def _amount(value: object) -> int:
    result = _integer(value, "recorded amount", 0)
    if result > 2**63 - 1:
        raise GatewayHistoryError("recorded amount exceeds SQLite's integer range")
    return result


def _path(value: object) -> str:
    text = _text(value, "recorded absolute path")
    if not (PurePosixPath(text).is_absolute() or PureWindowsPath(text).is_absolute()):
        raise GatewayHistoryError("recorded path is not absolute")
    return text


def _sealed(path: Path, digest: str, maximum: int) -> bytes:
    _plain(path)
    if file_hash(path, max_bytes=maximum) != digest:
        raise GatewayHistoryError("historical file seal differs")
    with path.open("rb") as stream:
        raw = stream.read(maximum + 1)
    if len(raw) > maximum or hashlib.sha256(raw).hexdigest() != digest:
        raise GatewayHistoryError("consumed historical file differs from its seal")
    return raw


@dataclass(frozen=True)
class HistoricalGatewayOperation:
    operation_id: str
    request_sha256: str
    reserve_microusd: int
    status: str
    actual_microusd: int | None
    provider_request_id: str | None
    receipt_json: str | None = field(repr=False)
    checkpoint_json: str | None = field(repr=False)
    checkpoint_request_id: str | None

    @property
    def receipt(self) -> dict[str, object] | None:
        return None if self.receipt_json is None else _object(_parse(self.receipt_json.encode()))

    @property
    def checkpoint(self) -> dict[str, object] | None:
        return (
            None if self.checkpoint_json is None else _object(_parse(self.checkpoint_json.encode()))
        )


@dataclass(frozen=True)
class GatewayHistory:
    run_id: str
    manifest_sha256: str
    ledger_sha256: str
    budget_microusd: int
    max_calls: int
    operations: tuple[HistoricalGatewayOperation, ...]
    manifest_json: str = field(repr=False)

    @property
    def manifest(self) -> dict[str, object]:
        return _object(_parse(self.manifest_json.encode()))

    def totals(self) -> dict[str, int]:
        spent = sum(
            item.actual_microusd or 0 for item in self.operations if item.status == "completed"
        )
        held = sum(item.reserve_microusd for item in self.operations if item.status != "completed")
        return {
            "committed_microusd": spent + held,
            "spent_microusd": spent,
            "reserved_microusd": held,
            "operation_count": len(self.operations),
        }


def _manifest(raw: bytes, expected: str) -> dict[str, object]:
    record = _object(_parse(raw))
    checksum = record.pop("record_sha256", None)
    if checksum != expected or _sha(record) != expected:
        raise GatewayHistoryError("historical manifest content seal differs")
    if (
        set(record)
        != {
            "format",
            "run_id",
            "settings",
            "selection",
            "selection_sha256",
            "roots",
            "profiles",
            "core",
            "runtime",
            "execution_sha256",
            "invocation",
            "review",
            "authorization_path",
        }
        or record["format"] != FORMAT
    ):
        raise GatewayHistoryError("unsupported historical Gateway manifest")
    _text(record["run_id"], "recorded run ID")
    settings = _object(record["settings"])
    if set(settings) != {"budget_microusd", "max_calls"}:
        raise GatewayHistoryError("invalid recorded ceilings")
    for value in settings.values():
        _amount(value)
    selection = Selection.from_bytes(_canonical(record["selection"]))
    if selection.fingerprint() != record["selection_sha256"]:
        raise GatewayHistoryError("recorded selected component identity differs")
    roots = _object(record["roots"])
    if set(roots) != ROLES:
        raise GatewayHistoryError("invalid recorded component roots")
    for value in [*roots.values(), record["authorization_path"]]:
        _path(value)
    for name in ("core", "runtime"):
        mapping = _object(record[name])
        if not 1 <= len(mapping) <= 128:
            raise GatewayHistoryError("invalid recorded host inventory")
        for key, value in mapping.items():
            if name == "core":
                if not re.fullmatch(r"buddha(?:\.[A-Za-z_]\w*)*", key, flags=re.ASCII):
                    raise GatewayHistoryError("invalid recorded host module name")
                _hex(value, "recorded source digest")
            else:
                _text(value, "recorded runtime metadata")
    # Stored core names are data. Comparing with today's CORE would make old
    # evidence unreadable precisely when a host dependency has been retired.
    invocation = _object(record["invocation"])
    if set(invocation) != {"id", "inputs"}:
        raise GatewayHistoryError("invalid recorded invocation")
    _text(invocation["id"], "recorded invocation ID")
    inputs = invocation["inputs"]
    if type(inputs) is not list or not 1 <= len(inputs) <= 1024:
        raise GatewayHistoryError("invalid recorded input inventory")
    seen = set()
    for value in inputs:
        item = _object(value)
        if set(item) != {"path", "sha256"} or _path(item["path"]) in seen:
            raise GatewayHistoryError("invalid recorded input")
        seen.add(item["path"])
        _hex(item["sha256"], "recorded input digest")
    if record["execution_sha256"] != _sha(
        {key: record[key] for key in ("selection_sha256", "core", "runtime", "invocation")}
    ):
        raise GatewayHistoryError("recorded execution identity differs")
    _object(record["profiles"])
    _object(record["review"])
    return record


def _receipt(value: object, row: sqlite3.Row, manifest: dict[str, object]) -> RawEnvelope | None:
    if value is None:
        return None
    if type(value) is not str or len(value.encode()) > MAX_RECEIPT_BYTES:
        raise GatewayHistoryError("historical raw receipt exceeds its declared ceiling")
    receipt = _object(_parse(value.encode()))
    if (
        set(receipt) != {"format", "request", "envelope"}
        or receipt["format"] != "buddha.gateway-receipt.v1"
    ):
        raise GatewayHistoryError("invalid historical raw receipt")
    request = _object(receipt["request"])
    keys = {"capability", "profile_id", "logical_id", "attempt", "body_base64"}
    if set(request) not in (keys, keys | {"headers"}):
        raise GatewayHistoryError("invalid historical raw request")
    encoded = request["body_base64"]
    if type(encoded) is not str or len(encoded) > 4 * ((MAX_BODY_BYTES + 2) // 3):
        raise GatewayHistoryError("invalid historical request byte ceiling")
    body = base64.b64decode(encoded, validate=True)
    headers = request.get("headers", [])
    if type(headers) is not list or any(
        type(pair) is not list or len(pair) != 2 for pair in headers
    ):
        raise GatewayHistoryError("invalid historical request headers")
    call = GatewayCall(
        cast(str, request["capability"]),
        cast(str, request["profile_id"]),
        cast(str, request["logical_id"]),
        cast(int, request["attempt"]),
        body,
        tuple((pair[0], pair[1]) for pair in headers),
    )
    if call.to_record() != request:
        raise GatewayHistoryError("historical request encoding is not canonical")
    profile = _object(_object(_object(manifest["profiles"])[call.capability])["profiles"])[
        call.profile_id
    ]
    operation_id = _sha(
        [
            "buddha.gateway-attempt.v1",
            manifest["run_id"],
            manifest["invocation"],
            call.logical_id,
            call.attempt,
        ]
    )
    request_hash = _sha(
        [
            "buddha.gateway-request.v1",
            manifest["execution_sha256"],
            manifest["selection_sha256"],
            _sha(profile),
            call.to_record(),
        ]
    )
    if operation_id != row["operation_id"] or request_hash != row["request_sha256"]:
        raise GatewayHistoryError("raw receipt differs from its recorded physical request")
    envelope = RawEnvelope.from_record(receipt["envelope"])
    if envelope.provider != CAPABILITIES[call.capability][0]:
        raise GatewayHistoryError("raw response provider differs from its request")
    return envelope


def _operation(row: sqlite3.Row, manifest: dict[str, object]) -> HistoricalGatewayOperation:
    for name in ("operation_id", "request_sha256"):
        _hex(row[name], "recorded operation digest")
    reserve = _amount(row["reserve_microusd"])
    status = row["status"]
    if status not in {"reserved", "dispatched", "completed", "unknown"}:
        raise GatewayHistoryError("unsupported recorded operation state")
    checkpoint = _receipt(row["checkpoint_json"], row, manifest)
    checkpoint_id = row["checkpoint_request_id"]
    if checkpoint_id is not None:
        _text(checkpoint_id, "recorded uncertain request ID")
    if row["checkpoint_operation_id"] is not None and (
        status not in {"completed", "unknown"} or checkpoint is None and checkpoint_id is None
    ):
        raise GatewayHistoryError("invalid historical receipt checkpoint")
    envelope = _receipt(row["response_json"], row, manifest)
    actual, request_id = row["actual_microusd"], row["provider_request_id"]
    if status == "completed":
        actual = _amount(actual)
        _text(request_id, "recorded terminal request ID")
        if envelope is None or envelope.provider_request_id != request_id:
            raise GatewayHistoryError("completed receipt identity differs")
    elif actual is not None or envelope is not None or request_id is not None:
        raise GatewayHistoryError("unfinished operation contains terminal fields")
    return HistoricalGatewayOperation(
        row["operation_id"],
        row["request_sha256"],
        reserve,
        status,
        actual,
        request_id,
        row["response_json"],
        row["checkpoint_json"],
        checkpoint_id,
    )


def _database(
    raw: bytes, manifest: dict[str, object], manifest_hash: str
) -> tuple[HistoricalGatewayOperation, ...]:
    # Consume exactly the sealed bytes. An immutable file connection intentionally
    # ignores writer locks and could otherwise observe transient unsealed content.
    with closing(sqlite3.connect(":memory:")) as connection:
        connection.deserialize(raw)
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA query_only=ON")
        connection.execute("PRAGMA trusted_schema=OFF")
        version = connection.execute("PRAGMA user_version").fetchone()[0]
        if version not in {1, 2}:
            raise GatewayHistoryError("unsupported historical raw ledger schema")
        binding = connection.execute(
            "SELECT 1 FROM sqlite_master WHERE type='table' AND name='authorization_binding'"
        ).fetchone()
        statements = [
            *_SCHEMA,
            *(_SCHEMA_V2 if version == 2 else []),
            *(_BINDING_SCHEMA if binding else ()),
        ]
        if _schema_signature(connection) != _expected_schema(tuple(statements)):
            raise GatewayHistoryError("historical raw ledger schema differs")
        if connection.execute("PRAGMA foreign_key_check").fetchone():
            raise GatewayHistoryError("historical raw ledger has orphan evidence")
        settings = _object(manifest["settings"])
        config = connection.execute("SELECT * FROM run_config").fetchall()
        if len(config) != 1 or tuple(config[0]) != (
            1,
            manifest["run_id"],
            manifest_hash,
            settings["budget_microusd"],
            settings["max_calls"],
        ):
            raise GatewayHistoryError("raw ledger does not match its sealed manifest")
        count = connection.execute("SELECT COUNT(*) FROM operations").fetchone()[0]
        if count > MAX_OPERATIONS or count and not binding:
            raise GatewayHistoryError("unbound or oversized historical operation population")
        if binding:
            rows = connection.execute("SELECT * FROM authorization_binding").fetchall()
            if len(rows) != 1 or rows[0]["singleton"] != 1 or rows[0]["schema_version"] != 1:
                raise GatewayHistoryError("invalid recorded authority binding")
            _text(rows[0]["authorization_id"], "recorded authorization ID")
            _hex(rows[0]["terms_sha256"], "recorded authority terms")
            if rows[0]["authority_path"] != manifest["authorization_path"]:
                raise GatewayHistoryError("recorded authority path differs")
        size_queries = [
            "SELECT 1 FROM operations WHERE length(CAST(response_json AS BLOB))>? LIMIT 1"
        ]
        if version == 2:
            size_queries.append(
                "SELECT 1 FROM unknown_receipts WHERE length(CAST(response_json AS BLOB))>? LIMIT 1"
            )
        for query in size_queries:
            if connection.execute(query, (MAX_RECEIPT_BYTES,)).fetchone():
                raise GatewayHistoryError("historical receipt exceeds its byte ceiling")
        query = (
            "SELECT o.*,u.operation_id AS checkpoint_operation_id,"
            "u.response_json AS checkpoint_json,u.provider_request_id AS checkpoint_request_id "
            "FROM operations o LEFT JOIN unknown_receipts u USING(operation_id) "
            "ORDER BY o.operation_id"
            if version == 2
            else "SELECT o.*,NULL AS checkpoint_operation_id,NULL AS checkpoint_json,"
            "NULL AS checkpoint_request_id FROM operations o ORDER BY o.operation_id"
        )
        return tuple(_operation(row, manifest) for row in connection.execute(query))


def read_gateway_history(
    directory: Path, *, manifest_sha256: str, ledger_sha256: str
) -> GatewayHistory:
    """Read exact supplied seals; never install, execute, migrate or authorize."""
    try:
        if not isinstance(directory, Path):
            raise GatewayHistoryError("historical Gateway directory must be a Path")
        _hex(manifest_sha256, "expected manifest digest")
        _hex(ledger_sha256, "expected ledger digest")
        directory = directory.absolute()
        _plain(directory)
        _inactive(directory)
        manifest_path, ledger_path = directory / "manifest.json", directory / "operations.sqlite3"
        manifest_file_hash = file_hash(manifest_path, max_bytes=MAX_JSON_BYTES)
        raw_manifest = _sealed(manifest_path, manifest_file_hash, MAX_JSON_BYTES)
        manifest = _manifest(raw_manifest, manifest_sha256)
        raw_ledger = _sealed(ledger_path, ledger_sha256, MAX_LEDGER_BYTES)
        operations = _database(raw_ledger, manifest, manifest_sha256)
        _inactive(directory)
        _plain(directory)
        if (
            file_hash(manifest_path) != manifest_file_hash
            or file_hash(ledger_path) != ledger_sha256
        ):
            raise GatewayHistoryError("historical evidence changed during observation")
        settings = _object(manifest["settings"])
        return GatewayHistory(
            _text(manifest["run_id"], "recorded run ID"),
            manifest_sha256,
            ledger_sha256,
            _amount(settings["budget_microusd"]),
            _amount(settings["max_calls"]),
            operations,
            _canonical(manifest).decode(),
        )
    except (OSError, sqlite3.Error, ValueError, TypeError, KeyError, RecursionError) as error:
        if isinstance(error, GatewayHistoryError):
            raise
        raise GatewayHistoryError(
            "historical raw evidence is not a consistent sealed snapshot"
        ) from None
