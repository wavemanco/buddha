"""One prospectively frozen complete final grid; no source adoption or ranking.

Task source is trusted-host data. Candidate source runs only through the existing
confined generation/native APIs. Final evidence never becomes adaptive feedback.
"""

import hashlib
import re
from collections.abc import Callable, Sequence
from contextlib import AbstractContextManager
from fractions import Fraction
from functools import wraps
from pathlib import Path
from typing import Any, cast

from buddha import candidate_generation, gateway, native_evaluation, trial_fence
from buddha import launch_common as launch
from buddha import native_pipeline as pipeline
from buddha import noveltybench_results as projection
from buddha import source_screen_results as saved_native
from buddha import validation_analysis as analysis
from buddha import validation_study as study
from buddha.answers import _id
from buddha.authorization import Authorization
from buddha.doctor import _authority
from buddha.improvement_rule import evaluate_improvement_rule
from buddha.native_evidence import NativeEvidence, authority_observation
from buddha.releases import (
    Release,
    ReleaseError,
    Selection,
    _digest,
    _json,
    _load,
    _text,
    file_hash,
)
from buddha.wire import _integer

FORMAT = "buddha.evaluation-trial.v1"
POLICY = {
    "method": "explicit_ordered_finalists",
    "eligible_pool": "complete-original-validation-candidates",
}
CLAIM = "One frozen fixed-panel final comparison; no ranking, promotion or unseen-task claim."


class FinalEvaluationError(ReleaseError):
    """Original prospective trial, freeze, grid or native evidence is invalid."""


def _checked[**P, T](function: Callable[P, T]) -> Callable[P, T]:
    @wraps(function)
    def checked(*args: P.args, **kwargs: P.kwargs) -> T:
        try:
            return function(*args, **kwargs)
        except (ValueError, TypeError, KeyError, OSError, RecursionError, OverflowError) as error:
            if isinstance(error, FinalEvaluationError):
                raise
            raise FinalEvaluationError(
                "original final trial or execution evidence is invalid"
            ) from None

    return checked


def _source_hashes() -> dict[str, str]:
    paths = {**analysis._source_paths(), "buddha/final_evaluation.py": Path(__file__).absolute()}
    return {name: file_hash(path) for name, path in paths.items()}


def _path(value: object) -> Path:
    return trial_fence._checked_path(value)


def _definition(raw: bytes, runtime: str) -> dict[str, Any]:
    record = study._obj(
        _load(raw),
        {
            "format",
            "experiment_id",
            "validation",
            "final_ids",
            "finalist_count",
            "finalist_policy",
            "search_purpose",
            "phase_limits",
            "consumer_sources",
        },
    )
    if record["format"] != FORMAT or record["finalist_policy"] != POLICY:
        raise FinalEvaluationError("unsupported explicit prospective finalist policy")
    _text(record["experiment_id"])
    _text(record["search_purpose"])
    controls: dict[Path, str] = {}
    validation = study._ref(record["validation"], controls)
    original = pipeline._read(Path(validation["path"]), validation["sha256"])
    state = study._definition(original, _digest(runtime))
    count = _integer(record["finalist_count"], 1)
    selected = [_id(item) for item in study._list(record["final_ids"])]
    population = {row["task_id"]: row for row in state["custody"]["population"]}
    expected = {key for key, member in population.items() if member["phase"] == "final"}
    disclosed = {
        row["task_id"]
        for row in state["custody"]["disclosures"]
        if row["process_id"] == state["custody"]["process_id"]
    }
    if (
        not selected
        or len(set(selected)) != len(selected)
        or set(selected) != expected
        or any(population[key]["exposure"] != "eligible" or key in disclosed for key in selected)
    ):
        raise FinalEvaluationError(
            "final schedule must include every eligible assigned final member"
        )
    plan = analysis.ValidationAnalysisPlan.from_bytes(
        pipeline._read(Path(state["record"]["analysis_plan"]["path"]))
    )
    method = plan.to_record()
    counts = {key: state["record"][key] for key in ("max_looks", "max_candidates", "repetitions")}
    counts.update(finalist_count=count, comparator_count=len(state["comparators"]))
    if any(method[key] != value for key, value in counts.items()) or (
        method["improvement_rule_sha256"] != state["rule"].fingerprint()
        or method["projection_release_sha256"] != state["tasks"].release_sha256
        or method["analyzer_sources"] != analysis._source_hashes()
        or record["consumer_sources"] != _source_hashes()
    ):
        raise FinalEvaluationError("trial changes prospective method, rule or consumed sources")
    limits = study._obj(record["phase_limits"], {"search", "validation", "final"})
    for value in limits.values():
        row = study._obj(value, {"budget_microusd", "max_calls"})
        for amount in row.values():
            _integer(amount, 1)
    controls.update(state["controls"])
    controls[Path(validation["path"])] = validation["sha256"]
    for name, digest in record["consumer_sources"].items():
        path = Path(__file__).absolute().parent.parent / name
        if file_hash(path) != digest:
            raise FinalEvaluationError("prospective final helper source changed")
        controls[path] = digest
    return state | {"definition": record, "plan": plan, "controls": controls}


def _purposes(record: dict[str, Any], identity: str, validation: dict[str, Any]) -> dict[str, str]:
    return {
        "search": record["search_purpose"],
        "validation": "validation study: " + pipeline._sha(validation),
        "final": "final evaluation: " + identity,
    }


