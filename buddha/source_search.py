"""Bounded inherited source search over one fixed development comparison.

Nested screens and proposal stages retain their original owners and anchors.
This controller allocates work; it introduces no broker or scientific score.
"""

import hashlib
import re
import sqlite3
import stat
from collections.abc import Callable, Mapping
from functools import wraps
from pathlib import Path
from typing import Any, cast

from buddha import (
    candidate_generation,
    candidate_improvement,
    gateway,
    source_feedback,
    source_screen,
    trial_fence,
)
from buddha import native_pipeline as pipeline
from buddha.answers import _Artifact
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
    inventory,
    prepare_selection,
)
from buddha.wire import _integer

_FORMAT = "buddha.source-search.v1"
_COPY_MANIFEST = "buddha.source-search-manifest.v4"
_MANIFEST = _COPY_MANIFEST
_WITNESS_MANIFEST = "buddha.source-search-manifest.v3"
_FULL_MANIFEST = "buddha.source-search-manifest.v2"
_LEGACY_MANIFEST = "buddha.source-search-manifest.v1"
_CONTEXT = "buddha.source-search-context.v1"
_PLAN = "buddha.source-search-plan.v1"
_REPORT = "buddha.source-search-report.v1"
_CLAIM = "bounded development source allocation only; no semantic or scientific improvement claim"
_FILES = ("source", "split", "feedback", "provenance")
_TOTALS = ("spent_microusd", "reserved_microusd", "committed_microusd", "operation_count")
MUTATION_WITNESS_POLICY = {
    "format": "buddha.source-mutation-witness.v1",
    "task_policy": "first_ordered_development_task",
    "depth": 1,
}
SOURCE_COPY_POLICY = {
    "format": "buddha.source-copy.v1",
    "method": "verified_private_snapshot_before_owner",
}


def _has_witness(state: dict[str, Any]) -> bool:
    return bool(state["record"]["format"] in {_COPY_MANIFEST, _WITNESS_MANIFEST})


def _has_source_copy(state: dict[str, Any]) -> bool:
    return bool(state["record"]["format"] == _COPY_MANIFEST)


def _source_copy_choice(mutation_witness: bool, source_copy: bool | None) -> bool:
    if type(mutation_witness) is not bool or (
        source_copy is not None and type(source_copy) is not bool
    ):
        raise SourceSearchError("source copy requires a literal boolean or the witnessed default")
    enabled = mutation_witness if source_copy is None else source_copy
    if enabled and not mutation_witness:
        raise SourceSearchError("source copy requires the fixed bounded mutation witness")
    return enabled


def _full_answers(state: dict[str, Any]) -> bool:
    return bool(state["record"]["format"] != _LEGACY_MANIFEST)


class SourceSearchError(ReleaseError):
    """The original search, fixed comparison or retained custody is invalid."""


class SourceSearchStopped(SourceSearchError):
    """Protocol stop carrying the exact durably saved partial observation."""

    def __init__(self, partial: dict[str, object]):
        self._partial = _json(partial)
        super().__init__("source execution stopped; original saved observation retained")

    @property
    def partial(self) -> dict[str, object]:
        return _load(self._partial)


class SourceSearchInterrupted(KeyboardInterrupt):
    """Cancellation carrying saved evidence without scanning a latest log."""

    def __init__(self, partial: dict[str, object]):
        self._partial = _json(partial)
        super().__init__("source execution cancelled; original saved observation retained")

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
            if isinstance(error, (SourceSearchError, source_feedback.SourceFeedbackTooLarge)):
                raise
            raise SourceSearchError(
                "source search configuration or retained evidence is invalid"
            ) from None

    return checked


class SourceSearchSpec(_Artifact):
    """Immutable bounded allocation parameters, using existing archive methods."""

    @_checked
    def __post_init__(self) -> None:
        record = _object(_load(self.data), {"format", "iterations", "method", "seed", "max_active"})
        if record["format"] != _FORMAT or record["method"] not in {
            "archive",
            "latest",
            "uninformed",
        }:
            raise SourceSearchError("unsupported source search specification")
        _integer(record["iterations"], 1, 8)
        _integer(record["seed"], 0)
        _integer(record["max_active"], 2, 64)
        object.__setattr__(self, "data", _json(record))


def _witness_path(value: object) -> Path:
    path = pipeline._absolute(value)
    if str(path) != value or ".." in path.parts:
        raise SourceSearchError("witness paths must be canonical without traversal")
    for part in path.parts[1:]:
        _path(part)
    return path


class _WitnessTreatment(_Artifact):
    """Immutable witness inputs; construction inspects no filesystem or owner."""

    @_checked
    def __post_init__(self) -> None:
        record = _object(
            _load(self.data),
            {
                "format",
                "scope",
                "directory",
                "parent",
                "base_screen",
                "proposal_template",
                "review",
                "expected_runtime_sha256",
                "controls",
                "source_copy",
                "policy",
            },
        )
        if record["format"] != "buddha.source-mutation-witness-treatment.v1" or (
            _json(record["policy"]) != _json(MUTATION_WITNESS_POLICY)
            or type(record["source_copy"]) is not bool
        ):
            raise SourceSearchError("unsupported bounded witness treatment")
        scope, directory = _witness_path(record["scope"]), _witness_path(record["directory"])
        parent = _object(record["parent"], {"directory", "authorization", "report_sha256"})
        parent_directory = _witness_path(parent["directory"])
        authority = _witness_path(parent["authorization"])
        _digest(parent["report_sha256"])
        if (
            directory == scope
            or not directory.is_relative_to(scope)
            or (
                not parent_directory.is_relative_to(scope)
                or directory.is_relative_to(parent_directory)
                or parent_directory.is_relative_to(directory)
                or directory.is_relative_to(authority)
                or authority.is_relative_to(directory)
            )
        ):
            raise SourceSearchError("witness output overlaps its original scope or evidence")
        base = source_screen.SourceScreen.from_bytes(_json(record["base_screen"]))
        generation = _object(base.to_record()["generation"])
        if base.to_record()["format"] != "buddha.source-screen.v2" or (
            generation["entrypoint"] != "candidate.py"
        ):
            raise SourceSearchError("witness needs a failure-aware one-file comparison")
        _template_screen(base, _template(record["proposal_template"]))
        _review(_object(record["review"]))
        runtime = _digest(record["expected_runtime_sha256"])
        controls = _object(record["controls"])
        if not 1 <= len(controls) <= 1024:
            raise SourceSearchError("witness needs bounded original common controls")
        paths = [_witness_path(path) for path in controls]
        if len(set(paths)) != len(paths):
            raise SourceSearchError("witness controls repeat an aliased path")
        for digest in controls.values():
            _digest(digest)
        if _object(generation["runtime"])["sha256"] != runtime or (
            controls.get(str(_witness_path(_object(generation["runtime"])["path"]))) != runtime
        ):
            raise SourceSearchError("witness controls omit independent runtime approval")
        protected = [*paths, authority]
        for role in ("generation", "native"):
            protected.extend(source_screen._roots(_object(base.to_record()[role])).values())
        if any(
            directory.is_relative_to(path) or path.is_relative_to(directory) for path in protected
        ):
            raise SourceSearchError("witness output overlaps an original selected input")
        object.__setattr__(self, "data", _json(record))


@_checked
def _witness_declaration(
    *,
    scope: Path,
    directory: Path,
    parent: dict[str, object],
    base_screen: source_screen.SourceScreen,
    proposal_template: dict[str, object],
    review: dict[str, object],
    expected_runtime_sha256: str,
    controls: Mapping[Path, str],
    source_copy: bool,
) -> _WitnessTreatment:
    if (
        not isinstance(scope, Path)
        or not isinstance(directory, Path)
        or (
            type(base_screen) is not source_screen.SourceScreen
            or any(not isinstance(path, Path) for path in controls)
        )
    ):
        raise SourceSearchError("witness requires explicit paths and immutable comparison")
    return _WitnessTreatment.from_bytes(
        _json(
            {
                "format": "buddha.source-mutation-witness-treatment.v1",
                "scope": str(scope),
                "directory": str(directory),
                "parent": parent,
                "base_screen": base_screen.to_record(),
                "proposal_template": proposal_template,
                "review": review,
                "expected_runtime_sha256": expected_runtime_sha256,
                "controls": {str(path): digest for path, digest in controls.items()},
                "source_copy": source_copy,
                "policy": dict(MUTATION_WITNESS_POLICY),
            }
        )
    )


def _search_witness_treatment(
    reader: NativeEvidence, state: dict[str, Any], reference: dict[str, object]
) -> _WitnessTreatment:
    return _witness_declaration(
        scope=reader.root,
        directory=_witness_location(reader, reference),
        parent=reference,
        base_screen=state["screen"],
        proposal_template=state["record"]["proposal_template"],
        review=state["record"]["review"],
        expected_runtime_sha256=state["record"]["expected_runtime_sha256"],
        controls=state["controls"],
        source_copy=_has_source_copy(state),
    )


def _witness_controls(treatment: _WitnessTreatment) -> dict[Path, str]:
    return {
        Path(path): _digest(digest)
        for path, digest in _object(treatment.to_record()["controls"]).items()
    }


def _sources() -> list[Path]:
    return sorted(
        set(
            source_screen._sources()
            + candidate_improvement._sources()
            + [
                Path(__file__).absolute(),
                Path(source_feedback.__file__).absolute(),
            ]
        )
    )


def _template(value: object) -> dict[str, Any]:
    record = _object(value, {"config", "profile", "max_callbacks", "budget_microusd", "max_calls"})
    _object(
        record["config"], {"provider", "model", "max_output_tokens", "instructions", "sampling"}
    )
    _object(record["profile"], {"capability", "profile_id"})
    _integer(record["max_callbacks"], 0, 1000)
    _integer(record["budget_microusd"], 1)
    _integer(record["max_calls"], 1)
    return record


def _template_screen(
    screen: source_screen.SourceScreen, template: dict[str, Any]
) -> source_screen.SourceScreen:
    record = screen.to_record()
    _object(record["generation"]).update(template)
    return source_screen.SourceScreen.from_bytes(_json(record))


