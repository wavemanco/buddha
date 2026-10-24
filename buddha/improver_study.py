"""Finite matched development study of two frozen source improvers.

Existing stages own execution, payments and benchmark measurements. This caller
owns the complete condition/arm schedule and never evaluates selected Python.
"""

import hashlib
import re
import sqlite3
from collections.abc import Callable, Iterator
from functools import wraps
from pathlib import Path
from typing import Any, cast

from buddha import (
    candidate_generation,
    candidate_improvement,
    source_feedback,
    source_screen,
    trial_fence,
)
from buddha import native_pipeline as pipeline
from buddha import source_search as shared
from buddha.answers import Answers
from buddha.authorization import Authorization
from buddha.doctor import _authority, _Busy, _Unsupported
from buddha.gateway import RawHTTPTransport, _input_records, _review
from buddha.native_evidence import NativeEvidence, authority_observation
from buddha.releases import (
    MAX_SOURCE_BYTES,
    Release,
    ReleaseError,
    Selection,
    _digest,
    _json,
    _load,
    _object,
    _path,
    _root,
    file_hash,
)
from buddha.search_evidence import MAX_FILES
from buddha.wire import _integer

_FORMAT = "buddha.improver-study.v1"
_CONTEXT = "buddha.improver-study-context.v1"
_PLAN = "buddha.improver-study-plan.v1"
_DECISION = "buddha.improver-study-decision.v1"
_REPORT = "buddha.improver-study-report.v1"
_OBSERVATION = "buddha.improver-study-observation.v1"
_TOTALS = ("spent_microusd", "reserved_microusd", "committed_microusd", "operation_count")
_CLAIM = "finite development comparison only; no improver effectiveness or sealed assessment claim"
_COORD = ("start", "repetition", "arm", "slot")


class ImproverStudyError(ReleaseError):
    """The original finite study or retained custody is inconsistent."""


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
            if isinstance(error, (ImproverStudyError, source_feedback.SourceFeedbackTooLarge)):
                raise
            raise ImproverStudyError(
                "finite study configuration or retained evidence is invalid"
            ) from None

    return checked


def _rows(value: object, minimum: int = 0, maximum: int = 1024) -> list[Any]:
    if type(value) is not list or not minimum <= len(value) <= maximum:
        raise ImproverStudyError("finite study needs a bounded literal ordered list")
    return value


def _path_value(value: object) -> Path:
    return shared._witness_path(value)


def _sum(rows: list[dict[str, Any]]) -> dict[str, int]:
    return {key: sum(cast(int, row[key]) for row in rows) for key in _TOTALS}


def _caps(record: dict[str, Any], screen: source_screen.SourceScreen) -> dict[str, Any]:
    data = screen.to_record()
    generation, native, template = (
        _object(data["generation"]),
        _object(data["native"]),
        _object(record["proposal_template"]),
    )
    stages = len(_rows(data["stages"], 1))
    result: dict[str, Any] = {}
    for key in ("budget_microusd", "max_calls"):
        screen_cap = len(screen.tasks.tasks) * (
            cast(int, generation[key]) + (stages - 1) * cast(int, native[key]) + 1
        )
        witness = cast(int, template[key]) + cast(int, generation[key])
        result.setdefault("common_cell", {})[key] = screen_cap + witness
        result.setdefault("arm_cell", {})[key] = cast(int, record["descendant_opportunities"]) * (
            cast(int, template[key]) + screen_cap + witness
        )
        result.setdefault("study", {})[key] = (
            len(record["starts"])
            * record["repetitions"]
            * (result["common_cell"][key] + 2 * result["arm_cell"][key])
        )
        for section in result.values():
            _integer(section[key], 1, 2**63 - 1)
    return result


def _operator(record: dict[str, Any], arm: int, base: source_screen.SourceScreen) -> dict[str, Any]:
    actor = record["improvers"][arm]
    generation = _object(base.to_record()["generation"])
    generation.update(_object(record["proposal_template"]))
    generation.update(
        selection=actor["selection"], roots=actor["roots"], entrypoint=actor["entrypoint"]
    )
    executor = _object(generation["executor"])
    executor["mounts"] = [
        ["/agent", actor["roots"]["agent"]],
        ["/runner", actor["roots"]["runner"]],
    ]
    return generation


def _declaration(
    value: object, runtime: str, *, active: bool = False
) -> tuple[dict[str, Any], list[source_screen.SourceScreen]]:
    record: dict[str, Any] = _object(
        value,
        {
            "format",
            "experiment_id",
            "improvers",
            "starts",
            "repetitions",
            "descendant_opportunities",
            "proposal_template",
            "selection",
            "witness_policy",
            "source_copy",
            "limits",
            "consumer_sources",
            "assessment",
        },
    )
    if record["format"] != _FORMAT or type(record["experiment_id"]) is not str:
        raise ImproverStudyError("unsupported finite improver study")
    _path(record["experiment_id"])
    _integer(record["repetitions"], 1, 8)
    _integer(record["descendant_opportunities"], 1, 8)
    actors = _rows(record["improvers"], 2, 2)
    starts = _rows(record["starts"], 1, 8)
    screens, names = [], set()
    for value in starts:
        start = _object(value, {"name", "screen"})
        if type(start["name"]) is not str or start["name"] in names:
            raise ImproverStudyError("starting bundles require unique literal names")
        _path(start["name"])
        names.add(start["name"])
        screen = source_screen.SourceScreen.from_bytes(_json(start["screen"]))
        if screen.to_record()["format"] != "buddha.source-screen.v2" or (
            _object(screen.to_record()["generation"])["entrypoint"] != "candidate.py"
            or screen.to_record()["lineage"] is not None
        ):
            raise ImproverStudyError("study starts need prospective one-file root bundles")
        screens.append(screen)
    base = screens[0]
    if len({screen.candidate_id for screen in screens}) != len(screens) or any(
        screen.comparison_key() != base.comparison_key() for screen in screens
    ):
        raise ImproverStudyError("starts repeat a source or change the protected comparison")
    template = shared._template(record["proposal_template"])
    shared._template_screen(base, template)
    baseline = _object(_object(base.to_record()["generation"])["selection"])
    roots = _object(_object(base.to_record()["generation"])["roots"])
    identifiers = []
    for arm, value in enumerate(actors):
        actor = _object(value, {"name", "selection", "roots", "entrypoint"})
        if actor["name"] != ("initial", "evolved")[arm]:
            raise ImproverStudyError("frozen improvers have fixed ordered role names")
        selected = Selection.from_bytes(_json(actor["selection"]))
        inventory_ = _object(_object(selected.to_record()["components"])["agent"])
        entrypoint = _path(actor["entrypoint"])
        if (
            len(Path(entrypoint).parts) != 1
            or not entrypoint.endswith(".py")
            or set(inventory_) != {entrypoint}
        ):
            raise ImproverStudyError("frozen improver requires its exact one-file entrypoint")
        normalized = selected.to_record()
        _object(normalized["components"])["agent"] = _object(baseline["components"])["agent"]
        if _json(normalized) != _json(baseline):
            raise ImproverStudyError("improver changes a protected non-agent selection")
        actor_roots = _object(actor["roots"])
        if set(actor_roots) != set(roots) or any(
            actor_roots[key] != value for key, value in roots.items() if key != "agent"
        ):
            raise ImproverStudyError("improver changes protected component roots")
        for path in actor_roots.values():
            _path_value(path)
        identifiers.append(selected.agent_sha256)
        section = _operator(record, arm, base)
        prospective = base.to_record()
        prospective["generation"] = section
        checked = source_screen.SourceScreen.from_bytes(_json(prospective))
        if active:
            source_screen._configuration(checked, runtime)
    if identifiers[0] == identifiers[1]:
        raise ImproverStudyError("the two fixed improver identities must differ")
    selection = _object(record["selection"], {"method", "max_active", "seed", "finalist_iteration"})
    if selection["method"] not in {"archive", "latest", "uninformed"}:
        raise ImproverStudyError("unsupported frozen parent selection")
    _integer(selection["max_active"], 2, 64)
    _integer(selection["seed"], 0)
    if (
        type(selection["finalist_iteration"]) is not int
        or selection["finalist_iteration"] != record["descendant_opportunities"]
    ):
        raise ImproverStudyError("final selection iteration differs from the finite allocation")
    if _json(record["witness_policy"]) != _json(shared.MUTATION_WITNESS_POLICY) or (
        _json(record["source_copy"]) != _json(shared.SOURCE_COPY_POLICY)
    ):
        raise ImproverStudyError(
            "finite study requires complete mutation witnesses and source copies"
        )
    if _json(record["limits"]) != _json(_caps(record, base)):
        raise ImproverStudyError("declared cell or whole-study ceilings are not derived exactly")
    consumers = _object(record["consumer_sources"])
    paths = [_path_value(path) for path in consumers]
    if not paths or len(paths) != len(set(paths)) or len(paths) > 64:
        raise ImproverStudyError("study consumers need bounded unique original source pins")
    for digest in consumers.values():
        _digest(digest)
    if sum(path.name == "improver_study.py" for path in paths) != 1:
        raise ImproverStudyError("finite consumer source must be an original common input")
    assessment = _object(record["assessment"], {"status", "reason"})
    if (
        assessment["status"] != "not_frozen"
        or type(assessment["reason"]) is not str
        or not assessment["reason"]
    ):
        raise ImproverStudyError(
            "this development consumer supports explicit unfrozen assessment only"
        )
    if active:
        for screen in screens:
            source_screen._configuration(screen, runtime)
    # shortcut: one finite development population, up to eight starts/repetitions/slots;
    # a larger declared study needs a separately reviewed bounded storage contract.
    opportunities = len(screens) * record["repetitions"] * 2 * record["descendant_opportunities"]
    owners_per_opportunity = (
        1 + len(base.tasks.tasks) * (1 + len(_rows(base.to_record()["stages"]))) + 2
    )
    if opportunities * owners_per_opportunity * 2 > MAX_FILES:
        raise ImproverStudyError("the full potential owner grid exceeds the evidence entry ceiling")
    return record, screens


