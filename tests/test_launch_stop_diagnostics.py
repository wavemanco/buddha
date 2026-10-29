"""Safe failure locations survive the actual nested launcher wrappers.

The composed check supplies synthetic controller state; it does not reconstruct
the original study, enter credentials, send requests or run a container.
"""

import copy
import hashlib
import json
import unittest
from contextlib import nullcontext
from datetime import UTC, datetime
from pathlib import Path
from unittest.mock import patch

import test_unified_launch as unified_fixtures

from buddha import improver_launch, improver_study, launch_common, native_pipeline, trial_fence
from buddha.common import ValidationError
from buddha.releases import _json

CANARY = "PRIVATE-CANARY-credential-and-error-text"
KINDS = {
    "os_error",
    "value_error",
    "type_error",
    "key_error",
    "runtime_error",
    "validation_error",
    "evidence_busy",
    "evidence_unsupported",
    "key_input",
    "evidence_total_limit",
    "evidence_field_limit",
    "evidence_path_limit",
    "other",
}


class PrivateError(RuntimeError):
    def __str__(self):
        raise AssertionError("exception text must not be inspected")


class LaunchStopDiagnosticTests(unittest.TestCase):
    def diagnostic(self, error):
        result = launch_common._stop_diagnostic(error)
        self.assertEqual(set(result), {"format", "reason", "chain"})
        self.assertEqual(result["format"], "buddha.launch-stop-diagnostic.v1")
        self.assertEqual(result["reason"], launch_common._stop_reason(error))
        self.assertLessEqual(len(result["chain"]), 8)
        for node in result["chain"]:
            self.assertEqual(set(node), {"kind", "frames"})
            self.assertIn(node["kind"], KINDS)
            self.assertLessEqual(len(node["frames"]), 8)
            for frame in node["frames"]:
                self.assertEqual(set(frame), {"file", "line"})
                self.assertEqual(Path(frame["file"]).name, frame["file"])
                self.assertTrue(frame["file"].endswith(".py"))
                self.assertIs(type(frame["line"]), int)
                self.assertGreater(frame["line"], 0)
                self.assertLessEqual(frame["line"], 1_000_000)
        encoded = _json(result)
        self.assertLessEqual(len(encoded), 12_000)
        self.assertNotIn(CANARY.encode(), encoded)
        self.assertEqual(json.loads(encoded), result)
        return result

    def test_actual_nested_search_failure_is_locatable_before_recording_without_dispatch(self):
        fixture = unified_fixtures.UnifiedLaunchLifecycleTests("runTest")
        fixture.setUp()
        self.addCleanup(fixture.doCleanups)
        (fixture.primary_root / "search/study").mkdir(parents=True)
        changed_input = fixture.root / (CANARY + ".txt")
        changed_input.write_text(CANARY, encoding="utf-8")
        review = {
            "format": "buddha.account-review.v2",
            "checked_on": datetime.now(UTC).date().isoformat(),
            "credential_context": fixture.record["primary_launch"]["sha256"],
            "credential_fingerprints": fixture.fingerprints,
            "account_scope": "synthetic local test only",
        }
        checked = {
            "directory": str(fixture.primary_root),
            "authorizations": dict.fromkeys(
                ("search", "validation", "final"), str(fixture.shared.path)
            ),
            "funding": {},
            "state": "prepared",
            "phase": "search",
            "stop_code": None,
            "review": review,
            "timeout_seconds": 30,
            "profiles": fixture.check(fixture.path, fixture.digest)["profiles"],
            "proposal": {},
            "bindings": {},
            "state_sha256": "0" * 64,
        }
        real_inner_launch = improver_launch.launch
        original_observe = fixture.observe

        def observe_after_diagnostic(output, **options):
            saved = list((fixture.workspace / "observations").glob("*.diagnostic.json"))
            self.assertEqual(len(saved), 1, "diagnostic must be durable before slow recording")
            fixture.events.append(("diagnostic_saved", json.loads(saved[0].read_bytes())))
            return original_observe(output, **options)

        fixture.observe = observe_after_diagnostic
        with (
            fixture.seams(),
            patch.object(improver_launch, "launch", side_effect=real_inner_launch),
            patch.object(
                improver_launch, "check_launch", side_effect=lambda *a, **k: copy.deepcopy(checked)
            ),
            patch.object(
                improver_study, "_context", return_value={"authorization": str(fixture.shared.path)}
            ),
            patch.object(
                improver_study,
                "_restore",
                return_value=(None, {"controls": {changed_input: "0" * 64}}),
            ),
            patch.object(trial_fence, "work", return_value=nullcontext()),
            patch.object(
                improver_study,
                "_advance_action",
                side_effect=AssertionError("scheduler must not advance"),
            ) as advance,
            self.assertRaises(improver_launch.ImproverLaunchError) as stopped,
        ):
            fixture.launch(notice=lambda text: fixture.events.append(("notice", text)))

        error = stopped.exception
        self.assertTrue(error.__suppress_context__)
        self.assertIsInstance(error.__context__, improver_study.ImproverStudyError)
        self.assertTrue(error.__context__.__suppress_context__)
        self.assertIsInstance(error.__context__.__context__, native_pipeline.PipelineError)
        diagnostic = self.diagnostic(error)
        self.assertEqual(diagnostic["reason"], "launch_stopped")
        self.assertIn("validation_error", {node["kind"] for node in diagnostic["chain"]})
        locations = {frame["file"] for node in diagnostic["chain"] for frame in node["frames"]}
        self.assertTrue(
            {"native_pipeline.py", "improver_study.py", "improver_launch.py"} <= locations
        )
        public_throw = native_pipeline._read.__code__
        self.assertTrue(
            any(
                frame["file"] == "native_pipeline.py"
                and public_throw.co_firstlineno <= frame["line"] < public_throw.co_firstlineno + 15
                for node in diagnostic["chain"]
                for frame in node["frames"]
            )
        )
        notices = [
            event
            for event in fixture.events
            if event[0] == "notice" and event[1].startswith("Stop diagnostic: ")
        ]
        self.assertEqual(len(notices), 1)
        emitted = json.loads(notices[0][1].removeprefix("Stop diagnostic: "))
        # Re-raising adds a later outer frame; persistence must equal the
        # diagnostic emitted before recording, not that later traceback.
        self.assertEqual(emitted["format"], diagnostic["format"])
        self.assertEqual(emitted["reason"], diagnostic["reason"])
        self.assertTrue(
            any(
                frame["file"] == "native_pipeline.py"
                and public_throw.co_firstlineno <= frame["line"] < public_throw.co_firstlineno + 15
                for node in emitted["chain"]
                for frame in node["frames"]
            )
        )
        observation = ("observation", "primary", "launch_stopped")
        self.assertLess(fixture.events.index(notices[0]), fixture.events.index(observation))
        saved = list((fixture.workspace / "observations").glob("*.diagnostic.json"))
        self.assertEqual(len(saved), 1)
        saved_raw = saved[0].read_bytes()
        self.assertEqual(json.loads(saved_raw), emitted)
        saved_notice = (
            "notice",
            "Stop diagnostic saved: "
            + str(saved[0])
            + "; SHA256 "
            + hashlib.sha256(saved_raw).hexdigest(),
        )
        self.assertLess(fixture.events.index(saved_notice), fixture.events.index(observation))
        self.assertLess(
            fixture.events.index(("diagnostic_saved", emitted)),
            fixture.events.index(observation),
        )
        self.assertNotIn(CANARY, repr(fixture.events))
        self.assertFalse(fixture.prepared)
        self.assertFalse(fixture.runs)
        self.assertFalse((fixture.primary_root / "search/study/owners").exists())
        advance.assert_not_called()

    def test_unknown_types_text_and_custom_attributes_never_become_diagnostic_fields(self):
        error = PrivateError(CANARY)
        error.code = CANARY
        error.private_filename = CANARY
        result = self.diagnostic(error)
        self.assertEqual(result["chain"], [{"kind": "other", "frames": []}])
        forged = type(CANARY, (ValidationError,), {})(CANARY)
        self.assertEqual(self.diagnostic(forged)["chain"][0]["kind"], "other")

    def test_cycles_shared_nodes_and_long_context_chains_are_bounded(self):
        shared = ValueError(CANARY)
        outer = RuntimeError(CANARY)
        outer.__context__ = shared
        outer.__cause__ = shared
        shared.__context__ = outer
        result = self.diagnostic(outer)
        self.assertEqual(len(result["chain"]), 2)
        for _ in range(100):
            new = RuntimeError(CANARY)
            new.__context__ = outer
            outer = new
        self.assertEqual(len(self.diagnostic(outer)["chain"]), 8)

    def test_private_paths_same_basename_and_exact_public_filename_spoofs_are_excluded(self):
        public = str(Path(improver_study.__file__).absolute())
        for filename in (
            str(Path("/PRIVATE-CANARY") / "candidate.py"),
            str(Path("/PRIVATE-CANARY") / "improver_study.py"),
            public,
        ):
            with self.subTest(filename=filename):
                namespace = {}
                exec(
                    compile(
                        "def forged():\n    raise ValueError('" + CANARY + "')\n", filename, "exec"
                    ),
                    namespace,
                )
                try:
                    namespace["forged"]()
                except ValueError as error:
                    diagnostic = self.diagnostic(error)
                else:
                    self.fail("the synthetic private error did not occur")
                self.assertTrue(all(not node["frames"] for node in diagnostic["chain"]))

    def test_diagnostic_notice_failure_does_not_replace_original_failure(self):
        fixture = unified_fixtures.UnifiedLaunchLifecycleTests("runTest")
        fixture.setUp()
        self.addCleanup(fixture.doCleanups)
        original = PrivateError(CANARY)
        fixture.primary_error = original

        def failed_diagnostic(text):
            if text.startswith("Stop diagnostic: "):
                raise ValueError(CANARY)
            fixture.events.append(("notice", text))

        with fixture.seams(), self.assertRaises(PrivateError) as stopped:
            fixture.launch(notice=failed_diagnostic)
        self.assertIs(stopped.exception, original)
        self.assertIn(("observation", "primary", "launch_stopped"), fixture.events)
        self.assertNotIn(CANARY, repr(fixture.events))

    def test_diagnostic_build_or_save_failure_keeps_the_original_error_and_partial(self):
        for boundary, problem in (
            ("build", ValueError(CANARY)),
            ("build", KeyboardInterrupt(CANARY)),
            ("save", OSError(CANARY)),
            ("save", KeyboardInterrupt(CANARY)),
        ):
            with self.subTest(boundary=boundary, problem=type(problem)):
                fixture = unified_fixtures.UnifiedLaunchLifecycleTests("runTest")
                fixture.setUp()
                self.addCleanup(fixture.doCleanups)
                original = PrivateError(CANARY)
                fixture.primary_error = original
                if boundary == "build":
                    failure = patch.object(launch_common, "_stop_diagnostic", side_effect=problem)
                else:
                    failure = patch.object(native_pipeline, "_write", side_effect=problem)
                with fixture.seams(), failure, self.assertRaises(PrivateError) as stopped:
                    fixture.launch(
                        notice=lambda text, fixture=fixture: fixture.events.append(("notice", text))
                    )
                self.assertIs(stopped.exception, original)
                self.assertIn(("observation", "primary", "launch_stopped"), fixture.events)
                self.assertNotIn(CANARY, repr(fixture.events))


if __name__ == "__main__":
    unittest.main()
