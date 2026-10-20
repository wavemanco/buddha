"""Read-only consistency checks for sealed, declared legacy v1.1 search evidence.

This is not execution, provider authentication or a semantic judgment audit.
Only trusted installed pure recipes consume saved replies. Archived code is data.
"""

import hashlib
import sqlite3
import zipfile
import zlib
from collections.abc import Sequence
from dataclasses import asdict, dataclass, replace
from pathlib import Path

from buddha.archive import Candidate, active_pool, frontier, select_parent
from buddha.authorization import _signature
from buddha.benchmark import (
    _ARTIFACTS,
    METRIC_VERSION,
    Prompt,
    _jsonl,
    import_evaluation_bytes,
    prompt_manifest,
)
from buddha.common import ValidationError, _canonical, _hex, _integer, _object, _parse, _text
from buddha.continuation import (
    _ACCEPTANCE_REASON,
    _BENCHMARK_BYTES_REVISION,
    _GENERIC_EXTRACTION_MODULES,
    _METADATA_KEYS,
    InheritedReference,
    ReplacementReference,
    Source,
    _context,
    _snapshot_bytes,
)
from buddha.history import HistoricalOperation, History, _amount, _read_database
from buddha.policy import MUTATION_SYSTEM, Policy, proposal_schema, propose_call
from buddha.provider import BudgetBroker, Call, Reply
from buddha.run import DATASETS, Execute, RunSettings, _generation, _sha, evaluate_prompts
from buddha.search import SearchSpec, _candidate_protocol, _comparison
from buddha.search_evidence import (
    SealedEvidence,
    SealedRun,
    _local_binding,
    read_authority,
    read_search_evidence,
)
from buddha.splits import validate_splits

_FINANCIALS = ("committed_microusd", "spent_microusd", "reserved_microusd", "operation_count")
_CLAIM = "saved-evidence consistency only; no provider or semantic attestation"
_CONTROLS = {
    "system_sha256": "8f8cfd4484326b753d4bbb741cbadebe07d9b60a8b95316f7ba7b4caab213318",
    "proposal_schema_sha256": "c7114823510ca143f2b18027aff226591229c2144864214176a7d4d6fbecf228",
    "parent_rule": "pareto-crowding-reserve20-uniform10-inverse-direct-children-v1",
    "proposal_role": "generation",
    "feedback": "selected-parent-common-development-only-or-empty-uninformed",
    "feedback_max_canonical_bytes": 200000,
}
# Explicit reviewed legacy profiles, independent of whole installed-runtime identity.
# Source digests are provenance, not proof that the historical program executed.
_SOURCES = {
    "buddha.archive": {"9549deb0f347cf6114ef3f802b9dfef8a94e0db7cbbd3497697987d5e21ba2ee"},
    "buddha.benchmark": {
        "9e131a9f4fd92197b256518ea778984875d9aee2a58efb3ccc759d6553a79ae2",
        "15b57b974c702d69c7b9e172c73798bd555db5eedb3286bd8c792d1fe0568763",
        "b72c74a0b9b7e786b9969c72a400f449ab5758938ee9f24af660a887d866c2a9",
        "7ef7e26b2ef3cbf4119118a985334048fd30b68a5629f3e3196fa77e8200c49f",
    },
    "buddha.evaluation": {
        "87e23a9afbdbc466da7ed44cc1bb2b2fd8622d480efd9db95155d75ddda77e78",
        "4cabb1a48689a140fc6f6129ed8d9eae1d047d3e09eae794170c74479413b8d6",
    },
    "buddha.policy": {"717f6fdad1e880d83326d6a314e0dfa604be1044f8209f27061380e16cfebb3e"},
    "buddha.splits": {"419fa286d812b43e3095fbb41a62844b40477f880d94c8d60de069a52c324a2a"},
    "buddha.run": {
        "e270fa16b87a57efa50f9e372561afffdb308f9ce441d6783ba31773dfb005e3",
        "a972cb8d1a04bef7abad7efdf7f1eec803bb88cd55c30cf64148119a3d7c6dbb",
    },
    "buddha.provider": {
        "2477feaa8b16f3715f0ee2db5db7baedf3066969fd9128e6b773803ff2b3711f",
        "052b639a5c61317868ad19f8381aeecd6be880677eb642a07b65a2338b0bebd1",
        "17de071c1416afa32f9da32eb627e24264d8a0a848862fdf4853057125f18a02",
    },
    "buddha.ledger": {
        "7d53f6fd6b34e6ed7edd7bc44d1b7b0282e46a7d56f08fc664f244852fd1dcf4",
        "5909b46f6943a96d0f8bf26bc7eda136231fca3770f37c8439979431dde8fc0b",
        "5c7e56f1e2c5e68046d6380ebacc03110300eae34d348d7dca683a0591d64130",
    },
}
_CONTROLLERS = {
    "aca15a11fa46a270fa9989fe88ccc0ca2914cec91149868b34895403aaff1182",
    "ac7b3648355b139797773cbe2bb8b67abbc8533eefd987cd7692275692a9a95c",
}


