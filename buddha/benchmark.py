"""Pinned NoveltyBench v1.1 prompts and local artifact integrity, never certification."""

import hashlib
import json
import math
import os
import random
import shutil
import tempfile
from collections.abc import Mapping, Sequence
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import cast

from buddha.evaluation import (
    EvaluationProtocol,
    RunSummary,
    ValidationError,
    _hex,
    _integer,
    _number,
    _sequence,
    _text,
    summarize_run,
)

UPSTREAM_COMMIT = "64a23be6b18ec1dacc298830aab276061b6e143c"
METRIC_VERSION = "1.1"
DEFAULT_PARTITION_MODEL = "gpt-5.6-luna"
DEFAULT_QUALITY_MODEL = "claude-opus-5"

# Upstream MIT-licensed strings; see THIRD_PARTY_NOTICES.md.
PARTITION_SYSTEM = """\
A language model was asked the same prompt several times. Partition its \
responses into groups of equivalent answers.

Two responses are equivalent if a user who had read one would gain essentially \
nothing from the other: the same central answer, recommendation, plot, argument \
or image, differing only in wording, formatting, length, ordering or minor \
detail. They are distinct if the central content differs, even when structure \
or register is shared. A list is distinct only if most of its items differ."""

SCORE_SYSTEM = """\
Score the response to the prompt, 1-10, by how well it serves what the prompt \
asked for.

A prompt that asks for one thing is best served by one thing; elaboration \
beyond the ask earns nothing, and craft counts where the prompt calls for it.
10: the best response an expert could give to this prompt.
7: good, with clear room to improve.
4: a weak attempt that still answers the prompt.
1-3: fails the ask: wrong form or scope, off-topic, empty, or a substantive error.

An unusual angle or format is fine if it answers the prompt."""

_ARTIFACTS = (
    "generations.jsonl",
    "v1.1/partitions.jsonl",
    "v1.1/scores.jsonl",
    "v1.1/summary.json",
)
_GENERATION_FIELDS = "id prompt model generations protocol_fingerprint generation_config".split()


