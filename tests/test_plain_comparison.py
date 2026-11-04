"""Exact descriptive aggregation and prospective-plan refusals; no model calls."""

import copy
import hashlib
import itertools
import tempfile
import unittest
from contextlib import ExitStack
from fractions import Fraction
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from buddha import plain_comparison as comparison
from buddha.releases import _json


def ratio(value):
    return {"numerator": value.numerator, "denominator": value.denominator}


class PlainPanelTests(unittest.TestCase):
    def setUp(self):
        self.state = {
            "plan": SimpleNamespace(
                to_record=lambda: {
                    "counts": {"starts": 2, "development_repetitions": 2, "sealed_repetitions": 2}
                }
            )
        }
        self.population = {
            "tasks": [
                {"task_id": identifier, "family_id": "shared-family", "count": 2}
                for identifier in (1, "1")
            ]
        }
        self.rows = []
        for role, start, repeat, sealed, task in itertools.product(
            ("starter", "initial", "evolved"), range(2), range(2), range(2), range(2)
        ):
            self.rows.append(
                {
                    "role": role,
                    "start": start,
                    "repetition": repeat,
                    "sealed_repetition": sealed,
                    "task_id": (1, "1")[task],
                    "task_index": task,
                    "agent_sha256": "7" * 64,
                    "status": "observed",
                    "utility": {"starter": 3, "initial": 4, "evolved": 6}[role]
                    + start
                    + 2 * repeat
                    + sealed / 2
                    + task / 4,
                    "distinct": 2,
                }
            )
        self.references = {
            name: [
                {
                    "task_id": identifier,
                    "utility": values[index],
                    "distinct": 1,
                    "invalid_metrics": [],
                }
                for index, identifier in enumerate((1, "1"))
            ]
            for name, values in (("regenerate", (2, 4)), ("in-context", (4, 6)))
        }

    def panel(self):
        with patch.object(
            comparison.improver_assessment, "_population", return_value=self.population
        ):
            return comparison._panel(self.state, self.rows, self.references)

    def contrast(self, result, role, name="regenerate"):
        return next(
            row["metrics"]
            for row in result["contrasts"]
            if row["role"] == role and row["reference"] == name
        )

    def test_equal_prompt_means_typed_ids_and_shared_reference_denominator(self):
        result = self.panel()
        self.assertEqual(result["status"], "complete")
        self.assertEqual(result["planned_buddha_sets"], 48)
        self.assertEqual(result["observed_buddha_sets"], 48)
        self.assertEqual(result["unique_reference_sets"], 4)
        self.assertEqual([row["task_id"] for row in result["prompts"]], [1, "1"])
        self.assertEqual(
            self.contrast(result, "starter")["utility"]["mean_difference"], ratio(Fraction(15, 8))
        )
        self.assertEqual(
            self.contrast(result, "starter", "in-context")["utility"]["mean_difference"],
            ratio(Fraction(-1, 8)),
        )
        self.assertEqual(
            self.contrast(result, "starter")["distinct"]["mean_difference"], ratio(Fraction(1))
        )
        # Identical source hashes do not merge the roles or duplicate references.
        self.assertEqual(len(result["contrasts"]), 6)
        self.assertEqual(
            self.contrast(result, "evolved")["utility"]["mean_difference"], ratio(Fraction(39, 8))
        )

    def test_null_descendant_preserves_every_planned_condition(self):
        self.rows = [
            row
            for row in self.rows
            if (row["role"], row["start"], row["repetition"]) != ("initial", 1, 1)
        ]
        result = self.panel()
        self.assertEqual(result["status"], "incomplete")
        self.assertEqual(result["planned_buddha_sets"], 48)
        self.assertEqual(result["observed_buddha_sets"], 44)
        self.assertEqual(result["unique_reference_sets"], 4)
        self.assertIsNone(self.contrast(result, "initial")["utility"]["mean_difference"])
        self.assertEqual(self.contrast(result, "initial")["utility"]["available_prompts"], 0)
        self.assertEqual(self.contrast(result, "starter")["utility"]["status"], "complete")

    def test_one_unusable_scalar_suppresses_affected_mean_without_zero_fill(self):
        next(row for row in self.rows if row["role"] == "evolved")["utility"] = None
        result = self.panel()
        metric = self.contrast(result, "evolved")["utility"]
        self.assertEqual(result["status"], "incomplete")
        self.assertEqual(metric["available_prompts"], 1)
        self.assertIsNone(metric["mean_difference"])
        self.assertEqual(self.contrast(result, "evolved")["distinct"]["status"], "complete")

    def test_unusable_plain_metric_is_not_recomputed_from_other_fields(self):
        scalar = self.references["regenerate"][0]
        scalar["invalid_metrics"] = ["utility"]
        scalar["utility"] = 0
        result = self.panel()
        for role in ("starter", "initial", "evolved"):
            self.assertIsNone(self.contrast(result, role)["utility"]["mean_difference"])
            self.assertEqual(
                self.contrast(result, role, "in-context")["utility"]["status"], "complete"
            )

    def test_literal_float_values_remain_exact_saved_binary_numbers(self):
        for row in self.rows:
            row["utility"] = 0.1
        for rows in self.references.values():
            for row in rows:
                row["utility"] = 0
        self.assertEqual(
            self.contrast(self.panel(), "starter")["utility"]["mean_difference"],
            ratio(Fraction.from_float(0.1)),
        )


