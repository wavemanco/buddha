"""Executable first-slice acceptance contract; no models or network required."""

import hashlib
import json
import math
import unittest
from dataclasses import FrozenInstanceError, replace
from pathlib import Path

from buddha.evaluation import (
    EvaluationProtocol,
    ValidationError,
    score_sequence,
    summarize_run,
)


def sha256(text):
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def protocol(**changes):
    fields = {
        "upstream_commit": "a" * 40,
        "metric_version": "1.1",
        "dataset_sha256": sha256("dataset"),
        "split_sha256": sha256("split"),
        "partition_model": "partition-model-snapshot",
        "quality_model": "quality-model-snapshot",
        "partition_prompt_sha256": sha256("partition prompt"),
        "quality_prompt_sha256": sha256("quality prompt"),
        "generation_config_sha256": sha256("generation configuration"),
        "fallback_policy_sha256": sha256("no fallback"),
        "ordering_seed": 7,
        "k": 3,
        "patience": 0.8,
    }
    fields.update(changes)
    return EvaluationProtocol(**fields)


def evidence_row(selected_protocol, **changes):
    row = {
        "id": "prompt-1",
        "prompt": "Offer a useful alternative.",
        "generations": ["First answer", "First answer again", "Second answer"],
        "partition": [0, 0, 1],
        "generation_scores": [10, None, 5],
        "utility": 330 / 61,
        "distinct": 2,
        "protocol_fingerprint": selected_protocol.fingerprint(),
    }
    row.update(changes)
    return row


