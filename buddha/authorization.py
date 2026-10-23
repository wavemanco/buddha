"""Shared paid-operation authority; atomic transitions with attached run ledgers.

Historical sources are read-only sealed inputs. New operation accounting commits
with the active run's ledger in one SQLite rollback-journal transaction. This is
a host-owned guard, not a sandbox against someone editing the host or old code.
"""

import hashlib
import sqlite3
from collections.abc import Iterator
from contextlib import closing, contextmanager
from pathlib import Path
from typing import cast

from buddha import trial_fence
from buddha.common import ValidationError, _canonical, _hex, _object, _parse, _text
from buddha.history import HistoricalOperation, _plain, read_history
from buddha.ledger import (
    _BINDING_SCHEMA as _BINDING_SCHEMA,
)
from buddha.ledger import (
    _SCHEMA as LEDGER_SCHEMA,
)
from buddha.ledger import (
    _SCHEMA_V2 as LEDGER_SCHEMA_V2,
)
from buddha.ledger import (
    BudgetExceeded,
    Ledger,
    Operation,
    OperationConflict,
    _amount,
    _expected_schema,
    _find,
    _operation,
    _response_json,
    _schema_signature,
)

_TABLES = {
    "auth_config",
    "auth_runs",
    "auth_operations",
    "auth_acceptances",
    "auth_deactivations",
    "auth_events",
}
_TERM_FIELDS = (
    "authorization_id",
    "currency",
    "budget_microusd",
    "max_calls",
    "scope",
    "terms_sha256",
)
_SCHEMA = (
    """CREATE TABLE main.auth_config (
        singleton INTEGER PRIMARY KEY CHECK(singleton=1), authorization_id TEXT NOT NULL,
        currency TEXT NOT NULL CHECK(currency='USD'),
        budget_microusd INTEGER NOT NULL CHECK(budget_microusd>=0),
        max_calls INTEGER NOT NULL CHECK(max_calls>=0), scope TEXT NOT NULL,
        terms_sha256 TEXT NOT NULL)""",
    """CREATE TABLE main.auth_runs (
        run_id TEXT PRIMARY KEY, manifest_sha256 TEXT NOT NULL,
        directory TEXT NOT NULL UNIQUE, ledger_path TEXT NOT NULL UNIQUE,
        runtime_sha256 TEXT, historical_ledger_sha256 TEXT,
        historical INTEGER NOT NULL CHECK(historical IN (0,1)),
        CHECK((historical=1 AND historical_ledger_sha256 IS NOT NULL AND runtime_sha256 IS NULL)
           OR (historical=0 AND historical_ledger_sha256 IS NULL
               AND runtime_sha256 IS NOT NULL)))""",
    """CREATE TABLE main.auth_operations (
        run_id TEXT NOT NULL REFERENCES auth_runs(run_id),
        operation_id TEXT NOT NULL UNIQUE, request_sha256 TEXT NOT NULL,
        reserve_microusd INTEGER NOT NULL CHECK(reserve_microusd>=0),
        status TEXT NOT NULL CHECK(status IN ('reserved','dispatched','completed','unknown')),
        response_json TEXT, actual_microusd INTEGER CHECK(actual_microusd>=0),
        provider_request_id TEXT, PRIMARY KEY(run_id,operation_id),
        CHECK((status='completed' AND response_json IS NOT NULL AND actual_microusd IS NOT NULL
                AND provider_request_id IS NOT NULL)
           OR (status!='completed' AND actual_microusd IS NULL)))""",
    """CREATE TABLE main.auth_acceptances (
        source_run_id TEXT NOT NULL, operation_id TEXT NOT NULL,
        continuation_run_id TEXT NOT NULL REFERENCES auth_runs(run_id),
        evidence_sha256 TEXT NOT NULL, reason TEXT NOT NULL,
        PRIMARY KEY(source_run_id,operation_id),
        FOREIGN KEY(source_run_id,operation_id) REFERENCES auth_operations(run_id,operation_id))""",
    """CREATE TABLE main.auth_deactivations (
        run_id TEXT PRIMARY KEY REFERENCES auth_runs(run_id), reason TEXT NOT NULL)""",
    """CREATE TABLE main.auth_events (
        event_id INTEGER PRIMARY KEY, event_type TEXT NOT NULL, run_id TEXT,
        operation_id TEXT, details_json TEXT NOT NULL,
        created_at TEXT NOT NULL DEFAULT(strftime('%Y-%m-%dT%H:%M:%fZ','now')))""",
    """CREATE TRIGGER main.auth_operations_no_delete BEFORE DELETE ON auth_operations BEGIN
        SELECT RAISE(ABORT,'operation history is permanent'); END""",
    """CREATE TRIGGER main.auth_operations_identity BEFORE UPDATE OF
        run_id,operation_id,request_sha256,reserve_microusd ON auth_operations BEGIN
        SELECT RAISE(ABORT,'operation identity is immutable'); END""",
    """CREATE TRIGGER main.auth_operations_completed BEFORE UPDATE ON auth_operations
        WHEN OLD.status='completed' BEGIN
        SELECT RAISE(ABORT,'completed operations are immutable'); END""",
    """CREATE TRIGGER main.auth_operations_historical BEFORE UPDATE ON auth_operations
        WHEN (SELECT historical FROM auth_runs WHERE run_id=OLD.run_id)=1 BEGIN
        SELECT RAISE(ABORT,'historical evidence is immutable'); END""",
)
_AUTH_TRIGGERS = tuple(
    f"CREATE TRIGGER main.{table}_no_{action.lower()} "
    f"BEFORE {action} ON {table} BEGIN "
    "SELECT RAISE(ABORT,'authorization records are immutable'); END"
    for table in sorted(_TABLES - {"auth_operations"})
    for action in ("UPDATE", "DELETE")
)


