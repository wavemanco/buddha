"""Small scale-worker/default proofs, not the 193-owner producer or timing gate."""

import hashlib
import json
import unittest
from pathlib import Path
from unittest.mock import patch

import test_improver_study as finite_fixtures
from scale_replay_fixture import (
    ANSWER_BYTES,
    DATASET_BYTES,
    TASK_IDS,
    TASK_SOURCE_BYTES,
    prepare,
    prepare_forward,
)


class ScaleReplayFixtureTests(unittest.TestCase):
    def test_forward_preparation_selects_v5_and_starts_no_bootstrap_or_study(self):
        f, record = prepare_forward(self, inventory_count=1, sized_source=False)
        self.assertEqual(record["format"], "buddha.improver-study.v5")
        self.assertFalse(hasattr(f, "bootstrap"))
        self.assertEqual(f.h.authorities, [])
        self.assertEqual((f.engine.workers, f.engine.physical_sends), (0, 0))
        self.assertEqual(f.events, [])
        self.assertEqual(f.outcomes, {})
        self.assertEqual(len(f.h.source.tasks), 6)
        self.assertEqual([task.id for task in f.base.tasks.tasks], list(TASK_IDS))
        self.assertEqual([task.count for task in f.base.tasks.tasks], [10, 10, 10])
        values = f.answer_values()
        self.assertEqual([len(text.encode("utf-8")) for text in values], [8192] * 10)
        self.assertEqual(ANSWER_BYTES, 8192)
        self.assertEqual(f.literal, values[0])
        self.assertTrue(values[0].startswith(finite_fixtures.LITERAL))
        for index in range(1, 10):
            self.assertTrue(values[index].startswith("Supplied answer " + str(index)))
        self.assertEqual(
            [hashlib.sha256(text.encode("utf-8")).hexdigest() for text in values],
            [
                "fd799460ec213ee4fcb8b2245d1ab3e9beff614d82759d5ca49eb1fc387e3cf6",
                "bf408a0d13c6434b93120723e3f45f17c5a0e1ffa0bfee62a99df34ac67b13db",
                "24ec136dcb99b4db1ad19e11acc2b04053db59e363093862aab067e982e38b93",
                "ef2a9f0d391d0e81959777583545faf84f30f08dbd71363fffe93cb25222ccf0",
                "5fbf490b82598331a6f2281058066986f0cb9cc2422025bce74066740caf1d3b",
                "6aa5c5e3576fb3868be3464e063c7e2279db99dca63bb98870b1c7d27309d382",
                "bc1bb3c99f6819ca63bf1310ce4f986baede8ba80fe812eb7ee42912779dde1c",
                "6d5b810d8d57539a7c46776663c3aa8f463b4c34f1e90308ed83142ec2a05550",
                "d9b5186631f0acec84033269046891855b6f15ce863a90654c9565f843f3a4e4",
                "76b3387625bbb633b5bfbfdcac30257474e982ab0cd027dac06d6d1dad5319e0",
            ],
        )
        frozen = tuple(values)
        values[0] = "caller list mutation"
        self.assertEqual(f.answer_values(), list(frozen))
        self.assertEqual(f.literal, frozen[0])
        self.assertTrue(
            all(program["answers"] == list(frozen) for program in f.h.programs.values())
        )
        oversized = list(frozen)
        oversized[0] += "!"
        with (
            patch("scale_replay_fixture.prepare", return_value=(f, record)),
            patch.object(f, "answer_values", return_value=oversized),
            self.assertRaisesRegex(AssertionError, "payload envelope"),
        ):
            prepare_forward(self)
        self.assertEqual(len(f.base.to_record()["native"]["environment"]["inventory"]), 1)
        self.assertEqual((f.generation_callbacks, f.engine.native_callback_counts), (12, (1, 10)))
        self.assertEqual(
            (
                len(record["starts"]),
                len(record["improvers"]),
                record["repetitions"],
                record["descendant_opportunities"],
            ),
            (2, 2, 2, 2),
        )
        self.assertFalse(f.scope.exists())

    def test_forward_schedule_derives_296_owners_1656_requests_and_declared_call_cap(self):
        f, record = prepare_forward(self, inventory_count=1, sized_source=False)
        screen = record["starts"][0]["screen"]
        tasks = len(screen["selected_ids"])
        common = len(record["starts"]) * record["repetitions"]
        counted = common * len(record["improvers"]) * record["descendant_opportunities"]
        screens = common + counted
        assessments = screens * tasks
        witnesses = screens
        owners = assessments * (1 + len(screen["stages"])) + witnesses * 2 + counted
        # Each supplied proposal makes one request; a witness generates only the first task.
        requests = (
            assessments * (f.generation_callbacks + sum(f.engine.native_callback_counts))
            + witnesses * (1 + f.generation_callbacks)
            + counted
        )
        self.assertEqual(
            (common, counted, screens, assessments, witnesses, owners, requests),
            (4, 16, 20, 60, 20, 296, 1656),
        )
        self.assertEqual(assessments * f.base.tasks.tasks[0].count, 600)
        scored_answers = assessments * f.base.tasks.tasks[0].count
        witness_answers = witnesses * f.base.tasks.tasks[0].count
        self.assertEqual(scored_answers * ANSWER_BYTES, 4_915_200)
        self.assertEqual(witness_answers * ANSWER_BYTES, 1_638_400)
        self.assertEqual(scored_answers + witness_answers, 800)
        self.assertEqual((scored_answers + witness_answers) * ANSWER_BYTES, 6_553_600)
        generation, native = screen["generation"], screen["native"]
        model_stages = sum(stage["allow_model"] for stage in screen["stages"])
        screen_cap = tasks * (
            generation["max_calls"]
            + model_stages * native["max_calls"]
            + len(screen["stages"])
            - model_stages
        )
        proposal_cap = record["proposal_template"]["max_calls"]
        witness_cap = proposal_cap + generation["max_calls"]
        maximum = common * (screen_cap + witness_cap) + counted * (
            proposal_cap + screen_cap + witness_cap
        )
        self.assertEqual(record["limits"]["study"]["max_calls"], maximum)
        self.assertLess(requests, maximum)
        self.assertEqual((f.engine.workers, f.engine.physical_sends), (0, 0))

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
