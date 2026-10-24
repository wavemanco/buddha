"""Pure fixed-panel paired arithmetic, not native-evidence or source attestation.

Bounds condition on fixed selected descendants and independent bounded family
blocks. Repeated starts/generations add no independent family units. Six lower
tails support simultaneous lower statements, not two-sided regression tests.
"""

from collections import Counter
from collections.abc import Callable
from dataclasses import dataclass
from fractions import Fraction
from functools import wraps
from pathlib import Path
from typing import cast

from buddha import noveltybench_results as projection
from buddha import validation_analysis as bounds
from buddha.answers import _Artifact, _id
from buddha.improvement_rule import ImprovementRule, evaluate_improvement_rule
from buddha.releases import ReleaseError, _digest, _json, _load, _object, _text, file_hash
from buddha.wire import _integer

_AXES = ("utility", "distinct")
_CONTRASTS = {
    "initial_gain": ("initial", "starter"),
    "evolved_gain": ("evolved", "starter"),
    "improver_effect": ("evolved", "initial"),
}
_ROLES = ("initial", "evolved")
_CLAIM = (
    "Numerical fixed-panel conditional bounds only. Input source/custody/release pins and "
    "independent bounded family assumptions are not attested. No promotion, future-search "
    "effectiveness, unseen-task generalization, two-sided regression or human-quality claim."
)


class ImproverAnalysisError(ReleaseError):
    """The prospective paired method or supplied numerical panel is invalid."""


def _checked[**P, T](function: Callable[P, T]) -> Callable[P, T]:
    @wraps(function)
    def checked(*args: P.args, **kwargs: P.kwargs) -> T:
        try:
            return function(*args, **kwargs)
        except (ReleaseError, TypeError, KeyError, ValueError, RecursionError, OverflowError):
            raise ImproverAnalysisError(
                "invalid paired plan, population or numerical panel"
            ) from None

    return checked


def _source_paths() -> dict[str, Path]:
    return bounds._source_paths() | {"buddha/improver_analysis.py": Path(__file__).absolute()}


def _source_hashes() -> dict[str, str]:
    """Explicit preparation helper; numerical analysis itself performs no I/O."""
    return {name: file_hash(path) for name, path in _source_paths().items()}


def _counts(value: object) -> dict[str, int]:
    record = _object(
        value, {"starts", "development_repetitions", "m", "tasks", "sealed_repetitions"}
    )
    result = {name: _integer(value, 1, 100_000) for name, value in record.items()}
    _integer(result["m"], 1, 8)
    cells = (
        3
        * result["starts"]
        * result["development_repetitions"]
        * result["tasks"]
        * result["sealed_repetitions"]
    )
    _integer(cells, 1, projection.MAX_ROWS)
    return result


def _tails(record: dict[str, object]) -> dict[str, dict[str, Fraction]]:
    total = bounds._rational(record["alpha_total"])
    allocation = _object(record["tail_allocations"], set(_CONTRASTS))
    tails = {
        contrast: {
            axis: bounds._rational(value) for axis, value in _object(axes, set(_AXES)).items()
        }
        for contrast, axes in allocation.items()
    }
    values = [value for axes in tails.values() for value in axes.values()]
    if not 0 < total < 1 or any(value <= 0 for value in values) or sum(values) > total:
        raise ImproverAnalysisError("six positive prospective tails must fit total alpha")
    return tails


@dataclass(frozen=True)
class ImproverAnalysisPlan(_Artifact):
    """Immutable supported method data; no silent numerical or population defaults."""

    @_checked
    def __post_init__(self) -> None:
        record = _object(
            _load(self.data),
            {
                "format",
                "method",
                "projection_release_sha256",
                "improvement_rule_sha256",
                "population_sha256",
                "counts",
                "weights",
                "alpha_total",
                "tail_allocations",
                "analyzer_sources",
            },
        )
        if (
            record["format"] != "buddha.improver-analysis-plan.v1"
            or record["method"] != "fixed_panel_family_hoeffding_shared_starter.v1"
            or record["weights"] != "equal_conditions_then_equal_prompts"
        ):
            raise ImproverAnalysisError("unsupported paired method")
        for name in ("projection_release_sha256", "improvement_rule_sha256", "population_sha256"):
            _digest(record[name])
        for digest in _object(record["analyzer_sources"], set(_source_paths())).values():
            _digest(digest)
        _counts(record["counts"])
        _tails(record)
        object.__setattr__(self, "data", _json(record))


