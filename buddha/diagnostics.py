"""Metadata-only HTTPS diagnostics; never retries or reconciles an operation.

The original run's frozen provider remains unchanged. This instrumentation
extension records its own source hash and the exact request fingerprint.
"""

import hashlib
import re
import sqlite3
import time
import uuid
import warnings
from collections.abc import Callable, Mapping
from contextlib import closing, suppress
from dataclasses import replace
from datetime import UTC, datetime
from pathlib import Path

from buddha.benchmark import _canonical, _object, _parse
from buddha.common import _hex, _text
from buddha.evaluation import ValidationError
from buddha.history import _plain
from buddha.ledger import (
    _BINDING_SCHEMA,
    _SCHEMA,
    _SCHEMA_V2,
    _amount,
    _expected_schema,
    _schema_signature,
)
from buddha.provider import (
    Call,
    HTTPTransport,
    PreparedHTTP,
    ProviderUncertain,
    Reply,
    _json,
    _ReceivedInterrupt,
)
from buddha.search import _put
from buddha.search_evidence import MAX_LEDGER_BYTES, MAX_MANIFEST_BYTES, _read, _sidecars

_LIMIT = 16 * 1024 * 1024
_HEX = re.compile(r"[0-9a-f]{64}")
_REQUEST_ID = re.compile(r"req_[A-Za-z0-9]{8,128}")
_PHASES = {"connect", "send_request", "await_headers", "read_body", "parse_response", "complete"}
_CATEGORIES = {"network", "timeout", "invalid_response", "http_status", "interrupted"}
_CODES = {
    "rate_limit_exceeded",
    "insufficient_quota",
    "invalid_api_key",
    "model_not_found",
    "context_length_exceeded",
    "server_error",
    "invalid_request_error",
    "overloaded_error",
    "authentication_error",
    "permission_error",
    "rate_limit_error",
    "api_error",
}
_REQUEST_KEYS = {
    "schema",
    "operation_id",
    "request_sha256",
    "provider",
    "at",
    "client_request_id",
    "adapter_sha256",
    "method",
    "host",
}
_OUTCOME_KEYS = _REQUEST_KEYS | {
    "phase",
    "http_status",
    "provider_request_id",
    "elapsed_ms",
    "outcome",
    "error_category",
    "error_code",
}


def _binding(directory: Path, call: Call, operation_id: str | None = None) -> str:
    """A read-only lookup cannot create or change the run's accounting database."""
    try:
        uri = (directory / "operations.sqlite3").as_uri() + "?mode=ro"
        with closing(sqlite3.connect(uri, uri=True)) as connection:
            connection.execute("PRAGMA query_only=ON")
            connection.execute("PRAGMA trusted_schema=OFF")
            if operation_id is None:
                rows = connection.execute(
                    "SELECT operation_id FROM operations WHERE status='dispatched' "
                    "AND request_sha256=?",
                    (call.fingerprint(),),
                ).fetchmany(2)
            else:
                rows = connection.execute(
                    "SELECT operation_id FROM operations WHERE operation_id=? "
                    "AND status IN ('reserved','dispatched') AND request_sha256=?",
                    (operation_id, call.fingerprint()),
                ).fetchmany(2)
    except sqlite3.Error:
        raise ValidationError("diagnostics could not bind the dispatched operation") from None
    if len(rows) != 1 or not isinstance(rows[0][0], str) or not _HEX.fullmatch(rows[0][0]):
        raise ValidationError("diagnostics require exactly one matching prepared operation")
    return rows[0][0]


def _code(raw: bytes) -> str | None:
    try:
        error = _object(_object(_parse(raw)).get("error"))
        for key in ("code", "type"):
            value = error.get(key)
            if isinstance(value, str) and value in _CODES:
                return value
    except ValidationError:
        pass
    return None


