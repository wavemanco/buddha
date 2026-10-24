"""Anchor one confined source generation for passive, fresh native assessment.

The candidate session is imported only on an executing path after its original
host inputs are checked. Passive consumption needs no producer program/runtime.
"""

import base64
import hashlib
from collections.abc import Callable, Mapping, Sequence
from functools import wraps
from pathlib import Path
from typing import cast

from buddha import native_pipeline as pipeline
from buddha import trial_fence
from buddha.answers import Answers, TaskSet, _utf8
from buddha.authorization import Authorization
from buddha.doctor import _authority, _Busy, _Capture, _owner, _Unsupported
from buddha.gateway import (
    Gateway,
    RawHTTPTransport,
    _final_producer_contract,
    _input_records,
    _read_manifest,
    execution_identity,
    prepare_gateway,
)
from buddha.gateway_history import read_gateway_history
from buddha.releases import (
    ReleaseError,
    Selection,
    _digest,
    _json,
    _load,
    _object,
    _path,
    _root,
    _text,
    file_hash,
    verify_selection,
)
from buddha.wire import _integer

SOURCE_FORMAT = "buddha.candidate-generation-source.v1"
CONTEXT_FORMAT = "buddha.candidate-generation-context.v1"
SEAL_FORMAT = "buddha.candidate-generation-stage.v1"
ANCHOR_PREFIX = "candidate generation completed: "
SOURCE_FORMAT_V2 = "buddha.candidate-generation-source.v2"
CONTEXT_FORMAT_V2 = "buddha.candidate-generation-context.v2"
SEAL_FORMAT_V2 = "buddha.candidate-generation-stage.v2"
ANCHOR_PREFIX_V2 = "candidate generation outcome completed: "
OUTCOME_FORMAT = "buddha.candidate-generation-outcome.v2"
CLAIM_V2 = "anchored source execution outcome only; no competence, eligibility or improvement claim"


class CandidateGenerationError(ReleaseError):
    """Source generation configuration, custody or completion is invalid."""


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
            _Busy,
            _Unsupported,
        ) as error:
            if isinstance(error, CandidateGenerationError):
                raise
            raise CandidateGenerationError("candidate generation evidence is invalid") from None

    return checked


def generation_formats(recipe_format: object) -> dict[str, str]:
    """Select explicit producer identities without reading files or guessing context."""
    if recipe_format == "buddha.candidate-generation.v1":
        return {
            "context": CONTEXT_FORMAT,
            "seal": SEAL_FORMAT,
            "anchor": ANCHOR_PREFIX,
            "source": SOURCE_FORMAT,
        }
    if recipe_format == "buddha.candidate-generation.v2":
        return {
            "context": CONTEXT_FORMAT_V2,
            "seal": SEAL_FORMAT_V2,
            "anchor": ANCHOR_PREFIX_V2,
            "source": SOURCE_FORMAT_V2,
        }
    raise CandidateGenerationError("only explicit candidate generation is supported")


def _sources(recipe_format: object = "buddha.candidate-generation.v1") -> list[Path]:
    # The generation-v1 host closure is fixed without importing its worker on a
    # passive read. These eight names are the SOURCE-CANDIDATES contract.
    names = (
        "__init__",
        "channel",
        "releases",
        "wire",
        "candidate_worker",
        "executor",
        "answers",
        "candidate_run",
        "candidate_generation",
        "trial_fence",
        "native_pipeline",
        "doctor",
        "process_observation",
        "gateway_history",
        "history",
        "search_evidence",
    )
    package = Path(__file__).absolute().parent
    return [package / (name + ".py") for name in names] + (
        [package / "native_evidence.py"]
        if recipe_format == "buddha.candidate-generation.v2"
        else []
    )


@_checked
def _recorded_sources(paths: Sequence[Path], core: object) -> list[Path]:
    """Select a closed original candidate closure without opening retired sources."""
    recorded = _object(core)
    legacy = {
        "buddha",
        "buddha.gateway",
        "buddha.wire",
        "buddha.releases",
        "buddha.authorization",
        "buddha.ledger",
        "buddha.history",
        "buddha.provider",
        "buddha.common",
    }
    if set(recorded) not in (legacy, legacy | {"buddha.trial_fence"}):
        raise CandidateGenerationError("unsupported original candidate core profile")
    for digest in recorded.values():
        _digest(digest)
    if "buddha.trial_fence" in recorded:
        if sum(path.name == "trial_fence.py" for path in paths) != 1:
            raise CandidateGenerationError("original fenced closure requires its helper")
        return list(paths)
    return [path for path in paths if path.name != "trial_fence.py"]


def _recipe(
    consume: Callable[[Path], bytes],
    descriptor: Path,
    runtime_sha256: str,
) -> tuple[dict[str, object], TaskSet]:
    recipe = _object(
        _load(consume(descriptor)),
        {
            "format",
            "tasks",
            "config",
            "entrypoint",
            "executor",
            "profile",
            "runtime",
            "max_callbacks",
        },
    )
    generation_formats(recipe["format"])
    _integer(recipe["max_callbacks"], 0, 1000)
    tasks = TaskSet.from_bytes(consume(pipeline._absolute(recipe["tasks"])))
    runtime = _object(recipe["runtime"], {"path", "sha256"})
    if (
        len(tasks.tasks) != 1
        or _digest(runtime["sha256"]) != runtime_sha256
        or hashlib.sha256(consume(pipeline._absolute(runtime["path"]))).hexdigest()
        != runtime_sha256
    ):
        raise CandidateGenerationError("source task/runtime differs from original approval")
    return recipe, tasks


