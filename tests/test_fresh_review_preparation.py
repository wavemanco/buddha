"""Supplied review metadata only; do not open frozen review or trial inputs."""

import copy
import importlib.util
import unittest
from pathlib import Path

SCRIPT = Path(__file__).resolve().parents[1] / "docs/conformance/prepare-fresh-review.py"
spec = importlib.util.spec_from_file_location("supplied_review_builder", SCRIPT)
builder = importlib.util.module_from_spec(spec)
spec.loader.exec_module(builder)


def require(value, code):
    if not value:
        raise ValueError(code)


class FreshReviewPreparationTests(unittest.TestCase):
    def fixture(self):
        return {
            "format": "buddha.source-review-plan.v1",
            "kind": "improver",
            "experiment_id": "supplied-original",
            "tasks_sha256": "a" * 64,
            "seed": 7,
            "protocol": {"path": "supplied-old-protocol", "sha256": "b" * 64},
            "materials": {"path": "supplied-old-materials", "sha256": "c" * 64},
            "sets": [
                {"role": role, "role_index": index, "task_id": str(index), "repetition": 0}
                for index in range(4)
                for role in ("starter", "initial", "evolved")
            ],
        }

    def population(self):
        return {
            "tasks": [
                {"task_id": str(index), "family_id": "family-" + str(index), "count": 10}
                for index in range(26)
            ]
        }

    def test_plan_rebinds_only_experiment_and_references_with_detached_sets(self):
        original = self.fixture()
        before = copy.deepcopy(original)
        protocol = {"path": "supplied-new-protocol", "sha256": "b" * 64}
        materials = {"path": "supplied-new-materials", "sha256": "c" * 64}
        result = builder.rebound_plan(
            original, "supplied-fresh", "a" * 64, protocol, materials, require
        )
        self.assertEqual(
            result,
            original
            | {"experiment_id": "supplied-fresh", "protocol": protocol, "materials": materials},
        )
        result["sets"][0]["role_index"] = 17
        self.assertEqual(original, before)
        for name, value in (("seed", 8), ("kind", "final"), ("tasks_sha256", "d" * 64)):
            with self.subTest(name=name), self.assertRaisesRegex(ValueError, "science_changed"):
                builder.rebound_plan(
                    original | {name: value}, "fresh", "a" * 64, protocol, materials, require
                )

    def test_exact_whole_set_policy_and_same_family_refusal(self):
        plan, population = self.fixture(), self.population()
        self.assertEqual(
            builder.sample_scope(plan, population, require),
            {
                "whole_sets": 12,
                "full_answer_positions": 120,
                "tasks": 4,
                "families": 4,
                "conditions": 4,
            },
        )
        population["tasks"][1]["family_id"] = population["tasks"][0]["family_id"]
        with self.assertRaisesRegex(ValueError, "sample_changed"):
            builder.sample_scope(plan, population, require)
        population = self.population()
        for field, value in (
            ("role_index", 4),
            ("repetition", 1),
            ("task_id", "missing"),
            ("role", "foreign"),
        ):
            changed = copy.deepcopy(plan)
            changed["sets"][0][field] = value
            with self.subTest(field=field), self.assertRaisesRegex(ValueError, "sample_changed"):
                builder.sample_scope(changed, population, require)
        repeated = copy.deepcopy(plan)
        repeated["sets"][0] = copy.deepcopy(repeated["sets"][1])
        with self.assertRaisesRegex(ValueError, "role_repeated"):
            builder.sample_scope(repeated, population, require)

    def test_answer_count_and_omitted_whole_set_refuse(self):
        plan, population = self.fixture(), self.population()
        population["tasks"][0]["count"] = 9
        with self.assertRaisesRegex(ValueError, "sample_changed"):
            builder.sample_scope(plan, population, require)
        plan["sets"].pop()
        with self.assertRaisesRegex(ValueError, "sample_changed"):
            builder.sample_scope(plan, self.population(), require)

    def test_custody_extension_preserves_every_existing_field_and_refuses_replacement(self):
        original = {
            "process_id": "retained-process-not-a-new-attestation",
            "custodian": "retained",
            "population": [{"task_id": "0", "exposure": "eligible"}],
            "disclosures": [{"kept": "unchanged"}],
            "evidence": [{"path": "old-" + str(i), "sha256": str(i)} for i in range(60)],
        }
        before = copy.deepcopy(original)
        leaves = [{"path": "new-" + str(i), "sha256": str(i)} for i in range(8)]
        result = builder.extended_custody(original, leaves, require)
        self.assertEqual(len(result["evidence"]), 68)
        self.assertEqual(
            {k: v for k, v in result.items() if k != "evidence"},
            {k: v for k, v in original.items() if k != "evidence"},
        )
        result["population"][0]["exposure"] = "unknown"
        result["evidence"][-1]["path"] = "mutated-return"
        self.assertEqual(original, before)
        self.assertEqual(leaves[-1]["path"], "new-7")
        for changed in (
            leaves[:7],
            leaves[:7] + [leaves[0]],
            leaves[:7] + [original["evidence"][0]],
        ):
            with (
                self.subTest(changed=changed),
                self.assertRaisesRegex(ValueError, "evidence_changed"),
            ):
                builder.extended_custody(original, changed, require)


if __name__ == "__main__":
    unittest.main()
