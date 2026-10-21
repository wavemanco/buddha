"""The paid operator entry point checks first and keeps key entry and waiting visible."""

import hashlib
import io
import json
import os
import py_compile
import tempfile
import threading
import unittest
from contextlib import contextmanager, redirect_stderr, redirect_stdout
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock, patch

from buddha.authorization import Authorization
from buddha.provider import ModelSpec

HELPER = Path(__file__).resolve().parents[1] / "docs/conformance/meas02-run.py"
namespace = {"__name__": "meas02_operator_test", "__file__": str(HELPER)}
exec(compile(HELPER.read_bytes(), str(HELPER), "exec"), namespace)  # nosec B102: reviewed engineering helper, never pyc.
main = namespace["main"]
execute = namespace["execute"]
OperatorError = namespace["OperatorError"]
KEY = "offline-operator-key-not-real"


class Terminal(io.StringIO):
    def __init__(self):
        super().__init__()
        self.flush_count = 0

    def isatty(self):
        return True

    def flush(self):
        self.flush_count += 1
        return super().flush()


class OperatorTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name).resolve()
        self.directory = self.root / "study"
        self.directory.mkdir()
        self.authority = Authorization.create(
            self.root / "authority.sqlite3",
            authorization_id="operator-test",
            budget_microusd=5_000_000,
            max_calls=120,
            scope="PRIVATE-ACCOUNT-SCOPE-CANARY",
        )
        self.profile = ModelSpec(
            "openai", "test-judge", 100, 100, 1_000_000, 2_000_000, "https://example.org/bounds"
        )
        self.facts = {
            "status": "ready",
            "next_batch": 0,
            "next_occasion": "baseline",
            "authorization_path": str(self.authority.path),
            "review": {
                "checked_on": "2026-10-20",
                "credential_sha256": {"openai": hashlib.sha256(KEY.encode()).hexdigest()},
                "account_scope": "PRIVATE-ACCOUNT-SCOPE-CANARY",
            },
            "profiles": [self.profile],
            "credential_sha256": {"openai": hashlib.sha256(KEY.encode()).hexdigest()},
        }
        self.report = {"status": "complete", "target_count": 40}
        self.controller = SimpleNamespace(
            check_native_audit=Mock(return_value=self.facts),
            run_native_audit=Mock(return_value=self.report),
            prepare_native_audit=Mock(return_value=self.directory),
        )
        self.out, self.err = Terminal(), Terminal()

    @contextmanager
    def operator(self, *, key="", prompt=None):
        with (
            patch.dict(namespace, {"_controller": lambda: self.controller}),
            patch.dict(os.environ, {"OPENAI_API_KEY": key}),
            patch("buddha.__main__.sys.stdin.isatty", return_value=True),
            patch("buddha.__main__.getpass.getpass", side_effect=prompt) as getpass,
            patch("http.client.HTTPSConnection", side_effect=AssertionError("provider forbidden")),
            patch("socket.create_connection", side_effect=AssertionError("network forbidden")),
            redirect_stdout(self.out),
            redirect_stderr(self.err),
        ):
            yield getpass

    def test_exact_source_loader_rejects_changed_bytes_and_ignores_bytecode(self):
        source = self.root / "controller.py"
        source.write_text("VALUE = 'poison'\n", encoding="utf-8")
        stamp = source.stat()
        cache = self.root / "__pycache__" / "controller.cpython-313.pyc"
        py_compile.compile(str(source), cfile=str(cache), doraise=True)
        source.write_text("VALUE = 'source'\n", encoding="utf-8")
        os.utime(source, ns=(stamp.st_atime_ns, stamp.st_mtime_ns))
        expected = hashlib.sha256(source.read_bytes()).hexdigest()
        with patch.dict(namespace, {"CONTROLLER": source, "CONTROLLER_SHA256": "0" * 64}):
            with self.assertRaises(OperatorError):
                namespace["_controller"]()
        with patch.dict(namespace, {"CONTROLLER": source, "CONTROLLER_SHA256": expected}):
            self.assertEqual(namespace["_controller"]().VALUE, "source")

    def test_all_preflight_failures_stop_before_key_prompt_or_execution(self):
        for label in ("source", "profile", "inactive", "unknown", "funds", "anchor"):
            self.controller.check_native_audit.side_effect = ValueError("SECRET-ERROR-" + label)
            with self.subTest(label=label), self.operator() as getpass:
                status = main(["run", "--run", str(self.directory), "--live", "--prompt-keys"])
                self.assertEqual(status, 2)
                getpass.assert_not_called()
                self.controller.run_native_audit.assert_not_called()
        self.assertNotIn("SECRET-ERROR", self.out.getvalue() + self.err.getvalue())

    def test_explicit_paid_flag_is_required_before_any_hidden_entry(self):
        with self.operator() as getpass:
            self.assertEqual(main(["run", "--run", str(self.directory), "--prompt-keys"]), 2)
            getpass.assert_not_called()
            self.controller.run_native_audit.assert_not_called()
        self.assertIn("--live", self.err.getvalue())

    def test_completed_only_replay_is_keyless_and_uses_unpaid_transport(self):
        self.facts.update(status="complete", next_batch=None, next_occasion=None)
        with self.operator() as getpass:
            self.assertEqual(main(["run", "--run", str(self.directory)]), 0)
            getpass.assert_not_called()
            self.assertFalse(
                self.controller.run_native_audit.call_args.kwargs["transport"].allow_paid
            )
        self.assertIn("complete", self.out.getvalue())
        self.assertIn("no keys", self.err.getvalue().lower())

    def test_hidden_key_feedback_precedes_worker_and_environment_is_restored(self):
        events = []

        def prompt(_):
            self.assertIn("Paste once", self.err.getvalue())
            events.append("key")
            return KEY

        def run(directory, *, transport):
            self.assertEqual(directory, self.directory)
            self.assertTrue(transport.allow_paid)
            self.assertEqual(os.environ["OPENAI_API_KEY"], KEY)
            self.assertIn("OPENAI_API_KEY received", self.err.getvalue())
            self.assertIn("Starting", self.err.getvalue())
            events.append("worker")
            return self.report

        self.controller.run_native_audit.side_effect = run
        with self.operator(prompt=prompt) as getpass:
            self.assertEqual(
                main(["run", "--run", str(self.directory), "--live", "--prompt-keys"]), 0
            )
            getpass.assert_called_once()
            self.assertEqual(os.environ["OPENAI_API_KEY"], "")
        self.assertEqual(events, ["key", "worker"])
        self.assertGreater(self.err.flush_count, 2)
        for canary in (KEY, "PRIVATE-ACCOUNT-SCOPE-CANARY"):
            self.assertNotIn(canary, self.out.getvalue() + self.err.getvalue())

    def test_existing_key_is_checked_without_prompt_and_bad_keys_never_launch(self):
        with self.operator(key=KEY) as getpass:
            self.assertEqual(main(["run", "--run", str(self.directory), "--live"]), 0)
            getpass.assert_not_called()
        self.controller.run_native_audit.reset_mock()
        for key in ("", "different-key", "bad\nkey"):
            with self.subTest(key=key), self.operator(key=key) as getpass:
                self.assertEqual(main(["run", "--run", str(self.directory), "--live"]), 2)
                getpass.assert_not_called()
                self.controller.run_native_audit.assert_not_called()

    def test_review_matched_overlong_key_is_rejected_before_worker(self):
        key = "k" * 4097
        self.facts["credential_sha256"]["openai"] = hashlib.sha256(key.encode()).hexdigest()
        with self.operator(key=key) as getpass:
            self.assertEqual(main(["run", "--run", str(self.directory), "--live"]), 2)
            getpass.assert_not_called()
            self.controller.run_native_audit.assert_not_called()

    def test_blocked_call_has_flushed_numeric_heartbeat(self):
        repeated = threading.Event()
        original_write = self.err.write

        def write(text):
            result = original_write(text)
            if self.err.getvalue().count("Shared attempts") >= 2:
                repeated.set()
            return result

        def blocked(*args, **kwargs):
            if not repeated.wait(2):
                raise AssertionError("no heartbeat while provider callback blocked")
            return self.report

        self.controller.run_native_audit.side_effect = blocked
        with self.operator(key=KEY), patch.object(self.err, "write", side_effect=write):
            result = execute(self.directory, live=True, heartbeat_seconds=0.01)
        self.assertEqual(result, self.report)
        self.assertTrue(repeated.is_set())
        for text in ("spent $0.000000", "held $0.000000", "cap $5.000000"):
            self.assertIn(text, self.err.getvalue())
        self.assertNotIn("PRIVATE-ACCOUNT", self.err.getvalue())

    def test_cancellation_and_incomplete_never_claim_complete_and_cleanup_keys(self):
        with self.operator(prompt=KeyboardInterrupt):
            self.assertEqual(
                main(["run", "--run", str(self.directory), "--live", "--prompt-keys"]), 130
            )
            self.controller.run_native_audit.assert_not_called()
        self.out, self.err = Terminal(), Terminal()
        self.controller.run_native_audit.side_effect = KeyboardInterrupt
        with self.operator(prompt=lambda _: KEY):
            self.assertEqual(
                main(["run", "--run", str(self.directory), "--live", "--prompt-keys"]), 130
            )
            self.assertEqual(os.environ["OPENAI_API_KEY"], "")
        self.assertNotIn("Run complete", self.err.getvalue())
        self.assertNotIn(KEY, self.out.getvalue() + self.err.getvalue())
        self.out, self.err = Terminal(), Terminal()
        self.controller.run_native_audit.side_effect = None
        self.controller.run_native_audit.return_value = {
            "status": "incomplete",
            "result": "partial",
            "stopped_batch": 1,
            "stop": {"reason": "money", "codes": ["money"]},
            "observation": "observations/operator-fixture.json",
        }
        with self.operator(key=KEY):
            self.assertEqual(main(["run", "--run", str(self.directory), "--live"]), 3)
        self.assertIn("incomplete", self.out.getvalue())
        self.assertNotIn("Run complete", self.err.getvalue())

    def test_offline_check_and_prepare_use_existing_authority_without_key_entry(self):
        descriptor, review = self.root / "descriptor.json", self.root / "review.json"
        descriptor.write_text("{}", encoding="utf-8")
        review.write_text(json.dumps(self.facts["review"]), encoding="utf-8")
        with (
            self.operator() as getpass,
            patch.object(
                Authorization, "create", side_effect=AssertionError("new allocation forbidden")
            ),
        ):
            self.assertEqual(main(["check", "--run", str(self.directory)]), 0)
            self.assertEqual(
                main(
                    [
                        "prepare",
                        "--run",
                        str(self.directory),
                        "--descriptor",
                        str(descriptor),
                        "--authorization",
                        str(self.authority.path),
                        "--review",
                        str(review),
                    ]
                ),
                0,
            )
            getpass.assert_not_called()
            self.controller.run_native_audit.assert_not_called()
        call = self.controller.prepare_native_audit.call_args
        self.assertEqual(call.args, (self.directory,))
        self.assertEqual(call.kwargs["descriptor"], descriptor)
        self.assertIsInstance(call.kwargs["authorization"], Authorization)
        self.assertEqual(call.kwargs["review"], self.facts["review"])
        self.assertNotIn("credential_sha256", self.out.getvalue())

    def test_observation_failure_does_not_stop_execution_or_print_private_error(self):
        with (
            self.operator(key=KEY),
            patch.object(
                Authorization, "summary", side_effect=ValueError("PRIVATE-OBSERVATION-CANARY")
            ),
        ):
            result = execute(self.directory, live=True, heartbeat_seconds=0.01)
        self.assertEqual(result, self.report)
        self.assertIn("temporarily unavailable", self.err.getvalue())
        self.assertNotIn("PRIVATE-OBSERVATION", self.err.getvalue())
