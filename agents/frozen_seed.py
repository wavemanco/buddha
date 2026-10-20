"""Frozen seed recipe; the caller owns transport, credentials, accounting and raw evidence.

The callback receives (provider, request bytes) and returns parsed provider JSON.
Placeholders are effective answers, never replacements for the caller's raw receipts.
Blank prompts retain the original generation procedure's rejection behavior.
"""

import json
from collections.abc import Callable
from typing import TypedDict, cast


class SeedError(ValueError):
    """The seed configuration, task or provider response is unsupported."""


class _Config(TypedDict):
    provider: str
    model: str
    max_output_tokens: int
    instructions: str
    sampling: str


class _Task(TypedDict):
    id: str | int
    prompt: str
    count: int


def _object(value: object) -> dict[str, object]:
    if type(value) is not dict or any(type(key) is not str for key in value):
        raise SeedError("expected a provider, configuration or task object")
    return cast(dict[str, object], value)


def _text(value: object, *, blank: bool = True) -> str:
    if type(value) is not str or (not blank and not value.strip()):
        raise SeedError("expected literal text")
    try:
        value.encode("utf-8")
    except UnicodeError:
        raise SeedError("text must be valid UTF-8") from None
    return value


def _integer(value: object, minimum: int = 0, maximum: int = 2**63 - 1) -> int:
    if type(value) is not int or not minimum <= value <= maximum:
        raise SeedError("expected a bounded integer")
    return value


def _provider(value: object) -> str:
    if type(value) is not str or value not in {"openai", "anthropic"}:
        raise SeedError("unsupported provider")
    return value


def _config(value: object) -> _Config:
    raw = _object(value)
    if set(raw) != {"provider", "model", "max_output_tokens", "instructions", "sampling"}:
        raise SeedError("configuration has missing or unexpected fields")
    instructions, sampling = _text(raw["instructions"]), _text(raw["sampling"])
    if len(instructions) > 4000 or sampling not in {"regenerate", "in-context"}:
        raise SeedError("unsupported instructions or sampling mode")
    return {
        "provider": _provider(raw["provider"]),
        "model": _text(raw["model"], blank=False),
        "max_output_tokens": _integer(raw["max_output_tokens"], 1),
        "instructions": instructions,
        "sampling": sampling,
    }


def _task(value: object) -> _Task:
    raw = _object(value)
    if set(raw) != {"id", "prompt", "count"}:
        raise SeedError("task has missing or unexpected fields")
    identifier = raw["id"]
    if type(identifier) is int:
        _integer(identifier, -(2**63))
    else:
        identifier = _text(identifier, blank=False)
        if len(identifier) > 4096 or "\x00" in identifier:
            raise SeedError("unsupported task ID")
    return {
        "id": identifier,
        "prompt": _text(raw["prompt"], blank=False),
        "count": _integer(raw["count"], 1, 1000),
    }


def request(config: object, task: object, previous: object = ()) -> bytes:
    """Construct the original generation body, using history only in in-context mode."""
    selected, item = _config(config), _task(task)
    if type(previous) not in {list, tuple}:
        raise SeedError("history must be a list or tuple of literal answers")
    history = [_text(answer) for answer in cast(list[object] | tuple[object, ...], previous)]
    messages: list[dict[str, object]] = [{"role": "user", "content": item["prompt"]}]
    if selected["sampling"] == "in-context":
        for answer in history:
            messages.extend(
                [
                    {"role": "assistant", "content": answer},
                    {"role": "user", "content": "Can you generate a different answer?"},
                ]
            )
    body: dict[str, object] = {"model": selected["model"], "messages": messages}
    if selected["provider"] == "anthropic":
        body |= {
            "service_tier": "standard_only",
            "max_tokens": selected["max_output_tokens"],
            "thinking": {"type": "adaptive"},
            "output_config": {"effort": "low"},
        }
        messages[-1]["content"] = [
            {
                "type": "text",
                "text": messages[-1]["content"],
                "cache_control": {"type": "ephemeral"},
            }
        ]
        if selected["instructions"]:
            body["system"] = selected["instructions"]
    else:
        if selected["instructions"]:
            messages.insert(0, {"role": "system", "content": selected["instructions"]})
        body |= {
            "max_completion_tokens": selected["max_output_tokens"],
            "reasoning_effort": "low",
            "service_tier": "default",
        }
    return json.dumps(
        body, sort_keys=True, separators=(",", ":"), ensure_ascii=False, allow_nan=False
    ).encode("utf-8")


def normalize(provider: object, response: object) -> str:
    """Extract literal legacy answer text, preserving explicit empty/refused placeholders."""
    selected, raw = _provider(provider), _object(response)
    _text(raw.get("model"), blank=False)
    usage = _object(raw.get("usage"))
    if selected == "openai":
        _integer(usage.get("prompt_tokens"))
        _integer(usage.get("completion_tokens"))
        choices = raw.get("choices")
        if type(choices) is not list or len(choices) != 1:
            raise SeedError("expected exactly one completion")
        choice = _object(choices[0])
        message = _object(choice.get("message"))
        if not {"content", "refusal"}.intersection(message):
            raise SeedError("completion has no text or refusal field")
        content, refusal = message.get("content"), message.get("refusal")
        text = "" if content is None else _text(content)
        if refusal is not None:
            _text(refusal)
        finish = _text(choice.get("finish_reason"), blank=False)
        refused = bool(refusal) or finish == "content_filter"
        tier = raw.get("service_tier")
    else:
        inputs = _integer(usage.get("input_tokens"))
        inputs += _integer(usage.get("cache_creation_input_tokens", 0))
        inputs += _integer(usage.get("cache_read_input_tokens", 0))
        _integer(inputs)
        _integer(usage.get("output_tokens"))
        blocks = raw.get("content")
        if type(blocks) is not list:
            raise SeedError("expected text content blocks")
        parts = []
        for value in blocks:
            block = _object(value)
            kind = _text(block.get("type"), blank=False)
            if kind == "text":
                parts.append(_text(block.get("text")))
            elif kind not in {"thinking", "redacted_thinking"}:
                raise SeedError("unsupported completion content block")
        text = "".join(parts)
        finish = _text(raw.get("stop_reason"), blank=False)
        refused = finish == "refusal"
        tier = usage.get("service_tier")
    if tier is not None:
        _text(tier)
    if finish not in {
        "stop",
        "end_turn",
        "length",
        "max_tokens",
        "model_context_window_exceeded",
        "content_filter",
        "refusal",
    }:
        raise SeedError("unsupported completion status")
    return "[refused]" if refused else (text if text.strip() else "[empty]")


def generate(task: object, config: object, complete: Callable[[str, bytes], object]) -> list[str]:
    """Generate the selected count in order; callback failures escape without retry."""
    item, selected = _task(task), _config(config)
    if not callable(complete):
        raise SeedError("generation requires a completion callback")
    answers: list[str] = []
    for _ in range(item["count"]):
        raw = complete(selected["provider"], request(selected, item, answers))
        answers.append(normalize(selected["provider"], raw))
    return answers
