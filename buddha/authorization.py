"""Shared paid-operation authority; atomic transitions with attached run ledgers.

Historical sources are read-only sealed inputs. New operation accounting commits
with the active run's ledger in one SQLite rollback-journal transaction. This is
a host-owned guard, not a sandbox against someone editing the host or old code.
"""

import base64
import hashlib
import sqlite3
from collections.abc import Iterable, Iterator, Mapping
from contextlib import closing, contextmanager
from dataclasses import asdict, dataclass, replace
from pathlib import Path
from typing import TYPE_CHECKING, Literal, cast

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
    _check_halted,
    _expected_schema,
    _find,
    _operation,
    _require,
    _response_json,
    _schema_signature,
)
from buddha.wire import RawEnvelope, WireError, extract_usage

if TYPE_CHECKING:
    from buddha.gateway import GatewayCall

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


_HELD_REPLACEMENT_EVENT = "held_replacement_reviewed.v1"
_RETRY_HEADER = "x-stainless-retry-count"


@dataclass(frozen=True)
class HeldReplacement:
    authorization_id: str
    terms_sha256: str
    run_id: str
    manifest_sha256: str
    original_operation_id: str
    original_request_sha256: str
    original_receipt_sha256: str
    replacement_operation_id: str
    replacement_request_sha256: str
    reserve_microusd: int
    review_sha256: str

    def __post_init__(self) -> None:
        _text(self.authorization_id, "recovery authorization ID")
        _text(self.run_id, "recovery owner ID")
        for value in (
            self.terms_sha256,
            self.manifest_sha256,
            self.original_operation_id,
            self.original_request_sha256,
            self.original_receipt_sha256,
            self.replacement_operation_id,
            self.replacement_request_sha256,
            self.review_sha256,
        ):
            _hex(value, "recovery digest")
        if (
            _amount(self.reserve_microusd, "recovery reservation") == 0
            or self.original_operation_id == self.replacement_operation_id
            or self.original_request_sha256 == self.replacement_request_sha256
        ):
            raise OperationConflict("replacement needs a new identity and a positive reservation")


def held_receipt_sha256(receipt: object) -> str:
    return hashlib.sha256(_canonical(_object(receipt))).hexdigest()


def read_held_replacement(
    connection: sqlite3.Connection, schema: str = "main"
) -> HeldReplacement | None:
    queries = {
        "main": "SELECT run_id,operation_id,details_json FROM main.auth_events "
        "WHERE event_type=? LIMIT 2",
        "funding": "SELECT run_id,operation_id,details_json FROM funding.auth_events "
        "WHERE event_type=? LIMIT 2",
    }
    if schema not in queries:
        raise ValidationError("unsupported recovery authority schema")
    rows = connection.execute(
        queries[schema],
        (_HELD_REPLACEMENT_EVENT,),
    ).fetchall()
    if not rows:
        return None
    if len(rows) != 1 or not isinstance(rows[0][2], str) or len(rows[0][2]) > 4096:
        raise OperationConflict("authority does not contain one bounded recovery decision")
    run_id, operation_id, details = rows[0]
    try:
        decision = HeldReplacement(**_object(_parse(details.encode("utf-8"))))  # type: ignore[arg-type]
    except TypeError:
        raise OperationConflict("invalid recovery decision fields") from None
    if (run_id, operation_id) != (decision.run_id, decision.original_operation_id) or (
        details.encode("utf-8") != _canonical(asdict(decision))
    ):
        raise OperationConflict("recovery decision differs from its original event identity")
    return decision


def _held_envelope(receipt: object) -> RawEnvelope:
    value = _object(receipt)
    if set(value) != {"format", "request", "envelope"} or (
        value["format"] != "buddha.gateway-receipt.v1"
    ):
        raise OperationConflict("recovery requires an exact gateway receipt")
    return RawEnvelope.from_record(value["envelope"])


