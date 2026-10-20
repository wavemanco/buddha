"""Bounded JSONL framing shared by the worker and its trusted host."""

from typing import BinaryIO

from buddha.releases import ReleaseError, _json, _load, _object

MAX_FRAME_BYTES = 32 * 1024**2
MAX_DEPTH = 64


class ChannelError(ReleaseError):
    """The bounded channel cannot establish one complete valid frame."""


def _depth(value: object, depth: int = 0) -> None:
    if depth > MAX_DEPTH:
        raise ChannelError("channel frame exceeds structural depth")
    if isinstance(value, dict):
        for item in value.values():
            _depth(item, depth + 1)
    elif isinstance(value, list):
        for item in value:
            _depth(item, depth + 1)


def read_frame(stream: BinaryIO) -> dict[str, object]:
    """Read at most one bounded newline-terminated UTF-8 JSON object."""
    try:
        raw = stream.readline(MAX_FRAME_BYTES + 1)
        if (
            type(raw) is not bytes
            or not raw
            or len(raw) > MAX_FRAME_BYTES
            or not raw.endswith(b"\n")
        ):
            raise ChannelError("channel requires a bounded complete binary frame")
        result = _load(raw[:-1])
        _depth(result)
        return result
    except (OSError, ValueError, RecursionError):
        raise ChannelError("channel frame is unavailable or invalid") from None


def write_frame(stream: BinaryIO, value: dict[str, object]) -> None:
    """Write a complete bounded frame, including short-write handling, then flush."""
    try:
        _object(value)
        _depth(value)
        raw = _json(value)
        if _load(raw) != value:
            raise ChannelError("channel data must preserve exact JSON types")
        raw += b"\n"
        if len(raw) > MAX_FRAME_BYTES:
            raise ChannelError("channel frame exceeds encoded byte ceiling")
        offset = 0
        while offset < len(raw):
            amount = stream.write(raw[offset:])
            if type(amount) is not int or not 0 < amount <= len(raw) - offset:
                raise ChannelError("channel write did not make bounded progress")
            offset += amount
        stream.flush()
    except (OSError, ValueError, RecursionError, TypeError):
        raise ChannelError("channel frame cannot be written") from None
