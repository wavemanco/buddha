"""Frozen development-only policy factors and prospective repetition identities.

This is host-side data, including the complete source population. It neither
authorizes execution nor chooses an instrument, funding, display order or analysis.
Only individual selected Tasks belong at the existing generation boundary.
"""

import hashlib
from dataclasses import dataclass
from typing import cast

from buddha.answers import TaskSet, _Artifact, _id, _source, _utf8
from buddha.releases import ReleaseError, _digest, _json, _load, _object, _text


class PolicyStudyError(ReleaseError):
    """The frozen comparison has invalid factors, population or repetition data."""


def _number(value: object, minimum: int, maximum: int) -> int:
    if type(value) is not int or not minimum <= value <= maximum:
        raise PolicyStudyError("study count or index is outside its declared bounds")
    return value


def _ids(value: object, known: set[str | int]) -> list[str | int]:
    if type(value) is not list or not 1 <= len(value) <= len(known):
        raise PolicyStudyError("study population must be a nonempty bounded ID list")
    result = [_id(item) for item in value]
    if len(set(result)) != len(result) or not set(result) <= known:
        raise PolicyStudyError("study population contains repeated or unknown IDs")
    return result


def _split(value: object, source: TaskSet) -> set[str | int]:
    split = _object(value, {"release_sha256", "dataset_sha256", "partitions", "families"})
    if (
        _digest(split["release_sha256"]) != source.release_sha256
        or _digest(split["dataset_sha256"]) != source.dataset_sha256
    ):
        raise PolicyStudyError("study split differs from its frozen source")
    tasks = source.tasks
    known = {task.id for task in tasks}
    partitions = _object(split["partitions"], {"development", "validation", "final"})
    assigned: dict[str | int, str] = {}
    for name, values in partitions.items():
        for identifier in _ids(values, known):
            if identifier in assigned:
                raise PolicyStudyError("source task occupies more than one partition")
            assigned[identifier] = name
    if set(assigned) != known:
        raise PolicyStudyError("study split omits source tasks")

    families = split["families"]
    if type(families) is not list or len(families) != len(tasks):
        raise PolicyStudyError("study families must cover every source task once")
    declared: set[str | int] = set()
    family_partitions: dict[str, str] = {}
    for item in families:
        family = _object(item, {"id", "family"})
        identifier, label = _id(family["id"]), _text(family["family"])
        if identifier not in assigned or identifier in declared:
            raise PolicyStudyError("family declaration repeats or changes a source ID")
        declared.add(identifier)
        name = assigned[identifier]
        if family_partitions.setdefault(label, name) != name:
            raise PolicyStudyError("declared source family crosses partitions")

    normalized: dict[str, str] = {}
    for task in tasks:
        signature = " ".join(task.prompt.split()).casefold()
        name = assigned[task.id]
        if normalized.setdefault(signature, name) != name:
            raise PolicyStudyError("normalized duplicate prompts cross partitions")
    return {identifier for identifier, name in assigned.items() if name == "development"}


def _arms(record: dict[str, object]) -> list[dict[str, object]]:
    instructions = _object(record["child_policy"])["instructions"]
    generation = _object(record["generation"])
    result = []
    for index, (text, sampling) in enumerate(
        (
            ("", "regenerate"),
            ("", "in-context"),
            (instructions, "regenerate"),
            (instructions, "in-context"),
        )
    ):
        policy = {"instructions": text, "sampling": sampling}
        result.append(
            {
                "index": index,
                "arm_id": hashlib.sha256(_json(policy)).hexdigest(),
                "policy": policy,
                "config": generation | policy,
            }
        )
    return result


