"""Frozen v1.1 evaluation and replayable execution shared by bounded policies."""

import hashlib
import os
import uuid
from collections.abc import Callable, Sequence
from dataclasses import asdict, dataclass
from datetime import UTC, date, datetime
from pathlib import Path

from buddha.authorization import Authorization
from buddha.benchmark import (
    DEFAULT_PARTITION_MODEL,
    DEFAULT_QUALITY_MODEL,
    METRIC_VERSION,
    PARTITION_SYSTEM,
    SCORE_SYSTEM,
    UPSTREAM_COMMIT,
    Prompt,
    _canonical,
    _check_protocol,
    _object,
    _parse,
    _utf8,
    export_evaluation,
    fold_partition,
    import_evaluation,
    load_prompts,
    partition_order,
    prompt_manifest,
    render_responses,
)
from buddha.evaluation import (
    EvaluationProtocol,
    RunSummary,
    ValidationError,
    _integer,
    _sequence,
    _text,
    score_sequence,
)
from buddha.ledger import Ledger
from buddha.provider import BudgetBroker, Call, HTTPTransport, ModelSpec, Reply, Transport

Execute = Callable[[str, str, int, Call], Reply]
Generate = Callable[[Prompt, Sequence[str]], Call]

DATASETS = {
    "curated": (
        "curated.jsonl",
        "ca9b6f470e5d7f7e34a281e2fdaa6f6e51c38bdae075ea580d184139ec391fa7",
    ),
    "wildchat": (
        "wildchat-1k.jsonl",
        "8534288089508df3f413c1151a58d5fa5bda9d8f8385ae2815384d4e310a54ca",
    ),
}


def _sha(value: object) -> str:
    return hashlib.sha256(_canonical(value)).hexdigest()


def _model(value: object) -> ModelSpec:
    raw = _object(value)
    if set(raw) != set(ModelSpec.__dataclass_fields__):
        raise ValidationError("model specification has missing or unexpected fields")
    return ModelSpec(
        provider=_text(raw["provider"], "provider"),
        model=_text(raw["model"], "model"),
        input_token_ceiling=_integer(raw["input_token_ceiling"], "input ceiling", 1),
        max_output_tokens=_integer(raw["max_output_tokens"], "output ceiling", 1),
        input_microusd_per_million=_integer(raw["input_microusd_per_million"], "input rate", 0),
        output_microusd_per_million=_integer(raw["output_microusd_per_million"], "output rate", 0),
        bounds_source=_text(raw["bounds_source"], "bounds source"),
    )


@dataclass(frozen=True)
class RunSettings:
    generation: ModelSpec
    partition: ModelSpec
    quality: ModelSpec
    budget_microusd: int
    max_calls: int
    bounds_verified: bool
    ordering_seed: int | None = None
    bounds_checked_on: str = ""

    def __post_init__(self) -> None:
        if any(not isinstance(spec, ModelSpec) for spec in self.profiles()):
            raise ValidationError("all roles require model specifications")
        _integer(self.budget_microusd, "budget_microusd", 0)
        _integer(self.max_calls, "max_calls", 0)
        if type(self.bounds_verified) is not bool or not isinstance(self.bounds_checked_on, str):
            raise ValidationError("invalid bounds-verification fields")
        if self.ordering_seed is not None:
            _integer(self.ordering_seed, "ordering_seed", 0)
        if [s.max_output_tokens for s in self.profiles()] != [4096, 16000, 16000]:
            raise ValidationError(
                "v1.1 baseline requires 4096 generation and 16000 judge token caps"
            )

    def profiles(self) -> tuple[ModelSpec, ModelSpec, ModelSpec]:
        return self.generation, self.partition, self.quality

    @classmethod
    def from_record(cls, value: object) -> "RunSettings":
        raw = _object(value)
        if set(raw) != set(cls.__dataclass_fields__):
            raise ValidationError("run settings have missing or unexpected fields")
        seed = raw["ordering_seed"]
        if seed is not None:
            seed = _integer(seed, "ordering_seed", 0)
        if type(raw["bounds_verified"]) is not bool:
            raise ValidationError("bounds_verified must be boolean")
        checked = raw["bounds_checked_on"]
        if not isinstance(checked, str):
            raise ValidationError("bounds_checked_on must be text")
        return cls(
            _model(raw["generation"]),
            _model(raw["partition"]),
            _model(raw["quality"]),
            _integer(raw["budget_microusd"], "budget_microusd", 0),
            _integer(raw["max_calls"], "max_calls", 0),
            raw["bounds_verified"],
            seed,
            checked,
        )

    def permit_live(self) -> None:
        if not self.bounds_verified or self.budget_microusd <= 0 or self.max_calls <= 0:
            raise ValidationError(
                "live execution requires a positive explicit cap and verified bounds"
            )
        try:
            checked = date.fromisoformat(self.bounds_checked_on)
        except ValueError:
            raise ValidationError("live bounds require a verification date") from None
        if not -1 <= (datetime.now(UTC).date() - checked).days <= 7:
            raise ValidationError("model and pricing bounds must be reverified within seven days")
        supported = {
            ("openai", DEFAULT_PARTITION_MODEL): (1050000, 500000, 1800000),
            ("anthropic", DEFAULT_QUALITY_MODEL): (1000000, 10000000, 25000000),
        }
        if (self.partition.provider, self.partition.model) != ("openai", DEFAULT_PARTITION_MODEL):
            raise ValidationError("live partition judge must match the pinned v1.1 reference")
        if (self.quality.provider, self.quality.model) != ("anthropic", DEFAULT_QUALITY_MODEL):
            raise ValidationError("live quality judge must match the pinned v1.1 reference")
        for spec in self.profiles():
            bounds = supported.get((spec.provider, spec.model))
            if bounds is None or any(
                current < floor
                for current, floor in zip(
                    (
                        spec.input_token_ceiling,
                        spec.input_microusd_per_million,
                        spec.output_microusd_per_million,
                    ),
                    bounds,
                    strict=True,
                )
            ):
                raise ValidationError(
                    "model context and maximum-rate bounds are unsupported or too low"
                )


