"""Execute a frozen policy matrix through the existing baseline and native routes.

The host preserves each complete answer set and every judging occasion. This
module neither allocates funding nor computes a benchmark score or ranking.
"""

import copy
import hashlib
import sqlite3
from collections.abc import Callable
from dataclasses import dataclass
from functools import wraps
from pathlib import Path
from typing import cast

from buddha import baseline, native_evaluation
from buddha import native_pipeline as pipeline
from buddha.answers import TaskSet
from buddha.authorization import Authorization
from buddha.doctor import _authority, _Busy, _Capture, _owner, _Unsupported
from buddha.gateway import Gateway, RawHTTPTransport, _read_manifest, execution_identity
from buddha.gateway_history import MAX_LEDGER_BYTES
from buddha.policy_study import PolicyStudy
from buddha.releases import ReleaseError, _digest, _json, _load, _object, _root, _text, file_hash


class PolicyRunError(ReleaseError):
    """The frozen study, original execution or retained child evidence is invalid."""


def _checked[**P, T](function: Callable[P, T]) -> Callable[P, T]:
    @wraps(function)
    def checked(*args: P.args, **kwargs: P.kwargs) -> T:
        try:
            return function(*args, **kwargs)
        except (ValueError, TypeError, KeyError, OSError, RecursionError) as error:
            if isinstance(error, PolicyRunError):
                raise
            raise PolicyRunError(
                "policy execution evidence is invalid; original state retained"
            ) from None

    return checked


def _sources() -> list[Path]:
    package = Path(__file__).absolute().parent
    return list(
        dict.fromkeys(
            [
                *baseline._sources(),
                *native_evaluation._sources(),
                package / "policy_run.py",
                package / "policy_study.py",
            ]
        )
    )


@dataclass(frozen=True)
class _Execution:
    study: PolicyStudy
    template: dict[str, object]
    recipe: dict[str, object]
    files: dict[Path, str]


def _definition(
    path: Path, authority: Authorization, bindings: dict[str, object] | None = None
) -> _Execution:
    files: dict[Path, str] = {}

    def consume(source: Path, expected: object = None) -> bytes:
        source = source.absolute()
        if bindings is not None:
            bound = bindings[str(source)]
            if expected is not None and expected != bound:
                raise PolicyRunError("study reference differs from its original binding")
            expected = bound
        raw = pipeline._read(source, expected)
        files[source] = hashlib.sha256(raw).hexdigest()
        return raw

    description = _object(_load(consume(path)), {"format", "study", "baseline", "authorization"})
    if description["format"] != "buddha.policy-execution.v1":
        raise PolicyRunError("unsupported policy execution descriptor")

    def reference(value: object) -> bytes:
        record = _object(value, {"path", "sha256"})
        return consume(pipeline._absolute(record["path"]), _digest(record["sha256"]))

    study = PolicyStudy.from_bytes(reference(description["study"]))
    template_raw = reference(description["baseline"])
    template = _object(_load(template_raw), {"format", "tasks", "generation", "native", "stages"})
    tasks = TaskSet.from_bytes(consume(pipeline._absolute(template["tasks"])))
    generation = _object(template["generation"])
    recipe_path = pipeline._absolute(generation["descriptor"])
    recipe = _object(
        _load(consume(recipe_path)),
        {"format", "tasks", "config", "entrypoint", "executor", "profile"},
    )
    baseline._definition(
        pipeline._absolute(_object(description["baseline"])["path"]),
        {str(source): digest for source, digest in files.items()},
    )
    if (
        tasks.fingerprint() != study.tasks.fingerprint()
        or recipe["format"] != "buddha.frozen-generation.v1"
        or pipeline._absolute(recipe["tasks"]) != pipeline._absolute(template["tasks"])
        or recipe["config"] != study.schedule()[0]["generation_config"]
    ):
        raise PolicyRunError("baseline template changes the study's selected tasks or first config")
    expected = _object(description["authorization"], {"path", "id", "terms_sha256", "scope"})
    summary = authority.summary()
    if (
        pipeline._absolute(expected["path"]) != authority.path
        or _text(expected["id"]) != summary["authorization_id"]
        or _digest(expected["terms_sha256"]) != summary["terms_sha256"]
        or expected["scope"] != "policy study: " + study.fingerprint()
        or expected["scope"] != summary["scope"]
    ):
        raise PolicyRunError("study differs from the explicit shared authority and scope")
    for source in _sources():
        consume(source)
    return _Execution(study, template, recipe, files)


