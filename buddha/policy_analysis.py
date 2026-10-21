"""Descriptive protocol arithmetic over already verified native observations.

This function does not verify observation provenance or implement benchmark math.
Ordinal zero remains primary; an incomplete matrix cannot yield a headline mean.
"""

import math
from copy import deepcopy
from typing import cast

from buddha.answers import Task, _id, _population, _source
from buddha.policy_study import PolicyStudy
from buddha.releases import ReleaseError, _digest, _json, _object, _text


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


MAX_RELATIONS = 1_000_000
_RECOVERY_FIELDS = ("repair_attempts", "lenient", "fallback_judge", "fallback_calls", "unscored")


def _report_range(values: list[object], planned: int) -> dict[str, object]:
    available = cast(list[int | float], [value for value in values if value is not None])
    span = [min(available), max(available)] if available else None
    return {
        "planned": planned,
        "available": len(available),
        "available_range": span,
        "complete_range": list(span) if span is not None and len(available) == planned else None,
    }


def _report_analysis(study: PolicyStudy, value: object) -> dict[str, object]:
    analysis = _object(value)
    rows = analysis["assessments"]
    if type(rows) is not list:
        raise PolicyResultsError("reporting requires the complete assessment grid")
    expected = analyze_metrics(study, [{key: _object(row)[key] for key in _FIELDS} for row in rows])
    # A final-publication failure may conservatively mark a fully observed grid incomplete.
    if analysis.get("status") == "incomplete" and analysis.get("mean_contrasts") is None:
        expected.update(status="incomplete", mean_contrasts=None)
    if _json(analysis) != _json(expected):
        raise PolicyResultsError("reporting analysis differs from its declared study")
    return expected


def _report_partition(value: object, count: int, distinct: object) -> list[int] | None:
    if value is None:
        return None
    if (
        type(value) is not list
        or len(value) != count
        or any(type(label) is not int or label < 0 for label in value)
    ):
        raise PolicyResultsError("reporting partition has invalid original-position labels")
    if distinct is not None and len(set(value)) != distinct:
        raise PolicyResultsError("reporting partition contradicts its saved distinct count")
    return list(value)


def _report_projections(
    occasions: object,
    schedule: list[dict[str, object]],
    tasks: list[Task],
    matrix: dict[tuple[str | int, int, int, int], dict[str, object]],
) -> dict[tuple[str | int, int, int, int], dict[str, object]]:
    if type(occasions) is not list:
        raise PolicyResultsError("reporting requires the verified occasion list")
    cells = {cell["cell_id"]: cell for cell in schedule}
    seen: set[tuple[str, str]] = set()
    sources: dict[str, bytes] = {}
    result: dict[tuple[str | int, int, int, int], dict[str, object]] = {}
    for value in occasions:
        occasion = _object(
            value,
            {"cell_id", "occasion_id", "source_generation", "report_sha256", "summary", "rows"},
        )
        cell_id, occasion_id = _digest(occasion["cell_id"]), _digest(occasion["occasion_id"])
        if cell_id not in cells or (cell_id, occasion_id) in seen:
            raise PolicyResultsError("reporting occasion repeats or changes a scheduled cell")
        cell = cells[cell_id]
        plans = cast(list[dict[str, object]], cell["judge_occasions"])
        matches = [plan for plan in plans if plan["occasion_id"] == occasion_id]
        if len(matches) != 1:
            raise PolicyResultsError("reporting occasion is outside its scheduled cell")
        seen.add((cell_id, occasion_id))
        source = _object(
            occasion["source_generation"],
            {
                "baseline_directory",
                "stage_seal_sha256",
                "owner_manifest_sha256",
                "owner_ledger_sha256",
            },
        )
        _text(source["baseline_directory"])
        for field in ("stage_seal_sha256", "owner_manifest_sha256", "owner_ledger_sha256"):
            _digest(source[field])
        encoded = _json(source)
        if sources.setdefault(cell_id, encoded) != encoded:
            raise PolicyResultsError("reporting occasions change their original answer source")
        _digest(occasion["report_sha256"])
        summary = _object(occasion["summary"], {"path", "sha256"})
        _text(summary["path"])
        _digest(summary["sha256"])
        rows = occasion["rows"]
        if type(rows) is not list or len(rows) != len(tasks):
            raise PolicyResultsError("reporting occasion omits its ordered task population")
        for task, row in zip(tasks, rows, strict=True):
            record = _object(
                row, {"task_id", "distinct", "utility", "invalid_metrics", "diagnostics"}
            )
            identifier = _id(record["task_id"])
            if _json(identifier) != _json(task.id):
                raise PolicyResultsError("reporting projection changes ordered typed task identity")
            key = (
                identifier,
                cast(int, cell["arm_index"]),
                cast(int, cell["generation_repeat"]),
                cast(int, matches[0]["index"]),
            )
            measurement = matrix[key]
            if measurement["status"] != "observed" or any(
                _json(record[field]) != _json(measurement[field])
                for field in ("distinct", "utility", "invalid_metrics")
            ):
                raise PolicyResultsError("reporting projection contradicts its scalar assessment")
            diagnostic = _object(record["diagnostics"])
            _json(diagnostic)
            partition = _object(diagnostic.get("partition", {}))
            _object(diagnostic.get("score", {}))
            result[key] = {
                "diagnostics": diagnostic,
                "partition": _report_partition(
                    partition.get("partition"), task.count, record["distinct"]
                ),
            }
    if any(row["status"] == "observed" and key not in result for key, row in matrix.items()):
        raise PolicyResultsError("observed scalar assessment lacks its verified occasion")
    return result