class _Unsupported(Exception):
    pass


class _Missing(Exception):
    def __init__(self, slot: dict[str, object]) -> None:
        super().__init__("required evidence is not complete")
        self.slot = slot


@dataclass(frozen=True)
class SearchVerification:
    record_json: str

    @property
    def status(self) -> str:
        return _text(self.to_record()["status"], "verification status")

    def to_record(self) -> dict[str, object]:
        return _object(_parse(self.record_json.encode()))


def _record(raw: bytes) -> dict[str, object]:
    record = _object(_parse(raw))
    checksum = record.pop("record_sha256", None)
    if checksum != _sha(record):
        raise ValidationError("sealed record checksum mismatch")
    return record


def _financial(run: SealedRun) -> History:
    manifest = _record(run.blob("manifest.json"))
    settings = _object(manifest.get("settings"))
    run_id = _text(manifest.get("run_id"), "run ID")
    budget = _amount(settings.get("budget_microusd"), "historical budget")
    calls = _amount(settings.get("max_calls"), "historical call cap")
    ledger = run.blob("operations.sqlite3")
    return History(
        run_id,
        _sha(manifest),
        hashlib.sha256(ledger).hexdigest(),
        budget,
        calls,
        _read_database(ledger, run_id, _sha(manifest), budget, calls),
        _canonical(manifest).decode(),
    )


@dataclass(frozen=True)
class _Search:
    sealed: SealedRun
    history: History
    manifest: dict[str, object]
    settings: RunSettings
    spec: SearchSpec
    prompts: tuple[Prompt, ...]
    seeds: tuple[Policy, ...]


def _search(run: SealedRun, history: History) -> _Search:
    manifest = history.manifest
    if manifest.get("format") not in {
        "buddha.policy-search.v1",
        "buddha.policy-search-continuation.v1",
    }:
        raise _Unsupported("unsupported historical search format")
    linked = manifest["format"] == "buddha.policy-search-continuation.v1"
    if set(manifest) != {
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
    } | ({"continuation"} if linked else set()):
        raise ValidationError("search manifest has missing or unexpected fields")
    if type(manifest["synthetic"]) is not bool or manifest["population"] != "development":
        raise ValidationError("search evidence must declare its development population")
    contracts = _object(manifest["contracts"])
    if set(contracts) != set(_CONTROLS) | {"source_sha256", "controller_sha256", "seed_policies"}:
        raise _Unsupported("unsupported historical search controls")
    if any(_canonical(contracts[key]) != _canonical(value) for key, value in _CONTROLS.items()):
        raise _Unsupported("unsupported historical search controls")
    if hashlib.sha256(MUTATION_SYSTEM.encode()).hexdigest() != _CONTROLS["system_sha256"] or (
        _sha(proposal_schema()) != _CONTROLS["proposal_schema_sha256"]
    ):
        raise _Unsupported("installed pure proposer recipe does not match the legacy profile")
    sources = dict(_object(contracts["source_sha256"]))
    if set(sources) != set(_SOURCES):
        raise _Unsupported("unsupported historical source profile")
    for name, digest in sources.items():
        _hex(digest, "historical source hash")
        if digest not in _SOURCES[name]:
            raise _Unsupported("unrecognized historical source profile")
    _hex(contracts["controller_sha256"], "historical controller hash")
    if contracts["controller_sha256"] not in _CONTROLLERS:
        raise _Unsupported("unrecognized historical controller profile")
    raw_seeds = contracts["seed_policies"]
    if not isinstance(raw_seeds, list) or len(raw_seeds) != 2:
        raise ValidationError("legacy search requires two recorded seed policies")
    seeds = tuple(Policy.from_record(item) for item in raw_seeds)
    if len({item.fingerprint() for item in seeds}) != 2:
        raise ValidationError("recorded seed policies must have separate identities")
    settings, spec = (
        RunSettings.from_record(manifest["settings"]),
        SearchSpec.from_record(manifest["spec"]),
    )
    source_hash = manifest["source_sha256"]
    _hex(source_hash, "source dataset hash")
    raw = run.blob("dataset.jsonl")
    if hashlib.sha256(raw).hexdigest() != source_hash:
        raise ValidationError("sealed dataset differs from the search manifest")
    if not manifest["synthetic"] and source_hash not in {item[1] for item in DATASETS.values()}:
        raise _Unsupported("unsupported official historical source population")
    prompts = tuple(
        Prompt(_text(row.get("id"), "prompt ID"), _text(row.get("prompt"), "prompt"))
        for row in _jsonl(raw)
    )
    prompt_manifest(prompts)
    families = manifest["families"]
    if families is not None:
        families = {key: _text(value, "family") for key, value in _object(families).items()}
    assigned = validate_splits(prompts, manifest["splits"], families=families)
    ids = assigned["development"][: spec.screen_size]
    if len(ids) != spec.screen_size or manifest["screen_ids"] != ids:
        raise ValidationError("search screen differs from its declared split")
    available = {item.id: item for item in prompts}
    screen = tuple(available[item] for item in ids)
    if manifest["comparison_key"] != _comparison(settings, str(source_hash), screen, contracts):
        raise ValidationError("historical comparison controls do not reconcile")
    return _Search(run, history, manifest, settings, spec, screen, seeds)


