"""Version-neutral sequential baseline: frozen seed, then configured native commands.

Every stage has its own immutable Gateway owner under one existing authority.
This module derives files/coverage, never benchmark scores or optimization policy.
"""

import hashlib
import json
import os
from collections.abc import Callable, Iterator, Mapping, Sequence
from contextlib import contextmanager
from functools import partial, wraps
from pathlib import Path
from typing import cast

from buddha import agent_run, native_pipeline, native_run
from buddha.answers import Answers, TaskSet, _id
from buddha.authorization import Authorization
from buddha.gateway import (
    Gateway,
    RawHTTPTransport,
    _input_records,
    _read_manifest,
    execution_identity,
    prepare_gateway,
)
from buddha.releases import (
    ROLES,
    Release,
    ReleaseError,
    Selection,
    _json,
    _load,
    _object,
    _pairs,
    _path,
    _root,
    _text,
    file_hash,
    verify_selection,
)

HOST_FILES = tuple(
    dict.fromkeys(
        (
            *agent_run.HOST_FILES,
            *native_run.RUNNER_FILES,
            "native_run",
            "native_pipeline",
            "baseline",
        )
    )
)


class BaselineError(ReleaseError):
    """The baseline configuration, provenance or complete population is invalid."""


def _checked[**P, T](function: Callable[P, T]) -> Callable[P, T]:
    @wraps(function)
    def checked(*args: P.args, **kwargs: P.kwargs) -> T:
        try:
            return function(*args, **kwargs)
        except (ValueError, TypeError, KeyError, OSError) as error:
            if isinstance(error, BaselineError):
                raise
            raise BaselineError(
                "baseline configuration or evidence is invalid; original state retained"
            ) from None

    return checked


def _sha(value: object) -> str:
    return hashlib.sha256(_json(value)).hexdigest()


def _read(path: Path, expected: object = None) -> bytes:
    return native_pipeline._read(path, expected)


def _write(path: Path, raw: bytes) -> None:
    _root(path.parent)
    with path.open("xb") as stream:
        stream.write(raw)
        stream.flush()
        os.fsync(stream.fileno())


def _same_or_write(path: Path, raw: bytes) -> None:
    if path.exists():
        if _read(path) != raw:
            raise BaselineError("an existing stage input or descriptor differs; owner retained")
    else:
        _write(path, raw)


def _absolute(value: object) -> Path:
    path = Path(_text(value))
    if not path.is_absolute():
        raise BaselineError("baseline paths must be absolute")
    return path


def _component(value: object) -> tuple[Selection, dict[str, Path]]:
    record = _object(value)
    selection = Selection.from_bytes(_json(record["selection"]))
    roots = {key: _absolute(path) for key, path in _object(record["roots"], set(ROLES)).items()}
    verify_selection(selection, roots, expected_sha256=selection.fingerprint())
    for name in ("budget_microusd", "max_calls"):
        if type(record[name]) is not int or not 0 < cast(int, record[name]) < 2**63:
            raise BaselineError("stage ceilings must be positive bounded integers")
    return selection, roots


def _definition(
    path: Path, bindings: dict[str, object] | None = None
) -> tuple[dict[str, object], TaskSet, Release]:
    def consume(source: Path) -> bytes:
        return _read(source, None if bindings is None else bindings[str(source.absolute())])

    definition = _object(
        _load(consume(path)), {"format", "tasks", "generation", "native", "stages"}
    )
    if definition["format"] != "buddha.native-baseline.v1":
        raise BaselineError("unsupported baseline descriptor")
    generation = _object(
        definition["generation"],
        {"selection", "roots", "descriptor", "budget_microusd", "max_calls"},
    )
    native = _object(
        definition["native"],
        {
            "selection",
            "roots",
            "environment",
            "hooks",
            "executor",
            "profiles",
            "budget_microusd",
            "max_calls",
        },
    )
    selected, _ = _component(generation)
    evaluated, _ = _component(native)
    tasks = TaskSet.from_bytes(consume(_absolute(definition["tasks"])))
    if (
        selected.release_sha256 != evaluated.release_sha256
        or selected.agent_sha256 != evaluated.agent_sha256
        or tasks.release_sha256 != selected.release_sha256
    ):
        raise BaselineError("generation, evaluation and tasks have different source lineage")
    recipe = _load(consume(_absolute(generation["descriptor"])))
    if _absolute(recipe["tasks"]) != _absolute(definition["tasks"]):
        raise BaselineError("generation descriptor names a different TaskSet")
    release = Release.from_record(selected.to_record()["release"])
    native_pipeline.validate_native(native, definition["stages"], release)
    return definition, tasks, release


