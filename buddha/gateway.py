"""Funded, version-neutral text API attempts with immutable raw receipts.

The trusted caller supplies logical identities. This module does not derive
identity from HTTP arrival order, run a benchmark, or certify dependency closure.
"""

import ast
import base64
import hashlib
import http.client
import os
import platform
import re
import sqlite3
import ssl
import sys
import uuid
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass, field, replace
from datetime import UTC, date, datetime
from functools import lru_cache, wraps
from pathlib import Path
from typing import cast

from buddha.authorization import Authorization, AuthorizedLedger
from buddha.common import ValidationError
from buddha.ledger import Ledger, OperationConflict
from buddha.provider import (
    BoundBreach,
    ModelSpec,
    PendingOperation,
    PreparedHTTP,
    ProviderUncertain,
)
from buddha.releases import (
    MAX_JSON_BYTES,
    ROLES,
    ReleaseError,
    Selection,
    _digest,
    _json,
    _load,
    _object,
    _path,
    _root,
    _text,
    file_hash,
    verify_selection,
)
from buddha.wire import (
    HEADER_NAMES,
    MAX_BODY_BYTES,
    RawEnvelope,
    WireError,
    decoded_body,
    extract_usage,
)

FORMAT = "buddha.gateway-run.v1"
CAPABILITIES = {
    "openai.chat-completions.v1": ("openai", "api.openai.com", "/v1/chat/completions"),
    "anthropic.messages.v1": ("anthropic", "api.anthropic.com", "/v1/messages"),
}
FORWARD_HEADERS = frozenset(
    {
        "accept",
        "accept-encoding",
        "content-type",
        "user-agent",
        "anthropic-version",
        "x-stainless-lang",
        "x-stainless-package-version",
        "x-stainless-os",
        "x-stainless-arch",
        "x-stainless-runtime",
        "x-stainless-runtime-version",
        "x-stainless-async",
        "x-stainless-retry-count",
        "x-stainless-read-timeout",
        "x-stainless-timeout",
        "x-stainless-helper-method",
    }
)
ACCOUNT_HEADERS = {
    "openai": frozenset({"openai-organization", "openai-project"}),
    "anthropic": frozenset({"anthropic-workspace-id"}),
}
CORE = frozenset(
    {
        "buddha",
        *(
            "buddha." + name
            for name in (
                "gateway",
                "wire",
                "releases",
                "authorization",
                "ledger",
                "history",
                "provider",
                "common",
            )
        ),
    }
)


class GatewayError(ValidationError, ReleaseError):
    """The gateway owner, profile or request violates its frozen contract."""


class ReceivedReply(ProviderUncertain):
    """Carry already captured evidence across an interrupted local processing step."""

    def __init__(self, envelope: RawEnvelope, error: BaseException) -> None:
        super().__init__("received evidence needs a durable checkpoint")
        self.envelope = envelope
        self.interruption = error if isinstance(error, (KeyboardInterrupt, SystemExit)) else None


def _checked[**P, T](function: Callable[P, T]) -> Callable[P, T]:
    """Expose selection failures through the gateway's typed public boundary."""

    @wraps(function)
    def checked(*args: P.args, **kwargs: P.kwargs) -> T:
        try:
            return function(*args, **kwargs)
        except GatewayError:
            raise
        except ReleaseError as error:
            raise GatewayError(str(error)) from None

    return checked


def _sha(value: object) -> str:
    return hashlib.sha256(_json(value)).hexdigest()


def _amount(value: object, *, positive: bool = False) -> int:
    if type(value) is not int or not int(positive) <= value <= 2**63 - 1:
        raise GatewayError("expected a bounded nonnegative integer")
    return value


def _texts(value: object, *, blank: bool = False) -> tuple[str, ...]:
    if type(value) is not list or not 1 <= len(value) <= 128:
        raise GatewayError("expected a bounded nonempty text list")
    result = tuple("" if blank and item == "" else _text(item) for item in value)
    if len(set(result)) != len(result):
        raise GatewayError("duplicate profile value")
    return result


def _header_value(value: object) -> str:
    text = _text(value)
    if any(not 32 <= ord(char) <= 126 for char in text):
        raise GatewayError("request headers require bounded printable ASCII")
    return text


def _headers(value: object) -> tuple[tuple[str, str], ...]:
    if type(value) is not tuple or len(value) > 64:
        raise GatewayError("request headers require a bounded immutable sequence")
    result = []
    seen = set()
    allowed = FORWARD_HEADERS | frozenset().union(*ACCOUNT_HEADERS.values())
    for pair in value:
        if type(pair) is not tuple or len(pair) != 2:
            raise GatewayError("request headers require immutable name/value pairs")
        name = _text(pair[0]).lower()
        if name not in allowed or name in seen:
            raise GatewayError("unsupported or duplicate request header")
        seen.add(name)
        result.append((name, _header_value(pair[1])))
    if sum(len(name) + len(text) for name, text in result) > 64 * 1024:
        raise GatewayError("request header byte ceiling exceeded")
    return tuple(result)


