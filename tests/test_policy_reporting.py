"""Registered diagnostics retain repeated sets and unknown evidence without new scores."""

import copy
import hashlib
import json
import unittest
from pathlib import Path
from unittest.mock import patch

from buddha.answers import TaskSet
from buddha.policy_analysis import PolicyResultsError, analyze_metrics, describe_observations
from buddha.policy_study import PolicyStudy
from buddha.releases import Release, _json

RECOVERY = ("repair_attempts", "lenient", "fallback_judge", "fallback_calls", "unscored")


def fixture(repeats=2, occasions=2, category=True):
    rows = [
        {"id": name, "prompt": "Literal task " + repr(name)} for name in (1, "1", "third", "v", "f")
    ]
    for index, row in enumerate(rows):
        if category:
            row["category"] = "Two-task category" if index < 2 else "Other category"
    raw = b"".join(_json(row) + b"\n" for row in rows)
    release = Release.from_record(
        {
            "format": "buddha.benchmark-release.v1",
            "benchmark": "synthetic",
            "release": "diagnostics",
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
                "count": 3,
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
    study = PolicyStudy.from_bytes(
        _json(
            {
                "format": "buddha.policy-study.v1",
                "source": source.to_record(),
                "split": {
                    "release_sha256": source.release_sha256,
                    "dataset_sha256": source.dataset_sha256,
                    "partitions": {
                        "development": [1, "1", "third"],
                        "validation": ["v"],
                        "final": ["f"],
                    },
                    "families": [
                        {"id": task.id, "family": "family-" + str(index)}
                        for index, task in enumerate(source.tasks)
                    ],
                },
                "selected_ids": [1, "1", "third"],
                "child_policy": {
                    "instructions": "Preserve literal tasks.",
                    "sampling": "regenerate",
                },
                "generation": {"provider": "openai", "model": "fixture", "max_output_tokens": 20},
                "generation_repeats": repeats,
                "judge_occasions": occasions,
                "execution_order": [
                    {"arm": arm, "repeat": repeat}
                    for repeat in range(repeats)
                    for arm in (3, 0, 2, 1)
                ],
            }
        )
    )
    measurements, projections = [], []
    for cell in study.schedule():
        for occasion in cell["judge_occasions"]:
            j = occasion["index"]
            projected = []
            for index, task in enumerate(study.tasks.tasks):
                labels = (
                    ([0, 0, 1], [0, 1, 1], [0, 1, 2])[index]
                    if j == 0
                    else ([9, 9, 3], [9, 3, 9], [5, 6, 7])[index]
                )
                d = len(set(labels))
                u = 2 + index + cell["arm_index"] + cell["generation_repeat"] * 0.5 + j * 0.25
                measurements.append(
                    {
                        "task_id": task.id,
                        "arm_index": cell["arm_index"],
                        "generation_repeat": cell["generation_repeat"],
                        "judge_occasion": j,
                        "distinct": d,
                        "utility": u,
                        "status": "observed",
                    }
                )
                projected.append(
                    {
                        "task_id": task.id,
                        "distinct": d,
                        "utility": u,
                        "invalid_metrics": [],
                        "diagnostics": {
                            "partition": {"partition": labels},
                            "score": {},
                            "absence_is_unknown": True,
                        },
                    }
                )
            projections.append(
                {
                    "cell_id": cell["cell_id"],
                    "occasion_id": occasion["occasion_id"],
                    "source_generation": {
                        "baseline_directory": "/data/" + cell["cell_id"],
                        "stage_seal_sha256": "a" * 64,
                        "owner_manifest_sha256": "b" * 64,
                        "owner_ledger_sha256": "c" * 64,
                    },
                    "report_sha256": "d" * 64,
                    "summary": {"path": "/data/summary.json", "sha256": "e" * 64},
                    "rows": projected,
                }
            )
    return study, analyze_metrics(study, measurements), projections


class PolicyReportingTests(unittest.TestCase):
    def setUp(self):
        self.study, self.analysis, self.occasions = fixture()

    def describe(self, analysis=None, occasions=None):
        return describe_observations(
            self.study,
            self.analysis if analysis is None else analysis,
            self.occasions if occasions is None else occasions,
        )

    def test_literal_source_categories_and_both_generation_repetitions_beside_primary_means(self):
        result = self.describe()
        self.assertEqual(result["format"], "buddha.policy-observations.v1")
        self.assertEqual(result["study_sha256"], self.study.fingerprint())
        desc = result["descriptive"]
        self.assertEqual(desc["primary_judge_occasion"], 0)
        self.assertEqual([row["task_id"] for row in desc["tasks"]], [1, "1", "third"])
        self.assertEqual(
            [row["category"] for row in desc["tasks"]],
            ["Two-task category", "Two-task category", "Other category"],
        )
        self.assertEqual(
            [row["prompt"] for row in desc["tasks"]],
            [task.prompt for task in self.study.tasks.tasks],
        )
        repetitions = desc["generation_repetitions"]
        self.assertEqual(len(repetitions), 12)
        first = repetitions[0]
        self.assertEqual((first["task_id"], first["arm_index"]), (1, 0))
        self.assertEqual([row["generation_repeat"] for row in first["values"]], [0, 1])
        self.assertEqual([row["utility"] for row in first["values"]], [2, 2.5])
        self.assertEqual(first["means"], {"distinct": 2, "utility": 2.25})
        self.assertNotIn("Literal task 'v'", json.dumps(result))
        self.assertNotIn("Literal task 'f'", json.dumps(result))

    def test_category_denominators_and_complete_ranges_use_existing_prompt_means_and_contrasts(
        self,
    ):
        category = self.describe()["descriptive"]["categories"][0]
        self.assertEqual(category["task_ids"], [1, "1"])
        self.assertEqual(
            category["coverage"],
            {
                "planned_tasks": 2,
                "observed_tasks": 2,
                "complete_observed_tasks": 2,
                "usable_tasks": 2,
                "planned_assessments": 16,
                "observed_assessments": 16,
                "usable_assessments": 16,
            },
        )
        self.assertEqual(
            category["arm_ranges"][0]["utility"],
            {
                "planned": 2,
                "available": 2,
                "available_range": [2.25, 3.25],
                "complete_range": [2.25, 3.25],
            },
        )
        self.assertEqual(
            category["contrast_ranges"]["utility"]["child_regenerate"]["complete_range"], [2, 2]
        )
        self.assertEqual(
            category["contrast_ranges"]["utility"]["interaction"]["complete_range"], [0, 0]
        )

    def test_partial_category_ranges_are_available_diagnostics_not_complete_subset_claims(self):
        rows = [
            {k: v for k, v in row.items() if k != "invalid_metrics"}
            for row in self.analysis["assessments"]
        ]
        missing = next(
            row
            for row in rows
            if type(row["task_id"]) is int
            and row["arm_index"] == row["generation_repeat"] == row["judge_occasion"] == 0
        )
        missing.update(utility=None)
        analysis = analyze_metrics(self.study, rows)
        # A single unscored quality row is incomplete while its occasion stays present.
        target = next(
            row
            for row in self.occasions
            if row["cell_id"] == self.study.schedule()[1]["cell_id"]
            and row["occasion_id"] == self.study.schedule()[1]["judge_occasions"][0]["occasion_id"]
        )
        occasions = copy.deepcopy(self.occasions)
        changed = next(
            row
            for row in occasions
            if row["cell_id"] == target["cell_id"] and row["occasion_id"] == target["occasion_id"]
        )
        unscored = next(row for row in changed["rows"] if type(row["task_id"]) is int)
        unscored.update(utility=None, invalid_metrics=["utility"])
        result = self.describe(analysis, occasions)
        category = result["descriptive"]["categories"][0]
        self.assertEqual(category["coverage"]["observed_tasks"], 2)
        self.assertEqual(category["coverage"]["complete_observed_tasks"], 2)
        self.assertEqual(category["coverage"]["usable_tasks"], 1)
        view = category["arm_ranges"][0]["utility"]
        self.assertEqual(
            view,
            {"planned": 2, "available": 1, "available_range": [3.25, 3.25], "complete_range": None},
        )
        self.assertIsNone(analysis["mean_contrasts"])

    def test_judge_deltas_and_ranges_compare_each_later_occasion_only_with_zero(self):
        result = self.describe()
        self.assertEqual(len(result["judge_agreement"]), 24)
        row = result["judge_agreement"][0]
        self.assertEqual([v["index"] for v in row["occasions"]], [0, 1])
        comparison = row["comparisons"][0]
        self.assertEqual((comparison["reference"], comparison["occasion"]), (0, 1))
        self.assertEqual(
            comparison["metrics"]["distinct"], {"delta": 0, "range": [2, 2], "missing_reasons": []}
        )
        self.assertEqual(
            comparison["metrics"]["utility"],
            {"delta": 0.25, "range": [5, 5.25], "missing_reasons": []},
        )
        self.assertEqual(row["occasions"][0]["partition"], [0, 0, 1])
        self.assertEqual(row["occasions"][1]["partition"], [9, 9, 3])

    def test_relations_are_label_invariant_and_changes_use_original_unordered_positions(self):
        rows = self.describe()["judge_agreement"]
        first = rows[0]["comparisons"][0]["relations"]
        self.assertEqual(
            first,
            {
                "planned_pairs": 3,
                "compared_pairs": 3,
                "agree": 3,
                "disagree": 0,
                "changed_pairs": [],
                "missing_reasons": [],
            },
        )
        second = rows[1]["comparisons"][0]["relations"]
        self.assertEqual((second["agree"], second["disagree"]), (1, 2))
        self.assertEqual(
            second["changed_pairs"],
            [
                {"left": 0, "right": 2, "reference": "distinct", "comparison": "equivalent"},
                {"left": 1, "right": 2, "reference": "equivalent", "comparison": "distinct"},
            ],
        )
        self.assertEqual(sum(r["comparisons"][0]["relations"]["planned_pairs"] for r in rows), 72)

    def test_missing_later_occasion_never_appears_as_perfect_agreement_or_replaces_zero(self):
        target = self.study.schedule()[0]
        rows = [
            {k: v for k, v in row.items() if k != "invalid_metrics"}
            for row in self.analysis["assessments"]
        ]
        for row in rows:
            if (
                row["arm_index"] == target["arm_index"]
                and row["generation_repeat"] == 0
                and row["judge_occasion"] == 1
            ):
                row.update(status="missing", distinct=None, utility=None)
        occasions = [
            row
            for row in self.occasions
            if row["occasion_id"] != target["judge_occasions"][1]["occasion_id"]
        ]
        analysis = analyze_metrics(self.study, rows)
        result = self.describe(analysis, occasions)
        row = result["judge_agreement"][0]
        comparison = row["comparisons"][0]
        self.assertIsNone(comparison["metrics"]["utility"]["delta"])
        relation = comparison["relations"]
        self.assertEqual((relation["planned_pairs"], relation["compared_pairs"]), (3, 0))
        self.assertIsNone(relation["agree"])
        self.assertIsNone(relation["disagree"])
        self.assertIsNone(relation["changed_pairs"])
        self.assertTrue(relation["missing_reasons"])
        self.assertEqual(analysis["primary"], self.analysis["primary"])

    def test_literal_recovery_fields_and_false_values_have_explicit_unknown_availability(self):
        occasions = copy.deepcopy(self.occasions)
        occasions[0]["rows"][0]["diagnostics"]["partition"].update(
            lenient=False, repair_attempts=[{"round": 2}]
        )
        occasions[0]["rows"][0]["diagnostics"]["score"].update(
            fallback_judge="saved", fallback_calls=[1], unscored=None
        )
        result = self.describe(occasions=occasions)
        row = result["recovery"][0]
        self.assertFalse(row["partition"]["lenient"])
        self.assertEqual(row["partition"]["repair_attempts"], [{"round": 2}])
        self.assertEqual(row["availability"]["partition"]["lenient"], "recorded")
        self.assertEqual(row["availability"]["score"]["unscored"], "unknown")
        self.assertEqual(row["availability"]["partition"]["fallback_calls"], "unknown")
        self.assertTrue(row["absence_is_unknown"])
        self.assertFalse({"parser_verified", "physical_retry_count", "no_repairs"} & set(row))

    def test_unrecorded_partition_keeps_relations_unknown_but_preserves_saved_metrics(self):
        occasions = copy.deepcopy(self.occasions)
        del occasions[0]["rows"][0]["diagnostics"]["partition"]["partition"]
        comparison = self.describe(occasions=occasions)["judge_agreement"][0]["comparisons"][0]
        self.assertEqual(comparison["metrics"]["utility"]["delta"], 0.25)
        relations = comparison["relations"]
        self.assertEqual((relations["planned_pairs"], relations["compared_pairs"]), (3, 0))
        self.assertIsNone(relations["agree"])
        self.assertIsNone(relations["changed_pairs"])
        self.assertIn("partition_not_recorded:0", relations["missing_reasons"])

    def test_identity_population_and_scalar_disagreement_are_typed_errors(self):
        mutations = [
            lambda x: x.append(copy.deepcopy(x[0])),
            lambda x: x[0].update(cell_id="f" * 64),
            lambda x: x[0].update(occasion_id="f" * 64),
            lambda x: x[0]["rows"][0].update(task_id=True),
            lambda x: x[0]["rows"][0].update(utility=9),
            lambda x: x[0]["rows"][0]["diagnostics"]["partition"].update(partition=[0, True, 1]),
            lambda x: x[0]["rows"][0]["diagnostics"]["partition"].update(partition=[0, 0]),
        ]
        for mutate in mutations:
            with self.subTest(mutation=mutate):
                changed = copy.deepcopy(self.occasions)
                mutate(changed)
                with self.assertRaises(PolicyResultsError):
                    self.describe(occasions=changed)
        for value in (None, {}, tuple(self.occasions)):
            with self.subTest(type=type(value)), self.assertRaises(PolicyResultsError):
                self.describe(occasions=value) if value is not None else describe_observations(
                    self.study, self.analysis, None
                )
        analysis = copy.deepcopy(self.analysis)
        analysis["primary"][0]["utility"]["arm_means"][0] = 9
        with self.assertRaises(PolicyResultsError):
            self.describe(analysis=analysis)

    def test_planned_relation_limit_is_checked_before_expansion(self):
        with patch("buddha.policy_analysis.MAX_RELATIONS", 71):
            with self.assertRaises(PolicyResultsError):
                self.describe()
        with patch("buddha.policy_analysis.MAX_RELATIONS", 72):
            self.assertEqual(len(self.describe()["judge_agreement"]), 24)

    def test_unknown_category_is_retained_and_future_repeat_axes_are_explicit(self):
        study, analysis, occasions = fixture(repeats=3, occasions=3, category=False)
        result = describe_observations(study, analysis, occasions)
        self.assertEqual(len(result["descriptive"]["categories"]), 1)
        self.assertIsNone(result["descriptive"]["categories"][0]["category"])
        self.assertEqual(
            result["descriptive"]["categories"][0]["coverage"]["planned_assessments"], 36
        )
        self.assertEqual(len(result["judge_agreement"]), 36)
        self.assertTrue(
            all(
                [r["occasion"] for r in row["comparisons"]] == [1, 2]
                for row in result["judge_agreement"]
            )
        )

    def test_result_is_detached_without_io_or_new_claims_and_primary_analysis_stays_unchanged(self):
        before = copy.deepcopy((self.analysis, self.occasions))
        with (
            patch("builtins.open", side_effect=AssertionError("no I/O")),
            patch.object(Path, "open", side_effect=AssertionError("no I/O")),
        ):
            result = self.describe()
        self.assertEqual((self.analysis, self.occasions), before)
        fresh = copy.deepcopy(result)
        result["recovery"][0]["partition"]["repair_attempts"] = [999]
        result["descriptive"]["generation_repetitions"][0]["values"][0]["utility"] = 999
        self.assertEqual(self.describe(), fresh)
        self.assertTrue(fresh["limitations"])
        self.assertFalse({"winner", "p_value", "accuracy", "promotion"} & set(fresh))
        json.dumps(fresh, allow_nan=False)
        analysis = copy.deepcopy(self.analysis)
        analysis.update(status="incomplete", mean_contrasts=None)
        self.assertEqual(self.describe(analysis=analysis)["descriptive"], fresh["descriptive"])


if __name__ == "__main__":
    unittest.main()