class PlainComparisonPlanTests(unittest.TestCase):
    def test_invalid_prospective_plan_refuses_before_original_study_read(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary).resolve()
            path = root / "plan.json"
            original = {
                "format": "buddha.plain-comparison-plan.v1",
                "method": comparison._METHOD,
                "trial": str(root / "trial"),
                "definition_sha256": "1" * 64,
                "references": [
                    {
                        "name": "regenerate",
                        "directory": str(root / "plain"),
                        "authorization": str(root / "grant.sqlite3"),
                        "definition": str(root / "baseline.json"),
                        "sha256": "2" * 64,
                    }
                ],
                "consumer_sources": comparison._source_hashes(),
            }
            self.assertEqual(comparison._plan(_json(original)), original)
            cases = []
            for key, value in (
                ("method", "choose_best_afterward"),
                ("consumer_sources", {}),
                ("definition_sha256", False),
            ):
                changed = copy.deepcopy(original)
                changed[key] = value
                cases.append(changed)
            for change in ("duplicate", "nested", "unknown"):
                changed = copy.deepcopy(original)
                if change == "duplicate":
                    changed["references"] *= 2
                elif change == "nested":
                    changed["references"][0]["directory"] = str(root / "trial/plain")
                else:
                    changed["references"][0]["name"] = "best"
                cases.append(changed)
            for case in cases:
                with self.subTest(case=case["method"]):
                    raw = _json(case)
                    path.write_bytes(raw)
                    with (
                        patch.object(
                            comparison.improver_assessment,
                            "_read_improver_assessment",
                            side_effect=AssertionError("study read"),
                        ),
                        self.assertRaises(comparison.PlainComparisonError),
                    ):
                        comparison.compare_plain_references(
                            path,
                            expected_plan_sha256=hashlib.sha256(raw).hexdigest(),
                            expected_assessment_report_sha256="3" * 64,
                            expected_reference_report_sha256={"regenerate": "4" * 64},
                        )


class DevelopmentUsageTests(unittest.TestCase):
    def test_retained_original_receipts_supply_tokens_once_without_source_sql(self):
        import sqlite3

        import test_baseline as fixtures

        from buddha import baseline_results
        from buddha.doctor import _Capture
        from buddha.native_evidence import _adopt_capture

        case = fixtures.BaselineTests("runTest")
        case.setUp()
        self.addCleanup(case.doCleanups)
        root = case.root / "development"
        case.directory = root / "common/0/0/screen"
        case.directory.parent.mkdir(parents=True)
        case.prepare()
        self.assertEqual(case.run_pipeline()["status"], "complete")
        observed = baseline_results._read_baseline(
            case.directory,
            authorization=case.authority.path,
            expected_report_sha256=hashlib.sha256(
                (case.directory / "report.json").read_bytes()
            ).hexdigest(),
            expected_definition_sha256=hashlib.sha256(case.descriptor.read_bytes()).hexdigest(),
        )
        captured = _Capture(root)
        _adopt_capture(observed.reader.capture, captured)
        owners = [
            {
                "directory": str(owner.directory),
                "run_id": owner.run_id,
                "manifest_sha256": owner.manifest_sha256,
                "ledger_sha256": owner.ledger_sha256,
            }
            for owner in observed.reader.owners.values()
        ]
        totals = {
            key: sum(owner.accounting()[key] for owner in observed.reader.owners.values())
            for key in (
                "committed_microusd",
                "spent_microusd",
                "reserved_microusd",
                "operation_count",
            )
        }
        state = {
            "development_capture": captured,
            "development_report": {
                "provenance": {"owners": owners},
                "costs": {"totals": totals},
            },
        }
        connect = sqlite3.connect

        def memory_only(path, *args, **kwargs):
            self.assertEqual(path, ":memory:")
            return connect(path, *args, **kwargs)

        with ExitStack() as stack:
            stack.enter_context(patch("sqlite3.connect", side_effect=memory_only))
            usage = comparison._development_resources(state)
            self.assertEqual(usage["summary"]["operation_count"], totals["operation_count"])
            self.assertEqual(
                usage["summary"]["tokens"]["known_operations"], totals["operation_count"]
            )
            self.assertEqual(len(usage["operations"]), totals["operation_count"])
            owners.append(owners[0])
            with self.assertRaises(comparison.PlainComparisonError):
                comparison._development_resources(state)
            owners.pop()
            owners[0]["ledger_sha256"] = "0" * 64
            with self.assertRaises(comparison.PlainComparisonError):
                comparison._development_resources(state)


if __name__ == "__main__":
    unittest.main()