def _sources() -> list[Path]:
    package = Path(__file__).absolute().parent
    if (
        Path(agent_run.__file__).absolute() != package / "agent_run.py"
        or Path(native_run.__file__).absolute() != package / "native_run.py"
    ):
        raise BaselineError("baseline imports a different session implementation")
    return [package / (name + ".py") for name in HOST_FILES] + [
        package.parent / "agents/frozen_seed.py"
    ]


@_checked
def prepare_baseline(
    directory: Path,
    *,
    descriptor: Path,
    authorization: Authorization,
    review: dict[str, object],
    input_files: Sequence[Path] = (),
    expected_input_hashes: Mapping[Path, str] | None = None,
) -> Path:
    """Freeze an offline baseline intent and its generation owner; never send a request."""
    if not isinstance(directory, Path) or not isinstance(descriptor, Path):
        raise BaselineError("baseline needs Path destinations and configuration")
    if (
        not isinstance(input_files, (list, tuple))
        or len(input_files) > 1024
        or any(not isinstance(path, Path) for path in input_files)
    ):
        raise BaselineError("baseline controls require a bounded ordered Path list")
    controls = _input_records(input_files, expected_input_hashes)
    definition, _, _ = _definition(descriptor)
    directory = directory.absolute()
    _root(directory.parent)
    _path(directory.name)
    for item in ("generation", "native"):
        for root in _object(_object(definition[item])["roots"]).values():
            if directory.is_relative_to(_absolute(root)):
                raise BaselineError("baseline output must be outside selected components")
    directory.mkdir()
    for name in ("owners", "completed", "attempts", "staging"):
        (directory / name).mkdir()
    context = directory / "context.json"
    _write(
        context,
        _json({"format": "buddha.baseline-context.v1", "descriptor": str(descriptor.absolute())}),
    )
    generation = _object(definition["generation"])
    selection, roots = _component(generation)
    paths = list(
        dict.fromkeys(
            path.absolute()
            for path in [
                context,
                descriptor,
                _absolute(definition["tasks"]),
                _absolute(generation["descriptor"]),
                *_sources(),
                *input_files,
            ]
        )
    )
    expected = _input_records(paths, {Path(row["path"]): row["sha256"] for row in controls})
    prepare_gateway(
        directory / "owners/0",
        selection=selection,
        roots=roots,
        authorization=authorization,
        budget_microusd=cast(int, generation["budget_microusd"]),
        max_calls=cast(int, generation["max_calls"]),
        input_files=paths,
        expected_input_hashes={Path(row["path"]): row["sha256"] for row in expected},
        review=review,
    )
    return directory


def _coverage(path: Path, field: str, tasks: TaskSet, expected_digest: object) -> None:
    # Inspect only the population seam. Native numerical content (even NaN) is
    # preserved literally and is never interpreted as host benchmark arithmetic.
    try:
        rows = _read(path, expected_digest).splitlines()
        found = [_id(_object(json.loads(row, object_pairs_hook=_pairs))[field]) for row in rows]
    except (ValueError, KeyError, UnicodeError, RecursionError):
        raise BaselineError("native output has invalid selected-population rows") from None
    expected = [task.id for task in tasks.tasks]
    if len(found) != len(expected) or len(set(found)) != len(found) or set(found) != set(expected):
        raise BaselineError("native output omits, repeats or changes selected typed task IDs")


