"""Execute one existing parent → full feedback → fixed improver → private child edge."""

from pathlib import Path
from typing import cast

from buddha import candidate_improvement, source_feedback, source_screen, trial_fence
from buddha import native_pipeline as pipeline
from buddha.authorization import Authorization
from buddha.gateway import RawHTTPTransport, _read_manifest
from buddha.releases import Selection, _json, _load, _object, _text, file_hash
from buddha.source_forward_results import (
    FORMAT,
    _checked,
    _definition,
    _proposal_binding,
    _recipe,
    _reference,
    _result,
    inspect_source_edge,
)
from buddha.source_forward_results import (
    SourceForwardError as SourceForwardError,
)
from buddha.source_search import _child_screen_for, _materialize_child_source_for


def _sources() -> list[Path]:
    return list(
        dict.fromkeys(
            [
                *candidate_improvement._sources(),
                *(
                    Path(__file__).with_name(name + ".py")
                    for name in ("source_forward", "source_forward_results", "source_search")
                ),
            ]
        )
    )


def _inputs(
    directory: Path, parent: Path, improver: dict[str, object], authorization: Authorization
) -> tuple[source_screen.SourceScreen, dict[str, object], str]:
    if not isinstance(authorization, Authorization):
        raise SourceForwardError("edge needs an explicit existing authorization")
    terms = authorization._terms()
    if trial_fence._parse_scope(_text(terms["scope"])) is not None:
        raise SourceForwardError("a standalone source edge cannot use a frozen trial grant")
    directory, parent = trial_fence._checked_path(directory), trial_fence._checked_path(parent)
    first = _read_manifest(parent / "tasks/0/generation/owners/0")
    if first["authorization_path"] != str(authorization.path):
        raise SourceForwardError("edge must retain its parent's original authorization")
    screen, controls, runtime = source_screen._original(parent, first)
    trial_fence.require_purpose(
        authorization.path,
        terms,
        directory=directory,
        expected="source screen: " + screen.comparison_key(),
    )
    generation = _object(screen.to_record()["generation"])
    _object(improver, set(generation))
    if generation["entrypoint"] != "candidate.py" or improver["entrypoint"] != "candidate.py":
        raise SourceForwardError("forward edges support the existing candidate.py boundary")
    actor = screen.to_record()
    actor["generation"] = improver
    source_screen._configuration(source_screen.SourceScreen.from_bytes(_json(actor)), runtime)
    protected = [parent, authorization.path, *controls]
    for section in (generation, _object(screen.to_record()["native"]), improver):
        protected.extend(source_screen._roots(section).values())
    if any(directory.is_relative_to(path) or path.is_relative_to(directory) for path in protected):
        raise SourceForwardError("edge output overlaps original inputs or funding")
    return screen, first, runtime


@_checked
def prepare_source_edge(
    directory: Path, *, parent: Path, improver: dict[str, object], authorization: Authorization
) -> Path:
    """Freeze one edge around an existing prepared parent; no new owners or calls."""
    screen, first, _ = _inputs(directory, parent, improver, authorization)
    record = {
        "format": FORMAT,
        "parent": {
            "directory": str(parent),
            "authorization": str(authorization.path),
            "screen_sha256": screen.fingerprint(),
            "manifest_sha256": pipeline._sha(first),
        },
        "improver": improver,
        "source_pins": {str(path): file_hash(path) for path in _sources()},
    }
    directory.mkdir(exist_ok=True)
    with pipeline._exclusive(directory):
        pipeline._same_or_write(directory / "edge.json", _json(record))
    return directory


def _execution_inputs(
    directory: Path, expected_definition_sha256: str
) -> tuple[dict[str, object], source_screen.SourceScreen, dict[str, object], str]:
    record, _ = _definition(directory, expected_definition_sha256)
    original = _object(record["parent"])
    screen, first, runtime = _inputs(
        directory,
        pipeline._absolute(original["directory"]),
        _object(record["improver"]),
        Authorization(pipeline._absolute(original["authorization"])),
    )
    if record["source_pins"] != {str(path): file_hash(path) for path in _sources()}:
        raise SourceForwardError("edge helpers changed; prepare a separately reviewed edge")
    return record, screen, first, runtime


