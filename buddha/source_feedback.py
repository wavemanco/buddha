"""Bounded descriptive development feedback from a verified native source screen.

No candidate, evaluator, executing owner or paid transport is constructed here.
The existing improvement packet stays unchanged; provenance describes derivation,
not authenticated judgments, semantic compliance or scientific improvement.
"""

import hashlib
from pathlib import Path
from typing import cast

from buddha import candidate_generation, source_screen
from buddha import native_pipeline as pipeline
from buddha.answers import TaskSet
from buddha.releases import (
    MAX_FEEDBACK_BYTES,
    MAX_JSON_BYTES,
    ReleaseError,
    _digest,
    _json,
    _load,
    _object,
    _path,
    _root,
)

_POLICY = {
    "version": "literal-prefix-v1",
    "max_answer_positions": 10,
    "max_excerpt_utf8_bytes": 64,
    "max_excerpt_json_bytes": 128,
    "max_note_utf8_bytes": 4096,
    "max_feedback_bytes": MAX_FEEDBACK_BYTES,
    "max_projected_bytes": MAX_FEEDBACK_BYTES,
}


class SourceFeedbackError(ReleaseError):
    """Measured feedback or its exclusive destination violates the frozen input."""


def _sha(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()


def _list(value: object) -> list[object]:
    if type(value) is not list:
        raise SourceFeedbackError("feedback requires literal ordered records")
    return cast(list[object], value)


def _amount(value: object) -> int:
    if type(value) is not int or not 0 <= value < 2**63:
        raise SourceFeedbackError("recorded task cost is not a bounded integer")
    return value


def _prefix(text: str) -> str:
    result = ""
    for character in text:
        proposed = result + character
        if len(proposed.encode("utf-8")) > 64 or len(_json(proposed)) > 128:
            break
        result = proposed
    return result


def _destination(directory: Path) -> Path:
    if not isinstance(directory, Path) or not directory.is_absolute() or ".." in directory.parts:
        raise SourceFeedbackError("feedback destination needs an absolute nontraversing Path")
    _root(directory.parent)
    _path(directory.name)
    # Resolve only the checked existing parent, never require retired programs.
    directory = directory.parent.resolve(strict=True) / directory.name
    if directory.exists() or directory.is_symlink():
        raise SourceFeedbackError("feedback destination must be NEW")
    return directory


def _build(directory: Path, reference: dict[str, object]) -> dict[str, object]:
    directory = _destination(directory)
    ref = _object(reference, {"directory", "authorization", "report_sha256"})
    original = pipeline._absolute(ref["directory"])
    authorization = pipeline._absolute(ref["authorization"])
    expected = _digest(ref["report_sha256"])
    if ".." in original.parts or ".." in authorization.parts:
        raise SourceFeedbackError("feedback references cannot traverse parents")
    if directory.is_relative_to(original):
        raise SourceFeedbackError("feedback destination overlaps retained screen evidence")
    report_path = original / "report.json"
    report_raw = pipeline._read(report_path, expected)
    report = source_screen.inspect_source_screen(
        original, authorization=authorization, expected_report_sha256=expected
    )
    if _json(report) != report_raw:
        raise SourceFeedbackError("screen publication changed during feedback observation")
    screen_path = original / "screen.json"
    screen_sha256 = _digest(report["screen_sha256"])
    screen_raw = pipeline._read(screen_path, screen_sha256)
    screen = source_screen.SourceScreen.from_bytes(screen_raw)
    record = screen.to_record()
    for section in ("generation", "native"):
        for path in _object(_object(record[section])["roots"]).values():
            protected = pipeline._absolute(path)
            if directory.is_relative_to(protected):
                raise SourceFeedbackError("feedback destination overlaps original selected inputs")
    if record["projection"] != "noveltybench-1.1":
        raise SourceFeedbackError("native feedback requires the explicit supported projection")
    source, split = _object(record["source"]), _object(record["split"])
    source_sha256, split_sha256 = _sha(_json(source)), _sha(_json(split))
    tasks = TaskSet.from_bytes(_json(source)).select(record["selected_ids"])
    rows = _list(report["tasks"])
    if len(rows) != len(tasks.tasks):
        raise SourceFeedbackError("feedback task population differs from the verified screen")
    records: list[dict[str, object]] = []
    provenance_tasks: list[dict[str, object]] = []
    projected: list[dict[str, object]] = []
    for index, (task, value) in enumerate(zip(tasks.tasks, rows, strict=True)):
        row = _object(value)
        if _json(row["task_id"]) != _json(task.id):
            raise SourceFeedbackError("feedback changes the original typed task order")
        generation_ref = _object(row["source_generation"])
        selected, answers, _, _, _ = candidate_generation.read_candidate_generation_source(
            generation_ref, authorization
        )
        if selected.to_bytes() != tasks.select([task.id]).to_bytes():
            raise SourceFeedbackError("literal feedback answers belong to another task")
        literal = _list(_object(_list(answers.to_record()["outputs"])[0])["answers"])
        generation_path = original / "tasks" / str(index) / "generation/report.json"
        native_path = original / "tasks" / str(index) / "evaluation/report.json"
        generation_sha256 = _digest(row["generation_report_sha256"])
        native_sha256 = _digest(row["evaluation_report_sha256"])
        generation = _load(pipeline._read(generation_path, generation_sha256))
        native = _load(pipeline._read(native_path, native_sha256))
        cost = _amount(
            _object(_object(generation["generation"])["gateway_totals"])["spent_microusd"]
        )
        cost += sum(
            _amount(_object(_object(stage)["gateway_totals"])["spent_microusd"])
            for stage in _list(native["stages"])
        )
        diagnostics = _object(row["diagnostics"])
        partition = _list(_object(diagnostics["partition"])["partition"])
        quality = _object(diagnostics["quality"])
        scores = _list(_object(diagnostics["score"])["generation_scores"])
        shown, answer_provenance = [], []
        for position, answer in enumerate(literal):
            if type(answer) is not str:
                raise SourceFeedbackError("literal C1 answers require UTF-8 text")
            raw = answer.encode("utf-8")
            excerpt = _prefix(answer) if position < 10 else ""
            excerpt_bytes = len(excerpt.encode("utf-8"))
            if position < 10:
                shown.append({"position": position, "text": excerpt})
            answer_provenance.append(
                {
                    "position": position,
                    "utf8_sha256": _sha(raw),
                    "utf8_bytes": len(raw),
                    "excerpt_utf8_bytes": excerpt_bytes,
                    "omitted_utf8_bytes": len(raw) - excerpt_bytes,
                    "omission": "answer_positions"
                    if position >= 10
                    else "excerpt_bytes"
                    if len(raw) != excerpt_bytes
                    else None,
                }
            )
        note_value = {
            "kind": "saved_native_measurements",
            "status": "complete",
            "distinct": row["distinct"],
            "utility": row["utility"],
            "invalid_metrics": row["invalid_metrics"],
            "quality_status": quality["status"],
            "partition": partition[:10],
            "generation_scores": [
                score if type(score) is int and 1 <= score <= 10 else None for score in scores[:10]
            ],
            "answers": shown,
            "omitted_answer_positions": max(0, len(literal) - 10),
            "omitted_partition_positions": max(0, len(partition) - 10),
            "omitted_score_positions": max(0, len(scores) - 10),
            "recorded_cost_microusd": cost,
            "cost_scope": "original_task_generation_and_native_owners",
        }
        note_raw = _json(note_value)
        if len(note_raw) > 4096:
            raise SourceFeedbackError("descriptive task note exceeds its byte ceiling")
        note = note_raw.decode("utf-8")
        records.append({"task_id": task.id, "note": note})
        projected.append({"task": task.to_record(), "note": note})
        provenance_tasks.append(
            {
                "task_id": task.id,
                "source_generation": generation_ref,
                "generation_report": {"path": str(generation_path), "sha256": generation_sha256},
                "evaluation_report": {"path": str(native_path), "sha256": native_sha256},
                "note_sha256": _sha(note_raw),
                "note_utf8_bytes": len(note_raw),
                "answers": answer_provenance,
                "partition": {
                    "positions": len(partition),
                    "included_positions": min(10, len(partition)),
                    "omitted_positions": max(0, len(partition) - 10),
                    "sha256": _sha(_json(partition)),
                },
                "quality": {
                    "positions": len(scores),
                    "included_positions": min(10, len(scores)),
                    "omitted_positions": max(0, len(scores) - 10),
                    "unusable_head_indices": quality["unusable_head_indices"],
                    "sha256": _sha(_json(scores)),
                },
            }
        )
    feedback: dict[str, object] = {
        "format": "buddha.candidate-development-feedback.v1",
        "source": {"path": str(directory / "source.json"), "sha256": source_sha256},
        "split": {"path": str(directory / "split.json"), "sha256": split_sha256},
        "records": records,
    }
    if len(_json(feedback)) > MAX_FEEDBACK_BYTES or len(_json(projected)) > MAX_FEEDBACK_BYTES:
        raise SourceFeedbackError("feedback packet or full task projection exceeds 1 MiB")
    provenance: dict[str, object] = {
        "format": "buddha.source-screen-feedback.v1",
        "reference": {
            "directory": str(original),
            "authorization": str(authorization),
            "report_sha256": expected,
        },
        "screen_sha256": screen_sha256,
        "candidate_id": report["candidate_id"],
        "comparison_key": report["comparison_key"],
        "controls_sha256": report["controls_sha256"],
        "projection": record["projection"],
        "policy": dict(_POLICY),
        "source_sha256": source_sha256,
        "split_sha256": split_sha256,
        "feedback_sha256": _sha(_json(feedback)),
        "tasks": provenance_tasks,
        "claim": (
            "deterministic descriptive native feedback; no semantic audit or improvement claim"
        ),
    }
    result = {"source": source, "split": split, "feedback": feedback, "provenance": provenance}
    if len(_json(result)) > MAX_JSON_BYTES:
        raise SourceFeedbackError("feedback host bundle exceeds its byte ceiling")
    if pipeline._read(report_path, expected) != report_raw or (
        pipeline._read(screen_path, screen_sha256) != screen_raw
    ):
        raise SourceFeedbackError("original screen changed during feedback construction")
    return _load(_json(result))


def build_source_feedback(directory: Path, *, reference: dict[str, object]) -> dict[str, object]:
    """Build detached prospective records, without writing or creating owners."""
    try:
        return _build(directory, reference)
    except (ValueError, TypeError, KeyError, OSError, RecursionError, OverflowError) as error:
        if isinstance(error, SourceFeedbackError):
            raise
        raise SourceFeedbackError("source feedback evidence or destination is invalid") from None


def write_source_feedback(directory: Path, *, reference: dict[str, object]) -> dict[str, object]:
    """Exclusively write four checked records; preserve any partial failure."""
    bundle = build_source_feedback(directory, reference=reference)
    try:
        directory = _destination(directory)
        records = {
            name + ".json": _json(bundle[name])
            for name in ("source", "split", "feedback", "provenance")
        }
        directory.mkdir()
        for name, raw in records.items():
            pipeline._write(directory / name, raw)
        for name, raw in records.items():
            if pipeline._read(directory / name, _sha(raw)) != raw:
                raise SourceFeedbackError("written feedback changed before handoff")
        return {
            name: {
                "path": str(directory / (name + ".json")),
                "sha256": _sha(records[name + ".json"]),
            }
            for name in ("feedback", "provenance")
        }
    except (ValueError, TypeError, KeyError, OSError, RecursionError) as error:
        if isinstance(error, SourceFeedbackError):
            raise
        raise SourceFeedbackError("feedback write failed; partial destination retained") from None