def _runtime_selection(
    recipe: dict[str, object],
    selection: Selection,
    roots: Mapping[str, object],
    consume: Callable[[Path], bytes],
    runtime_sha256: str,
) -> None:
    reference = _object(recipe["runtime"], {"path", "sha256"})
    path = pipeline._absolute(reference["path"])
    environment = pipeline._absolute(str(roots["environment"]))
    if not path.is_relative_to(environment):
        raise CandidateGenerationError("approved runtime is outside its original environment")
    selected = _object(_object(selection.to_record()["components"])["environment"])
    if selected.get(path.relative_to(environment).as_posix()) != runtime_sha256:
        raise CandidateGenerationError("approved runtime differs from its selected component")
    runtime = _load(consume(path))
    settings = _object(recipe["executor"])
    actual_env = settings["image_environment"]
    approved_env = _object(runtime["config"])["Env"]
    if (
        type(actual_env) is not list
        or type(approved_env) is not list
        or any(
            type(pair) is not list
            or len(pair) != 2
            or any(type(value) is not str for value in pair)
            for pair in actual_env
        )
        or any(type(value) is not str or "=" not in value for value in approved_env)
    ):
        raise CandidateGenerationError("invalid source runtime environment")
    if (
        runtime["format"] != "buddha.src01-runtime-environment.v1"
        or settings["image_id"] != runtime["image_id"]
        or dict(actual_env) != dict(value.split("=", 1) for value in approved_env)
    ):
        raise CandidateGenerationError("source execution differs from approved runtime")


@_checked
def prepare_candidate_generation(
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
    input_files: Sequence[Path] = (),
    expected_input_hashes: Mapping[Path, str] | None = None,
) -> Path:
    """Prepare a new original owner under existing authority; no model calls."""
    if not isinstance(directory, Path) or not isinstance(descriptor, Path):
        raise CandidateGenerationError("generation needs explicit Path inputs")
    if not isinstance(authorization, Authorization) or not isinstance(selection, Selection):
        raise CandidateGenerationError("generation needs existing authority and selection")
    directory, descriptor = pipeline._absolute(str(directory)), pipeline._absolute(str(descriptor))
    runtime_sha256 = _digest(expected_runtime_sha256)
    verify_selection(selection, roots, expected_sha256=selection.fingerprint())
    controls = _input_records(input_files, expected_input_hashes)
    expected = trial_fence._include_controls(
        directory, {Path(row["path"]): row["sha256"] for row in controls}
    )

    def consume(path: Path) -> bytes:
        raw = pipeline._read(path, expected.get(path))
        expected[path] = hashlib.sha256(raw).hexdigest()
        return raw

    recipe, tasks = _recipe(consume, descriptor, runtime_sha256)
    _runtime_selection(recipe, selection, roots, consume, runtime_sha256)
    if tasks.release_sha256 != selection.release_sha256:
        raise CandidateGenerationError("source task differs from selected release")
    for path in _sources(recipe["format"]):
        consume(path)
    protected = [*roots.values(), descriptor, *expected, authorization.path]
    if any(directory.is_relative_to(path) or path.is_relative_to(directory) for path in protected):
        raise CandidateGenerationError("generation output overlaps original inputs")
    _root(directory.parent)
    _path(directory.name)
    with trial_fence.work(
        authorization.path, authorization._terms(), directory=directory, kind="generation"
    ) as trial_controls:
        for path, digest in trial_controls.items():
            if path in expected and expected[path] != digest:
                raise CandidateGenerationError("original trial controls changed before preparation")
            expected[path] = digest
        _input_records(list(expected), expected)
        context = directory / "context.json"
        if len(set(expected) | {context}) > 1024:
            raise CandidateGenerationError("generation controls exceed the owner input limit")
        directory.mkdir()
        for name in ("owners", "attempts", "completed", "observations"):
            (directory / name).mkdir()
        context_raw = _json(
            {
                "format": generation_formats(recipe["format"])["context"],
                "descriptor": str(descriptor),
                "expected_runtime_sha256": runtime_sha256,
            }
        )
        pipeline._write(context, context_raw)
        expected[context] = hashlib.sha256(context_raw).hexdigest()
        with _final_producer_contract(
            directory / "owners/0",
            selection=selection,
            roots=roots,
            authorization=authorization,
            settings={"budget_microusd": budget_microusd, "max_calls": max_calls},
            review=review,
            inputs=_input_records(list(expected), expected),
        ):
            prepare_gateway(
                directory / "owners/0",
                selection=selection,
                roots=roots,
                authorization=authorization,
                budget_microusd=budget_microusd,
                max_calls=max_calls,
                input_files=list(expected),
                expected_input_hashes=expected,
                review=review,
            )
    return directory


