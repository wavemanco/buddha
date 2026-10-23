"""One frozen Chat request and data-only assessment of its observed capacity."""

import hashlib
from dataclasses import asdict

from buddha.common import ValidationError
from buddha.gateway import Gateway, GatewayCall
from buddha.releases import ReleaseError, _digest, _load, _object, _source_proposal, _text
from buddha.wire import (
    MAX_BODY_BYTES,
    RawEnvelope,
    WireError,
    _integer,
    decoded_body,
    extract_usage,
)


class SourceCapacityError(ValidationError, ReleaseError):
    """The frozen request or prospective assessment parameters are invalid."""


def guard_call(call: GatewayCall, expected: dict[str, object]) -> None:
    """Refuse drift before a caller delegates to the spending Gateway."""
    try:
        if (
            type(call) is not GatewayCall
            or type(expected) is not dict
            or set(expected) != {"capability", "profile_id", "logical_id", "attempt", "body_sha256"}
        ):
            raise SourceCapacityError("invalid frozen capacity request")
        capability = _text(expected["capability"])
        profile = _text(expected["profile_id"])
        logical = _text(expected["logical_id"])
        _integer(expected["attempt"], 0, 0)
        digest = _digest(expected["body_sha256"])
        if (
            capability != "openai.chat-completions.v1"
            or _text(call.capability) != capability
            or _text(call.profile_id) != profile
            or _text(call.logical_id) != logical
            or _integer(call.attempt, 0, 0) != 0
            or call.headers
            or type(call.body) is not bytes
            or len(call.body) > MAX_BODY_BYTES
            or hashlib.sha256(call.body).hexdigest() != digest
        ):
            raise SourceCapacityError("capacity request differs from its frozen identity")
    except (ReleaseError, ValueError, TypeError, KeyError):
        raise SourceCapacityError("invalid or changed frozen capacity request") from None


def execute_guarded(
    gateway: Gateway, call: GatewayCall, expected: dict[str, object]
) -> RawEnvelope:
    """Check the full request before any Gateway reservation, key access or send."""
    guard_call(call, expected)
    if not isinstance(gateway, Gateway):
        raise SourceCapacityError("capacity execution requires its original Gateway")
    return gateway.execute(call)


def assess_reply(
    envelope: RawEnvelope,
    *,
    parent_source_sha256: str,
    model: str,
    context_tokens: int,
    output_cap_tokens: int,
    min_context_slack: int,
    min_output_slack: int,
) -> dict[str, object]:
    """Assess inclusive usage and replacement text; never execute returned source.

    Missing/invalid reply evidence is partial. A valid complete proposal that
    misses a declared margin is a complete negative observation.
    """
    try:
        parent = _digest(parent_source_sha256)
        expected_model = _text(model)
        context = _integer(context_tokens, 1)
        cap = _integer(output_cap_tokens, 1)
        context_margin = _integer(min_context_slack)
        output_margin = _integer(min_output_slack)
    except (ReleaseError, ValueError, TypeError):
        raise SourceCapacityError("invalid prospective capacity parameters") from None

    result: dict[str, object] = {
        "measurement_status": "partial",
        "decision": "unavailable",
        "reason": "usage_unavailable",
        "usage": None,
        "finish_reason": None,
        "context_slack": None,
        "output_slack": None,
        "proposal": None,
    }
    if isinstance(envelope, RawEnvelope) and envelope.provider != "openai":
        return result | {"reason": "response_mismatch"}
    try:
        usage = extract_usage(envelope)
    except WireError:
        return result
    result["usage"] = asdict(usage)
    if (
        usage.model != expected_model
        or usage.service_tier not in {"", "default"}
        or not usage.provider_request_id
    ):
        return result | {"reason": "response_mismatch"}
    context_slack, output_slack = context - usage.input_tokens - cap, cap - usage.output_tokens
    result.update(context_slack=context_slack, output_slack=output_slack)
    if usage.input_tokens > context or usage.output_tokens > cap:
        return result | {"reason": "usage_bound"}

    try:
        raw = _load(decoded_body(envelope))
        choices = raw.get("choices")
        if type(choices) is not list or len(choices) != 1:
            raise ReleaseError("expected one choice")
        choice = _object(choices[0])
        finish = _text(choice.get("finish_reason"))
        message = _object(choice.get("message"))
        refusal = message.get("refusal")
        if refusal is not None and type(refusal) is not str:
            raise ReleaseError("expected literal refusal text")
    except (ReleaseError, UnicodeError, TypeError):
        return result | {"reason": "invalid_response"}
    result["finish_reason"] = finish
    if refusal or finish == "content_filter":
        return result | {"reason": "refusal"}
    if finish == "length":
        return result | {"reason": "output_limit"}
    if finish != "stop":
        return result | {"reason": "unsupported_finish"}
    content = message.get("content")
    if type(content) is not str:
        return result | {"reason": "invalid_response"}
    try:
        proposal_json = _load(content.encode("utf-8"))
    except (ReleaseError, UnicodeError):
        return result | {"reason": "invalid_proposal_json"}
    try:
        proposal = _source_proposal(proposal_json)
    except ReleaseError:
        return result | {"reason": "proposal_bound"}
    if hashlib.sha256(proposal["source"].encode("utf-8")).hexdigest() == parent:
        return result | {"reason": "source_unchanged"}
    passed = context_slack >= context_margin and output_slack >= output_margin
    return result | {
        "measurement_status": "complete",
        "decision": "pass" if passed else "fail",
        "reason": "capacity_pass" if passed else "margin_failed",
        "proposal": proposal,
    }
