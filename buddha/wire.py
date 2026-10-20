"""Bounded raw HTTP evidence and billing-only usage; no benchmark semantics.

The transport must filter headers and withhold evidence that echoes credentials.
Saved retry headers preserve policy inputs, not historical wall-clock scheduling.
"""

import base64
import binascii
import hashlib
import json
import re
from dataclasses import dataclass, field
from typing import cast

from buddha.releases import ReleaseError

MAX_BODY_BYTES = 16 * 1024 * 1024
MAX_HEADERS = 64
MAX_HEADER_VALUE_BYTES = 8192
MAX_REQUEST_ID_BYTES = 1024
MAX_INTEGER = 2**63 - 1
HEADER_NAMES = frozenset(
    {
        "x-request-id",
        "request-id",
        "retry-after",
        "retry-after-ms",
        "x-should-retry",
        "content-type",
    }
)


class WireError(ReleaseError):
    """Raw evidence cannot safely establish the requested wire/billing fact."""


def _integer(value: object, minimum: int = 0, maximum: int = MAX_INTEGER) -> int:
    if type(value) is not int or not minimum <= value <= maximum:
        raise WireError("expected a bounded integer")
    return value


def _text(value: object, *, blank: bool = False, limit: int = 4096) -> str:
    if type(value) is not str or len(value) > limit or (not blank and not value.strip()):
        raise WireError("expected bounded provider text")
    try:
        if len(value.encode("utf-8")) > limit or "\x00" in value:
            raise ValueError("invalid text")
    except (ValueError, UnicodeError):
        raise WireError("expected bounded valid provider text") from None
    return value


def _digest(value: object) -> str:
    if type(value) is not str or not re.fullmatch("[0-9a-f]{64}", value):
        raise WireError("expected a SHA-256 digest")
    return value


def _headers(value: object) -> tuple[tuple[str, str], ...]:
    if type(value) is not tuple or len(value) > MAX_HEADERS:
        raise WireError("expected a bounded immutable header sequence")
    result = []
    for pair in value:
        if type(pair) is not tuple or len(pair) != 2:
            raise WireError("expected an immutable header pair")
        name = _text(pair[0]).lower()
        if name not in HEADER_NAMES:
            raise WireError("unsupported response header")
        limit = (
            MAX_REQUEST_ID_BYTES
            if name in {"x-request-id", "request-id"}
            else MAX_HEADER_VALUE_BYTES
        )
        text = _text(pair[1], blank=True, limit=limit)
        if any(ord(char) < 32 or 127 <= ord(char) < 160 for char in text):
            raise WireError("response headers must not contain control characters")
        result.append((name, text))
    return tuple(result)