def _controls(directory: Path, execution: _Execution) -> list[Path]:
    return [directory / "context.json", *execution.files]


def _materialize(
    directory: Path, index: int, cell: dict[str, object], execution: _Execution
) -> Path:
    location = directory / "cells" / str(index)
    if not location.exists():
        location.mkdir()
        (location / "judgments").mkdir()
    _root(location)
    _root(location / "judgments")
    recipe = copy.deepcopy(execution.recipe)
    recipe["config"] = cell["generation_config"]
    recipe_path = location / "generation.json"
    pipeline._same_or_write(recipe_path, _json(recipe))
    description = copy.deepcopy(execution.template)
    _object(description["generation"])["descriptor"] = str(recipe_path)
    path = location / "baseline.json"
    pipeline._same_or_write(path, _json(description))
    return path


def _source_generation(directory: Path) -> dict[str, object]:
    owner = directory / "owners/0"
    return {
        "baseline_directory": str(directory),
        "stage_seal_sha256": file_hash(directory / "completed/0.json"),
        "owner_manifest_sha256": pipeline._sha(_read_manifest(owner)),
        "owner_ledger_sha256": file_hash(owner / "operations.sqlite3", max_bytes=MAX_LEDGER_BYTES),
    }


def _evaluation_descriptor(
    location: Path, source: dict[str, object], execution: _Execution
) -> Path:
    path = location.parent / (location.name + ".json")
    pipeline._same_or_write(
        path,
        _json(
            {
                "format": "buddha.native-evaluation.v1",
                "source_generation": source,
                "native": execution.template["native"],
                "stages": execution.template["stages"],
            }
        ),
    )
    return path


def _population(directory: Path, schedule: list[dict[str, object]], occasions: int) -> None:
    cells = list((directory / "cells").iterdir())
    if {path.name for path in cells} != {str(index) for index in range(len(cells))} or len(
        cells
    ) > len(schedule):
        raise PolicyRunError("study contains foreign or out-of-order cells")
    for cell in cells:
        _root(cell)
        judgments = cell / "judgments"
        _root(judgments)
        entries = list(judgments.iterdir())
        directories = [path for path in entries if path.name.isdecimal()]
        expected = {str(index) for index in range(1, len(directories) + 1)}
        if (
            {path.name for path in directories} != expected
            or len(directories) >= occasions
            or {path.name for path in entries} - expected - {name + ".json" for name in expected}
        ):
            raise PolicyRunError("study contains foreign or out-of-order judging occasions")
        for path in directories:
            _root(path)


