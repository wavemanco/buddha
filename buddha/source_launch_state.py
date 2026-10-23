"""Passive prospective custody checks for the original prepared source search.

This is a readiness observation, never a writer, lock remover or permission to
spend. The launcher separately binds approval, grant membership and live scope.
"""

import hashlib
import re
from pathlib import Path
from typing import Any, cast

from buddha import (
    candidate_generation,
    candidate_improvement,
    source_screen,
    source_search,
)
from buddha import native_pipeline as pipeline
from buddha.answers import Answers
from buddha.candidate_improvement_results import collect_candidate_improvement
from buddha.native_evidence import NativeEvidence
from buddha.releases import Release, _digest, _json, _load, _object, _path, file_hash


def _sha(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()


def _present(reader: NativeEvidence, path: Path) -> bool:
    return path.relative_to(reader.root).as_posix() in reader.capture.entries


def _ordinals(
    reader: NativeEvidence, path: Path, *, first: int, maximum: int, suffix: str = ""
) -> None:
    prefix = path.relative_to(reader.root).as_posix() + "/"
    names = {
        name.removeprefix(prefix).split("/")[0]
        for name in reader.capture.entries
        if name.startswith(prefix)
    }
    if len(names) > maximum or names != {str(i) + suffix for i in range(first, first + len(names))}:
        raise source_search.SourceSearchError("prepared schedule has missing or foreign entries")


def _owner(
    reader: NativeEvidence,
    state: dict[str, Any],
    path: Path,
    section: dict[str, Any],
    controls: dict[Path, str],
    *,
    no_model: bool = False,
) -> None:
    source_search._stage_owner(
        reader, state, path, section, controls, no_model=no_model, verify_files=True
    )
    state["checked_owners"].add(path)


def _seal(reader: NativeEvidence, state: dict[str, Any], path: Path, *, role: str) -> bool:
    return source_search._stage_seal(reader, state, path, role=role)


def _screen(
    reader: NativeEvidence,
    state: dict[str, Any],
    directory: Path,
    screen: source_screen.SourceScreen,
) -> tuple[Path | None, str | None]:
    source_search._screen_owner(reader, state, directory, screen)
    record = screen.to_record()
    _ordinals(reader, directory / "tasks", first=0, maximum=len(screen.tasks.tasks))
    anchor = reader.owner(directory / "tasks/0/generation/owners/0")
    context = _load(reader.bound(anchor, directory / "context.json"))
    controls = {
        Path(name): _digest(digest) for name, digest in _object(context["controls"]).items()
    } | {
        directory / "screen.json": screen.fingerprint(),
        directory / "context.json": pipeline._sha(context),
    }
    if _present(reader, directory / "report.json"):
        # _restore already reconstructs every published prefix screen. Only a
        # current screen whose decision was not written needs a separate read.
        if not any(reference["directory"] == str(directory) for reference in state["screens"]):
            source_screen.inspect_source_screen(
                directory,
                authorization=reader.authorization,
                expected_report_sha256=_sha(reader.raw(directory / "report.json")),
            )
        for path in tuple(reader.owners):
            if not path.is_relative_to(directory):
                continue
            parts = path.relative_to(directory).parts
            task_index, role = int(parts[1]), parts[2]
            _owner(
                reader,
                state,
                path,
                _object(record["generation" if role == "generation" else "native"]),
                controls
                | source_screen._task_controls(
                    directory / "tasks" / str(task_index), screen, task_index
                ),
                no_model=role == "evaluation"
                and int(path.name) == len(cast(list[object], record["stages"])),
            )
        return None, None
    stages = cast(list[dict[str, Any]], record["stages"])
    reader.release = Release.from_record(_object(record["source"])["release"])
    reader.template = {"native": record["native"], "stages": stages}
    reader.funded = state["funding"]
    next_owner, next_role = None, None
    unfinished, terminal_failure = False, False
    for index, task in enumerate(screen.tasks.tasks):
        location = directory / "tasks" / str(index)
        if not _present(reader, location):
            if next_owner is None and not terminal_failure:
                next_owner, next_role = location / "generation/owners/0", "generation"
            unfinished = True
            continue
        if terminal_failure:
            raise source_search.SourceSearchError("work follows a terminal candidate failure")
        task_controls = controls | source_screen._task_controls(location, screen, index)
        if reader.raw(location / "task.json") != screen.tasks.select([task.id]).to_bytes():
            raise source_search.SourceSearchError("prepared task differs from its original screen")
        if reader.raw(location / "generation.json") != _json(
            source_screen._generation_recipe(location, screen)
        ):
            raise source_search.SourceSearchError("prepared generation recipe differs")
        generation = location / "generation"
        _ordinals(reader, generation / "owners", first=0, maximum=1)
        _ordinals(reader, generation / "completed", first=0, maximum=1, suffix=".json")
        generation_context = {
            "format": source_screen._generation_formats(screen)["context"],
            "descriptor": str(location / "generation.json"),
            "expected_runtime_sha256": state["record"]["expected_runtime_sha256"],
        }
        if reader.raw(generation / "context.json") != _json(generation_context):
            raise source_search.SourceSearchError("prepared generation context differs")
        owner_path = generation / "owners/0"
        owner = reader.owner(owner_path)
        _owner(
            reader,
            state,
            owner_path,
            _object(record["generation"]),
            task_controls | {generation / "context.json": pipeline._sha(generation_context)},
        )
        sealed = _seal(reader, state, owner_path, role="generation")
        if unfinished and (owner.operations or sealed):
            raise source_search.SourceSearchError("prepared work skips an unfinished predecessor")
        if not sealed:
            if next_owner is None:
                next_owner, next_role = owner_path, "generation"
            unfinished = True
            continue
        reference = {
            "format": candidate_generation.SOURCE_FORMAT_V2,
            "generation_directory": str(generation),
            "stage_seal_sha256": _sha(reader.raw(generation / "completed/0.json")),
            "owner_manifest_sha256": owner.manifest_sha256,
            "owner_ledger_sha256": owner.ledger_sha256,
        }
        evidence = candidate_generation._read_evidence(reference, reader.authorization)
        for path, digest in cast(dict[Path, str], evidence["files"]).items():
            captured = reader.capture.raw.get(path)
            if captured is None:
                reader.raw(path, digest)
            elif _sha(captured) != digest:
                raise source_search.SourceSearchError("generation custody changed during checking")
        if _present(reader, generation / "report.json"):
            candidate_generation.inspect_candidate_generation(
                generation,
                authorization=reader.authorization,
                expected_report_sha256=_sha(reader.raw(generation / "report.json")),
            )
        if evidence["answers"] is None:
            terminal_failure = True
            if _present(reader, location / "evaluation"):
                raise source_search.SourceSearchError("evaluation follows a failed generation")
            continue
        evaluation = location / "evaluation"
        if not _present(reader, evaluation):
            if next_owner is None:
                next_owner, next_role = evaluation / "owners/1", "native"
            unfinished = True
            continue
        _ordinals(reader, evaluation / "owners", first=1, maximum=len(stages))
        _ordinals(reader, evaluation / "completed", first=1, maximum=len(stages), suffix=".json")
        definition = {
            "format": "buddha.native-evaluation.v1",
            "source_generation": reference,
            "native": record["native"],
            "stages": stages,
        }
        native_context = {
            "format": "buddha.native-evaluation-context.v1",
            "descriptor": str(location / "evaluation.json"),
        }
        if reader.raw(location / "evaluation.json") != _json(definition) or reader.raw(
            evaluation / "context.json"
        ) != _json(native_context):
            raise source_search.SourceSearchError("prepared native recipe differs")
        native_answers = evaluation / "native-answers.jsonl"
        if reader.raw(native_answers) != cast(Answers, evidence["answers"]).native_bytes():
            raise source_search.SourceSearchError("prepared native answers differ")
        available = {
            _path(_object(reader.release.to_record()["artifacts"])["answers"]): native_answers
        }
        for stage_index, stage in enumerate(stages, 1):
            owner_path = evaluation / "owners" / str(stage_index)
            if not _present(reader, owner_path):
                if next_owner is None:
                    next_owner, next_role = owner_path, "native"
                unfinished = True
                continue
            owner = reader.owner(owner_path)
            _owner(
                reader,
                state,
                owner_path,
                _object(record["native"]),
                task_controls
                | {
                    location / "evaluation.json": pipeline._sha(definition),
                    evaluation / "context.json": pipeline._sha(native_context),
                },
                no_model=stage_index == len(stages),
            )
            sealed = _seal(reader, state, owner_path, role="native")
            if unfinished and (owner.operations or sealed):
                raise source_search.SourceSearchError(
                    "prepared work skips an unfinished predecessor"
                )
            if not sealed:
                reader.native_configuration(
                    evaluation, stage_index, cast(Path, evidence["answers_path"]), available
                )
                if next_owner is None:
                    next_owner, next_role = owner_path, "native"
                unfinished = True
                continue
            report, attempt = reader.stage(evaluation, stage_index, baseline=False)
            reader.native(
                evaluation, stage_index, report, cast(Path, evidence["answers_path"]), available
            )
            for output in stage["outputs"]:
                available[_path(output["path"])] = attempt / "artifacts" / _path(output["path"])
    return next_owner, next_role


def _after_screen(
    reader: NativeEvidence,
    state: dict[str, Any],
    directory: Path,
    next_owner: Path | None,
    next_role: str | None,
) -> tuple[Path | None, str | None, bool]:
    if next_role is not None:
        return next_owner, next_role, False
    if not _present(reader, directory / "report.json"):
        # Sealed lower stages can still need original local publication.
        return None, None, False
    report = reader.record(directory / "report.json")
    if _object(report["admission"])["eligible"] is not True:
        return None, None, True
    progress = state["mutation_progress"].get(str(directory))
    if progress is None:
        raise source_search.SourceSearchError("eligible screen lacks its mutation witness state")
    return progress["next_owner"], progress["next_role"], progress["result"] is not None


@source_search._checked
def inspect_prepared_search(
    directory: Path,
    authorization: Path,
    *,
    seed_screen: source_screen.SourceScreen,
    proposal_template: dict[str, object],
    spec: source_search.SourceSearchSpec,
    review: dict[str, object],
    expected_runtime_sha256: str,
    input_bindings: dict[Path, str],
    mutation_witness: bool = False,
    source_copy: bool | None = None,
) -> dict[str, object]:
    """Check retained execution custody without keys or writable owner objects."""
    if (
        not isinstance(directory, Path)
        or not isinstance(authorization, Path)
        or type(seed_screen) is not source_screen.SourceScreen
        or type(spec) is not source_search.SourceSearchSpec
        or type(input_bindings) is not dict
        or type(mutation_witness) is not bool
    ):
        raise source_search.SourceSearchError("prepared custody needs explicit Paths")
    copy_source = source_search._source_copy_choice(mutation_witness, source_copy)
    reader = NativeEvidence(directory, authorization, error_type=source_search.SourceSearchError)
    state = source_search._restore(directory, authorization, reader=reader)
    from buddha.search_evidence import read_authority

    state["funding"] = read_authority(reader.capture.raw[authorization])
    state["checked_owners"], state["inactive_pending"] = set(), False
    expected_controls = dict(input_bindings)
    runtime = _object(_object(seed_screen.to_record()["generation"])["runtime"])
    automatic = {path: file_hash(path) for path in source_search._sources()}
    automatic[pipeline._absolute(runtime["path"])] = _digest(expected_runtime_sha256)
    if any(
        path in expected_controls and expected_controls[path] != digest
        for path, digest in automatic.items()
    ):
        raise source_search.SourceSearchError("approved input conflicts with an automatic control")
    expected_controls.update(automatic)
    expected = {
        "seed_screen": seed_screen.to_record(),
        "proposal_template": proposal_template,
        "spec": spec.to_record(),
        "review": review,
        "authorization": str(authorization),
        "expected_runtime_sha256": expected_runtime_sha256,
        "controls": {str(path): digest for path, digest in expected_controls.items()},
    }
    if any(_json(state["record"][name]) != _json(value) for name, value in expected.items()):
        raise source_search.SourceSearchError("original search differs from its approved launch")
    if mutation_witness:
        expected_format = (
            source_search._COPY_MANIFEST if copy_source else source_search._WITNESS_MANIFEST
        )
        if state["record"]["format"] != expected_format or _json(
            state["record"].get("mutation_witness")
        ) != _json(source_search.MUTATION_WITNESS_POLICY):
            raise source_search.SourceSearchError("approved search requires its mutation witness")
        if copy_source and _json(state["record"].get("source_copy")) != _json(
            source_search.SOURCE_COPY_POLICY
        ):
            raise source_search.SourceSearchError("approved search requires its source-copy policy")
        for path, treatment in state["witness_treatments"].items():
            _owner(reader, state, path, treatment["section"], treatment["controls"])
        for progress in state["mutation_progress"].values():
            state["inactive_pending"] |= progress["inactive_pending"]
    elif (
        state["record"]["format"]
        not in {
            source_search._LEGACY_MANIFEST,
            source_search._FULL_MANIFEST,
        }
        or "mutation_witness" in state["record"]
    ):
        raise source_search.SourceSearchError("approved legacy search changes its witness policy")
    next_owner, next_role = _screen(reader, state, directory / "seed", seed_screen)
    can_advance = True
    if mutation_witness:
        next_owner, next_role, can_advance = _after_screen(
            reader, state, directory / "seed", next_owner, next_role
        )
        can_advance &= not state.get("seed_parent_ineligible", False)
    for iteration in range(state["spec"]["iterations"]):
        location = directory / "iterations" / str(iteration)
        if not _present(reader, location / "plan.json"):
            if next_owner is None and can_advance and not state.get("seed_ineligible"):
                next_owner, next_role = location / "proposal/owners/0", "proposal"
            break
        plan = cast(dict[str, Any], _load(reader.raw(location / "plan.json")))
        if not _present(reader, location / "proposal"):
            if next_owner is None and can_advance:
                next_owner, next_role = location / "proposal/owners/0", "proposal"
            continue
        parent = source_screen.SourceScreen.from_bytes(
            reader.raw(pipeline._absolute(plan["parent"]["directory"]) / "screen.json")
        )
        parent_generation = _object(parent.to_record()["generation"])
        proposal_section = parent_generation | state["record"]["proposal_template"]
        proposal = location / "proposal"
        _ordinals(reader, proposal / "owners", first=0, maximum=1)
        _ordinals(reader, proposal / "completed", first=0, maximum=1, suffix=".json")
        context = {
            "format": candidate_improvement.CONTEXT_FORMAT,
            "descriptor": str(location / "proposal.json"),
            "expected_runtime_sha256": expected_runtime_sha256,
            "expected_feedback_provenance_sha256": plan["feedback_sha256"]["provenance.json"],
        }
        if reader.raw(proposal / "context.json") != _json(context):
            raise source_search.SourceSearchError("prepared proposal context differs")
        owner_path = proposal / "owners/0"
        _owner(
            reader,
            state,
            owner_path,
            proposal_section,
            source_search._proposal_controls(state, location, plan)
            | {proposal / "context.json": pipeline._sha(context)},
        )
        if not _seal(reader, state, owner_path, role="proposal"):
            if next_owner is None and can_advance:
                next_owner, next_role = owner_path, "proposal"
            continue
        if iteration < len(state["decisions"]):
            observed = reader.record(proposal / "report.json")
        else:
            observed = collect_candidate_improvement(
                proposal,
                authorization=authorization,
                expected_report_sha256=(
                    _sha(reader.raw(proposal / "report.json"))
                    if _present(reader, proposal / "report.json")
                    else None
                ),
            )
        if observed["disposition"] == "materialized" and _present(reader, location / "screen"):
            screen = source_search._child_screen(state, observed, location)
            pending, role = _screen(reader, state, location / "screen", screen)
            if mutation_witness:
                pending, role, can_advance = _after_screen(
                    reader, state, location / "screen", pending, role
                )
            if next_owner is None:
                next_owner, next_role = pending, role
        elif observed["disposition"] == "materialized" and (
            _object(observed["child"])["agent_sha256"] not in state["known_ids"]
        ):
            if next_owner is None and can_advance:
                next_owner, next_role = (
                    location / "screen/tasks/0/generation/owners/0",
                    "generation",
                )
    if set(reader.owners) != state["checked_owners"]:
        raise source_search.SourceSearchError("retained owner lacks its approved schedule")
    for name in reader.capture.entries:
        if re.search(r"/owners/[^/]+$", name) and reader.root / name not in state["checked_owners"]:
            raise source_search.SourceSearchError("prepared owner lacks its original manifest")
    complete = _present(reader, directory / "report.json")
    completion_reason = {}
    if complete:
        report = source_search.inspect_source_search(
            directory,
            authorization=authorization,
            expected_report_sha256=_sha(reader.raw(directory / "report.json")),
        )
        if mutation_witness and report["reason"] == "no_parent_eligible":
            completion_reason["reason"] = "no_parent_eligible"
        next_owner, next_role = None, None
    digests = reader.capture.finish()
    return {
        "state": "complete" if complete else "prepared",
        "busy": any(
            name == "running.lock" or name.endswith("/running.lock")
            for name in reader.capture.entries
        ),
        "inactive_pending": state["inactive_pending"],
        "next_owner": None if next_owner is None else str(next_owner),
        "next_role": next_role,
        "state_sha256": pipeline._sha({"files": digests, "entries": reader.capture.entries}),
    } | completion_reason
