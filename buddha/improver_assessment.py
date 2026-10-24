"""Prospective finite-improver trial, immutable final grid and original-record analysis.

Only the existing confined source/native producers execute selected code. Final
tasks/results never become improvement feedback. Scientific assumptions remain
separate from custody, numerical rule satisfaction and execution completion.
"""

import sqlite3
from collections.abc import Callable
from functools import wraps
from pathlib import Path
from typing import Any, cast

from buddha import final_evaluation as final
from buddha import gateway, improver_analysis, improver_study, trial_fence
from buddha import launch_common as launch
from buddha import native_pipeline as pipeline
from buddha import noveltybench_results as projection
from buddha import source_screen_results as saved_native
from buddha import validation_study as study
from buddha.answers import TaskSet, _id, _source
from buddha.authorization import Authorization
from buddha.doctor import _Busy, _Capture, _Unsupported
from buddha.improvement_rule import ImprovementRule
from buddha.native_evidence import NativeEvidence
from buddha.releases import ReleaseError, Selection, _digest, _json, _load, _text, file_hash
from buddha.wire import _integer

_FORMAT = "buddha.improver-assessment-trial.v1"
_CONTEXT = "buddha.improver-assessment-context.v1"
_SCHEDULE = "buddha.improver-final-schedule.v1"
_READY = "buddha.improver-final-freeze-ready.v1"
_POLICY = "confirmed_finite_c_only_slots.v1"
_CLAIM = (
    "Fixed selected-descendant panel under the original paired method; no future-search, "
    "unseen-task, human-quality, target-repair or promotion claim."
)


class ImproverAssessmentError(ReleaseError):
    """Original prospective intent, finite custody or sealed assessment is invalid."""


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
            if isinstance(error, ImproverAssessmentError):
                raise
            raise ImproverAssessmentError("invalid original improver assessment evidence") from None

    return checked


def _source_hashes() -> dict[str, str]:
    paths = improver_analysis._source_paths() | {
        "buddha/final_evaluation.py": Path(final.__file__).absolute(),
        "buddha/improver_study.py": Path(improver_study.__file__).absolute(),
        "buddha/improver_assessment.py": Path(__file__).absolute(),
    }
    return {name: file_hash(path) for name, path in paths.items()}


def _population(state: dict[str, Any]) -> dict[str, object]:
    tasks = {task.id: task for task in state["tasks"].tasks}
    members = {row["task_id"]: row for row in state["custody"]["population"]}
    return {
        "format": "buddha.improver-analysis-population.v1",
        "taskset_sha256": state["tasks"].fingerprint(),
        "custody_sha256": state["record"]["custody"]["sha256"],
        "tasks": [
            {"task_id": key, "family_id": members[key]["family_id"], "count": tasks[key].count}
            for key in state["record"]["final_ids"]
        ],
    }


