"""Bounded descriptive development feedback from a verified native source screen.

No candidate, evaluator, executing owner or paid transport is constructed here.
The existing improvement packet stays unchanged; provenance describes derivation,
not authenticated judgments, semantic compliance or scientific improvement.
"""

import hashlib
import json
import os
import stat
from collections.abc import Iterator, Sequence
from contextlib import ExitStack
from pathlib import Path
from typing import cast

from buddha import candidate_generation, source_screen, trial_fence
from buddha import native_pipeline as pipeline
from buddha.answers import TaskSet, _utf8
from buddha.releases import (
    MAX_FEEDBACK_BYTES,
    MAX_JSON_BYTES,
    ReleaseError,
    _checked_proposal_capture,
    _digest,
    _information,
    _json,
    _load,
    _object,
    _path,
    _root,
    _source_proposal,
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
_FAILURE_POLICY = {
    **_POLICY,
    "version": "measured-failed-children-v2",
    "max_answer_positions": 1,
    "max_excerpt_utf8_bytes": 16,
    "max_excerpt_json_bytes": 32,
    "max_failures": 8,
    "newest_source_utf8_bytes": 768,
    "newest_source_json_bytes": 1536,
    "minimum_source_utf8_bytes": 128,
    "newest_hypothesis_utf8_bytes": 128,
    "newest_hypothesis_json_bytes": 256,
    "older_source_and_hypothesis_excerpts": 0,
    "cost_scope": "original proposal and failed-generation owners separately",
}
_FULL_POLICY = {
    "version": "complete-outputs-v3",
    "answer_positions": "all_selected",
    "answer_text": "complete_literal_utf8",
    "diagnostic_positions": "all",
    "max_note_utf8_bytes": MAX_FEEDBACK_BYTES,
    "max_feedback_bytes": MAX_FEEDBACK_BYTES,
    "max_projected_bytes": MAX_FEEDBACK_BYTES,
}
_FULL_FAILURE_POLICY = {
    **_FULL_POLICY,
    "version": "complete-outputs-and-failed-children-v4",
    "max_failures": 8,
    "newest_source_and_hypothesis": "complete",
    "older_source_and_hypothesis_excerpts": 0,
    "cost_scope": "original proposal and failed-generation owners separately",
}


class SourceFeedbackError(ReleaseError):
    """Measured feedback or its exclusive destination violates the frozen input."""


class SourceFeedbackTooLarge(SourceFeedbackError):
    """Complete feedback cannot fit its declared resource ceilings."""


def _bounded_json(value: object, maximum: int) -> bytes:
    """Canonical JSON, refusing before accumulating an oversized result."""
    result = bytearray()
    try:
        encoder = json.JSONEncoder(sort_keys=True, separators=(",", ":"), allow_nan=False)
        for piece in encoder.iterencode(value):
            raw = piece.encode("utf-8")
            if len(result) + len(raw) > maximum:
                raise SourceFeedbackTooLarge("complete feedback exceeds its declared byte ceiling")
            result.extend(raw)
    except (TypeError, ValueError, UnicodeError, RecursionError) as error:
        if isinstance(error, SourceFeedbackError):
            raise
        raise SourceFeedbackError("feedback requires finite canonical JSON") from None
    return bytes(result)


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


def _prefix(text: str, *, utf8_bytes: int = 64, json_bytes: int = 128) -> str:
    result = ""
    for character in text:
        proposed = result + character
        if len(proposed.encode("utf-8")) > utf8_bytes or len(_json(proposed)) > json_bytes:
            break
        result = proposed
    return result


def _destination(directory: Path, *, existing: bool = False) -> Path:
    if not isinstance(directory, Path) or not directory.is_absolute() or ".." in directory.parts:
        raise SourceFeedbackError("feedback destination needs an absolute nontraversing Path")
    _root(directory.parent)
    _path(directory.name)
    # Resolve only the checked existing parent, never require retired programs.
    directory = directory.parent.resolve(strict=True) / directory.name
    if existing:
        return _root(directory)
    if directory.exists() or directory.is_symlink():
        raise SourceFeedbackError("feedback destination must be NEW")
    return directory


def _build(
    directory: Path,
    reference: dict[str, object],
    *,
    existing: bool = False,
    full_answers: bool = True,
) -> dict[str, object]:
    directory = _destination(directory, existing=existing)
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
    feedback: dict[str, object] = {
        "format": "buddha.candidate-development-feedback.v2"
        if full_answers
        else "buddha.candidate-development-feedback.v1",
        "source": {"path": str(directory / "source.json"), "sha256": source_sha256},
        "split": {"path": str(directory / "split.json"), "sha256": split_sha256},
        "records": records,
    }
    feedback_size = len(_bounded_json(feedback, MAX_FEEDBACK_BYTES)) if full_answers else 0
    projected_size = 2
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
            if full_answers and len(raw) > MAX_FEEDBACK_BYTES:
                raise SourceFeedbackTooLarge("complete answer exceeds the feedback byte ceiling")
            excerpt = answer if full_answers else _prefix(answer) if position < 10 else ""
            excerpt_bytes = len(excerpt.encode("utf-8"))
            if full_answers or position < 10:
                shown.append({"position": position, "text": excerpt})
            answer_provenance.append(
                {
                    "position": position,
                    "utf8_sha256": _sha(raw),
                    "utf8_bytes": len(raw),
                    "excerpt_utf8_bytes": excerpt_bytes,
                    "omitted_utf8_bytes": len(raw) - excerpt_bytes,
                    "omission": "answer_positions"
                    if not full_answers and position >= 10
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
            "partition": partition if full_answers else partition[:10],
            "generation_scores": scores
            if full_answers
            else [
                score if type(score) is int and 1 <= score <= 10 else None for score in scores[:10]
            ],
            "answers": shown,
            "omitted_answer_positions": 0 if full_answers else max(0, len(literal) - 10),
            "omitted_partition_positions": 0 if full_answers else max(0, len(partition) - 10),
            "omitted_score_positions": 0 if full_answers else max(0, len(scores) - 10),
            "recorded_cost_microusd": cost,
            "cost_scope": "original_task_generation_and_native_owners",
        }
        note_raw = (
            _bounded_json(note_value, MAX_FEEDBACK_BYTES) if full_answers else _json(note_value)
        )
        if len(note_raw) > (MAX_FEEDBACK_BYTES if full_answers else 4096):
            raise SourceFeedbackTooLarge("descriptive task note exceeds its byte ceiling")
        note = note_raw.decode("utf-8")
        feedback_row: dict[str, object] = {"task_id": task.id, "note": note}
        projected_row: dict[str, object] = {"task": task.to_record(), "note": note}
        if full_answers:
            comma = int(bool(records))
            feedback_size += comma + len(
                _bounded_json(feedback_row, MAX_FEEDBACK_BYTES - feedback_size - comma)
            )
            projected_size += comma + len(
                _bounded_json(projected_row, MAX_FEEDBACK_BYTES - projected_size - comma)
            )
        records.append(feedback_row)
        projected.append(projected_row)
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
                    "included_positions": len(partition)
                    if full_answers
                    else min(10, len(partition)),
                    "omitted_positions": 0 if full_answers else max(0, len(partition) - 10),
                    "sha256": _sha(_json(partition)),
                },
                "quality": {
                    "positions": len(scores),
                    "included_positions": len(scores) if full_answers else min(10, len(scores)),
                    "omitted_positions": 0 if full_answers else max(0, len(scores) - 10),
                    "unusable_head_indices": quality["unusable_head_indices"],
                    "sha256": _sha(_json(scores)),
                },
            }
        )
    if len(_json(feedback)) > MAX_FEEDBACK_BYTES or len(_json(projected)) > MAX_FEEDBACK_BYTES:
        raise SourceFeedbackTooLarge("feedback packet or full task projection exceeds 1 MiB")
    provenance: dict[str, object] = {
        "format": "buddha.source-screen-feedback.v3"
        if full_answers
        else "buddha.source-screen-feedback.v1",
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
        "policy": dict(_FULL_POLICY if full_answers else _POLICY),
        "source_sha256": source_sha256,
        "split_sha256": split_sha256,
        "feedback_sha256": _sha(_json(feedback)),
        "tasks": provenance_tasks,
        "claim": (
            "deterministic descriptive native feedback; no semantic audit or improvement claim"
        ),
    }
    result = {"source": source, "split": split, "feedback": feedback, "provenance": provenance}
    raw_result = _bounded_json(result, MAX_JSON_BYTES) if full_answers else _json(result)
    if pipeline._read(report_path, expected) != report_raw or (
        pipeline._read(screen_path, screen_sha256) != screen_raw
    ):
        raise SourceFeedbackError("original screen changed during feedback construction")
    return _load(raw_result)