def _ref(directory: Path, authorization: Path) -> dict[str, object]:
    return {
        "directory": str(directory),
        "authorization": str(authorization),
        "report_sha256": file_hash(directory / "report.json"),
    }


def _read_ref(
    reader: NativeEvidence, value: object, *, proposal: bool = False, capture: bool = False
) -> dict[str, Any]:
    if type(capture) is not bool or (capture and proposal):
        raise SourceSearchError("nested byte capture requires a screen and explicit boolean")
    reference = _object(value, {"directory", "authorization", "report_sha256"})
    directory = pipeline._absolute(reference["directory"])
    if reference["authorization"] != str(reader.authorization) or not directory.is_relative_to(
        reader.root
    ):
        raise SourceSearchError("a nested result belongs to another search or authority")
    expected = _digest(reference["report_sha256"])
    function = (
        candidate_improvement.inspect_candidate_improvement
        if proposal
        else source_screen.inspect_source_screen
    )
    if capture:
        result = source_screen.inspect_source_screen(
            directory,
            authorization=reader.authorization,
            expected_report_sha256=expected,
            sink=reader.capture,
        )
    else:
        result = function(
            directory, authorization=reader.authorization, expected_report_sha256=expected
        )
    if _json(result) != reader.raw(directory / "report.json", expected):
        raise SourceSearchError("returned nested result differs from its saved canonical report")
    return result


def _controls(
    record: dict[str, Any], directory: Path, manifest_raw: bytes, context_raw: bytes
) -> dict[Path, str]:
    values = {pipeline._absolute(p): _digest(h) for p, h in _object(record["controls"]).items()}
    return values | {
        directory / "manifest.json": pipeline._sha(_load(manifest_raw)),
        directory / "context.json": pipeline._sha(_load(context_raw)),
    }


def _original(reader: NativeEvidence) -> dict[str, Any]:
    anchor = reader.owner(reader.root / "seed/tasks/0/generation/owners/0")
    manifest_raw = reader.bound(anchor, reader.root / "manifest.json")
    value = _load(manifest_raw)
    record = _object(
        value,
        {
            "format",
            "seed_screen",
            "proposal_template",
            "spec",
            "authorization",
            "review",
            "expected_runtime_sha256",
            "controls",
        }
        | (
            {"mutation_witness"}
            if value.get("format") in {_COPY_MANIFEST, _WITNESS_MANIFEST}
            else set()
        )
        | ({"source_copy"} if value.get("format") == _COPY_MANIFEST else set()),
    )
    context_raw = reader.bound(anchor, reader.root / "context.json")
    context = _object(_load(context_raw), {"format", "manifest_sha256"})
    if (
        record["format"]
        not in {_COPY_MANIFEST, _WITNESS_MANIFEST, _FULL_MANIFEST, _LEGACY_MANIFEST}
        or context["format"] != _CONTEXT
        or context["manifest_sha256"] != pipeline._sha(record)
        or manifest_raw != _json(record)
        or context_raw != _json(context)
        or record["authorization"] != str(reader.authorization)
    ):
        raise SourceSearchError("search differs from its original first-owner declaration")
    if record["format"] in {_COPY_MANIFEST, _WITNESS_MANIFEST} and _json(
        record["mutation_witness"]
    ) != _json(MUTATION_WITNESS_POLICY):
        raise SourceSearchError("search changes its fixed bounded mutation witness")
    if record["format"] == _COPY_MANIFEST and _json(record["source_copy"]) != _json(
        SOURCE_COPY_POLICY
    ):
        raise SourceSearchError("search changes its fixed verified source-copy policy")
    if _json(_review(_object(record["review"]))) != _json(anchor.manifest["review"]):
        raise SourceSearchError("search review differs from its original first owner")
    screen = source_screen.SourceScreen.from_bytes(_json(record["seed_screen"]))
    if (
        screen.to_record()["format"] != "buddha.source-screen.v2"
        or _object(screen.to_record()["generation"])["entrypoint"] != "candidate.py"
    ):
        raise SourceSearchError("search requires its prospective one-file failure-aware seed")
    spec = SourceSearchSpec.from_bytes(_json(record["spec"]))
    _template_screen(screen, _template(record["proposal_template"]))
    controls = _controls(record, reader.root, manifest_raw, context_raw)
    original = reader._bindings(anchor)
    if any(original.get(str(path)) != expected for path, expected in controls.items()):
        raise SourceSearchError("first owner omitted an original search control")
    # Installed helpers are identities in original metadata, never retired code reads.
    names = {
        path.name
        for path in candidate_generation._recorded_sources(_sources(), anchor.manifest["core"])
    }
    candidates = {p.parent for p in controls if p.name == "source_search.py"}
    if len(candidates) != 1 or not all(next(iter(candidates)) / name in controls for name in names):
        raise SourceSearchError("original search controls omit the installed helper closure")
    return {
        "record": record,
        "screen": screen,
        "spec": spec.to_record(),
        "controls": controls,
        "manifest_sha256": pipeline._sha(record),
        "context_sha256": pipeline._sha(context),
    }


def _census(
    reader: NativeEvidence, state: dict[str, Any]
) -> tuple[dict[str, Any], list[dict[str, object]]]:
    count = len(state["screen"].tasks.tasks)
    stages = len(state["screen"].to_record()["stages"])
    owner_paths = []
    for name in reader.capture.entries:
        if not name.endswith("/owners/0/manifest.json") and not re.search(
            r"/owners/[1-9][0-9]*/manifest.json$", name
        ):
            continue
        ordinal = r"(0|[1-9][0-9]*)"
        match = re.fullmatch(
            rf"(?:seed|iterations/{ordinal}/screen)/tasks/{ordinal}/(generation|evaluation)/owners/{ordinal}/manifest.json",
            name,
        )
        proposal = re.fullmatch(rf"iterations/{ordinal}/proposal/owners/0/manifest.json", name)
        witness = re.fullmatch(
            rf"(?:seed-witness|iterations/{ordinal}/witness)/(proposal|generation)/owners/0/manifest.json",
            name,
        )
        if match:
            iteration, task, role, index = match.groups()
            if (
                iteration is not None
                and int(iteration) >= state["spec"]["iterations"]
                or int(task) >= count
                or (role == "generation" and int(index) != 0)
                or (role == "evaluation" and not 1 <= int(index) <= stages)
            ):
                raise SourceSearchError("retained owner is outside the fixed search schedule")
        elif witness and _has_witness(state):
            if (
                witness.group(1) is not None
                and int(witness.group(1)) >= state["spec"]["iterations"]
            ):
                raise SourceSearchError("witness owner exceeds the fixed search schedule")
        elif not proposal or int(proposal.group(1)) >= state["spec"]["iterations"]:
            raise SourceSearchError("retained owner is outside the fixed search schedule")
        owner_paths.append(reader.root / name.removesuffix("/manifest.json"))
    owner_paths.sort()
    owners = [reader.owner(path) for path in owner_paths]
    funded = _authority(reader.capture, reader.authorization, owners)
    if funded is None:
        raise SourceSearchError("search lacks its existing shared authority")
    for value in reader._rows(funded["auth_runs"]):
        path = pipeline._absolute(value["directory"])
        if path.is_relative_to(reader.root) and not any(
            path == owner.directory and value["run_id"] == owner.run_id for owner in owners
        ):
            raise SourceSearchError("a retained funded search owner is missing or replaced")
    current = authority_observation(reader.capture, reader.authorization, funded)
    trial_fence.require_purpose(
        reader.authorization,
        _object(funded["config"]),
        directory=reader.root,
        expected="source screen: " + state["screen"].comparison_key(),
    )
    refs: list[dict[str, object]] = [
        {
            "directory": str(path),
            "run_id": owner.run_id,
            "manifest_sha256": owner.manifest_sha256,
            "ledger_sha256": owner.ledger_sha256,
            "totals": {name: owner.accounting()[name] for name in _TOTALS},
        }
        for path, owner in zip(owner_paths, owners, strict=True)
    ]
    return current, refs


def _select(refs: list[dict[str, object]], spec: dict[str, Any], iteration: int) -> dict[str, Any]:
    return source_screen.select_source_parent(
        refs,
        method=spec["method"],
        max_active=spec["max_active"],
        seed=spec["seed"],
        iteration=iteration,
    )


def _bundle(
    directory: Path,
    parent: dict[str, object],
    failures: list[dict[str, object]],
    *,
    full_answers: bool,
) -> dict[str, Any]:
    if failures:
        return source_feedback._build_failures(
            directory, parent, failures, existing=directory.exists(), full_answers=full_answers
        )
    return source_feedback._build(
        directory, parent, existing=directory.exists(), full_answers=full_answers
    )


def _parent_evidence(
    reader: NativeEvidence, reference: dict[str, object]
) -> tuple[dict[str, Any], source_screen.SourceScreen]:
    root = pipeline._absolute(reference["directory"])
    report = _read_ref(reader, reference)
    raw = reader.raw(root / "screen.json", report["screen_sha256"])
    return report, source_screen.SourceScreen.from_bytes(raw)


def _parent_screen(
    reader: NativeEvidence, reference: dict[str, object]
) -> source_screen.SourceScreen:
    return _parent_evidence(reader, reference)[1]


def _plan(
    reader: NativeEvidence,
    state: dict[str, Any],
    iteration: int,
    refs: list[dict[str, object]],
    failures: list[dict[str, object]],
) -> dict[str, Any]:
    selection = _select(refs, state["spec"], iteration)
    selected = selection["selected_id"]
    parents = [ref for ref in refs if _read_ref(reader, ref)["candidate_id"] == selected]
    if len(parents) != 1:
        raise SourceSearchError("search has no unique eligible selected parent")
    parent = parents[0]
    generation = _object(_parent_screen(reader, parent).to_record()["generation"])
    location = reader.root / "iterations" / str(iteration)
    bundle = _bundle(location / "feedback", parent, failures, full_answers=_full_answers(state))
    hashes = {name + ".json": pipeline._sha(bundle[name]) for name in _FILES}
    template = state["record"]["proposal_template"]
    descriptor = {
        "format": "buddha.candidate-improvement.v1",
        **{name: generation[name] for name in ("entrypoint", "runtime", "executor")},
        **{name: template[name] for name in ("config", "profile", "max_callbacks")},
        "parent_agent_sha256": selected,
        "feedback": {
            "path": str(location / "feedback/feedback.json"),
            "sha256": hashes["feedback.json"],
        },
    }
    return {
        "format": "buddha.source-search-plan.v2" if _has_witness(state) else _PLAN,
        "iteration": iteration,
        "prior_pool": refs,
        "selection": selection,
        "parent": parent,
        "failures": failures,
        "feedback_sha256": hashes,
        "proposal_descriptor": descriptor,
        **(
            {"parent_witness": _witness_reference(reader, state, parent)}
            if _has_witness(state)
            else {}
        ),
    }


