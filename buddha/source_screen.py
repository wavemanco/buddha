"""Fixed development-task screening and exploratory source-parent eligibility.

Source code is the intervention. Official native results remain measurements;
complete execution, archive admission and confirmed improvement are separate.
"""

import hashlib
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass, field
from functools import wraps
from pathlib import Path
from typing import cast

from buddha import candidate_generation, native_evaluation, trial_fence
from buddha import native_pipeline as pipeline
from buddha.answers import TaskSet, _Artifact, _source, _utf8
from buddha.authorization import Authorization
from buddha.doctor import _Busy, _Capture, _Unsupported
from buddha.gateway import (
    CAPABILITIES,
    CORE,
    Gateway,
    RawHTTPTransport,
    _input_records,
    _profiles,
    _read_manifest,
)
from buddha.policy_study import _ids, _split
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
    verify_selection,
)
from buddha.wire import _integer


class SourceScreenError(ReleaseError):
    """Screen configuration, custody or exploratory admission is invalid."""


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
            if isinstance(error, SourceScreenError):
                raise
            raise SourceScreenError("source screen configuration or evidence is invalid") from None

    return checked


@dataclass(frozen=True)
class SourceScreen(_Artifact):
    """Immutable screen declaration; parsing and comparison never read components."""

    _format_version: str = field(init=False, repr=False, compare=False)

    @_checked
    def __post_init__(self) -> None:
        record = _object(
            _load(self.data),
            {
                "format",
                "source",
                "split",
                "selected_ids",
                "generation",
                "native",
                "stages",
                "projection",
                "lineage",
            },
        )
        if record["format"] not in {"buddha.source-screen.v1", "buddha.source-screen.v2"}:
            raise SourceScreenError("unsupported source screen")
        source = TaskSet.from_bytes(_json(record["source"]))
        release, dataset = _source(source.to_record())
        full = TaskSet.from_dataset(release, dataset)
        if {task.id for task in source.tasks} != {task.id for task in full.tasks}:
            raise SourceScreenError("source screen requires the complete source population")
        development = _split(record["split"], full)
        selected = _ids(record["selected_ids"], development)
        if len(selected) > 64:
            raise SourceScreenError("a source screen accepts at most 64 development tasks")
        generation = _object(
            record["generation"],
            {
                "selection",
                "roots",
                "config",
                "entrypoint",
                "executor",
                "profile",
                "runtime",
                "max_callbacks",
                "budget_microusd",
                "max_calls",
            },
        )
        selection = Selection.from_bytes(_json(generation["selection"]))
        native = _object(record["native"])
        examiner = Selection.from_bytes(_json(native["selection"]))
        if selection.release_sha256 != source.release_sha256 or (
            examiner.release_sha256 != source.release_sha256
        ):
            raise SourceScreenError("screen selections differ from the source release")
        roots = _object(generation["roots"], {"official", "agent", "runner", "host", "environment"})
        for value in roots.values():
            pipeline._absolute(value)
        entrypoint = _path(generation["entrypoint"])
        if not entrypoint.endswith(".py") or set(
            _object(_object(selection.to_record()["components"])["agent"])
        ) != {entrypoint}:
            raise SourceScreenError("screen needs one selected Python candidate")
        config = _object(
            generation["config"],
            {"provider", "model", "max_output_tokens", "instructions", "sampling"},
        )
        if (
            config["provider"] not in {"openai", "anthropic"}
            or (config["sampling"] not in {"regenerate", "in-context"})
            or len(_utf8(config["instructions"])) > 4000
        ):
            raise SourceScreenError("unsupported generation configuration")
        _text(config["model"])
        _integer(config["max_output_tokens"], 1)
        _integer(generation["max_callbacks"], 0, 1000)
        _integer(generation["budget_microusd"], 1)
        _integer(generation["max_calls"], 1)
        runtime = _object(generation["runtime"], {"path", "sha256"})
        member = (
            pipeline._absolute(runtime["path"])
            .relative_to(pipeline._absolute(roots["environment"]))
            .as_posix()
        )
        _path(member)
        if _object(_object(selection.to_record()["components"])["environment"]).get(
            member
        ) != _digest(runtime["sha256"]):
            raise SourceScreenError("runtime is not its original selected environment member")
        executor = _object(generation["executor"])
        if executor.get("mounts") != [["/agent", roots["agent"]], ["/runner", roots["runner"]]]:
            raise SourceScreenError("source mounts differ from the selected source roots")
        if record["projection"] is not None and record["projection"] != "noveltybench-1.1":
            raise SourceScreenError("unsupported optional results projection")
        stages = record["stages"]
        if type(stages) is not list or not stages or len(stages) > 16:
            raise SourceScreenError("source screen needs bounded native stages")
        if len(selected) * (1 + len(stages)) > 256:
            raise SourceScreenError("source screen exceeds its 256-owner schedule")
        pipeline.validate_native_flow(stages, Release.from_record(source.to_record()["release"]))
        if record["lineage"] is not None:
            lineage = _object(record["lineage"], {"path", "sha256"})
            pipeline._absolute(lineage["path"])
            _digest(lineage["sha256"])
        object.__setattr__(self, "data", _json(record))
        object.__setattr__(self, "_format_version", _text(record["format"]).rsplit(".", 1)[1])

    @property
    def tasks(self) -> TaskSet:
        record = self.to_record()
        return TaskSet.from_bytes(_json(record["source"])).select(record["selected_ids"])

    @property
    def candidate_id(self) -> str:
        return Selection.from_bytes(
            _json(_object(self.to_record()["generation"])["selection"])
        ).agent_sha256

    def comparison_key(self) -> str:
        """Fix the instrument/resources while allowing source inventory to differ."""
        record = self.to_record()
        generation = _object(record["generation"])
        roots = _object(generation.pop("roots"))
        components = _object(_object(generation["selection"])["components"])
        components["agent"] = {}
        runtime = _object(generation["runtime"])
        runtime["path"] = (
            pipeline._absolute(runtime["path"])
            .relative_to(pipeline._absolute(roots["environment"]))
            .as_posix()
        )
        _object(generation["executor"])["mounts"] = [["/agent", "{agent}"], ["/runner", "{runner}"]]
        _object(record["native"]).pop("roots", None)
        record["lineage"] = None
        return hashlib.sha256(_json(["buddha.source-screen-comparison.v1", record])).hexdigest()


