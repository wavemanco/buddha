"""Explicit v2 proposer contract; legacy search continues using its frozen v1.

This pure request builder neither sends requests nor creates spending authority.
Before a future funded invocation, its caller must freeze this contract record
and executing proposer sources through the existing Gateway input inventory.
"""

import hashlib
import json
from collections.abc import Mapping, Sequence
from typing import Any, cast

from buddha.policy import MUTATION_SYSTEM, Policy, proposal_schema, propose_call
from buddha.provider import Call, ModelSpec

_SAMPLING = (
    (
        "regenerate",
        "regenerate means independent sampling: each answer receives the original task "
        "and policy instructions without previous answers. Instructions alone cannot "
        "compare against outputs the generation request does not contain.",
    ),
    (
        "in-context",
        "in-context means history-aware sampling: each subsequent answer receives all "
        "preceding effective answers in their original order, each followed by the user "
        "continuation Can you generate a different answer? Effective answers include "
        "the seed's literal [empty] and [refused] placeholders. History can expose "
        "repetition and can also anchor later answers; it does not guarantee diversity.",
    ),
)

_SYSTEM = (
    MUTATION_SYSTEM.replace(
        "Buddha fixed policy proposer v1.", "Buddha fixed policy proposer v2.", 1
    )
    + "\nSampling semantics:\n"
    + "\n".join(text for _, text in _SAMPLING)
    + "\nThe policy is applied unchanged across tasks. The original task's literal "
    "format, count and tone take priority over general generation advice. Do not "
    "turn one feedback task's subject, sentence count, perspective or output form "
    "into unconditional requirements for other tasks. Keep advice conditional on "
    "the task where necessary. Do not add plans, critiques, alternatives or "
    "explanations to an answer unless its original task requests them. Schema "
    "validity alone does not establish task compliance or transfer."
)


def contract_record() -> dict[str, object]:
    """Return fresh, serializable v2 prompt/schema/semantics data; write nothing."""
    schema = proposal_schema()
    return {
        "format": "buddha.proposer-contract.v2",
        "system": _SYSTEM,
        "system_sha256": hashlib.sha256(_SYSTEM.encode("utf-8")).hexdigest(),
        "schema": schema,
        "schema_sha256": hashlib.sha256(
            json.dumps(schema, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode()
        ).hexdigest(),
        "sampling": dict(_SAMPLING),
    }


def propose_call_v2(
    spec: ModelSpec, *, parent: Policy, feedback: Sequence[Mapping[str, object]], method: str
) -> Call:
    """Reuse v1 validation and request fields, replacing only its system prompt."""
    original = propose_call(spec, parent=parent, feedback=feedback, method=method)
    body = cast(dict[str, Any], json.loads(original.body_json))
    if spec.provider == "anthropic":
        body["system"] = _SYSTEM
    else:
        body["messages"][0]["content"] = _SYSTEM
    return Call(
        original.spec,
        json.dumps(body, sort_keys=True, separators=(",", ":"), ensure_ascii=False),
    )
