"""Pure, exploratory parent selection on common-development-set results.

The controller must establish completion, common coverage, provenance, and
comparison compatibility before supplying candidates. These scalar records do
not authenticate judgments or establish a statistically confirmed improvement.
"""

import random
from collections import Counter
from collections.abc import Sequence
from dataclasses import dataclass

from buddha.evaluation import ValidationError, _hex, _integer, _number, _sequence


@dataclass(frozen=True)
class Candidate:
    """A completed candidate's two means on the controller's common development set."""

    candidate_id: str
    parent_id: str | None
    mean_utility: float
    mean_distinct: float

    def __post_init__(self) -> None:
        _hex(self.candidate_id, "candidate_id")
        if self.parent_id is not None:
            _hex(self.parent_id, "parent_id")
        for name, minimum in (("mean_utility", 0), ("mean_distinct", 1)):
            if not minimum <= _number(getattr(self, name), name) <= 10:
                raise ValidationError(f"{name} must be in [{minimum}, 10]")


def _checked(candidates: Sequence[Candidate]) -> tuple[Candidate, ...]:
    _sequence(candidates, "candidates")
    result = tuple(candidates)
    if any(not isinstance(item, Candidate) for item in result):
        raise ValidationError("candidates must contain Candidate records")
    if len({item.candidate_id for item in result}) != len(result):
        raise ValidationError("duplicate candidate_id")
    return result


def _capacity(max_active: int) -> None:
    if _integer(max_active, "max_active", 2) > 64:
        raise ValidationError("max_active must be <= 64")


def _children(candidates: Sequence[Candidate]) -> Counter[str]:
    return Counter(item.parent_id for item in candidates if item.parent_id is not None)


def frontier(candidates: Sequence[Candidate]) -> tuple[Candidate, ...]:
    """Exact Pareto frontier maximizing both axes; equal points remain eligible."""
    items = _checked(candidates)
    return tuple(
        sorted(
            (
                item
                for item in items
                if not any(
                    other.mean_utility >= item.mean_utility
                    and other.mean_distinct >= item.mean_distinct
                    and (
                        other.mean_utility > item.mean_utility
                        or other.mean_distinct > item.mean_distinct
                    )
                    for other in items
                )
            ),
            key=lambda item: item.candidate_id,
        )
    )


def _crowded(candidates: tuple[Candidate, ...], limit: int) -> tuple[Candidate, ...]:
    """NSGA-II normalized neighbor crowding, with explicit objective extremes."""
    if len(candidates) <= limit:
        return candidates
    distances = dict.fromkeys((item.candidate_id for item in candidates), 0.0)
    # Explicit extremes prevent duplicate endpoints from crowding out one axis.
    extremes: set[str] = set()
    for objective in ("mean_utility", "mean_distinct"):
        ordered = sorted(candidates, key=lambda item: (getattr(item, objective), item.candidate_id))
        low, high = getattr(ordered[0], objective), getattr(ordered[-1], objective)
        best = min(candidates, key=lambda item: (-getattr(item, objective), item.candidate_id))
        extremes.add(best.candidate_id)
        if high == low:
            continue
        distances[ordered[0].candidate_id] = float("inf")
        distances[ordered[-1].candidate_id] = float("inf")
        for previous, item, following in zip(ordered, ordered[1:], ordered[2:], strict=False):
            distances[item.candidate_id] += (
                getattr(following, objective) - getattr(previous, objective)
            ) / (high - low)
    ranked = sorted(candidates, key=lambda item: (-distances[item.candidate_id], item.candidate_id))
    selected = [item for item in candidates if item.candidate_id in extremes]
    selected.extend(item for item in ranked if item.candidate_id not in extremes)
    return tuple(sorted(selected[:limit], key=lambda item: item.candidate_id))


def active_pool(candidates: Sequence[Candidate], *, max_active: int) -> tuple[Candidate, ...]:
    """Bound the frontier and retain at most 20% dominated exploration reserve.

    Reserve rank is fewest direct children, greatest utility, greatest distinct,
    then candidate ID. Child counts describe search allocation, not novelty.
    """
    _capacity(max_active)
    items = _checked(candidates)
    pareto = frontier(items)
    pareto_ids = {item.candidate_id for item in pareto}
    counts = _children(items)
    dominated = sorted(
        (item for item in items if item.candidate_id not in pareto_ids),
        key=lambda item: (
            counts[item.candidate_id],
            -item.mean_utility,
            -item.mean_distinct,
            item.candidate_id,
        ),
    )
    reserve = dominated[: max_active // 5]
    selected = _crowded(pareto, max_active - len(reserve)) + tuple(reserve)
    return tuple(sorted(selected, key=lambda item: item.candidate_id))


def select_parent(
    candidates: Sequence[Candidate], *, method: str, max_active: int, seed: int, iteration: int
) -> Candidate:
    """Select with archive feedback or historical latest/initial ablations.

    Archive selection explores uniformly with probability 0.1. Otherwise each
    active member has weight (2 if Pareto else 1) / (1 + direct child count).
    The history's insertion order is authoritative for latest and uninformed.
    """
    _capacity(max_active)
    _integer(seed, "seed", 0)
    _integer(iteration, "iteration", 0)
    if method not in ("archive", "latest", "uninformed"):
        raise ValidationError("method must be archive, latest, or uninformed")
    items = _checked(candidates)
    if not items:
        raise ValidationError("cannot select a parent from an empty archive")
    if method != "archive":
        return items[-1] if method == "latest" else items[0]
    pool = active_pool(items, max_active=max_active)
    # Non-security experimental sampling, locally seeded for exact resume.
    rng = random.Random(f"{seed}:{iteration}")  # nosec B311
    if rng.random() < 0.1:
        return pool[rng.randrange(len(pool))]
    pareto_ids = {item.candidate_id for item in frontier(items)}
    counts = _children(items)
    weights = [
        (2 if item.candidate_id in pareto_ids else 1) / (1 + counts[item.candidate_id])
        for item in pool
    ]
    remaining = rng.random() * sum(weights)
    for item, weight in zip(pool, weights, strict=True):
        remaining -= weight
        if remaining < 0:
            return item
    return pool[-1]  # Floating-point rounding at the upper cumulative boundary.
