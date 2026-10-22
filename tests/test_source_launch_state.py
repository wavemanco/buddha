"""Passive original-owner readiness, without constructing a spending interface."""

import copy
import json
import os
import unittest
from unittest.mock import patch

import test_source_search

from buddha import native_pipeline
from buddha.gateway import execution_identity
from buddha.releases import _json
from buddha.source_launch_state import inspect_prepared_search
from buddha.source_search import SourceSearchError, _sources


class SourceLaunchStateTests(unittest.TestCase):
    def fixture(self):
        h = test_source_search.SourceSearchTests("runTest")
        h.fixture(iterations=1)
        self.addCleanup(h.doCleanups)
        return h

    def inspect(self, h, **changes):
        values = {
            "seed_screen": h.seed,
            "proposal_template": h.template,
            "spec": h.spec,
            "review": h.engine.fixture.review,
            "expected_runtime_sha256": h.engine.candidate.expected_runtime,
            "input_bindings": {},
        }
        before = h.h.files(h.directory), h.authority.path.read_bytes(), h.engine.physical_sends
        with (
            h.h.readonly(),
            patch.dict(os.environ, {}, clear=True),
            patch("socket.socket", side_effect=AssertionError("passive socket")),
        ):
            try:
                return inspect_prepared_search(h.directory, h.authority.path, **(values | changes))
            finally:
                self.assertEqual(
                    (
                        h.h.files(h.directory),
                        h.authority.path.read_bytes(),
                        h.engine.physical_sends,
                    ),
                    before,
                )

    def test_original_fresh_owner_is_passive_and_stable_and_all_locks_are_busy(self):
        h = self.fixture()
        h.prepare()
        first = self.inspect(h)
        self.assertEqual(first["state"], "prepared")
        self.assertEqual(first["next_role"], "generation")
        self.assertEqual(first["next_owner"], str(h.directory / "seed/tasks/0/generation/owners/0"))
        self.assertFalse(first["busy"])
        self.assertFalse(first["inactive_pending"])
        self.assertEqual(self.inspect(h), first)
        lock = h.directory / "seed/tasks/0/generation/running.lock"
        lock.write_bytes(b"1234567")
        busy = self.inspect(h)
        self.assertTrue(busy["busy"])
        self.assertNotEqual(busy["state_sha256"], first["state_sha256"])
        self.assertEqual(lock.read_bytes(), b"1234567")
        lock.unlink()
        after = self.inspect(h)
        self.assertFalse(after["busy"])
        self.assertNotEqual(after["state_sha256"], first["state_sha256"])
        self.assertEqual(self.inspect(h), after)

    def test_all_approved_initial_fields_and_external_controls_stay_original(self):
        h = self.fixture()
        control = h.root / "approved-launch.json"
        control.write_bytes(b"{}")
        bindings = {control: test_source_search.sha(b"{}")}
        h.prepare(input_bindings=bindings)
        self.inspect(h, input_bindings=bindings)
        review = copy.deepcopy(h.engine.fixture.review)
        review["account_scope"] += "; changed"
        template = copy.deepcopy(h.template)
        template["budget_microusd"] += 1
        for changes in (
            {"input_bindings": {}},
            {"input_bindings": {control: "0" * 64}},
            {"review": review},
            {"proposal_template": template},
            {"spec": h.Spec.from_bytes(_json(h.specification(iterations=2)))},
            {"expected_runtime_sha256": "0" * 64},
        ):
            with self.subTest(changes=list(changes)), self.assertRaises(SourceSearchError):
                self.inspect(h, **({"input_bindings": bindings} | changes))
        helper = next(path for path in _sources() if path.name == "source_search.py")
        with self.assertRaises(SourceSearchError):
            self.inspect(h, input_bindings=bindings | {helper: "0" * 64})

    def test_inactive_unfinished_original_owner_is_reported_without_reactivation(self):
        h = self.fixture()
        h.prepare()
        owner = h.authority.summary()["runs"][0]
        h.authority.deactivate(owner["run_id"], "test-only stop; no completion seal")
        result = self.inspect(h)
        self.assertTrue(result["inactive_pending"])
        self.assertEqual(result["next_owner"], owner["directory"])
        self.assertFalse(h.authority.summary()["runs"][0]["active"])

    def test_orphan_owner_and_future_task_are_rejected_before_execution(self):
        h = self.fixture()
        h.prepare()
        orphan = h.directory / "seed/tasks/0/generation/owners/1"
        orphan.mkdir()
        with self.assertRaises(SourceSearchError):
            self.inspect(h)
        orphan.rmdir()
        future = h.directory / "seed/tasks/9"
        future.mkdir()
        with self.assertRaises(SourceSearchError):
            self.inspect(h)

    def test_pending_native_readiness_retains_its_original_owner(self):
        h = self.fixture()
        h.prepare()
        h.engine.native_fail_once = True
        first = h.run_search()
        self.assertEqual(first["status"], "incomplete")
        before = h.authority.summary()
        native = self.inspect(h)
        self.assertEqual(native["next_role"], "native")
        self.assertFalse(native["inactive_pending"])
        self.assertEqual(h.authority.summary(), before)
        self.assertIn(native["next_owner"], {row["directory"] for row in before["runs"]})

    def test_pending_native_command_cannot_change_the_prescribed_flow(self):
        h = self.fixture()
        h.prepare()
        original = native_pipeline._native_descriptor

        def wrong_command(*args, **kwargs):
            path, inputs = original(*args, **kwargs)
            record = json.loads(path.read_bytes())
            command = record["worker"]["command"]
            command["module"] = "unapproved.module"
            command.pop("sha256")
            command["sha256"] = test_source_search.sha(_json(command))
            path.write_bytes(_json(record))
            return path, inputs

        with (
            patch("buddha.native_pipeline._native_descriptor", side_effect=wrong_command),
            patch("buddha.native_evaluation.run_evaluation", side_effect=ValueError("test stop")),
            self.assertRaises(SourceSearchError),
        ):
            h.run_search()
        native = h.directory / "seed/tasks/0/evaluation/owners/1"
        # This is the actual original, internally consistent owner prepared with
        # the wrong command. No manifest, local DB or grant was rewritten.
        execution_identity(native)
        self.assertEqual(h.engine.physical_sends, 2)
        with self.assertRaises(SourceSearchError):
            self.inspect(h)


if __name__ == "__main__":
    unittest.main()
