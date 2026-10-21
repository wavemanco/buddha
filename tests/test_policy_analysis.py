"""Pure preregistered descriptive arithmetic, without judging or financial access."""

import copy
import json
import subprocess
import sys
import unittest
from pathlib import Path
from unittest.mock import patch

from buddha.answers import TaskSet
from buddha.policy_analysis import PolicyResultsError, analyze_metrics
from buddha.policy_study import PolicyStudy
from buddha.releases import Release, _json

ROOT = Path(__file__).resolve().parents[1]
NAMES = ("child_regenerate", "child_in_context", "history_empty", "history_child", "interaction")


def study_fixture(repeats=2, occasions=2):
    rows = [
        {"id": identifier, "prompt": "Literal selected task " + repr(identifier)}
        for identifier in (1, "1", "v", "f")
    ]
    raw = b"".join(_json(row) + b"\n" for row in rows)
    import hashlib

    release = Release.from_record(
        {
            "format": "buddha.benchmark-release.v1",
            "benchmark": "synthetic",
            "release": "data-only",
            "upstream": {"url": "https://example.org/source", "revision": "a" * 40},
            "source": {
                "tasks.jsonl": hashlib.sha256(raw).hexdigest(),
                "lock.txt": "b" * 64,
                "src/check.py": "c" * 64,
            },
            "dependency_lock": "lock.txt",
            "task": {
                "dataset": "tasks.jsonl",
                "id_field": "id",
                "prompt_field": "prompt",
                "answers_field": "generations",
                "count": 10,
            },
            "commands": [{"module": "src.check", "argv": ["{artifacts}"]}],
            "artifacts": {
                "answers": "answers.jsonl",
                "results": ["rows.jsonl"],
                "summary": "summary.json",
            },
            "requires": ["ordered-text.v1"],
        }
    )
    source = TaskSet.from_dataset(release, raw)
    return PolicyStudy.from_bytes(
        _json(
            {
                "format": "buddha.policy-study.v1",
                "source": source.to_record(),
                "split": {
                    "release_sha256": source.release_sha256,
                    "dataset_sha256": source.dataset_sha256,
                    "partitions": {"development": [1, "1"], "validation": ["v"], "final": ["f"]},
                    "families": [
                        {"id": task.id, "family": "family-" + str(index)}
                        for index, task in enumerate(source.tasks)
                    ],
                },
                "selected_ids": [1, "1"],
                "child_policy": {
                    "instructions": "Preserve literal requirements.",
                    "sampling": "regenerate",
                },
                "generation": {
                    "provider": "openai",
                    "model": "frozen-fixture",
                    "max_output_tokens": 20,
                },
                "generation_repeats": repeats,
                "judge_occasions": occasions,
                "execution_order": [
                    {"arm": arm, "repeat": repeat}
                    for repeat in range(repeats)
                    for arm in ((0, 1, 2, 3) if repeat % 2 == 0 else (3, 2, 1, 0))
                ],
            }
        )
    )


def assessment_fixture(study):
    record = study.to_record()
    distinct = {1: ((1, 3, 4, 8), (3, 5, 6, 10)), "1": ((7, 4, 3, 2), (9, 6, 5, 4))}
    utility = {1: ((6, 5, 2, 1), (8, 7, 4, 3)), "1": ((0, 2, 5, 4), (2, 4, 7, 6))}
    return [
        {
            "task_id": task.id,
            "arm_index": arm,
            "generation_repeat": repeat,
            "judge_occasion": occasion,
            "distinct": distinct[task.id][repeat % 2][arm] if occasion == 0 else 10,
            "utility": utility[task.id][repeat % 2][arm] if occasion == 0 else 9.75,
            "status": "observed",
        }
        for task in study.tasks.tasks
        for arm in range(4)
        for repeat in range(record["generation_repeats"])
        for occasion in range(record["judge_occasions"])
    ]


