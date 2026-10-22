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
from buddha.answers import Answers, TaskSet, _utf8
from buddha.authorization import Authorization
from buddha.doctor import _authority, _Busy, _Capture, _owner, _Unsupported
from buddha.gateway import (
    Gateway,
    RawHTTPTransport,
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


def _sources() -> list[Path]:
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
        "native_pipeline",
        "doctor",
        "process_observation",
        "gateway_history",
        "history",
        "search_evidence",
    )
    package = Path(__file__).absolute().parent
    return [package / (name + ".py") for name in names]


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
    if recipe["format"] != "buddha.candidate-generation.v1":
        raise CandidateGenerationError("only explicit candidate generation is supported")
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
    expected = {Path(row["path"]): row["sha256"] for row in controls}

    def consume(path: Path) -> bytes:
        raw = pipeline._read(path, expected.get(path))
        expected[path] = hashlib.sha256(raw).hexdigest()
        return raw

    recipe, tasks = _recipe(consume, descriptor, runtime_sha256)
    _runtime_selection(recipe, selection, roots, consume, runtime_sha256)
    if tasks.release_sha256 != selection.release_sha256:
        raise CandidateGenerationError("source task differs from selected release")
    for path in _sources():
        consume(path)
    protected = [*roots.values(), descriptor, *expected, authorization.path]
    if any(directory.is_relative_to(path) or path.is_relative_to(directory) for path in protected):
        raise CandidateGenerationError("generation output overlaps original inputs")
    _root(directory.parent)
    _path(directory.name)
    directory.mkdir()
    for name in ("owners", "attempts", "completed", "observations"):
        (directory / name).mkdir()
    context = directory / "context.json"
    context_raw = _json(
        {
            "format": CONTEXT_FORMAT,
            "descriptor": str(descriptor),
            "expected_runtime_sha256": runtime_sha256,
        }
    )
    pipeline._write(context, context_raw)
    expected[context] = hashlib.sha256(context_raw).hexdigest()
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


@_checked
def run_candidate_generation(directory: Path, *, transport: RawHTTPTransport) -> dict[str, object]:
    """Execute or replay the same original source owner and retain partial work."""
    if not isinstance(directory, Path):
        raise CandidateGenerationError("generation needs an explicit Path")
    directory = pipeline._absolute(str(directory))
    with pipeline._exclusive(directory):
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
        if context["format"] != CONTEXT_FORMAT:
            raise CandidateGenerationError("unsupported candidate producer context")
        descriptor = pipeline._absolute(context["descriptor"])
        runtime_sha256 = _digest(context["expected_runtime_sha256"])
        recipe, tasks = _recipe(consume, descriptor, runtime_sha256)
        _runtime_selection(
            recipe,
            Selection.from_bytes(_json(owner["selection"])),
            _object(owner["roots"]),
            consume,
            runtime_sha256,
        )
        for path in _sources():
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
            return candidate_run.CandidateSession(
                gateway,
                descriptor=descriptor,
                output=attempt,
                expected_runtime_sha256=runtime_sha256,
            ).run()

        def validate(attempt: Path, report: dict[str, object]) -> dict[str, Path]:
            execution_identity(gateway.directory)
            for path in _sources():
                consume(path)
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
                "format": "buddha.candidate-generation-observation.v1",
                "status": "incomplete",
                "reason": reason,
                "owner": str(gateway.directory),
                "attempt": None
                if actual_attempt is None or not actual_attempt.is_dir()
                else str(actual_attempt),
                "generation": report,
                "authorization": authority.summary(),
                "observation": path.relative_to(directory).as_posix(),
            }
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

        try:
            report, _, _, sealed, _ = pipeline.execute_stage(
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
            observation("cancelled", saved_report())
            raise
        except (ValueError, TypeError, KeyError, OSError, RecursionError):
            if actual_attempt is not None and actual_attempt.is_dir():
                observation("protocol", saved_report())
            raise
        if sealed is None:
            return observation(_text(report["reason"]), report)
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


@_checked
def read_candidate_generation_source(
    value: object,
    authority_path: Path,
) -> tuple[TaskSet, Answers, Path, dict[Path, str], dict[str, object]]:
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
    if reference["format"] != SOURCE_FORMAT:
        raise CandidateGenerationError("unsupported candidate source reference")
    root = pipeline._absolute(reference["generation_directory"])
    _root(root)
    capture = _Capture(root)
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
        or anchors[0]["reason"] != ANCHOR_PREFIX + seal_sha256
    ):
        raise CandidateGenerationError("candidate source lacks its original independent anchor")
    seal = _object(_load(seal_raw), {"format", "index", "owner_sha256", "attempt", "files"})
    relative = Path(_path(seal["attempt"]))
    if (
        seal["format"] != SEAL_FORMAT
        or type(seal["index"]) is not int
        or seal["index"] != 0
        or seal["owner_sha256"] != history.manifest_sha256
        or len(relative.parts) != 2
        or relative.parts[0] != "attempts"
        or not relative.name.startswith("0-")
    ):
        raise CandidateGenerationError("candidate source completion identity differs")
    attempt = root / relative
    expected_files = {"report.json", "answers.json"}
    prefix = attempt.relative_to(root).as_posix() + "/"
    actual_entries = {
        name.removeprefix(prefix) for name in capture.entries if name.startswith(prefix)
    }
    if actual_entries != expected_files or set(_object(seal["files"])) != expected_files:
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
    if context["format"] != CONTEXT_FORMAT:
        raise CandidateGenerationError("candidate source context differs")
    runtime_sha256 = _digest(context["expected_runtime_sha256"])
    descriptor = pipeline._absolute(context["descriptor"])
    recipe, tasks = _recipe(bound, descriptor, runtime_sha256)
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
    report = _load(capture.read(attempt / "report.json"))
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
    answers_path = attempt / "answers.json"
    answers = Answers.from_bytes(capture.read(answers_path))
    capture.finish()
    return (
        tasks,
        answers,
        answers_path,
        {
            path: hashlib.sha256(raw).hexdigest()
            for path, raw in capture.raw.items()
            if path != authority_path
        },
        _object(funding["config"]),
    )