def _preflight(
    directory: Path,
    execution: _Execution,
    authority: Authorization,
    review: dict[str, object],
    controls: list[Path],
    bindings: dict[str, object],
    transport: RawHTTPTransport,
) -> set[str]:
    """Validate every already existing owner before running an earlier cell."""
    identifiers: set[str] = set()
    expected_controls = {str(path): _digest(bindings[str(path)]) for path in controls}
    if any(file_hash(path) != expected_controls[str(path)] for path in controls):
        raise PolicyRunError("an original study control changed")
    stages = cast(list[object], execution.template["stages"])
    schedule = execution.study.schedule()
    occasions = cast(int, execution.study.to_record()["judge_occasions"])
    _population(directory, schedule, occasions)
    funded = {
        _text(row["run_id"]): row
        for row in cast(list[dict[str, object]], authority.summary()["runs"])
    }
    unfinished = False
    for cell in sorted((directory / "cells").iterdir(), key=lambda path: int(path.name)):
        baseline_descriptor = _materialize(
            directory, int(cell.name), schedule[int(cell.name)], execution
        )
        children = [(cell / "baseline", True)] + [
            (cell / "judgments" / str(index), False) for index in range(1, occasions)
        ]
        for child, is_baseline in children:
            if not child.exists():
                unfinished = True
                continue
            _root(child)
            owners = child / "owners"
            _root(owners)
            descriptor = (
                baseline_descriptor
                if is_baseline
                else _evaluation_descriptor(child, _source_generation(cell / "baseline"), execution)
            )
            context_path = child / "context.json"
            context = _load(pipeline._read(context_path))
            if context != {
                "format": "buddha.baseline-context.v1"
                if is_baseline
                else "buddha.native-evaluation-context.v1",
                "descriptor": str(descriptor),
            }:
                raise PolicyRunError("child context changes the planned descriptor")
            child_controls = expected_controls | {
                str(descriptor): file_hash(descriptor),
                str(context_path): file_hash(context_path),
            }
            entries = list(owners.iterdir())
            first = 0 if is_baseline else 1
            if {path.name for path in entries} != {
                str(i) for i in range(first, first + len(entries))
            } or first + len(entries) > 1 + len(stages):
                raise PolicyRunError("child contains foreign or aliased owners")
            for owner in entries:
                gateway = Gateway(owner, transport=transport)
                record = _read_manifest(owner)
                execution_identity(owner, record)
                identifier = _text(record["run_id"])
                funding = funded[identifier]
                if (
                    type(funding["historical"]) is not int
                    or funding["historical"] != 0
                    or funding["runtime_sha256"] != record["execution_sha256"]
                    or funding["manifest_sha256"] != gateway.manifest_sha256
                ):
                    raise PolicyRunError("child owner differs from its original funding identity")
                if unfinished and gateway.ledger.totals()["operation_count"]:
                    raise PolicyRunError("retained work skips an unfinished scheduled predecessor")
                index = int(owner.name)
                role = "generation" if is_baseline and index == 0 else "native"
                template = _object(execution.template[role])
                no_model = index == len(stages)
                inputs = {
                    _text(item["path"]): item["sha256"]
                    for item in cast(
                        list[dict[str, object]], _object(record["invocation"])["inputs"]
                    )
                }
                if (
                    record["authorization_path"] != str(authority.path)
                    or record["selection"] != template["selection"]
                    or record["roots"] != template["roots"]
                    or record["review"] != review
                    or record["settings"]
                    != {
                        "budget_microusd": 1 if no_model else template["budget_microusd"],
                        "max_calls": 1 if no_model else template["max_calls"],
                    }
                    or any(inputs.get(path) != digest for path, digest in child_controls.items())
                    or gateway.manifest_sha256 != pipeline._sha(record)
                ):
                    raise PolicyRunError("existing child owner differs from the frozen study")
                identifiers.add(identifier)
            complete = _completed_child(child, first, len(stages), entries, funded, authority)
            unfinished = unfinished or not complete
    for row in cast(list[dict[str, object]], authority.summary()["runs"]):
        if (
            Path(_text(row["directory"])).is_relative_to(directory)
            and row["run_id"] not in identifiers
        ):
            raise PolicyRunError("a known study owner is missing; replacement is not recovery")
    return identifiers


def _completed_child(
    child: Path,
    first: int,
    last: int,
    owners: list[Path],
    funded: dict[str, dict[str, object]],
    authority: Authorization,
) -> bool:
    path = child / "report.json"
    if not path.exists():
        return False
    report = _load(pipeline._read(path))
    if report.get("status") != "complete" or {owner.name for owner in owners} != {
        str(index) for index in range(first, last + 1)
    }:
        raise PolicyRunError("stored child completion has invalid coverage")
    seals = {}
    for index in range(first, last + 1):
        record = _read_manifest(child / "owners" / str(index))
        if funded[_text(record["run_id"])]["active"] is not False:
            raise PolicyRunError("stored child completion lacks its inactive owner anchor")
        seal = child / "completed" / (str(index) + ".json")
        digest = file_hash(seal)
        prefix = "baseline completed: " if first == 0 else "native evaluation completed: "
        # This checks an existing inactive owner's reason; it never anchors active work.
        authority.deactivate(_text(record["run_id"]), prefix + digest)
        seals[str(seal.relative_to(child))] = digest
    if _json(report.get("stage_seals")) != _json(seals):
        raise PolicyRunError("stored child completion differs from its anchored seals")
    return True


