"""Passive prospective fixed-panel analysis of original complete native occasions.

The bound is conditional on the declared independent family-block and bounded
measurement assumptions. It supplies neither promotion nor unseen-task claims.
"""

import math
import sqlite3
from collections import Counter
from collections.abc import Callable
from dataclasses import dataclass
from decimal import (
    MAX_EMAX,
    MIN_EMIN,
    ROUND_CEILING,
    ROUND_FLOOR,
    ROUND_HALF_EVEN,
    Clamped,
    Context,
    Decimal,
    DecimalException,
    DivisionByZero,
    InvalidOperation,
    Overflow,
    Subnormal,
    Underflow,
)
from fractions import Fraction
from functools import wraps
from pathlib import Path
from typing import Any, cast

from buddha import native_pipeline as pipeline
from buddha import noveltybench_results as projection
from buddha import source_screen_results as saved_native
from buddha import validation_study as study
from buddha.answers import _Artifact, _id
from buddha.doctor import _Busy, _Unsupported
from buddha.improvement_rule import evaluate_improvement_rule
from buddha.releases import ReleaseError, _digest, _json, _load, _object, _text, file_hash
from buddha.wire import _integer

_IDENTIFIERS = {
    "format": "buddha.validation-analysis-plan.v1",
    "method": "fixed-panel-family-hoeffding.v1",
    "projection": "noveltybench-1.1",
    "estimand": "fixed-panel-conditional-expected-native-difference",
    "weighting": "equal-prompts",
    "repetition_aggregation": "mean-within-prompt",
    "block": "custody-family",
    "independence": "conditional-independent-family-blocks",
    "score_support_assumption": "well-defined-bounded-native-metrics",
    "judge_policy": "single-native-occasion",
}
_COUNTS = ("max_looks", "max_candidates", "comparator_count", "repetitions", "finalist_count")
_TRANSFER_FORMAT = "buddha.validation-analysis-plan.v2"
_AXES = ("utility", "distinct")
_CLAIM = (
    "Conditional fixed-panel native-metric bounds only; family independence and bounded "
    "measurement assumptions are not verified. No promotion, finalized trial, unseen-task "
    "generalization or human-quality claim."
)


class ValidationAnalysisError(ReleaseError):
    """Prospective analysis inputs or original saved custody are invalid."""


def _checked[**P, T](function: Callable[P, T]) -> Callable[P, T]:
    @wraps(function)
    def checked(*args: P.args, **kwargs: P.kwargs) -> T:
        try:
            return function(*args, **kwargs)
        except (
            ReleaseError,
            ValueError,
            TypeError,
            KeyError,
            OSError,
            RecursionError,
            OverflowError,
            sqlite3.Error,
            _Busy,
            _Unsupported,
        ) as error:
            if isinstance(error, ValidationAnalysisError):
                raise
            raise ValidationAnalysisError(
                "invalid analysis plan or original native evidence"
            ) from None

    return checked


def _source_paths() -> dict[str, Path]:
    paths = [*study._sources(), Path(__file__).absolute(), Path(projection.__file__).absolute()]
    return {"buddha/" + path.name: path for path in paths}


def _source_hashes() -> dict[str, str]:
    """Exact installed trusted closure for inclusion in an original prospective plan."""
    return {name: file_hash(path) for name, path in _source_paths().items()}


def _rational(value: object) -> Fraction:
    record = _object(value, {"numerator", "denominator"})
    numerator, denominator = record["numerator"], record["denominator"]
    if type(numerator) is not int or type(denominator) is not int or denominator <= 0:
        raise ValidationAnalysisError(
            "rational budgets require literal integer numerator/denominator"
        )
    return Fraction(numerator, denominator)


def _ratio(value: Fraction) -> dict[str, int]:
    return {"numerator": value.numerator, "denominator": value.denominator}


