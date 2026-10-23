"""One approved frozen-request capacity observation; no generated-source execution."""

import hashlib
import math
from collections.abc import Callable
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, cast

from buddha import credentials, gateway, source_capacity
from buddha import launch_common as common
from buddha import native_pipeline as pipeline
from buddha.authorization import _TERM_FIELDS, Authorization
from buddha.gateway_history import read_gateway_history
from buddha.ledger import BudgetExceeded
from buddha.provider import BoundBreach, PendingOperation, ProviderUncertain
from buddha.releases import (
    ReleaseError,
    _digest,
    _json,
    _load,
    _object,
    _root,
    _text,
    file_hash,
    verify_selection,
)
from buddha.wire import RawEnvelope, _integer

FORMAT = "buddha.source-capacity-launch.v1"
SEAL = "buddha.source-capacity-stage.v1"
ANCHOR = "source capacity completed: "


class CapacityLaunchError(ReleaseError):
    """A fixed launch-boundary failure, never raw exception or credential text."""


def _sources() -> list[Path]:
    # One small diagnostic freezes the installed package, rather than adding a
    # second import-closure registry. Selected release inputs remain separate.
    package = Path(__file__).absolute().parent
    return [
        *sorted(package.rglob("*.py")),
        package.parent / "docs/conformance/src02-capacity-run.py",
    ]


