"""Fresh native assessment of one already anchored generation, without generation.

Original generation is passive evidence, never an executing Gateway or runtime.
New occasions use new owners; recovery retains this occasion's original owners.
"""

import hashlib
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from functools import partial, wraps
from pathlib import Path
from typing import cast

from buddha import native_pipeline as pipeline
from buddha import native_run
from buddha.answers import Answers, TaskSet, _utf8
from buddha.authorization import Authorization
from buddha.doctor import _authority, _Busy, _Capture, _owner
from buddha.gateway import (
    Gateway,
    RawHTTPTransport,
    _input_records,
    _read_manifest,
    execution_identity,
    prepare_gateway,
)
from buddha.gateway_history import read_gateway_history
from buddha.ledger import BudgetExceeded
from buddha.releases import (
    Release,
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
    inventory,
)

FORMAT = "buddha.native-evaluation.v1"


class EvaluationError(ReleaseError):
    """The source generation, native occasion or retained evidence is invalid."""


def _checked[**P, T](function: Callable[P, T]) -> Callable[P, T]:
    @wraps(function)
    def checked(*args: P.args, **kwargs: P.kwargs) -> T:
        try:
            return function(*args, **kwargs)
        except (ValueError, TypeError, KeyError, OSError, RecursionError, _Busy) as error:
            if isinstance(error, EvaluationError):
                raise
            raise EvaluationError(
                "native evaluation evidence is invalid; original state retained"
            ) from None

    return checked


@dataclass(frozen=True)
class _Generation:
    tasks: TaskSet
    answers: Answers
    answers_path: Path
    files: dict[Path, str]
    authority_config: dict[str, object]


def _generation(value: object, authority: Authorization) -> _Generation:
    return _read_generation(value, authority.path)


