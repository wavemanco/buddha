"""Passive verification of one source-evolution edge, not a search-history replay."""

from collections.abc import Callable
from functools import wraps
from pathlib import Path
from typing import cast

from buddha import candidate_improvement, source_screen, trial_fence
from buddha import native_pipeline as pipeline
from buddha.gateway import _read_manifest
from buddha.releases import ReleaseError, Selection, _digest, _json, _load, _object, file_hash

FORMAT = "buddha.source-forward-edge.v1"
REPORT_FORMAT = "buddha.source-forward-edge-report.v1"
CLAIM = "development edge only; no archive admission or scientific improvement claim"


class SourceForwardError(ReleaseError):
    """An edge differs from its explicit original inputs or stage evidence."""


def _checked[**P, T](function: Callable[P, T]) -> Callable[P, T]:
    @wraps(function)
    def checked(*args: P.args, **kwargs: P.kwargs) -> T:
        try:
            return function(*args, **kwargs)
        except (ValueError, TypeError, KeyError, OSError, RecursionError, OverflowError) as error:
            if isinstance(error, SourceForwardError):
                raise
            raise SourceForwardError("source edge inputs or evidence are invalid") from error

    return checked


def _definition(
    directory: Path, expected: str
) -> tuple[dict[str, object], source_screen.SourceScreen]:
    directory = trial_fence._checked_path(directory)
    record = _object(
        _load(pipeline._read(directory / "edge.json", _digest(expected))),
        {"format", "parent", "improver", "source_pins"},
    )
    if record["format"] != FORMAT:
        raise SourceForwardError("unsupported source edge")
    parent = _object(
        record["parent"], {"directory", "authorization", "screen_sha256", "manifest_sha256"}
    )
    location = trial_fence._checked_path(parent["directory"])
    authority = trial_fence._checked_path(parent["authorization"])
    original = _read_manifest(location / "tasks/0/generation/owners/0")
    if original["authorization_path"] != str(authority) or (
        pipeline._sha(original) != _digest(parent["manifest_sha256"])
    ):
        raise SourceForwardError("parent differs from its original owner")
    screen = source_screen.SourceScreen.from_bytes(
        pipeline._read(location / "screen.json", _digest(parent["screen_sha256"]))
    )
    for path, digest in _object(record["source_pins"]).items():
        trial_fence._checked_path(path)
        _digest(digest)
    _object(record["improver"], set(_object(screen.to_record()["generation"])))
    return record, screen


def _reference(directory: Path, authorization: Path) -> dict[str, object]:
    return {
        "directory": str(directory),
        "authorization": str(authorization),
        "report_sha256": file_hash(directory / "report.json"),
    }


def _recipe(
    directory: Path, record: dict[str, object], screen: source_screen.SourceScreen
) -> dict[str, object]:
    improver = _object(record["improver"])
    generation = _object(screen.to_record()["generation"])
    selected = Selection.from_bytes(_json(generation["selection"]))
    return {
        "format": "buddha.candidate-improvement.v2",
        **{
            key: improver[key]
            for key in ("config", "entrypoint", "executor", "profile", "runtime", "max_callbacks")
        },
        "parent_agent_sha256": screen.candidate_id,
        "task_parent": {
            "path": str(pipeline._absolute(_object(generation["roots"])["agent"]) / "candidate.py"),
            "sha256": _object(_object(selected.to_record()["components"])["agent"])["candidate.py"],
        },
        "feedback": {
            "path": str(directory / "feedback/feedback.json"),
            "sha256": file_hash(directory / "feedback/feedback.json"),
        },
    }


def _proposal_binding(
    directory: Path,
    record: dict[str, object],
    screen: source_screen.SourceScreen,
    definition_sha256: str,
) -> None:
    owner = _read_manifest(directory / "proposal/owners/0")
    first = _read_manifest(
        pipeline._absolute(_object(record["parent"])["directory"]) / "tasks/0/generation/owners/0"
    )
    improver = _object(record["improver"])
    bindings = source_screen._bindings(owner)
    context = _object(
        _load(
            pipeline._read(
                directory / "proposal/context.json", bindings[directory / "proposal/context.json"]
            )
        )
    )
    provenance = _object(
        _load(
            pipeline._read(
                directory / "feedback/provenance.json",
                bindings[directory / "feedback/provenance.json"],
            )
        )
    )
    parent_reference = _reference(
        pipeline._absolute(_object(record["parent"])["directory"]),
        pipeline._absolute(_object(record["parent"])["authorization"]),
    )
    if (
        owner["authorization_path"] != _object(record["parent"])["authorization"]
        or owner["selection"] != improver["selection"]
        or owner["roots"] != improver["roots"]
        or owner["review"] != first["review"]
        or owner["settings"]
        != {"budget_microusd": improver["budget_microusd"], "max_calls": improver["max_calls"]}
        or bindings.get(directory / "edge.json") != definition_sha256
        or any(
            bindings.get(pipeline._absolute(path)) != digest
            for path, digest in _object(record["source_pins"]).items()
        )
        or context["descriptor"] != str(directory / "proposal.json")
        or provenance["format"] != "buddha.source-screen-feedback.v3"
        or provenance["reference"] != parent_reference
        or pipeline._read(directory / "proposal.json", bindings[directory / "proposal.json"])
        != _json(_recipe(directory, record, screen))
    ):
        raise SourceForwardError("proposal differs from its fixed edge and improver")