def _prepare_trial_root(
    directory: Path,
    *,
    declaration: Path,
    expected_sha256: str,
    expected_runtime_sha256: str,
    state: dict[str, Any],
    authorizations: dict[str, Authorization],
    purposes: dict[str, str],
    context_format: str,
    extra_context: dict[str, object] | None = None,
) -> Path:
    """Shared original three-phase reserve/root publication, before any lower owner."""
    record = state["definition"]
    identity = pipeline._sha(record)
    if type(authorizations) is not dict or set(authorizations) != {"search", "validation", "final"}:
        raise FinalEvaluationError("one explicit original grant per phase is required")
    phases, originals = {}, dict(state["controls"])
    originals[declaration] = _digest(expected_sha256)
    protected = [
        *originals,
        *state.get("protected", []),
        *[Path(value) for value in state["record"]["generation"]["roots"].values()],
        *[Path(value) for value in state["record"]["native"]["roots"].values()],
    ]
    for phase, authority in authorizations.items():
        if not isinstance(authority, Authorization):
            raise FinalEvaluationError("phase funding must be an original Authorization")
        funding, before = launch._snapshot(authority.path)
        terms = study._obj(funding["config"])
        expected_scope = trial_fence._scope_text(
            trial_fence._TrialScope(directory, identity, phase)
        )
        if (
            terms["scope"] != expected_scope
            or any(terms[key] != value for key, value in record["phase_limits"][phase].items())
            or funding["auth_runs"]
            or funding["auth_operations"]
            or funding["auth_deactivations"]
        ):
            raise FinalEvaluationError("original phase reserve is changed, used or foreign")
        phases[phase] = {
            "authorization_path": str(authority.path),
            "purpose": purposes[phase],
            **{
                key: terms[key]
                for key in (
                    "authorization_id",
                    "terms_sha256",
                    "budget_microusd",
                    "max_calls",
                    "scope",
                )
            },
        }
        launch._finish_snapshot(authority.path, before)
        protected.append(authority.path)
    if len({row["authorization_path"] for row in phases.values()}) != 3:
        raise FinalEvaluationError("phase grants must be distinct original reserves")
    if directory.exists() or any(
        path.is_relative_to(directory) or directory.is_relative_to(path) for path in protected
    ):
        raise FinalEvaluationError("new trial overlaps original controls or funding")
    funding = {
        "format": "buddha.evaluation-trial-funding.v1",
        "root": str(directory),
        "definition_sha256": identity,
        "total_budget_microusd": sum(row["budget_microusd"] for row in phases.values()),
        "total_max_calls": sum(row["max_calls"] for row in phases.values()),
        "phases": phases,
    }
    for key in ("total_budget_microusd", "total_max_calls"):
        _integer(funding[key], 1)
    context: dict[str, Any] = {
        "format": context_format,
        "external_declaration": {"path": str(declaration), "sha256": expected_sha256},
        "expected_runtime_sha256": expected_runtime_sha256,
        "controls": {str(path): pin for path, pin in originals.items()},
        "host_core": gateway._core_sources(),
        "host_runtime": gateway._runtime(),
    }
    if extra_context is not None:
        if set(extra_context) & set(context):
            raise FinalEvaluationError("extra trial context conflicts with fixed fields")
        context.update(extra_context)
    marker = {
        "format": "buddha.evaluation-trial-root.v1",
        "root": str(directory),
        "definition_sha256": identity,
        "funding_sha256": pipeline._sha(funding),
    }
    directory.mkdir()
    # Missing dependencies keep the first marker poisoned until fixed files exist.
    pipeline._write(directory / ".buddha-evaluation-trial.json", _json(marker))
    pipeline._write(directory / "definition.json", _json(record))
    pipeline._write(directory / "context.json", _json(context))
    for phase in phases:
        (directory / phase).mkdir()
    pipeline._write(directory / "funding.json", _json(funding))
    return directory


@_checked
def prepare_evaluation_trial(
    directory: Path,
    *,
    declaration: Path,
    expected_sha256: str,
    expected_runtime_sha256: str,
    authorizations: dict[str, Authorization],
) -> Path:
    directory, declaration = _path(directory), _path(declaration)
    raw = pipeline._read(declaration, _digest(expected_sha256))
    state = _definition(raw, expected_runtime_sha256)
    record = state["definition"]
    identity = pipeline._sha(record)
    _prepare_trial_root(
        directory,
        declaration=declaration,
        expected_sha256=expected_sha256,
        expected_runtime_sha256=expected_runtime_sha256,
        state=state,
        authorizations=authorizations,
        purposes=_purposes(record, identity, state["record"]),
        context_format="buddha.evaluation-trial-context.v1",
    )
    study.prepare_validation_study(
        directory / "validation/study",
        declaration=Path(record["validation"]["path"]),
        expected_sha256=record["validation"]["sha256"],
        expected_runtime_sha256=expected_runtime_sha256,
        authorization=authorizations["validation"],
    )
    return directory


def _state(directory: Path) -> dict[str, Any]:
    directory = _path(directory)
    fixed = trial_fence.required_controls(directory / "final")
    context = study._obj(
        _load(pipeline._read(directory / "context.json")),
        {
            "format",
            "external_declaration",
            "expected_runtime_sha256",
            "controls",
            "host_core",
            "host_runtime",
        },
    )
    if context["format"] != "buddha.evaluation-trial-context.v1":
        raise FinalEvaluationError("unsupported original trial context")
    state = _definition(
        pipeline._read(directory / "definition.json"), context["expected_runtime_sha256"]
    )
    external = study._obj(context["external_declaration"], {"path", "sha256"})
    if _json(_load(pipeline._read(Path(external["path"]), external["sha256"]))) != _json(
        state["definition"]
    ):
        raise FinalEvaluationError("original raw declaration changed")
    expected = state["controls"] | {Path(external["path"]): external["sha256"]}
    if context["controls"] != {str(path): pin for path, pin in expected.items()}:
        raise FinalEvaluationError("original trial controls changed")
    for path, digest in expected.items():
        pipeline._read(path, digest)
    funding = study._obj(_load(pipeline._read(directory / "funding.json")))
    purposes = _purposes(state["definition"], pipeline._sha(state["definition"]), state["record"])
    for phase, row in funding["phases"].items():
        if row["purpose"] != purposes[phase] or any(
            row[key] != value for key, value in state["definition"]["phase_limits"][phase].items()
        ):
            raise FinalEvaluationError("funding changed original phase purposes or limits")
    state.update(root=directory, directory=directory / "final", context=context, funding=funding)
    state["controls"] = expected | fixed | {directory / "context.json": pipeline._sha(context)}
    return state


