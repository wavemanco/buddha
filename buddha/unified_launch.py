"""One scoped operator for original primary work and matched plain references."""

from collections.abc import Callable
from dataclasses import asdict
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, cast
from uuid import uuid4

from buddha import (
    baseline,
    baseline_state,
    comparison_observation,
    credentials,
    gateway,
    improver_handoff,
    improver_launch,
    plain_comparison,
    unified_funding,
)
from buddha import launch_common as common
from buddha import native_pipeline as pipeline
from buddha.answers import TaskSet
from buddha.doctor import _Busy, _Unsupported
from buddha.gateway import RawHTTPTransport
from buddha.provider import ModelSpec
from buddha.releases import ReleaseError, Selection, _digest, _json, _load, _object, file_hash
from buddha.search_evidence import _overlap

_ERRORS = (
    ValueError,
    TypeError,
    KeyError,
    OSError,
    RecursionError,
    OverflowError,
    _Busy,
    _Unsupported,
)
_ORDER = ("regenerate", "in-context")
_CLAIM = "Computational comparison only; native and human reviews remain separately required."


class UnifiedLaunchError(ReleaseError):
    """A combined launch differs from its reviewed scope or original state."""


def _entrypoint() -> Path:
    return Path(__file__).absolute().parent.parent / "docs/conformance/unified-run.py"


def _sources() -> list[Path]:
    return sorted(
        {
            *improver_launch._sources(),
            *baseline._sources(),
            *(common._path(p) for p in plain_comparison._source_hashes()),
            _entrypoint(),
            *(
                Path(cast(str, module.__file__)).absolute()
                for module in (
                    baseline,
                    baseline_state,
                    comparison_observation,
                    plain_comparison,
                    unified_funding,
                )
            ),
            Path(__file__).absolute(),
        }
    )


def _parameters(record: dict[str, Any]) -> dict[str, Any]:
    primary, plan = record["primary_launch"], record["comparison_plan"]
    return {
        "primary_launch": common._path(primary["path"]),
        "expected_launch_sha256": primary["sha256"],
        "comparison_plan": common._path(plan["path"]),
        "expected_plan_sha256": plan["sha256"],
        "reference_grant": record["reference_grant"],
        "total_limits": record["total_limits"],
    }


def _configuration(path: Path, digest: str) -> tuple[dict[str, Any], dict[Path, str]]:
    if not isinstance(path, Path):
        raise UnifiedLaunchError("combined launch needs an explicit Path")
    path, digest = common._path(str(path.absolute())), _digest(digest)
    record = cast(
        dict[str, Any],
        _object(
            _load(pipeline._read(path, digest)),
            {
                "format",
                "primary_launch",
                "comparison_plan",
                "reference_grant",
                "total_limits",
                "directory",
                "source_sha256",
            },
        ),
    )
    if record["format"] != "buddha.unified-launch.v1":
        raise UnifiedLaunchError("unsupported combined launch")
    for name in ("primary_launch", "comparison_plan"):
        comparison_observation._reference(record[name])
    pins = _object(record["source_sha256"])
    if not 1 <= len(pins) <= 1023:
        raise UnifiedLaunchError("combined source inventory exceeds its boundary")
    controls = {common._path(p): _digest(d) for p, d in pins.items()}
    if path in controls or any(controls.get(source) != file_hash(source) for source in _sources()):
        raise UnifiedLaunchError("combined runner sources are not reviewed")
    for source, expected in controls.items():
        if file_hash(source, max_bytes=256 * 1024**2) != expected:
            raise UnifiedLaunchError("combined source or control changed")
    _, protected = comparison_observation._arm(
        **{
            "primary": common._path(record["primary_launch"]["path"]),
            "launch_digest": record["primary_launch"]["sha256"],
            "plan": common._path(record["comparison_plan"]["path"]),
            "plan_digest": record["comparison_plan"]["sha256"],
            "reference_grant": record["reference_grant"],
            "total_limits": record["total_limits"],
            "input_bindings": controls,
        }
    )
    directory = common._path(record["directory"])
    protected.update((path, *controls))
    protected.update(p.parent for p in controls if p.suffix.lower() == ".py")
    if any(_overlap(directory, source) for source in protected):
        raise UnifiedLaunchError("operator workspace overlaps protected inputs or runs")
    controls[path] = digest  # Downstream raw owners only; never a primary hash cycle.
    return record, controls


