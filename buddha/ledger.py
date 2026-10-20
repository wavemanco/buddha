"""Host-owned SQLite reservations and durable replay; never sends provider requests.

One database belongs to one immutable run. Dispatched/unknown operations retain
their full reservation until reconciled. Response payloads must already exclude
credentials and request headers; event records contain accounting metadata only.

Schema 2 appends immutable unknown receipts to schema 1. Safe rollback, inside
BEGIN IMMEDIATE: first require SELECT COUNT(*) FROM unknown_receipts to be zero,
then DROP TABLE unknown_receipts and PRAGMA user_version=1 before COMMIT. Refuse
rollback when any receipt exists; preserve that evidence and use a forward fix.
Reopening a schema-1 ledger applies the append-only schema-2 upgrade atomically.
"""

import json
import sqlite3
from collections.abc import Iterator
from contextlib import closing, contextmanager
from dataclasses import dataclass
from functools import cache
from pathlib import Path
from typing import cast

from buddha.common import ValidationError, _hex, _integer, _text


class BudgetExceeded(ValidationError):
    """A cap or reservation was exceeded; no further spend is authorized."""


class OperationConflict(ValidationError):
    """A run identity, operation identity, or state transition conflicts."""


class UnknownOperation(ValidationError):
    """The operation has never been reserved in this run."""


@dataclass(frozen=True)
class Operation:
    operation_id: str
    request_sha256: str
    reserve_microusd: int
    status: str
    response: dict[str, object] | None
    actual_microusd: int | None
    provider_request_id: str | None


_SCHEMA = [
    """CREATE TABLE run_config (
        singleton INTEGER PRIMARY KEY CHECK(singleton=1), run_id TEXT NOT NULL,
        manifest_sha256 TEXT NOT NULL, budget_microusd INTEGER NOT NULL CHECK(budget_microusd>=0),
        max_calls INTEGER NOT NULL CHECK(max_calls>=0))""",
    """CREATE TABLE operations (
        operation_id TEXT PRIMARY KEY, request_sha256 TEXT NOT NULL,
        reserve_microusd INTEGER NOT NULL CHECK(reserve_microusd>=0),
        status TEXT NOT NULL CHECK(status IN ('reserved','dispatched','completed','unknown')),
        response_json TEXT, actual_microusd INTEGER CHECK(actual_microusd>=0),
        provider_request_id TEXT,
        CHECK((status='completed' AND response_json IS NOT NULL AND actual_microusd IS NOT NULL
               AND provider_request_id IS NOT NULL) OR
              (status!='completed' AND response_json IS NULL AND actual_microusd IS NULL
               AND provider_request_id IS NULL)))""",
    """CREATE TABLE events (
        event_id INTEGER PRIMARY KEY, event_type TEXT NOT NULL,
        operation_id TEXT REFERENCES operations(operation_id), reserved_microusd INTEGER,
        actual_microusd INTEGER,
        created_at TEXT NOT NULL DEFAULT(strftime('%Y-%m-%dT%H:%M:%fZ','now')))""",
    """CREATE TRIGGER events_no_update BEFORE UPDATE ON events BEGIN
        SELECT RAISE(ABORT, 'events are append-only'); END""",
    """CREATE TRIGGER events_no_delete BEFORE DELETE ON events BEGIN
        SELECT RAISE(ABORT, 'events are append-only'); END""",
    """CREATE TRIGGER run_config_no_update BEFORE UPDATE ON run_config BEGIN
        SELECT RAISE(ABORT, 'run configuration is immutable'); END""",
    """CREATE TRIGGER run_config_no_delete BEFORE DELETE ON run_config BEGIN
        SELECT RAISE(ABORT, 'run configuration is immutable'); END""",
    """CREATE TRIGGER operations_no_delete BEFORE DELETE ON operations BEGIN
        SELECT RAISE(ABORT, 'operation history is permanent'); END""",
    """CREATE TRIGGER completed_no_update BEFORE UPDATE ON operations
        WHEN OLD.status='completed' BEGIN
        SELECT RAISE(ABORT, 'completed operations are immutable'); END""",
    """CREATE TRIGGER operation_identity_no_update BEFORE UPDATE OF
        operation_id, request_sha256, reserve_microusd ON operations BEGIN
        SELECT RAISE(ABORT, 'operation identity is immutable'); END""",
]