def _child_screen_for(
    base_screen: source_screen.SourceScreen,
    proposal: dict[str, Any],
    location: Path,
    *,
    source_copy: bool,
) -> source_screen.SourceScreen:
    record = base_screen.to_record()
    child = _object(proposal["child"])
    generation = _object(record["generation"])
    selection = _object(generation["selection"])
    _object(selection["components"])["agent"] = {"candidate.py": child["source_sha256"]}
    agent = str(location / "agent") if source_copy else child["directory"]
    _object(generation["roots"])["agent"] = agent
    _object(generation["executor"])["mounts"] = [
        ["/agent", agent],
        ["/runner", _object(generation["roots"])["runner"]],
    ]
    record["lineage"] = child["lineage"]
    screen = source_screen.SourceScreen.from_bytes(_json(record))
    if (
        screen.candidate_id != child["agent_sha256"]
        or screen.comparison_key() != base_screen.comparison_key()
    ):
        raise SourceSearchError("materialized child changes the fixed source comparison")
    return screen


def _child_screen(
    state: dict[str, Any], proposal: dict[str, Any], location: Path
) -> source_screen.SourceScreen:
    return _child_screen_for(
        state["screen"], proposal, location, source_copy=_has_source_copy(state)
    )


def _materialize_child_source_for(
    base_screen: source_screen.SourceScreen,
    proposal: dict[str, Any],
    location: Path,
    *,
    owner_directory: Path,
    source_copy: bool,
) -> None:
    """Copy checked returned bytes before a new owner; retained owners are never repaired."""
    if not source_copy:
        return
    _root(location)
    if owner_directory not in {location / "screen", location / "generation"}:
        raise SourceSearchError("source snapshot belongs to another stage")
    child = _object(proposal["child"])
    if child["entrypoint"] != "candidate.py":
        raise SourceSearchError("source snapshot requires the original one-file child")
    original = _root(pipeline._absolute(child["directory"]))
    expected = {"candidate.py": _digest(child["source_sha256"])}
    if inventory(original) != expected:
        raise SourceSearchError("returned source inventory differs before copying")
    path = original / "candidate.py"
    if file_hash(path, max_bytes=MAX_SOURCE_BYTES) != expected["candidate.py"]:
        raise SourceSearchError("returned source differs or exceeds its byte ceiling")
    raw = pipeline._read(path, expected["candidate.py"])
    if len(raw) > MAX_SOURCE_BYTES:
        raise SourceSearchError("returned source exceeds its byte ceiling")
    try:
        raw.decode("utf-8")
    except UnicodeError:
        raise SourceSearchError("returned source must be complete UTF-8") from None
    copied = location / "agent"
    if copied == original:
        raise SourceSearchError("a private source snapshot must differ from its original root")
    present = copied.exists() or copied.is_symlink()
    copied_inventory = inventory(copied) if present else {}
    if copied_inventory not in ({}, expected):
        raise SourceSearchError("an existing source snapshot differs; no files replaced")
    bound = owner_directory.exists() or owner_directory.is_symlink()
    if bound:
        _root(owner_directory)
        if not present or copied_inventory != expected:
            raise SourceSearchError("original owner source snapshot is missing; no repair")
    else:
        if not present:
            copied.mkdir()
        pipeline._same_or_write(copied / "candidate.py", raw)
    if inventory(copied) != expected:
        raise SourceSearchError("copied child differs from its verified source inventory")
    generation = _object(
        _child_screen_for(base_screen, proposal, location, source_copy=source_copy).to_record()[
            "generation"
        ]
    )
    selected = Selection.from_bytes(_json(generation["selection"]))
    actual = prepare_selection(
        Release.from_record(selected.to_record()["release"]),
        source_screen._roots(generation),
        capabilities=cast(dict[str, str], _object(selected.to_record()["capabilities"])),
    )
    if actual.to_bytes() != selected.to_bytes():
        raise SourceSearchError("copied child changes a fixed non-agent selection")


def _materialize_child_source(
    state: dict[str, Any],
    proposal: dict[str, Any],
    location: Path,
    *,
    owner_directory: Path,
) -> None:
    _materialize_child_source_for(
        state["screen"],
        proposal,
        location,
        owner_directory=owner_directory,
        source_copy=_has_source_copy(state),
    )


def _proposal_controls_for(
    controls: Mapping[Path, str], location: Path, plan: dict[str, Any]
) -> dict[Path, str]:
    return (
        dict(controls)
        | {
            location / "plan.json": pipeline._sha(plan),
            location / "proposal.json": pipeline._sha(plan["proposal_descriptor"]),
        }
        | {
            location / "feedback" / name: _digest(value)
            for name, value in plan["feedback_sha256"].items()
        }
    )


def _proposal_controls(
    state: dict[str, Any], location: Path, plan: dict[str, Any]
) -> dict[Path, str]:
    return _proposal_controls_for(state["controls"], location, plan)


def _screen_owner_for(
    reader: NativeEvidence,
    common_controls: Mapping[Path, str],
    review: dict[str, object],
    runtime_sha256: str,
    directory: Path,
    expected: source_screen.SourceScreen,
) -> None:
    """Join the prepared screen to the original search before any nested call."""
    owner = reader.owner(directory / "tasks/0/generation/owners/0")
    context = _object(
        _load(reader.bound(owner, directory / "context.json")),
        {
            "format",
            "screen_sha256",
            "expected_runtime_sha256",
            "controls",
            "comparison_controls",
        },
    )
    controls = {str(path): digest for path, digest in common_controls.items()}
    lineage = expected.to_record()["lineage"]
    if lineage is not None:
        reference = _object(lineage)
        path, digest = str(pipeline._absolute(reference["path"])), _digest(reference["sha256"])
        if path in controls and controls[path] != digest:
            raise SourceSearchError("screen lineage conflicts with an original search control")
        controls[path] = digest
    if (
        reader.bound(owner, directory / "screen.json") != expected.to_bytes()
        or context["format"] != source_screen._version(expected, "source-screen-context")
        or context["screen_sha256"] != expected.fingerprint()
        or context["expected_runtime_sha256"] != runtime_sha256
        or _json(_object(context["controls"])) != _json(controls)
        or owner.manifest["authorization_path"] != str(reader.authorization)
        or _json(owner.manifest["review"]) != _json(review)
    ):
        raise SourceSearchError("prepared screen differs from its original search treatment")


def _screen_owner(
    reader: NativeEvidence,
    state: dict[str, Any],
    directory: Path,
    expected: source_screen.SourceScreen,
) -> None:
    _screen_owner_for(
        reader,
        state["controls"],
        state["record"]["review"],
        state["record"]["expected_runtime_sha256"],
        directory,
        expected,
    )


def _proposal_owner(
    reader: NativeEvidence, state: dict[str, Any], location: Path, plan: dict[str, Any]
) -> None:
    """Join allocation and selected components before execution and on passive read."""
    parent = _parent_screen(reader, plan["parent"])
    generation = _object(parent.to_record()["generation"])
    manifest = reader.owner(location / "proposal/owners/0").manifest
    template = state["record"]["proposal_template"]
    expected = {
        "authorization_path": str(reader.authorization),
        "selection": generation["selection"],
        "roots": generation["roots"],
        "review": state["record"]["review"],
        "settings": {name: template[name] for name in ("budget_microusd", "max_calls")},
    }
    if any(_json(manifest[name]) != _json(value) for name, value in expected.items()):
        raise SourceSearchError("proposal owner changes its selected parent or frozen allocation")
    original = reader._bindings(reader.owner(location / "proposal/owners/0"))
    if any(original.get(str(p)) != h for p, h in _proposal_controls(state, location, plan).items()):
        raise SourceSearchError(
            "proposal owner omitted original plan or measured feedback controls"
        )


def _stage_owner_for(
    reader: NativeEvidence,
    path: Path,
    section: dict[str, Any],
    controls: dict[Path, str],
    *,
    review: dict[str, object],
    funding: dict[str, Any],
    no_model: bool = False,
    verify_files: bool = False,
) -> None:
    """Original treatment and financial custody, including unfinished witness owners."""
    owner = reader.owner(path)
    expected = {
        "selection": section["selection"],
        "roots": section["roots"],
        "review": review,
        "authorization_path": str(reader.authorization),
        "settings": {
            "budget_microusd": 1 if no_model else section["budget_microusd"],
            "max_calls": 1 if no_model else section["max_calls"],
        },
    }
    if any(_json(owner.manifest[name]) != _json(value) for name, value in expected.items()):
        raise SourceSearchError("prepared owner changes its original treatment")
    bindings = reader._bindings(owner)
    if any(bindings.get(str(p)) != digest for p, digest in controls.items()):
        raise SourceSearchError("prepared owner omits an original input")
    if verify_files:
        gateway.execution_identity(path, owner.manifest)
    funded = [row for row in funding["auth_runs"] if row["run_id"] == owner.run_id]
    if (
        len(funded) != 1
        or type(funded[0]["historical"]) is not int
        or funded[0]["historical"] != 0
        or funded[0]["runtime_sha256"] != owner.manifest["execution_sha256"]
    ):
        raise SourceSearchError("prepared owner changes its original runtime")


def _stage_owner(
    reader: NativeEvidence,
    state: dict[str, Any],
    path: Path,
    section: dict[str, Any],
    controls: dict[Path, str],
    *,
    no_model: bool = False,
    verify_files: bool = False,
) -> None:
    _stage_owner_for(
        reader,
        path,
        section,
        controls,
        review=state["record"]["review"],
        funding=state["funding"],
        no_model=no_model,
        verify_files=verify_files,
    )