class DiagnosticHTTPTransport(HTTPTransport):
    """Same one-attempt fixed-host transport, with immutable safe sidecar records."""

    def __init__(
        self, directory: Path, *, allow_paid: bool = False, timeout_seconds: float = 60
    ) -> None:
        super().__init__(allow_paid=allow_paid, timeout_seconds=timeout_seconds)
        self.directory = directory.resolve()

    def prepare(self, operation_id: str, call: Call) -> PreparedHTTP:
        operation_id = _binding(self.directory, call, operation_id)
        provider = call.spec.provider
        host = "api.openai.com" if provider == "openai" else "api.anthropic.com"
        expected: dict[str, object] = {
            "schema": 1,
            "operation_id": operation_id,
            "request_sha256": call.fingerprint(),
            "provider": provider,
            "method": "POST",
            "host": host,
            "adapter_sha256": hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
        }
        destination = self.directory / "diagnostics" / operation_id
        request = destination / "request.json"
        try:
            for component in (request, *request.parents):
                try:
                    _plain(component)
                except FileNotFoundError:
                    continue
            if request.exists():
                with request.open("rb") as stream:
                    raw = stream.read(65_537)
                if len(raw) > 65_536:
                    raise ValidationError("oversized diagnostic request")
                record = _object(_parse(raw))
                checksum = record.pop("record_sha256", None)
                at, client_id = record.get("at"), record.get("client_request_id")
                if (
                    checksum != hashlib.sha256(_canonical(record)).hexdigest()
                    or set(record) != _REQUEST_KEYS
                    or type(record["schema"]) is not int
                    or any(record.get(key) != value for key, value in expected.items())
                    or not isinstance(at, str)
                    or datetime.fromisoformat(at).tzinfo is None
                    or not isinstance(client_id, str)
                    or str(uuid.UUID(client_id)) != client_id
                ):
                    raise ValidationError("diagnostic request identity differs")
            else:
                record = expected | {
                    "at": datetime.now(UTC).isoformat(),
                    "client_request_id": str(uuid.uuid4()),
                }
                _put(request, record)
        except Exception:
            raise ValidationError(
                "diagnostic request preparation failed; no request sent"
            ) from None
        prepared = super().prepare(operation_id, call)
        try:
            return replace(
                prepared,
                headers=prepared.headers
                + (
                    (("X-Client-Request-Id", str(record["client_request_id"])),)
                    if provider == "openai"
                    else ()
                ),
                diagnostic=tuple(record.items()),
            )
        except BaseException:
            prepared.close()
            raise

    def send(self, call: Call) -> Reply:
        # Legacy/direct transport entry: no automatic reuse of a dispatched request.
        operation_id = _binding(self.directory, call)
        request = self.directory / "diagnostics" / operation_id / "request.json"
        if request.exists() or request.is_symlink():
            raise ValidationError("diagnostic request was already prepared; use its broker")
        prepared = self.prepare(operation_id, call)
        try:
            return self.send_prepared(prepared)
        except _ReceivedInterrupt as received:
            raise received.interruption from None
        finally:
            prepared.close()

    def send_prepared(self, prepared: PreparedHTTP) -> Reply:
        record = dict(prepared.diagnostic)
        destination = self.directory / "diagnostics" / str(record["operation_id"])
        provider, connection = prepared.provider, prepared.connection
        phase, status, request_id, error_code = "connect", None, None, None
        started = time.monotonic()

        def outcome(result: str, category: str | None) -> None:
            try:
                saved = record | {
                    "at": datetime.now(UTC).isoformat(),
                    "phase": phase,
                    "http_status": status,
                    "provider_request_id": request_id,
                    "elapsed_ms": int((time.monotonic() - started) * 1000),
                    "outcome": result,
                    "error_category": category,
                    "error_code": error_code,
                }
                _put(destination / "outcome.json", saved)
            except Exception:
                # A diagnostic storage failure must never discard a billable reply.
                with suppress(Exception):
                    warnings.warn(
                        "diagnostic outcome could not be saved", RuntimeWarning, stacklevel=2
                    )

        try:
            phase = "send_request"
            connection.request(
                "POST", prepared.path, body=prepared.body, headers=dict(prepared.headers)
            )
            phase = "await_headers"
            response = connection.getresponse()
            status = response.status
            received_id = response.getheader(
                "x-request-id" if provider == "openai" else "request-id"
            )
            if isinstance(received_id, str) and _REQUEST_ID.fullmatch(received_id):
                request_id = received_id
            phase = "read_body"
            raw = response.read(_LIMIT + 1)
            if status != 200:
                error_code = _code(raw) if len(raw) <= _LIMIT else None
                raise ProviderUncertain("provider HTTP response cannot be reconciled")
            phase = "parse_response"
            if len(raw) > _LIMIT:
                raise ProviderUncertain("provider response exceeded the supported bound")
            result = self._reply(provider, _json(raw.decode("utf-8")), received_id or "")
            phase = "complete"
        except (KeyboardInterrupt, SystemExit):
            outcome("uncertain", "interrupted")
            raise
        except Exception as error:
            category = (
                "http_status"
                if status is not None and status != 200 and isinstance(error, ProviderUncertain)
                else "timeout"
                if isinstance(error, TimeoutError)
                else "invalid_response"
                if phase == "parse_response"
                else "network"
            )
            outcome("uncertain", category)
            raise ProviderUncertain("provider response cannot be reconciled") from None
        try:
            outcome("response_received", None)
        except (KeyboardInterrupt, SystemExit) as interruption:
            raise _ReceivedInterrupt(result, interruption) from None
        return result


