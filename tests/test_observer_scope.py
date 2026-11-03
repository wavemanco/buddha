"""Injected observer scopes replace polling without owning execution."""

import hashlib
import io
import json
import unittest
from contextlib import ExitStack, contextmanager
from pathlib import Path
from unittest.mock import patch

from buddha import launch_common, progress
from buddha.evaluation import ValidationError
from buddha.reference import judge_body


class RecordedScope:
    def __init__(self, events, *, fail=None, error=None, suppress=False):
        self.events = events
        self.fail = fail
        self.error = error
        self.suppress = suppress

    def __enter__(self):
        self.events.append("enter")
        if self.fail == "enter":
            raise self.error
        return self

    def __exit__(self, kind, error, traceback):
        self.events.append(("exit", kind, error))
        if self.fail == "exit":
            raise self.error
        return self.suppress


class ObserverScopeTests(unittest.TestCase):
    def scope(self, kind, observer):
        if kind == "progress":
            return progress.Progress(
                Path("unused-observer-run"), stream=io.StringIO(), observer=observer
            )
        return launch_common._heartbeat(
            lambda message: self.fail("legacy notice called"),
            ["synthetic"],
            [Path("unused-observer-authority")],
            1,
            observer=observer,
        )

    @contextmanager
    def forbid_legacy(self):
        with ExitStack() as stack:
            spies = [
                stack.enter_context(patch.object(owner, name))
                for owner, name in (
                    (progress.Progress, "_observe"),
                    (progress.Progress, "_write"),
                    (progress, "snapshot"),
                    (launch_common, "_snapshot"),
                    (launch_common, "_finish_snapshot"),
                    (launch_common, "_emit"),
                )
            ]
            spies.append(stack.enter_context(patch("threading.Thread")))
            yield
            for spy in spies:
                spy.assert_not_called()

    def test_progress_scope_bypasses_legacy_reads_threads_and_display(self):
        events = []

        def observer(label):
            events.append(label)
            return RecordedScope(events)

        expected = judge_body("Partition", "synthetic observer input")
        with self.forbid_legacy(), self.scope("progress", observer) as entered:
            self.assertIsInstance(entered, progress.Progress)
            actual = judge_body("Partition", "synthetic observer input")

        def digest(value):
            return hashlib.sha256(
                json.dumps(value, sort_keys=True, separators=(",", ":")).encode()
            ).hexdigest()

        self.assertEqual(digest(actual), digest(expected))
        self.assertEqual(events, ["progress", "enter", ("exit", None, None)])

    def test_heartbeat_scope_bypasses_legacy_reads_threads_and_display(self):
        events = []

        def observer(label):
            events.append(label)
            return RecordedScope(events)

        with self.forbid_legacy():
            with self.assertRaises(ValidationError) as caught:
                with self.scope("launcher", observer):
                    judge_body("Invalid", "synthetic observer input")
        self.assertEqual(events[:2], ["launcher", "enter"])
        self.assertEqual(events[2][:2], ("exit", ValidationError))
        self.assertIs(events[2][2], caught.exception)

    def test_ordinary_observer_failures_preserve_result_without_polling_fallback(self):
        for kind in ("progress", "launcher"):
            for failing in ("factory", "enter", "exit"):
                with self.subTest(kind=kind, failing=failing), self.forbid_legacy():
                    events, calls, result = [], [], object()

                    def observer(label, failing=failing, events=events):
                        if failing == "factory":
                            raise RuntimeError("synthetic observer failure")
                        return RecordedScope(
                            events, fail=failing, error=RuntimeError("synthetic observer failure")
                        )

                    def operation(kind=kind, observer=observer, calls=calls, result=result):
                        with self.scope(kind, observer):
                            calls.append("operation")
                            return result

                    self.assertIs(operation(), result)
                    self.assertEqual(calls, ["operation"])

    def test_body_error_identity_wins_over_suppression_or_any_cleanup_failure(self):
        for kind in ("progress", "launcher"):
            for body_type in (ValidationError, KeyboardInterrupt, SystemExit):
                for cleanup in (None, RuntimeError, KeyboardInterrupt, SystemExit):
                    with self.subTest(kind=kind, body=body_type, cleanup=cleanup):
                        body_error = body_type("synthetic body failure")
                        cleanup_error = None if cleanup is None else cleanup("synthetic cleanup")
                        events = []

                        def observer(
                            label, events=events, cleanup=cleanup, cleanup_error=cleanup_error
                        ):
                            return RecordedScope(
                                events,
                                fail=None if cleanup is None else "exit",
                                error=cleanup_error,
                                suppress=True,
                            )

                        with self.forbid_legacy():
                            with self.assertRaises(body_type) as caught:
                                with self.scope(kind, observer):
                                    raise body_error
                        self.assertIs(caught.exception, body_error)
                        self.assertIs(events[-1][2], body_error)

    def test_factory_and_entry_process_control_propagate_before_operation(self):
        for kind in ("progress", "launcher"):
            for failing in ("factory", "enter"):
                for control_type in (KeyboardInterrupt, SystemExit):
                    with self.subTest(kind=kind, failing=failing, control=control_type):
                        events, calls = [], []
                        control = control_type("synthetic observer control")

                        def observer(label, failing=failing, control=control, events=events):
                            if failing == "factory":
                                raise control
                            return RecordedScope(events, fail="enter", error=control)

                        with self.forbid_legacy():
                            with self.assertRaises(control_type) as caught:
                                with self.scope(kind, observer):
                                    calls.append("operation")
                        self.assertIs(caught.exception, control)
                        self.assertEqual(calls, [])
                        self.assertFalse(any(isinstance(event, tuple) for event in events))

    def test_clean_body_exit_process_control_propagates_after_one_operation(self):
        for kind in ("progress", "launcher"):
            for control_type in (KeyboardInterrupt, SystemExit):
                with self.subTest(kind=kind, control=control_type), self.forbid_legacy():
                    events, calls = [], []
                    control = control_type("synthetic observer control")

                    def observer(label, events=events, control=control):
                        return RecordedScope(events, fail="exit", error=control)

                    with self.assertRaises(control_type) as caught:
                        with self.scope(kind, observer):
                            calls.append("operation")
                    self.assertIs(caught.exception, control)
                    self.assertEqual(calls, ["operation"])

    def test_injected_progress_keeps_existing_interval_validation(self):
        for value in (0, -1, True, float("nan"), float("inf"), 61):
            with self.subTest(value=value):
                with self.assertRaises(ValueError):
                    progress.Progress(
                        Path("unused-observer-run"), poll_seconds=value, observer=lambda label: None
                    )
