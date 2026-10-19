"""Bounded declarative policy optimization on one locked development screen.

Candidate code never executes. Results are exploratory development measurements,
not held-out improvement claims. File checksums establish consistency, not origin
authentication against an operator who can rewrite the entire local experiment.
"""

import hashlib
import os
import tempfile
import uuid
from collections.abc import Iterator, Mapping, Sequence
from contextlib import contextmanager
from dataclasses import asdict, dataclass, replace
from pathlib import Path

from buddha import archive, benchmark, evaluation, ledger, policy, provider, run
from buddha import splits as split_tools
from buddha.archive import Candidate, active_pool, frontier, select_parent
from buddha.benchmark import (
    METRIC_VERSION,
    Prompt,
    _canonical,
    _object,
    _parse,
    export_evaluation,
    import_evaluation,
    load_prompts,
    prompt_manifest,
)
from buddha.evaluation import EvaluationProtocol, ValidationError, _hex, _integer, _text
from buddha.ledger import Ledger
from buddha.policy import MUTATION_SYSTEM, Policy, proposal_schema, propose_call
from buddha.provider import BudgetBroker, Call, Reply, Transport
from buddha.run import (
    DATASETS,
    Execute,
    RunSettings,
    _generation,
    _protocol,
    _sha,
    evaluate_prompts,
    generation_config,
    operation_executor,
)
from buddha.splits import freeze_splits, validate_splits


@dataclass(frozen=True)
class SearchSpec:
    iterations: int = 3
    max_active: int = 8
    seed: int = 7
    method: str = "archive"
    screen_size: int = 2

    def __post_init__(self) -> None:
        for name, minimum, maximum in (
            ("iterations", 0, 256),
            ("max_active", 2, 64),
            ("seed", 0, 2**63 - 1),
            ("screen_size", 1, 1000),
        ):
            if _integer(getattr(self, name), name, minimum) > maximum:
                raise ValidationError(f"{name} exceeds {maximum}")
        if type(self.method) is not str or self.method not in {"archive", "latest", "uninformed"}:
            raise ValidationError("unsupported search method")

    @classmethod
    def from_record(cls, value: object) -> "SearchSpec":
        raw = _object(value)
        if set(raw) != set(cls.__dataclass_fields__):
            raise ValidationError("search specification has missing or unexpected fields")
        return cls(
            _integer(raw["iterations"], "iterations", 0),
            _integer(raw["max_active"], "max_active", 2),
            _integer(raw["seed"], "seed", 0),
            _text(raw["method"], "method"),
            _integer(raw["screen_size"], "screen_size", 1),
        )


def _contracts() -> dict[str, object]:
    return {
        "system_sha256": hashlib.sha256(MUTATION_SYSTEM.encode()).hexdigest(),
        "proposal_schema_sha256": _sha(proposal_schema()),
        "source_sha256": {
            module.__name__: hashlib.sha256(
                Path(_text(module.__file__, "source path")).read_bytes()
            ).hexdigest()
            for module in (
                archive,
                benchmark,
                evaluation,
                ledger,
                policy,
                provider,
                run,
                split_tools,
            )
        },
        "controller_sha256": hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
        "parent_rule": "pareto-crowding-reserve20-uniform10-inverse-direct-children-v1",
        "proposal_role": "generation",
        "feedback": "selected-parent-common-development-only-or-empty-uninformed",
        "feedback_max_canonical_bytes": 200000,
        "seed_policies": [Policy().to_record(), Policy(sampling="in-context").to_record()],
    }