def _present(reader: NativeEvidence, path: Path) -> bool:
    return path.relative_to(reader.root).as_posix() in reader.capture.entries


def _stage_seal_for(
    reader: NativeEvidence, path: Path, *, funding: dict[str, Any], role: str
) -> tuple[bool, bool]:
    """Check the existing stage anchor without reading retired producer programs."""
    owner = reader.owner(path)
    child, index = path.parent.parent, int(path.name)
    sealed = child / "completed" / (str(index) + ".json")
    anchors = [
        row["reason"] for row in funding["auth_deactivations"] if row["run_id"] == owner.run_id
    ]
    if not _present(reader, sealed):
        return False, bool(anchors)
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
        or anchors != [prefix + hashlib.sha256(raw).hexdigest()]
        or any(op.status != "completed" for op in owner.operations)
    ):
        raise SourceSearchError("prepared completion lacks its original anchor")
    attempt = child / relative
    files = _object(seal["files"])
    prefix_path = attempt.relative_to(reader.root).as_posix() + "/"
    actual = {
        name.removeprefix(prefix_path)
        for name in reader.capture.entries
        if name.startswith(prefix_path) and stat.S_ISREG((reader.root / name).lstat().st_mode)
    }
    if set(files) != actual or "report.json" not in files:
        raise SourceSearchError("prepared completion inventory differs")
    for name, digest in files.items():
        reader.raw(attempt / _path(name), _digest(digest))
    return True, False


def _stage_seal(reader: NativeEvidence, state: dict[str, Any], path: Path, *, role: str) -> bool:
    sealed, inactive = _stage_seal_for(reader, path, funding=state["funding"], role=role)
    state["inactive_pending"] |= inactive
    return sealed


def _witness_location(reader: NativeEvidence, reference: dict[str, object]) -> Path:
    relative = pipeline._absolute(reference["directory"]).relative_to(reader.root).as_posix()
    if relative == "seed":
        return reader.root / "seed-witness"
    if re.fullmatch(r"iterations/(0|[1-9][0-9]*)/screen", relative):
        return reader.root / relative.removesuffix("/screen") / "witness"
    raise SourceSearchError("witness needs an original search candidate screen")


def _witness_parent(
    reader: NativeEvidence, treatment: _WitnessTreatment
) -> source_screen.SourceScreen:
    record = treatment.to_record()
    if reader.root != _witness_path(record["scope"]) or reader.authorization != _witness_path(
        _object(record["parent"])["authorization"]
    ):
        raise SourceSearchError("witness reader belongs to another original scope or authority")
    reference = _object(record["parent"])
    report, parent = _parent_evidence(reader, reference)
    base = source_screen.SourceScreen.from_bytes(_json(record["base_screen"]))
    if parent.comparison_key() != base.comparison_key() or (
        _object(report["admission"])["eligible"] is not True
    ):
        raise SourceSearchError("witness needs its complete eligible common comparison")
    controls = _witness_controls(treatment)
    _screen_owner_for(
        reader,
        controls,
        _object(record["review"]),
        _digest(record["expected_runtime_sha256"]),
        _witness_path(reference["directory"]),
        parent,
    )
    owner = reader.owner(_witness_path(reference["directory"]) / "tasks/0/generation/owners/0")
    names = {
        path.name
        for path in candidate_generation._recorded_sources(_sources(), owner.manifest["core"])
    }
    prefixes = {
        path.parent
        for path in controls
        if path.name == "source_search.py" and all(path.parent / name in controls for name in names)
    }
    if len(prefixes) != 1:
        raise SourceSearchError("witness original controls omit the closed helper inventory")
    return parent


def _witness_materials(
    treatment: _WitnessTreatment, parent: source_screen.SourceScreen
) -> tuple[source_screen.SourceScreen, dict[str, Any], dict[str, Any]]:
    record = treatment.to_record()
    reference = _object(record["parent"])
    location = _witness_path(record["directory"])
    generation = _object(parent.to_record()["generation"])
    bundle = _bundle(location / "feedback", reference, [], full_answers=True)
    hashes = {name + ".json": pipeline._sha(bundle[name]) for name in _FILES}
    template = _object(record["proposal_template"])
    plan = {
        "format": "buddha.source-mutation-witness-plan.v1",
        "policy": dict(MUTATION_WITNESS_POLICY),
        "parent": reference,
        "task": parent.tasks.select([parent.tasks.tasks[0].id]).to_record(),
        "feedback_sha256": hashes,
        "proposal_descriptor": {
            "format": "buddha.candidate-improvement.v1",
            **{name: generation[name] for name in ("entrypoint", "runtime", "executor")},
            **{name: template[name] for name in ("config", "profile", "max_callbacks")},
            "parent_agent_sha256": parent.candidate_id,
            "feedback": {
                "path": str(location / "feedback/feedback.json"),
                "sha256": hashes["feedback.json"],
            },
        },
    }
    return parent, plan, bundle


def _witness_plan(
    reader: NativeEvidence, state: dict[str, Any], parent: dict[str, object], location: Path
) -> tuple[dict[str, Any], dict[str, Any]]:
    treatment = _search_witness_treatment(reader, state, parent)
    if _witness_path(treatment.to_record()["directory"]) != location:
        raise SourceSearchError("witness plan belongs to another original location")
    checked_parent = _witness_parent(reader, treatment)
    _, plan, bundle = _witness_materials(treatment, checked_parent)
    return plan, bundle


def _witness_generation_inputs(
    base_screen: source_screen.SourceScreen,
    controls: Mapping[Path, str],
    source_copy: bool,
    location: Path,
    plan: dict[str, Any],
    proposal: dict[str, Any],
) -> tuple[source_screen.SourceScreen, dict[str, object], dict[Path, str]]:
    child = _child_screen_for(base_screen, proposal, location, source_copy=source_copy)
    task = child.tasks.select([child.tasks.tasks[0].id])
    if task.to_record() != plan["task"]:
        raise SourceSearchError("witness changes its first ordered development task")
    recipe = source_screen._generation_recipe(location, child)
    lineage = _object(child.to_record()["lineage"])
    inputs = _proposal_controls_for(controls, location, plan) | {
        location / "task.json": task.fingerprint(),
        location / "generation.json": pipeline._sha(recipe),
        location / "proposal/report.json": file_hash(location / "proposal/report.json"),
        location / "proposal/completed/0.json": file_hash(location / "proposal/completed/0.json"),
        pipeline._absolute(lineage["path"]): _digest(lineage["sha256"]),
    }
    return child, recipe, inputs


def _witness_generation_for(
    treatment: _WitnessTreatment, plan: dict[str, Any], proposal: dict[str, Any]
) -> tuple[source_screen.SourceScreen, dict[str, object], dict[Path, str]]:
    record = treatment.to_record()
    return _witness_generation_inputs(
        source_screen.SourceScreen.from_bytes(_json(record["base_screen"])),
        _witness_controls(treatment),
        cast(bool, record["source_copy"]),
        _witness_path(record["directory"]),
        plan,
        proposal,
    )


def _witness_generation(
    state: dict[str, Any], location: Path, plan: dict[str, Any], proposal: dict[str, Any]
) -> tuple[source_screen.SourceScreen, dict[str, object], dict[Path, str]]:
    return _witness_generation_inputs(
        state["screen"], state["controls"], _has_source_copy(state), location, plan, proposal
    )


def _witness_funding(reader: NativeEvidence, location: Path) -> dict[str, Any]:
    prefix = location.relative_to(reader.root).as_posix() + "/"
    allowed = {location / role / "owners/0" for role in ("proposal", "generation")}
    observed = set()
    for name in reader.capture.entries:
        if not name.startswith(prefix):
            continue
        relative = name.removeprefix(prefix)
        parts = relative.split("/")
        if "owners" in parts:
            index = parts.index("owners")
            if parts[:index] not in (["proposal"], ["generation"]) or (
                len(parts) > index + 1 and parts[index + 1] != "0"
            ):
                raise SourceSearchError("witness contains a foreign original owner")
        if name.endswith("/manifest.json") and "/owners/" in relative:
            path = reader.root / name.removesuffix("/manifest.json")
            if path not in allowed:
                raise SourceSearchError("witness contains a foreign original owner")
            observed.add(path)
            reader.owner(path)
    for role in ("proposal", "generation"):
        if _present(reader, location / role):
            path = location / role / "owners/0"
            reader.owner(path)
            observed.add(path)
    funding = _authority(reader.capture, reader.authorization, list(reader.owners.values()))
    if funding is None:
        raise SourceSearchError("witness lacks its original authority")
    for row in reader._rows(funding["auth_runs"]):
        path = pipeline._absolute(row["directory"])
        if path.is_relative_to(location) and path not in observed:
            raise SourceSearchError("a funded original witness owner is missing or replaced")
    return funding


