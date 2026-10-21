"""Pure pre-answer panel coordinates; the resulting map is private host data.

Caller-trusted publication pins establish identity, not prior publication time.
No answers, file readers, spending authority or review outcomes are consumed.
Deterministic labels provide procedural masking, not cryptographic blinding.
"""

import hashlib
from typing import cast

from buddha.answers import _id, _population, _source, _utf8
from buddha.policy_study import PolicyStudy, validate_intent
from buddha.releases import MAX_JSON_BYTES, ReleaseError, _digest, _json, _load, _object, _text

MAX_PANEL_POSITIONS = 100_000


class PolicyPanelError(ReleaseError):
    """The pinned panel coordinates contradict the reviewed study or source."""


def _pinned(raw: bytes, expected: str) -> dict[str, object]:
    if (
        type(raw) is not bytes
        or len(raw) > MAX_JSON_BYTES
        or hashlib.sha256(raw).hexdigest() != _digest(expected)
    ):
        raise PolicyPanelError("panel publication bytes differ from the trusted pin")
    return _load(raw)


def _label(vector: list[object]) -> str:
    return hashlib.sha256(_json(vector)).hexdigest()


def plan_panel(
    study: PolicyStudy,
    *,
    intent_raw: bytes,
    expected_intent_sha256: str,
    source_review_raw: bytes,
    expected_source_review_sha256: str,
    expected_protocol_sha256: str,
) -> dict[str, object]:
    """Bind reviewed membership and derive every prospective masked coordinate.

    Positions use each task's declared count. More than MAX_PANEL_POSITIONS
    planned answer appearances fails before label expansion; none are sampled.
    Generation/judging availability and answer-text bindings belong to the
    later materializer, not this pre-answer map.
    """
    try:
        if not isinstance(study, PolicyStudy):
            raise PolicyPanelError("panel requires an immutable policy study")
        intent = _pinned(intent_raw, expected_intent_sha256)
        review = _pinned(source_review_raw, expected_source_review_sha256)
        protocol_sha256 = _digest(expected_protocol_sha256)
        validate_intent(study, intent, protocol_sha256)

        declaration = study.to_record()
        release, dataset = _source(_object(declaration["source"]))
        population = _population(release, dataset)
        source = _object(review["source"])
        if (
            review["format"] != "buddha.policy-study-source-review.v1"
            or _digest(source["dataset_sha256"]) != hashlib.sha256(dataset).hexdigest()
        ):
            raise PolicyPanelError("panel source review differs from the complete source")
        categories = {
            identifier: _utf8(_text(row.get("category")))
            for identifier, (_task, row) in population.items()
        }
        category_order = list(dict.fromkeys(categories.values()))
        tasks = study.tasks
        selected = tasks.tasks
        selected_by_id = {task.id: task for task in selected}
        reviewed = review["selected"]
        if type(reviewed) is not list or len(reviewed) != len(selected):
            raise PolicyPanelError("source review must cover the selected population")
        for task, item in zip(selected, reviewed, strict=True):
            row = _object(item)
            if (
                _id(row["id"]) != task.id
                or row["category"] != categories[task.id]
                or _digest(row["prompt_sha256"]) != hashlib.sha256(task.prompt.encode()).hexdigest()
            ):
                raise PolicyPanelError("reviewed task identity, category or literal prompt differs")

        panel = _object(review["supplemental_panel"])
        identifiers, repeats = panel["ids"], panel["generation_repeats"]
        if (
            type(identifiers) is not list
            or type(repeats) is not list
            or len(identifiers) != len(category_order)
            or len(repeats) != len(category_order)
        ):
            raise PolicyPanelError("panel must declare one task per source category")
        identifiers = [_id(identifier) for identifier in identifiers]
        if len(set(identifiers)) != len(identifiers):
            raise PolicyPanelError("panel repeats a source task")
        for index, (identifier, repeat) in enumerate(zip(identifiers, repeats, strict=True)):
            if (
                identifier not in selected_by_id
                or categories[identifier] != category_order[index]
                or type(repeat) is not int
                or repeat != index % 2
                or repeat >= cast(int, declaration["generation_repeats"])
            ):
                raise PolicyPanelError("panel changes reviewed category order or repetition")
        planned = 4 * sum(selected_by_id[identifier].count for identifier in identifiers)
        counts = {"conditions": 4, "complete_answer_sets": 4 * len(identifiers), "answers": planned}
        if any(type(panel[key]) is not int or panel[key] != value for key, value in counts.items()):
            raise PolicyPanelError("panel declared counts differ from its complete coordinates")
        if planned > MAX_PANEL_POSITIONS:
            raise PolicyPanelError("planned panel positions exceed the explicit ceiling")

        cells = {
            (cell["arm_index"], cell["generation_repeat"]): cell["cell_id"]
            for cell in study.schedule()
        }
        labels: set[str] = set()

        def label(vector: list[object]) -> str:
            digest = _digest(_label(vector))
            if digest in labels:
                raise PolicyPanelError("panel label collision")
            labels.add(digest)
            return digest

        sets = []
        for identifier, repeat in zip(identifiers, repeats, strict=True):
            for arm in range(4):
                vector: list[object] = ["pol02-panel-v1", identifier, arm, repeat]
                set_id = label(vector)
                answers = [
                    {"id": label([*vector, position]), "position": position}
                    for position in range(selected_by_id[identifier].count)
                ]
                sets.append(
                    {
                        "id": set_id,
                        "task_id": identifier,
                        "arm_index": arm,
                        "generation_repeat": repeat,
                        "cell_id": cells[arm, repeat],
                        "answers": sorted(answers, key=lambda row: cast(str, row["id"])),
                    }
                )
        result: dict[str, object] = {
            "format": "buddha.policy-panel-plan.v1",
            "study_sha256": study.fingerprint(),
            "tasks_sha256": tasks.fingerprint(),
            "input_sha256": {
                "intent": expected_intent_sha256,
                "source_review": expected_source_review_sha256,
                "protocol": protocol_sha256,
            },
            "rules": {
                "hash_domain": "pol02-panel-v1",
                "labels": "full_lowercase_sha256",
                "set_order": "ascending_digest",
                "answer_order": "ascending_digest",
                "position_index_base": 0,
                "collision": "error",
            },
            "counts": {"tasks": len(identifiers), "sets": len(sets), "positions": planned},
            "sets": sorted(sets, key=lambda row: cast(str, row["id"])),
        }
        _json(result)
        return result
    except (ReleaseError, ValueError, TypeError, KeyError, UnicodeError, RecursionError):
        raise PolicyPanelError("invalid pinned pre-answer panel data") from None