def _profile(section: dict[str, Any], role: dict[str, Any]) -> dict[str, object]:
    selected = Selection.from_bytes(_json(section["selection"]))
    profiles = gateway._profiles(
        selected, {key: common._path(p) for key, p in section["roots"].items()}
    )
    return _object(_object(_object(profiles[role["capability"]])["profiles"])[role["profile_id"]])


def _compatible(record: dict[str, Any], primary: dict[str, Any]) -> list[ModelSpec]:
    launch = _load(
        pipeline._read(
            common._path(record["primary_launch"]["path"]), record["primary_launch"]["sha256"]
        )
    )
    proposal = _object(launch["proposal"])
    state = improver_handoff._configuration(
        common._path(proposal["path"]), _digest(proposal["sha256"]), fresh=False
    )
    generation, native = state["record"]["generation"], state["record"]["native"]
    tasks = state["tasks"].select(state["record"]["final_ids"])
    access = _profile(generation, generation["profile"])
    specs = [gateway._spec(p) for p in primary["profiles"]]
    plan = plain_comparison._plan(
        pipeline._read(
            common._path(record["comparison_plan"]["path"]), record["comparison_plan"]["sha256"]
        )
    )
    for row in plan["references"]:
        definition = _load(pipeline._read(common._path(row["definition"]), row["sha256"]))
        producer = cast(dict[str, Any], _object(definition["generation"]))
        recipe = _load(pipeline._read(common._path(producer["descriptor"])))
        config = _object(recipe["config"])
        original = TaskSet.from_bytes(pipeline._read(common._path(definition["tasks"])))
        if (
            original.to_bytes() != tasks.to_bytes()
            or config["instructions"] != ""
            or config["sampling"] != row["name"]
            or any(
                config[key] != generation["config"][key]
                for key in ("provider", "model", "max_output_tokens")
            )
            or _json(_profile(producer, cast(dict[str, Any], recipe["profile"]))) != _json(access)
            or _json(plain_comparison._instrument(cast(dict[str, Any], definition["native"])))
            != _json(plain_comparison._instrument(native))
            or _json(definition["stages"]) != _json(state["record"]["stages"])
        ):
            raise UnifiedLaunchError("plain references change the prospective panel or instrument")
        choices = common._model_specs(
            producer | {"profile": recipe["profile"]}, cast(dict[str, object], definition["native"])
        )
        specs.extend(spec for members in choices.values() for spec in members)
    return list(dict.fromkeys(specs))


def _workspace(directory: Path) -> bool:
    if baseline_state._absent(directory):
        return False
    from buddha.releases import _root

    _root(directory)
    if not {p.name for p in directory.iterdir()} <= {
        "running.lock",
        "review.json",
        "observations",
        "comparison.json",
    }:
        raise UnifiedLaunchError("operator workspace contains unexpected state")
    if not baseline_state._absent(directory / "observations"):
        _root(directory / "observations")
    return not baseline_state._absent(directory / "running.lock")


def _raw_review(
    record: dict[str, Any],
    digest: str,
    primary: dict[str, Any],
    raw: dict[str, Any],
    providers: set[str],
) -> dict[str, object] | None:
    path = common._path(record["directory"]) / "review.json"
    if baseline_state._absent(path):
        if any(row["state"] != "fresh" for row in raw["references"]):
            raise UnifiedLaunchError("original raw review is missing")
        return None
    if primary["state"] != "complete":
        raise UnifiedLaunchError("raw review precedes primary completion")
    review = gateway._review(_load(pipeline._read(path)))
    if (
        review.get("format") != "buddha.account-review.v2"
        or review["credential_context"] != digest
        or review["account_scope"] != primary["account_scope"]
        or set(_object(review["credential_fingerprints"])) != providers
    ):
        raise UnifiedLaunchError("raw review differs from the original combined context")
    for row in raw["references"]:
        if row["state"] != "fresh":
            owner = common._path(row["directory"]) / "owners/0/manifest.json"
            if _load(pipeline._read(owner))["review"] != review:
                raise UnifiedLaunchError("raw owner replaces its original account review")
    return review