def _first(directory: Path) -> Path:
    return directory / "common/0/0/screen/tasks/0/generation/owners/0"


def _presence(reader: NativeEvidence, path: Path) -> bool:
    return path.relative_to(reader.root).as_posix() in reader.capture.entries


def _reference(reader: NativeEvidence, directory: Path) -> dict[str, object]:
    return {
        "directory": str(directory),
        "authorization": str(reader.authorization),
        "report_sha256": pipeline._sha(_load(reader.raw(directory / "report.json"))),
    }


def _coordinates(record: dict[str, Any]) -> Iterator[tuple[int, int, int, int]]:
    for slot in range(record["descendant_opportunities"]):
        for start in range(len(record["starts"])):
            for repetition in range(record["repetitions"]):
                first = (start + repetition + slot) % 2
                for arm in (first, 1 - first):
                    yield start, repetition, arm, slot


def _location(directory: Path, coordinate: tuple[int, int, int, int]) -> Path:
    return directory / "cells" / "/".join(map(str, coordinate))


def _context(directory: Path) -> dict[str, Any]:
    return _object(
        _load(pipeline._read(directory / "context.json")),
        {
            "format",
            "authorization",
            "review",
            "expected_runtime_sha256",
            "declaration",
            "declaration_sha256",
            "controls",
        },
    )


def _check_current(state: dict[str, Any]) -> None:
    for path, digest in state["controls"].items():
        pipeline._read(path, digest)


@_checked
def prepare_improver_study(
    directory: Path,
    *,
    declaration: Path,
    expected_sha256: str,
    authorization: Authorization,
    review: dict[str, object],
    expected_runtime_sha256: str,
) -> Path:
    if (
        not isinstance(directory, Path)
        or not isinstance(declaration, Path)
        or not isinstance(authorization, Authorization)
    ):
        raise ImproverStudyError("study preparation needs explicit paths and existing authority")
    directory, declaration = _path_value(str(directory)), _path_value(str(declaration))
    raw = pipeline._read(declaration, _digest(expected_sha256))
    runtime = _digest(expected_runtime_sha256)
    record, screens = _declaration(_load(raw), runtime, active=True)
    base = screens[0]
    checked_review = _review(review, fresh=True)
    terms = authorization._terms()
    purpose = "source screen: " + base.comparison_key()
    trial_fence.require_purpose(authorization.path, terms, directory=directory, expected=purpose)
    limits = record["limits"]["study"]
    if any(cast(int, terms[key]) < limits[key] for key in ("budget_microusd", "max_calls")):
        raise ImproverStudyError("original authority cannot cover the complete declared grid")
    controls = {
        _path_value(path): _digest(digest) for path, digest in record["consumer_sources"].items()
    }
    current_consumer = Path(__file__).absolute()
    if controls.get(current_consumer) != file_hash(current_consumer):
        raise ImproverStudyError("current finite producer lacks its original approval pin")
    controls[declaration] = _digest(expected_sha256)
    for path in shared._sources():
        controls[path] = file_hash(path)
    controls = trial_fence._include_controls(directory, controls)
    sources: list[bytes] = []
    for screen in screens:
        generation = _object(screen.to_record()["generation"])
        path = _path_value(_object(generation["roots"])["agent"]) / "candidate.py"
        source_raw = pipeline._read(
            path,
            _object(_object(_object(generation["selection"])["components"])["agent"])[
                "candidate.py"
            ],
        )
        if len(source_raw) > MAX_SOURCE_BYTES:
            raise ImproverStudyError("starting parent exceeds its literal source ceiling")
        source_raw.decode("utf-8")
        controls[path] = file_hash(path, max_bytes=MAX_SOURCE_BYTES)
        controls[_path_value(_object(generation["runtime"])["path"])] = runtime
        sources.append(source_raw)
    for actor in record["improvers"]:
        path = _path_value(actor["roots"]["agent"]) / actor["entrypoint"]
        raw_actor = pipeline._read(
            path,
            _object(_object(_object(actor["selection"])["components"])["agent"])[
                actor["entrypoint"]
            ],
        )
        if len(raw_actor) > MAX_SOURCE_BYTES:
            raise ImproverStudyError("frozen improver exceeds its literal source ceiling")
        raw_actor.decode("utf-8")
        controls[path] = file_hash(path, max_bytes=MAX_SOURCE_BYTES)
    protected = [authorization.path, *controls]
    for screen in screens:
        for role in ("generation", "native"):
            protected.extend(source_screen._roots(_object(screen.to_record()[role])).values())
    if directory.exists() or any(
        directory.is_relative_to(path) or path.is_relative_to(directory) for path in protected
    ):
        raise ImproverStudyError("fresh study overlaps original inputs or retained evidence")
    # Project ordinary and witness control closures before creating any owner.
    prospective = set(controls) | {directory / "declaration.json", directory / "context.json"}
    prospective |= {
        directory / "inputs/starts" / str(i) / "candidate.py" for i in range(len(sources))
    }
    _input_records(list(controls), controls)
    _capacity(directory, record, base, prospective)
    with trial_fence.work(authorization.path, terms, directory=directory, kind="search"):
        directory.mkdir()
        (directory / "observations").mkdir()
        (directory / "inputs/starts").mkdir(parents=True)
        for i, source_raw in enumerate(sources):
            parent = directory / "inputs/starts" / str(i)
            parent.mkdir()
            pipeline._write(parent / "candidate.py", source_raw)
            controls[parent / "candidate.py"] = file_hash(parent / "candidate.py")
        declaration_raw = _json(record)
        pipeline._write(directory / "declaration.json", declaration_raw)
        controls[directory / "declaration.json"] = pipeline._sha(record)
        context = {
            "format": _CONTEXT,
            "authorization": str(authorization.path),
            "review": checked_review,
            "expected_runtime_sha256": runtime,
            "declaration": str(declaration),
            "declaration_sha256": _digest(expected_sha256),
            "controls": {str(path): digest for path, digest in controls.items()},
        }
        pipeline._write(directory / "context.json", _json(context))
        controls[directory / "context.json"] = pipeline._sha(context)
        first = directory / "common/0/0/screen"
        first.parent.mkdir(parents=True)
        source_screen.prepare_source_screen(
            first,
            screen=base,
            authorization=authorization,
            review=checked_review,
            expected_runtime_sha256=runtime,
            input_bindings=controls,
        )
    return directory