def _held_original(receipt: object) -> RawEnvelope:
    envelope = _held_envelope(receipt)
    if (
        envelope.provider != "anthropic"
        or envelope.status != 503
        or envelope.truncated
        or envelope.withheld
        or not envelope.headers_complete
        or not envelope.provider_request_id
        or any(name == "x-should-retry" and value != "true" for name, value in envelope.headers)
    ):
        raise OperationConflict("recovery requires the complete Anthropic 503 receipt")
    return envelope


def held_replacement_calls(
    receipt: object, manifest: Mapping[str, object]
) -> tuple["GatewayCall", "GatewayCall"]:
    from buddha.gateway import GatewayCall, _request_spec, _selected_headers

    _held_original(receipt)
    request = _object(_object(receipt)["request"])
    if set(request) != {
        "capability",
        "profile_id",
        "logical_id",
        "attempt",
        "body_base64",
        "headers",
    }:
        raise OperationConflict("recovery request differs from the native request format")
    try:
        original = GatewayCall(
            _text(request["capability"], "recovery capability"),
            _text(request["profile_id"], "recovery profile"),
            _text(request["logical_id"], "recovery logical ID"),
            _amount(request["attempt"], "recovery attempt"),
            base64.b64decode(_text(request["body_base64"], "recovery request body"), validate=True),
            tuple((name, value) for name, value in cast(list[list[str]], request["headers"])),
        )
    except (TypeError, ValueError):
        raise OperationConflict("invalid stored recovery request") from None
    if (
        original.to_record() != request
        or original.attempt != 0
        or dict(original.headers).get(_RETRY_HEADER) != "0"
    ):
        raise OperationConflict("recovery requires the first native SDK attempt")
    replacement = replace(
        original,
        attempt=1,
        headers=tuple(
            (name, "1" if name == _RETRY_HEADER else value) for name, value in original.headers
        ),
    )
    profile = _held_profile(manifest, original)
    for call in (original, replacement):
        if _request_spec(call, profile).provider != "anthropic":
            raise OperationConflict("recovery request differs from the original provider profile")
        _selected_headers(call, profile)
    return original, replacement


def _held_profile(manifest: Mapping[str, object], call: "GatewayCall") -> dict[str, object]:
    capabilities = _object(manifest["profiles"])
    profiles = _object(_object(capabilities.get(call.capability))["profiles"])
    return _object(profiles.get(call.profile_id))


def _held_utility_owner(scope: object, directory: Path) -> bool:
    binding = trial_fence._parse_scope(_text(scope, "recovery scope"))
    return (
        binding is not None
        and binding.phase == "search"
        and directory.is_relative_to(binding.root / "search" / "study")
        and directory.parts[-3:] == ("evaluation", "owners", "2")
        and directory.parts[-6:-4] == ("screen", "tasks")
        and directory.parts[-4].isascii()
        and directory.parts[-4].isdigit()
    )