def _sources() -> list[Path]:
    package = Path(__file__).absolute().parent
    return list(
        dict.fromkeys(
            [
                *(
                    package / ("__init__.py" if name == "buddha" else name.split(".")[-1] + ".py")
                    for name in sorted(CORE)
                ),
                *candidate_generation._sources(),
                *native_evaluation._sources(),
                *(
                    package / (name + ".py")
                    for name in (
                        "source_screen",
                        "source_screen_results",
                        "native_evidence",
                        "noveltybench_results",
                        "policy_study",
                        "archive",
                        "evaluation",
                    )
                ),
            ]
        )
    )


def _roots(section: dict[str, object]) -> dict[str, Path]:
    return {name: pipeline._absolute(path) for name, path in _object(section["roots"]).items()}


def _version(screen: SourceScreen, stem: str) -> str:
    return "buddha." + stem + "." + screen._format_version


def _generation_formats(screen: SourceScreen) -> dict[str, str]:
    return candidate_generation.generation_formats(_version(screen, "candidate-generation"))


def _comparison_controls(
    context: dict[str, object],
    controls: dict[Path, str],
    screen: SourceScreen,
    *,
    core: object | None = None,
) -> str:
    """Compare original helper roles and conservative external pins, without IO."""
    comparison = _object(context["comparison_controls"], {"sources", "external"})
    sources = _object(comparison["sources"])
    paths = _sources()
    if core is not None:
        paths = candidate_generation._recorded_sources(paths, core)
    if set(sources) != {"buddha/" + path.name for path in paths}:
        raise SourceScreenError("comparison helper coverage differs from the screen contract")
    package: Path | None = None
    source_paths: set[Path] = set()
    hashes: dict[str, str] = {}
    for name, value in sources.items():
        reference = _object(value, {"path", "sha256"})
        path = pipeline._absolute(reference["path"])
        digest = _digest(reference["sha256"])
        if (
            path.name != name.removeprefix("buddha/")
            or path.parent.name != "buddha"
            or (package is not None and path.parent != package)
            or path in source_paths
            or controls.get(path) != digest
        ):
            raise SourceScreenError("comparison helper differs from its original role or binding")
        package = path.parent
        source_paths.add(path)
        hashes[name] = digest
    external: dict[str, str] = {}
    for value, expected in _object(comparison["external"]).items():
        path, digest = pipeline._absolute(value), _digest(expected)
        if path in source_paths or controls.get(path) != digest:
            raise SourceScreenError("external comparison input differs from its original binding")
        external[str(path)] = digest
    record = screen.to_record()
    runtime = _object(_object(record["generation"])["runtime"])
    excluded = {pipeline._absolute(runtime["path"]): _digest(runtime["sha256"])}
    if record["lineage"] is not None:
        lineage = _object(record["lineage"])
        excluded[pipeline._absolute(lineage["path"])] = _digest(lineage["sha256"])
    if (
        any(controls.get(path) != digest for path, digest in excluded.items())
        or {Path(path) for path in external} != controls.keys() - source_paths - excluded.keys()
    ):
        raise SourceScreenError("comparison controls omit or add an original input")
    return pipeline._sha({"sources": hashes, "external": external})


