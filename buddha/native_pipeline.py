"""Shared native artifact flow and single-stage lifecycle; no generation imports."""

import hashlib
import json
import os
from collections.abc import Callable, Iterator
from contextlib import contextmanager
from pathlib import Path
from typing import Any, cast

from buddha import executor
from buddha.answers import TaskSet, _id
from buddha.authorization import Authorization
from buddha.gateway import Gateway, _read_manifest
from buddha.releases import (
    MAX_JSON_BYTES,
    ROLES,
    Release,
    ReleaseError,
    Selection,
    _json,
    _load,
    _object,
    _pairs,
    _path,
    _paths,
    _root,
    _text,
    file_hash,
    inventory,
    verify_selection,
)


class PipelineError(ReleaseError):
    """A native artifact-flow or stage identity is invalid."""


def _sha(value: object) -> str:
    return hashlib.sha256(_json(value)).hexdigest()


def _read(path: Path, expected: object = None) -> bytes:
    digest = file_hash(path, max_bytes=MAX_JSON_BYTES)
    with path.open("rb") as stream:
        raw = stream.read(MAX_JSON_BYTES + 1)
    if (
        len(raw) > MAX_JSON_BYTES
        or hashlib.sha256(raw).hexdigest() != digest
        or (expected is not None and digest != expected)
    ):
        raise PipelineError("baseline input changed while consumed")
    return raw


def _write(path: Path, raw: bytes) -> None:
    _root(path.parent)
    with path.open("xb") as stream:
        stream.write(raw)
        stream.flush()
        os.fsync(stream.fileno())


def _same_or_write(path: Path, raw: bytes) -> None:
    if path.exists():
        if _read(path) != raw:
            raise PipelineError("an existing stage input or descriptor differs; owner retained")
    else:
        _write(path, raw)


def _absolute(value: object) -> Path:
    path = Path(_text(value))
    if not path.is_absolute():
        raise PipelineError("baseline paths must be absolute")
    return path


def _component(value: object) -> tuple[Selection, dict[str, Path]]:
    record = _object(value)
    selection = Selection.from_bytes(_json(record["selection"]))
    roots = {key: _absolute(path) for key, path in _object(record["roots"], set(ROLES)).items()}
    verify_selection(selection, roots, expected_sha256=selection.fingerprint())
    for name in ("budget_microusd", "max_calls"):
        if type(record[name]) is not int or not 0 < cast(int, record[name]) < 2**63:
            raise PipelineError("stage ceilings must be positive bounded integers")
    return selection, roots


def _coverage(path: Path, field: str, tasks: TaskSet, expected_digest: object) -> None:
    # Inspect only the population seam. Native numerical content (even NaN) is
    # preserved literally and is never interpreted as host benchmark arithmetic.
    try:
        rows = _read(path, expected_digest).splitlines()
        found = [_id(_object(json.loads(row, object_pairs_hook=_pairs))[field]) for row in rows]
    except (ValueError, KeyError, UnicodeError, RecursionError):
        raise PipelineError("native output has invalid selected-population rows") from None
    expected = [task.id for task in tasks.tasks]
    if len(found) != len(expected) or len(set(found)) != len(found) or set(found) != set(expected):
        raise PipelineError("native output omits, repeats or changes selected typed task IDs")


@contextmanager
def _exclusive(directory: Path) -> Iterator[None]:
    _root(directory)
    path = directory / "running.lock"
    try:
        stream = path.open("xb")
    except FileExistsError:
        raise PipelineError(
            "baseline is already running or has a retained interrupted lock"
        ) from None
    try:
        with stream:
            stream.write(str(os.getpid()).encode("ascii"))
            stream.flush()
        yield
    finally:
        path.unlink()