def _tails(record: dict[str, object]) -> dict[str, Fraction]:
    phases = {"validation", "final"}
    if record.get("format") == _TRANSFER_FORMAT:
        phases.add("transfer")
    alpha = _object(record["alpha"], {"total"} | phases)
    portions = {name: _rational(value) for name, value in alpha.items()}
    if not (
        0 < portions["total"] < 1
        and all(portions[phase] > 0 for phase in phases)
        and sum(portions[phase] for phase in phases) <= portions["total"]
    ):
        raise ValidationAnalysisError("positive allocated alpha must fit the original total")
    validation = portions["validation"] / (
        2
        * _integer(record["max_looks"], 1)
        * _integer(record["max_candidates"], 1)
        * _integer(record["comparator_count"], 1)
    )
    final = portions["final"] / (
        2 * _integer(record["finalist_count"], 1) * _integer(record["comparator_count"], 1)
    )
    result = {"validation": validation, "final": final}
    if "transfer" in phases:
        result["transfer"] = portions["transfer"] / (
            2 * _integer(record["finalist_count"], 1) * _integer(record["comparator_count"], 1)
        )
    _json({name: _ratio(value) for name, value in result.items()})
    return result


@dataclass(frozen=True)
class ValidationAnalysisPlan(_Artifact):
    """Canonical immutable prospective method data; no reads or numerical defaults."""

    def __post_init__(self) -> None:
        try:
            raw_record = _object(_load(self.data))
            transfer = raw_record.get("format") == _TRANSFER_FORMAT
            record = _object(
                raw_record,
                set(_IDENTIFIERS)
                | set(_COUNTS)
                | {
                    "alpha",
                    "improvement_rule_sha256",
                    "projection_release_sha256",
                    "analyzer_sources",
                }
                | (
                    {"transfer_projection_release_sha256", "transfer_repetitions"}
                    if transfer
                    else set()
                ),
            )
            if any(
                type(record[key]) is not str
                or record[key] != (_TRANSFER_FORMAT if key == "format" and transfer else value)
                for key, value in _IDENTIFIERS.items()
            ):
                raise ValidationAnalysisError("unsupported prospective analysis semantics")
            for key in _COUNTS:
                _integer(record[key], 1)
            for key in ("improvement_rule_sha256", "projection_release_sha256"):
                _digest(record[key])
            if transfer:
                _digest(record["transfer_projection_release_sha256"])
                _integer(record["transfer_repetitions"], 1)
            sources = _object(record["analyzer_sources"], set(_source_paths()))
            for digest in sources.values():
                _digest(digest)
            _tails(record)
            canonical = _json(record)
        except (ReleaseError, ValueError, TypeError, RecursionError, OverflowError):
            raise ValidationAnalysisError("invalid prospective analysis plan") from None
        object.__setattr__(self, "data", canonical)


def _fraction(value: object) -> Fraction:
    if type(value) is not Fraction:
        raise ValidationAnalysisError("numeric kernel requires exact literal Fractions")
    return value


def _downward_float(value: Fraction) -> float:
    """Export one finite float no greater than the exact rational, with postcheck."""
    value = _fraction(value)
    try:
        result = float(value)
        if not math.isfinite(result):
            raise ValueError("nonfinite export")
        if Fraction.from_float(result) > value:
            result = math.nextafter(result, -math.inf)
        if not math.isfinite(result) or Fraction.from_float(result) > value:
            raise ValueError("unsupported rounding")
    except (ValueError, OverflowError):
        raise ValidationAnalysisError("cannot export a conservative finite lower bound") from None
    return result


def _context(rounding: str) -> Context:
    # Explicit isolated settings; expected Inexact/Rounded do not invalidate enclosures.
    return Context(
        prec=80,
        rounding=rounding,
        Emin=MIN_EMIN,
        Emax=MAX_EMAX,
        capitals=1,
        clamp=0,
        flags=[],
        traps=[InvalidOperation, DivisionByZero, Overflow, Underflow, Subnormal, Clamped],
    )