_MAX_RECORD = 65_536
_MAX_OUTSTANDING = 100_000
_SUMMARY_KEYS = (
    "operation_id",
    "phase",
    "http_status",
    "error_category",
    "error_code",
    "provider_request_id",
    "client_request_id",
)


def _diagnostic_record(raw: bytes, *, outcome: bool) -> tuple[datetime, dict[str, object]]:
    if not isinstance(raw, bytes) or len(raw) > _MAX_RECORD:
        raise ValidationError("diagnostic record exceeds its byte contract")
    saved = _object(_parse(raw))
    checksum = saved.pop("record_sha256", None)
    if checksum != hashlib.sha256(_canonical(saved)).hexdigest() or (
        set(saved) != (_OUTCOME_KEYS if outcome else _REQUEST_KEYS)
        or type(saved["schema"]) is not int
        or saved["schema"] != 1
    ):
        raise ValidationError("diagnostic schema or checksum differs")
    for key in ("operation_id", "request_sha256", "adapter_sha256"):
        _hex(saved[key], "diagnostic identity")
    if saved["method"] != "POST" or (saved["provider"], saved["host"]) not in {
        ("openai", "api.openai.com"),
        ("anthropic", "api.anthropic.com"),
    }:
        raise ValidationError("diagnostic provider or method differs")
    client_id = saved["client_request_id"]
    if not isinstance(client_id, str) or str(uuid.UUID(client_id)) != client_id:
        raise ValidationError("invalid diagnostic client identity")
    timestamp = saved["at"]
    if not isinstance(timestamp, str):
        raise ValidationError("invalid diagnostic timestamp")
    at = datetime.fromisoformat(timestamp)
    if at.tzinfo is None:
        raise ValidationError("diagnostic timestamp has no timezone")
    if outcome:
        if saved["phase"] not in _PHASES or saved["outcome"] not in {
            "response_received",
            "uncertain",
        }:
            raise ValidationError("invalid diagnostic outcome")
        if saved["http_status"] is not None and (
            type(saved["http_status"]) is not int or not 100 <= saved["http_status"] <= 599
        ):
            raise ValidationError("invalid diagnostic HTTP status")
        if saved["provider_request_id"] is not None and (
            not isinstance(saved["provider_request_id"], str)
            or not _REQUEST_ID.fullmatch(saved["provider_request_id"])
        ):
            raise ValidationError("invalid diagnostic provider identity")
        if saved["error_category"] is not None and saved["error_category"] not in _CATEGORIES:
            raise ValidationError("invalid diagnostic error category")
        if saved["error_code"] is not None and saved["error_code"] not in _CODES:
            raise ValidationError("invalid diagnostic error code")
        if type(saved["elapsed_ms"]) is not int or not 0 <= saved["elapsed_ms"] <= 2**63 - 1:
            raise ValidationError("invalid diagnostic duration")
    return at, saved