def _build_failures(
    directory: Path,
    reference: dict[str, object],
    history: Sequence[dict[str, object]],
    *,
    existing: bool = False,
    full_answers: bool = True,
) -> dict[str, object]:
    """Rebuild checked history, including at a private partial-write destination."""
    if type(history) not in {list, tuple} or not 1 <= len(history) <= 8:
        raise SourceFeedbackError("failure history requires 1..8 ordered original edges")
    directory = _destination(directory, existing=existing)
    if existing:
        _packet_files(directory, partial=True)
    base = _build(directory, reference, existing=existing, full_answers=full_answers)
    provenance = _object(base["provenance"])
    measured_sha256 = _sha(_json(provenance))
    original_ref = _object(provenance["reference"])
    authorization = pipeline._absolute(original_ref["authorization"])
    observed: dict[Path, str] = {}

    def consume(path: Path, expected: object) -> bytes:
        raw = pipeline._read(path, expected)
        digest = _sha(raw)
        if path in observed and observed[path] != digest:
            raise SourceFeedbackError("failure evidence changed during derivation")
        observed[path] = digest
        return raw

    def checked_ref(value: object) -> dict[str, object]:
        item = _object(value, {"directory", "authorization", "report_sha256"})
        location = pipeline._absolute(item["directory"])
        authority = pipeline._absolute(item["authorization"])
        if ".." in location.parts or ".." in authority.parts or authority != authorization:
            raise SourceFeedbackError("failure history changes its original shared authority")
        if directory.is_relative_to(location):
            raise SourceFeedbackError("failure feedback overlaps its original evidence")
        return {
            "directory": str(location),
            "authorization": str(authority),
            "report_sha256": _digest(item["report_sha256"]),
        }

    def screen_input(
        value: object,
    ) -> tuple[dict[str, object], dict[str, object], dict[str, object]]:
        ref = checked_ref(value)
        location = pipeline._absolute(ref["directory"])
        raw = consume(location / "report.json", ref["report_sha256"])
        report = source_screen.inspect_source_screen(
            location,
            authorization=authorization,
            expected_report_sha256=_digest(ref["report_sha256"]),
        )
        record = source_screen.SourceScreen.from_bytes(
            consume(location / "screen.json", _digest(report["screen_sha256"]))
        ).to_record()
        if (
            raw != _json(report)
            or any(report[key] != provenance[key] for key in ("comparison_key", "controls_sha256"))
            or any(_json(record[key]) != _json(base[key]) for key in ("source", "split"))
        ):
            raise SourceFeedbackError("failed children change the original common screen")
        selected_ids = [
            task.id for task in source_screen.SourceScreen.from_bytes(_json(record)).tasks.tasks
        ]
        if _json(selected_ids) != _json(
            [_object(row)["task_id"] for row in _list(_object(base["feedback"])["records"])]
        ):
            raise SourceFeedbackError("failed children change the ordered development population")
        for section in ("generation", "native"):
            if any(
                directory.is_relative_to(pipeline._absolute(path))
                for path in _object(_object(record[section])["roots"]).values()
            ):
                raise SourceFeedbackError("failure feedback overlaps original selected components")
        return ref, report, record

    from buddha import candidate_improvement
    from buddha.gateway import _read_manifest

    edges, failures, summaries = [], [], []
    seen_proposals: set[str] = set()
    seen_screens: set[str] = set()
    latest_source = latest_hypothesis = ""
    tasks = TaskSet.from_bytes(_json(base["source"]))
    for ordinal, value in enumerate(history):
        edge = _object(value, {"parent", "proposal", "screen"})
        parent_ref, parent, parent_record = screen_input(edge["parent"])
        failed_ref, failed, failed_record = screen_input(edge["screen"])
        proposal_ref = checked_ref(edge["proposal"])
        if parent.get("disposition", "screened") != "screened" or (
            failed.get("disposition") != "candidate_execution_failed"
        ):
            raise SourceFeedbackError(
                "failure history needs a complete parent and terminal failed child"
            )
        proposal_path = pipeline._absolute(proposal_ref["directory"])
        proposal_raw = consume(proposal_path / "report.json", proposal_ref["report_sha256"])
        proposal = candidate_improvement.inspect_candidate_improvement(
            proposal_path,
            authorization=authorization,
            expected_report_sha256=_digest(proposal_ref["report_sha256"]),
        )
        if proposal_raw != _json(proposal) or proposal["disposition"] != "materialized":
            raise SourceFeedbackError("failed child lacks an original materialized proposal")
        child = _object(proposal["child"])
        if (
            proposal["parent_agent_sha256"] != parent["candidate_id"]
            or failed["parent_id"] != parent["candidate_id"]
            or failed["candidate_id"] != child["agent_sha256"]
            or _json(failed_record["lineage"]) != _json(child["lineage"])
            or str(proposal_ref["directory"]) in seen_proposals
            or str(failed_ref["directory"]) in seen_screens
        ):
            raise SourceFeedbackError(
                "failure history repeats or changes an original parent-child edge"
            )
        owner_ref = _object(_object(proposal["provenance"])["owner"])
        owner = _read_manifest(pipeline._absolute(owner_ref["directory"]))
        if pipeline._sha(owner) != owner_ref["manifest_sha256"] or (
            _json(owner["selection"]) != _json(_object(parent_record["generation"])["selection"])
        ):
            raise SourceFeedbackError("proposal changes its parent's protected selection")
        inputs = _object(_object(proposal["provenance"])["original_inputs"])
        context_path = proposal_path / "context.json"
        context = _load(consume(context_path, inputs[str(context_path)]))
        descriptor_path = pipeline._absolute(context["descriptor"])
        recipe = _load(consume(descriptor_path, inputs[str(descriptor_path)]))
        feedback_path = pipeline._absolute(_object(recipe["feedback"])["path"])
        provenance_path = feedback_path.parent / "provenance.json"
        measured_provenance = _load(consume(provenance_path, inputs[str(provenance_path)]))
        if _json(measured_provenance["reference"]) != _json(parent_ref):
            raise SourceFeedbackError("proposal feedback names another original parent occasion")
        lineage_ref = _object(child["lineage"])
        lineage_path = pipeline._absolute(lineage_ref["path"])
        lineage = _load(consume(lineage_path, lineage_ref["sha256"]))
        frame = _load(consume(lineage_path.parent / "proposal.json", lineage["proposal_sha256"]))
        returned = _source_proposal(_checked_proposal_capture(frame["proposal"])["value"])
        child_source = returned["source"].encode("utf-8")
        if _sha(child_source) != child["source_sha256"] or (
            consume(pipeline._absolute(child["directory"]) / "candidate.py", child["source_sha256"])
            != child_source
        ):
            raise SourceFeedbackError("failed source differs from its retained original proposal")
        failure = _object(failed["failure"])
        task_ids = _list(_object(base["feedback"])["records"])
        index = failure["task_index"]
        if (
            type(index) is not int
            or not 0 <= index < len(task_ids)
            or (_json(failure["task_id"]) != _json(_object(task_ids[index])["task_id"]))
        ):
            raise SourceFeedbackError("failed source is not its original development task")
        generation_ref = _object(failure["source_generation"])
        generation = _load(
            consume(
                pipeline._absolute(generation_ref["generation_directory"]) / "report.json",
                _digest(failure["generation_report_sha256"]),
            )
        )
        terminal = _object(failure["terminal"])
        if generation["disposition"] != "candidate_execution_failed" or (
            _json(_object(generation["outcome"])["terminal"]) != _json(terminal)
            or _object(generation["generation"])["agent_sha256"] != child["agent_sha256"]
            or type(terminal["ready_seen"]) is not bool
            or terminal["done_reason"] != "agent_error"
        ):
            raise SourceFeedbackError("failed child has no checked original worker outcome")
        summary = {
            "ordinal": ordinal,
            "parent_id": parent["candidate_id"],
            "child_id": child["agent_sha256"],
            "task_id": failure["task_id"],
            "reason": terminal["done_reason"],
            "ready_seen": terminal["ready_seen"],
            "completed_callbacks": _amount(terminal["operation_count"]),
            "recorded_cost_microusd": _amount(terminal["recorded_cost_microusd"]),
            "proposal_cost_microusd": _amount(
                _object(_object(proposal["improvement"])["gateway_totals"])["spent_microusd"]
            ),
        }
        edges.append({"parent": parent_ref, "proposal": proposal_ref, "screen": failed_ref})
        summaries.append(summary)
        failures.append(
            summary
            | {
                "source_generation": generation_ref,
                "generation_report_sha256": failure["generation_report_sha256"],
                "source": {"sha256": _sha(child_source), "utf8_bytes": len(child_source)},
                "hypothesis": {
                    "sha256": _sha(returned["hypothesis"].encode()),
                    "utf8_bytes": len(returned["hypothesis"].encode()),
                },
            }
        )
        seen_proposals.add(str(proposal_ref["directory"]))
        seen_screens.add(str(failed_ref["directory"]))
        latest_source, latest_hypothesis = returned["source"], returned["hypothesis"]
    source_prefix = (
        latest_source if full_answers else _prefix(latest_source, utf8_bytes=768, json_bytes=1536)
    )
    hypothesis_prefix = (
        latest_hypothesis
        if full_answers
        else _prefix(latest_hypothesis, utf8_bytes=128, json_bytes=256)
    )
    measured = [
        _load(_utf8(_object(row)["note"]).encode())
        for row in _list(_object(base["feedback"])["records"])
    ]
    for note, task_provenance in zip(measured, _list(provenance["tasks"]), strict=True):
        if full_answers:
            continue
        answers = _list(note["answers"])
        shown = (
            [
                {
                    "position": 0,
                    "text": _prefix(
                        _utf8(_object(answers[0])["text"]), utf8_bytes=16, json_bytes=32
                    ),
                }
            ]
            if answers
            else []
        )
        note["answers"] = shown
        originals = _list(_object(task_provenance)["answers"])
        note["omitted_answer_positions"] = max(0, len(originals) - len(shown))
        for position, answer in enumerate(originals):
            item = _object(answer)
            included = len(_utf8(shown[0]["text"]).encode()) if position == 0 and shown else 0
            item.update(
                excerpt_utf8_bytes=included,
                omitted_utf8_bytes=cast(int, item["utf8_bytes"]) - included,
                omission="answer_positions"
                if position >= 1
                else "excerpt_bytes"
                if item["utf8_bytes"] != included
                else None,
            )

    def notes(prefix: str) -> Iterator[bytes]:
        for note in measured:
            value = {
                "kind": "saved_native_measurements_and_failed_children",
                "measurements": note,
                "failures": summaries,
                "newest_failure": {
                    "ordinal": len(failures) - 1,
                    "source_sha256": _sha(latest_source.encode()),
                    "hypothesis_sha256": _sha(latest_hypothesis.encode()),
                    "source": prefix,
                    "hypothesis": hypothesis_prefix,
                    "source_omitted_utf8_bytes": len(latest_source.encode()) - len(prefix.encode()),
                    "hypothesis_omitted_utf8_bytes": len(latest_hypothesis.encode())
                    - len(hypothesis_prefix.encode()),
                },
                "older_failure_excerpts_omitted": len(failures) - 1,
            }
            yield _bounded_json(value, MAX_FEEDBACK_BYTES) if full_answers else _json(value)

    if not full_answers:
        minimum = _prefix(source_prefix, utf8_bytes=128, json_bytes=1536)
        if any(len(raw) > 4096 for raw in notes(minimum)):
            raise SourceFeedbackError(
                "all failed-child summaries and minimum source context exceed note ceiling"
            )
        low, high = len(minimum), len(source_prefix)
        while low < high:
            middle = (low + high + 1) // 2
            if all(len(raw) <= 4096 for raw in notes(source_prefix[:middle])):
                low = middle
            else:
                high = middle - 1
        source_prefix = source_prefix[:low]
    raw_notes = notes(source_prefix)
    feedback = _object(base["feedback"])
    feedback_size = (
        len(_bounded_json(feedback | {"records": []}, MAX_FEEDBACK_BYTES)) if full_answers else 0
    )
    projected_size = 2
    position = 0
    for row, raw, task_provenance in zip(
        _list(feedback["records"]), raw_notes, _list(provenance["tasks"]), strict=True
    ):
        note_text = raw.decode()
        if full_answers:
            comma = int(position > 0)
            feedback_row = _object(row) | {"note": note_text}
            projected_row = {
                "task": tasks.select([feedback_row["task_id"]]).tasks[0].to_record(),
                "note": note_text,
            }
            feedback_size += comma + len(
                _bounded_json(feedback_row, MAX_FEEDBACK_BYTES - feedback_size - comma)
            )
            projected_size += comma + len(
                _bounded_json(projected_row, MAX_FEEDBACK_BYTES - projected_size - comma)
            )
            position += 1
        _object(row)["note"] = note_text
        _object(task_provenance).update(note_sha256=_sha(raw), note_utf8_bytes=len(raw))
    for index, failure in enumerate(failures):
        for key, excerpt in (("source", source_prefix), ("hypothesis", hypothesis_prefix)):
            item = _object(failure[key])
            included = len(excerpt.encode()) if index == len(failures) - 1 else 0
            item.update(
                excerpt_utf8_bytes=included,
                omitted_utf8_bytes=cast(int, item["utf8_bytes"]) - included,
            )
    provenance.update(
        format="buddha.source-screen-feedback.v4"
        if full_answers
        else "buddha.source-screen-feedback.v2",
        policy=dict(_FULL_FAILURE_POLICY if full_answers else _FAILURE_POLICY),
        measured_base_sha256=measured_sha256,
        failure_history=edges,
        failures=failures,
        feedback_sha256=_sha(_json(feedback)),
        claim=(
            "descriptive native measurements and worker-declared source failures; "
            "no invalidity oracle or improvement claim"
        ),
    )
    projected = [
        {
            "task": tasks.select([_object(row)["task_id"]]).tasks[0].to_record(),
            "note": _object(row)["note"],
        }
        for row in _list(feedback["records"])
    ]
    if len(_json(feedback)) > MAX_FEEDBACK_BYTES or len(_json(projected)) > MAX_FEEDBACK_BYTES:
        raise SourceFeedbackTooLarge(
            "failure feedback packet or full task projection exceeds 1 MiB"
        )
    raw_base = _bounded_json(base, MAX_JSON_BYTES) if full_answers else _json(base)
    for path, digest in observed.items():
        pipeline._read(path, digest)
    return _load(raw_base)