def _capacity(
    directory: Path, record: dict[str, Any], screen: source_screen.SourceScreen, common: set[Path]
) -> None:
    """Count known invocation unions; future paths are data, never opened here."""
    slot = directory / "cells/0/0/0/0"
    proposal = slot / "proposal"
    packet = {slot / "feedback" / (name + ".json") for name in shared._FILES}
    plans = common | packet | {slot / "plan.json", slot / "proposal.json"}
    maximum = len(plans | {proposal / "context.json"} | set(candidate_improvement._sources()))
    location = slot / "screen/tasks/0"
    generation, evaluation = location / "generation", location / "evaluation"
    runtime = _path_value(_object(_object(screen.to_record()["generation"])["runtime"])["path"])
    lineage = slot / "proposal/attempts/0-0/session/child/lineage.json"
    controls = common | {
        slot / "screen/screen.json",
        slot / "screen/context.json",
        lineage,
        location / "task.json",
        location / "generation.json",
    }
    maximum = max(
        maximum,
        len(
            controls
            | {generation / "context.json", runtime}
            | set(candidate_generation._sources("buddha.candidate-generation.v2"))
        ),
    )
    attempt = generation / "attempts/0-0"
    source = {
        generation / "owners/0/manifest.json",
        generation / "owners/0/operations.sqlite3",
        generation / "completed/0.json",
        generation / "context.json",
        location / "generation.json",
        location / "task.json",
        runtime,
        attempt / "report.json",
        attempt / "session/report.json",
        attempt / "session/done.json",
        attempt / "session/answers.json",
    }
    release = Release.from_record(_object(screen.to_record()["source"])["release"])
    available = {
        _path(_object(release.to_record()["artifacts"])["answers"]): evaluation
        / "native-answers.jsonl"
    }
    seals: set[Path] = set()
    first: set[Path] = set()
    from buddha import native_evaluation

    for index, stage in enumerate(_rows(screen.to_record()["stages"]), 1):
        paths = (
            controls
            | source
            | {
                location / "evaluation.json",
                evaluation / "context.json",
                evaluation / ("command-" + str(index) + ".json"),
            }
            | set(available.values())
            | seals
        )
        paths |= {
            evaluation / "staging" / str(index) / (str(i) + ".bin")
            for i in range(len(stage["inputs"]))
        }
        paths |= set(native_evaluation._sources())
        if index == 1:
            first = set(paths)
        else:
            paths |= first | {evaluation / "owners/1/manifest.json"}
        maximum = max(maximum, len(paths))
        for output in stage["outputs"]:
            name = _path(output["path"])
            available[name] = evaluation / "attempts" / (str(index) + "-0") / "artifacts" / name
        seals.add(evaluation / "completed" / (str(index) + ".json"))
    witness = slot / "witness"
    witness_inputs = (
        common
        | {witness / "plan.json", witness / "proposal.json"}
        | {witness / "feedback" / (name + ".json") for name in shared._FILES}
    )
    maximum = max(
        maximum,
        len(
            witness_inputs
            | {witness / "proposal/context.json"}
            | set(candidate_improvement._sources())
        ),
    )
    maximum = max(
        maximum,
        len(
            witness_inputs
            | {
                witness / name
                for name in (
                    "task.json",
                    "generation.json",
                    "proposal/report.json",
                    "proposal/completed/0.json",
                    "proposal/attempts/0-0/session/child/lineage.json",
                    "generation/context.json",
                )
            }
            | {runtime}
            | set(candidate_generation._sources("buddha.candidate-generation.v2"))
        ),
    )
    if maximum > 1024:
        raise ImproverStudyError("known fixed owner inputs exceed the existing 1024-path ceiling")


def _original(reader: NativeEvidence) -> dict[str, Any]:
    anchor = reader.owner(_first(reader.root))
    raw = reader.bound(anchor, reader.root / "context.json")
    context = _context(reader.root)
    if (
        raw != _json(context)
        or context["format"] != _CONTEXT
        or (context["authorization"] != str(reader.authorization))
    ):
        raise ImproverStudyError("study context lacks its original first owner")
    record, screens = _declaration(
        _load(reader.bound(anchor, reader.root / "declaration.json")),
        _digest(context["expected_runtime_sha256"]),
    )
    controls = {
        _path_value(path): _digest(digest) for path, digest in _object(context["controls"]).items()
    }
    controls[reader.root / "context.json"] = pipeline._sha(context)
    if controls.get(reader.root / "declaration.json") != pipeline._sha(record) or (
        controls.get(_path_value(context["declaration"])) != context["declaration_sha256"]
    ):
        raise ImproverStudyError("original declaration identities changed")
    names = {
        path.name
        for path in candidate_generation._recorded_sources(
            shared._sources(), anchor.manifest["core"]
        )
    }
    prefixes = {
        path.parent
        for path in controls
        if path.name == "source_search.py" and all(path.parent / name in controls for name in names)
    }
    if len(prefixes) != 1 or any(
        controls.get(_path_value(path)) != digest
        for path, digest in record["consumer_sources"].items()
    ):
        raise ImproverStudyError("study original helper/consumer closure is incomplete")
    bindings = reader._bindings(anchor)
    if any(bindings.get(str(path)) != digest for path, digest in controls.items()):
        raise ImproverStudyError("common first owner omitted original controls")
    for start, screen in enumerate(screens):
        path = reader.root / "inputs/starts" / str(start) / "candidate.py"
        source = reader.bound(anchor, path)
        if (
            len(source) > MAX_SOURCE_BYTES
            or pipeline._sha({"candidate.py": file_hash(path, max_bytes=MAX_SOURCE_BYTES)})
            != screen.candidate_id
        ):
            raise ImproverStudyError("retained starting parent differs from its original source")
        source.decode("utf-8")
    return {
        "directory": reader.root,
        "record": record,
        "screens": screens,
        "context": context,
        "controls": controls,
        "runtime": _digest(context["expected_runtime_sha256"]),
        "review": _object(context["review"]),
        "checked": set(),
        "inactive": False,
    }


def _census(reader: NativeEvidence, state: dict[str, Any]) -> None:
    record = state["record"]
    integer = r"(0|[1-9][0-9]*)"
    paths = set()
    for name in reader.capture.entries:
        if "/owners/" not in name:
            continue
        prefix = (
            name.split("/owners/", 1)[0] + "/owners/" + name.split("/owners/", 1)[1].split("/")[0]
        )
        common = re.fullmatch(rf"common/{integer}/{integer}/(.+)", prefix)
        cell = re.fullmatch(rf"cells/{integer}/{integer}/{integer}/{integer}/(.+)", prefix)
        if common:
            start, repetition, tail = common.groups()
            arm, slot = "0", "0"
        elif cell:
            start, repetition, arm, slot, tail = cell.groups()
        else:
            raise ImproverStudyError("foreign owner is outside the finite schedule")
        if (
            int(start) >= len(record["starts"])
            or int(repetition) >= record["repetitions"]
            or int(arm) >= 2
            or int(slot) >= record["descendant_opportunities"]
        ):
            raise ImproverStudyError("original owner is outside a declared condition or slot")
        stage = re.fullmatch(
            rf"screen/tasks/{integer}/(generation|evaluation)/owners/{integer}", tail
        )
        witness = re.fullmatch(r"witness/(proposal|generation)/owners/0", tail)
        proposal = cell is not None and tail == "proposal/owners/0"
        if stage:
            task, role, index = stage.groups()
            if (
                int(task) >= len(state["screens"][int(start)].tasks.tasks)
                or (role == "generation" and index != "0")
                or (
                    role == "evaluation"
                    and not 1 <= int(index) <= len(state["screens"][0].to_record()["stages"])
                )
            ):
                raise ImproverStudyError("screen owner changes its typed task/stage schedule")
        elif not witness and not proposal:
            raise ImproverStudyError("foreign role owner is not a declared stage")
        path = reader.root / prefix
        if prefix + "/manifest.json" not in reader.capture.entries:
            raise ImproverStudyError("orphan original owner directory has no manifest")
        paths.add(path)
    for path in paths:
        reader.owner(path)
    funding = _authority(reader.capture, reader.authorization, list(reader.owners.values()))
    if funding is None:
        raise ImproverStudyError("study lacks its original funding authority")
    funded = {
        _path_value(row["directory"]): row
        for row in reader._rows(funding["auth_runs"])
        if _path_value(row["directory"]).is_relative_to(reader.root)
    }
    if set(funded) != paths or any(
        funded[path]["run_id"] != reader.owner(path).run_id for path in paths
    ):
        raise ImproverStudyError("funded and retained original owners are not bijective")
    trial_fence.require_purpose(
        reader.authorization,
        _object(funding["config"]),
        directory=reader.root,
        expected="source screen: " + state["screens"][0].comparison_key(),
    )
    state.update(
        funding=funding,
        authorization=authority_observation(reader.capture, reader.authorization, funding),
        owner_paths=paths,
    )


def _owner(
    reader: NativeEvidence,
    state: dict[str, Any],
    path: Path,
    section: dict[str, Any],
    controls: dict[Path, str],
    *,
    no_model: bool = False,
) -> bool:
    shared._stage_owner_for(
        reader,
        path,
        section,
        controls,
        review=state["review"],
        funding=state["funding"],
        no_model=no_model,
    )
    state["checked"].add(path)
    role = (
        "proposal"
        if path.parent.parent.name == "proposal"
        else ("generation" if path.parent.parent.name == "generation" else "native")
    )
    sealed, inactive = shared._stage_seal_for(reader, path, funding=state["funding"], role=role)
    state["inactive"] |= inactive
    return sealed


def _ordinals(
    reader: NativeEvidence, path: Path, first: int, maximum: int, *, suffix: str = ""
) -> None:
    prefix = path.relative_to(reader.root).as_posix() + "/"
    names = {
        name.removeprefix(prefix).split("/")[0]
        for name in reader.capture.entries
        if name.startswith(prefix)
    }
    expected = {str(i) + suffix for i in range(first, first + len(names))}
    if names != expected or len(names) > maximum:
        raise ImproverStudyError("nested role has foreign or noncontiguous original ordinals")


