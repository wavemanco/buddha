"""Offline arithmetic and evidence checks; this module never calls a model.

Partitions and quality scores are external measurements. Validating their shape
and arithmetic does not establish that their judgments are correct or authentic.
"""

import hashlib
import json
import math
from collections.abc import Mapping, Sequence
from dataclasses import asdict, dataclass, fields

from buddha.common import ValidationError as ValidationError
from buddha.common import _hex as _hex
from buddha.common import _integer as _integer
from buddha.common import _text as _text


def _number(value: object, name: str) -> float:
    if not isinstance(value, (int, float)) or isinstance(value, bool):
        raise ValidationError(f"{name} must be a finite number")
    try:
        finite = math.isfinite(value)
    except OverflowError:
        finite = False
    if not finite:
        raise ValidationError(f"{name} must be a finite number")
    return float(value)


def _patience(value: object) -> None:
    numeric = _number(value, "patience")
    if not 0 <= numeric <= 1:
        raise ValidationError("patience must be in [0, 1]")


def _sequence(value: object, name: str) -> Sequence[object]:
    if not isinstance(value, Sequence) or isinstance(value, (str, bytes, bytearray)):
        raise ValidationError(f"{name} must be a sequence")
    return value


@dataclass(frozen=True)
class EvaluationProtocol:
    """Scalar-only, immutable identity of an evaluation instrument and population.

    Hashes identify effective configuration stored elsewhere; no placeholder
    manifest is implicitly populated and no model-version syntax is invented.
    """

    upstream_commit: str
    metric_version: str
    dataset_sha256: str
    split_sha256: str
    partition_model: str
    quality_model: str
    partition_prompt_sha256: str
    quality_prompt_sha256: str
    generation_config_sha256: str
    fallback_policy_sha256: str
    ordering_seed: int | None
    k: int = 10
    patience: float = 0.8

    def __post_init__(self) -> None:
        _hex(self.upstream_commit, "upstream_commit", 40)
        if self.metric_version != "1.1":
            raise ValidationError("only the current NoveltyBench metric 1.1 is supported")
        for field in fields(self):
            if field.name.endswith("_sha256"):
                _hex(getattr(self, field.name), field.name)
        _text(self.partition_model, "partition_model")
        _text(self.quality_model, "quality_model")
        if self.ordering_seed is not None:
            _integer(self.ordering_seed, "ordering_seed", 0)
        _integer(self.k, "k", 1)
        _patience(self.patience)

    def fingerprint(self) -> str:
        encoded = json.dumps(
            asdict(self), sort_keys=True, separators=(",", ":"), allow_nan=False
        ).encode("utf-8")
        return hashlib.sha256(encoded).hexdigest()


@dataclass(frozen=True)
class SequenceScore:
    distinct: int
    utility: float


def score_sequence(
    partition: Sequence[object],
    generation_scores: Sequence[object],
    *,
    patience: float = 0.8,
    expected_k: int = 10,
) -> SequenceScore:
    """Credit quality at each class's first position, retaining every position.

    Duplicate positions may carry None or an independently supplied valid quality
    score; their utility is zero in either case. Class heads require a score.
    """
    _integer(expected_k, "expected_k", 1)
    _patience(patience)
    _sequence(partition, "partition")
    _sequence(generation_scores, "generation_scores")
    if len(partition) != expected_k or len(generation_scores) != expected_k:
        raise ValidationError("partition and scores must each have expected_k entries")

    seen: set[int] = set()
    weighted_quality: list[float] = []
    weights = [patience**index for index in range(expected_k)]
    for label, quality, weight in zip(partition, generation_scores, weights, strict=True):
        label = _integer(label, "partition label", 0)
        if quality is not None and (type(quality) is not int or not 1 <= quality <= 10):
            raise ValidationError("quality must be an integer in [1, 10] or None")
        if label not in seen:
            if quality is None:
                raise ValidationError("class head is missing its quality score")
            weighted_quality.append(weight * quality)
            seen.add(label)

    return SequenceScore(len(seen), math.fsum(weighted_quality) / math.fsum(weights))


@dataclass(frozen=True)
class RunSummary:
    expected_count: int
    scored_count: int
    mean_distinct: float
    mean_utility: float
    protocol_fingerprint: str


def summarize_run(
    expected_prompt_hashes: Mapping[str, str],
    rows: Sequence[Mapping[str, object]],
    *,
    protocol: EvaluationProtocol,
) -> RunSummary:
    """Summarize complete, consistent evidence; incomplete runs cannot promote.

    Rows use upstream score fields plus a required protocol_fingerprint supplied
    by a trusted importer. This function is not that importer or an attestation.
    """
    if not isinstance(protocol, EvaluationProtocol):
        raise ValidationError("protocol must be an EvaluationProtocol")
    if not isinstance(expected_prompt_hashes, Mapping) or not expected_prompt_hashes:
        raise ValidationError("expected prompt manifest must be a nonempty mapping")
    for instance_id, prompt_hash in expected_prompt_hashes.items():
        _text(instance_id, "expected prompt ID")
        _hex(prompt_hash, "expected prompt hash")
    _sequence(rows, "rows")

    fingerprint = protocol.fingerprint()
    seen: set[str] = set()
    results: list[SequenceScore] = []
    required = {
        "id",
        "prompt",
        "generations",
        "partition",
        "generation_scores",
        "utility",
        "distinct",
        "protocol_fingerprint",
    }
    for row in rows:
        if not isinstance(row, Mapping) or not required.issubset(row):
            raise ValidationError("evaluation row is missing required evidence")
        instance_id = _text(row["id"], "prompt ID")
        if instance_id not in expected_prompt_hashes or instance_id in seen:
            raise ValidationError("unexpected or duplicate prompt ID")
        if "unscored" in row or row["protocol_fingerprint"] != fingerprint:
            raise ValidationError("unscored evidence or mismatched evaluation protocol")
        prompt = row["prompt"]
        if not isinstance(prompt, str):
            raise ValidationError("prompt must be text")
        try:
            prompt_hash = hashlib.sha256(prompt.encode("utf-8")).hexdigest()
        except UnicodeError as error:
            raise ValidationError("prompt must be valid UTF-8 text") from error
        if prompt_hash != expected_prompt_hashes[instance_id]:
            raise ValidationError("prompt content does not match expected hash")
        generations = _sequence(row["generations"], "generations")
        if len(generations) != protocol.k or any(not isinstance(g, str) for g in generations):
            raise ValidationError("generations must contain k strings, including empty attempts")
        result = score_sequence(
            _sequence(row["partition"], "partition"),
            _sequence(row["generation_scores"], "generation_scores"),
            patience=protocol.patience,
            expected_k=protocol.k,
        )
        _integer(row["distinct"], "distinct", 1)
        reported_utility = _number(row["utility"], "utility")
        if row["distinct"] != result.distinct or not math.isclose(
            reported_utility, result.utility, rel_tol=1e-9, abs_tol=1e-9
        ):
            raise ValidationError("reported metric does not match evidence arithmetic")
        seen.add(instance_id)
        results.append(result)

    if seen != set(expected_prompt_hashes):
        raise ValidationError("evaluation is missing expected prompt IDs")
    count = len(results)
    return RunSummary(
        expected_count=count,
        scored_count=count,
        mean_distinct=math.fsum(result.distinct for result in results) / count,
        mean_utility=math.fsum(result.utility for result in results) / count,
        protocol_fingerprint=fingerprint,
    )