_SCHEMA_V2 = [
    """CREATE TABLE unknown_receipts (
        operation_id TEXT PRIMARY KEY REFERENCES operations(operation_id),
        response_json TEXT, provider_request_id TEXT,
        CHECK(response_json IS NOT NULL OR provider_request_id IS NOT NULL))""",
    """CREATE TRIGGER unknown_receipts_no_update BEFORE UPDATE ON unknown_receipts BEGIN
        SELECT RAISE(ABORT, 'unknown receipts are immutable'); END""",
    """CREATE TRIGGER unknown_receipts_no_delete BEFORE DELETE ON unknown_receipts BEGIN
        SELECT RAISE(ABORT, 'unknown receipts are immutable'); END""",
]


_BINDING_SCHEMA = (
    "CREATE TABLE main.authorization_binding ("
    "singleton INTEGER PRIMARY KEY CHECK(singleton=1), "
    "schema_version INTEGER NOT NULL CHECK(schema_version=1), "
    "authorization_id TEXT NOT NULL, authority_path TEXT NOT NULL, "
    "terms_sha256 TEXT NOT NULL)",
    *(
        f"CREATE TRIGGER main.authorization_binding_no_{action.lower()} "
        f"BEFORE {action} ON authorization_binding BEGIN "
        "SELECT RAISE(ABORT,'authority binding is immutable'); END"
        for action in ("UPDATE", "DELETE")
    ),
)


def _schema_signature(
    connection: sqlite3.Connection, schema: str = "main"
) -> tuple[tuple[str, str, str, str | None], ...]:
    queries = {
        "main": "SELECT type,name,tbl_name,sql FROM main.sqlite_master "
        "WHERE name NOT GLOB 'sqlite_*' ORDER BY type,name",
        "funding": "SELECT type,name,tbl_name,sql FROM funding.sqlite_master "
        "WHERE name NOT GLOB 'sqlite_*' ORDER BY type,name",
    }
    return tuple(tuple(row) for row in connection.execute(queries[schema]))


@cache
def _expected_schema(statements: tuple[str, ...]) -> tuple[tuple[str, str, str, str | None], ...]:
    """Let SQLite normalize trusted DDL exactly as it does durable databases."""
    with closing(sqlite3.connect(":memory:")) as connection:
        for statement in statements:
            connection.execute(statement)
        return _schema_signature(connection)


def _amount(value: object, name: str) -> int:
    amount = _integer(value, name, 0)
    if amount > (1 << 63) - 1:
        raise ValidationError(f"{name} exceeds SQLite's integer range")
    return amount


def _response_json(response: object) -> str:
    if not isinstance(response, dict):
        raise ValidationError("response must be a JSON object")
    try:
        encoded = json.dumps(response, sort_keys=True, separators=(",", ":"), allow_nan=False)
        if json.loads(encoded) != response:
            raise ValidationError("response must use JSON values and string object keys")
        return encoded
    except (ValueError, TypeError, RecursionError) as error:
        raise ValidationError("response must be a finite, serializable JSON object") from error


def _operation(row: sqlite3.Row) -> Operation:
    try:
        response = None if row["response_json"] is None else json.loads(row["response_json"])
    except (ValueError, TypeError) as error:
        raise ValidationError("stored response is corrupt") from error
    return Operation(
        row["operation_id"],
        row["request_sha256"],
        row["reserve_microusd"],
        row["status"],
        cast(dict[str, object] | None, response),
        row["actual_microusd"],
        row["provider_request_id"],
    )


def _find(connection: sqlite3.Connection, operation_id: str) -> sqlite3.Row | None:
    return cast(
        sqlite3.Row | None,
        connection.execute(
            "SELECT o.operation_id,o.request_sha256,o.reserve_microusd,o.status,o.actual_microusd,"
            "CASE WHEN o.status='unknown' THEN r.response_json ELSE o.response_json END "
            "AS response_json,"
            "CASE WHEN o.status='unknown' THEN r.provider_request_id "
            "ELSE o.provider_request_id END "
            "AS provider_request_id FROM operations o LEFT JOIN unknown_receipts r "
            "ON r.operation_id=o.operation_id WHERE o.operation_id=?",
            (operation_id,),
        ).fetchone(),
    )


def _require(connection: sqlite3.Connection, operation_id: str) -> sqlite3.Row:
    row = _find(connection, operation_id)
    if row is None:
        raise UnknownOperation("operation is not reserved")
    return row


def _event(
    connection: sqlite3.Connection,
    event_type: str,
    operation_id: str | None = None,
    reserved: int | None = None,
    actual: int | None = None,
) -> None:
    connection.execute(
        "INSERT INTO events(event_type,operation_id,reserved_microusd,actual_microusd) "
        "VALUES (?,?,?,?)",
        (event_type, operation_id, reserved, actual),
    )


