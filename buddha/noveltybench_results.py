"""Passive projection of saved NoveltyBench 1.1-shaped rows onto literal C1.

The caller must separately bind the reviewed official release and source bytes.
This opt-in adapter runs no official source and recomputes no utility. It checks
saved structure, not provider, parser, repair or callback authenticity. Missing
row metadata means unknown; raw files remain the caller's evidence.
"""

import json
import math
from typing import cast

from buddha.answers import Answers, TaskSet, _id
from buddha.releases import MAX_JSON_BYTES, Release, ReleaseError, _json, _object, _pairs

MAX_ROWS = 100_000
_DIAGNOSTIC_FIELDS = (
    "partition_key",
    "partition_config",
    "score_key",
    "score_config",
    "repair_attempts",
    "lenient",
    "fallback_judge",
    "fallback_calls",
    "unscored",
)


class NoveltyBenchResultsError(ReleaseError):
    """Saved rows contradict their literal answers or the supported row structure."""


def reporting_configuration(release: Release, stages: list[dict[str, object]]) -> dict[str, object]:
    """Read this adapter's artifact roles and a uniquely explicit fallback model.

    Absent or ambiguous CLI metadata does not establish the official defaults.
    This neither executes the original parser nor claims a fallback occurred.
    """
    try:
        if not isinstance(release, Release) or type(stages) is not list:
            raise NoveltyBenchResultsError("explicit saved release and stage list required")
        record = release.to_record()
        artifacts = _object(record["artifacts"])
        results = cast(list[str], artifacts["results"])
        commands = cast(list[dict[str, object]], record["commands"])
        if len(results) != 2 or len(stages) != 3 or len(commands) != len(stages):
            raise NoveltyBenchResultsError("reporting requires three declared native stages")
        expected = {results[0]: "grouping", results[1]: "quality", artifacts["summary"]: "summary"}
        roles = []
        for stage in stages:
            outputs = _object(stage)["outputs"]
            if type(outputs) is not list:
                raise NoveltyBenchResultsError("stage outputs must be declared")
            matches = {
                expected[path]
                for output in outputs
                if (path := _object(output)["path"]) in expected
            }
            if len(matches) != 1:
                raise NoveltyBenchResultsError("native stage artifact role is ambiguous")
            roles.append(matches.pop())
        if set(roles) != {"grouping", "quality", "summary"}:
            raise NoveltyBenchResultsError("native stage roles are incomplete")
        argv = cast(list[str], commands[roles.index("quality")]["argv"])
        values = []
        for index, argument in enumerate(argv):
            if argument == "--fallback-judge":
                values.append(argv[index + 1] if index + 1 < len(argv) else "")
            elif argument.startswith("--fallback-judge="):
                values.append(argument.split("=", 1)[1])
        fallback = values[0] if len(values) == 1 else None
        if fallback is not None and (
            not fallback.strip() or fallback.startswith("--") or len(fallback.encode()) > 4096
        ):
            fallback = None
        return {"stage_roles": roles, "fallback_model": fallback}
    except (ReleaseError, ValueError, TypeError, KeyError, UnicodeError, RecursionError):
        raise NoveltyBenchResultsError(
            "saved reporting configuration contradicts the supported projection"
        ) from None


def _rows(raw: bytes) -> list[dict[str, object]]:
    if type(raw) is not bytes or not raw or len(raw) > MAX_JSON_BYTES:
        raise NoveltyBenchResultsError("native rows require bounded original bytes")
    count = raw.count(b"\n") + (not raw.endswith(b"\n"))
    if not 1 <= count <= MAX_ROWS:
        raise NoveltyBenchResultsError("native row population is outside the supported bounds")
    lines = raw.split(b"\n")
    if lines[-1] == b"":
        lines.pop()
    return [_object(json.loads(line.decode("utf-8"), object_pairs_hook=_pairs)) for line in lines]


def _same(first: object, second: object) -> bool:
    return _json(first) == _json(second)


def _distinct(value: object, count: int, classes: int) -> int | None:
    if type(value) is int and 1 <= value <= count:
        if value != classes:
            raise NoveltyBenchResultsError("saved distinct count contradicts its partition")
        return value
    return None


def _utility(value: object) -> int | float | None:
    if type(value) in (int, float):
        number = cast(int | float, value)
        if 0 <= number <= 10 and math.isfinite(number):
            return number
    return None


def _heads(value: object, count: int) -> list[int]:
    if type(value) is not list or len(value) != count:
        raise NoveltyBenchResultsError("native partition length differs from its answer set")
    seen: set[int] = set()
    heads = []
    for index, label in enumerate(value):
        if type(label) is not int or label < 0:
            raise NoveltyBenchResultsError("native class labels must be nonnegative integers")
        if label not in seen:
            if label != len(seen):
                raise NoveltyBenchResultsError(
                    "native classes must be normalized in original answer order"
                )
            seen.add(label)
            heads.append(index)
    return heads


