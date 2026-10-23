"""One durable, measured-feedback source proposal under its original owner.

A complete lifecycle may materialize a child or retain a clean worker-declared
failure. Neither outcome is a competence, archive-admission or improvement claim.
"""

import hashlib
from collections.abc import Callable, Mapping, Sequence
from functools import wraps
from pathlib import Path
from typing import cast

from buddha import candidate_generation, source_screen, trial_fence
from buddha import native_pipeline as pipeline
from buddha.answers import TaskSet, _utf8
from buddha.authorization import Authorization
from buddha.doctor import _Busy, _Unsupported
from buddha.gateway import (
    CAPABILITIES,
    Gateway,
    RawHTTPTransport,
    _input_records,
    _profiles,
    _read_manifest,
    execution_identity,
    prepare_gateway,
)
from buddha.releases import (
    MAX_SOURCE_BYTES,
    ReleaseError,
    Selection,
    _checked_proposal_capture,
    _digest,
    _json,
    _load,
    _object,
    _path,
    _root,
    _source_proposal,
    _text,
    file_hash,
    verify_selection,
)
from buddha.wire import _integer

CONTEXT_FORMAT = "buddha.candidate-improvement-context.v1"
SEAL_FORMAT = "buddha.candidate-improvement-stage.v1"
ANCHOR_PREFIX = "candidate improvement completed: "
OUTCOME_FORMAT = "buddha.candidate-improvement-outcome.v1"
CLAIM = (
    "anchored proposal outcome only; no child competence, archive viability or improvement claim"
)
_REJECTED_REASONS = frozenset(
    {"protocol", "agent_error", "invalid_proposal", "proposal_oversized", "proposal_unavailable"}
)


class CandidateImprovementError(ReleaseError):
    """Original proposal inputs, custody or lifecycle evidence is invalid."""


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
            _Busy,
            _Unsupported,
        ) as error:
            if isinstance(error, CandidateImprovementError):
                raise
            raise CandidateImprovementError(
                "candidate improvement inputs or evidence are invalid"
            ) from None

    return checked