def _population(value: object, record: dict[str, object], count: int) -> list[dict[str, object]]:
    population = _object(value, {"format", "taskset_sha256", "custody_sha256", "tasks"})
    if population["format"] != "buddha.improver-analysis-population.v1":
        raise ImproverAnalysisError("unsupported ordered population")
    for key in ("taskset_sha256", "custody_sha256"):
        _digest(population[key])
    if type(population["tasks"]) is not list or len(population["tasks"]) != count:
        raise ImproverAnalysisError("population must retain all declared tasks")
    tasks, ids = [], set()
    for item in population["tasks"]:
        task = _object(item, {"task_id", "family_id", "count"})
        identity = _id(task["task_id"])
        typed = (type(identity), identity)
        if typed in ids:
            raise ImproverAnalysisError("population repeats a typed task ID")
        ids.add(typed)
        _text(task["family_id"])
        projection.metric_support(cast(int, task["count"]))
        tasks.append(task)
    if _Artifact(_json(population)).fingerprint() != record["population_sha256"]:
        raise ImproverAnalysisError("ordered population differs from prospective commitment")
    return tasks


def _slots(value: object, counts: dict[str, int]) -> dict[tuple[int, int, str], str]:
    size = counts["starts"] * counts["development_repetitions"]
    if type(value) is not list or len(value) != 2 * size:
        raise ImproverAnalysisError("exact selected/null descendant slots are required")
    agents: dict[tuple[int, int, str], str] = {}
    starters: dict[int, str] = {}
    improvers: dict[int, str] = {}
    seen = set()
    for item in value:
        slot = _object(
            item,
            {
                "start",
                "repetition",
                "arm",
                "starter_agent_sha256",
                "improver_agent_sha256",
                "status",
                "descendant_agent_sha256",
            },
        )
        start = _integer(slot["start"], 0, counts["starts"] - 1)
        repeat = _integer(slot["repetition"], 0, counts["development_repetitions"] - 1)
        arm = _integer(slot["arm"], 0, 1)
        key = (start, repeat, arm)
        if key in seen:
            raise ImproverAnalysisError("duplicate descendant coordinate")
        seen.add(key)
        starter, improver = (
            _digest(slot["starter_agent_sha256"]),
            _digest(slot["improver_agent_sha256"]),
        )
        if (
            starters.setdefault(start, starter) != starter
            or improvers.setdefault(arm, improver) != improver
        ):
            raise ImproverAnalysisError("starter or fixed improver identity changed")
        agents[start, repeat, "starter"] = starter
        if slot["status"] == "selected":
            agents[start, repeat, _ROLES[arm]] = _digest(slot["descendant_agent_sha256"])
        elif slot["status"] != "no_valid_descendant" or slot["descendant_agent_sha256"] is not None:
            raise ImproverAnalysisError("null selection is explicit and has no substitute source")
    return agents


def _rows(
    value: object,
    agents: dict[tuple[int, int, str], str],
    tasks: list[dict[str, object]],
    repetitions: int,
) -> dict[tuple[int, int, str, int, int], dict[str, Fraction | None]]:
    expected = len(agents) * len(tasks) * repetitions
    if type(value) is not list or len(value) != expected:
        raise ImproverAnalysisError(
            "every executable cell requires an explicit observed/failed row"
        )
    result = {}
    for item in value:
        row = _object(
            item,
            {
                "start",
                "repetition",
                "role",
                "task_index",
                "task_id",
                "family_id",
                "sealed_repetition",
                "agent_sha256",
                "status",
                "utility",
                "distinct",
            },
        )
        prefix = (_integer(row["start"]), _integer(row["repetition"]), _text(row["role"]))
        if prefix not in agents or _digest(row["agent_sha256"]) != agents[prefix]:
            raise ImproverAnalysisError("foreign numerical source/condition")
        index = _integer(row["task_index"], 0, len(tasks) - 1)
        occasion = _integer(row["sealed_repetition"], 0, repetitions - 1)
        task = tasks[index]
        if (
            type(row["task_id"]) is not type(task["task_id"])
            or row["task_id"] != task["task_id"]
            or row["family_id"] != task["family_id"]
        ):
            raise ImproverAnalysisError("numerical task/family differs from ordered population")
        key = (*prefix, index, occasion)
        if key in result or row["status"] not in ("observed", "failed"):
            raise ImproverAnalysisError("duplicate or malformed measurement")
        support = projection.metric_support(cast(int, task["count"]))
        scalars = {}
        for axis in _AXES:
            scalar = bounds._scalar(row[axis])
            low, high = support[axis]
            if scalar is not None and (
                not low <= scalar <= high
                or (axis == "distinct" and type(row[axis]) is not int)
                or row["status"] == "failed"
            ):
                raise ImproverAnalysisError("native scalar violates its support or failure status")
            scalars[axis] = scalar
        result[key] = scalars
    return result