def _native_descriptor(
    directory: Path,
    index: int,
    definition: dict[str, object],
    release: Release,
    answers: Path,
    available: dict[str, Path],
    frozen_files: dict[Path, str],
) -> tuple[Path, list[Path]]:
    native = _object(definition["native"])
    selected, roots = _component(native)
    flow = _object(cast(list[object], definition["stages"])[index - 1])
    staging = directory / "staging" / str(index)
    if not staging.exists():
        staging.mkdir()
    _root(staging)
    inputs = []
    paths = []
    for ordinal, name in enumerate(cast(list[str], flow["inputs"])):
        path = staging / (str(ordinal) + ".bin")
        _same_or_write(path, _read(available[name], frozen_files[available[name]]))
        paths.append(path)
        inputs.append({"source": path.name, "destination": name, "sha256": file_hash(path)})
    if inventory(staging) != {path.name: file_hash(path) for path in paths}:
        raise PipelineError("unexpected files in native input staging")
    command = cast(list[dict[str, object]], release.to_record()["commands"])[index - 1]
    configured = {
        "index": index - 1,
        "module": command["module"],
        "argv": [
            "/scratch/artifacts" if argument == "{artifacts}" else argument
            for argument in cast(list[str], command["argv"])
        ],
    }
    configured["sha256"] = _sha(configured)
    components = _object(selected.to_record()["components"])
    record = {
        "format": "buddha.native-command.v1",
        "worker": {
            "type": "configure",
            "format": "buddha.native-worker.v1",
            "command": configured,
            "release_sha256": release.fingerprint(),
            # This is the exact exported C1 file digest, distinct from its logical
            # canonical artifact digest and the separately materialized native bytes.
            "answers_sha256": file_hash(answers),
            "roots": {
                "official": "/official",
                "runner": "/runner",
                "environment": "/opt/venv",
                "inputs": "/inputs",
                "artifacts": "/scratch/artifacts",
            },
            "inventories": {
                "official": components["official"],
                "runner": components["runner"],
                "environment": native["environment"],
            },
            "inputs": inputs,
            "hooks": native["hooks"],
        },
        "executor": _object(native["executor"])
        | {
            "mounts": [
                ["/official", str(roots["official"])],
                ["/runner", str(roots["runner"])],
                ["/inputs", str(staging)],
            ],
        },
        "profiles": native["profiles"] if flow["allow_model"] else {},
    }
    descriptor = directory / ("command-" + str(index) + ".json")
    _same_or_write(descriptor, _json(record))
    return descriptor, paths


def validate_native_flow(stages: object, release: Release) -> None:
    """Validate declared artifact flow without reading component paths."""
    record = release.to_record()
    artifacts = _object(record["artifacts"])
    commands = cast(list[dict[str, object]], record["commands"])
    if type(stages) is not list or len(stages) != len(commands):
        raise PipelineError("each configured native command needs one stage")
    available = {_path(artifacts["answers"])}
    expected = {*cast(list[str], artifacts["results"]), _path(artifacts["summary"])}
    produced: set[str] = set()
    for index, value in enumerate(stages):
        stage = _object(value, {"inputs", "outputs", "allow_model"})
        inputs = _paths(stage["inputs"])
        outputs = stage["outputs"]
        if (
            not set(inputs) <= available
            or type(outputs) is not list
            or not outputs
            or type(stage["allow_model"]) is not bool
            or stage["allow_model"] != (index < len(stages) - 1)
        ):
            raise PipelineError("stage flow or final no-model role is invalid")
        names = []
        for output in outputs:
            output = _object(output, {"path", "id_field"})
            name = _path(output["path"])
            if output["id_field"] is not None:
                _text(output["id_field"])
            elif name != artifacts["summary"]:
                raise PipelineError("result artifacts require selected-population coverage")
            names.append(name)
        _paths(names)
        if set(names) & available or not set(names) <= expected:
            raise PipelineError("outputs must be new declared release artifacts")
        if (artifacts["summary"] in names) != (index == len(stages) - 1):
            raise PipelineError("the native summary must be the final output")
        available.update(names)
        produced.update(names)
    if produced != expected:
        raise PipelineError("stage flow omits declared release outputs")


def validate_native(native: dict[str, object], stages: object, release: Release) -> None:
    _object(
        native,
        {
            "selection",
            "roots",
            "environment",
            "hooks",
            "executor",
            "profiles",
            "budget_microusd",
            "max_calls",
        },
    )
    _component(native)
    validate_native_flow(stages, release)
    _object(native["environment"])
    _object(native["hooks"], {"modules", "cache", "calls", "sdk"})
    _object(native["profiles"])
    runtime = _object(
        native["executor"],
        {"image_id", "role", "runner_entrypoint", "image_environment", "limits", "docker_endpoint"},
    )
    _, native_roots = _component(native)
    pairs = runtime["image_environment"]
    if type(pairs) is not list or any(type(pair) is not list or len(pair) != 2 for pair in pairs):
        raise PipelineError("invalid native image environment")
    spec = executor.ContainerSpec(
        _text(runtime["image_id"]),
        _text(runtime["role"]),
        (("/official", native_roots["official"]), ("/runner", native_roots["runner"])),
        _path(runtime["runner_entrypoint"]),
        tuple((_text(pair[0]), _text(pair[1])) for pair in pairs),
    )
    if spec.role != "evaluator" or spec.runner_entrypoint != "buddha/native_worker.py":
        raise PipelineError("native baseline requires the bound evaluator worker")
    executor.Limits(
        **cast(
            dict[str, Any], _object(runtime["limits"], set(executor.Limits.__dataclass_fields__))
        )
    )
    executor._local_endpoint(runtime["docker_endpoint"])