def _check(path: Path, expected_sha256: str, *, owned_lock: bool = False) -> dict[str, Any]:
    record, controls = _configuration(path, expected_sha256)
    parameters = _parameters(record)
    funded = cast(dict[str, Any], unified_funding.check_funding(**parameters))
    primary = funded["primary"]
    if any(
        primary["bindings"].get(str(p)) != d for p, d in controls.items() if p != path.absolute()
    ):
        raise UnifiedLaunchError("primary work lacks reviewed combined sources or controls")
    directory = common._path(record["directory"])
    review_path = directory / "review.json"
    if not baseline_state._absent(review_path):
        controls[review_path] = file_hash(review_path)
    raw = cast(
        dict[str, Any],
        baseline_state.inspect_references(
            parameters["comparison_plan"],
            expected_plan_sha256=parameters["expected_plan_sha256"],
            input_bindings=controls,
        ),
    )
    if primary["state"] != "complete" and any(row["state"] != "fresh" for row in raw["references"]):
        raise UnifiedLaunchError("raw work precedes complete original primary work")
    rows = {row["name"]: row for row in raw["references"]}
    if set(rows) != set(_ORDER):
        raise UnifiedLaunchError("combined launch requires both declared plain references")
    if rows["regenerate"]["state"] != "complete" and rows["in-context"]["state"] != "fresh":
        raise UnifiedLaunchError("in-context work precedes its scheduled predecessor")
    specs = _compatible(record, primary)
    providers = {spec.provider for spec in specs}
    review = _raw_review(record, expected_sha256, primary, raw, providers)
    lock = _workspace(directory)
    stop = "execution_lock_present" if lock and not owned_lock else primary["stop_code"]
    if stop is None and raw["blocked_reasons"]:
        stop = raw["blocked_reasons"][0]
    if review is not None and raw["state"] != "complete" and stop is None:
        try:
            gateway._review(review, fresh=True)
        except ValueError:
            stop = "review_expired"
    phase = (
        "primary"
        if primary["state"] != "complete"
        else "plain-regenerate"
        if rows["regenerate"]["state"] != "complete"
        else "plain-in-context"
        if rows["in-context"]["state"] != "complete"
        else "comparison"
    )
    if not baseline_state._absent(directory / "comparison.json") and phase != "comparison":
        raise UnifiedLaunchError("comparison publication precedes its original complete inputs")
    repeated = baseline_state.inspect_references(
        parameters["comparison_plan"],
        expected_plan_sha256=parameters["expected_plan_sha256"],
        input_bindings=controls,
    )
    if repeated["state_sha256"] != raw["state_sha256"]:
        raise UnifiedLaunchError("reference state changed during combined checking")
    for p, d in controls.items():
        if file_hash(p, max_bytes=256 * 1024**2) != d:
            raise UnifiedLaunchError("combined control changed during checking")
    return {
        "format": "buddha.unified-launch-check.v1",
        "record": record,
        "controls": {str(p): d for p, d in controls.items()},
        "funding": funded,
        "primary": primary,
        "references": raw,
        "review": review,
        "profiles": [asdict(spec) for spec in specs],
        "phase": phase,
        "stop_code": stop,
        "directory": str(directory),
        "outer_lock_present": lock,
    }


def check_launch(path: Path, *, expected_sha256: str) -> dict[str, object]:
    """Read original inputs, funding and all owners; never enter keys or write."""
    try:
        return _load(_json(_check(path, expected_sha256)))
    except _ERRORS:
        raise UnifiedLaunchError("combined preflight failed; original records retained") from None


def _stable(first: dict[str, Any], second: dict[str, Any]) -> bool:
    return all(
        _json(first[key]) == _json(second[key])
        for key in ("controls", "funding", "references", "review", "phase", "stop_code")
    )


def _primary_keys(checked: dict[str, Any]) -> None:
    review = checked["primary"].get("review")
    if review is not None:
        expected = _object(review["credential_fingerprints"])
        actual = gateway.credential_fingerprints(
            list(expected), context=checked["record"]["primary_launch"]["sha256"]
        )
        if actual != expected:
            raise UnifiedLaunchError("credential differs from the original primary review")