def _read_generation(value: object, authority_path: Path) -> _Generation:
    """Verify retained generation using an explicit authority file, without execution."""
    reference = _object(
        value,
        {"baseline_directory", "stage_seal_sha256", "owner_manifest_sha256", "owner_ledger_sha256"},
    )
    root = pipeline._absolute(reference["baseline_directory"])
    _root(root)
    capture = _Capture(root)
    source_dir = root / "owners/0"
    history = read_gateway_history(
        source_dir,
        manifest_sha256=_digest(reference["owner_manifest_sha256"]),
        ledger_sha256=_digest(reference["owner_ledger_sha256"]),
    )
    observed = _owner(capture, source_dir)
    if (
        observed.manifest_sha256 != history.manifest_sha256
        or observed.ledger_sha256 != history.ledger_sha256
    ):
        raise EvaluationError("source generation changed while observed")
    funding = _authority(capture, authority_path, [observed])
    if (
        funding is None
        or pipeline._absolute(history.manifest["authorization_path"]) != authority_path
    ):
        raise EvaluationError("source generation belongs to another shared authority")
    funded_sources = [
        row
        for row in cast(list[dict[str, object]], funding["auth_runs"])
        if row["run_id"] == history.run_id
    ]
    if (
        len(funded_sources) != 1
        or type(funded_sources[0]["historical"]) is not int
        or funded_sources[0]["historical"] != 0
        or funded_sources[0]["runtime_sha256"] != history.manifest["execution_sha256"]
    ):
        raise EvaluationError("source authority runtime differs from its original owner")
    if any(operation.status != "completed" for operation in history.operations):
        raise EvaluationError("source generation contains unfinished physical operations")
    sealed = root / "completed/0.json"
    seal_raw = capture.read(sealed)
    digest = hashlib.sha256(seal_raw).hexdigest()
    if digest != _digest(reference["stage_seal_sha256"]):
        raise EvaluationError("source generation seal differs")
    anchors = [
        row
        for row in cast(list[dict[str, object]], funding["auth_deactivations"])
        if row["run_id"] == history.run_id
    ]
    if len(anchors) != 1 or anchors[0]["reason"] != "baseline completed: " + digest:
        raise EvaluationError("source generation lacks its original authority anchor")
    seal = _object(_load(seal_raw), {"format", "index", "owner_sha256", "attempt", "files"})
    if (
        seal["format"] != "buddha.baseline-stage.v1"
        or type(seal["index"]) is not int
        or seal["index"] != 0
        or seal["owner_sha256"] != history.manifest_sha256
    ):
        raise EvaluationError("source generation completion identity differs")
    relative = _path(seal["attempt"])
    if (
        len(Path(relative).parts) != 2
        or Path(relative).parts[0] != "attempts"
        or not Path(relative).name.startswith("0-")
    ):
        raise EvaluationError("source generation attempt is outside its declared stage")
    attempt = root / relative
    files = _object(seal["files"])
    if inventory(attempt) != files:
        raise EvaluationError("source generation attempt inventory differs")
    for name, expected in files.items():
        if hashlib.sha256(capture.read(attempt / _path(name))).hexdigest() != _digest(expected):
            raise EvaluationError("source generation artifact differs")
    report = _load(capture.read(attempt / "report.json"))
    bindings = {
        _text(item["path"]): _digest(item["sha256"])
        for item in cast(list[dict[str, object]], _object(history.manifest["invocation"])["inputs"])
    }

    def bound(path: Path) -> bytes:
        raw = capture.read(path)
        if hashlib.sha256(raw).hexdigest() != bindings.get(str(path)):
            raise EvaluationError("source generation data is not an original invocation input")
        return raw

    context = _object(_load(bound(root / "context.json")), {"format", "descriptor"})
    if context["format"] != "buddha.baseline-context.v1":
        raise EvaluationError("unsupported generation producer context")
    definition = _object(
        _load(bound(pipeline._absolute(context["descriptor"]))),
        {"format", "tasks", "generation", "native", "stages"},
    )
    if definition["format"] != "buddha.native-baseline.v1":
        raise EvaluationError("unsupported generation producer descriptor")
    producer = _object(definition["generation"])
    selection = Selection.from_bytes(_json(producer["selection"]))
    if selection.to_record() != history.manifest["selection"]:
        raise EvaluationError("source generation selection differs from its owner")
    tasks_path = pipeline._absolute(definition["tasks"])
    task_raw = bound(tasks_path)
    tasks = TaskSet.from_bytes(task_raw)
    recipe_path = pipeline._absolute(producer["descriptor"])
    recipe_raw = bound(recipe_path)
    recipe = _object(
        _load(recipe_raw), {"format", "tasks", "config", "entrypoint", "executor", "profile"}
    )
    config = _object(
        recipe["config"], {"provider", "model", "max_output_tokens", "instructions", "sampling"}
    )
    instructions = _utf8(config["instructions"])
    cap = config["max_output_tokens"]
    if (
        recipe["format"] != "buddha.frozen-generation.v1"
        or type(config["provider"]) is not str
        or config["provider"] not in {"openai", "anthropic"}
        or type(cap) is not int
        or not 1 <= cap <= 2**63 - 1
        or len(instructions) > 4000
        or type(config["sampling"]) is not str
        or config["sampling"] not in {"regenerate", "in-context"}
    ):
        raise EvaluationError("source generation configuration is unsupported")
    _text(config["model"])
    role = _object(recipe["profile"], {"capability", "profile_id"})
    source_profile = _object(
        _object(_object(history.manifest["profiles"])[_text(role["capability"])])["profiles"]
    )
    spec = _object(_object(source_profile[_text(role["profile_id"])])["spec"])
    if any(spec[key] != config[key] for key in ("provider", "model", "max_output_tokens")):
        raise EvaluationError("source generation profile differs from its treatment")
    if pipeline._absolute(recipe["tasks"]) != tasks_path:
        raise EvaluationError("source generation recipe changes task input")
    answers_path = attempt / "answers.json"
    answer_raw = capture.read(answers_path)
    answers = Answers.from_bytes(answer_raw)
    answer_record = answers.to_record()
    totals = _object(report.get("gateway_totals"))
    if any(type(item) is not int for item in totals.values()) or totals != history.totals():
        raise EvaluationError("source generation accounting differs")
    if (
        report.get("format") != "buddha.generation-report.v1"
        or report.get("status") != "complete"
        or report.get("reason") != "complete"
        or report.get("gateway_manifest_sha256") != history.manifest_sha256
        or report.get("descriptor_sha256") != hashlib.sha256(recipe_raw).hexdigest()
        or report.get("config_sha256") != pipeline._sha(recipe["config"])
        or report.get("tasks_sha256") != tasks.fingerprint()
        or report.get("tasks_file_sha256") != hashlib.sha256(task_raw).hexdigest()
        or report.get("agent_sha256") != selection.agent_sha256
        or answer_record["tasks_sha256"] != tasks.fingerprint()
        or answer_record["agent_sha256"] != selection.agent_sha256
        or tasks.release_sha256 != selection.release_sha256
        or answer_record["metadata"] != {}
        or _object(report["artifacts"]).get("answers.json")
        != hashlib.sha256(answer_raw).hexdigest()
    ):
        raise EvaluationError("source C1/report/task/treatment lineage differs")
    for name in ("expected_tasks", "completed_tasks"):
        if type(report.get(name)) is not int or report[name] != len(tasks.tasks):
            raise EvaluationError("source generation population counters differ")
    calls = _object(report["calls"], {"requested", "completed", "stopped"})
    count = sum(task.count for task in tasks.tasks)
    if (
        any(type(item) is not int for item in calls.values())
        or calls != {"requested": count, "completed": count, "stopped": 0}
        or len(history.operations) != count
    ):
        raise EvaluationError("source generation callback coverage differs")
    executions = report["executions"]
    if type(executions) is not list or len(executions) != len(tasks.tasks):
        raise EvaluationError("source generation lacks execution population coverage")
    for value in executions:
        execution = _object(value)
        if (
            type(execution.get("exit_code")) is not int
            or execution["exit_code"] != 0
            or execution.get("cleanup_status") != "removed"
            or execution.get("image_id") != _object(recipe["executor"])["image_id"]
        ):
            raise EvaluationError("source generation lacks positive owned cleanup")
    entrypoint = _path(recipe["entrypoint"])
    if report.get("seed_source_sha256") != _object(
        _object(selection.to_record()["components"])["agent"]
    ).get(entrypoint):
        raise EvaluationError("source generation program identity differs")
    capture.finish()
    protected = {
        path: hashlib.sha256(raw).hexdigest()
        for path, raw in capture.raw.items()
        if path != authority_path
    }
    return _Generation(tasks, answers, answers_path, protected, _object(funding["config"]))