def _outputs(
    attempt: Path,
    report: dict[str, object],
    recipe: dict[str, object],
    tasks: TaskSet,
    descriptor_raw: bytes,
    runtime_sha256: str,
    owner: dict[str, object],
) -> dict[str, Path]:
    path = attempt / "answers.json"
    answer_raw = pipeline._read(
        path, _object(report["artifacts"], {"answers.json"})["answers.json"]
    )
    answers = Answers.from_bytes(answer_raw).to_record()
    calls = _object(report["calls"], {"requested", "completed", "stopped"})
    count = _integer(calls["completed"], 0, cast(int, recipe["max_callbacks"]))
    execution = _object(report["execution"])
    if (
        report.get("format") != "buddha.candidate-generation-report.v1"
        or report.get("status") != "complete"
        or report.get("reason") != "complete"
        or report.get("gateway_manifest_sha256") != pipeline._sha(owner)
        or report.get("descriptor_sha256") != hashlib.sha256(descriptor_raw).hexdigest()
        or report.get("config_sha256") != pipeline._sha(recipe["config"])
        or report.get("runtime_sha256") != runtime_sha256
        or report.get("tasks_sha256") != tasks.fingerprint()
        or report.get("agent_sha256")
        != Selection.from_bytes(_json(owner["selection"])).agent_sha256
        or answers["tasks_sha256"] != tasks.fingerprint()
        or answers["agent_sha256"] != report["agent_sha256"]
        or answers["metadata"] != {}
        or any(type(value) is not int for value in calls.values())
        or calls != {"requested": count, "completed": count, "stopped": 0}
        or report.get("owner_operation_coverage_complete") is not True
        or type(report.get("max_callbacks")) is not int
        or report["max_callbacks"] != recipe["max_callbacks"]
        or report.get("host_stop_reason") is not None
        or type(execution.get("exit_code")) is not int
        or execution["exit_code"] != 0
        or execution.get("cleanup_status") != "removed"
        or execution.get("image_id") != _object(recipe["executor"])["image_id"]
    ):
        raise CandidateGenerationError("candidate C1/report/cleanup lineage differs")
    return {"answers": path}


def _wrap_outcome(attempt: Path, session: object, report: dict[str, object]) -> dict[str, object]:
    from buddha.candidate_run import CandidateSession

    if not isinstance(session, CandidateSession):
        raise CandidateGenerationError("generation outcome needs the actual source session")
    raw = pipeline._read(attempt / "session/report.json")
    if raw != _json(report) + b"\n":
        raise CandidateGenerationError("raw generation report differs from its actual return")
    done = session.done
    totals = session.gateway.ledger.totals()
    terminal = {
        "ready_seen": session.ready,
        "broken": session.broken,
        "sequence": session.sequence,
        "delivered": session.delivered,
        "stop_reason": session.stop_reason,
        "done_sha256": None if done is None else pipeline._sha(done),
        "done_status": None if done is None else done["status"],
        "done_reason": None if done is None else done["reason"],
        "operation_count": totals["operation_count"],
        "recorded_cost_microusd": totals["spent_microusd"],
    }
    if done is not None:
        pipeline._write(attempt / "session/done.json", _json(done) + b"\n")
    execution = report["execution"]
    calls = _object(report["calls"])
    accepted = (
        type(terminal["ready_seen"]) is bool
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
        and type(session.sequence) is int
        and type(session.delivered) is int
        and session.sequence == session.delivered == totals["operation_count"]
        and all(type(value) is int for value in calls.values())
        and calls == {"requested": session.delivered, "completed": session.delivered, "stopped": 0}
        and report["status"] == done["status"]
        and report["reason"] == done["reason"]
    )
    disposition = None
    if accepted:
        if session.ready and report["status"] == report["reason"] == "complete":
            disposition = "generated"
        elif report["status"] == "failed" and report["reason"] == "agent_error":
            if session.ready or session.delivered == 0:
                disposition = "candidate_execution_failed"
    reason = report["reason"]
    if disposition is None and session.stop_reason is None:
        if session.broken or done is None:
            reason = "protocol"
        elif report["owner_operation_coverage_complete"] is not True:
            reason = "owner_prefix"
    artifacts = {"session/report.json": hashlib.sha256(raw).hexdigest()} | {
        "session/" + _path(name): _digest(digest)
        for name, digest in _object(report["artifacts"]).items()
    }
    if done is not None:
        artifacts["session/done.json"] = file_hash(attempt / "session/done.json")
    result = {
        "format": OUTCOME_FORMAT,
        "status": "complete" if disposition is not None else "incomplete",
        "disposition": disposition,
        "reason": reason,
        "session_report_sha256": hashlib.sha256(raw).hexdigest(),
        "terminal": terminal,
        "artifacts": artifacts,
        "claim": CLAIM_V2,
    }
    pipeline._write(attempt / "report.json", _json(result) + b"\n")
    return result