def _profile_headers(profile: dict[str, object], provider: str) -> None:
    forwarded = _object(profile["headers"])
    accounts = _object(profile["account_headers"])
    if set(forwarded) - FORWARD_HEADERS or set(accounts) - ACCOUNT_HEADERS[provider]:
        raise GatewayError("profile declares an unsupported request header")
    for name, values in forwarded.items():
        for value in _texts(values):
            _header_value(value)
            if name == "accept-encoding" and (
                len(value.split(",")) > 5
                or any(
                    item.strip().lower() not in {"identity", "gzip", "deflate"}
                    for item in value.split(",")
                )
            ):
                raise GatewayError("profile declares unsupported content coding")
            if name == "anthropic-version" and (provider != "anthropic" or value != "2023-06-01"):
                raise GatewayError("profile declares an unsupported Anthropic protocol")
            if name == "content-type" and value.lower() not in {
                "application/json",
                "application/json; charset=utf-8",
            }:
                raise GatewayError("profile must send JSON content")
    for account_value in accounts.values():
        _header_value(account_value)


def _profile_file(value: object) -> dict[str, object]:
    record = _object(value, {"format", "profiles"})
    if _text(record["format"]) not in {"buddha.gateway-profiles.v1", "buddha.gateway-profiles.v2"}:
        raise GatewayError("unsupported gateway profile file")
    profiles = _object(record["profiles"])
    if not 1 <= len(profiles) <= 128:
        raise GatewayError("expected a bounded nonempty profile map")
    for name, raw in profiles.items():
        _text(name)
        fields = {
            "spec",
            "response_models",
            "request_tiers",
            "response_tiers",
            "allow_omitted_tier",
        }
        if record["format"] == "buddha.gateway-profiles.v2":
            fields |= {"headers", "account_headers"}
        profile = _object(raw, fields)
        spec = _spec(profile["spec"])
        if spec.provider not in {"openai", "anthropic"}:
            raise GatewayError("a gateway profile requires a supported HTTP provider")
        _texts(profile["response_models"])
        _texts(profile["request_tiers"])
        _texts(profile["response_tiers"], blank=True)
        if type(profile["allow_omitted_tier"]) is not bool:
            raise GatewayError("omitted-tier permission must be boolean")
        if "headers" in profile:
            _profile_headers(profile, spec.provider)
    return record


def _spec(value: object) -> ModelSpec:
    raw = _object(value, set(ModelSpec.__dataclass_fields__))
    return ModelSpec(
        _text(raw["provider"]),
        _text(raw["model"]),
        _amount(raw["input_token_ceiling"], positive=True),
        _amount(raw["max_output_tokens"], positive=True),
        _amount(raw["input_microusd_per_million"], positive=True),
        _amount(raw["output_microusd_per_million"], positive=True),
        _text(raw["bounds_source"]),
    )


def _validate_core_source(raw: bytes, allowed: frozenset[str]) -> None:
    for node in ast.walk(ast.parse(raw)):
        if isinstance(node, ast.Import):
            names = [alias.name for alias in node.names]
        elif isinstance(node, ast.ImportFrom):
            if node.level:
                raise GatewayError("relative core imports require a reviewed closure update")
            names = (
                ["buddha." + alias.name for alias in node.names]
                if node.module == "buddha"
                else [node.module or ""]
            )
        else:
            names = []
        if any(item.startswith("buddha") and item not in allowed for item in names):
            raise GatewayError("executing core imports an unbound package module")
        if isinstance(node, ast.Call) and (
            isinstance(node.func, ast.Name)
            and node.func.id in {"exec", "eval", "__import__"}
            or isinstance(node.func, ast.Attribute)
            and node.func.attr in {"import_module", "exec_module", "load_module"}
        ):
            raise GatewayError("dynamic core loading is outside the supported closure")


_cached_core_source = lru_cache(maxsize=16)(_validate_core_source)


