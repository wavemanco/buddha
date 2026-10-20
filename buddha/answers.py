"""Frozen task and ordered-text artifacts; no agent execution or judgment.

TaskSet/Answers retain the full source for the trusted host; an agent receives
individual Tasks only. Source hashes establish consistency, not authenticity.
All records and native output are bounded by the release JSON byte ceiling.
"""

import base64
import binascii
import hashlib
from dataclasses import dataclass, field
from pathlib import Path
from typing import Self, cast

from buddha.releases import (
    MAX_JSON_BYTES,
    Release,
    ReleaseError,
    _digest,
    _json,
    _load,
    _object,
    _text,
    file_hash,
)


def _utf8(value: object) -> str:
    if type(value) is not str:
        raise ReleaseError("task prompts and answers must be literal text")
    try:
        value.encode("utf-8")
    except UnicodeError:
        raise ReleaseError("artifact text must be valid UTF-8") from None
    return value


def _count(value: object) -> int:
    if type(value) is not int or not 1 <= value <= 1000:
        raise ReleaseError("task count must be an integer from 1 to 1000")
    return value


def _id(value: object) -> str | int:
    if type(value) is int and -(2**63) <= value <= 2**63 - 1:
        return value
    if type(value) is str:
        return _text(value)
    raise ReleaseError("task IDs must be bounded strings or signed 64-bit integers")


@dataclass(frozen=True)
class Task:
    id: str | int
    prompt: str
    count: int

    def __post_init__(self) -> None:
        _id(self.id)
        _utf8(self.prompt)
        _count(self.count)

    def to_record(self) -> dict[str, object]:
        return {"id": self.id, "prompt": self.prompt, "count": self.count}


@dataclass(frozen=True)
class _Artifact:
    data: bytes = field(repr=False)

    def __post_init__(self) -> None:
        _load(self.data)

    @classmethod
    def from_bytes(cls, raw: bytes) -> Self:
        return cls(raw)

    def to_record(self) -> dict[str, object]:
        return _load(self.data)

    def to_bytes(self) -> bytes:
        return self.data

    def fingerprint(self) -> str:
        return hashlib.sha256(self.data).hexdigest()


def _population(release: Release, raw: bytes) -> dict[str | int, tuple[Task, dict[str, object]]]:
    if not isinstance(release, Release) or type(raw) is not bytes or len(raw) > MAX_JSON_BYTES:
        raise ReleaseError("tasks require a release and bounded dataset bytes")
    record = release.to_record()
    schema = _object(record["task"])
    source = _object(record["source"])
    if hashlib.sha256(raw).hexdigest() != source[_text(schema["dataset"])]:
        raise ReleaseError("dataset differs from its frozen release source")
    lines = raw.split(b"\n")
    if lines[-1:] == [b""]:
        lines.pop()
    if not 1 <= len(lines) <= 100_000:
        raise ReleaseError("dataset must contain from 1 to 100000 JSONL tasks")
    result = {}
    for line in lines:
        row = _metadata(_load(line), set())
        task = Task(
            _id(row.get(_text(schema["id_field"]))),
            _utf8(row.get(_text(schema["prompt_field"]))),
            _count(schema["count"]),
        )
        if task.id in result:
            raise ReleaseError("dataset task IDs must be unique")
        result[task.id] = (task, row)
    return result


def _source(record: dict[str, object]) -> tuple[Release, bytes]:
    release = Release.from_record(record["release"])
    encoded = record["dataset_base64"]
    try:
        if type(encoded) is not str:
            raise ValueError("invalid dataset encoding")
        raw = base64.b64decode(encoded, validate=True)
        if base64.b64encode(raw).decode("ascii") != encoded:
            raise ValueError("noncanonical dataset encoding")
    except (ValueError, binascii.Error):
        raise ReleaseError("dataset must use canonical base64") from None
    return release, raw


def _selected(
    population: dict[str | int, tuple[Task, dict[str, object]]], ids: object
) -> list[tuple[Task, dict[str, object]]]:
    if type(ids) is not list or not 1 <= len(ids) <= len(population):
        raise ReleaseError("selection must name a bounded nonempty task population")
    result = []
    seen = set()
    for value in ids:
        key = _id(value)
        if key not in population or key in seen:
            raise ReleaseError("selected task IDs must be known and unique")
        seen.add(key)
        result.append(population[key])
    return result