def _outputs(
    attempt: Path,
    report: dict[str, object],
    index: int,
    definition: dict[str, object],
    tasks: TaskSet,
    bindings: dict[str, object],
) -> dict[str, Path]:
    if report["status"] != "complete":
        raise BaselineError("incomplete native or generation stage cannot publish coverage")
    generation = _object(definition["generation"])
    selected = Selection.from_bytes(_json(generation["selection"]))
    declared = _object(report["artifacts"])
    if index == 0:
        path = attempt / "answers.json"
        if file_hash(path) != declared.get("answers.json"):
            raise BaselineError("exported C1 Answers differs from generation report")
        answers = Answers.from_bytes(_read(path, declared["answers.json"]))
        record = answers.to_record()
        if (
            record["tasks_sha256"] != tasks.fingerprint()
            or record["agent_sha256"] != selected.agent_sha256
            or record["metadata"] != {}
        ):
            raise BaselineError("C1 Answers changes selected source, agent or native metadata")
        recipe_path = _absolute(generation["descriptor"])
        recipe = _load(_read(recipe_path, bindings[str(recipe_path)]))
        if (
            report["tasks_sha256"] != tasks.fingerprint()
            or report["agent_sha256"] != selected.agent_sha256
            or report["config_sha256"] != _sha(recipe["config"])
        ):
            raise BaselineError("generation report differs from frozen treatment")
        return {"answers": path}
    return native_pipeline.native_outputs(attempt, report, index, definition, tasks)


@contextmanager
def _exclusive(directory: Path) -> Iterator[None]:
    _root(directory)
    path = directory / "running.lock"
    try:
        stream = path.open("xb")
    except FileExistsError:
        raise BaselineError(
            "baseline is already running or has a retained interrupted lock"
        ) from None
    try:
        with stream:
            stream.write(str(os.getpid()).encode("ascii"))
            stream.flush()
        yield
    finally:
        path.unlink()


def _native_descriptor(
    directory: Path,
    index: int,
    definition: dict[str, object],
    release: Release,
    answers: Path,
    available: dict[str, Path],
    frozen_files: dict[Path, str],
) -> tuple[Path, list[Path]]:
    return native_pipeline._native_descriptor(
        directory, index, definition, release, answers, available, frozen_files
    )


@_checked
def run_baseline(directory: Path, *, transport: RawHTTPTransport) -> dict[str, object]:
    """Run/resume the original owners, retaining every attempt and ambiguous hold."""
    if not isinstance(directory, Path) or not isinstance(transport, RawHTTPTransport):
        raise BaselineError("baseline needs its original directory and raw transport")
    directory = directory.absolute()
    with _exclusive(directory):
        return _run(directory, transport)


def _session(gateway: Gateway, descriptor: Path, index: int, attempt: Path) -> dict[str, object]:
    return (
        agent_run.AgentSession(gateway, descriptor=descriptor, output=attempt)
        if index == 0
        else native_run.NativeSession(gateway, descriptor=descriptor, output=attempt)
    ).run()