def _core_sources() -> dict[str, str]:
    """Bind the actual installed core, separately from operator-selected input trees."""
    import buddha
    from buddha import (
        authorization,
        common,
        history,
        ledger,
        provider,
        releases,
        wire,
    )

    modules = (
        buddha,
        sys.modules[__name__],
        authorization,
        common,
        history,
        ledger,
        provider,
        releases,
        wire,
    )
    package = Path(__file__).absolute().parent
    result = {}
    for module in modules:
        name = module.__name__
        path = Path(_text(module.__file__)).absolute()
        expected = package / ("__init__.py" if name == "buddha" else name.split(".")[-1] + ".py")
        if path != expected or name not in CORE:
            raise GatewayError("executing core module is outside its installed package")
        digest = file_hash(path)
        raw = path.read_bytes()
        if hashlib.sha256(raw).hexdigest() != digest:
            raise GatewayError("executing core changed during verification")
        # Only successful exact-byte predicates are reused: <=8 MiB raw keys,
        # plus cache overhead and in-flight work. File identity is always fresh.
        validate = _cached_core_source if len(raw) <= 512 * 1024 else _validate_core_source
        validate(raw, CORE)
        result[name] = digest
    if set(result) != CORE:
        raise GatewayError("executing core inventory is incomplete")
    return result


def _runtime() -> dict[str, str]:
    return {
        "python": sys.version,
        "implementation": sys.implementation.name,
        "platform": sys.platform,
        "machine": platform.machine(),
        "openssl": ssl.OPENSSL_VERSION,
        "sqlite": sqlite3.sqlite_version,
    }


def _review(value: object, *, fresh: bool = False) -> dict[str, object]:
    record = _object(value, {"checked_on", "credential_sha256", "account_scope"})
    _text(record["account_scope"])
    try:
        checked = date.fromisoformat(_text(record["checked_on"]))
    except ValueError:
        raise GatewayError("account/bounds review needs an ISO date") from None
    if fresh and not -1 <= (datetime.now(UTC).date() - checked).days <= 7:
        raise GatewayError("account and applicable bounds need a current review")
    credentials = _object(record["credential_sha256"])
    if not credentials or set(credentials) - {"openai", "anthropic"}:
        raise GatewayError("review needs supported credential fingerprints")
    for digest in credentials.values():
        _digest(digest)
    return record


@_checked
def validate_manifest(record: object) -> dict[str, object]:
    """Validate stored data only; terminal receipt writes must not depend on current files."""
    raw = _object(
        record,
        {
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
        },
    )
    if raw["format"] != FORMAT:
        raise GatewayError("unsupported gateway manifest")
    _text(raw["run_id"])
    settings = _object(raw["settings"], {"budget_microusd", "max_calls"})
    for value in settings.values():
        _amount(value, positive=True)
    selection = Selection.from_bytes(_json(raw["selection"]))
    if selection.fingerprint() != _digest(raw["selection_sha256"]):
        raise GatewayError("release selection differs from its owner digest")
    roots = _object(raw["roots"], set(ROLES))
    for value in (*roots.values(), raw["authorization_path"]):
        if not Path(_text(value)).is_absolute():
            raise GatewayError("gateway owner paths must be absolute")
    profiles = _object(raw["profiles"], set(_object(selection.to_record()["capabilities"])))
    for capability, profile in profiles.items():
        if capability not in CAPABILITIES:
            raise GatewayError("selected gateway capability is unsupported")
        _profile_file(profile)
    core = _object(raw["core"], set(CORE))
    for digest in core.values():
        _digest(digest)
    runtime = _object(raw["runtime"], set(_runtime()))
    for value in runtime.values():
        _text(value)
    invocation = _object(raw["invocation"], {"id", "inputs"})
    _text(invocation["id"])
    inputs = invocation["inputs"]
    if type(inputs) is not list or not 1 <= len(inputs) <= 1024:
        raise GatewayError("invocation needs a bounded ordered input inventory")
    seen = set()
    for value in inputs:
        item = _object(value, {"path", "sha256"})
        path = Path(_text(item["path"]))
        if not path.is_absolute() or str(path) in seen:
            raise GatewayError("invocation input paths must be absolute and unique")
        seen.add(str(path))
        _digest(item["sha256"])
    _review(raw["review"])
    identity = _sha(
        {key: raw[key] for key in ("selection_sha256", "core", "runtime", "invocation")}
    )
    if _digest(raw["execution_sha256"]) != identity:
        raise GatewayError("selected execution identity differs from its frozen owner")
    return raw


def _read_manifest(directory: Path) -> dict[str, object]:
    path = directory / "manifest.json"
    file_hash(path, max_bytes=MAX_JSON_BYTES)
    record = _load(path.read_bytes())
    checksum = record.pop("record_sha256", None)
    if checksum != _sha(record):
        raise GatewayError("gateway manifest checksum differs")
    return validate_manifest(record)