def generation_config(settings: RunSettings) -> dict[str, object]:
    # These are the current upstream regenerate parameters, including its doubled
    # low-reasoning budget. No extra generation instructions are inserted.
    return {
        "stage": "generation",
        "version": 2,
        "model": settings.generation.model,
        "mode": settings.generation.provider,
        "sampling": "regenerate",
        "num_generations": 10,
        "temperature": None,
        "max_tokens": 2048,
        "reasoning_effort": "low",
        "buddha_service_tiers": {"openai": "default", "anthropic": "standard_only"},
        # Bind all effective judging settings too, since they change the instrument.
        "buddha_judging": {
            "partition_max_output_tokens": settings.partition.max_output_tokens,
            "partition_effort": "provider_default",
            "quality_max_output_tokens": 16000,
            "quality_effort": "high",
            "ordering_seed": settings.ordering_seed,
            "fallback": "disabled",
            "partition_repair": "disabled",
        },
    }


def _protocol(
    settings: RunSettings, dataset_hash: str, prompts: Sequence[Prompt]
) -> EvaluationProtocol:
    return EvaluationProtocol(
        upstream_commit=UPSTREAM_COMMIT,
        metric_version=METRIC_VERSION,
        dataset_sha256=dataset_hash,
        split_sha256=_sha([asdict(p) for p in prompts]),
        partition_model=settings.partition.model,
        quality_model=settings.quality.model,
        partition_prompt_sha256=hashlib.sha256(PARTITION_SYSTEM.encode()).hexdigest(),
        quality_prompt_sha256=hashlib.sha256(SCORE_SYSTEM.encode()).hexdigest(),
        generation_config_sha256=_sha(generation_config(settings)),
        fallback_policy_sha256=_sha({"fallback": "disabled", "retry": "none", "repair": "none"}),
        ordering_seed=settings.ordering_seed,
    )


