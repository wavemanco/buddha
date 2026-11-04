"""DESIGN6 numerical rule over caller-supplied lower bounds and coverage.

This neither estimates uncertainty nor verifies provenance, coverage or an
occasion's authority. Satisfaction can allow the declared loss on the other
axis; non-satisfaction does not disprove improvement. The future controller
must consume the exact prospectively frozen rule before observation.
"""

import math
from dataclasses import dataclass
from typing import cast

from buddha.answers import _Artifact
from buddha.releases import ReleaseError, _json, _load, _object


class ImprovementRuleError(ReleaseError):
    """The numerical rule or supplied bounds violate their declared shape."""


def _number(value: object) -> int | float:
    if type(value) not in (int, float):
        raise ImprovementRuleError("bounds and margins require literal finite numbers")
    number = cast(int | float, value)
    # Integers are finite without converting them to potentially lossy floats.
    if type(number) is float and not math.isfinite(number):
        raise ImprovementRuleError("bounds and margins require literal finite numbers")
    return number


@dataclass(frozen=True)
class ImprovementRule(_Artifact):
    """Immutable canonical rule bytes; margins and primary axis have no defaults."""

    def __post_init__(self) -> None:
        try:
            record = _object(
                _load(self.data),
                {"format", "primary_metric", "minimum_gain", "max_other_loss"},
            )
            if (
                type(record["format"]) is not str
                or record["format"] != "buddha.improvement-rule.v1"
                or type(record["primary_metric"]) is not str
                or record["primary_metric"] not in {"utility", "distinct"}
                or _number(record["minimum_gain"]) < 0
                or _number(record["max_other_loss"]) < 0
            ):
                raise ImprovementRuleError("unsupported rule or negative margin")
            canonical = _json(record)
        except ReleaseError:
            raise ImprovementRuleError("invalid numerical improvement rule") from None
        object.__setattr__(self, "data", canonical)


def evaluate_improvement_rule(
    rule: ImprovementRule,
    *,
    lower_bounds: object,
    complete_coverage: bool,
) -> dict[str, object]:
    """Apply the declared axis only; the completeness assertion is not attestation.

    Validate all supplied bounds even when incomplete. Missing evidence returns
    an inconclusive numerical result and never substitutes a zero or an axis.
    """
    if type(rule) is not ImprovementRule or type(complete_coverage) is not bool:
        raise ImprovementRuleError("an exact rule and literal coverage boolean are required")
    if type(lower_bounds) is not dict:
        raise ImprovementRuleError("lower bounds require the exact two-key object")
    try:
        supplied = _object(lower_bounds, {"utility", "distinct"})
    except ReleaseError:
        raise ImprovementRuleError("lower bounds require the exact two-key object") from None
    bounds = {name: None if value is None else _number(value) for name, value in supplied.items()}
    record = rule.to_record()
    metric = cast(str, record["primary_metric"])
    other_metric = "distinct" if metric == "utility" else "utility"
    primary, other = bounds[metric], bounds[other_metric]
    status = "inconclusive"
    checks: dict[str, bool | None] = {"primary_gain": None, "other_noninferiority": None}
    if complete_coverage and primary is not None and other is not None:
        checks = {
            "primary_gain": primary > _number(record["minimum_gain"]),
            "other_noninferiority": other >= -_number(record["max_other_loss"]),
        }
        status = "rule_satisfied" if all(checks.values()) else "rule_not_satisfied"
    result = {
        "format": "buddha.improvement-rule-result.v1",
        "status": status,
        "rule_sha256": rule.fingerprint(),
        "primary_metric": metric,
        "lower_bounds": bounds,
        "complete_coverage": complete_coverage,
        "checks": checks,
        "claim": "Numerical rule only; bounds and coverage are caller-supplied, "
        "with no provenance attestation or promotion authority.",
    }
    try:
        _json(result)
    except ReleaseError:
        raise ImprovementRuleError("numerical result must be bounded finite JSON") from None
    return result