@_checked
def execution_identity(
    directory: Path, record: object | None = None, *, verify_files: bool = True
) -> str:
    """Verify a frozen owner, including actual core code; never accept a new hash on reopen."""
    raw = _read_manifest(directory) if record is None else validate_manifest(record)
    if verify_files:
        selection = Selection.from_bytes(_json(raw["selection"]))
        roots = {key: Path(_text(value)) for key, value in _object(raw["roots"]).items()}
        verify_selection(selection, roots, expected_sha256=_text(raw["selection_sha256"]))
        if _core_sources() != raw["core"] or _runtime() != raw["runtime"]:
            raise GatewayError("actual executing core or runtime changed")
        if _profiles(selection, roots) != raw["profiles"]:
            raise GatewayError("selected host profiles changed")
        invocation = _object(raw["invocation"])
        for value in cast(list[object], invocation["inputs"]):
            item = _object(value)
            if file_hash(Path(_text(item["path"])), max_bytes=256 * 1024**2) != item["sha256"]:
                raise GatewayError("frozen invocation input changed")
    return _text(raw["execution_sha256"])


def _profiles(selection: Selection, roots: Mapping[str, Path]) -> dict[str, object]:
    record = selection.to_record()
    paths = _object(record["capabilities"])
    expected = _object(_object(record["components"])["host"])
    result: dict[str, object] = {}
    for capability, relative in paths.items():
        if capability not in CAPABILITIES:
            raise GatewayError("selected gateway capability is unsupported")
        path = roots["host"] / _path(relative)
        if file_hash(path, max_bytes=1024**2) != expected[_text(relative)]:
            raise GatewayError("host profile bytes differ from selected inventory")
        raw = path.read_bytes()
        if hashlib.sha256(raw).hexdigest() != expected[_text(relative)]:
            raise GatewayError("host profile changed during read")
        result[capability] = _profile_file(_load(raw))
    return result


def _input_hashes(value: Mapping[Path, str] | None) -> dict[Path, str]:
    if value is None:
        return {}
    if not isinstance(value, Mapping) or len(value) > 1024:
        raise GatewayError("expected inputs require a bounded Path-to-SHA mapping")
    result: dict[Path, str] = {}
    for path, digest in value.items():
        if not isinstance(path, Path):
            raise GatewayError("expected input paths must be Paths")
        absolute = path.absolute()
        checked = _digest(digest)
        if absolute in result and result[absolute] != checked:
            raise GatewayError("expected input aliases have conflicting digests")
        result[absolute] = checked
    return result


def _input_records(
    paths: Sequence[Path], expected: Mapping[Path, str] | None = None
) -> list[dict[str, str]]:
    if (
        not isinstance(paths, (list, tuple))
        or len(paths) > 1024
        or any(not isinstance(path, Path) for path in paths)
    ):
        raise GatewayError("invocation needs a bounded ordered Path list")
    pins = _input_hashes(expected)
    if not pins.keys() <= {path.absolute() for path in paths}:
        raise GatewayError("expected input is not an invocation member")
    result = []
    for path in paths:
        absolute = path.absolute()
        digest = file_hash(path, max_bytes=256 * 1024**2)
        required = pins.get(absolute, digest)
        if digest != required:
            raise GatewayError("invocation input differs from its expected digest")
        result.append({"path": str(absolute), "sha256": required})
    return result


@_checked
def prepare_gateway(
    directory: Path,
    *,
    selection: Selection,
    roots: Mapping[str, Path],
    authorization: Authorization,
    budget_microusd: int,
    max_calls: int,
    input_files: Sequence[Path],
    review: dict[str, object],
    run_id: str | None = None,
    expected_input_hashes: Mapping[Path, str] | None = None,
) -> Path:
    """Prepare and bind an empty allocation; this never reads a key or contacts a provider."""
    directory = directory.absolute()
    if directory.exists():
        raise GatewayError("gateway output already exists; nothing overwritten")
    if not isinstance(input_files, (list, tuple)) or not 1 <= len(input_files) <= 1024:
        raise GatewayError("invocation needs a bounded ordered input list")
    verify_selection(selection, roots, expected_sha256=selection.fingerprint())
    inputs = _input_records(input_files, expected_input_hashes)
    record: dict[str, object] = {
        "format": FORMAT,
        "run_id": run_id or uuid.uuid4().hex,
        "settings": {"budget_microusd": budget_microusd, "max_calls": max_calls},
        "selection": selection.to_record(),
        "selection_sha256": selection.fingerprint(),
        "roots": {name: str(_root(path)) for name, path in roots.items()},
        "profiles": _profiles(selection, roots),
        "core": _core_sources(),
        "runtime": _runtime(),
        "invocation": {"id": uuid.uuid4().hex, "inputs": inputs},
        "review": _review(review, fresh=True),
        "authorization_path": str(authorization.path),
    }
    record["execution_sha256"] = _sha(
        {key: record[key] for key in ("selection_sha256", "core", "runtime", "invocation")}
    )
    validate_manifest(record)
    digest = _sha(record)
    directory.mkdir(parents=True, exist_ok=False)
    with (directory / "manifest.json").open("xb") as stream:
        stream.write(_json(record | {"record_sha256": digest}) + b"\n")
    Ledger(
        directory / "operations.sqlite3",
        run_id=_text(record["run_id"]),
        manifest_sha256=digest,
        budget_microusd=budget_microusd,
        max_calls=max_calls,
    )
    authorization.bind_run(directory, runtime_sha256=execution_identity(directory))
    return directory