def _check(path: Path, expected_sha256: str, *, locked: bool = False) -> dict[str, Any]:
    if not isinstance(path, Path):
        raise CapacityLaunchError("an explicit launch path is required")
    path = common._path(str(path.absolute()))
    digest = _digest(expected_sha256)
    raw = pipeline._read(path, digest)
    record = _object(
        _load(raw),
        {
            "format",
            "directory",
            "authorization_path",
            "requested_terms",
            "selection",
            "roots",
            "profile_id",
            "request_path",
            "protocol_path",
            "source_sha256",
            "account_scope",
            "timeout_seconds",
        },
    )
    if record["format"] != FORMAT:
        raise CapacityLaunchError("unsupported capacity launch")
    directory = common._path(record["directory"])
    _root(directory.parent)
    if not locked and (
        (directory / "running.lock").exists() or (directory / "running.lock").is_symlink()
    ):
        raise CapacityLaunchError("capacity has a retained writer lock")
    authority_path = common._path(record["authorization_path"])
    funding, funding_raw = common._snapshot(authority_path)
    terms = _object(record["requested_terms"], set(_TERM_FIELDS))
    if {key: _object(funding["config"])[key] for key in _TERM_FIELDS} != terms:
        raise CapacityLaunchError("capacity authorization differs from its approved terms")
    if _integer(terms["max_calls"], 1, 1) != 1 or terms["currency"] != "USD":
        raise CapacityLaunchError("capacity needs a separate one-attempt USD allocation")
    _integer(terms["budget_microusd"], 1)
    _text(record["account_scope"])
    timeout = record["timeout_seconds"]
    if (
        not isinstance(timeout, (int, float))
        or isinstance(timeout, bool)
        or not math.isfinite(timeout)
        or not 1 <= timeout <= 600
    ):
        raise CapacityLaunchError("invalid capacity timeout")
    selection, roots = pipeline._component(
        record | {name: terms[name] for name in ("budget_microusd", "max_calls")}
    )
    verify_selection(selection, roots, expected_sha256=selection.fingerprint())
    request_path, protocol_path = (
        common._path(record["request_path"]),
        common._path(record["protocol_path"]),
    )
    pins = _object(record["source_sha256"])
    required = {*_sources(), request_path, protocol_path}
    if set(pins) != {str(item) for item in required} or len(pins) > 1022:
        raise CapacityLaunchError("capacity source/input population differs")
    bindings = {str(common._path(name)): _digest(value) for name, value in pins.items()}
    for name, expected_hash in bindings.items():
        if file_hash(Path(name)) != expected_hash:
            raise CapacityLaunchError("capacity source/input changed")
    protocol = _load(pipeline._read(protocol_path, bindings[str(protocol_path)]))
    if protocol.get("format") != "buddha.source-request-capacity-protocol.v1":
        raise CapacityLaunchError("unsupported capacity protocol")
    request, rule, custody = (
        _object(protocol[name]) for name in ("request", "decision_rule", "custody")
    )
    body = pipeline._read(request_path, bindings[str(request_path)])
    body_sha = hashlib.sha256(body).hexdigest()
    cap = _integer(request["max_completion_tokens"], 1)
    if (
        request["capability"] != "openai.chat-completions.v1"
        or (request["provider"], request["host"], request["path"])
        != gateway.CAPABILITIES["openai.chat-completions.v1"]
        or body_sha != _digest(request["sha256"])
        or len(body) != _integer(request["bytes"], 1)
        or _integer(request["logical_target_count"], 1, 1) != 1
        or _integer(request["attempt_count"], 1, 1) != 1
        or _integer(request["automatic_retries"], 0, 0) != 0
        or _integer(rule["selected_output_cap"], 1) != cap
    ):
        raise CapacityLaunchError("frozen capacity request differs")
    decoded = _load(body)
    if any(
        decoded.get(key) != request[key]
        for key in ("model", "max_completion_tokens", "service_tier", "reasoning_effort")
    ):
        raise CapacityLaunchError("capacity model, cap or tier differs")
    profile_id = _text(record["profile_id"])
    profiles = gateway._profiles(selection, roots)
    profile = _object(_object(_object(profiles[request["capability"]])["profiles"])[profile_id])
    spec = gateway._spec(profile["spec"])
    context = _integer(rule["model_context_tokens"], 1)
    context_margin = _integer(rule["minimum_context_slack_tokens"], 1)
    output_margin = _integer(rule["minimum_observed_output_slack_tokens"], 1)
    if (
        spec.provider != "openai"
        or spec.model != request["model"]
        or spec.input_token_ceiling != context
        or cap > spec.max_output_tokens
        or context_margin + cap > context
        or output_margin > cap
        or request["service_tier"] != "default"
        or request["reasoning_effort"] != "low"
    ):
        raise CapacityLaunchError("capacity profile or prospective margins differ")
    parent = _object(custody["prospective_parent_source"])
    parent_sha = _digest(parent["sha256"])
    agent = _object(_object(selection.to_record()["components"])["agent"])
    if (
        selection.agent_sha256 != custody["prospective_parent_agent_sha256"]
        or agent != {"candidate.py": parent_sha}
        or custody["historical_measured_candidate_id"] == selection.agent_sha256
    ):
        raise CapacityLaunchError("capacity parent identity differs or erases historical custody")
    protected = [path, authority_path, *required, *roots.values()]
    if any(
        item == directory
        or item.is_relative_to(directory)
        or (item.is_dir() and directory.is_relative_to(item))
        for item in protected
    ):
        raise CapacityLaunchError("capacity output overlaps protected input")
    call = gateway.GatewayCall(
        request["capability"], profile_id, "source-capacity/" + digest, 0, body
    )
    expected = {
        key: getattr(call, key) for key in ("capability", "profile_id", "logical_id", "attempt")
    } | {"body_sha256": body_sha}
    source_capacity.guard_call(call, expected)
    spec = gateway._request_spec(call, profile)
    gateway._selected_headers(call, profile)
    bindings[str(path)] = digest
    review_path, owner = directory / "review.json", directory / "owner"
    run_id = "source-capacity-" + digest
    state, review, stop, completed_operation = "fresh", None, None, False
    runs = cast(list[dict[str, Any]], funding["auth_runs"])
    if directory.exists():
        _root(directory)
        manifest = gateway._read_manifest(owner)
        review_raw = pipeline._read(review_path)
        review = gateway._review(_load(review_raw))
        if (
            review.get("format") != "buddha.account-review.v2"
            or review.get("credential_context") != digest
            or review["account_scope"] != record["account_scope"]
        ):
            raise CapacityLaunchError("original capacity review differs")
        bindings[str(review_path)] = hashlib.sha256(review_raw).hexdigest()
        inputs = {
            row["path"]: row["sha256"]
            for row in cast(list[dict[str, str]], _object(manifest["invocation"])["inputs"])
        }
        if (
            manifest["run_id"] != run_id
            or manifest["selection"] != selection.to_record()
            or manifest["roots"] != {key: str(value) for key, value in roots.items()}
            or manifest["profiles"] != profiles
            or manifest["review"] != review
            or manifest["authorization_path"] != str(authority_path)
            or manifest["settings"] != {"budget_microusd": terms["budget_microusd"], "max_calls": 1}
            or inputs != bindings
        ):
            raise CapacityLaunchError("original capacity owner differs")
        manifest_sha = gateway._sha(manifest)
        history = read_gateway_history(
            owner,
            manifest_sha256=manifest_sha,
            ledger_sha256=file_hash(owner / "operations.sqlite3"),
        )
        if (
            len(runs) != 1
            or runs[0]["run_id"] != run_id
            or runs[0]["directory"] != str(owner)
            or runs[0]["manifest_sha256"] != manifest_sha
            or runs[0]["runtime_sha256"] != gateway.execution_identity(owner, manifest)
        ):
            raise CapacityLaunchError("capacity owner lacks its original authority binding")
        operations = history.operations
        shared = cast(list[dict[str, Any]], funding["auth_operations"])
        if len(operations) > 1 or len(shared) != len(operations):
            raise CapacityLaunchError("capacity operation population differs")
        if operations:
            operation = operations[0]
            expected_operation = gateway._sha(
                ["buddha.gateway-attempt.v1", run_id, manifest["invocation"], call.logical_id, 0]
            )
            expected_request = gateway._sha(
                [
                    "buddha.gateway-request.v1",
                    manifest["execution_sha256"],
                    manifest["selection_sha256"],
                    gateway._sha(profile),
                    call.to_record(),
                ]
            )
            if (
                operation.operation_id != expected_operation
                or operation.request_sha256 != expected_request
                or operation.reserve_microusd != spec.reserve_microusd()
                or shared[0]["operation_id"] != operation.operation_id
                or shared[0]["run_id"] != run_id
                or shared[0]["status"] != operation.status
                or shared[0]["request_sha256"] != operation.request_sha256
                or shared[0]["reserve_microusd"] != operation.reserve_microusd
                or shared[0]["actual_microusd"] != operation.actual_microusd
                or shared[0]["provider_request_id"] != operation.provider_request_id
                or shared[0]["response_json"] != operation.receipt_json
            ):
                raise CapacityLaunchError("capacity local/shared accounting differs")
            receipt = operation.receipt
            if receipt is not None and receipt["request"] != call.to_record():
                raise CapacityLaunchError("capacity original raw request differs")
            if operation.status in {"dispatched", "unknown"}:
                stop = "provider_unknown"
            completed_operation = operation.status == "completed"
        inactive = {
            row["run_id"]: row["reason"]
            for row in cast(list[dict[str, Any]], funding["auth_deactivations"])
        }
        seal = directory / "completed/0.json"
        if seal.exists():
            if inactive.get(run_id) != ANCHOR + file_hash(seal) or not completed_operation:
                raise CapacityLaunchError("capacity completion lacks its original anchor")
            state = "complete"
        elif run_id in inactive or (directory / "report.json").exists():
            raise CapacityLaunchError("inactive or published capacity lacks a valid completion")
        else:
            state = "existing"
    elif runs or funding["auth_operations"] or funding["auth_deactivations"]:
        raise CapacityLaunchError("capacity allocation already belongs to another owner")
    if state == "fresh" and cast(int, terms["budget_microusd"]) < spec.cost_microusd(context, cap):
        stop = "budget"
    common._finish_snapshot(authority_path, funding_raw, error=CapacityLaunchError)
    for name, expected_hash in bindings.items():
        if file_hash(Path(name)) != expected_hash:
            raise CapacityLaunchError("capacity input changed during checking")
    return dict(
        record=record,
        path=path,
        digest=digest,
        directory=directory,
        owner=owner,
        review_path=review_path,
        review=review,
        terms=terms,
        funding_raw=funding_raw,
        authority_path=authority_path,
        bindings=bindings,
        selection=selection,
        roots=roots,
        profiles=profiles,
        spec=spec,
        call=call,
        expected=expected,
        parent_sha=parent_sha,
        context=context,
        cap=cap,
        context_margin=context_margin,
        output_margin=output_margin,
        state=state,
        stop=stop,
        funding=funding,
        completed_operation=completed_operation,
        run_id=run_id,
        timeout=timeout,
    )