@_checked
def _witness_progress_at(reader: NativeEvidence, treatment: _WitnessTreatment) -> dict[str, Any]:
    """Reconstruct one nonrecursive witness, including every original pending owner."""
    if type(treatment) is not _WitnessTreatment or not isinstance(reader, NativeEvidence):
        raise SourceSearchError("witness needs immutable treatment and original evidence")
    record = treatment.to_record()
    reference = _object(record["parent"])
    location = _witness_path(record["directory"])
    parent = _witness_parent(reader, treatment)
    funding = _witness_funding(reader, location)
    current = authority_observation(reader.capture, reader.authorization, funding)
    progress: dict[str, Any] = {
        "result": None,
        "publication": None,
        "next_owner": location / "proposal/owners/0",
        "next_role": "proposal",
        "inactive_pending": False,
        "lower_role": "proposal",
        "needs_prepare": True,
        "owner_treatments": {},
    }
    if not _present(reader, location / "plan.json"):
        prefix = location.relative_to(reader.root).as_posix() + "/"
        if any(name.startswith(prefix) for name in reader.capture.entries):
            raise SourceSearchError("witness entries precede the original plan")
        return progress
    _, plan, bundle = _witness_materials(treatment, parent)
    if reader.raw(location / "plan.json") != _json(plan):
        raise SourceSearchError("witness changes its original candidate or measured feedback")
    required = {location / "proposal.json": _json(plan["proposal_descriptor"])} | {
        location / "feedback" / (name + ".json"): _json(bundle[name]) for name in _FILES
    }
    proposal_dir = location / "proposal"
    prepared = _present(reader, proposal_dir)
    for path, raw in required.items():
        if (prepared or _present(reader, path)) and reader.raw(path) != raw:
            raise SourceSearchError("witness changes a planned input")
    if not prepared:
        if _present(reader, location / "generation") or _present(reader, location / "report.json"):
            raise SourceSearchError("witness outcome precedes its original proposal")
        return progress
    progress["needs_prepare"] = False
    section = _object(parent.to_record()["generation"]) | _object(record["proposal_template"])
    context = {
        "format": candidate_improvement.CONTEXT_FORMAT,
        "descriptor": str(location / "proposal.json"),
        "expected_runtime_sha256": record["expected_runtime_sha256"],
        "expected_feedback_provenance_sha256": plan["feedback_sha256"]["provenance.json"],
    }
    if reader.raw(proposal_dir / "context.json") != _json(context):
        raise SourceSearchError("witness proposal context changes its original treatment")
    proposal_controls = _proposal_controls_for(_witness_controls(treatment), location, plan) | {
        proposal_dir / "context.json": pipeline._sha(context)
    }
    proposal_owner = proposal_dir / "owners/0"
    progress["owner_treatments"][proposal_owner] = {
        "section": section,
        "controls": proposal_controls,
    }
    _stage_owner_for(
        reader,
        proposal_owner,
        section,
        proposal_controls,
        review=_object(record["review"]),
        funding=funding,
    )
    sealed, inactive = _stage_seal_for(reader, proposal_owner, funding=funding, role="proposal")
    progress["inactive_pending"] |= inactive
    if not sealed or not _present(reader, proposal_dir / "report.json"):
        if _present(reader, location / "generation") or _present(reader, location / "report.json"):
            raise SourceSearchError("witness work skips its unfinished original proposal")
        if sealed:
            progress.update(next_owner=None, next_role=None)
        return progress
    proposal_ref = _ref(proposal_dir, reader.authorization)
    proposal = _read_ref(reader, proposal_ref, proposal=True)
    generation_ref = None
    owner_paths = [proposal_owner]
    reason, status = proposal["reason"], "failed"
    progress.update(next_owner=None, next_role=None)
    if proposal["disposition"] == "materialized":
        child, recipe, inputs = _witness_generation_for(treatment, plan, proposal)
        generation_dir = location / "generation"
        progress.update(
            next_owner=generation_dir / "owners/0",
            next_role="generation",
            lower_role="generation",
            needs_prepare=True,
        )
        if not _present(reader, generation_dir):
            if _present(reader, location / "report.json"):
                raise SourceSearchError("witness publication precedes further-child execution")
            return progress
        progress["needs_prepare"] = False
        for path, expected in inputs.items():
            reader.raw(path, expected)
        generation_context = {
            "format": candidate_generation.generation_formats(recipe["format"])["context"],
            "descriptor": str(location / "generation.json"),
            "expected_runtime_sha256": record["expected_runtime_sha256"],
        }
        if reader.raw(generation_dir / "context.json") != _json(generation_context):
            raise SourceSearchError("witness generation context changes its original child")
        inputs |= {generation_dir / "context.json": pipeline._sha(generation_context)}
        generation_owner = generation_dir / "owners/0"
        generation_section = _object(child.to_record()["generation"])
        progress["owner_treatments"][generation_owner] = {
            "section": generation_section,
            "controls": inputs,
        }
        _stage_owner_for(
            reader,
            generation_owner,
            generation_section,
            inputs,
            review=_object(record["review"]),
            funding=funding,
        )
        sealed, inactive = _stage_seal_for(
            reader, generation_owner, funding=funding, role="generation"
        )
        progress["inactive_pending"] |= inactive
        if not sealed or not _present(reader, generation_dir / "report.json"):
            if _present(reader, location / "report.json"):
                raise SourceSearchError("witness publication skips unfinished generation")
            if sealed:
                progress.update(next_owner=None, next_role=None)
            return progress
        generation_ref = _ref(generation_dir, reader.authorization)
        generated = candidate_generation.inspect_candidate_generation(
            generation_dir,
            authorization=reader.authorization,
            expected_report_sha256=cast(str, generation_ref["report_sha256"]),
        )
        if _json(generated) != reader.raw(generation_dir / "report.json"):
            raise SourceSearchError("witness generation differs from its anchored publication")
        owner_paths.append(generation_owner)
        reason = generated["reason"]
        status = "passed" if generated["disposition"] == "generated" else "failed"
    elif _present(reader, location / "generation"):
        raise SourceSearchError("a rejected witness proposal cannot execute a further child")
    progress.update(lower_role=None, needs_prepare=False)
    expected_result = {
        "format": "buddha.source-mutation-witness-report.v1",
        "candidate_id": parent.candidate_id,
        "screen": reference,
        "plan_sha256": pipeline._sha(plan),
        "status": status,
        "reason": reason,
        "proposal": proposal_ref,
        "generation": generation_ref,
        "authorization": current,
        "costs": {
            name: sum(reader.owner(path).accounting()[name] for path in owner_paths)
            for name in _TOTALS
        },
        "claim": (
            "one bounded further mutation and first-task generation witness; "
            "no universal competence or improvement claim"
        ),
    }
    progress.update(publication=expected_result, next_owner=None, next_role=None)
    if _present(reader, location / "report.json"):
        raw = reader.raw(location / "report.json")
        saved = _load(raw)
        pipeline.validate_authorization_snapshot(
            saved["authorization"],
            current,
            {reader.owner(path).run_id for path in owner_paths},
        )
        if raw != _json(expected_result | {"authorization": saved["authorization"]}):
            raise SourceSearchError("saved witness changes its original anchored outcome")
        progress["result"] = saved
    return progress


def _witness_progress(
    reader: NativeEvidence, state: dict[str, Any], reference: dict[str, object]
) -> dict[str, Any]:
    current = _witness_progress_at(reader, _search_witness_treatment(reader, state, reference))
    progress = {
        name: current[name]
        for name in ("result", "publication", "next_owner", "next_role", "inactive_pending")
    }
    state["witness_treatments"].update(current["owner_treatments"])
    if current["owner_treatments"]:
        state["inactive_pending"] |= progress["inactive_pending"]
        progress["inactive_pending"] = state["inactive_pending"]
    state["mutation_progress"][str(reference["directory"])] = progress
    return progress


def _witness_reference(
    reader: NativeEvidence, state: dict[str, Any], reference: dict[str, object]
) -> dict[str, object]:
    progress = state["mutation_progress"].get(str(reference["directory"]))
    if not progress or progress["result"] is None or progress["result"]["status"] != "passed":
        raise SourceSearchError("selected parent lacks its own completed mutation witness")
    return _ref(_witness_location(reader, reference), reader.authorization)


def _write_witness_inputs(
    treatment: _WitnessTreatment, plan: dict[str, Any], bundle: dict[str, Any]
) -> None:
    location = _witness_path(treatment.to_record()["directory"])
    if not location.exists():
        location.mkdir()
    _root(location)
    pipeline._same_or_write(location / "plan.json", _json(plan))
    _write_packet(location / "feedback", plan, bundle)
    pipeline._same_or_write(location / "proposal.json", _json(plan["proposal_descriptor"]))


@_checked
def _advance_witness(
    reader: NativeEvidence,
    treatment: _WitnessTreatment,
    *,
    authorization: Authorization | None = None,
    transport: RawHTTPTransport | None = None,
) -> dict[str, object]:
    """Prepare OR execute one original role; caller censuses between invocations."""
    progress = _witness_progress_at(reader, treatment)
    if progress["result"] is not None:
        reader.capture.finish()
        return {"action": "complete", "role": None, "result": progress["result"]}
    record = treatment.to_record()
    location = _witness_path(record["directory"])
    if not isinstance(authorization, Authorization) or authorization.path != reader.authorization:
        raise SourceSearchError("witness advancement needs its original authority")
    if progress["inactive_pending"]:
        raise SourceSearchError("witness has an inactive original pending owner")
    role = progress["lower_role"]
    reader.capture.finish()
    base = source_screen.SourceScreen.from_bytes(_json(record["base_screen"]))
    purpose = "source screen: " + base.comparison_key()
    with trial_fence.work(
        authorization.path, authorization._terms(), directory=location, kind="search"
    ):
        trial_fence.require_purpose(
            authorization.path, authorization._terms(), directory=location, expected=purpose
        )
        for path, digest in _witness_controls(treatment).items():
            pipeline._read(path, digest)
        if progress["publication"] is not None:
            owners = {reader.owner(path).run_id for path in progress["owner_treatments"]}
            result = pipeline.publish_complete(
                location / "report.json", progress["publication"], authorization, owners
            )
            return {"action": "published", "role": None, "result": result}
        if role not in {"proposal", "generation"}:
            raise SourceSearchError("witness has no checked next lower role")
        if not location.exists():
            location.mkdir()
        _root(location)
        fresh = NativeEvidence(reader.root, reader.authorization, error_type=SourceSearchError)
        parent = _witness_parent(fresh, treatment)
        _, plan, bundle = _witness_materials(treatment, parent)
        proposal = None
        if role == "generation":
            proposal = _read_ref(
                fresh, _ref(location / "proposal", reader.authorization), proposal=True
            )
        fresh.capture.finish()
        if progress["needs_prepare"]:
            _write_witness_inputs(treatment, plan, bundle)
            if role == "proposal":
                generation = _object(parent.to_record()["generation"])
                template = _object(record["proposal_template"])
                inputs = _proposal_controls_for(_witness_controls(treatment), location, plan)
                candidate_improvement.prepare_candidate_improvement(
                    location / "proposal",
                    descriptor=location / "proposal.json",
                    selection=Selection.from_bytes(_json(generation["selection"])),
                    roots=source_screen._roots(generation),
                    authorization=authorization,
                    review=_object(record["review"]),
                    budget_microusd=cast(int, template["budget_microusd"]),
                    max_calls=cast(int, template["max_calls"]),
                    expected_runtime_sha256=_digest(record["expected_runtime_sha256"]),
                    expected_feedback_provenance_sha256=plan["feedback_sha256"]["provenance.json"],
                    input_files=list(inputs),
                    expected_input_hashes=inputs,
                )
            else:
                if proposal is None:
                    raise SourceSearchError("further generation lacks its original proposal")
                _materialize_child_source_for(
                    base,
                    proposal,
                    location,
                    owner_directory=location / "generation",
                    source_copy=cast(bool, record["source_copy"]),
                )
                child, recipe, inputs = _witness_generation_for(treatment, plan, proposal)
                task = child.tasks.select([child.tasks.tasks[0].id])
                pipeline._same_or_write(location / "task.json", task.to_bytes())
                pipeline._same_or_write(location / "generation.json", _json(recipe))
                generation = _object(child.to_record()["generation"])
                candidate_generation.prepare_candidate_generation(
                    location / "generation",
                    descriptor=location / "generation.json",
                    selection=Selection.from_bytes(_json(generation["selection"])),
                    roots=source_screen._roots(generation),
                    authorization=authorization,
                    review=_object(record["review"]),
                    budget_microusd=cast(int, generation["budget_microusd"]),
                    max_calls=cast(int, generation["max_calls"]),
                    expected_runtime_sha256=_digest(record["expected_runtime_sha256"]),
                    input_files=list(inputs),
                    expected_input_hashes=inputs,
                )
            return {"action": "prepared", "role": role, "result": None}
        if not isinstance(transport, RawHTTPTransport):
            raise SourceSearchError("witness execution needs its original raw transport")
        if role == "generation":
            if proposal is None:
                raise SourceSearchError("further generation lacks its original proposal")
            _materialize_child_source_for(
                base,
                proposal,
                location,
                owner_directory=location / "generation",
                source_copy=cast(bool, record["source_copy"]),
            )
            result = candidate_generation.run_candidate_generation(
                location / role, transport=transport
            )
        else:
            result = candidate_improvement.run_candidate_improvement(
                location / role, transport=transport
            )
        if result["status"] != "complete":
            return {"action": "incomplete", "role": role, "result": result}
        source_screen._accepted(location / role, result)
        return {"action": "executed", "role": role, "result": result}