@dataclass(frozen=True)
class GatewayCall:
    capability: str
    profile_id: str
    logical_id: str
    attempt: int
    body: bytes = field(repr=False)
    headers: tuple[tuple[str, str], ...] = field(default=(), repr=False)

    @_checked
    def __post_init__(self) -> None:
        if _text(self.capability) not in CAPABILITIES:
            raise GatewayError("unsupported request capability")
        _text(self.profile_id)
        _text(self.logical_id)
        _amount(self.attempt)
        if type(self.body) is not bytes or len(self.body) > MAX_BODY_BYTES:
            raise GatewayError("request must contain bounded immutable bytes")
        _load(self.body)
        object.__setattr__(self, "headers", _headers(self.headers))

    def to_record(self) -> dict[str, object]:
        record: dict[str, object] = {
            "capability": self.capability,
            "profile_id": self.profile_id,
            "logical_id": self.logical_id,
            "attempt": self.attempt,
            "body_base64": base64.b64encode(self.body).decode("ascii"),
        }
        if self.headers:
            record["headers"] = [list(pair) for pair in self.headers]
        return record


def _selected_headers(call: GatewayCall, profile: dict[str, object]) -> tuple[tuple[str, str], ...]:
    permitted = _object(profile.get("headers", {}))
    accounts = _object(profile.get("account_headers", {}))
    submitted = dict(call.headers)
    for name, value in call.headers:
        if name in accounts:
            if value != accounts[name]:
                raise GatewayError("request account differs from the frozen owner")
        elif name not in permitted or value not in _texts(permitted[name]):
            raise GatewayError("request header differs from its reviewed profile")
        if name == "x-stainless-retry-count" and value != str(call.attempt):
            raise GatewayError("SDK retry count differs from the physical identity")
    return call.headers + tuple(
        (name, _text(value)) for name, value in accounts.items() if name not in submitted
    )


def _request_spec(call: GatewayCall, profile: dict[str, object]) -> ModelSpec:
    spec = _spec(profile["spec"])
    body = _load(call.body)
    provider = CAPABILITIES[call.capability][0]
    if provider != spec.provider or body.get("model") != spec.model:
        raise GatewayError("request model/provider differs from the selected profile")
    allowed = {"model", "messages", "max_tokens", "temperature", "top_p", "service_tier"}
    allowed |= (
        {"max_completion_tokens", "response_format", "reasoning_effort", "stream", "n", "seed"}
        if provider == "openai"
        else {"system", "thinking", "output_config", "stop_sequences"}
    )
    if (
        set(body) - allowed
        or body.get("stream", False) is not False
        or type(body.get("n", 1)) is not int
        or body.get("n", 1) != 1
    ):
        raise GatewayError("unsupported request fields, streaming or multiple completions")
    messages = body.get("messages")
    if type(messages) is not list or not messages:
        raise GatewayError("text requests require messages")

    def content_text(content: object) -> None:
        if type(content) is str:
            try:
                content.encode("utf-8")
            except UnicodeError:
                raise GatewayError("input text must be valid UTF-8") from None
        elif provider == "anthropic" and type(content) is list and content:
            for value in content:
                block = _object(value)
                if set(block) - {"type", "text", "cache_control"} or block.get("type") != "text":
                    raise GatewayError("only text content blocks are supported")
                if type(block.get("text")) is not str:
                    raise GatewayError("text content must be a string")
                content_text(block["text"])
                if "cache_control" in block:
                    cache = _object(block["cache_control"])
                    if (
                        set(cache) - {"type", "ttl"}
                        or cache.get("type") != "ephemeral"
                        or cache.get("ttl", "5m") not in ("5m", "1h")
                    ):
                        raise GatewayError("unsupported cache billing feature")
        else:
            raise GatewayError("only text input is funded")

    for message in messages:
        row = _object(message, {"role", "content"})
        roles = (
            {"user", "assistant"}
            if provider == "anthropic"
            else {"system", "developer", "user", "assistant"}
        )
        if _text(row["role"]) not in roles:
            raise GatewayError("unsupported text message role")
        content_text(row["content"])
    if provider == "anthropic" and "system" in body:
        content_text(body["system"])
    fields = [name for name in ("max_tokens", "max_completion_tokens") if name in body]
    if len(fields) > 1 or (provider == "anthropic" and not fields):
        raise GatewayError("request has an ambiguous or missing output allowance")
    maximum = _amount(body[fields[0]], positive=True) if fields else spec.max_output_tokens
    if maximum > spec.max_output_tokens:
        raise GatewayError("request output allowance exceeds the verified model maximum")
    if "service_tier" in body:
        if _text(body["service_tier"]) not in _texts(profile["request_tiers"]):
            raise GatewayError("request tier is outside the verified profile")
    elif profile["allow_omitted_tier"] is not True:
        raise GatewayError("omitted request tier is not covered by the profile")
    return replace(spec, max_output_tokens=maximum)