def runtime_fingerprint() -> str:
    """Bind every package source file, including CLI, transport and this guard."""
    source = Path(__file__).parent
    files = {}
    for path in sorted(source.glob("*.py")):
        _plain(path)
        files[path.name] = hashlib.sha256(path.read_bytes()).hexdigest()
    if not files:
        raise ValidationError("runtime source is unavailable")
    return hashlib.sha256(_canonical(files)).hexdigest()


def _path(value: Path | str) -> Path:
    if not isinstance(value, (Path, str)) or not str(value).strip():
        raise ValidationError("authorization requires a durable filesystem path")
    if str(value) == ":memory:" or "\x00" in str(value) or str(value).startswith("\\\\"):
        raise ValidationError("authorization requires a local filesystem path")
    try:
        result = Path(value).absolute()
        _plain(result)
        if result.is_file() and result.stat().st_nlink != 1:
            raise ValidationError("accounting files must not have hard-link aliases")
        return result.resolve()
    except (OSError, ValueError) as error:
        raise ValidationError("authorization filesystem path is invalid") from error


def _journal(connection: sqlite3.Connection, schema: str) -> None:
    if connection.execute(f"PRAGMA {schema}.journal_mode").fetchone()[0] != "delete":
        raise ValidationError("shared accounting requires DELETE rollback journals")
    connection.execute(f"PRAGMA {schema}.synchronous=FULL")
    if connection.execute(f"PRAGMA {schema}.synchronous").fetchone()[0] != 2:
        raise ValidationError("shared accounting requires full synchronization")


def _validate(connection: sqlite3.Connection, schema: str) -> sqlite3.Row:
    if connection.execute(f"PRAGMA {schema}.user_version").fetchone()[0] != 1:
        raise ValidationError("unsupported authorization schema")
    if _schema_signature(connection, schema) != _expected_schema(_SCHEMA + _AUTH_TRIGGERS):
        raise ValidationError("authorization schema differs from its trusted definition")
    queries = {
        "main": "SELECT * FROM main.auth_config",
        "funding": "SELECT * FROM funding.auth_config",
    }
    rows = connection.execute(queries[schema]).fetchall()
    if len(rows) != 1 or rows[0]["singleton"] != 1 or rows[0]["currency"] != "USD":
        raise ValidationError("invalid authorization terms")
    row = rows[0]
    _text(row["authorization_id"], "authorization ID")
    _hex(row["terms_sha256"], "authorization terms hash")
    _amount(row["budget_microusd"], "authorization budget")
    _amount(row["max_calls"], "authorization call cap")
    _text(row["scope"], "authorization scope")
    if row["terms_sha256"] != _terms_hash(row["budget_microusd"], row["max_calls"], row["scope"]):
        raise ValidationError("authorization terms checksum differs")
    return cast(sqlite3.Row, row)


def _terms_hash(budget_microusd: int, max_calls: int, scope: str) -> str:
    return hashlib.sha256(
        _canonical(
            {
                "currency": "USD",
                "budget_microusd": budget_microusd,
                "max_calls": max_calls,
                "scope": scope,
            }
        )
    ).hexdigest()


def _event(
    connection: sqlite3.Connection,
    schema: str,
    kind: str,
    run_id: str | None = None,
    operation_id: str | None = None,
    details: object = None,
) -> None:
    queries = {
        "main": "INSERT INTO main.auth_events(event_type,run_id,operation_id,details_json) "
        "VALUES (?,?,?,?)",
        "funding": "INSERT INTO funding.auth_events(event_type,run_id,operation_id,details_json) "
        "VALUES (?,?,?,?)",
    }
    connection.execute(
        queries[schema],
        (kind, run_id, operation_id, _canonical(details).decode("utf-8")),
    )


def _totals(rows: list[sqlite3.Row]) -> dict[str, int]:
    spent = sum(row["actual_microusd"] for row in rows if row["status"] == "completed")
    held = sum(row["reserve_microusd"] for row in rows if row["status"] != "completed")
    return {
        "committed_microusd": spent + held,
        "spent_microusd": spent,
        "reserved_microusd": held,
        "operation_count": len(rows),
    }