def _execute_witness(
    directory: Path,
    state: dict[str, Any],
    reference: dict[str, object],
    authority: Authorization,
    transport: RawHTTPTransport,
    phase: Callable[[str], None],
) -> dict[str, object]:
    """Adapt explicit witness steps, preserving full search checks before dispatch."""
    reader = NativeEvidence(directory, authority.path, error_type=SourceSearchError)
    treatment = _search_witness_treatment(reader, state, reference)
    progress = state["mutation_progress"][str(reference["directory"])]
    if progress["result"] is not None:
        reader.capture.finish()
        return cast(dict[str, object], progress["result"])
    reader.capture.finish()
    phase("witness_feedback")
    location = _witness_path(treatment.to_record()["directory"])
    with trial_fence.work(authority.path, authority._terms(), directory=location, kind="search"):
        trial_fence.require_purpose(
            authority.path,
            authority._terms(),
            directory=location,
            expected="source screen: " + state["screen"].comparison_key(),
        )
        _check_current(state)
        if not location.exists():
            location.mkdir()
        _root(location)
        fresh = NativeEvidence(directory, authority.path, error_type=SourceSearchError)
        parent = _witness_parent(fresh, treatment)
        _, plan, bundle = _witness_materials(treatment, parent)
        fresh.capture.finish()
        _write_witness_inputs(treatment, plan, bundle)
    observed_phase = "witness_feedback"
    while True:
        reader = NativeEvidence(directory, authority.path, error_type=SourceSearchError)
        state = _restore(directory, authority.path, reader=reader)
        _check_current(state)
        treatment = _search_witness_treatment(reader, state, reference)
        current = state["mutation_progress"][str(reference["directory"])]
        role = current["next_role"]
        if role is None and current["result"] is None:
            if location / "generation/owners/0" in state["witness_treatments"]:
                role = "generation"
            elif location / "proposal/owners/0" in state["witness_treatments"]:
                role = "proposal"
            else:
                raise SourceSearchError("witness phase lacks its checked original owner")
        if role is not None and observed_phase != "witness_" + role:
            observed_phase = "witness_" + role
            phase(observed_phase)
        action = _advance_witness(reader, treatment, authorization=authority, transport=transport)
        if action["action"] in {"incomplete", "published", "complete"}:
            return cast(dict[str, object], action["result"])


def _decision(
    reader: NativeEvidence, state: dict[str, Any], plan: dict[str, Any], known_ids: set[str]
) -> tuple[dict[str, Any], dict[str, object] | None]:
    iteration = plan["iteration"]
    location = reader.root / "iterations" / str(iteration)
    _proposal_owner(reader, state, location, plan)
    proposal_ref = _ref(location / "proposal", reader.authorization)
    proposal = _read_ref(reader, proposal_ref, proposal=True)
    if proposal["parent_agent_sha256"] != plan["selection"]["selected_id"]:
        raise SourceSearchError("proposal belongs to another original selected parent")
    original = _object(_object(proposal["provenance"])["original_inputs"])
    if any(original.get(str(p)) != h for p, h in _proposal_controls(state, location, plan).items()):
        raise SourceSearchError("proposal omitted its original plan or measured feedback controls")
    if reader.raw(location / "proposal.json") != _json(plan["proposal_descriptor"]):
        raise SourceSearchError("proposal descriptor changes its immutable iteration plan")
    child_id, screen_ref, failed, witness_ref = None, None, None, None
    if proposal["disposition"] == "rejected":
        status = "rejected"
    else:
        child_id = _object(proposal["child"])["agent_sha256"]
        if child_id in known_ids:
            status = "duplicate"
        else:
            screen_ref = _ref(location / "screen", reader.authorization)
            report = _read_ref(reader, screen_ref)
            expected = _child_screen(state, proposal, location)
            _screen_owner(reader, state, location / "screen", expected)
            if (
                report["comparison_key"] != state["screen"].comparison_key()
                or report["controls_sha256"] != state["controls_sha256"]
            ):
                raise SourceSearchError("child screen changes the original comparison pool")
            if report.get("disposition") == "candidate_execution_failed":
                status = "candidate_execution_failed"
                failed = {"parent": plan["parent"], "proposal": proposal_ref, "screen": screen_ref}
            else:
                status = (
                    "admitted" if _object(report["admission"])["eligible"] is True else "ineligible"
                )
                if status == "admitted" and _has_witness(state):
                    progress = _witness_progress(reader, state, screen_ref)
                    if progress["result"] is None:
                        raise SourceSearchError(
                            "decision precedes the child's complete mutation witness"
                        )
                    witness_ref = _ref(_witness_location(reader, screen_ref), reader.authorization)
                    if progress["result"]["status"] != "passed":
                        status = "mutation_witness_failed"
    return {
        "iteration": iteration,
        "parent_id": plan["selection"]["selected_id"],
        "proposal": proposal_ref,
        "child_id": child_id,
        "screen": screen_ref,
        "status": status,
        **(
            {
                "format": "buddha.source-search-decision.v2",
                "witness": witness_ref,
                "parent_eligible": status == "admitted",
            }
            if _has_witness(state)
            else {}
        ),
    }, failed


def _pending_witness(
    reader: NativeEvidence,
    state: dict[str, Any],
    location: Path,
    plan: dict[str, Any],
    known_ids: set[str],
) -> None:
    """Check the current child before a decision exists, without skipping its proposal."""
    if not _has_witness(state) or not _present(reader, location / "screen/report.json"):
        return
    _proposal_owner(reader, state, location, plan)
    proposal = _read_ref(reader, _ref(location / "proposal", reader.authorization), proposal=True)
    if proposal["disposition"] != "materialized" or proposal["child"]["agent_sha256"] in known_ids:
        raise SourceSearchError("child screen precedes a new materialized original proposal")
    reference = _ref(location / "screen", reader.authorization)
    report = _read_ref(reader, reference)
    _screen_owner(reader, state, location / "screen", _child_screen(state, proposal, location))
    if (
        report["comparison_key"] != state["screen"].comparison_key()
        or report["controls_sha256"] != state["controls_sha256"]
    ):
        raise SourceSearchError("pending child changes the fixed comparison")
    if report["admission"]["eligible"] is True:
        _witness_progress(reader, state, reference)


