"""Descriptive plain/Buddha comparisons from prospectively bound original evidence."""

from collections.abc import Mapping
from fractions import Fraction
from pathlib import Path
from typing import Any, cast

from buddha import (
    baseline_results,
    doctor,
    improver_assessment,
    policy_results,
    validation_analysis,
)
from buddha import native_pipeline as pipeline
from buddha import noveltybench_results as projection
from buddha import validation_study as study
from buddha.doctor import _Busy, _Owner, _Unsupported
from buddha.native_evidence import NativeEvidence, _rows, authority_observation
from buddha.releases import ReleaseError, Selection, _digest, _json, _load, _object, file_hash

_ROLES = ("starter", "initial", "evolved")
_AXES = ("utility", "distinct")
_METHOD = "all_conditions_then_equal_prompts_descriptive.v1"


class PlainComparisonError(ReleaseError):
    """Original evidence or the prospective comparison controls are inconsistent."""


def _source_hashes() -> dict[str, str]:
    modules = (
        baseline_results,
        doctor,
        improver_assessment,
        projection,
        policy_results,
        validation_analysis,
    )
    paths = [
        Path(__file__).absolute(),
        *(Path(cast(str, module.__file__)).absolute() for module in modules),
    ]
    return {str(path): file_hash(path) for path in paths}


def _plan(raw: bytes) -> dict[str, Any]:
    record = _object(
        _load(raw),
        {"format", "method", "trial", "definition_sha256", "references", "consumer_sources"},
    )
    if (
        record["format"] != "buddha.plain-comparison-plan.v1"
        or record["method"] != _METHOD
        or record["consumer_sources"] != _source_hashes()
    ):
        raise PlainComparisonError("unsupported or changed prospective comparison method")
    trial = pipeline._absolute(record["trial"])
    _digest(record["definition_sha256"])
    rows = record["references"]
    if type(rows) is not list or not 1 <= len(rows) <= 2:
        raise PlainComparisonError("declare one or both plain sampling references")
    names, locations = set(), [trial]
    for value in rows:
        row = _object(value, {"name", "directory", "authorization", "definition", "sha256"})
        if row["name"] not in {"regenerate", "in-context"} or row["name"] in names:
            raise PlainComparisonError("plain reference mode is unknown or repeated")
        names.add(row["name"])
        root = pipeline._absolute(row["directory"])
        if any(root.is_relative_to(path) or path.is_relative_to(root) for path in locations):
            raise PlainComparisonError("comparison populations need distinct original roots")
        locations.append(root)
        pipeline._absolute(row["authorization"])
        pipeline._absolute(row["definition"])
        _digest(row["sha256"])
    return cast(dict[str, Any], record)


def _bound(reader: NativeEvidence, path: Path, digest: str) -> None:
    for owner in reader.owners.values():
        if reader._bindings(owner).get(str(path)) != digest:
            raise PlainComparisonError("comparison was not bound into every original owner")
        reader.raw(path, digest)


def _profile(generation: dict[str, Any], owner: _Owner) -> dict[str, object]:
    role = _object(generation["profile"])
    profiles = _object(_object(owner.manifest["profiles"])[cast(str, role["capability"])])
    return _object(_object(profiles["profiles"])[cast(str, role["profile_id"])])


def _instrument(native: dict[str, Any]) -> dict[str, object]:
    # Source inventory, locations and whole-panel wallet/call limits differ;
    # all evaluator code, runtime, hooks, profiles and execution limits stay fixed.
    record = _load(_json(native))
    for name in ("roots", "budget_microusd", "max_calls"):
        record.pop(name)
    selected = Selection.from_bytes(_json(record["selection"])).to_record()
    _object(selected["components"])["agent"] = {}
    record["selection"] = selected
    return record


def _ratios(values: list[object], expected: int) -> dict[str, int] | None:
    numbers = [validation_analysis._scalar(value) for value in values]
    if len(numbers) != expected or any(number is None for number in numbers):
        return None
    return validation_analysis._ratio(sum(cast(list[Fraction], numbers), Fraction()) / expected)


def _fraction(value: dict[str, int] | None) -> Fraction | None:
    return None if value is None else Fraction(value["numerator"], value["denominator"])


