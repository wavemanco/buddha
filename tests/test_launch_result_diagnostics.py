"""Returned controller failures retain safe metadata before slow partial checks.

All execution, key and provider seams are synthetic; no real worker is started.
"""

import copy
import hashlib
import json
import unittest
from datetime import UTC, datetime
from unittest.mock import patch

import test_unified_launch as unified_fixtures

from buddha import improver_assessment, improver_launch, improver_study, launch_common
from buddha import native_pipeline as pipeline
from buddha.releases import _json

CANARY = "PRIVATE-result-credential-path-answer-and-message"


def failure():
    return {
        "format": "buddha.improver-study-observation.v1",
        "status": "incomplete",
        "reason": "protocol",
        "position": {"start": 0, "repetition": 0, "arm": 0, "slot": 1, "stage": "screen"},
        "coverage": {"expected": 16},
        "observation": "observations/1.json",
        "child": {
            "format": "buddha.source-screen-observation.v1",
            "status": "incomplete",
            "reason": "protocol",
            "stage": "generation",
            "task_index": 0,
            "child": {
                "format": "buddha.candidate-generation-observation.v2",
                "status": "incomplete",
                "reason": "protocol",
                "attempt": CANARY,
                "owner": CANARY,
                "generation": {
                    "status": "failed",
                    "reason": "execution",
                    "execution": {
                        "reason": "cleanup",
                        "cleanup_status": "unknown",
                        "container_id": CANARY,
                    },
                    "calls": {"requested": 0, "completed": 0, "stopped": 0},
                    "answers": [CANARY],
                },
                "outcome": {
                    "terminal": {
                        "ready_seen": False,
                        "broken": False,
                        "done_status": None,
                        "sequence": 0,
                        "delivered": 0,
                        "operation_count": 0,
                        "recorded_cost_microusd": 0,
                        "stop_reason": None,
                        "done_sha256": CANARY,
                    }
                },
            },
        },
    }


class Trap(dict):
    def get(self, *args):
        raise AssertionError("custom mappings must not be inspected")

    def __str__(self):
        raise AssertionError("private values must not be converted to text")


class PrivateString(str):
    def __hash__(self):
        raise AssertionError("private string subclasses must not be hashed")

    def __eq__(self, other):
        raise AssertionError("private string subclasses must not be compared")

    def __len__(self):
        raise AssertionError("private string subclasses must not be sized")

    def __str__(self):
        raise AssertionError("private string subclasses must not become text")