class PolicyAnalysisTests(unittest.TestCase):
    def setUp(self):
        self.study = study_fixture()
        self.rows = assessment_fixture(self.study)

    def test_means_are_within_prompt_before_equal_prompt_contrasts_with_all_five_signs(self):
        result = analyze_metrics(self.study, self.rows)
        self.assertEqual(result["format"], "buddha.policy-analysis.v1")
        self.assertEqual(result["study_sha256"], self.study.fingerprint())
        self.assertEqual(result["status"], "complete")
        self.assertEqual(result["coverage"], {"expected": 32, "observed": 32, "usable": 32})
        primary = result["primary"]
        self.assertEqual([row["task_id"] for row in primary], [1, "1"])
        self.assertEqual(primary[0]["distinct"]["arm_means"], [2, 4, 5, 9])
        self.assertEqual(primary[1]["distinct"]["arm_means"], [8, 5, 4, 3])
        self.assertEqual(primary[0]["utility"]["arm_means"], [7, 6, 3, 2])
        self.assertEqual(primary[1]["utility"]["arm_means"], [1, 3, 6, 5])
        for metric, expected in (
            ("distinct", [-0.5, 1.5, -0.5, 1.5, 2]),
            ("utility", [0.5, -1, 0.5, -1, -1.5]),
        ):
            self.assertEqual(
                result["mean_contrasts"][metric], dict(zip(NAMES, expected, strict=True))
            )
        self.assertEqual(
            primary[0]["distinct"]["contrasts"], dict(zip(NAMES, [3, 5, 2, 4, 2], strict=True))
        )
        self.assertEqual(
            primary[1]["utility"]["contrasts"], dict(zip(NAMES, [5, 2, 2, -1, -3], strict=True))
        )

    def test_all_judging_occasions_are_retained_and_input_order_does_not_choose_primary(self):
        result = analyze_metrics(self.study, self.rows)
        reversed_result = analyze_metrics(self.study, list(reversed(self.rows)))
        self.assertEqual(result, reversed_result)
        retained = [{key: row[key] for key in self.rows[0]} for row in result["assessments"]]

        def coordinate(row):
            return (
                type(row["task_id"]).__name__,
                str(row["task_id"]),
                row["arm_index"],
                row["generation_repeat"],
                row["judge_occasion"],
            )

        self.assertEqual(sorted(retained, key=coordinate), sorted(self.rows, key=coordinate))
        self.assertEqual(sum(row["judge_occasion"] == 1 for row in result["assessments"]), 16)
        self.assertTrue(all(row["invalid_metrics"] == [] for row in result["assessments"]))

    def test_missing_primary_is_never_replaced_by_favorable_second_occasion(self):
        rows = [
            row
            for row in self.rows
            if not (
                row["task_id"] == 1
                and row["arm_index"] == 0
                and row["generation_repeat"] == 0
                and row["judge_occasion"] == 0
            )
        ]
        result = analyze_metrics(self.study, rows)
        self.assertEqual(result["status"], "incomplete")
        self.assertIsNone(result["mean_contrasts"])
        self.assertIsNone(result["primary"][0]["distinct"]["arm_means"][0])
        self.assertIsNone(result["primary"][0]["distinct"]["contrasts"]["child_regenerate"])
        self.assertEqual(result["primary"][0]["distinct"]["contrasts"]["child_in_context"], 5)
        self.assertEqual(result["primary"][1]["distinct"]["arm_means"], [8, 5, 4, 3])

    def test_missing_nonprimary_still_suppresses_complete_study_headline(self):
        rows = [row for row in self.rows if row is not self.rows[-1]]
        result = analyze_metrics(self.study, rows)
        self.assertEqual(result["status"], "incomplete")
        self.assertIsNone(result["mean_contrasts"])
        self.assertEqual(result["primary"], analyze_metrics(self.study, self.rows)["primary"])
        self.assertEqual(result["coverage"], {"expected": 32, "observed": 31, "usable": 31})

    def test_missing_population_is_explicit_and_never_zero_filled(self):
        result = analyze_metrics(self.study, [])
        self.assertEqual(result["status"], "incomplete")
        self.assertEqual(result["coverage"], {"expected": 32, "observed": 0, "usable": 0})
        self.assertEqual(len(result["assessments"]), 32)
        self.assertTrue(
            all(
                row["status"] == "missing" and row["distinct"] is None and row["utility"] is None
                for row in result["assessments"]
            )
        )
        self.assertIsNone(result["mean_contrasts"])
        for row in result["primary"]:
            for metric in ("distinct", "utility"):
                self.assertEqual(row[metric]["arm_means"], [None] * 4)
                self.assertTrue(all(value is None for value in row[metric]["contrasts"].values()))

    def test_nonfinite_boolean_out_of_range_or_missing_metrics_stay_incomplete_json_safe(self):
        invalid = {
            "distinct": [None, True, False, 2.0, 0, 11, float("nan"), float("inf"), "2"],
            "utility": [None, True, False, -1, 11, float("nan"), float("inf"), -float("inf"), "2"],
        }
        for metric, values in invalid.items():
            for value in values:
                with self.subTest(metric=metric, value=value):
                    rows = copy.deepcopy(self.rows)
                    rows[0][metric] = value
                    result = analyze_metrics(self.study, rows)
                    self.assertEqual(result["status"], "incomplete")
                    self.assertEqual(
                        result["coverage"], {"expected": 32, "observed": 32, "usable": 31}
                    )
                    self.assertIsNone(result["mean_contrasts"])
                    row = next(
                        row
                        for row in result["assessments"]
                        if type(row["task_id"]) is int
                        and row["arm_index"]
                        == row["generation_repeat"]
                        == row["judge_occasion"]
                        == 0
                    )
                    self.assertIsNone(row[metric])
                    self.assertIn(metric, row["invalid_metrics"])
                    self.assertIsNone(result["primary"][0][metric]["arm_means"][0])
                    json.dumps(result, allow_nan=False)

    def test_valid_zero_utility_and_one_distinct_remain_real_observations(self):
        rows = copy.deepcopy(self.rows)
        rows[0].update(distinct=1, utility=0.0)
        result = analyze_metrics(self.study, rows)
        self.assertEqual(result["status"], "complete")
        self.assertEqual(result["coverage"]["usable"], 32)
        self.assertTrue(
            any(
                row["utility"] == 0.0 and row["invalid_metrics"] == []
                for row in result["assessments"]
            )
        )

    def test_duplicate_coordinates_reject_identical_and_conflicting_records(self):
        for value in (self.rows[0], self.rows[0] | {"distinct": 9}):
            with self.subTest(conflicting=value["distinct"]), self.assertRaises(PolicyResultsError):
                analyze_metrics(self.study, [*self.rows, copy.deepcopy(value)])

    def test_closed_row_schema_and_coordinate_identity_errors_are_typed(self):
        changes = [
            ("task_id", True),
            ("task_id", 1.0),
            ("task_id", "foreign"),
            ("arm_index", True),
            ("arm_index", 4),
            ("generation_repeat", False),
            ("generation_repeat", 2),
            ("judge_occasion", True),
            ("judge_occasion", -1),
            ("status", "complete"),
            ("unexpected", 1),
        ]
        for field, value in changes:
            with self.subTest(field=field, value=value), self.assertRaises(PolicyResultsError):
                analyze_metrics(self.study, [self.rows[0] | {field: value}])
        for rows in (
            None,
            tuple(self.rows),
            [None],
            [{k: v for k, v in self.rows[0].items() if k != "utility"}],
        ):
            with self.subTest(rows=type(rows)), self.assertRaises(PolicyResultsError):
                analyze_metrics(self.study, rows)
        with self.assertRaises(PolicyResultsError):
            analyze_metrics({}, self.rows)

    def test_missing_status_requires_both_metrics_none(self):
        row = self.rows[0] | {"status": "missing", "distinct": None, "utility": None}
        result = analyze_metrics(self.study, [row])
        self.assertEqual(result["coverage"], {"expected": 32, "observed": 0, "usable": 0})
        for field in ("distinct", "utility"):
            with self.subTest(field=field), self.assertRaises(PolicyResultsError):
                analyze_metrics(self.study, [row | {field: 1}])

    def test_declared_repetitions_and_occasions_are_not_hardcoded(self):
        study = study_fixture(repeats=3, occasions=3)
        result = analyze_metrics(study, assessment_fixture(study))
        self.assertEqual(result["coverage"], {"expected": 72, "observed": 72, "usable": 72})
        self.assertEqual(len(result["assessments"]), 72)
        self.assertEqual(
            result["primary"][0]["distinct"]["arm_means"], [5 / 3, 11 / 3, 14 / 3, 26 / 3]
        )

    def test_oversized_declared_matrix_is_rejected_without_silent_sampling(self):
        with patch("buddha.policy_analysis.MAX_ASSESSMENTS", 31):
            with self.assertRaises(PolicyResultsError):
                analyze_metrics(self.study, [])
        with patch("buddha.policy_analysis.MAX_ASSESSMENTS", 32):
            self.assertEqual(analyze_metrics(self.study, self.rows)["coverage"]["expected"], 32)

    def test_result_views_are_independent_no_io_and_no_scientific_claim_is_invented(self):
        source = copy.deepcopy(self.rows)
        frozen_study = self.study.to_bytes()
        with (
            patch("builtins.open", side_effect=AssertionError("no I/O")),
            patch.object(Path, "open", side_effect=AssertionError("no I/O")),
        ):
            result = analyze_metrics(self.study, self.rows)
        self.assertEqual(self.rows, source)
        self.assertEqual(self.study.to_bytes(), frozen_study)
        first = copy.deepcopy(result)
        result["assessments"][0]["distinct"] = 999
        result["primary"][0]["distinct"]["arm_means"][0] = 999
        self.assertEqual(analyze_metrics(self.study, self.rows), first)
        self.assertTrue(first["limitations"])
        self.assertFalse(
            {"winner", "p_value", "p_values", "promotion", "heldout_improvement", "accuracy"}
            & set(first)
        )
        json.dumps(first, allow_nan=False)

    def test_pure_module_import_does_not_load_finance_native_or_legacy_science(self):
        script = """
import importlib.abc,sys
class Block(importlib.abc.MetaPathFinder):
 def find_spec(self,fullname,path=None,target=None):
  if fullname in {
   'buddha.authorization','buddha.gateway','buddha.ledger','buddha.provider',
   'buddha.native_run','buddha.native_evaluation','buddha.baseline','buddha.policy_run',
   'buddha.benchmark','buddha.evaluation','buddha.doctor','openai','anthropic'
  }:
   raise AssertionError('forbidden dependency '+fullname)
sys.meta_path.insert(0,Block())
from buddha.policy_analysis import analyze_metrics
assert callable(analyze_metrics)
"""
        completed = subprocess.run(
            [sys.executable, "-B", "-c", script],
            cwd=ROOT,
            capture_output=True,
            check=False,
            timeout=15,
        )
        self.assertEqual(completed.returncode, 0, completed.stderr)


if __name__ == "__main__":
    unittest.main()
