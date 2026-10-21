"""The public handoff reports fixed input reasons without exposing credentials."""

import getpass
import json
import os
import unittest
from contextlib import chdir
from types import SimpleNamespace
from unittest.mock import patch

import test_meas02_live as fixtures

from buddha.__main__ import KeyInputError, _key_environment
from buddha.evaluation import ValidationError


class LiveInputDiagnosticsTests(unittest.TestCase):
    def setUp(self):
        self.fixture = fixture = fixtures.LiveHandoffTests("runTest")
        fixture.setUp()
        self.addCleanup(fixture.doCleanups)
        fixture.operator.OperatorError = fixtures.operator_namespace["OperatorError"]

    def result(self):
        return json.loads(self.fixture.out.getvalue().splitlines()[-1])

    def reset_output(self):
        for stream in (self.fixture.out, self.fixture.err):
            stream.seek(0)
            stream.truncate()

    def test_noninteractive_missing_key_has_actionable_reason_before_prompt_or_writes(self):
        fixture = self.fixture
        authority = fixture.fixture.authority.path
        before = authority.read_bytes()
        with (
            fixture.local() as prompt,
            patch("buddha.__main__.sys.stdin.isatty", return_value=False),
        ):
            self.assertEqual(fixture.command(), 2)
            prompt.assert_not_called()
        result = json.loads(fixture.out.getvalue().splitlines()[-1])
        self.assertEqual(result.get("reason_code"), "key_terminal_required")
        self.assertIn("interactive", result.get("action", ""))
        self.assertIn("key_terminal_required", fixture.err.getvalue())
        self.assertNotIn("Key input is hidden", fixture.err.getvalue())
        self.assertEqual(authority.read_bytes(), before)
        self.assertFalse(fixture.study.exists())
        self.assertFalse(fixture.review.exists())
        fixture.operator.execute.assert_not_called()

    def test_relative_handoff_cli_path_reaches_hidden_entry_without_preparing_or_spending(self):
        fixture = self.fixture
        authority = fixture.fixture.authority.path
        before = authority.read_bytes()
        with fixture.local(prompt=KeyboardInterrupt) as prompt, chdir(fixture.root):
            result = fixtures.main(
                [
                    "--handoff",
                    fixture.handoff.name,
                    "--live",
                    "--prompt-keys",
                    "--confirm-project-key",
                ]
            )
            self.assertEqual(result, 130)
            prompt.assert_called_once()
        self.assertEqual(self.result()["status"], "cancelled")
        self.assertEqual(authority.read_bytes(), before)
        self.assertFalse(fixture.study.exists())
        self.assertFalse(fixture.review.exists())
        fixture.operator.execute.assert_not_called()

    def test_unavailable_and_invalid_input_have_fixed_public_codes_without_secret_text(self):
        fixture = self.fixture
        canary = "PRIVATE-INPUT-CANARY"
        before = fixture.fixture.authority.path.read_bytes()
        for failure, expected in (
            (EOFError(canary), "key_input_unavailable"),
            (getpass.GetPassWarning(canary), "key_input_unavailable"),
            (lambda _: canary + " invalid space", "key_input_invalid"),
            (lambda _: "", "key_input_invalid"),
        ):
            self.reset_output()
            with self.subTest(expected=expected), fixture.local(prompt=failure):
                self.assertEqual(fixture.command(), 2)
                self.assertEqual(os.environ["OPENAI_API_KEY"], "")
            self.assertEqual(self.result()["reason_code"], expected)
            self.assertNotIn(canary, fixture.out.getvalue() + fixture.err.getvalue())
            self.assertFalse(fixture.review.exists())
            self.assertFalse(fixture.study.exists())
        self.assertEqual(fixture.fixture.authority.path.read_bytes(), before)

    def test_shared_errors_keep_validation_identity_messages_and_partial_cleanup(self):
        settings = SimpleNamespace(
            profiles=lambda: [
                SimpleNamespace(provider="openai"),
                SimpleNamespace(provider="anthropic"),
            ]
        )
        with (
            patch.dict(os.environ, {}, clear=True),
            patch("buddha.__main__.sys.stdin.isatty", return_value=True),
            patch("buddha.__main__.sys.stderr.isatty", return_value=True),
            patch("buddha.__main__._notice"),
            patch("buddha.__main__.getpass.getpass", side_effect=["offline-key", EOFError()]),
        ):
            with self.assertRaises(KeyInputError) as caught:
                with _key_environment(settings, prompt_keys=True):
                    self.fail("partial input cannot execute")
            self.assertIsInstance(caught.exception, ValidationError)
            self.assertEqual(caught.exception.code, "key_input_unavailable")
            self.assertEqual(str(caught.exception), "hidden key entry was unavailable or cancelled")
            self.assertEqual(dict(os.environ), {})

    def test_existing_key_bypasses_terminal_guard_and_remains_unchanged(self):
        fixture = self.fixture
        with (
            fixture.local(key=fixtures.KEY) as prompt,
            patch("buddha.__main__.sys.stdin.isatty", return_value=False),
        ):
            self.assertEqual(fixture.command(), 0)
            prompt.assert_not_called()
            self.assertEqual(os.environ["OPENAI_API_KEY"], fixtures.KEY)
        self.assertNotIn(fixtures.KEY, fixture.out.getvalue() + fixture.err.getvalue())

    def test_credentials_code_applies_only_to_the_known_local_validation_seam(self):
        fixture = self.fixture
        canary = "PRIVATE-CREDENTIAL-CANARY"
        with (
            fixture.local(key=fixtures.KEY),
            patch.object(
                fixture.operator,
                "_credentials",
                side_effect=fixture.operator.OperatorError(canary),
            ),
        ):
            self.assertEqual(fixture.command(), 2)
        self.assertEqual(self.result()["reason_code"], "key_credentials_rejected")
        self.assertFalse(fixture.study.exists())
        self.assertFalse(fixture.review.exists())
        self.reset_output()
        fixture.operator.execute.side_effect = fixture.operator.OperatorError(canary)
        with fixture.local(key=fixtures.KEY):
            self.assertEqual(fixture.command(), 2)
        self.assertEqual(self.result()["reason_code"], "handoff_stopped")
        self.assertNotIn(canary, fixture.out.getvalue() + fixture.err.getvalue())

    def test_spoofed_unknown_code_and_untrusted_exception_text_stay_redacted(self):
        fixture = self.fixture
        canary = "PRIVATE-EXCEPTION-CANARY"
        spoofed = KeyInputError("key_terminal_required")
        spoofed.code = canary
        spoofed.args = (canary,)
        for failure in (spoofed, RuntimeError(canary)):
            self.reset_output()
            with self.subTest(error=type(failure).__name__), fixture.local(prompt=failure):
                self.assertEqual(fixture.command(), 2)
            self.assertEqual(self.result()["reason_code"], "handoff_stopped")
            self.assertNotIn(canary, fixture.out.getvalue() + fixture.err.getvalue())
            self.assertFalse(fixture.study.exists())
            self.assertFalse(fixture.review.exists())

    def test_missing_confirmation_and_bad_options_are_static_before_configuration(self):
        fixture = self.fixture
        with (
            fixture.local(),
            patch.dict(
                fixtures.namespace,
                {"_configuration": lambda *_: self.fail("configuration cannot run")},
            ),
        ):
            self.assertEqual(fixture.command(flags=False), 2)
            self.assertEqual(self.result()["reason_code"], "live_confirmation_required")
            self.reset_output()
            self.assertEqual(fixtures.main(["--unknown", fixtures.KEY]), 2)
            self.assertEqual(self.result()["reason_code"], "invalid_options")
        self.assertNotIn(fixtures.KEY, fixture.out.getvalue() + fixture.err.getvalue())