class SequenceScoreTests(unittest.TestCase):
    def test_pinned_published_metric_vectors(self):
        fixture_path = Path(__file__).parent / "fixtures" / "published_metrics.json"
        fixture = json.loads(fixture_path.read_text(encoding="utf-8"))
        for case in fixture["cases"]:
            with self.subTest(instance_id=case["id"]):
                result = score_sequence(case["partition"], case["generation_scores"])
                self.assertEqual(result.distinct, case["distinct"])
                self.assertAlmostEqual(result.utility, case["utility"], places=12)

    def test_malformed_sequence_containers_fail_with_typed_error(self):
        for partition, scores in [("001", [10, None, 5]), ([0, 0, 1], None)]:
            with self.subTest(partition=partition, scores=scores):
                with self.assertRaises(ValidationError):
                    score_sequence(partition, scores, expected_k=3)

    def test_independent_golden_discounted_utility(self):
        # (10 + .8 * 0 + .64 * 5) / (1 + .8 + .64) = 330/61.
        result = score_sequence([0, 0, 1], [10, None, 5], expected_k=3)
        self.assertEqual(result.distinct, 2)
        self.assertAlmostEqual(result.utility, 330 / 61, places=12)

    def test_patience_zero_and_one_are_defined(self):
        for patience, expected in [(0, 10), (1, 5)]:
            with self.subTest(patience=patience):
                result = score_sequence([0, 0, 1], [10, None, 5], patience=patience, expected_k=3)
                self.assertEqual(result.utility, expected)

    def test_every_unique_response_receives_its_quality(self):
        result = score_sequence([0, 1, 2], [10, 10, 10], expected_k=3)
        self.assertEqual(result.distinct, 3)
        self.assertAlmostEqual(result.utility, 10)

    def test_duplicates_credit_only_first_occurrence(self):
        result = score_sequence([0, 0, 0], [10, 10, 10], expected_k=3)
        self.assertEqual(result.distinct, 1)
        self.assertAlmostEqual(result.utility, 250 / 61, places=12)

    def test_later_duplicate_with_higher_quality_does_not_replace_head(self):
        first = score_sequence([0, 0, 1], [1, None, 5], expected_k=3)
        later = score_sequence([0, 0, 1], [1, 10, 5], expected_k=3)
        self.assertEqual(first, later)

    def test_response_order_affects_discounted_utility(self):
        low_first = score_sequence([0, 1, 2], [1, 5, 10], expected_k=3)
        high_first = score_sequence([0, 1, 2], [10, 5, 1], expected_k=3)
        self.assertGreater(high_first.utility, low_first.utility)

    def test_class_label_relabeling_does_not_change_scores(self):
        canonical = score_sequence([0, 0, 1], [10, None, 5], expected_k=3)
        relabeled = score_sequence((17, 17, 4), (10, None, 5), expected_k=3)
        self.assertEqual(canonical, relabeled)

    def test_default_contract_requires_ten_generations(self):
        with self.assertRaises(ValidationError):
            score_sequence([0, 0, 1], [10, None, 5])
        self.assertEqual(score_sequence(list(range(10)), [10] * 10).distinct, 10)

    def test_result_is_frozen(self):
        result = score_sequence([0, 0, 1], [10, None, 5], expected_k=3)
        with self.assertRaises((AttributeError, FrozenInstanceError)):
            result.utility = 100

    def test_invalid_lengths_and_expected_counts_fail(self):
        cases = [
            ([], [], 0),
            ([], [], 3),
            ([0, 0, 1], [10, None], 3),
            ([0, 0], [10, None, 5], 3),
            ([0, 0, 1], [10, None, 5], True),
            ([0, 0, 1], [10, None, 5], 3.0),
            ([0, 0, 1], [10, None, 5], -3),
        ]
        for partition, scores, count in cases:
            with self.subTest(partition=partition, scores=scores, count=count):
                with self.assertRaises(ValidationError):
                    score_sequence(partition, scores, expected_k=count)

    def test_invalid_partition_labels_fail(self):
        for bad in [-1, True, 0.0, "0", None]:
            with self.subTest(label=bad):
                with self.assertRaises(ValidationError):
                    score_sequence([bad, 0, 1], [10, 7, 5], expected_k=3)

    def test_invalid_quality_including_duplicate_scores_fails(self):
        for bad in [0, 11, True, 5.0, "5", math.nan, math.inf]:
            for index in [0, 1, 2]:
                scores = [10, None, 5]
                scores[index] = bad
                with self.subTest(score=bad, index=index):
                    with self.assertRaises(ValidationError):
                        score_sequence([0, 0, 1], scores, expected_k=3)
        for scores in [[None, None, 5], [10, None, None]]:
            with self.subTest(missing_head=scores):
                with self.assertRaises(ValidationError):
                    score_sequence([0, 0, 1], scores, expected_k=3)

    def test_invalid_patience_fails(self):
        for bad in [-0.1, 1.1, math.nan, math.inf, -math.inf, True, "0.8"]:
            with self.subTest(patience=bad):
                with self.assertRaises(ValidationError):
                    score_sequence([0, 0, 1], [10, None, 5], patience=bad, expected_k=3)