def _definition(
    path: Path, authority: Authorization, expected: object = None
) -> tuple[dict[str, object], _Generation, Release]:
    definition = _object(
        _load(pipeline._read(path, expected)), {"format", "source_generation", "native", "stages"}
    )
    if definition["format"] != FORMAT:
        raise EvaluationError("unsupported native evaluation descriptor")
    source = _generation(definition["source_generation"], authority)
    native = _object(definition["native"])
    selected, _ = pipeline._component(native)
    if selected.release_sha256 != source.tasks.release_sha256:
        raise EvaluationError("new evaluation instrument changes the original C1 release")
    release = Release.from_record(selected.to_record()["release"])
    pipeline.validate_native(native, definition["stages"], release)
    return definition, source, release


def _sources() -> list[Path]:
    package = Path(__file__).absolute().parent
    names = tuple(
        dict.fromkeys(
            (
                *native_run.RUNNER_FILES,
                "executor",
                "native_run",
                "answers",
                "native_pipeline",
                "native_evaluation",
                "doctor",
                "process_observation",
                "gateway_history",
                "history",
                "search_evidence",
            )
        )
    )
    return [package / (name + ".py") for name in names]


def _owner_stage(
    directory: Path,
    definition_path: Path,
    index: int,
    definition: dict[str, object],
    source: _Generation,
    release: Release,
    authority: Authorization,
    review: dict[str, object],
    available: dict[str, Path],
    frozen: dict[Path, str],
    seals: list[Path],
    control_inputs: Sequence[Path] = (),
    control_hashes: dict[str, object] | None = None,
) -> tuple[Path, Path]:
    descriptor, inputs = pipeline._native_descriptor(
        directory, index, definition, release, source.answers_path, available, frozen
    )
    native = _object(definition["native"])
    selected, roots = pipeline._component(native)
    no_model = index == len(cast(list[object], definition["stages"]))
    paths = [
        directory / "context.json",
        definition_path,
        *source.files,
        descriptor,
        *seals,
        *available.values(),
        *inputs,
        *_sources(),
        *control_inputs,
    ]
    if index > 1:
        paths.append(directory / "owners/1/manifest.json")
    paths = list(dict.fromkeys(path.absolute() for path in paths))
    expected_inputs = []
    for path in paths:
        digest = file_hash(path)
        expected = (control_hashes or {}).get(str(path), frozen.get(path, digest))
        if digest != expected:
            raise EvaluationError("an original control or sealed predecessor changed")
        expected_inputs.append({"path": str(path), "sha256": expected})
    for path, digest in frozen.items():
        if file_hash(path) != digest:
            raise EvaluationError("sealed predecessor changed before native owner preparation")
    owner = directory / "owners" / str(index)
    settings = {
        "budget_microusd": 1 if no_model else native["budget_microusd"],
        "max_calls": 1 if no_model else native["max_calls"],
    }
    if not owner.exists():
        prepare_gateway(
            owner,
            selection=selected,
            roots=roots,
            authorization=authority,
            budget_microusd=cast(int, settings["budget_microusd"]),
            max_calls=cast(int, settings["max_calls"]),
            input_files=paths,
            expected_input_hashes={
                Path(_text(row["path"])): _text(row["sha256"]) for row in expected_inputs
            },
            review=review,
        )
    record = _read_manifest(owner)
    if (
        record["authorization_path"] != str(authority.path)
        or record["selection"] != selected.to_record()
        or record["roots"] != {key: str(path) for key, path in roots.items()}
        or record["settings"] != settings
        or record["review"] != review
        or _object(record["invocation"])["inputs"] != expected_inputs
    ):
        raise EvaluationError("existing native owner differs from the original occasion")
    return owner, descriptor