def _screen(
    reader: NativeEvidence,
    state: dict[str, Any],
    directory: Path,
    screen: source_screen.SourceScreen,
) -> dict[str, Any] | None:
    shared._screen_owner_for(
        reader, state["controls"], state["review"], state["runtime"], directory, screen
    )
    record = screen.to_record()
    anchor = reader.owner(directory / "tasks/0/generation/owners/0")
    context = _load(reader.bound(anchor, directory / "context.json"))
    controls = {
        _path_value(path): _digest(digest) for path, digest in _object(context["controls"]).items()
    }
    source_screen._comparison_controls(context, controls, screen, core=anchor.manifest["core"])
    controls |= {
        directory / "screen.json": screen.fingerprint(),
        directory / "context.json": pipeline._sha(context),
    }
    _ordinals(reader, directory / "tasks", 0, len(screen.tasks.tasks))
    stages = _rows(record["stages"])
    reader.release = Release.from_record(_object(record["source"])["release"])
    reader.template = {"native": record["native"], "stages": stages}
    reader.funded = state["funding"]
    if _presence(reader, directory / "report.json"):
        report = shared._read_ref(reader, _reference(reader, directory), capture=True)
        expected = {path for path in state["owner_paths"] if path.is_relative_to(directory)}
        checked: set[Path] = set()
        for value in _rows(_object(report["provenance"])["owners"], 1, len(expected)):
            row = _object(value, {"directory", "run_id", "manifest_sha256", "ledger_sha256"})
            path = _path_value(row["directory"])
            if path not in expected or path in checked:
                raise ImproverStudyError(
                    "complete screen has foreign or duplicate owner provenance"
                )
            owner = reader.owner(path)
            if (
                row["run_id"] != owner.run_id
                or _digest(row["manifest_sha256"]) != owner.manifest_sha256
                or _digest(row["ledger_sha256"]) != owner.ledger_sha256
            ):
                raise ImproverStudyError("complete screen provenance changes an original owner")
            checked.add(path)
        if checked != expected:
            raise ImproverStudyError("complete screen provenance omits an original owner")
        if report.get("disposition") == "candidate_execution_failed":
            index = _integer(
                _object(report["failure"])["task_index"], 0, len(screen.tasks.tasks) - 1
            )
            if _presence(reader, directory / "tasks" / str(index) / "evaluation"):
                raise ImproverStudyError("native work follows a checked failed generation")
        for path in sorted(checked):
            parts = path.relative_to(directory).parts
            index, role = int(parts[1]), parts[2]
            location = directory / "tasks" / str(index)
            task_controls = controls | source_screen._task_controls(location, screen, index)
            if role == "generation":
                context = {
                    "format": source_screen._generation_formats(screen)["context"],
                    "descriptor": str(location / "generation.json"),
                    "expected_runtime_sha256": state["runtime"],
                }
                inputs = task_controls | {
                    location / "generation/context.json": pipeline._sha(context)
                }
            else:
                definition = {
                    "format": "buddha.native-evaluation.v1",
                    "source_generation": _object(_rows(report["tasks"])[index])[
                        "source_generation"
                    ],
                    "native": record["native"],
                    "stages": stages,
                }
                context = {
                    "format": "buddha.native-evaluation-context.v1",
                    "descriptor": str(location / "evaluation.json"),
                }
                inputs = task_controls | {
                    location / "evaluation.json": pipeline._sha(definition),
                    location / "evaluation/context.json": pipeline._sha(context),
                }
            # The full inspector proves completion; retain the finite caller's
            # extra per-owner task/recipe bindings before marking custody checked.
            shared._stage_owner_for(
                reader,
                path,
                _object(record["generation" if role == "generation" else "native"]),
                inputs,
                review=state["review"],
                funding=state["funding"],
                no_model=role == "evaluation" and int(path.name) == len(stages),
            )
        state["checked"].update(checked)
        return report
    unfinished, terminal = False, False
    for index, task in enumerate(screen.tasks.tasks):
        location = directory / "tasks" / str(index)
        if not _presence(reader, location):
            unfinished = True
            continue
        if terminal:
            raise ImproverStudyError("work follows a checked terminal source failure")
        task_controls = controls | source_screen._task_controls(location, screen, index)
        if reader.raw(location / "task.json") != screen.tasks.select(
            [task.id]
        ).to_bytes() or reader.raw(location / "generation.json") != _json(
            source_screen._generation_recipe(location, screen)
        ):
            raise ImproverStudyError("screen changes its original task or source recipe")
        generation = location / "generation"
        _ordinals(reader, generation / "owners", 0, 1)
        _ordinals(reader, generation / "completed", 0, 1, suffix=".json")
        generation_context = {
            "format": source_screen._generation_formats(screen)["context"],
            "descriptor": str(location / "generation.json"),
            "expected_runtime_sha256": state["runtime"],
        }
        if reader.raw(generation / "context.json") != _json(generation_context):
            raise ImproverStudyError("generation context changed")
        path = generation / "owners/0"
        owner = reader.owner(path)
        sealed = _owner(
            reader,
            state,
            path,
            _object(record["generation"]),
            task_controls | {generation / "context.json": pipeline._sha(generation_context)},
        )
        if unfinished and (owner.operations or sealed):
            raise ImproverStudyError("work skips an unfinished screen predecessor")
        if not sealed:
            unfinished = True
            continue
        reference = {
            "format": candidate_generation.SOURCE_FORMAT_V2,
            "generation_directory": str(generation),
            "stage_seal_sha256": pipeline._sha(_load(reader.raw(generation / "completed/0.json"))),
            "owner_manifest_sha256": owner.manifest_sha256,
            "owner_ledger_sha256": owner.ledger_sha256,
        }
        evidence = candidate_generation._read_evidence(reference, reader.authorization)
        for path, digest in cast(dict[Path, str], evidence["files"]).items():
            reader.raw(path, digest)
        if evidence["answers"] is None:
            terminal = True
            if _presence(reader, location / "evaluation"):
                raise ImproverStudyError("native work follows a checked failed generation")
            continue
        evaluation = location / "evaluation"
        if not _presence(reader, evaluation):
            unfinished = True
            continue
        _ordinals(reader, evaluation / "owners", 1, len(stages))
        _ordinals(reader, evaluation / "completed", 1, len(stages), suffix=".json")
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
            raise ImproverStudyError("native recipe changes its original source")
        answers = evaluation / "native-answers.jsonl"
        if reader.raw(answers) != cast(Answers, evidence["answers"]).native_bytes():
            raise ImproverStudyError("native answers differ from the original C1 bytes")
        available = {_path(_object(reader.release.to_record()["artifacts"])["answers"]): answers}
        for ordinal, stage in enumerate(stages, 1):
            path = evaluation / "owners" / str(ordinal)
            if not _presence(reader, path):
                unfinished = True
                continue
            owner = reader.owner(path)
            sealed = _owner(
                reader,
                state,
                path,
                _object(record["native"]),
                task_controls
                | {
                    location / "evaluation.json": pipeline._sha(definition),
                    evaluation / "context.json": pipeline._sha(native_context),
                },
                no_model=ordinal == len(stages),
            )
            if unfinished and (owner.operations or sealed):
                raise ImproverStudyError("native work skips an unfinished predecessor")
            if not sealed:
                reader.native_configuration(
                    evaluation, ordinal, cast(Path, evidence["answers_path"]), available
                )
                unfinished = True
                continue
            report, attempt = reader.stage(evaluation, ordinal, baseline=False)
            reader.native(
                evaluation, ordinal, report, cast(Path, evidence["answers_path"]), available
            )
            for output in stage["outputs"]:
                name = _path(output["path"])
                available[name] = attempt / "artifacts" / name
    for path in state["checked"]:
        if path.is_relative_to(directory):
            owner = reader.owner(path)
            if (
                owner.manifest["core"] != anchor.manifest["core"]
                or owner.manifest["runtime"] != anchor.manifest["runtime"]
            ):
                raise ImproverStudyError("screen owners changed their original runtime/core")
    if not _presence(reader, directory / "report.json"):
        return None
    if unfinished:
        raise ImproverStudyError("screen publication precedes its original completed stages")
    return shared._read_ref(reader, _reference(reader, directory))


def _witness(
    reader: NativeEvidence,
    state: dict[str, Any],
    parent: dict[str, object],
    directory: Path,
    base: source_screen.SourceScreen,
) -> tuple[Any, dict[str, Any]]:
    treatment = shared._witness_declaration(
        scope=reader.root,
        directory=directory,
        parent=parent,
        base_screen=base,
        proposal_template=state["record"]["proposal_template"],
        review=state["review"],
        expected_runtime_sha256=state["runtime"],
        controls=state["controls"],
        source_copy=True,
    )
    progress = shared._witness_progress_at(reader, treatment)
    state["checked"].update(progress["owner_treatments"])
    state["inactive"] |= progress["inactive_pending"]
    return treatment, progress


def _select(
    state: dict[str, Any], references: list[dict[str, object]], iteration: int
) -> dict[str, Any]:
    selection = state["record"]["selection"]
    return source_screen.select_source_parent(
        references,
        method=selection["method"],
        max_active=selection["max_active"],
        seed=selection["seed"],
        iteration=iteration,
    )


def _parent_source(
    reader: NativeEvidence, state: dict[str, Any], start: int, reference: dict[str, object]
) -> tuple[Path, str]:
    directory = _path_value(reference["directory"])
    if directory.is_relative_to(reader.root / "common"):
        path = reader.root / "inputs/starts" / str(start) / "candidate.py"
    else:
        _, parent = shared._parent_evidence(reader, reference)
        path = (
            _path_value(_object(_object(parent.to_record()["generation"])["roots"])["agent"])
            / "candidate.py"
        )
    raw = reader.raw(path)
    if len(raw) > MAX_SOURCE_BYTES:
        raise ImproverStudyError("measured task parent exceeds the bounded literal source channel")
    raw.decode("utf-8")
    import hashlib

    digest = hashlib.sha256(raw).hexdigest()
    if (
        pipeline._sha({"candidate.py": digest})
        != shared._read_ref(reader, reference)["candidate_id"]
    ):
        raise ImproverStudyError("literal task parent is not its measured original candidate")
    return path, digest


