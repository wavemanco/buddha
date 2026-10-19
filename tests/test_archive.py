"""Exploratory archive selection checks; no capability or significance claims."""

import random
import unittest
from collections import Counter
from dataclasses import FrozenInstanceError

from buddha.archive import Candidate, active_pool, frontier, select_parent
from buddha.evaluation import ValidationError


def candidate(index, utility, distinct, parent=None):
    return Candidate(
        f"{index:064x}", None if parent is None else f"{parent:064x}", utility, distinct
    )


class CandidateTests(unittest.TestCase):
    def test_frozen_scalar_record(self):
        item = candidate(1, 0, 10)
        self.assertEqual(item.mean_utility, 0)
        with self.assertRaises(FrozenInstanceError):
            item.mean_utility = 3

    def test_invalid_ids_and_metric_boundaries(self):
        for field, values in {
            "candidate_id": ["a" * 63, "A" * 64, "z" * 64, None, True],
            "parent_id": ["x" * 64, "A" * 64, 123, False],
            "mean_utility": [True, False, -0.1, 10.1, float("nan"), float("inf"), "2", 10**999],
            "mean_distinct": [True, 0.9, 10.1, float("nan"), -float("inf"), None],
        }.items():
            for value in values:
                with self.subTest(field=field, value=value), self.assertRaises(ValidationError):
                    Candidate(
                        **(
                            {
                                "candidate_id": "a" * 64,
                                "parent_id": None,
                                "mean_utility": 5,
                                "mean_distinct": 5,
                            }
                            | {field: value}
                        )
                    )


class FrontierTests(unittest.TestCase):
    def test_pareto_requires_weak_both_and_strict_one_objective(self):
        items = [
            candidate(8, 5, 5),
            candidate(7, 5, 4),
            candidate(6, 4, 5),
            candidate(5, 6, 3),
            candidate(4, 3, 6),
            candidate(3, 5, 5),
        ]
        self.assertEqual(
            [item.candidate_id for item in frontier(items)],
            [f"{index:064x}" for index in (3, 4, 5, 8)],
        )

    def test_empty_and_order_independent(self):
        self.assertEqual(frontier([]), ())
        items = [candidate(i, i, 11 - i) for i in range(1, 11)]
        self.assertEqual(frontier(items), frontier(list(reversed(items))))

    def test_duplicate_ids_rejected_by_all_public_selectors(self):
        items = [candidate(1, 5, 5), candidate(1, 6, 6)]
        for invoke in (
            lambda: frontier(items),
            lambda: active_pool(items, max_active=5),
            lambda: select_parent(items, method="latest", max_active=5, seed=1, iteration=0),
        ):
            with self.assertRaises(ValidationError):
                invoke()

    def test_non_candidate_records_and_non_sequences_rejected(self):
        for items in ([{"mean_utility": 5}], [None], "anything", iter([])):
            with self.subTest(items=items), self.assertRaises(ValidationError):
                frontier(items)


class ActivePoolTests(unittest.TestCase):
    def test_crowding_preserves_both_objective_extremes_and_caps_pool(self):
        items = [candidate(i, i, 11 - i) for i in range(1, 11)]
        selected = active_pool(items, max_active=4)
        self.assertEqual(len(selected), 4)
        self.assertIn(items[0], selected)
        self.assertIn(items[-1], selected)
        self.assertEqual(selected, active_pool(list(reversed(items)), max_active=4))

    def test_crowding_zero_ranges_duplicate_points_deterministic(self):
        items = [candidate(i, 4, 5) for i in range(1, 11)]
        self.assertEqual(active_pool(items, max_active=2), tuple(items[:2]))

    def test_duplicate_extremes_cannot_crowd_out_one_objective(self):
        items = [
            candidate(1, 10, 1),
            candidate(2, 10, 1),
            candidate(3, 1, 10),
            candidate(4, 1, 10),
            candidate(5, 5, 5),
        ]
        self.assertEqual(active_pool(items, max_active=2), (items[0], items[2]))

    def test_neighbor_crowding_normalizes_each_objective_range(self):
        points = [(0, 10), (1, 9), (4, 8), (8, 2), (10, 1)]
        for scale in (1, 0.1):
            items = [
                candidate(i, utility * scale, distinct)
                for i, (utility, distinct) in enumerate(points, start=1)
            ]
            self.assertEqual(active_pool(items, max_active=3), (items[0], items[2], items[4]))

    def test_exploration_reserve_is_bounded_and_prefers_fewer_children(self):
        # Index 1 dominates all others; 2 has two children and 3 has none.
        items = [
            candidate(1, 10, 10),
            candidate(2, 8, 8, 1),
            candidate(3, 6, 6, 1),
            candidate(4, 5, 5, 2),
            candidate(5, 4, 4, 2),
        ]
        self.assertEqual(active_pool(items, max_active=5), (items[0], items[2]))
        self.assertEqual(active_pool(items, max_active=4), (items[0],))

    def test_reserve_ties_rank_utility_then_distinct_then_id(self):
        items = [
            candidate(1, 10, 10),
            candidate(5, 7, 4),
            candidate(4, 7, 5),
            candidate(3, 7, 5),
            candidate(2, 6, 9),
        ]
        self.assertEqual(active_pool(items, max_active=5), (items[0], items[3]))

    def test_frontier_not_ejected_when_it_fits_beside_reserve(self):
        items = [
            candidate(1, 8, 10),
            candidate(2, 10, 8),
            candidate(3, 7, 7),
            candidate(4, 6, 6),
            candidate(5, 5, 5),
        ]
        self.assertEqual(active_pool(items, max_active=5), tuple(items[:3]))

    def test_missing_parent_is_permitted_in_archive_subsets(self):
        self.assertEqual(frontier([candidate(2, 5, 5, 1)]), (candidate(2, 5, 5, 1),))

    def test_active_capacity_validated(self):
        for capacity in (True, 0, 1, 65, 2.0, None):
            with self.subTest(capacity=capacity), self.assertRaises(ValidationError):
                active_pool([], max_active=capacity)
        self.assertEqual(active_pool([], max_active=64), ())