def _receipt(call: Call, operation: HistoricalOperation) -> Reply:
    if operation.request_sha256 != call.fingerprint() or (
        operation.reserve_microusd != call.spec.reserve_microusd()
    ):
        raise ValidationError("saved request or reservation differs from its semantic slot")
    if operation.status != "completed" or operation.reply is None:
        raise ValidationError("saved semantic request is not complete")
    BudgetBroker._bounds(call, operation.reply)
    if operation.actual_microusd != call.spec.cost_microusd(
        operation.reply.input_tokens, operation.reply.output_tokens
    ):
        raise ValidationError("recorded charge differs from its frozen rate and usage")
    return operation.reply


def _archive_contract(snapshot: dict[str, bytes], contracts: dict[str, object]) -> None:
    sources = dict(_object(contracts["source_sha256"]))
    sources["buddha.search"] = contracts["controller_sha256"]
    for name, digest in sources.items():
        raw = snapshot.get(name.replace(".", "/") + ".py")
        if raw is None or hashlib.sha256(raw).hexdigest() != digest:
            raise ValidationError("archived source does not match its recorded contract")
    common = snapshot.get("buddha/common.py")
    needs_common = (
        any(
            sources.get(name) == revision[1]
            for name, revision in _GENERIC_EXTRACTION_MODULES.items()
        )
        or sources.get("buddha.benchmark") == _BENCHMARK_BYTES_REVISION[1]
    )
    needs_common = (
        needs_common
        or sources.get("buddha.provider")
        == ("17de071c1416afa32f9da32eb627e24264d8a0a848862fdf4853057125f18a02")
        or sources.get("buddha.ledger")
        == ("5c7e56f1e2c5e68046d6380ebacc03110300eae34d348d7dca683a0591d64130")
    )
    if (common is not None or needs_common) and (
        common is None
        or hashlib.sha256(common).hexdigest()
        != "3a0a693a0f4a0f2eed3b858d0b3ac42148871dbca284e56e0e368726309393c0"
    ):
        raise ValidationError("archived generic helpers differ from the legacy profile")


def _shared(snapshot: SealedEvidence, histories: dict[Path, History]) -> dict[str, object] | None:
    if snapshot.authorization is None:
        return None
    authority = read_authority(snapshot.authorization)
    rows = [_object(item) for item in _list(authority["auth_runs"])]
    operations = [_object(item) for item in _list(authority["auth_operations"])]
    fields = (
        "request_sha256",
        "reserve_microusd",
        "status",
        "response_json",
        "actual_microusd",
        "provider_request_id",
    )
    for directory, history in histories.items():
        owners = [item for item in rows if item["run_id"] == history.run_id]
        if len(owners) != 1:
            raise ValidationError("sealed shared authority does not bind a selected run")
        owner = owners[0]
        if (
            owner["directory"] != str(directory)
            or owner["ledger_path"] != str(directory / "operations.sqlite3")
            or (owner["manifest_sha256"] != history.manifest_sha256)
        ):
            raise ValidationError("shared run identity differs from its selected source")
        if owner["historical"] and owner["historical_ledger_sha256"] != history.ledger_sha256:
            raise ValidationError("shared historical ledger seal differs")
        if not owner["historical"]:
            binding = _local_binding(snapshot.run(directory).blob("operations.sqlite3"))
            config = _object(authority["config"])
            if binding is None or any(
                binding[key] != value
                for key, value in (
                    ("authorization_id", config["authorization_id"]),
                    ("authority_path", str(snapshot.authorization_path)),
                    ("terms_sha256", _sha(config)),
                )
            ):
                raise ValidationError("local binding differs from the selected shared authority")
        saved = {
            str(item["operation_id"]): tuple(item[key] for key in fields)
            for item in operations
            if item["run_id"] == history.run_id
        }
        expected = {item.operation_id: _signature(item) for item in history.operations}
        if saved != expected:
            raise ValidationError("shared operation mirror differs from the selected ledger")
    return authority


def _list(value: object) -> list[object]:
    if not isinstance(value, list):
        raise ValidationError("stored evidence population must be a list")
    return value


