"""Temporary hidden key entry, independent of benchmark and execution code."""

import getpass as getpass
import os as os
import sys
import warnings
from collections.abc import Callable, Iterable, Iterator
from contextlib import contextmanager
from typing import Protocol

from buddha.common import ValidationError


class _Profile(Protocol):
    @property
    def provider(self) -> str: ...


class ProfileSource(Protocol):
    def profiles(self) -> Iterable[_Profile]: ...


class KeyInputError(ValidationError):
    """A fixed credential-input guard reason, without credential contents."""

    def __init__(self, code: str) -> None:
        self.code = code
        super().__init__(
            {
                "key_terminal_required": "hidden key entry requires an interactive terminal",
                "key_input_unavailable": "hidden key entry was unavailable or cancelled",
                "key_input_invalid": "provider credential is missing or invalid",
            }[code]
        )


@contextmanager
def key_environment(
    settings: ProfileSource, *, prompt_keys: bool, notice: Callable[[str], None]
) -> Iterator[None]:
    """Acquire missing keys only in this trusted host's temporary environment.

    The caller supplies safe notices and keeps these values out of worker
    environments. Existing keys are untouched; new values are restored on exit.
    """
    previous: dict[str, str | None] = {}
    try:
        if prompt_keys:
            names = {
                "openai": "OPENAI_API_KEY",
                "anthropic": "ANTHROPIC_API_KEY",
            }
            for provider in dict.fromkeys(spec.provider for spec in settings.profiles()):
                name = names.get(provider)
                if name is None or os.environ.get(name):
                    continue
                if not sys.stdin.isatty() or not sys.stderr.isatty():
                    raise KeyInputError("key_terminal_required")
                notice("Key input is hidden. Paste once, then press Enter; no characters appear.")
                try:
                    with warnings.catch_warnings():
                        warnings.simplefilter("error", getpass.GetPassWarning)
                        value = getpass.getpass(f"{name} (hidden, this process only): ")
                except (EOFError, getpass.GetPassWarning):
                    raise KeyInputError("key_input_unavailable") from None
                if not value or any(not 33 <= ord(char) <= 126 for char in value):
                    raise KeyInputError("key_input_invalid")
                previous[name] = os.environ.get(name)
                os.environ[name] = value
                notice(f"{name} received (hidden; provider access is checked during execution).")
        yield
    finally:
        for name, old_value in previous.items():
            if old_value is None:
                os.environ.pop(name, None)
            else:
                os.environ[name] = old_value