def _lineage(screen: SourceScreen, consume: Callable[[Path, object], bytes]) -> str | None:
    record = screen.to_record()
    if record["lineage"] is None:
        return None
    reference = _object(record["lineage"])
    raw = consume(pipeline._absolute(reference["path"]), reference["sha256"])
    lineage = _object(_load(raw))
    detached = lineage.get("format") == "buddha.source-lineage.v2"
    _object(
        lineage,
        {
            "format",
            "parent",
            "child",
            "descriptor_sha256",
            "feedback",
            "owner",
            "proposal_sha256",
        }
        | ({"improver"} if detached else set()),
    )
    generation = _object(record["generation"])
    selected = Selection.from_bytes(_json(generation["selection"]))
    entrypoint = _path(generation["entrypoint"])
    child = _object(lineage["child"], {"agent_sha256", "source_sha256", "entrypoint"})
    parent = _object(lineage["parent"], {"agent_sha256", "source_sha256", "entrypoint"})
    parent_id = _digest(parent["agent_sha256"])
    _digest(parent["source_sha256"])
    _path(parent["entrypoint"])
    if (
        lineage["format"] not in {"buddha.source-lineage.v1", "buddha.source-lineage.v2"}
        or child
        != {
            "agent_sha256": screen.candidate_id,
            "entrypoint": entrypoint,
            "source_sha256": _object(_object(selected.to_record()["components"])["agent"])[
                entrypoint
            ],
        }
        or parent_id == screen.candidate_id
    ):
        raise SourceScreenError("retained lineage differs from the selected child")
    if detached:
        improver = _object(lineage["improver"], {"agent_sha256", "source_sha256", "entrypoint"})
        improver_entrypoint = _path(improver["entrypoint"])
        if (
            parent["entrypoint"] != "candidate.py"
            or parent_id != pipeline._sha({"candidate.py": _digest(parent["source_sha256"])})
            or not improver_entrypoint.endswith(".py")
            or _digest(improver["agent_sha256"])
            != pipeline._sha({improver_entrypoint: _digest(improver["source_sha256"])})
        ):
            raise SourceScreenError("detached lineage changes parent or improver source identity")
    _digest(lineage["descriptor_sha256"])
    _digest(lineage["proposal_sha256"])
    feedback = _object(lineage["feedback"], {"file_sha256", "input_sha256"})
    for value in feedback.values():
        _digest(value)
    owner = _object(lineage["owner"], {"path", "manifest_sha256"})
    pipeline._absolute(owner["path"])
    _digest(owner["manifest_sha256"])
    return parent_id


def _profiles_checked(screen: SourceScreen) -> None:
    record = screen.to_record()
    generation, native = _object(record["generation"]), _object(record["native"])
    selected = {
        name: _profiles(Selection.from_bytes(_json(section["selection"])), _roots(section))
        for name, section in (("generation", generation), ("native", native))
    }
    role = _object(generation["profile"], {"capability", "profile_id"})
    capability, profile_id = _text(role["capability"]), _text(role["profile_id"])
    config = _object(generation["config"])
    profile = _object(_object(_object(selected["generation"][capability])["profiles"])[profile_id])
    spec = _object(profile["spec"])
    if (
        capability not in CAPABILITIES
        or CAPABILITIES[capability][0] != config["provider"]
        or any(spec[key] != config[key] for key in ("provider", "model", "max_output_tokens"))
    ):
        raise SourceScreenError("source config differs from its reviewed host profile")
    for provider, models in _object(native["profiles"]).items():
        if provider not in {value[0] for value in CAPABILITIES.values()}:
            raise SourceScreenError("unsupported native provider")
        capability = next(key for key, value in CAPABILITIES.items() if value[0] == provider)
        choices = _object(_object(selected["native"][capability])["profiles"])
        for model, name in _object(models).items():
            spec = _object(_object(choices[_text(name)])["spec"])
            if spec["provider"] != provider or spec["model"] != model:
                raise SourceScreenError("native model mapping differs from its reviewed profile")


def _configuration(screen: SourceScreen, runtime_sha256: str) -> None:
    record = screen.to_record()
    generation = _object(record["generation"])
    runtime = _object(generation["runtime"])
    if runtime["sha256"] != runtime_sha256:
        raise SourceScreenError("source runtime differs from independent approval")
    selected = Selection.from_bytes(_json(generation["selection"]))
    roots = _roots(generation)
    verify_selection(selected, roots, expected_sha256=selected.fingerprint())
    candidate_generation._runtime_selection(
        generation,
        selected,
        roots,
        lambda path: pipeline._read(path, runtime_sha256),
        runtime_sha256,
    )
    release = Release.from_record(_object(record["source"])["release"])
    pipeline.validate_native(_object(record["native"]), record["stages"], release)
    _profiles_checked(screen)
    if record["projection"] == "noveltybench-1.1":
        from buddha.noveltybench_results import reporting_configuration

        reporting_configuration(release, cast(list[dict[str, object]], record["stages"]))


