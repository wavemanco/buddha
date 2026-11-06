"""Fast contracts for the optional adapter; real Inspect is exercised separately."""

import asyncio
import json
import os
import sys
import tempfile
import threading
import traceback
import unittest
from contextlib import asynccontextmanager, contextmanager, nullcontext
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock, patch

from buddha import improver_study, inspect_study, launch_common
from buddha.gateway import RawHTTPTransport
from buddha.search_evidence import EvidenceTotalLimitError


class InspectStudyTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.directory = Path(self.temporary.name).resolve()
        (self.directory / ".env").write_bytes(b"")
        previous = Path.cwd()
        os.chdir(self.directory)
        self.addCleanup(os.chdir, previous)
        environment = patch.dict(
            os.environ, {"INSPECT_TRACEBACK_LOCALS": "0", "INSPECT_TRACE_LEVEL": "TRACE"}
        )
        environment.start()
        self.addCleanup(environment.stop)
        self.events, self.errors, self.traces = [], [], []
        self.eval_options, self.state = {}, SimpleNamespace(metadata={})

    @contextmanager
    def trace(self, logger, action, detail):
        self.traces.append(("enter", json.loads(detail)))
        try:
            yield
        except BaseException as error:
            self.traces.append(("error", str(error), traceback.format_exc()))
            raise
        else:
            self.traces.append(("exit", json.loads(detail)))

    @asynccontextmanager
    async def span(self, name):
        yield

    def framework(self):
        def evaluate(task, **options):
            self.eval_options.update(options)
            self.task = task
            try:
                asyncio.run(task.solver(self.state, None))
            except BaseException as error:
                self.errors.append((str(error), traceback.format_exc()))
            return [SimpleNamespace(status="error" if self.errors else "success")]

        return (
            SimpleNamespace(Task=SimpleNamespace, eval=evaluate),
            SimpleNamespace(Sample=SimpleNamespace),
            SimpleNamespace(solver=lambda function: function),
            SimpleNamespace(transcript=lambda: SimpleNamespace(info=self.events.append)),
            SimpleNamespace(trace_action=self.trace, span=self.span),
        )

    def run_observed(self, operation, name="logs"):
        with patch.object(inspect_study, "_framework", return_value=self.framework()):
            return inspect_study.run(operation, log_dir=self.directory / name)

    def test_real_entry_calls_once_on_same_thread_and_replaces_heartbeat(self):
        expected = {"status": "checked", "unlogged_private_value": "SECRET"}
        original_thread, calls = threading.get_ident(), []

        def operation():
            self.assertEqual(threading.get_ident(), original_thread)
            calls.append(1)
            with launch_common._heartbeat(lambda text: None, ["checking"], [None], 0.01):
                with launch_common._study_stage(
                    "screen", {"start": 0, "arm": 1, "prompt": "SECRET"}
                ):
                    pass
            return expected

        with (
            patch.object(
                launch_common.threading, "Thread", side_effect=AssertionError("poller started")
            ),
            patch.object(launch_common, "_snapshot", side_effect=AssertionError("history read")),
        ):
            self.assertIs(self.run_observed(operation), expected)
        self.assertEqual(calls, [1])
        self.assertIsNone(launch_common._INSPECT_STAGE.get())
        self.assertEqual(self.eval_options["model"], None)
        for key in ("retry_on_error", "task_retry_attempts", "max_retries"):
            self.assertEqual(self.eval_options[key], 0)
        self.assertFalse(self.eval_options["score"])
        self.assertEqual(self.state.metadata["canonical_status"], "checked")
        self.assertEqual(
            {event["stage"] for event in self.events}, {"operation", "launcher", "screen"}
        )
        self.assertNotIn("SECRET", repr(self.events) + repr(self.traces))
        self.assertEqual(Path.cwd(), self.directory)
        self.assertEqual(os.environ["INSPECT_TRACEBACK_LOCALS"], "0")

    def test_errors_are_redacted_but_original_exception_identity_survives(self):
        secret = "SECRET_CANARY_MUST_NOT_BE_LOGGED"
        for index, kind in enumerate((ValueError, TimeoutError, KeyboardInterrupt, RuntimeError)):
            with self.subTest(kind=kind.__name__):
                original = kind(secret)
                operation = Mock(side_effect=original)
                with self.assertRaises(kind) as stopped:
                    self.run_observed(operation, "error" + str(index))
                self.assertIs(stopped.exception, original)
                operation.assert_called_once()
                self.assertNotIn(secret, repr(self.events) + repr(self.traces) + repr(self.errors))
                self.assertIsNone(launch_common._INSPECT_STAGE.get())

    def test_original_error_cause_context_suppression_and_stop_reason_survive(self):
        for explicit in (False, True):
            for framework_raises in (False, True):
                with self.subTest(explicit=explicit, framework_raises=framework_raises):
                    try:
                        try:
                            raise EvidenceTotalLimitError("SECRET_CAUSE")
                        except EvidenceTotalLimitError as cause:
                            try:
                                raise KeyError("SECRET_CONTEXT")
                            except KeyError:
                                if explicit:
                                    raise ValueError("SECRET_ORIGINAL") from cause
                                raise ValueError("SECRET_ORIGINAL")  # noqa: B904 - Exercise implicit context.
                    except ValueError as error:
                        original = error
                    attributes = (
                        original.__cause__,
                        original.__context__,
                        original.__suppress_context__,
                    )
                    reason = launch_common._stop_reason(original)
                    framework = self.framework()
                    if framework_raises:
                        evaluate = framework[0].eval

                        def failed_framework(*args, target=evaluate, **kwargs):
                            target(*args, **kwargs)
                            raise RuntimeError("framework ended")

                        framework[0].eval = failed_framework
                    with (
                        patch.object(inspect_study, "_framework", return_value=framework),
                        self.assertRaises(ValueError) as stopped,
                    ):
                        inspect_study.run(
                            Mock(side_effect=original),
                            log_dir=self.directory
                            / ("chain-" + str(explicit) + str(framework_raises)),
                        )
                    self.assertIs(stopped.exception, original)
                    self.assertIs(original.__cause__, attributes[0])
                    self.assertIs(original.__context__, attributes[1])
                    self.assertEqual(original.__suppress_context__, attributes[2])
                    self.assertEqual(launch_common._stop_reason(original), reason)
                    self.assertEqual(reason, "evidence_total_bytes_limit")
                    self.assertNotIn(
                        "SECRET_", repr(self.events) + repr(self.traces) + repr(self.errors)
                    )

    def test_incomplete_result_stays_incomplete_and_inspect_records_error(self):
        partial = {"status": "incomplete", "reason": "private reason omitted"}
        self.assertIs(self.run_observed(lambda: partial), partial)
        self.assertEqual(self.state.metadata["canonical_status"], "incomplete")
        self.assertTrue(self.errors)
        self.assertNotIn(partial["reason"], repr(self.errors) + repr(self.events))

    def test_failed_log_after_return_does_not_claim_observation_success(self):
        framework = self.framework()
        evaluate = framework[0].eval

        def failed_log(*args, **kwargs):
            evaluate(*args, **kwargs)
            return [SimpleNamespace(status="error")]

        framework[0].eval = failed_log
        operation = Mock(return_value={"status": "checked"})
        with patch.object(inspect_study, "_framework", return_value=framework):
            with self.assertRaisesRegex(RuntimeError, "observation did not complete"):
                inspect_study.run(operation, log_dir=self.directory / "log-failure")
        operation.assert_called_once()
        self.assertIsNone(launch_common._INSPECT_STAGE.get())

    def test_unrecognised_canonical_status_is_not_logged(self):
        canonical = {"status": {"SECRET": "payload"}}
        self.assertIs(self.run_observed(lambda: canonical), canonical)
        self.assertEqual(self.state.metadata["canonical_status"], "returned")
        self.assertNotIn("SECRET", repr(self.events) + repr(self.errors))

    def test_real_shaped_blocked_check_is_logged_as_stopped(self):
        canonical = {"phase": "search", "state": "fresh", "stop_code": "SECRET_STOP_DETAIL"}
        self.assertIs(self.run_observed(lambda: canonical), canonical)
        self.assertEqual(self.state.metadata["canonical_status"], "stopped")
        self.assertTrue(self.errors)
        self.assertNotIn("SECRET_STOP_DETAIL", repr(self.events) + repr(self.errors))

    def test_bad_startup_refuses_before_framework_import_or_operation(self):
        for kind in ("dotenv", "locals", "trace", "external_file", "relative", "existing"):
            with self.subTest(kind=kind):
                (self.directory / ".env").write_bytes(b"SECRET" if kind == "dotenv" else b"")
                destination = self.directory / ("bad-" + kind)
                if kind == "existing":
                    destination.mkdir()
                if kind == "relative":
                    destination = Path("relative")
                changes = {
                    "INSPECT_TRACEBACK_LOCALS": "1" if kind == "locals" else "0",
                    "INSPECT_TRACE_LEVEL": "WARNING" if kind == "trace" else "TRACE",
                }
                if kind == "external_file":
                    changes["INSPECT_TRACE_FILE"] = str(self.directory.parent / "outside.trace")
                with (
                    patch.dict(os.environ, changes),
                    patch.object(inspect_study, "_framework") as framework,
                ):
                    operation = Mock()
                    with self.assertRaises((ValueError, OSError)):
                        inspect_study.run(operation, log_dir=destination)
                    framework.assert_not_called()
                    operation.assert_not_called()

    def test_preloaded_inspect_refuses_before_log_creation_or_operation(self):
        for name in ("inspect_ai", "inspect_ai.cached_logger"):
            with self.subTest(name=name):
                output = self.directory / "preloaded"
                operation = Mock()
                with (
                    patch.dict(sys.modules, {name: SimpleNamespace()}),
                    patch.object(inspect_study, "_framework") as framework,
                    self.assertRaisesRegex(ValueError, "fresh process"),
                ):
                    inspect_study.run(operation, log_dir=output)
                framework.assert_not_called()
                operation.assert_not_called()
                self.assertFalse(output.exists())

    def test_dangling_file_override_is_not_followed(self):
        target = self.directory / "not-created"
        link = self.directory / "dangling"
        try:
            link.symlink_to(target)
        except OSError as error:
            if os.name == "nt" and error.winerror == 1314:
                self.skipTest("Windows symlink privilege unavailable")
            raise
        self.assertFalse(link.exists())
        self.assertTrue(os.path.lexists(link))
        for name in ("INSPECT_TRACE_FILE", "INSPECT_PY_LOGGER_FILE"):
            with self.subTest(name=name):
                operation = Mock()
                with (
                    patch.dict(os.environ, {name: str(link)}),
                    patch.object(inspect_study, "_framework") as framework,
                    self.assertRaisesRegex(ValueError, "file overrides"),
                ):
                    inspect_study.run(operation, log_dir=self.directory / "dangling-logs")
                framework.assert_not_called()
                operation.assert_not_called()
                self.assertTrue(os.path.lexists(link))
                self.assertFalse(target.exists())

    def test_ordinary_scope_does_not_import_inspect(self):
        with patch.object(
            inspect_study.importlib, "import_module", side_effect=AssertionError("import")
        ):
            with launch_common._study_stage("restore"):
                pass

    def test_actual_study_dispatch_is_observed_without_changing_stage_order(self):
        canonical = {"status": "complete"}
        position = {"start": 0, "repetition": 0, "arm": 0, "slot": 0}
        state = {"action": {"kind": "freeze", "position": position}}
        reader = SimpleNamespace(capture=SimpleNamespace(finish=lambda: None))
        authority = SimpleNamespace(_terms=lambda: {})
        stages = []

        @contextmanager
        def observer(name, coordinate):
            stages.append(name)
            yield

        def forward(previous, current):
            current["action"] = {"kind": "publish", "position": position}
            return previous, current

        token = launch_common._INSPECT_STAGE.set(observer)
        try:
            with (
                patch.object(
                    improver_study, "_context", return_value={"authorization": str(self.directory)}
                ),
                patch.object(improver_study, "Authorization", return_value=authority),
                patch.object(improver_study.trial_fence, "work", return_value=nullcontext()),
                patch.object(improver_study.pipeline, "_exclusive", return_value=nullcontext()),
                patch.object(improver_study, "_restore", return_value=(reader, state)),
                patch.object(improver_study, "_check_current"),
                patch.object(
                    improver_study, "_advance_action", side_effect=[None, canonical]
                ) as advance,
                patch.object(improver_study, "_forward_read", side_effect=forward),
            ):
                result = improver_study.run_improver_study(
                    self.directory, transport=RawHTTPTransport()
                )
        finally:
            launch_common._INSPECT_STAGE.reset(token)
        self.assertIs(result, canonical)
        self.assertEqual(advance.call_count, 2)
        self.assertEqual(stages, ["restore", "freeze", "forward_read", "restore", "publish"])