class ParentSelectionTests(unittest.TestCase):
    def test_resume_same_iteration_same_parent_without_global_rng_effects(self):
        items = [candidate(i, i, 11 - i) for i in range(1, 11)]
        before = random.getstate()
        uninterrupted = [
            select_parent(items, method="archive", max_active=5, seed=12, iteration=i)
            for i in range(20)
        ]
        resumed = [
            select_parent(items, method="archive", max_active=5, seed=12, iteration=i)
            for i in range(8, 20)
        ]
        self.assertEqual(uninterrupted[8:], resumed)
        self.assertEqual(before, random.getstate())

    def test_latest_and_uninformed_follow_history_and_ignore_scores(self):
        items = [candidate(8, 5, 5), candidate(2, 10, 10), candidate(4, 1, 1)]
        self.assertEqual(
            select_parent(items, method="latest", max_active=2, seed=0, iteration=9), items[-1]
        )
        self.assertEqual(
            select_parent(items, method="uninformed", max_active=2, seed=0, iteration=9), items[0]
        )

    def test_archive_inverse_child_count_weighting_and_exploration(self):
        # Equal frontier rank; 1 has four children. All children are dominated.
        items = [candidate(1, 10, 5), candidate(2, 5, 10)]
        items += [candidate(i, 1, 1, 1) for i in range(3, 7)]
        counts = Counter(
            select_parent(items, method="archive", max_active=5, seed=4, iteration=i).candidate_id
            for i in range(1000)
        )
        self.assertGreater(counts[items[1].candidate_id], 2 * counts[items[0].candidate_id])
        self.assertGreater(counts[items[2].candidate_id], 0)
        self.assertEqual(
            set(counts), {item.candidate_id for item in active_pool(items, max_active=5)}
        )

    def test_frontier_rank_has_more_selection_weight_than_equal_child_count_reserve(self):
        items = [candidate(1, 10, 10), candidate(2, 5, 5)]
        counts = Counter(
            select_parent(items, method="archive", max_active=5, seed=4, iteration=i).candidate_id
            for i in range(1000)
        )
        # Mixture probability is 0.1/2 + 0.9*(2/3) = 0.65 for the frontier.
        self.assertGreater(counts[items[0].candidate_id], 600)
        self.assertLess(counts[items[0].candidate_id], 700)

    def test_no_eligible_parent_or_unsupported_method(self):
        with self.assertRaises(ValidationError):
            select_parent([], method="archive", max_active=2, seed=0, iteration=0)
        for method in ("random", "", None, True):
            with self.subTest(method=method), self.assertRaises(ValidationError):
                select_parent(
                    [candidate(1, 5, 5)], method=method, max_active=2, seed=0, iteration=0
                )

    def test_selection_integer_controls_are_strict(self):
        for field, values in {
            "seed": [True, 1.0, -1],
            "iteration": [False, -1, 2.0],
            "max_active": [True, 1, 65],
        }.items():
            for value in values:
                args = {"method": "archive", "max_active": 2, "seed": 0, "iteration": 0}
                args[field] = value
                with self.subTest(field=field, value=value), self.assertRaises(ValidationError):
                    select_parent([candidate(1, 5, 5)], **args)


if __name__ == "__main__":
    unittest.main()