def _publication(checked: dict[str, Any], digest: str) -> dict[str, object]:
    record = checked["record"]
    plan = plain_comparison._plan(
        pipeline._read(
            common._path(record["comparison_plan"]["path"]), record["comparison_plan"]["sha256"]
        )
    )
    primary_pin = file_hash(common._path(plan["trial"]) / "final/report.json")
    pins = {
        row["name"]: file_hash(common._path(row["directory"]) / "report.json")
        for row in plan["references"]
    }
    comparison = plain_comparison.compare_plain_references(
        common._path(record["comparison_plan"]["path"]),
        expected_plan_sha256=record["comparison_plan"]["sha256"],
        expected_assessment_report_sha256=primary_pin,
        expected_reference_report_sha256=pins,
    )
    destination = common._path(checked["directory"]) / "comparison.json"
    result = {
        "format": "buddha.unified-comparison-report.v1",
        "status": "complete",
        "launch_sha256": digest,
        "comparison_plan_sha256": record["comparison_plan"]["sha256"],
        "primary_report_sha256": primary_pin,
        "reference_report_sha256": pins,
        "comparison": comparison,
        "review_status": "pending_separate_review",
        "claim": _CLAIM,
        "publication_path": str(destination),
    }
    baseline._same_or_write(destination, _json(result))
    if pipeline._read(destination) != _json(result):
        raise UnifiedLaunchError("comparison publication changed during readback")
    return result


def _notice(text: str) -> None:
    common._notice("comparison", text)


def _controller_reason(result: dict[str, object], fallback: str) -> str:
    try:
        reason = result.get("reason")
        stages = result.get("stages")
        if reason is None and type(stages) is list and stages:
            last = _object(stages[-1])
            reason = last.get("reason")
            if reason is None:
                reason = _object(last.get("worker", {})).get("reason")
        return comparison_observation._code(reason)
    except (ValueError, TypeError):
        return fallback