def check_launch(path: Path, *, expected_sha256: str) -> dict[str, object]:
    """Check the exact diagnostic and funding with data-only snapshots; no writes."""
    try:
        plan = _check(path, expected_sha256)
        return {
            "format": "buddha.source-capacity-check.v1",
            "state": plan["state"],
            "stop_code": plan["stop"],
            "request_sha256": plan["expected"]["body_sha256"],
            "directory": str(plan["directory"]),
            "source_pin_count": len(plan["bindings"]),
        }
    except (ValueError, TypeError, KeyError, OSError, RecursionError, OverflowError):
        raise CapacityLaunchError(
            "capacity launch inputs or original evidence are invalid"
        ) from None


class _Profiles:
    def __init__(self, spec: Any) -> None:
        self.spec = spec

    def profiles(self) -> tuple[Any, ...]:
        return (self.spec,)


def run_launch(
    path: Path,
    *,
    expected_sha256: str,
    live: bool = False,
    prompt_keys: bool = False,
    confirm_project_key: bool = False,
    transport: gateway.RawHTTPTransport | None = None,
    notice: Callable[[str], None] = print,
) -> dict[str, object]:
    """Run/replay this one original target; never allocate funds or adopt source."""
    phase = ["checking"]
    observed_authority: list[Path | None] = [None]
    try:
        if any(
            type(value) is not bool for value in (live, prompt_keys, confirm_project_key)
        ) or not callable(notice):
            raise CapacityLaunchError("invalid capacity launch mode")
        plan = _check(path, expected_sha256)
        if plan["stop"]:
            return {
                "format": "buddha.source-capacity-report.v1",
                "status": "partial",
                "stage": "request" if plan["stop"] == "provider_unknown" else "funding",
                "reason": plan["stop"],
                "owner": str(plan["owner"]) if plan["state"] != "fresh" else None,
                "recorded_accounting": plan["funding"]["totals"],
            }
        cached = plan["completed_operation"]
        if not cached and not live:
            return check_launch(path, expected_sha256=expected_sha256) | {"status": "ready"}
        if not cached and not confirm_project_key:
            raise CapacityLaunchError("manual account confirmation is required")
        if transport is not None and (
            transport.timeout_seconds != plan["timeout"] or transport.allow_paid != (not cached)
        ):
            raise CapacityLaunchError("capacity transport differs from the frozen request")

        def execute() -> dict[str, object]:
            authority = Authorization(plan["authority_path"])
            gw = gateway.Gateway(
                plan["owner"],
                transport=transport
                or gateway.RawHTTPTransport(allow_paid=not cached, timeout_seconds=plan["timeout"]),
            )

            def measurement(envelope: RawEnvelope) -> dict[str, object]:
                return source_capacity.assess_reply(
                    envelope,
                    parent_source_sha256=plan["parent_sha"],
                    model=plan["spec"].model,
                    context_tokens=plan["context"],
                    output_cap_tokens=plan["cap"],
                    min_context_slack=plan["context_margin"],
                    min_output_slack=plan["output_margin"],
                )

            def cached_reply() -> RawEnvelope:
                operation = gw.ledger.get(gw.operation_id(plan["call"]))
                if (
                    operation is None
                    or operation.status != "completed"
                    or gw.ledger.totals()["operation_count"] != 1
                ):
                    raise CapacityLaunchError(
                        "capacity replay requires exactly its completed original operation"
                    )
                return source_capacity.execute_guarded(gw, plan["call"], plan["expected"])

            def run(attempt: Path) -> dict[str, object]:
                attempt.mkdir(parents=True, exist_ok=False)
                phase[0] = "request"
                reply = (
                    cached_reply()
                    if cached
                    else source_capacity.execute_guarded(gw, plan["call"], plan["expected"])
                )
                phase[0] = "assessment"
                envelope_raw = _json(reply.to_record()) + b"\n"
                pipeline._write(attempt / "raw-envelope.json", envelope_raw)
                report = {
                    "format": "buddha.source-capacity-attempt.v1",
                    "status": "complete",
                    "measurement": measurement(reply),
                    "operation_id": gw.operation_id(plan["call"]),
                    "request_sha256": plan["expected"]["body_sha256"],
                    "owner_sha256": gw.manifest_sha256,
                    "artifacts": {"raw-envelope.json": hashlib.sha256(envelope_raw).hexdigest()},
                }
                pipeline._write(attempt / "report.json", _json(report) + b"\n")
                return report

            def validate(attempt: Path, report: dict[str, object]) -> dict[str, Path]:
                reply = cached_reply()
                envelope_raw = _json(reply.to_record()) + b"\n"
                expected = {
                    "format": "buddha.source-capacity-attempt.v1",
                    "status": "complete",
                    "measurement": measurement(reply),
                    "operation_id": gw.operation_id(plan["call"]),
                    "request_sha256": plan["expected"]["body_sha256"],
                    "owner_sha256": gw.manifest_sha256,
                    "artifacts": {"raw-envelope.json": hashlib.sha256(envelope_raw).hexdigest()},
                }
                if (
                    report != expected
                    or pipeline._read(attempt / "raw-envelope.json") != envelope_raw
                ):
                    raise CapacityLaunchError(
                        "capacity attempt differs from its original raw receipt"
                    )
                return {}

            report, _, _, sealed, _ = pipeline.execute_stage(
                plan["directory"],
                0,
                gw,
                authority,
                run=run,
                validate=validate,
                seal_format=SEAL,
                anchor_prefix=ANCHOR,
            )
            if sealed is None:
                raise CapacityLaunchError("capacity execution lacks a completed stage")
            assessment = _object(report["measurement"])
            result = {
                "format": "buddha.source-capacity-report.v1",
                "status": assessment["measurement_status"],
                "stage": "assessment",
                "reason": assessment["reason"],
                "measurement": assessment,
                "owner": str(plan["owner"]),
                "seal_sha256": file_hash(sealed),
                "authorization": authority.summary(),
                "claim": (
                    "one prospective request observation; no measured-parent, "
                    "source competence or improvement claim"
                ),
            }
            return pipeline.publish_complete(
                plan["directory"] / "report.json", result, authority, {plan["run_id"]}
            )

        def partial(reason: str) -> dict[str, object]:
            result: dict[str, object] = {
                "format": "buddha.source-capacity-report.v1",
                "status": "partial",
                "reason": reason,
                "stage": phase[0],
                "owner": str(plan["owner"]),
                "authorization": Authorization(plan["authority_path"]).summary(),
            }
            observations = plan["directory"] / "observations"
            if observations.is_dir():
                number = 0
                while (observations / f"{number}.json").exists():
                    number += 1
                pipeline._write(observations / f"{number}.json", _json(result))
            return result

        def recheck_locked() -> None:
            common._finish_snapshot(plan["authority_path"], plan["funding_raw"])
            for name, digest in plan["bindings"].items():
                if file_hash(Path(name)) != digest:
                    raise CapacityLaunchError("capacity inputs changed before original execution")
            if plan["state"] != "fresh":
                latest = _check(path, expected_sha256, locked=True)
                if latest["state"] != plan["state"] or latest["bindings"] != plan["bindings"]:
                    raise CapacityLaunchError("capacity owner changed before original execution")

        def execute_observed() -> dict[str, object]:
            try:
                return execute()
            except (ProviderUncertain, PendingOperation, BoundBreach):
                return partial("provider_unknown")
            except BudgetExceeded:
                return partial("budget")
            except (KeyboardInterrupt, SystemExit):
                partial("cancelled")
                raise
            except (ValueError, TypeError, KeyError, OSError, RecursionError, OverflowError):
                if plan["state"] == "complete":
                    raise
                return partial("execution_stopped")

        observed_authority[0] = plan["authority_path"]
        with common._heartbeat(
            notice, phase, observed_authority, 10, thread_name="capacity-progress"
        ):
            if cached:
                with pipeline._exclusive(plan["directory"]):
                    recheck_locked()
                    return execute_observed()
            phase[0] = "keys"
            with credentials.key_environment(
                _Profiles(plan["spec"]), prompt_keys=prompt_keys, notice=notice
            ):
                fingerprints = gateway.credential_fingerprints(["openai"], context=plan["digest"])
                if (
                    plan["review"] is not None
                    and plan["review"]["credential_fingerprints"] != fingerprints
                ):
                    raise CapacityLaunchError(
                        "capacity credential differs from its original review"
                    )
                repeated = _check(path, expected_sha256)
                if (
                    repeated["funding_raw"] != plan["funding_raw"]
                    or repeated["state"] != plan["state"]
                    or repeated["bindings"] != plan["bindings"]
                ):
                    raise CapacityLaunchError("capacity state changed during key entry")
                if plan["state"] == "fresh":
                    plan["directory"].mkdir(exist_ok=False)
                with pipeline._exclusive(plan["directory"]):
                    recheck_locked()
                    if plan["state"] == "fresh":
                        for name in ("attempts", "completed", "observations"):
                            (plan["directory"] / name).mkdir()
                        review = gateway._review(
                            {
                                "format": "buddha.account-review.v2",
                                "checked_on": datetime.now(UTC).date().isoformat(),
                                "credential_context": plan["digest"],
                                "credential_fingerprints": fingerprints,
                                "account_scope": plan["record"]["account_scope"],
                            },
                            fresh=True,
                        )
                        review_raw = _json(review)
                        pipeline._write(plan["review_path"], review_raw)
                        plan["bindings"][str(plan["review_path"])] = hashlib.sha256(
                            review_raw
                        ).hexdigest()
                        phase[0] = "preparing"
                        gateway.prepare_gateway(
                            plan["owner"],
                            selection=plan["selection"],
                            roots=plan["roots"],
                            authorization=Authorization(plan["authority_path"]),
                            budget_microusd=plan["terms"]["budget_microusd"],
                            max_calls=1,
                            review=review,
                            run_id=plan["run_id"],
                            input_files=[Path(name) for name in plan["bindings"]],
                            expected_input_hashes={
                                Path(name): value for name, value in plan["bindings"].items()
                            },
                        )
                    return execute_observed()
    except (ValueError, TypeError, KeyError, OSError, RecursionError, OverflowError):
        raise CapacityLaunchError(
            "capacity launch inputs or original execution evidence are invalid"
        ) from None