def _manifest_record(directory: Path) -> tuple[dict[str, object], tuple[str, str, int, int]]:
    path = _path(directory / "manifest.json")
    record = _object(_parse(path.read_bytes()))
    checksum = record.pop("record_sha256", None)
    digest = hashlib.sha256(_canonical(record)).hexdigest()
    if record.get("format") == "buddha.gateway-run.v1":
        from buddha.gateway import validate_manifest

        if checksum != digest:
            raise ValidationError("gateway manifest checksum differs")
        validate_manifest(record)
    elif record.get("format") in (
        "buddha.policy-search.v1",
        "buddha.policy-search-continuation.v1",
    ):
        if checksum != digest:
            raise ValidationError("search manifest checksum differs")
    elif record.get("format") != "buddha.baseline.v1" or checksum is not None:
        raise ValidationError("unsupported run manifest")
    settings = _object(record.get("settings"))
    return record, (
        _text(record.get("run_id"), "run ID"),
        digest,
        _amount(settings.get("budget_microusd"), "run budget"),
        _amount(settings.get("max_calls"), "run call cap"),
    )


def _manifest(directory: Path) -> tuple[str, str, int, int]:
    return _manifest_record(directory)[1]


def _execution_identity(directory: Path, record: dict[str, object]) -> str:
    if record.get("format") == "buddha.gateway-run.v1":
        from buddha.gateway import execution_identity

        return execution_identity(directory, record)
    return runtime_fingerprint()


def _accept_unknown(
    connection: sqlite3.Connection,
    schema: str,
    values: tuple[str, str, str, str, str],
    *,
    require_existing: bool = False,
) -> None:
    source_run_id, operation_id, continuation_run_id, evidence_sha256, reason = values
    for value, name in (
        (source_run_id, "source run"),
        (operation_id, "operation ID"),
        (continuation_run_id, "continuation run"),
        (reason, "review reason"),
    ):
        _text(value, name)
    _hex(evidence_sha256, "historical evidence hash")
    queries = {
        "main": (
            "SELECT r.historical,r.historical_ledger_sha256,o.status,o.response_json,"
            "o.provider_request_id FROM main.auth_runs r "
            "JOIN main.auth_operations o USING(run_id) WHERE r.run_id=? AND o.operation_id=?",
            "SELECT r.historical,d.run_id FROM main.auth_runs r "
            "LEFT JOIN main.auth_deactivations d USING(run_id) WHERE r.run_id=?",
            "SELECT * FROM main.auth_acceptances WHERE source_run_id=? AND operation_id=?",
            "INSERT INTO main.auth_acceptances VALUES (?,?,?,?,?)",
        ),
        "funding": (
            "SELECT r.historical,r.historical_ledger_sha256,o.status,o.response_json,"
            "o.provider_request_id FROM funding.auth_runs r "
            "JOIN funding.auth_operations o USING(run_id) WHERE r.run_id=? AND o.operation_id=?",
            "SELECT r.historical,d.run_id FROM funding.auth_runs r "
            "LEFT JOIN funding.auth_deactivations d USING(run_id) WHERE r.run_id=?",
            "SELECT * FROM funding.auth_acceptances WHERE source_run_id=? AND operation_id=?",
            "INSERT INTO funding.auth_acceptances VALUES (?,?,?,?,?)",
        ),
    }
    source_query, target_query, prior_query, insert_query = queries[schema]
    source = connection.execute(source_query, (source_run_id, operation_id)).fetchone()
    target = connection.execute(target_query, (continuation_run_id,)).fetchone()
    if source is None or tuple(source)[:3] != (1, evidence_sha256, "unknown"):
        raise OperationConflict("review must identify an exact historical unknown")
    if source["response_json"] is not None or source["provider_request_id"] is not None:
        raise OperationConflict(
            "received uncertain billing evidence requires reconciliation before continuation"
        )
    if target is None or tuple(target) != (0, None):
        raise OperationConflict("unknown review requires an active newly bound continuation")
    prior = connection.execute(prior_query, (source_run_id, operation_id)).fetchone()
    if prior is not None:
        if tuple(prior) != values:
            raise OperationConflict("historical unknown already has a different review")
        return
    if require_existing:
        raise OperationConflict("continuation binding lacks its original atomic source claim")
    connection.execute(insert_query, values)
    _event(
        connection,
        schema,
        "historical_unknown_accepted",
        source_run_id,
        operation_id,
        {"continuation_run_id": continuation_run_id, "evidence_sha256": evidence_sha256},
    )