def native_outputs(
    attempt: Path,
    report: dict[str, object],
    index: int,
    definition: dict[str, object],
    tasks: TaskSet,
) -> dict[str, Path]:
    if report["status"] != "complete":
        raise PipelineError("incomplete native stage cannot publish coverage")
    declared = _object(report["artifacts"])
    stage = _object(cast(list[object], definition["stages"])[index - 1])
    outputs = {}
    for value in cast(list[object], stage["outputs"]):
        item = _object(value)
        name = _path(item["path"])
        path = attempt / "artifacts" / name
        if file_hash(path) != declared.get(name):
            raise PipelineError("required native artifact is missing or differs from report")
        if item["id_field"] is not None:
            _coverage(path, _text(item["id_field"]), tasks, declared[name])
        outputs[name] = path
    return outputs


def execute_stage(
    directory: Path,
    index: int,
    gateway: Gateway,
    authority: Authorization,
    *,
    run: Callable[[Path], dict[str, object]],
    validate: Callable[[Path, dict[str, object]], dict[str, Path]],
    read: Callable[[Path, object], bytes] = _read,
    seal_format: str = "buddha.baseline-stage.v1",
    anchor_prefix: str = "baseline completed: ",
) -> tuple[dict[str, object], dict[str, Path], dict[str, str], Path | None, Path]:
    """Run one trusted host session or reuse its independently anchored completion.

    The two callables are installed host code, never selected JSON/agent hooks.
    Generation and native callers share this publication boundary.
    """
    sealed = directory / "completed" / (str(index) + ".json")
    if sealed.exists():
        seal_digest = file_hash(sealed)
        owner_id = _read_manifest(gateway.directory)["run_id"]
        if any(
            row["run_id"] == owner_id and row["active"]
            for row in cast(list[dict[str, object]], authority.summary()["runs"])
        ):
            raise PipelineError("existing completion lacks its independent authority anchor")
        authority.deactivate(_text(owner_id), anchor_prefix + seal_digest)
        seal = _object(
            _load(read(sealed, seal_digest)),
            {"format", "index", "owner_sha256", "attempt", "files"},
        )
        attempt = directory / _path(seal["attempt"])
        if (
            seal["format"] != seal_format
            or type(seal["index"]) is not int
            or seal["index"] != index
            or seal["owner_sha256"] != gateway.manifest_sha256
            or not attempt.is_relative_to(directory / "attempts")
            or inventory(attempt) != seal["files"]
        ):
            raise PipelineError("completed stage seal or literal outputs changed")
        files = cast(dict[str, str], seal["files"])
        report = _load(read(attempt / "report.json", files["report.json"]))
        outputs = validate(attempt, report)
    else:
        ordinal = 0
        while (directory / "attempts" / f"{index}-{ordinal}").exists():
            ordinal += 1
        attempt = directory / "attempts" / f"{index}-{ordinal}"
        report = run(attempt)
        if report["status"] != "complete":
            return report, {}, {}, None, attempt
        outputs = validate(attempt, report)
        files = inventory(attempt)
        if read(attempt / "report.json", files["report.json"]) != _json(report) + b"\n":
            raise PipelineError("stored stage report differs from the actual session")
        for name, digest in _object(report["artifacts"]).items():
            relative = name if index == 0 else "artifacts/" + name
            if files.get(relative) != digest:
                raise PipelineError("stage artifact changed before completion sealing")
        seal_bytes = _json(
            {
                "format": seal_format,
                "index": index,
                "owner_sha256": gateway.manifest_sha256,
                "attempt": attempt.relative_to(directory).as_posix(),
                "files": files,
            }
        )
        seal_digest = hashlib.sha256(seal_bytes).hexdigest()
        _write(sealed, seal_bytes)
    authority.deactivate(
        _text(_read_manifest(gateway.directory)["run_id"]), anchor_prefix + seal_digest
    )
    if file_hash(sealed) != seal_digest:
        raise PipelineError("completion seal changed after authority anchoring")
    return report, outputs, files, sealed, attempt