def _generation_recipe(location: Path, screen: SourceScreen) -> dict[str, object]:
    generation = _object(screen.to_record()["generation"])
    return {
        "format": _version(screen, "candidate-generation"),
        "tasks": str(location / "task.json"),
        **{
            key: generation[key]
            for key in (
                "config",
                "entrypoint",
                "executor",
                "profile",
                "runtime",
                "max_callbacks",
            )
        },
    }


def _task_controls(location: Path, screen: SourceScreen, index: int) -> dict[Path, str]:
    task = screen.tasks.select([screen.tasks.tasks[index].id])
    return {
        location / "task.json": task.fingerprint(),
        location / "generation.json": pipeline._sha(_generation_recipe(location, screen)),
    }


def _materialize(directory: Path, screen: SourceScreen, index: int) -> tuple[Path, Path]:
    location = directory / "tasks" / str(index)
    if not location.exists():
        location.mkdir()
    _root(location)
    task = screen.tasks.select([screen.tasks.tasks[index].id])
    pipeline._same_or_write(location / "task.json", task.to_bytes())
    descriptor = location / "generation.json"
    pipeline._same_or_write(descriptor, _json(_generation_recipe(location, screen)))
    return location, descriptor


def _source_reference(directory: Path, screen: SourceScreen) -> dict[str, object]:
    owner = directory / "owners/0"
    return {
        "format": _generation_formats(screen)["source"],
        "generation_directory": str(directory),
        "stage_seal_sha256": file_hash(directory / "completed/0.json"),
        "owner_manifest_sha256": pipeline._sha(_read_manifest(owner)),
        "owner_ledger_sha256": file_hash(owner / "operations.sqlite3", max_bytes=512 * 1024**2),
    }


def _evaluation_record(location: Path, screen: SourceScreen) -> dict[str, object]:
    record = screen.to_record()
    return {
        "format": "buddha.native-evaluation.v1",
        "source_generation": _source_reference(location / "generation", screen),
        "native": record["native"],
        "stages": record["stages"],
    }


def _evaluation_recipe(location: Path, screen: SourceScreen) -> Path:
    path = location / "evaluation.json"
    pipeline._same_or_write(path, _json(_evaluation_record(location, screen)))
    return path


@_checked
def prepare_source_screen(
    directory: Path,
    *,
    screen: SourceScreen,
    authorization: Authorization,
    review: dict[str, object],
    expected_runtime_sha256: str,
    input_bindings: Mapping[Path, str] | None = None,
) -> Path:
    if type(screen) is not SourceScreen or not isinstance(authorization, Authorization):
        raise SourceScreenError("source screen needs its explicit artifact and existing authority")
    directory = pipeline._absolute(str(directory))
    runtime_sha256 = _digest(expected_runtime_sha256)
    _configuration(screen, runtime_sha256)
    trial_fence.require_purpose(
        authorization.path,
        authorization._terms(),
        directory=directory,
        expected="source screen: " + screen.comparison_key(),
    )
    external = trial_fence._include_controls(directory, dict(input_bindings or {}))
    inputs = _input_records(list(external), external)
    expected = {Path(row["path"]): row["sha256"] for row in inputs}
    for source in _sources():
        actual = file_hash(source)
        if source in expected and expected[source] != actual:
            raise SourceScreenError("screen helper differs from its original supplied hash")
        expected[source] = actual
    record = screen.to_record()
    runtime_path = pipeline._absolute(_object(_object(record["generation"])["runtime"])["path"])
    if runtime_path in expected and expected[runtime_path] != runtime_sha256:
        raise SourceScreenError("runtime conflicts with original external inputs")
    expected[runtime_path] = runtime_sha256
    _lineage(screen, lambda path, digest: pipeline._read(path, digest))
    if record["lineage"] is not None:
        reference = _object(record["lineage"])
        lineage_path = pipeline._absolute(reference["path"])
        if lineage_path in expected and expected[lineage_path] != reference["sha256"]:
            raise SourceScreenError("lineage conflicts with an original external input")
        expected[lineage_path] = _digest(reference["sha256"])
    protected = [authorization.path, *expected]
    for name in ("generation", "native"):
        protected.extend(_roots(_object(record[name])).values())
    if any(directory.is_relative_to(path) or path.is_relative_to(directory) for path in protected):
        raise SourceScreenError("screen output overlaps original inputs or funding")
    _root(directory.parent)
    _path(directory.name)
    with trial_fence.work(
        authorization.path, authorization._terms(), directory=directory, kind="screen"
    ) as trial_controls:
        if any(expected.get(path) != digest for path, digest in trial_controls.items()):
            raise SourceScreenError("original trial controls changed before screen preparation")
        trial_fence.require_purpose(
            authorization.path,
            authorization._terms(),
            directory=directory,
            expected="source screen: " + screen.comparison_key(),
        )
        directory.mkdir()
        for name in ("tasks", "observations"):
            (directory / name).mkdir()
        pipeline._write(directory / "screen.json", screen.to_bytes())
        context: dict[str, object] = {
            "format": _version(screen, "source-screen-context"),
            "screen_sha256": screen.fingerprint(),
            "expected_runtime_sha256": runtime_sha256,
            "controls": {str(path): digest for path, digest in expected.items()},
            "comparison_controls": {
                "sources": {
                    "buddha/" + source.name: {"path": str(source), "sha256": expected[source]}
                    for source in _sources()
                },
                "external": {
                    str(path): digest
                    for path, digest in external.items()
                    if path not in _sources()
                    and path != runtime_path
                    and (
                        record["lineage"] is None or str(path) != _object(record["lineage"])["path"]
                    )
                },
            },
        }
        _comparison_controls(context, expected, screen)
        pipeline._write(directory / "context.json", _json(context))
        expected[directory / "screen.json"] = screen.fingerprint()
        expected[directory / "context.json"] = pipeline._sha(context)
        location, descriptor = _materialize(directory, screen, 0)
        expected |= _task_controls(location, screen, 0)
        generation = _object(record["generation"])
        candidate_generation.prepare_candidate_generation(
            location / "generation",
            descriptor=descriptor,
            selection=Selection.from_bytes(_json(generation["selection"])),
            roots=_roots(generation),
            authorization=authorization,
            review=review,
            budget_microusd=cast(int, generation["budget_microusd"]),
            max_calls=cast(int, generation["max_calls"]),
            expected_runtime_sha256=runtime_sha256,
            input_files=list(expected),
            expected_input_hashes=expected,
        )
    return directory


