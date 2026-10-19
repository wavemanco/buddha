"""Deterministic source-family partitions, with no semantic deduplication claim.

Whitespace/case normalized exact duplicates and caller-declared families travel
together, including their transitive unions. Groups, not individual prompts, are
allocated approximately 60/20/20; at least one group occupies each partition.
No source/task stratification or exact prompt proportions are promised. Returned
IDs are sorted, independent of source order. This module cannot prevent host
access to held-out source text; the controller must restrict feedback separately.
"""

import hashlib
from collections.abc import Mapping, Sequence

from buddha.benchmark import Prompt, _canonical, prompt_manifest
from buddha.evaluation import ValidationError

_NAMES = ("development", "validation", "final")


def _groups(prompts: Sequence[Prompt], families: Mapping[str, str] | None) -> list[list[str]]:
    if not isinstance(prompts, Sequence) or isinstance(prompts, (str, bytes)):
        raise ValidationError("source prompts must be a sequence")
    ids = prompt_manifest(prompts)
    if families is not None and (
        not isinstance(families, Mapping)
        or set(families) != set(ids)
        or any(not isinstance(label, str) or not label.strip() for label in families.values())
    ):
        raise ValidationError("families must map every source ID to a nonblank family label")
    parent = {item: item for item in ids}

    def find(item: str) -> str:
        while parent[item] != item:
            parent[item] = parent[parent[item]]
            item = parent[item]
        return item

    by_text: dict[str, str] = {}
    by_family: dict[str, str] = {}
    for prompt in prompts:
        text = " ".join(prompt.prompt.split()).casefold()
        parent[find(prompt.id)] = find(by_text.setdefault(text, prompt.id))
        if families is not None:
            label = families[prompt.id]
            parent[find(prompt.id)] = find(by_family.setdefault(label, prompt.id))
    grouped: dict[str, list[str]] = {}
    for item in sorted(ids):
        grouped.setdefault(find(item), []).append(item)
    return list(grouped.values())


def freeze_splits(
    prompts: Sequence[Prompt],
    *,
    seed: int,
    families: Mapping[str, str] | None = None,
) -> dict[str, list[str]]:
    """Freeze all IDs once, sorting groups by SHA256(seed, sorted member IDs)."""
    if type(seed) is not int or not 0 <= seed <= 2**63 - 1:
        raise ValidationError("split seed must be a bounded nonnegative integer")
    groups = _groups(prompts, families)
    if len(groups) < 3:
        raise ValidationError("three independent source groups are required")
    groups.sort(key=lambda members: (hashlib.sha256(_canonical([seed, members])).digest(), members))
    count = len(groups)
    development = min(max(1, count * 3 // 5), count - 2)
    validation = min(max(1, count // 5), count - development - 1)
    cuts = (0, development, development + validation, count)
    return {
        name: sorted(item for group in groups[cuts[index] : cuts[index + 1]] for item in group)
        for index, name in enumerate(_NAMES)
    }


def validate_splits(
    prompts: Sequence[Prompt],
    splits: object,
    *,
    families: Mapping[str, str] | None = None,
) -> dict[str, list[str]]:
    """Require a complete, nonempty three-way ID partition with no family leak."""
    groups = _groups(prompts, families)
    if not isinstance(splits, dict) or set(splits) != set(_NAMES):
        raise ValidationError("splits must contain exactly development, validation, and final")
    assignments: dict[str, str] = {}
    result: dict[str, list[str]] = {}
    source_ids = {item for group in groups for item in group}
    for name in _NAMES:
        items = splits[name]
        if not isinstance(items, list) or not items:
            raise ValidationError("each split must contain a nonempty ID list")
        for item in items:
            if not isinstance(item, str) or item not in source_ids or item in assignments:
                raise ValidationError("split contains an unknown or repeated source ID")
            assignments[item] = name
        result[name] = sorted(items)
    if set(assignments) != source_ids:
        raise ValidationError("splits must cover every source ID")
    if any(len({assignments[item] for item in group}) != 1 for group in groups):
        raise ValidationError("related source prompts must occupy the same split")
    return result