def _definition(raw: bytes, runtime: str) -> dict[str, Any]:
    record = study._obj(
        _load(raw),
        {
            "format",
            "experiment_id",
            "development",
            "tasks",
            "custody",
            "final_ids",
            "sealed_repetitions",
            "generation",
            "native",
            "stages",
            "analysis_plan",
            "improvement_rule",
            "selection_policy",
            "phase_limits",
            "consumer_sources",
        },
    )
    if record["format"] != _FORMAT or record["selection_policy"] != _POLICY:
        raise ImproverAssessmentError("unsupported prospective improver assessment")
    _text(record["experiment_id"])
    runtime = _digest(runtime)
    controls: dict[Path, str] = {}
    refs = {
        name: study._ref(record[name], controls)
        for name in ("development", "tasks", "custody", "analysis_plan", "improvement_rule")
    }
    development, screens = improver_study._declaration(
        _load(pipeline._read(Path(refs["development"]["path"]))),
        runtime,
        active=True,
    )
    tasks = TaskSet.from_bytes(pipeline._read(Path(refs["tasks"]["path"])))
    release, data = _source(tasks.to_record())
    if tasks.to_bytes() != TaskSet.from_dataset(release, data).to_bytes():
        raise ImproverAssessmentError("assessment requires the complete original task source")
    selected = [_id(key) for key in study._list(record["final_ids"])]
    if (
        not selected
        or len(set(selected)) != len(selected)
        or not set(selected) <= {task.id for task in tasks.tasks}
    ):
        raise ImproverAssessmentError("final IDs repeat or change the complete population")
    custody = study._custody(
        _load(pipeline._read(Path(refs["custody"]["path"]))),
        tasks,
        selected,
        controls,
        phase="final",
    )
    assigned = {row["task_id"] for row in custody["population"] if row["phase"] == "final"}
    if set(selected) != assigned:
        raise ImproverAssessmentError("every and only assigned final member must be assessed")
    for screen in screens:
        base = screen.to_record()
        if _json(base["source"]) != tasks.to_bytes():
            raise ImproverAssessmentError("development and sealed custody use different sources")
        partition = study._obj(base["split"])["partitions"]
        if set(study._obj(partition)["final"]) != assigned:
            raise ImproverAssessmentError("development split changes original final membership")
        if any(
            row["phase"] != "development"
            for row in custody["population"]
            if row["task_id"] in study._list(base["selected_ids"])
        ):
            raise ImproverAssessmentError("development consumes a non-development custody member")
    study._validate_execution(record, tasks, runtime)
    rule = ImprovementRule.from_bytes(pipeline._read(Path(refs["improvement_rule"]["path"])))
    plan = improver_analysis.ImproverAnalysisPlan.from_bytes(
        pipeline._read(Path(refs["analysis_plan"]["path"]))
    )
    method = plan.to_record()
    repetitions = _integer(record["sealed_repetitions"], 1)
    counts = {
        "starts": len(screens),
        "development_repetitions": development["repetitions"],
        "m": development["descendant_opportunities"],
        "tasks": len(selected),
        "sealed_repetitions": repetitions,
    }
    intrinsic, _ = improver_study._intrinsic_inputs(
        development,
        screens,
        Path(refs["development"]["path"]),
        refs["development"]["sha256"],
        runtime,
    )
    improver_study._bind_controls(controls, intrinsic)
    state: dict[str, Any] = {
        "record": record,
        "definition": record,
        "tasks": tasks,
        "custody": custody,
        "plan": plan,
        "rule": rule,
        "runtime": runtime,
        "development": development,
        "screens": screens,
        "controls": controls,
    }
    if (
        method["counts"] != counts
        or method["projection_release_sha256"] != tasks.release_sha256
        or method["improvement_rule_sha256"] != rule.fingerprint()
        or method["population_sha256"] != pipeline._sha(_population(state))
        or method["analyzer_sources"] != improver_analysis._source_hashes()
        or record["consumer_sources"] != _source_hashes()
    ):
        raise ImproverAssessmentError(
            "prospective method, population, rule or source closure changed"
        )
    conditions = len(screens) * development["repetitions"]
    maximum = 3 * conditions * len(selected) * repetitions
    limits = study._obj(record["phase_limits"], {"search", "validation", "final"})
    for value in limits.values():
        for amount in study._obj(value, {"budget_microusd", "max_calls"}).values():
            _integer(amount)
    expected_final = {
        key: maximum
        * (record["generation"][key] + (len(record["stages"]) - 1) * record["native"][key] + 1)
        for key in ("budget_microusd", "max_calls")
    }
    for amount in expected_final.values():
        _integer(amount, 1)
    if limits != {
        "search": development["limits"]["study"],
        "validation": {"budget_microusd": 0, "max_calls": 0},
        "final": expected_final,
    }:
        raise ImproverAssessmentError("original reserves must cover the complete prospective grid")
    package = Path(__file__).absolute().parent.parent
    improver_study._bind_controls(
        controls, {package / name: _digest(pin) for name, pin in record["consumer_sources"].items()}
    )
    protected: list[Path] = []
    for screen in screens:
        for role in ("generation", "native"):
            roots = study._obj(study._obj(screen.to_record()[role])["roots"])
            protected.extend(Path(_text(value)) for value in roots.values())
    for actor in development["improvers"]:
        protected.extend(Path(value) for value in actor["roots"].values())
    state["protected"] = protected
    return state


