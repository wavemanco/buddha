"""Prospective failure-aware screens retain old screen semantics explicitly."""

import copy
import json
import unittest
from unittest.mock import patch

import test_source_screen as fixtures

from buddha.answers import Answers
from buddha.releases import _json


class SourceScreenOutcomeTests(unittest.TestCase):
    def fixture(self):
        self.h = fixtures.SourceScreenTests("runTest")
        self.h.setUp()
        self.addCleanup(self.h.doCleanups)
        engine = self.h.engine

        def answers():
            attempt = engine.attempt()
            context = json.loads((engine.directory / "context.json").read_bytes())
            if context["format"] == "buddha.candidate-generation-context.v2":
                attempt = attempt / "session"
            return Answers.from_bytes((attempt / "answers.json").read_bytes())

        engine.answers = answers
        return self.h

    def prepare(self):
        h = self.fixture()
        record = copy.deepcopy(h.record)
        record["format"] = "buddha.source-screen.v2"
        screen = h.screen(record)
        directory, authority = h.prepare(screen)
        return h, screen, directory, authority

    @staticmethod
    def failed_worker(h, task_id, original):
        def execute(spec, *, initial, handle, **kwargs):
            if spec.role == "agent" and initial["task"]["id"] == task_id:
                h.engine.workers += 1
                h.generation_events.append((initial["agent_sha256"], initial["task"]))
                handle({"type": "done", "status": "failed", "reason": "agent_error", "answers": []})
                return h.engine.execution(spec)
            return original(spec, initial=initial, handle=handle, **kwargs)

        return execute

    def test_explicit_failure_aware_screen_keeps_a_separate_comparison(self):
        h = self.fixture()
        old = h.screen()
        record = copy.deepcopy(h.record)
        record["format"] = "buddha.source-screen.v2"
        prospective = h.screen(record)
        self.assertEqual(prospective.candidate_id, old.candidate_id)
        self.assertNotEqual(prospective.comparison_key(), old.comparison_key())
        self.assertEqual(prospective.tasks.to_bytes(), old.tasks.to_bytes())
        changed = prospective.to_record()
        changed["format"] = "buddha.source-screen.v3"
        with self.assertRaises(h.Error):
            h.Screen.from_bytes(_json(changed))
        self.assertEqual(h.engine.physical_sends, 0)

    def test_clean_first_task_failure_has_no_numeric_score_or_native_assessment(self):
        h, screen, directory, authority = self.prepare()
        with patch.object(h, "execute", side_effect=self.failed_worker(h, "1", h.execute)):
            result = h.run_screen(directory)
        self.assertEqual(result["status"], "complete")
        self.assertEqual(result["disposition"], "candidate_execution_failed")
        self.assertEqual(result["tasks"], [])
        self.assertEqual(result["failure"]["task_id"], "1")
        self.assertFalse(result["failure"]["terminal"]["ready_seen"])
        self.assertEqual(
            result["admission"],
            {
                "eligible": False,
                "reasons": ["candidate_execution_failed"],
                "mean_distinct": None,
                "mean_utility": None,
            },
        )
        self.assertEqual(
            result["unattempted"], {"generation_task_ids": [1], "native_task_ids": ["1", 1]}
        )
        self.assertEqual(
            (len(h.generation_events), len(h.native_events), h.engine.physical_sends), (1, 0, 0)
        )
        self.assertEqual(h.inspect(directory, authority), result)
        selected = h.select_api(
            [h.reference(directory, authority)], method="latest", max_active=2, seed=0, iteration=0
        )
        self.assertIsNone(selected["selected_id"])
        self.assertEqual(authority.summary()["reserved_microusd"], 0)
        self.assertFalse(any(run["active"] for run in authority.summary()["runs"]))
        self.assertEqual(screen.tasks.tasks[1].id, 1)

    def test_complete_v2_screen_preserves_native_metrics_and_eligibility(self):
        h, _, directory, authority = self.prepare()
        result = h.run_screen(directory)
        self.assertEqual(result["disposition"], "screened")
        self.assertIsNone(result["failure"])
        self.assertTrue(result["admission"]["eligible"])
        self.assertEqual([row["task_id"] for row in result["tasks"]], ["1", 1])
        self.assertEqual(result["unattempted"], {"generation_task_ids": [], "native_task_ids": []})
        self.assertEqual(h.inspect(directory, authority), result)

    def test_later_failure_retains_completed_task_measurements_without_partial_means(self):
        h, _, directory, authority = self.prepare()
        with patch.object(h, "execute", side_effect=self.failed_worker(h, 1, h.execute)):
            result = h.run_screen(directory)
        self.assertEqual([row["task_id"] for row in result["tasks"]], ["1"])
        self.assertEqual(result["tasks"][0]["utility"], 7)
        self.assertIsNone(result["admission"]["mean_utility"])
        self.assertEqual(result["failure"]["task_id"], 1)
        self.assertEqual(result["unattempted"], {"generation_task_ids": [], "native_task_ids": [1]})
        self.assertEqual(h.inspect(directory, authority), result)


if __name__ == "__main__":
    unittest.main()