def build_source_feedback(
    directory: Path,
    *,
    reference: dict[str, object],
    failure_history: Sequence[dict[str, object]] = (),
) -> dict[str, object]:
    """Build detached prospective records, without writing or creating owners."""
    try:
        if type(failure_history) not in {list, tuple}:
            raise SourceFeedbackError("failure history requires an ordered literal sequence")
        return (
            _build_failures(directory, reference, failure_history)
            if failure_history
            else _build(directory, reference)
        )
    except (ValueError, TypeError, KeyError, OSError, RecursionError, OverflowError) as error:
        if isinstance(error, SourceFeedbackError):
            raise
        raise SourceFeedbackError("source feedback evidence or destination is invalid") from None


def _packet_files(directory: Path, *, partial: bool = False) -> None:
    expected = {"source.json", "split.json", "feedback.json", "provenance.json"}
    found = set()
    with os.scandir(directory) as entries:
        for entry in entries:
            if entry.name not in expected or entry.name in found:
                raise SourceFeedbackError("feedback packet requires exactly four original files")
            information = _information(Path(entry.path))
            if not stat.S_ISREG(information.st_mode) or information.st_nlink != 1:
                raise SourceFeedbackError("feedback packet files must be regular without aliases")
            found.add(entry.name)
    if not partial and found != expected:
        raise SourceFeedbackError("feedback packet requires exactly four original files")