def failure_summaries(
    outstanding: Mapping[str, tuple[str, str]], *, read: Callable[[str, int], bytes]
) -> tuple[dict[str, object], ...]:
    """Match safe legacy metadata to one supplied accounting snapshot, newest first.

    The callback consumes only requested relative paths within its own observed
    root. Native RawEnvelope owners do not publish this legacy diagnostic format.
    Reserved work has no diagnostic explanation of a dispatched failure.
    """
    if not isinstance(outstanding, Mapping) or not callable(read):
        raise ValidationError("diagnostics require an operation map and bounded reader")
    selected = dict(outstanding)
    if len(selected) > _MAX_OUTSTANDING:
        raise ValidationError("diagnostic operation population exceeds its ceiling")
    for operation_id, value in selected.items():
        _hex(operation_id, "diagnostic operation ID")
        if not isinstance(value, tuple) or len(value) != 2:
            raise ValidationError("diagnostic operation identity must contain hash and state")
        _hex(value[0], "diagnostic request hash")
        if not isinstance(value[1], str) or value[1] not in {"reserved", "dispatched", "unknown"}:
            raise ValidationError("diagnostic operation is not outstanding")
    matched = []
    for operation_id, (request_hash, status) in sorted(selected.items()):
        if status == "reserved":
            continue
        prefix = f"diagnostics/{operation_id}/"
        try:
            _, request = _diagnostic_record(
                read(prefix + "request.json", _MAX_RECORD), outcome=False
            )
            at, saved = _diagnostic_record(read(prefix + "outcome.json", _MAX_RECORD), outcome=True)
            if (
                saved["operation_id"] != operation_id
                or saved["request_sha256"] != request_hash
                or saved["outcome"] != "uncertain"
                or any(request[key] != saved[key] for key in _REQUEST_KEYS - {"at"})
            ):
                continue
            matched.append((at, operation_id, {key: saved[key] for key in _SUMMARY_KEYS}))
        except (OSError, ValueError, TypeError, KeyError, RecursionError):
            continue
    return tuple(item[2] for item in sorted(matched, key=lambda item: item[:2], reverse=True))