def _digest(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()


def _utf8(text: str) -> bytes:
    try:
        return text.encode("utf-8")
    except UnicodeError as error:
        raise ValidationError("text must be valid UTF-8") from error


def _canonical(value: object) -> bytes:
    try:
        return json.dumps(
            value, sort_keys=True, separators=(",", ":"), ensure_ascii=True, allow_nan=False
        ).encode("utf-8")
    except (TypeError, ValueError, UnicodeError, RecursionError) as error:
        raise ValidationError("configuration or evidence is not finite JSON") from error


def _object(value: object) -> dict[str, object]:
    if not isinstance(value, dict) or any(not isinstance(k, str) for k in value):
        raise ValidationError("expected a JSON object with string keys")
    return cast(dict[str, object], value)


def _same(first: object, second: object) -> bool:
    return _canonical(first) == _canonical(second)


def _unique_pairs(pairs: list[tuple[str, object]]) -> dict[str, object]:
    result: dict[str, object] = {}
    for key, value in pairs:
        if key in result:
            raise ValidationError("duplicate JSON object key")
        result[key] = value
    return result


def _invalid_constant(value: str) -> object:
    raise ValidationError("nonfinite JSON number")


def _parse(raw: bytes) -> object:
    try:
        return cast(
            object,
            json.loads(
                raw.decode("utf-8"),
                object_pairs_hook=_unique_pairs,
                parse_constant=_invalid_constant,
            ),
        )
    except (UnicodeError, json.JSONDecodeError) as error:
        raise ValidationError("invalid UTF-8 JSON") from error


def _jsonl(raw: bytes) -> list[dict[str, object]]:
    rows = [_object(_parse(line)) for line in raw.splitlines()]
    if not rows:
        raise ValidationError("JSONL must contain at least one row")
    return rows


@dataclass(frozen=True)
class Prompt:
    id: str
    prompt: str

    def __post_init__(self) -> None:
        _utf8(_text(self.id, "prompt ID"))
        _utf8(_text(self.prompt, "prompt"))


def prompt_manifest(prompts: Sequence[Prompt]) -> dict[str, str]:
    result: dict[str, str] = {}
    for prompt in prompts:
        if not isinstance(prompt, Prompt) or prompt.id in result:
            raise ValidationError("invalid or duplicate prompt")
        result[prompt.id] = _digest(_utf8(prompt.prompt))
    if not result:
        raise ValidationError("prompt manifest must not be empty")
    return result


def load_prompts(path: Path, *, expected_sha256: str) -> tuple[Prompt, ...]:
    _hex(expected_sha256, "dataset hash")
    raw = path.read_bytes()
    if _digest(raw) != expected_sha256:
        raise ValidationError("dataset byte hash mismatch")
    rows = _jsonl(raw)
    if any(not {"id", "prompt"}.issubset(row) for row in rows):
        raise ValidationError("dataset row is missing its ID or prompt")
    prompts = tuple(Prompt(_text(row["id"], "ID"), _text(row["prompt"], "prompt")) for row in rows)
    prompt_manifest(prompts)
    return prompts


def render_responses(prompt: str, responses: Sequence[str]) -> str:
    _utf8(_text(prompt, "prompt"))
    _sequence(responses, "responses")
    if any(not isinstance(response, str) for response in responses):
        raise ValidationError("responses must be strings")
    for response in responses:
        _utf8(response)
    parts = [f"<prompt>\n{prompt}\n</prompt>"]
    parts.extend(f'<response index="{i}">\n{r}\n</response>' for i, r in enumerate(responses))
    return "\n\n".join(parts)


def partition_order(prompt: str, n: int, seed: int | None) -> list[int]:
    _text(prompt, "prompt")
    _integer(n, "response count", 1)
    if seed is not None and type(seed) is not int:
        raise ValidationError("ordering seed must be an integer or None")
    order = list(range(n))
    if seed is not None:
        # Deterministic benchmark ordering, not a security or credential primitive.
        random.Random(f"{seed}{prompt}").shuffle(order)  # nosec B311
    return order


def fold_partition(groups: object, *, prompt: str, n: int, seed: int | None) -> list[int]:
    order = partition_order(prompt, n, seed)
    partition = [-1] * n
    for label, group in enumerate(_sequence(groups, "groups")):
        members = _sequence(group, "group")
        if not members:
            raise ValidationError("partition groups must not be empty")
        for member in members:
            index = _integer(member, "response index", 0)
            if index >= n or partition[order[index]] != -1:
                raise ValidationError("duplicate or out-of-range response index")
            partition[order[index]] = label
    if -1 in partition:
        raise ValidationError("judge partition is incomplete")
    seen: dict[int, int] = {}
    return [seen.setdefault(label, len(seen)) for label in partition]


def _check_protocol(protocol: EvaluationProtocol) -> None:
    if not isinstance(protocol, EvaluationProtocol) or (
        protocol.metric_version != METRIC_VERSION
        or protocol.upstream_commit != UPSTREAM_COMMIT
        or protocol.partition_prompt_sha256 != _digest(_utf8(PARTITION_SYSTEM))
        or protocol.quality_prompt_sha256 != _digest(_utf8(SCORE_SYSTEM))
    ):
        raise ValidationError("adapter requires the pinned v1.1 evaluator and judge prompts")


def _config(value: Mapping[str, object], protocol: EvaluationProtocol) -> dict[str, object]:
    def deny_secrets(node: object) -> None:
        if isinstance(node, Mapping):
            for key, item in node.items():
                if not isinstance(key, str):
                    raise ValidationError("configuration keys must be strings")
                normalized = key.lower().replace("-", "_")
                secret_fields = (
                    "api_key apikey authorization secret password credentials access_token "
                    "refresh_token"
                ).split()
                if normalized in secret_fields or normalized.endswith("_api_key"):
                    raise ValidationError("secret-bearing configuration is forbidden")
                deny_secrets(item)
        elif isinstance(node, (list, tuple)):
            for item in node:
                deny_secrets(item)

    raw = _canonical(value)
    snapshot = _object(_parse(raw))
    deny_secrets(snapshot)
    if _digest(raw) != protocol.generation_config_sha256:
        raise ValidationError("generation configuration hash mismatch")
    return snapshot


def _stage_configs(protocol: EvaluationProtocol) -> tuple[dict[str, object], dict[str, object]]:
    partition: dict[str, object] = dict(stage="partition", version=METRIC_VERSION, alg="llm")
    partition.update(judge_model=protocol.partition_model, seed=protocol.ordering_seed)
    score: dict[str, object] = dict(stage="score", version=METRIC_VERSION, scorer="llm")
    score.update(judge_model=protocol.quality_model, effort="high", patience=protocol.patience)
    return partition, score


def _validated_rows(
    rows: Sequence[Mapping[str, object]], protocol: EvaluationProtocol, config: dict[str, object]
) -> tuple[RunSummary, list[dict[str, object]]]:
    normalized = []
    for row in _sequence(rows, "evaluation rows"):
        if not isinstance(row, Mapping):
            raise ValidationError("evaluation row must be a mapping")
        normalized.append(_object(dict(row)))
    manifest = prompt_manifest(
        tuple(
            Prompt(_text(r.get("id"), "ID"), _text(r.get("prompt"), "prompt")) for r in normalized
        )
    )
    summary = summarize_run(manifest, normalized, protocol=protocol)
    for row in normalized:
        model = _text(row.get("model"), "model")
        if "model" in config and config["model"] != model:
            raise ValidationError("generation model does not match configuration")
        for response in cast(Sequence[str], row["generations"]):
            _utf8(response)
        labels = cast(Sequence[int], row["partition"])
        classes = list(dict.fromkeys(labels))
        if classes != list(range(len(classes))):
            raise ValidationError("partition labels must be canonical")
        scores = cast(Sequence[int | None], row["generation_scores"])
        heads = [labels.index(label) for label in classes]
        if any(score is not None for index, score in enumerate(scores) if index not in heads):
            raise ValidationError("v1.1 duplicate positions must be unscored")
        partition_scores = [scores[index] for index in heads]
        if "partition_scores" in row and not _same(row["partition_scores"], partition_scores):
            raise ValidationError("partition scores disagree with class heads")
        row["partition_scores"] = partition_scores
    return summary, normalized


def _existing_matches(destination: Path, files: Mapping[str, bytes]) -> bool:
    if destination.is_symlink() or not destination.is_dir():
        return False
    paths = list(destination.rglob("*"))
    if any(path.is_symlink() for path in paths):
        return False
    actual = {p.relative_to(destination).as_posix() for p in paths if p.is_file()}
    directories = {p.relative_to(destination).as_posix() for p in paths if p.is_dir()}
    return (
        actual == set(files)
        and directories == {"v1.1"}
        and all((destination / name).read_bytes() == raw for name, raw in files.items())
    )


def export_evaluation(
    destination: Path,
    *,
    protocol: EvaluationProtocol,
    rows: Sequence[Mapping[str, object]],
    generation_config: Mapping[str, object],
) -> None:
    _check_protocol(protocol)
    config = _config(generation_config, protocol)
    summary, normalized = _validated_rows(rows, protocol, config)
    partition_config, score_config = _stage_configs(protocol)
    generations, partitions, scores = [], [], []
    for row in normalized:
        base = {key: row[key] for key in _GENERATION_FIELDS if key != "generation_config"}
        base["generation_config"] = config
        partition = base | {key: row[key] for key in ("partition", "distinct")}
        partition["partition_config"] = partition_config
        score = partition | {
            key: row[key] for key in ("generation_scores", "partition_scores", "utility")
        }
        score["score_config"] = score_config
        generations.append(base)
        partitions.append(partition)
        scores.append(score)
    files = {
        name: b"".join(_canonical(row) + b"\n" for row in data)
        for name, data in zip(_ARTIFACTS[:3], (generations, partitions, scores), strict=True)
    }
    files[_ARTIFACTS[3]] = (
        _canonical(
            {
                "version": METRIC_VERSION,
                "mean_distinct": summary.mean_distinct,
                "mean_utility": summary.mean_utility,
            }
        )
        + b"\n"
    )
    provenance: dict[str, object] = {
        "format": "buddha.noveltybench.v1",
        "origin": "buddha-local",
        "protocol": asdict(protocol),
        "protocol_fingerprint": protocol.fingerprint(),
        "generation_config": config,
        "artifact_hashes": {n: _digest(b) for n, b in files.items()},
    }
    provenance["provenance_sha256"] = _digest(_canonical(provenance))
    files["provenance.json"] = _canonical(provenance) + b"\n"
    destination = destination.absolute()
    destination.parent.mkdir(parents=True, exist_ok=True)
    lock = destination.parent / f".{destination.name}.export.lock"
    try:
        lock_fd = os.open(lock, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
    except FileExistsError as error:
        raise ValidationError("another export owns the destination lock") from error
    staging: Path | None = None
    staging_prefix = f".{destination.name}."
    try:
        os.close(lock_fd)
        if destination.exists() or destination.is_symlink():
            if _existing_matches(destination, files):
                return
            raise ValidationError("destination conflicts with the evaluation; nothing overwritten")
        staging = Path(tempfile.mkdtemp(prefix=staging_prefix, dir=destination.parent))
        for name, raw in files.items():
            path = staging / name
            path.parent.mkdir(parents=True, exist_ok=True)
            with path.open("xb") as stream:
                stream.write(raw)
                stream.flush()
                os.fsync(stream.fileno())
        if destination.exists() or destination.is_symlink():
            raise ValidationError("destination appeared during export; nothing overwritten")
        # shortcut: lock coordinates our exports, not unrelated host writers; Windows rename
        # also refuses an existing destination. Stronger cross-tool isolation needs a broker.
        os.rename(staging, destination)
    finally:
        try:
            if staging is not None and (staging.exists() or staging.is_symlink()):
                resolved = staging.resolve(strict=True)
                if (
                    staging.is_symlink()
                    or resolved.parent != destination.parent.resolve(strict=True)
                    or resolved.name != staging.name
                    or not resolved.name.startswith(staging_prefix)
                ):
                    raise ValidationError("refusing cleanup outside the owned staging directory")
                shutil.rmtree(resolved)
        finally:
            lock.unlink()


def import_evaluation(
    source: Path, *, protocol: EvaluationProtocol, expected_prompt_hashes: Mapping[str, str]
) -> tuple[RunSummary, list[dict[str, object]]]:
    _check_protocol(protocol)
    expected_files = set(_ARTIFACTS) | {"provenance.json"}
    if source.is_symlink() or not source.is_dir():
        raise ValidationError("evaluation source must be a directory, not a symlink")
    paths = list(source.rglob("*"))
    if (
        any(p.is_symlink() for p in paths)
        or {p.relative_to(source).as_posix() for p in paths if p.is_file()} != expected_files
        or {p.relative_to(source).as_posix() for p in paths if p.is_dir()} != {"v1.1"}
    ):
        raise ValidationError("evaluation has missing, unexpected, or symlinked artifacts")
    provenance = _object(_parse((source / "provenance.json").read_bytes()))
    checksum = provenance.pop("provenance_sha256", None)
    if (
        checksum != _digest(_canonical(provenance))
        or provenance.get("format") != "buddha.noveltybench.v1"
        or provenance.get("origin") != "buddha-local"
    ):
        raise ValidationError("provenance checksum, format, or local origin mismatch")
    if (
        not _same(provenance.get("protocol"), asdict(protocol))
        or provenance.get("protocol_fingerprint") != protocol.fingerprint()
    ):
        raise ValidationError("provenance protocol mismatch")
    config = _config(_object(provenance.get("generation_config")), protocol)
    hashes = _object(provenance.get("artifact_hashes"))
    if set(hashes) != set(_ARTIFACTS):
        raise ValidationError("provenance artifact inventory mismatch")
    blobs = {name: (source / name).read_bytes() for name in _ARTIFACTS}
    if any(hashes[name] != _digest(raw) for name, raw in blobs.items()):
        raise ValidationError("artifact byte hash mismatch")
    generations, partitions, scores = (_jsonl(blobs[name]) for name in _ARTIFACTS[:3])
    if not len(generations) == len(partitions) == len(scores):
        raise ValidationError("artifact row coverage mismatch")
    partition_config, score_config = _stage_configs(protocol)
    for generation, partition, score in zip(generations, partitions, scores, strict=True):
        for key in _GENERATION_FIELDS:
            if (
                key not in generation
                or not _same(generation[key], partition.get(key))
                or not _same(generation[key], score.get(key))
            ):
                raise ValidationError("generation identity differs across artifacts")
        if (
            not _same(generation["generation_config"], config)
            or not _same(partition.get("partition_config"), partition_config)
            or not _same(score.get("score_config"), score_config)
        ):
            raise ValidationError("artifact configuration mismatch")
        if (
            not _same(partition.get("partition"), score.get("partition"))
            or not _same(partition.get("distinct"), score.get("distinct"))
            or not _same(score.get("partition_config"), partition_config)
        ):
            raise ValidationError("partition identity differs across artifacts")
    _, normalized = _validated_rows(scores, protocol, config)
    summary = summarize_run(expected_prompt_hashes, normalized, protocol=protocol)
    reported = _object(_parse(blobs[_ARTIFACTS[3]]))
    if reported.get("version") != METRIC_VERSION or set(reported) != {
        "version",
        "mean_distinct",
        "mean_utility",
    }:
        raise ValidationError("summary schema mismatch")
    for key, actual in (
        ("mean_distinct", summary.mean_distinct),
        ("mean_utility", summary.mean_utility),
    ):
        if not math.isclose(_number(reported[key], key), actual, rel_tol=1e-9, abs_tol=1e-9):
            raise ValidationError("reported summary disagrees with evidence")
    return summary, normalized
