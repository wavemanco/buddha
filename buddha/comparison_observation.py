"""Write-once incomplete comparison diagnostics; never execution or completion."""

import re
from collections.abc import Callable
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, cast

from buddha import baseline_state, improver_launch, plain_comparison
from buddha import launch_common as common
from buddha import native_pipeline as pipeline
from buddha.doctor import _Busy, _Unsupported
from buddha.native_evidence import _sha
from buddha.provider import _integer
from buddha.releases import ReleaseError, _digest, _json, _load, _object, _text, file_hash
from buddha.search_evidence import _overlap
from buddha.unified_funding import reference_scope

_PHASES = ("search", "validation", "final", "shared_plain_references")
_AMOUNTS = ("spent_microusd", "reserved_microusd", "committed_microusd", "operation_count")
_STOPS = {"checking", "keys", "primary", "plain-regenerate", "plain-in-context", "comparison"}
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
_CLAIM = "Incomplete diagnostic observation; no execution approval or complete comparison claim."


class ComparisonObservationError(ReleaseError):
    """Observation metadata, output protection or durable publication failed."""


def _code(value: object) -> str:
    text = _text(value)
    if re.fullmatch(r"[a-z][a-z0-9_]{0,63}", text, re.ASCII) is None:
        raise ComparisonObservationError("stop reasons require bounded machine codes")
    return text


def _reference(value: object) -> dict[str, object]:
    row = _object(value, {"path", "sha256"})
    common._path(row["path"])
    _digest(row["sha256"])
    return row


def _grant(value: object) -> dict[str, object]:
    row = _object(value, {"path", "id", "terms_sha256", "scope", "budget_microusd", "max_calls"})
    common._path(row["path"])
    _digest(row["terms_sha256"])
    if (
        len(_text(row["id"]).encode("utf-8")) > 128
        or len(_text(row["scope"]).encode("utf-8")) > 4096
    ):
        raise ComparisonObservationError("grant identity exceeds its boundary")
    for key in ("budget_microusd", "max_calls"):
        _integer(row[key], key)
    return row


def _arm(
    primary: Path,
    launch_digest: str,
    plan: Path,
    plan_digest: str,
    reference_grant: dict[str, object],
    total_limits: dict[str, object],
    input_bindings: dict[Path, str] | None,
) -> tuple[dict[str, Any], set[Path]]:
    if not isinstance(primary, Path) or not isinstance(plan, Path):
        raise ComparisonObservationError("observation inputs need explicit Paths")
    primary, plan = common._path(str(primary.absolute())), common._path(str(plan.absolute()))
    launch_digest, plan_digest = _digest(launch_digest), _digest(plan_digest)
    roots = set(common._receipt_roots(primary, launch_digest))
    launch = _load(pipeline._read(primary, launch_digest))
    if launch["format"] != "buddha.improver-launch.v1":
        raise ComparisonObservationError("observation needs the pinned original primary launch")
    approval_ref = _reference(launch["approval"])
    approval = _load(pipeline._read(common._path(approval_ref["path"]), approval_ref["sha256"]))
    selected = plain_comparison._plan(pipeline._read(plan, plan_digest))
    if (
        approval["format"] != "buddha.improver-approval.v1"
        or selected["trial"] != launch["directory"]
        or approval["directory"] != launch["directory"]
        or selected["definition_sha256"] != approval["definition_sha256"]
    ):
        raise ComparisonObservationError("observation replaces its pinned experiment")
    grants = {
        name: _grant(row)
        for name, row in _object(approval["authorizations"], set(_PHASES[:3])).items()
    }
    grants["shared_plain_references"] = _grant(reference_grant)
    if reference_grant["scope"] != reference_scope(plan_digest):
        raise ComparisonObservationError("reference funding is not scoped to the pinned plan")
    limits = _object(total_limits, {"budget_microusd", "max_calls"})
    for key, value in limits.items():
        _integer(value, key)
    controls: dict[str, str] = {}
    if input_bindings is not None:
        if type(input_bindings) is not dict or len(input_bindings) > 1024:
            raise ComparisonObservationError("extra controls need a bounded Path mapping")
        for source, digest in input_bindings.items():
            if not isinstance(source, Path):
                raise ComparisonObservationError("extra controls need explicit Paths")
            controls[str(common._path(str(source.absolute())))] = _digest(digest)
    roots.update((primary, plan, *(common._path(p) for p in controls)))
    roots.update(common._path(p) for p in selected["consumer_sources"])
    roots.update(common._path(row["path"]) for row in grants.values())
    for row in selected["references"]:
        if row["authorization"] != reference_grant["path"]:
            raise ComparisonObservationError("reference modes do not share the declared grant")
        definition_path = common._path(row["definition"])
        definition = _object(
            _load(pipeline._read(definition_path, row["sha256"])),
            {"format", "tasks", "generation", "native", "stages"},
        )
        if definition["format"] != "buddha.native-baseline.v1":
            raise ComparisonObservationError("unsupported reference observation input")
        roots.update(
            (definition_path, common._path(row["directory"]), common._path(definition["tasks"]))
        )
        roots.add(common._path(_object(definition["generation"])["descriptor"]))
        for role in ("generation", "native"):
            roots.update(
                common._path(p) for p in _object(_object(definition[role])["roots"]).values()
            )
    writer = Path(__file__).absolute()
    roots.add(writer)
    roots.update(p.parent for p in tuple(roots) if p.suffix.lower() == ".py")
    inputs = {
        "primary_launch": {"path": str(primary), "sha256": launch_digest},
        "comparison_plan": {"path": str(plan), "sha256": plan_digest},
        "writer": {"path": str(writer), "sha256": file_hash(writer)},
        "grants": grants,
        "total_limits": limits,
        "input_bindings": controls,
    }
    return cast(dict[str, Any], _load(_json(inputs))), roots