@dataclass(frozen=True)
class TaskSet(_Artifact):
    def __post_init__(self) -> None:
        record = _object(
            _load(self.data),
            {
                "format",
                "release",
                "release_sha256",
                "dataset_sha256",
                "dataset_base64",
                "selection",
                "tasks",
            },
        )
        if record["format"] != "buddha.tasks.v1":
            raise ReleaseError("unsupported task artifact")
        release, raw = _source(record)
        if _digest(record["release_sha256"]) != release.fingerprint():
            raise ReleaseError("task release identity differs")
        selected = _selected(_population(release, raw), record["selection"])
        if hashlib.sha256(raw).hexdigest() != _digest(record["dataset_sha256"]) or _json(
            record["tasks"]
        ) != _json([task.to_record() for task, _ in selected]):
            raise ReleaseError("derived tasks differ from their frozen dataset")
        object.__setattr__(self, "data", _json(record))

    @classmethod
    def from_dataset(cls, release: Release, raw: bytes) -> Self:
        population = _population(release, raw)
        return cls(
            _json(
                {
                    "format": "buddha.tasks.v1",
                    "release": release.to_record(),
                    "release_sha256": release.fingerprint(),
                    "dataset_sha256": hashlib.sha256(raw).hexdigest(),
                    "dataset_base64": base64.b64encode(raw).decode("ascii"),
                    "selection": list(population),
                    "tasks": [task.to_record() for task, _ in population.values()],
                }
            )
        )

    @classmethod
    def from_file(cls, release: Release, path: Path) -> Self:
        if not isinstance(release, Release):
            raise ReleaseError("tasks require a frozen release")
        digest = file_hash(path, max_bytes=MAX_JSON_BYTES)
        record = release.to_record()
        if digest != _object(record["source"])[_text(_object(record["task"])["dataset"])]:
            raise ReleaseError("dataset differs from its frozen release source")
        try:
            with path.open("rb") as stream:
                raw = stream.read(MAX_JSON_BYTES + 1)
        except OSError:
            raise ReleaseError("task dataset could not be read") from None
        if hashlib.sha256(raw).hexdigest() != digest:
            raise ReleaseError("task dataset changed during read")
        return cls.from_dataset(release, raw)

    def select(self, ordered_ids: object) -> Self:
        """Select an explicit host-owned population; preserve the entire sealed source."""
        record = self.to_record()
        release, raw = _source(record)
        selected = _selected(_population(release, raw), ordered_ids)
        record["selection"] = [task.id for task, _ in selected]
        record["tasks"] = [task.to_record() for task, _ in selected]
        return type(self)(_json(record))

    @property
    def tasks(self) -> tuple[Task, ...]:
        return tuple(
            Task(_id(row["id"]), _utf8(row["prompt"]), _count(row["count"]))
            for value in cast(list[object], self.to_record()["tasks"])
            for row in [_object(value)]
        )

    @property
    def release_sha256(self) -> str:
        return _digest(self.to_record()["release_sha256"])

    @property
    def dataset_sha256(self) -> str:
        return _digest(self.to_record()["dataset_sha256"])


def _metadata(value: object, mapped: set[str]) -> dict[str, object]:
    _json(value)  # Reject cycles, nonfinite numbers and oversized data before walking it.
    record = _object(value)
    if set(record) & mapped:
        raise ReleaseError("metadata cannot override mapped native fields")
    pending: list[object] = [record]
    while pending:
        item = pending.pop()
        if type(item) is str:
            _utf8(item)
        elif type(item) is dict:
            pending.extend(_object(item).keys())
            pending.extend(item.values())
        elif type(item) is list:
            pending.extend(item)
        elif item is not None and type(item) not in {bool, int, float}:
            raise ReleaseError("metadata must use literal JSON values")
    return record


def _native(record: dict[str, object], tasks: TaskSet) -> bytes:
    task_record = tasks.to_record()
    release, raw = _source(task_record)
    schema = _object(release.to_record()["task"])
    fields = [_text(schema[name]) for name in ("id_field", "prompt_field", "answers_field")]
    selected = _selected(_population(release, raw), task_record["selection"])
    metadata = _metadata(
        record["metadata"], set(fields) | {name for _, row in selected for name in row}
    )
    outputs = record["outputs"]
    if type(outputs) is not list or len(outputs) != len(selected):
        raise ReleaseError("answers must cover the exact ordered task population")
    native = bytearray()
    for (task, source), value in zip(selected, outputs, strict=True):
        output = _object(value, {"task_id", "answers"})
        answers = output["answers"]
        if (
            _id(output["task_id"]) != task.id
            or type(answers) is not list
            or len(answers) != task.count
        ):
            raise ReleaseError("answer IDs, order or outer count differ from the frozen tasks")
        texts = [_utf8(answer) for answer in answers]
        row = source | metadata | {fields[2]: texts}
        encoded = _json(row) + b"\n"
        if len(native) + len(encoded) > MAX_JSON_BYTES:
            raise ReleaseError("native answer artifact exceeds the byte ceiling")
        native.extend(encoded)
    return bytes(native)


@dataclass(frozen=True)
class Answers(_Artifact):
    def __post_init__(self) -> None:
        record = _object(
            _load(self.data),
            {"format", "tasks", "tasks_sha256", "agent_sha256", "metadata", "outputs"},
        )
        if record["format"] != "buddha.answers.v1":
            raise ReleaseError("unsupported answer artifact")
        tasks = TaskSet.from_bytes(_json(record["tasks"]))
        if _digest(record["tasks_sha256"]) != tasks.fingerprint():
            raise ReleaseError("answer population differs from its frozen task artifact")
        _digest(record["agent_sha256"])
        _native(record, tasks)
        object.__setattr__(self, "data", _json(record))

    @classmethod
    def from_results(
        cls,
        release: Release,
        tasks: TaskSet,
        ordered_outputs: object,
        *,
        agent_sha256: str,
        metadata: object,
    ) -> Self:
        if not isinstance(release, Release) or not isinstance(tasks, TaskSet):
            raise ReleaseError("answers require frozen release and task artifacts")
        if release.fingerprint() != tasks.release_sha256:
            raise ReleaseError("answer release differs from its task population")
        schema = _object(release.to_record()["task"])
        _metadata(
            metadata,
            {_text(schema[name]) for name in ("id_field", "prompt_field", "answers_field")},
        )
        if type(ordered_outputs) is not list:
            raise ReleaseError("ordered results must be a literal data list")
        return cls(
            _json(
                {
                    "format": "buddha.answers.v1",
                    "tasks": tasks.to_record(),
                    "tasks_sha256": tasks.fingerprint(),
                    "agent_sha256": agent_sha256,
                    "metadata": metadata,
                    "outputs": ordered_outputs,
                }
            )
        )

    def native_bytes(self) -> bytes:
        record = self.to_record()
        return _native(record, TaskSet.from_bytes(_json(record["tasks"])))