class ProtocolTests(unittest.TestCase):
    def test_fingerprint_is_stable_lowercase_sha256(self):
        first = protocol()
        second = protocol()
        self.assertRegex(first.fingerprint(), r"^[0-9a-f]{64}$")
        self.assertEqual(first.fingerprint(), second.fingerprint())

    def test_every_protocol_field_changes_fingerprint(self):
        original = protocol()
        alternatives = {
            "upstream_commit": "b" * 40,
            "dataset_sha256": sha256("another dataset"),
            "split_sha256": sha256("another split"),
            "partition_model": "another-partition-model",
            "quality_model": "another-quality-model",
            "partition_prompt_sha256": sha256("another partition prompt"),
            "quality_prompt_sha256": sha256("another quality prompt"),
            "generation_config_sha256": sha256("another generation configuration"),
            "fallback_policy_sha256": sha256("another fallback policy"),
            "ordering_seed": 8,
            "k": 10,
            "patience": 0.7,
        }
        for field, value in alternatives.items():
            with self.subTest(field=field):
                self.assertNotEqual(
                    original.fingerprint(), replace(original, **{field: value}).fingerprint()
                )

    def test_protocol_is_frozen_and_validation_error_is_typed(self):
        self.assertTrue(issubclass(ValidationError, ValueError))
        selected = protocol()
        with self.assertRaises((AttributeError, FrozenInstanceError)):
            selected.ordering_seed = 99

    def test_upstream_null_ordering_seed_is_supported_and_fingerprinted(self):
        unshuffled = protocol(ordering_seed=None)
        self.assertIsNone(unshuffled.ordering_seed)
        self.assertNotEqual(unshuffled.fingerprint(), protocol().fingerprint())

    def test_invalid_protocol_identity_and_models_fail(self):
        cases = {
            "upstream_commit": ["", "a" * 39, "z" * 40, None],
            "metric_version": ["", "1.0", "2.0", "v1.1", None],
            "partition_model": ["", " \t", None, 7],
            "quality_model": ["", " \n", None, 7],
        }
        hash_fields = [
            "dataset_sha256",
            "split_sha256",
            "partition_prompt_sha256",
            "quality_prompt_sha256",
            "generation_config_sha256",
            "fallback_policy_sha256",
        ]
        for field in hash_fields:
            cases[field] = ["", "a" * 63, "z" * 64, None, 7]
        for field, invalid_values in cases.items():
            for bad in invalid_values:
                with self.subTest(field=field, value=bad):
                    with self.assertRaises(ValidationError):
                        protocol(**{field: bad})

    def test_invalid_protocol_numeric_configuration_fails(self):
        cases = {
            "ordering_seed": [-1, True, 1.0, "1"],
            "k": [0, -1, True, 3.0, "3"],
            "patience": [-0.1, 1.1, math.nan, math.inf, True, "0.8"],
        }
        for field, invalid_values in cases.items():
            for bad in invalid_values:
                with self.subTest(field=field, value=bad):
                    with self.assertRaises(ValidationError):
                        protocol(**{field: bad})