def _result(
    directory: Path,
    definition_sha256: str,
    record: dict[str, object],
    screen: source_screen.SourceScreen,
    parent: dict[str, object],
    proposal: dict[str, object],
    child: dict[str, object] | None,
) -> dict[str, object]:
    authority = pipeline._absolute(_object(record["parent"])["authorization"])
    selected = Selection.from_bytes(_json(_object(record["improver"])["selection"]))
    if (
        parent["status"] != "complete"
        or _object(parent["admission"])["eligible"] is not True
        or parent["candidate_id"] != screen.candidate_id
        or proposal["status"] != "complete"
        or proposal["parent_agent_sha256"] != screen.candidate_id
        or proposal["improver_agent_sha256"] != selected.agent_sha256
    ):
        raise SourceForwardError("completed edge lacks its matching eligible parent and proposal")
    if proposal["disposition"] == "rejected":
        disposition = "rejected"
    elif proposal["disposition"] == "materialized":
        proposed = _object(proposal["child"])
        disposition = (
            "unchanged" if proposed["agent_sha256"] == screen.candidate_id else "evaluated"
        )
    else:
        raise SourceForwardError("unsupported complete proposal disposition")
    if disposition == "evaluated":
        if child is None or (
            child["status"] != "complete"
            or child["candidate_id"] != _object(proposal["child"])["agent_sha256"]
            or child["parent_id"] != screen.candidate_id
            or child["comparison_key"] != parent["comparison_key"]
            or child["controls_sha256"] != parent["controls_sha256"]
        ):
            raise SourceForwardError("child differs from its matched parent comparison")
        if _object(child["admission"])["eligible"] is not True:
            disposition = "child_failed"
        child_screen = source_screen.SourceScreen.from_bytes(
            pipeline._read(directory / "child/screen/screen.json", child["screen_sha256"])
        ).to_record()
        generation = _object(child_screen["generation"])
        if (
            child_screen["lineage"] != _object(proposal["child"])["lineage"]
            or generation["entrypoint"] != "candidate.py"
            or _object(generation["roots"])["agent"] != str(directory / "child/agent")
        ):
            raise SourceForwardError("child does not use this edge's private source and lineage")
    elif child is not None or (directory / "child").exists():
        raise SourceForwardError("failed proposal unexpectedly has a child screen")
    return {
        "format": REPORT_FORMAT,
        "definition_sha256": definition_sha256,
        "status": "complete",
        "disposition": disposition,
        "failed_opportunities": int(disposition != "evaluated"),
        "parent": _reference(pipeline._absolute(_object(record["parent"])["directory"]), authority),
        "proposal": _reference(directory / "proposal", authority),
        "child": None if child is None else _reference(directory / "child/screen", authority),
        "measurements": {
            "parent": parent["admission"],
            "child": None if child is None else child["admission"],
        },
        "claim": CLAIM,
    }


@_checked
def inspect_source_edge(
    directory: Path, *, expected_definition_sha256: str, expected_report_sha256: str
) -> dict[str, object]:
    """Verify only this edge's original records; no keys, workers, locks or writes."""
    record, screen = _definition(directory, expected_definition_sha256)
    saved = _object(
        _load(pipeline._read(directory / "report.json", _digest(expected_report_sha256)))
    )
    authority = pipeline._absolute(_object(record["parent"])["authorization"])
    reports: dict[str, dict[str, object] | None] = {}
    for name in ("parent", "proposal", "child"):
        reference = saved[name]
        if reference is None and name == "child":
            reports[name] = None
            continue
        reference = _object(reference, {"directory", "authorization", "report_sha256"})
        expected = (
            pipeline._absolute(_object(record["parent"])["directory"])
            if name == "parent"
            else directory / ("proposal" if name == "proposal" else "child/screen")
        )
        if reference["directory"] != str(expected) or reference["authorization"] != str(authority):
            raise SourceForwardError("edge report points outside its original stage")
        inspect = (
            candidate_improvement.inspect_candidate_improvement
            if name == "proposal"
            else source_screen.inspect_source_screen
        )
        reports[name] = inspect(
            expected,
            authorization=authority,
            expected_report_sha256=_digest(reference["report_sha256"]),
        )
    _proposal_binding(directory, record, screen, expected_definition_sha256)
    expected_result = _result(
        directory,
        expected_definition_sha256,
        record,
        screen,
        cast(dict[str, object], reports["parent"]),
        cast(dict[str, object], reports["proposal"]),
        reports["child"],
    )
    if saved != expected_result:
        raise SourceForwardError("edge publication differs from its original anchored outcomes")
    return expected_result
