"""Passive complete-source-screen custody and optional scalar admission.

Original bindings establish saved-byte consistency, not judgment authenticity.
No executing owner, current component inventory or source program is loaded.
"""

from __future__ import annotations

import hashlib
import math
import os
import sqlite3
import threading
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING, cast

from buddha import doctor, trial_fence
from buddha import native_pipeline as pipeline
from buddha.answers import TaskSet
from buddha.doctor import _authority, _Busy, _Capture, _Unsupported
from buddha.native_evaluation import _Generation, _read_generation, _read_published_generation
from buddha.native_evidence import NativeEvidence, _adopt_capture, authority_observation
from buddha.releases import MAX_JSON_BYTES, Release, _digest, _json, _load, _object, _path, _text

if TYPE_CHECKING:
    from buddha.source_screen import SourceScreen


@dataclass(frozen=True)
class _CompletedScreenRead:
    screen: SourceScreen
    report_raw: bytes
    reader: NativeEvidence
    context: tuple[object, ...] | None
    observation_root: Path


def _read_context(directory: Path) -> tuple[object, ...] | None:
    from buddha import source_screen

    lease = doctor._tree_context(directory)
    if (
        lease is None
        or source_screen._CONTROL_PROFILES.get() is not None
        or source_screen._CONTROL_PROFILES_V2.get() is not None
    ):
        return None
    return os.getpid(), threading.get_ident(), doctor._observation_limits(), lease


def _reuse_completed_screen(
    value: object, directory: Path, authorization: Path, expected: str
) -> _CompletedScreenRead:
    from buddha.source_screen import SourceScreen, SourceScreenError

    try:
        if (
            type(value) is not _CompletedScreenRead
            or type(value.reader) is not NativeEvidence
            or type(value.screen) is not SourceScreen
            or value.reader.root != directory
            or value.reader.authorization != authorization
            or _sha(value.report_raw) != expected
            or value.context is None
            or value.context != _read_context(value.observation_root)
        ):
            raise SourceScreenError("completed screen read differs from its exact original scope")
        value.reader.finish()
        trial_fence.require_purpose(
            authorization,
            _object(value.reader.funded["config"]),
            directory=directory,
            expected="source screen: " + value.screen.comparison_key(),
        )
        return value
    except (ValueError, TypeError, KeyError, OSError, RecursionError, _Busy, _Unsupported) as error:
        if isinstance(error, SourceScreenError):
            raise
        raise SourceScreenError("completed screen evidence is invalid or changed") from None


_CLAIM = (
    "complete common development screen; exploratory parent eligibility only; no improvement claim"
)