def _purposes(state: dict[str, Any]) -> dict[str, str]:
    identity = pipeline._sha(state["definition"])
    return {
        "search": "source screen: " + state["screens"][0].comparison_key(),
        "validation": "unused improver validation: " + identity,
        "final": "improver assessment: " + identity,
    }


def _prospective_controls(state: dict[str, Any], root: Path) -> dict[Path, str]:
    pins = dict(state["controls"])
    paths = [
        root / name
        for name in (
            ".buddha-evaluation-trial.json",
            "definition.json",
            "context.json",
            "funding.json",
        )
    ]
    study_root = root / "search/study"
    paths += [
        study_root / name
        for name in (
            "context.json",
            "declaration.json",
            "report.json",
            "freeze/selections.json",
            "freeze/confirmation.json",
        )
    ]
    for start in range(len(state["screens"])):
        paths.append(study_root / "inputs/starts" / str(start) / "candidate.py")
        for repeat in range(state["development"]["repetitions"]):
            common = study_root / "common" / str(start) / str(repeat)
            paths.append(common / "screen/report.json")
            paths += [
                common / "witness/feedback" / (name + ".json")
                for name in ("source", "split", "feedback", "provenance")
            ]
            for arm in range(2):
                index = (start * state["development"]["repetitions"] + repeat) * 2 + arm
                paths.append(study_root / "freeze/sources" / (str(index) + ".py"))
    maximum_arms = 3 * len(state["screens"]) * state["development"]["repetitions"]
    paths += [root / "freeze/sources" / (str(index) + ".py") for index in range(maximum_arms)]
    return pins | dict.fromkeys(paths, "0" * 64)


@_checked
def prepare_improver_assessment_trial(
    directory: Path,
    *,
    declaration: Path,
    expected_sha256: str,
    expected_runtime_sha256: str,
    authorizations: dict[str, Authorization],
    development_review: dict[str, object],
) -> Path:
    directory, declaration = final._path(directory), final._path(declaration)
    state = _definition(
        pipeline._read(declaration, _digest(expected_sha256)), expected_runtime_sha256
    )
    review = gateway._review(development_review, fresh=True)
    prospective = _prospective_controls(state, directory) | {declaration: _digest(expected_sha256)}
    study._capacity(
        state,
        {
            "directory": str(directory / "final"),
            "controls": {str(p): d for p, d in prospective.items()},
        },
        receipts={
            directory / "freeze" / name: "0" * 64 for name in ("schedule.json", "ready.json")
        },
    )
    final._prepare_trial_root(
        directory,
        declaration=declaration,
        expected_sha256=expected_sha256,
        expected_runtime_sha256=expected_runtime_sha256,
        state=state,
        authorizations=authorizations,
        purposes=_purposes(state),
        context_format=_CONTEXT,
        extra_context={"development_review": review},
    )
    controls = dict(state["controls"]) | {
        declaration: _digest(expected_sha256),
        directory / "context.json": file_hash(directory / "context.json"),
    }
    development = state["record"]["development"]
    improver_study.prepare_improver_study(
        directory / "search/study",
        declaration=Path(development["path"]),
        expected_sha256=development["sha256"],
        expected_runtime_sha256=expected_runtime_sha256,
        authorization=authorizations["search"],
        review=review,
        input_bindings=controls,
    )
    return directory


