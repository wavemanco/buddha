"""Single-dispatch HTTPS and durable conservative liability accounting.

Configured rates must bound every applicable pricing tier and cache operation.
They are human-verified upper rates, not automatically verified invoice prices.
Input ceilings must be documented model context maxima, not token estimates.
No inference is performed by constructing these objects or importing this file.
"""

import hashlib
import http.client
import json
import math
import os
from contextlib import suppress
from dataclasses import asdict, dataclass
from typing import TYPE_CHECKING, Protocol
from urllib.parse import urlsplit

from buddha.evaluation import ValidationError

if TYPE_CHECKING:
    from buddha.ledger import Ledger


class ProviderUncertain(ValidationError):
    """A dispatched request cannot be safely reconciled; retain its reservation."""


class PendingOperation(ValidationError):
    """A prior dispatch might have been billed; automatic redispatch is forbidden."""


class BoundBreach(ValidationError):
    """Observed usage violated the configured bound; its charge remains recorded."""


def _integer(value: object, name: str, minimum: int = 0) -> int:
    if type(value) is not int or not minimum <= value <= 2**63 - 1:
        raise ValidationError(f"{name} must be a bounded integer >= {minimum}")
    return value


def _text(value: object, name: str, *, blank: bool = False) -> str:
    if not isinstance(value, str) or (not blank and not value.strip()):
        raise ValidationError(f"{name} must be text")
    return value


def _pairs(pairs: list[tuple[str, object]]) -> dict[str, object]:
    result: dict[str, object] = {}
    for key, value in pairs:
        if key in result:
            raise ValidationError("duplicate JSON property")
        result[key] = value
    return result


def _json(text: str) -> object:
    def invalid_constant(value: str) -> None:
        raise ValidationError("nonfinite JSON number")

    try:
        result: object = json.loads(text, object_pairs_hook=_pairs, parse_constant=invalid_constant)
        _canonical(result)
        return result
    except (TypeError, ValueError, RecursionError):
        raise ValidationError("invalid JSON") from None


def _canonical(value: object) -> str:
    return json.dumps(
        value, sort_keys=True, separators=(",", ":"), ensure_ascii=False, allow_nan=False
    )


@dataclass(frozen=True)
class ModelSpec:
    provider: str
    model: str
    input_token_ceiling: int
    max_output_tokens: int
    input_microusd_per_million: int
    output_microusd_per_million: int
    bounds_source: str

    def __post_init__(self) -> None:
        if not isinstance(self.provider, str) or self.provider not in {
            "openai",
            "anthropic",
            "replay",
        }:
            raise ValidationError("unsupported provider")
        _text(self.model, "model")
        _integer(self.input_token_ceiling, "input ceiling", 1)
        _integer(self.max_output_tokens, "output cap", 1)
        minimum = 0 if self.provider == "replay" else 1
        _integer(self.input_microusd_per_million, "maximum input rate", minimum)
        _integer(self.output_microusd_per_million, "maximum output rate", minimum)
        _text(self.bounds_source, "bounds source")
        try:
            source = urlsplit(self.bounds_source)
            hostname = source.hostname
        except ValueError:
            raise ValidationError("invalid bounds source URL") from None
        if self.provider != "replay" and (
            source.scheme != "https" or not hostname or source.username or source.password
        ):
            raise ValidationError("live bounds source must be an HTTPS URL")
        _integer(self.reserve_microusd(), "reservation")

    def cost_microusd(self, input_tokens: int, output_tokens: int) -> int:
        """Upper-rate charge, rounded once upward; includes reasoning and cache use."""
        _integer(input_tokens, "input tokens")
        _integer(output_tokens, "output tokens")
        numerator = (
            input_tokens * self.input_microusd_per_million
            + output_tokens * self.output_microusd_per_million
        )
        return (numerator + 999_999) // 1_000_000

    def reserve_microusd(self) -> int:
        return self.cost_microusd(self.input_token_ceiling, self.max_output_tokens)