def _phase_authority(state: dict[str, Any], phase: str) -> Path:
    return _path(state["funding"]["phases"][phase]["authorization_path"])


def _quiescent_funding(path: Path, *, fresh: bool = False) -> tuple[dict[str, object], bytes]:
    """Check a financial snapshot; caller joins its publication before finishing it."""
    funding, raw = launch._snapshot(path)
    inactive = {row["run_id"] for row in study._list(funding["auth_deactivations"])}
    if (
        any(row["run_id"] not in inactive for row in study._list(funding["auth_runs"]))
        or any(row["status"] != "completed" for row in study._list(funding["auth_operations"]))
        or (fresh and (funding["auth_runs"] or funding["auth_operations"] or inactive))
    ):
        raise FinalEvaluationError(
            "freeze cannot strand unfinished work or consume used final funding"
        )
    return funding, raw


def _quiescent(state: dict[str, Any], phase: str, *, fresh: bool = False) -> None:
    path = _phase_authority(state, phase)
    funding, raw = _quiescent_funding(path, fresh=fresh)
    if phase == "search" and funding["auth_runs"]:
        from buddha import source_search

        searches = []
        for manifest in (state["root"] / "search").rglob("manifest.json"):
            value = _load(pipeline._read(manifest))
            if str(value.get("format", "")).startswith("buddha.source-search-manifest."):
                searches.append(manifest.parent)
        if len(searches) != 1:
            raise FinalEvaluationError(
                "funded search needs its one complete original search publication"
            )
        source_search.inspect_source_search(
            searches[0],
            authorization=path,
            expected_report_sha256=file_hash(searches[0] / "report.json"),
        )
    launch._finish_snapshot(path, raw)


def _validation_pool(
    state: dict[str, Any],
    results: object,
) -> tuple[dict[str, dict[str, Any]], dict[Path, str]]:
    validation = study._state(state["root"] / "validation/study")
    slots = study._slots(validation)
    reader, current = study._census(validation, slots, _phase_authority(state, "validation"))
    complete = study._saved_results(validation, slots, reader, current)
    refs = study._list(results)
    expected = [
        {
            "ordinal": ordinal,
            "result_sha256": file_hash(
                validation["directory"] / "validation" / str(ordinal) / "result.json"
            ),
        }
        for ordinal in sorted(complete)
    ]
    if _json(refs) != _json(expected) or not refs:
        raise FinalEvaluationError("freeze needs every complete original validation publication")
    eligible, controls = {}, dict(validation["controls"])
    for occasion in slots:
        if occasion["ordinal"] not in complete:
            _, _, failed = study._collect(validation, occasion, reader, current)
            if failed is None:
                raise FinalEvaluationError("freeze cannot bypass unfinished original validation")
            continue
        for arm in occasion["arms"]:
            if arm["role"] == "candidate":
                eligible[arm["agent_sha256"]] = arm
        path = validation["directory"] / "validation" / str(occasion["ordinal"]) / "result.json"
        controls[path] = file_hash(path)
    reader.finish()
    state["validation_capture"] = reader.capture
    return eligible, controls


def _schedule(state: dict[str, Any]) -> tuple[dict[str, Any], dict[Path, str]]:
    root = state["root"]
    schedule_raw = pipeline._read(root / "freeze/schedule.json")
    schedule = study._obj(
        _load(schedule_raw),
        {
            "format",
            "directory",
            "definition_sha256",
            "finalist_refs",
            "validation_results",
            "arms",
            "selected_ids",
            "repetitions",
            "counts",
            "review",
            "controls",
            "grant",
        },
    )
    gateway._review(schedule["review"])
    _integer(schedule["repetitions"], 1)
    _integer(study._obj(schedule["counts"], {"cells"})["cells"], 1)
    ready_raw = pipeline._read(root / "freeze/ready.json")
    ready = {"format": "buddha.final-freeze-ready.v1", "schedule_sha256": sha(schedule_raw)}
    if (
        ready_raw != _json(ready)
        or schedule_raw != _json(schedule)
        or (
            schedule["format"] != "buddha.final-schedule.v1"
            or schedule["directory"] != str(root / "final")
            or schedule["definition_sha256"] != pipeline._sha(state["definition"])
            or _json(schedule["selected_ids"]) != _json(state["definition"]["final_ids"])
            or schedule["repetitions"] != state["record"]["repetitions"]
        )
    ):
        raise FinalEvaluationError("original final freeze lacks exact positive confirmation")
    eligible, original = _validation_pool(state, schedule["validation_results"])
    expected_refs = study._source_refs(
        [
            {
                key: study._obj(ref, {"path", "sha256", "agent_sha256"})[key]
                for key in ("path", "sha256")
            }
            for ref in study._list(schedule["finalist_refs"])
        ],
        {},
    )
    if expected_refs != schedule["finalist_refs"]:
        raise FinalEvaluationError("frozen finalist fingerprint changed")
    if len(expected_refs) != state["definition"]["finalist_count"] or any(
        ref["agent_sha256"] not in eligible for ref in expected_refs
    ):
        raise FinalEvaluationError("frozen finalist is not in its original permitted pool")
    for ref in expected_refs:
        if ref["sha256"] != eligible[ref["agent_sha256"]]["sha256"]:
            raise FinalEvaluationError("frozen finalist changes its original source")
    arms: list[dict[str, Any]] = []
    for role, refs in (("comparator", state["comparators"]), ("candidate", expected_refs)):
        for index, ref in enumerate(refs):
            path = root / "freeze/sources" / (str(len(arms)) + ".py")
            pipeline._read(path, ref["sha256"])
            arms.append(
                {
                    "arm_index": len(arms),
                    "role": role,
                    "role_index": index,
                    **ref,
                    "path": str(path),
                    "origin": ref["path"],
                }
            )
    common = state["controls"] | original
    for ref in [*state["comparators"], *expected_refs]:
        common[Path(ref["path"])] = ref["sha256"]
    if _json(schedule["arms"]) != _json(arms) or schedule["controls"] != {
        str(path): pin for path, pin in common.items()
    }:
        raise FinalEvaluationError("frozen sources or original controls changed")
    count = len(arms) * len(schedule["selected_ids"]) * schedule["repetitions"]
    if schedule["counts"] != {"cells": count} or _json(schedule["grant"]) != _json(
        study._grant(
            study._obj(launch._snapshot(_phase_authority(state, "final"))[0]["config"]),
            _phase_authority(state, "final"),
        )
    ):
        raise FinalEvaluationError("final schedule coverage or original grant changed")
    pins = common | {
        root / "freeze/schedule.json": sha(schedule_raw),
        root / "freeze/ready.json": sha(ready_raw),
    }
    for path, digest in pins.items():
        pipeline._read(path, digest)
    return schedule, pins