def launch(
    path: Path,
    *,
    expected_sha256: str,
    live: bool = False,
    prompt_keys: bool = False,
    confirm_project_keys: bool = False,
    transport: RawHTTPTransport | None = None,
    notice: Callable[[str], None] = _notice,
    heartbeat_seconds: float = 10,
) -> dict[str, object]:
    """Run the fixed original order once; keep partials and original exceptions."""
    if (
        any(type(v) is not bool for v in (live, prompt_keys, confirm_project_keys))
        or not callable(notice)
        or type(heartbeat_seconds) not in (int, float)
        or not 0 < heartbeat_seconds <= 60
        or transport is not None
        and not isinstance(transport, RawHTTPTransport)
    ):
        raise UnifiedLaunchError("invalid combined launch options")
    record: dict[str, Any] | None = None
    phase, current = ["checking"], cast(list[Path | None], [None])
    observation_directory: Path | None = None

    def partial(reason: str, *, cancelled: bool = False) -> dict[str, object]:
        result: dict[str, object] = {
            "status": "incomplete",
            "phase": phase[0],
            "reason": reason,
            "observation_saved": False,
        }
        if record is not None and observation_directory is not None:
            try:
                common._emit(notice, "Saving an incomplete observation; no new provider requests.")
                with common._heartbeat(notice, ["recording"], current, heartbeat_seconds):
                    saved = comparison_observation.save_observation(
                        observation_directory / (uuid4().hex + ".json"),
                        **_parameters(record),
                        phase=phase[0],
                        reason=reason,
                        cancelled=cancelled,
                        input_bindings={
                            common._path(p): d for p, d in record["source_sha256"].items()
                        }
                        | {path.absolute(): expected_sha256},
                    )
                result.update(
                    observation_saved=True,
                    observation={key: saved[key] for key in ("path", "sha256")},
                )
                common._emit(notice, "Incomplete observation saved: " + str(saved["path"]))
            except (Exception, KeyboardInterrupt):
                common._emit(
                    notice, "Observation unavailable; original execution evidence retained."
                )
        else:
            common._emit(
                notice, "No observation armed: initial pinned configuration did not verify."
            )
        return result

    def inspect(*, owned: bool = False) -> dict[str, Any]:
        with common._heartbeat(notice, ["checking"], [None], heartbeat_seconds):
            return _check(path, expected_sha256, owned_lock=owned)

    try:
        record, _ = _configuration(path, expected_sha256)
        directory = common._path(record["directory"])
        _workspace(directory)
        directory.mkdir(exist_ok=True)
        observation_directory = directory / "observations"
        observation_directory.mkdir(exist_ok=True)
        common._emit(
            notice, "Checking the complete funded comparison and original owners before keys."
        )
        checked = inspect()
        if checked["stop_code"] is not None:
            return partial(checked["stop_code"])
        with baseline._exclusive(directory):
            checked = inspect(owned=True)
            phase[0] = checked["phase"]
            if checked["stop_code"] is not None:
                return partial(checked["stop_code"])
            if phase[0] == "comparison":
                with common._heartbeat(notice, phase, [None], heartbeat_seconds):
                    return _publication(checked, expected_sha256)
            if not live or not confirm_project_keys:
                raise UnifiedLaunchError(
                    "live execution and manual project confirmation are required"
                )
            timeout = checked["primary"]["timeout_seconds"]
            if transport is not None and (
                not transport.allow_paid or transport.timeout_seconds != timeout
            ):
                raise UnifiedLaunchError("transport differs from the original primary launch")
            specs = [gateway._spec(p) for p in checked["profiles"]]
            phase[0] = "keys"
            with credentials.key_environment(
                improver_launch._Profiles(specs),
                prompt_keys=prompt_keys,
                notice=lambda text: common._emit(notice, text),
            ):
                fingerprints = gateway.credential_fingerprints(
                    list(dict.fromkeys(spec.provider for spec in specs)), context=expected_sha256
                )
                if (
                    checked["review"] is not None
                    and checked["review"]["credential_fingerprints"] != fingerprints
                ):
                    raise UnifiedLaunchError("credential differs from the original raw review")
                _primary_keys(checked)
                phase[0] = "checking"
                repeated = inspect(owned=True)
                if not _stable(checked, repeated):
                    raise UnifiedLaunchError("original comparison changed during key entry")
                phase[0] = checked["phase"]
                active = transport or RawHTTPTransport(allow_paid=True, timeout_seconds=timeout)
                if checked["primary"]["state"] != "complete":
                    phase[0] = "primary"
                    result = improver_launch.launch(
                        common._path(record["primary_launch"]["path"]),
                        expected_sha256=record["primary_launch"]["sha256"],
                        live=True,
                        prompt_keys=False,
                        confirm_project_keys=True,
                        transport=active,
                        notice=notice,
                        heartbeat_seconds=heartbeat_seconds,
                    )
                    if result["status"] != "complete":
                        return partial(_controller_reason(result, "primary_incomplete"))
                checked = inspect(owned=True)
                if checked["primary"]["state"] != "complete" or checked["stop_code"] is not None:
                    return partial(checked["stop_code"] or "primary_incomplete")
                _primary_keys(checked)
                review = checked["review"]
                if review is None:
                    phase[0] = "plain-regenerate"
                    review = gateway._review(
                        {
                            "format": "buddha.account-review.v2",
                            "checked_on": datetime.now(UTC).date().isoformat(),
                            "credential_context": expected_sha256,
                            "credential_fingerprints": fingerprints,
                            "account_scope": checked["primary"]["account_scope"],
                        },
                        fresh=True,
                    )
                    pipeline._write(directory / "review.json", _json(review))
                checked = inspect(owned=True)
                plan = plain_comparison._plan(
                    pipeline._read(
                        common._path(record["comparison_plan"]["path"]),
                        record["comparison_plan"]["sha256"],
                    )
                )
                for name in _ORDER:
                    checked = inspect(owned=True)
                    if checked["stop_code"] is not None:
                        return partial(checked["stop_code"])
                    row = next(
                        row for row in checked["references"]["references"] if row["name"] == name
                    )
                    if row["state"] == "complete":
                        continue
                    phase[0] = "plain-" + name
                    current[0] = common._path(record["reference_grant"]["path"])
                    declared = next(row for row in plan["references"] if row["name"] == name)
                    root = common._path(row["directory"])
                    with common._heartbeat(notice, phase, current, heartbeat_seconds):
                        if row["state"] == "fresh":
                            from buddha.authorization import Authorization

                            controls = {common._path(p): d for p, d in checked["controls"].items()}
                            baseline.prepare_baseline(
                                root,
                                descriptor=common._path(declared["definition"]),
                                authorization=Authorization(
                                    common._path(record["reference_grant"]["path"])
                                ),
                                review=review,
                                input_files=list(controls),
                                expected_input_hashes=controls,
                            )
                        result = baseline.run_baseline(root, transport=active)
                    if result["status"] != "complete":
                        return partial(_controller_reason(result, "reference_incomplete"))
                phase[0] = "comparison"
                checked = inspect(owned=True)
                if checked["stop_code"] is not None or checked["references"]["state"] != "complete":
                    return partial(checked["stop_code"] or "reference_incomplete")
                with common._heartbeat(notice, phase, [None], heartbeat_seconds):
                    return _publication(checked, expected_sha256)
    except KeyboardInterrupt:
        partial("cancelled", cancelled=True)
        raise
    except Exception as error:
        partial(error.code if isinstance(error, credentials.KeyInputError) else "launch_stopped")
        raise
