"""Frozen source partitions exclude related tasks from different occasions."""

import unittest

from buddha.benchmark import Prompt
from buddha.evaluation import ValidationError
from buddha.splits import freeze_splits, validate_splits


def prompts(count=10):
    return tuple(Prompt(f"id-{index:02}", f"Task number {index}.") for index in range(count))


def membership(splits):
    return {item: split for split, items in splits.items() for item in items}


class FrozenSplitTests(unittest.TestCase):
    def test_deterministic_complete_sorted_and_input_order_independent(self):
        source = prompts()
        frozen = freeze_splits(source, seed=19)
        self.assertEqual(set(frozen), {"development", "validation", "final"})
        self.assertEqual([len(frozen[name]) for name in frozen], [6, 2, 2])
        self.assertEqual(set(membership(frozen)), {prompt.id for prompt in source})
        self.assertTrue(all(items == sorted(items) for items in frozen.values()))
        self.assertEqual(frozen, freeze_splits(source, seed=19))
        self.assertEqual(frozen, freeze_splits(tuple(reversed(source)), seed=19))
        self.assertEqual(frozen, validate_splits(source, frozen))

    def test_seed_changes_assignment(self):
        self.assertNotEqual(freeze_splits(prompts(), seed=1), freeze_splits(prompts(), seed=2))

    def test_small_group_counts_keep_every_split_nonempty(self):
        for count in range(3, 8):
            with self.subTest(count=count):
                result = freeze_splits(prompts(count), seed=0)
                self.assertTrue(all(result.values()))
                self.assertEqual(sum(map(len, result.values())), count)

    def test_normalized_duplicates_remain_together(self):
        source = (*prompts(5), Prompt("same", "  TASK\nnumber 0. \t"))
        result = membership(freeze_splits(source, seed=9))
        self.assertEqual(result["id-00"], result["same"])

    def test_declared_families_and_exact_duplicates_union_transitively(self):
        source = (*prompts(6), Prompt("same", "TASK NUMBER 0."))
        families = {prompt.id: prompt.id for prompt in source}
        families["id-01"] = families["id-00"]
        families["same"] = families["id-02"]
        frozen = freeze_splits(source, seed=10, families=families)
        assignments = membership(frozen)
        self.assertEqual(
            len({assignments[item] for item in ["id-00", "id-01", "id-02", "same"]}), 1
        )
        self.assertEqual(
            frozen,
            freeze_splits(
                tuple(reversed(source)), seed=10, families=dict(reversed(list(families.items())))
            ),
        )
        self.assertEqual(frozen, validate_splits(source, frozen, families=families))

    def test_insufficient_independent_groups_rejected(self):
        cases = [prompts(2), (Prompt("a", "same"), Prompt("b", " SAME "), Prompt("c", "other"))]
        for source in cases:
            with self.subTest(source=source), self.assertRaises(ValidationError):
                freeze_splits(source, seed=0)
        with self.assertRaises(ValidationError):
            freeze_splits(prompts(3), seed=0, families={p.id: "all" for p in prompts(3)})

    def test_invalid_seed_rejected(self):
        for seed in [True, False, -1, 1.0, "0", None, 2**63]:
            with self.subTest(seed=seed), self.assertRaises(ValidationError):
                freeze_splits(prompts(), seed=seed)

    def test_invalid_source_rejected(self):
        for source in [None, "bad", [], [object()], [prompts(1)[0], prompts(1)[0]]]:
            with self.subTest(source=source), self.assertRaises(ValidationError):
                freeze_splits(source, seed=0)
            with self.subTest(source=source), self.assertRaises(ValidationError):
                validate_splits(source, {"development": ["a"], "validation": ["b"], "final": ["c"]})

    def test_invalid_family_mapping_rejected(self):
        source = prompts(3)
        good = {prompt.id: prompt.id for prompt in source}
        cases = [
            [],
            {},
            good | {"extra": "x"},
            good | {"id-00": " "},
            good | {"id-00": 3},
            good | {"id-00": None},
        ]
        for families in cases:
            with self.subTest(families=families), self.assertRaises(ValidationError):
                freeze_splits(source, seed=0, families=families)
            with self.subTest(families=families), self.assertRaises(ValidationError):
                validate_splits(
                    source,
                    {"development": ["id-00"], "validation": ["id-01"], "final": ["id-02"]},
                    families=families,
                )

    def test_strict_partition_rejects_missing_duplicate_unknown_and_wrong_shapes(self):
        source = prompts(3)
        good = {"development": ["id-00"], "validation": ["id-01"], "final": ["id-02"]}
        cases = [
            None,
            [],
            {key: value for key, value in good.items() if key != "final"},
            good | {"extra": []},
            good | {"final": []},
            good | {"final": ["unknown"]},
            good | {"final": ["id-01"]},
            good | {"development": ["id-00", "id-00"]},
            good | {"development": "id-00"},
            good | {"development": ("id-00",)},
            good | {"development": [True]},
        ]
        for splits in cases:
            with self.subTest(splits=splits), self.assertRaises(ValidationError):
                validate_splits(source, splits)

    def test_validation_rejects_exact_duplicate_leakage(self):
        source = (*prompts(3), Prompt("same", "TASK NUMBER 0."))
        split = {"development": ["id-00"], "validation": ["id-01", "same"], "final": ["id-02"]}
        with self.assertRaises(ValidationError):
            validate_splits(source, split)

    def test_validation_rejects_declared_family_leakage(self):
        source = prompts(4)
        split = {"development": ["id-00", "id-03"], "validation": ["id-01"], "final": ["id-02"]}
        families = {prompt.id: prompt.id for prompt in source} | {"id-01": "id-00"}
        with self.assertRaises(ValidationError):
            validate_splits(source, split, families=families)

    def test_validation_sorts_and_copies_lists(self):
        source = prompts(4)
        split = {"development": ["id-03", "id-00"], "validation": ["id-01"], "final": ["id-02"]}
        original = list(split["development"])
        result = validate_splits(source, split)
        self.assertEqual(result["development"], ["id-00", "id-03"])
        self.assertEqual(split["development"], original)
        result["development"].append("unrelated")
        self.assertEqual(split["development"], original)


if __name__ == "__main__":
    unittest.main()