def sha(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()


@_checked
def freeze_finalists(
    directory: Path,
    *,
    finalist_refs: Sequence[dict[str, str]],
    validation_results: list[dict[str, object]],
    review: dict[str, object],
) -> dict[str, object]:
    state = _state(directory)
    authority = Authorization(_phase_authority(state, "final"))
    checked_review = gateway._review(review)
    refs = study._source_refs(list(finalist_refs), {})
    if (state["root"] / "freeze").exists():
        schedule, _ = _schedule(state)
        if (
            schedule["finalist_refs"] != refs
            or schedule["validation_results"] != validation_results
            or schedule["review"] != checked_review
        ):
            raise FinalEvaluationError("final identities cannot be reselected")
        return schedule
    with trial_fence.lease(authority.path, authority._terms(), directory=state["root"] / "final"):
        state = _state(directory)
        if (state["root"] / "freeze").exists():
            raise FinalEvaluationError("a freeze was already consumed")
        eligible, original = _validation_pool(state, validation_results)
        if len(refs) != state["definition"]["finalist_count"] or any(
            ref["agent_sha256"] not in eligible for ref in refs
        ):
            raise FinalEvaluationError("exactly F unique original eligible finalists are required")
        for phase in ("search", "validation", "final"):
            _quiescent(state, phase, fresh=phase == "final")
        common = state["controls"] | original
        arms: list[dict[str, Any]] = []
        for role, sources in (("comparator", state["comparators"]), ("candidate", refs)):
            for index, source in enumerate(sources):
                common[Path(source["path"])] = source["sha256"]
                arms.append(
                    {
                        "arm_index": len(arms),
                        "role": role,
                        "role_index": index,
                        **source,
                        "origin": source["path"],
                        "path": str(state["root"] / "freeze/sources" / (str(len(arms)) + ".py")),
                    }
                )
        schedule = {
            "format": "buddha.final-schedule.v1",
            "directory": str(state["root"] / "final"),
            "definition_sha256": pipeline._sha(state["definition"]),
            "finalist_refs": refs,
            "validation_results": validation_results,
            "arms": arms,
            "selected_ids": state["definition"]["final_ids"],
            "repetitions": state["record"]["repetitions"],
            "counts": {
                "cells": len(arms)
                * len(state["definition"]["final_ids"])
                * state["record"]["repetitions"]
            },
            "review": checked_review,
            "controls": {str(path): pin for path, pin in common.items()},
            "grant": study._grant(
                study._obj(launch._snapshot(authority.path)[0]["config"]), authority.path
            ),
        }
        for value in schedule["counts"].values():
            _integer(value, 1)
        receipt_paths = {
            state["root"] / "freeze" / name: "0" * 64 for name in ("schedule.json", "ready.json")
        }
        study._capacity(state, schedule, receipts=receipt_paths)
        freeze = state["root"] / "freeze"
        freeze.mkdir()
        (freeze / "sources").mkdir()
        for arm in arms:
            pipeline._write(Path(arm["path"]), pipeline._read(Path(arm["origin"]), arm["sha256"]))
        raw = _json(schedule)
        pipeline._write(freeze / "schedule.json", raw)
        if pipeline._read(freeze / "schedule.json") != raw:
            raise FinalEvaluationError("original freeze failed durable reread")
        pipeline._write(
            freeze / "ready.json",
            _json(
                {
                    "format": "buddha.final-freeze-ready.v1",
                    "schedule_sha256": sha(raw),
                }
            ),
        )
        _schedule(state)
        return schedule


def _census(
    state: dict[str, Any], occasion: dict[str, Any], pins: dict[Path, str]
) -> tuple[NativeEvidence, dict[str, Any]]:
    authority = _phase_authority(state, "final")
    reader = NativeEvidence(state["directory"], authority, error_type=FinalEvaluationError)
    if state.get("development_capture") is not None:
        reader.retain_capture(state["development_capture"])
    if state.get("validation_capture") is not None:
        reader.retain_capture(state["validation_capture"])
    owners, positions, touched = [], set(), set()
    stages = len(state["record"]["stages"])
    pattern = re.compile(
        r"arms/(0|[1-9][0-9]*)/tasks/(0|[1-9][0-9]*)/repetitions/(0|[1-9][0-9]*)/(generation|evaluation)/owners/(0|[1-9][0-9]*)"
    )
    for name in reader.capture.entries:
        child = re.fullmatch(
            r"arms/([^/]+)/tasks/([^/]+)/repetitions/([^/]+)/(generation|evaluation)", name
        )
        if child is not None:
            a, t, r, role = child.groups()
            if not all(re.fullmatch(r"0|[1-9][0-9]*", value) for value in (a, t, r)):
                raise FinalEvaluationError("final child has noncanonical grid indices")
            arm, task, repeat = map(int, (a, t, r))
            if (
                arm >= len(occasion["arms"])
                or task >= len(occasion["selected_ids"])
                or repeat >= occasion["repetitions"]
            ):
                raise FinalEvaluationError("child is outside the full frozen final grid")
            first = "0" if role == "generation" else "1"
            if name + "/owners/" + first + "/manifest.json" not in reader.capture.entries:
                raise FinalEvaluationError("final child has no original first owner")
        if "/owners/" not in name:
            continue
        prefix = (
            name.split("/owners/", 1)[0] + "/owners/" + name.split("/owners/", 1)[1].split("/")[0]
        )
        match = pattern.fullmatch(prefix)
        if match is None:
            raise FinalEvaluationError("foreign or orphan final owner")
        a, t, r, role, s = match.groups()
        arm, task, repeat, stage = map(int, (a, t, r, s))
        if (
            arm >= len(occasion["arms"])
            or task >= len(occasion["selected_ids"])
            or repeat >= occasion["repetitions"]
            or (role == "generation" and stage != 0)
            or (role == "evaluation" and not 1 <= stage <= stages)
        ):
            raise FinalEvaluationError("owner is outside the full frozen final grid")
        if prefix + "/manifest.json" not in reader.capture.entries:
            raise FinalEvaluationError("retained final owner lost its original manifest")
        if name != prefix + "/manifest.json":
            continue
        owner = reader.owner(reader.root / prefix)
        bindings = reader._bindings(owner)
        if any(bindings.get(str(path)) != pin for path, pin in pins.items()):
            raise FinalEvaluationError("final owner omitted or changed frozen controls")
        if (
            owner.manifest["core"] != state["context"]["host_core"]
            or owner.manifest["runtime"] != state["context"]["host_runtime"]
        ):
            raise FinalEvaluationError("final owner changes the original host execution closure")
        owners.append(owner)
        touched.add((arm, task, repeat))
        positions.add(
            ((arm * len(occasion["selected_ids"]) + task) * occasion["repetitions"] + repeat)
            * (stages + 1)
            + stage
        )
    if positions != set(range(len(positions))):
        raise FinalEvaluationError("final owner grid skipped its original serial predecessor")
    funded = _authority(reader.capture, authority, owners)
    if funded is None:
        raise FinalEvaluationError("final owners lack their original authority")
    reader.funded = funded
    current = cast(dict[str, Any], authority_observation(reader.capture, authority, funded))
    if occasion["grant"] != study._grant(current, authority):
        raise FinalEvaluationError("final grant changed after the original freeze")
    runs = study._list(funded["auth_runs"])
    if {row["directory"] for row in runs} != {str(owner.directory) for owner in owners}:
        raise FinalEvaluationError("funded final owner is missing, replaced or foreign")
    for row in runs:
        owner = reader.owner(Path(row["directory"]))
        if row["historical"] != 0 or row["runtime_sha256"] != owner.manifest["execution_sha256"]:
            raise FinalEvaluationError("final owner was imported or changed runtime")
    reader.release = Release.from_record(state["tasks"].to_record()["release"])
    reader.template = {key: state["record"][key] for key in ("native", "stages")}
    for arm, task, repeat in sorted(touched):
        agent = occasion["arms"][arm]
        identifier = occasion["selected_ids"][task]
        cell = study._location(state, occasion, arm, task, repeat)
        study._generation_identity(state, occasion, reader, agent, identifier, cell)
        if (cell / "evaluation/owners/1") in reader.owners:
            report, source = study._generation(state, occasion, reader, agent, identifier, cell)
            if source is None:
                raise FinalEvaluationError("final native owner has no original generated C1")
            study._native_identity(state, occasion, reader, cell, report, source)
        if (
            any(other > (arm, task, repeat) for other in touched)
            and (cell / "evaluation/report.json").relative_to(reader.root).as_posix()
            not in reader.capture.entries
        ):
            raise FinalEvaluationError(
                "later final cell precedes complete original native evidence"
            )
    _partials(state, occasion, reader, current)
    return reader, current


def _position(occasion: dict[str, Any], completed: int, generated: int) -> dict[str, object]:
    """Locate the next unfinished child from the original durable serial prefix."""
    expected = _integer(occasion["counts"]["cells"], 1)
    _integer(completed, 0, expected)
    _integer(generated, completed, min(completed + 1, expected))
    if completed == expected:
        return {"stage": "publication"}
    per_arm = len(occasion["selected_ids"]) * occasion["repetitions"]
    arm, offset = divmod(completed, per_arm)
    task, repeat = divmod(offset, occasion["repetitions"])
    return {
        "arm_index": arm,
        "task_index": task,
        "repetition": repeat,
        "stage": "native" if generated > completed else "generation",
    }


def _partials(
    state: dict[str, Any],
    occasion: dict[str, Any],
    reader: NativeEvidence,
    current: dict[str, Any],
) -> list[dict[str, Any]]:
    """Join every retained observation to an actual immutable completed prefix."""
    paths = [name for name in reader.capture.entries if name.startswith("observations/")]
    expected_names = {"observations/" + str(index) + ".json" for index in range(len(paths))}
    if set(paths) != expected_names:
        raise FinalEvaluationError("final partial journal is missing or contains foreign entries")
    cells, generated, failed = study._collect(state, occasion, reader, current)
    result = []
    for index in range(len(paths)):
        raw = reader.raw(reader.root / "observations" / (str(index) + ".json"))
        saved = study._obj(
            _load(raw),
            {
                "format",
                "status",
                "reason",
                "position",
                "cells",
                "coverage",
                "failed_generation",
                "authorization",
                "schedule_sha256",
                "claim",
                "child_observation",
            },
        )
        prefix = study._list(saved["cells"])
        coverage = study._obj(saved["coverage"], {"expected", "generated", "evaluated"})
        size = len(prefix)
        count = _integer(coverage["generated"], size, size + 1)
        if (
            raw != _json(saved)
            or saved["format"] != "buddha.final-evaluation-partial.v1"
            or saved["status"] != "incomplete"
            or saved["claim"] != CLAIM
            or saved["schedule_sha256"] != pipeline._sha(occasion)
            or prefix != cells[:size]
            or size > len(cells)
            or count > generated
            or coverage["expected"] != occasion["counts"]["cells"]
            or coverage["evaluated"] != size
            or saved["reason"]
            not in {
                "cancelled",
                "protocol",
                "authority",
                "unknown",
                "native_error",
                "candidate_execution_failed",
            }
        ):
            raise FinalEvaluationError("retained final partial changes its original prefix")
        position = _position(occasion, size, count)
        failure = saved["failed_generation"]
        if saved["position"] != position or (
            saved["reason"] == "candidate_execution_failed" and failure is None
        ):
            raise FinalEvaluationError(
                "retained final partial changes its original position or failure"
            )
        if failure is not None:
            if (
                saved["reason"] not in {"candidate_execution_failed", "cancelled", "protocol"}
                or position["stage"] != "generation"
                or failed is None
                or _json(failure) != _json(failed)
            ):
                raise FinalEvaluationError("retained final partial changes checked failure")
            arm = cast(int, position["arm_index"])
            task = cast(int, position["task_index"])
            identity = study._identity(
                occasion["arms"][arm],
                task,
                occasion["selected_ids"][task],
                cast(int, position["repetition"]),
            )
            if _json(failure) != _json(identity | {"generation": failed["generation"]}):
                raise FinalEvaluationError("checked failure is outside the saved final prefix")
        child = saved["child_observation"]
        if child is not None:
            if position["stage"] == "publication" or failure is not None:
                raise FinalEvaluationError("final stop cannot name a completed child")
            ref = study._obj(child, {"path", "sha256"})
            child_path = _path(ref["path"])
            cell = study._location(
                state,
                occasion,
                cast(int, position["arm_index"]),
                cast(int, position["task_index"]),
                cast(int, position["repetition"]),
            )
            expected_parent = (
                cell
                / ("evaluation" if position["stage"] == "native" else "generation")
                / "observations"
            )
            if child_path.parent != expected_parent or not re.fullmatch(
                r"(0|[1-9][0-9]*)\.json", child_path.name
            ):
                raise FinalEvaluationError("final partial substitutes another child observation")
            record = _load(reader.raw(child_path, ref["sha256"]))
            if record["status"] != "incomplete" or record["reason"] != saved["reason"]:
                raise FinalEvaluationError("final partial changes the exact child reason")
        elif saved["reason"] in {"unknown", "authority", "native_error"}:
            raise FinalEvaluationError("final child stop lacks its original saved observation")
        pipeline.validate_authorization_snapshot(saved["authorization"], current, set())
        result.append(saved)
    return result


def _episode(
    state: dict[str, Any],
    occasion: dict[str, Any],
    pins: dict[Path, str],
    reader: NativeEvidence,
    cell: Path,
    kind: str,
    generation: dict[str, Any],
    descriptor: Path,
) -> AbstractContextManager[None]:
    selected = Selection.from_bytes(_json(generation["selection"]))
    roots = {key: Path(value) for key, value in generation["roots"].items()}
    role_root = cell / ("generation" if kind == "generation" else "evaluation")
    common = pins | {
        cell / "task.json": file_hash(cell / "task.json"),
        cell / "generation.json": file_hash(cell / "generation.json"),
    }
    if kind == "native":
        common[descriptor] = file_hash(descriptor)
    contract = {
        "directory": str(role_root),
        "kind": kind,
        "controls": {str(path): pin for path, pin in common.items()},
        "descriptor_path": str(descriptor),
        "descriptor_sha256": file_hash(descriptor),
        "runtime_sha256": state["runtime"],
        "stage_count": len(state["record"]["stages"]),
        "owner": {
            "selection": selected.to_record(),
            "roots": generation["roots"],
            "settings": {key: generation[key] for key in ("budget_microusd", "max_calls")},
            "review": occasion["review"],
            "profiles": gateway._profiles(selected, roots),
            "core": state["context"]["host_core"],
            "runtime": state["context"]["host_runtime"],
        },
    }
    authority = Authorization(_phase_authority(state, "final"))
    return trial_fence._final_episode(
        authority.path,
        authority._terms(),
        cell=contract,
        owners={
            owner.directory: owner.manifest
            for owner in reader.owners.values()
            if owner.directory.is_relative_to(role_root)
        },
    )


def _analysis(
    state: dict[str, Any], occasion: dict[str, Any], reader: NativeEvidence, current: dict[str, Any]
) -> dict[str, object]:
    matrix, spans = [], {axis: Fraction() for axis in ("utility", "distinct")}
    artifacts = study._obj(reader.release.to_record()["artifacts"])
    projection.reporting_configuration(reader.release, state["record"]["stages"])
    custody = {row["task_id"]: row for row in state["custody"]["population"]}
    for arm, index, identifier, repeat, cell in study._cells(state, occasion):
        report, source = study._generation(state, occasion, reader, arm, identifier, cell)
        if source is None:
            raise FinalEvaluationError("final matrix has a failed required generation")
        available, _, _ = saved_native._native(
            reader, state["record"], source, study._obj(report["source_generation"]), cell, current
        )
        rows = projection.project_rows(
            source.tasks,
            source.answers,
            reader.raw(available[artifacts["results"][0]]),
            reader.raw(available[artifacts["results"][1]]),
        )
        if len(rows) != 1 or rows[0]["task_id"] != identifier:
            raise FinalEvaluationError("final scalar projection changes the frozen task grid")
        for axis, (low, high) in projection.metric_support(source.tasks.tasks[0].count).items():
            spans[axis] = max(spans[axis], Fraction(high - low))
        matrix.append(
            rows[0]
            | {
                "arm_index": arm["arm_index"],
                "task_index": index,
                "repetition": repeat,
                "family_id": custody[identifier]["family_id"],
            }
        )
    if len(matrix) != occasion["counts"]["cells"]:
        raise FinalEvaluationError("final analysis cannot drop any frozen cell")
    tail = analysis._tails(state["plan"].to_record())["final"]
    contrasts = []
    for candidate in occasion["arms"]:
        if candidate["role"] != "candidate":
            continue
        for comparator in occasion["arms"]:
            if comparator["role"] != "comparator":
                continue
            aggregate = analysis._aggregate_contrast(
                matrix,
                candidate_arm=candidate["arm_index"],
                comparator_arm=comparator["arm_index"],
                repetitions=occasion["repetitions"],
            )
            axes = {}
            for axis in spans:
                point = aggregate["points"][axis]
                axes[axis] = (
                    {
                        "status": "unavailable",
                        "lower_bound": None,
                        "reason": "required_native_scalar_missing",
                        "tail": analysis._ratio(tail),
                    }
                    if point is None
                    else analysis._hoeffding_lower_bound(
                        point,
                        span=spans[axis],
                        squared_weight_sum=aggregate["squared_weight_sum"],
                        tail=tail,
                    )
                )
            contrasts.append(
                {
                    "candidate_arm": candidate["arm_index"],
                    "comparator_arm": comparator["arm_index"],
                    "axes": axes,
                    "rule": evaluate_improvement_rule(
                        state["rule"],
                        lower_bounds={axis: axes[axis]["lower_bound"] for axis in spans},
                        complete_coverage=aggregate["complete"],
                    ),
                }
            )
    return {
        "matrix": matrix,
        "contrasts": contrasts,
        "allocation": {
            key: analysis._ratio(value)
            for key, value in analysis._tails(state["plan"].to_record()).items()
        },
    }


def _result(
    state: dict[str, Any], occasion: dict[str, Any], reader: NativeEvidence, current: dict[str, Any]
) -> dict[str, object]:
    cells, generated, failed = study._collect(state, occasion, reader, current)
    expected = occasion["counts"]["cells"]
    if failed is not None or len(cells) != expected or generated != expected:
        raise FinalEvaluationError("final publication needs every frozen original cell")
    return {
        "format": "buddha.final-evaluation-report.v1",
        "status": "complete",
        "definition_sha256": pipeline._sha(state["definition"]),
        "schedule_sha256": pipeline._sha(occasion),
        "selected_ids": occasion["selected_ids"],
        "arms": occasion["arms"],
        "coverage": {"expected": expected, "generated": generated, "evaluated": len(cells)},
        "cells": cells,
        "analysis": _analysis(state, occasion, reader, current),
        "authorization": current,
        "claim": CLAIM,
    }


@_checked
def _read_final_evaluation(
    directory: Path, *, expected_report_sha256: str
) -> tuple[dict[str, object], dict[str, Any], dict[str, Any], NativeEvidence]:
    """Retain the checked observation for a passive downstream consumer."""
    state = _state(directory)
    occasion, pins = _schedule(state)
    reader, current = _census(state, occasion, pins)
    expected = _result(state, occasion, reader, current)
    raw = reader.raw(state["directory"] / "report.json", _digest(expected_report_sha256))
    saved = _load(raw)
    pipeline.validate_authorization_snapshot(
        saved["authorization"], current, {owner.run_id for owner in reader.owners.values()}
    )
    if raw != _json(expected | {"authorization": saved["authorization"]}):
        raise FinalEvaluationError("saved final publication contradicts complete original evidence")
    reader.finish()
    return saved, state, occasion, reader


def inspect_final_evaluation(directory: Path, *, expected_report_sha256: str) -> dict[str, object]:
    return _read_final_evaluation(directory, expected_report_sha256=expected_report_sha256)[0]


def _restore_grid(directory: Path) -> tuple[dict[str, Any], dict[str, Any], dict[Path, str]]:
    state = _state(directory)
    occasion, pins = _schedule(state)
    return state, occasion, pins


@_checked
def run_final_evaluation(
    directory: Path,
    *,
    authorization: Authorization,
    review: dict[str, object],
    transport: gateway.RawHTTPTransport,
) -> dict[str, object]:
    return _run_grid(
        directory,
        authorization=authorization,
        review=review,
        transport=transport,
        restore=_restore_grid,
        build_result=_result,
        inspect_result=lambda path, digest: inspect_final_evaluation(
            path, expected_report_sha256=digest
        ),
    )


def _run_grid(
    directory: Path,
    *,
    authorization: Authorization,
    review: dict[str, object],
    transport: gateway.RawHTTPTransport,
    restore: Callable[[Path], tuple[dict[str, Any], dict[str, Any], dict[Path, str]]],
    build_result: Callable[
        [dict[str, Any], dict[str, Any], NativeEvidence, dict[str, Any]], dict[str, object]
    ],
    inspect_result: Callable[[Path, str], dict[str, object]],
) -> dict[str, object]:
    """Two trusted scientific consumers share the unchanged physical execution protocol."""
    if not isinstance(authorization, Authorization) or not isinstance(
        transport, gateway.RawHTTPTransport
    ):
        raise FinalEvaluationError(
            "final execution needs explicit original authorization and transport"
        )
    state, occasion, pins = restore(directory)
    if (
        authorization.path != _phase_authority(state, "final")
        or gateway._review(review) != occasion["review"]
    ):
        raise FinalEvaluationError("final execution cannot replace its original grant or review")
    report_path = state["directory"] / "report.json"
    if report_path.exists():
        return inspect_result(directory, file_hash(report_path))
    reader, current = _census(state, occasion, pins)
    history = _partials(state, occasion, reader, current)
    reader.finish()
    if history and history[-1]["reason"] == "candidate_execution_failed":
        return history[-1]
    with trial_fence.lease(
        authorization.path, authorization._terms(), directory=state["directory"]
    ):
        state, occasion, pins = restore(directory)
        observations = state["directory"] / "observations"
        if not observations.exists():
            observations.mkdir()

        def partial(reason: str) -> dict[str, object]:
            reader, current = _census(state, occasion, pins)
            cells, generated, failed = study._collect(state, occasion, reader, current)
            position = _position(occasion, len(cells), generated)
            child_ref = None
            if position["stage"] != "publication" and failed is None:
                child = study._location(
                    state,
                    occasion,
                    cast(int, position["arm_index"]),
                    cast(int, position["task_index"]),
                    cast(int, position["repetition"]),
                )
                child = (
                    child
                    / ("evaluation" if position["stage"] == "native" else "generation")
                    / "observations"
                )
                if child.is_dir():
                    candidates = sorted(child.glob("*.json"), key=lambda path: int(path.stem))
                    if candidates:
                        path = candidates[-1]
                        raw = reader.raw(path)
                        value = _load(raw)
                        if value.get("reason") == reason:
                            child_ref = {"path": str(path), "sha256": sha(raw)}
            result: dict[str, object] = {
                "format": "buddha.final-evaluation-partial.v1",
                "status": "incomplete",
                "reason": reason,
                "position": position,
                "cells": cells,
                "coverage": {
                    "expected": occasion["counts"]["cells"],
                    "generated": generated,
                    "evaluated": len(cells),
                },
                "failed_generation": failed,
                "child_observation": child_ref,
                "authorization": current,
                "schedule_sha256": pipeline._sha(occasion),
                "claim": CLAIM,
            }
            reader.finish()
            number = len(list(observations.iterdir()))
            pipeline._write(observations / (str(number) + ".json"), _json(result))
            return result

        try:
            for arm, index, identifier, repeat, cell in study._cells(state, occasion):
                reader, current = _census(state, occasion, pins)
                complete, _, failed = study._collect(state, occasion, reader, current)
                ordinal = (arm["arm_index"] * len(occasion["selected_ids"]) + index) * occasion[
                    "repetitions"
                ] + repeat
                if ordinal < len(complete):
                    reader.finish()
                    continue
                if failed is not None:
                    reader.finish()
                    return partial("candidate_execution_failed")
                reader.finish()
                generation, selected, controls = study._materialize(
                    state, occasion, arm, identifier, cell, receipts=pins
                )
                with _episode(
                    state,
                    occasion,
                    pins,
                    reader,
                    cell,
                    "generation",
                    generation,
                    cell / "generation.json",
                ):
                    if not (cell / "generation").exists():
                        candidate_generation.prepare_candidate_generation(
                            cell / "generation",
                            descriptor=cell / "generation.json",
                            selection=selected,
                            roots={key: Path(value) for key, value in generation["roots"].items()},
                            authorization=authorization,
                            review=occasion["review"],
                            budget_microusd=generation["budget_microusd"],
                            max_calls=generation["max_calls"],
                            expected_runtime_sha256=state["runtime"],
                            input_files=list(controls),
                            expected_input_hashes=controls,
                        )
                    child = candidate_generation.run_candidate_generation(
                        cell / "generation", transport=transport
                    )
                if child["status"] != "complete":
                    return partial(_text(child["reason"]))
                if child["disposition"] != "generated":
                    return partial("candidate_execution_failed")
                descriptor = cell / "evaluation.json"
                pipeline._same_or_write(
                    descriptor,
                    _json(
                        {
                            "format": "buddha.native-evaluation.v1",
                            "source_generation": child["source_generation"],
                            "native": state["record"]["native"],
                            "stages": state["record"]["stages"],
                        }
                    ),
                )
                controls[descriptor] = file_hash(descriptor)
                reader, _ = _census(state, occasion, pins)
                with _episode(
                    state,
                    occasion,
                    pins,
                    reader,
                    cell,
                    "native",
                    state["record"]["native"],
                    descriptor,
                ):
                    reader.finish()
                    if not (cell / "evaluation").exists():
                        native_evaluation.prepare_evaluation(
                            cell / "evaluation",
                            descriptor=descriptor,
                            authorization=authorization,
                            review=occasion["review"],
                            input_files=list(controls),
                            expected_input_hashes=controls,
                        )
                    child = native_evaluation.run_evaluation(
                        cell / "evaluation", transport=transport
                    )
                if child["status"] != "complete":
                    return partial(_text(child["reason"]))
            reader, current = _census(state, occasion, pins)
            result = build_result(state, occasion, reader, current)
            reader.finish()
            pipeline._write(report_path, _json(result))
            return result
        except KeyboardInterrupt as error:
            try:
                partial("cancelled")
            except (ValueError, TypeError, KeyError, OSError, RecursionError):
                error.add_note(
                    "Original final cancellation retained; partial evidence could not be verified."
                )
            raise
        except (ValueError, TypeError, KeyError, OSError, RecursionError) as error:
            try:
                partial("protocol")
            except (ValueError, TypeError, KeyError, OSError, RecursionError):
                error.add_note(
                    "Original final failure retained; partial evidence could not be verified."
                )
            raise
