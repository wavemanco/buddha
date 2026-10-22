"""Passive prospective custody checks for the original prepared source search.

This is a readiness observation, never a writer, lock remover or permission to
spend. The launcher separately binds approval, grant membership and live scope.
"""

import hashlib
import re
import stat
from pathlib import Path
from typing import Any, cast

from buddha import (
    candidate_generation,
    candidate_improvement,
    gateway,
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
    owner = reader.owner(path)
    expected = {
        "selection": section["selection"],
        "roots": section["roots"],
        "review": state["record"]["review"],
        "authorization_path": str(reader.authorization),
        "settings": {
            "budget_microusd": 1 if no_model else section["budget_microusd"],
            "max_calls": 1 if no_model else section["max_calls"],
        },
    }
    if any(_json(owner.manifest[name]) != _json(value) for name, value in expected.items()):
        raise source_search.SourceSearchError("prepared owner changes its original treatment")
    bindings = reader._bindings(owner)
    if any(bindings.get(str(path)) != digest for path, digest in controls.items()):
        raise source_search.SourceSearchError("prepared owner omits an original input")
    gateway.execution_identity(path, owner.manifest)
    funded = [row for row in state["funding"]["auth_runs"] if row["run_id"] == owner.run_id]
    if (
        len(funded) != 1
        or type(funded[0]["historical"]) is not int
        or funded[0]["historical"] != 0
        or funded[0]["runtime_sha256"] != owner.manifest["execution_sha256"]
    ):
        raise source_search.SourceSearchError("prepared owner changes its original runtime")
    state["checked_owners"].add(path)


def _seal(reader: NativeEvidence, state: dict[str, Any], path: Path, *, role: str) -> bool:
    owner = reader.owner(path)
    child, index = path.parent.parent, int(path.name)
    sealed = child / "completed" / (str(index) + ".json")
    anchors = [
        row["reason"]
        for row in state["funding"]["auth_deactivations"]
        if row["run_id"] == owner.run_id
    ]
    if not _present(reader, sealed):
        state["inactive_pending"] |= bool(anchors)
        return False
    raw = reader.raw(sealed)
    seal = _object(_load(raw), {"format", "index", "owner_sha256", "attempt", "files"})
    formats = {
        "generation": (candidate_generation.SEAL_FORMAT_V2, candidate_generation.ANCHOR_PREFIX_V2),
        "proposal": (candidate_improvement.SEAL_FORMAT, candidate_improvement.ANCHOR_PREFIX),
        "native": ("buddha.native-evaluation-stage.v1", "native evaluation completed: "),
    }
    kind, prefix = formats[role]
    relative = _path(seal["attempt"])
    if (
        seal["format"] != kind
        or type(seal["index"]) is not int
        or seal["index"] != index
        or seal["owner_sha256"] != owner.manifest_sha256
        or not re.fullmatch(rf"attempts/{index}-(?:0|[1-9][0-9]*)", relative)
        or anchors != [prefix + _sha(raw)]
        or any(op.status != "completed" for op in owner.operations)
    ):
        raise source_search.SourceSearchError("prepared completion lacks its original anchor")
    attempt = child / relative
    files = _object(seal["files"])
    prefix_path = attempt.relative_to(reader.root).as_posix() + "/"
    actual = {
        name.removeprefix(prefix_path)
        for name in reader.capture.entries
        if name.startswith(prefix_path) and stat.S_ISREG((reader.root / name).lstat().st_mode)
    }
    if set(files) != actual or "report.json" not in files:
        raise source_search.SourceSearchError("prepared completion inventory differs")
    for name, digest in files.items():
        reader.raw(attempt / _path(name), _digest(digest))
    return True


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
) -> dict[str, object]:
    """Check retained execution custody without keys or writable owner objects."""
    if (
        not isinstance(directory, Path)
        or not isinstance(authorization, Path)
        or type(seed_screen) is not source_screen.SourceScreen
        or type(spec) is not source_search.SourceSearchSpec
        or type(input_bindings) is not dict
    ):
        raise source_search.SourceSearchError("prepared custody needs explicit Paths")
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
    next_owner, next_role = _screen(reader, state, directory / "seed", seed_screen)
    for iteration in range(state["spec"]["iterations"]):
        location = directory / "iterations" / str(iteration)
        if not _present(reader, location / "plan.json"):
            if next_owner is None and not state.get("seed_ineligible"):
                next_owner, next_role = location / "proposal/owners/0", "proposal"
            break
        plan = cast(dict[str, Any], _load(reader.raw(location / "plan.json")))
        if not _present(reader, location / "proposal"):
            if next_owner is None:
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
            if next_owner is None:
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
            screen = source_search._child_screen(state, observed)
            pending, role = _screen(reader, state, location / "screen", screen)
            if next_owner is None:
                next_owner, next_role = pending, role
        elif observed["disposition"] == "materialized" and (
            _object(observed["child"])["agent_sha256"] not in state["known_ids"]
        ):
            if next_owner is None:
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
    if complete:
        source_search.inspect_source_search(
            directory,
            authorization=authorization,
            expected_report_sha256=_sha(reader.raw(directory / "report.json")),
        )
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
    }