def _plan(
    reader: NativeEvidence,
    state: dict[str, Any],
    coordinate: tuple[int, int, int, int],
    pool: list[dict[str, object]],
    failures: list[dict[str, object]],
    previous: list[dict[str, Any]],
) -> tuple[dict[str, Any], dict[str, Any]]:
    start, _, arm, slot = coordinate
    selection = _select(state, pool, slot)
    matches = [
        ref
        for ref in pool
        if shared._read_ref(reader, ref)["candidate_id"] == selection["selected_id"]
    ]
    if len(matches) != 1:
        raise ImproverStudyError("cell has no unique original eligible selected task parent")
    parent = matches[0]
    location = _location(reader.root, coordinate)
    packet = location / "feedback"
    improver = Selection.from_bytes(
        _json(state["record"]["improvers"][arm]["selection"])
    ).agent_sha256
    bundle = (
        source_feedback._build_failures(
            packet,
            parent,
            failures,
            existing=packet.exists(),
            full_answers=True,
            improver_agent_sha256=improver,
        )
        if failures
        else (source_feedback._build(packet, parent, existing=packet.exists(), full_answers=True))
    )
    hashes = {name + ".json": pipeline._sha(bundle[name]) for name in shared._FILES}
    source_path, source_sha = _parent_source(reader, state, start, parent)
    section = _operator(state["record"], arm, state["screens"][start])
    descriptor = {
        "format": "buddha.candidate-improvement.v2",
        **{
            key: section[key]
            for key in ("config", "entrypoint", "executor", "profile", "runtime", "max_callbacks")
        },
        "parent_agent_sha256": selection["selected_id"],
        "task_parent": {"path": str(source_path), "sha256": source_sha},
        "feedback": {"path": str(packet / "feedback.json"), "sha256": hashes["feedback.json"]},
    }
    plan = {
        "format": _PLAN,
        **dict(zip(_COORD, coordinate, strict=True)),
        "improver_agent_sha256": improver,
        "prior_decisions": [pipeline._sha(row) for row in previous],
        "selection": selection,
        "parent": parent,
        "failures": failures,
        "feedback_sha256": hashes,
        "proposal_descriptor": descriptor,
    }
    return plan, bundle


def _proposal(
    reader: NativeEvidence,
    state: dict[str, Any],
    coordinate: tuple[int, int, int, int],
    plan: dict[str, Any],
) -> dict[str, Any] | None:
    location = _location(reader.root, coordinate)
    root = location / "proposal"
    if not _presence(reader, root):
        return None
    descriptor = plan["proposal_descriptor"]
    expected_context = {
        "format": candidate_improvement.CONTEXT_FORMAT,
        "descriptor": str(location / "proposal.json"),
        "expected_runtime_sha256": state["runtime"],
        "expected_feedback_provenance_sha256": plan["feedback_sha256"]["provenance.json"],
    }
    if reader.raw(location / "proposal.json") != _json(descriptor) or reader.raw(
        root / "context.json"
    ) != _json(expected_context):
        raise ImproverStudyError("counted proposal changes its original descriptor/context")
    section = _operator(state["record"], coordinate[2], state["screens"][coordinate[0]])
    inputs = shared._proposal_controls_for(state["controls"], location, plan) | {
        root / "context.json": pipeline._sha(expected_context),
        _path_value(descriptor["task_parent"]["path"]): _digest(
            descriptor["task_parent"]["sha256"]
        ),
    }
    _ordinals(reader, root / "owners", 0, 1)
    _ordinals(reader, root / "completed", 0, 1, suffix=".json")
    sealed = _owner(reader, state, root / "owners/0", section, inputs)
    if not _presence(reader, root / "report.json"):
        return None
    if not sealed:
        raise ImproverStudyError("counted proposal publication lacks its original completion seal")
    result = shared._read_ref(reader, _reference(reader, root), proposal=True)
    if result["format"] != "buddha.candidate-improvement-stage-report.v2" or (
        result["improver_agent_sha256"] != plan["improver_agent_sha256"]
        or result["parent_agent_sha256"] != plan["proposal_descriptor"]["parent_agent_sha256"]
    ):
        raise ImproverStudyError("proposal changes frozen improver and measured task-parent roles")
    return result


def _coverage(state: dict[str, Any]) -> dict[str, int]:
    record = state["record"]
    common = len(record["starts"]) * record["repetitions"]
    cells = common * 2
    expected = cells * record["descendant_opportunities"]
    completed = len(state["decisions"])
    attempted = state["attempted"]
    return {
        "expected_common": common,
        "completed_common": len(state["common"]),
        "expected_cells": cells,
        "completed_cells": sum(
            len(rows) == record["descendant_opportunities"]
            for rows in state["cell_decisions"].values()
        ),
        "expected_opportunities": expected,
        "attempted_opportunities": attempted,
        "completed_opportunities": completed,
        "in_flight_opportunities": attempted - completed,
        "unattempted_opportunities": expected - attempted,
    }


def _position(
    start: int, repetition: int, arm: int | None, slot: int | None, stage: str
) -> dict[str, object]:
    return dict(zip(_COORD, (start, repetition, arm, slot), strict=True)) | {"stage": stage}


def _set_action(
    state: dict[str, Any], kind: str, directory: Path, position: dict[str, object], **values: Any
) -> None:
    if state["action"] is None:
        state["action"] = {"kind": kind, "directory": directory, "position": position, **values}


def _future(reader: NativeEvidence, path: Path) -> None:
    if _presence(reader, path):
        raise ImproverStudyError("future condition/slot work precedes its completed serial prefix")