def inspect_source_feedback(
    directory: Path, *, expected_provenance_sha256: str
) -> dict[str, object]:
    """Verify an existing measured packet against its original screen, without writes."""
    try:
        directory = _destination(directory, existing=True)
        _packet_files(directory)
        provenance_raw = pipeline._read(
            directory / "provenance.json", _digest(expected_provenance_sha256)
        )
        original = _load(provenance_raw)
        version = original.get("format")
        if version not in {"buddha.source-screen-feedback.v" + str(i) for i in range(1, 5)}:
            raise SourceFeedbackError("unsupported saved feedback derivation")
        full_answers = version in {
            "buddha.source-screen-feedback.v3",
            "buddha.source-screen-feedback.v4",
        }
        reference = _object(original["reference"])
        bundle = (
            _build_failures(
                directory,
                reference,
                cast(list[dict[str, object]], _list(original["failure_history"])),
                existing=True,
                full_answers=full_answers,
            )
            if version in {"buddha.source-screen-feedback.v2", "buddha.source-screen-feedback.v4"}
            else _build(directory, reference, existing=True, full_answers=full_answers)
        )
        records = {
            name + ".json": _json(bundle[name])
            for name in ("source", "split", "feedback", "provenance")
        }
        if records["provenance.json"] != provenance_raw:
            raise SourceFeedbackError("saved provenance differs from its original derivation")
        for name, raw in records.items():
            if pipeline._read(directory / name, _sha(raw)) != raw:
                raise SourceFeedbackError("saved feedback differs from its original derivation")
        _packet_files(directory)
        for name, raw in records.items():
            if pipeline._read(directory / name, _sha(raw)) != raw:
                raise SourceFeedbackError("saved feedback changed during inspection")
        _packet_files(directory)
        return bundle
    except (ValueError, TypeError, KeyError, OSError, RecursionError, OverflowError) as error:
        if isinstance(error, SourceFeedbackError):
            raise
        raise SourceFeedbackError("saved source feedback evidence is invalid") from None