def _state(directory: Path) -> dict[str, Any]:
    root = final._path(directory)
    fixed = trial_fence.required_controls(root / "final")
    context = study._obj(
        _load(pipeline._read(root / "context.json")),
        {
            "format",
            "external_declaration",
            "expected_runtime_sha256",
            "controls",
            "host_core",
            "host_runtime",
            "development_review",
        },
    )
    if context["format"] != _CONTEXT:
        raise ImproverAssessmentError("unsupported original improver context")
    state = _definition(
        pipeline._read(root / "definition.json"), context["expected_runtime_sha256"]
    )
    external = study._obj(context["external_declaration"], {"path", "sha256"})
    if (
        _load(pipeline._read(final._path(external["path"]), external["sha256"]))
        != state["definition"]
    ):
        raise ImproverAssessmentError("original raw declaration changed")
    controls = state["controls"] | {Path(external["path"]): external["sha256"]}
    if context["controls"] != {str(path): pin for path, pin in controls.items()}:
        raise ImproverAssessmentError("original source/control population changed")
    funding = study._obj(_load(pipeline._read(root / "funding.json")))
    purposes = _purposes(state)
    for phase, row in funding["phases"].items():
        if row["purpose"] != purposes[phase] or any(
            row[key] != value for key, value in state["record"]["phase_limits"][phase].items()
        ):
            raise ImproverAssessmentError("original phase purpose or reserve changed")
    state.update(root=root, directory=root / "final", context=context, funding=funding)
    state["controls"] = controls | fixed | {root / "context.json": pipeline._sha(context)}
    for path, digest in state["controls"].items():
        pipeline._read(path, digest)
    return state


def _development(state: dict[str, Any], expected: str) -> tuple[dict[str, Any], _Capture]:
    directory = state["root"] / "search/study"
    capture = _Capture(directory)
    report = study._obj(
        improver_study.inspect_improver_study(
            directory,
            authorization=final._phase_authority(state, "search"),
            expected_report_sha256=expected,
            sink=capture,
        )
    )
    raw = capture.read(directory / "context.json")
    context = study._obj(_load(raw))
    if (
        context["declaration"] != state["record"]["development"]["path"]
        or context["declaration_sha256"] != state["record"]["development"]["sha256"]
        or context["review"] != state["context"]["development_review"]
    ):
        raise ImproverAssessmentError(
            "finite study is not the original prospectively bound development"
        )
    bindings = study._obj(context["controls"])
    if any(bindings.get(str(path)) != pin for path, pin in state["controls"].items()):
        raise ImproverAssessmentError("finite first owner omitted original outer trial controls")
    if report["provenance"]["declaration_sha256"] != pipeline._sha(state["development"]):
        raise ImproverAssessmentError("finite study rebound its original declaration")
    return report, capture