def _contains_secret(raw: bytes, key: str) -> bool:
    if key.encode() in raw:
        return True
    if b"\\" in raw:
        # Credentials are printable ASCII. Decode their possible JSON escapes in
        # one bounded pass, independently of malformed/truncated outer structure.
        decoded = re.sub(
            rb'\\u00[0-7][0-9a-fA-F]|\\["\\/]',
            lambda match: (
                bytes([int(match.group()[-2:], 16)])
                if len(match.group()) == 6
                else match.group()[1:]
            ),
            raw,
        )
        return key.encode() in decoded
    return False


def _secrets(current: str) -> tuple[str, ...]:
    """Known provider credentials are used only for redaction, never persisted."""
    return tuple(
        {
            current,
            *(
                key
                for name in ("OPENAI_API_KEY", "ANTHROPIC_API_KEY")
                if (key := os.environ.get(name))
                and len(key) <= 4096
                and all(33 <= ord(char) <= 126 for char in key)
            ),
        }
        - {""}
    )


def _capture(
    provider: str,
    status: int,
    raw: bytes,
    headers: tuple[tuple[str, str], ...],
    *,
    secrets: tuple[str, ...],
    truncated: bool,
    headers_complete: bool,
    compression_requested: bool = False,
) -> RawEnvelope:
    withheld = any(
        _contains_secret(raw, key)
        or any(
            _contains_secret(value.encode("utf-8", errors="replace"), key) for _, value in headers
        )
        for key in secrets
    )
    try:
        captured = RawEnvelope(
            provider,
            status,
            raw[:MAX_BODY_BYTES],
            headers,
            truncated=truncated,
            headers_complete=headers_complete,
        )
    except WireError:
        captured = RawEnvelope(
            provider, status, raw[:MAX_BODY_BYTES], (), truncated=truncated, headers_complete=False
        )
    if not captured.headers_complete:
        if compression_requested:
            withheld = True
        else:
            try:
                # Without coding metadata, retain only verifiable plain JSON.
                _load(raw)
            except ReleaseError:
                withheld = True
    decoded = raw
    if any(name == "content-encoding" for name, _ in headers):
        try:
            decoded = decoded_body(captured)
        except WireError:
            # Unscreenable encoded bytes may contain a recoverable credential.
            withheld = True
    try:
        decoded.decode("utf-8")
        if re.search(rb"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]", decoded):
            withheld = True
    except UnicodeError:
        withheld = True
    withheld |= any(_contains_secret(decoded, key) for key in secrets)
    if withheld:
        return RawEnvelope(
            provider,
            status,
            b"",
            (),
            truncated,
            True,
            hashlib.sha256(raw).hexdigest(),
            headers_complete=captured.headers_complete,
        )
    return captured