def _sha(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()


def _same(left: object, right: object) -> bool:
    return _json(left) == _json(right)


def _rows(value: object) -> list[dict[str, object]]:
    if type(value) is not list:
        raise ValueError("saved native records require a list")
    return [_object(row) for row in value]


def _publication(
    reader: NativeEvidence,
    path: Path,
    expected: dict[str, object],
    current: dict[str, object],
    owners: set[str],
    expected_sha256: str | None = None,
) -> tuple[dict[str, object], str]:
    raw = reader.raw(path, expected_sha256)
    saved = _load(raw)
    if raw != _json(saved):
        raise reader.error_type("complete publication is not its original canonical output")
    snapshot = _object(saved["authorization"])
    pipeline.validate_authorization_snapshot(snapshot, current, owners)
    if not _same(saved, expected | {"authorization": snapshot}):
        raise reader.error_type("complete publication differs from its original sealed evidence")
    return saved, _sha(raw)


def _owners(
    reader: NativeEvidence,
    record: dict[str, object],
    count: int,
    controls: dict[str, str],
    *,
    failed_index: int | None = None,
) -> dict[str, object]:
    stages = _rows(record["stages"])
    planned = {
        reader.root / "tasks" / str(i) / role / "owners" / str(index): section
        for i in range(count)
        for role, indexes, section in (
            ("generation", [0], "generation"),
            ("evaluation", list(range(1, len(stages) + 1)), "native"),
        )
        for index in indexes
        if not (i == failed_index and section == "native")
    }
    observed_tasks = {
        name.split("/")[1] for name in reader.capture.entries if name.startswith("tasks/")
    }
    if observed_tasks != {str(i) for i in range(count)}:
        raise reader.error_type("saved screen changes its ordered task population")
    for name in reader.capture.entries:
        parts = Path(name).parts
        if len(parts) >= 5 and parts[:1] == ("tasks",) and parts[3] == "owners":
            path = reader.root.joinpath(*parts[:5])
            if (
                path not in planned
                or (path / "manifest.json").relative_to(reader.root).as_posix()
                not in reader.capture.entries
            ):
                raise reader.error_type("screen contains a foreign or orphan owner")
    anchor = reader.owner(reader.root / "tasks/0/generation/owners/0")
    review = anchor.manifest["review"]
    for path, section in planned.items():
        owner = reader.owner(path)
        settings = _object(record[section])
        last = section == "native" and path.name == str(len(stages))
        expected_settings = {
            "budget_microusd": 1 if last else settings["budget_microusd"],
            "max_calls": 1 if last else settings["max_calls"],
        }
        bindings = reader._bindings(owner)
        if (
            not _same(owner.manifest["selection"], settings["selection"])
            or not _same(owner.manifest["roots"], settings["roots"])
            or not _same(owner.manifest["settings"], expected_settings)
            or not _same(owner.manifest["review"], review)
            or not _same(owner.manifest["core"], anchor.manifest["core"])
            or not _same(owner.manifest["runtime"], anchor.manifest["runtime"])
            or owner.manifest["authorization_path"] != str(reader.authorization)
            or any(bindings.get(path) != digest for path, digest in controls.items())
        ):
            raise reader.error_type("screen owner changes an original component or control")
    funding = _authority(reader.capture, reader.authorization, list(reader.owners.values()))
    if funding is None:
        raise reader.error_type("explicit original screen authority is required")
    funded = {str(row["run_id"]): row for row in _rows(funding["auth_runs"])}
    for row in funded.values():
        path = pipeline._absolute(row["directory"])
        if path.is_relative_to(reader.root) and (
            path not in planned
            or path not in reader.owners
            or reader.owners[path].run_id != row["run_id"]
        ):
            raise reader.error_type("retained funded owner is missing or outside the screen")
    for owner in reader.owners.values():
        row = funded[owner.run_id]
        if (
            type(row["historical"]) is not int
            or row["historical"] != 0
            or row["runtime_sha256"] != owner.manifest["execution_sha256"]
        ):
            raise reader.error_type("screen owner differs from its original authority runtime")
    return funding


def _source(
    reader: NativeEvidence,
    screen: object,
    tasks: TaskSet,
    location: Path,
    runtime_sha256: str,
    current: dict[str, object],
) -> tuple[_Generation, dict[str, object], str]:
    from buddha.source_screen import SourceScreen, _generation_formats, _version

    if not isinstance(screen, SourceScreen):
        raise reader.error_type("source needs its original screen")
    record = screen.to_record()
    root = location / "generation"
    owner = reader.owner(root / "owners/0")
    task_path, descriptor = location / "task.json", location / "generation.json"
    if reader.bound(owner, task_path) != tasks.to_bytes():
        raise reader.error_type("source task differs from its original common screen")
    generation = _object(record["generation"])
    recipe = {
        "format": _version(screen, "candidate-generation"),
        "tasks": str(task_path),
        **{
            key: generation[key]
            for key in ("config", "entrypoint", "executor", "profile", "runtime", "max_callbacks")
        },
    }
    if not _same(_load(reader.bound(owner, descriptor)), recipe) or not _same(
        _load(reader.bound(owner, root / "context.json")),
        {
            "format": _generation_formats(screen)["context"],
            "descriptor": str(descriptor),
            "expected_runtime_sha256": runtime_sha256,
        },
    ):
        raise reader.error_type("source recipe differs from its original common screen")
    reference: dict[str, object] = {
        "format": _generation_formats(screen)["source"],
        "generation_directory": str(root),
        "stage_seal_sha256": _sha(reader.raw(root / "completed/0.json")),
        "owner_manifest_sha256": owner.manifest_sha256,
        "owner_ledger_sha256": owner.ledger_sha256,
    }
    prospective_report = None
    if record["format"] == "buddha.source-screen.v2":
        prospective_report, source, captured = _read_published_generation(
            root,
            authorization=reader.authorization,
            expected_report_sha256=_sha(reader.raw(root / "report.json")),
        )
        if source is None or not _same(prospective_report["source_generation"], reference):
            raise reader.error_type("source publication changes its original generation")
        _adopt_capture(captured, reader.capture)
    else:
        source = _read_generation(reference, reader.authorization)
    if source.tasks.fingerprint() != tasks.fingerprint():
        raise reader.error_type("source C1 changes the declared screen task")
    reader.verify_files(source.files)
    seal = reader.record(root / "completed/0.json")
    attempt = root / _path(seal["attempt"])
    report = reader.record(attempt / "report.json")
    if prospective_report is not None:
        _, digest = _publication(
            reader, root / "report.json", prospective_report, current, {owner.run_id}
        )
        return source, reference, digest
    expected: dict[str, object] = {
        "format": "buddha.candidate-generation-stage-report.v1",
        "status": "complete",
        "stage_seal_sha256": reference["stage_seal_sha256"],
        "generation": report,
        "authorization": current,
        "claim": "anchored source generation only; no development eligibility or improvement claim",
    }
    _, digest = _publication(reader, root / "report.json", expected, current, {owner.run_id})
    return source, reference, digest


def _failed_source(
    reader: NativeEvidence,
    screen: object,
    index: int,
    runtime_sha256: str,
    current: dict[str, object],
) -> dict[str, object]:
    from buddha.source_screen import SourceScreen, _generation_formats, _generation_recipe

    if not isinstance(screen, SourceScreen):
        raise reader.error_type("failed source needs its original screen")
    location = reader.root / "tasks" / str(index)
    root = location / "generation"
    owner = reader.owner(root / "owners/0")
    tasks = screen.tasks
    task = tasks.tasks[index]
    if reader.bound(owner, location / "task.json") != tasks.select([task.id]).to_bytes():
        raise reader.error_type("failed source changes the original task")
    descriptor = location / "generation.json"
    if reader.bound(owner, descriptor) != _json(_generation_recipe(location, screen)) or (
        reader.bound(owner, root / "context.json")
        != _json(
            {
                "format": _generation_formats(screen)["context"],
                "descriptor": str(descriptor),
                "expected_runtime_sha256": runtime_sha256,
            }
        )
    ):
        raise reader.error_type("failed source changes an original screen control")
    raw = reader.raw(root / "report.json")
    report, _, captured = _read_published_generation(
        root, authorization=reader.authorization, expected_report_sha256=_sha(raw)
    )
    _adopt_capture(captured, reader.capture)
    if raw != _json(report) or report["disposition"] != "candidate_execution_failed":
        raise reader.error_type("failed source lacks a checked terminal outcome")
    reference = _object(report["source_generation"])
    if reference != {
        "format": _generation_formats(screen)["source"],
        "generation_directory": str(root),
        "stage_seal_sha256": _sha(reader.raw(root / "completed/0.json")),
        "owner_manifest_sha256": owner.manifest_sha256,
        "owner_ledger_sha256": owner.ledger_sha256,
    }:
        raise reader.error_type("failed source reference changes its original owner")
    anchors = [
        row["reason"]
        for row in reader._rows(reader.funded["auth_deactivations"])
        if row["run_id"] == owner.run_id
    ]
    if anchors != [_generation_formats(screen)["anchor"] + _text(reference["stage_seal_sha256"])]:
        raise reader.error_type("failed source lacks its original captured completion anchor")
    _publication(reader, root / "report.json", report, current, {owner.run_id}, _sha(raw))
    return {
        "task_index": index,
        "task_id": task.id,
        "source_generation": reference,
        "generation_report_sha256": _sha(raw),
        "terminal": _object(_object(report["outcome"])["terminal"]),
    }


def _native(
    reader: NativeEvidence,
    record: dict[str, object],
    source: _Generation,
    reference: dict[str, object],
    location: Path,
    current: dict[str, object],
) -> tuple[dict[str, Path], dict[str, object], str]:
    root = location / "evaluation"
    first = reader.owner(root / "owners/1")
    descriptor = location / "evaluation.json"
    expected_definition = {
        "format": "buddha.native-evaluation.v1",
        "source_generation": reference,
        "native": record["native"],
        "stages": record["stages"],
    }
    if not _same(_load(reader.bound(first, descriptor)), expected_definition) or not _same(
        _load(reader.bound(first, root / "context.json")),
        {"format": "buddha.native-evaluation-context.v1", "descriptor": str(descriptor)},
    ):
        raise reader.error_type("native occasion changes its original common screen")
    native_raw = source.answers.native_bytes()
    if reader.raw(root / "native-answers.jsonl") != native_raw:
        raise reader.error_type("native occasion changes the original literal C1")
    artifacts = _object(reader.release.to_record()["artifacts"])
    stages = _rows(record["stages"])
    available = {_path(artifacts["answers"]): root / "native-answers.jsonl"}
    reports, seals = [], {}
    for index, stage in enumerate(stages, 1):
        report, attempt = reader.stage(root, index, baseline=False)
        reader.native(root, index, report, source.answers_path, available)
        outputs = _rows(stage["outputs"])
        names = [_path(output["path"]) for output in outputs]
        for output, name in zip(outputs, names, strict=True):
            path = attempt / "artifacts" / name
            if output["id_field"] is not None:
                pipeline._coverage(
                    path,
                    _text(output["id_field"]),
                    source.tasks,
                    _object(report["artifacts"])[name],
                )
            available[name] = path
        reports.append(report)
        sealed = root / "completed" / (str(index) + ".json")
        seals[str(sealed.relative_to(root))] = reader.seals[sealed]
    summary = available[_path(artifacts["summary"])]
    summary_reference: dict[str, object] = {
        "path": str(summary),
        "sha256": _sha(reader.raw(summary)),
    }
    expected: dict[str, object] = {
        "format": "buddha.native-evaluation-report.v1",
        "status": "complete",
        "release_sha256": reader.release.fingerprint(),
        "tasks_sha256": source.tasks.fingerprint(),
        "source_generation": reference,
        "answers_file_sha256": _sha(reader.raw(source.answers_path)),
        "answers_sha256": source.answers.fingerprint(),
        "native_answers_sha256": _sha(native_raw),
        "stages": reports,
        "stage_seals": seals,
        "summary": summary_reference,
        "authorization": current,
        "claim": "complete fresh native assessment of saved generation; no improvement claim",
    }
    _, digest = _publication(
        reader,
        root / "report.json",
        expected,
        current,
        {reader.owner(root / "owners" / str(i)).run_id for i in range(1, len(stages) + 1)},
    )
    return available, summary_reference, digest


def _collect_source_screen(
    directory: Path,
    *,
    authorization: Path,
    expected_report_sha256: str | None = None,
    sink: _Capture | None = None,
    retain: bool = False,
    observation_root: Path | None = None,
) -> _CompletedScreenRead:
    """Reconstruct complete custody or verify an explicitly pinned publication."""
    from buddha.source_screen import (
        SourceScreen,
        SourceScreenError,
        _comparison_controls,
        _lineage,
        _version,
    )

    try:
        if not isinstance(directory, Path) or not isinstance(authorization, Path):
            raise SourceScreenError("screen evidence requires explicit Path inputs")
        directory, authorization = (
            pipeline._absolute(str(directory)),
            pipeline._absolute(str(authorization)),
        )
        if sink is not None and (
            type(sink) is not _Capture or not directory.is_relative_to(sink.root)
        ):
            raise SourceScreenError("screen capture requires its original containing observation")
        observation_root = directory if observation_root is None else observation_root
        read_context = _read_context(observation_root) if retain else None
        if retain and (
            expected_report_sha256 is None
            or read_context is None
            or not directory.is_relative_to(observation_root)
        ):
            raise SourceScreenError("retained read requires one pinned original publication")
        reader = NativeEvidence(directory, authorization, error_type=SourceScreenError)
        anchor = reader.owner(directory / "tasks/0/generation/owners/0")
        screen_raw = reader.bound(anchor, directory / "screen.json")
        screen = SourceScreen.from_bytes(screen_raw)
        record, tasks = screen.to_record(), screen.tasks
        context_raw = reader.bound(anchor, directory / "context.json")
        context = _object(
            _load(context_raw),
            {
                "format",
                "screen_sha256",
                "expected_runtime_sha256",
                "controls",
                "comparison_controls",
            },
        )
        runtime_sha256 = _digest(context["expected_runtime_sha256"])
        generation = _object(record["generation"])
        runtime = _object(generation["runtime"])
        if (
            context["format"] != _version(screen, "source-screen-context")
            or context["screen_sha256"] != screen.fingerprint()
            or runtime["sha256"] != runtime_sha256
            or screen_raw != screen.to_bytes()
        ):
            raise SourceScreenError("original screen/context identity differs")
        controls = {
            str(pipeline._absolute(path)): _digest(digest)
            for path, digest in _object(context["controls"]).items()
        }
        if (
            not controls
            or len(controls) > 1024
            or controls.get(_text(runtime["path"])) != runtime_sha256
        ):
            raise SourceScreenError("original screen controls omit independent runtime approval")
        controls_sha256 = pipeline._sha(
            {
                "files": _comparison_controls(
                    context,
                    {Path(path): digest for path, digest in controls.items()},
                    screen,
                    core=anchor.manifest["core"],
                ),
                "core": anchor.manifest["core"],
                "runtime": anchor.manifest["runtime"],
            }
        )
        controls.update(
            {
                str(directory / "screen.json"): _sha(screen_raw),
                str(directory / "context.json"): _sha(context_raw),
            }
        )
        reader.release = Release.from_record(_object(record["source"])["release"])
        reader.template = {"native": record["native"], "stages": record["stages"]}
        pipeline.validate_native_flow(record["stages"], reader.release)
        failed_index: int | None = None
        count = len(tasks.tasks)
        if record["format"] == "buddha.source-screen.v2":
            observed = {
                name.split("/")[1] for name in reader.capture.entries if name.startswith("tasks/")
            }
            if (
                not observed
                or observed != {str(i) for i in range(len(observed))}
                or (len(observed) > count)
            ):
                raise SourceScreenError("prospective screen has an invalid task prefix")
            for index in range(len(observed)):
                published = reader.record(
                    directory / "tasks" / str(index) / "generation/report.json"
                )
                if published.get("disposition") == "candidate_execution_failed":
                    if index != len(observed) - 1:
                        raise SourceScreenError("screen work follows a failed candidate")
                    failed_index = index
            if failed_index is None and len(observed) != count:
                raise SourceScreenError("complete screen omits scheduled tasks")
            count = len(observed)
        reader.funded = _owners(reader, record, count, controls, failed_index=failed_index)
        config = _object(reader.funded["config"])
        trial_fence.require_purpose(
            authorization,
            config,
            directory=directory,
            expected="source screen: " + screen.comparison_key(),
        )
        current = authority_observation(reader.capture, authorization, reader.funded)
        if record["lineage"] is not None:
            lineage = _object(record["lineage"])
            if controls.get(_text(lineage["path"])) != lineage["sha256"]:
                raise SourceScreenError("lineage was not an original screen control")
        parent_id = _lineage(screen, lambda path, digest: reader.raw(path, digest))
        rows: list[dict[str, object]] = []
        seals: dict[str, str] = {}
        failure: dict[str, object] | None = None
        for index, task in enumerate(tasks.tasks[:count]):
            location = directory / "tasks" / str(index)
            if index == failed_index:
                failure = _failed_source(reader, screen, index, runtime_sha256, current)
                if any(
                    name.startswith(
                        (location / "evaluation").relative_to(directory).as_posix() + "/"
                    )
                    for name in reader.capture.entries
                ):
                    raise SourceScreenError("failed candidate has unexpected native work")
                seals[
                    (location / "generation/completed/0.json").relative_to(directory).as_posix()
                ] = _digest(_object(failure["source_generation"])["stage_seal_sha256"])
                break
            for role, names in (
                ("generation", {"0.json"}),
                (
                    "evaluation",
                    {str(i) + ".json" for i in range(1, len(_rows(record["stages"])) + 1)},
                ),
            ):
                prefix = (location / role / "completed").relative_to(directory).as_posix() + "/"
                actual = {
                    name.removeprefix(prefix)
                    for name in reader.capture.entries
                    if name.startswith(prefix)
                }
                if actual != names:
                    raise SourceScreenError("screen contains missing or orphan completion seals")
            source, reference, source_digest = _source(
                reader, screen, tasks.select([task.id]), location, runtime_sha256, current
            )
            available, summary, evaluation_digest = _native(
                reader, record, source, reference, location, current
            )
            projected: dict[str, object] = {
                "task_id": task.id,
                "distinct": None,
                "utility": None,
                "invalid_metrics": [],
                "diagnostics": {"projection": None},
            }
            if record["projection"] == "noveltybench-1.1":
                from buddha.noveltybench_results import project_rows, reporting_configuration

                reporting_configuration(reader.release, _rows(record["stages"]))
                artifacts = _object(reader.release.to_record()["artifacts"])
                result_paths = cast(list[str], artifacts["results"])
                projected = project_rows(
                    source.tasks,
                    source.answers,
                    reader.raw(available[result_paths[0]]),
                    reader.raw(available[result_paths[1]]),
                )[0]
            rows.append(
                projected
                | {
                    "source_generation": reference,
                    "generation_report_sha256": source_digest,
                    "evaluation_report_sha256": evaluation_digest,
                    "summary": summary,
                }
            )
            seals[(location / "generation/completed/0.json").relative_to(directory).as_posix()] = (
                cast(str, reference["stage_seal_sha256"])
            )
        reasons = ["candidate_execution_failed"] if failure is not None else []
        means: dict[str, object] = {}
        for metric, minimum in (("distinct", 1), ("utility", 0)):
            values = [row[metric] for row in rows]
            usable = (
                failure is None
                and bool(values)
                and all(
                    type(value) in (int, float)
                    and minimum <= cast(float, value) <= 10
                    and math.isfinite(cast(float, value))
                    for value in values
                )
            )
            means["mean_" + metric] = (
                math.fsum(cast(list[float], values)) / len(rows) if usable else None
            )
            if not usable and failure is None:
                reasons.append("unavailable_or_invalid_" + metric)
        if record["projection"] is None:
            reasons.append("projection_unavailable")
        if any(task.count > 10 for task in tasks.tasks):
            reasons.append("answer_count_outside_archive_domain")
        result: dict[str, object] = {
            "format": _version(screen, "source-screen-report"),
            "status": "complete",
            "screen_sha256": screen.fingerprint(),
            "candidate_id": screen.candidate_id,
            "comparison_key": screen.comparison_key(),
            "parent_id": parent_id,
            "controls_sha256": controls_sha256,
            "admission": {"eligible": not reasons, "reasons": reasons, **means},
            "tasks": rows,
            "authorization": current,
            "provenance": {
                "context_sha256": _sha(context_raw),
                "controls": controls,
                "owners": [
                    {
                        "directory": str(path),
                        "run_id": owner.run_id,
                        "manifest_sha256": owner.manifest_sha256,
                        "ledger_sha256": owner.ledger_sha256,
                    }
                    for path, owner in sorted(reader.owners.items())
                ],
                "seals": seals
                | {
                    path.relative_to(directory).as_posix(): digest
                    for path, digest in reader.seals.items()
                },
            },
            "claim": _CLAIM,
        }
        if record["format"] == "buddha.source-screen.v2":
            result.update(
                {
                    "disposition": "screened" if failure is None else "candidate_execution_failed",
                    "failure": failure,
                    "unattempted": {
                        "generation_task_ids": [task.id for task in tasks.tasks[count:]],
                        "native_task_ids": [task.id for task in tasks.tasks[count - 1 :]]
                        if failure is not None
                        else [],
                    },
                    "claim": _CLAIM
                    if failure is None
                    else "checked candidate execution failure; no complete screen or numeric score",
                }
            )
        if expected_report_sha256 is not None:
            result, _ = _publication(
                reader,
                directory / "report.json",
                result,
                current,
                {owner.run_id for owner in reader.owners.values()},
                _digest(expected_report_sha256),
            )
        if len(_json(result)) > MAX_JSON_BYTES:
            raise SourceScreenError("screen report exceeds its bounded output ceiling")
        completed = _CompletedScreenRead(
            screen, _json(result), reader, read_context, observation_root
        )
        if retain:
            _reuse_completed_screen(
                completed, directory, authorization, _digest(expected_report_sha256)
            )
            if sink is not None:
                _adopt_capture(reader.capture, sink)
        elif sink is None:
            reader.capture.finish()
        else:
            _adopt_capture(reader.capture, sink)
        return completed
    except (
        ValueError,
        TypeError,
        KeyError,
        OSError,
        RecursionError,
        OverflowError,
        sqlite3.Error,
        _Busy,
        _Unsupported,
    ) as error:
        if isinstance(error, SourceScreenError):
            raise
        raise SourceScreenError("source screen evidence is invalid or changed") from None


def collect_source_screen(
    directory: Path,
    *,
    authorization: Path,
    expected_report_sha256: str | None = None,
    sink: _Capture | None = None,
) -> dict[str, object]:
    """Reconstruct complete custody or verify an explicitly pinned publication."""
    return _load(
        _collect_source_screen(
            directory,
            authorization=authorization,
            expected_report_sha256=expected_report_sha256,
            sink=sink,
        ).report_raw
    )