def _bindings(owner: dict[str, object]) -> dict[Path, str]:
    return {
        pipeline._absolute(row["path"]): _digest(row["sha256"])
        for row in cast(list[dict[str, object]], _object(owner["invocation"])["inputs"])
    }


def _original(
    directory: Path, first: dict[str, object]
) -> tuple[SourceScreen, dict[Path, str], str]:
    bindings = _bindings(first)

    def consume(path: Path) -> bytes:
        return pipeline._read(path, bindings[path])

    context = _object(
        _load(consume(directory / "context.json")),
        {
            "format",
            "screen_sha256",
            "expected_runtime_sha256",
            "controls",
            "comparison_controls",
        },
    )
    screen = SourceScreen.from_bytes(consume(directory / "screen.json"))
    if context["format"] != _version(screen, "source-screen-context") or (
        context["screen_sha256"] != screen.fingerprint()
    ):
        raise SourceScreenError("screen differs from its original context")
    controls = {
        pipeline._absolute(path): _digest(digest)
        for path, digest in _object(context["controls"]).items()
    }
    _comparison_controls(context, controls, screen)
    controls |= {
        directory / "context.json": bindings[directory / "context.json"],
        directory / "screen.json": screen.fingerprint(),
    }
    if any(path not in controls for path in _sources()) or any(
        bindings.get(path) != digest or file_hash(path) != digest
        for path, digest in controls.items()
    ):
        raise SourceScreenError("an original screen control is missing or changed")
    runtime = _digest(context["expected_runtime_sha256"])
    _configuration(screen, runtime)
    _lineage(screen, lambda path, digest: pipeline._read(path, digest))
    return screen, controls, runtime


def _seal(
    child: Path,
    index: int,
    gateway: Gateway,
    authority: Authorization,
    funding: dict[str, object],
    *,
    source: bool,
    screen: SourceScreen,
) -> bool:
    path = child / "completed" / (str(index) + ".json")
    if not path.exists():
        if funding["active"] is not True:
            raise SourceScreenError("unfinished original owner is inactive")
        return False
    digest = file_hash(path)
    seal = _object(
        _load(pipeline._read(path, digest)),
        {
            "format",
            "index",
            "owner_sha256",
            "attempt",
            "files",
        },
    )
    attempt = Path(_path(seal["attempt"]))
    if (
        funding["active"] is not False
        or seal["format"]
        != (_generation_formats(screen)["seal"] if source else "buddha.native-evaluation-stage.v1")
        or type(seal["index"]) is not int
        or seal["index"] != index
        or seal["owner_sha256"] != gateway.manifest_sha256
        or len(attempt.parts) != 2
        or attempt.parts[0] != "attempts"
        or not attempt.name.startswith(str(index) + "-")
    ):
        raise SourceScreenError("completion differs from its original owner")
    from buddha.releases import inventory

    if inventory(child / attempt) != seal["files"]:
        raise SourceScreenError("sealed original stage outputs changed")
    # Existing inactive anchors are checked; this never closes an active owner.
    authority.deactivate(
        _text(_read_manifest(gateway.directory)["run_id"]),
        (_generation_formats(screen)["anchor"] if source else "native evaluation completed: ")
        + digest,
    )
    return True