def _child_controls(
    child: Path, first: int, controls: list[Path], bindings: dict[str, object]
) -> None:
    record = _read_manifest(child / "owners" / str(first))
    inputs = {
        _text(item["path"]): item["sha256"]
        for item in cast(list[dict[str, object]], _object(record["invocation"])["inputs"])
    }
    for path in controls:
        expected = _digest(bindings[str(path)])
        if inputs.get(str(path)) != expected or file_hash(path) != expected:
            raise PolicyRunError("child owner cannot adopt a changed original study control")


def _reason(child: dict[str, object], directory: Path, authority: Authorization) -> str:
    reason = child.get("reason")
    if reason is None:
        reports = child.get("stages")
        if type(reports) is not list or not reports:
            raise PolicyRunError("incomplete child lacks its actual stop report")
        report = _object(reports[-1])
        reason = report.get("reason", _object(report.get("worker", {})).get("reason"))
    reason = (
        reason
        if type(reason) is str
        and reason
        in {"unknown", "authority", "protocol", "cancelled", "native_error", "agent_error"}
        else "native_error"
    )
    if reason == "authority":
        # The native session groups funding guards under this broad stop code.
        # Explain a verified retained unknown without rewriting its literal report
        # or claiming it was the only guard; the shared spending halt is unchanged.
        try:
            index = child.get("stopped_stage")
            if type(index) is int and index >= 0:
                owner = directory / "owners" / str(index)
                capture = _Capture(owner)
                observed = _owner(capture, owner)
                funding = _authority(capture, authority.path, [observed])
                matches = (
                    [
                        row
                        for row in cast(list[dict[str, object]], funding["auth_runs"])
                        if row["run_id"] == observed.run_id
                    ]
                    if funding is not None
                    else []
                )
                if (
                    len(matches) == 1
                    and type(matches[0]["historical"]) is int
                    and matches[0]["historical"] == 0
                    and matches[0]["runtime_sha256"] == observed.manifest["execution_sha256"]
                    and observed.manifest["authorization_path"] == str(authority.path)
                    and any(operation.status == "unknown" for operation in observed.operations)
                ):
                    capture.finish()
                    return "unknown"
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
            pass  # Unavailable diagnostic evidence cannot replace the actual stop code.
    return reason


def _partial(
    directory: Path,
    execution: _Execution,
    authority: Authorization,
    cells: list[dict[str, object]],
    index: int,
    cell: dict[str, object],
    occasion: int,
    child: Path,
    reason: str,
    report: dict[str, object] | None,
) -> dict[str, object]:
    number = 0
    while (directory / "observations" / (str(number) + ".json")).exists():
        number += 1
    path = directory / "observations" / (str(number) + ".json")
    result: dict[str, object] = {
        "format": "buddha.policy-run-report.v1",
        "status": "incomplete",
        "study_sha256": execution.study.fingerprint(),
        "reason": reason,
        "cell_index": index,
        "cell_id": cell["cell_id"],
        "occasion_index": occasion,
        "child_directory": str(child),
        "child_report": report,
        "cells": cells,
        "authorization": authority.summary(),
        "observation": path.relative_to(directory).as_posix(),
        "claim": "incomplete declared study; original children, replies and holds retained",
    }
    pipeline._write(path, _json(result))
    return result