def _initial_context(
    context: dict[str, object],
    histories: dict[Path, History],
    authority: dict[str, object],
) -> None:
    """Check immutable imported populations without confusing past/current totals."""
    by_id = {history.run_id: history for history in histories.values()}
    owners = {
        _text(row["run_id"], "shared run ID"): row
        for value in _list(authority["auth_runs"])
        for row in [_object(value)]
    }
    seen = set()
    for value in _list(context["runs"]):
        row = _object(value)
        run_id = _text(row.get("run_id"), "initial shared run ID")
        if run_id in seen:
            raise ValidationError("initial shared population contains duplicate runs")
        seen.add(run_id)
        historical = row.get("historical")
        if type(historical) is not int or historical not in {0, 1}:
            raise ValidationError("initial shared population has an invalid ownership mode")
        if not historical:
            raise _Unsupported("initial mutable-run totals lack a sealed historical snapshot")
        if run_id not in by_id or run_id not in owners:
            raise ValidationError("initial imports require their explicitly sealed source roots")
        history, owner = by_id[run_id], owners[run_id]
        if owner["historical"] != 1:
            raise ValidationError("initial imported ownership differs from shared history")
        expected = owner | {"active": False, **history.totals()}
        if _canonical(row) != _canonical(expected):
            raise ValidationError("initial imported context differs from its immutable source")


