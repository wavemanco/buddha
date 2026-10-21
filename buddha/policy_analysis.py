"""Descriptive protocol arithmetic over already verified native observations.

This function does not verify observation provenance or implement benchmark math.
Ordinal zero remains primary; an incomplete matrix cannot yield a headline mean.
"""

import math
from typing import cast

from buddha.answers import _id
from buddha.policy_study import PolicyStudy
from buddha.releases import ReleaseError, _object


class PolicyResultsError(ReleaseError):
    """An assessment contradicts the declared study or its record schema."""


MAX_ASSESSMENTS = 100_000
_CONTRASTS = (
    "child_regenerate",
    "child_in_context",
    "history_empty",
    "history_child",
    "interaction",
)
_FIELDS = {
    "task_id",
    "arm_index",
    "generation_repeat",
    "judge_occasion",
    "distinct",
    "utility",
    "status",
}
_LIMITATIONS = [
    "Descriptive development comparison only; no winner, promotion or significance claim.",
    "Prompt means have equal weight; answers and judging occasions are not independent samples.",
    "Ordinal-zero judgments are primary even when missing; later occasions never replace them.",
    "Observation provenance and native parser, repair, cost and supplemental review "
    "require separate evidence.",
    "Fixed model access and ceilings do not establish matched actual-token superiority "
    "or held-out improvement.",
]


def _index(value: object, ceiling: int) -> int:
    if type(value) is not int or not 0 <= value < ceiling:
        raise PolicyResultsError("assessment index differs from the study")
    return value


def _metric(value: object, name: str, count: int) -> int | float | None:
    if name == "distinct":
        return value if type(value) is int and 1 <= value <= count else None
    if type(value) in (int, float):
        number = cast(int | float, value)
        if 0 <= number <= 10 and math.isfinite(number):
            return number
    return None


def _contrasts(means: list[float | None]) -> dict[str, float | None]:
    result: dict[str, float | None] = {}
    for name, (left, right) in zip(_CONTRASTS[:4], ((2, 0), (3, 1), (1, 0), (3, 2)), strict=True):
        a, b = means[left], means[right]
        result[name] = None if a is None or b is None else a - b
    first, second = result["child_in_context"], result["child_regenerate"]
    result["interaction"] = None if first is None or second is None else first - second
    return result


def analyze_metrics(study: PolicyStudy, assessments: list[dict[str, object]]) -> dict[str, object]:
    """Retain the complete declared matrix and compute fixed ordinal-zero contrasts.

    Missing/non-numeric metrics are numerical incompleteness, not zero scores.
    Coordinate/schema contradictions are typed errors. The caller must establish
    native evidence and protocol identity before supplying these observations.
    A matrix above MAX_ASSESSMENTS is rejected, never sampled or truncated.
    """
    try:
        if not isinstance(study, PolicyStudy) or type(assessments) is not list:
            raise PolicyResultsError("analysis requires a study and assessment list")
        record = study.to_record()
        tasks = study.tasks.tasks
        known = {task.id: task.count for task in tasks}
        repeats = cast(int, record["generation_repeats"])
        occasions = cast(int, record["judge_occasions"])
        expected = len(tasks) * 4 * repeats * occasions
        if expected > MAX_ASSESSMENTS:
            raise PolicyResultsError("declared assessment matrix exceeds the analysis ceiling")
        if len(assessments) > expected:
            raise PolicyResultsError("assessment population exceeds the study")
        observed: dict[tuple[str | int, int, int, int], dict[str, object]] = {}
        for value in assessments:
            row = _object(value, _FIELDS)
            identifier = _id(row["task_id"])
            if identifier not in known:
                raise PolicyResultsError(
                    "assessment task is outside the selected development population"
                )
            arm = _index(row["arm_index"], 4)
            repeat = _index(row["generation_repeat"], repeats)
            occasion = _index(row["judge_occasion"], occasions)
            key = identifier, arm, repeat, occasion
            if key in observed:
                raise PolicyResultsError("assessment coordinates repeat")
            if type(row["status"]) is not str or row["status"] not in {"observed", "missing"}:
                raise PolicyResultsError("assessment status is unknown")
            if row["status"] == "missing" and (
                row["distinct"] is not None or row["utility"] is not None
            ):
                raise PolicyResultsError("missing assessments cannot contain metrics")
            invalid = []
            checked: dict[str, object] = {
                "task_id": identifier,
                "arm_index": arm,
                "generation_repeat": repeat,
                "judge_occasion": occasion,
                "status": row["status"],
            }
            for name in ("distinct", "utility"):
                number = _metric(row[name], name, known[identifier])
                checked[name] = number
                if row["status"] == "observed" and number is None:
                    invalid.append(name)
            checked["invalid_metrics"] = invalid
            observed[key] = checked

        matrix = []
        for task in tasks:
            for arm in range(4):
                for repeat in range(repeats):
                    for occasion in range(occasions):
                        key = task.id, arm, repeat, occasion
                        matrix.append(
                            observed.get(
                                key,
                                {
                                    "task_id": task.id,
                                    "arm_index": arm,
                                    "generation_repeat": repeat,
                                    "judge_occasion": occasion,
                                    "distinct": None,
                                    "utility": None,
                                    "status": "missing",
                                    "invalid_metrics": [],
                                },
                            )
                        )
        usable = sum(row["status"] == "observed" and not row["invalid_metrics"] for row in matrix)
        primary = []
        for task in tasks:
            diagnostic: dict[str, object] = {"task_id": task.id}
            for name in ("distinct", "utility"):
                means: list[float | None] = []
                for arm in range(4):
                    values = [
                        observed.get((task.id, arm, repeat, 0), {}).get(name)
                        for repeat in range(repeats)
                    ]
                    means.append(
                        None
                        if any(value is None for value in values)
                        else sum(cast(list[int | float], values)) / repeats
                    )
                diagnostic[name] = {"arm_means": means, "contrasts": _contrasts(means)}
            primary.append(diagnostic)
        mean_contrasts: dict[str, object] | None = None
        if usable == expected:
            mean_contrasts = {}
            for name in ("distinct", "utility"):
                maps = [_object(_object(row[name])["contrasts"]) for row in primary]
                mean_contrasts[name] = {
                    contrast: sum(cast(float, values[contrast]) for values in maps) / len(tasks)
                    for contrast in _CONTRASTS
                }
        return {
            "format": "buddha.policy-analysis.v1",
            "study_sha256": study.fingerprint(),
            "status": "complete" if usable == expected else "incomplete",
            "coverage": {
                "expected": expected,
                "observed": sum(row["status"] == "observed" for row in matrix),
                "usable": usable,
            },
            "assessments": matrix,
            "primary": primary,
            "mean_contrasts": mean_contrasts,
            "limitations": list(_LIMITATIONS),
        }
    except (ReleaseError, TypeError, ValueError, OverflowError):
        raise PolicyResultsError("assessment records differ from the declared study") from None
