"""Check a fresh, unfunded matched study using the original v4 validators."""

from pathlib import Path
from typing import Any, cast

from buddha import improver_assessment as assessment
from buddha import improver_study, validation_study
from buddha import launch_common as common
from buddha import native_pipeline as pipeline
from buddha.releases import ReleaseError, _digest, _json, _load, _object, _root, file_hash


class ImproverHandoffError(ReleaseError):
    """The proposed matched study differs from its reviewed configuration."""


def _sources() -> list[Path]:
    package = Path(__file__).absolute().parent.parent
    return sorted(
        {
            *improver_study._sources({"format": improver_study._CAPACITY_FORMAT}),
            *(package / name for name in assessment._source_hashes()),
            Path(__file__).absolute(),
            Path(common.__file__).absolute(),
        }
    )


def _components(state: dict[str, Any], runtime: str) -> None:
    # Active inventory/configuration checks do not decode selected Python.
    # The separate active intrinsic-input collector does; do not call it here.
    improver_study._declaration(state["development"], runtime, active=True)
    validation_study._validate_execution(state["record"], state["tasks"], runtime, active=True)


def _destination(directory: Path) -> None:
    _root(directory.parent)
    try:
        directory.lstat()
    except FileNotFoundError:
        return
    raise ImproverHandoffError("handoff needs a fresh trial destination")


def _configuration(path: Path, expected_sha256: str, *, fresh: bool) -> dict[str, Any]:
    if not isinstance(path, Path):
        raise ImproverHandoffError("handoff needs an explicit Path")
    path = common._path(str(path.absolute()), error=ImproverHandoffError)
    expected = _digest(expected_sha256)
    raw = pipeline._read(path, expected)
    record = _object(
        _load(raw),
        {"format", "assessment", "expected_runtime_sha256", "directory", "source_sha256"},
    )
    if record["format"] != "buddha.improver-handoff.v1":
        raise ImproverHandoffError("unsupported matched handoff")
    reference = _object(record["assessment"], {"path", "sha256"})
    declaration = common._path(reference["path"], error=ImproverHandoffError)
    declared = _digest(reference["sha256"])
    runtime = _digest(record["expected_runtime_sha256"])
    directory = common._path(record["directory"], error=ImproverHandoffError)
    if fresh:
        _destination(directory)
    pins = _object(record["source_sha256"])
    if not 1 <= len(pins) <= 1023:
        raise ImproverHandoffError("handoff controls exceed the preparation boundary")
    controls: dict[Path, str] = {path: expected, declaration: declared}
    aliases: set[Path] = set()
    for name, digest in pins.items():
        source = common._path(name, error=ImproverHandoffError)
        if source == path or source in aliases:
            raise ImproverHandoffError("handoff controls have aliases or self-reference")
        aliases.add(source)
        improver_study._bind_controls(controls, {source: _digest(digest)})
    required = {
        common._path(source): pin
        for source, pin in common._historical_sources(
            {str(source): file_hash(source) for source in _sources()}
        ).items()
    }
    if any(controls.get(source) != digest for source, digest in required.items()):
        raise ImproverHandoffError("handoff omits or changes an installed helper pin")
    definition_raw = pipeline._read(declaration, declared)
    state = assessment._definition(definition_raw, runtime, active=False)
    if state["record"]["format"] != assessment._CAPACITY_FORMAT:
        raise ImproverHandoffError("fresh matched handoff requires assessment and study v4")
    if fresh:
        _components(state, runtime)
    improver_study._bind_controls(controls, state["controls"])
    return state | {
        "handoff_path": path,
        "handoff_raw": raw,
        "handoff": record,
        "declaration": declaration,
        "declared_sha256": declared,
        "directory": directory,
        "controls": controls,
    }


def check_improver_handoff(path: Path, *, expected_sha256: str) -> dict[str, object]:
    """Read and recheck configuration; create no authority, owner, output or worker.

    This fresh-only check is not a retained-trial reader or permission to spend.
    Selected source is inventoried as bytes, never decoded or executed here.
    """
    try:
        state = _configuration(path, expected_sha256, fresh=True)
        path, raw = state["handoff_path"], state["handoff_raw"]
        directory, runtime = state["directory"], state["runtime"]
        declared, controls = state["declared_sha256"], state["controls"]
        expected = _digest(expected_sha256)
        protected = [
            common._path(str(source), error=ImproverHandoffError)
            for source in (
                *controls,
                *state["protected"],
                *state["record"]["generation"]["roots"].values(),
                *state["record"]["native"]["roots"].values(),
            )
        ]
        if any(
            directory.is_relative_to(source) or source.is_relative_to(directory)
            for source in protected
        ):
            raise ImproverHandoffError("trial destination overlaps reviewed inputs")
        prospective = assessment._prospective_controls(state, directory)
        improver_study._bind_controls(prospective, controls)
        validation_study._capacity(
            state,
            {
                "directory": str(directory / "final"),
                "controls": {str(source): digest for source, digest in prospective.items()},
            },
            receipts={
                directory / "freeze" / name: "0" * 64 for name in ("schedule.json", "ready.json")
            },
        )
        assessment._development_capacity(state, directory, controls)
        _components(state, runtime)
        for source, digest in controls.items():
            if file_hash(source, max_bytes=256 * 1024**2) != digest:
                raise ImproverHandoffError("reviewed handoff input changed")
        if pipeline._read(path, expected) != raw:
            raise ImproverHandoffError("handoff changed during checking")
        _destination(directory)
        limits = _object(state["record"]["phase_limits"])
        development = state["development"]
        starts, repetitions = len(state["screens"]), development["repetitions"]
        final_tasks = len(state["record"]["final_ids"])
        sealed = state["record"]["sealed_repetitions"]
        return _load(
            _json(
                {
                    "format": "buddha.improver-handoff-check.v1",
                    "status": "configuration_checked",
                    "assessment_sha256": declared,
                    "definition_sha256": pipeline._sha(state["definition"]),
                    "directory": str(directory),
                    "requested_phase_limits": limits,
                    "requested_totals": {
                        key: sum(cast(int, _object(value)[key]) for value in limits.values())
                        for key in ("budget_microusd", "max_calls")
                    },
                    "funding": {"status": "unallocated"},
                    "reviewed_bindings": {
                        str(source): digest for source, digest in controls.items()
                    },
                    "planned": {
                        "starts": starts,
                        "development_repetitions": repetitions,
                        "opportunities_per_arm": development["descendant_opportunities"],
                        "development_tasks": len(state["screens"][0].tasks.tasks),
                        "final_tasks": final_tasks,
                        "sealed_repetitions": sealed,
                        "maximum_final_cells": 3 * starts * repetitions * final_tasks * sealed,
                    },
                    "limitations": [
                        "Configuration only; no authority, keys, SQL database, output or "
                        "execution.",
                        "Requires separate original search, zero validation and final authorities.",
                        "Read-only consistency checks do not establish an atomic snapshot.",
                        "No retained-trial/recovery check, account access, price, future model "
                        "capacity or full-grid runtime certification.",
                        "Known-future file capacity is checked; funded preparation must bind and "
                        "check its actual additional launch/approval controls before owners.",
                        "No scientific effectiveness, human review or generalization claim.",
                    ],
                }
            )
        )
    except (ValueError, TypeError, KeyError, OSError, RecursionError):
        raise ImproverHandoffError(
            "unfunded matched configuration is invalid; no execution prepared"
        ) from None
