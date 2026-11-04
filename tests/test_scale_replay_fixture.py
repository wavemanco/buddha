"""Small scale-worker/default proofs, not the 193-owner producer or timing gate."""

import json
import unittest
from pathlib import Path
from unittest.mock import patch

import test_improver_study as finite_fixtures
from scale_replay_fixture import DATASET_BYTES, TASK_IDS, TASK_SOURCE_BYTES, prepare


class ScaleReplayFixtureTests(unittest.TestCase):
    def test_legacy_default_keeps_one_task_two_answers_and_one_callback(self):
        f = finite_fixtures.FiniteImproverStudyTests("runTest")
        self.addCleanup(f.doCleanups)
        f.fixture_before_new_api()
        self.assertEqual([task.id for task in f.base.tasks.tasks], [finite_fixtures.TASK_ID])
        self.assertEqual([task.count for task in f.base.tasks.tasks], [2])
        self.assertEqual(f.answer_values(), [finite_fixtures.LITERAL, ""])
        self.assertEqual(f.generation_callbacks, 1)
        self.assertEqual(f.engine.native_callback_counts, (1, 1))
        self.assertFalse(f.unique_children)
        self.assertEqual(f.bootstrap[2]["operation_count"], 4)
        screen = json.loads((f.bootstrap_directories[0] / "report.json").read_bytes())
        self.assertEqual([(row["distinct"], row["utility"]) for row in screen["tasks"]], [(2, 7)])

    def test_three_tasks_ten_answers_and_prospective_worker_caps_bootstrap_honestly(self):
        try:
            f, record = prepare(self, inventory_count=64)
        except Exception as error:
            from buddha.launch_common import _stop_diagnostic

            print(json.dumps(_stop_diagnostic(error)), flush=True)
            raise
        self.assertEqual(len(f.h.source.tasks), 1000)
        self.assertEqual(len(f.h.source.to_bytes()), TASK_SOURCE_BYTES)
        dataset = f.engine.fixture.roots["official"] / "data/tasks.jsonl"
        self.assertEqual(dataset.stat().st_size, DATASET_BYTES)
        self.assertEqual([task.id for task in f.base.tasks.tasks], list(TASK_IDS))
        self.assertEqual([task.count for task in f.base.tasks.tasks], [10, 10, 10])
        self.assertEqual(f.generation_callbacks, 4)
        self.assertEqual(f.engine.native_callback_counts, (1, 10))
        self.assertTrue(f.unique_children)
        generation, native = (f.base.to_record()[key] for key in ("generation", "native"))
        self.assertEqual((generation["max_callbacks"], generation["max_calls"]), (4, 4))
        self.assertEqual(native["max_calls"], 10)
        self.assertEqual(len(native["environment"]["inventory"]), 64)
        self.assertEqual(record["limits"]["study"]["max_calls"], 1724)
        self.assertEqual(
            (len(record["starts"]), record["repetitions"], record["descendant_opportunities"]),
            (2, 2, 2),
        )
        # Three genuine screens each use4generation+1partition+10utility calls;
        # the bootstrap proposal adds1. These are real supplied Gateway rows.
        self.assertEqual(f.bootstrap[2]["operation_count"], 3 * (4 + 1 + 10) + 1)
        self.assertEqual(len(f.bootstrap[2]["runs"]), 3 * 4 + 1)
        self.assertEqual(f.bootstrap[2]["reserved_microusd"], 0)
        screen_root = f.bootstrap_directories[0]
        screen = json.loads((screen_root / "report.json").read_bytes())
        self.assertEqual([row["task_id"] for row in screen["tasks"]], list(TASK_IDS))
        self.assertEqual(
            [(row["distinct"], row["utility"]) for row in screen["tasks"]], [(10, 7)] * 3
        )
        for index in range(3):
            stage = screen_root / "tasks" / str(index) / "generation"
            seal = json.loads((stage / "completed/0.json").read_bytes())
            answers = json.loads(
                (stage / Path(seal["attempt"]) / "session/answers.json").read_bytes()
            )
            self.assertEqual(answers["outputs"][0]["answers"], f.answer_values())
        self.assertFalse((f.root / "scale-replay/context.json").exists())

    def test_witness_reads_three_full_task_records_and_generates_only_first_task(self):
        # This is a small branch check, not the 1000-row/native-metadata scale gate.
        f, record = prepare(
            self,
            inventory_count=1,
            sized_source=False,
            generation_callbacks=1,
            native_callbacks=(1, 1),
        )
        self.assertEqual(f.bootstrap[2]["operation_count"], 10)
        self.assertEqual(len(f.h.source.tasks), 6)
        directory, _, authority = f.prepare_study("scaled-first-witness", record)
        witness_report = directory / "common/0/0/witness/report.json"
        ordinary = f.api._advance_action

        class ReachedFirstWitness(Exception):
            pass

        def advance(reader, state, funded, transport):
            if witness_report.is_file():
                self.assertEqual(json.loads(witness_report.read_bytes())["status"], "passed")
                self.assertEqual(len(state["owner_paths"]), 14)
                self.assertEqual(state["authorization"]["operation_count"], 11)
                self.assertEqual(state["authorization"]["reserved_microusd"], 0)
                reader.finish()
                raise ReachedFirstWitness
            return ordinary(reader, state, funded, transport)

        with (
            f.supplied(),
            patch.object(f.api, "_advance_action", side_effect=advance),
            self.assertRaises(ReachedFirstWitness),
        ):
            f.api.run_improver_study(directory, transport=f.transport())
        witness = f.improvements[-1]
        self.assertTrue(witness["witness"])
        self.assertEqual([row["task"]["id"] for row in witness["feedback"]], list(TASK_IDS))
        self.assertEqual(f.generated[-1]["task"]["id"], TASK_IDS[0])
        self.assertEqual(authority.summary()["operation_count"], 11)


if __name__ == "__main__":
    unittest.main()