def _validate_outcome(
    attempt: Path,
    outcome: dict[str, object],
    recipe: dict[str, object],
    tasks: TaskSet,
    descriptor_raw: bytes,
    runtime_sha256: str,
    owner: dict[str, object],
    totals: dict[str, int],
    read: Callable[[Path], bytes],
) -> dict[str, Path]:
    _object(
        outcome,
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
        outcome["terminal"],
        {
            "ready_seen",
            "broken",
            "sequence",
            "delivered",
            "stop_reason",
            "done_sha256",
            "done_status",
            "done_reason",
            "operation_count",
            "recorded_cost_microusd",
        },
    )
    raw = read(attempt / "session/report.json")
    report = _load(raw)
    done_raw = read(attempt / "session/done.json")
    done = _object(_load(done_raw), {"type", "status", "reason", "answers"})
    calls = _object(report["calls"], {"requested", "completed", "stopped"})
    count = _integer(totals["operation_count"], 0, cast(int, recipe["max_callbacks"]))
    execution = _object(report["execution"])
    if (
        outcome["format"] != OUTCOME_FORMAT
        or outcome["status"] != "complete"
        or outcome["claim"] != CLAIM_V2
        or outcome["disposition"] not in {"generated", "candidate_execution_failed"}
        or raw != _json(report) + b"\n"
        or hashlib.sha256(raw).hexdigest() != _digest(outcome["session_report_sha256"])
        or done_raw != _json(done) + b"\n"
        or pipeline._sha(done) != _digest(terminal["done_sha256"])
        or done["type"] != "done"
        or done["status"] != report["status"]
        or done["reason"] != report["reason"]
        or terminal["done_status"] != done["status"]
        or terminal["done_reason"] != done["reason"]
        or outcome["reason"] != report["reason"]
        or type(terminal["ready_seen"]) is not bool
        or terminal["broken"] is not False
        or terminal["stop_reason"] is not None
        or any(
            type(terminal[key]) is not int
            for key in ("sequence", "delivered", "operation_count", "recorded_cost_microusd")
        )
        or terminal["sequence"] != count
        or terminal["delivered"] != count
        or terminal["operation_count"] != count
        or terminal["recorded_cost_microusd"] != totals["spent_microusd"]
        or _json(report["gateway_totals"]) != _json(totals)
        or report["owner_operation_coverage_complete"] is not True
        or any(type(value) is not int for value in calls.values())
        or calls != {"requested": count, "completed": count, "stopped": 0}
        or type(execution.get("exit_code")) is not int
        or execution["exit_code"] != 0
        or execution.get("cleanup_status") != "removed"
        or execution.get("image_id") != _object(recipe["executor"])["image_id"]
        or report["host_stop_reason"] is not None
        or report["format"] != "buddha.candidate-generation-report.v1"
        or report["gateway_manifest_sha256"] != pipeline._sha(owner)
        or report["descriptor_sha256"] != hashlib.sha256(descriptor_raw).hexdigest()
        or report["runtime_sha256"] != runtime_sha256
        or report["config_sha256"] != pipeline._sha(recipe["config"])
        or report["tasks_sha256"] != tasks.fingerprint()
        or report["agent_sha256"] != Selection.from_bytes(_json(owner["selection"])).agent_sha256
        or type(report["max_callbacks"]) is not int
        or report["max_callbacks"] != recipe["max_callbacks"]
    ):
        raise CandidateGenerationError("generation outcome identity, terminal or prefix differs")
    declared = _object(outcome["artifacts"])
    for name, digest in declared.items():
        if hashlib.sha256(read(attempt / _path(name))).hexdigest() != _digest(digest):
            raise CandidateGenerationError("generation outcome artifact differs")
    expected = {"session/report.json", "session/done.json"}
    outputs = {}
    if outcome["disposition"] == "generated":
        if terminal["ready_seen"] is not True or done["status"] != "complete":
            raise CandidateGenerationError("generated C1 has no ready completed terminal")
        outputs = _outputs(
            attempt / "session", report, recipe, tasks, descriptor_raw, runtime_sha256, owner
        )
        answers = Answers.from_bytes(read(attempt / "session/answers.json"))
        if _json(
            cast(list[dict[str, object]], answers.to_record()["outputs"])[0]["answers"]
        ) != _json(done["answers"]):
            raise CandidateGenerationError("generated C1 differs from accepted literal answers")
        expected.add("session/answers.json")
    elif (
        report["status"] != "failed"
        or report["reason"] != "agent_error"
        or type(done["answers"]) is not list
        or done["answers"]
        or report["artifacts"] != {}
        or (terminal["ready_seen"] is False and count != 0)
    ):
        raise CandidateGenerationError("source failure is not a clean accepted agent_error")
    if set(declared) != expected:
        raise CandidateGenerationError("generation outcome output population differs")
    return outputs


def _source_reference(
    directory: Path, seal: Path, owner: dict[str, object], recipe_format: object
) -> dict[str, object]:
    return {
        "format": generation_formats(recipe_format)["source"],
        "generation_directory": str(directory),
        "stage_seal_sha256": file_hash(seal),
        "owner_manifest_sha256": pipeline._sha(owner),
        "owner_ledger_sha256": file_hash(directory / "owners/0/operations.sqlite3"),
    }