def _restore(directory: Path, authorization: Path) -> tuple[NativeEvidence, dict[str, Any]]:
    reader = NativeEvidence(directory, authorization, error_type=ImproverStudyError)
    state = _original(reader)
    _census(reader, state)
    state.update(
        common={},
        cell_decisions={},
        decisions=[],
        attempted=0,
        action=None,
        witnesses=[],
        frozen=None,
        observations=[],
    )
    record = state["record"]
    for start, base in enumerate(state["screens"]):
        for repetition in range(record["repetitions"]):
            location = directory / "common" / str(start) / str(repetition)
            if state["action"] is not None:
                _future(reader, location)
                continue
            screen_root = location / "screen"
            if not _presence(reader, screen_root):
                _set_action(
                    state,
                    "prepare_common",
                    screen_root,
                    _position(start, repetition, None, None, "common_screen"),
                    screen=base,
                )
                continue
            report = _screen(reader, state, screen_root, base)
            if report is None:
                _set_action(
                    state,
                    "screen",
                    screen_root,
                    _position(start, repetition, None, None, "common_screen"),
                )
                continue
            reference = _reference(reader, screen_root)
            if _object(report["admission"])["eligible"] is not True:
                _set_action(
                    state,
                    "common_ineligible",
                    screen_root,
                    _position(start, repetition, None, None, "common_screen"),
                    result=report,
                )
                continue
            treatment, progress = _witness(reader, state, reference, location / "witness", base)
            if progress["result"] is None:
                role = progress["lower_role"]
                stage = "common_witness_" + (
                    "feedback"
                    if progress["needs_prepare"] and role == "proposal"
                    else (role or "publication")
                )
                _set_action(
                    state,
                    "witness",
                    location / "witness",
                    _position(start, repetition, None, None, stage),
                    treatment=treatment,
                )
                continue
            state["witnesses"].append(progress["result"])
            if progress["result"]["status"] != "passed":
                _set_action(
                    state,
                    "common_ineligible",
                    location / "witness",
                    _position(start, repetition, None, None, "common_witness"),
                    result=progress["result"],
                )
                continue
            state["common"][(start, repetition)] = reference
    pools: dict[tuple[int, int, int], list[dict[str, object]]] = {}
    failures: dict[tuple[int, int, int], list[dict[str, object]]] = {}
    known: dict[tuple[int, int, int], set[str]] = {}
    for coordinate in _coordinates(record):
        start, repetition, arm, slot = coordinate
        key = coordinate[:3]
        location = _location(directory, coordinate)
        state["cell_decisions"].setdefault(key, [])
        if state["action"] is not None:
            _future(reader, location)
            continue
        if key not in pools:
            pools[key] = [state["common"][(start, repetition)]]
            failures[key], known[key] = [], {state["screens"][start].candidate_id}
        position = _position(*coordinate, "feedback")
        if not _presence(reader, location / "plan.json"):
            prefix = location.relative_to(directory).as_posix() + "/"
            if any(name.startswith(prefix) for name in reader.capture.entries):
                raise ImproverStudyError("counted work precedes its original checked plan")
            _set_action(
                state,
                "plan",
                location,
                position,
                coordinate=coordinate,
                pool=pools[key],
                failures=failures[key],
                previous=state["cell_decisions"][key],
            )
            continue
        state["attempted"] += 1
        plan, bundle = _plan(
            reader, state, coordinate, pools[key], failures[key], state["cell_decisions"][key]
        )
        if reader.raw(location / "plan.json") != _json(plan):
            raise ImproverStudyError("counted plan changes its original cell/parent/failure prefix")
        ready = _presence(reader, location / "proposal")
        for name in shared._FILES:
            path = location / "feedback" / (name + ".json")
            if (ready or _presence(reader, path)) and reader.raw(path) != _json(bundle[name]):
                raise ImproverStudyError(
                    "counted packet changes its complete original measured data"
                )
        if not ready:
            _set_action(
                state,
                "prepare_proposal",
                location,
                _position(*coordinate, "proposal"),
                coordinate=coordinate,
                plan=plan,
                bundle=bundle,
            )
            continue
        proposal = _proposal(reader, state, coordinate, plan)
        if proposal is None:
            _set_action(
                state, "proposal", location / "proposal", _position(*coordinate, "proposal")
            )
            continue
        status, screen_ref, witness_ref = "rejected", None, None
        identifier = None
        if proposal["disposition"] == "materialized":
            identifier = proposal["child"]["agent_sha256"]
            if identifier in known[key]:
                status = "duplicate"
                if _presence(reader, location / "screen") or _presence(
                    reader, location / "witness"
                ):
                    raise ImproverStudyError(
                        "duplicate counted source executes extra screen/witness work"
                    )
            else:
                child = shared._child_screen_for(
                    state["screens"][start], proposal, location, source_copy=True
                )
                if not _presence(reader, location / "screen"):
                    _set_action(
                        state,
                        "prepare_child",
                        location,
                        _position(*coordinate, "screen"),
                        child=child,
                        proposal=proposal,
                    )
                    continue
                report = _screen(reader, state, location / "screen", child)
                if report is None:
                    _set_action(
                        state, "screen", location / "screen", _position(*coordinate, "screen")
                    )
                    continue
                screen_ref = _reference(reader, location / "screen")
                if report.get("disposition") == "candidate_execution_failed":
                    status = "candidate_execution_failed"
                elif _object(report["admission"])["eligible"] is not True:
                    status = "ineligible"
                else:
                    treatment, progress = _witness(
                        reader, state, screen_ref, location / "witness", state["screens"][start]
                    )
                    if progress["result"] is None:
                        role = progress["lower_role"]
                        stage = "witness_" + (
                            "feedback"
                            if progress["needs_prepare"] and role == "proposal"
                            else (role or "publication")
                        )
                        _set_action(
                            state,
                            "witness",
                            location / "witness",
                            _position(*coordinate, stage),
                            treatment=treatment,
                        )
                        continue
                    state["witnesses"].append(progress["result"])
                    witness_ref = _reference(reader, location / "witness")
                    status = (
                        "admitted"
                        if progress["result"]["status"] == "passed"
                        else "mutation_witness_failed"
                    )
        elif _presence(reader, location / "screen") or _presence(reader, location / "witness"):
            raise ImproverStudyError("rejected proposal executes descendant work")
        decision = {
            "format": _DECISION,
            **dict(zip(_COORD, coordinate, strict=True)),
            "status": status,
            "candidate_id": identifier,
            "improver_agent_sha256": plan["improver_agent_sha256"],
            "parent": plan["parent"],
            "proposal": _reference(reader, location / "proposal"),
            "screen": screen_ref,
            "witness": witness_ref,
        }
        if not _presence(reader, location / "decision.json"):
            _set_action(
                state, "decision", location, _position(*coordinate, "decision"), decision=decision
            )
            continue
        if reader.raw(location / "decision.json") != _json(decision):
            raise ImproverStudyError("decision changes its actual original terminal outcomes")
        state["cell_decisions"][key].append(decision)
        state["decisions"].append(decision)
        if identifier is not None:
            known[key].add(identifier)
        if status == "admitted":
            pools[key].append(cast(dict[str, object], screen_ref))
        elif status == "candidate_execution_failed":
            failures[key].append(
                {"parent": plan["parent"], "proposal": decision["proposal"], "screen": screen_ref}
            )
    state["pools"], state["failures"] = pools, failures
    if state["checked"] != state["owner_paths"]:
        raise ImproverStudyError("a retained owner lacks its original scheduled treatment")
    if state["inactive"]:
        raise ImproverStudyError("an unfinished original owner is inactive")
    state["coverage"] = _coverage(state)
    _observations(reader, state)
    if _presence(reader, directory / "freeze"):
        if state["action"] is not None:
            raise ImproverStudyError("descendant freeze precedes the full terminal grid")
        state["frozen"] = _frozen(reader, state)
    if state["action"] is None:
        _set_action(
            state,
            "freeze" if state["frozen"] is None else "publish",
            directory,
            _position(0, 0, None, None, "publication"),
        )
    reader.capture.finish()
    return reader, state


def _selection_rows(reader: NativeEvidence, state: dict[str, Any]) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for start in range(len(state["record"]["starts"])):
        for repetition in range(state["record"]["repetitions"]):
            for arm in range(2):
                key = start, repetition, arm
                candidates = [
                    row for row in state["cell_decisions"][key] if row["status"] == "admitted"
                ]
                chosen = None
                if candidates:
                    selected = _select(
                        state,
                        [row["screen"] for row in candidates],
                        state["record"]["selection"]["finalist_iteration"],
                    )
                    matches = [
                        row for row in candidates if row["candidate_id"] == selected["selected_id"]
                    ]
                    if len(matches) != 1:
                        raise ImproverStudyError(
                            "final C-only rule has no unique original descendant"
                        )
                    chosen = matches[0]
                ordinal = len(rows)
                selected_source = None
                if chosen is not None:
                    _, selected_screen = shared._parent_evidence(reader, chosen["screen"])
                    selected_selection = Selection.from_bytes(
                        _json(_object(selected_screen.to_record()["generation"])["selection"])
                    )
                    inventory_ = _object(
                        _object(selected_selection.to_record()["components"])["agent"]
                    )
                    selected_source = {
                        "path": str(reader.root / "freeze/sources" / (str(ordinal) + ".py")),
                        "sha256": _digest(inventory_["candidate.py"]),
                    }
                rows.append(
                    {
                        "start": start,
                        "repetition": repetition,
                        "arm": arm,
                        "status": "no_valid_descendant" if chosen is None else "selected",
                        "candidate_id": None if chosen is None else chosen["candidate_id"],
                        "origin": chosen,
                        "source": selected_source,
                    }
                )
    return rows


def _frozen(reader: NativeEvidence, state: dict[str, Any]) -> list[dict[str, Any]]:
    root = reader.root / "freeze"
    if not _presence(reader, root / "confirmation.json"):
        raise ImproverStudyError("partial descendant freeze is poisoned; never repaired")
    rows = _selection_rows(reader, state)
    table = {
        "format": "buddha.improver-study-selections.v1",
        "rows": rows,
        "declaration_sha256": pipeline._sha(state["record"]),
        "claim": _CLAIM,
    }
    if reader.raw(root / "selections.json") != _json(table) or reader.raw(
        root / "confirmation.json"
    ) != _json(
        {"format": "buddha.improver-study-freeze.v1", "selections_sha256": pipeline._sha(table)}
    ):
        raise ImproverStudyError("frozen selections differ from their original counted descendants")
    expected = {"selections.json", "confirmation.json", "sources"}
    prefix = root.relative_to(reader.root).as_posix() + "/"
    actual = {
        name.removeprefix(prefix).split("/")[0]
        for name in reader.capture.entries
        if name.startswith(prefix)
    }
    if actual != expected:
        raise ImproverStudyError("descendant freeze has foreign or missing entries")
    source_prefix = prefix + "sources/"
    actual_sources = {
        name.removeprefix(source_prefix)
        for name in reader.capture.entries
        if name.startswith(source_prefix)
    }
    expected_sources = {str(i) + ".py" for i, row in enumerate(rows) if row["source"] is not None}
    if actual_sources != expected_sources:
        raise ImproverStudyError("frozen source population omits or invents a descendant")
    for row in rows:
        if row["source"] is not None:
            raw = reader.raw(_path_value(row["source"]["path"]), row["source"]["sha256"])
            if len(raw) > MAX_SOURCE_BYTES:
                raise ImproverStudyError("frozen source exceeds the original one-file ceiling")
            raw.decode("utf-8")
    return rows