@_checked
def prepare_evaluation(
    directory: Path,
    *,
    descriptor: Path,
    authorization: Authorization,
    review: dict[str, object],
    input_files: Sequence[Path] = (),
    expected_input_hashes: Mapping[Path, str] | None = None,
) -> Path:
    """Verify original generation and prepare a fresh native owner; no API calls."""
    if (
        not isinstance(directory, Path)
        or not isinstance(descriptor, Path)
        or not isinstance(authorization, Authorization)
    ):
        raise EvaluationError("evaluation requires explicit paths and an existing shared authority")
    if (
        not isinstance(input_files, (list, tuple))
        or len(input_files) > 1024
        or any(not isinstance(path, Path) for path in input_files)
    ):
        raise EvaluationError("evaluation controls require a bounded ordered Path list")
    controls = _input_records(input_files, expected_input_hashes)
    definition, source, release = _definition(descriptor, authorization)
    directory = directory.absolute()
    _root(directory.parent)
    _path(directory.name)
    roots = [
        pipeline._absolute(path)
        for path in _object(_object(definition["native"])["roots"]).values()
    ]
    roots.append(pipeline._absolute(_object(definition["source_generation"])["baseline_directory"]))
    if any(directory.is_relative_to(root) or root.is_relative_to(directory) for root in roots):
        raise EvaluationError("evaluation output overlaps selected inputs or original generation")
    directory.mkdir()
    for name in ("owners", "completed", "attempts", "staging", "observations"):
        (directory / name).mkdir()
    pipeline._write(
        directory / "context.json",
        _json(
            {
                "format": "buddha.native-evaluation-context.v1",
                "descriptor": str(descriptor.absolute()),
            }
        ),
    )
    native_answers = directory / "native-answers.jsonl"
    pipeline._write(native_answers, source.answers.native_bytes())
    frozen = source.files | {native_answers: file_hash(native_answers)}
    available = {_path(_object(release.to_record()["artifacts"])["answers"]): native_answers}
    _owner_stage(
        directory,
        descriptor.absolute(),
        1,
        definition,
        source,
        release,
        authorization,
        review,
        available,
        frozen,
        [],
        input_files,
        {row["path"]: row["sha256"] for row in controls},
    )
    return directory