def _messages(messages: object, provider: str) -> None:
    if not isinstance(messages, list) or not messages:
        raise ValidationError("messages must be a nonempty list")
    for message in messages:
        if not isinstance(message, dict) or set(message) != {"role", "content"}:
            raise ValidationError("unsupported message shape")
        allowed = (
            {"user", "assistant"}
            if provider == "anthropic"
            else {"system", "developer", "user", "assistant"}
        )
        if not isinstance(message["role"], str) or message["role"] not in allowed:
            raise ValidationError("unsupported message role")
        content = message["content"]
        if isinstance(content, str):
            continue
        if provider != "anthropic" or not isinstance(content, list) or not content:
            raise ValidationError("only text messages are supported")
        for block in content:
            if (
                not isinstance(block, dict)
                or block.get("type") != "text"
                or set(block) - {"type", "text", "cache_control"}
                or not isinstance(block.get("text"), str)
            ):
                raise ValidationError("unsupported message block")
            if "cache_control" in block and block["cache_control"] not in (
                {"type": "ephemeral"},
                {"type": "ephemeral", "ttl": "5m"},
            ):
                raise ValidationError("only upstream five-minute cache markers are supported")


@dataclass(frozen=True)
class Call:
    spec: ModelSpec
    body_json: str

    def __post_init__(self) -> None:
        if not isinstance(self.spec, ModelSpec):
            raise ValidationError("call requires a model specification")
        body = _json(self.body_json)
        if not isinstance(body, dict) or body.get("model") != self.spec.model:
            raise ValidationError("request model must match its specification")
        allowed = {"model", "messages", "max_tokens", "temperature", "service_tier"}
        if self.spec.provider == "anthropic":
            allowed |= {"system", "thinking", "output_config"}
        else:
            allowed |= {
                "max_completion_tokens",
                "reasoning_effort",
                "response_format",
                "n",
                "stream",
                "store",
            }
        if set(body) - allowed:
            raise ValidationError("request contains unsupported fields")
        expected_tier = "standard_only" if self.spec.provider == "anthropic" else "default"
        if (self.spec.provider != "replay" or "service_tier" in body) and (
            body.get("service_tier") != expected_tier
        ):
            raise ValidationError("an explicit standard pricing tier is required")
        caps = [key for key in ("max_tokens", "max_completion_tokens") if key in body]
        if (
            len(caps) != 1
            or type(body[caps[0]]) is not int
            or body[caps[0]] != self.spec.max_output_tokens
        ):
            raise ValidationError("request output limit must equal its reserved cap")
        if "n" in body and (type(body["n"]) is not int or body["n"] != 1):
            raise ValidationError("one completion per operation is required")
        if "stream" in body and body["stream"] is not False:
            raise ValidationError("streaming is unsupported")
        _messages(body.get("messages"), self.spec.provider)
        object.__setattr__(self, "body_json", _canonical(body))

    def fingerprint(self) -> str:
        payload = {"spec": asdict(self.spec), "body": _json(self.body_json)}
        return hashlib.sha256(_canonical(payload).encode("utf-8")).hexdigest()


@dataclass(frozen=True)
class Reply:
    text: str
    model: str
    provider_request_id: str
    input_tokens: int
    output_tokens: int
    finish_reason: str
    refused: bool = False
    service_tier: str = ""

    def __post_init__(self) -> None:
        _text(self.text, "response text", blank=True)
        _text(self.model, "response model")
        _text(self.provider_request_id, "provider request ID", blank=True)
        _integer(self.input_tokens, "input tokens")
        _integer(self.output_tokens, "output tokens")
        _text(self.finish_reason, "finish reason")
        _text(self.service_tier, "service tier", blank=True)
        if type(self.refused) is not bool:
            raise ValidationError("refused must be boolean")

    def to_record(self) -> dict[str, object]:
        return asdict(self)

    @classmethod
    def from_record(cls, record: object) -> "Reply":
        names = set(cls.__dataclass_fields__)
        if not isinstance(record, dict) or set(record) not in (names, names - {"service_tier"}):
            raise ValidationError("invalid completed reply record")
        refused = record["refused"]
        if type(refused) is not bool:
            raise ValidationError("refused must be boolean")
        return cls(
            _text(record["text"], "response text", blank=True),
            _text(record["model"], "response model"),
            _text(record["provider_request_id"], "provider request ID", blank=True),
            _integer(record["input_tokens"], "input tokens"),
            _integer(record["output_tokens"], "output tokens"),
            _text(record["finish_reason"], "finish reason"),
            refused,
            _text(record.get("service_tier", ""), "service tier", blank=True),
        )