def _costs(reader: NativeEvidence, state: dict[str, Any]) -> dict[str, Any]:
    values = [(path, reader.owner(path).accounting()) for path in state["owner_paths"]]
    cells = []
    for start in range(len(state["record"]["starts"])):
        for repetition in range(state["record"]["repetitions"]):
            for arm in range(2):
                root = reader.root / "cells" / str(start) / str(repetition) / str(arm)
                totals = _sum([row for path, row in values if path.is_relative_to(root)])
                cap = state["record"]["limits"]["arm_cell"]
                if (
                    totals["committed_microusd"] > cap["budget_microusd"]
                    or totals["operation_count"] > cap["max_calls"]
                ):
                    raise ImproverStudyError(
                        "original arm cell exceeds its immutable allocated ceiling"
                    )
                cells.append({"start": start, "repetition": repetition, "arm": arm, **totals})
    total = _sum([row for _, row in values])
    cap = state["record"]["limits"]["study"]
    if (
        total["committed_microusd"] > cap["budget_microusd"]
        or total["operation_count"] > cap["max_calls"]
    ):
        raise ImproverStudyError("original study exceeds its complete fixed allocation")
    for start in range(len(state["record"]["starts"])):
        for repetition in range(state["record"]["repetitions"]):
            root = reader.root / "common" / str(start) / str(repetition)
            common = _sum([row for path, row in values if path.is_relative_to(root)])
            cap = state["record"]["limits"]["common_cell"]
            if (
                common["committed_microusd"] > cap["budget_microusd"]
                or common["operation_count"] > cap["max_calls"]
            ):
                raise ImproverStudyError("common preparation exceeds its original fixed allocation")
    return {
        "totals": total,
        "common": _sum(
            [row for path, row in values if path.is_relative_to(reader.root / "common")]
        ),
        "cells": cells,
        "witness": _sum(
            [row for path, row in values if "witness" in path.relative_to(reader.root).parts]
        ),
    }


def _result(reader: NativeEvidence, state: dict[str, Any]) -> dict[str, Any]:
    if (
        state["frozen"] is None
        or state["coverage"]["completed_opportunities"]
        != state["coverage"]["expected_opportunities"]
    ):
        raise ImproverStudyError("completion lacks the entire frozen terminal grid")
    return {
        "format": _REPORT,
        "status": "complete",
        "reason": "finite_grid_complete",
        "experiment_id": state["record"]["experiment_id"],
        "coverage": state["coverage"],
        "decisions": state["decisions"],
        "selections": state["frozen"],
        "costs": _costs(reader, state),
        "assessment": {
            "status": "not_ready",
            "target_repair": "not_assessed",
            "reason": state["record"]["assessment"]["reason"],
        },
        "authorization": state["authorization"],
        "provenance": {
            "declaration_sha256": pipeline._sha(state["record"]),
            "context_sha256": pipeline._sha(state["context"]),
            "controls": {str(path): digest for path, digest in state["controls"].items()},
            "observations": {
                value["observation"]: hashlib.sha256(
                    reader.raw(reader.root / _path(value["observation"]))
                ).hexdigest()
                for value in state["observations"]
            },
            "owners": [
                {
                    "directory": str(path),
                    "run_id": reader.owner(path).run_id,
                    "manifest_sha256": reader.owner(path).manifest_sha256,
                    "ledger_sha256": reader.owner(path).ledger_sha256,
                }
                for path in sorted(state["owner_paths"])
            ],
        },
        "claim": _CLAIM,
    }


def _origin(directory: Path, position: dict[str, Any]) -> Path:
    start, repetition = position["start"], position["repetition"]
    arm, slot = position["arm"], position["slot"]
    stage: str = position["stage"]
    if arm is None:
        root = directory / "common" / str(start) / str(repetition)
        if stage == "common_screen":
            return root / "screen"
        if stage.startswith("common_witness_"):
            role = stage.removeprefix("common_witness_")
            if role in {"proposal", "generation"}:
                return root / "witness" / role
            return root / "witness"
        return root / "witness"
    root = _location(directory, (start, repetition, arm, slot))
    if stage in {"proposal", "screen"}:
        return root / stage
    if stage.startswith("witness_"):
        role = stage.removeprefix("witness_")
        return root / "witness" / role if role in {"proposal", "generation"} else root / "witness"
    return root


def _observations(reader: NativeEvidence, state: dict[str, Any]) -> None:
    prefix = "observations/"
    names = {name for name in reader.capture.entries if name.startswith(prefix)}
    if names != {prefix + str(i) + ".json" for i in range(len(names))}:
        raise ImproverStudyError("partial observations have a foreign or noncontiguous prefix")
    expected_coverage = state["coverage"]
    order = list(_coordinates(state["record"]))
    for index in range(len(names)):
        path = reader.root / "observations" / (str(index) + ".json")
        value = _object(
            _load(reader.raw(path)),
            {
                "format",
                "status",
                "reason",
                "position",
                "child",
                "coverage",
                "authorization",
                "observation",
                "declaration_sha256",
                "claim",
            },
        )
        if (
            reader.raw(path) != _json(value)
            or value["format"] != _OBSERVATION
            or value["status"] != "incomplete"
            or (
                value["declaration_sha256"] != pipeline._sha(state["record"])
                or value["observation"] != path.relative_to(reader.root).as_posix()
                or value["claim"] != _CLAIM
            )
        ):
            raise ImproverStudyError("partial observation changed its original study identity")
        position = _object(value["position"], {*_COORD, "stage"})
        start = _integer(position["start"], 0, len(state["record"]["starts"]) - 1)
        repetition = _integer(position["repetition"], 0, state["record"]["repetitions"] - 1)
        stage = position["stage"]
        if type(stage) is not str or stage not in {
            "common_screen",
            "common_witness",
            "common_witness_feedback",
            "common_witness_proposal",
            "common_witness_generation",
            "common_witness_publication",
            "feedback",
            "proposal",
            "screen",
            "witness_feedback",
            "witness_proposal",
            "witness_generation",
            "witness_publication",
            "decision",
            "publication",
        }:
            raise ImproverStudyError("partial changes its original lower-stage position")
        coverage = {
            key: _integer(item, 0)
            for key, item in _object(value["coverage"], set(expected_coverage)).items()
        }
        for key, actual in coverage.items():
            _integer(actual, 0)
            if key.startswith("expected_") and actual != expected_coverage[key]:
                raise ImproverStudyError("partial erases a declared population denominator")
        completed, inflight = (
            coverage["completed_opportunities"],
            coverage["in_flight_opportunities"],
        )
        if (
            inflight not in {0, 1}
            or coverage["attempted_opportunities"] != completed + inflight
            or (
                completed + inflight + coverage["unattempted_opportunities"]
                != coverage["expected_opportunities"]
                or completed > expected_coverage["completed_opportunities"]
                or coverage["attempted_opportunities"]
                > expected_coverage["attempted_opportunities"]
                or coverage["completed_common"] > expected_coverage["completed_common"]
                or coverage["completed_cells"] > expected_coverage["completed_cells"]
            )
        ):
            raise ImproverStudyError("partial coverage contradicts the durable original prefix")
        if position["arm"] is None:
            if stage == "publication":
                if (
                    position != _position(0, 0, None, None, "publication")
                    or completed != coverage["expected_opportunities"]
                    or inflight
                ):
                    raise ImproverStudyError(
                        "publication partial lacks its entire completed prefix"
                    )
                completed_common = coverage["expected_common"]
            else:
                if (
                    not stage.startswith("common_")
                    or position["slot"] is not None
                    or completed
                    or inflight
                ):
                    raise ImproverStudyError("common partial invents counted opportunity work")
                completed_common = start * state["record"]["repetitions"] + repetition
        else:
            _integer(position["arm"], 0, 1)
            _integer(position["slot"], 0, state["record"]["descendant_opportunities"] - 1)
            saved_coordinate = tuple(position[key] for key in _COORD)
            if (
                stage.startswith("common_")
                or stage == "publication"
                or completed >= len(order)
                or order[completed] != saved_coordinate
                or inflight != int(stage != "feedback")
                or (
                    inflight
                    and not _presence(
                        reader, _location(reader.root, order[completed]) / "plan.json"
                    )
                )
            ):
                raise ImproverStudyError("partial skips its original serial opportunity")
            completed_common = coverage["expected_common"]
        prefix_cells: dict[tuple[int, int, int], int] = {}
        for coordinate in order[:completed]:
            cell = coordinate[:3]
            prefix_cells[cell] = prefix_cells.get(cell, 0) + 1
        if (
            coverage["completed_common"] != completed_common
            or coverage["completed_cells"]
            != sum(
                count == state["record"]["descendant_opportunities"]
                for count in prefix_cells.values()
            )
            or (
                state["observations"]
                and any(
                    coverage[key] < state["observations"][-1]["coverage"][key]
                    for key in (
                        "completed_common",
                        "completed_opportunities",
                        "attempted_opportunities",
                    )
                )
            )
        ):
            raise ImproverStudyError("partial changes its exact historical completed prefix")
        child = value["child"]
        required: set[str] = set()
        if child is not None:
            child = _object(child)
            origin = _origin(reader.root, position)
            child_path = (
                origin / _path(child["observation"])
                if child.get("status") == "incomplete"
                else origin / "report.json"
            )
            if (
                reader.raw(child_path) != _json(child)
                or child["reason"] != value["reason"]
                and value["reason"] != "common_ineligible"
            ):
                raise ImproverStudyError("partial changes the original returned lower observation")
            if "owner" in child:
                path = _path_value(child["owner"])
                if path != origin / "owners/0" or path not in state["owner_paths"]:
                    raise ImproverStudyError("partial names a replacement original owner")
                required.add(reader.owner(path).run_id)
        # Historical partial owners may subsequently complete and deactivate.
        # Require their original presence while checking monotonic history.
        pipeline.validate_authorization_snapshot(
            value["authorization"], state["authorization"], set()
        )
        if not required <= {
            row["run_id"] for row in cast(dict[str, Any], value["authorization"])["runs"]
        }:
            raise ImproverStudyError("partial omits its referenced original owner")
        state["observations"].append(value)