def _freeze_data(
    state: dict[str, Any], report: dict[str, Any], capture: _Capture, review: dict[str, object]
) -> dict[str, Any]:
    root, directory = state["root"], state["root"] / "search/study"
    controls = dict(state["controls"])
    for path, digest in report["provenance"]["controls"].items():
        path = final._path(path)
        if path in controls and controls[path] != digest:
            raise ImproverAssessmentError("development control conflicts with original trial")
        controls[path] = digest
    for name in ("report.json", "freeze/selections.json", "freeze/confirmation.json"):
        path = directory / name
        controls[path] = final.sha(capture.read(path))
    arms: list[dict[str, Any]] = []
    slots: list[dict[str, Any]] = []
    for selected in report["selections"]:
        start, repeat, index = selected["start"], selected["repetition"], len(slots)
        starter = state["screens"][start].candidate_id
        actor = Selection.from_bytes(
            _json(state["development"]["improvers"][selected["arm"]]["selection"])
        ).agent_sha256
        common_root = directory / "common" / str(start) / str(repeat)
        common: dict[str, Any] = {
            "screen": {
                "directory": str(common_root / "screen"),
                "authorization": str(final._phase_authority(state, "search")),
                "report_sha256": final.sha(capture.read(common_root / "screen/report.json")),
            },
            "feedback": {},
        }
        controls[common_root / "screen/report.json"] = common["screen"]["report_sha256"]
        for name in ("source", "split", "feedback", "provenance"):
            path = common_root / "witness/feedback" / (name + ".json")
            digest = final.sha(capture.read(path))
            common["feedback"][name] = {"path": str(path), "sha256": digest}
            controls[path] = digest
        slot = {
            **selected,
            "improver_agent_sha256": actor,
            "starter_agent_sha256": starter,
            "common": common,
        }
        slots.append(slot)
        sources: list[tuple[str, int | None, dict[str, Any], str]] = []
        if selected["arm"] == 0:
            path = directory / "inputs/starts" / str(start) / "candidate.py"
            sources.append(
                (
                    "starter",
                    None,
                    {"path": str(path), "sha256": final.sha(capture.read(path))},
                    starter,
                )
            )
        if selected["source"] is not None:
            sources.append(
                (
                    ("initial", "evolved")[selected["arm"]],
                    index,
                    selected["source"],
                    selected["candidate_id"],
                )
            )
        for role, slot_index, ref, identity in sources:
            source = study._source_refs([ref], {})[0]
            if source["agent_sha256"] != identity:
                raise ImproverAssessmentError("frozen raw source and agent identities differ")
            controls[Path(source["path"])] = source["sha256"]
            arms.append(
                {
                    "arm_index": len(arms),
                    "role": role,
                    "role_index": start * state["development"]["repetitions"] + repeat,
                    **source,
                    "origin": source["path"],
                    "path": str(root / "freeze/sources" / (str(len(arms)) + ".py")),
                    "start": start,
                    "repetition": repeat,
                    "slot_index": slot_index,
                }
            )
    count = len(state["screens"]) * state["development"]["repetitions"]
    selected_count = sum(row["source"] is not None for row in slots)
    cells_per_arm = len(state["record"]["final_ids"]) * state["record"]["sealed_repetitions"]
    terms, snapshot = launch._snapshot(final._phase_authority(state, "final"))
    launch._finish_snapshot(final._phase_authority(state, "final"), snapshot)
    return {
        "format": _SCHEDULE,
        "directory": str(state["directory"]),
        "definition_sha256": pipeline._sha(state["definition"]),
        "development": {
            "directory": str(directory),
            "authorization": str(final._phase_authority(state, "search")),
            "report_sha256": controls[directory / "report.json"],
            "selections_sha256": controls[directory / "freeze/selections.json"],
            "confirmation_sha256": controls[directory / "freeze/confirmation.json"],
        },
        "slots": slots,
        "arms": arms,
        "selected_ids": state["record"]["final_ids"],
        "repetitions": state["record"]["sealed_repetitions"],
        "counts": {
            "cells": (count + selected_count) * cells_per_arm,
            "maximum_cells": 3 * count * cells_per_arm,
            "conditions": count,
            "descendant_slots": 2 * count,
            "no_valid_descendant_slots": 2 * count - selected_count,
        },
        "review": review,
        "controls": {str(path): pin for path, pin in controls.items()},
        "grant": study._grant(study._obj(terms["config"]), final._phase_authority(state, "final")),
    }


def _schedule(state: dict[str, Any]) -> tuple[dict[str, Any], dict[Path, str]]:
    freeze = state["root"] / "freeze"
    raw, ready_raw = pipeline._read(freeze / "schedule.json"), pipeline._read(freeze / "ready.json")
    saved, ready = (
        study._obj(_load(raw)),
        study._obj(_load(ready_raw), {"format", "schedule_sha256"}),
    )
    if ready != {"format": _READY, "schedule_sha256": final.sha(raw)} or ready_raw != _json(ready):
        raise ImproverAssessmentError("original freeze lacks exact durable confirmation")
    development = study._obj(saved["development"])
    report, capture = _development(state, _digest(development["report_sha256"]))
    expected = _freeze_data(state, report, capture, gateway._review(saved["review"]))
    if raw != _json(expected):
        raise ImproverAssessmentError("frozen grid, null slots, source roles or controls changed")
    expected_names = {"schedule.json", "ready.json", "sources"}
    if {path.name for path in freeze.iterdir()} != expected_names or {
        path.name for path in (freeze / "sources").iterdir()
    } != {str(i) + ".py" for i in range(len(expected["arms"]))}:
        raise ImproverAssessmentError("freeze contains foreign or missing source entries")
    pins = {final._path(path): digest for path, digest in expected["controls"].items()}
    for arm in expected["arms"]:
        pins[Path(arm["path"])] = arm["sha256"]
    pins |= {freeze / "schedule.json": final.sha(raw), freeze / "ready.json": final.sha(ready_raw)}
    for path, digest in pins.items():
        if final.sha(capture.read(path)) != digest:
            raise ImproverAssessmentError("frozen original input changed")
    capture.finish()
    state["development_capture"], state["development_report"] = capture, report
    return expected, pins


