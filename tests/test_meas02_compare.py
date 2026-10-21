"""Saved class relations are diagnostics, never a corrected novelty score."""

import copy
import json
import unittest
from pathlib import Path
from unittest.mock import patch

from test_meas01_pack import readonly, sha

HELPER = Path(__file__).resolve().parents[1] / "docs/conformance/meas02-compare.py"
namespace = {"__name__": "meas02_compare_test", "__file__": str(HELPER)}
exec(compile(HELPER.read_bytes(), str(HELPER), "exec"), namespace)  # nosec B102: reviewed engineering source, never pyc.
compare_resolved = namespace["compare_resolved"]


class MeasurementComparisonTests(unittest.TestCase):
    def setUp(self):
        self.text = {
            "A:0": "same premise Ω",
            "A:1": "other wording",
            "A:2": "new outcome",
            "B:0": "another policy",
            "B:1": "different again",
        }
        self.scope_a = {"run_id": "run-a", "candidate_id": "candidate-a", "prompt_id": "prompt"}
        self.scope_b = self.scope_a | {"candidate_id": "candidate-b"}
        self.provenance = []
        self.cases = []
        self.add("A-full", "historical_set", ["A:0", "A:1", "A:2"], [[0, 1], [2]])
        self.add("A-card", "historical_comparison", ["A:0", "A:1"], [[0, 1]])
        self.add("B-full", "historical_set", ["B:0", "B:1"], [[0, 1]], status="uncertain")
        self.add("cross", "historical_comparison", ["A:2", "B:0"], [[0, 1]])
        self.add(
            "authored", "authored_control", ["authored:control:0", "authored:control:1"], [[0], [1]]
        )
        self.expectations = {
            "format": "buddha.meas01-expectations.v1",
            "cases": self.cases,
            "unresolved_item_ids": ["B-full"],
        }
        self.rows = [
            self.row(self.scope_a, ["A:0", "A:1", "A:2"], [7, 7, 91]),
            self.row(self.scope_b, ["B:0", "B:1"], [0, 1]),
        ]

    def source(self, reference):
        if reference.startswith("authored:"):
            index = int(reference.rsplit(":", 1)[1])
            text = str(index)
            return {
                "control_id": "control",
                "original_index_0based": index,
                "answer_utf8_sha256": sha(text.encode()),
            }, text
        scope = self.scope_a if reference.startswith("A:") else self.scope_b
        return scope | {
            "reference_id": reference,
            "original_index_0based": int(reference[-1]),
            "answer_utf8_sha256": sha(self.text[reference].encode()),
        }, self.text[reference]

    def add(self, identity, kind, references, groups, *, status="resolved"):
        answer_ids = [f"{identity}-{index}" for index in range(len(references))]
        sources = {
            answer: self.source(ref)[0] for answer, ref in zip(answer_ids, references, strict=True)
        }
        self.provenance.append(
            {
                "item_id": identity,
                "kind": kind,
                "status": status,
                "answer_sources": sources,
                "groups": [[references[index] for index in group] for group in groups],
                "uncertain_pairs": [],
            }
        )
        if status == "resolved":
            self.cases.append(
                {
                    "item": {
                        "id": identity,
                        "prompt": "The original task.",
                        "answers": [
                            {"id": answer, "text": self.source(ref)[1]}
                            for answer, ref in zip(answer_ids, references, strict=True)
                        ],
                    },
                    "assessment": {
                        "id": identity,
                        "groups": [[answer_ids[index] for index in group] for group in groups],
                        "uncertain_pairs": [],
                    },
                    "adjudication": {"item_id": identity, "status": status},
                }
            )

    def row(self, scope, references, labels):
        return scope | {
            "prompt_sha256": sha(b"The original task."),
            "reference_ids": references,
            "answer_sha256": [sha(self.text[ref].encode()) for ref in references],
            "partition": labels,
            "unused_audit_metadata": "not a class label",
        }

    def compare(self):
        with readonly():
            return compare_resolved(self.expectations, self.provenance, self.rows)

    def item(self, result, identity):
        return next(item for item in result["items"] if item["item_id"] == identity)

    def test_equivalence_relations_ignore_arbitrary_class_label_numbers(self):
        result = self.compare()
        self.assertEqual(result["format"], "buddha.meas02-relation-comparison.v1")
        full = self.item(result, "A-full")
        self.assertEqual(full["status"], "compared")
        self.assertEqual([pair["outcome"] for pair in full["pairs"]], ["agree"] * 3)
        self.assertEqual(full["pairs"][0]["references"], ["A:0", "A:1"])
        self.assertEqual(full["pairs"][0]["expected"], "equivalent")
        self.rows[0]["partition"] = [900, 900, 4]
        self.assertEqual(self.compare(), result)

    def test_true_mismatch_branch_preserves_expected_and_saved_relation(self):
        self.rows[0]["partition"] = [7, 8, 91]
        result = self.compare()
        pair = self.item(result, "A-full")["pairs"][0]
        self.assertEqual(
            (pair["expected"], pair["saved"], pair["outcome"]),
            ("equivalent", "distinct", "disagree"),
        )
        self.assertEqual(result["counts"]["unique_disagreeing_pairs"], 1)
        self.assertEqual(result["counts"]["unique_agreeing_pairs"], 2)

    def test_duplicate_pair_appearances_are_separate_from_unique_candidate_pairs(self):
        result = self.compare()
        self.assertFalse(self.item(result, "A-full")["pairs"][0]["duplicate_appearance"])
        self.assertTrue(self.item(result, "A-card")["pairs"][0]["duplicate_appearance"])
        self.assertEqual(result["counts"]["unique_candidate_pairs"], 3)
        self.assertEqual(result["counts"]["duplicate_pair_appearances"], 1)
        self.assertEqual(result["counts"]["compared_pair_appearances"], 4)
        pair = next(pair for pair in result["unique_pairs"] if pair["references"] == ["A:0", "A:1"])
        self.assertEqual(pair["appearance_count"], 2)

    def test_conflicting_case_expectations_remain_explicit_without_consensus(self):
        self.cases[1]["assessment"]["groups"] = [["A-card-0"], ["A-card-1"]]
        self.provenance[1]["groups"] = [["A:0"], ["A:1"]]
        result = self.compare()
        pair = next(pair for pair in result["unique_pairs"] if pair["references"] == ["A:0", "A:1"])
        self.assertTrue(pair["conflicting_expectations"])
        self.assertCountEqual(pair["expected_relations"], ["distinct", "equivalent"])
        self.assertEqual(pair["outcome"], "conflicting_expectations")
        self.assertEqual(result["counts"]["unique_conflicting_pairs"], 1)
        self.assertEqual(result["counts"]["unique_agreeing_pairs"], 2)
        self.assertEqual(result["counts"]["unique_disagreeing_pairs"], 0)
        self.assertEqual(self.item(result, "A-card")["pairs"][0]["outcome"], "disagree")

    def test_cross_scope_authored_and_missing_saved_measurements_stay_unmeasured(self):
        self.rows = self.rows[1:]
        result = self.compare()
        for identity, reason in (
            ("A-full", "not_measured_missing_saved_judgment"),
            ("cross", "not_measured_cross_scope"),
            ("authored", "not_measured_no_saved_judgment"),
        ):
            item = self.item(result, identity)
            self.assertEqual(item["status"], reason)
            self.assertTrue(item["source_references"])
            self.assertTrue(
                all(pair["saved"] is None and pair["outcome"] == reason for pair in item["pairs"])
            )
        self.assertEqual(result["counts"]["compared_pair_appearances"], 0)
        self.assertEqual(result["counts"]["unique_unmeasured_pairs"], 3)

    def test_uncertain_items_supply_only_identity_coverage_never_tentative_groups(self):
        self.provenance[2]["groups"] = "not a usable settled partition"
        result = self.compare()
        self.assertEqual(result["unresolved_item_ids"], ["B-full"])
        self.assertNotIn("B-full", [item["item_id"] for item in result["items"]])
        self.assertEqual(result["counts"]["unique_candidate_pairs"], 3)
        self.provenance[0]["status"] = "uncertain"
        with self.assertRaises(ValueError):
            self.compare()

    def test_partial_reordered_and_foreign_saved_populations_are_rejected(self):
        original = copy.deepcopy(self.rows)
        for field, replacement in (
            ("reference_ids", ["A:0", "A:1"]),
            ("answer_sha256", original[0]["answer_sha256"][:2]),
            ("partition", [0, 0]),
            ("reference_ids", ["A:1", "A:0", "A:2"]),
            ("candidate_id", "foreign"),
            ("prompt_sha256", "0" * 64),
        ):
            self.rows = copy.deepcopy(original)
            self.rows[0][field] = replacement
            with self.subTest(field=field, replacement=replacement), self.assertRaises(ValueError):
                self.compare()
        self.rows = original + [copy.deepcopy(original[0])]
        with self.assertRaises(ValueError):
            self.compare()

    def test_changed_text_source_hash_index_or_identity_binding_is_rejected(self):
        original_expectations = copy.deepcopy(self.expectations)
        original_provenance = copy.deepcopy(self.provenance)
        self.cases[0]["item"]["answers"][0]["text"] = "Changed literal text"
        with self.assertRaises(ValueError):
            self.compare()

        self.expectations = original_expectations
        for field, bad in (
            ("answer_utf8_sha256", "0" * 64),
            ("original_index_0based", True),
            ("original_index_0based", 1),
            ("reference_id", "foreign"),
            ("candidate_id", "foreign"),
        ):
            self.provenance = copy.deepcopy(original_provenance)
            self.provenance[1]["answer_sources"]["A-card-0"][field] = bad
            with self.subTest(field=field, bad=bad), self.assertRaises(ValueError):
                self.compare()
        self.provenance = original_provenance
        self.rows[0]["answer_sha256"][0] = "0" * 64
        with self.assertRaises(ValueError):
            self.compare()

    def test_selected_historical_prompt_is_bound_to_saved_prompt_bytes(self):
        for index in (0, 2):
            original = self.cases[index]["item"]["prompt"]
            self.cases[index]["item"]["prompt"] = "A different task with unchanged answer strings."
            with self.subTest(item=self.cases[index]["item"]["id"]), self.assertRaises(ValueError):
                self.compare()
            self.cases[index]["item"]["prompt"] = original

    def test_duplicate_unknown_or_missing_item_and_answer_ids_are_rejected(self):
        original = copy.deepcopy(self.expectations)
        for mutate in (
            lambda v: v["cases"].append(copy.deepcopy(v["cases"][0])),
            lambda v: v["cases"].pop(),
            lambda v: v["cases"][0]["item"].update(id="unknown"),
            lambda v: v["cases"][0]["item"]["answers"][1].update(id="A-full-0"),
            lambda v: v["unresolved_item_ids"].append("B-full"),
            lambda v: v["unresolved_item_ids"].append("unknown"),
        ):
            self.expectations = copy.deepcopy(original)
            mutate(self.expectations)
            with self.subTest(mutate=mutate), self.assertRaises(ValueError):
                self.compare()
        self.expectations = original
        self.provenance.append(copy.deepcopy(self.provenance[0]))
        with self.assertRaises(ValueError):
            self.compare()

    def test_labels_are_nonnegative_integers_not_booleans_or_contiguous_class_numbers(self):
        for bad in (True, -1, 1.0, "0", None):
            self.rows[0]["partition"] = [bad, 7, 91]
            with self.subTest(bad=bad), self.assertRaises(ValueError):
                self.compare()

    def test_comparison_is_pure_and_defensive_without_io_or_scientific_score_fields(self):
        before = copy.deepcopy((self.expectations, self.provenance, self.rows))

        def forbidden(*args, **kwargs):
            raise AssertionError("pure comparison accessed a file")

        with (
            patch("pathlib.Path.open", side_effect=forbidden),
            patch("builtins.open", side_effect=forbidden),
        ):
            result = self.compare()
        self.assertEqual((self.expectations, self.provenance, self.rows), before)
        result["items"][0]["pairs"][0]["references"].clear()
        result["unresolved_item_ids"].clear()
        again = self.compare()
        self.assertTrue(again["limits"])
        self.assertEqual(again["unresolved_item_ids"], ["B-full"])
        for key in ("utility", "distinctiveness", "ranking", "accuracy"):
            self.assertNotIn(key, again)

    def test_published_saved_measurements_reproduce_source_bound_diagnostic(self):
        root = Path(__file__).resolve().parents[1]
        publication = json.loads(
            (root / "docs/conformance/meas02-relation-comparison.json").read_bytes()
        )
        expected_inputs = {
            "tests/fixtures/meas01-expectations.json",
            "docs/conformance/meas01-adjudication-review.json",
            "docs/conformance/meas02-official-replay.json",
            "docs/conformance/meas02-official-replay.py",
            "docs/conformance/meas02-compare.py",
        }
        self.assertEqual(set(publication["input_sha256"]), expected_inputs)
        inputs = {}
        for name, expected in publication["input_sha256"].items():
            raw = (root / name).read_bytes()
            self.assertEqual(sha(raw), expected, name)
            if name.endswith(".json"):
                inputs[name] = json.loads(raw)
        expectations = inputs["tests/fixtures/meas01-expectations.json"]
        provenance = inputs["docs/conformance/meas01-adjudication-review.json"][
            "adjudicator_stated_results"
        ]
        replay = inputs["docs/conformance/meas02-official-replay.json"]
        self.assertEqual(
            sha((root / "docs/conformance/meas02-official-replay.py").read_bytes()),
            replay["probe_sha256"],
        )
        rows = replay["rows"]
        with readonly():
            result = compare_resolved(expectations, provenance, rows)
        self.assertEqual(result, publication["comparison"])
        counts = result["counts"]
        self.assertEqual(
            (
                counts["pair_appearances"],
                counts["compared_pair_appearances"],
                counts["unique_candidate_pairs"],
                counts["duplicate_pair_appearances"],
            ),
            (115, 97, 95, 2),
        )
        self.assertEqual(
            (counts["unique_agreeing_pairs"], counts["unique_disagreeing_pairs"]), (95, 0)
        )
        self.assertTrue(
            all(pair["expected_relations"] == ["distinct"] for pair in result["unique_pairs"])
        )
        self.assertEqual(len(result["unresolved_item_ids"]), 5)
        self.assertTrue(
            any("equivalence sensitivity" in limit for limit in publication["selection_limits"])
        )
        self.assertNotIn("accuracy", result)


if __name__ == "__main__":
    unittest.main()
