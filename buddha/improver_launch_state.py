"""Keyless custody observation of an original matched trial, including partials."""

from hashlib import sha256
from pathlib import Path
from typing import Any, cast

from buddha import final_evaluation as final
from buddha import gateway, improver_study, source_search, validation_study
from buddha import improver_assessment as assessment
from buddha import native_pipeline as pipeline
from buddha.doctor import _authority, _Capture, _Owner
from buddha.native_evidence import NativeEvidence, _adopt_capture
from buddha.releases import _digest, _json, _load

_AMOUNTS = ("spent_microusd", "reserved_microusd", "committed_microusd", "operation_count")
_STATUSES = ("reserved", "dispatched", "unknown", "completed")


def _grant(
    capture: _Capture, path: Path, expected: dict[str, Any], owners: list[_Owner]
) -> dict[str, Any]:
    observed = _authority(capture, path, owners)
    if observed is None:
        raise assessment.ImproverAssessmentError("original phase grant is unavailable")
    funding = cast(dict[str, Any], observed)
    if any(
        funding["config"][key] != expected[key]
        for key in ("authorization_id", "terms_sha256", "budget_microusd", "max_calls", "scope")
    ):
        raise assessment.ImproverAssessmentError("original phase grant changed")
    runs = cast(list[dict[str, Any]], funding["auth_runs"])
    by_path = {str(owner.directory): owner for owner in owners}
    if {row["directory"] for row in runs} != set(by_path) or funding["auth_acceptances"]:
        raise assessment.ImproverAssessmentError("phase has missing, foreign or replaced owners")
    if any(
        row["historical"] != 0
        or row["runtime_sha256"] != by_path[row["directory"]].manifest["execution_sha256"]
        for row in runs
    ):
        raise assessment.ImproverAssessmentError("phase changes its original executing owners")
    return funding


def _summary(path: Path, funding: dict[str, Any]) -> dict[str, object]:
    counts = dict.fromkeys(_STATUSES, 0)
    for row in funding["auth_operations"]:
        counts[row["status"]] += 1
    return {
        "authorization_path": str(path),
        **{name: funding["config"][name] for name in ("budget_microusd", "max_calls")},
        **funding["totals"],
        "owner_count": len(funding["auth_runs"]),
        "status_counts": counts,
    }


def _owners(capture: _Capture) -> set[Path]:
    # Join membership to the existing typed censuses; do not invent a schedule.
    return {
        capture.root / (prefix + "/owners/" + tail.split("/", 1)[0])
        for name in capture.entries
        if "/owners/" in name
        for prefix, tail in [name.split("/owners/", 1)]
    }


