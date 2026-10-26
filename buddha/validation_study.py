"""Consumed validation occasions over existing confined generation/native owners.

This file journal binds one original grant and finite looks. It supplies no
finalization, uncertainty estimate, promotion authority or holdout certification.
Trusted host source access is distinct from projecting a task to a candidate.
"""

import hashlib
import re
import sqlite3
from collections.abc import Callable, Iterator, Mapping, Sequence
from contextlib import ExitStack
from functools import wraps
from pathlib import Path
from typing import Any, cast

from buddha import candidate_generation, executor, native_evaluation, trial_fence
from buddha import native_pipeline as pipeline
from buddha import source_screen_results as saved_native
from buddha.answers import TaskSet, _id, _source, _utf8
from buddha.authorization import Authorization
from buddha.doctor import _authority, _Busy, _Owner, _Unsupported
from buddha.gateway import CORE, RawHTTPTransport, _input_records, _profiles, _review
from buddha.improvement_rule import ImprovementRule
from buddha.native_evidence import NativeEvidence, _adopt_capture, authority_observation
from buddha.releases import (
    MAX_SOURCE_BYTES,
    ROLES,
    Release,
    ReleaseError,
    Selection,
    _digest,
    _json,
    _load,
    _object,
    _path,
    _root,
    _text,
    file_hash,
    inventory,
    prepare_selection,
    verify_selection,
)
from buddha.wire import _integer

_FORMAT = "buddha.validation-study.v1"
_OCCASION = "buddha.validation-occasion.v1"
_RESERVATION = "buddha.validation-reservation.v1"
_RESULT = "buddha.validation-occasion-result.v1"
_OBSERVATION = "buddha.validation-occasion-observation.v1"
_CLAIM = "native validation measurements only; no uncertainty, promotion or improvement claim"
# Match the existing gateway invocation contract; this does not reduce its limit.
_INPUT_LIMIT = 1024
_CONTROL_NAMES = (
    "declaration.json",
    "context.json",
    "improvement-rule.json",
    "custody.json",
    "analysis-plan",
)
_REASONS = {
    "authority",
    "unknown",
    "protocol",
    "native_error",
    "cancelled",
    "candidate_execution_failed",
    "executor",
}


class ValidationStudyError(ReleaseError):
    """Original validation controls or retained occasion evidence are invalid."""


class ValidationStudyStopped(ValidationStudyError):
    """An execution error carrying the exact successfully saved partial record."""

    def __init__(self, partial: dict[str, object]):
        self._partial = _json(partial)
        super().__init__("validation stopped; original saved partial retained")

    @property
    def partial(self) -> dict[str, object]:
        return _load(self._partial)


class ValidationStudyInterrupted(KeyboardInterrupt):
    """Cancellation carrying the exact saved partial record."""

    def __init__(self, partial: dict[str, object]):
        self._partial = _json(partial)
        super().__init__("validation cancelled; original saved partial retained")

    @property
    def partial(self) -> dict[str, object]:
        return _load(self._partial)


def _checked[**P, T](function: Callable[P, T]) -> Callable[P, T]:
    @wraps(function)
    def checked(*args: P.args, **kwargs: P.kwargs) -> T:
        try:
            return function(*args, **kwargs)
        except (
            ValueError,
            TypeError,
            KeyError,
            OSError,
            RecursionError,
            OverflowError,
            sqlite3.Error,
            _Busy,
            _Unsupported,
        ) as error:
            if isinstance(error, ValidationStudyError):
                raise
            raise ValidationStudyError(
                "validation controls or retained evidence are invalid"
            ) from None

    return checked


def _obj(value: object, keys: set[str] | None = None) -> dict[str, Any]:
    return cast(dict[str, Any], _object(value, keys))


def _list(value: object) -> list[Any]:
    if type(value) is not list:
        raise ValidationStudyError("validation requires literal ordered lists")
    return value


def _absolute(value: object) -> Path:
    path = pipeline._absolute(value)
    if ".." in path.parts:
        raise ValidationStudyError("validation paths cannot traverse parents")
    for component in path.parts[1:]:
        _path(component)
    _root(path.parent)
    if str(path.resolve()) != str(path):
        raise ValidationStudyError("validation paths require their resolved long spelling")
    return path