def _local_config(
    connection: sqlite3.Connection, expected: tuple[str, str, int, int], *, bound: bool = True
) -> None:
    if connection.execute("PRAGMA main.user_version").fetchone()[0] != 2:
        raise ValidationError("active shared accounting requires a schema-2 run ledger")
    schema = tuple(LEDGER_SCHEMA) + tuple(LEDGER_SCHEMA_V2) + (_BINDING_SCHEMA if bound else ())
    if _schema_signature(connection) != _expected_schema(schema):
        raise ValidationError("run ledger schema differs from its trusted definition")
    rows = connection.execute(
        "SELECT run_id,manifest_sha256,budget_microusd,max_calls FROM main.run_config"
    ).fetchall()
    if len(rows) != 1 or tuple(rows[0]) != expected:
        raise OperationConflict("run ledger configuration differs from its manifest")


def _binding_values(authority: "Authorization", config: sqlite3.Row) -> tuple[object, ...]:
    return (
        1,
        1,
        config["authorization_id"],
        str(authority.path),
        hashlib.sha256(_canonical(dict(config))).hexdigest(),
    )


def _check_binding(
    connection: sqlite3.Connection, authority: "Authorization", config: sqlite3.Row
) -> None:
    rows = connection.execute("SELECT * FROM main.authorization_binding").fetchall()
    if len(rows) != 1 or tuple(rows[0]) != _binding_values(authority, config):
        raise OperationConflict("run ledger belongs to a different spending authority")


def _signature(operation: Operation | HistoricalOperation) -> tuple[object, ...]:
    response = (
        operation.reply.to_record()
        if isinstance(operation, HistoricalOperation) and operation.reply is not None
        else None
        if isinstance(operation, HistoricalOperation)
        else operation.response
    )
    return (
        operation.request_sha256,
        operation.reserve_microusd,
        operation.status,
        None if response is None else _response_json(response),
        operation.actual_microusd,
        operation.provider_request_id,
    )


def _local_operations(connection: sqlite3.Connection) -> dict[str, tuple[object, ...]]:
    result = {}
    for row in connection.execute("SELECT operation_id FROM main.operations"):
        saved = _find(connection, row[0])
        if saved is None:
            raise OperationConflict("run operation disappeared")
        result[row[0]] = _signature(_operation(saved))
    return result


def _mirror_operation(
    connection: sqlite3.Connection,
    run_id: str,
    operation_id: str,
    before: tuple[object, ...] | None,
    after: tuple[object, ...],
) -> None:
    if before is None:
        owner = connection.execute(
            "SELECT run_id FROM funding.auth_operations WHERE operation_id=?", (operation_id,)
        ).fetchone()
        if owner is not None:
            raise OperationConflict("operation identity is already owned by another run")
        connection.execute(
            "INSERT INTO funding.auth_operations VALUES (?,?,?,?,?,?,?,?)",
            (run_id, operation_id, *after),
        )
    else:
        connection.execute(
            "UPDATE funding.auth_operations SET status=?,response_json=?,actual_microusd=?,"
            "provider_request_id=? WHERE run_id=? AND operation_id=?",
            (*after[2:], run_id, operation_id),
        )