def _preflight(
    directory: Path,
    screen: SourceScreen,
    authority: Authorization,
    review: dict[str, object],
    controls: dict[Path, str],
) -> set[str]:
    """Check every retained owner and the reverse funding schedule before calls."""
    tasks = list((directory / "tasks").iterdir())
    if {task.name for task in tasks} != {str(index) for index in range(len(tasks))} or (
        not tasks or len(tasks) > len(screen.tasks.tasks)
    ):
        raise SourceScreenError("screen task schedule has foreign or missing entries")
    funded = {
        _text(row["run_id"]): row
        for row in cast(list[dict[str, object]], authority.summary()["runs"])
    }
    identifiers: set[str] = set()
    unfinished = False
    terminal_failure = False
    record = screen.to_record()
    stages = cast(list[object], record["stages"])
    for task in sorted(tasks, key=lambda path: int(path.name)):
        _root(task)
        index = int(task.name)
        expected_task = screen.tasks.select([screen.tasks.tasks[index].id]).to_bytes()
        if pipeline._read(task / "task.json") != expected_task:
            raise SourceScreenError("original task input differs from the fixed population")
        generation = _object(record["generation"])
        recipe = _generation_recipe(task, screen)
        if pipeline._read(task / "generation.json") != _json(recipe):
            raise SourceScreenError("original source recipe changed")
        for child, source in ((task / "generation", True), (task / "evaluation", False)):
            if not source and terminal_failure:
                if child.exists() or index != len(tasks) - 1:
                    raise SourceScreenError("work follows a terminal candidate failure")
                continue
            if not child.exists():
                unfinished = True
                continue
            _root(child)
            descriptor = task / ("generation.json" if source else "evaluation.json")
            if not source:
                expected = _evaluation_record(task, screen)
                if pipeline._read(descriptor) != _json(expected):
                    raise SourceScreenError("original native recipe changed")
            context_path = child / "context.json"
            context: dict[str, object] = {
                "format": _generation_formats(screen)["context"]
                if source
                else "buddha.native-evaluation-context.v1",
                "descriptor": str(descriptor),
            }
            if source:
                context["expected_runtime_sha256"] = _object(generation["runtime"])["sha256"]
            if pipeline._read(context_path) != _json(context):
                raise SourceScreenError("original child context changed")
            child_controls = controls | {
                descriptor: pipeline._sha(recipe) if source else pipeline._sha(expected),
                context_path: pipeline._sha(context),
                task / "task.json": hashlib.sha256(expected_task).hexdigest(),
            }
            owners = list((child / "owners").iterdir())
            first, count = (0, 1) if source else (1, len(stages))
            if (
                not owners
                or {owner.name for owner in owners}
                != {str(i) for i in range(first, first + len(owners))}
                or len(owners) > count
            ):
                raise SourceScreenError("child has foreign, missing or aliased owners")
            completed = {item.name for item in (child / "completed").iterdir()}
            if completed != {str(i) + ".json" for i in range(first, first + len(completed))} or (
                not {name.removesuffix(".json") for name in completed} <= {o.name for o in owners}
            ):
                raise SourceScreenError("child completion schedule is not a contiguous prefix")
            all_complete = len(owners) == count
            for owner in sorted(owners, key=lambda path: int(path.name)):
                gateway = Gateway(owner, transport=RawHTTPTransport(allow_paid=False))
                actual = _read_manifest(owner)
                identifier = _text(actual["run_id"])
                funding = funded[identifier]
                section = _object(record["generation" if source else "native"])
                no_model = not source and int(owner.name) == count
                if (
                    identifier in identifiers
                    or type(funding["historical"]) is not int
                    or funding["historical"] != 0
                    or funding["runtime_sha256"] != actual["execution_sha256"]
                    or funding["manifest_sha256"] != gateway.manifest_sha256
                    or funding["directory"] != str(owner)
                    or actual["authorization_path"] != str(authority.path)
                    or actual["selection"] != section["selection"]
                    or actual["roots"] != section["roots"]
                    or actual["review"] != review
                    or actual["settings"]
                    != {
                        "budget_microusd": 1 if no_model else section["budget_microusd"],
                        "max_calls": 1 if no_model else section["max_calls"],
                    }
                    or any(
                        _bindings(actual).get(path) != digest
                        for path, digest in child_controls.items()
                    )
                ):
                    raise SourceScreenError("retained owner differs from its original screen")
                complete = _seal(
                    child,
                    int(owner.name),
                    gateway,
                    authority,
                    funding,
                    source=source,
                    screen=screen,
                )
                if unfinished and (gateway.ledger.totals()["operation_count"] or complete):
                    raise SourceScreenError("retained work skips an unfinished predecessor")
                unfinished = unfinished or not complete
                all_complete = all_complete and complete
                identifiers.add(identifier)
            report_path = child / "report.json"
            if report_path.exists() and not all_complete:
                raise SourceScreenError("published child lacks its complete original owners")
            if (
                source
                and all_complete
                and report_path.exists()
                and (record["format"] == "buddha.source-screen.v2")
            ):
                observed = candidate_generation.inspect_candidate_generation(
                    child,
                    authorization=authority.path,
                    expected_report_sha256=file_hash(report_path),
                )
                terminal_failure = observed["disposition"] == "candidate_execution_failed"
            unfinished = unfinished or not all_complete or not report_path.exists()
    if any(
        pipeline._absolute(row["directory"]).is_relative_to(directory)
        and row["run_id"] not in identifiers
        for row in funded.values()
    ):
        raise SourceScreenError("known funded owner is missing; replacement is not recovery")
    if (directory / "report.json").exists() and (
        unfinished or (len(tasks) != len(screen.tasks.tasks) and not terminal_failure)
    ):
        raise SourceScreenError("root completion lacks its complete original schedule")
    return identifiers