def _atomic(path: Path, raw: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.is_symlink():
        raise ValidationError("immutable artifact must not be a symlink")
    if path.exists():
        if not path.is_file() or path.read_bytes() != raw:
            raise ValidationError("immutable artifact conflicts; nothing overwritten")
        return
    descriptor, temporary = tempfile.mkstemp(prefix=".write-", dir=path.parent)
    try:
        with os.fdopen(descriptor, "wb") as stream:
            stream.write(raw)
            stream.flush()
            os.fsync(stream.fileno())
        try:
            os.link(temporary, path)
        except FileExistsError:
            if path.is_symlink() or path.read_bytes() != raw:
                raise ValidationError("concurrent immutable artifact conflict") from None
    finally:
        Path(temporary).unlink()


def _put(path: Path, value: dict[str, object]) -> None:
    _atomic(path, _canonical(value | {"record_sha256": _sha(value)}) + b"\n")


def _read(path: Path) -> dict[str, object]:
    value = _object(_parse(path.read_bytes()))
    checksum = value.pop("record_sha256", None)
    if checksum != _sha(value):
        raise ValidationError("immutable record checksum mismatch")
    return value


@contextmanager
def _lock(directory: Path) -> Iterator[None]:
    path = directory / ".search.lock"
    try:
        descriptor = os.open(path, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
    except FileExistsError:
        raise ValidationError(
            "another search owns .search.lock; review stale locks manually"
        ) from None
    try:
        os.close(descriptor)
        yield
    finally:
        path.unlink()


def _comparison(
    settings: RunSettings, source_hash: str, prompts: Sequence[Prompt], contracts: object
) -> str:
    instrument: dict[str, object] = asdict(_protocol(settings, source_hash, prompts))
    instrument.pop("generation_config_sha256")
    return _sha({"instrument": instrument, "settings": asdict(settings), "contracts": contracts})


def prepare_search(
    destination: Path,
    *,
    dataset_path: Path,
    expected_dataset_sha256: str,
    settings: RunSettings,
    spec: SearchSpec,
    splits: object = None,
    families: Mapping[str, str] | None = None,
    synthetic: bool = False,
) -> Path:
    if (
        type(spec) is not SearchSpec
        or not isinstance(settings, RunSettings)
        or type(synthetic) is not bool
    ):
        raise ValidationError("invalid search preparation settings")
    prompts = load_prompts(dataset_path, expected_sha256=expected_dataset_sha256)
    if not synthetic and expected_dataset_sha256 not in {item[1] for item in DATASETS.values()}:
        raise ValidationError("official search requires a pinned official dataset")
    assigned = validate_splits(
        prompts,
        freeze_splits(prompts, seed=spec.seed, families=families) if splits is None else splits,
        families=families,
    )
    screen_ids = assigned["development"][: spec.screen_size]
    if len(screen_ids) != spec.screen_size:
        raise ValidationError("screen_size exceeds development prompt count")
    available = {prompt.id: prompt for prompt in prompts}
    screen = tuple(available[item] for item in screen_ids)
    contracts = _contracts()
    manifest: dict[str, object] = {
        "format": "buddha.policy-search.v1",
        "run_id": uuid.uuid4().hex,
        "population": "development",
        "synthetic": synthetic,
        "settings": asdict(settings),
        "spec": asdict(spec),
        "source_sha256": expected_dataset_sha256,
        "splits": assigned,
        "families": None if families is None else dict(families),
        "screen_ids": screen_ids,
        "contracts": contracts,
        "comparison_key": _comparison(settings, expected_dataset_sha256, screen, contracts),
    }
    raw = dataset_path.read_bytes()
    if hashlib.sha256(raw).hexdigest() != expected_dataset_sha256:
        raise ValidationError("source changed during preparation")
    try:
        destination.mkdir(parents=True, exist_ok=False)
    except FileExistsError:
        raise ValidationError("search directory exists; resume it instead") from None
    _atomic(destination / "dataset.jsonl", raw)
    _put(destination / "manifest.json", manifest)
    _ledger(destination, manifest, settings)
    return destination


def load_search(
    directory: Path,
) -> tuple[dict[str, object], RunSettings, SearchSpec, tuple[Prompt, ...]]:
    if directory.is_symlink() or any(path.is_symlink() for path in directory.rglob("*")):
        raise ValidationError("search artifacts must not contain symlinks")
    manifest = _read(directory / "manifest.json")
    if (
        set(manifest)
        != {
            "format",
            "run_id",
            "population",
            "synthetic",
            "settings",
            "spec",
            "source_sha256",
            "splits",
            "families",
            "screen_ids",
            "contracts",
            "comparison_key",
        }
        or manifest["format"] != "buddha.policy-search.v1"
    ):
        raise ValidationError("unsupported search manifest")
    _text(manifest["run_id"], "run ID")
    if type(manifest["synthetic"]) is not bool or manifest["population"] != "development":
        raise ValidationError("search accepts development population only")
    settings, spec = (
        RunSettings.from_record(manifest["settings"]),
        SearchSpec.from_record(manifest["spec"]),
    )
    source_hash = _text(manifest["source_sha256"], "source hash")
    prompts = load_prompts(directory / "dataset.jsonl", expected_sha256=source_hash)
    if not manifest["synthetic"] and source_hash not in {item[1] for item in DATASETS.values()}:
        raise ValidationError("unsupported official source")
    raw_families = manifest["families"]
    families = (
        None
        if raw_families is None
        else {key: _text(value, "family") for key, value in _object(raw_families).items()}
    )
    assigned = validate_splits(prompts, manifest["splits"], families=families)
    ids = assigned["development"][: spec.screen_size]
    if len(ids) != spec.screen_size or manifest["screen_ids"] != ids:
        raise ValidationError("common screen is inconsistent with development split")
    available = {prompt.id: prompt for prompt in prompts}
    screen = tuple(available[item] for item in ids)
    if manifest["contracts"] != _contracts() or manifest["comparison_key"] != _comparison(
        settings, source_hash, screen, manifest["contracts"]
    ):
        raise ValidationError("frozen implementation or comparison controls changed")
    return manifest, settings, spec, screen


def _ledger(directory: Path, manifest: dict[str, object], settings: RunSettings) -> Ledger:
    return Ledger(
        directory / "operations.sqlite3",
        run_id=_text(manifest["run_id"], "run ID"),
        manifest_sha256=_sha(manifest),
        budget_microusd=settings.budget_microusd,
        max_calls=settings.max_calls,
    )


def _configuration(
    settings: RunSettings, selected: Policy, manifest: dict[str, object]
) -> dict[str, object]:
    return generation_config(settings) | {
        "sampling": selected.sampling,
        "buddha_policy": selected.to_record(),
        "buddha_template": manifest["contracts"],
    }


def _candidate_protocol(
    settings: RunSettings, selected: Policy, manifest: dict[str, object], prompts: Sequence[Prompt]
) -> EvaluationProtocol:
    return replace(
        _protocol(settings, _text(manifest["source_sha256"], "source hash"), prompts),
        generation_config_sha256=_sha(_configuration(settings, selected, manifest)),
    )


def _preflight(
    directory: Path, manifest: dict[str, object], settings: RunSettings, prompts: Sequence[Prompt]
) -> None:
    for path in (directory / "decisions").glob("*.json"):
        _read(path)
    if (directory / "report.json").exists():
        _read(directory / "report.json")
    for candidate_dir in (directory / "candidates").glob("*"):
        _hex(candidate_dir.name, "candidate directory")
        if not candidate_dir.is_dir():
            raise ValidationError("candidate artifact must be a directory")
        path = candidate_dir / "policy.json"
        if not path.exists() and all(
            item.is_file() and item.name.startswith(".write-") for item in candidate_dir.iterdir()
        ):
            continue  # Interrupted creation before the first atomic file publication.
        selected = Policy.from_record(_read(path))
        if candidate_dir.name != selected.fingerprint():
            raise ValidationError("candidate policy identity mismatch")
        if (candidate_dir / "evaluation").exists():
            import_evaluation(
                candidate_dir / "evaluation",
                protocol=_candidate_protocol(settings, selected, manifest, prompts),
                expected_prompt_hashes=prompt_manifest(prompts),
            )


class _NeedsCall(Exception):
    pass


class _RejectTransport:
    def send(self, call: Call) -> Reply:
        raise ValidationError("offline inspection cannot send model requests")


class _CachedBroker(BudgetBroker):
    def execute(self, operation_id: str, call: Call) -> Reply:
        saved = self.ledger.get(operation_id)
        if saved is None or saved.status != "completed":
            raise _NeedsCall
        return super().execute(operation_id, call)


def _walk(
    directory: Path,
    manifest: dict[str, object],
    settings: RunSettings,
    spec: SearchSpec,
    prompts: tuple[Prompt, ...],
    broker: BudgetBroker,
) -> dict[str, object]:
    candidates: list[Candidate] = []
    policies: dict[str, Policy] = {}
    evidence: dict[str, list[dict[str, object]]] = {}
    summaries: dict[str, dict[str, object]] = {}
    decisions: list[dict[str, object]] = []
    billed: dict[str, tuple[str, int, str | None]] = {}

    def metered(namespace: Sequence[object], candidate_id: str | None = None) -> Execute:
        invoke = operation_executor(broker, settings, namespace=namespace)

        def execute(prompt_id: str, stage: str, index: int, call: Call) -> Reply:
            reply = invoke(prompt_id, stage, index, call)
            operation_id = _sha([*namespace, prompt_id, stage, index])
            operation = broker.ledger.get(operation_id)
            if (
                operation is None
                or operation.status != "completed"
                or operation.actual_microusd is None
            ):
                raise ValidationError("completed request lacks a recorded charge")
            billed[operation_id] = (stage, operation.actual_microusd, candidate_id)
            return reply

        return execute

    def admit(selected: Policy, parent_id: str | None) -> None:
        candidate_id = selected.fingerprint()
        candidate_dir = directory / "candidates" / candidate_id
        _put(candidate_dir / "policy.json", selected.to_record())
        protocol = _candidate_protocol(settings, selected, manifest, prompts)
        execute = metered([manifest["run_id"], "candidate", candidate_id], candidate_id)

        def generate(prompt: Prompt, previous: Sequence[str]) -> Call:
            return _generation(
                settings.generation,
                prompt.prompt,
                instructions=selected.instructions,
                history=previous if selected.sampling == "in-context" else (),
            )

        rows = evaluate_prompts(
            prompts, settings=settings, protocol=protocol, execute=execute, generate=generate
        )
        export_evaluation(
            candidate_dir / "evaluation",
            protocol=protocol,
            rows=rows,
            generation_config=_configuration(settings, selected, manifest),
        )
        summary, checked = import_evaluation(
            candidate_dir / "evaluation",
            protocol=protocol,
            expected_prompt_hashes=prompt_manifest(prompts),
        )
        candidates.append(
            Candidate(candidate_id, parent_id, summary.mean_utility, summary.mean_distinct)
        )
        policies[candidate_id], evidence[candidate_id] = selected, checked
        summaries[candidate_id] = asdict(summary)

    for index, seed_policy in enumerate((Policy(), Policy(sampling="in-context"))):
        admit(seed_policy, None)
        _put(
            directory / "decisions" / f"seed-{index}.json",
            {
                "status": "admitted",
                "candidate_id": seed_policy.fingerprint(),
                "parent_id": None,
                "comparison_key": manifest["comparison_key"],
            },
        )
    for iteration in range(spec.iterations):
        parent = select_parent(
            candidates,
            method=spec.method,
            max_active=spec.max_active,
            seed=spec.seed,
            iteration=iteration,
        )
        decision_path = directory / "decisions" / f"iteration-{iteration:06d}.json"
        saved_decision = _read(decision_path) if decision_path.exists() else None
        if saved_decision is not None and any(
            saved_decision.get(key) != value
            for key, value in {
                "iteration": iteration,
                "parent_id": parent.candidate_id,
                "comparison_key": manifest["comparison_key"],
            }.items()
        ):
            raise ValidationError("saved proposal decision conflicts with search history")
        feedback = [] if spec.method == "uninformed" else evidence[parent.candidate_id]
        call = propose_call(
            settings.generation,
            parent=policies[parent.candidate_id],
            feedback=feedback,
            method=spec.method,
        )
        execute = metered([manifest["run_id"], "proposal", iteration])
        reply = execute("development", "proposal", 0, call)
        decision: dict[str, object] = {
            "iteration": iteration,
            "parent_id": parent.candidate_id,
            "proposal_sha256": hashlib.sha256(
                reply.text.encode(errors="surrogatepass")
            ).hexdigest(),
            "comparison_key": manifest["comparison_key"],
        }
        # Paid-operation failures above propagate. Only completed semantic output
        # is eligible for invalid-proposal classification and iteration consumption.
        child: Policy | None = None
        try:
            if reply.refused or reply.finish_reason not in {"stop", "end_turn"}:
                raise ValidationError("proposer did not return a complete policy")
            selected = Policy.from_record(_parse(reply.text.encode()))
        except (ValidationError, UnicodeError):
            decision["status"] = "invalid"
        else:
            candidate_id = selected.fingerprint()
            decision["candidate_id"] = candidate_id
            decision["policy"] = selected.to_record()
            if candidate_id in policies:
                decision["status"] = "duplicate"
            else:
                decision["status"] = "admitted"
                child = selected
        if saved_decision is not None and saved_decision != decision:
            raise ValidationError("saved decision differs from its completed proposal receipt")
        if child is not None:
            admit(child, parent.candidate_id)
        _put(decision_path, decision)
        decisions.append(decision)
    totals = broker.ledger.totals()
    by_stage = {
        stage: sum(amount for recorded, amount, _ in billed.values() if recorded == stage)
        for stage in ("proposal", "generation", "partition", "score")
    }
    by_candidate = {
        item.candidate_id: sum(
            amount for _, amount, owner in billed.values() if owner == item.candidate_id
        )
        for item in candidates
    }
    if (
        sum(by_stage.values()) != totals["spent_microusd"]
        or totals["reserved_microusd"]
        or len(billed) != totals["operation_count"]
    ):
        raise ValidationError(
            "complete search expenditure does not reconcile with its global ledger"
        )
    costs: dict[str, object] = dict(totals)
    costs.update(
        {
            "by_stage_microusd": by_stage,
            "by_candidate_microusd": by_candidate,
            "seed_evaluation_microusd": sum(
                by_candidate[item.candidate_id] for item in candidates[:2]
            ),
            "child_evaluation_microusd": sum(
                by_candidate[item.candidate_id] for item in candidates[2:]
            ),
            "proposal_microusd": by_stage["proposal"],
        }
    )
    report: dict[str, object] = {
        "format": "buddha.policy-search-report.v1",
        "status": "complete",
        "synthetic": manifest["synthetic"],
        "run_id": manifest["run_id"],
        "metric_version": METRIC_VERSION,
        "method": spec.method,
        "comparison_key": manifest["comparison_key"],
        "screen_ids": manifest["screen_ids"],
        "spec": asdict(spec),
        "candidates": [
            asdict(item)
            | {
                "summary": summaries[item.candidate_id],
                "evaluation_microusd": by_candidate[item.candidate_id],
            }
            for item in candidates
        ],
        "active_ids": [
            item.candidate_id for item in active_pool(candidates, max_active=spec.max_active)
        ],
        "frontier_ids": [item.candidate_id for item in frontier(candidates)],
        "decisions": decisions,
        "costs": costs,
        "claim": "exploratory development measurements; no held-out improvement claim",
    }
    _put(directory / "report.json", report)
    return report


def run_search(
    directory: Path, *, transport: Transport, allow_paid: bool = False
) -> dict[str, object]:
    if type(allow_paid) is not bool:
        raise ValidationError("allow_paid must be boolean")
    with _lock(directory):
        manifest, settings, spec, prompts = load_search(directory)
        if any(item.provider != "replay" for item in settings.profiles()):
            if not allow_paid:
                raise ValidationError("live search requires explicit paid execution")
            settings.permit_live()
        elif not manifest["synthetic"]:
            raise ValidationError("replay is reserved for synthetic demonstrations")
        ledger = _ledger(directory, manifest, settings)
        _preflight(directory, manifest, settings, prompts)
        return _walk(directory, manifest, settings, spec, prompts, BudgetBroker(ledger, transport))


def inspect_search(directory: Path) -> dict[str, object]:
    """Replay completed receipts offline; stop before reserving any missing work."""
    with _lock(directory):
        manifest, settings, spec, prompts = load_search(directory)
        ledger = _ledger(directory, manifest, settings)
        _preflight(directory, manifest, settings, prompts)
        try:
            return _walk(
                directory,
                manifest,
                settings,
                spec,
                prompts,
                _CachedBroker(ledger, _RejectTransport()),
            )
        except _NeedsCall:
            return {
                "status": "incomplete",
                "synthetic": manifest["synthetic"],
                "run_id": manifest["run_id"],
                "metric_version": METRIC_VERSION,
                "method": spec.method,
                "screen_ids": manifest["screen_ids"],
                "costs": ledger.totals(),
            }