def _partial(
    directory: Path,
    index: int,
    reports: list[dict[str, object]],
    authority: Authorization,
    reason: str,
    attempt: Path | None = None,
) -> dict[str, object]:
    if reason not in {"unknown", "authority", "protocol", "cancelled", "native_error"}:
        reason = "native_error"
    number = len(list((directory / "observations").iterdir()))
    path = directory / "observations" / (str(number) + ".json")
    result: dict[str, object] = {
        "format": "buddha.native-evaluation-report.v1",
        "status": "incomplete",
        "reason": reason,
        "stopped_stage": index,
        "attempt": None if attempt is None else attempt.relative_to(directory).as_posix(),
        "owner": "owners/" + str(index),
        "stages": reports,
        "authorization": authority.summary(),
        "observation": path.relative_to(directory).as_posix(),
        "claim": (
            "incomplete native occasion; original owners, raw replies, "
            "partial artifacts and holds retained"
        ),
    }
    pipeline._write(path, _json(result))
    return result


def _session(
    gateway: Gateway, descriptor: Path, started: list[Path], attempt: Path
) -> dict[str, object]:
    started.append(attempt)
    return native_run.NativeSession(gateway, descriptor=descriptor, output=attempt).run()


@_checked
def run_evaluation(directory: Path, *, transport: RawHTTPTransport) -> dict[str, object]:
    """Run or resume this original native occasion, without regenerating answers."""
    if not isinstance(directory, Path) or not isinstance(transport, RawHTTPTransport):
        raise EvaluationError("evaluation requires its original directory and raw transport")
    directory = directory.absolute()
    with pipeline._exclusive(directory):
        return _run(directory, transport)