class RunSummaryTests(unittest.TestCase):
    def setUp(self):
        self.protocol = protocol()
        self.row = evidence_row(self.protocol)
        self.expected = {self.row["id"]: sha256(self.row["prompt"])}

    def summarize(self, rows=None, expected=None):
        return summarize_run(
            self.expected if expected is None else expected,
            [self.row] if rows is None else rows,
            protocol=self.protocol,
        )

    def test_complete_evidence_produces_frozen_summary(self):
        summary = self.summarize()
        self.assertEqual(summary.expected_count, 1)
        self.assertEqual(summary.scored_count, 1)
        self.assertEqual(summary.mean_distinct, 2)
        self.assertAlmostEqual(summary.mean_utility, 330 / 61, places=12)
        self.assertEqual(summary.protocol_fingerprint, self.protocol.fingerprint())
        with self.assertRaises((AttributeError, FrozenInstanceError)):
            summary.scored_count = 0

    def test_summary_averages_prompts_not_response_classes(self):
        second = evidence_row(
            self.protocol,
            id="prompt-2",
            prompt="A second prompt.",
            partition=[0, 1, 2],
            generation_scores=[10, 10, 10],
            utility=10,
            distinct=3,
        )
        expected = self.expected | {second["id"]: sha256(second["prompt"])}
        summary = self.summarize(rows=[second, self.row], expected=expected)
        self.assertEqual(summary.expected_count, 2)
        self.assertEqual(summary.scored_count, 2)
        self.assertEqual(summary.mean_distinct, 2.5)
        self.assertAlmostEqual(summary.mean_utility, (330 / 61 + 10) / 2)

    def test_missing_duplicate_and_unexpected_ids_fail(self):
        cases = [
            [],
            [self.row, dict(self.row)],
            [self.row | {"id": "unexpected"}],
            [self.row | {"id": ""}],
            [self.row | {"id": 1}],
        ]
        for rows in cases:
            with self.subTest(rows=rows):
                with self.assertRaises(ValidationError):
                    self.summarize(rows=rows)

    def test_empty_or_invalid_expected_prompt_manifest_fails(self):
        for expected in [{}, {"": sha256("x")}, {1: sha256("x")}, {"x": "bad"}]:
            with self.subTest(expected=expected):
                with self.assertRaises(ValidationError):
                    self.summarize(expected=expected)

    def test_exact_utf8_prompt_hash_is_required(self):
        unicode_prompt = "A caf\u00e9 in \u96e8."
        row = self.row | {"prompt": unicode_prompt}
        expected = {row["id"]: sha256(unicode_prompt)}
        self.assertEqual(self.summarize(rows=[row], expected=expected).scored_count, 1)
        with self.assertRaises(ValidationError):
            self.summarize(rows=[row | {"prompt": unicode_prompt + " "}], expected=expected)

    def test_unencodable_prompt_fails_with_typed_error(self):
        with self.assertRaises(ValidationError):
            self.summarize(rows=[self.row | {"prompt": "\ud800"}])

    def test_malformed_run_containers_and_protocol_fail_with_typed_error(self):
        for expected, rows, selected_protocol in [
            ([], [self.row], self.protocol),
            (self.expected, None, self.protocol),
            (self.expected, [None], self.protocol),
            (self.expected, [self.row], None),
        ]:
            with self.subTest(expected=expected, rows=rows, protocol=selected_protocol):
                with self.assertRaises(ValidationError):
                    summarize_run(expected, rows, protocol=selected_protocol)

    def test_unresolved_unscored_rows_and_missing_utility_cannot_be_dropped(self):
        for changes in [
            {"unscored": "judge_refusal"},
            {"unscored": "provider_failure"},
            {"utility": None},
            {"utility": math.nan},
            {"utility": math.inf},
            {"utility": True},
        ]:
            with self.subTest(changes=changes):
                with self.assertRaises(ValidationError):
                    self.summarize(rows=[self.row | changes])

    def test_wrong_protocol_and_forged_derived_scores_fail(self):
        for changes in [
            {"protocol_fingerprint": "f" * 64},
            {"utility": self.row["utility"] + 0.001},
            {"utility": "5.4"},
            {"distinct": 3},
            {"distinct": 2.0},
            {"distinct": True},
        ]:
            with self.subTest(changes=changes):
                with self.assertRaises(ValidationError):
                    self.summarize(rows=[self.row | changes])

    def test_tiny_derived_utility_rounding_error_is_accepted(self):
        rounded = self.row | {"utility": self.row["utility"] + 1e-10}
        summary = self.summarize(rows=[rounded])
        self.assertAlmostEqual(summary.mean_utility, 330 / 61, places=12)

    def test_empty_generated_text_is_preserved_as_evidence(self):
        row = self.row | {"generations": ["", "", ""]}
        summary = self.summarize(rows=[row])
        self.assertEqual(summary.expected_count, 1)
        self.assertEqual(summary.scored_count, 1)

    def test_missing_fields_and_malformed_evidence_fail(self):
        for field in self.row:
            broken = dict(self.row)
            del broken[field]
            with self.subTest(missing_field=field):
                with self.assertRaises(ValidationError):
                    self.summarize(rows=[broken])
        for changes in [
            {"prompt": None},
            {"generations": "three responses"},
            {"generations": ["one", "two"]},
            {"generations": ["one", None, "three"]},
            {"partition": [0, 0]},
            {"partition": [0, True, 1]},
            {"partition": [0, -1, 1]},
            {"generation_scores": [10, None]},
            {"generation_scores": [None, None, 5]},
            {"generation_scores": [10, 11, 5]},
        ]:
            with self.subTest(changes=changes):
                with self.assertRaises(ValidationError):
                    self.summarize(rows=[self.row | changes])


if __name__ == "__main__":
    unittest.main()