def _accepted(directory: Path, result: dict[str, object]) -> str:
    raw = pipeline._read(directory / "report.json")
    if raw != _json(result):
        raise SourceScreenError("stored child publication differs from the actual returned report")
    return hashlib.sha256(raw).hexdigest()


@_checked
def run_source_screen(directory: Path, *, transport: RawHTTPTransport) -> dict[str, object]:
    """Execute or resume this fixed screen with its original owners and controls."""
    if not isinstance(directory, Path) or not isinstance(transport, RawHTTPTransport):
        raise SourceScreenError("screen requires its original Path and raw transport")
    directory = pipeline._absolute(str(directory))
    anchor = directory / "tasks/0/generation/owners/0"
    original = _read_manifest(anchor)
    authority_path = pipeline._absolute(original["authorization_path"])
    if trial_fence.is_closed(directory):
        return inspect_source_screen(
            directory,
            authorization=authority_path,
            expected_report_sha256=file_hash(directory / "report.json"),
        )
    with (
        trial_fence.work(
            authority_path,
            Authorization(authority_path)._terms(),
            directory=directory,
            kind="screen",
        ),
        pipeline._exclusive(directory),
    ):
        Gateway(anchor, transport=RawHTTPTransport(allow_paid=False))
        first = _read_manifest(anchor)
        screen, controls, runtime = _original(directory, first)
        authority = Authorization(pipeline._absolute(first["authorization_path"]))
        trial_fence.require_purpose(
            authority.path,
            authority._terms(),
            directory=directory,
            expected="source screen: " + screen.comparison_key(),
        )
        review = _object(first["review"])
        _preflight(directory, screen, authority, review, controls)
        generation = _object(screen.to_record()["generation"])
        retained: dict[Path, str] = {}
        current_index, current_stage = 0, "generation"

        def observe(reason: str, child: dict[str, object] | None) -> dict[str, object]:
            ordinal = 0
            while (directory / "observations" / (str(ordinal) + ".json")).exists():
                ordinal += 1
            path = directory / "observations" / (str(ordinal) + ".json")
            value: dict[str, object] = {
                "format": "buddha.source-screen-observation.v1",
                "status": "incomplete",
                "reason": reason,
                "candidate_id": screen.candidate_id,
                "comparison_key": screen.comparison_key(),
                "task_index": current_index,
                "stage": current_stage,
                "child": child,
                "authorization": authority.summary(),
                "observation": path.relative_to(directory).as_posix(),
                "claim": "incomplete development screen; original evidence and holds retained",
            }
            pipeline._write(path, _json(value))
            return value

        try:
            for current_index in range(len(screen.tasks.tasks)):
                current_stage = "generation"
                location, descriptor = _materialize(directory, screen, current_index)
                source = location / "generation"
                if not source.exists():
                    source_controls = controls | _task_controls(location, screen, current_index)
                    candidate_generation.prepare_candidate_generation(
                        source,
                        descriptor=descriptor,
                        selection=Selection.from_bytes(_json(generation["selection"])),
                        roots=_roots(generation),
                        authorization=authority,
                        review=review,
                        budget_microusd=cast(int, generation["budget_microusd"]),
                        max_calls=cast(int, generation["max_calls"]),
                        expected_runtime_sha256=runtime,
                        input_files=list(source_controls),
                        expected_input_hashes=source_controls,
                    )
                child = candidate_generation.run_candidate_generation(source, transport=transport)
                if child["status"] != "complete":
                    return observe(_text(child["reason"]), child)
                retained[source / "report.json"] = _accepted(source, child)
                if screen.to_record()["format"] == "buddha.source-screen.v2" and (
                    child["disposition"] == "candidate_execution_failed"
                ):
                    break
                current_stage = "native"
                descriptor = _evaluation_recipe(location, screen)
                evaluation = location / "evaluation"
                if not evaluation.exists():
                    native_controls = (
                        controls
                        | _task_controls(location, screen, current_index)
                        | {
                            descriptor: pipeline._sha(_evaluation_record(location, screen)),
                        }
                    )
                    native_evaluation.prepare_evaluation(
                        evaluation,
                        descriptor=descriptor,
                        authorization=authority,
                        review=review,
                        input_files=list(native_controls),
                        expected_input_hashes=native_controls,
                    )
                child = native_evaluation.run_evaluation(evaluation, transport=transport)
                if child["status"] != "complete":
                    return observe(_text(child["reason"]), child)
                retained[evaluation / "report.json"] = _accepted(evaluation, child)
            current_stage = "publication"
            for path, digest in retained.items():
                pipeline._read(path, digest)
            from buddha.source_screen_results import collect_source_screen

            result = collect_source_screen(directory, authorization=authority.path)
            identifiers = _preflight(directory, screen, authority, review, controls)
            return pipeline.publish_complete(
                directory / "report.json", result, authority, identifiers
            )
        except KeyboardInterrupt:
            observe("cancelled", None)
            raise
        except (ValueError, TypeError, KeyError, OSError, RecursionError):
            observe("protocol", None)
            raise