class Authorization:
    def __init__(self, path: Path | str) -> None:
        self.path = _path(path)
        if not self.path.is_file():
            raise ValidationError("authorization database is missing")
        with self._connection() as connection:
            config = _validate(connection, "main")
            self._original_terms = {key: config[key] for key in _TERM_FIELDS}

    def _terms(self) -> dict[str, object]:
        """Original immutable terms, rechecked against SQLite before mutation."""
        return dict(self._original_terms)

    def _reject_trial_history(self) -> None:
        if trial_fence._parse_scope(cast(str, self._terms()["scope"])) is not None:
            raise OperationConflict("trial grants require original owners, not imported history")

    @classmethod
    def create(
        cls,
        path: Path | str,
        *,
        authorization_id: str,
        budget_microusd: int,
        max_calls: int,
        scope: str,
    ) -> "Authorization":
        _text(authorization_id, "authorization ID")
        _amount(budget_microusd, "authorization budget")
        _amount(max_calls, "authorization call cap")
        _text(scope, "authorization scope")
        terms_sha256 = _terms_hash(budget_microusd, max_calls, scope)
        if (
            not isinstance(path, (Path, str))
            or not str(path).strip()
            or (str(path) == ":memory:" or "\x00" in str(path) or str(path).startswith("\\\\"))
        ):
            raise ValidationError("authorization requires a durable filesystem path")
        destination = Path(path).absolute()
        _path(destination.parent)
        try:
            with destination.open("xb"):
                pass
        except OSError:
            raise ValidationError(
                "authorization destination already exists or is unavailable"
            ) from None
        try:
            with closing(sqlite3.connect(destination, isolation_level=None)) as connection:
                connection.execute("PRAGMA journal_mode=DELETE")
                connection.execute("PRAGMA synchronous=FULL")
                connection.execute("PRAGMA foreign_keys=ON")
                connection.execute("BEGIN IMMEDIATE")
                with connection:
                    for statement in _SCHEMA + _AUTH_TRIGGERS:
                        connection.execute(statement)
                    connection.execute(
                        "INSERT INTO main.auth_config VALUES (1,?,'USD',?,?,?,?)",
                        (authorization_id, budget_microusd, max_calls, scope, terms_sha256),
                    )
                    connection.execute("PRAGMA main.user_version=1")
                    _event(connection, "main", "authorization_created")
        except sqlite3.Error:
            # Preserve an incomplete database as evidence; never overwrite/reinitialize it.
            raise ValidationError("authorization creation failed; preserve its database") from None
        return cls(destination)

    @contextmanager
    def _connection(self, *, write: bool = False) -> Iterator[sqlite3.Connection]:
        try:
            path = _path(self.path)
            mode = "rw" if write else "ro"
            with closing(
                sqlite3.connect(
                    path.as_uri() + f"?mode={mode}", uri=True, timeout=30, isolation_level=None
                )
            ) as connection:
                connection.row_factory = sqlite3.Row
                connection.execute("PRAGMA trusted_schema=OFF")
                connection.execute("PRAGMA foreign_keys=ON")
                if write:
                    _journal(connection, "main")
                    connection.execute("BEGIN IMMEDIATE")
                else:
                    if connection.execute("PRAGMA main.journal_mode").fetchone()[0] != "delete":
                        raise ValidationError("shared accounting requires DELETE rollback journals")
                    connection.execute("PRAGMA query_only=ON")
                    connection.execute("BEGIN")
                with connection:
                    config = _validate(connection, "main")
                    if write and {key: config[key] for key in _TERM_FIELDS} != self._terms():
                        raise OperationConflict(
                            "original authorization terms changed before mutation"
                        )
                    yield connection
        except (sqlite3.Error, OSError, ValueError) as error:
            if isinstance(error, ValidationError):
                raise
            raise ValidationError("authorization storage transaction failed") from None

    def import_history(self, directory: Path, *, manifest_sha256: str, ledger_sha256: str) -> None:
        self._reject_trial_history()
        if trial_fence.required_controls(directory):
            raise OperationConflict("trial-owned history cannot become an unrelated allocation")
        source = read_history(
            directory, manifest_sha256=manifest_sha256, ledger_sha256=ledger_sha256
        )
        directory = _path(directory)
        ledger = _path(directory / "operations.sqlite3")
        authority_path = _path(self.path)
        if ledger.samefile(authority_path):
            raise OperationConflict("authorization and run ledger must be different files")
        values = (
            source.run_id,
            source.manifest_sha256,
            str(directory),
            str(ledger),
            None,
            source.ledger_sha256,
            1,
        )
        with self._connection(write=True) as connection:
            prior = connection.execute(
                "SELECT * FROM main.auth_runs WHERE run_id=?", (source.run_id,)
            ).fetchone()
            if prior is not None:
                if tuple(prior) != values:
                    raise OperationConflict("historical run is already bound to different evidence")
                return
            connection.execute("INSERT INTO main.auth_runs VALUES (?,?,?,?,?,?,?)", values)
            for operation in source.operations:
                connection.execute(
                    "INSERT INTO main.auth_operations VALUES (?,?,?,?,?,?,?,?)",
                    (source.run_id, operation.operation_id, *_signature(operation)),
                )
            _event(
                connection,
                "main",
                "history_imported",
                source.run_id,
                details={"ledger_sha256": ledger_sha256, **source.totals()},
            )

    def bind_run(self, directory: Path, *, runtime_sha256: str) -> None:
        self._bind(directory, runtime_sha256=runtime_sha256)

    def bind_continuation(
        self,
        directory: Path,
        *,
        runtime_sha256: str,
        source_run_id: str,
        operation_id: str,
        evidence_sha256: str,
        reason: str,
    ) -> None:
        """Atomically bind one continuation and its still-held historical unknown."""
        self._bind(
            directory,
            runtime_sha256=runtime_sha256,
            claim=(source_run_id, operation_id, evidence_sha256, reason),
        )

    def _bind(
        self,
        directory: Path,
        *,
        runtime_sha256: str,
        claim: tuple[str, str, str, str] | None = None,
    ) -> None:
        if claim is not None:
            self._reject_trial_history()
        directory = _path(directory)
        terms = self._terms()
        with trial_fence.lease(self.path, terms, directory=directory, settlement=True):
            self._bind_current(
                directory, runtime_sha256=runtime_sha256, claim=claim, expected_terms=terms
            )

    def _bind_current(
        self,
        directory: Path,
        *,
        runtime_sha256: str,
        claim: tuple[str, str, str, str] | None,
        expected_terms: dict[str, object],
    ) -> None:
        _hex(runtime_sha256, "runtime hash")
        directory = _path(directory)
        record, config = _manifest_record(directory)
        if runtime_sha256 != _execution_identity(directory, record):
            raise OperationConflict("declared runtime differs from the actual installed runtime")
        ledger = _path(directory / "operations.sqlite3")
        authority_path = _path(self.path)
        if claim is None:
            if record["format"] == "buddha.policy-search-continuation.v1":
                raise OperationConflict("a linked continuation requires its atomic source claim")
        else:
            if record["format"] != "buddha.policy-search-continuation.v1":
                raise OperationConflict("source claims require a linked continuation manifest")
            continuation = _object(record.get("continuation"))
            replacement = _object(continuation.get("replacement"))
            for value, name in zip(
                claim,
                ("source run", "operation ID", "historical evidence hash", "review reason"),
                strict=True,
            ):
                _text(value, name)
            _hex(claim[2], "historical evidence hash")
            if (
                continuation.get("format") != "buddha.linked-continuation.v1"
                or (
                    continuation.get("source_run_id"),
                    replacement.get("source_operation_id"),
                    continuation.get("source_ledger_sha256"),
                    continuation.get("acceptance_reason"),
                )
                != claim
                or continuation.get("authorization_path") != str(authority_path)
                or continuation.get("runtime_sha256") != runtime_sha256
            ):
                raise OperationConflict("continuation manifest differs from its exact source claim")
        if ledger.samefile(authority_path):
            raise OperationConflict("authorization and run ledger must be different files")
        values = (config[0], config[1], str(directory), str(ledger), runtime_sha256, None, 0)
        try:
            with closing(
                sqlite3.connect(
                    ledger.as_uri() + "?mode=rw", uri=True, timeout=30, isolation_level=None
                )
            ) as connection:
                connection.row_factory = sqlite3.Row
                connection.execute("PRAGMA foreign_keys=ON")
                connection.execute("PRAGMA trusted_schema=OFF")
                connection.execute(
                    "ATTACH DATABASE ? AS funding", (authority_path.as_uri() + "?mode=rw",)
                )
                _journal(connection, "main")
                _journal(connection, "funding")
                connection.execute("BEGIN IMMEDIATE")
                with connection:
                    if _manifest(directory) != config:
                        raise OperationConflict("run manifest changed during authorization binding")
                    terms = _validate(connection, "funding")
                    if {key: terms[key] for key in _TERM_FIELDS} != expected_terms:
                        raise OperationConflict(
                            "original authorization terms changed before binding"
                        )
                    has_binding = connection.execute(
                        "SELECT 1 FROM main.sqlite_master WHERE type='table' "
                        "AND name='authorization_binding'"
                    ).fetchone()
                    _local_config(connection, config, bound=bool(has_binding))
                    if has_binding:
                        _check_binding(connection, self, terms)
                    prior = connection.execute(
                        "SELECT * FROM funding.auth_runs WHERE run_id=?", (config[0],)
                    ).fetchone()
                    if prior is not None:
                        if tuple(prior) != values or not has_binding:
                            raise OperationConflict(
                                "run is already bound to another scope or runtime"
                            )
                        if claim is not None:
                            _accept_unknown(
                                connection,
                                "funding",
                                (claim[0], claim[1], config[0], *claim[2:]),
                                require_existing=True,
                            )
                        return
                    trial_fence.assert_work(
                        self.path, expected_terms, directory=directory, manifest=record
                    )
                    if (
                        has_binding
                        or connection.execute("SELECT 1 FROM main.operations LIMIT 1").fetchone()
                    ):
                        raise OperationConflict("new binding requires an empty, unbound run ledger")
                    for statement in _BINDING_SCHEMA:
                        connection.execute(statement)
                    connection.execute(
                        "INSERT INTO main.authorization_binding VALUES (?,?,?,?,?)",
                        _binding_values(self, terms),
                    )
                    connection.execute(
                        "INSERT INTO funding.auth_runs VALUES (?,?,?,?,?,?,?)", values
                    )
                    _event(
                        connection,
                        "funding",
                        "run_bound",
                        config[0],
                        details={"runtime_sha256": runtime_sha256},
                    )
                    if claim is not None:
                        _accept_unknown(
                            connection, "funding", (claim[0], claim[1], config[0], *claim[2:])
                        )
        except (sqlite3.Error, OSError, ValueError) as error:
            if isinstance(error, ValidationError):
                raise
            raise ValidationError("run authorization binding transaction failed") from None

    def for_run(self, directory: Path) -> "AuthorizedLedger":
        return AuthorizedLedger(self, directory)

    def accept_historical_unknown(
        self,
        source_run_id: str,
        operation_id: str,
        *,
        continuation_run_id: str,
        evidence_sha256: str,
        reason: str,
    ) -> None:
        self._reject_trial_history()
        values = (source_run_id, operation_id, continuation_run_id, evidence_sha256, reason)
        with self._connection(write=True) as connection:
            _accept_unknown(connection, "main", values)

    def deactivate(self, run_id: str, reason: str) -> None:
        _text(run_id, "run ID")
        _text(reason, "deactivation reason")
        terms = self._terms()
        scope = trial_fence._parse_scope(cast(str, terms["scope"]))
        directory = self.path if scope is None else scope.root
        with trial_fence.lease(self.path, terms, directory=directory, settlement=True):
            self._deactivate_current(run_id, reason, terms)

    def _deactivate_current(
        self, run_id: str, reason: str, expected_terms: dict[str, object]
    ) -> None:
        with self._connection(write=True) as connection:
            config = _validate(connection, "main")
            if {key: config[key] for key in _TERM_FIELDS} != expected_terms:
                raise OperationConflict("original authorization terms changed before deactivation")
            if (
                connection.execute(
                    "SELECT 1 FROM main.auth_runs WHERE run_id=?", (run_id,)
                ).fetchone()
                is None
            ):
                raise OperationConflict("run has no authorization binding")
            prior = connection.execute(
                "SELECT reason FROM main.auth_deactivations WHERE run_id=?", (run_id,)
            ).fetchone()
            if prior is not None:
                if prior[0] != reason:
                    raise OperationConflict("run already has a different deactivation record")
                return
            connection.execute("INSERT INTO main.auth_deactivations VALUES (?,?)", (run_id, reason))
            _event(connection, "main", "run_deactivated", run_id)

    def summary(self) -> dict[str, object]:
        with self._connection() as connection:
            config = _validate(connection, "main")
            operations = connection.execute("SELECT * FROM main.auth_operations").fetchall()
            totals = _totals(operations)
            inactive = {
                row[0] for row in connection.execute("SELECT run_id FROM main.auth_deactivations")
            }
            runs = [
                dict(row)
                | {
                    "active": not row["historical"] and row["run_id"] not in inactive,
                    **_totals([op for op in operations if op["run_id"] == row["run_id"]]),
                }
                for row in connection.execute("SELECT * FROM main.auth_runs ORDER BY run_id")
            ]
            return {
                "authorization_id": config["authorization_id"],
                "budget_microusd": config["budget_microusd"],
                "max_calls": config["max_calls"],
                "scope": config["scope"],
                "terms_sha256": config["terms_sha256"],
                **totals,
                "available_microusd": max(
                    0, config["budget_microusd"] - totals["committed_microusd"]
                ),
                "remaining_calls": max(0, config["max_calls"] - totals["operation_count"]),
                "runs": runs,
                "event_count": connection.execute(
                    "SELECT COUNT(*) FROM main.auth_events"
                ).fetchone()[0],
            }