def _v2_report(
    outcome: dict[str, object],
    generation: dict[str, object],
    reference: dict[str, object],
    authorization: dict[str, object],
) -> dict[str, object]:
    return {
        "format": "buddha.candidate-generation-stage-report.v2",
        "status": "complete",
        "disposition": outcome["disposition"],
        "reason": outcome["reason"],
        "stage_seal_sha256": reference["stage_seal_sha256"],
        "generation": generation,
        "outcome": outcome,
        "source_generation": reference,
        "authorization": authorization,
        "claim": CLAIM_V2,
    }


@_checked
def run_candidate_generation(directory: Path, *, transport: RawHTTPTransport) -> dict[str, object]:
    """Execute or replay the same original source owner and retain partial work."""
    if not isinstance(directory, Path) or not isinstance(transport, RawHTTPTransport):
        raise CandidateGenerationError("generation needs its explicit Path and raw transport")
    directory = pipeline._absolute(str(directory))
    original = _read_manifest(directory / "owners/0")
    authority_path = pipeline._absolute(original["authorization_path"])
    if trial_fence.is_closed(directory):
        return inspect_candidate_generation(
            directory,
            authorization=authority_path,
            expected_report_sha256=file_hash(directory / "report.json"),
        )
    with (
        trial_fence.work(
            authority_path,
            Authorization(authority_path)._terms(),
            directory=directory,
            kind="generation",
        ),
        pipeline._exclusive(directory),
    ):
        gateway = Gateway(directory / "owners/0", transport=transport)
        owner = _read_manifest(gateway.directory)
        bindings = {
            Path(_text(row["path"])): row["sha256"]
            for row in cast(list[dict[str, object]], _object(owner["invocation"])["inputs"])
        }

        def consume(path: Path) -> bytes:
            if path not in bindings:
                raise CandidateGenerationError("generation input was not original")
            return pipeline._read(path, bindings[path])

        context = _object(
            _load(consume(directory / "context.json")),
            {
                "format",
                "descriptor",
                "expected_runtime_sha256",
            },
        )
        if context["format"] not in {CONTEXT_FORMAT, CONTEXT_FORMAT_V2}:
            raise CandidateGenerationError("unsupported candidate producer context")
        descriptor = pipeline._absolute(context["descriptor"])
        runtime_sha256 = _digest(context["expected_runtime_sha256"])
        recipe, tasks = _recipe(consume, descriptor, runtime_sha256)
        formats = generation_formats(recipe["format"])
        prospective = recipe["format"] == "buddha.candidate-generation.v2"
        if context["format"] != formats["context"]:
            raise CandidateGenerationError("candidate descriptor/context modes differ")
        _runtime_selection(
            recipe,
            Selection.from_bytes(_json(owner["selection"])),
            _object(owner["roots"]),
            consume,
            runtime_sha256,
        )
        for path in _sources(recipe["format"]):
            consume(path)
        authority = Authorization(pipeline._absolute(owner["authorization_path"]))
        actual_attempt: Path | None = None

        def run(attempt: Path) -> dict[str, object]:
            nonlocal actual_attempt
            actual_attempt = attempt
            # Every executing installed input was verified before this import.
            from buddha import candidate_run

            if (
                Path(candidate_run.__file__).absolute()
                != Path(__file__).with_name("candidate_run.py").absolute()
            ):
                raise CandidateGenerationError("a different source session was imported")
            if prospective:
                attempt.mkdir()
            session = candidate_run.CandidateSession(
                gateway,
                descriptor=descriptor,
                output=attempt / "session" if prospective else attempt,
                expected_runtime_sha256=runtime_sha256,
            )
            report = session.run()
            return _wrap_outcome(attempt, session, report) if prospective else report

        def validate(attempt: Path, report: dict[str, object]) -> dict[str, Path]:
            execution_identity(gateway.directory)
            for path in _sources(recipe["format"]):
                consume(path)
            if prospective:
                return _validate_outcome(
                    attempt,
                    report,
                    recipe,
                    tasks,
                    consume(descriptor),
                    runtime_sha256,
                    owner,
                    gateway.ledger.totals(),
                    lambda path: pipeline._read(path),
                )
            result = _outputs(
                attempt, report, recipe, tasks, consume(descriptor), runtime_sha256, owner
            )
            if report["gateway_totals"] != gateway.ledger.totals():
                raise CandidateGenerationError("candidate accounting changed before publication")
            return result

        def observation(reason: str, report: dict[str, object] | None) -> dict[str, object]:
            ordinal = 0
            while (directory / "observations" / f"{ordinal}.json").exists():
                ordinal += 1
            path = directory / "observations" / f"{ordinal}.json"
            value: dict[str, object] = {
                "format": "buddha.candidate-generation-observation.v2"
                if prospective
                else "buddha.candidate-generation-observation.v1",
                "status": "incomplete",
                "reason": reason,
                "owner": str(gateway.directory),
                "attempt": None
                if actual_attempt is None or not actual_attempt.is_dir()
                else str(actual_attempt),
                "generation": saved_session() if prospective else report,
                "authorization": authority.summary(),
                "observation": path.relative_to(directory).as_posix(),
            }
            if prospective:
                value.update(disposition=None, outcome=report)
            pipeline._write(path, _json(value))
            return value

        def saved_report() -> dict[str, object] | None:
            if actual_attempt is not None and (actual_attempt / "report.json").is_file():
                try:
                    return _load(pipeline._read(actual_attempt / "report.json"))
                except (ReleaseError, OSError):
                    # The original unavailable/malformed file remains at this attempt.
                    return None
            return None

        def saved_session() -> dict[str, object] | None:
            if actual_attempt is not None and (actual_attempt / "session/report.json").is_file():
                try:
                    return _load(pipeline._read(actual_attempt / "session/report.json"))
                except (ReleaseError, OSError):
                    return None
            return None

        try:
            report, _, _, sealed, _ = pipeline.execute_stage(
                directory,
                0,
                gateway,
                authority,
                run=run,
                validate=validate,
                seal_format=formats["seal"],
                anchor_prefix=formats["anchor"],
            )
        except KeyboardInterrupt:
            observation("cancelled", saved_report())
            raise
        except (ValueError, TypeError, KeyError, OSError, RecursionError):
            if actual_attempt is not None and actual_attempt.is_dir():
                observation("protocol", saved_report())
            raise
        if sealed is None:
            return observation(_text(report["reason"]), report)
        if prospective:
            seal = _load(pipeline._read(sealed))
            attempt = directory / _path(seal["attempt"])
            raw_report = _load(pipeline._read(attempt / "session/report.json"))
            return pipeline.publish_complete(
                directory / "report.json",
                _v2_report(
                    report,
                    raw_report,
                    _source_reference(directory, sealed, owner, recipe["format"]),
                    authority.summary(),
                ),
                authority,
                {_text(owner["run_id"])},
            )
        return pipeline.publish_complete(
            directory / "report.json",
            {
                "format": "buddha.candidate-generation-stage-report.v1",
                "status": "complete",
                "stage_seal_sha256": file_hash(sealed),
                "generation": report,
                "authorization": authority.summary(),
                "claim": (
                    "anchored source generation only; "
                    "no development eligibility or improvement claim"
                ),
            },
            authority,
            {_text(owner["run_id"])},
        )


