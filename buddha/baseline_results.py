"""Passive original baseline custody; never run a producer or interpret its scores."""

from dataclasses import dataclass
from pathlib import Path
from typing import cast

from buddha import native_pipeline as pipeline
from buddha.answers import TaskSet
from buddha.doctor import _authority, _Busy, _Unsupported
from buddha.native_evaluation import _Generation, _read_baseline_generation
from buddha.native_evidence import NativeEvidence, _sha, authority_observation
from buddha.releases import Release, ReleaseError, Selection, _digest, _json, _load, _object, _path


class BaselineResultsError(ReleaseError):
    """A baseline lacks its original complete, consistently bound evidence."""


@dataclass(frozen=True)
class _Baseline:
    report: dict[str, object]
    definition: dict[str, object]
    source: _Generation
    artifacts: dict[str, Path]
    reader: NativeEvidence


def _context(
    reader: NativeEvidence,
    definition_digest: str,
    *,
    complete: bool = True,
) -> tuple[dict[str, object], TaskSet]:
    """Join frozen inputs and every existing owner to its original funding."""
    root, authority = reader.root, reader.authorization
    anchor = reader.owner(root / "owners/0")
    context = _object(_load(reader.bound(anchor, root / "context.json")), {"format", "descriptor"})
    if context["format"] != "buddha.baseline-context.v1":
        raise BaselineResultsError("unsupported original baseline context")
    descriptor = pipeline._absolute(context["descriptor"])
    raw = reader.bound(anchor, descriptor)
    if _sha(raw) != _digest(definition_digest):
        raise BaselineResultsError("baseline definition differs from its expected bytes")
    definition = _object(_load(raw), {"format", "tasks", "generation", "native", "stages"})
    if definition["format"] != "buddha.native-baseline.v1":
        raise BaselineResultsError("unsupported original baseline definition")
    generation, native = _object(definition["generation"]), _object(definition["native"])
    selected = Selection.from_bytes(_json(generation["selection"]))
    evaluated = Selection.from_bytes(_json(native["selection"]))
    reader.release = Release.from_record(selected.to_record()["release"])
    reader.template = definition
    tasks = TaskSet.from_bytes(reader.bound(anchor, pipeline._absolute(definition["tasks"])))
    if (
        selected.release_sha256 != evaluated.release_sha256
        or selected.agent_sha256 != evaluated.agent_sha256
        or tasks.release_sha256 != selected.release_sha256
    ):
        raise BaselineResultsError("baseline source, evaluation and task lineage differ")
    pipeline.validate_native_flow(definition["stages"], reader.release)
    stages = reader._rows(definition["stages"])
    # Include empty/foreign owner directories, not just manifest-bearing paths.
    found = {
        root / "owners" / name.split("/", 2)[1]
        for name in reader.capture.entries
        if name.startswith("owners/")
    }
    count = len(stages) + 1 if complete else len(found)
    planned = {root / "owners" / str(index) for index in range(count)}
    if not 1 <= count <= len(stages) + 1 or found != planned:
        raise BaselineResultsError("baseline has missing or foreign owner evidence")
    controls = reader._bindings(anchor)
    for index in range(count):
        owner = reader.owner(root / "owners" / str(index))
        section = generation if index == 0 else native
        expected_settings = (
            {"budget_microusd": 1, "max_calls": 1}
            if index == len(stages)
            else {key: section[key] for key in ("budget_microusd", "max_calls")}
        )
        if any(
            _json(owner.manifest[key]) != _json(value)
            for key, value in {
                "selection": section["selection"],
                "roots": section["roots"],
                "settings": expected_settings,
                "review": anchor.manifest["review"],
                "core": anchor.manifest["core"],
                "runtime": anchor.manifest["runtime"],
                "authorization_path": str(authority),
            }.items()
        ) or any(reader._bindings(owner).get(path) != pin for path, pin in controls.items()):
            raise BaselineResultsError("baseline owner changes an original component or control")
    funding = _authority(reader.capture, authority, list(reader.owners.values()))
    if funding is None:
        raise BaselineResultsError("baseline needs its original explicit authority")
    reader.funded = funding
    funded = {row["run_id"]: row for row in reader._rows(funding["auth_runs"])}
    for row in funded.values():
        path = pipeline._absolute(row["directory"])
        if path.is_relative_to(root) and (
            path not in reader.owners or reader.owners[path].run_id != row["run_id"]
        ):
            raise BaselineResultsError("funded baseline owner is missing or unscheduled")
    for owner in reader.owners.values():
        row = funded[owner.run_id]
        if (
            type(row["historical"]) is not int
            or row["historical"] != 0
            or row["runtime_sha256"] != owner.manifest["execution_sha256"]
        ):
            raise BaselineResultsError("baseline owner differs from original funding")
    return definition, tasks