def _restore(
    directory: Path,
    authorization: Path,
    *,
    complete: bool = False,
    reader: NativeEvidence | None = None,
) -> dict[str, Any]:
    reader = reader or NativeEvidence(directory, authorization, error_type=SourceSearchError)
    if reader.root != directory or reader.authorization != authorization:
        raise SourceSearchError("retained reader belongs to another search or authority")
    state = _original(reader)
    current, owners = _census(reader, state)
    from buddha.search_evidence import read_authority

    state.update(
        authorization=current,
        owners=owners,
        screens=[],
        decisions=[],
        failures=[],
        plan_sha256={},
        decision_sha256={},
        funding=read_authority(reader.capture.raw[authorization]),
        inactive_pending=False,
        parent_screens=[],
        mutation_progress={},
        witness_treatments={},
    )
    first = directory / "seed/report.json"
    if first.relative_to(directory).as_posix() not in reader.capture.entries:
        state["seed"] = None
    else:
        seed_ref = _ref(directory / "seed", authorization)
        seed = _read_ref(reader, seed_ref)
        _screen_owner(reader, state, directory / "seed", state["screen"])
        state.update(seed=seed_ref, screens=[seed_ref], controls_sha256=seed["controls_sha256"])
        if _object(seed["admission"])["eligible"] is not True:
            state["seed_ineligible"] = True
            if _has_witness(state):
                state["seed_parent_ineligible"] = True
        elif _has_witness(state):
            progress = _witness_progress(reader, state, seed_ref)
            if progress["result"] is not None:
                if progress["result"]["status"] == "passed":
                    state["parent_screens"].append(seed_ref)
                else:
                    state["seed_parent_ineligible"] = True
        else:
            state["parent_screens"].append(seed_ref)
    known_ids = {state["screen"].candidate_id}
    for iteration in range(state["spec"]["iterations"]):
        location = directory / "iterations" / str(iteration)
        plan_name = (location / "plan.json").relative_to(directory).as_posix()
        decision_name = (location / "decision.json").relative_to(directory).as_posix()
        if plan_name not in reader.capture.entries:
            if decision_name in reader.capture.entries:
                raise SourceSearchError("decision precedes its original iteration plan")
            break
        if (
            state["seed"] is None
            or state.get("seed_ineligible")
            or (_has_witness(state) and not state["parent_screens"])
        ):
            raise SourceSearchError("proposal work precedes an eligible fixed seed screen")
        plan = _plan(
            reader,
            state,
            iteration,
            state["parent_screens"] if _has_witness(state) else state["screens"],
            state["failures"],
        )
        raw = reader.raw(location / "plan.json")
        if raw != _json(plan):
            raise SourceSearchError(
                "retained iteration plan changes its original parent or feedback"
            )
        state["plan_sha256"][str(iteration)] = pipeline._sha(plan)
        if decision_name not in reader.capture.entries:
            _pending_witness(reader, state, location, plan, known_ids)
            break
        decision, failed = _decision(reader, state, plan, known_ids)
        if reader.raw(location / "decision.json") != _json(decision):
            raise SourceSearchError("retained iteration decision changes its anchored outcome")
        state["decision_sha256"][str(iteration)] = pipeline._sha(decision)
        state["decisions"].append(decision)
        if decision["child_id"] is not None:
            known_ids.add(decision["child_id"])
        if decision["screen"] is not None:
            state["screens"].append(decision["screen"])
            if not _has_witness(state) or decision["status"] == "admitted":
                state["parent_screens"].append(decision["screen"])
        if failed is not None:
            state["failures"].append(failed)
    cursor = len(state["decisions"])
    for name in reader.capture.entries:
        if not name.startswith("iterations/"):
            continue
        parts = name.split("/")
        if (
            len(parts) < 2
            or not re.fullmatch(r"0|[1-9][0-9]*", parts[1])
            or int(parts[1]) >= state["spec"]["iterations"]
        ):
            raise SourceSearchError("retained iteration is outside the bounded schedule")
        if (
            state["seed"] is None
            or state.get("seed_ineligible")
            or state.get("seed_parent_ineligible")
            or int(parts[1]) > cursor
        ):
            raise SourceSearchError("future iteration entries precede the eligible verified prefix")
        if len(parts) == 3 and parts[2] == "decision.json" and int(parts[1]) >= cursor:
            raise SourceSearchError("future decision precedes the verified search prefix")
    if _has_witness(state):
        locations = {
            _witness_location(reader, {"directory": name}).relative_to(directory).as_posix()
            for name in state["mutation_progress"]
        }
        for name in reader.capture.entries:
            match = re.match(r"^(seed-witness|iterations/(?:0|[1-9][0-9]*)/witness)(?:/|$)", name)
            if match and match.group(1) not in locations:
                raise SourceSearchError("witness work precedes its eligible complete candidate")
        actual = {
            pipeline._absolute(row["directory"])
            for row in owners
            if re.fullmatch(
                r"(?:seed-witness|iterations/(?:0|[1-9][0-9]*)/witness)/(?:proposal|generation)/owners/0",
                pipeline._absolute(row["directory"]).relative_to(directory).as_posix(),
            )
        }
        if actual != set(state["witness_treatments"]):
            raise SourceSearchError("a retained witness owner lacks its original treatment")
    terminal_seed = _has_witness(state) and state.get("seed_parent_ineligible") and cursor == 0
    if complete and (
        (cursor != state["spec"]["iterations"] and not terminal_seed) or state["seed"] is None
    ):
        raise SourceSearchError("search has no complete bounded decision sequence")
    state["known_ids"] = known_ids
    reader.capture.finish()
    return state


def _check_current(state: dict[str, Any]) -> None:
    for path, expected in state["controls"].items():
        pipeline._read(path, expected)


def _write_packet(directory: Path, plan: dict[str, Any], bundle: dict[str, Any]) -> None:
    if not directory.exists():
        directory.mkdir()
    _root(directory)
    expected = {name + ".json" for name in _FILES}
    if any(
        path.name not in expected or not path.is_file() or path.is_symlink()
        for path in directory.iterdir()
    ):
        raise SourceSearchError("partial feedback packet has foreign entries")
    for name in _FILES:
        raw = _json(bundle[name])
        if pipeline._sha(bundle[name]) != plan["feedback_sha256"][name + ".json"]:
            raise SourceSearchError("feedback changes its pre-write planned hash")
        pipeline._same_or_write(directory / (name + ".json"), raw)


def _result(state: dict[str, Any]) -> dict[str, object]:
    witnessed = _has_witness(state)
    refs = state["parent_screens"] if witnessed else state["screens"]
    iteration = len(state["decisions"]) if witnessed else state["spec"]["iterations"]
    selection = (
        _select(refs, state["spec"], iteration)
        if refs
        else {
            "format": "buddha.source-search-selection.v2",
            "comparison_key": state["screen"].comparison_key(),
            "controls_sha256": state["controls_sha256"],
            **{name: state["spec"][name] for name in ("method", "seed", "max_active")},
            "iteration": iteration,
            "selected_id": None,
            "admissions": [],
            "active_ids": [],
            "frontier_ids": [],
            "reason": "no_parent_eligible",
            "claim": (
                "no candidate satisfies search parent eligibility; official task metrics unchanged"
            ),
        }
    )
    witnesses = [
        progress["result"]
        for progress in state["mutation_progress"].values()
        if progress["result"] is not None
    ]
    return {
        "format": "buddha.source-search-report.v2" if witnessed else _REPORT,
        "status": "complete",
        "reason": "no_parent_eligible"
        if witnessed and state.get("seed_parent_ineligible")
        else "bounded_iterations_complete",
        "spec": state["spec"],
        "seed": state["seed"],
        "comparison_key": state["screen"].comparison_key(),
        "controls_sha256": state["controls_sha256"],
        "screens": state["screens"],
        "decisions": state["decisions"],
        "selection": selection,
        "failures": state["failures"],
        **(
            {
                "mutation_witness": dict(MUTATION_WITNESS_POLICY),
                "witnesses": witnesses,
                "witness_costs": {
                    name: sum(row["costs"][name] for row in witnesses) for name in _TOTALS
                },
            }
            if witnessed
            else {}
        ),
        "authorization": state["authorization"],
        "provenance": {
            "manifest_sha256": state["manifest_sha256"],
            "context_sha256": state["context_sha256"],
            "original_controls": {str(p): h for p, h in state["controls"].items()},
            "owners": state["owners"],
            "plan_sha256": state["plan_sha256"],
            "decision_sha256": state["decision_sha256"],
            "scoped_totals": {
                name: sum(cast(int, _object(row["totals"])[name]) for row in state["owners"])
                for name in _TOTALS
            },
        },
        "claim": _CLAIM,
    }


@_checked
def prepare_source_search(
    directory: Path,
    *,
    seed_screen: source_screen.SourceScreen,
    proposal_template: dict[str, object],
    spec: SourceSearchSpec,
    authorization: Authorization,
    review: dict[str, object],
    expected_runtime_sha256: str,
    input_bindings: Mapping[Path, str] | None = None,
    mutation_witness: bool = True,
    source_copy: bool | None = None,
) -> Path:
    if (
        type(seed_screen) is not source_screen.SourceScreen
        or type(spec) is not SourceSearchSpec
        or not isinstance(authorization, Authorization)
        or type(mutation_witness) is not bool
    ):
        raise SourceSearchError("search requires its explicit artifacts and existing authority")
    copy_source = _source_copy_choice(mutation_witness, source_copy)
    directory = pipeline._absolute(str(directory))
    seed = seed_screen.to_record()
    generation = _object(seed["generation"])
    if seed["format"] != "buddha.source-screen.v2" or generation["entrypoint"] != "candidate.py":
        raise SourceSearchError("search needs a prospective failure-aware one-file seed")
    runtime = _digest(expected_runtime_sha256)
    checked_review = _review(review, fresh=True)
    template = _template(proposal_template)
    source_screen._configuration(seed_screen, runtime)
    source_screen._configuration(_template_screen(seed_screen, template), runtime)
    trial_fence.require_purpose(
        authorization.path,
        authorization._terms(),
        directory=directory,
        expected="source screen: " + seed_screen.comparison_key(),
    )
    external = trial_fence._include_controls(directory, dict(input_bindings or {}))
    inputs = _input_records(list(external), external)
    controls = {Path(row["path"]): _digest(row["sha256"]) for row in inputs}
    if seed["lineage"] is not None and (
        pipeline._absolute(_object(seed["lineage"])["path"]) in controls
    ):
        raise SourceSearchError("seed lineage is automatically bound, not a common search control")
    for path in _sources():
        actual = file_hash(path)
        if path in controls and controls[path] != actual:
            raise SourceSearchError("installed helper differs from caller's original expectation")
        controls[path] = actual
    runtime_path = pipeline._absolute(_object(generation["runtime"])["path"])
    if runtime_path in controls and controls[runtime_path] != runtime:
        raise SourceSearchError("runtime differs from original input expectation")
    controls[runtime_path] = runtime
    protected = [authorization.path, *controls]
    for role in ("generation", "native"):
        protected.extend(source_screen._roots(_object(seed[role])).values())
    if any(directory.is_relative_to(p) or p.is_relative_to(directory) for p in protected):
        raise SourceSearchError("search destination overlaps its original controls or components")
    _root(directory.parent)
    _path(directory.name)
    with trial_fence.work(
        authorization.path, authorization._terms(), directory=directory, kind="search"
    ) as trial_controls:
        if any(controls.get(path) != digest for path, digest in trial_controls.items()):
            raise SourceSearchError("original trial controls changed before search preparation")
        trial_fence.require_purpose(
            authorization.path,
            authorization._terms(),
            directory=directory,
            expected="source screen: " + seed_screen.comparison_key(),
        )
        directory.mkdir()
        (directory / "iterations").mkdir()
        (directory / "observations").mkdir()
        manifest = {
            "format": (_MANIFEST if copy_source else _WITNESS_MANIFEST)
            if mutation_witness
            else _FULL_MANIFEST,
            "seed_screen": seed,
            "proposal_template": template,
            "spec": spec.to_record(),
            "authorization": str(authorization.path),
            "review": checked_review,
            "expected_runtime_sha256": runtime,
            "controls": {str(p): h for p, h in controls.items()},
            **({"mutation_witness": dict(MUTATION_WITNESS_POLICY)} if mutation_witness else {}),
            **({"source_copy": dict(SOURCE_COPY_POLICY)} if copy_source else {}),
        }
        context = {"format": _CONTEXT, "manifest_sha256": pipeline._sha(manifest)}
        pipeline._write(directory / "manifest.json", _json(manifest))
        pipeline._write(directory / "context.json", _json(context))
        controls |= {
            directory / "manifest.json": pipeline._sha(manifest),
            directory / "context.json": pipeline._sha(context),
        }
        source_screen.prepare_source_screen(
            directory / "seed",
            screen=seed_screen,
            authorization=authorization,
            review=checked_review,
            expected_runtime_sha256=runtime,
            input_bindings=controls,
        )
    return directory