class Transport(Protocol):
    def send(self, call: Call) -> Reply: ...


class HTTPTransport:
    """Official HTTPS hosts only; one attempt, no redirects, SDKs, tools, or proxies.

    Socket timeout is not proof of provider cancellation. All ambiguous outcomes
    remain potentially billable. Secrets are read only at explicit paid dispatch.
    """

    def __init__(self, *, allow_paid: bool = False, timeout_seconds: float = 60) -> None:
        if type(allow_paid) is not bool:
            raise ValidationError("allow_paid must be boolean")
        if (
            isinstance(timeout_seconds, bool)
            or not isinstance(timeout_seconds, (float, int))
            or not math.isfinite(timeout_seconds)
            or timeout_seconds <= 0
        ):
            raise ValidationError("timeout must be positive and finite")
        self.allow_paid = allow_paid
        self.timeout_seconds = timeout_seconds

    def _credential(self, call: Call) -> str:
        provider = call.spec.provider
        if not self.allow_paid or provider not in {"openai", "anthropic"}:
            raise ValidationError("explicit paid permission and live provider are required")
        key = os.environ.get("OPENAI_API_KEY" if provider == "openai" else "ANTHROPIC_API_KEY")
        if not key or key != key.strip() or any(not 33 <= ord(char) <= 126 for char in key):
            raise ValidationError("provider credential is missing or invalid")
        return key

    def preflight(self, call: Call) -> None:
        """Validate local permission/credentials without creating a paid operation."""
        self._credential(call)

    def send(self, call: Call) -> Reply:
        provider = call.spec.provider
        key = self._credential(call)
        host, path = (
            ("api.openai.com", "/v1/chat/completions")
            if provider == "openai"
            else ("api.anthropic.com", "/v1/messages")
        )
        headers = {"Content-Type": "application/json"}
        if provider == "openai":
            headers["Authorization"] = "Bearer " + key
        else:
            headers |= {"x-api-key": key, "anthropic-version": "2023-06-01"}
        connection = None
        try:
            connection = http.client.HTTPSConnection(host, timeout=self.timeout_seconds)
            connection.request("POST", path, body=call.body_json.encode("utf-8"), headers=headers)
            response = connection.getresponse()
            raw = response.read(16 * 1024 * 1024 + 1)
            if response.status != 200 or len(raw) > 16 * 1024 * 1024:
                raise ProviderUncertain("provider response cannot be reconciled")
            envelope = _json(raw.decode("utf-8"))
            request_id = response.getheader(
                "x-request-id" if provider == "openai" else "request-id"
            )
            return self._reply(provider, envelope, request_id or "")
        except Exception:
            raise ProviderUncertain("provider response cannot be reconciled") from None
        finally:
            if connection is not None:
                # A socket-close error must not discard received billable usage.
                with suppress(OSError):
                    connection.close()

    @staticmethod
    def _reply(provider: str, body: object, request_id: str) -> Reply:
        if not isinstance(body, dict) or not isinstance(body.get("usage"), dict):
            raise ProviderUncertain("missing provider usage")
        usage = body["usage"]
        if provider == "openai":
            inputs = _integer(usage["prompt_tokens"], "input usage")
            outputs = _integer(usage["completion_tokens"], "output usage")
            choices = body.get("choices", [])
            choice = choices[0] if isinstance(choices, list) and len(choices) == 1 else {}
            message = choice.get("message", {})
            text = message.get("content") or ""
            stop = choice.get("finish_reason") or "invalid_response"
            refused = bool(message.get("refusal")) or stop == "content_filter"
        else:
            inputs = sum(
                _integer(usage.get(key, 0), "input usage")
                for key in (
                    "input_tokens",
                    "cache_creation_input_tokens",
                    "cache_read_input_tokens",
                )
            )
            if "input_tokens" not in usage:
                raise ProviderUncertain("missing input usage")
            outputs = _integer(usage["output_tokens"], "output usage")
            text = "".join(
                block["text"] for block in body.get("content", []) if block.get("type") == "text"
            )
            stop = body.get("stop_reason") or "invalid_response"
            refused = stop == "refusal"
        tier = body.get("service_tier") if provider == "openai" else usage.get("service_tier")
        return Reply(text, body["model"], request_id, inputs, outputs, stop, refused, tier or "")


