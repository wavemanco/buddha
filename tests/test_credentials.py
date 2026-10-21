"""Shared hidden entry remains usable without the retired scientific CLI."""

import getpass
import os
import subprocess
import sys
import unittest
import warnings
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock, patch

from buddha.common import ValidationError
from buddha.credentials import KeyInputError, key_environment


def profiles(*providers):
    return SimpleNamespace(
        profiles=Mock(return_value=[SimpleNamespace(provider=provider) for provider in providers])
    )


class CredentialTests(unittest.TestCase):
    def test_clean_import_needs_only_generic_host_code(self):
        root = Path(__file__).resolve().parents[1]
        script = """
import importlib.abc
import sys

forbidden = {
    'buddha.__main__', 'buddha.benchmark', 'buddha.evaluation', 'buddha.run',
    'buddha.search', 'buddha.proposer', 'openai', 'anthropic',
}

class NoScience(importlib.abc.MetaPathFinder):
    def find_spec(self, fullname, path=None, target=None):
        if fullname in forbidden:
            raise AssertionError('retired science or SDK import: ' + fullname)

sys.meta_path.insert(0, NoScience())
from buddha.common import ValidationError
from buddha.credentials import KeyInputError, key_environment
assert issubclass(KeyInputError, ValidationError)
assert callable(key_environment)
assert not forbidden.intersection(sys.modules)
"""
        result = subprocess.run(
            [sys.executable, "-B", "-c", script],
            cwd=root,
            env={"PYTHONPATH": str(root), "PYTHONDONTWRITEBYTECODE": "1", "PYTHONUTF8": "1"},
            capture_output=True,
            text=True,
            timeout=10,
            check=False,
        )
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)

    def test_both_providers_deduplicate_and_notice_before_hidden_entry(self):
        settings = profiles("openai", "openai", "replay", "anthropic")
        notices = []
        answers = iter(("offline-openai", "offline-anthropic"))

        def prompt(label):
            self.assertEqual(
                notices[-1],
                "Key input is hidden. Paste once, then press Enter; no characters appear.",
            )
            return next(answers)

        with (
            patch.dict(os.environ, {}, clear=True),
            patch("buddha.credentials.sys.stdin.isatty", return_value=True),
            patch("buddha.credentials.sys.stderr.isatty", return_value=True),
            patch("buddha.credentials.getpass.getpass", side_effect=prompt) as entered,
        ):
            with key_environment(settings, prompt_keys=True, notice=notices.append):
                self.assertEqual(
                    dict(os.environ),
                    {
                        "OPENAI_API_KEY": "offline-openai",
                        "ANTHROPIC_API_KEY": "offline-anthropic",
                    },
                )
            self.assertEqual(dict(os.environ), {})
        self.assertEqual(entered.call_count, 2)
        self.assertIn("OPENAI_API_KEY", entered.call_args_list[0].args[0])
        self.assertIn("ANTHROPIC_API_KEY", entered.call_args_list[1].args[0])
        self.assertNotIn("offline-openai", "\n".join(notices))
        self.assertNotIn("offline-anthropic", "\n".join(notices))

    def test_default_is_lazy_and_existing_keys_bypass_terminal_input(self):
        lazy = SimpleNamespace(profiles=Mock(side_effect=AssertionError("profiles inspected")))
        with (
            patch.dict(os.environ, {}, clear=True),
            patch("buddha.credentials.getpass.getpass") as entered,
            patch("buddha.credentials.sys.stdin.isatty") as terminal,
        ):
            with key_environment(lazy, prompt_keys=False, notice=Mock()):
                pass
            lazy.profiles.assert_not_called()
            terminal.assert_not_called()
            entered.assert_not_called()
        existing = {"OPENAI_API_KEY": "offline-existing-a", "ANTHROPIC_API_KEY": "offline-b"}
        with (
            patch.dict(os.environ, existing, clear=True),
            patch("buddha.credentials.getpass.getpass") as entered,
            patch("buddha.credentials.sys.stdin.isatty") as terminal,
        ):
            with key_environment(profiles("openai", "anthropic"), prompt_keys=True, notice=Mock()):
                self.assertEqual(dict(os.environ), existing)
            self.assertEqual(dict(os.environ), existing)
            terminal.assert_not_called()
            entered.assert_not_called()

    def test_nonterminal_refuses_without_prompt_or_body(self):
        with (
            patch.dict(os.environ, {}, clear=True),
            patch("buddha.credentials.sys.stdin.isatty", return_value=False),
            patch("buddha.credentials.getpass.getpass") as entered,
        ):
            with self.assertRaises(KeyInputError) as caught:
                with key_environment(profiles("openai"), prompt_keys=True, notice=Mock()):
                    self.fail("nonterminal entry reached execution")
            self.assertEqual(caught.exception.code, "key_terminal_required")
            self.assertIsInstance(caught.exception, ValidationError)
            entered.assert_not_called()
            self.assertEqual(dict(os.environ), {})

    def test_partial_entry_errors_keep_fixed_codes_and_restore_environment(self):
        cases = (
            (EOFError("offline-private-error"), "key_input_unavailable"),
            (getpass.GetPassWarning("offline-private-error"), "key_input_unavailable"),
            ("", "key_input_invalid"),
            ("offline bad space", "key_input_invalid"),
            ("offline-\u00e9", "key_input_invalid"),
        )
        for failure, code in cases:
            with (
                self.subTest(code=code, failure=type(failure).__name__),
                patch.dict(os.environ, {"OPENAI_API_KEY": ""}, clear=True),
                patch("buddha.credentials.sys.stdin.isatty", return_value=True),
                patch("buddha.credentials.sys.stderr.isatty", return_value=True),
                patch("buddha.credentials.getpass.getpass", side_effect=["offline-a", failure]),
            ):
                with self.assertRaises(KeyInputError) as caught:
                    with key_environment(
                        profiles("openai", "anthropic"), prompt_keys=True, notice=Mock()
                    ):
                        self.fail("partial entry reached execution")
                self.assertEqual(caught.exception.code, code)
                self.assertNotIn("offline", str(caught.exception))
                self.assertEqual(dict(os.environ), {"OPENAI_API_KEY": ""})

    def test_actual_getpass_warning_is_an_error_and_never_echoes(self):
        def warned(_):
            warnings.warn("offline fallback would echo", getpass.GetPassWarning, stacklevel=1)
            self.fail("warning fallback continued")

        with (
            patch.dict(os.environ, {}, clear=True),
            patch("buddha.credentials.sys.stdin.isatty", return_value=True),
            patch("buddha.credentials.sys.stderr.isatty", return_value=True),
            patch("buddha.credentials.getpass.getpass", side_effect=warned),
        ):
            with self.assertRaises(KeyInputError) as caught:
                with key_environment(profiles("openai"), prompt_keys=True, notice=Mock()):
                    self.fail("warned entry reached execution")
            self.assertEqual(caught.exception.code, "key_input_unavailable")
            self.assertEqual(dict(os.environ), {})

    def test_interrupt_during_entry_or_body_restores_every_new_value(self):
        for during_entry in (True, False):
            answers = (
                ["offline-a", KeyboardInterrupt()] if during_entry else ["offline-a", "offline-b"]
            )
            with (
                self.subTest(during_entry=during_entry),
                patch.dict(os.environ, {}, clear=True),
                patch("buddha.credentials.sys.stdin.isatty", return_value=True),
                patch("buddha.credentials.sys.stderr.isatty", return_value=True),
                patch("buddha.credentials.getpass.getpass", side_effect=answers),
            ):
                with self.assertRaises(KeyboardInterrupt):
                    with key_environment(
                        profiles("openai", "anthropic"), prompt_keys=True, notice=Mock()
                    ):
                        raise KeyboardInterrupt
                self.assertEqual(dict(os.environ), {})

    def test_legacy_exports_and_late_notice_patch_remain_compatible(self):
        from buddha import __main__ as cli

        self.assertIs(cli.KeyInputError, KeyInputError)
        self.assertIs(cli.getpass, getpass)
        notices = []
        with (
            patch.dict(os.environ, {}, clear=True),
            patch("buddha.__main__.sys.stdin.isatty", return_value=True),
            patch("buddha.__main__.sys.stderr.isatty", return_value=True),
            patch("buddha.__main__._notice", side_effect=notices.append),
            patch("buddha.__main__.getpass.getpass", return_value="offline-a") as entered,
        ):
            with cli._key_environment(profiles("openai"), prompt_keys=True):
                self.assertEqual(os.environ["OPENAI_API_KEY"], "offline-a")
            self.assertEqual(dict(os.environ), {})
        entered.assert_called_once()
        self.assertEqual(len(notices), 2)
        self.assertIn("received", notices[1])


if __name__ == "__main__":
    unittest.main()