class RawHTTPTransport:
    """One physical HTTPS send to a fixed provider endpoint; no SDK retries or redirects."""

    def __init__(self, *, allow_paid: bool = False, timeout_seconds: float = 60) -> None:
        from buddha.provider import HTTPTransport

        checked = HTTPTransport(allow_paid=allow_paid, timeout_seconds=timeout_seconds)
        self.allow_paid, self.timeout_seconds = checked.allow_paid, checked.timeout_seconds

    def prepare(
        self, operation_id: str, call: GatewayCall, spec: ModelSpec, review_fingerprint: str
    ) -> PreparedHTTP:
        _text(operation_id)
        if not self.allow_paid:
            raise GatewayError("explicit paid transport permission is required")
        provider, host, path = CAPABILITIES[call.capability]
        key = os.environ.get("OPENAI_API_KEY" if provider == "openai" else "ANTHROPIC_API_KEY")
        if not key or len(key) > 4096 or any(not 33 <= ord(char) <= 126 for char in key):
            raise GatewayError("provider credential is missing or invalid")
        if hashlib.sha256(key.encode()).hexdigest() != review_fingerprint:
            raise GatewayError("provider credential differs from the reviewed account binding")
        header_bytes = b"\n".join(
            name.encode() + b":" + value.encode() for name, value in call.headers
        )
        if any(
            _contains_secret(call.body, value) or _contains_secret(header_bytes, value)
            for value in _secrets(key)
        ):
            raise GatewayError("request contains the provider credential; nothing was sent")
        headers = dict(call.headers)
        if "content-type" not in headers:
            headers["Content-Type"] = "application/json"
        if provider == "openai":
            headers["Authorization"] = "Bearer " + key
        else:
            headers["x-api-key"] = key
            headers.setdefault("anthropic-version", "2023-06-01")
        try:
            connection = http.client.HTTPSConnection(host, timeout=self.timeout_seconds)
        except Exception:
            raise GatewayError("local connection preparation failed; nothing was sent") from None
        return PreparedHTTP(provider, path, call.body, tuple(headers.items()), connection)

    def send_prepared(self, prepared: PreparedHTTP) -> RawEnvelope:
        headers = dict(prepared.headers)
        key = headers.get("Authorization", "").removeprefix("Bearer ") or headers.get(
            "x-api-key", ""
        )
        secrets = _secrets(key)
        compression_requested = any(
            name.lower() == "accept-encoding"
            and any(token.strip().lower() != "identity" for token in value.split(","))
            for name, value in prepared.headers
        )
        raw: bytes | None = None
        selected: tuple[tuple[str, str], ...] = ()
        truncated = False
        headers_complete = False
        try:
            prepared.connection.request("POST", prepared.path, body=prepared.body, headers=headers)
            response = prepared.connection.getresponse()
            try:
                raw = response.read(MAX_BODY_BYTES + 1)
            except http.client.IncompleteRead as error:
                raw = error.partial[: MAX_BODY_BYTES + 1]
                truncated = True
            truncated = truncated or len(raw) > MAX_BODY_BYTES
            selected = tuple(
                (name.lower(), value)
                for name, value in response.getheaders()
                if name.lower() in HEADER_NAMES
            )
            headers_complete = True
            return _capture(
                prepared.provider,
                response.status,
                raw,
                selected,
                secrets=secrets,
                truncated=truncated,
                headers_complete=True,
                compression_requested=compression_requested,
            )
        except BaseException as error:
            if raw is not None:
                envelope = _capture(
                    prepared.provider,
                    response.status,
                    raw,
                    selected,
                    secrets=secrets,
                    truncated=truncated,
                    headers_complete=headers_complete,
                    compression_requested=compression_requested,
                )
                raise ReceivedReply(envelope, error) from None
            if isinstance(error, (KeyboardInterrupt, SystemExit)):
                raise
            raise ProviderUncertain("provider response could not be safely captured") from None