class BudgetBroker:
    """Reserve before dispatch; persist upper-rate charges before semantic parsing.

    Unknown/dispatched operations never automatically retry. Completed operations
    replay their response without network. Cost is a configured upper-rate charge,
    not an independently verified invoice. The ledger owns atomic transitions.
    """

    def __init__(self, ledger: "Ledger", transport: Transport) -> None:
        self.ledger, self.transport = ledger, transport

    @staticmethod
    def _bounds(call: Call, reply: Reply) -> None:
        if reply.model != call.spec.model or not reply.provider_request_id:
            raise BoundBreach("recorded provider identity did not match the configured instrument")
        if (
            reply.input_tokens > call.spec.input_token_ceiling
            or reply.output_tokens > call.spec.max_output_tokens
        ):
            raise BoundBreach("recorded provider usage exceeded the configured token bound")
        expected = {"openai": "default", "anthropic": "standard"}.get(call.spec.provider)
        if expected and reply.service_tier and reply.service_tier != expected:
            raise BoundBreach("recorded provider tier differed from the requested standard tier")

    def execute(self, operation_id: str, call: Call) -> Reply:
        existing = self.ledger.get(operation_id)
        if (existing is None or existing.status == "reserved") and isinstance(
            self.transport, HTTPTransport
        ):
            self.transport.preflight(call)
        operation = self.ledger.reserve(
            operation_id, call.fingerprint(), call.spec.reserve_microusd()
        )
        if operation.status == "completed":
            result = Reply.from_record(operation.response)
            self._bounds(call, result)
            return result
        if operation.status != "reserved" or not self.ledger.dispatch(operation_id):
            raise PendingOperation("operation may already be billed; reconciliation is required")
        try:
            result = self.transport.send(call)
            if not isinstance(result, Reply):
                raise ProviderUncertain("transport returned an invalid reply")
        except BaseException as error:
            self.ledger.mark_unknown(operation_id)
            if isinstance(error, (KeyboardInterrupt, SystemExit)):
                raise
            raise ProviderUncertain("dispatched operation has an uncertain outcome") from None
        expected_tier = {"openai": "default", "anthropic": "standard"}.get(call.spec.provider)
        if (
            result.model != call.spec.model
            or not result.provider_request_id
            or (expected_tier and result.service_tier and result.service_tier != expected_tier)
        ):
            self.ledger.mark_unknown(
                operation_id,
                response=result.to_record(),
                provider_request_id=result.provider_request_id or None,
            )
            raise BoundBreach(
                "provider identity or pricing tier is uncertain; receipt and reservation retained"
            )
        self.ledger.complete(
            operation_id,
            response=result.to_record(),
            actual_microusd=call.spec.cost_microusd(result.input_tokens, result.output_tokens),
            provider_request_id=result.provider_request_id,
        )
        self._bounds(call, result)
        return result