class _Verifier:
    def __init__(
        self,
        snapshot: SealedEvidence,
        main: _Search,
        histories: dict[Path, History],
        authority: dict[str, object] | None,
    ) -> None:
        self.snapshot, self.main, self.histories, self.authority = (
            snapshot,
            main,
            histories,
            authority,
        )
        self.operations = {item.operation_id: item for item in main.history.operations}
        self.billed: dict[str, tuple[str, int, str | None]] = {}
        self.inherited: dict[str, InheritedReference] = {}
        self.used_inherited: set[str] = set()
        self.candidates: list[Candidate] = []
        self.policies: dict[str, Policy] = {}
        self.rows: dict[str, list[dict[str, object]]] = {}
        self.summaries: dict[str, dict[str, object]] = {}
        self.decisions: list[dict[str, object]] = []
        self.checked_decisions = 0
        self.lineage: dict[str, object] | None = None
        self.historical_shared: dict[str, object] | None = None

    def require(self, name: str) -> bytes:
        if name not in self.main.sealed.files:
            raise _Missing({"stage": "artifact", "path": name, "status": "missing"})
        return self.main.sealed.blob(name)

    def record(self, name: str, expected: dict[str, object]) -> None:
        if _canonical(_record(self.require(name))) != _canonical(expected):
            raise ValidationError("saved artifact conflicts with its checked evidence")

    def execute(self, namespace: Sequence[object], candidate: str | None = None) -> Execute:
        def lookup(prompt_id: str, stage: str, index: int, call: Call) -> Reply:
            operation_id = _sha([*namespace, prompt_id, stage, index])
            if operation_id in self.inherited:
                item = self.inherited[operation_id]
                if (
                    item.prompt_id,
                    item.stage,
                    item.index,
                    item.candidate_id,
                    item.request_sha256,
                ) != (prompt_id, stage, index, candidate, call.fingerprint()):
                    raise ValidationError("inherited reply differs from its semantic slot")
                BudgetBroker._bounds(call, item.reply)
                if operation_id in self.operations:
                    raise ValidationError("inherited evidence also has a new physical operation")
                self.used_inherited.add(operation_id)
                return item.reply
            operation = self.operations.get(operation_id)
            if operation is not None and (
                operation.request_sha256 != call.fingerprint()
                or operation.reserve_microusd != call.spec.reserve_microusd()
            ):
                raise ValidationError("saved request differs from its semantic slot")
            if operation is None or operation.status != "completed":
                raise _Missing(
                    {
                        "operation_id": operation_id,
                        "prompt_id": prompt_id,
                        "stage": stage,
                        "index": index,
                        "status": "missing" if operation is None else operation.status,
                    }
                )
            reply = _receipt(call, operation)
            actual = _amount(operation.actual_microusd, "recorded charge")
            self.billed[operation_id] = (stage, actual, candidate)
            return reply

        return lookup

    def admit(self, selected: Policy, parent: str | None) -> None:
        candidate = selected.fingerprint()
        prefix = f"candidates/{candidate}/"
        self.record(prefix + "policy.json", selected.to_record())
        main = self.main
        protocol = _candidate_protocol(main.settings, selected, main.manifest, main.prompts)

        def generate(prompt: Prompt, previous: Sequence[str]) -> Call:
            return _generation(
                main.settings.generation,
                prompt.prompt,
                instructions=selected.instructions,
                history=previous if selected.sampling == "in-context" else (),
            )

        replayed = evaluate_prompts(
            main.prompts,
            settings=main.settings,
            protocol=protocol,
            execute=self.execute([main.history.run_id, "candidate", candidate], candidate),
            generate=generate,
        )
        expected_files = {*_ARTIFACTS, "provenance.json"}
        blobs = {name: self.require(prefix + "evaluation/" + name) for name in expected_files}
        actual_files = {
            name.removeprefix(prefix + "evaluation/")
            for name in main.sealed.files
            if name.startswith(prefix + "evaluation/")
        }
        if actual_files != expected_files:
            raise ValidationError("candidate evaluation has an unexpected artifact inventory")
        candidate_files = {name for name in main.sealed.files if name.startswith(prefix)}
        if candidate_files != {prefix + "policy.json"} | {
            prefix + "evaluation/" + name for name in expected_files
        }:
            raise ValidationError("candidate has an unexpected artifact inventory")
        summary, checked = import_evaluation_bytes(
            blobs, protocol=protocol, expected_prompt_hashes=prompt_manifest(main.prompts)
        )
        if len(checked) != len(replayed) or any(
            _canonical({key: saved.get(key) for key in row}) != _canonical(row)
            for saved, row in zip(checked, replayed, strict=True)
        ):
            raise ValidationError("saved scientific artifacts differ from their recorded replies")
        self.candidates.append(
            Candidate(candidate, parent, summary.mean_utility, summary.mean_distinct)
        )
        self.policies[candidate], self.rows[candidate], self.summaries[candidate] = (
            selected,
            checked,
            asdict(summary),
        )

    def funding(self) -> None:
        if "funding.json" not in self.main.sealed.files:
            return
        record = _record(self.main.sealed.blob("funding.json"))
        if record.get("format") != "buddha.recovery-funding.v1":
            raise _Unsupported("unsupported historical recovery funding record")
        sources = [
            item for item in self.histories.values() if item.run_id == record.get("source_run_id")
        ]
        if len(sources) != 1 or sources[0].run_id == self.main.history.run_id:
            raise ValidationError("funding requires its separately selected sealed original source")
        source, main = sources[0], self.main.history
        totals = source.totals()
        budget = _amount(record.get("authorization_total_microusd"), "combined budget")
        calls = _amount(record.get("authorization_total_calls"), "combined call cap")
        expected: dict[str, object] = {
            "format": "buddha.recovery-funding.v1",
            "policy": (
                "original stays inactive with reservation retained; fresh recovery evidence only"
            ),
            "source_run_id": source.run_id,
            "source_manifest_sha256": source.manifest_sha256,
            "source_ledger_sha256": source.ledger_sha256,
            "source_attempted_calls": totals["operation_count"],
            "source_known_microusd": totals["spent_microusd"],
            "source_held_microusd": totals["reserved_microusd"],
            "recovery_run_id": main.run_id,
            "recovery_manifest_sha256": main.manifest_sha256,
            "recovery_budget_microusd": main.budget_microusd,
            "recovery_max_calls": main.max_calls,
            "authorization_total_microusd": budget,
            "authorization_total_calls": calls,
        }
        if _canonical(record) != _canonical(expected) or (
            main.budget_microusd != budget - totals["committed_microusd"]
            or main.max_calls != calls - totals["operation_count"]
            or source.budget_microusd != budget
            or source.max_calls != calls
        ):
            raise ValidationError("historical recovery funding does not reconcile with its source")
        if self.authority is not None:
            config = _object(self.authority["config"])
            if config["budget_microusd"] != budget or config["max_calls"] != calls:
                raise ValidationError("shared terms differ from the historical recovery envelope")

    def linked(self) -> None:
        main = self.main
        if main.manifest["format"] != "buddha.policy-search-continuation.v1":
            return
        metadata = _object(main.manifest["continuation"])
        if set(metadata) != _METADATA_KEYS or metadata["format"] != "buddha.linked-continuation.v1":
            raise ValidationError("unsupported linked continuation metadata")
        if (
            metadata["archived_runtime_file"] != "source-runtime.zip"
            or metadata["runtime_archive_file"] != "runtime-source.zip"
        ):
            raise ValidationError("linked archive names differ from the declared format")
        source_run = self.snapshot.run(
            Path(_text(metadata["source_directory"], "source directory"))
        )
        source = _search(source_run, self.histories[source_run.directory])
        if source.manifest["format"] != "buddha.policy-search.v1" or len(source.prompts) != 1:
            raise ValidationError("linked source is not the bounded original search")
        history, seed, prompt = source.history, source.seeds[0], source.prompts[0]
        if (
            metadata["source_run_id"] != history.run_id
            or metadata["source_manifest_sha256"] != history.manifest_sha256
            or metadata["source_ledger_sha256"] != history.ledger_sha256
            or main.history.run_id == history.run_id
        ):
            raise ValidationError("linked source identity or seals differ")
        old_snapshot = _snapshot_bytes(
            self.require("source-runtime.zip"),
            _text(metadata["archived_runtime_sha256"], "source archive seal"),
        )
        _archive_contract(old_snapshot, _object(source.manifest["contracts"]))
        runtime = _snapshot_bytes(
            self.require("runtime-source.zip"),
            _text(metadata["runtime_archive_sha256"], "runtime archive seal"),
        )
        _archive_contract(runtime, _object(main.manifest["contracts"]))
        package = {
            name.removeprefix("buddha/"): hashlib.sha256(raw).hexdigest()
            for name, raw in runtime.items()
            if name.startswith("buddha/")
            and name.endswith(".py")
            and "/" not in name[len("buddha/") :]
        }
        if (
            set(runtime) != {"buddha/" + name for name in package} | {"THIRD_PARTY_NOTICES.md"}
            or _sha(package) != metadata["runtime_sha256"]
        ):
            raise ValidationError("archived runtime differs from its recorded identity")
        original = {item.operation_id: item for item in history.operations}
        expected = [
            _sha([history.run_id, "candidate", seed.fingerprint(), prompt.id, "generation", index])
            for index in range(10)
        ]
        if set(original) != set(expected):
            raise ValidationError("linked source does not contain exactly the original ten slots")
        call = _generation(
            source.settings.generation, prompt.prompt, instructions=seed.instructions
        )
        completed = tuple(original[operation_id] for operation_id in expected[:9])
        unknown = original[expected[9]]
        if (
            unknown.status != "unknown"
            or unknown.reply is not None
            or unknown.provider_request_id is not None
            or unknown.actual_microusd is not None
            or unknown.request_sha256 != call.fingerprint()
            or unknown.reserve_microusd != call.spec.reserve_microusd()
        ):
            raise ValidationError("original tenth request must remain receiptless and held")
        for index, operation in enumerate(completed):
            reply = _receipt(call, operation)
            actual = _amount(operation.actual_microusd, "inherited charge")
            operation_id = _sha(
                [
                    main.history.run_id,
                    "candidate",
                    seed.fingerprint(),
                    prompt.id,
                    "generation",
                    index,
                ]
            )
            self.inherited[operation_id] = InheritedReference(
                operation_id,
                history.run_id,
                operation.operation_id,
                seed.fingerprint(),
                prompt.id,
                "generation",
                index,
                operation.request_sha256,
                reply,
                actual,
                operation.reserve_microusd,
                history.manifest_sha256,
                history.ledger_sha256,
            )
        replacement = ReplacementReference(
            _sha(
                [main.history.run_id, "candidate", seed.fingerprint(), prompt.id, "generation", 9]
            ),
            history.run_id,
            unknown.operation_id,
            seed.fingerprint(),
            prompt.id,
            "generation",
            9,
            unknown.request_sha256,
            history.manifest_sha256,
            history.ledger_sha256,
        )
        if (
            _canonical(metadata["inherited"])
            != _canonical([asdict(item) for item in self.inherited.values()])
            or _canonical(metadata["replacement"]) != _canonical(asdict(replacement))
            or metadata["acceptance_reason"] != _ACCEPTANCE_REASON
        ):
            raise ValidationError(
                "inherited references or replacement lineage do not match source slots"
            )
        origin = Source(
            history,
            source.settings,
            source.spec,
            prompt,
            completed,
            unknown,
            _text(metadata["archived_runtime_sha256"], "archive seal"),
        )
        budget, calls = _context(metadata["authorization_context"], origin, source_run.directory)
        if (
            main.settings != replace(source.settings, budget_microusd=budget, max_calls=calls)
            or main.spec != source.spec
            or main.prompts != source.prompts
        ):
            raise ValidationError("continuation changed frozen settings or population")
        if (
            any(
                _canonical(main.manifest[key]) != _canonical(source.manifest[key])
                for key in (
                    "source_sha256",
                    "splits",
                    "families",
                    "screen_ids",
                    "synthetic",
                    "population",
                )
            )
            or main.seeds != source.seeds
        ):
            raise ValidationError("continuation changed source data or seed policies")
        if (
            self.authority is None
            or self.snapshot.authorization_path is None
            or metadata["authorization_path"] != str(self.snapshot.authorization_path)
        ):
            raise ValidationError("linked verification requires its explicitly sealed authority")
        context = _object(metadata["authorization_context"])
        _initial_context(context, self.histories, self.authority)
        config = _object(self.authority["config"])
        static = ("authorization_id", "budget_microusd", "max_calls", "scope", "terms_sha256")
        if any(config[key] != context[key] for key in static):
            raise ValidationError("shared terms differ from the continuation context")
        owners = [
            _object(item)
            for item in _list(self.authority["auth_runs"])
            if _object(item)["run_id"] == main.history.run_id
        ]
        if len(owners) != 1 or owners[0]["runtime_sha256"] != metadata["runtime_sha256"]:
            raise ValidationError("shared runtime binding differs from the saved continuation")
        acceptance = {
            "source_run_id": history.run_id,
            "operation_id": unknown.operation_id,
            "continuation_run_id": main.history.run_id,
            "evidence_sha256": history.ledger_sha256,
            "reason": _ACCEPTANCE_REASON,
        }
        if acceptance not in _list(self.authority["auth_acceptances"]):
            raise ValidationError("shared authority lacks the recorded continuation acceptance")
        totals = main.history.totals()
        self.historical_shared = {key: context[key] for key in static}
        self.historical_shared.update(
            {
                key: _integer(context[key], "initial accounting", 0) + totals[key]
                for key in _FINANCIALS
            }
        )
        self.historical_shared["available_microusd"] = max(
            0,
            _integer(context["budget_microusd"], "budget", 0)
            - _integer(self.historical_shared["committed_microusd"], "committed cost", 0),
        )
        self.historical_shared["remaining_calls"] = max(
            0,
            _integer(context["max_calls"], "calls", 0)
            - _integer(self.historical_shared["operation_count"], "operation count", 0),
        )
        self.lineage = {
            "source_run_id": history.run_id,
            "source_manifest_sha256": history.manifest_sha256,
            "source_ledger_sha256": history.ledger_sha256,
            "replacement": asdict(replacement),
            "inherited_operation_ids": list(self.inherited),
            "accounting": (
                "costs are new physical operations; inherited evidence is charged once "
                "in shared accounting"
            ),
        }

    def walk(self) -> None:
        self.funding()
        self.linked()
        main = self.main
        for index, seed in enumerate(main.seeds):
            self.admit(seed, None)
            self.record(
                f"decisions/seed-{index}.json",
                {
                    "status": "admitted",
                    "candidate_id": seed.fingerprint(),
                    "parent_id": None,
                    "comparison_key": main.manifest["comparison_key"],
                },
            )
            self.checked_decisions += 1
        for iteration in range(main.spec.iterations):
            parent = select_parent(
                self.candidates,
                method=main.spec.method,
                max_active=main.spec.max_active,
                seed=main.spec.seed,
                iteration=iteration,
            )
            feedback = [] if main.spec.method == "uninformed" else self.rows[parent.candidate_id]
            call = propose_call(
                main.settings.generation,
                parent=self.policies[parent.candidate_id],
                feedback=feedback,
                method=main.spec.method,
            )
            reply = self.execute([main.history.run_id, "proposal", iteration])(
                "development", "proposal", 0, call
            )
            decision: dict[str, object] = {
                "iteration": iteration,
                "parent_id": parent.candidate_id,
                "proposal_sha256": hashlib.sha256(
                    reply.text.encode(errors="surrogatepass")
                ).hexdigest(),
                "comparison_key": main.manifest["comparison_key"],
            }
            child = None
            try:
                if reply.refused or reply.finish_reason not in {"stop", "end_turn"}:
                    raise ValidationError("incomplete proposal")
                selected = Policy.from_record(_parse(reply.text.encode()))
            except (ValidationError, UnicodeError):
                decision["status"] = "invalid"
            else:
                candidate = selected.fingerprint()
                decision.update(
                    {
                        "candidate_id": candidate,
                        "policy": selected.to_record(),
                        "status": "duplicate" if candidate in self.policies else "admitted",
                    }
                )
                if candidate not in self.policies:
                    child = selected
            if child is not None:
                self.admit(child, parent.candidate_id)
            self.record(f"decisions/iteration-{iteration:06d}.json", decision)
            self.decisions.append(decision)
            self.checked_decisions += 1
        self.record("report.json", self.report())
        expected_candidates = {item.candidate_id for item in self.candidates}
        actual_candidates = {
            name.split("/")[1] for name in main.sealed.files if name.startswith("candidates/")
        }
        if actual_candidates != expected_candidates:
            raise ValidationError("saved candidate population differs from checked search history")
        expected_decisions = {f"decisions/seed-{index}.json" for index in range(2)} | {
            f"decisions/iteration-{index:06d}.json" for index in range(main.spec.iterations)
        }
        if {
            name for name in main.sealed.files if name.startswith("decisions/")
        } != expected_decisions:
            raise ValidationError("saved decision population differs from checked search history")

    def report(self) -> dict[str, object]:
        main = self.main
        totals = main.history.totals()
        if (
            set(self.billed) != set(self.operations)
            or totals["reserved_microusd"]
            or self.used_inherited != set(self.inherited)
        ):
            raise ValidationError(
                "complete search does not account for every physical/inherited operation"
            )
        by_stage = {
            stage: sum(amount for recorded, amount, _ in self.billed.values() if recorded == stage)
            for stage in ("proposal", "generation", "partition", "score")
        }
        by_candidate = {
            item.candidate_id: sum(
                amount for _, amount, owner in self.billed.values() if owner == item.candidate_id
            )
            for item in self.candidates
        }
        costs: dict[str, object] = dict(totals)
        costs.update(
            {
                "by_stage_microusd": by_stage,
                "by_candidate_microusd": by_candidate,
                "seed_evaluation_microusd": sum(
                    by_candidate[item.candidate_id] for item in self.candidates[:2]
                ),
                "child_evaluation_microusd": sum(
                    by_candidate[item.candidate_id] for item in self.candidates[2:]
                ),
                "proposal_microusd": by_stage["proposal"],
            }
        )
        candidates = [
            asdict(item)
            | {
                "summary": self.summaries[item.candidate_id],
                "evaluation_microusd": by_candidate[item.candidate_id],
            }
            for item in self.candidates
        ]
        report: dict[str, object] = {
            "format": "buddha.policy-search-report.v1",
            "status": "complete",
            "synthetic": main.manifest["synthetic"],
            "run_id": main.history.run_id,
            "metric_version": METRIC_VERSION,
            "method": main.spec.method,
            "comparison_key": main.manifest["comparison_key"],
            "screen_ids": main.manifest["screen_ids"],
            "spec": asdict(main.spec),
            "candidates": candidates,
            "active_ids": [
                item.candidate_id
                for item in active_pool(self.candidates, max_active=main.spec.max_active)
            ],
            "frontier_ids": [item.candidate_id for item in frontier(self.candidates)],
            "decisions": self.decisions,
            "costs": costs,
            "claim": "exploratory development measurements; no held-out improvement claim",
        }
        if self.lineage is not None:
            inherited = sum(item.actual_microusd for item in self.inherited.values())
            by_inherited = {
                item.candidate_id: sum(
                    ref.actual_microusd
                    for ref in self.inherited.values()
                    if ref.candidate_id == item.candidate_id
                )
                for item in self.candidates
            }
            report.update(
                {
                    "format": "buddha.policy-search-report.v2",
                    "inherited_costs": {
                        "committed_microusd": inherited,
                        "spent_microusd": inherited,
                        "reserved_microusd": 0,
                        "operation_count": len(self.inherited),
                        "by_stage_microusd": {"generation": inherited},
                        "by_candidate_microusd": by_inherited,
                    },
                    "evidence_costs": {
                        "committed_microusd": totals["committed_microusd"] + inherited,
                        "spent_microusd": totals["spent_microusd"] + inherited,
                        "reserved_microusd": totals["reserved_microusd"],
                        "operation_count": totals["operation_count"] + len(self.inherited),
                    },
                    "authorization": self.historical_shared,
                    "continuation": self.lineage,
                }
            )
            for candidate in candidates:
                identity = _text(candidate["candidate_id"], "candidate ID")
                candidate["inherited_evaluation_microusd"] = by_inherited[identity]
                candidate["evidence_evaluation_microusd"] = (
                    by_candidate[identity] + by_inherited[identity]
                )
        return report


