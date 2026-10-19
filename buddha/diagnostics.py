"""Metadata-only HTTPS diagnostics; never retries or reconciles an operation.

The original run's frozen provider remains unchanged. This instrumentation
extension records its own source hash and the exact request fingerprint.
"""

import hashlib
import http.client
import re
import sqlite3
import time
import uuid
import warnings
from contextlib import closing, suppress
from datetime import UTC, datetime
from pathlib import Path

from buddha.benchmark import _canonical, _object, _parse
from buddha.evaluation import ValidationError
from buddha.provider import Call, HTTPTransport, ProviderUncertain, Reply, _json
from buddha.search import _put

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


def _binding(directory: Path, call: Call) -> str:
    """A read-only lookup cannot create or change the run's accounting database."""
    try:
        uri = (directory / "operations.sqlite3").as_uri() + "?mode=ro"
        with closing(sqlite3.connect(uri, uri=True)) as connection:
            rows = connection.execute(
                "SELECT operation_id FROM operations "
                "WHERE status='dispatched' AND request_sha256=?",
                (call.fingerprint(),),
            ).fetchmany(2)
    except sqlite3.Error:
        raise ValidationError("diagnostics could not bind the dispatched operation") from None
    if len(rows) != 1 or not isinstance(rows[0][0], str) or not _HEX.fullmatch(rows[0][0]):
        raise ValidationError("diagnostics require exactly one matching dispatched operation")
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

    def send(self, call: Call) -> Reply:
        key = self._credential(call)
        operation_id = _binding(self.directory, call)
        provider = call.spec.provider
        host, path = (
            ("api.openai.com", "/v1/chat/completions")
            if provider == "openai"
            else ("api.anthropic.com", "/v1/messages")
        )
        record: dict[str, object] = {
            "schema": 1,
            "operation_id": operation_id,
            "request_sha256": call.fingerprint(),
            "provider": provider,
            "at": datetime.now(UTC).isoformat(),
            "client_request_id": str(uuid.uuid4()),
            "method": "POST",
            "host": host,
            "adapter_sha256": hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
        }
        destination = self.directory / "diagnostics" / operation_id
        try:
            _put(destination / "request.json", record)
        except (OSError, ValidationError):
            raise ValidationError(
                "diagnostic request record could not be saved; no request sent"
            ) from None
        headers = {"Content-Type": "application/json"}
        if provider == "openai":
            headers |= {
                "Authorization": "Bearer " + key,
                "X-Client-Request-Id": str(record["client_request_id"]),
            }
        else:
            headers |= {"x-api-key": key, "anthropic-version": "2023-06-01"}
        phase, status, request_id, error_code = "connect", None, None, None
        started = time.monotonic()
        connection = None

        def outcome(result: str, category: str | None) -> None:
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
            try:
                _put(destination / "outcome.json", saved)
            except (OSError, ValidationError):
                # A diagnostic storage failure must never discard a billable reply.
                with suppress(Exception):
                    warnings.warn(
                        "diagnostic outcome could not be saved", RuntimeWarning, stacklevel=2
                    )

        try:
            connection = http.client.HTTPSConnection(host, timeout=self.timeout_seconds)
            phase = "send_request"
            connection.request("POST", path, body=call.body_json.encode("utf-8"), headers=headers)
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
        finally:
            if connection is not None:
                with suppress(Exception):
                    connection.close()
        outcome("response_received", None)
        return result


def failure_summary(directory: Path) -> dict[str, object] | None:
    """Return only validated metadata from the newest valid outcome, without writes."""
    latest: tuple[datetime, str, dict[str, object]] | None = None
    for path in (directory / "diagnostics").glob("*/outcome.json"):
        try:
            if path.is_symlink() or path.parent.is_symlink():
                continue
            with path.open("rb") as stream:
                raw = stream.read(65_537)
            if len(raw) > 65_536:
                continue
            saved = _object(_parse(raw))
            checksum = saved.pop("record_sha256", None)
            if checksum != hashlib.sha256(_canonical(saved)).hexdigest():
                continue
            if (
                set(saved) != _OUTCOME_KEYS
                or type(saved["schema"]) is not int
                or saved["schema"] != 1
            ):
                continue
            if not all(
                isinstance(value, str) and _HEX.fullmatch(value)
                for value in (
                    saved[key] for key in ("operation_id", "request_sha256", "adapter_sha256")
                )
            ):
                continue
            if saved["operation_id"] != path.parent.name or saved["method"] != "POST":
                continue
            if (saved["provider"], saved["host"]) not in {
                ("openai", "api.openai.com"),
                ("anthropic", "api.anthropic.com"),
            }:
                continue
            if saved["phase"] not in _PHASES or saved["outcome"] not in {
                "response_received",
                "uncertain",
            }:
                continue
            if saved["http_status"] is not None and (
                type(saved["http_status"]) is not int or not 100 <= saved["http_status"] <= 599
            ):
                continue
            if saved["provider_request_id"] is not None and (
                not isinstance(saved["provider_request_id"], str)
                or not _REQUEST_ID.fullmatch(saved["provider_request_id"])
            ):
                continue
            if saved["error_category"] is not None and saved["error_category"] not in _CATEGORIES:
                continue
            if saved["error_code"] is not None and saved["error_code"] not in _CODES:
                continue
            if type(saved["elapsed_ms"]) is not int or not 0 <= saved["elapsed_ms"] <= 2**63 - 1:
                continue
            client_id = saved["client_request_id"]
            if not isinstance(client_id, str) or str(uuid.UUID(client_id)) != client_id:
                continue
            timestamp = saved["at"]
            if not isinstance(timestamp, str):
                continue
            at = datetime.fromisoformat(timestamp)
            if at.tzinfo is None:
                continue
            selected = (at, path.parent.name, saved)
            if latest is None or selected[:2] > latest[:2]:
                latest = selected
        except (OSError, ValidationError, ValueError, TypeError):
            continue
    if latest is None or latest[2]["outcome"] != "uncertain":
        return None
    saved = latest[2]
    try:
        request_path = directory / "diagnostics" / latest[1] / "request.json"
        if request_path.is_symlink():
            return None
        with request_path.open("rb") as stream:
            request_raw = stream.read(65_537)
        if len(request_raw) > 65_536:
            return None
        request = _object(_parse(request_raw))
        checksum = request.pop("record_sha256", None)
        if checksum != hashlib.sha256(_canonical(request)).hexdigest():
            return None
        if set(request) != _REQUEST_KEYS or any(
            request[key] != saved[key] for key in _REQUEST_KEYS - {"at"}
        ):
            return None
        uri = (directory.resolve() / "operations.sqlite3").as_uri() + "?mode=ro"
        with closing(sqlite3.connect(uri, uri=True)) as connection:
            row = connection.execute(
                "SELECT request_sha256,status FROM operations WHERE operation_id=?",
                (saved["operation_id"],),
            ).fetchone()
        if row is None or row != (saved["request_sha256"], "unknown"):
            return None
    except (OSError, sqlite3.Error, ValidationError, ValueError, TypeError):
        return None
    return {
        key: latest[2][key]
        for key in (
            "operation_id",
            "phase",
            "http_status",
            "error_category",
            "error_code",
            "provider_request_id",
            "client_request_id",
        )
    }
