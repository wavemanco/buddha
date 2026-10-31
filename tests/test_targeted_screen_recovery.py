"""One supplied SCREEN recovery/reentry; no trial-wide recovery claim."""

import json
import os
import tempfile
import threading
import unittest
from contextlib import nullcontext
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock, patch

import test_source_screen_outcome as screen_fixtures

from buddha import unified_continuation as continuation
from buddha.executor import ExecutorError
from buddha.gateway import RawHTTPTransport


class TargetedScreenRecoveryTests(unittest.TestCase):
    def test_pre_ready_failure_then_supplied_cleanup_precondition_screen_and_reentry(self):
        fixture = screen_fixtures.SourceScreenOutcomeTests("runTest")
        h, _, directory, authority = fixture.prepare()
        self.addCleanup(fixture.doCleanups)
        generation = directory / "tasks/0/generation"
        owner = generation / "owners/0/manifest.json"
        manifest = owner.read_bytes()
        owner_id = json.loads(manifest)["run_id"]

        def fail_before_ready(*args, **kwargs):
            raise ExecutorError("cleanup", cleanup_status="unknown", container_id=None)

        with patch.object(h, "execute", side_effect=fail_before_ready) as failed_worker:
            stopped = h.run_screen(directory)
        failed_worker.assert_called_once()
        self.assertEqual(stopped["status"], "incomplete")
        self.assertEqual(stopped["stage"], "generation")
        self.assertEqual(stopped["task_index"], 0)
        self.assertFalse((directory / "report.json").exists())
        failed = generation / "attempts/0-0"
        session = json.loads((failed / "session/report.json").read_bytes())
        outcome = json.loads((failed / "report.json").read_bytes())
        self.assertEqual(session["execution"]["cleanup_status"], "unknown")
        self.assertIsNone(session["execution"]["container_id"])
        self.assertEqual(session["calls"], {"requested": 0, "completed": 0, "stopped": 0})
        self.assertFalse(outcome["terminal"]["ready_seen"])
        self.assertEqual(outcome["terminal"]["operation_count"], 0)
        self.assertEqual(h.engine.physical_sends, 0)
        self.assertEqual(authority.summary()["operation_count"], 0)
        self.assertEqual(authority.summary()["reserved_microusd"], 0)
        self.assertTrue(
            next(row for row in authority.summary()["runs"] if row["run_id"] == owner_id)["active"]
        )
        self.assertFalse((generation / "completed/0.json").exists())
        preserved = {
            path: path.read_bytes()
            for path in (
                *failed.rglob("*"),
                *generation.glob("observations/*.json"),
                *directory.glob("observations/*.json"),
            )
            if path.is_file()
        }
        with self.subTest(checkpoint="pre_ready_failure_retained"):
            self.assertTrue(preserved)

        # Cleanup is now a supplied precondition. This checks the existing retry,
        # not an operator's reconciliation or a production cleanup retry latch.
        with patch(
            "buddha.improver_study._advance_action", side_effect=AssertionError("study dispatch")
        ):
            complete = h.run_screen(directory)
        self.assertEqual(complete["status"], "complete")
        self.assertEqual(complete["disposition"], "screened")
        self.assertEqual([row["task_id"] for row in complete["tasks"]], ["1", 1])
        self.assertEqual(
            [(row["distinct"], row["utility"]) for row in complete["tasks"]], [(2, 7), (2, 7)]
        )
        self.assertEqual(
            complete["unattempted"], {"generation_task_ids": [], "native_task_ids": []}
        )
        self.assertTrue(complete["admission"]["eligible"])
        self.assertEqual(owner.read_bytes(), manifest)
        for path, raw in preserved.items():
            self.assertEqual(path.read_bytes(), raw)
        seal = json.loads((generation / "completed/0.json").read_bytes())
        self.assertEqual(seal["attempt"], "attempts/0-1")
        self.assertFalse(
            next(row for row in authority.summary()["runs"] if row["run_id"] == owner_id)["active"]
        )
        self.assertGreater(h.engine.physical_sends, 0)
        self.assertEqual(authority.summary()["operation_count"], h.engine.physical_sends)
        self.assertEqual(authority.summary()["reserved_microusd"], 0)
        self.assertFalse((directory.parent / "witness").exists())
        self.assertFalse((directory.parent / "decision.json").exists())
        with self.subTest(checkpoint="same_owner_next_attempt_full_screen"):
            self.assertEqual(len(complete["tasks"]), 2)

        before = h.files(h.root), authority.summary(), h.engine.physical_sends
        with (
            patch.dict(os.environ, {}, clear=True),
            patch("buddha.executor.run_container", side_effect=AssertionError("reentry worker")),
            patch("http.client.HTTPSConnection", side_effect=AssertionError("reentry HTTPS")),
            patch(
                "buddha.improver_study._advance_action", side_effect=AssertionError("next action")
            ),
        ):
            replay = h.run_api(directory, transport=RawHTTPTransport(allow_paid=False))
        self.assertEqual(replay, complete)
        self.assertEqual((h.files(h.root), authority.summary(), h.engine.physical_sends), before)
        with self.subTest(checkpoint="keyless_reentry_no_new_work"):
            self.assertEqual(owner.read_bytes(), manifest)

    def test_supplied_checked_dispatch_seam_stops_after_exactly_one_screen_action(self):
        """Unit seam only: scope/leases are supplied, not a checked trial fixture."""
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary).resolve()
            study = root / "study"
            checked = continuation.CheckedTrialContinuation(
                path=root / "descriptor.json",
                sha256="a" * 64,
                study=study,
                witness=study / "witness",
                _parent=study / "screen",
                runtime_sha256="b" * 64,
                _before=(),
                _after=(),
                _screen_sha256="c" * 64,
                _policy=b"{}",
                _summary=b"{}",
                _pid=os.getpid(),
                _thread=threading.get_ident(),
                _old_owners=frozenset(),
                _cells=(),
                _screens=frozenset(),
                _authorization=root / "authority.sqlite3",
                _profiles=("d" * 64, "e" * 64),
                _trial=root,
                _launch=(root / "launch.json", "f" * 64),
                _roles=(),
            )
            state = {"action": {"kind": "screen"}}
            prepared = SimpleNamespace(
                checked=checked,
                state=state,
                search_grant=checked._authorization,
                study_result=None,
                action={"kind": "screen"},
                after_locks=Mock(),
            )
            authority = SimpleNamespace(path=checked._authorization, _terms=lambda: {})

            def advance(*args):
                self.assertEqual(state["action"]["kind"], "screen")
                state["action"]["kind"] = "witness"
                return None

            with (
                patch.object(
                    continuation.CheckedTrialContinuation, "_scope", return_value=nullcontext()
                ),
                patch.object(continuation, "Authorization", return_value=authority),
                patch.object(continuation.trial_fence, "work", return_value=nullcontext()),
                patch.object(continuation.pipeline, "_exclusive", return_value=nullcontext()),
                patch.object(continuation, "NativeEvidence", return_value=object()),
                patch.object(continuation.improver_study, "_check_current") as current,
                patch.object(
                    continuation.improver_study, "_advance_action", side_effect=advance
                ) as dispatch,
            ):
                result = continuation._advance_prepared(
                    prepared, transport=RawHTTPTransport(allow_paid=False)
                )
            self.assertEqual(result, {"action": "screen", "role": None, "result": None})
            prepared.after_locks.assert_called_once_with()
            current.assert_called_once_with(state)
            dispatch.assert_called_once()
            self.assertEqual(state["action"]["kind"], "witness")


if __name__ == "__main__":
    unittest.main()