@dataclass(frozen=True)
class RawEnvelope:
    provider: str
    status: int
    body: bytes = field(repr=False)
    headers: tuple[tuple[str, str], ...] = field(default=(), repr=False)
    truncated: bool = False
    withheld: bool = False
    received_sha256: str | None = None
    headers_complete: bool = True

    def __post_init__(self) -> None:
        if type(self.provider) is not str or self.provider not in {"openai", "anthropic"}:
            raise WireError("unsupported wire provider")
        _integer(self.status, 100, 599)
        if type(self.body) is not bytes or len(self.body) > MAX_BODY_BYTES:
            raise WireError("expected bounded immutable response bytes")
        if any(
            type(value) is not bool
            for value in (self.truncated, self.withheld, self.headers_complete)
        ):
            raise WireError("evidence flags must be boolean")
        headers = _headers(self.headers)
        actual = hashlib.sha256(self.body).hexdigest()
        if self.withheld:
            if self.body or headers or self.received_sha256 is None:
                raise WireError("withheld evidence requires an explicit digest and empty payload")
            digest = _digest(self.received_sha256)
        else:
            digest = actual if self.received_sha256 is None else _digest(self.received_sha256)
            if digest != actual:
                raise WireError("response bytes do not match their digest")
        object.__setattr__(self, "headers", headers)
        object.__setattr__(self, "received_sha256", digest)

    @property
    def provider_request_id(self) -> str:
        name = "x-request-id" if self.provider == "openai" else "request-id"
        values = [value for key, value in self.headers if key == name]
        if len(values) > 1:
            raise WireError("provider request identity is ambiguous")
        return values[0] if values and values[0].strip() else ""

    def to_record(self) -> dict[str, object]:
        return {
            "format": "buddha.raw-envelope.v1",
            "provider": self.provider,
            "status": self.status,
            "body_base64": base64.b64encode(self.body).decode("ascii"),
            "headers": [[name, value] for name, value in self.headers],
            "headers_complete": self.headers_complete,
            "truncated": self.truncated,
            "withheld": self.withheld,
            "received_sha256": self.received_sha256,
        }

    @classmethod
    def from_record(cls, record: object) -> "RawEnvelope":
        keys = {
            "format",
            "provider",
            "status",
            "body_base64",
            "headers",
            "truncated",
            "withheld",
            "received_sha256",
            "headers_complete",
        }
        if type(record) is not dict or set(record) != keys:
            raise WireError("invalid raw response record fields")
        if record["format"] != "buddha.raw-envelope.v1":
            raise WireError("unsupported raw response record")
        encoded = record["body_base64"]
        if type(encoded) is not str or len(encoded) > 4 * ((MAX_BODY_BYTES + 2) // 3):
            raise WireError("invalid bounded response encoding")
        try:
            body = base64.b64decode(encoded, validate=True)
            if base64.b64encode(body).decode("ascii") != encoded:
                raise ValueError("noncanonical base64")
        except (ValueError, binascii.Error):
            raise WireError("invalid response encoding") from None
        headers = record["headers"]
        if type(headers) is not list or len(headers) > MAX_HEADERS:
            raise WireError("invalid response header record")
        pairs = []
        for pair in headers:
            if type(pair) is not list or len(pair) != 2:
                raise WireError("invalid response header pair record")
            pairs.append(tuple(pair))
        _digest(record["received_sha256"])
        return cls(
            record["provider"],
            record["status"],
            body,
            tuple(pairs),
            record["truncated"],
            record["withheld"],
            record["received_sha256"],
            record["headers_complete"],
        )


@dataclass(frozen=True)
class Usage:
    model: str = field(repr=False)
    provider_request_id: str = field(repr=False)
    input_tokens: int
    output_tokens: int
    service_tier: str = field(repr=False)

    def __post_init__(self) -> None:
        _text(self.model)
        _text(self.provider_request_id, blank=True, limit=MAX_REQUEST_ID_BYTES)
        _integer(self.input_tokens)
        _integer(self.output_tokens)
        _text(self.service_tier, blank=True)


def _pairs(items: list[tuple[str, object]]) -> dict[str, object]:
    result = {}
    for key, value in items:
        if key in result:
            raise WireError("duplicate provider JSON property")
        result[key] = value
    return result


def _nonfinite(value: str) -> None:
    raise WireError("nonfinite provider JSON number")


def _object(value: object) -> dict[str, object]:
    if not isinstance(value, dict):
        raise WireError("expected a provider JSON object")
    return cast(dict[str, object], value)


def extract_usage(envelope: RawEnvelope) -> Usage:
    """Read inclusive billing counters only; do not parse content, finish or judgment.

    A caller must separately verify model/tier/bounds and source authenticity.
    Missing counters, ambiguous IDs and unavailable evidence retain uncertainty.
    """
    if not isinstance(envelope, RawEnvelope) or (
        envelope.status != 200
        or envelope.truncated
        or envelope.withheld
        or not envelope.headers_complete
    ):
        raise WireError("complete successful response evidence is required")
    try:
        parsed: object = json.loads(
            envelope.body.decode("utf-8"), object_pairs_hook=_pairs, parse_constant=_nonfinite
        )
        json.dumps(parsed, allow_nan=False)
        record = _object(parsed)
        counters = _object(record.get("usage"))
        if envelope.provider == "openai":
            inputs = _integer(counters.get("prompt_tokens"))
            outputs = _integer(counters.get("completion_tokens"))
            tier = _text(record.get("service_tier", ""), blank=True)
        else:
            inputs = _integer(
                _integer(counters.get("input_tokens"))
                + _integer(counters.get("cache_creation_input_tokens", 0))
                + _integer(counters.get("cache_read_input_tokens", 0))
            )
            outputs = _integer(counters.get("output_tokens"))
            tier = _text(counters.get("service_tier", ""), blank=True)
        return Usage(
            _text(record.get("model")), envelope.provider_request_id, inputs, outputs, tier
        )
    except (ValueError, TypeError, UnicodeError, RecursionError):
        raise WireError("response cannot establish unambiguous billing usage") from None