def verify_search(directory: Path, *, evidence: dict[str, object]) -> SearchVerification:
    """Verify explicit saved bytes without writers, credentials or runtime replay."""
    try:
        if not isinstance(directory, Path):
            raise ValidationError("verification requires a filesystem Path")
        declaration = _object(_parse(_canonical(evidence)))
        snapshot = read_search_evidence(directory.absolute(), evidence=declaration)
        histories = {run.directory: _financial(run) for run in snapshot.runs}
        main_history = histories[snapshot.runs[0].directory]
        authority = _shared(snapshot, histories)
        verifier = None
        missing = None
        reason = None
        try:
            main = _search(snapshot.runs[0], main_history)
            verifier = _Verifier(snapshot, main, histories, authority)
            verifier.walk()
            status = "verified"
        except _Missing as error:
            if "report.json" in snapshot.runs[0].files:
                raise ValidationError(
                    "saved complete report lacks required checked evidence"
                ) from None
            missing, status = error.slot, "incomplete"
        except _Unsupported as error:
            reason, status = str(error), "unsupported"
        snapshot.finish()
        checked = {
            "physical_operations": len(verifier.billed) if verifier else 0,
            "inherited_operations": len(verifier.used_inherited) if verifier else 0,
            "candidates": len(verifier.candidates) if verifier else 0,
            "decisions": verifier.checked_decisions if verifier else 0,
        }
        result: dict[str, object] = {
            "format": "buddha.search-verification-report.v1",
            "status": status,
            "run_id": main_history.run_id,
            "evidence_sha256": _sha(declaration),
            "costs": main_history.totals(),
            "checked": checked,
            "missing": missing,
            "shared_accounting": None if authority is None else authority["totals"],
            "shared_scope": None
            if authority is None
            else {
                "matched_run_ids": sorted(history.run_id for history in histories.values()),
                "unmatched_run_ids": sorted(
                    _text(row["run_id"], "shared run ID")
                    for value in _list(authority["auth_runs"])
                    for row in [_object(value)]
                    if row["run_id"] not in {history.run_id for history in histories.values()}
                ),
            },
            "claim": _CLAIM,
        }
        if reason is not None:
            result["reason"] = reason
        return SearchVerification(_canonical(result).decode())
    except (
        OSError,
        sqlite3.Error,
        ValueError,
        TypeError,
        KeyError,
        UnicodeError,
        RecursionError,
        zipfile.BadZipFile,
        zlib.error,
        EOFError,
        RuntimeError,
    ) as error:
        if isinstance(error, ValidationError):
            raise
        raise ValidationError("sealed search evidence could not be verified consistently") from None