def _observe(
    directory: Path,
    state: dict[str, Any],
    authority: Authorization,
    reason: str,
    child: dict[str, object] | None,
) -> dict[str, Any]:
    ordinal = len(state["observations"])
    path = directory / "observations" / (str(ordinal) + ".json")
    value = {
        "format": _OBSERVATION,
        "status": "incomplete",
        "reason": reason,
        "position": state["action"]["position"],
        "child": child,
        "coverage": state["coverage"],
        "authorization": authority.summary(),
        "observation": path.relative_to(directory).as_posix(),
        "declaration_sha256": pipeline._sha(state["record"]),
        "claim": _CLAIM,
    }
    pipeline._write(path, _json(value))
    return value


def _write_plan(
    directory: Path, state: dict[str, Any], action: dict[str, Any], authorization: Path
) -> None:
    location = action["directory"]
    location.mkdir(parents=True, exist_ok=True)
    _root(location)
    reader = NativeEvidence(directory, authorization, error_type=ImproverStudyError)
    plan, bundle = _plan(
        reader, state, action["coordinate"], action["pool"], action["failures"], action["previous"]
    )
    reader.capture.finish()
    pipeline._same_or_write(location / "plan.json", _json(plan))
    shared._write_packet(location / "feedback", plan, bundle)
    pipeline._same_or_write(location / "proposal.json", _json(plan["proposal_descriptor"]))


def _prepare_proposal(
    state: dict[str, Any], action: dict[str, Any], authority: Authorization
) -> None:
    location, plan = action["directory"], action["plan"]
    shared._write_packet(location / "feedback", plan, action["bundle"])
    pipeline._same_or_write(location / "proposal.json", _json(plan["proposal_descriptor"]))
    coordinate = action["coordinate"]
    section = _operator(state["record"], coordinate[2], state["screens"][coordinate[0]])
    inputs = shared._proposal_controls_for(state["controls"], location, plan)
    candidate_improvement.prepare_candidate_improvement(
        location / "proposal",
        descriptor=location / "proposal.json",
        selection=Selection.from_bytes(_json(section["selection"])),
        roots=source_screen._roots(section),
        authorization=authority,
        review=state["review"],
        budget_microusd=section["budget_microusd"],
        max_calls=section["max_calls"],
        expected_runtime_sha256=state["runtime"],
        expected_feedback_provenance_sha256=plan["feedback_sha256"]["provenance.json"],
        input_files=list(inputs),
        expected_input_hashes=inputs,
    )


def _freeze(reader: NativeEvidence, state: dict[str, Any]) -> None:
    rows = _selection_rows(reader, state)
    sources = []
    for row in rows:
        if row["source"] is None:
            continue
        _, parent = shared._parent_evidence(reader, row["origin"]["screen"])
        source = (
            _path_value(_object(_object(parent.to_record()["generation"])["roots"])["agent"])
            / "candidate.py"
        )
        raw = reader.raw(source, row["source"]["sha256"])
        if len(raw) > MAX_SOURCE_BYTES:
            raise ImproverStudyError("selected descendant exceeds its declared source ceiling")
        raw.decode("utf-8")
        sources.append((_path_value(row["source"]["path"]), raw))
    reader.capture.finish()
    root = reader.root / "freeze"
    if root.exists() or root.is_symlink():
        raise ImproverStudyError("existing partial descendant freeze is not repaired")
    root.mkdir()
    (root / "sources").mkdir()
    for path, raw in sources:
        pipeline._write(path, raw)
    table = {
        "format": "buddha.improver-study-selections.v1",
        "rows": rows,
        "declaration_sha256": pipeline._sha(state["record"]),
        "claim": _CLAIM,
    }
    pipeline._write(root / "selections.json", _json(table))
    pipeline._write(
        root / "confirmation.json",
        _json(
            {"format": "buddha.improver-study-freeze.v1", "selections_sha256": pipeline._sha(table)}
        ),
    )


@_checked
def inspect_improver_study(
    directory: Path, *, authorization: Path, expected_report_sha256: str
) -> dict[str, object]:
    if not isinstance(directory, Path) or not isinstance(authorization, Path):
        raise ImproverStudyError("inspection requires explicit original paths")
    directory, authorization = _path_value(str(directory)), _path_value(str(authorization))
    expected = _digest(expected_report_sha256)
    reader, state = _restore(directory, authorization)
    report = _result(reader, state)
    raw = reader.raw(directory / "report.json", expected)
    saved = _load(raw)
    pipeline.validate_authorization_snapshot(
        saved["authorization"],
        state["authorization"],
        {reader.owner(path).run_id for path in state["owner_paths"]},
    )
    if raw != _json(report | {"authorization": saved["authorization"]}):
        raise ImproverStudyError("complete report differs from the original entire finite study")
    reader.capture.finish()
    return saved


@_checked
def run_improver_study(directory: Path, *, transport: RawHTTPTransport) -> dict[str, object]:
    if not isinstance(directory, Path) or not isinstance(transport, RawHTTPTransport):
        raise ImproverStudyError("execution needs an explicit study and raw transport")
    directory = _path_value(str(directory))
    context = _context(directory)
    authorization = _path_value(context["authorization"])
    if (directory / "report.json").exists():
        return inspect_improver_study(
            directory,
            authorization=authorization,
            expected_report_sha256=file_hash(directory / "report.json"),
        )
    authority = Authorization(authorization)
    with (
        trial_fence.work(authorization, authority._terms(), directory=directory, kind="search"),
        pipeline._exclusive(directory),
    ):
        while True:
            reader, state = _restore(directory, authorization)
            _check_current(state)
            action = state["action"]
            kind, location = action["kind"], action["directory"]
            unknown = any(
                row["status"] != "completed"
                for row in reader._rows(state["funding"]["auth_operations"])
            )
            if unknown:
                if state["observations"] and state["observations"][-1]["reason"] == "unknown":
                    return cast(dict[str, object], state["observations"][-1])
                raise ImproverStudyError(
                    "unresolved original liability lacks its recorded lower stop"
                )
            if kind == "common_ineligible":
                return _observe(directory, state, authority, "common_ineligible", action["result"])
            try:
                child = None
                if kind == "prepare_common":
                    location.parent.mkdir(parents=True, exist_ok=True)
                    _root(location.parent)
                    source_screen.prepare_source_screen(
                        location,
                        screen=action["screen"],
                        authorization=authority,
                        review=state["review"],
                        expected_runtime_sha256=state["runtime"],
                        input_bindings=state["controls"],
                    )
                elif kind == "plan":
                    _write_plan(directory, state, action, authorization)
                elif kind == "prepare_proposal":
                    _prepare_proposal(state, action, authority)
                elif kind == "proposal":
                    child = candidate_improvement.run_candidate_improvement(
                        location, transport=transport
                    )
                elif kind == "prepare_child":
                    shared._materialize_child_source_for(
                        state["screens"][action["position"]["start"]],
                        action["proposal"],
                        location,
                        owner_directory=location / "screen",
                        source_copy=True,
                    )
                    source_screen.prepare_source_screen(
                        location / "screen",
                        screen=action["child"],
                        authorization=authority,
                        review=state["review"],
                        expected_runtime_sha256=state["runtime"],
                        input_bindings=state["controls"],
                    )
                elif kind == "screen":
                    child = source_screen.run_source_screen(location, transport=transport)
                elif kind == "witness":
                    step = shared._advance_witness(
                        reader, action["treatment"], authorization=authority, transport=transport
                    )
                    if step["action"] == "incomplete":
                        child = cast(dict[str, object], step["result"])
                elif kind == "decision":
                    pipeline._same_or_write(location / "decision.json", _json(action["decision"]))
                elif kind == "freeze":
                    _freeze(reader, state)
                elif kind == "publish":
                    result = _result(reader, state)
                    return pipeline.publish_complete(
                        directory / "report.json",
                        result,
                        authority,
                        {reader.owner(path).run_id for path in state["owner_paths"]},
                    )
                else:
                    raise ImproverStudyError("finite study has no checked next operation")
                if child is not None and child["status"] != "complete":
                    _, observed = _restore(directory, authorization)
                    _check_current(observed)
                    return _observe(
                        directory, observed, authority, cast(str, child["reason"]), child
                    )
            except source_feedback.SourceFeedbackTooLarge:
                _, observed = _restore(directory, authorization)
                _check_current(observed)
                return _observe(directory, observed, authority, "feedback_capacity", None)
            except KeyboardInterrupt:
                _, observed = _restore(directory, authorization)
                _observe(directory, observed, authority, "cancelled", None)
                raise