def write_source_feedback(
    directory: Path,
    *,
    reference: dict[str, object],
    failure_history: Sequence[dict[str, object]] = (),
) -> dict[str, object]:
    """Exclusively write four checked records; preserve any partial failure."""
    bundle = build_source_feedback(directory, reference=reference, failure_history=failure_history)
    try:
        directory = _destination(directory)
        records = {
            name + ".json": _json(bundle[name])
            for name in ("source", "split", "feedback", "provenance")
        }
        provenance = _object(bundle["provenance"])
        references = [_object(provenance["reference"])]
        for value in _list(provenance.get("failure_history", [])):
            edge = _object(value, {"parent", "proposal", "screen"})
            references.extend(_object(edge[name]) for name in ("parent", "proposal", "screen"))
        authority_path = pipeline._absolute(references[0]["authorization"])
        original_terms = None
        with ExitStack() as stack:
            for item in references:
                if pipeline._absolute(item["authorization"]) != authority_path:
                    raise SourceFeedbackError("feedback history changes its original grant")
                location = pipeline._absolute(item["directory"])
                report = _object(
                    _load(pipeline._read(location / "report.json", _digest(item["report_sha256"])))
                )
                # The builder verified this exact report against original custody.
                # Reuse its immutable terms without opening a financial database.
                terms = _object(report["authorization"])
                if original_terms is None:
                    original_terms = terms
                elif trial_fence._actual_terms(terms) != trial_fence._actual_terms(original_terms):
                    raise SourceFeedbackError("feedback history changes original grant terms")
                stack.enter_context(
                    trial_fence.work(authority_path, terms, directory=location, kind="feedback")
                )
            if original_terms is None:
                raise SourceFeedbackError("feedback requires its original measured grant")
            stack.enter_context(
                trial_fence.work(
                    authority_path, original_terms, directory=directory, kind="feedback"
                )
            )
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
