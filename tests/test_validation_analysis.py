"""Prospective analysis consumes original synthetic native evidence; no live I/O."""

import copy
import hashlib
import io
import json
import math
import os
import sqlite3
import unittest
from contextlib import ExitStack, contextmanager
from decimal import Decimal, localcontext
from fractions import Fraction
from pathlib import Path
from unittest.mock import patch


def sha(raw):
    return hashlib.sha256(raw).hexdigest()


def rational(value):
    return {"numerator": value.numerator, "denominator": value.denominator}


def log_two_bracket(terms=180):
    """Independent rational series and geometric upper tail, with no Decimal log."""
    z = Fraction(1, 3)
    lower = 2 * sum((z ** (2 * n + 1) / (2 * n + 1) for n in range(terms)), Fraction())
    tail = 2 * z ** (2 * terms + 1) / ((2 * terms + 1) * (1 - z * z))
    return lower, lower + tail


def sqrt_bracket(value, digits=90):
    """Exact integer-square oracle, independent of Decimal sqrt and its rounding."""
    scale = 10**digits
    floor = math.isqrt(value.numerator * scale * scale // value.denominator)
    lower, upper = Fraction(floor, scale), Fraction(floor + 1, scale)
    assert lower * lower <= value < upper * upper
    return lower, upper


class ValidationAnalysisTests(unittest.TestCase):
    def setUp(self):
        # Import failure is an interface RED before any fixture, SQL or fake worker.
        from buddha import validation_analysis
        from buddha.releases import _json
        from buddha.validation_analysis import (
            ValidationAnalysisError,
            ValidationAnalysisPlan,
            analyze_validation_occasion,
        )

        self.module = validation_analysis
        self.Error, self.Plan = ValidationAnalysisError, ValidationAnalysisPlan
        self.analyze = analyze_validation_occasion
        self.json = _json

    def plan_record(self, **changes):
        record = {
            "format": "buddha.validation-analysis-plan.v1",
            "method": "fixed-panel-family-hoeffding.v1",
            "projection": "noveltybench-1.1",
            "projection_release_sha256": "a" * 64,
            "estimand": "fixed-panel-conditional-expected-native-difference",
            "weighting": "equal-prompts",
            "repetition_aggregation": "mean-within-prompt",
            "block": "custody-family",
            "independence": "conditional-independent-family-blocks",
            "score_support_assumption": "well-defined-bounded-native-metrics",
            "judge_policy": "single-native-occasion",
            "max_looks": 2,
            "max_candidates": 2,
            "comparator_count": 2,
            "repetitions": 2,
            "finalist_count": 1,
            "alpha": {
                "total": rational(Fraction(1, 8)),
                "validation": rational(Fraction(1, 16)),
                "final": rational(Fraction(1, 32)),
            },
            "improvement_rule_sha256": "b" * 64,
            "analyzer_sources": self.module._source_hashes(),
        }
        return record | changes

    def fixture(self, *, opaque=False, unusable=False):
        import test_validation_study

        from buddha.improvement_rule import ImprovementRule

        f = test_validation_study.ValidationStudyTests("runTest")
        f.setUp()
        self.addCleanup(f.doCleanups)
        self.engine = f.engine
        self.generation_events, self.native_events = f.generation_events, f.native_events
        self.f = f
        f.record["repetitions"] = 1
        f.record["max_looks"] = 2
        f.record["max_candidates"] = 2
        if not opaque:
            self.original_plan = self.plan_record(
                projection_release_sha256=f.engine.candidate.release.fingerprint(),
                max_looks=f.record["max_looks"],
                max_candidates=f.record["max_candidates"],
                comparator_count=len(f.record["comparators"]),
                repetitions=f.record["repetitions"],
                improvement_rule_sha256=ImprovementRule.from_bytes(self.json(f.rule)).fingerprint(),
            )
            self.Plan.from_bytes(self.json(self.original_plan))
            f.record["analysis_plan"] = f.reference(
                f.write("analysis-plan.json", self.original_plan)
            )
        f.declaration = f.write("declaration.json", f.record)

        def native_row(row, index):
            # Supplied synthetic native artifacts, not an official judge's decisions.
            row["distinct"] = 2
            if index == 1:
                row.update(generation_scores=[7, 7], partition_scores=[7, 7], utility=7.0)
                arm = (
                    Path(f.native_events[-1][0])
                    .relative_to(f.directory / "validation/0/arms")
                    .parts[0]
                )
                if unusable and arm == "1":
                    row["utility"] = float("nan")
            return row

        f.engine.native_row = native_row
        f.prepare()
        authority = f.authority()
        return f, authority

    def completed(self, **changes):
        f, authority = self.fixture(**changes)
        with f.offline():
            result = f.run_occasion(authority)
        self.assertEqual(result["status"], "complete")
        return f, authority, result

    def call(self, f, authority, **changes):
        result = f.directory / "validation/0/result.json"
        return self.analyze(
            f.directory,
            **(
                {
                    "ordinal": 0,
                    "authorization": authority.path,
                    "expected_result_sha256": sha(result.read_bytes()),
                }
                | changes
            ),
        )

    @contextmanager
    def passive(self):
        connect, opened, path_opened = sqlite3.connect, io.open, os.open

        def memory_only(database, *args, **kwargs):
            self.assertEqual(database, ":memory:", "analysis cannot open file-backed SQL")
            return connect(database, *args, **kwargs)

        def read_only(file, mode="r", *args, **kwargs):
            self.assertFalse(any(flag in mode for flag in "wax+"), "analysis cannot write files")
            return opened(file, mode, *args, **kwargs)

        def read_only_descriptor(path, flags, *args, **kwargs):
            self.assertEqual(
                flags & (os.O_WRONLY | os.O_RDWR | os.O_CREAT | os.O_TRUNC | os.O_APPEND), 0
            )
            return path_opened(path, flags, *args, **kwargs)

        with ExitStack() as stack:
            stack.enter_context(patch.dict(os.environ, {}, clear=True))
            for target in (
                "buddha.gateway.Gateway.__init__",
                "buddha.authorization.Authorization.__init__",
                "buddha.gateway.RawHTTPTransport.__init__",
                "buddha.native_pipeline._exclusive",
                "buddha.native_pipeline._write",
                "buddha.candidate_generation.prepare_candidate_generation",
                "buddha.candidate_generation.run_candidate_generation",
                "buddha.native_evaluation.prepare_evaluation",
                "buddha.native_evaluation.run_evaluation",
                "buddha.executor.run_container",
                "subprocess.Popen",
                "socket.create_connection",
                "socket.socket.connect",
                "socket.getaddrinfo",
            ):
                stack.enter_context(
                    patch(target, side_effect=AssertionError("active analysis I/O"))
                )
            stack.enter_context(patch("sqlite3.connect", side_effect=memory_only))
            stack.enter_context(patch("io.open", side_effect=read_only))
            stack.enter_context(patch("os.open", side_effect=read_only_descriptor))
            yield

    def test_strict_prospective_plan_and_exact_rational_allocation(self):
        record = self.plan_record()
        plan = self.Plan.from_bytes(self.json(record))
        self.assertEqual(plan.to_record(), record)
        self.assertEqual(self.Plan.from_bytes(plan.to_bytes()).fingerprint(), plan.fingerprint())
        record["alpha"]["total"]["numerator"] = 7
        self.assertEqual(plan.to_record(), self.plan_record())
        invalid = []
        for key, value in (
            ("max_looks", True),
            ("max_candidates", 0),
            ("comparator_count", 1.0),
            ("repetitions", "2"),
            ("finalist_count", -1),
            ("method", "unreviewed-method"),
            ("projection_release_sha256", "unknown"),
            ("analyzer_sources", {"arbitrary-local-path": "f" * 64}),
        ):
            invalid.append(self.plan_record(**{key: value}))
        missing, extra = self.plan_record(), self.plan_record()
        del missing["alpha"]
        extra["confidence"] = 0.95
        invalid += [missing, extra]
        for portion, value in (
            ("total", Fraction(1)),
            ("total", Fraction(0)),
            ("validation", Fraction(0)),
            ("final", Fraction(-1, 32)),
            ("validation", Fraction(1, 4)),
        ):
            value_record = self.plan_record()
            value_record["alpha"][portion] = rational(value)
            invalid.append(value_record)
        for numerator, denominator in ((True, 8), (1, False), (1, 0), (1.0, 8)):
            value_record = self.plan_record()
            value_record["alpha"]["total"] = {"numerator": numerator, "denominator": denominator}
            invalid.append(value_record)
        for index, value in enumerate(invalid):
            with self.subTest(case=index), self.assertRaises(self.Error):
                self.Plan.from_bytes(self.json(value))
        alpha = self.plan_record()["alpha"]
        portions = {key: Fraction(**value) for key, value in alpha.items()}
        self.assertEqual(portions["validation"] / (2 * 2 * 2 * 2), Fraction(1, 256))
        self.assertEqual(portions["final"] / (2 * 1 * 2), Fraction(1, 128))
        self.assertEqual(
            portions["total"] - portions["validation"] - portions["final"], Fraction(1, 32)
        )

    def test_exact_panel_family_and_repetition_aggregation(self):
        values = [
            ([1, 3], [4, 6], [1, 3], [3, 3]),
            ([2, 4], [4, 6], [2, 2], [1, 3]),
            ([6, 8], [2, 4], [4, 2], [1, 1]),
        ]
        rows = []
        for task, (comparator_u, candidate_u, comparator_d, candidate_d) in enumerate(values):
            for arm, utility, distinct in (
                (0, comparator_u, comparator_d),
                (1, candidate_u, candidate_d),
            ):
                for repetition in range(2):
                    rows.append(
                        {
                            "arm_index": arm,
                            "task_index": task,
                            "task_id": "p" + str(task),
                            "family_id": "A" if task == 0 else "B",
                            "repetition": repetition,
                            "utility": utility[repetition],
                            "distinct": distinct[repetition],
                            "invalid_metrics": [],
                        }
                    )
        aggregate = self.module._aggregate_contrast(
            rows, candidate_arm=1, comparator_arm=0, repetitions=2
        )
        self.assertEqual(
            aggregate["points"], {"utility": Fraction(1, 3), "distinct": Fraction(-1, 3)}
        )
        self.assertEqual(aggregate["family_weights"], {"A": Fraction(1, 3), "B": Fraction(2, 3)})
        self.assertEqual(aggregate["squared_weight_sum"], Fraction(5, 9))
        self.assertIs(aggregate["complete"], True)
        repeated = rows + [row | {"repetition": row["repetition"] + 2} for row in rows]
        self.assertEqual(
            self.module._aggregate_contrast(
                repeated, candidate_arm=1, comparator_arm=0, repetitions=4
            ),
            aggregate,
        )
        reverse = self.module._aggregate_contrast(
            rows, candidate_arm=0, comparator_arm=1, repetitions=2
        )
        self.assertEqual(
            reverse["points"], {key: -value for key, value in aggregate["points"].items()}
        )
        unavailable = copy.deepcopy(rows)
        unavailable[-1]["utility"] = None
        unavailable[-1]["invalid_metrics"] = ["utility"]
        missing = self.module._aggregate_contrast(
            unavailable, candidate_arm=1, comparator_arm=0, repetitions=2
        )
        self.assertIs(missing["complete"], False)
        self.assertIsNone(missing["points"]["utility"])

    def test_independent_radius_brackets_and_exact_downward_threshold_neighbors(self):
        from buddha.improvement_rule import ImprovementRule, evaluate_improvement_rule

        _, log_upper = log_two_bracket()
        sqrt_upper = sqrt_bracket(log_upper)[1]
        for ambient_precision in (6, 100):
            with self.subTest(ambient_precision=ambient_precision), localcontext() as ambient:
                ambient.prec = ambient_precision
                result = self.module._hoeffding_lower_bound(
                    Fraction(1),
                    span=Fraction(1),
                    squared_weight_sum=Fraction(1, 2),
                    tail=Fraction(1, 2),
                )
            self.assertEqual(result["status"], "available")
            radius = Fraction(Decimal(result["radius_upper"]))
            self.assertGreaterEqual(radius * radius, log_upper)
            self.assertLessEqual(radius - sqrt_upper, Fraction(1, 10**70))
            lower = Fraction.from_float(result["lower_bound"])
            self.assertLessEqual(lower, 1 - sqrt_upper)
            self.assertLessEqual((1 - sqrt_upper) - lower, Fraction(1, 10**14))
            self.assertEqual(result["point"], rational(Fraction(1)))
            self.assertIs(result["support_clipped"], False)
        tiny = self.module._hoeffding_lower_bound(
            Fraction(1), span=Fraction(1), squared_weight_sum=Fraction(1), tail=Fraction(1, 2**512)
        )
        self.assertEqual(tiny["status"], "available")
        self.assertEqual(tiny["lower_bound"], -1)
        self.assertIs(tiny["support_clipped"], True)
        tiny_radius = Fraction(Decimal(tiny["radius_upper"]))
        self.assertGreaterEqual(tiny_radius * tiny_radius, 1024 * log_upper)
        zero = self.module._hoeffding_lower_bound(
            Fraction(0), span=Fraction(0), squared_weight_sum=Fraction(1), tail=Fraction(1, 256)
        )
        self.assertEqual(zero["status"], "available")
        self.assertEqual(zero["lower_bound"], 0)
        self.assertEqual(Fraction(Decimal(zero["radius_upper"])), 0)
        for value in (
            Fraction(1, 10),
            Fraction(1, 2),
            Fraction.from_float(math.nextafter(0.5, 1)),
            Fraction(-1, 10),
            Fraction(1, 10**310),
        ):
            downward = self.module._downward_float(value)
            self.assertLessEqual(Fraction.from_float(downward), value)
            if Fraction.from_float(downward) != value:
                self.assertGreater(Fraction.from_float(math.nextafter(downward, math.inf)), value)
        rule = ImprovementRule.from_bytes(
            self.json(
                {
                    "format": "buddha.improvement-rule.v1",
                    "primary_metric": "utility",
                    "minimum_gain": 0.5,
                    "max_other_loss": 0.125,
                }
            )
        )
        for point, other, expected in (
            (Fraction(1, 2), Fraction(-1, 8), "rule_not_satisfied"),
            (Fraction.from_float(math.nextafter(0.5, 1)), Fraction(-1, 8), "rule_satisfied"),
            (
                Fraction.from_float(math.nextafter(0.5, 1)),
                Fraction.from_float(math.nextafter(-0.125, -1)),
                "rule_not_satisfied",
            ),
        ):
            result = evaluate_improvement_rule(
                rule,
                lower_bounds={
                    "utility": self.module._downward_float(point),
                    "distinct": self.module._downward_float(other),
                },
                complete_coverage=True,
            )
            self.assertEqual(result["status"], expected)

    def test_original_plan_owners_native_projection_rule_and_fully_passive_repeat(self):
        from buddha.doctor import _Capture
        from buddha.improvement_rule import evaluate_improvement_rule
        from buddha.releases import inventory

        f, authority = self.fixture()
        original = Path(f.record["analysis_plan"]["path"]).read_bytes()
        dispatch_bindings = []
        worker = f.execute

        def consumed_before_worker(spec, **kwargs):
            owner = kwargs["handle"].__self__.gateway.directory
            manifest = json.loads((owner / "manifest.json").read_bytes())
            pins = {row["path"]: row["sha256"] for row in manifest["invocation"]["inputs"]}
            self.assertEqual((f.directory / "analysis-plan").read_bytes(), original)
            self.assertEqual(pins[str(f.directory / "analysis-plan")], sha(original))
            dispatch_bindings.append(spec.role)
            return worker(spec, **kwargs)

        with (
            f.offline(),
            patch("buddha.executor.run_container", side_effect=consumed_before_worker),
        ):
            complete = f.run_occasion(authority)
        self.assertEqual(len(dispatch_bindings), 8)
        self.assertEqual(f.engine.physical_sends, 6)
        before, authority_raw = inventory(f.directory), authority.path.read_bytes()
        finishes = []
        finish = _Capture.finish

        def finished(capture):
            result = finish(capture)
            finishes.append(result)
            return result

        with (
            self.passive(),
            patch.object(_Capture, "finish", new=finished),
            patch.object(
                self.module, "evaluate_improvement_rule", wraps=evaluate_improvement_rule
            ) as rule,
            patch.object(
                self.module, "_hoeffding_lower_bound", wraps=self.module._hoeffding_lower_bound
            ) as bound,
        ):
            analysis = self.call(f, authority)
            again = self.call(f, authority)
        self.assertEqual(analysis, again)
        self.assertGreaterEqual(len(finishes), 2)
        self.assertEqual(len(analysis["matrix"]), 2)
        self.assertEqual([row["task_id"] for row in analysis["matrix"]], [1, 1])
        self.assertTrue(all(type(row["task_id"]) is int for row in analysis["matrix"]))
        self.assertTrue(
            all((row["utility"], row["distinct"]) == (7.0, 2) for row in analysis["matrix"])
        )
        self.assertEqual(len(analysis["contrasts"]), 1)
        contrast = analysis["contrasts"][0]
        self.assertEqual((contrast["candidate_arm"], contrast["comparator_arm"]), (1, 0))
        self.assertEqual(set(contrast["axes"]), {"utility", "distinct"})
        self.assertEqual(contrast["rule"]["status"], "rule_not_satisfied")
        self.assertIs(contrast["rule"]["complete_coverage"], True)
        for call in rule.call_args_list:
            self.assertEqual(
                call.args[0].to_bytes(), (f.directory / "improvement-rule.json").read_bytes()
            )
            self.assertIs(call.kwargs["complete_coverage"], True)
        self.assertEqual(rule.call_count, 2)
        self.assertEqual(bound.call_count, 4)
        self.assertTrue(
            all(call.kwargs["tail"] == Fraction(1, 128) for call in bound.call_args_list)
        )
        provenance = analysis["provenance"]
        for key, value in {
            "analysis_plan_sha256": sha(original),
            "improvement_rule_sha256": f.record["improvement_rule"]["sha256"],
            "result_sha256": sha((f.directory / "validation/0/result.json").read_bytes()),
            "occasion_sha256": complete["occasion_sha256"],
            "projection_release_sha256": f.engine.candidate.release.fingerprint(),
        }.items():
            self.assertEqual(provenance[key], value)
        with self.passive(), self.assertRaises(self.Error):
            self.call(f, authority, expected_result_sha256="0" * 64)
        plan_copy = f.directory / "analysis-plan"
        plan_copy.write_bytes(original + b" ")
        try:
            with self.passive(), self.assertRaises(self.Error):
                self.call(f, authority)
        finally:
            plan_copy.write_bytes(original)
        with (
            self.passive(),
            patch.object(_Capture, "finish", side_effect=self.Error("finish sentinel")),
            self.assertRaises(self.Error),
        ):
            self.call(f, authority)
        self.assertEqual(inventory(f.directory), before)
        self.assertEqual(authority.path.read_bytes(), authority_raw)

    def test_native_complete_unusable_scalar_keeps_full_matrix_and_inconclusive_contrast(self):
        from buddha.releases import inventory

        f, authority, _ = self.completed(unusable=True)
        before = inventory(f.directory)
        with self.passive():
            analysis = self.call(f, authority)
        self.assertEqual(len(analysis["matrix"]), 2)
        comparator, candidate = analysis["matrix"]
        self.assertEqual(comparator["utility"], 7.0)
        self.assertIsNone(candidate["utility"])
        self.assertIn("utility", candidate["invalid_metrics"])
        self.assertEqual(candidate["distinct"], 2)
        self.assertEqual(len(analysis["contrasts"]), 1)
        contrast = analysis["contrasts"][0]
        self.assertIsNone(contrast["axes"]["utility"]["lower_bound"])
        self.assertEqual(contrast["rule"]["status"], "inconclusive")
        self.assertIs(contrast["rule"]["complete_coverage"], False)
        self.assertEqual(inventory(f.directory), before)

    def test_original_partial_without_complete_result_rejects_without_new_work(self):
        from buddha.releases import inventory

        f, authority = self.fixture()
        with (
            f.offline(),
            patch(
                "buddha.candidate_generation.prepare_candidate_generation",
                side_effect=KeyboardInterrupt,
            ),
            self.assertRaises(KeyboardInterrupt) as interrupted,
        ):
            f.run_occasion(authority)
        partial = interrupted.exception.partial
        path = f.directory / "validation/0" / partial["observation"]
        before, authority_raw = inventory(f.directory), authority.path.read_bytes()
        self.assertFalse((f.directory / "validation/0/result.json").exists())
        with self.passive(), self.assertRaises(self.Error):
            self.analyze(
                f.directory,
                ordinal=0,
                authorization=authority.path,
                expected_result_sha256=sha(path.read_bytes()),
            )
        self.assertEqual(f.engine.workers, 0)
        self.assertEqual(f.engine.physical_sends, 0)
        self.assertEqual(inventory(f.directory), before)
        self.assertEqual(authority.path.read_bytes(), authority_raw)

    def test_original_opaque_plan_returns_unavailable_after_capture_and_cannot_be_retrofitted(self):
        from buddha.doctor import _Capture
        from buddha.releases import inventory

        f, authority, _ = self.completed(opaque=True)
        before, authority_raw = inventory(f.directory), authority.path.read_bytes()
        finishes = []
        finish = _Capture.finish

        def finished(capture):
            result = finish(capture)
            finishes.append(result)
            return result

        with self.passive(), patch.object(_Capture, "finish", new=finished):
            analysis = self.call(f, authority)
        self.assertEqual(analysis["status"], "unavailable")
        self.assertIn("unsupported", json.dumps(analysis).lower())
        self.assertTrue(finishes)
        self.assertFalse(analysis["contrasts"])
        with (
            self.passive(),
            patch.object(_Capture, "finish", side_effect=self.Error("finish sentinel")),
            self.assertRaises(self.Error),
        ):
            self.call(f, authority)
        original = (f.directory / "analysis-plan").read_bytes()
        (f.directory / "analysis-plan").write_bytes(json.dumps(self.plan_record()).encode())
        try:
            with self.passive(), self.assertRaises(self.Error):
                self.call(f, authority)
        finally:
            (f.directory / "analysis-plan").write_bytes(original)
        self.assertEqual(inventory(f.directory), before)
        self.assertEqual(authority.path.read_bytes(), authority_raw)