def _unavailable(reason: str) -> dict[str, object]:
    return {"status": "unavailable", "reason": reason, "totals": None}


def _funding(grants: dict[str, Any]) -> tuple[dict[str, Any], dict[str, bytes]]:
    rows, snapshots = {}, {}
    if any(len({row[key] for row in grants.values()}) != 4 for key in ("path", "id")):
        return {name: _unavailable("ambiguous_grants") for name in _PHASES}, {}
    for name, expected in grants.items():
        try:
            observed, raw = common._snapshot(common._path(expected["path"]))
            config = _object(observed["config"])
            actual = {
                "path": expected["path"],
                "id": config["authorization_id"],
                **{
                    key: config[key]
                    for key in ("terms_sha256", "scope", "budget_microusd", "max_calls")
                },
            }
            if _json(expected) != _json(actual):
                rows[name] = _unavailable("funding_mismatch")
                continue
            rows[name] = {"status": "observed", "reason": None, "totals": observed["totals"]}
            snapshots[name] = raw
        except _ERRORS:
            rows[name] = _unavailable("funding_unavailable")
    return rows, snapshots


def _financial(rows: dict[str, Any]) -> dict[str, object]:
    known = [row["totals"] for row in rows.values() if row["status"] == "observed"]
    subtotal = {key: sum(row[key] for row in known) for key in _AMOUNTS} if known else None
    return {
        "status": "observed" if len(known) == 4 else "partial" if known else "unavailable",
        "phases": rows,
        "known_subtotal": subtotal,
        "totals": subtotal if len(known) == 4 else None,
    }


def _observe(
    call: Callable[[], dict[str, object]], keys: tuple[str, ...], reason: str
) -> dict[str, object]:
    try:
        value = call()
        return {"status": "observed", "reason": None, "value": {key: value[key] for key in keys}}
    except _ERRORS:
        return {"status": "unavailable", "reason": reason, "value": None}