def prepare_run(
    destination: Path,
    *,
    dataset_path: Path,
    expected_dataset_sha256: str,
    settings: RunSettings,
    prompt_ids: Sequence[str] | None = None,
    synthetic: bool = False,
) -> Path:
    if not isinstance(settings, RunSettings) or type(synthetic) is not bool:
        raise ValidationError("invalid run preparation settings")
    prompts = load_prompts(dataset_path, expected_sha256=expected_dataset_sha256)
    if not synthetic and expected_dataset_sha256 not in {value[1] for value in DATASETS.values()}:
        raise ValidationError("non-synthetic preparation requires a pinned official dataset")
    if prompt_ids is not None:
        available = {p.id: p for p in prompts}
        if (
            not prompt_ids
            or isinstance(prompt_ids, (str, bytes))
            or any(not isinstance(i, str) for i in prompt_ids)
            or len(set(prompt_ids)) != len(prompt_ids)
            or any(i not in available for i in prompt_ids)
        ):
            raise ValidationError("selected prompt IDs must be unique and present in the dataset")
        prompts = tuple(available[i] for i in prompt_ids)
    protocol = _protocol(settings, expected_dataset_sha256, prompts)
    manifest = {
        "format": "buddha.baseline.v1",
        "run_id": uuid.uuid4().hex,
        "synthetic": synthetic,
        "population": "development",
        "settings": asdict(settings),
        "protocol": asdict(protocol),
        "prompts": [asdict(p) for p in prompts],
        "generation_config": generation_config(settings),
    }
    encoded = _canonical(manifest) + b"\n"
    try:
        destination.mkdir(parents=True, exist_ok=False)
    except FileExistsError:
        raise ValidationError("run directory already exists; resume it instead") from None
    with (destination / "manifest.json").open("xb") as stream:
        stream.write(encoded)
        stream.flush()
        os.fsync(stream.fileno())
    # A verified source snapshot binds the embedded subset back to the real data.
    # Keeping only a declared dataset hash would permit arbitrary substituted prompts.
    with (destination / "dataset.jsonl").open("xb") as stream:
        raw_dataset = dataset_path.read_bytes()
        if hashlib.sha256(raw_dataset).hexdigest() != expected_dataset_sha256:
            raise ValidationError("dataset changed during preparation")
        stream.write(raw_dataset)
        stream.flush()
        os.fsync(stream.fileno())
    return destination


def load_run(
    directory: Path,
) -> tuple[dict[str, object], RunSettings, tuple[Prompt, ...], EvaluationProtocol]:
    manifest = _object(_parse((directory / "manifest.json").read_bytes()))
    if (
        set(manifest)
        != {
            "format",
            "run_id",
            "synthetic",
            "population",
            "settings",
            "protocol",
            "prompts",
            "generation_config",
        }
        or manifest["format"] != "buddha.baseline.v1"
    ):
        raise ValidationError("unsupported or malformed baseline manifest")
    if type(manifest["synthetic"]) is not bool or manifest["population"] != "development":
        raise ValidationError("slice 2 accepts development baselines only")
    _text(manifest["run_id"], "run ID")
    settings = RunSettings.from_record(manifest["settings"])
    raw_prompts = manifest["prompts"]
    if not isinstance(raw_prompts, list):
        raise ValidationError("manifest prompts must be a list")
    prompts = tuple(
        Prompt(_text(_object(p).get("id"), "ID"), _text(_object(p).get("prompt"), "prompt"))
        for p in raw_prompts
    )
    prompt_manifest(prompts)
    raw_protocol = _object(manifest["protocol"])
    dataset_hash = _text(raw_protocol.get("dataset_sha256"), "dataset hash")
    original = {
        p.id: p.prompt
        for p in load_prompts(directory / "dataset.jsonl", expected_sha256=dataset_hash)
    }
    if any(original.get(p.id) != p.prompt for p in prompts):
        raise ValidationError("selected prompts do not belong to the verified source snapshot")
    protocol = _protocol(settings, dataset_hash, prompts)
    if not manifest["synthetic"] and dataset_hash not in {value[1] for value in DATASETS.values()}:
        raise ValidationError("manifest references an unsupported official dataset")
    if _canonical(raw_protocol) != _canonical(asdict(protocol)) or (
        _canonical(manifest["generation_config"]) != _canonical(generation_config(settings))
    ):
        raise ValidationError("manifest configuration or protocol mismatch")
    return manifest, settings, prompts, protocol


def _schema(kind: str) -> dict[str, object]:
    field = (
        {"type": "integer", "title": "Score"}
        if kind == "Score"
        else {
            "items": {"items": {"type": "integer"}, "type": "array"},
            "title": "Groups",
            "type": "array",
        }
    )
    key = "score" if kind == "Score" else "groups"
    return {
        "properties": {key: field},
        "required": [key],
        "title": kind,
        "type": "object",
        "additionalProperties": False,
    }