@_checked
def run_source_search(directory: Path, *, transport: RawHTTPTransport) -> dict[str, object]:
    if not isinstance(directory, Path) or not isinstance(transport, RawHTTPTransport):
        raise SourceSearchError("search execution requires explicit paths and raw transport")
    directory = pipeline._absolute(str(directory))
    first = pipeline._read(directory / "manifest.json")
    authorization_path = pipeline._absolute(_load(first)["authorization"])
    if (directory / "report.json").exists():
        return inspect_source_search(
            directory,
            authorization=authorization_path,
            expected_report_sha256=file_hash(directory / "report.json"),
        )
    with (
        trial_fence.work(
            authorization_path,
            Authorization(authorization_path)._terms(),
            directory=directory,
            kind="search",
        ),
        pipeline._exclusive(directory),
    ):
        state = _restore(directory, authorization_path)
        _check_current(state)
        authority = Authorization(authorization_path)
        iteration, stage, child = 0, "seed", None

        def witness_phase(value: str) -> None:
            nonlocal stage, child
            stage, child = value, None

        def finish(value: dict[str, Any]) -> dict[str, object]:
            return pipeline.publish_complete(
                directory / "report.json",
                _result(value),
                authority,
                {row["run_id"] for row in value["owners"]},
            )

        def observe(reason: str, result: dict[str, object] | None) -> dict[str, object]:
            ordinal = 0
            while (directory / "observations" / (str(ordinal) + ".json")).exists():
                ordinal += 1
            path = directory / "observations" / (str(ordinal) + ".json")
            value = {
                "format": "buddha.source-search-observation.v1",
                "status": "incomplete",
                "reason": reason,
                "iteration": iteration,
                "stage": stage,
                "child": result,
                "authorization": authority.summary(),
                "observation": path.relative_to(directory).as_posix(),
                "claim": "incomplete search; original evidence and liabilities retained",
            }
            pipeline._write(path, _json(value))
            return value

        try:
            if (directory / "report.json").exists():
                return inspect_source_search(
                    directory,
                    authorization=authorization_path,
                    expected_report_sha256=file_hash(directory / "report.json"),
                )
            if state["seed"] is None:
                reader = NativeEvidence(directory, authorization_path, error_type=SourceSearchError)
                _screen_owner(reader, state, directory / "seed", state["screen"])
                reader.capture.finish()
                child = source_screen.run_source_screen(directory / "seed", transport=transport)
                if child["status"] != "complete":
                    return observe(cast(str, child["reason"]), child)
                source_screen._accepted(directory / "seed", child)
            state = _restore(directory, authorization_path)
            if _has_witness(state):
                if not state.get("seed_ineligible"):
                    child = _execute_witness(
                        directory, state, state["seed"], authority, transport, witness_phase
                    )
                    if child["status"] == "incomplete":
                        return observe(cast(str, child["reason"]), child)
                    state = _restore(directory, authorization_path)
                if state.get("seed_parent_ineligible"):
                    return finish(_restore(directory, authorization_path, complete=True))
            if state.get("seed_ineligible"):
                return observe(
                    "seed_ineligible",
                    source_screen.inspect_source_screen(
                        directory / "seed",
                        authorization=authorization_path,
                        expected_report_sha256=file_hash(directory / "seed/report.json"),
                    ),
                )
            for iteration in range(len(state["decisions"]), state["spec"]["iterations"]):
                _check_current(state)
                location = directory / "iterations" / str(iteration)
                if not location.exists():
                    location.mkdir()
                _root(location)
                stage, child = "feedback", None
                reader = NativeEvidence(directory, authorization_path, error_type=SourceSearchError)
                plan = _plan(
                    reader,
                    state,
                    iteration,
                    state["parent_screens"] if _has_witness(state) else state["screens"],
                    state["failures"],
                )
                reader.capture.finish()
                pipeline._same_or_write(location / "plan.json", _json(plan))
                bundle = _bundle(
                    location / "feedback",
                    plan["parent"],
                    state["failures"],
                    full_answers=_full_answers(state),
                )
                _write_packet(location / "feedback", plan, bundle)
                pipeline._same_or_write(
                    location / "proposal.json", _json(plan["proposal_descriptor"])
                )
                stage = "proposal"
                reader = NativeEvidence(directory, authorization_path, error_type=SourceSearchError)
                parent = _parent_screen(reader, plan["parent"])
                reader.capture.finish()
                generation = _object(parent.to_record()["generation"])
                if not (location / "proposal").exists():
                    inputs = _proposal_controls(state, location, plan)
                    template = state["record"]["proposal_template"]
                    candidate_improvement.prepare_candidate_improvement(
                        location / "proposal",
                        descriptor=location / "proposal.json",
                        selection=Selection.from_bytes(_json(generation["selection"])),
                        roots=source_screen._roots(generation),
                        authorization=authority,
                        review=state["record"]["review"],
                        budget_microusd=template["budget_microusd"],
                        max_calls=template["max_calls"],
                        expected_runtime_sha256=state["record"]["expected_runtime_sha256"],
                        expected_feedback_provenance_sha256=plan["feedback_sha256"][
                            "provenance.json"
                        ],
                        input_files=list(inputs),
                        expected_input_hashes=inputs,
                    )
                _check_current(state)
                reader = NativeEvidence(directory, authorization_path, error_type=SourceSearchError)
                _proposal_owner(reader, state, location, plan)
                reader.capture.finish()
                child = candidate_improvement.run_candidate_improvement(
                    location / "proposal", transport=transport
                )
                if child["status"] != "complete":
                    return observe(cast(str, child["reason"]), child)
                proposal_digest = source_screen._accepted(location / "proposal", child)
                reader = NativeEvidence(directory, authorization_path, error_type=SourceSearchError)
                verified = _read_ref(
                    reader,
                    {
                        "directory": str(location / "proposal"),
                        "authorization": str(authorization_path),
                        "report_sha256": proposal_digest,
                    },
                    proposal=True,
                )
                if _json(child) != _json(verified):
                    raise SourceSearchError(
                        "returned proposal differs from its anchored publication"
                    )
                reader.capture.finish()
                if (
                    child["disposition"] == "materialized"
                    and _object(child["child"])["agent_sha256"] not in state["known_ids"]
                ):
                    stage = "screen"
                    _materialize_child_source(
                        state, verified, location, owner_directory=location / "screen"
                    )
                    screen = _child_screen(state, verified, location)
                    if not (location / "screen").exists():
                        _check_current(state)
                        source_screen.prepare_source_screen(
                            location / "screen",
                            screen=screen,
                            authorization=authority,
                            review=state["record"]["review"],
                            expected_runtime_sha256=state["record"]["expected_runtime_sha256"],
                            input_bindings=state["controls"],
                        )
                    _check_current(state)
                    reader = NativeEvidence(
                        directory, authorization_path, error_type=SourceSearchError
                    )
                    _screen_owner(reader, state, location / "screen", screen)
                    reader.capture.finish()
                    child = source_screen.run_source_screen(
                        location / "screen", transport=transport
                    )
                    if child["status"] != "complete":
                        return observe(cast(str, child["reason"]), child)
                    source_screen._accepted(location / "screen", child)
                    if _has_witness(state) and _object(child["admission"])["eligible"] is True:
                        state = _restore(directory, authorization_path)
                        child = _execute_witness(
                            directory,
                            state,
                            _ref(location / "screen", authorization_path),
                            authority,
                            transport,
                            witness_phase,
                        )
                        if child["status"] == "incomplete":
                            return observe(cast(str, child["reason"]), child)
                        state = _restore(directory, authorization_path)
                reader = NativeEvidence(directory, authorization_path, error_type=SourceSearchError)
                decision, _ = _decision(reader, state, plan, state["known_ids"])
                reader.capture.finish()
                pipeline._same_or_write(location / "decision.json", _json(decision))
                state = _restore(directory, authorization_path)
            state = _restore(directory, authorization_path, complete=True)
            return finish(state)
        except KeyboardInterrupt:
            raise SourceSearchInterrupted(observe("cancelled", child)) from None
        except source_feedback.SourceFeedbackTooLarge:
            raise SourceSearchStopped(observe("feedback_capacity", child)) from None
        except (ValueError, TypeError, KeyError, OSError, RecursionError):
            raise SourceSearchStopped(observe("protocol", child)) from None


@_checked
def inspect_source_search(
    directory: Path, *, authorization: Path, expected_report_sha256: str
) -> dict[str, object]:
    directory, authorization = (
        pipeline._absolute(str(directory)),
        pipeline._absolute(str(authorization)),
    )
    reader = NativeEvidence(directory, authorization, error_type=SourceSearchError)
    state = _restore(directory, authorization, complete=True, reader=reader)
    result = _result(state)
    raw = reader.raw(directory / "report.json", _digest(expected_report_sha256))
    saved = _load(raw)
    snapshot = _object(saved["authorization"])
    pipeline.validate_authorization_snapshot(
        snapshot, state["authorization"], {row["run_id"] for row in state["owners"]}
    )
    if raw != _json(saved) or raw != _json(result | {"authorization": snapshot}):
        raise SourceSearchError("search publication differs from its original anchored outcomes")
    reader.capture.finish()
    return saved