class Gateway:
    @_checked
    def __init__(self, directory: Path, *, transport: RawHTTPTransport) -> None:
        if not isinstance(transport, RawHTTPTransport):
            raise GatewayError("a raw HTTP transport is required")
        self.directory = directory.absolute()
        record = _read_manifest(self.directory)
        self._record_bytes = _json(record)
        self.manifest_sha256 = _sha(record)
        execution_identity(self.directory, record)
        self.ledger: AuthorizedLedger = Authorization(
            Path(_text(record["authorization_path"]))
        ).for_run(self.directory)
        self.transport = transport

    def operation_id(self, call: GatewayCall) -> str:
        record = _load(self._record_bytes)
        return _sha(
            [
                "buddha.gateway-attempt.v1",
                record["run_id"],
                record["invocation"],
                call.logical_id,
                call.attempt,
            ]
        )

    @_checked
    def execute(self, call: GatewayCall) -> RawEnvelope:
        if not isinstance(call, GatewayCall):
            raise GatewayError("gateway requires a typed request")
        current = _read_manifest(self.directory)
        if _sha(current) != self.manifest_sha256:
            raise GatewayError("gateway owner manifest changed")
        execution_identity(self.directory, current)
        profiles = _object(_object(current["profiles"]).get(call.capability))
        profile = _object(_object(profiles["profiles"]).get(call.profile_id))
        spec = _request_spec(call, profile)
        headers = _selected_headers(call, profile)
        operation_id = self.operation_id(call)
        request_hash = _sha(
            [
                "buddha.gateway-request.v1",
                current["execution_sha256"],
                current["selection_sha256"],
                _sha(profile),
                call.to_record(),
            ]
        )
        prior = self.ledger.get(operation_id)
        if prior is not None and prior.status == "completed":
            if (
                prior.request_sha256 != request_hash
                or prior.reserve_microusd != spec.reserve_microusd()
            ):
                raise OperationConflict("cached attempt differs from its bound request")
            receipt = _object(prior.response, {"format", "request", "envelope"})
            if receipt["format"] != "buddha.gateway-receipt.v1" or _json(
                receipt["request"]
            ) != _json(call.to_record()):
                raise OperationConflict("cached request evidence differs")
            envelope = RawEnvelope.from_record(receipt["envelope"])
            usage = extract_usage(envelope)
            if (
                usage.input_tokens > spec.input_token_ceiling
                or usage.output_tokens > spec.max_output_tokens
            ):
                raise BoundBreach("cached usage exceeds verified token bounds; no new send")
            if (
                envelope.provider != spec.provider
                or usage.model not in _texts(profile["response_models"])
                or usage.service_tier not in _texts(profile["response_tiers"], blank=True)
                or usage.provider_request_id != prior.provider_request_id
                or spec.cost_microusd(usage.input_tokens, usage.output_tokens)
                != prior.actual_microusd
            ):
                raise OperationConflict("cached billing evidence differs")
            return envelope
        _review(current["review"], fresh=True)
        self.ledger.authorize_dispatch()
        operation = self.ledger.reserve(operation_id, request_hash, spec.reserve_microusd())
        if operation.status != "reserved":
            raise PendingOperation("attempt may already be billed; no automatic retry")
        reviewed = _object(_object(current["review"])["credential_sha256"])
        prepared = self.transport.prepare(
            operation_id, replace(call, headers=headers), spec, _text(reviewed.get(spec.provider))
        )
        try:
            if not self.ledger.dispatch(operation_id):
                raise PendingOperation("another caller already claimed this physical attempt")
            interruption: KeyboardInterrupt | SystemExit | None = None
            try:
                envelope = self.transport.send_prepared(prepared)
                if not isinstance(envelope, RawEnvelope) or envelope.provider != spec.provider:
                    raise ProviderUncertain("transport returned unsupported raw evidence")
            except ReceivedReply as received:
                envelope = received.envelope
                interruption = received.interruption
            except BaseException as error:
                self.ledger.mark_unknown(operation_id)
                if isinstance(error, (KeyboardInterrupt, SystemExit)):
                    raise
                raise ProviderUncertain("dispatched attempt has an uncertain outcome") from None

            def make_receipt() -> dict[str, object]:
                return {
                    "format": "buddha.gateway-receipt.v1",
                    "request": call.to_record(),
                    "envelope": envelope.to_record(),
                }

            try:
                receipt = make_receipt()
            except (KeyboardInterrupt, SystemExit) as error:
                receipt = make_receipt()
                interruption = error
            try:
                request_id = envelope.provider_request_id or None
            except WireError:
                request_id = None
            except (KeyboardInterrupt, SystemExit) as error:
                request_id = None
                interruption = error
            try:
                self.ledger.mark_unknown(
                    operation_id, response=receipt, provider_request_id=request_id
                )
            except (KeyboardInterrupt, SystemExit) as error:
                self.ledger.mark_unknown(
                    operation_id, response=receipt, provider_request_id=request_id
                )
                interruption = error
            try:
                usage = extract_usage(envelope)
                if (
                    not usage.provider_request_id
                    or usage.model not in _texts(profile["response_models"])
                    or usage.service_tier not in _texts(profile["response_tiers"], blank=True)
                ):
                    raise WireError("received model/tier is outside the verified profile")
            except WireError:
                if interruption is not None:
                    raise interruption from None
                raise ProviderUncertain("raw receipt retained; billing remains uncertain") from None
            actual = spec.cost_microusd(usage.input_tokens, usage.output_tokens)
            if actual <= spec.reserve_microusd() and (
                usage.input_tokens > spec.input_token_ceiling
                or usage.output_tokens > spec.max_output_tokens
            ):
                raise BoundBreach("raw usage exceeds verified token bounds; reservation retained")
            try:
                self.ledger.complete(
                    operation_id,
                    response=receipt,
                    actual_microusd=actual,
                    provider_request_id=usage.provider_request_id,
                )
            except (KeyboardInterrupt, SystemExit) as error:
                self.ledger.complete(
                    operation_id,
                    response=receipt,
                    actual_microusd=actual,
                    provider_request_id=usage.provider_request_id,
                )
                interruption = error
            if interruption is not None:
                raise interruption
            return envelope
        finally:
            prepared.close()