def _generation(
    spec: ModelSpec, prompt: str, *, instructions: str = "", history: Sequence[str] = ()
) -> Call:
    _utf8(_text(prompt, "prompt"))
    if type(instructions) is not str:
        raise ValidationError("generation instructions must be text")
    _utf8(instructions)
    messages: list[dict[str, object]] = [{"role": "user", "content": prompt}]
    for response in _sequence(history, "generation history"):
        if type(response) is not str:
            raise ValidationError("generation history must contain text responses")
        _utf8(response)
        messages.extend(
            [
                {"role": "assistant", "content": response},
                {"role": "user", "content": "Can you generate a different answer?"},
            ]
        )
    body: dict[str, object] = {
        "model": spec.model,
        "messages": messages,
    }
    if spec.provider == "anthropic":
        body |= {
            "service_tier": "standard_only",
            "max_tokens": spec.max_output_tokens,
            "thinking": {"type": "adaptive"},
            "output_config": {"effort": "low"},
        }
        messages[-1]["content"] = [
            {
                "type": "text",
                "text": messages[-1]["content"],
                "cache_control": {"type": "ephemeral"},
            }
        ]
        if instructions:
            body["system"] = instructions
    else:
        if instructions:
            messages.insert(0, {"role": "system", "content": instructions})
        body |= {
            "max_completion_tokens": spec.max_output_tokens,
            "reasoning_effort": "low",
            "service_tier": "default",
        }
    return Call(spec, _canonical(body).decode())


def _judge(spec: ModelSpec, system: str, user: str, kind: str) -> Call:
    body: dict[str, object] = {"model": spec.model, "messages": [{"role": "user", "content": user}]}
    schema = _schema(kind)
    if spec.provider == "anthropic":
        body |= {
            "service_tier": "standard_only",
            "max_tokens": spec.max_output_tokens,
            "system": system,
            "thinking": {"type": "adaptive"},
            "output_config": {
                "effort": "high",
                "format": {"type": "json_schema", "schema": schema},
            },
        }
    else:
        body |= {
            "service_tier": "default",
            "max_completion_tokens": spec.max_output_tokens,
            "messages": [{"role": "system", "content": system}, {"role": "user", "content": user}],
            "response_format": {
                "type": "json_schema",
                "json_schema": {"name": kind, "strict": True, "schema": schema},
            },
        }
    return Call(spec, _canonical(body).decode())


def _judgment(reply: Reply) -> dict[str, object]:
    if (
        not isinstance(reply, Reply)
        or reply.refused
        or (reply.finish_reason not in {"stop", "end_turn"})
    ):
        raise ValidationError("judge refused or did not finish; evaluation is incomplete")
    return _object(_parse(_utf8(reply.text)))


def operation_executor(
    broker: BudgetBroker, settings: RunSettings, *, namespace: Sequence[object]
) -> Execute:
    if not isinstance(broker, BudgetBroker) or not isinstance(settings, RunSettings):
        raise ValidationError("execution requires a broker and run settings")
    prefix = _sequence(_parse(_canonical(_sequence(namespace, "namespace"))), "namespace")
    if not prefix:
        raise ValidationError("operation namespace must not be empty")
    credentials_checked = False

    def execute(prompt_id: str, stage: str, index: int, call: Call) -> Reply:
        nonlocal credentials_checked
        _text(prompt_id, "prompt ID")
        _text(stage, "stage")
        _integer(index, "operation index", 0)
        operation_id = _sha([*prefix, prompt_id, stage, index])
        saved = broker.ledger.get(operation_id)
        if (saved is None or saved.status == "reserved") and not credentials_checked:
            broker.authorize(call)
            if isinstance(broker.transport, HTTPTransport):
                broker.transport.preflight(_generation(settings.generation, "preflight"))
                broker.transport.preflight(
                    _judge(settings.partition, PARTITION_SYSTEM, "preflight", "Partition")
                )
                broker.transport.preflight(
                    _judge(settings.quality, SCORE_SYSTEM, "preflight", "Score")
                )
            credentials_checked = True
        return broker.execute(operation_id, call)

    return execute