def _panel(
    state: dict[str, Any], rows: list[dict[str, Any]], references: dict[str, list[dict[str, Any]]]
) -> dict[str, object]:
    counts = state["plan"].to_record()["counts"]
    expected = counts["starts"] * counts["development_repetitions"] * counts["sealed_repetitions"]
    population = cast(list[dict[str, Any]], improver_assessment._population(state)["tasks"])
    prompts = []
    for task in population:
        identifier = task["task_id"]
        role_means = {
            role: {
                axis: _ratios(
                    [
                        row[axis]
                        for row in rows
                        if row["role"] == role and row["task_id"] == identifier
                    ],
                    expected,
                )
                for axis in _AXES
            }
            for role in _ROLES
        }
        reference_means = {}
        for name, scalars in references.items():
            scalar = next(row for row in scalars if row["task_id"] == identifier)
            reference_means[name] = {
                axis: _ratios([None if axis in scalar["invalid_metrics"] else scalar[axis]], 1)
                for axis in _AXES
            }
        prompts.append({**task, "buddha": role_means, "references": reference_means})
    contrasts: list[dict[str, Any]] = []
    for name in references:
        for role in _ROLES:
            axes = {}
            for axis in _AXES:
                differences = []
                for prompt in prompts:
                    left = _fraction(prompt["buddha"][role][axis])
                    right = _fraction(prompt["references"][name][axis])
                    differences.append(None if left is None or right is None else left - right)
                axes[axis] = {
                    "status": "incomplete" if None in differences else "complete",
                    "available_prompts": sum(value is not None for value in differences),
                    "planned_prompts": len(population),
                    "mean_difference": None
                    if None in differences
                    else validation_analysis._ratio(
                        sum(cast(list[Fraction], differences), Fraction()) / len(population)
                    ),
                }
            contrasts.append({"reference": name, "role": role, "metrics": axes})
    complete = all(
        metric["status"] == "complete" for row in contrasts for metric in row["metrics"].values()
    )
    return {
        "status": "complete" if complete else "incomplete",
        "reason": "complete_planned_panel" if complete else "missing_planned_condition_or_scalar",
        "planned_buddha_sets": 3 * expected * len(population),
        "observed_buddha_sets": len(rows),
        "unique_reference_sets": len(references) * len(population),
        "buddha_measurements": rows,
        "reference_measurements": references,
        "prompts": prompts,
        "contrasts": contrasts,
    }


def _resources(readers: dict[str, NativeEvidence], schedule: dict[str, Any]) -> dict[str, object]:
    operations, owners = [], []
    seen = set()
    for label, reader in readers.items():
        stages = projection.reporting_configuration(
            reader.release, cast(list[dict[str, object]], reader.template["stages"])
        )
        for owner in reader.owners.values():
            if owner.run_id in seen:
                raise PlainComparisonError("one original owner appears in multiple conditions")
            seen.add(owner.run_id)
            condition = label
            if label == "buddha":
                arm = int(owner.directory.relative_to(reader.root).parts[1])
                condition += "/" + schedule["arms"][arm]["role"]
            stage = int(owner.directory.name)
            stage_role = (
                "generation" if stage == 0 else cast(list[str], stages["stage_roles"])[stage - 1]
            )
            owners.append(
                {"condition": condition, "run_id": owner.run_id, "accounting": owner.accounting()}
            )
            operations += policy_results._operation_evidence(
                owner,
                {"condition": condition, "group": label, "stage_role": stage_role},
                cast(str | None, stages["fallback_model"]),
            )
    summary = policy_results._cost_summary(operations)
    if any(
        summary[key] != sum(cast(int, _object(owner["accounting"])[key]) for owner in owners)
        for key in ("committed_microusd", "spent_microusd", "reserved_microusd", "operation_count")
    ):
        raise PlainComparisonError("comparison costs differ from original owner accounting")
    return {
        "owners": owners,
        "operations": operations,
        "unique_original_execution": summary,
        "by_condition": {
            name: policy_results._cost_summary(
                [row for row in operations if row["condition"] == name]
            )
            for name in [*("buddha/" + role for role in _ROLES), *list(readers)[1:]]
        },
        "by_group": {
            name: policy_results._cost_summary([row for row in operations if row["group"] == name])
            for name in readers
        },
    }


def _development_resources(state: dict[str, Any]) -> dict[str, object]:
    capture = state["development_capture"]
    report = state["development_report"]
    owners, operations, seen = [], [], set()
    for row in report["provenance"]["owners"]:
        path = pipeline._absolute(row["directory"])
        if not path.is_relative_to(capture.root):
            raise PlainComparisonError("development owner leaves its original captured study")
        owner = doctor._owner(capture, path)
        if (
            owner.run_id in seen
            or owner.run_id != row["run_id"]
            or owner.manifest_sha256 != row["manifest_sha256"]
            or owner.ledger_sha256 != row["ledger_sha256"]
        ):
            raise PlainComparisonError("development resource evidence changes an original owner")
        seen.add(owner.run_id)
        parts = path.relative_to(capture.root).parts
        condition = "common" if parts[0] == "common" else ("initial", "evolved")[int(parts[3])]
        owners.append({"directory": str(path), "run_id": owner.run_id})
        operations += policy_results._operation_evidence(
            owner,
            {"condition": "development/" + condition, "stage_role": "unattributed_development"},
            None,
        )
    summary = policy_results._cost_summary(operations)
    if any(summary[key] != value for key, value in report["costs"]["totals"].items()):
        raise PlainComparisonError("development usage differs from its original accounting")
    capture.finish()
    return {"owners": owners, "operations": operations, "summary": summary}