def held_replacement_state(
    recovery: HeldReplacement | None,
    config: Mapping[str, object],
    runs: Iterable[Mapping[str, object]],
    operations: Iterable[Mapping[str, object]],
    *,
    _reserving: bool = False,
) -> Literal["pending", "settled", "blocked"] | None:
    """Validate the exact original/replacement pair independently of later operations."""
    if recovery is None:
        return None
    owner = next((row for row in runs if row["run_id"] == recovery.run_id), None)
    rows = {
        row["operation_id"]: row
        for row in operations
        if row["operation_id"]
        in {recovery.original_operation_id, recovery.replacement_operation_id}
    }
    original = rows.get(recovery.original_operation_id)
    if (
        (config["authorization_id"], config["terms_sha256"])
        != (recovery.authorization_id, recovery.terms_sha256)
        or owner is None
        or owner["historical"] != 0
        or owner["manifest_sha256"] != recovery.manifest_sha256
        or not _held_utility_owner(
            config["scope"], Path(_text(owner["directory"], "recovery owner directory"))
        )
        or original is None
        or (
            original["run_id"],
            original["status"],
            original["request_sha256"],
            original["reserve_microusd"],
        )
        != (recovery.run_id, "unknown", recovery.original_request_sha256, recovery.reserve_microusd)
        or original["actual_microusd"] is not None
    ):
        raise OperationConflict("recovery decision differs from the retained owner or hold")
    prior = _object(_parse(_text(original["response_json"], "recovery receipt").encode("utf-8")))
    if (
        held_receipt_sha256(prior) != recovery.original_receipt_sha256
        or _held_original(prior).provider_request_id != original["provider_request_id"]
    ):
        raise OperationConflict("recovery decision differs from the retained receipt")
    replacement = rows.get(recovery.replacement_operation_id)
    if replacement is None:
        if _reserving:
            return "pending"
        raise OperationConflict("recovery decision lacks its atomic reservation")
    if (replacement["run_id"], replacement["request_sha256"], replacement["reserve_microusd"]) != (
        recovery.run_id,
        recovery.replacement_request_sha256,
        recovery.reserve_microusd,
    ):
        raise OperationConflict("recovery operation differs from the reviewed replacement")
    status = replacement["status"]
    if status == "reserved":
        return "pending"
    if status == "dispatched" or (status == "unknown" and replacement["response_json"] is None):
        return "blocked"
    if status not in ("unknown", "completed"):
        raise OperationConflict("invalid replacement status")
    receipt = _object(
        _parse(_text(replacement["response_json"], "replacement receipt").encode("utf-8"))
    )
    request = _object(prior["request"])
    replacement_request = _object(receipt["request"])
    headers = cast(list[list[str]], request["headers"])
    if (
        request["attempt"] != 0
        or dict(headers).get(_RETRY_HEADER) != "0"
        or replacement_request
        != request
        | {
            "attempt": 1,
            "headers": [[name, "1" if name == _RETRY_HEADER else value] for name, value in headers],
        }
    ):
        raise OperationConflict("replacement receipt differs from the reviewed retry")
    envelope = _held_envelope(receipt)
    if envelope.provider != "anthropic":
        raise OperationConflict("replacement response is from a different provider")
    try:
        usage = extract_usage(envelope)
    except WireError:
        if status == "unknown":
            return "blocked"
        raise
    if (
        not usage.provider_request_id
        or usage.provider_request_id != replacement["provider_request_id"]
        or usage.provider_request_id == original["provider_request_id"]
    ):
        raise OperationConflict("replacement receipt has a different provider request ID")
    if status == "unknown":
        return "pending"
    if _amount(replacement["actual_microusd"], "replacement charge") > recovery.reserve_microusd:
        return "blocked"
    return "settled"