def evaluate_prompts(
    prompts: Sequence[Prompt],
    *,
    settings: RunSettings,
    protocol: EvaluationProtocol,
    execute: Execute,
    generate: Generate | None = None,
) -> list[dict[str, object]]:
    if (
        not isinstance(settings, RunSettings)
        or not callable(execute)
        or (generate is not None and not callable(generate))
    ):
        raise ValidationError("evaluation requires settings and callable execution")
    _check_protocol(protocol)
    if (
        protocol.k != 10
        or protocol.patience != 0.8
        or (
            protocol.partition_model != settings.partition.model
            or protocol.quality_model != settings.quality.model
        )
    ):
        raise ValidationError("evaluation requires the v1.1 measurement settings")
    prompt_manifest(prompts)
    rows: list[dict[str, object]] = []
    for prompt in prompts:
        generations = []
        previous: list[str] = []
        for index in range(10):
            call = (
                _generation(settings.generation, prompt.prompt)
                if generate is None
                else generate(prompt, tuple(previous))
            )
            if not isinstance(call, Call) or call.spec != settings.generation:
                raise ValidationError("generation cannot change the configured model or bounds")
            reply = execute(prompt.id, "generation", index, call)
            if not isinstance(reply, Reply) or reply.finish_reason not in {
                "stop",
                "end_turn",
                "length",
                "max_tokens",
                "model_context_window_exceeded",
                "content_filter",
                "refusal",
            }:
                raise ValidationError("generator returned an unsupported completion status")
            _utf8(reply.text)
            generations.append(
                "[refused]" if reply.refused else (reply.text if reply.text.strip() else "[empty]")
            )
            previous.append(generations[-1])
        order = partition_order(prompt.prompt, 10, protocol.ordering_seed)
        partition_reply = execute(
            prompt.id,
            "partition",
            0,
            _judge(
                settings.partition,
                PARTITION_SYSTEM,
                render_responses(prompt.prompt, [generations[i] for i in order]),
                "Partition",
            ),
        )
        groups = _judgment(partition_reply)
        if set(groups) != {"groups"}:
            raise ValidationError("partition judge returned an unexpected schema")
        partition = fold_partition(
            groups["groups"], prompt=prompt.prompt, n=10, seed=protocol.ordering_seed
        )
        scores: list[int | None] = [None] * 10
        for index, label in enumerate(partition):
            if label in partition[:index]:
                continue
            quality = _judgment(
                execute(
                    prompt.id,
                    "score",
                    index,
                    _judge(
                        settings.quality,
                        SCORE_SYSTEM,
                        f"<prompt>\n{prompt.prompt}\n</prompt>\n\n<response>\n{generations[index]}\n</response>",
                        "Score",
                    ),
                )
            )
            if (
                set(quality) != {"score"}
                or type(quality["score"]) is not int
                or not 1 <= quality["score"] <= 10
            ):
                raise ValidationError("quality judge returned an invalid score")
            scores[index] = quality["score"]
        result = score_sequence(partition, scores)
        rows.append(
            {
                "id": prompt.id,
                "prompt": prompt.prompt,
                "model": settings.generation.model,
                "generations": generations,
                "partition": partition,
                "generation_scores": scores,
                "distinct": result.distinct,
                "utility": result.utility,
                "protocol_fingerprint": protocol.fingerprint(),
            }
        )
    return rows


def run_baseline(
    directory: Path,
    *,
    transport: Transport,
    allow_paid: bool = False,
    authorization: Authorization | None = None,
) -> RunSummary:
    manifest, settings, prompts, protocol = load_run(directory)
    if type(allow_paid) is not bool:
        raise ValidationError("allow_paid must be boolean")
    live = any(spec.provider != "replay" for spec in settings.profiles())
    if live:
        if not allow_paid:
            raise ValidationError("live model calls require explicit paid execution")
        settings.permit_live()
        if authorization is None:
            raise ValidationError("live evaluation requires shared authorization")
    elif not manifest["synthetic"]:
        raise ValidationError("replay transport is reserved for synthetic demonstrations")
    ledger = (
        authorization.for_run(directory)
        if authorization is not None
        else Ledger(
            directory / "operations.sqlite3",
            run_id=_text(manifest["run_id"], "run ID"),
            manifest_sha256=_sha(manifest),
            budget_microusd=settings.budget_microusd,
            max_calls=settings.max_calls,
        )
    )
    execute = operation_executor(
        BudgetBroker(ledger, transport), settings, namespace=(manifest["run_id"],)
    )
    rows = evaluate_prompts(prompts, settings=settings, protocol=protocol, execute=execute)
    export_evaluation(
        directory / "evaluation",
        protocol=protocol,
        rows=rows,
        generation_config=generation_config(settings),
    )
    summary, _ = import_evaluation(
        directory / "evaluation", protocol=protocol, expected_prompt_hashes=prompt_manifest(prompts)
    )
    return summary


class ReplayTransport:
    """Canned demonstration responses, never semantic judgments or model scores."""

    def __init__(self) -> None:
        self.calls = 0

    def send(self, call: Call) -> Reply:
        if call.spec.provider != "replay":
            raise ValidationError("replay cannot represent live model evidence")
        self.calls += 1
        body = _object(_parse(call.body_json.encode()))
        response_format = body.get("response_format")
        text = "An offline demonstration response."
        if isinstance(response_format, dict):
            name = _object(response_format.get("json_schema")).get("name")
            text = '{"score":8}' if name == "Score" else '{"groups":[[0,1,2,3,4,5,6,7,8,9]]}'
        return Reply(text, call.spec.model, f"replay-{self.calls}", 10, 5, "stop", False)