def _hoeffding_lower_bound(
    point: Fraction, *, span: Fraction, squared_weight_sum: Fraction, tail: Fraction
) -> dict[str, object]:
    """Directed lower bound; private arithmetic alone attests no scientific evidence."""
    point, span = _fraction(point), _fraction(span)
    weight, tail = _fraction(squared_weight_sum), _fraction(tail)
    if span < 0 or not 0 < weight <= 1 or not 0 < tail < 1 or not -span <= point <= span:
        raise ValidationAnalysisError("numeric bound inputs violate their declared supports")
    base: dict[str, object] = {"point": _ratio(point), "tail": _ratio(tail)}
    try:
        _json(base)
    except ReleaseError:
        raise ValidationAnalysisError("numeric provenance must fit bounded JSON") from None
    try:
        if span == 0:
            radius, lower, clipped = Decimal(0), Fraction(0), False
        else:
            near, up, down = (
                _context(mode) for mode in (ROUND_HALF_EVEN, ROUND_CEILING, ROUND_FLOOR)
            )

            def log_neighbors(integer: int) -> tuple[Decimal, Decimal]:
                if integer == 1:
                    return Decimal(0), Decimal(0)
                nearest = Decimal(integer).ln(context=near)
                return nearest.next_minus(context=near), nearest.next_plus(context=near)

            p_lo, _ = log_neighbors(tail.numerator)
            _, q_hi = log_neighbors(tail.denominator)
            log_up = up.subtract(q_hi, p_lo)
            if not log_up.is_finite() or log_up <= 0:
                raise ArithmeticError("log enclosure unavailable")
            coefficient = 2 * span * span * weight
            coefficient_up = up.divide(
                Decimal(coefficient.numerator), Decimal(coefficient.denominator)
            )
            if Fraction(coefficient_up) < coefficient:
                raise ArithmeticError("coefficient enclosure unavailable")
            square_up = up.multiply(coefficient_up, log_up)
            radius = square_up.sqrt(context=near).next_plus(context=near)
            if not radius.is_finite() or radius < 0 or Fraction(radius) ** 2 < Fraction(square_up):
                raise ArithmeticError("root enclosure unavailable")
            point_down = down.divide(Decimal(point.numerator), Decimal(point.denominator))
            if Fraction(point_down) > point:
                raise ArithmeticError("point enclosure unavailable")
            bound = Fraction(down.subtract(point_down, radius))
            clipped = bound < -span
            lower = max(-span, bound)
        result = base | {
            "status": "available",
            "reason": None,
            "lower_bound": _downward_float(lower),
            "radius_upper": str(radius),
            "support_clipped": clipped,
            "uninformative": lower == -span,
        }
        _json(result)
        return result
    except (DecimalException, ArithmeticError, ReleaseError, ValueError, OverflowError):
        return base | {
            "status": "unavailable",
            "reason": "conservative_numeric_path_unavailable",
            "lower_bound": None,
            "radius_upper": None,
            "support_clipped": False,
            "uninformative": True,
        }


def _scalar(value: object) -> Fraction | None:
    if value is None:
        return None
    if type(value) is int:
        return Fraction(value)
    if type(value) is float and math.isfinite(value):
        return Fraction.from_float(value)
    raise ValidationAnalysisError("matrix scalars require literal finite saved numbers")


@_checked
def _aggregate_contrast(
    matrix: list[dict[str, object]], *, candidate_arm: int, comparator_arm: int, repetitions: int
) -> dict[str, Any]:
    """Pair all sets within fixed prompts/families; the caller verifies full custody."""
    candidate_arm, comparator_arm = _integer(candidate_arm), _integer(comparator_arm)
    repetitions = _integer(repetitions, 1)
    if candidate_arm == comparator_arm or type(matrix) is not list:
        raise ValidationAnalysisError("contrast requires different arms and ordered rows")
    selected: dict[tuple[int, int, int], dict[str, object]] = {}
    tasks: dict[int, tuple[str | int, str]] = {}
    for row in matrix:
        row = _object(row)
        arm = _integer(row["arm_index"])
        if arm not in (candidate_arm, comparator_arm):
            continue
        task, repeat = _integer(row["task_index"]), _integer(row["repetition"])
        identity = (_id(row["task_id"]), _text(row["family_id"]))
        if tasks.setdefault(task, identity) != identity or repeat >= repetitions:
            raise ValidationAnalysisError("contrast changes prompt/family or repetition identity")
        key = (arm, task, repeat)
        if key in selected:
            raise ValidationAnalysisError("contrast repeats a matrix cell")
        selected[key] = row
    if not tasks or set(tasks) != set(range(len(tasks))):
        raise ValidationAnalysisError("contrast requires an ordered nonempty prompt population")
    if len({identity[0] for identity in tasks.values()}) != len(tasks):
        raise ValidationAnalysisError("contrast repeats a typed prompt ID")
    counts = Counter(identity[1] for identity in tasks.values())
    weights = {family: Fraction(count, len(tasks)) for family, count in counts.items()}
    square = sum((value * value for value in weights.values()), Fraction())
    complete = len(selected) == 2 * len(tasks) * repetitions
    totals = {axis: Fraction() for axis in _AXES}
    valid = dict.fromkeys(_AXES, complete)
    for (arm, _, _), row in selected.items():
        invalid = row["invalid_metrics"]
        if type(invalid) is not list or any(value not in _AXES for value in invalid):
            raise ValidationAnalysisError("matrix invalid-metric markers are malformed")
        for axis in _AXES:
            value = _scalar(row[axis])
            if value is None or axis in invalid:
                valid[axis] = False
            else:
                totals[axis] += value if arm == candidate_arm else -value
    return {
        "points": {
            axis: totals[axis] / (len(tasks) * repetitions) if valid[axis] else None
            for axis in _AXES
        },
        "family_weights": weights,
        "squared_weight_sum": square,
        "complete": complete and all(valid.values()),
    }