def _observe(
    directory: Path,
    authorization: Path,
    report_digest: str,
    definition_digest: str,
) -> _Baseline:
    if not isinstance(directory, Path) or not isinstance(authorization, Path):
        raise BaselineResultsError("baseline observation needs explicit Path inputs")
    root = pipeline._absolute(str(directory.absolute()))
    authority = pipeline._absolute(str(authorization.absolute()))
    reader = NativeEvidence(root, authority, error_type=BaselineResultsError)
    report_raw = reader.raw(root / "report.json", _digest(report_digest))
    report = _object(_load(report_raw))
    definition, tasks = _context(reader, definition_digest)
    anchor, funding = reader.owner(root / "owners/0"), reader.funded
    stages = reader._rows(definition["stages"])
    source = _read_baseline_generation(
        {
            "baseline_directory": str(root),
            "stage_seal_sha256": _sha(reader.raw(root / "completed/0.json")),
            "owner_manifest_sha256": anchor.manifest_sha256,
            "owner_ledger_sha256": anchor.ledger_sha256,
        },
        authority,
    )
    if source.tasks.fingerprint() != tasks.fingerprint():
        raise BaselineResultsError("baseline generation changes the selected tasks")
    reader.verify_files(source.files)
    answers = root / "native-answers.jsonl"
    if reader.raw(answers) != source.answers.native_bytes():
        raise BaselineResultsError("baseline changes the original native answers")
    artifacts = _object(reader.release.to_record()["artifacts"])
    available = {_path(artifacts["answers"]): answers}
    reports, seals = [], {}
    for index in range(len(stages) + 1):
        stage, attempt = reader.stage(root, index, baseline=True)
        reports.append(stage)
        sealed = root / "completed" / (str(index) + ".json")
        seals[str(sealed.relative_to(root))] = reader.seals[sealed]
        if index:
            reader.native(root, index, stage, source.answers_path, available)
            for output in reader._rows(stages[index - 1]["outputs"]):
                name = _path(output["path"])
                available[name] = attempt / "artifacts" / name
                if output["id_field"] is not None:
                    pipeline._coverage(
                        available[name],
                        cast(str, output["id_field"]),
                        tasks,
                        _object(stage["artifacts"])[name],
                    )
    summary = available[_path(artifacts["summary"])]
    expected = {
        "format": "buddha.native-baseline-report.v1",
        "status": "complete",
        "release_sha256": reader.release.fingerprint(),
        "tasks_sha256": tasks.fingerprint(),
        "stages": reports,
        "stage_seals": seals,
        "summary": {"path": str(summary), "sha256": _sha(reader.capture.raw[summary])},
        "authorization": report["authorization"],
        "claim": "complete selected native baseline; no optimizer projection or improvement claim",
    }
    current = authority_observation(reader.capture, authority, funding)
    pipeline.validate_authorization_snapshot(
        report["authorization"], current, {owner.run_id for owner in reader.owners.values()}
    )
    if report_raw != _json(expected):
        raise BaselineResultsError(
            "baseline publication differs from its original complete evidence"
        )
    reader.finish()
    return _Baseline(report, definition, source, available, reader)


def _read_baseline(
    directory: Path,
    *,
    authorization: Path,
    expected_report_sha256: str,
    expected_definition_sha256: str,
) -> _Baseline:
    try:
        return _observe(
            directory, authorization, expected_report_sha256, expected_definition_sha256
        )
    except (
        ReleaseError,
        _Busy,
        _Unsupported,
        ValueError,
        TypeError,
        KeyError,
        OSError,
        RecursionError,
    ):
        raise BaselineResultsError("original complete baseline evidence is invalid") from None


def inspect_baseline(
    directory: Path,
    *,
    authorization: Path,
    expected_report_sha256: str,
    expected_definition_sha256: str,
) -> dict[str, object]:
    """Return the original checked complete report without code, keys or writers."""
    return _read_baseline(
        directory,
        authorization=authorization,
        expected_report_sha256=expected_report_sha256,
        expected_definition_sha256=expected_definition_sha256,
    ).report