class ResultDiagnosticProjectionTests(unittest.TestCase):
    def test_cleanup_and_terminal_metadata_survive_without_private_fields(self):
        original = failure()
        before = copy.deepcopy(original)
        result = launch_common._result_diagnostic(original, phase="search")
        self.assertEqual(result["format"], "buddha.launch-result-diagnostic.v1")
        self.assertEqual(result["scope"], "controller_reported_inline_fields_only")
        node = result["chain"][-1]
        self.assertEqual(node["generation"]["reason"], "execution")
        self.assertEqual(node["generation"]["executor_reason"], "cleanup")
        self.assertEqual(node["generation"]["cleanup_status"], "unknown")
        self.assertIs(node["terminal"]["ready_seen"], False)
        self.assertIsNone(node["terminal"]["done_status"])
        self.assertEqual(
            node["generation"]["calls"], {"requested": 0, "completed": 0, "stopped": 0}
        )
        self.assertNotIn(CANARY.encode(), _json(result))
        self.assertEqual(json.loads(_json(result)), result)
        node["generation"]["calls"]["requested"] = 9
        result["chain"].clear()
        self.assertEqual(original, before)

    def test_cycles_depth_unknown_formats_and_custom_mappings_are_bounded(self):
        root = failure()
        root["child"] = root
        self.assertEqual(len(launch_common._result_diagnostic(root, phase="search")["chain"]), 1)
        root = current = {}
        for _ in range(30):
            current["child"] = {}
            current = current["child"]
        result = launch_common._result_diagnostic(root, phase="search")
        self.assertEqual(len(result["chain"]), 8)
        self.assertLess(len(_json(result)), 8_000)
        for value in ([], None, Trap()):
            self.assertEqual(launch_common._result_diagnostic(value, phase="search")["chain"], [])
        result = launch_common._result_diagnostic(
            {"format": Trap(), "reason": CANARY, "status": CANARY, "stage": Trap()}, phase=CANARY
        )
        self.assertNotIn(CANARY.encode(), _json(result))
        self.assertEqual(result["chain"][0]["kind"], "other")

    def test_giant_strings_and_hostile_subclasses_never_escape_projection(self):
        huge = CANARY * 100_000
        for text in (huge, PrivateString(CANARY)):
            with self.subTest(kind=type(text).__name__):
                result = launch_common._result_diagnostic(
                    {"format": text, "status": text, "reason": text, "stage": text},
                    phase=text,
                )
                self.assertEqual(result["chain"][0]["kind"], "other")
                self.assertLess(len(_json(result)), 1_000)
                self.assertNotIn(CANARY.encode(), _json(result))
        result = launch_common._result_diagnostic(
            {"generation": Trap(), "outcome": Trap(), "position": Trap(), "child": Trap()},
            phase="search",
        )
        self.assertEqual(len(result["chain"]), 1)
        self.assertNotIn("generation", result["chain"][0])
        self.assertNotIn("terminal", result["chain"][0])

    def test_counter_and_boolean_types_are_strict(self):
        result = launch_common._result_diagnostic(
            {
                "generation": {"calls": {"requested": True, "completed": -1, "stopped": 0}},
                "position": {"start": 1.0, "arm": 2**63, "slot": 0},
                "outcome": {
                    "terminal": {
                        "ready_seen": 1,
                        "broken": "false",
                        "sequence": False,
                        "delivered": 2**63,
                    }
                },
            },
            phase="search",
        )["chain"][0]
        self.assertEqual(result["generation"]["calls"], {"stopped": 0})
        self.assertEqual(result["position"], {"slot": 0})
        self.assertNotIn("ready_seen", result["terminal"])
        self.assertNotIn("broken", result["terminal"])
        self.assertNotIn("sequence", result["terminal"])
        self.assertNotIn("delivered", result["terminal"])


