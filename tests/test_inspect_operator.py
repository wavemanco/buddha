"""The selected observer cannot change ordinary checks or enable live work."""

import hashlib
import importlib.util
import io
import json
import os
import tempfile
import unittest
from contextlib import redirect_stdout
from pathlib import Path
from unittest.mock import patch

from buddha import inspect_study, launch_common


class InspectOperatorTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name).resolve()
        path = Path(__file__).parents[1] / "docs/conformance/unified-run.py"
        spec = importlib.util.spec_from_file_location("inspect_operator", path)
        self.cli = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(self.cli)
        self.args = ["--handoff", "unused.json", "--sha256", "0" * 64]

    def test_inspect_check_preserves_canonical_result_directory_and_environment(self):
        original = Path.cwd()
        runtime = self.root / "observation"
        checked = {"phase": "primary", "stop_code": None}
        calls = []

        def canonical(path, *, expected_sha256):
            self.assertEqual(Path.cwd(), original)
            calls.append((path, expected_sha256))
            return checked

        def observe(operation, *, log_dir):
            self.assertEqual(Path.cwd(), runtime)
            self.assertEqual(log_dir, runtime / "logs")
            self.assertEqual((runtime / ".env").read_bytes(), b"")
            for name in ("INSPECT_TRACE_FILE", "INSPECT_PY_LOGGER_FILE"):
                self.assertTrue(Path(os.environ[name]).is_relative_to(runtime))
            return operation()

        output = io.StringIO()
        with (
            patch.dict(os.environ, {"INSPECT_TRACE_FILE": "prior-value"}),
            patch.object(launch_common, "_receipt_roots", return_value=[]),
            patch.object(self.cli, "check_launch", side_effect=canonical),
            patch.object(inspect_study, "run", side_effect=observe) as observer,
            redirect_stdout(output),
        ):
            code = self.cli.main(self.args + ["--check", "--inspect-log-dir", str(runtime)])
            self.assertEqual(os.environ["INSPECT_TRACE_FILE"], "prior-value")
        self.assertEqual(code, 0)
        self.assertEqual(Path.cwd(), original)
        self.assertEqual(calls, [(original / "unused.json", "0" * 64)])
        self.assertEqual(observer.call_count, 1)
        self.assertEqual(json.loads(output.getvalue())["status"], "checked")

    def test_inspect_refuses_live_or_original_continuation_before_observer(self):
        for flags in ([], ["--live"], ["--check", "--live"], ["--check", "--continuation"]):
            runtime = self.root / "never-created"
            with (
                self.subTest(flags=flags),
                patch.object(inspect_study, "run") as observer,
                patch.object(self.cli, "launch") as launch,
                redirect_stdout(io.StringIO()),
            ):
                self.assertEqual(
                    self.cli.main(self.args + flags + ["--inspect-log-dir", str(runtime)]),
                    2,
                )
                observer.assert_not_called()
                launch.assert_not_called()
                self.assertFalse(runtime.exists())

    def test_observer_cannot_overwrite_originals_and_restores_context_after_failure(self):
        original = Path.cwd()
        with patch.object(launch_common, "_receipt_roots", return_value=[self.root]):
            with self.assertRaises(self.cli.UnifiedLaunchError):
                self.cli._inspect_check(
                    lambda: {}, self.root / "handoff", "0" * 64, self.root / "blocked"
                )
        self.assertFalse((self.root / "blocked").exists())
        failure = RuntimeError("private-canary")
        with (
            patch.dict(os.environ, {"INSPECT_PY_LOGGER_FILE": "prior-logger"}),
            patch.object(launch_common, "_receipt_roots", return_value=[]),
            patch.object(inspect_study, "run", side_effect=failure),
        ):
            with self.assertRaises(RuntimeError) as caught:
                self.cli._inspect_check(
                    lambda: {}, self.root / "handoff", "0" * 64, self.root / "failed"
                )
            self.assertEqual(os.environ["INSPECT_PY_LOGGER_FILE"], "prior-logger")
        self.assertIs(caught.exception, failure)
        self.assertEqual(Path.cwd(), original)

    def test_unified_envelope_exclusions_follow_both_pinned_inputs(self):
        # This passive exclusion check deliberately does not validate a whole study.
        def save(name, value):
            path = self.root / name
            raw = json.dumps(value).encode()
            path.write_bytes(raw)
            return {"path": str(path), "sha256": hashlib.sha256(raw).hexdigest()}

        primary = save("primary.json", {"directory": str(self.root / "primary")})
        plan = save("plan.json", {"directory": str(self.root / "plain")})
        (self.root / "plain").mkdir()
        source = self.root / "controller" / "entry.py"
        source.parent.mkdir()
        source.write_bytes(b"# fixed public controller\n")
        for version in (1, 2):
            handoff = save(
                f"unified-{version}.json",
                {
                    "format": f"buddha.unified-launch.v{version}",
                    "primary_launch": primary,
                    "comparison_plan": plan,
                    "directory": str(self.root / "combined"),
                    "source_sha256": {str(source): hashlib.sha256(source.read_bytes()).hexdigest()},
                },
            )
            roots = launch_common._receipt_roots(Path(handoff["path"]), handoff["sha256"])
            self.assertTrue(
                {self.root / name for name in ("primary", "plain", "combined")} <= set(roots)
            )
            with (
                patch.object(inspect_study, "run") as observer,
                self.assertRaises(self.cli.UnifiedLaunchError),
            ):
                self.cli._inspect_check(
                    lambda: {},
                    Path(handoff["path"]),
                    handoff["sha256"],
                    self.root / "plain" / "log",
                )
            observer.assert_not_called()
            self.assertFalse((self.root / "plain" / "log").exists())
            with (
                patch.object(inspect_study, "run") as observer,
                self.assertRaises(self.cli.UnifiedLaunchError),
            ):
                self.cli._inspect_check(
                    lambda: {}, Path(handoff["path"]), handoff["sha256"], source.parent / "log"
                )
            observer.assert_not_called()
            self.assertFalse((source.parent / "log").exists())
        (self.root / "plan.json").write_bytes(b"{}")
        with self.assertRaises(ValueError):
            launch_common._receipt_roots(Path(handoff["path"]), handoff["sha256"])