@_checked
def check_source_edge(directory: Path, *, expected_definition_sha256: str) -> dict[str, object]:
    """Check current execution inputs before keys; creates no owners or requests."""
    record, _, _, _ = _execution_inputs(directory, expected_definition_sha256)
    return record


@_checked
def run_source_edge(
    directory: Path, *, expected_definition_sha256: str, transport: RawHTTPTransport
) -> dict[str, object]:
    """Advance original stages, never restoring the whole search or study history."""
    if not isinstance(directory, Path) or not isinstance(transport, RawHTTPTransport):
        raise SourceForwardError("edge execution needs an explicit Path and raw transport")
    if (directory / "report.json").exists():
        return inspect_source_edge(
            directory,
            expected_definition_sha256=expected_definition_sha256,
            expected_report_sha256=file_hash(directory / "report.json"),
        )
    check_source_edge(directory, expected_definition_sha256=expected_definition_sha256)
    with pipeline._exclusive(directory):
        record, screen, first, runtime = _execution_inputs(directory, expected_definition_sha256)
        original = _object(record["parent"])
        parent_dir = pipeline._absolute(original["directory"])
        authority = Authorization(pipeline._absolute(original["authorization"]))
        stage = "parent"

        def observe(
            reason: str, outcome: dict[str, object] | None, error: BaseException | None = None
        ) -> dict[str, object]:
            folder = directory / "observations"
            folder.mkdir(exist_ok=True)
            ordinal = 0
            while (folder / f"{ordinal}.json").exists():
                ordinal += 1
            path = folder / f"{ordinal}.json"
            value = {
                "format": "buddha.source-forward-edge-observation.v1",
                "definition_sha256": expected_definition_sha256,
                "status": "incomplete",
                "stage": stage,
                "reason": reason,
                "failed_opportunities": 0,
                "outcome": outcome,
                "exception_type": None if error is None else type(error).__name__,
                "authorization": authority.summary(),
                "observation": path.relative_to(directory).as_posix(),
            }
            pipeline._write(path, _json(value))
            return value

        def run_screen(location: Path) -> dict[str, object]:
            if (location / "report.json").exists():
                return source_screen.inspect_source_screen(
                    location,
                    authorization=authority.path,
                    expected_report_sha256=file_hash(location / "report.json"),
                )
            result = source_screen.run_source_screen(location, transport=transport)
            if result["status"] == "complete":
                digest = source_screen._accepted(location, result)
                return source_screen.inspect_source_screen(
                    location, authorization=authority.path, expected_report_sha256=digest
                )
            return result

        try:
            parent_result = run_screen(parent_dir)
            if parent_result["status"] != "complete":
                return observe(cast(str, parent_result["reason"]), parent_result)
            if _object(parent_result["admission"])["eligible"] is not True:
                return observe("parent_ineligible", parent_result)
            retained = {parent_dir: source_screen._accepted(parent_dir, parent_result)}
            stage = "feedback"
            feedback = directory / "feedback"
            parent_reference = _reference(parent_dir, authority.path)
            if not feedback.exists():
                source_feedback.write_source_feedback(feedback, reference=parent_reference)
            provenance = file_hash(feedback / "provenance.json")
            packet = source_feedback.inspect_source_feedback(
                feedback, expected_provenance_sha256=provenance
            )
            saved_provenance = _object(
                _load(pipeline._read(feedback / "provenance.json", provenance))
            )
            if saved_provenance["format"] != "buddha.source-screen-feedback.v3" or (
                saved_provenance["reference"] != parent_reference
                or _object(packet["feedback"])["format"]
                != "buddha.candidate-development-feedback.v2"
            ):
                raise SourceForwardError("edge requires full feedback from this original parent")
            stage = "proposal"
            descriptor = directory / "proposal.json"
            pipeline._same_or_write(descriptor, _json(_recipe(directory, record, screen)))
            proposal_dir = directory / "proposal"
            improver = _object(record["improver"])
            if not proposal_dir.exists():
                pins = {
                    pipeline._absolute(path): cast(str, digest)
                    for path, digest in _object(record["source_pins"]).items()
                }
                pins[directory / "edge.json"] = expected_definition_sha256
                candidate_improvement.prepare_candidate_improvement(
                    proposal_dir,
                    descriptor=descriptor,
                    selection=Selection.from_bytes(_json(improver["selection"])),
                    roots=source_screen._roots(improver),
                    authorization=authority,
                    review=_object(first["review"]),
                    budget_microusd=cast(int, improver["budget_microusd"]),
                    max_calls=cast(int, improver["max_calls"]),
                    expected_runtime_sha256=runtime,
                    expected_feedback_provenance_sha256=provenance,
                    input_files=list(pins),
                    expected_input_hashes=pins,
                )
            _proposal_binding(directory, record, screen, expected_definition_sha256)
            if (proposal_dir / "report.json").exists():
                proposal = candidate_improvement.inspect_candidate_improvement(
                    proposal_dir,
                    authorization=authority.path,
                    expected_report_sha256=file_hash(proposal_dir / "report.json"),
                )
            else:
                proposal = candidate_improvement.run_candidate_improvement(
                    proposal_dir, transport=transport
                )
                if proposal["status"] != "complete":
                    return observe(cast(str, proposal["reason"]), proposal)
                proposal = candidate_improvement.inspect_candidate_improvement(
                    proposal_dir,
                    authorization=authority.path,
                    expected_report_sha256=source_screen._accepted(proposal_dir, proposal),
                )
            retained[proposal_dir] = source_screen._accepted(proposal_dir, proposal)
            child_result = None
            if proposal["disposition"] == "materialized" and (
                _object(proposal["child"])["agent_sha256"] != screen.candidate_id
            ):
                stage = "child"
                location = directory / "child"
                location.mkdir(exist_ok=True)
                child_dir = location / "screen"
                _materialize_child_source_for(
                    screen, proposal, location, owner_directory=child_dir, source_copy=True
                )
                child = _child_screen_for(screen, proposal, location, source_copy=True)
                parent_context = _object(_load(pipeline._read(parent_dir / "context.json")))
                external = _object(_object(parent_context["comparison_controls"])["external"])
                if not child_dir.exists():
                    source_screen.prepare_source_screen(
                        child_dir,
                        screen=child,
                        authorization=authority,
                        review=_object(first["review"]),
                        expected_runtime_sha256=runtime,
                        input_bindings={
                            pipeline._absolute(path): cast(str, digest)
                            for path, digest in external.items()
                        },
                    )
                child_context = _object(_load(pipeline._read(child_dir / "context.json")))
                pipeline._read(child_dir / "screen.json", child.fingerprint())
                if child_context["comparison_controls"] != parent_context["comparison_controls"]:
                    raise SourceForwardError("child changes the common measurement controls")
                child_result = run_screen(child_dir)
                if child_result["status"] != "complete":
                    return observe(cast(str, child_result["reason"]), child_result)
                retained[child_dir] = source_screen._accepted(child_dir, child_result)
            result = _result(
                directory,
                expected_definition_sha256,
                record,
                screen,
                parent_result,
                proposal,
                child_result,
            )
            for name in ("parent", "proposal", "child"):
                if result[name] is not None:
                    reference = _object(result[name])
                    location = pipeline._absolute(reference["directory"])
                    digest = retained[location]
                    pipeline._read(location / "report.json", digest)
                    if reference["report_sha256"] != digest:
                        raise SourceForwardError("accepted stage changed before edge publication")
            pipeline._same_or_write(directory / "report.json", _json(result))
            return result
        except KeyboardInterrupt:
            observe("cancelled", None)
            raise
        except (ValueError, TypeError, KeyError, OSError, RecursionError, OverflowError) as error:
            observe("protocol", None, error)
            raise