def _run(directory: Path, transport: RawHTTPTransport) -> dict[str, object]:
    first = Gateway(directory / "owners/1", transport=transport)
    initial = _read_manifest(first.directory)
    bound = {
        _text(item["path"]): item["sha256"]
        for item in cast(list[dict[str, object]], _object(initial["invocation"])["inputs"])
    }
    context_path = directory / "context.json"
    context = _object(
        _load(pipeline._read(context_path, bound[str(context_path)])), {"format", "descriptor"}
    )
    if context["format"] != "buddha.native-evaluation-context.v1":
        raise EvaluationError("unsupported native evaluation context")
    path = pipeline._absolute(context["descriptor"])
    authority = Authorization(pipeline._absolute(initial["authorization_path"]))
    definition, source, release = _definition(path, authority, bound[str(path)])
    for item in _sources():
        if file_hash(item) != bound.get(str(item)):
            raise EvaluationError("native evaluation source is not frozen")
    native_answers = directory / "native-answers.jsonl"
    pipeline._same_or_write(native_answers, source.answers.native_bytes())
    frozen = source.files | {native_answers: file_hash(native_answers)}
    available = {_path(_object(release.to_record()["artifacts"])["answers"]): native_answers}
    reports: list[dict[str, object]] = []
    seals: list[Path] = []
    stages = cast(list[object], definition["stages"])
    owners = {item.name for item in (directory / "owners").iterdir()}
    completed = {item.name for item in (directory / "completed").iterdir()}
    if (
        owners != {str(index) for index in range(1, len(owners) + 1)}
        or len(owners) > len(stages)
        or completed != {str(index) + ".json" for index in range(1, len(completed) + 1)}
        or not {name.removesuffix(".json") for name in completed} <= owners
    ):
        raise EvaluationError("native occasion has foreign, aliased or orphan stage records")
    for index in range(1, len(stages) + 1):
        execution_identity(first.directory)
        _definition(path, authority, bound[str(path)])
        owner, descriptor = _owner_stage(
            directory,
            path,
            index,
            definition,
            source,
            release,
            authority,
            _object(initial["review"]),
            available,
            frozen,
            seals,
            [Path(path) for path in bound],
            bound,
        )
        gateway = (
            Gateway(owner, transport=RawHTTPTransport(allow_paid=False))
            if index == len(stages)
            else first
            if index == 1
            else Gateway(owner, transport=transport)
        )
        started: list[Path] = []
        try:
            report, outputs, files, sealed, attempt = pipeline.execute_stage(
                directory,
                index,
                gateway,
                authority,
                run=partial(_session, gateway, descriptor, started),
                validate=partial(
                    pipeline.native_outputs, index=index, definition=definition, tasks=source.tasks
                ),
                seal_format="buddha.native-evaluation-stage.v1",
                anchor_prefix="native evaluation completed: ",
            )
        except KeyboardInterrupt:
            _partial(
                directory,
                index,
                reports,
                authority,
                "cancelled",
                started[-1] if started else None,
            )
            raise
        except BudgetExceeded:
            return _partial(directory, index, reports, authority, "authority")
        except (ValueError, TypeError, KeyError, OSError, RecursionError):
            if started and started[-1].is_dir():
                _partial(directory, index, reports, authority, "protocol", started[-1])
            raise
        if sealed is None:
            reason = _text(_object(report.get("worker", {})).get("reason", "native_error"))
            return _partial(directory, index, reports + [report], authority, reason, attempt)
        frozen.update({attempt / name: digest for name, digest in files.items()})
        frozen[sealed] = file_hash(sealed)
        available.update(outputs)
        seals.append(sealed)
        reports.append(report)
    try:
        for item, digest in frozen.items():
            if file_hash(item) != digest:
                raise EvaluationError("sealed source/output changed before native publication")
        summary = _path(_object(release.to_record()["artifacts"])["summary"])
        result: dict[str, object] = {
            "format": "buddha.native-evaluation-report.v1",
            "status": "complete",
            "release_sha256": release.fingerprint(),
            "tasks_sha256": source.tasks.fingerprint(),
            "source_generation": definition["source_generation"],
            "answers_file_sha256": file_hash(source.answers_path),
            "answers_sha256": source.answers.fingerprint(),
            "native_answers_sha256": file_hash(native_answers),
            "stages": reports,
            "stage_seals": {str(item.relative_to(directory)): file_hash(item) for item in seals},
            "summary": {"path": str(available[summary]), "sha256": frozen[available[summary]]},
            "authorization": authority.summary(),
            "claim": "complete fresh native assessment of saved generation; no improvement claim",
        }
        return pipeline.publish_complete(
            directory / "report.json",
            result,
            authority,
            {
                _text(_read_manifest(directory / "owners" / str(index))["run_id"])
                for index in range(1, len(stages) + 1)
            },
        )
    except (ValueError, TypeError, KeyError, OSError, RecursionError):
        _partial(directory, len(stages), reports, authority, "protocol", attempt)
        raise