class AuthorizedLedger(Ledger):
    """Reuse Ledger transitions, with an atomic independent authority mirror."""

    def __init__(self, authority: Authorization, directory: Path) -> None:
        if not isinstance(authority, Authorization):
            raise ValidationError("a shared authorization is required")
        self.authority, self.directory = authority, _path(directory)
        self.path = _path(self.directory / "operations.sqlite3")
        if self.path.samefile(authority.path):
            raise OperationConflict("authorization and run ledger must be different files")
        self.config = _manifest(self.directory)
        self.run_id = self.config[0]
        self.runtime_sha256 = _execution_identity(
            self.directory, _manifest_record(self.directory)[0]
        )
        with self._transaction():
            pass

    def _execution_contract(self) -> None:
        record, config = _manifest_record(self.directory)
        if config != self.config or (
            _execution_identity(self.directory, record) != self.runtime_sha256
        ):
            raise OperationConflict("bound run manifest or executable runtime changed")

    def _guard(self, connection: sqlite3.Connection) -> None:
        record, _ = _manifest_record(self.directory)
        trial_fence.assert_work(
            self.authority.path,
            self.authority._terms(),
            directory=self.directory,
            manifest=record,
        )
        binding = connection.execute(
            "SELECT historical FROM funding.auth_runs WHERE run_id=?", (self.run_id,)
        ).fetchone()
        if (
            binding is None
            or binding[0]
            or connection.execute(
                "SELECT 1 FROM funding.auth_deactivations WHERE run_id=?", (self.run_id,)
            ).fetchone()
        ):
            raise OperationConflict("run is inactive under its shared authorization")
        if connection.execute(
            "SELECT 1 FROM funding.auth_operations WHERE actual_microusd>reserve_microusd LIMIT 1"
        ).fetchone():
            raise BudgetExceeded("a known reservation overrun has halted the shared authorization")
        if connection.execute(
            "SELECT 1 FROM funding.auth_operations WHERE status='dispatched' LIMIT 1"
        ).fetchone():
            raise BudgetExceeded("an outstanding dispatch has halted further shared spending")
        if connection.execute(
            "SELECT 1 FROM funding.auth_operations o WHERE o.status='unknown' AND NOT EXISTS "
            "(SELECT 1 FROM funding.auth_acceptances a WHERE a.source_run_id=o.run_id "
            "AND a.operation_id=o.operation_id AND a.continuation_run_id=?) LIMIT 1",
            (self.run_id,),
        ).fetchone():
            raise BudgetExceeded("an unreviewed unknown operation has halted shared spending")

    def authorize_dispatch(self) -> None:
        """Fail closed before credential prompting or paid transport preflight."""
        with (
            trial_fence.lease(
                self.authority.path, self.authority._terms(), directory=self.directory
            ),
            self._transaction() as connection,
        ):
            self._execution_contract()
            self._guard(connection)

    @contextmanager
    def _transaction(
        self, action: str = "read", operation_id: str | None = None
    ) -> Iterator[sqlite3.Connection]:
        if action == "read":
            with self._transaction_current(action, operation_id) as connection:
                yield connection
            return
        if action not in {"reserve", "dispatch", "complete", "unknown"}:
            raise ValidationError("unsupported shared ledger action")
        with (
            trial_fence.lease(
                self.authority.path,
                self.authority._terms(),
                directory=self.directory,
                settlement=action in {"complete", "unknown"},
            ),
            self._transaction_current(action, operation_id) as connection,
        ):
            yield connection

    @contextmanager
    def _transaction_current(
        self, action: str, operation_id: str | None
    ) -> Iterator[sqlite3.Connection]:
        if action not in {"read", "reserve", "dispatch", "complete", "unknown"}:
            raise ValidationError("unsupported shared ledger action")
        if action != "read" and operation_id is None:
            raise ValidationError("shared ledger transition requires its operation identity")
        try:
            if _path(self.path) != self.directory / "operations.sqlite3":
                raise OperationConflict("run ledger path changed")
            authority_path = _path(self.authority.path)
            if self.path.samefile(authority_path):
                raise OperationConflict("authorization and run ledger must be different files")
            with closing(
                sqlite3.connect(
                    self.path.as_uri() + "?mode=rw", uri=True, timeout=30, isolation_level=None
                )
            ) as connection:
                connection.row_factory = sqlite3.Row
                connection.execute("PRAGMA foreign_keys=ON")
                connection.execute("PRAGMA trusted_schema=OFF")
                connection.execute(
                    "ATTACH DATABASE ? AS funding", (authority_path.as_uri() + "?mode=rw",)
                )
                _journal(connection, "main")
                _journal(connection, "funding")
                connection.execute("BEGIN IMMEDIATE")
                with connection:
                    config = _validate(connection, "funding")
                    if {key: config[key] for key in _TERM_FIELDS} != self.authority._terms():
                        raise OperationConflict(
                            "original authorization terms changed before transition"
                        )
                    _local_config(connection, self.config)
                    _check_binding(connection, self.authority, config)
                    binding = connection.execute(
                        "SELECT * FROM funding.auth_runs WHERE run_id=?", (self.run_id,)
                    ).fetchone()
                    if (
                        binding is None
                        or binding["historical"]
                        or (
                            binding["directory"],
                            binding["ledger_path"],
                            binding["manifest_sha256"],
                            binding["runtime_sha256"],
                        )
                        != (
                            str(self.directory),
                            str(self.path),
                            self.config[1],
                            self.runtime_sha256,
                        )
                    ):
                        raise OperationConflict(
                            "run lacks a matching active runtime authorization binding"
                        )
                    before = _local_operations(connection)
                    mirror = {
                        row["operation_id"]: tuple(row)[2:]
                        for row in connection.execute(
                            "SELECT * FROM funding.auth_operations WHERE run_id=?", (self.run_id,)
                        )
                    }
                    if before != mirror:
                        raise OperationConflict(
                            "run ledger differs from its independent shared accounting"
                        )
                    prior = before.get(operation_id) if operation_id is not None else None
                    spending = (action == "reserve" and prior is None) or (
                        action == "dispatch" and prior is not None and prior[2] == "reserved"
                    )
                    if spending:
                        self._execution_contract()
                        self._guard(connection)
                    yield connection
                    after = _local_operations(connection)
                    changed = {
                        key
                        for key in before.keys() | after.keys()
                        if before.get(key) != after.get(key)
                    }
                    if changed:
                        if (
                            changed != {operation_id}
                            or operation_id is None
                            or operation_id not in after
                        ):
                            raise OperationConflict(
                                "ledger transition changed unrelated operation history"
                            )
                        _mirror_operation(
                            connection, self.run_id, operation_id, prior, after[operation_id]
                        )
                        _event(
                            connection,
                            "funding",
                            action,
                            self.run_id,
                            operation_id,
                            {"status": after[operation_id][2]},
                        )
                    if spending:
                        totals = _totals(
                            connection.execute("SELECT * FROM funding.auth_operations").fetchall()
                        )
                        if totals["committed_microusd"] > config["budget_microusd"] or (
                            totals["operation_count"] > config["max_calls"]
                        ):
                            raise BudgetExceeded(
                                "shared dollar or call authorization would be exceeded"
                            )
        except (sqlite3.Error, OSError, ValueError) as error:
            if isinstance(error, ValidationError):
                raise
            raise ValidationError("shared accounting transaction failed") from None