def _sha(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()


def _sources() -> list[Path]:
    package = Path(__file__).absolute().parent
    return list(
        dict.fromkeys(
            [
                *source_screen._sources(),
                *(
                    package / (name + ".py")
                    for name in (
                        "source_feedback",
                        "candidate_improvement",
                        "candidate_improvement_results",
                    )
                ),
            ]
        )
    )


def _definition(
    consume: Callable[[Path], bytes],
    descriptor: Path,
    selection: Selection,
    roots: Mapping[str, object],
    runtime_sha256: str,
    provenance_sha256: str,
    profiles: dict[str, object],
) -> tuple[dict[str, object], dict[str, object], str]:
    """Check original descriptor/data only; never open or execute producer programs."""
    recipe = _object(
        _load(consume(descriptor)),
        {
            "format",
            "config",
            "entrypoint",
            "executor",
            "profile",
            "runtime",
            "max_callbacks",
            "parent_agent_sha256",
            "feedback",
        },
    )
    agent = _object(_object(selection.to_record()["components"])["agent"])
    entrypoint = _path(recipe["entrypoint"])
    if (
        recipe["format"] != "buddha.candidate-improvement.v1"
        or _digest(recipe["parent_agent_sha256"]) != selection.agent_sha256
        or set(agent) != {entrypoint}
        or not entrypoint.endswith(".py")
    ):
        raise CandidateImprovementError("proposal parent differs from selected one-file source")
    _integer(recipe["max_callbacks"], 0, 1000)
    config = _object(
        recipe["config"], {"provider", "model", "max_output_tokens", "instructions", "sampling"}
    )
    if config["provider"] not in {"openai", "anthropic"} or (
        config["sampling"] not in {"regenerate", "in-context"}
        or len(_utf8(config["instructions"])) > 4000
    ):
        raise CandidateImprovementError("unsupported proposal configuration")
    _text(config["model"])
    _integer(config["max_output_tokens"], 1)
    profile = _object(recipe["profile"], {"capability", "profile_id"})
    capability, profile_id = _text(profile["capability"]), _text(profile["profile_id"])
    if capability not in CAPABILITIES or CAPABILITIES[capability][0] != config["provider"]:
        raise CandidateImprovementError("proposal capability differs from configured provider")
    spec = _object(_object(_object(_object(profiles[capability])["profiles"])[profile_id])["spec"])
    if any(spec[key] != config[key] for key in ("provider", "model", "max_output_tokens")):
        raise CandidateImprovementError("proposal configuration differs from original host profile")
    runtime = _object(recipe["runtime"], {"path", "sha256"})
    if _digest(runtime["sha256"]) != runtime_sha256 or (
        _sha(consume(pipeline._absolute(runtime["path"]))) != runtime_sha256
    ):
        raise CandidateImprovementError("proposal runtime differs from independent approval")
    candidate_generation._runtime_selection(recipe, selection, roots, consume, runtime_sha256)
    feedback = _object(recipe["feedback"], {"path", "sha256"})
    path = pipeline._absolute(feedback["path"])
    if path.name != "feedback.json" or ".." in path.parts:
        raise CandidateImprovementError("proposal needs the original measured feedback packet")
    provenance_raw = consume(path.parent / "provenance.json")
    if _sha(provenance_raw) != provenance_sha256:
        raise CandidateImprovementError("feedback provenance differs from caller's original pin")
    from buddha import source_feedback

    if Path(source_feedback.__file__).absolute() != Path(__file__).with_name("source_feedback.py"):
        raise CandidateImprovementError("a different feedback inspector was imported")
    bundle = source_feedback.inspect_source_feedback(
        path.parent, expected_provenance_sha256=provenance_sha256
    )
    for name in ("source", "split", "feedback", "provenance"):
        if consume(path.parent / (name + ".json")) != _json(bundle[name]):
            raise CandidateImprovementError(
                "feedback changed after original measurement inspection"
            )
    if _sha(_json(bundle["feedback"])) != _digest(feedback["sha256"]) or (
        _object(bundle["provenance"])["candidate_id"] != selection.agent_sha256
    ):
        raise CandidateImprovementError("measured feedback belongs to another parent or packet")
    source = TaskSet.from_bytes(_json(bundle["source"]))
    if source.release_sha256 != selection.release_sha256:
        raise CandidateImprovementError("measured feedback belongs to another source release")
    records = cast(list[dict[str, object]], _object(bundle["feedback"])["records"])
    tasks = {task.id: task for task in source.tasks}
    projected = [
        {"task": tasks[cast(str | int, row["task_id"])].to_record(), "note": row["note"]}
        for row in records
    ]
    return recipe, bundle, _sha(_json(projected))


def _validate_outcome(
    attempt: Path,
    envelope: dict[str, object],
    *,
    recipe: dict[str, object],
    bundle: dict[str, object],
    runtime_sha256: str,
    owner: dict[str, object],
    totals: Mapping[str, object],
    read: Callable[[Path, object], bytes],
) -> dict[str, Path]:
    """Validate an accepted lifecycle; both live and passive callers use this."""
    _object(
        envelope,
        {
            "format",
            "status",
            "disposition",
            "reason",
            "session_report_sha256",
            "terminal",
            "artifacts",
            "claim",
        },
    )
    terminal = _object(
        envelope["terminal"],
        {
            "ready",
            "broken",
            "sequence",
            "delivered",
            "stop_reason",
            "done_sha256",
            "done_status",
            "done_reason",
        },
    )
    session = attempt / "session"
    raw = read(session / "report.json", _digest(envelope["session_report_sha256"]))
    report = _load(raw)
    if raw != _json(report) + b"\n":
        raise CandidateImprovementError("original session report is not canonical")
    selected = Selection.from_bytes(_json(owner["selection"]))
    descriptor_sha256 = _digest(report["descriptor_sha256"])
    context_inputs = {
        _text(row["path"]): _digest(row["sha256"])
        for row in cast(list[dict[str, object]], _object(owner["invocation"])["inputs"])
    }
    directory = attempt.parent.parent
    context_path = directory / "context.json"
    context = _load(read(context_path, context_inputs[str(context_path)]))
    descriptor = pipeline._absolute(context["descriptor"])
    descriptor_raw = read(descriptor, context_inputs[str(descriptor)])
    if _sha(descriptor_raw) != descriptor_sha256 or _json(_load(descriptor_raw)) != _json(recipe):
        raise CandidateImprovementError("session descriptor was not an original owner input")
    records = cast(list[dict[str, object]], _object(bundle["feedback"])["records"])
    source = TaskSet.from_bytes(_json(bundle["source"]))
    tasks = {task.id: task for task in source.tasks}
    projected = [
        {"task": tasks[cast(str | int, row["task_id"])].to_record(), "note": row["note"]}
        for row in records
    ]
    calls = _object(report["calls"], {"requested", "completed", "stopped"})
    count = _integer(totals["operation_count"], 0, cast(int, recipe["max_callbacks"]))
    execution = _object(report["execution"])
    if (
        envelope["format"] != OUTCOME_FORMAT
        or envelope["status"] != "complete"
        or envelope["disposition"] not in {"materialized", "rejected"}
        or envelope["claim"] != CLAIM
        or report["format"] != "buddha.candidate-improvement-report.v1"
        or report["parent_agent_sha256"] != selected.agent_sha256
        or report["gateway_manifest_sha256"] != pipeline._sha(owner)
        or report["runtime_sha256"] != runtime_sha256
        or report["config_sha256"] != pipeline._sha(recipe["config"])
        or report["feedback_file_sha256"] != pipeline._sha(bundle["feedback"])
        or report["feedback_sha256"] != _sha(_json(projected))
        or type(report["max_callbacks"]) is not int
        or report["max_callbacks"] != recipe["max_callbacks"]
        or _json(report["gateway_totals"]) != _json(totals)
        or report["owner_operation_coverage_complete"] is not True
        or any(type(value) is not int for value in calls.values())
        or calls != {"requested": count, "completed": count, "stopped": 0}
        or terminal["ready"] is not True
        or terminal["broken"] is not False
        or type(terminal["sequence"]) is not int
        or terminal["sequence"] != count
        or type(terminal["delivered"]) is not int
        or terminal["delivered"] != count
        or terminal["stop_reason"] is not None
        or report["host_stop_reason"] is not None
        or type(execution.get("exit_code")) is not int
        or execution["exit_code"] != 0
        or execution.get("cleanup_status") != "removed"
        or execution.get("image_id") != _object(recipe["executor"])["image_id"]
    ):
        raise CandidateImprovementError("proposal lifecycle, original identity or prefix differs")
    declared = _object(report["artifacts"])
    frame_raw = read(session / "proposal.json", _digest(declared["proposal.json"]))
    frame = _object(_load(frame_raw), {"type", "status", "reason", "proposal"})
    if frame_raw != _json(frame) + b"\n" or _sha(_json(frame)) != _digest(terminal["done_sha256"]):
        raise CandidateImprovementError("accepted terminal proposal frame differs")
    capture = _checked_proposal_capture(frame["proposal"])
    if (
        frame["type"] != "done"
        or frame["status"] != terminal["done_status"]
        or frame["reason"] != terminal["done_reason"]
        or report["status"] != frame["status"]
        or report["reason"] != frame["reason"]
        or envelope["reason"] != frame["reason"]
    ):
        raise CandidateImprovementError("raw session and accepted terminal outcome differ")
    outputs: dict[str, Path] = {}
    if envelope["disposition"] == "materialized":
        if (
            frame["status"] != "complete"
            or frame["reason"] != "complete"
            or capture["status"] != "captured"
        ):
            raise CandidateImprovementError("materialized child lacks an accepted proposal")
        proposal = _source_proposal(capture["value"])
        child_raw = proposal["source"].encode("utf-8")
        child_sha = _sha(child_raw)
        parent_sha = _object(_object(selected.to_record()["components"])["agent"])[
            _path(recipe["entrypoint"])
        ]
        if child_sha == parent_sha or read(session / "child/candidate.py", child_sha) != child_raw:
            raise CandidateImprovementError("child is unchanged or differs from accepted source")
        lineage_path = session / "lineage.json"
        lineage_raw = read(lineage_path, declared["lineage.json"])
        lineage = {
            "format": "buddha.source-lineage.v1",
            "parent": {
                "entrypoint": recipe["entrypoint"],
                "source_sha256": parent_sha,
                "agent_sha256": selected.agent_sha256,
            },
            "child": {
                "entrypoint": "candidate.py",
                "source_sha256": child_sha,
                "agent_sha256": pipeline._sha({"candidate.py": child_sha}),
            },
            "descriptor_sha256": descriptor_sha256,
            "feedback": {
                "file_sha256": report["feedback_file_sha256"],
                "input_sha256": report["feedback_sha256"],
            },
            "proposal_sha256": declared["proposal.json"],
            "owner": {
                "path": str(directory / "owners/0"),
                "manifest_sha256": report["gateway_manifest_sha256"],
            },
        }
        if lineage_raw != _json(lineage) + b"\n":
            raise CandidateImprovementError("materialized source lineage differs")
        if set(declared) != {"proposal.json", "child/candidate.py", "lineage.json"}:
            raise CandidateImprovementError("materialized proposal artifact population differs")
        outputs = {"child": session / "child/candidate.py", "lineage": lineage_path}
    elif (
        frame["status"] != "failed"
        or frame["reason"] not in _REJECTED_REASONS
        or set(declared) != {"proposal.json"}
    ):
        raise CandidateImprovementError("rejected lifecycle lacks a clean accepted failure")
    artifacts: dict[str, str] = {"session/report.json": _sha(raw)}
    for name, digest in declared.items():
        path = session / _path(name)
        read(path, _digest(digest))
        artifacts["session/" + name] = _digest(digest)
    if _json(envelope["artifacts"]) != _json(artifacts):
        raise CandidateImprovementError("wrapper artifact references differ from original session")
    return outputs


@_checked
def prepare_candidate_improvement(
    directory: Path,
    *,
    descriptor: Path,
    selection: Selection,
    roots: dict[str, Path],
    authorization: Authorization,
    review: dict[str, object],
    budget_microusd: int,
    max_calls: int,
    expected_runtime_sha256: str,
    expected_feedback_provenance_sha256: str,
    input_files: Sequence[Path] = (),
    expected_input_hashes: Mapping[Path, str] | None = None,
) -> Path:
    """Check measured parent feedback and prepare one original owner; no calls."""
    if (
        not isinstance(directory, Path)
        or not isinstance(descriptor, Path)
        or (not isinstance(selection, Selection) or not isinstance(authorization, Authorization))
    ):
        raise CandidateImprovementError("proposal needs explicit paths, selection and authority")
    directory, descriptor = pipeline._absolute(str(directory)), pipeline._absolute(str(descriptor))
    if ".." in directory.parts:
        raise CandidateImprovementError("proposal output cannot traverse parents")
    runtime, provenance = (
        _digest(expected_runtime_sha256),
        _digest(expected_feedback_provenance_sha256),
    )
    supplied = _input_records(input_files, expected_input_hashes)
    expected = trial_fence._include_controls(
        directory, {Path(row["path"]): row["sha256"] for row in supplied}
    )

    def consume(path: Path) -> bytes:
        raw = pipeline._read(path, expected.get(path))
        expected[path] = _sha(raw)
        return raw

    for path in _sources():
        consume(path)
    recipe, _, _ = _definition(
        consume, descriptor, selection, roots, runtime, provenance, _profiles(selection, roots)
    )
    parent = roots["agent"] / _path(recipe["entrypoint"])
    expected_parent = _object(_object(selection.to_record()["components"])["agent"])[
        _path(recipe["entrypoint"])
    ]
    if file_hash(parent, max_bytes=MAX_SOURCE_BYTES) != expected_parent:
        raise CandidateImprovementError("parent source differs or exceeds its byte ceiling")
    with parent.open("rb") as stream:
        stream.read(MAX_SOURCE_BYTES + 1).decode("utf-8")
    verify_selection(selection, roots, expected_sha256=selection.fingerprint())
    protected = [*roots.values(), descriptor, *expected, authorization.path]
    if any(directory.is_relative_to(path) or path.is_relative_to(directory) for path in protected):
        raise CandidateImprovementError("proposal output overlaps original inputs")
    _root(directory.parent)
    _path(directory.name)
    with trial_fence.work(
        authorization.path, authorization._terms(), directory=directory, kind="improvement"
    ) as trial_controls:
        for path, digest in trial_controls.items():
            if path in expected and expected[path] != digest:
                raise CandidateImprovementError(
                    "original trial controls changed before preparation"
                )
            expected[path] = digest
        _input_records(list(expected), expected)
        context = directory / "context.json"
        if len(set(expected) | {context}) > 1024:
            raise CandidateImprovementError("proposal controls exceed the owner input limit")
        directory.mkdir()
        for name in ("owners", "attempts", "completed", "observations"):
            (directory / name).mkdir()
        context_raw = _json(
            {
                "format": CONTEXT_FORMAT,
                "descriptor": str(descriptor),
                "expected_runtime_sha256": runtime,
                "expected_feedback_provenance_sha256": provenance,
            }
        )
        pipeline._write(context, context_raw)
        expected[context] = _sha(context_raw)
        prepare_gateway(
            directory / "owners/0",
            selection=selection,
            roots=roots,
            authorization=authorization,
            review=review,
            budget_microusd=budget_microusd,
            max_calls=max_calls,
            input_files=list(expected),
            expected_input_hashes=expected,
        )
    return directory


def _wrap(attempt: Path, session: object, report: dict[str, object]) -> dict[str, object]:
    # This function receives the real installed session, never an agent-supplied object.
    from buddha.candidate_run import CandidateSession

    if not isinstance(session, CandidateSession):
        raise CandidateImprovementError("proposal wrapper needs the actual source session")
    raw = pipeline._read(attempt / "session/report.json")
    if raw != _json(report) + b"\n":
        raise CandidateImprovementError("raw session publication differs from its actual return")
    done = session.done
    terminal = {
        "ready": session.ready,
        "broken": session.broken,
        "sequence": session.sequence,
        "delivered": session.delivered,
        "stop_reason": session.stop_reason,
        "done_sha256": None if done is None else _sha(_json(done)),
        "done_status": None if done is None else done["status"],
        "done_reason": None if done is None else done["reason"],
    }
    calls = _object(report["calls"])
    totals = session.gateway.ledger.totals()
    execution = report["execution"]
    accepted = (
        terminal["ready"] is True
        and terminal["broken"] is False
        and done is not None
        and session.stop_reason is None
        and report["host_stop_reason"] is None
        and type(execution) is dict
        and type(execution.get("exit_code")) is int
        and execution["exit_code"] == 0
        and execution.get("cleanup_status") == "removed"
        and execution.get("image_id") == session.spec.image_id
        and report["owner_operation_coverage_complete"] is True
        and _json(report["gateway_totals"]) == _json(totals)
        and session.delivered == session.sequence == totals["operation_count"]
        and calls == {"requested": session.delivered, "completed": session.delivered, "stopped": 0}
        and report["status"] == done["status"]
        and report["reason"] == done["reason"]
    )
    disposition = None
    if accepted:
        if report["status"] == "complete" and report["reason"] == "complete":
            disposition = "materialized"
        elif report["status"] == "failed" and report["reason"] in _REJECTED_REASONS:
            disposition = "rejected"
    reason = report["reason"]
    if disposition is None and session.stop_reason is None:
        if session.done is None or session.broken or not session.ready:
            reason = "protocol"
        elif report["owner_operation_coverage_complete"] is not True:
            reason = "owner_prefix"
    result: dict[str, object] = {
        "format": OUTCOME_FORMAT,
        "status": "complete" if disposition is not None else "incomplete",
        "disposition": disposition,
        "reason": reason,
        "session_report_sha256": _sha(raw),
        "terminal": terminal,
        "artifacts": {"session/report.json": _sha(raw)}
        | {
            "session/" + _path(name): _digest(digest)
            for name, digest in _object(report["artifacts"]).items()
        },
        "claim": CLAIM,
    }
    pipeline._write(attempt / "report.json", _json(result) + b"\n")
    return result


@_checked
def run_candidate_improvement(directory: Path, *, transport: RawHTTPTransport) -> dict[str, object]:
    """Run once or resume the same owner; completed outcomes never rerun the worker."""
    if not isinstance(directory, Path) or not isinstance(transport, RawHTTPTransport):
        raise CandidateImprovementError(
            "proposal execution needs its original Path and raw transport"
        )
    directory = pipeline._absolute(str(directory))
    original_manifest = _read_manifest(directory / "owners/0")
    authority_path = pipeline._absolute(original_manifest["authorization_path"])
    if trial_fence.is_closed(directory):
        return inspect_candidate_improvement(
            directory,
            authorization=authority_path,
            expected_report_sha256=file_hash(directory / "report.json"),
        )
    with (
        trial_fence.work(
            authority_path,
            Authorization(authority_path)._terms(),
            directory=directory,
            kind="improvement",
        ),
        pipeline._exclusive(directory),
    ):
        if {path.name for path in (directory / "owners").iterdir()} != {"0"}:
            raise CandidateImprovementError("proposal owner population differs")
        if not {path.name for path in (directory / "completed").iterdir()} <= {"0.json"}:
            raise CandidateImprovementError("proposal completion population differs")
        gateway = Gateway(directory / "owners/0", transport=transport)
        owner = _read_manifest(gateway.directory)
        bindings = {
            Path(_text(row["path"])): _digest(row["sha256"])
            for row in cast(list[dict[str, object]], _object(owner["invocation"])["inputs"])
        }

        def consume(path: Path) -> bytes:
            if path not in bindings:
                raise CandidateImprovementError("proposal input was not original")
            return pipeline._read(path, bindings[path])

        for path in _sources():
            consume(path)
        context = _object(
            _load(consume(directory / "context.json")),
            {
                "format",
                "descriptor",
                "expected_runtime_sha256",
                "expected_feedback_provenance_sha256",
            },
        )
        if context["format"] != CONTEXT_FORMAT:
            raise CandidateImprovementError("unsupported original proposal context")
        descriptor = pipeline._absolute(context["descriptor"])
        runtime = _digest(context["expected_runtime_sha256"])
        provenance = _digest(context["expected_feedback_provenance_sha256"])
        recipe, bundle, _ = _definition(
            consume,
            descriptor,
            Selection.from_bytes(_json(owner["selection"])),
            _object(owner["roots"]),
            runtime,
            provenance,
            _object(owner["profiles"]),
        )
        authority = Authorization(pipeline._absolute(owner["authorization_path"]))
        identifier = _text(owner["run_id"])
        funding = cast(list[dict[str, object]], authority.summary()["runs"])
        if any(
            pipeline._absolute(row["directory"]).is_relative_to(directory)
            and row["run_id"] != identifier
            for row in funding
        ):
            raise CandidateImprovementError("known funded proposal owner is missing or replaced")
        original = [row for row in funding if row["run_id"] == identifier]
        if len(original) != 1 or original[0]["directory"] != str(gateway.directory):
            raise CandidateImprovementError("proposal lacks its original funded owner")
        if not (directory / "completed/0.json").exists() and original[0]["active"] is not True:
            raise CandidateImprovementError("unfinished original proposal owner is inactive")
        actual_attempt: Path | None = None

        def run(attempt: Path) -> dict[str, object]:
            nonlocal actual_attempt
            actual_attempt = attempt
            attempt.mkdir()
            from buddha import candidate_run

            if Path(candidate_run.__file__).absolute() != Path(__file__).with_name(
                "candidate_run.py"
            ):
                raise CandidateImprovementError("a different proposal session was imported")
            session = candidate_run.CandidateSession(
                gateway,
                descriptor=descriptor,
                output=attempt / "session",
                expected_runtime_sha256=runtime,
            )
            try:
                report = session.run()
            except KeyboardInterrupt:
                if (attempt / "session/report.json").is_file():
                    try:
                        _wrap(
                            attempt, session, _load(pipeline._read(attempt / "session/report.json"))
                        )
                    except (ValueError, TypeError, KeyError, OSError, RecursionError):
                        pass  # Preserve the interrupt and the original raw evidence.
                raise
            return _wrap(attempt, session, report)

        def validate(attempt: Path, envelope: dict[str, object]) -> dict[str, Path]:
            execution_identity(gateway.directory)
            for path in _sources():
                consume(path)
            for name in ("source", "split", "feedback", "provenance"):
                path = pipeline._absolute(_object(recipe["feedback"])["path"]).parent / (
                    name + ".json"
                )
                if consume(path) != _json(bundle[name]):
                    raise CandidateImprovementError(
                        "measured feedback changed during proposal execution"
                    )
            return _validate_outcome(
                attempt,
                envelope,
                recipe=recipe,
                bundle=bundle,
                runtime_sha256=runtime,
                owner=owner,
                totals=gateway.ledger.totals(),
                read=lambda path, digest: pipeline._read(path, cast(str | None, digest)),
            )

        def observation(reason: str) -> dict[str, object]:
            ordinal = 0
            while (directory / "observations" / f"{ordinal}.json").exists():
                ordinal += 1
            path = directory / "observations" / f"{ordinal}.json"
            outcome = None
            if actual_attempt is not None and (actual_attempt / "report.json").is_file():
                try:
                    outcome = _load(pipeline._read(actual_attempt / "report.json"))
                except (ValueError, OSError, RecursionError):
                    pass  # Raw unavailable evidence stays untouched at the attempt.
            result: dict[str, object] = {
                "format": "buddha.candidate-improvement-observation.v1",
                "status": "incomplete",
                "reason": reason,
                "owner": str(gateway.directory),
                "attempt": None if actual_attempt is None else str(actual_attempt),
                "outcome": outcome,
                "authorization": authority.summary(),
                "observation": path.relative_to(directory).as_posix(),
            }
            pipeline._write(path, _json(result))
            return result

        try:
            envelope, _, _, sealed, _ = pipeline.execute_stage(
                directory,
                0,
                gateway,
                authority,
                run=run,
                validate=validate,
                seal_format=SEAL_FORMAT,
                anchor_prefix=ANCHOR_PREFIX,
            )
        except KeyboardInterrupt:
            observation("cancelled")
            raise
        except (ValueError, TypeError, KeyError, OSError, RecursionError):
            if actual_attempt is not None:
                observation("protocol")
            raise
        if sealed is None:
            return observation(_text(envelope["reason"]))
        from buddha.candidate_improvement_results import collect_candidate_improvement

        result = collect_candidate_improvement(directory, authorization=authority.path)
        return pipeline.publish_complete(directory / "report.json", result, authority, {identifier})


@_checked
def inspect_candidate_improvement(
    directory: Path, *, authorization: Path, expected_report_sha256: str
) -> dict[str, object]:
    from buddha.candidate_improvement_results import collect_candidate_improvement

    return collect_candidate_improvement(
        directory,
        authorization=authorization,
        expected_report_sha256=_digest(expected_report_sha256),
    )