def _report_comparison(
    first: dict[str, object],
    later: dict[str, object],
    count: int,
) -> dict[str, object]:
    metrics = {}
    for name in ("distinct", "utility"):
        missing = [
            f"missing_judgment:{row['index']}"
            if row["status"] == "missing"
            else f"unusable_{name}:{row['index']}"
            for row in (first, later)
            if row[name] is None
        ]
        left, right = cast(int | float, first[name]), cast(int | float, later[name])
        metrics[name] = {
            "delta": None if missing else right - left,
            "range": None if missing else [min(left, right), max(left, right)],
            "missing_reasons": missing,
        }
    planned = count * (count - 1) // 2
    absent = [
        f"missing_judgment:{row['index']}"
        if row["status"] == "missing"
        else f"partition_not_recorded:{row['index']}"
        for row in (first, later)
        if row["partition"] is None
    ]
    changes = []
    if absent:
        relations: dict[str, object] = {
            "planned_pairs": planned,
            "compared_pairs": 0,
            "agree": None,
            "disagree": None,
            "changed_pairs": None,
            "missing_reasons": absent,
        }
    else:
        a, b = cast(list[int], first["partition"]), cast(list[int], later["partition"])
        for left in range(count):
            for right in range(left + 1, count):
                old, new = a[left] == a[right], b[left] == b[right]
                if old != new:
                    changes.append(
                        {
                            "left": left,
                            "right": right,
                            "reference": "equivalent" if old else "distinct",
                            "comparison": "equivalent" if new else "distinct",
                        }
                    )
        relations = {
            "planned_pairs": planned,
            "compared_pairs": planned,
            "agree": planned - len(changes),
            "disagree": len(changes),
            "changed_pairs": changes,
            "missing_reasons": [],
        }
    return {"reference": 0, "occasion": later["index"], "metrics": metrics, "relations": relations}