def _read_evidence(
    value: object,
    authority_path: Path,
    *,
    capture: _Capture | None = None,
) -> dict[str, object]:
    """Read original inactive evidence without the producer's source or Gateway."""
    reference = _object(
        value,
        {
            "format",
            "generation_directory",
            "stage_seal_sha256",
            "owner_manifest_sha256",
            "owner_ledger_sha256",
        },
    )
    if reference["format"] not in {SOURCE_FORMAT, SOURCE_FORMAT_V2}:
        raise CandidateGenerationError("unsupported candidate source reference")
    prospective = reference["format"] == SOURCE_FORMAT_V2
    formats = generation_formats(
        "buddha.candidate-generation.v2" if prospective else "buddha.candidate-generation.v1"
    )
    root = pipeline._absolute(reference["generation_directory"])
    _root(root)
    capture = capture if capture is not None else _Capture(root)
    owner_path = root / "owners/0"
    history = read_gateway_history(
        owner_path,
        manifest_sha256=_digest(reference["owner_manifest_sha256"]),
        ledger_sha256=_digest(reference["owner_ledger_sha256"]),
    )
    observed = _owner(capture, owner_path)
    if (
        observed.manifest_sha256 != history.manifest_sha256
        or observed.ledger_sha256 != history.ledger_sha256
    ):
        raise CandidateGenerationError("candidate source changed during observation")
    funding = _authority(capture, authority_path, [observed])
    if (
        funding is None
        or pipeline._absolute(history.manifest["authorization_path"]) != authority_path
    ):
        raise CandidateGenerationError("candidate source belongs to another authority")
    if prospective:
        owner_names = {name.split("/")[1] for name in capture.entries if name.startswith("owners/")}
        seals = {name for name in capture.entries if name.startswith("completed/")}
        if owner_names != {"0"} or seals != {"completed/0.json"}:
            raise CandidateGenerationError("generation outcome has foreign owners or seals")
        for row in cast(list[dict[str, object]], funding["auth_runs"]):
            path = pipeline._absolute(row["directory"])
            if path.is_relative_to(root) and (
                path != owner_path or row["run_id"] != history.run_id
            ):
                raise CandidateGenerationError("a retained funded generation owner is missing")
    rows = [
        row
        for row in cast(list[dict[str, object]], funding["auth_runs"])
        if row["run_id"] == history.run_id
    ]
    if (
        len(rows) != 1
        or type(rows[0]["historical"]) is not int
        or rows[0]["historical"] != 0
        or rows[0]["runtime_sha256"] != history.manifest["execution_sha256"]
        or any(operation.status != "completed" for operation in history.operations)
    ):
        raise CandidateGenerationError(
            "candidate source is not an inactive complete original owner"
        )
    seal_raw = capture.read(root / "completed/0.json")
    seal_sha256 = hashlib.sha256(seal_raw).hexdigest()
    anchors = [
        row
        for row in cast(list[dict[str, object]], funding["auth_deactivations"])
        if row["run_id"] == history.run_id
    ]
    if (
        seal_sha256 != _digest(reference["stage_seal_sha256"])
        or len(anchors) != 1
        or anchors[0]["reason"] != formats["anchor"] + seal_sha256
    ):
        raise CandidateGenerationError("candidate source lacks its original independent anchor")
    seal = _object(_load(seal_raw), {"format", "index", "owner_sha256", "attempt", "files"})
    relative = Path(_path(seal["attempt"]))
    if (
        seal["format"] != formats["seal"]
        or type(seal["index"]) is not int
        or seal["index"] != 0
        or seal["owner_sha256"] != history.manifest_sha256
        or len(relative.parts) != 2
        or relative.parts[0] != "attempts"
        or not relative.name.startswith("0-")
    ):
        raise CandidateGenerationError("candidate source completion identity differs")
    attempt = root / relative
    outcome = _load(capture.read(attempt / "report.json")) if prospective else None
    expected_files = (
        {"report.json", "session/report.json", "session/done.json"}
        | (
            {"session/answers.json"}
            if outcome is not None and outcome.get("disposition") == "generated"
            else set()
        )
        if prospective
        else {"report.json", "answers.json"}
    )
    prefix = attempt.relative_to(root).as_posix() + "/"
    actual_entries = {
        name.removeprefix(prefix) for name in capture.entries if name.startswith(prefix)
    }
    if (
        actual_entries != expected_files | ({"session"} if prospective else set())
        or set(_object(seal["files"])) != expected_files
    ):
        raise CandidateGenerationError("candidate source output inventory differs")
    for name, digest in _object(seal["files"]).items():
        if hashlib.sha256(capture.read(attempt / _path(name))).hexdigest() != _digest(digest):
            raise CandidateGenerationError("candidate source artifact changed")
    bindings = {
        Path(_text(row["path"])): row["sha256"]
        for row in cast(list[dict[str, object]], _object(history.manifest["invocation"])["inputs"])
    }

    def bound(path: Path) -> bytes:
        raw = capture.read(path)
        if hashlib.sha256(raw).hexdigest() != bindings.get(path):
            raise CandidateGenerationError("candidate source data was not an original input")
        return raw

    context = _object(
        _load(bound(root / "context.json")), {"format", "descriptor", "expected_runtime_sha256"}
    )
    if context["format"] != formats["context"]:
        raise CandidateGenerationError("candidate source context differs")
    runtime_sha256 = _digest(context["expected_runtime_sha256"])
    descriptor = pipeline._absolute(context["descriptor"])
    recipe, tasks = _recipe(bound, descriptor, runtime_sha256)
    if generation_formats(recipe["format"]) != formats:
        raise CandidateGenerationError("candidate source modes differ")
    if prospective:
        names = {
            path.name
            for path in _recorded_sources(_sources(recipe["format"]), history.manifest["core"])
        }
        prefixes = {
            path.parent
            for path in bindings
            if path.name == "candidate_generation.py"
            and all(path.parent / name in bindings for name in names)
        }
        if len(prefixes) != 1:
            raise CandidateGenerationError("generation outcome omits original installed sources")
    owner = history.manifest
    selection = Selection.from_bytes(_json(owner["selection"]))
    _runtime_selection(recipe, selection, _object(owner["roots"]), bound, runtime_sha256)
    entrypoint = _path(recipe["entrypoint"])
    if tasks.release_sha256 != selection.release_sha256 or set(
        _object(_object(selection.to_record()["components"])["agent"])
    ) != {entrypoint}:
        raise CandidateGenerationError("candidate source task/program selection differs")
    config = _object(
        recipe["config"], {"provider", "model", "max_output_tokens", "instructions", "sampling"}
    )
    if (
        config["provider"] not in {"openai", "anthropic"}
        or len(_utf8(config["instructions"])) > 4000
        or config["sampling"] not in {"regenerate", "in-context"}
    ):
        raise CandidateGenerationError("candidate source configuration is unsupported")
    _text(config["model"])
    _integer(config["max_output_tokens"], 1)
    role = _object(recipe["profile"], {"capability", "profile_id"})
    profile = _object(_object(_object(owner["profiles"])[_text(role["capability"])])["profiles"])[
        _text(role["profile_id"])
    ]
    spec = _object(_object(profile)["spec"])
    if any(spec[key] != config[key] for key in ("provider", "model", "max_output_tokens")):
        raise CandidateGenerationError("candidate source profile differs")
    report = _load(
        capture.read(attempt / ("session/report.json" if prospective else "report.json"))
    )
    if prospective:
        _validate_outcome(
            attempt,
            cast(dict[str, object], outcome),
            recipe,
            tasks,
            bound(descriptor),
            runtime_sha256,
            owner,
            history.totals(),
            capture.read,
        )
    else:
        _outputs(attempt, report, recipe, tasks, bound(descriptor), runtime_sha256, owner)
    totals = _object(report["gateway_totals"])
    if (
        any(type(item) is not int for item in totals.values())
        or totals != history.totals()
        or _object(report["calls"])["completed"] != len(history.operations)
    ):
        raise CandidateGenerationError("candidate source callback/accounting coverage differs")
    expected_ids = {
        pipeline._sha(
            [
                "buddha.candidate-call.v1",
                hashlib.sha256(bound(descriptor)).hexdigest(),
                selection.agent_sha256,
                tasks.fingerprint(),
                ordinal,
            ]
        )
        for ordinal in range(len(history.operations))
    }
    observed_ids = set()
    for operation in history.operations:
        request = _object(_object(operation.receipt)["request"])
        # History already checked the literal type, encoding and request-byte ceiling.
        body = _object(_load(base64.b64decode(cast(str, request["body_base64"]), validate=True)))
        cap = "max_tokens" if config["provider"] == "anthropic" else "max_completion_tokens"
        if (
            request["capability"] != role["capability"]
            or request["profile_id"] != role["profile_id"]
            or type(request["attempt"]) is not int
            or request["attempt"] != 0
            or body.get("model") != config["model"]
            or type(body.get(cap)) is not int
            or ("max_tokens" in body and "max_completion_tokens" in body)
            or not 1 <= cast(int, body[cap]) <= cast(int, config["max_output_tokens"])
        ):
            raise CandidateGenerationError("candidate source callback changes original contract")
        observed_ids.add(_text(request["logical_id"]))
    if observed_ids != expected_ids or len(observed_ids) != len(history.operations):
        raise CandidateGenerationError("candidate source skipped its original callback prefix")
    generated = not prospective or cast(dict[str, object], outcome)["disposition"] == "generated"
    answers_path = (
        attempt / ("session/answers.json" if prospective else "answers.json") if generated else None
    )
    answers = Answers.from_bytes(capture.read(answers_path)) if answers_path is not None else None
    capture.finish()
    return {
        "tasks": tasks,
        "answers": answers,
        "answers_path": answers_path,
        "files": {
            path: hashlib.sha256(raw).hexdigest()
            for path, raw in capture.raw.items()
            if path != authority_path
        },
        "terms": _object(funding["config"]),
        "generation": report,
        "outcome": outcome,
        "reference": reference,
        "funding": funding,
        "owner": owner,
        "capture": capture,
    }


