"""The controlled comparison freezes factors, scope and repetition before execution."""

import copy
import hashlib
import json
import subprocess
import sys
import unittest
from dataclasses import FrozenInstanceError
from pathlib import Path
from unittest.mock import patch

from buddha.answers import TaskSet
from buddha.policy_study import PolicyStudy, PolicyStudyError
from buddha.releases import Release, ReleaseError

ROOT = Path(__file__).resolve().parents[1]


def encoded(value):
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=True).encode()


class PolicyStudyTests(unittest.TestCase):
    def setUp(self):
        self.rows = [
            {"key": 1, "question": "Describe a clockwork garden. 🌱", "tag": "literal"},
            {"key": "1", "question": "Argue for a new kind of school."},
            {"key": "d2", "question": "Invent a quiet transport system."},
            {"key": "d3", "question": "Write a two-line dialogue."},
            {"key": "v0", "question": "VALIDATION-SENTINEL alpha"},
            {"key": "v1", "question": "VALIDATION-SENTINEL beta"},
            {"key": "f0", "question": "FINAL-SENTINEL alpha"},
            {"key": "f1", "question": "FINAL-SENTINEL beta"},
        ]
        self.reset_source()

    def reset_source(self):
        self.dataset = b"".join(encoded(row) + b"\n" for row in self.rows)
        self.release = Release.from_record(
            {
                "format": "buddha.benchmark-release.v1",
                "benchmark": "renamed-schema-fixture",
                "release": "configuration-only",
                "upstream": {"url": "https://example.org/official", "revision": "a" * 40},
                "source": {
                    "src/evaluate.py": "b" * 64,
                    "uv.lock": "c" * 64,
                    "population/tasks.jsonl": hashlib.sha256(self.dataset).hexdigest(),
                },
                "dependency_lock": "uv.lock",
                "task": {
                    "dataset": "population/tasks.jsonl",
                    "id_field": "key",
                    "prompt_field": "question",
                    "answers_field": "responses",
                    "count": 2,
                },
                "commands": [{"module": "src.evaluate", "argv": ["{artifacts}"]}],
                "artifacts": {
                    "answers": "new/answers.jsonl",
                    "results": ["new/results.jsonl"],
                    "summary": "new/summary.json",
                },
                "requires": ["ordered-text.v1"],
            }
        )
        self.source = TaskSet.from_dataset(self.release, self.dataset)
        self.record = {
            "format": "buddha.policy-study.v1",
            "source": self.source.to_record(),
            "split": {
                "release_sha256": self.source.release_sha256,
                "dataset_sha256": self.source.dataset_sha256,
                "partitions": {
                    "development": [1, "1", "d2", "d3"],
                    "validation": ["v0", "v1"],
                    "final": ["f0", "f1"],
                },
                "families": [
                    {"id": task.id, "family": "declared-family-" + str(index)}
                    for index, task in enumerate(self.source.tasks)
                ],
            },
            "selected_ids": ["1", 1, "d2"],
            "child_policy": {
                "instructions": "Choose a concrete original mechanism. 🌱",
                "sampling": "in-context",
            },
            "generation": {"provider": "openai", "model": "frozen-model", "max_output_tokens": 512},
            "generation_repeats": 2,
            "judge_occasions": 3,
            "execution_order": [
                {"arm": arm, "repeat": repeat} for repeat in range(2) for arm in (3, 0, 2, 1)
            ],
        }

    def study(self, record=None):
        return PolicyStudy.from_bytes(encoded(self.record if record is None else record))

    def test_four_fixed_arms_preserve_instructions_and_equal_model_access(self):
        study = self.study()
        instructions = self.record["child_policy"]["instructions"]
        expected = [
            ("", "regenerate"),
            ("", "in-context"),
            (instructions, "regenerate"),
            (instructions, "in-context"),
        ]
        arms = study.arms
        self.assertEqual(len(arms), 4)
        for index, ((text, sampling), arm) in enumerate(zip(expected, arms, strict=True)):
            policy = {"instructions": text, "sampling": sampling}
            self.assertEqual(set(arm), {"index", "arm_id", "policy", "config"})
            self.assertEqual(arm["index"], index)
            self.assertEqual(arm["policy"], policy)
            self.assertEqual(arm["arm_id"], hashlib.sha256(encoded(policy)).hexdigest())
            self.assertEqual(arm["config"], self.record["generation"] | policy)
        self.assertEqual(len({arm["arm_id"] for arm in arms}), 4)
        self.assertEqual(study.to_record()["child_policy"], self.record["child_policy"])

    def test_explicit_development_selection_preserves_order_types_literals_and_count(self):
        selected = self.study().tasks
        self.assertIsInstance(selected, TaskSet)
        self.assertEqual([task.id for task in selected.tasks], ["1", 1, "d2"])
        self.assertEqual([type(task.id) for task in selected.tasks], [str, int, str])
        self.assertEqual(selected.tasks[1].prompt, self.rows[0]["question"])
        self.assertTrue(all(task.count == 2 for task in selected.tasks))
        self.assertEqual(selected.release_sha256, self.release.fingerprint())
        self.assertEqual(selected.dataset_sha256, hashlib.sha256(self.dataset).hexdigest())
        self.assertEqual(
            selected.to_record()["dataset_base64"], self.source.to_record()["dataset_base64"]
        )

    def test_derived_configs_construct_actual_seed_requests_and_keep_existing_policy_ids(self):
        from agents.frozen_seed import request
        from buddha.policy import Policy

        for provider in ("openai", "anthropic"):
            record = copy.deepcopy(self.record)
            record["generation"]["provider"] = provider
            record["child_policy"]["instructions"] = "🌱" * 4000
            study = self.study(record)
            for arm in study.arms:
                self.assertEqual(arm["arm_id"], Policy.from_record(arm["policy"]).fingerprint())
                for task in study.tasks.tasks:
                    body = json.loads(request(arm["config"], task.to_record()))
                    self.assertEqual(body["model"], record["generation"]["model"])
                    cap = "max_completion_tokens" if provider == "openai" else "max_tokens"
                    self.assertEqual(body[cap], record["generation"]["max_output_tokens"])

    def test_schedule_has_every_arm_repeat_once_and_distinguishes_judging_from_generation(self):
        study = self.study()
        schedule = study.schedule()
        self.assertEqual(len(schedule), 8)
        self.assertEqual(
            [(cell["arm_index"], cell["generation_repeat"]) for cell in schedule],
            [(row["arm"], row["repeat"]) for row in self.record["execution_order"]],
        )
        self.assertEqual(len({cell["cell_id"] for cell in schedule}), 8)
        self.assertEqual(
            len(
                {
                    occasion["occasion_id"]
                    for cell in schedule
                    for occasion in cell["judge_occasions"]
                }
            ),
            24,
        )
        for cell in schedule:
            self.assertEqual(
                set(cell),
                {
                    "cell_id",
                    "arm_id",
                    "arm_index",
                    "generation_repeat",
                    "tasks_sha256",
                    "generation_config",
                    "judge_occasions",
                },
            )
            self.assertEqual(cell["tasks_sha256"], study.tasks.fingerprint())
            self.assertEqual(cell["generation_config"], study.arms[cell["arm_index"]]["config"])
            self.assertEqual([occasion["index"] for occasion in cell["judge_occasions"]], [0, 1, 2])
        # A schedule carries identities/configuration, never source data or judge inputs.
        raw = encoded(schedule)
        for sentinel in (
            b"FINAL-SENTINEL",
            b"VALIDATION-SENTINEL",
            b"dataset_base64",
            b"Describe a clockwork garden",
        ):
            self.assertNotIn(sentinel, raw)

    def test_round_trip_and_stable_identities_bind_the_whole_declared_order(self):
        study = self.study()
        self.assertEqual(PolicyStudy.from_bytes(study.to_bytes()), study)
        self.assertEqual(study.to_record(), self.record)
        self.assertEqual(study.fingerprint(), hashlib.sha256(study.to_bytes()).hexdigest())
        self.assertEqual(study.schedule(), self.study().schedule())
        changed = copy.deepcopy(self.record)
        changed["execution_order"].reverse()
        other = self.study(changed)
        self.assertNotEqual(other.fingerprint(), study.fingerprint())
        self.assertTrue(
            {cell["cell_id"] for cell in study.schedule()}.isdisjoint(
                {cell["cell_id"] for cell in other.schedule()}
            )
        )

    def test_mutating_inputs_or_returned_views_cannot_change_frozen_contract(self):
        record = copy.deepcopy(self.record)
        study = self.study(record)
        saved = study.to_bytes()
        record["child_policy"]["instructions"] = "changed"
        study.to_record()["split"]["partitions"]["final"].clear()
        study.arms[0]["config"]["model"] = "changed"
        study.schedule()[0]["judge_occasions"].clear()
        self.assertEqual(study.to_bytes(), saved)
        self.assertEqual(len(study.schedule()[0]["judge_occasions"]), 3)
        with self.assertRaises(FrozenInstanceError):
            study.data = b"{}"

    def test_partial_source_view_cannot_hide_the_heldout_population(self):
        record = copy.deepcopy(self.record)
        record["source"] = self.source.select(
            self.record["split"]["partitions"]["development"]
        ).to_record()
        with self.assertRaises(PolicyStudyError):
            self.study(record)
        # Full source membership is allowed in an explicitly reordered view.
        record["source"] = self.source.select(
            [task.id for task in reversed(self.source.tasks)]
        ).to_record()
        self.assertEqual([task.id for task in self.study(record).tasks.tasks], ["1", 1, "d2"])

    def test_split_is_complete_disjoint_and_bound_to_exact_source(self):
        variants = []
        for key in ("release_sha256", "dataset_sha256"):
            record = copy.deepcopy(self.record)
            record["split"][key] = "0" * 64
            variants.append(record)
        for partition, values in (
            ("development", [1, "1", "d2"]),
            ("validation", ["v0", "f0"]),
            ("final", ["f0", "foreign"]),
            ("final", ["f0", "f0"]),
            ("final", []),
            ("development", [True, "1", "d2", "d3"]),
        ):
            record = copy.deepcopy(self.record)
            record["split"]["partitions"][partition] = values
            variants.append(record)
        for record in variants:
            with self.subTest(split=record["split"]), self.assertRaises(PolicyStudyError):
                self.study(record)

    def test_selected_ids_must_be_nonempty_unique_explicit_development_members(self):
        for selected in ([], ["v0"], ["f0"], ["foreign"], [1, 1], [True], "d2", None):
            record = copy.deepcopy(self.record)
            record["selected_ids"] = selected
            with self.subTest(selected=selected), self.assertRaises(PolicyStudyError):
                self.study(record)

    def test_declared_families_cannot_cross_partitions_or_omit_any_source_id(self):
        variants = []
        for index, family in ((4, "declared-family-0"), (6, "declared-family-4")):
            record = copy.deepcopy(self.record)
            record["split"]["families"][index]["family"] = family
            variants.append(record)
        for values in (
            self.record["split"]["families"][:-1],
            self.record["split"]["families"] + [self.record["split"]["families"][0]],
            [{"id": True, "family": "x"}] + self.record["split"]["families"][1:],
        ):
            record = copy.deepcopy(self.record)
            record["split"]["families"] = values
            variants.append(record)
        for record in variants:
            with (
                self.subTest(families=record["split"]["families"]),
                self.assertRaises(PolicyStudyError),
            ):
                self.study(record)
        # Related prompts may share one development partition.
        record = copy.deepcopy(self.record)
        record["split"]["families"][1]["family"] = "declared-family-0"
        self.study(record)

    def test_normalized_prompt_duplicates_cannot_leak_across_partitions(self):
        self.rows[4]["question"] = "  DESCRIBE a\nclockwork\tGARDEN. 🌱 "
        self.reset_source()
        with self.assertRaises(PolicyStudyError):
            self.study()
        # The same duplicate inside development is permitted and preserved.
        self.rows[4]["question"] = "VALIDATION-SENTINEL alpha"
        self.rows[2]["question"] = "  DESCRIBE a\nclockwork\tGARDEN. 🌱 "
        self.reset_source()
        self.assertEqual(self.study().tasks.tasks[-1].prompt, self.rows[2]["question"])

    def test_exact_policy_shape_and_unicode_character_limit_match_frozen_seed(self):
        for policy in (
            {"instructions": "", "sampling": "regenerate"},
            {"instructions": " \n\t", "sampling": "in-context"},
            {"instructions": "x" * 4001, "sampling": "regenerate"},
            {"instructions": "\ud800", "sampling": "regenerate"},
            {"instructions": "x", "sampling": "other"},
            {"instructions": "x", "sampling": True},
            {"instructions": 4, "sampling": "regenerate"},
            {"instructions": "x", "sampling": "regenerate", "tools": []},
        ):
            record = copy.deepcopy(self.record)
            record["child_policy"] = policy
            with self.subTest(policy=policy), self.assertRaises(PolicyStudyError):
                self.study(record)
        record = copy.deepcopy(self.record)
        record["child_policy"]["instructions"] = "🌱" * 4000
        self.assertEqual(self.study(record).arms[2]["policy"]["instructions"], "🌱" * 4000)

    def test_generation_limits_are_explicit_positive_and_shared_across_arms(self):
        for key, value in (
            ("provider", "other"),
            ("provider", True),
            ("model", " "),
            ("max_output_tokens", True),
            ("max_output_tokens", 0),
            ("max_output_tokens", 2**63),
            ("temperature", 1),
        ):
            record = copy.deepcopy(self.record)
            record["generation"][key] = value
            with self.subTest(key=key, value=value), self.assertRaises(PolicyStudyError):
                self.study(record)
        record = copy.deepcopy(self.record)
        record["generation"] = {
            "provider": "anthropic",
            "model": "other-frozen-model",
            "max_output_tokens": 2**63 - 1,
        }
        self.assertTrue(
            all(arm["config"]["provider"] == "anthropic" for arm in self.study(record).arms)
        )

    def test_generation_and_judging_repetitions_have_distinct_bounded_axes(self):
        for key, values in (
            ("generation_repeats", [True, 1, 101, 2.0]),
            ("judge_occasions", [True, 1, 17, 2.0]),
        ):
            for value in values:
                record = copy.deepcopy(self.record)
                record[key] = value
                with self.subTest(key=key, value=value), self.assertRaises(PolicyStudyError):
                    self.study(record)
        record = copy.deepcopy(self.record)
        record["generation_repeats"] = 100
        record["judge_occasions"] = 16
        record["execution_order"] = [
            {"arm": arm, "repeat": repeat} for repeat in range(100) for arm in range(4)
        ]
        self.assertEqual(len(self.study(record).schedule()), 400)

    def test_execution_order_cannot_drop_duplicate_or_invent_a_cell(self):
        for replacement in (
            None,
            [],
            self.record["execution_order"][:-1],
            self.record["execution_order"] + [self.record["execution_order"][0]],
        ):
            record = copy.deepcopy(self.record)
            record["execution_order"] = replacement
            with self.subTest(order=replacement), self.assertRaises(PolicyStudyError):
                self.study(record)
        for cell in (
            {"arm": True, "repeat": 0},
            {"arm": 4, "repeat": 0},
            {"arm": 0, "repeat": 2},
            {"arm": 0, "repeat": False},
            {"arm": 0, "repeat": 0, "extra": 1},
            self.record["execution_order"][1],
        ):
            record = copy.deepcopy(self.record)
            record["execution_order"][0] = cell
            with self.subTest(cell=cell), self.assertRaises(PolicyStudyError):
                self.study(record)

    def test_untrusted_json_failures_are_typed_without_file_or_network_access(self):
        self.assertTrue(issubclass(PolicyStudyError, ReleaseError))
        for raw in (
            b"{}",
            b"[]",
            b'{"format":1,"format":2}',
            b"not json",
            encoded(self.record | {"extra": 1}),
        ):
            with self.subTest(raw=raw[:80]), self.assertRaises(PolicyStudyError):
                PolicyStudy.from_bytes(raw)
        with (
            patch.object(Path, "open", side_effect=AssertionError("file access")),
            patch("socket.socket", side_effect=AssertionError("network access")),
        ):
            self.assertEqual(len(self.study().schedule()), 8)

    def test_contract_imports_without_legacy_benchmark_sdk_or_financial_modules(self):
        program = """
import importlib.abc, sys
class Block(importlib.abc.MetaPathFinder):
    def find_spec(self, fullname, path=None, target=None):
        if fullname.split('.')[0] in {'openai', 'anthropic', 'httpx'} or fullname in {
            'buddha.benchmark', 'buddha.evaluation', 'buddha.policy', 'buddha.splits',
            'buddha.provider', 'buddha.ledger', 'buddha.authorization', 'buddha.gateway',
            'buddha.history', 'buddha.gateway_history', 'buddha.baseline',
            'buddha.agent_run', 'buddha.native_run', 'buddha.reference',
        }:
            raise AssertionError('forbidden import: ' + fullname)
sys.meta_path.insert(0, Block())
sys.path.insert(0, sys.argv[1])
from buddha.policy_study import PolicyStudy
print(PolicyStudy.__name__)
"""
        result = subprocess.run(
            [sys.executable, "-I", "-B", "-c", program, str(ROOT)],
            capture_output=True,
            text=True,
            timeout=15,
            check=False,
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(result.stdout, "PolicyStudy\n")


if __name__ == "__main__":
    unittest.main()
