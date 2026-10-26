"""Passive funding consistency for a matched study and its shared plain references."""

from pathlib import Path
from typing import cast

from buddha import improver_launch, plain_comparison
from buddha import launch_common as common
from buddha import native_pipeline as pipeline
from buddha.doctor import _Busy, _Unsupported
from buddha.provider import _integer
from buddha.releases import ReleaseError, _digest, _json, _load, _object, file_hash
from buddha.search_evidence import _overlap

_PHASES = ("search", "validation", "final")
_AMOUNTS = ("spent_microusd", "reserved_microusd", "committed_microusd", "operation_count")


class UnifiedFundingError(ReleaseError):
    """The declared combined limits or original funding do not agree."""


def reference_scope(expected_plan_sha256: str) -> str:
    """Identify the shared reference grant by the exact prospective plan bytes."""
    return "buddha.plain-references.v1:" + _digest(expected_plan_sha256)


def _limits(value: object) -> dict[str, int]:
    record = _object(value, {"budget_microusd", "max_calls"})
    return {key: _integer(v, "combined " + key) for key, v in record.items()}


def check_funding(
    primary_launch: Path,
    *,
    expected_launch_sha256: str,
    comparison_plan: Path,
    expected_plan_sha256: str,
    reference_grant: dict[str, object],
    total_limits: dict[str, object],
) -> dict[str, object]:
    """Observe four original grants once, without keys, writers or execution.

    The caller must obtain these exact arguments from its approved handoff.
    This check neither supplies that approval nor validates raw owner recovery.
    """
    try:
        if not isinstance(primary_launch, Path) or not isinstance(comparison_plan, Path):
            raise UnifiedFundingError("combined checks require explicit Paths")
        launch_path = common._path(str(primary_launch.absolute()))
        plan_path = common._path(str(comparison_plan.absolute()))
        launch_digest, plan_digest = _digest(expected_launch_sha256), _digest(expected_plan_sha256)
        limits = _limits(total_limits)
        if not all(limits.values()):
            raise UnifiedFundingError("combined limits must be positive")
        plan = plain_comparison._plan(pipeline._read(plan_path, plan_digest))
        controls = {
            str(plan_path): plan_digest,
            **cast(dict[str, str], plan["consumer_sources"]),
            str(Path(__file__).absolute()): file_hash(Path(__file__).absolute()),
        }
        primary = improver_launch.check_launch(launch_path, expected_sha256=launch_digest)
        if (
            plan["trial"] != primary["directory"]
            or plan["definition_sha256"] != primary["definition_sha256"]
            or any(_object(primary["bindings"]).get(p) != d for p, d in controls.items())
        ):
            raise UnifiedFundingError("comparison controls differ from the original primary launch")

        grant = _object(
            reference_grant,
            {"path", "id", "terms_sha256", "scope", "budget_microusd", "max_calls"},
        )
        raw_path = common._path(grant["path"])
        raw_limits = _limits({name: grant[name] for name in limits})
        if not all(raw_limits.values()):
            raise UnifiedFundingError("reference grant limits must be positive")
        protected = [common._path(p) for p in cast(list[object], primary["protected_roots"])]
        protected.extend(common._path(p) for p in controls)
        for row in plan["references"]:
            if common._path(row["authorization"]) != raw_path:
                raise UnifiedFundingError("all plain references must share one original grant")
            source = common._path(row["definition"])
            digest = _digest(row["sha256"])
            pipeline._read(source, digest)
            protected.extend((source, common._path(row["directory"])))
            if str(source) in controls and controls[str(source)] != digest:
                raise UnifiedFundingError("conflicting comparison control seals")
            controls[str(source)] = digest
        if any(_overlap(raw_path, path) for path in protected):
            raise UnifiedFundingError("reference grant overlaps protected inputs or outputs")

        paths = {name: common._path(p) for name, p in _object(primary["authorizations"]).items()}
        if set(paths) != set(_PHASES):
            raise UnifiedFundingError("primary phase grants are incomplete")
        paths["shared_plain_references"] = raw_path
        observed, snapshots, phases = {}, {}, {}
        for name, path in paths.items():
            current, raw = common._snapshot(path)
            observed[name], snapshots[path] = current, raw
            phases[name] = _object(current["config"]) | _object(current["totals"])
        if len(snapshots) != 4:
            raise UnifiedFundingError("four distinct original grants are required")
        if any(
            _json(phases[name]) != _json(_object(_object(primary["funding"])["phases"])[name])
            for name in _PHASES
        ):
            raise UnifiedFundingError("primary funding changed during combined checking")
        raw_config = _object(observed["shared_plain_references"]["config"])
        expected_grant = {
            "path": str(raw_path),
            "id": raw_config["authorization_id"],
            "terms_sha256": raw_config["terms_sha256"],
            "scope": reference_scope(plan_digest),
            **raw_limits,
        }
        if _json(grant) != _json(expected_grant) or any(
            raw_config[key] != expected_grant[key] for key in ("scope", *raw_limits)
        ):
            raise UnifiedFundingError("reference funding differs from the declared original grant")
        if any(
            len({row[key] for row in phases.values()}) != 4 for key in ("authorization_id", "scope")
        ):
            raise UnifiedFundingError("grant identities and scopes must be distinct")
        allocations = {
            name: _limits({key: row[key] for key in limits}) for name, row in phases.items()
        }
        if {key: sum(row[key] for row in allocations.values()) for key in limits} != limits:
            raise UnifiedFundingError("four allocations must sum to the one declared ceiling")
        for name, row in phases.items():
            if (
                _integer(row["committed_microusd"], "committed cost")
                > allocations[name]["budget_microusd"]
                or _integer(row["operation_count"], "recorded attempts")
                > allocations[name]["max_calls"]
            ):
                raise UnifiedFundingError("original grant exceeds its declared limits")
            if primary["state"] == "fresh" and any(
                observed[name][table]
                for table in (
                    "auth_runs",
                    "auth_operations",
                    "auth_acceptances",
                    "auth_deactivations",
                )
            ):
                raise UnifiedFundingError("a fresh combined study cannot replace used funding")
        totals = {key: sum(_integer(row[key], key) for row in phases.values()) for key in _AMOUNTS}
        for path, raw in snapshots.items():
            common._finish_snapshot(path, raw, error=UnifiedFundingError)
        for control_path, digest in controls.items():
            pipeline._read(common._path(control_path), digest)
        pipeline._read(launch_path, launch_digest)
        return _load(
            _json(
                {
                    "format": "buddha.unified-funding-check.v1",
                    "primary": primary,
                    "reference_authorization": str(raw_path),
                    "controls": controls,
                    "allocations": allocations,
                    "limits": limits,
                    "phases": phases,
                    "totals": totals,
                    "claim": "Funding consistency observation only; approval, account checks, "
                    "raw original-owner recovery and execution remain separate.",
                }
            )
        )
    except (
        ValueError,
        TypeError,
        KeyError,
        OSError,
        RecursionError,
        OverflowError,
        _Busy,
        _Unsupported,
    ):
        raise UnifiedFundingError(
            "combined funding checks failed; original records retained"
        ) from None
