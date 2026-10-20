"""Trusted worker call identity, allocated at coroutine creation, never HTTP arrival.

This supplies context only. It neither executes an official CLI nor authorizes
network access, spending, source execution or a particular hook configuration.
"""

import hashlib
import inspect
from collections.abc import Callable, Coroutine, Iterator
from contextlib import contextmanager
from contextvars import ContextVar
from dataclasses import dataclass, field
from functools import wraps
from threading import Lock
from typing import Any

from buddha.releases import ReleaseError, _json, _text


class ContextError(ReleaseError):
    """A native call lacks a supported explicit identity context."""


class NativeStop(BaseException):
    """A durable host stop that must escape native SDK Exception retry handlers."""

    def __init__(self, reason: str) -> None:
        if type(reason) is not str or reason not in {
            "authority",
            "unknown",
            "protocol",
            "cancelled",
        }:
            raise ContextError("unsupported native stop reason")
        super().__init__("native bridge stopped: " + reason)
        self.reason = reason


def _label(value: object) -> str:
    try:
        return _text(value)
    except ReleaseError:
        raise ContextError("identity context requires bounded valid text") from None


def _sha(value: object) -> str:
    return hashlib.sha256(_json(value)).hexdigest()


@dataclass(slots=True)
class _Frame:
    identity: str
    depth: int
    children: int = 0
    attempts: int = 0
    lock: Lock = field(default_factory=Lock, repr=False)

    def allocate(self, *, physical: bool = False) -> int:
        with self.lock:
            value = self.attempts if physical else self.children
            if value >= 2**31 - 1:
                raise ContextError("native context counter limit exceeded")
            if physical:
                self.attempts += 1
            else:
                self.children += 1
            return value


class Contexts:
    def __init__(self) -> None:
        self._current: ContextVar[_Frame | None] = ContextVar("native_call", default=None)

    @contextmanager
    def row(self, identity: str) -> Iterator[None]:
        """Enter one explicit population/cache identity with independent counters."""
        frame = _Frame(_sha(["buddha.native-row.v1", _label(identity)]), 0)
        token = self._current.set(frame)
        try:
            yield
        finally:
            self._current.reset(token)

    def wrap[**P, T](
        self, function: Callable[P, Coroutine[Any, Any, T]], label: str
    ) -> Callable[P, Coroutine[Any, Any, T]]:
        """Allocate a child before scheduling; its body runs under that child's context."""
        label = _label(label)
        if not inspect.iscoroutinefunction(function):
            raise ContextError("native context hook requires an async function")
        signature = inspect.signature(function)

        @wraps(function)
        def create(*args: P.args, **kwargs: P.kwargs) -> Coroutine[Any, Any, T]:
            parent = self._current.get()
            if parent is None or parent.depth >= 64:
                raise ContextError("native coroutine requires a bounded row/call context")
            signature.bind(*args, **kwargs)
            frame = _Frame(
                _sha(["buddha.native-call.v1", parent.identity, label, parent.allocate()]),
                parent.depth + 1,
            )

            async def invoke() -> T:
                token = self._current.set(frame)
                try:
                    return await function(*args, **kwargs)
                finally:
                    self._current.reset(token)

            return invoke()

        return create

    def attempt(self) -> tuple[str, int]:
        """Allocate one physical attempt inside the active logical call."""
        frame = self._current.get()
        if frame is None or frame.depth == 0:
            raise ContextError("physical attempt requires an active logical call")
        return frame.identity, frame.allocate(physical=True)