def _source_from_evidence(
    evidence: dict[str, object],
) -> tuple[TaskSet, Answers, Path, dict[Path, str], dict[str, object]]:
    """Project checked C1 without adding publication-only invocation bindings."""
    if evidence["answers"] is None or evidence["answers_path"] is None:
        raise CandidateGenerationError("a checked source failure has no C1 answers")
    publication = cast(_Capture, evidence["capture"]).root / "report.json"
    return (
        cast(TaskSet, evidence["tasks"]),
        cast(Answers, evidence["answers"]),
        cast(Path, evidence["answers_path"]),
        {
            path: digest
            for path, digest in cast(dict[Path, str], evidence["files"]).items()
            if path != publication
        },
        cast(dict[str, object], evidence["terms"]),
    )


@_checked
def read_candidate_generation_source(
    value: object,
    authority_path: Path,
) -> tuple[TaskSet, Answers, Path, dict[Path, str], dict[str, object]]:
    """Read only generated C1; a checked failed execution is never an answer source."""
    return _source_from_evidence(_read_evidence(value, authority_path))


@_checked
def _read_published_evidence(
    directory: Path, *, authorization: Path, expected_report_sha256: str
) -> tuple[dict[str, object], dict[str, object]]:
    """Check one published v2 outcome and retain the complete original observation."""
    from buddha.native_evidence import authority_observation

    if not isinstance(directory, Path) or not isinstance(authorization, Path):
        raise CandidateGenerationError("generation inspection needs explicit Paths")
    directory, authorization = (
        pipeline._absolute(str(directory)),
        pipeline._absolute(str(authorization)),
    )
    capture = _Capture(directory)
    raw = capture.read(directory / "report.json")
    if hashlib.sha256(raw).hexdigest() != _digest(expected_report_sha256):
        raise CandidateGenerationError("generation publication differs from caller approval")
    saved = _load(raw)
    owner_path = directory / "owners/0"
    observed = _owner(capture, owner_path)
    reference: dict[str, object] = {
        "format": SOURCE_FORMAT_V2,
        "generation_directory": str(directory),
        "stage_seal_sha256": hashlib.sha256(
            capture.read(directory / "completed/0.json")
        ).hexdigest(),
        "owner_manifest_sha256": observed.manifest_sha256,
        "owner_ledger_sha256": observed.ledger_sha256,
    }
    evidence = _read_evidence(reference, authorization, capture=capture)
    current = authority_observation(
        capture, authorization, cast(dict[str, object], evidence["funding"])
    )
    snapshot = _object(saved.get("authorization"))
    pipeline.validate_authorization_snapshot(
        snapshot, current, {_text(_object(evidence["owner"])["run_id"])}
    )
    reconstructed = _v2_report(
        _object(evidence["outcome"]),
        _object(evidence["generation"]),
        reference,
        snapshot,
    )
    if raw != _json(saved) or _json(saved) != _json(reconstructed):
        raise CandidateGenerationError("generation publication differs from its sealed outcome")
    capture.finish()
    return saved, evidence


@_checked
def inspect_candidate_generation(
    directory: Path, *, authorization: Path, expected_report_sha256: str
) -> dict[str, object]:
    """Passively check a published v2 outcome, including original independent anchor."""
    return _read_published_evidence(
        directory, authorization=authorization, expected_report_sha256=expected_report_sha256
    )[0]