@dataclass(frozen=True)
class PolicyStudy(_Artifact):
    """An immutable declared matrix, with fresh data views and no execution effects."""

    def __post_init__(self) -> None:
        try:
            record = _object(
                _load(self.data),
                {
                    "format",
                    "source",
                    "split",
                    "selected_ids",
                    "child_policy",
                    "generation",
                    "generation_repeats",
                    "judge_occasions",
                    "execution_order",
                },
            )
            if record["format"] != "buddha.policy-study.v1":
                raise PolicyStudyError("unsupported policy study format")
            source = TaskSet.from_bytes(_json(record["source"]))
            release, dataset = _source(source.to_record())
            full = TaskSet.from_dataset(release, dataset)
            if {task.id for task in source.tasks} != {task.id for task in full.tasks}:
                raise PolicyStudyError("study source is only a partial population view")
            development = _split(record["split"], full)
            _ids(record["selected_ids"], development)

            policy = _object(record["child_policy"], {"instructions", "sampling"})
            instructions = _utf8(policy["instructions"])
            if (
                not instructions.strip()
                or len(instructions) > 4000
                or type(policy["sampling"]) is not str
                or policy["sampling"] not in {"regenerate", "in-context"}
            ):
                raise PolicyStudyError("study child policy differs from the fixed policy contract")
            generation = _object(record["generation"], {"provider", "model", "max_output_tokens"})
            if type(generation["provider"]) is not str or generation["provider"] not in {
                "openai",
                "anthropic",
            }:
                raise PolicyStudyError("study generation provider is unsupported")
            _text(generation["model"])
            _number(generation["max_output_tokens"], 1, 2**63 - 1)
            repeats = _number(record["generation_repeats"], 2, 100)
            _number(record["judge_occasions"], 2, 16)
            order = record["execution_order"]
            if type(order) is not list or len(order) != 4 * repeats:
                raise PolicyStudyError("study order must include every arm and repetition")
            seen = set()
            for item in order:
                cell = _object(item, {"arm", "repeat"})
                identity = (_number(cell["arm"], 0, 3), _number(cell["repeat"], 0, repeats - 1))
                if identity in seen:
                    raise PolicyStudyError("study order repeats a generation cell")
                seen.add(identity)
            object.__setattr__(self, "data", _json(record))
        except (ReleaseError, TypeError, KeyError, ValueError, RecursionError):
            raise PolicyStudyError("invalid frozen policy study data") from None

    @property
    def tasks(self) -> TaskSet:
        """Derive selected source tasks; this artifact still retains host-only source data."""
        record = self.to_record()
        return TaskSet.from_bytes(_json(record["source"])).select(record["selected_ids"])

    @property
    def arms(self) -> list[dict[str, object]]:
        return _arms(self.to_record())

    def schedule(self) -> list[dict[str, object]]:
        record = self.to_record()
        arms = _arms(record)
        tasks = TaskSet.from_bytes(_json(record["source"])).select(record["selected_ids"])
        tasks_sha256, study_sha256 = tasks.fingerprint(), self.fingerprint()
        result = []
        for item in cast(list[object], record["execution_order"]):
            order = _object(item)
            arm_index, repeat = cast(int, order["arm"]), cast(int, order["repeat"])
            arm = arms[arm_index]
            cell_id = hashlib.sha256(
                _json(["buddha.policy-study-cell.v1", study_sha256, arm["arm_id"], repeat])
            ).hexdigest()
            result.append(
                {
                    "cell_id": cell_id,
                    "arm_id": arm["arm_id"],
                    "arm_index": arm_index,
                    "generation_repeat": repeat,
                    "tasks_sha256": tasks_sha256,
                    "generation_config": _object(arm["config"]).copy(),
                    "judge_occasions": [
                        {
                            "index": index,
                            "occasion_id": hashlib.sha256(
                                _json(["buddha.policy-study-judgment.v1", cell_id, index])
                            ).hexdigest(),
                        }
                        for index in range(cast(int, record["judge_occasions"]))
                    ],
                }
            )
        return result


def validate_intent(study: PolicyStudy, value: object, protocol_sha256: str) -> None:
    """Join reviewed publication data to the complete study, without reading files.

    The caller verifies original byte pins; this check establishes data consistency,
    not publication time or authenticity.
    """
    try:
        if not isinstance(study, PolicyStudy):
            raise PolicyStudyError("a frozen study is required")
        _digest(protocol_sha256)
        record = _object(value, {"format", "protocol_sha256", "release", "study", "expected"})
        source = TaskSet.from_bytes(_json(study.to_record()["source"]))
        declaration = study.to_record()
        del declaration["source"]
        expected = {
            "release_sha256": source.release_sha256,
            "source_tasks_sha256": source.fingerprint(),
            "selected_tasks_sha256": study.tasks.fingerprint(),
            "study_sha256": study.fingerprint(),
            "arm_ids": [row["arm_id"] for row in study.arms],
            "cell_ids": [row["cell_id"] for row in study.schedule()],
        }
        if (
            record["format"] != "buddha.policy-study-intent.v1"
            or record["protocol_sha256"] != protocol_sha256
            or _json(record["release"]) != _json(source.to_record()["release"])
            or _json(record["study"]) != _json(declaration)
            or _json(record["expected"]) != _json(expected)
        ):
            raise PolicyStudyError("reviewed intent differs from the frozen study")
    except (ReleaseError, TypeError, KeyError, ValueError, RecursionError):
        raise PolicyStudyError("reviewed intent differs from the frozen study") from None
