"""Generic validation and canonical evidence JSON, without benchmark semantics."""

import json
import re
from typing import cast


class ValidationError(ValueError):
    """Evidence or configuration violates the experiment contract."""


def _integer(value: object, name: str, minimum: int) -> int:
    if type(value) is not int or value < minimum:
        raise ValidationError(f"{name} must be an integer >= {minimum}")
    return value


def _hex(value: object, name: str, length: int = 64) -> None:
    if not isinstance(value, str) or not re.fullmatch(rf"[0-9a-f]{{{length}}}", value):
        raise ValidationError(f"{name} must be {length} lowercase hexadecimal characters")


def _text(value: object, name: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValidationError(f"{name} must be nonblank text")
    return value


def _canonical(value: object) -> bytes:
    try:
        return json.dumps(
            value, sort_keys=True, separators=(",", ":"), ensure_ascii=True, allow_nan=False
        ).encode("utf-8")
    except (TypeError, ValueError, UnicodeError, RecursionError) as error:
        raise ValidationError("configuration or evidence is not finite JSON") from error


def _object(value: object) -> dict[str, object]:
    if not isinstance(value, dict) or any(not isinstance(k, str) for k in value):
        raise ValidationError("expected a JSON object with string keys")
    return cast(dict[str, object], value)


def _unique_pairs(pairs: list[tuple[str, object]]) -> dict[str, object]:
    result: dict[str, object] = {}
    for key, value in pairs:
        if key in result:
            raise ValidationError("duplicate JSON object key")
        result[key] = value
    return result


def _invalid_constant(value: str) -> object:
    raise ValidationError("nonfinite JSON number")


def _parse(raw: bytes) -> object:
    try:
        return cast(
            object,
            json.loads(
                raw.decode("utf-8"),
                object_pairs_hook=_unique_pairs,
                parse_constant=_invalid_constant,
            ),
        )
    except (UnicodeError, json.JSONDecodeError) as error:
        raise ValidationError("invalid UTF-8 JSON") from error