def _record(value: object) -> dict[str, Any]:
    record = _object(
        value,
        {
            "format",
            "status",
            "recorded_at",
            "stop",
            "inputs",
            "funding",
            "primary",
            "references",
            "claim",
        },
    )
    if (
        record["format"] != "buddha.comparison-observation.v1"
        or record["status"] != "incomplete"
        or record["claim"] != _CLAIM
    ):
        raise ComparisonObservationError("observation cannot claim complete execution")
    when = datetime.fromisoformat(_text(record["recorded_at"]))
    if when.tzinfo != UTC or when.isoformat(timespec="seconds") != record["recorded_at"]:
        raise ComparisonObservationError("observation needs its canonical UTC recording time")
    stop = _object(record["stop"], {"phase", "reason", "cancelled", "source"})
    if (
        stop["phase"] not in _STOPS
        or type(stop["cancelled"]) is not bool
        or stop["source"] != "launcher_reported"
    ):
        raise ComparisonObservationError("invalid launcher stop metadata")
    _code(stop["reason"])
    inputs = _object(
        record["inputs"],
        {"primary_launch", "comparison_plan", "writer", "grants", "total_limits", "input_bindings"},
    )
    for name in ("primary_launch", "comparison_plan", "writer"):
        _reference(inputs[name])
    grants = {name: _grant(row) for name, row in _object(inputs["grants"], set(_PHASES)).items()}
    for key, amount in _object(inputs["total_limits"], {"budget_microusd", "max_calls"}).items():
        _integer(amount, key)
    for path, digest in _object(inputs["input_bindings"]).items():
        common._path(path)
        _digest(digest)
    financial = _object(record["funding"], {"status", "phases", "known_subtotal", "totals"})
    rows = _object(financial["phases"], set(_PHASES))
    for row in rows.values():
        item = _object(row, {"status", "reason", "totals"})
        if item["status"] == "observed":
            amounts = _object(item["totals"], set(_AMOUNTS))
            if (
                item["reason"] is not None
                or any(type(v) is not int or v < 0 for v in amounts.values())
                or cast(int, amounts["spent_microusd"]) + cast(int, amounts["reserved_microusd"])
                != amounts["committed_microusd"]
            ):
                raise ComparisonObservationError("invalid observed financial totals")
        elif (
            item["status"] != "unavailable"
            or item["totals"] is not None
            or item["reason"]
            not in {
                "ambiguous_grants",
                "funding_mismatch",
                "funding_unavailable",
                "funding_changed",
            }
        ):
            raise ComparisonObservationError("unknown costs must remain unavailable")
    if _json(financial) != _json(_financial(rows)):
        raise ComparisonObservationError("financial totals must count known grants exactly once")
    if (
        any(len({row[key] for row in grants.values()}) != 4 for key in ("path", "id"))
        and financial["known_subtotal"] is not None
    ):
        raise ComparisonObservationError("ambiguous original grants cannot form a subtotal")
    for name, keys in (
        ("primary", {"state", "phase", "stop_code", "next_position", "state_sha256"}),
        ("references", {"state", "ready", "blocked_reasons", "references", "state_sha256"}),
    ):
        observed = _object(record[name], {"status", "reason", "value"})
        if observed["status"] == "observed":
            summary = _object(observed["value"], keys)
            if observed["reason"] is not None:
                raise ComparisonObservationError("observed state cannot have an unavailable reason")
            _digest(summary["state_sha256"])
            if summary["state"] not in {"fresh", "prepared", "complete"}:
                raise ComparisonObservationError("invalid observed state")
            if name == "primary":
                if summary["phase"] not in {"search", "freeze", "final", "complete"}:
                    raise ComparisonObservationError("invalid observed primary phase")
                if summary["stop_code"] is not None:
                    _code(summary["stop_code"])
                _object(summary["next_position"])
            else:
                if (
                    type(summary["ready"]) is not bool
                    or type(summary["blocked_reasons"]) is not list
                ):
                    raise ComparisonObservationError("invalid reference readiness")
                for blocker in summary["blocked_reasons"]:
                    _code(blocker)
                population = summary["references"]
                if type(population) is not list or not 1 <= len(population) <= 2:
                    raise ComparisonObservationError("invalid observed reference population")
                names = set()
                for value in population:
                    row = _object(
                        value,
                        {
                            "name",
                            "directory",
                            "state",
                            "next_stage",
                            "completed_stages",
                            "owner_count",
                        },
                    )
                    if row["name"] not in {"regenerate", "in-context"} or row["name"] in names:
                        raise ComparisonObservationError("invalid observed reference mode")
                    names.add(row["name"])
                    common._path(row["directory"])
                    if row["state"] not in {"fresh", "prepared", "complete"}:
                        raise ComparisonObservationError("invalid reference state")
                    for key in ("next_stage", "completed_stages", "owner_count"):
                        _integer(row[key], key)
        elif (
            observed["status"] != "unavailable"
            or observed["value"] is not None
            or observed["reason"] != name + "_state_unavailable"
        ):
            raise ComparisonObservationError("unavailable state cannot invent an observation")
    return cast(dict[str, Any], record)