@_checked
def analyze_improver_panel(
    plan: ImproverAnalysisPlan,
    *,
    population: object,
    slots: object,
    rows: object,
    rule: ImprovementRule,
) -> dict[str, object]:
    """Validate all planned cells before arithmetic; never drop incomplete conditions.

    Source hashes name agent identities, not raw candidate.py hashes. Source pins
    are supplied commitments only; a protected original-evidence consumer must
    attest them before treating these numbers as experiment results.
    """
    if type(plan) is not ImproverAnalysisPlan or type(rule) is not ImprovementRule:
        raise ImproverAnalysisError("exact supported plan and rule are required")
    record = plan.to_record()
    if record["improvement_rule_sha256"] != rule.fingerprint():
        raise ImproverAnalysisError("rule differs from prospective commitment")
    # Bound and detach inputs before traversal; caller-owned containers are never mutated.
    supplied = _load(_json({"population": population, "slots": slots, "rows": rows}))
    counts, tails = _counts(record["counts"]), _tails(record)
    tasks = _population(supplied["population"], record, counts["tasks"])
    agents = _slots(supplied["slots"], counts)
    matrix = _rows(supplied["rows"], agents, tasks, counts["sealed_repetitions"])
    conditions = counts["starts"] * counts["development_repetitions"]
    nulls = 3 * conditions - len(agents)
    complete = not nulls and all(
        value is not None for row in matrix.values() for value in row.values()
    )
    families = Counter(cast(str, task["family_id"]) for task in tasks)
    weights = {family: Fraction(number, len(tasks)) for family, number in families.items()}
    square = sum((weight * weight for weight in weights.values()), Fraction())
    spans = {
        axis: max(
            high - low
            for task in tasks
            for low, high in [projection.metric_support(cast(int, task["count"]))[axis]]
        )
        for axis in _AXES
    }
    contrasts: dict[str, dict[str, object]] = {}
    denominator = conditions * len(tasks) * counts["sealed_repetitions"]
    for name, (candidate, comparator) in _CONTRASTS.items():
        axes: dict[str, object] = {}
        for axis in _AXES:
            total, available = Fraction(), True
            for start in range(counts["starts"]):
                for repeat in range(counts["development_repetitions"]):
                    for task in range(len(tasks)):
                        for occasion in range(counts["sealed_repetitions"]):
                            first = matrix.get((start, repeat, candidate, task, occasion), {}).get(
                                axis
                            )
                            second = matrix.get(
                                (start, repeat, comparator, task, occasion), {}
                            ).get(axis)
                            if first is None or second is None:
                                available = False
                            else:
                                total += first - second
            axes[axis] = (
                bounds._hoeffding_lower_bound(
                    total / denominator,
                    span=Fraction(spans[axis]),
                    squared_weight_sum=square,
                    tail=tails[name][axis],
                )
                if available
                else {
                    "point": None,
                    "tail": bounds._ratio(tails[name][axis]),
                    "status": "unavailable",
                    "reason": "incomplete_planned_contrast",
                    "lower_bound": None,
                    "radius_upper": None,
                    "support_clipped": False,
                    "uninformative": True,
                }
            )
        contrasts[name] = axes
    effect = contrasts["improver_effect"]
    lower = {axis: _object(effect[axis])["lower_bound"] for axis in _AXES}
    result = {
        "format": "buddha.improver-analysis-result.v1",
        "plan_sha256": plan.fingerprint(),
        "population_sha256": record["population_sha256"],
        "projection_release_sha256": record["projection_release_sha256"],
        "analyzer_sources": record["analyzer_sources"],
        "counts": counts,
        "coverage": {
            "conditions": conditions,
            "descendant_slots": 2 * conditions,
            "null_slots": nulls,
            "maximum_rows": 3 * denominator,
            "expected_rows": len(matrix),
            "complete": complete,
        },
        "family_weights": {key: bounds._ratio(value) for key, value in weights.items()},
        "squared_weight_sum": bounds._ratio(square),
        "support_spans": spans,
        "alpha_total": record["alpha_total"],
        "tail_allocations": record["tail_allocations"],
        "contrasts": contrasts,
        "rule": evaluate_improvement_rule(rule, lower_bounds=lower, complete_coverage=complete),
        "target_repair": "not_assessed",
        "claim": _CLAIM,
    }
    _json(result)
    return result