@assessment._checked
def inspect_prepared_improver_trial(
    directory: Path,
    *,
    declaration: Path,
    expected_sha256: str,
    expected_runtime_sha256: str,
    authorizations: dict[str, Path],
    development_review: dict[str, object],
    input_bindings: dict[Path, str],
) -> dict[str, object]:
    """Check original custody without keys, writers, lock removal or new requests.

    A passing observation is not approval, model/account availability or a right
    to resend an uncertain operation. Existing controllers retain execution.
    """
    if (
        not isinstance(directory, Path)
        or not isinstance(declaration, Path)
        or type(authorizations) is not dict
        or set(authorizations) != {"search", "validation", "final"}
        or any(not isinstance(path, Path) for path in authorizations.values())
        or type(input_bindings) is not dict
    ):
        raise assessment.ImproverAssessmentError("matched custody needs explicit original paths")
    root, declaration = final._path(directory), final._path(declaration)
    capture = _Capture(root)
    state = assessment._state(root, active=False)
    expected = _digest(expected_sha256)
    bindings: dict[Path, str] = {}
    improver_study._bind_controls(bindings, input_bindings)
    bindings = {final._path(path): digest for path, digest in bindings.items()}
    context = state["context"]
    if (
        state["record"]["format"] != assessment._CAPACITY_FORMAT
        or context["format"] != assessment._BINDINGS_CONTEXT
        or context["external_declaration"] != {"path": str(declaration), "sha256": expected}
        or context["expected_runtime_sha256"] != _digest(expected_runtime_sha256)
        or context["development_review"] != gateway._review(development_review)
        or context["input_bindings"] != {str(path): pin for path, pin in bindings.items()}
    ):
        raise assessment.ImproverAssessmentError("trial differs from the reviewed original launch")
    grants = {phase: final._path(path) for phase, path in authorizations.items()}
    if any(grants[phase] != final._phase_authority(state, phase) for phase in grants):
        raise assessment.ImproverAssessmentError("launch changes an original phase grant")
    for path, pin in state["controls"].items():
        if path not in state["retirable_producers"] or path.is_relative_to(root):
            if sha256(capture.read(path, 256 * 1024**2)).hexdigest() != pin:
                raise assessment.ImproverAssessmentError("original outer input changed")
    search_root = root / "search/study"
    development_reader, development = improver_study._restore(search_root, grants["search"])
    assessment._development_context(state, development["context"])
    if development["record"] != state["development"]:
        raise assessment.ImproverAssessmentError("original development declaration changed")
    complete_development = "report.json" in development_reader.capture.entries
    if complete_development:
        report = development_reader.raw(search_root / "report.json")
        improver_study._complete_report(development_reader, development, sha256(report).hexdigest())
    _adopt_capture(development_reader.capture, capture)
    readers: dict[str, NativeEvidence] = {"search": development_reader}
    phase = "freeze" if complete_development else "search"
    position = (
        {"stage": "freeze"}
        if complete_development
        else cast(dict[str, object], development["action"]["position"])
    )
    inactive, failed = False, False
    if "freeze" in capture.entries:
        if not complete_development:
            raise assessment.ImproverAssessmentError("final freeze precedes complete development")
        state, schedule, pins = assessment._restore_grid(root, active=False)
        final_reader, current = final._census(state, schedule, pins)
        cells, generated, failure = validation_study._collect(
            state, schedule, final_reader, current
        )
        failed = failure is not None
        position = final._position(schedule, len(cells), generated)
        for path in final_reader.owners:
            _, pending = source_search._stage_seal_for(
                final_reader,
                path,
                funding=cast(dict[str, Any], final_reader.funded),
                role="generation" if path.parent.parent.name == "generation" else "native",
            )
            inactive |= pending
        if "report.json" in final_reader.capture.entries:
            assessment.inspect_improver_assessment(
                root,
                expected_report_sha256=sha256(
                    final_reader.raw(root / "final/report.json")
                ).hexdigest(),
            )
            phase, position = "complete", {"stage": "complete"}
        else:
            phase = "final"
        _adopt_capture(final_reader.capture, capture)
        readers["final"] = final_reader
    elif any(name.startswith("final/") for name in capture.entries):
        raise assessment.ImproverAssessmentError("final work precedes the original freeze")
    expected_owners = {path for reader in readers.values() for path in reader.owners}
    if _owners(capture) != expected_owners:
        raise assessment.ImproverAssessmentError("trial contains an unscheduled original owner")
    phases: dict[str, Any] = {}
    overrun = False
    for name, path in grants.items():
        owners = list(readers[name].owners.values()) if name in readers else []
        funding = _grant(capture, path, state["funding"]["phases"][name], owners)
        phases[name] = _summary(path, funding)
        overrun |= any(
            row["status"] == "completed" and row["actual_microusd"] > row["reserve_microusd"]
            for row in funding["auth_operations"]
        )
    reasons = []
    busy = any(
        name.rsplit("/", 1)[-1] in {"running.lock", ".trial-running.lock", ".search.lock"}
        for name in capture.entries
    )
    if busy:
        reasons.append("execution_lock_present")
    if overrun:
        reasons.append("reservation_overrun")
    for status in ("dispatched", "unknown"):
        if any(value["status_counts"][status] for value in phases.values()):
            reasons.append(status + "_operations")
    if inactive:
        reasons.append("inactive_original_owner")
    if failed:
        reasons.append("candidate_execution_failed")
    if phase == "search" and development["action"]["kind"] == "proposal_capacity":
        checkpoint = development["action"]["directory"] / "proposal-capacity.json"
        if (
            checkpoint.relative_to(search_root).as_posix() in development_reader.capture.entries
            and development_reader.record(checkpoint)["decision"] != "pass"
        ):
            reasons.append("proposal_capacity")
    digests = capture.fingerprints()
    return _load(
        _json(
            {
                "format": "buddha.improver-launch-state.v1",
                "state": "complete" if phase == "complete" else "prepared",
                "phase": phase,
                "ready": not reasons,
                "busy": busy,
                "inactive_pending": inactive,
                "blocked_reasons": reasons,
                "next_position": position,
                "phases": phases,
                "totals": {
                    name: sum(value[name] for value in phases.values()) for name in _AMOUNTS
                },
                "state_sha256": pipeline._sha({"files": digests, "entries": capture.entries}),
                "limitations": [
                    "Original custody observation only, not approval or permission to spend.",
                    "Sequential captured bytes are not an atomic live snapshot.",
                    "A lock indicates retained evidence, not a verified live process.",
                    "Held amounts stay held; no retry, reissue, settlement or lock removal.",
                    "Trusted validators may decode retained UTF-8 source; no selected code "
                    "is parsed as Python, imported, compiled or executed by this reader.",
                    "No model/account, price, future request capacity or runtime certification.",
                ],
            }
        )
    )