@_checked
def inspect_source_screen(
    directory: Path,
    *,
    authorization: Path,
    expected_report_sha256: str,
    sink: _Capture | None = None,
) -> dict[str, object]:
    from buddha.source_screen_results import collect_source_screen

    if sink is not None:
        return collect_source_screen(
            directory,
            authorization=authorization,
            expected_report_sha256=_digest(expected_report_sha256),
            sink=sink,
        )
    return collect_source_screen(
        directory,
        authorization=authorization,
        expected_report_sha256=_digest(expected_report_sha256),
    )


@_checked
def select_source_parent(
    references: Sequence[dict[str, object]],
    *,
    method: str,
    max_active: int,
    seed: int,
    iteration: int,
) -> dict[str, object]:
    if type(references) not in {list, tuple} or not 1 <= len(references) <= 256:
        raise SourceScreenError("source parent pool needs 1..256 explicit complete references")
    if method not in {"archive", "latest", "uninformed"}:
        raise SourceScreenError("unsupported exploratory parent method")
    _integer(max_active, 2, 64)
    _integer(seed, 0)
    _integer(iteration, 0)
    admissions: list[dict[str, object]] = []
    seen: set[str] = set()
    key: str | None = None
    controls_key: str | None = None
    eligible: list[dict[str, object]] = []
    for value in references:
        reference = _object(value, {"directory", "authorization", "report_sha256"})
        report = inspect_source_screen(
            pipeline._absolute(reference["directory"]),
            authorization=pipeline._absolute(reference["authorization"]),
            expected_report_sha256=_digest(reference["report_sha256"]),
        )
        identifier = _digest(report["candidate_id"])
        comparison = _digest(report["comparison_key"])
        control = _digest(report["controls_sha256"])
        if (
            identifier in seen
            or (key is not None and comparison != key)
            or (controls_key is not None and control != controls_key)
        ):
            raise SourceScreenError("parent pool repeats a source or changes the common comparison")
        seen.add(identifier)
        key = comparison
        controls_key = control
        admission = _object(report["admission"])
        admissions.append({"candidate_id": identifier, **admission})
        if admission["eligible"] is True:
            eligible.append(report)
    result: dict[str, object] = {
        "format": "buddha.source-parent-selection.v1",
        "comparison_key": key,
        "controls_sha256": controls_key,
        "method": method,
        "max_active": max_active,
        "seed": seed,
        "iteration": iteration,
        "selected_id": None,
        "admissions": admissions,
        "active_ids": [],
        "frontier_ids": [],
        "claim": "exploratory source parent allocation only; no improvement claim",
    }
    if not eligible:
        return result | {"reason": "no complete source has usable common-task metrics"}
    from buddha.archive import Candidate, active_pool, frontier, select_parent

    candidates = [
        Candidate(
            _digest(row["candidate_id"]),
            cast(str | None, row["parent_id"]),
            cast(float, _object(row["admission"])["mean_utility"]),
            cast(float, _object(row["admission"])["mean_distinct"]),
        )
        for row in eligible
    ]
    selected = select_parent(
        candidates,
        method=method,
        max_active=max_active,
        seed=seed,
        iteration=iteration,
    )
    return result | {
        "selected_id": selected.candidate_id,
        "active_ids": [row.candidate_id for row in active_pool(candidates, max_active=max_active)],
        "frontier_ids": [row.candidate_id for row in frontier(candidates)],
    }