def _sha(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()


def _ref(value: object, controls: dict[Path, str], *, source: bool = False) -> dict[str, Any]:
    ref = _obj(value, {"path", "sha256"})
    path, digest = _absolute(ref["path"]), _digest(ref["sha256"])
    raw = pipeline._read(path, digest)
    if not raw or (source and (len(raw) > MAX_SOURCE_BYTES or not _utf8(raw.decode("utf-8")))):
        raise ValidationStudyError("validation source or metadata file is empty or oversized")
    if path in controls and controls[path] != digest:
        raise ValidationStudyError("conflicting original input aliases")
    controls[path] = digest
    result = {"path": str(path), "sha256": digest}
    if source:
        result["agent_sha256"] = pipeline._sha({"candidate.py": digest})
    return result


def _source_refs(value: object, controls: dict[Path, str]) -> list[dict[str, Any]]:
    values = _list(value)
    if not values:
        raise ValidationStudyError("source arm lists must be nonempty")
    result = [_ref(item, controls, source=True) for item in values]
    if len({row["agent_sha256"] for row in result}) != len(result):
        raise ValidationStudyError("a role repeats the same source identity")
    return result


def _sources() -> list[Path]:
    package = Path(__file__).absolute().parent
    return list(
        dict.fromkeys(
            [
                *(
                    package / ("__init__.py" if name == "buddha" else name.split(".")[-1] + ".py")
                    for name in sorted(CORE)
                ),
                *candidate_generation._sources("buddha.candidate-generation.v2"),
                *native_evaluation._sources(),
                Path(__file__).absolute(),
                package / "improvement_rule.py",
                package / "source_screen_results.py",
                package / "native_evidence.py",
            ]
        )
    )


def _custody(
    value: object,
    tasks: TaskSet,
    selected: list[str | int],
    controls: dict[Path, str],
    *,
    phase: str = "validation",
) -> dict[str, Any]:
    if type(phase) is not str or phase not in {"validation", "final", "transfer"}:
        raise ValidationStudyError("unsupported selected custody phase")
    record = _obj(
        value,
        {"format", "process_id", "custodian", "basis", "evidence", "disclosures", "population"},
    )
    if record["format"] != "buddha.validation-custody.v1":
        raise ValidationStudyError("unsupported validation custody")
    for key in ("process_id", "custodian", "basis"):
        _text(record[key])
    evidence = _list(record["evidence"])
    if not evidence:
        raise ValidationStudyError("custody needs explicit metadata evidence")
    for item in evidence:
        _ref(item, controls)
    known = {task.id: task for task in tasks.tasks}
    members: dict[str | int, dict[str, Any]] = {}
    phases: dict[str, str] = {}
    normalized: dict[str, str] = {}
    for item in _list(record["population"]):
        row = _obj(
            item,
            {"task_id", "task_sha256", "family_id", "source", "task_type", "phase", "exposure"},
        )
        identifier = _id(row["task_id"])
        if identifier not in known or identifier in members:
            raise ValidationStudyError("custody population repeats or changes typed task IDs")
        if _digest(row["task_sha256"]) != pipeline._sha(known[identifier].to_record()):
            raise ValidationStudyError("custody content differs from the frozen task")
        for key in ("family_id", "source", "task_type"):
            _text(row[key])
        if row["phase"] not in {"development", "validation", "final", "transfer"} or (
            row["exposure"] not in {"eligible", "exposed", "unknown"}
        ):
            raise ValidationStudyError("invalid custody phase or exposure")
        if phases.setdefault(row["family_id"], row["phase"]) != row["phase"]:
            raise ValidationStudyError("a declared family crosses phases")
        signature = " ".join(known[identifier].prompt.split()).casefold()
        if normalized.setdefault(signature, row["phase"]) != row["phase"]:
            raise ValidationStudyError("normalized duplicate prompts cross phases")
        members[identifier] = row
    if set(members) != set(known):
        raise ValidationStudyError("custody omits source members")
    disclosed: set[str | int] = set()
    for item in _list(record["disclosures"]):
        row = _obj(item, {"task_id", "process_id", "recipient", "channel", "basis"})
        identifier = _id(row["task_id"])
        if identifier not in known:
            raise ValidationStudyError("disclosure names an unknown typed task")
        for key in ("process_id", "recipient", "channel", "basis"):
            _text(row[key])
        if row["process_id"] == record["process_id"]:
            disclosed.add(identifier)
    if any(
        members[key]["phase"] != phase or members[key]["exposure"] != "eligible" or key in disclosed
        for key in selected
    ):
        raise ValidationStudyError(f"selected tasks lack declared named-process {phase} custody")
    return record


def _validate_execution(
    record: dict[str, Any], tasks: TaskSet, runtime: str, *, active: bool = True
) -> None:
    """Shared fixed source/native contract; no phase or scientific-plan interpretation."""
    if type(active) is not bool:
        raise ValidationStudyError("execution validation needs an explicit activity mode")
    release = Release.from_record(tasks.to_record()["release"])
    generation = _obj(
        record["generation"],
        {
            "selection",
            "roots",
            "config",
            "entrypoint",
            "executor",
            "profile",
            "runtime",
            "max_callbacks",
            "budget_microusd",
            "max_calls",
        },
    )
    selected_source = Selection.from_bytes(_json(generation["selection"]))
    roots = {key: _absolute(value) for key, value in _obj(generation["roots"], set(ROLES)).items()}
    if (
        generation["entrypoint"] != "candidate.py"
        or set(_obj(_obj(selected_source.to_record()["components"])["agent"])) != {"candidate.py"}
        or selected_source.release_sha256 != tasks.release_sha256
    ):
        raise ValidationStudyError("generation must retain the one-file source/release interface")
    if active:
        verify_selection(selected_source, roots, expected_sha256=selected_source.fingerprint())
    candidate_generation._runtime_selection(
        generation, selected_source, roots, lambda path: pipeline._read(path, runtime), runtime
    )
    if _obj(generation["runtime"])["sha256"] != runtime:
        raise ValidationStudyError("runtime differs from independent approval")
    config = _obj(
        generation["config"], {"provider", "model", "max_output_tokens", "instructions", "sampling"}
    )
    if (
        config["provider"] not in {"openai", "anthropic"}
        or config["sampling"] not in {"regenerate", "in-context"}
        or len(_utf8(config["instructions"])) > 4000
    ):
        raise ValidationStudyError("invalid fixed generation configuration")
    _text(config["model"])
    _integer(config["max_output_tokens"], 1)
    _integer(generation["max_callbacks"], 0, 1000)
    for name in ("budget_microusd", "max_calls"):
        _integer(generation[name], 1)
    settings = _obj(
        generation["executor"],
        {
            "image_id",
            "role",
            "mounts",
            "runner_entrypoint",
            "image_environment",
            "limits",
            "docker_endpoint",
        },
    )
    if settings["mounts"] != [["/agent", str(roots["agent"])], ["/runner", str(roots["runner"])]]:
        raise ValidationStudyError("fixed source mounts differ from selected roots")
    validate_spec = executor.ContainerSpec if active else executor._validate_container_fields
    validate_spec(
        settings["image_id"],
        settings["role"],
        (("/agent", roots["agent"]), ("/runner", roots["runner"])),
        settings["runner_entrypoint"],
        tuple(tuple(pair) for pair in settings["image_environment"]),
    )
    if not active:
        _root(roots["runner"])
        file_hash(roots["runner"] / settings["runner_entrypoint"])
    executor.Limits(**_obj(settings["limits"], set(executor.Limits.__dataclass_fields__)))
    executor._local_endpoint(settings["docker_endpoint"])
    if settings["role"] != "agent" or settings["runner_entrypoint"] != "buddha/candidate_worker.py":
        raise ValidationStudyError("source executor changes the candidate boundary")
    profile = _obj(generation["profile"], {"capability", "profile_id"})
    profiles = _profiles(selected_source, roots)
    spec = _obj(_obj(_obj(profiles[profile["capability"]])["profiles"])[profile["profile_id"]])[
        "spec"
    ]
    if any(spec[name] != config[name] for name in ("provider", "model", "max_output_tokens")):
        raise ValidationStudyError("generation differs from selected host profile")
    native = _obj(record["native"])
    if Selection.from_bytes(_json(native["selection"])).release_sha256 != tasks.release_sha256:
        raise ValidationStudyError("native release differs from the source")
    pipeline.validate_native(native, record["stages"], release)


def _definition(raw: bytes, runtime: str) -> dict[str, Any]:
    record = _obj(
        _load(raw),
        {
            "format",
            "experiment_id",
            "tasks",
            "selected_ids",
            "custody",
            "improvement_rule",
            "analysis_plan",
            "comparators",
            "max_candidates",
            "max_looks",
            "repetitions",
            "comparator_policy",
            "repetition_unit",
            "bound_axes",
            "generation",
            "native",
            "stages",
        },
    )
    if (
        record["format"] != _FORMAT
        or record["comparator_policy"] != "fresh-each-occasion"
        or (record["repetition_unit"] != "complete-task-answer-set")
        or record["bound_axes"] != ["utility", "distinct"]
    ):
        raise ValidationStudyError("unsupported prospective validation declaration")
    _text(record["experiment_id"])
    for name in ("max_candidates", "max_looks", "repetitions"):
        _integer(record[name], 1, 2**63 - 1)
    controls: dict[Path, str] = {}
    refs = {
        name: _ref(record[name], controls)
        for name in ("tasks", "custody", "improvement_rule", "analysis_plan")
    }
    tasks = TaskSet.from_bytes(pipeline._read(Path(refs["tasks"]["path"])))
    release, data = _source(tasks.to_record())
    full = TaskSet.from_dataset(release, data)
    if tasks.to_bytes() != full.to_bytes():
        raise ValidationStudyError("validation needs the complete trusted-host source")
    selected = [_id(item) for item in _list(record["selected_ids"])]
    if (
        not selected
        or len(set(selected)) != len(selected)
        or not set(selected) <= {task.id for task in tasks.tasks}
    ):
        raise ValidationStudyError("validation selection repeats or changes typed task IDs")
    custody = _custody(
        _load(pipeline._read(Path(refs["custody"]["path"]))), tasks, selected, controls
    )
    rule = ImprovementRule.from_bytes(pipeline._read(Path(refs["improvement_rule"]["path"])))
    comparators = _source_refs(record["comparators"], controls)
    _validate_execution(record, tasks, runtime)
    for path in _sources():
        controls[path] = file_hash(path)
    return {
        "record": record,
        "tasks": tasks,
        "custody": custody,
        "rule": rule,
        "comparators": comparators,
        "controls": controls,
        "runtime": runtime,
    }


@_checked
def prepare_validation_study(
    directory: Path,
    *,
    declaration: Path,
    expected_sha256: str,
    expected_runtime_sha256: str,
    authorization: Authorization | None = None,
) -> Path:
    """Freeze original metadata/controls; create no financial authority or worker.

    Canonical copied declaration bytes define the study scope. The external raw
    declaration hash and original rule reference remain separately bound inputs.
    """
    directory, declaration = _absolute(str(directory)), _absolute(str(declaration))
    raw = pipeline._read(declaration, _digest(expected_sha256))
    state = _definition(raw, _digest(expected_runtime_sha256))
    originals = trial_fence._include_controls(
        directory, state["controls"] | {declaration: _digest(expected_sha256)}
    )
    if authorization is None and trial_fence.required_controls(directory):
        raise ValidationStudyError("trial validation preparation needs its explicit original grant")
    if authorization is not None and not isinstance(authorization, Authorization):
        raise ValidationStudyError("validation preparation needs an original Authorization")
    record = state["record"]
    internal = {
        "declaration.json": _json(record),
        "custody.json": _json(state["custody"]),
        "improvement-rule.json": state["rule"].to_bytes(),
        "analysis-plan": pipeline._read(Path(record["analysis_plan"]["path"])),
    }
    protected = [
        *originals,
        *(
            _absolute(value)
            for section in ("generation", "native")
            for value in record[section]["roots"].values()
        ),
    ]
    if directory.exists() or any(
        directory.is_relative_to(path) or path.is_relative_to(directory) for path in protected
    ):
        raise ValidationStudyError("new study output overlaps or replaces original evidence")
    context = {
        "format": "buddha.validation-study-context.v1",
        "declaration_sha256": _sha(internal["declaration.json"]),
        "external_declaration": {"path": str(declaration), "sha256": expected_sha256},
        "expected_runtime_sha256": state["runtime"],
        "original_controls": {str(path): digest for path, digest in originals.items()},
        "internal_controls": {name: _sha(value) for name, value in internal.items()},
    }
    _json(context)
    with ExitStack() as stack:
        if authorization is not None:
            controls = stack.enter_context(
                trial_fence.work(
                    authorization.path,
                    authorization._terms(),
                    directory=directory,
                    kind="validation",
                )
            )
            if any(originals.get(path) != pin for path, pin in controls.items()):
                raise ValidationStudyError("original trial controls changed before preparation")
            trial_fence.require_purpose(
                authorization.path,
                authorization._terms(),
                directory=directory,
                expected="validation study: " + _sha(internal["declaration.json"]),
            )
        directory.mkdir()
        for name, value in internal.items():
            pipeline._write(directory / name, value)
        pipeline._write(directory / "context.json", _json(context))
        (directory / "validation").mkdir()
    return directory


def _state(directory: Path) -> dict[str, Any]:
    _root(directory)
    context_raw = pipeline._read(directory / "context.json")
    context = _obj(
        _load(context_raw),
        {
            "format",
            "declaration_sha256",
            "external_declaration",
            "expected_runtime_sha256",
            "original_controls",
            "internal_controls",
        },
    )
    if context["format"] != "buddha.validation-study-context.v1" or _json(context) != context_raw:
        raise ValidationStudyError("invalid original study context")
    raw = pipeline._read(directory / "declaration.json", _digest(context["declaration_sha256"]))
    state = _definition(raw, _digest(context["expected_runtime_sha256"]))
    if raw != _json(state["record"]):
        raise ValidationStudyError("original declaration is not canonical")
    originals = {
        _absolute(name): _digest(pin) for name, pin in _obj(context["original_controls"]).items()
    }
    for path, pin in originals.items():
        pipeline._read(path, pin)
    external = _obj(context["external_declaration"], {"path", "sha256"})
    external_path = _absolute(external["path"])
    if originals.get(external_path) != external["sha256"] or (
        _json(_load(pipeline._read(external_path))) != raw
    ):
        raise ValidationStudyError("external declaration differs from its original copied identity")
    if any(originals.get(path) != pin for path, pin in state["controls"].items()):
        raise ValidationStudyError("an original reference or installed helper changed")
    expected = {
        "declaration.json": raw,
        "custody.json": _json(state["custody"]),
        "improvement-rule.json": state["rule"].to_bytes(),
        "analysis-plan": pipeline._read(Path(state["record"]["analysis_plan"]["path"])),
    }
    if context["internal_controls"] != {name: _sha(value) for name, value in expected.items()}:
        raise ValidationStudyError("internal controls changed their original identities")
    for name, value in expected.items():
        if pipeline._read(directory / name) != value:
            raise ValidationStudyError("an original copied control changed")
    controls = originals | {directory / name: _sha(value) for name, value in expected.items()}
    controls[directory / "context.json"] = _sha(context_raw)
    state.update(
        directory=directory, context=context, controls=controls, declaration_sha256=_sha(raw)
    )
    return state


def _reservation(occasion: dict[str, Any]) -> dict[str, object]:
    return {"format": _RESERVATION, "occasion_sha256": pipeline._sha(occasion)}


def _slots(state: dict[str, Any]) -> list[dict[str, Any]]:
    root = state["directory"] / "validation"
    _root(root)
    children = list(root.iterdir())
    names = {str(i) for i in range(len(children))}
    if {path.name for path in children} != names or len(children) > state["record"]["max_looks"]:
        raise ValidationStudyError("validation look prefix is orphaned or outside its ceiling")
    result = []
    for index in range(len(children)):
        directory = root / str(index)
        _root(directory)
        raw = pipeline._read(directory / "occasion.json")
        value = _obj(
            _load(raw),
            {
                "format",
                "ordinal",
                "declaration_sha256",
                "controls",
                "arms",
                "selected_ids",
                "repetitions",
                "counts",
                "authorization",
                "review",
                "directory",
            },
        )
        if (
            value["format"] != _OCCASION
            or type(value["ordinal"]) is not int
            or (value["ordinal"] != index or value["directory"] != str(directory))
            or raw != _json(value)
            or value["declaration_sha256"] != state["declaration_sha256"]
        ):
            raise ValidationStudyError("reserved occasion is missing, malformed or changed")
        if pipeline._read(directory / "reservation.json") != _json(_reservation(value)):
            raise ValidationStudyError("original occasion lacks its confirmed reservation")
        for name, pin in state["controls"].items():
            if _obj(value["controls"]).get(str(name)) != pin:
                raise ValidationStudyError("occasion changes its original study controls")
        for name, pin in _obj(value["controls"]).items():
            pipeline._read(_absolute(name), _digest(pin))
        _review(_obj(value["review"]))
        for identifier in _list(value["selected_ids"]):
            _id(identifier)
        if value["selected_ids"] != state["record"]["selected_ids"] or (
            value["repetitions"] != state["record"]["repetitions"]
        ):
            raise ValidationStudyError("occasion changes its complete measurement schedule")
        arms = _list(value["arms"])
        comparator_count = len(state["comparators"])
        if not comparator_count < len(arms) <= comparator_count + state["record"]["max_candidates"]:
            raise ValidationStudyError("occasion arm population differs")
        for arm_index, arm in enumerate(arms):
            row = _obj(arm, {"arm_index", "role", "role_index", "path", "sha256", "agent_sha256"})
            comparator = arm_index < comparator_count
            if (
                type(row["arm_index"]) is not int
                or row["arm_index"] != arm_index
                or (row["role"] != ("comparator" if comparator else "candidate"))
                or row["role_index"] != (arm_index if comparator else arm_index - comparator_count)
            ):
                raise ValidationStudyError("occasion role identity differs")
            _absolute(row["path"])
            if row["agent_sha256"] != pipeline._sha({"candidate.py": _digest(row["sha256"])}):
                raise ValidationStudyError("occasion source identity differs")
            if comparator and any(
                row[key] != state["comparators"][arm_index][key]
                for key in ("path", "sha256", "agent_sha256")
            ):
                raise ValidationStudyError("occasion changed a fixed comparator")
        for role in ("comparator", "candidate"):
            identities = [arm["agent_sha256"] for arm in arms if arm["role"] == role]
            if len(set(identities)) != len(identities):
                raise ValidationStudyError("occasion repeats a source within a role")
        counts = {
            "cells": len(arms) * len(value["selected_ids"]) * value["repetitions"],
            "contrasts": (len(arms) - comparator_count) * comparator_count,
            "max_contrasts": state["record"]["max_looks"]
            * state["record"]["max_candidates"]
            * comparator_count,
            "max_axis_bounds": 2
            * state["record"]["max_looks"]
            * state["record"]["max_candidates"]
            * comparator_count,
        }
        if value["counts"] != counts or any(
            type(number) is not int for number in _obj(value["counts"]).values()
        ):
            raise ValidationStudyError("occasion changes its prospective coverage counts")
        result.append(value)
    return result


def _location(
    state: dict[str, Any], occasion: dict[str, Any], arm: int, task: int, repetition: int
) -> Path:
    return (
        Path(occasion["directory"])
        / "arms"
        / str(arm)
        / ("tasks")
        / str(task)
        / "repetitions"
        / str(repetition)
    )


def _cells(
    state: dict[str, Any], occasion: dict[str, Any]
) -> Iterator[tuple[dict[str, Any], int, str | int, int, Path]]:
    for arm in occasion["arms"]:
        for task_index, identifier in enumerate(occasion["selected_ids"]):
            for repetition in range(occasion["repetitions"]):
                yield (
                    arm,
                    task_index,
                    identifier,
                    repetition,
                    _location(state, occasion, arm["arm_index"], task_index, repetition),
                )


def _grant(current: dict[str, Any], authorization: Path) -> dict[str, object]:
    return {
        "path": str(authorization),
        **{
            name: current[name]
            for name in (
                "authorization_id",
                "terms_sha256",
                "scope",
                "budget_microusd",
                "max_calls",
            )
        },
    }


def _owner_identity(
    reader: NativeEvidence,
    owner: _Owner,
    occasion: dict[str, Any],
    selected: Selection,
    roots: dict[str, Path],
    settings: dict[str, object],
) -> None:
    manifest = owner.manifest
    if (
        manifest["authorization_path"] != str(reader.authorization)
        or manifest["selection"] != selected.to_record()
        or manifest["roots"] != {key: str(path) for key, path in roots.items()}
        or manifest["settings"] != settings
        or manifest["review"] != occasion["review"]
        or manifest["profiles"] != _profiles(selected, roots)
    ):
        raise ValidationStudyError("original owner differs from its reserved execution contract")


def _generation_identity(
    state: dict[str, Any],
    occasion: dict[str, Any],
    reader: NativeEvidence,
    arm: dict[str, Any],
    identifier: str | int,
    location: Path,
) -> TaskSet:
    root = location / "generation"
    owner = reader.owner(root / "owners/0")
    generation, roots, selected = _arm_generation(state, occasion, arm)
    _owner_identity(
        reader,
        owner,
        occasion,
        selected,
        roots,
        {name: generation[name] for name in ("budget_microusd", "max_calls")},
    )
    task = state["tasks"].select([identifier])
    if (
        reader.bound(owner, location / "task.json") != task.to_bytes()
        or reader.bound(owner, location / "generation.json") != _json(_recipe(generation, location))
        or reader.bound(owner, root / "context.json")
        != _json(
            {
                "format": "buddha.candidate-generation-context.v2",
                "descriptor": str(location / "generation.json"),
                "expected_runtime_sha256": state["runtime"],
            }
        )
    ):
        raise ValidationStudyError("original generation differs from its reserved arm/task")
    return cast(TaskSet, task)


def _generation(
    state: dict[str, Any],
    occasion: dict[str, Any],
    reader: NativeEvidence,
    arm: dict[str, Any],
    identifier: str | int,
    location: Path,
) -> tuple[dict[str, object], native_evaluation._Generation | None]:
    task = _generation_identity(state, occasion, reader, arm, identifier, location)
    root = location / "generation"
    raw = reader.raw(root / "report.json")
    report, source, captured = native_evaluation._read_published_generation(
        root, authorization=reader.authorization, expected_report_sha256=_sha(raw)
    )
    _adopt_capture(captured, reader.capture)
    if _json(report) != raw:
        raise ValidationStudyError("generation publication changed during consumption")
    if report["disposition"] == "candidate_execution_failed":
        return report, None
    if report["disposition"] != "generated" or source is None:
        raise ValidationStudyError("unsupported original source execution outcome")
    if (
        source.tasks.to_bytes() != task.to_bytes()
        or source.answers.to_record()["agent_sha256"] != arm["agent_sha256"]
    ):
        raise ValidationStudyError("anchored C1 differs from its reserved source/task")
    reader.verify_files(source.files)
    return report, source


def _native_identity(
    state: dict[str, Any],
    occasion: dict[str, Any],
    reader: NativeEvidence,
    location: Path,
    report: dict[str, object],
    source: native_evaluation._Generation,
) -> None:
    root = location / "evaluation"
    native = _obj(state["record"]["native"])
    selected = Selection.from_bytes(_json(native["selection"]))
    roots = {key: Path(value) for key, value in _obj(native["roots"]).items()}
    stages = _list(state["record"]["stages"])
    present = [i for i in range(1, len(stages) + 1) if root / "owners" / str(i) in reader.owners]
    descriptor = {
        "format": "buddha.native-evaluation.v1",
        "source_generation": report["source_generation"],
        "native": native,
        "stages": stages,
    }
    if reader.raw(root / "native-answers.jsonl") != source.answers.native_bytes():
        raise ValidationStudyError("native input changes the original literal C1")
    artifacts = _obj(reader.release.to_record()["artifacts"])
    available = {_path(artifacts["answers"]): root / "native-answers.jsonl"}
    for index in present:
        owner = reader.owner(root / "owners" / str(index))
        _owner_identity(
            reader,
            owner,
            occasion,
            selected,
            roots,
            {
                name: 1 if index == len(stages) else native[name]
                for name in ("budget_microusd", "max_calls")
            },
        )
        if reader.bound(owner, location / "evaluation.json") != _json(descriptor) or reader.bound(
            owner, root / "context.json"
        ) != _json(
            {
                "format": "buddha.native-evaluation-context.v1",
                "descriptor": str(location / "evaluation.json"),
            }
        ):
            raise ValidationStudyError("native owner changes its original reserved definition")
        reader.native_configuration(root, index, source.answers_path, available)
        seal = root / "completed" / (str(index) + ".json")
        if seal.relative_to(reader.root).as_posix() not in reader.capture.entries:
            if index != present[-1]:
                raise ValidationStudyError("native successor lacks its anchored predecessor")
            continue
        stage_report, attempt = reader.stage(root, index, baseline=False)
        reader.native(root, index, stage_report, source.answers_path, available)
        for output in _list(_obj(stages[index - 1])["outputs"]):
            output = _obj(output)
            name = _path(output["path"])
            path = attempt / "artifacts" / name
            if output["id_field"] is not None:
                pipeline._coverage(
                    path,
                    _text(output["id_field"]),
                    source.tasks,
                    _obj(stage_report["artifacts"])[name],
                )
            available[name] = path


def _census(
    state: dict[str, Any], slots: list[dict[str, Any]], authorization: Path
) -> tuple[NativeEvidence, dict[str, Any]]:
    reader = NativeEvidence(state["directory"], authorization, error_type=ValidationStudyError)
    stages = len(state["record"]["stages"])
    owners = []
    scheduled: set[tuple[int, int, int, int]] = set()
    positions: dict[int, set[int]] = {}
    pattern = re.compile(
        r"validation/(0|[1-9][0-9]*)/arms/(0|[1-9][0-9]*)/tasks/"
        r"(0|[1-9][0-9]*)/repetitions/(0|[1-9][0-9]*)/(generation|evaluation)/owners/"
        r"(0|[1-9][0-9]*)"
    )
    for name in reader.capture.entries:
        child_match = re.fullmatch(
            r"validation/(0|[1-9][0-9]*)/arms/(0|[1-9][0-9]*)/tasks/"
            r"(0|[1-9][0-9]*)/repetitions/(0|[1-9][0-9]*)/(generation|evaluation)",
            name,
        )
        if child_match is not None:
            first = "0" if child_match.group(5) == "generation" else "1"
            if name + "/owners/" + first + "/manifest.json" not in reader.capture.entries:
                raise ValidationStudyError("nested preparation has no original owner")
        if "/owners/" not in name:
            continue
        prefix = (
            name.split("/owners/", 1)[0] + "/owners/" + name.split("/owners/", 1)[1].split("/")[0]
        )
        match = pattern.fullmatch(prefix)
        if match is None:
            raise ValidationStudyError("foreign or orphan validation owner path")
        look, arm, task, repetition, role, stage = match.groups()
        look_index, arm_index, task_index, repeat_index, stage_index = map(
            int, (look, arm, task, repetition, stage)
        )
        if look_index >= len(slots):
            raise ValidationStudyError("owner precedes its original reserved look")
        occasion = slots[look_index]
        if (
            arm_index >= len(occasion["arms"])
            or task_index >= len(occasion["selected_ids"])
            or (repeat_index >= occasion["repetitions"])
            or (role == "generation" and stage_index != 0)
            or (role == "evaluation" and not 1 <= stage_index <= stages)
        ):
            raise ValidationStudyError("owner is outside the declared validation schedule")
        manifest_name = prefix + "/manifest.json"
        if manifest_name not in reader.capture.entries:
            raise ValidationStudyError("nested preparation lost its original owner manifest")
        if name != manifest_name:
            continue
        owner = reader.owner(reader.root / prefix)
        owners.append(owner)
        scheduled.add((look_index, arm_index, task_index, repeat_index))
        position = (
            (arm_index * len(occasion["selected_ids"]) + task_index) * occasion["repetitions"]
            + repeat_index
        ) * (stages + 1) + stage_index
        positions.setdefault(look_index, set()).add(position)
        expected_controls = _obj(occasion["controls"]) | {
            str(reader.root / "validation" / look / "occasion.json"): pipeline._sha(occasion),
            str(reader.root / "validation" / look / "reservation.json"): pipeline._sha(
                _reservation(occasion)
            ),
        }
        bindings = reader._bindings(owner)
        if any(bindings.get(path) != pin for path, pin in expected_controls.items()):
            raise ValidationStudyError("original owner omitted or changed occasion controls")
    for values in positions.values():
        if values != set(range(len(values))):
            raise ValidationStudyError("validation owners skip their original serial schedule")
    funded = _authority(reader.capture, authorization, owners)
    if funded is None:
        raise ValidationStudyError("validation lacks original financial authority")
    reader.funded = funded
    current = cast(dict[str, Any], authority_observation(reader.capture, authorization, funded))
    trial_fence.require_purpose(
        authorization,
        _obj(funded["config"]),
        directory=state["directory"],
        expected="validation study: " + state["declaration_sha256"],
    )
    for row in reader._rows(funded["auth_runs"]):
        path = _absolute(row["directory"])
        if not any(path == owner.directory and row["run_id"] == owner.run_id for owner in owners):
            raise ValidationStudyError("funded validation owner is missing or replaced")
        owner = reader.owner(path)
        if (
            type(row["historical"]) is not int
            or row["historical"] != 0
            or row["runtime_sha256"] != owner.manifest["execution_sha256"]
        ):
            raise ValidationStudyError("validation requires its original nonimported owner")
    reader.release = Release.from_record(state["tasks"].to_record()["release"])
    reader.template = {key: state["record"][key] for key in ("native", "stages")}
    inactive = {row["run_id"] for row in reader._rows(funded["auth_deactivations"])}
    if owners:
        anchor = reader.owner(min(owner.directory for owner in owners)).manifest
        for owner in owners:
            seal = owner.directory.parent.parent / "completed" / (owner.directory.name + ".json")
            if (
                owner.manifest["core"] != anchor["core"]
                or owner.manifest["runtime"] != anchor["runtime"]
                or (
                    owner.run_id in inactive
                    and seal.relative_to(reader.root).as_posix() not in reader.capture.entries
                )
            ):
                raise ValidationStudyError("owner changes original runtime or unfinished activity")
    for look_index, arm_index, task_index, repetition in sorted(scheduled):
        occasion = slots[look_index]
        arm = occasion["arms"][arm_index]
        identifier = occasion["selected_ids"][task_index]
        location = _location(state, occasion, arm_index, task_index, repetition)
        _generation_identity(state, occasion, reader, arm, identifier, location)
        published = location / "generation/report.json"
        native = location / "evaluation/owners/1"
        if published.relative_to(reader.root).as_posix() in reader.capture.entries:
            report, source = _generation(state, occasion, reader, arm, identifier, location)
            if native in reader.owners:
                if source is None:
                    raise ValidationStudyError("native owner has no generated original C1")
                _native_identity(state, occasion, reader, location, report, source)
        elif native in reader.owners:
            raise ValidationStudyError("native owner precedes its original source publication")
        else:
            seal = location / "generation/completed/0.json"
            if seal.relative_to(reader.root).as_posix() in reader.capture.entries:
                owner = reader.owner(location / "generation/owners/0")
                evidence = candidate_generation._read_evidence(
                    {
                        "format": "buddha.candidate-generation-source.v2",
                        "generation_directory": str(location / "generation"),
                        "stage_seal_sha256": _sha(reader.raw(seal)),
                        "owner_manifest_sha256": owner.manifest_sha256,
                        "owner_ledger_sha256": owner.ledger_sha256,
                    },
                    reader.authorization,
                )
                for path, pin in cast(dict[Path, str], evidence["files"]).items():
                    reader.raw(path, pin)
        if any(
            key[0] == look_index and key > (look_index, arm_index, task_index, repetition)
            for key in scheduled
        ):
            native_report = location / "evaluation/report.json"
            if native_report.relative_to(reader.root).as_posix() not in reader.capture.entries:
                raise ValidationStudyError("later cell precedes its complete original predecessor")
    for occasion in slots:
        if occasion["authorization"] != _grant(current, authorization):
            raise ValidationStudyError("v1 study cannot replace its original grant")
        for observation in _observations(state, occasion, reader, current):
            pipeline.validate_authorization_snapshot(observation["authorization"], current, set())
    return reader, current


def _observation_child(
    state: dict[str, Any],
    occasion: dict[str, Any],
    reader: NativeEvidence,
    value: dict[str, Any],
    location: Path,
    current: dict[str, Any],
) -> None:
    reason, child, position = value["reason"], value["child"], value["position"]
    if child is None:
        if reason not in {"protocol", "cancelled"}:
            raise ValidationStudyError("partial lacks its required original child evidence")
        return
    reference = _obj(child, {"path", "sha256"})
    path = _absolute(reference["path"])
    raw = reader.raw(path, reference["sha256"])
    stage = position["stage"]
    root = location / ("generation" if stage == "generation" else "evaluation")
    saved = _obj(_load(raw))
    if raw != _json(saved):
        raise ValidationStudyError("lower partial child is not canonical")
    if path == root / "report.json":
        arm = occasion["arms"][position["arm_index"]]
        identifier = occasion["selected_ids"][position["task_index"]]
        report, source = _generation(state, occasion, reader, arm, identifier, location)
        if stage == "generation":
            if raw != _json(report) or (
                reason == "candidate_execution_failed"
                and report["disposition"] != "candidate_execution_failed"
            ):
                raise ValidationStudyError("partial changes its original source outcome")
        else:
            if source is None:
                raise ValidationStudyError("native partial has no generated original source")
            saved_native._native(
                reader,
                state["record"],
                source,
                _obj(report["source_generation"]),
                location,
                current,
            )
        if reason != "candidate_execution_failed" and reason not in {"protocol", "cancelled"}:
            raise ValidationStudyError("completed child contradicts its partial reason")
        return
    if (
        path.parent != root / "observations"
        or re.fullmatch(r"(?:0|[1-9][0-9]*)\.json", path.name) is None
        or saved.get("status") != "incomplete"
        or saved.get("reason") != reason
        or saved.get("observation") != path.relative_to(root).as_posix()
    ):
        raise ValidationStudyError("partial child changes its original stage, path or reason")
    if stage == "generation":
        saved = _obj(
            saved,
            {
                "format",
                "status",
                "reason",
                "owner",
                "attempt",
                "generation",
                "authorization",
                "observation",
                "disposition",
                "outcome",
            },
        )
        if saved["format"] != "buddha.candidate-generation-observation.v2" or (
            saved["disposition"] is not None
        ):
            raise ValidationStudyError("partial child changes its source observation schema")
        owner = reader.owner(root / "owners/0")
        if saved["owner"] != str(owner.directory):
            raise ValidationStudyError("source partial changes its original owner")
        attempt = None if saved["attempt"] is None else _absolute(saved["attempt"])
        if attempt is not None and (
            attempt.parent != root / "attempts"
            or re.fullmatch(r"0-(?:0|[1-9][0-9]*)", attempt.name) is None
        ):
            raise ValidationStudyError("source partial changes its original attempt")
    else:
        saved = _obj(
            saved,
            {
                "format",
                "status",
                "reason",
                "stopped_stage",
                "attempt",
                "owner",
                "stages",
                "authorization",
                "observation",
                "claim",
            },
        )
        index = _integer(saved["stopped_stage"], 1, len(state["record"]["stages"]))
        if (
            saved["format"] != "buddha.native-evaluation-report.v1"
            or saved["owner"] != "owners/" + str(index)
            or saved["claim"]
            != (
                "incomplete native occasion; original owners, raw replies, "
                "partial artifacts and holds retained"
            )
        ):
            raise ValidationStudyError("native partial changes its original owner/schema")
        owner = reader.owner(root / "owners" / str(index))
        reports = _list(saved["stages"])
        if len(reports) not in (index - 1, index):
            raise ValidationStudyError("native partial changes its completed stage prefix")
        for ordinal, recorded in enumerate(reports[: index - 1], 1):
            report, _ = reader.stage(root, ordinal, baseline=False)
            if _json(recorded) != _json(report):
                raise ValidationStudyError("native partial changes its original completed stage")
        relative = None if saved["attempt"] is None else _path(saved["attempt"])
        if (
            relative is not None
            and re.fullmatch(rf"attempts/{index}-(?:0|[1-9][0-9]*)", relative) is None
        ):
            raise ValidationStudyError("native partial changes its original attempt")
        attempt = None if relative is None else root / relative
        if len(reports) == index:
            if attempt is None:
                raise ValidationStudyError("unsealed native report lacks its original attempt")
            unsealed = _obj(reports[-1])
            command = reader.bound(owner, root / ("command-" + str(index) + ".json"))
            if (
                reader.raw(attempt / "report.json") != _json(unsealed) + b"\n"
                or unsealed.get("format") != "buddha.native-command-report.v1"
                or unsealed.get("status") not in {"stopped", "failed"}
                or unsealed.get("gateway_manifest_sha256") != owner.manifest_sha256
                or unsealed.get("descriptor_sha256") != _sha(command)
                or unsealed.get("command_sha256")
                != _obj(_obj(_load(command)["worker"])["command"])["sha256"]
            ):
                raise ValidationStudyError("unsealed native report changes its original attempt")
    if attempt is not None and attempt.relative_to(reader.root).as_posix() not in (
        reader.capture.entries
    ):
        raise ValidationStudyError("partial's original attempt is missing")
    child_snapshot = _obj(saved["authorization"])
    snapshot = _obj(value["authorization"])
    pipeline.validate_authorization_snapshot(child_snapshot, snapshot, set())
    for observed in (child_snapshot, snapshot):
        if owner.run_id not in {row["run_id"] for row in reader._rows(observed["runs"])}:
            raise ValidationStudyError("partial financial snapshot omits its original child owner")


def _observations(
    state: dict[str, Any],
    occasion: dict[str, Any],
    reader: NativeEvidence,
    current: dict[str, Any],
) -> list[dict[str, Any]]:
    directory = state["directory"] / "validation" / str(occasion["ordinal"])
    prefix = (directory / "observations").relative_to(reader.root).as_posix() + "/"
    names = [name for name in reader.capture.entries if name.startswith(prefix)]
    if set(names) != {prefix + str(i) + ".json" for i in range(len(names))}:
        raise ValidationStudyError("retained observations have a noncontiguous or foreign prefix")
    if not names:
        return []
    actual_cells, actual_generated, actual_failed = _collect(state, occasion, reader, current)
    result: list[dict[str, Any]] = []
    for index in range(len(names)):
        path = directory / "observations" / (str(index) + ".json")
        raw = reader.raw(path)
        value = _obj(
            _load(raw),
            {
                "format",
                "status",
                "reason",
                "ordinal",
                "occasion_sha256",
                "position",
                "child",
                "coverage",
                "authorization",
                "observation",
                "claim",
            },
        )
        if (
            raw != _json(value)
            or value["format"] != _OBSERVATION
            or (
                value["status"] != "incomplete"
                or value["reason"] not in _REASONS
                or type(value["ordinal"]) is not int
                or value["ordinal"] != occasion["ordinal"]
                or value["occasion_sha256"] != pipeline._sha(occasion)
                or value["observation"] != str(path.relative_to(directory).as_posix())
                or value["claim"]
                != ("incomplete validation; original evidence, look and liabilities retained")
            )
        ):
            raise ValidationStudyError("retained partial observation changed its original identity")
        position = _obj(value["position"], {"arm_index", "task_index", "repetition", "stage"})
        _integer(position["arm_index"], 0, len(occasion["arms"]) - 1)
        _integer(position["task_index"], 0, len(occasion["selected_ids"]) - 1)
        _integer(position["repetition"], 0, occasion["repetitions"] - 1)
        if position["stage"] not in {"generation", "native"}:
            raise ValidationStudyError("partial observation changes its stage")
        coverage = _obj(
            value["coverage"],
            {
                "expected_cells",
                "generated_cells",
                "native_cells",
                "checked_failed_generations",
                "unattempted_generations",
            },
        )
        for number in coverage.values():
            _integer(number, 0, occasion["counts"]["cells"])
        if (
            coverage["expected_cells"] != occasion["counts"]["cells"]
            or not (
                coverage["native_cells"]
                <= coverage["generated_cells"]
                <= coverage["expected_cells"]
            )
            or coverage["checked_failed_generations"] > 1
            or (
                coverage["generated_cells"]
                + coverage["checked_failed_generations"]
                + coverage["unattempted_generations"]
                != coverage["expected_cells"]
            )
        ):
            raise ValidationStudyError("partial observation coverage is contradictory")
        cell_index = (
            position["arm_index"] * len(occasion["selected_ids"]) + position["task_index"]
        ) * occasion["repetitions"] + position["repetition"]
        native_count = coverage["native_cells"]
        generated_count = coverage["generated_cells"]
        failed_count = coverage["checked_failed_generations"]
        if (
            native_count > len(actual_cells)
            or generated_count > actual_generated
            or (position["stage"] == "generation" and native_count != cell_index)
            or (
                position["stage"] == "native"
                and (
                    generated_count != cell_index + 1
                    or native_count not in (cell_index, cell_index + 1)
                )
            )
            or not cell_index <= generated_count <= cell_index + 1
        ):
            raise ValidationStudyError("partial coverage lacks its original serial frontier")
        arm = occasion["arms"][position["arm_index"]]
        identifier = occasion["selected_ids"][position["task_index"]]
        expected_identity = _identity(
            arm, position["task_index"], identifier, position["repetition"]
        )
        if failed_count and (
            actual_failed is None
            or any(actual_failed[key] != value for key, value in expected_identity.items())
            or position["stage"] != "generation"
            or native_count != cell_index
            or generated_count != cell_index
        ):
            raise ValidationStudyError("partial lacks its recorded checked source failure")
        if value["reason"] == "candidate_execution_failed" and failed_count != 1:
            raise ValidationStudyError("terminal partial lacks an anchored checked failure")
        required: set[str] = set()
        for ordinal, (_, _, _, _, cell) in enumerate(_cells(state, occasion)):
            if ordinal >= max(generated_count, native_count):
                break
            if ordinal < generated_count:
                required.add(reader.owner(cell / "generation/owners/0").run_id)
            if ordinal < native_count:
                required.update(
                    reader.owner(cell / "evaluation/owners" / str(stage)).run_id
                    for stage in range(1, len(state["record"]["stages"]) + 1)
                )
        location = _location(
            state, occasion, position["arm_index"], position["task_index"], position["repetition"]
        )
        if failed_count:
            required.add(reader.owner(location / "generation/owners/0").run_id)
        pipeline.validate_authorization_snapshot(value["authorization"], current, required)
        if result:
            previous = result[-1]
            pipeline.validate_authorization_snapshot(
                previous["authorization"], value["authorization"], set()
            )
            if any(
                previous["coverage"][key] > coverage[key]
                for key in ("generated_cells", "native_cells", "checked_failed_generations")
            ):
                raise ValidationStudyError("partial history reverses its original coverage")
        _observation_child(state, occasion, reader, value, location, current)
        result.append(value)
    return result


def _arm_generation(
    state: dict[str, Any], occasion: dict[str, Any], arm: dict[str, Any]
) -> tuple[dict[str, Any], dict[str, Path], Selection]:
    generation = _obj(_load(_json(state["record"]["generation"])))
    agent = Path(occasion["directory"]) / "arms" / str(arm["arm_index"]) / "agent"
    roots = {key: Path(value) for key, value in generation["roots"].items()}
    roots["agent"] = agent
    selected_record = _obj(generation["selection"])
    _obj(selected_record["components"])["agent"] = {"candidate.py": arm["sha256"]}
    selected = Selection.from_bytes(_json(selected_record))
    generation["selection"] = selected.to_record()
    generation["roots"] = {key: str(path) for key, path in roots.items()}
    generation["executor"]["mounts"] = [["/agent", str(agent)], ["/runner", str(roots["runner"])]]
    return generation, roots, selected


def _recipe(generation: dict[str, Any], location: Path) -> dict[str, object]:
    return {
        "format": "buddha.candidate-generation.v2",
        "tasks": str(location / "task.json"),
        **{
            name: generation[name]
            for name in ("config", "entrypoint", "executor", "profile", "runtime", "max_callbacks")
        },
    }


def _identity(
    arm: dict[str, Any], task_index: int, identifier: str | int, repetition: int
) -> dict[str, object]:
    return {
        "arm_index": arm["arm_index"],
        "role": arm["role"],
        "role_index": arm["role_index"],
        "source_sha256": arm["sha256"],
        "agent_sha256": arm["agent_sha256"],
        "task_index": task_index,
        "task_id": identifier,
        "repetition": repetition,
    }


def _collect(
    state: dict[str, Any], occasion: dict[str, Any], reader: NativeEvidence, current: dict[str, Any]
) -> tuple[list[dict[str, object]], int, dict[str, object] | None]:
    cells: list[dict[str, object]] = []
    generated = 0
    for arm, task_index, identifier, repetition, location in _cells(state, occasion):
        root = location / "generation"
        report_path = root / "report.json"
        if report_path.relative_to(reader.root).as_posix() not in reader.capture.entries:
            break
        raw = reader.raw(report_path)
        report, source = _generation(state, occasion, reader, arm, identifier, location)
        identity = _identity(arm, task_index, identifier, repetition)
        generation_ref: dict[str, object] = {
            "directory": str(root),
            "report_sha256": _sha(raw),
            "source_generation": report["source_generation"],
        }
        if source is None:
            return cells, generated, identity | {"generation": generation_ref}
        generated += 1
        native_path = location / "evaluation/report.json"
        if native_path.relative_to(reader.root).as_posix() not in reader.capture.entries:
            break
        _, _, digest = saved_native._native(
            reader, state["record"], source, _obj(report["source_generation"]), location, current
        )
        cells.append(
            identity
            | {
                "generation": generation_ref,
                "native": {"directory": str(location / "evaluation"), "report_sha256": digest},
            }
        )
    return cells, generated, None


def _coverage(
    occasion: dict[str, Any], cells: list[dict[str, object]], generated: int, failed: bool = False
) -> dict[str, object]:
    return {
        "expected_cells": occasion["counts"]["cells"],
        "generated_cells": generated,
        "native_cells": len(cells),
        "checked_failed_generations": int(failed),
        "unattempted_generations": occasion["counts"]["cells"] - generated - int(failed),
    }


def _complete(
    state: dict[str, Any], occasion: dict[str, Any], reader: NativeEvidence, current: dict[str, Any]
) -> dict[str, object]:
    cells, generated, failed = _collect(state, occasion, reader, current)
    if failed is not None or len(cells) != occasion["counts"]["cells"] or generated != len(cells):
        raise ValidationStudyError("validation result lacks exact complete native cell coverage")
    return {
        "format": _RESULT,
        "status": "complete",
        "ordinal": occasion["ordinal"],
        "occasion_sha256": pipeline._sha(occasion),
        "cells": cells,
        "coverage": _coverage(occasion, cells, generated),
        "authorization": current,
        "claim": _CLAIM,
    }


def _saved_results(
    state: dict[str, Any],
    slots: list[dict[str, Any]],
    reader: NativeEvidence,
    current: dict[str, Any],
) -> dict[int, dict[str, object]]:
    results = {}
    for occasion in slots:
        path = state["directory"] / "validation" / str(occasion["ordinal"]) / "result.json"
        if path.relative_to(reader.root).as_posix() not in reader.capture.entries:
            # Still inspect every retained completed child before earlier new calls.
            _collect(state, occasion, reader, current)
            continue
        expected = _complete(state, occasion, reader, current)
        raw = reader.raw(path)
        saved = _obj(_load(raw))
        owners = {
            owner.run_id
            for owner in reader.owners.values()
            if owner.directory.is_relative_to(path.parent)
        }
        snapshot = _obj(saved["authorization"])
        pipeline.validate_authorization_snapshot(snapshot, current, owners)
        if raw != _json(saved) or raw != _json(expected | {"authorization": snapshot}):
            raise ValidationStudyError("saved validation completion contradicts original evidence")
        results[occasion["ordinal"]] = saved
    return results


def _occasion(
    state: dict[str, Any],
    ordinal: int,
    candidates: list[dict[str, Any]],
    controls: dict[Path, str],
    current: dict[str, Any],
    authorization: Path,
    review: dict[str, object],
) -> dict[str, Any]:
    record = state["record"]
    arms: list[dict[str, Any]] = []
    for role, refs in (("comparator", state["comparators"]), ("candidate", candidates)):
        for index, ref in enumerate(refs):
            arms.append({"arm_index": len(arms), "role": role, "role_index": index, **ref})
    counts = {
        "cells": len(arms) * len(record["selected_ids"]) * record["repetitions"],
        "contrasts": len(candidates) * len(state["comparators"]),
        "max_contrasts": record["max_looks"] * record["max_candidates"] * len(state["comparators"]),
        "max_axis_bounds": 2
        * record["max_looks"]
        * record["max_candidates"]
        * len(state["comparators"]),
    }
    for value in counts.values():
        _integer(value, 1, 2**63 - 1)
    value = {
        "format": _OCCASION,
        "ordinal": ordinal,
        "declaration_sha256": state["declaration_sha256"],
        "controls": {str(path): pin for path, pin in controls.items()},
        "arms": arms,
        "selected_ids": record["selected_ids"],
        "repetitions": record["repetitions"],
        "counts": counts,
        "authorization": _grant(current, authorization),
        "review": review,
        "directory": str(state["directory"] / "validation" / str(ordinal)),
    }
    _json(value)
    return value


def _capacity(
    state: dict[str, Any],
    occasion: dict[str, Any],
    *,
    receipts: Mapping[Path, str] | None = None,
) -> None:
    """Project current v2/native input sets without reading future files.

    Each cell has the same disjoint layout. Actual attempt ordinals change path
    spelling, not cardinality. The strict generated-v2 evidence closure has the
    eleven paths below; a producer-interface change requires revisiting it.
    Actual preparation still checks all file identities and byte/resource caps.
    """
    location = _location(state, occasion, 0, 0, 0)
    generation = location / "generation"
    generated = generation / "attempts/0-0"
    evaluation = location / "evaluation"
    runtime = Path(state["record"]["generation"]["runtime"]["path"])
    reservation_paths = (
        set(receipts)
        if receipts is not None
        else {
            Path(occasion["directory"]) / "occasion.json",
            Path(occasion["directory"]) / "reservation.json",
        }
    )
    common = (
        {Path(path) for path in occasion["controls"]}
        | reservation_paths
        | {
            location / "task.json",
            location / "generation.json",
        }
    )
    source = {
        generation / "owners/0/manifest.json",
        generation / "owners/0/operations.sqlite3",
        generation / "completed/0.json",
        generated / "report.json",
        generated / "session/report.json",
        generated / "session/done.json",
        generated / "session/answers.json",
        generation / "context.json",
        location / "generation.json",
        location / "task.json",
        runtime,
    }
    maximum = len(
        common
        | {generation / "context.json", runtime}
        | set(candidate_generation._sources("buddha.candidate-generation.v2"))
    )
    release = Release.from_record(state["tasks"].to_record()["release"])
    artifacts = _obj(release.to_record()["artifacts"])
    available = {_path(artifacts["answers"]): evaluation / "native-answers.jsonl"}
    seals: set[Path] = set()
    first: set[Path] = set()
    for index, stage in enumerate(_list(state["record"]["stages"]), 1):
        stage = _obj(stage)
        paths = (
            common
            | {location / "evaluation.json", evaluation / "context.json"}
            | source
            | {evaluation / ("command-" + str(index) + ".json")}
            | set(available.values())
            | seals
            | {
                evaluation / "staging" / str(index) / (str(ordinal) + ".bin")
                for ordinal in range(len(stage["inputs"]))
            }
            | set(native_evaluation._sources())
        )
        if index == 1:
            first = paths
        else:
            paths |= first | {evaluation / "owners/1/manifest.json"}
        maximum = max(maximum, len(paths))
        attempt = evaluation / "attempts" / (str(index) + "-0")
        for output in _list(stage["outputs"]):
            name = _path(_obj(output)["path"])
            available[name] = attempt / "artifacts" / name
        seals.add(evaluation / "completed" / (str(index) + ".json"))
    if maximum > _INPUT_LIMIT:
        raise ValidationStudyError("fixed validation owner inputs exceed the gateway path limit")


def _mkdir(path: Path) -> None:
    if not path.exists():
        path.mkdir()
    _root(path)


def _materialize(
    state: dict[str, Any],
    occasion: dict[str, Any],
    arm: dict[str, Any],
    identifier: str | int,
    location: Path,
    *,
    receipts: Mapping[Path, str] | None = None,
) -> tuple[dict[str, Any], Selection, dict[Path, str]]:
    generation, roots, expected = _arm_generation(state, occasion, arm)
    arm_root = roots["agent"].parent
    _mkdir(arm_root.parent)
    _mkdir(arm_root)
    _mkdir(roots["agent"])
    pipeline._same_or_write(
        roots["agent"] / "candidate.py", pipeline._read(Path(arm["path"]), arm["sha256"])
    )
    if inventory(roots["agent"]) != {"candidate.py": arm["sha256"]}:
        raise ValidationStudyError("copied arm has foreign source files")
    selected = prepare_selection(
        Release.from_record(expected.to_record()["release"]),
        roots,
        capabilities=cast(dict[str, str], _obj(expected.to_record()["capabilities"])),
    )
    if selected.to_bytes() != expected.to_bytes():
        raise ValidationStudyError("arm changed a fixed non-agent selection")
    _mkdir(arm_root / "tasks")
    _mkdir(location.parent.parent)
    _mkdir(location.parent)
    _mkdir(location)
    task = state["tasks"].select([identifier])
    recipe = _recipe(generation, location)
    pipeline._same_or_write(location / "task.json", task.to_bytes())
    pipeline._same_or_write(location / "generation.json", _json(recipe))
    controls = {_absolute(path): _digest(pin) for path, pin in occasion["controls"].items()}
    controls.update(
        receipts
        if receipts is not None
        else {
            Path(occasion["directory"]) / "occasion.json": pipeline._sha(occasion),
            Path(occasion["directory"]) / "reservation.json": pipeline._sha(_reservation(occasion)),
        }
    )
    controls.update(
        {
            location / "task.json": task.fingerprint(),
            location / "generation.json": pipeline._sha(recipe),
        }
    )
    return generation, selected, controls


def _child_ref(
    directory: Path, child: dict[str, object] | None, reason: str
) -> dict[str, object] | None:
    if child is not None:
        if child.get("status") == "complete":
            path = directory / "report.json"
        elif type(child.get("observation")) is str:
            path = directory / _path(child["observation"])
        else:
            return None
        raw = pipeline._read(path)
        if _json(child) != raw:
            raise ValidationStudyError("lower observation differs from its saved original")
        return {"path": str(path), "sha256": _sha(raw)}
    observations = directory / "observations"
    if observations.is_dir():
        paths = list(observations.iterdir())
        if paths and {path.name for path in paths} == {str(i) + ".json" for i in range(len(paths))}:
            path = observations / (str(len(paths) - 1) + ".json")
            raw = pipeline._read(path)
            if _load(raw).get("reason") == reason:
                return {"path": str(path), "sha256": _sha(raw)}
    return None


def _observe(
    state: dict[str, Any],
    occasion: dict[str, Any],
    authorization: Path,
    reason: str,
    position: dict[str, object],
    child: dict[str, object] | None,
    child_directory: Path,
) -> dict[str, object]:
    reader, current = _census(state, _slots(state), authorization)
    cells, generated, failed = _collect(state, occasion, reader, current)
    previous = _observations(state, occasion, reader, current)
    child_reference = _child_ref(child_directory, child, reason)
    if reason == "candidate_execution_failed" and failed is not None:
        generation = _obj(failed["generation"])
        child_reference = {
            "path": str(Path(_text(generation["directory"])) / "report.json"),
            "sha256": generation["report_sha256"],
        }
    reader.capture.finish()
    directory = Path(occasion["directory"])
    observations = directory / "observations"
    _mkdir(observations)
    path = observations / (str(len(previous)) + ".json")
    value = {
        "format": _OBSERVATION,
        "status": "incomplete",
        "reason": reason,
        "ordinal": occasion["ordinal"],
        "occasion_sha256": pipeline._sha(occasion),
        "position": position,
        "child": child_reference,
        "coverage": _coverage(occasion, cells, generated, failed is not None),
        "authorization": current,
        "observation": path.relative_to(directory).as_posix(),
        "claim": "incomplete validation; original evidence, look and liabilities retained",
    }
    pipeline._write(path, _json(value))
    return value


@_checked
def run_validation_occasion(
    directory: Path,
    *,
    ordinal: int,
    candidate_refs: Sequence[dict[str, str]],
    authorization: Authorization,
    review: dict[str, object],
    transport: RawHTTPTransport,
) -> dict[str, object]:
    """Reserve/use one original validation look; completed replay is passive.

    This v1 retains one grant for the whole study. Funding changes require a
    separately designed continuation; they cannot reset scientific look counts.
    """
    if (
        not isinstance(directory, Path)
        or not isinstance(authorization, Authorization)
        or (
            not isinstance(transport, RawHTTPTransport) or type(candidate_refs) not in (list, tuple)
        )
    ):
        raise ValidationStudyError("validation execution requires explicit original inputs")
    directory = _absolute(str(directory))
    authority_path = _absolute(str(authorization.path))
    checked_review = _review(review)

    def check() -> tuple[
        dict[str, Any],
        list[dict[str, Any]],
        dict[str, Any],
        NativeEvidence,
        dict[str, Any],
        dict[int, dict[str, object]],
    ]:
        state = _state(directory)
        _integer(ordinal, 0, state["record"]["max_looks"] - 1)
        controls = dict(state["controls"])
        candidates = _source_refs(list(candidate_refs), controls)
        if len(candidates) > state["record"]["max_candidates"]:
            raise ValidationStudyError("candidate count exceeds the fixed per-look ceiling")
        # Hash existing common inputs here; project actual derivative unions
        # separately before reserving a new occasion.
        _input_records(list(controls), controls)
        slots = _slots(state)
        if ordinal > len(slots):
            raise ValidationStudyError("new validation reservations cannot skip a look")
        reader, current = _census(state, slots, authority_path)
        occasion = _occasion(
            state, ordinal, candidates, controls, current, authority_path, checked_review
        )
        proposed = Path(occasion["directory"])
        if any(
            proposed.is_relative_to(path) or path.is_relative_to(proposed)
            for path in [*controls, authority_path]
        ):
            raise ValidationStudyError("reserved outputs overlap original inputs or authority")
        if ordinal < len(slots) and _json(slots[ordinal]) != _json(occasion):
            raise ValidationStudyError("existing look cannot adopt changed inputs or grant")
        completed = _saved_results(state, slots, reader, current)
        if ordinal == len(slots):
            _capacity(state, occasion)
            for previous in slots:
                if previous["ordinal"] not in completed:
                    _, _, failed = _collect(state, previous, reader, current)
                    if failed is None:
                        raise ValidationStudyError(
                            "new look cannot bypass unfinished original validation"
                        )
        reader.capture.finish()
        return state, slots, occasion, reader, current, completed

    state, slots, occasion, _, _, completed = check()
    if ordinal in completed:
        return completed[ordinal]
    with (
        trial_fence.work(
            authority_path, authorization._terms(), directory=directory, kind="validation"
        ),
        pipeline._exclusive(directory),
    ):
        state, slots, occasion, _, _, completed = check()
        if ordinal in completed:
            return completed[ordinal]
        location = Path(occasion["directory"])
        if ordinal == len(slots):
            location.mkdir()  # Consumed even if the original write is interrupted.
            pipeline._write(location / "occasion.json", _json(occasion))
            if pipeline._read(location / "occasion.json") != _json(occasion):
                raise ValidationStudyError("reserved occasion was not durably reread")
            # Only this original path may confirm reservation. A retained slot
            # without this receipt stays consumed and cannot reconstruct it.
            pipeline._write(location / "reservation.json", _json(_reservation(occasion)))
        reader, current = _census(state, _slots(state), authority_path)
        previous = _observations(state, occasion, reader, current)
        reader.capture.finish()
        if previous and previous[-1]["reason"] == "candidate_execution_failed":
            return previous[-1]
        position: dict[str, object] = {
            "arm_index": 0,
            "task_index": 0,
            "repetition": 0,
            "stage": "generation",
        }
        child_directory = location
        child: dict[str, object] | None = None
        try:
            for arm, task_index, identifier, repetition, cell in _cells(state, occasion):
                position = {
                    "arm_index": arm["arm_index"],
                    "task_index": task_index,
                    "repetition": repetition,
                    "stage": "generation",
                }
                child_directory, child = cell / "generation", None
                reader, current = _census(state, _slots(state), authority_path)
                done, _, failed = _collect(state, occasion, reader, current)
                reader.capture.finish()
                cell_index = (
                    arm["arm_index"] * len(occasion["selected_ids"]) + task_index
                ) * occasion["repetitions"] + repetition
                if cell_index < len(done):
                    continue
                if failed is not None:
                    return _observe(
                        state,
                        occasion,
                        authority_path,
                        "candidate_execution_failed",
                        position,
                        None,
                        child_directory,
                    )
                generation, selected, controls = _materialize(
                    state, occasion, arm, identifier, cell
                )
                if not child_directory.exists():
                    candidate_generation.prepare_candidate_generation(
                        child_directory,
                        descriptor=cell / "generation.json",
                        selection=selected,
                        roots={key: Path(value) for key, value in generation["roots"].items()},
                        authorization=authorization,
                        review=checked_review,
                        budget_microusd=generation["budget_microusd"],
                        max_calls=generation["max_calls"],
                        expected_runtime_sha256=state["runtime"],
                        input_files=list(controls),
                        expected_input_hashes=controls,
                    )
                child = candidate_generation.run_candidate_generation(
                    child_directory, transport=transport
                )
                if child["status"] != "complete":
                    return _observe(
                        state,
                        occasion,
                        authority_path,
                        _text(child["reason"]),
                        position,
                        child,
                        child_directory,
                    )
                verified = candidate_generation.inspect_candidate_generation(
                    child_directory,
                    authorization=authority_path,
                    expected_report_sha256=file_hash(child_directory / "report.json"),
                )
                if _json(verified) != _json(child):
                    raise ValidationStudyError("returned generation contradicts its publication")
                if child["disposition"] == "candidate_execution_failed":
                    return _observe(
                        state,
                        occasion,
                        authority_path,
                        "candidate_execution_failed",
                        position,
                        child,
                        child_directory,
                    )
                description = {
                    "format": "buddha.native-evaluation.v1",
                    "source_generation": child["source_generation"],
                    "native": state["record"]["native"],
                    "stages": state["record"]["stages"],
                }
                descriptor = cell / "evaluation.json"
                pipeline._same_or_write(descriptor, _json(description))
                controls[descriptor] = pipeline._sha(description)
                position["stage"] = "native"
                child_directory, child = cell / "evaluation", None
                if not child_directory.exists():
                    native_evaluation.prepare_evaluation(
                        child_directory,
                        descriptor=descriptor,
                        authorization=authorization,
                        review=checked_review,
                        input_files=list(controls),
                        expected_input_hashes=controls,
                    )
                child = native_evaluation.run_evaluation(child_directory, transport=transport)
                if child["status"] != "complete":
                    return _observe(
                        state,
                        occasion,
                        authority_path,
                        _text(child["reason"]),
                        position,
                        child,
                        child_directory,
                    )
            reader, current = _census(state, _slots(state), authority_path)
            result = _complete(state, occasion, reader, current)
            reader.capture.finish()
            pipeline._write(location / "result.json", _json(result))
            return result
        except KeyboardInterrupt:
            try:
                partial = _observe(
                    state, occasion, authority_path, "cancelled", position, child, child_directory
                )
            except (
                ValueError,
                TypeError,
                KeyError,
                OSError,
                RecursionError,
                sqlite3.Error,
                _Busy,
                _Unsupported,
            ):
                raise ValidationStudyError(
                    "cancelled validation slot retained; partial could not be saved"
                ) from None
            raise ValidationStudyInterrupted(partial) from None
        except (
            ValueError,
            TypeError,
            KeyError,
            OSError,
            RecursionError,
            sqlite3.Error,
            _Busy,
            _Unsupported,
        ):
            try:
                partial = _observe(
                    state, occasion, authority_path, "protocol", position, child, child_directory
                )
            except (
                ValueError,
                TypeError,
                KeyError,
                OSError,
                RecursionError,
                sqlite3.Error,
                _Busy,
                _Unsupported,
            ):
                raise ValidationStudyError(
                    "validation slot retained; partial could not be saved"
                ) from None
            raise ValidationStudyStopped(partial) from None
