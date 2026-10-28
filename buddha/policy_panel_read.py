"""Passive C1-to-panel custody; reviewer data and private coverage stay separate."""

import hashlib
import sqlite3
from pathlib import Path
from typing import cast

from buddha.answers import _id
from buddha.doctor import _Busy, _Unsupported
from buddha.native_evaluation import _Generation, _read_generation
from buddha.policy_panel import _materials as panel_materials
from buddha.policy_panel import _pinned, plan_panel
from buddha.policy_results import _Reader, _rows, _same
from buddha.releases import ReleaseError, _digest, _json, _object, _root, _text


class PolicyPanelReadError(ReleaseError):
    """The original panel, generation custody or stable observation is invalid."""


def _sha(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()


def _materials(
    raw: bytes, expected: str, protocol: bytes, protocol_sha256: str, release: dict[str, object]
) -> tuple[dict[str, object], str]:
    try:
        return panel_materials(raw, expected, protocol, protocol_sha256, release)
    except ReleaseError:
        raise PolicyPanelReadError(
            "review materials differ from their reviewed release/protocol"
        ) from None


def materialize_panel(
    directory: Path,
    *,
    intent: Path,
    protocol: Path,
    source_review: Path,
    expected_intent_sha256: str,
    expected_protocol_sha256: str,
    expected_source_review_sha256: str,
    authorization: Path,
    plan_raw: bytes,
    expected_plan_sha256: str,
    review_materials_raw: bytes,
    expected_review_materials_sha256: str,
) -> dict[str, object]:
    """Read anchored generation without running producers or inspecting score files.

    The return value contains a reviewer-only ``packet`` and a host-only
    ``private`` receipt. This function writes neither. Supplied pins establish
    reviewed identity, not authentication that publication preceded generation.
    """
    try:
        if any(
            not isinstance(path, Path)
            for path in (directory, intent, protocol, source_review, authorization)
        ):
            raise PolicyPanelReadError("explicit original evidence Paths required")
        directory, authorization = directory.absolute(), authorization.absolute()
        _root(directory)
        reader = _Reader(directory, authorization)
        intent_raw = reader.raw(intent.absolute(), _digest(expected_intent_sha256))
        review_raw = reader.raw(source_review.absolute(), _digest(expected_source_review_sha256))
        protocol_raw = reader.raw(protocol.absolute(), _digest(expected_protocol_sha256))
        anchor = reader.owner(directory / "cells/0/baseline/owners/0")
        study, execution = reader.definition(anchor)
        planned = _pinned(plan_raw, expected_plan_sha256)
        expected_plan = plan_panel(
            study,
            intent_raw=intent_raw,
            expected_intent_sha256=expected_intent_sha256,
            source_review_raw=review_raw,
            expected_source_review_sha256=expected_source_review_sha256,
            expected_protocol_sha256=expected_protocol_sha256,
        )
        if not _same(planned, expected_plan):
            raise PolicyPanelReadError("saved pre-answer mapping differs from original coordinates")
        rule, rubric = _materials(
            review_materials_raw,
            expected_review_materials_sha256,
            protocol_raw,
            expected_protocol_sha256,
            reader.release.to_record(),
        )
        if len(_rows(reader.template["stages"])) != 3:
            raise PolicyPanelReadError("this registered panel requires the three-stage study")
        reader.scheduled_owners(study, ["grouping", "quality", "summary"])
        reader.funding(execution, study)

        schedule = study.schedule()
        # Inspect every retained generation, including cells not represented by
        # this smaller panel; contradictory source custody is never discarded.
        sources: dict[str, _Generation] = {}
        unavailable: dict[str, str] = {}
        references: dict[str, dict[str, object]] = {}
        for index, cell in enumerate(schedule):
            cell_id = _text(cell["cell_id"])
            base = directory / "cells" / str(index) / "baseline"
            owner = reader.owners.get(base / "owners/0")
            seal = base / "completed/0.json"
            sealed = seal.relative_to(directory).as_posix() in reader.capture.entries
            if owner is None:
                if sealed:
                    raise PolicyPanelReadError("generation seal lacks its original owner")
                unavailable[cell_id] = "generation_not_prepared"
                continue
            reader.cell_definition(index, cell)
            anchors = [
                row
                for row in _rows(reader.funded["auth_deactivations"])
                if row["run_id"] == owner.run_id
            ]
            if not sealed:
                if any(str(row["reason"]).startswith("baseline completed:") for row in anchors):
                    raise PolicyPanelReadError("anchored generation seal is missing")
                unavailable[cell_id] = (
                    "generation_not_started" if not owner.operations else "generation_unsealed"
                )
                continue
            reference = reader.generation_reference(base)
            if [row["reason"] for row in anchors] != [
                "baseline completed: " + _text(reference["stage_seal_sha256"])
            ]:
                raise PolicyPanelReadError("generation lacks its captured authority anchor")
            generated = _read_generation(reference, authorization)
            if generated.tasks.fingerprint() != study.tasks.fingerprint():
                raise PolicyPanelReadError(
                    "generation changes the original selected task population"
                )
            for path, expected in generated.files.items():
                reader.raw(path, expected)
            sources[cell_id] = generated
            references[cell_id] = reference

        tasks = {task.id: task for task in study.tasks.tasks}
        items: list[dict[str, object]] = []
        private_sets: list[dict[str, object]] = []
        available_positions = 0
        for planned_set in _rows(planned["sets"]):
            cell_id = _text(planned_set["cell_id"])
            identifier = _id(planned_set["task_id"])
            positions = _rows(planned_set["answers"])
            source = sources.get(cell_id)
            binding: dict[str, object] | None = None
            answer_bindings: list[dict[str, object]] = []
            if source is not None:
                outputs = {
                    row["task_id"]: cast(list[str], row["answers"])
                    for row in _rows(source.answers.to_record()["outputs"])
                }
                texts = outputs[identifier]
                public_answers = []
                for position in positions:
                    text = texts[cast(int, position["position"])]
                    public_answers.append({"id": position["id"], "text": text})
                    answer_bindings.append(position | {"text_utf8_sha256": _sha(text.encode())})
                items.append(
                    {
                        "id": planned_set["id"],
                        "prompt": tasks[identifier].prompt,
                        "answers": public_answers,
                    }
                )
                available_positions += len(public_answers)
                binding = {
                    "source_generation": references[cell_id],
                    "answers_path": str(source.answers_path),
                    "answers_file_sha256": _sha(reader.capture.raw[source.answers_path]),
                    "answers_sha256": source.answers.fingerprint(),
                    "derived_native_answers_sha256": _sha(source.answers.native_bytes()),
                }
            else:
                answer_bindings = [row | {"text_utf8_sha256": None} for row in positions]
            private_sets.append(
                planned_set
                | {
                    "state": "available" if source is not None else "unavailable",
                    "reason": None if source is not None else unavailable[cell_id],
                    "binding": binding,
                    "answers": answer_bindings,
                }
            )
        packet: dict[str, object] = {
            "format": "buddha.policy-panel-packet.v1",
            "rule": rule,
            "rubric": rubric,
            "items": items,
        }
        packet_raw = _json(packet)
        counts = _object(planned["counts"])
        sets, positions_count = cast(int, counts["sets"]), cast(int, counts["positions"])
        fingerprints = reader.fingerprints()
        private: dict[str, object] = {
            "format": "buddha.policy-panel-materialization.v1",
            "status": "complete" if len(items) == sets else "incomplete",
            "coverage": {
                "planned_sets": sets,
                "available_sets": len(items),
                "unavailable_sets": sets - len(items),
                "planned_positions": positions_count,
                "available_positions": available_positions,
                "unavailable_positions": positions_count - available_positions,
            },
            "plan_sha256": expected_plan_sha256,
            "review_materials_sha256": expected_review_materials_sha256,
            "study_sha256": study.fingerprint(),
            "packet_sha256": _sha(packet_raw),
            "sets": private_sets,
            "provenance": {
                "consumed_files": fingerprints,
                "owners": [
                    {
                        "directory": str(owner.directory),
                        "run_id": owner.run_id,
                        "manifest_sha256": owner.manifest_sha256,
                        "ledger_sha256": owner.ledger_sha256,
                    }
                    for owner in reader.owners.values()
                ],
            },
            "current_shared_accounting": reader.funded["totals"],
            "limitations": [
                "Pins and stable bytes do not authenticate publication time or provider origin.",
                "Deterministic labels provide procedural masking, not secrecy.",
                "Generation coverage is separate from study/judge coverage and review completion.",
            ],
        }
        result: dict[str, object] = {"packet": packet, "private": private}
        _json(result)
        return result
    except (
        ValueError,
        TypeError,
        KeyError,
        IndexError,
        OSError,
        RecursionError,
        sqlite3.Error,
        _Busy,
        _Unsupported,
    ):
        raise PolicyPanelReadError(
            "panel evidence is invalid or changed; original state retained"
        ) from None
