"""Native v1.1 request JSON; constructing a body grants no paid authority.

The profile follows pinned upstream judge.py with explicit reference models,
including SDK serialization captured under its uv.lock. Legacy calls stay on
their frozen bounded profile. Accounting/parser integration is BENCH-02B/C.
"""

from buddha.benchmark import (
    DEFAULT_PARTITION_MODEL,
    DEFAULT_QUALITY_MODEL,
    PARTITION_SYSTEM,
    SCORE_SYSTEM,
    _utf8,
)
from buddha.evaluation import ValidationError, _text
from buddha.run import _schema


def judge_body(kind: str, user: str, *, fallback: bool = False) -> dict[str, object]:
    """Build the prescribed judge body without caps, tiers or added criteria.

    Anthropic's official 16,000-token cap remains. OpenAI's partition body has
    no cap; a future broker must reserve its verified maximum before dispatch.
    """
    if type(kind) is not str or kind not in ("Partition", "Score"):
        raise ValidationError("reference judgment must be Partition or Score")
    if type(fallback) is not bool or (kind == "Partition" and fallback):
        raise ValidationError("reference fallback is supported only for quality scoring")
    _utf8(_text(user, "judge input"))
    if kind == "Partition":
        return {
            "model": DEFAULT_PARTITION_MODEL,
            "messages": [
                {"role": "system", "content": PARTITION_SYSTEM},
                {"role": "user", "content": user},
            ],
            "response_format": {
                "type": "json_schema",
                "json_schema": {"name": kind, "strict": True, "schema": _schema(kind)},
            },
            "stream": False,
        }
    return {
        "model": "claude-sonnet-5" if fallback else DEFAULT_QUALITY_MODEL,
        "system": SCORE_SYSTEM,
        "messages": [{"role": "user", "content": user}],
        "max_tokens": 16000,
        "thinking": {"type": "adaptive"},
        "output_config": {
            "effort": "high",
            "format": {"type": "json_schema", "schema": _schema(kind)},
        },
    }