def read_observation(path: Path, *, expected_sha256: str) -> dict[str, object]:
    """Read a pinned historical diagnostic without reopening its live experiment."""
    try:
        if not isinstance(path, Path):
            raise ComparisonObservationError("observation needs an explicit Path")
        return _record(
            _load(pipeline._read(common._path(str(path.absolute())), _digest(expected_sha256)))
        )
    except _ERRORS:
        raise ComparisonObservationError("saved comparison observation is invalid") from None


def save_observation(
    output: Path,
    *,
    primary_launch: Path,
    expected_launch_sha256: str,
    comparison_plan: Path,
    expected_plan_sha256: str,
    reference_grant: dict[str, object],
    total_limits: dict[str, object],
    phase: str,
    reason: str,
    cancelled: bool = False,
    input_bindings: dict[Path, str] | None = None,
) -> dict[str, object]:
    """Save one new incomplete observation, retaining unavailable facts explicitly."""
    try:
        if phase not in _STOPS or type(cancelled) is not bool:
            raise ComparisonObservationError("invalid comparison stop")
        _code(reason)
        inputs, roots = _arm(
            primary_launch,
            expected_launch_sha256,
            comparison_plan,
            expected_plan_sha256,
            reference_grant,
            total_limits,
            input_bindings,
        )
        destination = common._receipt_path(output, error=ComparisonObservationError)
        if any(_overlap(destination, root) for root in roots):
            raise ComparisonObservationError("observation overlaps protected experiment data")
        rows, snapshots = _funding(inputs["grants"])
        primary = _observe(
            lambda: improver_launch.check_launch(
                common._path(inputs["primary_launch"]["path"]),
                expected_sha256=inputs["primary_launch"]["sha256"],
            ),
            ("state", "phase", "stop_code", "next_position", "state_sha256"),
            "primary_state_unavailable",
        )
        references = _observe(
            lambda: baseline_state.inspect_references(
                common._path(inputs["comparison_plan"]["path"]),
                expected_plan_sha256=inputs["comparison_plan"]["sha256"],
                input_bindings={common._path(p): d for p, d in inputs["input_bindings"].items()},
            ),
            ("state", "ready", "blocked_reasons", "references", "state_sha256"),
            "references_state_unavailable",
        )
        repeated, protected = _arm(
            primary_launch,
            expected_launch_sha256,
            comparison_plan,
            expected_plan_sha256,
            reference_grant,
            total_limits,
            input_bindings,
        )
        if _json(repeated) != _json(inputs) or roots != protected:
            raise ComparisonObservationError("pinned observation context changed")
        for name, raw in snapshots.items():
            try:
                common._finish_snapshot(common._path(inputs["grants"][name]["path"]), raw)
            except _ERRORS:
                rows[name] = _unavailable("funding_changed")
        record = _record(
            {
                "format": "buddha.comparison-observation.v1",
                "status": "incomplete",
                "recorded_at": datetime.now(UTC).isoformat(timespec="seconds"),
                "stop": {
                    "phase": phase,
                    "reason": reason,
                    "cancelled": cancelled,
                    "source": "launcher_reported",
                },
                "inputs": inputs,
                "funding": _financial(rows),
                "primary": primary,
                "references": references,
                "claim": _CLAIM,
            }
        )
        raw = _json(record)
        pipeline._write(destination, raw)
        digest = _sha(raw)
        saved = read_observation(destination, expected_sha256=digest)
        if _json(saved) != raw:
            raise ComparisonObservationError("saved comparison observation differs")
        return {"path": str(destination), "sha256": digest, "observation": saved}
    except _ERRORS:
        raise ComparisonObservationError(
            "comparison observation not saved; original evidence retained"
        ) from None
