"""Paired numerical contract; supplied scalars attest no original evidence."""

import copy
import hashlib
import unittest
from contextlib import ExitStack
from dataclasses import FrozenInstanceError
from fractions import Fraction
from unittest.mock import patch

from buddha.improvement_rule import ImprovementRule
from buddha.releases import _json


def digest(value):
    return hashlib.sha256(_json(value)).hexdigest()


def ratio(value):
    return {"numerator": value.numerator, "denominator": value.denominator}


class ImproverAnalysisTests(unittest.TestCase):
    def setUp(self):
        from buddha import improver_analysis

        self.module = improver_analysis
        self.Plan = improver_analysis.ImproverAnalysisPlan
        self.Error = improver_analysis.ImproverAnalysisError
        self.rule = ImprovementRule.from_bytes(
            _json(
                {
                    "format": "buddha.improvement-rule.v1",
                    "primary_metric": "utility",
                    "minimum_gain": 0,
                    "max_other_loss": 0,
                }
            )
        )

    def fixture(self, *, starts=1, repetitions=1, sealed=1):
        population = {
            "format": "buddha.improver-analysis-population.v1",
            "taskset_sha256": "a" * 64,
            "custody_sha256": "b" * 64,
            "tasks": [
                {"task_id": 1, "family_id": "f", "count": 10},
                {"task_id": "1", "family_id": "f", "count": 10},
                {"task_id": "third", "family_id": "g", "count": 10},
            ],
        }
        record = {
            "format": "buddha.improver-analysis-plan.v1",
            "method": "fixed_panel_family_hoeffding_shared_starter.v1",
            "projection_release_sha256": "c" * 64,
            "improvement_rule_sha256": self.rule.fingerprint(),
            "population_sha256": digest(population),
            "counts": {
                "starts": starts,
                "development_repetitions": repetitions,
                "m": 2,
                "tasks": 3,
                "sealed_repetitions": sealed,
            },
            "weights": "equal_conditions_then_equal_prompts",
            "alpha_total": ratio(Fraction(1, 10)),
            "tail_allocations": {
                contrast: {axis: ratio(Fraction(1, 100)) for axis in ("utility", "distinct")}
                for contrast in ("initial_gain", "evolved_gain", "improver_effect")
            },
            "analyzer_sources": self.module._source_hashes(),
        }
        slots, rows = [], []
        for start in range(starts):
            starter = hashlib.sha256(str(start).encode()).hexdigest()
            for repeat in range(repetitions):
                for arm in range(2):
                    slots.append(
                        {
                            "start": start,
                            "repetition": repeat,
                            "arm": arm,
                            "starter_agent_sha256": starter,
                            "improver_agent_sha256": str(arm + 1) * 64,
                            "status": "selected",
                            "descendant_agent_sha256": str(arm + 3) * 64,
                        }
                    )
                for role, agent, utility, distinct in (
                    ("starter", starter, 2, 3),
                    ("initial", "3" * 64, 5, 5),
                    ("evolved", "4" * 64, 7, 6),
                ):
                    for index, task in enumerate(population["tasks"]):
                        for occasion in range(sealed):
                            rows.append(
                                {
                                    "start": start,
                                    "repetition": repeat,
                                    "role": role,
                                    "task_index": index,
                                    "task_id": task["task_id"],
                                    "family_id": task["family_id"],
                                    "sealed_repetition": occasion,
                                    "agent_sha256": agent,
                                    "status": "observed",
                                    "utility": utility,
                                    "distinct": distinct,
                                }
                            )
        return record, population, slots, rows

    def call(self, fixture):
        record, population, slots, rows = fixture
        return self.module.analyze_improver_panel(
            self.Plan.from_bytes(_json(record)),
            population=population,
            slots=slots,
            rows=rows,
            rule=self.rule,
        )

    def test_shared_starter_exact_gains_and_family_weights_without_false_replication(self):
        first = self.call(self.fixture())
        repeated = self.call(self.fixture(starts=2, repetitions=2, sealed=3))
        expected = {
            "initial_gain": {"utility": 3, "distinct": 2},
            "evolved_gain": {"utility": 5, "distinct": 3},
            "improver_effect": {"utility": 2, "distinct": 1},
        }
        self.assertTrue(first["coverage"]["complete"])
        for contrast, axes in expected.items():
            for axis, point in axes.items():
                a, b = (r["contrasts"][contrast][axis] for r in (first, repeated))
                self.assertEqual(a["point"], ratio(Fraction(point)))
                self.assertEqual(a, b, "repetition is not an independent prompt family")
        self.assertEqual(
            first["family_weights"], {"f": ratio(Fraction(2, 3)), "g": ratio(Fraction(1, 3))}
        )
        self.assertEqual(first["squared_weight_sum"], ratio(Fraction(5, 9)))
        self.assertEqual(first["support_spans"], {"utility": 10, "distinct": 9})

    def test_unequal_measurements_are_averaged_within_declared_conditions_and_prompts(self):
        fixture = self.fixture(starts=2, repetitions=2, sealed=2)
        for row in fixture[3]:
            if row["role"] == "evolved":
                row["utility"] = row["start"] + 2 * row["repetition"] + row["sealed_repetition"]
        result = self.call(fixture)
        self.assertEqual(
            result["contrasts"]["evolved_gain"]["utility"]["point"], ratio(Fraction(0))
        )
        self.assertEqual(
            result["contrasts"]["improver_effect"]["utility"]["point"], ratio(Fraction(-3))
        )

    def test_unequal_task_means_use_prompt_weights_and_six_original_tail_allocations(self):
        fixture = self.fixture(starts=2, repetitions=2, sealed=2)
        values = ((3, 3, 4.5), (5, 6, 5), (4, 2, 3))
        for row in fixture[3]:
            role = ("starter", "initial", "evolved").index(row["role"])
            row["utility"] = values[row["task_index"]][role]
        index = 0
        for axes in fixture[0]["tail_allocations"].values():
            for axis in axes:
                index += 1
                axes[axis] = ratio(Fraction(index, 1000))
        result = self.call(fixture)
        for name, point in (
            ("initial_gain", Fraction(-1, 3)),
            ("evolved_gain", Fraction(1, 6)),
            ("improver_effect", Fraction(1, 2)),
        ):
            self.assertEqual(result["contrasts"][name]["utility"]["point"], ratio(point))
            for axis in ("utility", "distinct"):
                self.assertEqual(
                    result["contrasts"][name][axis]["tail"],
                    fixture[0]["tail_allocations"][name][axis],
                )

    def test_explicit_null_and_missing_measurements_preserve_all_planned_denominators(self):
        fixture = self.fixture()
        fixture[2][0].update(status="no_valid_descendant", descendant_agent_sha256=None)
        fixture[3][:] = [row for row in fixture[3] if row["role"] != "initial"]
        result = self.call(fixture)
        self.assertFalse(result["coverage"]["complete"])
        self.assertEqual(result["coverage"]["descendant_slots"], 2)
        self.assertEqual(result["coverage"]["null_slots"], 1)
        self.assertEqual(result["rule"]["status"], "inconclusive")
        self.assertIsNone(result["contrasts"]["initial_gain"]["utility"]["point"])
        self.assertEqual(
            result["contrasts"]["evolved_gain"]["utility"]["point"], ratio(Fraction(5))
        )
        self.assertEqual(result["tail_allocations"], fixture[0]["tail_allocations"])
        missing = self.fixture()
        missing[3][0].update(status="failed", utility=None, distinct=None)
        partial = self.call(missing)
        self.assertEqual(partial["rule"]["status"], "inconclusive")
        self.assertIsNone(partial["contrasts"]["evolved_gain"]["utility"]["point"])
        self.assertEqual(
            partial["contrasts"]["improver_effect"]["utility"]["point"], ratio(Fraction(2))
        )
        missing[3][0].update(status="observed", utility=None, distinct=3)
        partial = self.call(missing)
        self.assertIsNotNone(partial["contrasts"]["evolved_gain"]["distinct"]["point"])
        self.assertEqual(partial["rule"]["status"], "inconclusive")

    def test_foreign_omitted_and_malformed_coordinates_refuse_before_arithmetic(self):
        def change(fixture, case):
            if case == "omitted_task":
                fixture[3][:] = [row for row in fixture[3] if row["task_index"] != 1]
            elif case == "omitted_slot":
                fixture[2].pop()
            elif case == "duplicate":
                fixture[3].append(copy.deepcopy(fixture[3][0]))
            elif case == "duplicate_preserved":
                fixture[3][-1] = copy.deepcopy(fixture[3][0])
            elif case == "duplicate_slot":
                fixture[2][1] = copy.deepcopy(fixture[2][0])
            elif case == "typed_id":
                fixture[3][0]["task_id"] = "1"
            elif case == "family":
                fixture[3][0]["family_id"] = "foreign"
            elif case == "agent":
                fixture[3][0]["agent_sha256"] = "9" * 64
            elif case == "repeat":
                fixture[3][0]["sealed_repetition"] = 1
            elif case == "bool":
                fixture[2][0]["start"] = False
            elif case == "failed_value":
                fixture[3][0]["status"] = "failed"
            else:
                fixture[2][1]["starter_agent_sha256"] = "9" * 64

        for case in (
            "omitted_task",
            "omitted_slot",
            "duplicate",
            "duplicate_preserved",
            "duplicate_slot",
            "typed_id",
            "family",
            "agent",
            "repeat",
            "bool",
            "failed_value",
            "starter",
        ):
            with self.subTest(case=case):
                fixture = self.fixture()
                change(fixture, case)
                with patch.object(
                    self.module.bounds,
                    "_hoeffding_lower_bound",
                    side_effect=AssertionError("arithmetic before coverage validation"),
                ):
                    with self.assertRaises(self.Error):
                        self.call(fixture)

    def test_same_source_roles_retain_actual_independent_measurements(self):
        fixture = self.fixture()
        fixture[2][1]["descendant_agent_sha256"] = "3" * 64
        for row in fixture[3]:
            if row["role"] == "evolved":
                row["agent_sha256"] = "3" * 64
        observed = self.call(fixture)
        self.assertEqual(
            observed["contrasts"]["improver_effect"]["utility"]["point"], ratio(Fraction(2))
        )
        for row in fixture[3]:
            if row["role"] == "evolved":
                row.update(utility=5, distinct=5)
        equal = self.call(fixture)
        self.assertEqual(
            equal["contrasts"]["improver_effect"]["utility"]["point"], ratio(Fraction(0))
        )
        self.assertEqual(equal["contrasts"]["initial_gain"]["utility"]["point"], ratio(Fraction(3)))
        self.assertEqual(equal["coverage"]["expected_rows"], 9)

    def test_shared_starter_cancels_and_raw_support_reaches_the_conservative_kernel(self):
        fixture = self.fixture()
        before = self.call(fixture)
        for row in fixture[3]:
            if row["role"] == "starter":
                row["utility"] += 1
        kernel = self.module.bounds._hoeffding_lower_bound
        with patch.object(self.module.bounds, "_hoeffding_lower_bound", wraps=kernel) as observed:
            after = self.call(fixture)
        self.assertEqual(
            after["contrasts"]["improver_effect"], before["contrasts"]["improver_effect"]
        )
        for name in ("initial_gain", "evolved_gain"):
            self.assertEqual(
                after["contrasts"][name]["utility"]["point"]["numerator"],
                before["contrasts"][name]["utility"]["point"]["numerator"] - 1,
            )
        self.assertEqual(len(observed.call_args_list), 6)
        for index, call in enumerate(observed.call_args_list):
            self.assertEqual(call.kwargs["span"], Fraction(10 if index % 2 == 0 else 9))
            self.assertEqual(call.kwargs["squared_weight_sum"], Fraction(5, 9))
            self.assertEqual(call.kwargs["tail"], Fraction(1, 100))

    def test_zero_distinct_span_and_unchanged_strict_gain_inclusive_loss_rule(self):
        fixture = self.fixture()
        for task in fixture[1]["tasks"]:
            task["count"] = 1
        for row in fixture[3]:
            row["distinct"] = 1
        fixture[0]["population_sha256"] = digest(fixture[1])
        self.rule = ImprovementRule.from_bytes(
            _json(
                {
                    "format": "buddha.improvement-rule.v1",
                    "primary_metric": "distinct",
                    "minimum_gain": 0,
                    "max_other_loss": 10,
                }
            )
        )
        fixture[0]["improvement_rule_sha256"] = self.rule.fingerprint()
        result = self.call(fixture)
        for contrast in result["contrasts"].values():
            self.assertEqual(contrast["distinct"]["point"], ratio(Fraction(0)))
            self.assertEqual(contrast["distinct"]["lower_bound"], 0)
            self.assertEqual(contrast["distinct"]["radius_upper"], "0")
        self.assertEqual(result["rule"]["status"], "rule_not_satisfied")
        self.assertEqual(
            result["rule"]["checks"], {"primary_gain": False, "other_noninferiority": True}
        )

    def test_fixed_operator_and_starter_identities_cannot_drift_between_conditions(self):
        for case in ("improver", "starter", "duplicate_population", "foreign_null_row"):
            with self.subTest(case=case):
                fixture = self.fixture(starts=2, repetitions=2)
                if case == "improver":
                    fixture[2][-1]["improver_agent_sha256"] = "9" * 64
                elif case == "starter":
                    for slot in fixture[2]:
                        if slot["start"] == 1 and slot["repetition"] == 1:
                            slot["starter_agent_sha256"] = "9" * 64
                elif case == "duplicate_population":
                    fixture[1]["tasks"][1]["task_id"] = 1
                    fixture[0]["population_sha256"] = digest(fixture[1])
                else:
                    fixture[2][0].update(status="no_valid_descendant", descendant_agent_sha256=None)
                with self.assertRaises(self.Error):
                    self.call(fixture)

    def test_plan_population_support_allocations_and_inputs_are_checked_and_immutable(self):
        fixture = self.fixture()
        original = copy.deepcopy(fixture)
        plan = self.Plan.from_bytes(_json(fixture[0]))
        detached = plan.to_record()
        detached["counts"]["starts"] = 99
        self.assertEqual(plan.to_record()["counts"]["starts"], 1)
        with self.assertRaises(FrozenInstanceError):
            plan.data = b"{}"
        with ExitStack() as stack:
            for target in (
                "builtins.open",
                "pathlib.Path.open",
                "sqlite3.connect",
                "socket.socket",
                "subprocess.Popen",
            ):
                stack.enter_context(
                    patch(target, side_effect=AssertionError("pure arithmetic performed I/O"))
                )
            self.call(fixture)
        self.assertEqual(fixture, original)
        for case in (
            "population",
            "alpha",
            "extra_tail",
            "huge",
            "support",
            "nan",
            "distinct_float",
            "wrong_rule",
            "source",
            "bool_scalar",
            "bool_tail",
            "invalid_count",
            "unknown_method",
        ):
            with self.subTest(case=case):
                broken = copy.deepcopy(fixture)
                if case == "population":
                    broken[1]["tasks"][0]["task_id"] = "foreign"
                elif case == "alpha":
                    broken[0]["alpha_total"] = ratio(Fraction(1, 100))
                elif case == "extra_tail":
                    broken[0]["tail_allocations"]["extra"] = {}
                elif case == "huge":
                    broken[0]["counts"]["sealed_repetitions"] = 2**63 - 1
                elif case == "support":
                    broken[3][0]["utility"] = 11
                elif case == "nan":
                    broken[3][0]["utility"] = float("nan")
                elif case == "distinct_float":
                    broken[3][0]["distinct"] = 3.0
                elif case == "wrong_rule":
                    broken[0]["improvement_rule_sha256"] = "9" * 64
                elif case == "bool_scalar":
                    broken[3][0]["utility"] = True
                elif case == "bool_tail":
                    broken[0]["tail_allocations"]["initial_gain"]["utility"]["numerator"] = True
                elif case == "invalid_count":
                    broken[1]["tasks"][0]["count"] = 0
                    broken[0]["population_sha256"] = digest(broken[1])
                elif case == "unknown_method":
                    broken[0]["method"] = "unsupported"
                else:
                    broken[0]["analyzer_sources"].pop("buddha/improver_analysis.py")
                with self.assertRaises(self.Error):
                    self.call(broken)
        with self.assertRaises(self.Error):
            self.Plan.from_bytes(b'{"format":"x","format":"y"}')
        oversized = copy.deepcopy(fixture[0])
        oversized["counts"].update(starts=1000, development_repetitions=1000)
        with self.assertRaises(self.Error):
            self.Plan.from_bytes(_json(oversized))


if __name__ == "__main__":
    unittest.main()