def _held_state(
    connection: sqlite3.Connection, recovery: HeldReplacement, *, reserving: bool = False
) -> Literal["pending", "settled", "blocked"] | None:
    return held_replacement_state(
        recovery,
        dict(_validate(connection, "funding")),
        (
            dict(row)
            for row in connection.execute(
                "SELECT * FROM funding.auth_runs WHERE run_id=?", (recovery.run_id,)
            )
        ),
        (
            dict(row)
            for row in connection.execute(
                "SELECT * FROM funding.auth_operations WHERE operation_id IN (?,?)",
                (recovery.original_operation_id, recovery.replacement_operation_id),
            )
        ),
        _reserving=reserving,
    )


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
        directory = _path(directory)
        if trial_fence.required_controls(directory):
            raise OperationConflict("trial-owned history cannot become an unrelated allocation")
        source = read_history(
            directory, manifest_sha256=manifest_sha256, ledger_sha256=ledger_sha256
        )
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

    def _guard(
        self,
        connection: sqlite3.Connection,
        operation_id: str | None,
        *,
        preparing_recovery: bool = False,
    ) -> HeldReplacement | None:
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
        recovery = read_held_replacement(connection, "funding")
        if recovery is not None:
            # During atomic preparation, the reviewed event precedes the reservation
            # inside this same transaction; no other caller observes that state.
            state = _held_state(connection, recovery, reserving=preparing_recovery)
            if state != "settled" and (
                state != "pending"
                or (self.run_id, operation_id)
                != (recovery.run_id, recovery.replacement_operation_id)
            ):
                raise BudgetExceeded("only the exact reviewed recovery may spend before settlement")
        if connection.execute(
            "SELECT 1 FROM funding.auth_operations o WHERE o.status='unknown' AND NOT EXISTS "
            "(SELECT 1 FROM funding.auth_acceptances a WHERE a.source_run_id=o.run_id "
            "AND a.operation_id=o.operation_id AND a.continuation_run_id=?) "
            "AND o.operation_id IS NOT ? LIMIT 1",
            (self.run_id, recovery.original_operation_id if recovery is not None else None),
        ).fetchone():
            raise BudgetExceeded("an unreviewed unknown operation has halted shared spending")
        return recovery

    def _check_spending(
        self,
        connection: sqlite3.Connection,
        operation_id: str,
        request_sha256: str,
        reserve_microusd: int,
        *,
        preparing_recovery: bool = False,
    ) -> None:
        recovery = self._guard(connection, operation_id, preparing_recovery=preparing_recovery)
        if (
            recovery is not None
            and operation_id == recovery.replacement_operation_id
            and (request_sha256, reserve_microusd)
            != (recovery.replacement_request_sha256, recovery.reserve_microusd)
        ):
            raise OperationConflict("spending differs from the reviewed replacement")
        _check_halted(
            connection, held_operation_id=recovery.original_operation_id if recovery else None
        )

    def authorize_dispatch(self, operation_id: str | None = None) -> None:
        """Fail closed before credential prompting or paid transport preflight."""
        if operation_id is not None:
            _text(operation_id, "operation ID")
        with (
            trial_fence.lease(
                self.authority.path, self.authority._terms(), directory=self.directory
            ),
            self._transaction() as connection,
        ):
            self._execution_contract()
            self._guard(connection, operation_id)

    def held_replacement(self) -> HeldReplacement | None:
        with self._transaction() as connection:
            recovery = read_held_replacement(connection, "funding")
            if recovery is not None and recovery.run_id == self.run_id:
                _held_state(connection, recovery)
                return recovery
        return None

    def record_held_replacement(self, recovery: HeldReplacement) -> None:
        """Commit the reviewed decision and its new reservation under the original lease."""
        if type(recovery) is not HeldReplacement or recovery.run_id != self.run_id:
            raise OperationConflict("recovery decision needs its exact original owner")
        terms = self.authority._terms()
        if not _held_utility_owner(terms["scope"], self.directory):
            raise OperationConflict("recovery requires the original development utility owner")
        trial_fence.assert_work(self.authority.path, terms, directory=self.directory)
        with self._transaction("held_replacement", recovery.replacement_operation_id) as connection:
            existing = read_held_replacement(connection, "funding")
            if existing is not None:
                if existing != recovery:
                    raise OperationConflict(
                        "authority already contains a different recovery decision"
                    )
                _held_state(connection, recovery)
                return
            _held_state(connection, recovery, reserving=True)
            if connection.execute(
                "SELECT 1 FROM funding.auth_operations WHERE operation_id=? "
                "OR (status!='completed' AND operation_id!=?) LIMIT 1",
                (recovery.replacement_operation_id, recovery.original_operation_id),
            ).fetchone():
                raise OperationConflict("other unfinished or existing operations block recovery")
            original = _operation(_require(connection, recovery.original_operation_id))
            self._check_held_requests(recovery, original)
            _event(
                connection,
                "funding",
                _HELD_REPLACEMENT_EVENT,
                self.run_id,
                recovery.original_operation_id,
                asdict(recovery),
            )
            self._reserve(
                connection,
                recovery.replacement_operation_id,
                recovery.replacement_request_sha256,
                recovery.reserve_microusd,
                preparing_recovery=True,
            )

    def _check_held_requests(
        self, recovery: HeldReplacement, operation: Operation
    ) -> tuple["GatewayCall", dict[str, object]]:
        from buddha.gateway import _request_fingerprint, _request_spec, _sha

        manifest = _manifest_record(self.directory)[0]
        original, replacement = held_replacement_calls(operation.response, manifest)
        profile = _held_profile(manifest, original)
        for call, operation_id, request_hash in (
            (original, recovery.original_operation_id, recovery.original_request_sha256),
            (replacement, recovery.replacement_operation_id, recovery.replacement_request_sha256),
        ):
            if operation_id != _sha(
                [
                    "buddha.gateway-attempt.v1",
                    self.run_id,
                    manifest["invocation"],
                    call.logical_id,
                    call.attempt,
                ]
            ) or request_hash != _request_fingerprint(manifest, call, profile):
                raise OperationConflict("recovery request is not the exact original or SDK retry")
        if _request_spec(replacement, profile).reserve_microusd() != recovery.reserve_microusd:
            raise OperationConflict("reviewed recovery differs from the original request reserve")
        return replacement, profile

    @contextmanager
    def _transaction(
        self, action: str = "read", operation_id: str | None = None
    ) -> Iterator[sqlite3.Connection]:
        if action == "read":
            with self._transaction_current(action, operation_id) as connection:
                yield connection
            return
        if action not in {"reserve", "dispatch", "complete", "unknown", "held_replacement"}:
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
        if action not in {"read", "reserve", "dispatch", "complete", "unknown", "held_replacement"}:
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
                    spending = (
                        (action == "reserve" and prior is None)
                        or (action == "dispatch" and prior is not None and prior[2] == "reserved")
                        or action == "held_replacement"
                    )
                    if spending:
                        self._execution_contract()
                    recovery = (
                        read_held_replacement(connection, "funding")
                        if action == "complete"
                        else None
                    )
                    if recovery is not None and operation_id == recovery.original_operation_id:
                        raise OperationConflict("the reviewed original hold must stay intact")
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
                        if (
                            recovery is not None
                            and operation_id == recovery.replacement_operation_id
                        ):
                            self._validate_held_completion(connection, recovery, prior)
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
                    if action == "held_replacement":
                        recorded = read_held_replacement(connection, "funding")
                        if recorded is None or operation_id != recorded.replacement_operation_id:
                            raise OperationConflict("recovery reservation lacks its decision")
                        _held_state(connection, recorded)
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

    def _validate_held_completion(
        self,
        connection: sqlite3.Connection,
        recovery: HeldReplacement,
        prior: tuple[object, ...] | None,
    ) -> None:
        from buddha.gateway import _request_spec, _validated_usage

        if prior is None or prior[2] != "unknown" or not isinstance(prior[3], str):
            raise OperationConflict("replacement must first retain its exact received reply")
        original = _operation(_require(connection, recovery.original_operation_id))
        replacement, profile = self._check_held_requests(recovery, original)
        result = _operation(_require(connection, recovery.replacement_operation_id))
        receipt = _object(result.response)
        if _canonical(receipt).decode("utf-8") != prior[3] or (
            receipt.get("request") != replacement.to_record()
        ):
            raise OperationConflict("replacement completion differs from its durable checkpoint")
        envelope = _held_envelope(receipt)
        spec = _request_spec(replacement, profile)
        usage = _validated_usage(envelope, spec, profile)
        actual = spec.cost_microusd(usage.input_tokens, usage.output_tokens)
        if (
            usage.provider_request_id != result.provider_request_id
            or usage.provider_request_id == original.provider_request_id
            or (
                actual <= recovery.reserve_microusd
                and (
                    usage.input_tokens > spec.input_token_ceiling
                    or usage.output_tokens > spec.max_output_tokens
                )
            )
            or actual != result.actual_microusd
        ):
            raise OperationConflict("replacement completion cannot establish reviewed billing")