def _totals(connection: sqlite3.Connection) -> dict[str, int]:
    rows = connection.execute("SELECT status,reserve_microusd,actual_microusd FROM operations")
    spent, reserved, count = 0, 0, 0
    for row in rows:
        count += 1
        if row["status"] == "completed":
            spent += row["actual_microusd"]
        else:
            reserved += row["reserve_microusd"]
    # Python integers preserve true aggregate costs even after an overrun exceeds SQLite SUM.
    return {
        "committed_microusd": spent + reserved,
        "spent_microusd": spent,
        "reserved_microusd": reserved,
        "operation_count": count,
    }


def _check_halted(connection: sqlite3.Connection) -> None:
    if connection.execute(
        "SELECT 1 FROM operations o JOIN unknown_receipts r USING(operation_id) "
        "WHERE o.status='unknown' LIMIT 1"
    ).fetchone():
        raise BudgetExceeded("an unreconciled provider receipt has halted spending")
    if connection.execute(
        "SELECT 1 FROM operations WHERE actual_microusd>reserve_microusd LIMIT 1"
    ).fetchone():
        raise BudgetExceeded("a prior reservation overrun has halted spending")


class Ledger:
    def __init__(
        self,
        path: Path | str,
        *,
        run_id: str,
        manifest_sha256: str,
        budget_microusd: int,
        max_calls: int,
    ) -> None:
        _text(run_id, "run_id")
        _hex(manifest_sha256, "manifest_sha256")
        _amount(budget_microusd, "budget_microusd")
        _amount(max_calls, "max_calls")
        if (
            not isinstance(path, (str, Path))
            or not str(path).strip()
            or str(path) == ":memory:"
            or "\x00" in str(path)
        ):
            raise ValidationError("ledger requires a durable filesystem path")
        try:
            str(path).encode("utf-8")
            self.path = Path(path).resolve()
        except (OSError, UnicodeError, ValueError) as error:
            raise ValidationError("ledger filesystem path is invalid") from error
        config = (run_id, manifest_sha256, budget_microusd, max_calls)
        with self._transaction() as connection:
            version = connection.execute("PRAGMA user_version").fetchone()[0]
            if version == 0:
                if connection.execute(
                    "SELECT 1 FROM sqlite_master WHERE name NOT GLOB 'sqlite_*' LIMIT 1"
                ).fetchone():
                    raise ValidationError("unversioned database is not an empty ledger")
                for statement in _SCHEMA:
                    connection.execute(statement)
                connection.execute("INSERT INTO run_config VALUES (1,?,?,?,?)", config)
                connection.execute("PRAGMA user_version=1")
                _event(connection, "run_created")
                version = 1
            if version == 1:
                for statement in _SCHEMA_V2:
                    connection.execute(statement)
                connection.execute("PRAGMA user_version=2")
            elif version != 2:
                raise ValidationError("unsupported ledger schema version")
            stored = connection.execute(
                "SELECT run_id,manifest_sha256,budget_microusd,max_calls FROM run_config"
            ).fetchone()
            if stored is None or tuple(stored) != config:
                raise OperationConflict("ledger run configuration differs from the frozen run")

    @contextmanager
    def _transaction(
        self, action: str = "read", operation_id: str | None = None
    ) -> Iterator[sqlite3.Connection]:
        try:
            with closing(
                sqlite3.connect(self.path, timeout=30, isolation_level=None)
            ) as connection:
                connection.row_factory = sqlite3.Row
                connection.execute("PRAGMA foreign_keys=ON")
                connection.execute("PRAGMA synchronous=FULL")
                connection.execute("BEGIN IMMEDIATE")
                with connection:
                    yield connection
        except sqlite3.Error as error:
            raise ValidationError("ledger storage transaction failed") from error

    def reserve(self, operation_id: str, request_sha256: str, reserve_microusd: int) -> Operation:
        _text(operation_id, "operation_id")
        _hex(request_sha256, "request_sha256")
        _amount(reserve_microusd, "reserve_microusd")
        with self._transaction("reserve", operation_id) as connection:
            prior = _find(connection, operation_id)
            if prior is not None:
                if (prior["request_sha256"], prior["reserve_microusd"]) != (
                    request_sha256,
                    reserve_microusd,
                ):
                    raise OperationConflict("operation ID is already bound to different parameters")
                return _operation(prior)
            _check_halted(connection)
            config = connection.execute("SELECT * FROM run_config").fetchone()
            totals = _totals(connection)
            if (
                totals["committed_microusd"] + reserve_microusd > config["budget_microusd"]
                or totals["operation_count"] >= config["max_calls"]
            ):
                raise BudgetExceeded("run dollar or call cap would be exceeded")
            connection.execute(
                "INSERT INTO operations(operation_id,request_sha256,reserve_microusd,status) "
                "VALUES (?,?,?,'reserved')",
                (operation_id, request_sha256, reserve_microusd),
            )
            _event(connection, "reserved", operation_id, reserve_microusd)
            return _operation(_require(connection, operation_id))

    def dispatch(self, operation_id: str) -> bool:
        _text(operation_id, "operation_id")
        with self._transaction("dispatch", operation_id) as connection:
            row = _require(connection, operation_id)
            if row["status"] != "reserved":
                return False
            _check_halted(connection)
            connection.execute(
                "UPDATE operations SET status='dispatched' WHERE operation_id=?", (operation_id,)
            )
            _event(connection, "dispatched", operation_id, row["reserve_microusd"])
            return True

    def get(self, operation_id: str) -> Operation | None:
        _text(operation_id, "operation_id")
        with self._transaction() as connection:
            row = _find(connection, operation_id)
            return None if row is None else _operation(row)

    def complete(
        self,
        operation_id: str,
        *,
        response: dict[str, object],
        actual_microusd: int,
        provider_request_id: str,
    ) -> Operation:
        _text(operation_id, "operation_id")
        _amount(actual_microusd, "actual_microusd")
        _text(provider_request_id, "provider_request_id")
        encoded = _response_json(response)
        with self._transaction("complete", operation_id) as connection:
            prior = _require(connection, operation_id)
            if prior["status"] == "completed":
                if (
                    prior["response_json"],
                    prior["actual_microusd"],
                    prior["provider_request_id"],
                ) != (encoded, actual_microusd, provider_request_id):
                    raise OperationConflict("completed operation has a different terminal result")
                return _operation(prior)
            if prior["status"] not in ("dispatched", "unknown"):
                raise OperationConflict("only dispatched or unknown operations can complete")
            connection.execute(
                "UPDATE operations SET status='completed',response_json=?,actual_microusd=?,"
                "provider_request_id=? WHERE operation_id=?",
                (encoded, actual_microusd, provider_request_id, operation_id),
            )
            _event(
                connection, "completed", operation_id, prior["reserve_microusd"], actual_microusd
            )
            result = _operation(_require(connection, operation_id))
            overrun = actual_microusd > prior["reserve_microusd"]
        if overrun:
            raise BudgetExceeded("true cost exceeded the reservation; result was durably recorded")
        return result

    def mark_unknown(
        self,
        operation_id: str,
        *,
        response: dict[str, object] | None = None,
        provider_request_id: str | None = None,
    ) -> None:
        _text(operation_id, "operation_id")
        encoded = None if response is None else _response_json(response)
        if provider_request_id is not None:
            _text(provider_request_id, "provider_request_id")
        supplied = encoded is not None or provider_request_id is not None
        with self._transaction("unknown", operation_id) as connection:
            prior = _require(connection, operation_id)
            if prior["status"] == "unknown":
                if prior["response_json"] is not None or prior["provider_request_id"] is not None:
                    if supplied and (encoded, provider_request_id) != (
                        prior["response_json"],
                        prior["provider_request_id"],
                    ):
                        raise OperationConflict("unknown operation already has a different receipt")
                    return
                if not supplied:
                    return
            elif prior["status"] != "dispatched":
                raise OperationConflict("only a dispatched operation can become unknown")
            if supplied:
                connection.execute(
                    "INSERT INTO unknown_receipts VALUES (?,?,?)",
                    (operation_id, encoded, provider_request_id),
                )
            connection.execute(
                "UPDATE operations SET status='unknown' WHERE operation_id=?", (operation_id,)
            )
            _event(
                connection,
                "unknown" if prior["status"] == "dispatched" else "unknown_receipt",
                operation_id,
                prior["reserve_microusd"],
            )

    def events(self) -> list[dict[str, object]]:
        with self._transaction() as connection:
            rows = connection.execute("SELECT * FROM events ORDER BY event_id")
            return [dict(row) for row in rows]

    def totals(self) -> dict[str, int]:
        with self._transaction() as connection:
            return _totals(connection)