@_checked
def freeze_improver_descendants(
    directory: Path, *, expected_development_report_sha256: str, review: dict[str, object]
) -> dict[str, object]:
    state = _state(directory)
    checked_review = gateway._review(review)
    expected = _digest(expected_development_report_sha256)
    freeze = state["root"] / "freeze"
    if freeze.exists():
        schedule, _ = _schedule(state)
        if (
            schedule["development"]["report_sha256"] != expected
            or schedule["review"] != checked_review
        ):
            raise ImproverAssessmentError("original descendant freeze cannot be replaced")
        return schedule
    authority = Authorization(final._phase_authority(state, "final"))
    with trial_fence.lease(authority.path, authority._terms(), directory=state["directory"]):
        state = _state(directory)
        if freeze.exists():
            raise ImproverAssessmentError("first freeze was already consumed")
        report, capture = _development(state, expected)
        for phase in ("search", "validation", "final"):
            path = final._phase_authority(state, phase)
            _, snapshot = final._quiescent_funding(path, fresh=phase in {"validation", "final"})
            launch._finish_snapshot(path, snapshot)
        schedule = _freeze_data(state, report, capture, checked_review)
        study._capacity(
            state,
            schedule,
            receipts={freeze / name: "0" * 64 for name in ("schedule.json", "ready.json")}
            | {Path(arm["path"]): arm["sha256"] for arm in schedule["arms"]},
        )
        capture.finish()
        freeze.mkdir()
        (freeze / "sources").mkdir()
        for arm in schedule["arms"]:
            pipeline._write(Path(arm["path"]), pipeline._read(Path(arm["origin"]), arm["sha256"]))
        raw = _json(schedule)
        pipeline._write(freeze / "schedule.json", raw)
        if pipeline._read(freeze / "schedule.json") != raw:
            raise ImproverAssessmentError("original schedule failed durable reread")
        pipeline._write(
            freeze / "ready.json", _json({"format": _READY, "schedule_sha256": final.sha(raw)})
        )
        _schedule(state)
        return schedule


@_checked
def inspect_improver_assessment_freeze(
    directory: Path, *, expected_schedule_sha256: str
) -> dict[str, object]:
    state = _state(directory)
    schedule, _ = _schedule(state)
    if pipeline._sha(schedule) != _digest(expected_schedule_sha256):
        raise ImproverAssessmentError("wrong original schedule digest")
    state["development_capture"].finish()
    return schedule


def _restore_grid(directory: Path) -> tuple[dict[str, Any], dict[str, Any], dict[Path, str]]:
    state = _state(directory)
    schedule, pins = _schedule(state)
    return state, schedule, pins