def _scores(row: dict[str, object], count: int, heads: list[int]) -> dict[str, object]:
    values, per_class = row["generation_scores"], row["partition_scores"]
    if type(values) is not list or len(values) != count or type(per_class) is not list:
        raise NoveltyBenchResultsError("native quality arrays differ from the answer population")
    if "unscored" in row:
        reason = row["unscored"]
        if (
            type(reason) is not str
            or not reason.strip()
            or any(value is not None for value in values)
            or per_class
            or row["utility"] is not None
        ):
            raise NoveltyBenchResultsError(
                "explicit unscored rows must retain no quality judgments"
            )
        return {
            "status": "explicit_unscored",
            "head_indices": list(heads),
            "unusable_head_indices": list(heads),
        }
    head_set = set(heads)
    unusable = []
    for index, value in enumerate(values):
        if index in head_set:
            if type(value) is not int or not 1 <= value <= 10:
                unusable.append(index)
        elif value is not None:
            raise NoveltyBenchResultsError("duplicate non-head positions must remain unscored")
    # Compare supplied arrays as data, including invalid nonfinite numeric scores.
    # Raw files stay with the caller; these values never become projected utility.
    if (per_class or not unusable) and json.dumps(
        per_class, sort_keys=True, allow_nan=True
    ) != json.dumps([values[index] for index in heads], sort_keys=True, allow_nan=True):
        raise NoveltyBenchResultsError("native class scores differ from original-order head scores")
    return {
        "status": (
            "missing_head_scores"
            if any(values[index] is None for index in unusable)
            else "invalid_head_scores"
        )
        if unusable
        else "scored",
        "head_indices": list(heads),
        "unusable_head_indices": unusable,
    }


def _diagnostics(row: dict[str, object], native_fields: set[str]) -> dict[str, object]:
    result = {
        key: value
        for key, value in row.items()
        if key not in native_fields | {"distinct", "utility"}
    }
    for field in _DIAGNOSTIC_FIELDS:
        result.setdefault(field, None)
    for field in ("generation_scores", "partition_scores"):
        if field in result:
            result[field] = [
                None if type(value) is float and not math.isfinite(value) else value
                for value in cast(list[object], result[field])
            ]
    _json(result)  # Only projected metrics and diagnostic quality values may be nonfinite.
    return result


def _generation(
    row: dict[str, object],
    original: dict[str, object],
    fields: tuple[str, str, str],
    identifier: str | int,
) -> None:
    if any((field in row) != (field in original) for field in ("model", "prompt_paraphrases")):
        raise NoveltyBenchResultsError(
            "native row invented or removed retained generation metadata"
        )
    required = set(fields) | ({"model", "prompt_paraphrases"} & original.keys())
    if not required <= row.keys() or not _same(_id(row[fields[0]]), identifier):
        raise NoveltyBenchResultsError(
            "native row order or required typed generation fields differ"
        )
    for key, value in original.items():
        if (
            key in row
            and key
            not in {"partition", "distinct", "utility", "generation_scores", "partition_scores"}
            and not _same(row[key], value)
        ):
            raise NoveltyBenchResultsError("native row changed retained literal generation fields")


def project_rows(
    tasks: TaskSet, answers: Answers, partitions_raw: bytes, scores_raw: bytes
) -> list[dict[str, object]]:
    """Bind ordered native fields and project saved D/U without metric substitution.

    Structural contradictions raise a typed error. Invalid scalar distinct/utility
    values remain None with invalid_metrics; they are never derived or zero-filled.
    Required head scores and literal native metadata must still be consistent.
    """
    try:
        if not isinstance(tasks, TaskSet) or not isinstance(answers, Answers):
            raise NoveltyBenchResultsError("projection requires task and answer artifacts")
        if answers.to_record()["tasks_sha256"] != tasks.fingerprint():
            raise NoveltyBenchResultsError("answer and selected task artifacts differ")
        task_record = tasks.to_record()
        schema = _object(_object(task_record["release"])["task"])
        fields = cast(
            tuple[str, str, str],
            tuple(schema[name] for name in ("id_field", "prompt_field", "answers_field")),
        )
        native, partitions, scores = (
            _rows(answers.native_bytes()),
            _rows(partitions_raw),
            _rows(scores_raw),
        )
        selected = tasks.tasks
        if (
            len(native) != len(selected)
            or len(partitions) != len(selected)
            or len(scores) != len(selected)
        ):
            raise NoveltyBenchResultsError(
                "native row population differs from the ordered selected tasks"
            )
        result: list[dict[str, object]] = []
        for task, original, partition, score in zip(
            selected, native, partitions, scores, strict=True
        ):
            _generation(partition, original, fields, task.id)
            _generation(score, original, fields, task.id)
            if not {"partition", "distinct"} <= partition.keys():
                raise NoveltyBenchResultsError("partition omits required native fields")
            required_score = {"generation_scores", "partition_scores", "utility", "distinct"}
            if not required_score <= score.keys():
                raise NoveltyBenchResultsError("score row omits required native fields")
            for key, value in partition.items():
                if key != "distinct" and (key not in score or not _same(score[key], value)):
                    raise NoveltyBenchResultsError("score row changed inherited partition fields")
            heads = _heads(partition["partition"], task.count)
            partition_d = _distinct(partition["distinct"], task.count, len(heads))
            score_d = _distinct(score["distinct"], task.count, len(heads))
            distinct = score_d if partition_d is not None else None
            quality = _scores(score, task.count, heads)
            utility = _utility(score["utility"]) if quality["status"] == "scored" else None
            invalid = [
                name
                for name, value in (("distinct", distinct), ("utility", utility))
                if value is None
            ]
            result.append(
                {
                    "task_id": task.id,
                    "distinct": distinct,
                    "utility": utility,
                    "invalid_metrics": invalid,
                    "diagnostics": {
                        "partition": _diagnostics(partition, set(original)),
                        "score": _diagnostics(score, set(original)),
                        "absence_is_unknown": True,
                        "quality": quality,
                    },
                }
            )
        return result
    except (ReleaseError, ValueError, TypeError, UnicodeError, RecursionError, OverflowError):
        raise NoveltyBenchResultsError(
            "saved native rows contradict the supported literal projection"
        ) from None