def _supported_plan(raw: bytes) -> ValidationAnalysisPlan | None:
    # Opaque historical plans are not repaired or interpreted by marker sniffing.
    try:
        record = _load(raw)
    except ReleaseError:
        return None
    if record.get("format") not in {_IDENTIFIERS["format"], _TRANSFER_FORMAT}:
        return None
    if record.get("method") not in (None, _IDENTIFIERS["method"]) or record.get(
        "projection"
    ) not in (None, _IDENTIFIERS["projection"]):
        return None
    return ValidationAnalysisPlan.from_bytes(raw)


@_checked
def analyze_validation_occasion(
    directory: Path, *, ordinal: int, authorization: Path, expected_result_sha256: str
) -> dict[str, object]:
    """Read one pinned complete original occasion without active owners or writes."""
    directory, authorization = study._absolute(str(directory)), study._absolute(str(authorization))
    ordinal, expected_result_sha256 = _integer(ordinal), _digest(expected_result_sha256)
    state = study._state(directory)
    slots = study._slots(state)
    if ordinal >= len(slots):
        raise ValidationAnalysisError("analysis occasion was never originally reserved")
    reader, current = study._census(state, slots, authorization)
    saved = study._saved_results(state, slots, reader, current)
    if ordinal not in saved:
        raise ValidationAnalysisError("analysis requires an original complete native result")
    occasion = slots[ordinal]
    result_path = directory / "validation" / str(ordinal) / "result.json"
    reader.raw(result_path, expected_result_sha256)
    for path, digest in state["controls"].items():
        reader.raw(path, digest)
    raw_plan = reader.raw(directory / "analysis-plan")
    provenance = {
        "declaration_sha256": state["declaration_sha256"],
        "occasion_sha256": pipeline._sha(occasion),
        "result_sha256": expected_result_sha256,
        "analysis_plan_sha256": study._sha(raw_plan),
        "improvement_rule_sha256": state["rule"].fingerprint(),
        "projection_release_sha256": reader.release.fingerprint(),
        "tasks_sha256": state["tasks"].fingerprint(),
        "upstream": reader.release.to_record()["upstream"],
        "official_source": reader.release.to_record()["source"],
        "authorization": saved[ordinal]["authorization"],
    }
    plan = _supported_plan(raw_plan)
    if plan is None:
        result: dict[str, object] = {
            "format": "buddha.validation-analysis.v1",
            "status": "unavailable",
            "reason": "unsupported_original_analysis_plan",
            "matrix": [],
            "contrasts": [],
            "provenance": provenance,
            "claim": _CLAIM,
        }
        _json(result)
        reader.capture.finish()
        return result
    record = plan.to_record()
    expected_counts = {
        key: state["record"][key] for key in ("max_looks", "max_candidates", "repetitions")
    }
    expected_counts["comparator_count"] = len(state["comparators"])
    if any(record[key] != value for key, value in expected_counts.items()) or (
        record["improvement_rule_sha256"] != state["rule"].fingerprint()
        or record["projection_release_sha256"] != reader.release.fingerprint()
    ):
        raise ValidationAnalysisError("prospective analysis differs from original study bindings")
    for name, digest in _object(record["analyzer_sources"]).items():
        reader.raw(_source_paths()[name], _digest(digest))
    provenance.update(
        analysis_plan_canonical_sha256=plan.fingerprint(),
        analyzer_sources=record["analyzer_sources"],
    )
    artifacts = _object(reader.release.to_record()["artifacts"])
    results = cast(list[str], artifacts["results"])
    projection.reporting_configuration(reader.release, state["record"]["stages"])
    custody = {row["task_id"]: row for row in state["custody"]["population"]}
    spans = {axis: Fraction() for axis in _AXES}
    matrix: list[dict[str, object]] = []
    for arm, task_index, identifier, repetition, location in study._cells(state, occasion):
        report, source = study._generation(state, occasion, reader, arm, identifier, location)
        if source is None:
            raise ValidationAnalysisError("complete native result has no original source C1")
        available, _, _ = saved_native._native(
            reader, state["record"], source, _object(report["source_generation"]), location, current
        )
        projected = projection.project_rows(
            source.tasks,
            source.answers,
            reader.raw(available[results[0]]),
            reader.raw(available[results[1]]),
        )
        if len(projected) != 1 or projected[0]["task_id"] != identifier:
            raise ValidationAnalysisError("native projection changed the original cell population")
        task = source.tasks.tasks[0]
        support = projection.metric_support(task.count)
        for axis, (low, high) in support.items():
            spans[axis] = max(spans[axis], Fraction(high - low))
        member = custody[identifier]
        matrix.append(
            projected[0]
            | {
                "arm_index": arm["arm_index"],
                "task_index": task_index,
                "repetition": repetition,
                "family_id": member["family_id"],
                "source": member["source"],
                "task_type": member["task_type"],
                "answer_count": task.count,
                "generation_report_sha256": study._sha(
                    reader.raw(location / "generation/report.json")
                ),
                "native_report_sha256": study._sha(reader.raw(location / "evaluation/report.json")),
            }
        )
    tail = _tails(record)["validation"]
    contrasts: list[dict[str, object]] = []
    for candidate in occasion["arms"]:
        if candidate["role"] != "candidate":
            continue
        for comparator in occasion["arms"]:
            if comparator["role"] != "comparator":
                continue
            aggregate = _aggregate_contrast(
                matrix,
                candidate_arm=candidate["arm_index"],
                comparator_arm=comparator["arm_index"],
                repetitions=occasion["repetitions"],
            )
            axes: dict[str, dict[str, object]] = {}
            for axis in _AXES:
                point = aggregate["points"][axis]
                axes[axis] = (
                    {
                        "status": "unavailable",
                        "reason": "required_native_scalar_missing",
                        "lower_bound": None,
                        "radius_upper": None,
                        "point": None,
                        "support_clipped": False,
                        "uninformative": True,
                        "tail": _ratio(tail),
                    }
                    if point is None
                    else _hoeffding_lower_bound(
                        point,
                        span=spans[axis],
                        squared_weight_sum=aggregate["squared_weight_sum"],
                        tail=tail,
                    )
                )
            contrasts.append(
                {
                    "candidate_arm": candidate["arm_index"],
                    "comparator_arm": comparator["arm_index"],
                    "axes": axes,
                    "prompt_weight": _ratio(Fraction(1, len(occasion["selected_ids"]))),
                    "family_weights": {
                        key: _ratio(value) for key, value in aggregate["family_weights"].items()
                    },
                    "squared_weight_sum": _ratio(aggregate["squared_weight_sum"]),
                    "support_spans": {key: _ratio(value) for key, value in spans.items()},
                    "rule": evaluate_improvement_rule(
                        state["rule"],
                        lower_bounds={axis: axes[axis]["lower_bound"] for axis in _AXES},
                        complete_coverage=aggregate["complete"],
                    ),
                }
            )
    result = {
        "format": "buddha.validation-analysis.v1",
        "status": "analyzed",
        "matrix": matrix,
        "contrasts": contrasts,
        "provenance": provenance,
        "allocation": {name: _ratio(value) for name, value in _tails(record).items()},
        "method": {key: record[key] for key in _IDENTIFIERS},
        "claim": _CLAIM,
    }
    _json(result)
    reader.capture.finish()
    return result
