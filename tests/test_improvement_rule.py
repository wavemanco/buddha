"""DESIGN6 numerical rule only: supplied bounds do not grant promotion authority."""

import copy
import json
import math
import subprocess
import sys
import unittest
from dataclasses import FrozenInstanceError
from pathlib import Path
from unittest.mock import patch

from buddha.improvement_rule import (
    ImprovementRule,
    ImprovementRuleError,
    evaluate_improvement_rule,
)


def record(primary="utility", gain=1, loss=0.5):
    return {
        "format": "buddha.improvement-rule.v1",
        "primary_metric": primary,
        "minimum_gain": gain,
        "max_other_loss": loss,
    }


def make_rule(value):
    return ImprovementRule.from_bytes(json.dumps(value, allow_nan=True).encode())


class IntSubtype(int):
    pass


class FloatSubtype(float):
    pass


class TextSubtype(str):
    pass


class DictSubtype(dict):
    pass


class ImprovementRuleTests(unittest.TestCase):
    def decide(self, *, primary="utility", gain=1, loss=0.5, utility=1.25, distinct=0):
        return evaluate_improvement_rule(
            make_rule(record(primary, gain, loss)),
            lower_bounds={"utility": utility, "distinct": distinct},
            complete_coverage=True,
        )

    def test_utility_gain_is_strict_other_loss_is_inclusive(self):
        equal = self.decide(utility=1, distinct=0)
        self.assertEqual(equal["status"], "rule_not_satisfied")
        self.assertEqual(equal["checks"], {"primary_gain": False, "other_noninferiority": True})
        allowed_loss = self.decide(utility=1.25, distinct=-0.5)
        self.assertEqual(allowed_loss["status"], "rule_satisfied")
        self.assertEqual(
            allowed_loss["checks"], {"primary_gain": True, "other_noninferiority": True}
        )
        exceeded = self.decide(utility=1.25, distinct=-0.5001)
        self.assertEqual(exceeded["status"], "rule_not_satisfied")
        self.assertEqual(exceeded["checks"], {"primary_gain": True, "other_noninferiority": False})

    def test_distinctiveness_rule_is_symmetric(self):
        self.assertEqual(
            self.decide(primary="distinct", distinct=1)["status"], "rule_not_satisfied"
        )
        self.assertEqual(
            self.decide(primary="distinct", utility=-0.5, distinct=1.25)["status"], "rule_satisfied"
        )
        self.assertEqual(
            self.decide(primary="distinct", utility=-0.5001, distinct=1.25)["status"],
            "rule_not_satisfied",
        )

    def test_declared_axis_cannot_be_replaced_by_the_favorable_axis(self):
        self.assertEqual(self.decide(utility=0.1, distinct=9)["status"], "rule_not_satisfied")
        self.assertEqual(
            self.decide(primary="distinct", utility=9, distinct=0.1)["status"], "rule_not_satisfied"
        )

    def test_no_rounding_tolerance_or_float_coercion_of_large_integers(self):
        high = 2**53
        self.assertEqual(
            self.decide(gain=high, utility=high + 1, distinct=-0.5)["status"], "rule_satisfied"
        )
        self.assertEqual(
            self.decide(gain=high + 1, utility=high, distinct=-0.5)["status"], "rule_not_satisfied"
        )
        self.assertEqual(
            self.decide(gain=0, loss=0, utility=math.nextafter(0, 1), distinct=0)["status"],
            "rule_satisfied",
        )
        self.assertEqual(
            self.decide(gain=0, loss=0, utility=0, distinct=0)["status"], "rule_not_satisfied"
        )

    def test_missing_bounds_or_incomplete_coverage_are_inconclusive(self):
        rule = make_rule(record())
        for coverage, utility, distinct in (
            (False, 9, 9),
            (True, None, 9),
            (True, 9, None),
            (False, None, None),
        ):
            with self.subTest(coverage=coverage, utility=utility, distinct=distinct):
                result = evaluate_improvement_rule(
                    rule,
                    lower_bounds={"utility": utility, "distinct": distinct},
                    complete_coverage=coverage,
                )
                self.assertEqual(result["status"], "inconclusive")
                self.assertEqual(
                    result["checks"], {"primary_gain": None, "other_noninferiority": None}
                )

    def test_all_values_are_validated_even_when_coverage_is_false(self):
        rule = make_rule(record())
        invalid = (
            True,
            False,
            math.nan,
            math.inf,
            -math.inf,
            "1",
            [],
            {},
            IntSubtype(1),
            FloatSubtype(1),
        )
        for coverage in (False, True):
            for field in ("utility", "distinct"):
                for value in invalid:
                    with self.subTest(coverage=coverage, field=field, kind=type(value)):
                        bounds = {"utility": 9, "distinct": 9} | {field: value}
                        with self.assertRaises(ImprovementRuleError):
                            evaluate_improvement_rule(
                                rule, lower_bounds=bounds, complete_coverage=coverage
                            )
        for coverage in (0, 1, None, "true", [], IntSubtype(1)):
            with self.subTest(coverage=coverage), self.assertRaises(ImprovementRuleError):
                evaluate_improvement_rule(
                    rule, lower_bounds={"utility": 9, "distinct": 9}, complete_coverage=coverage
                )

    def test_bounds_are_an_exact_two_key_builtin_object(self):
        rule = make_rule(record())
        cases = (
            None,
            [],
            (),
            {},
            {"utility": 1},
            {"utility": 1, "distinct": 1, "other": 1},
            DictSubtype(utility=1, distinct=1),
            {TextSubtype("utility"): 1, "distinct": 1},
        )
        for bounds in cases:
            with self.subTest(kind=type(bounds)), self.assertRaises(ImprovementRuleError):
                evaluate_improvement_rule(rule, lower_bounds=bounds, complete_coverage=False)

    def test_rule_fields_are_exact_and_margins_have_no_defaults(self):
        good = record()
        cases = [None, [], good | {"extra": 1}]
        cases += [{key: value for key, value in good.items() if key != missing} for missing in good]
        cases += [good | {"format": value} for value in ("other", 1)]
        cases += [good | {"primary_metric": value} for value in ("both", "Utility", 1)]
        for field in ("minimum_gain", "max_other_loss"):
            cases += [
                good | {field: value}
                for value in (
                    -1,
                    -0.1,
                    True,
                    False,
                    math.nan,
                    math.inf,
                    -math.inf,
                    "1",
                    None,
                )
            ]
        for value in cases:
            with self.subTest(value=repr(value)), self.assertRaises(ImprovementRuleError):
                make_rule(value)

    def test_raw_json_is_strict_and_rule_class_cannot_be_spoofed(self):
        for raw in (
            b"{",
            b"[]",
            b"null",
            b"{}",
            b'{"format":1,"format":2}',
            b'{"format":NaN}',
            bytearray(b"{}"),
            "{}",
        ):
            with self.subTest(raw=repr(raw)), self.assertRaises(ImprovementRuleError):
                ImprovementRule.from_bytes(raw)

        class RuleSubtype(ImprovementRule):
            pass

        for rule in ({}, None, RuleSubtype.from_bytes(json.dumps(record()).encode())):
            with self.subTest(kind=type(rule)), self.assertRaises(ImprovementRuleError):
                evaluate_improvement_rule(
                    rule, lower_bounds={"utility": 9, "distinct": 9}, complete_coverage=True
                )

    def test_rule_canonical_identity_and_views_are_immutable(self):
        source = record()
        rule = make_rule(source)
        source["minimum_gain"] = 99
        self.assertEqual(rule.to_record()["minimum_gain"], 1)
        view = rule.to_record()
        view["max_other_loss"] = 99
        self.assertEqual(rule.to_record()["max_other_loss"], 0.5)
        with self.assertRaises(FrozenInstanceError):
            rule.data = b"{}"
        reversed_raw = json.dumps(dict(reversed(list(record().items()))), indent=2).encode()
        restored = ImprovementRule.from_bytes(reversed_raw)
        self.assertEqual(rule.to_bytes(), restored.to_bytes())
        self.assertEqual(rule.fingerprint(), restored.fingerprint())
        identities = {rule.fingerprint()}
        identities.update(
            make_rule(value).fingerprint()
            for value in (
                record("distinct"),
                record(gain=2),
                record(loss=1),
            )
        )
        self.assertEqual(len(identities), 4)

    def test_result_is_detached_pure_and_never_a_promotion_attestation(self):
        rule = make_rule(record())
        bounds = {"utility": 1.25, "distinct": -0.5}
        original = copy.deepcopy(bounds)
        with (
            patch("builtins.open", side_effect=AssertionError("no I/O")),
            patch.object(Path, "open", side_effect=AssertionError("no I/O")),
        ):
            result = evaluate_improvement_rule(rule, lower_bounds=bounds, complete_coverage=True)
        self.assertEqual(bounds, original)
        self.assertEqual(
            set(result),
            {
                "format",
                "status",
                "rule_sha256",
                "primary_metric",
                "lower_bounds",
                "complete_coverage",
                "checks",
                "claim",
            },
        )
        self.assertEqual(result["format"], "buddha.improvement-rule-result.v1")
        self.assertEqual(result["rule_sha256"], rule.fingerprint())
        self.assertIn("caller", result["claim"])
        self.assertIn("promotion", result["claim"])
        result["lower_bounds"]["utility"] = 999
        result["checks"]["primary_gain"] = False
        fresh = evaluate_improvement_rule(rule, lower_bounds=bounds, complete_coverage=True)
        self.assertEqual(fresh["lower_bounds"], original)
        self.assertTrue(fresh["checks"]["primary_gain"])
        self.assertFalse(
            {"promoted", "winner", "p_value", "confidence_level", "heldout_improvement"}
            & set(fresh)
        )
        json.dumps(fresh, allow_nan=False)

    def test_result_must_be_bounded_json_even_when_coverage_is_false(self):
        previous_limit = sys.get_int_max_str_digits()
        self.addCleanup(sys.set_int_max_str_digits, previous_limit)
        sys.set_int_max_str_digits(4300)
        rule = make_rule(record())
        for coverage in (False, True):
            with self.subTest(coverage=coverage), self.assertRaises(ImprovementRuleError):
                evaluate_improvement_rule(
                    rule,
                    lower_bounds={"utility": 10**5000, "distinct": 0},
                    complete_coverage=coverage,
                )

    def test_import_needs_no_finance_native_or_statistical_dependencies(self):
        root = Path(__file__).resolve().parents[1]
        script = """
import sys
before=set(sys.modules)
sys.path.insert(0,sys.argv[1])
from buddha.improvement_rule import ImprovementRule,evaluate_improvement_rule
assert callable(evaluate_improvement_rule)
assert not (set(sys.modules)-before) & {
 'buddha.authorization','buddha.gateway','buddha.ledger','buddha.provider',
 'buddha.native_run','buddha.native_evaluation','buddha.source_search',
 'openai','anthropic','numpy','scipy','pandas'
}
"""
        result = subprocess.run(
            [sys.executable, "-I", "-B", "-c", script, str(root)],
            capture_output=True,
            text=True,
            check=False,
        )
        self.assertEqual(result.returncode, 0, result.stderr)


if __name__ == "__main__":
    unittest.main()
