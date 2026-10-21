"""Saved 1.1 rows bind literal C1 data without running the official evaluator."""

import copy
import hashlib
import json
import math
import unittest
from pathlib import Path
from unittest.mock import patch

from buddha.answers import Answers, TaskSet
from buddha.noveltybench_results import NoveltyBenchResultsError, project_rows
from buddha.releases import Release, _json


def encoded(rows):
    return b"".join(
        json.dumps(row, ensure_ascii=False, allow_nan=True).encode() + b"\n" for row in rows
    )


def fixture():
    dataset = encoded(
        [
            {
                "qid": 1,
                "question": "Literal task one. 🌱",
                "category": "control",
                "prompt_paraphrases": ["A literal paraphrase."],
            },
            {"qid": "1", "question": "Literal task two.", "category": "creative"},
        ]
    )
    release = Release.from_record(
        {
            "format": "buddha.benchmark-release.v1",
            "benchmark": "synthetic",
            "release": "projection-fixture",
            "upstream": {"url": "https://example.org/source", "revision": "a" * 40},
            "source": {
                "tasks.jsonl": hashlib.sha256(dataset).hexdigest(),
                "lock.txt": "b" * 64,
                "src/check.py": "c" * 64,
            },
            "dependency_lock": "lock.txt",
            "task": {
                "dataset": "tasks.jsonl",
                "id_field": "qid",
                "prompt_field": "question",
                "answers_field": "responses",
                "count": 2,
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
    tasks = TaskSet.from_dataset(release, dataset)
    answers = Answers.from_results(
        release,
        tasks,
        [
            {"task_id": 1, "answers": ["", "[refused]"]},
            {"task_id": "1", "answers": ["same", "same"]},
        ],
        agent_sha256="d" * 64,
        metadata={"model": "saved-generator", "settings": {"x": True}},
    )
    retained = {"qid", "question", "responses", "model", "prompt_paraphrases"}
    native = [json.loads(line) for line in answers.native_bytes().splitlines()]
    partitions = [
        {k: v for k, v in row.items() if k in retained}
        | {
            "partition": [0, 1],
            "distinct": 2,
            "partition_key": "a" * 64,
            "partition_config": {
                "version": "1.1",
                "alg": "llm",
                "seed": None,
                "judge_model": "saved-judge",
            },
        }
        for row in native
    ]
    scores = [
        copy.deepcopy(row)
        | {
            "generation_scores": [8, 6],
            "partition_scores": [8, 6],
            "utility": 7,
            "score_key": "b" * 64,
            "score_config": {"version": "1.1", "scorer": "llm", "patience": 0.8},
        }
        for row in partitions
    ]
    return tasks, answers, partitions, scores


class NoveltyBenchResultsTests(unittest.TestCase):
    def setUp(self):
        self.tasks, self.answers, self.partitions, self.scores = fixture()

    def project(self, partitions=None, scores=None):
        return project_rows(
            self.tasks,
            self.answers,
            encoded(self.partitions if partitions is None else partitions),
            encoded(self.scores if scores is None else scores),
        )

    def test_projects_literal_native_metrics_and_typed_ids_without_recomputing_utility(self):
        result = self.project()
        self.assertEqual([row["task_id"] for row in result], [1, "1"])
        self.assertEqual([(row["distinct"], row["utility"]) for row in result], [(2, 7), (2, 7)])
        self.assertTrue(all(row["invalid_metrics"] == [] for row in result))
        self.assertEqual(self.partitions[0]["responses"], ["", "[refused]"])
        self.assertNotIn("category", self.partitions[0])
        # The supplied scalar is deliberately not recomputed from patience or head scores.
        self.assertEqual(result[0]["utility"], self.scores[0]["utility"])

    def test_duplicate_nonhead_none_is_legal_and_retained_metadata_can_be_present(self):
        partitions, scores = copy.deepcopy(self.partitions), copy.deepcopy(self.scores)
        partitions[0].update(partition=[0, 0], distinct=1, category="control", settings={"x": True})
        scores[0] = copy.deepcopy(partitions[0]) | {
            "generation_scores": [8, None],
            "partition_scores": [8],
            "utility": 4,
        }
        result = self.project(partitions, scores)
        self.assertEqual((result[0]["distinct"], result[0]["utility"]), (1, 4))
        self.assertEqual(result[0]["diagnostics"]["score"]["generation_scores"], [8, None])

    def test_explicit_official_refusal_remains_unscored_not_zero_utility(self):
        scores = copy.deepcopy(self.scores)
        scores[0].update(
            generation_scores=[None, None],
            partition_scores=[],
            utility=None,
            unscored="judge_refusal",
        )
        result = self.project(scores=scores)[0]
        self.assertEqual(result["distinct"], 2)
        self.assertIsNone(result["utility"])
        self.assertIn("utility", result["invalid_metrics"])
        self.assertEqual(result["diagnostics"]["score"]["unscored"], "judge_refusal")

    def test_numeric_invalidity_is_json_safe_missingness_without_coercion(self):
        for field, values in {
            "distinct": [None, True, 2.0, 0, -1, float("nan"), float("inf"), "2"],
            "utility": [None, False, -1, 11, float("nan"), float("inf"), -float("inf"), "7"],
        }.items():
            for value in values:
                with self.subTest(field=field, value=value):
                    partitions, scores = copy.deepcopy(self.partitions), copy.deepcopy(self.scores)
                    scores[0][field] = value
                    if field == "distinct":
                        partitions[0][field] = value
                    raw = encoded(scores)
                    before = hashlib.sha256(raw).hexdigest()
                    result = project_rows(self.tasks, self.answers, encoded(partitions), raw)
                    self.assertIsNone(result[0][field])
                    self.assertIn(field, result[0]["invalid_metrics"])
                    json.dumps(result, allow_nan=False)
                    self.assertEqual(hashlib.sha256(raw).hexdigest(), before)

    def test_partitions_require_normalized_integer_head_labels_and_consistent_valid_distinct(self):
        for labels in ([1, 0], [0, 2], [-1, 0], [0, True], [0, "1"], [], [0], [0, 1, 2]):
            with self.subTest(labels=labels), self.assertRaises(NoveltyBenchResultsError):
                partitions, scores = copy.deepcopy(self.partitions), copy.deepcopy(self.scores)
                partitions[0]["partition"] = scores[0]["partition"] = labels
                self.project(partitions, scores)
        partitions, scores = copy.deepcopy(self.partitions), copy.deepcopy(self.scores)
        partitions[0]["distinct"] = scores[0]["distinct"] = 1
        with self.assertRaises(NoveltyBenchResultsError):
            self.project(partitions, scores)

    def test_order_population_and_literal_generation_field_drift_rejects(self):
        for field, value in (
            ("qid", "1"),
            ("qid", True),
            ("question", "changed"),
            ("responses", ["edited", "[refused]"]),
            ("model", "changed"),
            ("prompt_paraphrases", ["changed"]),
            ("category", "foreign"),
        ):
            with self.subTest(field=field), self.assertRaises(NoveltyBenchResultsError):
                partitions, scores = copy.deepcopy(self.partitions), copy.deepcopy(self.scores)
                partitions[0][field] = value
                scores[0][field] = value
                self.project(partitions, scores)
        for partitions in (
            self.partitions[:1],
            [*self.partitions, self.partitions[0]],
            list(reversed(self.partitions)),
        ):
            with self.subTest(count=len(partitions)), self.assertRaises(NoveltyBenchResultsError):
                self.project(partitions=partitions)
        for field in ("qid", "question", "responses", "model", "prompt_paraphrases"):
            with self.subTest(missing=field), self.assertRaises(NoveltyBenchResultsError):
                partitions, scores = copy.deepcopy(self.partitions), copy.deepcopy(self.scores)
                del partitions[0][field]
                del scores[0][field]
                self.project(partitions, scores)

    def test_score_rows_preserve_every_partition_field_and_population(self):
        for field, value in (
            ("partition", [0, 0]),
            ("partition_key", "other"),
            ("partition_config", {}),
            ("question", "foreign"),
        ):
            with self.subTest(field=field), self.assertRaises(NoveltyBenchResultsError):
                scores = copy.deepcopy(self.scores)
                scores[0][field] = value
                self.project(scores=scores)
        with self.assertRaises(NoveltyBenchResultsError):
            self.project(scores=list(reversed(self.scores)))
        with self.assertRaises(NoveltyBenchResultsError):
            self.project(scores=self.scores[:1])

    def test_head_scores_and_partition_scores_are_structural_not_invented(self):
        for field, value in (
            ("generation_scores", [8]),
            ("generation_scores", [8, None]),
            ("generation_scores", [8, True]),
            ("generation_scores", [8, 11]),
            ("generation_scores", [8, 6.0]),
            ("partition_scores", [8]),
            ("partition_scores", [8, 7]),
        ):
            with (
                self.subTest(field=field, value=value),
                self.assertRaises(NoveltyBenchResultsError),
            ):
                scores = copy.deepcopy(self.scores)
                scores[0][field] = value
                self.project(scores=scores)
        partitions, scores = copy.deepcopy(self.partitions), copy.deepcopy(self.scores)
        partitions[0].update(partition=[0, 0], distinct=1)
        scores[0] = copy.deepcopy(partitions[0]) | {
            "generation_scores": [8, 6],
            "partition_scores": [8],
            "utility": 4,
        }
        with self.assertRaises(NoveltyBenchResultsError):
            self.project(partitions, scores)
        scores = copy.deepcopy(self.scores)
        scores[0].update(
            generation_scores=[None, None], partition_scores=[], utility=1, unscored="judge_refusal"
        )
        with self.assertRaises(NoveltyBenchResultsError):
            self.project(scores=scores)

    def test_missing_or_invalid_head_scores_are_explicit_incomplete_utility(self):
        for value in (None, True, 0, 11, 6.0, float("nan"), float("inf")):
            for per_class in ([8, value], []):
                with self.subTest(value=value, per_class=per_class):
                    scores = copy.deepcopy(self.scores)
                    scores[0].update(generation_scores=[8, value], partition_scores=per_class)
                    result = self.project(scores=scores)[0]
                    self.assertEqual(result["distinct"], 2)
                    self.assertIsNone(result["utility"])
                    self.assertIn("utility", result["invalid_metrics"])
                    quality = result["diagnostics"]["quality"]
                    self.assertEqual(quality["head_indices"], [0, 1])
                    self.assertEqual(quality["unusable_head_indices"], [1])
                    self.assertEqual(
                        quality["status"],
                        "missing_head_scores" if value is None else "invalid_head_scores",
                    )
                    safe = None if type(value) is float and not math.isfinite(value) else value
                    self.assertEqual(result["diagnostics"]["score"]["generation_scores"], [8, safe])
                    json.dumps(result, allow_nan=False)
        scores = copy.deepcopy(self.scores)
        scores[0].update(generation_scores=[None, None], partition_scores=[])
        result = self.project(scores=scores)[0]
        self.assertEqual(result["diagnostics"]["quality"]["status"], "missing_head_scores")
        self.assertEqual(result["diagnostics"]["quality"]["unusable_head_indices"], [0, 1])
        self.assertIsNone(result["utility"])

    def test_diagnostic_fields_are_copied_as_data_and_absence_never_proves_no_repair(self):
        partitions, scores = copy.deepcopy(self.partitions), copy.deepcopy(self.scores)
        partitions[0].update(repair_attempts=[{"round": 2}], lenient=True)
        scores[0] = copy.deepcopy(partitions[0]) | {
            k: v for k, v in scores[0].items() if k not in self.partitions[0]
        }
        scores[0].update(fallback_judge="saved-fallback", fallback_calls=[1])
        result = self.project(partitions, scores)
        self.assertEqual(result[0]["diagnostics"]["partition"]["repair_attempts"], [{"round": 2}])
        self.assertEqual(result[0]["diagnostics"]["score"]["fallback_calls"], [1])
        self.assertTrue(result[1]["diagnostics"]["absence_is_unknown"])
        self.assertIsNone(result[1]["diagnostics"]["partition"]["repair_attempts"])
        self.assertIsNone(result[1]["diagnostics"]["score"]["fallback_calls"])
        self.assertEqual(result[0]["diagnostics"]["partition"]["partition_key"], "a" * 64)
        result[0]["diagnostics"]["partition"]["repair_attempts"][0]["round"] = 999
        self.assertEqual(
            self.project(partitions, scores)[0]["diagnostics"]["partition"]["repair_attempts"],
            [{"round": 2}],
        )

    def test_mismatched_c1_task_artifact_is_rejected_and_projection_reads_no_paths(self):
        with self.assertRaises(NoveltyBenchResultsError):
            project_rows(
                self.tasks.select(["1", 1]),
                self.answers,
                encoded(self.partitions),
                encoded(self.scores),
            )
        before = self.answers.to_bytes(), self.tasks.to_bytes()
        with (
            patch("builtins.open", side_effect=AssertionError("no I/O")),
            patch.object(Path, "open", side_effect=AssertionError("no I/O")),
        ):
            result = self.project()
        self.assertEqual((self.answers.to_bytes(), self.tasks.to_bytes()), before)
        self.assertEqual(len(result), 2)

    def test_known_optional_native_fields_cannot_be_invented(self):
        record = self.answers.to_record()
        del record["metadata"]["model"]
        without_model = Answers.from_bytes(_json(record))
        with self.subTest(field="model"), self.assertRaises(NoveltyBenchResultsError):
            project_rows(self.tasks, without_model, encoded(self.partitions), encoded(self.scores))
        partitions, scores = copy.deepcopy(self.partitions), copy.deepcopy(self.scores)
        for row in [*partitions, *scores]:
            del row["model"]
        scores[0]["model"] = "Invented generator."
        with self.subTest(field="score-only model"), self.assertRaises(NoveltyBenchResultsError):
            project_rows(self.tasks, without_model, encoded(partitions), encoded(scores))
        scores = copy.deepcopy(self.scores)
        scores[0]["category"] = "foreign"
        with self.subTest(field="score-only category"), self.assertRaises(NoveltyBenchResultsError):
            self.project(scores=scores)
        partitions, scores = copy.deepcopy(self.partitions), copy.deepcopy(self.scores)
        partitions[1]["prompt_paraphrases"] = ["Invented source metadata."]
        scores[1]["prompt_paraphrases"] = ["Invented source metadata."]
        with self.subTest(field="prompt_paraphrases"), self.assertRaises(NoveltyBenchResultsError):
            self.project(partitions, scores)

    def test_json_bytes_row_count_and_depth_boundaries_are_typed(self):
        good = encoded(self.partitions)
        malformed = [
            None,
            good.decode(),
            b"\xff",
            b"{}\n",
            b"[]\n",
            b"\n",
            good.replace(b'"distinct": 2', b'"distinct": 2, "distinct": 2', 1),
            b'{"x":' + b"[" * 2000 + b"0" + b"]" * 2000 + b"}\n",
        ]
        for raw in malformed:
            with self.subTest(type=type(raw)), self.assertRaises(NoveltyBenchResultsError):
                project_rows(self.tasks, self.answers, raw, encoded(self.scores))
        with patch("buddha.noveltybench_results.MAX_JSON_BYTES", len(good) - 1):
            with self.assertRaises(NoveltyBenchResultsError):
                self.project()
        with patch("buddha.noveltybench_results.MAX_ROWS", 1):
            with self.assertRaises(NoveltyBenchResultsError):
                self.project()
        partitions, scores = copy.deepcopy(self.partitions), copy.deepcopy(self.scores)
        partitions[0]["partition_config"]["seed"] = float("nan")
        scores[0]["partition_config"]["seed"] = float("nan")
        with self.assertRaises(NoveltyBenchResultsError):
            self.project(partitions, scores)


if __name__ == "__main__":
    unittest.main()