def publish_complete(
    path: Path, result: dict[str, object], authority: Authorization, owner_ids: set[str]
) -> dict[str, object]:
    """Keep the original completion-time observation when other owners advance.

    This checks a compatible observation, not authentication of its historical
    capture time. Current authority remains the only spending authority.
    """
    if not path.exists():
        _write(path, _json(result))
        return result
    digest = file_hash(path)
    saved = _load(_read(path, digest))
    snapshot = _object(saved.get("authorization"))
    current = authority.summary()
    validate_authorization_snapshot(snapshot, current, owner_ids)
    if _json(saved) != _json(result | {"authorization": snapshot}):
        raise PipelineError("stored complete publication changes its sealed source or outputs")
    if file_hash(path) != digest:
        raise PipelineError("stored complete publication changed during consumption")
    return saved


def validate_authorization_snapshot(
    snapshot: object, current: dict[str, object], owner_ids: set[str]
) -> None:
    """Check a retained observation against decoded current state, without writes."""
    snapshot = _object(snapshot)
    if set(snapshot) != set(current):
        raise PipelineError("stored authorization observation has different fields")
    for key in ("authorization_id", "budget_microusd", "max_calls", "scope", "terms_sha256"):
        if snapshot[key] != current[key] or type(snapshot[key]) is not type(current[key]):
            raise PipelineError("stored authorization observation has different terms")
    amounts = ("committed_microusd", "spent_microusd", "reserved_microusd", "operation_count")

    def totals(record: dict[str, object]) -> None:
        if any(
            type(record.get(key)) is not int or not 0 <= cast(int, record[key]) < 2**63
            for key in amounts
        ):
            raise PipelineError("stored financial observation has invalid numeric types")
        if record["committed_microusd"] != cast(int, record["spent_microusd"]) + cast(
            int, record["reserved_microusd"]
        ):
            raise PipelineError("stored financial observation does not add up")

    totals(snapshot)
    for key in ("event_count", "available_microusd", "remaining_calls"):
        if type(snapshot[key]) is not int or not 0 <= cast(int, snapshot[key]) < 2**63:
            raise PipelineError("stored authorization observation has invalid counters")
    if any(
        cast(int, snapshot[key]) > cast(int, current[key])
        for key in ("spent_microusd", "operation_count", "event_count")
    ):
        raise PipelineError("stored authorization observation exceeds current monotonic totals")
    if snapshot["available_microusd"] != max(
        0, cast(int, snapshot["budget_microusd"]) - cast(int, snapshot["committed_microusd"])
    ) or snapshot["remaining_calls"] != max(
        0, cast(int, snapshot["max_calls"]) - cast(int, snapshot["operation_count"])
    ):
        raise PipelineError("stored authorization allowance observation does not add up")
    values = snapshot["runs"]
    if type(values) is not list:
        raise PipelineError("stored authorization population is invalid")
    actual = {_text(row["run_id"]): row for row in cast(list[dict[str, object]], current["runs"])}
    old: dict[str, dict[str, object]] = {}
    for value in values:
        row = _object(value)
        identifier = _text(row.get("run_id"))
        if identifier in old or identifier not in actual or set(row) != set(actual[identifier]):
            raise PipelineError("stored authorization population differs")
        totals(row)
        if type(row["active"]) is not bool:
            raise PipelineError("stored authorization activity is not boolean")
        for key in row.keys() - {*amounts, "active"}:
            if row[key] != actual[identifier][key] or type(row[key]) is not type(
                actual[identifier][key]
            ):
                raise PipelineError("stored authorization owner identity differs")
        if any(
            cast(int, row[key]) > cast(int, actual[identifier][key])
            for key in ("spent_microusd", "operation_count")
        ) or (not row["active"] and actual[identifier]["active"]):
            raise PipelineError("stored owner observation is not monotonic")
        if identifier in owner_ids and row != actual[identifier]:
            raise PipelineError("completed pipeline owner observation differs")
        old[identifier] = row
    if cast(int, snapshot["event_count"]) < 1 + len(old):
        raise PipelineError("stored event count cannot cover creation and its known owners")
    if not owner_ids <= old.keys() or any(
        sum(cast(int, row[key]) for row in old.values()) != snapshot[key] for key in amounts
    ):
        raise PipelineError("stored authorization observation omits or miscounts owners")