def _outstanding(raw: bytes, expected: tuple[str, str, int, int]) -> dict[str, tuple[str, str]]:
    """Decode identities without interpreting completed legacy reply bodies."""
    with closing(sqlite3.connect(":memory:")) as connection:
        connection.deserialize(raw)
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA query_only=ON")
        connection.execute("PRAGMA trusted_schema=OFF")
        version = connection.execute("PRAGMA user_version").fetchone()[0]
        if version not in {1, 2}:
            raise ValidationError("unsupported diagnostic ledger schema")
        binding = connection.execute(
            "SELECT 1 FROM sqlite_master WHERE type='table' AND name='authorization_binding'"
        ).fetchone()
        statements = (
            *_SCHEMA,
            *(_SCHEMA_V2 if version == 2 else ()),
            *(_BINDING_SCHEMA if binding else ()),
        )
        if _schema_signature(connection) != _expected_schema(statements):
            raise ValidationError("diagnostic ledger schema differs")
        if connection.execute("PRAGMA foreign_key_check").fetchone():
            raise ValidationError("diagnostic ledger contains orphan evidence")
        config = connection.execute("SELECT * FROM run_config").fetchall()
        if len(config) != 1 or config[0]["singleton"] != 1:
            raise ValidationError("invalid diagnostic ledger configuration")
        _text(config[0]["run_id"], "diagnostic run ID")
        _hex(config[0]["manifest_sha256"], "diagnostic manifest hash")
        _amount(config[0]["budget_microusd"], "diagnostic budget")
        _amount(config[0]["max_calls"], "diagnostic call cap")
        if tuple(config[0]) != (1, *expected):
            raise ValidationError("diagnostic ledger differs from its manifest")
        if binding:
            rows = connection.execute("SELECT * FROM authorization_binding").fetchall()
            if len(rows) != 1 or rows[0]["singleton"] != 1 or rows[0]["schema_version"] != 1:
                raise ValidationError("invalid diagnostic authority binding")
            _text(rows[0]["authorization_id"], "diagnostic authority ID")
            _text(rows[0]["authority_path"], "diagnostic authority path")
            _hex(rows[0]["terms_sha256"], "diagnostic authority terms")
        rows = connection.execute(
            "SELECT operation_id,request_sha256,status FROM operations "
            "WHERE status IN ('reserved','dispatched','unknown') ORDER BY operation_id LIMIT ?",
            (_MAX_OUTSTANDING + 1,),
        ).fetchall()
        if len(rows) > _MAX_OUTSTANDING:
            raise ValidationError("diagnostic ledger population exceeds its ceiling")
        selected = {row["operation_id"]: (row["request_sha256"], row["status"]) for row in rows}
        if len(selected) != len(rows):
            raise ValidationError("diagnostic ledger repeats an operation identity")
        for operation_id, (request_hash, _) in selected.items():
            _text(operation_id, "diagnostic ledger operation ID")
            _hex(request_hash, "diagnostic ledger request hash")
        # The general ledger also permits IDs outside this sidecar codec's grammar.
        return {key: value for key, value in selected.items() if _HEX.fullmatch(key)}


def failure_summary(directory: Path) -> dict[str, object] | None:
    """Newest validated explanation of outstanding legacy work; never changes it."""
    try:
        if not isinstance(directory, Path):
            return None
        directory = directory.absolute()
        manifest_path = directory / "manifest.json"
        manifest_raw = _read(manifest_path, MAX_MANIFEST_BYTES)
        manifest = _object(_parse(manifest_raw))
        format_name = manifest.get("format")
        if format_name not in {
            "buddha.baseline.v1",
            "buddha.policy-search.v1",
            "buddha.policy-search-continuation.v1",
        }:
            return None
        checksum = (
            manifest.pop("record_sha256", None) if format_name != "buddha.baseline.v1" else None
        )
        manifest_hash = hashlib.sha256(_canonical(manifest)).hexdigest()
        if format_name != "buddha.baseline.v1" and checksum != manifest_hash:
            return None
        settings = _object(manifest.get("settings"))
        expected = (
            _text(manifest.get("run_id"), "diagnostic run ID"),
            manifest_hash,
            _amount(settings.get("budget_microusd"), "diagnostic budget"),
            _amount(settings.get("max_calls"), "diagnostic call cap"),
        )
        ledger = directory / "operations.sqlite3"
        _sidecars(ledger)
        raw = _read(ledger, MAX_LEDGER_BYTES)
        selected = _outstanding(raw, expected)
        summaries = failure_summaries(
            selected, read=lambda relative, maximum: _read(directory / relative, maximum)
        )
        _sidecars(ledger)
        if (
            _read(ledger, MAX_LEDGER_BYTES) != raw
            or _read(manifest_path, MAX_MANIFEST_BYTES) != manifest_raw
        ):
            return None
        return summaries[0] if summaries else None
    except (OSError, sqlite3.Error, ValueError, TypeError, RecursionError, OverflowError):
        return None