class ReturnedFailureLifecycleTests(unittest.TestCase):
    def run_case(self, phase, *, mode="publish"):
        fixture = unified_fixtures.UnifiedLaunchLifecycleTests("runTest")
        fixture.setUp()
        self.addCleanup(fixture.doCleanups)
        canonical = (
            failure()
            if phase == "search"
            else {
                "status": "incomplete",
                "reason": "protocol",
                "position": {"stage": "generation", "arm_index": 0, "task_index": 0},
                "coverage": {"expected": 312},
                "child_observation": {"path": CANARY, "sha256": CANARY},
            }
        )
        before = copy.deepcopy(canonical)
        if phase == "final":
            report = fixture.primary_root / "search/study/report.json"
            report.parent.mkdir(parents=True)
            report.write_bytes(b'{"synthetic":"completed development seam"}')
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
            "phase": phase,
            "stop_code": None,
            "review": review,
            "timeout_seconds": 30,
            "profiles": fixture.check(fixture.path, fixture.digest)["profiles"],
            "proposal": {},
            "bindings": {},
            "state_sha256": "0" * 64,
        }
        real_inner = improver_launch.launch
        real_write = pipeline._write

        def saved_partial(*args):
            fixture.events.append(("slim", phase))
            self.assertEqual(canonical, before)
            paths = list((fixture.workspace / "observations").glob("*.diagnostic.json"))
            if mode == "publish":
                self.assertEqual(len(paths), 1, "diagnostic must precede the slow partial check")
            return {
                "status": "incomplete",
                "reason": "protocol",
                "position": before["position"],
                "coverage": before["coverage"],
                "observation": "observations/1.json",
            }

        def inner(*args, **options):
            if mode in {"mutate", "observer_error", "observer_interrupt"}:

                def observer(details):
                    details["chain"].clear()
                    details["phase"] = CANARY
                    if mode == "observer_error":
                        raise RuntimeError(CANARY)
                    if mode == "observer_interrupt":
                        raise KeyboardInterrupt(CANARY)

                options["on_incomplete"] = observer
            return real_inner(*args, **options)

        def notice(text):
            fixture.events.append(("notice", text))
            if mode == "notice_interrupt" and text.startswith("Stop diagnostic:"):
                raise KeyboardInterrupt(CANARY)

        def write(path, raw):
            if mode == "save_interrupt" and path.name.endswith(".diagnostic.json"):
                raise KeyboardInterrupt(CANARY)
            return real_write(path, raw)

        from contextlib import ExitStack

        with ExitStack() as stack:
            stack.enter_context(fixture.seams())
            stack.enter_context(patch.object(improver_launch, "launch", side_effect=inner))
            stack.enter_context(
                patch.object(
                    improver_launch,
                    "check_launch",
                    side_effect=lambda *a, **k: copy.deepcopy(checked),
                )
            )
            stack.enter_context(
                patch.object(improver_study, "run_improver_study", return_value=canonical)
            )
            stack.enter_context(patch.object(improver_assessment, "freeze_improver_descendants"))
            stack.enter_context(
                patch.object(improver_assessment, "run_improver_assessment", return_value=canonical)
            )
            stack.enter_context(
                patch.object(improver_launch, "_saved_partial", side_effect=saved_partial)
            )
            stack.enter_context(patch.object(pipeline, "_write", side_effect=write))
            if mode == "build_interrupt":
                stack.enter_context(
                    patch.object(
                        launch_common, "_result_diagnostic", side_effect=KeyboardInterrupt(CANARY)
                    )
                )
            result = fixture.launch(notice=notice)
        self.assertEqual((result["status"], result["reason"]), ("incomplete", "protocol"))
        self.assertEqual(canonical, before)
        self.assertTrue(result["observation_saved"])
        self.assertFalse(fixture.prepared)
        self.assertFalse(fixture.runs)
        self.assertEqual(fixture.shared.summary()["operation_count"], 0)
        if mode == "publish":
            (path,) = (fixture.workspace / "observations").glob("*.diagnostic.json")
            raw = path.read_bytes()
            details = json.loads(raw)
            self.assertEqual(details["phase"], phase)
            self.assertNotIn(CANARY.encode(), raw)
            self.assertNotIn(CANARY, repr(fixture.events))
            emitted = ("notice", "Stop diagnostic: " + raw.decode())
            saved = (
                "notice",
                "Stop diagnostic saved: "
                + str(path)
                + "; SHA256 "
                + hashlib.sha256(raw).hexdigest(),
            )
            self.assertLess(fixture.events.index(emitted), fixture.events.index(("slim", phase)))
            self.assertLess(fixture.events.index(saved), fixture.events.index(("slim", phase)))
            self.assertLess(
                fixture.events.index(("slim", phase)),
                fixture.events.index(("observation", "primary", "protocol")),
            )
            if phase == "search":
                self.assertEqual(details["chain"][-1]["generation"]["executor_reason"], "cleanup")
            else:
                self.assertEqual(len(details["chain"]), 1)
                self.assertNotIn("generation", details["chain"][0])

    def test_search_return_is_published_before_slimming(self):
        self.run_case("search")

    def test_final_return_is_header_only_without_dereferencing_child_files(self):
        self.run_case("final")

    def test_mutating_or_failing_observers_keep_the_original_result_in_both_phases(self):
        for phase in ("search", "final"):
            for mode in ("mutate", "observer_error", "observer_interrupt"):
                with self.subTest(phase=phase, mode=mode):
                    self.run_case(phase, mode=mode)

    def test_build_notice_and_save_interruptions_keep_the_original_partial(self):
        for phase in ("search", "final"):
            for mode in ("build_interrupt", "notice_interrupt", "save_interrupt"):
                with self.subTest(phase=phase, mode=mode):
                    self.run_case(phase, mode=mode)


if __name__ == "__main__":
    unittest.main()