@_checked
def prepare_study(
    directory: Path, *, descriptor: Path, authorization: Authorization, review: dict[str, object]
) -> Path:
    """Bind the declared study and first baseline owner, without keys or calls."""
    if (
        not isinstance(directory, Path)
        or not isinstance(descriptor, Path)
        or not isinstance(authorization, Authorization)
    ):
        raise PolicyRunError("study needs explicit paths and an existing authority")
    descriptor = descriptor.absolute()
    execution = _definition(descriptor, authorization)
    directory = directory.absolute()
    _root(directory.parent)
    for role in ("generation", "native"):
        for value in _object(_object(execution.template[role])["roots"]).values():
            root = pipeline._absolute(value)
            if directory.is_relative_to(root) or root.is_relative_to(directory):
                raise PolicyRunError("study output overlaps a selected input component")
    directory.mkdir()
    for name in ("cells", "observations"):
        (directory / name).mkdir()
    context = {"format": "buddha.policy-run-context.v1", "descriptor": str(descriptor)}
    pipeline._write(directory / "context.json", _json(context))
    schedule = execution.study.schedule()
    first = _materialize(directory, 0, schedule[0], execution)
    baseline.prepare_baseline(
        first.parent / "baseline",
        descriptor=first,
        authorization=authorization,
        review=review,
        input_files=_controls(directory, execution),
    )
    initial = _read_manifest(first.parent / "baseline/owners/0")
    bound = {
        _text(item["path"]): item["sha256"]
        for item in cast(list[dict[str, object]], _object(initial["invocation"])["inputs"])
    }
    for path, digest in (
        execution.files | {directory / "context.json": pipeline._sha(context)}
    ).items():
        if file_hash(path) != digest or bound.get(str(path)) != digest:
            raise PolicyRunError("study control changed during first-owner preparation")
    return directory


def _occasion(
    index: int,
    plan: dict[str, object],
    child: Path,
    report: dict[str, object],
    frozen: dict[Path, str],
) -> dict[str, object]:
    stored = pipeline._read(child / "report.json")
    if _json(_load(stored)) != _json(report) or report.get("status") != "complete":
        raise PolicyRunError("child completion differs from its literal stored report")
    summary = _object(report["summary"], {"path", "sha256"})
    summary_path = pipeline._absolute(summary["path"])
    if not summary_path.is_relative_to(child / "attempts"):
        raise PolicyRunError("child summary is outside its actual attempts")
    frozen[child / "report.json"] = hashlib.sha256(stored).hexdigest()
    frozen[summary_path] = _digest(summary["sha256"])
    if file_hash(summary_path) != frozen[summary_path]:
        raise PolicyRunError("child summary differs from its completion")
    return {
        "index": index,
        "occasion_id": plan["occasion_id"],
        "directory": str(child),
        "report_sha256": hashlib.sha256(stored).hexdigest(),
        "summary": report["summary"],
    }


@_checked
def run_study(directory: Path, *, transport: RawHTTPTransport) -> dict[str, object]:
    """Run or recover declared cells and occasions, preserving every original child."""
    if not isinstance(directory, Path) or not isinstance(transport, RawHTTPTransport):
        raise PolicyRunError("study needs its original directory and raw transport")
    directory = directory.absolute()
    with pipeline._exclusive(directory):
        return _run(directory, transport)