def _analysis(
    state: dict[str, Any], schedule: dict[str, Any], reader: NativeEvidence, current: dict[str, Any]
) -> dict[str, object]:
    population = _population(state)
    artifacts = study._obj(reader.release.to_record()["artifacts"])
    projection.reporting_configuration(reader.release, state["record"]["stages"])
    families = {
        row["task_id"]: row["family_id"] for row in cast(list[dict[str, Any]], population["tasks"])
    }
    rows = []
    for arm, task_index, identifier, repeat, cell in study._cells(state, schedule):
        report, source = study._generation(state, schedule, reader, arm, identifier, cell)
        if source is None:
            raise ImproverAssessmentError("paired analysis needs the complete executable grid")
        available, _, _ = saved_native._native(
            reader, state["record"], source, study._obj(report["source_generation"]), cell, current
        )
        scalars = projection.project_rows(
            source.tasks,
            source.answers,
            reader.raw(available[artifacts["results"][0]]),
            reader.raw(available[artifacts["results"][1]]),
        )
        if (
            len(scalars) != 1
            or type(scalars[0]["task_id"]) is not type(identifier)
            or scalars[0]["task_id"] != identifier
        ):
            raise ImproverAssessmentError("official scalar changed its frozen typed task")
        scalar = scalars[0]
        rows.append(
            {
                "start": arm["start"],
                "repetition": arm["repetition"],
                "role": arm["role"],
                "task_index": task_index,
                "task_id": identifier,
                "family_id": families[identifier],
                "sealed_repetition": repeat,
                "agent_sha256": arm["agent_sha256"],
                "status": "observed",
                **{
                    axis: None if axis in study._list(scalar["invalid_metrics"]) else scalar[axis]
                    for axis in ("utility", "distinct")
                },
            }
        )
    slots = [
        {
            key: row[key]
            for key in (
                "start",
                "repetition",
                "arm",
                "starter_agent_sha256",
                "improver_agent_sha256",
                "status",
            )
        }
        | {"descendant_agent_sha256": row["candidate_id"]}
        for row in schedule["slots"]
    ]
    return improver_analysis.analyze_improver_panel(
        state["plan"], population=population, slots=slots, rows=rows, rule=state["rule"]
    )


def _result(
    state: dict[str, Any], schedule: dict[str, Any], reader: NativeEvidence, current: dict[str, Any]
) -> dict[str, object]:
    cells, generated, failed = study._collect(state, schedule, reader, current)
    if failed is not None or len(cells) != schedule["counts"]["cells"] or generated != len(cells):
        raise ImproverAssessmentError("completed report needs every original executable cell")
    return {
        "format": "buddha.improver-assessment-report.v1",
        "status": "complete",
        "definition_sha256": pipeline._sha(state["definition"]),
        "schedule_sha256": pipeline._sha(schedule),
        "selected_ids": schedule["selected_ids"],
        "slots": schedule["slots"],
        "arms": schedule["arms"],
        "coverage": {
            "expected": schedule["counts"]["cells"],
            "generated": generated,
            "evaluated": len(cells),
        },
        "cells": cells,
        "analysis": _analysis(state, schedule, reader, current),
        "development_costs": state["development_report"]["costs"],
        "authorization": current,
        "claim": _CLAIM,
    }


@_checked
def inspect_improver_assessment(
    directory: Path, *, expected_report_sha256: str
) -> dict[str, object]:
    state, schedule, pins = _restore_grid(directory)
    reader, current = final._census(state, schedule, pins)
    result = _result(state, schedule, reader, current)
    raw = reader.raw(state["directory"] / "report.json", _digest(expected_report_sha256))
    saved = _load(raw)
    pipeline.validate_authorization_snapshot(
        saved["authorization"], current, {owner.run_id for owner in reader.owners.values()}
    )
    if raw != _json(result | {"authorization": saved["authorization"]}):
        raise ImproverAssessmentError(
            "original complete report differs from original native evidence"
        )
    reader.finish()
    return saved


@_checked
def run_improver_assessment(
    directory: Path,
    *,
    authorization: Authorization,
    review: dict[str, object],
    transport: gateway.RawHTTPTransport,
) -> dict[str, object]:
    return final._run_grid(
        directory,
        authorization=authorization,
        review=review,
        transport=transport,
        restore=_restore_grid,
        build_result=_result,
        inspect_result=lambda path, digest: inspect_improver_assessment(
            path, expected_report_sha256=digest
        ),
    )