def describe_observations(
    study: PolicyStudy,
    analysis: dict[str, object],
    occasions: list[dict[str, object]],
) -> dict[str, object]:
    """Describe existing observations; never create a score or replace missing J0.

    Category assessment denominators are J0 task x four arms x generation repeats.
    Observed tasks have any observed J0 row; complete_observed_tasks have all J0
    rows, and usable_tasks have both metrics usable in all those planned rows.
    Available ranges are diagnostics; complete ranges require their entire local
    planned denominator. Relation counts are dependent descriptions, not accuracy.
    """
    try:
        if not isinstance(study, PolicyStudy):
            raise PolicyResultsError("reporting requires an immutable declared study")
        record = study.to_record()
        repeats, judgments = (
            cast(int, record["generation_repeats"]),
            cast(int, record["judge_occasions"]),
        )
        release, raw = _source(_object(record["source"]))
        population = _population(release, raw)
        tasks = [
            population[_id(identifier)][0]
            for identifier in cast(list[object], record["selected_ids"])
        ]
        if len(tasks) * 4 * repeats * judgments > MAX_ASSESSMENTS:
            raise PolicyResultsError("reporting assessment matrix exceeds its ceiling")
        planned_relations = (
            sum(task.count * (task.count - 1) // 2 for task in tasks)
            * 4
            * repeats
            * (judgments - 1)
        )
        if planned_relations > MAX_RELATIONS:
            raise PolicyResultsError("planned relation comparisons exceed the reporting ceiling")
        checked = _report_analysis(study, analysis)
        measurements = cast(list[dict[str, object]], checked["assessments"])
        matrix = {
            (
                _id(row["task_id"]),
                cast(int, row["arm_index"]),
                cast(int, row["generation_repeat"]),
                cast(int, row["judge_occasion"]),
            ): row
            for row in measurements
        }
        schedule = study.schedule()
        projected = _report_projections(occasions, schedule, tasks, matrix)
        primary = {
            _id(row["task_id"]): row for row in cast(list[dict[str, object]], checked["primary"])
        }
        descriptions = []
        categories: dict[str | None, list[str | int]] = {}
        for task in tasks:
            category = population[task.id][1].get("category")
            if category is not None and type(category) is not str:
                raise PolicyResultsError("source category is not literal text or unknown")
            label = category
            categories.setdefault(label, []).append(task.id)
            descriptions.append({"task_id": task.id, "category": label, "prompt": task.prompt})
        repetitions = []
        for task in tasks:
            for arm in range(4):
                values = []
                for repeat in range(repeats):
                    row = matrix[task.id, arm, repeat, 0]
                    values.append(
                        {
                            "generation_repeat": repeat,
                            **{
                                k: deepcopy(row[k])
                                for k in ("distinct", "utility", "status", "invalid_metrics")
                            },
                        }
                    )
                repetitions.append(
                    {
                        "task_id": task.id,
                        "arm_index": arm,
                        "values": values,
                        "means": {
                            name: cast(list[object], _object(primary[task.id][name])["arm_means"])[
                                arm
                            ]
                            for name in ("distinct", "utility")
                        },
                    }
                )
        category_rows = []
        for category, identifiers in categories.items():
            group = [
                [
                    matrix[identifier, arm, repeat, 0]
                    for arm in range(4)
                    for repeat in range(repeats)
                ]
                for identifier in identifiers
            ]
            coverage = {
                "planned_tasks": len(identifiers),
                "observed_tasks": sum(
                    any(row["status"] == "observed" for row in rows) for rows in group
                ),
                "complete_observed_tasks": sum(
                    all(row["status"] == "observed" for row in rows) for rows in group
                ),
                "usable_tasks": sum(
                    all(row["status"] == "observed" and not row["invalid_metrics"] for row in rows)
                    for rows in group
                ),
                "planned_assessments": len(identifiers) * 4 * repeats,
                "observed_assessments": sum(
                    row["status"] == "observed" for rows in group for row in rows
                ),
                "usable_assessments": sum(
                    row["status"] == "observed" and not row["invalid_metrics"]
                    for rows in group
                    for row in rows
                ),
            }
            arm_ranges = [
                {
                    "arm_index": arm,
                    **{
                        name: _report_range(
                            [
                                cast(list[object], _object(primary[i][name])["arm_means"])[arm]
                                for i in identifiers
                            ],
                            len(identifiers),
                        )
                        for name in ("distinct", "utility")
                    },
                }
                for arm in range(4)
            ]
            contrast_ranges = {
                name: {
                    contrast: _report_range(
                        [
                            _object(_object(primary[i][name])["contrasts"])[contrast]
                            for i in identifiers
                        ],
                        len(identifiers),
                    )
                    for contrast in _CONTRASTS
                }
                for name in ("distinct", "utility")
            }
            category_rows.append(
                {
                    "category": category,
                    "task_ids": list(identifiers),
                    "coverage": coverage,
                    "arm_ranges": arm_ranges,
                    "contrast_ranges": contrast_ranges,
                }
            )
        agreement, recovery = [], []
        for cell in schedule:
            arm, repeat = cast(int, cell["arm_index"]), cast(int, cell["generation_repeat"])
            for task in tasks:
                observed = []
                for j, plan in enumerate(cast(list[dict[str, object]], cell["judge_occasions"])):
                    key = task.id, arm, repeat, j
                    row = matrix[key]
                    projected_row = projected.get(key, {})
                    observed.append(
                        {
                            "index": j,
                            "distinct": row["distinct"],
                            "utility": row["utility"],
                            "status": row["status"],
                            "partition": deepcopy(projected_row.get("partition")),
                        }
                    )
                    diagnostic = _object(projected_row.get("diagnostics", {}))
                    stages = {
                        stage: {
                            field: deepcopy(_object(diagnostic.get(stage, {})).get(field))
                            for field in _RECOVERY_FIELDS
                        }
                        for stage in ("partition", "score")
                    }
                    recovery.append(
                        {
                            "cell_id": cell["cell_id"],
                            "occasion_id": plan["occasion_id"],
                            "task_id": task.id,
                            **stages,
                            "availability": {
                                stage: {
                                    field: "unknown" if value is None else "recorded"
                                    for field, value in values.items()
                                }
                                for stage, values in stages.items()
                            },
                            "absence_is_unknown": True,
                        }
                    )
                agreement.append(
                    {
                        "cell_id": cell["cell_id"],
                        "arm_index": arm,
                        "generation_repeat": repeat,
                        "task_id": task.id,
                        "occasions": observed,
                        "comparisons": [
                            _report_comparison(observed[0], later, task.count)
                            for later in observed[1:]
                        ],
                    }
                )
        return {
            "format": "buddha.policy-observations.v1",
            "study_sha256": study.fingerprint(),
            "descriptive": {
                "primary_judge_occasion": 0,
                "tasks": descriptions,
                "generation_repetitions": repetitions,
                "categories": category_rows,
            },
            "judge_agreement": agreement,
            "recovery": recovery,
            "limitations": [
                "Descriptive development diagnostics; no winner, inference "
                "or held-out improvement.",
                "Available category ranges do not replace complete planned denominators.",
                "Pair relations and judging occasions are dependent; agreement "
                "is not semantic truth or accuracy.",
                "Recorded row metadata does not attest parser execution, physical "
                "retries or callback attribution.",
                "Absent and explicit-null repair/fallback values remain unknown.",
            ],
        }
    except (ReleaseError, ValueError, TypeError, KeyError, RecursionError, OverflowError):
        raise PolicyResultsError("reporting observations contradict the declared study") from None