def _run(directory: Path, transport: RawHTTPTransport) -> dict[str, object]:
    anchor = Gateway(directory / "owners/0", transport=transport)
    initial = _read_manifest(anchor.directory)
    bindings = {
        _text(item["path"]): item["sha256"]
        for item in cast(list[dict[str, object]], _object(initial["invocation"])["inputs"])
    }
    context_path = directory / "context.json"
    context = _object(
        _load(_read(context_path, bindings[str(context_path)])), {"format", "descriptor"}
    )
    if context["format"] != "buddha.baseline-context.v1":
        raise BaselineError("unsupported baseline context")
    definition_path = _absolute(context["descriptor"])
    definition, tasks, release = _definition(definition_path, bindings)
    for path in [context_path, definition_path, *_sources()]:
        if bindings.get(str(path.absolute())) != file_hash(path):
            raise BaselineError("baseline control input or source is not frozen")
    generation = _object(definition["generation"])
    native = _object(definition["native"])
    authority = Authorization(_absolute(initial["authorization_path"]))
    available: dict[str, Path] = {}
    seals: list[Path] = []
    reports: list[dict[str, object]] = []
    frozen_files: dict[Path, str] = {}
    answers_path: Path | None = None
    for index in range(1 + len(cast(list[object], definition["stages"]))):
        execution_identity(anchor.directory)
        _definition(definition_path, bindings)
        for path, digest in frozen_files.items():
            if file_hash(path) != digest:
                raise BaselineError("a sealed predecessor changed before the next stage")
        owner = directory / "owners" / str(index)
        descriptor = _absolute(generation["descriptor"]) if index == 0 else None
        no_model = index == len(cast(list[object], definition["stages"]))
        if index:
            if answers_path is None:
                raise BaselineError("native evaluation lacks complete C1 Answers")
            descriptor, inputs = _native_descriptor(
                directory, index, definition, release, answers_path, available, frozen_files
            )
            selected, roots = _component(native)
            bound_inputs = [
                context_path,
                definition_path,
                anchor.directory / "manifest.json",
                _absolute(definition["tasks"]),
                answers_path,
                descriptor,
                *seals,
                *available.values(),
                *inputs,
                *_sources(),
                *(Path(path) for path in bindings),
            ]
            bound_inputs = list(dict.fromkeys(bound_inputs))
            expected_inputs = []
            for path in bound_inputs:
                digest = file_hash(path)
                expected = bindings.get(str(path), frozen_files.get(path, digest))
                if digest != expected:
                    raise BaselineError("an original control or sealed predecessor changed")
                expected_inputs.append({"path": str(path.absolute()), "sha256": expected})
            for path, digest in frozen_files.items():
                if file_hash(path) != digest:
                    raise BaselineError("a sealed predecessor changed during input staging")
            if not owner.exists():
                prepare_gateway(
                    owner,
                    selection=selected,
                    roots=roots,
                    authorization=authority,
                    budget_microusd=1 if no_model else cast(int, native["budget_microusd"]),
                    max_calls=1 if no_model else cast(int, native["max_calls"]),
                    input_files=bound_inputs,
                    expected_input_hashes={
                        Path(_text(row["path"])): _text(row["sha256"]) for row in expected_inputs
                    },
                    review=_object(initial["review"]),
                )
            owned = _read_manifest(owner)
            if (
                owned["authorization_path"] != initial["authorization_path"]
                or owned["selection"] != selected.to_record()
                or owned["roots"] != {name: str(path) for name, path in roots.items()}
                or owned["settings"]
                != {
                    "budget_microusd": 1 if no_model else native["budget_microusd"],
                    "max_calls": 1 if no_model else native["max_calls"],
                }
                or _object(owned["invocation"])["inputs"] != expected_inputs
            ):
                raise BaselineError(
                    "existing stage owner differs from the original pipeline authority or inputs"
                )
        if descriptor is None:
            raise BaselineError("stage lacks its frozen descriptor")
        stage_gateway = (
            anchor
            if index == 0
            else Gateway(
                owner, transport=RawHTTPTransport(allow_paid=False) if no_model else transport
            )
        )
        report, outputs, files, sealed, attempt = native_pipeline.execute_stage(
            directory,
            index,
            stage_gateway,
            authority,
            run=partial(_session, stage_gateway, descriptor, index),
            validate=partial(
                _outputs, index=index, definition=definition, tasks=tasks, bindings=bindings
            ),
            read=_read,
        )
        if sealed is None:
            return {
                "format": "buddha.native-baseline-report.v1",
                "status": "incomplete",
                "stopped_stage": index,
                "stages": reports + [report],
                "authorization": authority.summary(),
                "claim": "incomplete baseline; original owners, attempts and holds retained",
            }
        seal_digest = file_hash(sealed)
        frozen_files.update({attempt / name: digest for name, digest in files.items()})
        frozen_files[sealed] = seal_digest
        if index == 0:
            answers_path = outputs["answers"]
            answers = Answers.from_bytes(_read(answers_path, frozen_files[answers_path]))
            native_answers = directory / "native-answers.jsonl"
            _same_or_write(native_answers, answers.native_bytes())
            frozen_files[native_answers] = hashlib.sha256(answers.native_bytes()).hexdigest()
            available[_path(_object(release.to_record()["artifacts"])["answers"])] = native_answers
        else:
            available.update(outputs)
        seals.append(sealed)
        reports.append(report)
    summary = _path(_object(release.to_record()["artifacts"])["summary"])
    for path, digest in frozen_files.items():
        if file_hash(path) != digest:
            raise BaselineError("sealed output changed before final baseline publication")
    result: dict[str, object] = {
        "format": "buddha.native-baseline-report.v1",
        "status": "complete",
        "release_sha256": release.fingerprint(),
        "tasks_sha256": tasks.fingerprint(),
        "stages": reports,
        "stage_seals": {str(p.relative_to(directory)): file_hash(p) for p in seals},
        "summary": {"path": str(available[summary]), "sha256": frozen_files[available[summary]]},
        "authorization": authority.summary(),
        "claim": "complete selected native baseline; no optimizer projection or improvement claim",
    }
    return native_pipeline.publish_complete(
        directory / "report.json",
        result,
        authority,
        {
            _text(_read_manifest(directory / "owners" / str(index))["run_id"])
            for index in range(len(reports))
        },
    )