def _compare(
    plan: Path,
    plan_digest: str,
    assessment_digest: str,
    reference_digests: Mapping[str, str],
) -> dict[str, object]:
    if not isinstance(plan, Path) or not isinstance(reference_digests, Mapping):
        raise PlainComparisonError("comparison needs a plan Path and original publication pins")
    plan = pipeline._absolute(str(plan.absolute()))
    pin = _digest(plan_digest)
    record = _plan(pipeline._read(plan, pin))
    report, state, schedule, reader = improver_assessment._read_improver_assessment(
        pipeline._absolute(record["trial"]), expected_report_sha256=_digest(assessment_digest)
    )
    if state["controls"].get(plan) != pin or (
        pipeline._sha(state["definition"]) != record["definition_sha256"]
    ):
        raise PlainComparisonError("original study did not declare this comparison")
    _bound(reader, plan, pin)
    references = cast(list[dict[str, Any]], record["references"])
    if set(reference_digests) != {row["name"] for row in references}:
        raise PlainComparisonError("every declared original reference publication is required")
    tasks = state["tasks"].select(schedule["selected_ids"])
    generation = state["record"]["generation"]
    first = next(study._cells(state, schedule))[-1]
    access = _profile(generation, reader.owner(first / "generation/owners/0"))
    scalars: dict[str, list[dict[str, Any]]] = {}
    readers = {"buddha": reader}
    resources = {"buddha": {"generation": generation, "native": state["record"]["native"]}}
    publications = {}
    for row in references:
        name = row["name"]
        observed = baseline_results._read_baseline(
            pipeline._absolute(row["directory"]),
            authorization=pipeline._absolute(row["authorization"]),
            expected_report_sha256=_digest(reference_digests[name]),
            expected_definition_sha256=row["sha256"],
        )
        original = observed.reader.owner(observed.reader.root / "owners/0")
        context = _load(observed.reader.bound(original, observed.reader.root / "context.json"))
        if context["descriptor"] != row["definition"]:
            raise PlainComparisonError("reference uses a different original definition location")
        _bound(observed.reader, plan, pin)
        producer = _object(observed.definition["generation"])
        recipe = _load(observed.reader.bound(original, pipeline._absolute(producer["descriptor"])))
        config = _object(recipe["config"])
        if (
            observed.source.tasks.to_bytes() != tasks.to_bytes()
            or config["instructions"] != ""
            or config["sampling"] != name
            or any(
                config[key] != generation["config"][key]
                for key in ("provider", "model", "max_output_tokens")
            )
            or _json(_profile(recipe, original)) != _json(access)
            or _json(_instrument(cast(dict[str, Any], observed.definition["native"])))
            != _json(_instrument(state["record"]["native"]))
            or _json(observed.definition["stages"]) != _json(state["record"]["stages"])
        ):
            raise PlainComparisonError("reference changes the panel, plain procedure or instrument")
        projection.reporting_configuration(
            observed.reader.release, cast(list[dict[str, object]], observed.definition["stages"])
        )
        artifacts = _object(observed.reader.release.to_record()["artifacts"])
        results = cast(list[str], artifacts["results"])
        scalars[name] = projection.project_rows(
            observed.source.tasks,
            observed.source.answers,
            observed.reader.raw(observed.artifacts[results[0]]),
            observed.reader.raw(observed.artifacts[results[1]]),
        )
        readers[name] = observed.reader
        resources[name] = {
            "generation": recipe | {"owner_limits": original.manifest["settings"]},
            "native": observed.definition["native"],
        }
        publications[name] = {"report_sha256": reference_digests[name], "report": observed.report}
    current = authority_observation(reader.capture, reader.authorization, reader.funded)
    rows = improver_assessment._measurement_rows(state, schedule, reader, current)
    execution = _resources(readers, schedule)
    development_execution = _development_resources(state)
    development = _object(report["development_costs"])
    original_owners = [*_rows(execution["owners"]), *_rows(development_execution["owners"])]
    if len({row["run_id"] for row in original_owners}) != len(original_owners):
        raise PlainComparisonError("development and final/reference owners overlap")
    result = {
        "format": "buddha.plain-comparison-report.v1",
        "plan_sha256": pin,
        "method": _METHOD,
        "assessment_report_sha256": assessment_digest,
        "references": publications,
        "slots": schedule["slots"],
        "analysis": _panel(state, rows, scalars),
        "generation_access": access,
        "declared_resources": resources,
        "actual_execution": execution,
        "development_costs": development,
        "development_execution": development_execution,
        "combined_original_api_research": policy_results._cost_summary(
            [*_rows(execution["operations"]), *_rows(development_execution["operations"])]
        ),
        "claim": (
            "Descriptive fixed-panel system comparison; no significance, promotion, "
            "human preference, "
            "unseen-task or compute-isolated harness effect claim."
        ),
    }
    for evidence in readers.values():
        evidence.finish()
    return result


def compare_plain_references(
    plan: Path,
    *,
    expected_plan_sha256: str,
    expected_assessment_report_sha256: str,
    expected_reference_report_sha256: Mapping[str, str],
) -> dict[str, object]:
    """Read original complete publications; retain undefined contrasts without imputation."""
    try:
        return _compare(
            plan,
            expected_plan_sha256,
            expected_assessment_report_sha256,
            expected_reference_report_sha256,
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
        raise PlainComparisonError("invalid original plain/Buddha comparison evidence") from None