def _run(directory: Path, transport: RawHTTPTransport) -> dict[str, object]:
    anchor = directory / "cells/0/baseline/owners/0"
    Gateway(anchor, transport=transport)
    initial = _read_manifest(anchor)
    bound = {
        _text(item["path"]): item["sha256"]
        for item in cast(list[dict[str, object]], _object(initial["invocation"])["inputs"])
    }
    context_path = directory / "context.json"
    context = _object(
        _load(pipeline._read(context_path, bound[str(context_path)])), {"format", "descriptor"}
    )
    if context["format"] != "buddha.policy-run-context.v1":
        raise PolicyRunError("unsupported original study context")
    authority = Authorization(pipeline._absolute(initial["authorization_path"]))
    execution = _definition(pipeline._absolute(context["descriptor"]), authority, bound)
    schedule = execution.study.schedule()
    controls = _controls(directory, execution)
    _population(directory, schedule, cast(int, execution.study.to_record()["judge_occasions"]))
    _preflight(
        directory, execution, authority, _object(initial["review"]), controls, bound, transport
    )
    cells: list[dict[str, object]] = []
    frozen: dict[Path, str] = {}
    executed = False
    for index, cell in enumerate(schedule):
        execution_identity(anchor)
        description = _materialize(directory, index, cell, execution)
        source: dict[str, object] | None = None
        occasions: list[dict[str, object]] = []
        for occasion_index, plan in enumerate(
            cast(list[dict[str, object]], cell["judge_occasions"])
        ):
            child = (
                description.parent / "baseline"
                if occasion_index == 0
                else description.parent / "judgments" / str(occasion_index)
            )
            if occasion_index == 0:
                if not child.exists():
                    baseline.prepare_baseline(
                        child,
                        descriptor=description,
                        authorization=authority,
                        review=_object(initial["review"]),
                        input_files=controls,
                    )
                run = baseline.run_baseline
            else:
                if source is None:
                    raise PolicyRunError("judging lacks its completed original generation")
                evaluation = _evaluation_descriptor(child, source, execution)
                if not child.exists():
                    native_evaluation.prepare_evaluation(
                        child,
                        descriptor=evaluation,
                        authorization=authority,
                        review=_object(initial["review"]),
                        input_files=controls,
                    )
                run = native_evaluation.run_evaluation
            execution_identity(anchor)
            _child_controls(child, 0 if occasion_index == 0 else 1, controls, bound)
            attempts = {path.name for path in (child / "attempts").iterdir()}
            report: dict[str, object] | None = None
            try:
                report = run(child, transport=transport)
                executed = executed or bool(
                    {path.name for path in (child / "attempts").iterdir()} - attempts
                )
                execution_identity(anchor)
                if report["status"] != "complete":
                    return _partial(
                        directory,
                        execution,
                        authority,
                        cells,
                        index,
                        cell,
                        occasion_index,
                        child,
                        _reason(report, child, authority),
                        report,
                    )
                occasions.append(_occasion(occasion_index, plan, child, report, frozen))
            except KeyboardInterrupt:
                _partial(
                    directory,
                    execution,
                    authority,
                    cells,
                    index,
                    cell,
                    occasion_index,
                    child,
                    "cancelled",
                    report,
                )
                raise
            except (ValueError, TypeError, KeyError, OSError, RecursionError):
                if {path.name for path in (child / "attempts").iterdir()} - attempts:
                    _partial(
                        directory,
                        execution,
                        authority,
                        cells,
                        index,
                        cell,
                        occasion_index,
                        child,
                        "protocol",
                        report,
                    )
                raise
            if occasion_index == 0:
                source = _source_generation(child)
        cells.append(
            {
                "cell_id": cell["cell_id"],
                "arm_id": cell["arm_id"],
                "arm_index": cell["arm_index"],
                "generation_repeat": cell["generation_repeat"],
                "source_generation": source,
                "occasions": occasions,
            }
        )
    try:
        execution_identity(anchor)
        owners = _preflight(
            directory, execution, authority, _object(initial["review"]), controls, bound, transport
        )
        for path, digest in frozen.items():
            if file_hash(path) != digest:
                raise PolicyRunError(
                    "a recorded child report or summary changed before publication"
                )
        result: dict[str, object] = {
            "format": "buddha.policy-run-report.v1",
            "status": "complete",
            "study_sha256": execution.study.fingerprint(),
            "cells": cells,
            "authorization": authority.summary(),
            "claim": "complete declared native comparison; no ranking or improvement claim",
        }
        return pipeline.publish_complete(directory / "report.json", result, authority, owners)
    except (ValueError, TypeError, KeyError, OSError, RecursionError):
        if executed:
            _partial(
                directory,
                execution,
                authority,
                cells,
                index,
                cell,
                occasion_index,
                child,
                "protocol",
                report,
            )
        raise
