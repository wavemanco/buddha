"""Read and bind the nine preserved pilot replies without granting paid authority.

The archived program is inspected as bounded data; it is never extracted or
executed here. Source seals establish consistency, not provider authentication.
"""

from __future__ import annotations

import ast
import hashlib
import sqlite3
import stat
import zipfile
import zlib
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path, PurePosixPath
from types import MappingProxyType
from typing import TYPE_CHECKING

from buddha import archive, benchmark, evaluation, policy, provider, run, splits
from buddha.benchmark import Prompt, _object, _parse, load_prompts
from buddha.evaluation import ValidationError, _hex, _text
from buddha.history import HistoricalOperation, History, _plain, read_history
from buddha.policy import Policy
from buddha.provider import BudgetBroker, Reply
from buddha.run import RunSettings, _generation, _sha

if TYPE_CHECKING:
    from buddha.search import SearchSpec

_MAX_ARCHIVE = 64 * 1024 * 1024
_MAX_MEMBER = 16 * 1024 * 1024
_CORE_MODULES = (archive, benchmark, evaluation, policy, splits)
_OLD_CONTRACT_KEYS = {
    "system_sha256",
    "proposal_schema_sha256",
    "source_sha256",
    "controller_sha256",
    "parent_rule",
    "proposal_role",
    "feedback",
    "feedback_max_canonical_bytes",
    "seed_policies",
}
_HOST_DEFINITIONS = {
    "buddha.run": {"operation_executor", "run_baseline"},
    "buddha.provider": {"PreparedHTTP", "_ReceivedInterrupt"},
    "buddha.search": {"run_search"},
}
_HOST_METHODS = {
    "HTTPTransport": {"__init__", "_credential", "preflight", "prepare", "send", "send_prepared"},
    "BudgetBroker": {"__init__", "authorize", "execute"},
}


@dataclass(frozen=True)
class InheritedReference:
    operation_id: str
    source_run_id: str
    source_operation_id: str
    candidate_id: str
    prompt_id: str
    stage: str
    index: int
    request_sha256: str
    reply: Reply
    actual_microusd: int
    reserve_microusd: int
    source_manifest_sha256: str
    source_ledger_sha256: str


@dataclass(frozen=True)
class ReplacementReference:
    operation_id: str
    source_run_id: str
    source_operation_id: str
    candidate_id: str
    prompt_id: str
    stage: str
    index: int
    request_sha256: str
    source_manifest_sha256: str
    source_ledger_sha256: str


@dataclass(frozen=True)
class Source:
    history: History
    settings: RunSettings
    spec: SearchSpec
    prompt: Prompt
    completed: tuple[HistoricalOperation, ...]
    unknown: HistoricalOperation
    archived_runtime_sha256: str

    def _identity(self, new_run_id: str, index: int) -> tuple[str, str]:
        _text(new_run_id, "new continuation run ID")
        if new_run_id == self.history.run_id:
            raise ValidationError("a continuation must have a new run identity")
        candidate_id = Policy().fingerprint()
        return (
            _sha([new_run_id, "candidate", candidate_id, self.prompt.id, "generation", index]),
            candidate_id,
        )

    def references(self, new_run_id: str) -> Mapping[str, InheritedReference]:
        references = {}
        for index, operation in enumerate(self.completed):
            operation_id, candidate_id = self._identity(new_run_id, index)
            if operation.reply is None or operation.actual_microusd is None:
                raise ValidationError("inherited operation has no complete receipt")
            references[operation_id] = InheritedReference(
                operation_id,
                self.history.run_id,
                operation.operation_id,
                candidate_id,
                self.prompt.id,
                "generation",
                index,
                operation.request_sha256,
                operation.reply,
                operation.actual_microusd,
                operation.reserve_microusd,
                self.history.manifest_sha256,
                self.history.ledger_sha256,
            )
        return MappingProxyType(references)

    def replacement(self, new_run_id: str) -> ReplacementReference:
        operation_id, candidate_id = self._identity(new_run_id, 9)
        return ReplacementReference(
            operation_id,
            self.history.run_id,
            self.unknown.operation_id,
            candidate_id,
            self.prompt.id,
            "generation",
            9,
            self.unknown.request_sha256,
            self.history.manifest_sha256,
            self.history.ledger_sha256,
        )


def _file_hash(path: Path) -> str:
    _plain(path)
    if not path.is_file():
        raise ValidationError("continuation source evidence must be a regular file")
    with path.open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def _snapshot(path: Path, expected_sha256: str) -> dict[str, bytes]:
    _hex(expected_sha256, "archived runtime hash")
    if not isinstance(path, Path):
        raise ValidationError("archived runtime requires a filesystem Path")
    _plain(path)
    if path.stat().st_size > _MAX_ARCHIVE or _file_hash(path) != expected_sha256:
        raise ValidationError("archived runtime seal or size differs")
    with zipfile.ZipFile(path) as bundle:
        entries = bundle.infolist()
        names = [entry.filename for entry in entries]
        if (
            len(entries) > 4096
            or len(set(names)) != len(names)
            or sum(entry.file_size for entry in entries) > _MAX_ARCHIVE
        ):
            raise ValidationError("archived runtime contains duplicate or oversized entries")
        for entry in entries:
            entry_path = PurePosixPath(entry.filename)
            if (
                entry.is_dir()
                or entry_path.is_absolute()
                or ".." in entry_path.parts
                or "\\" in entry.filename
                or ":" in entry.filename
                or entry_path.as_posix() != entry.filename
                or entry.orig_filename != entry.filename
                or entry.flag_bits & 1
                or stat.S_IFMT(entry.external_attr >> 16) not in {0, stat.S_IFREG}
                or entry.file_size > _MAX_MEMBER
            ):
                raise ValidationError(
                    "archived runtime entries must be bounded regular relative files"
                )
        if "source-index.json" not in names:
            raise ValidationError("archived runtime has no source index")
        index = _object(_parse(bundle.read("source-index.json")))
        if index.get("format") != "buddha.runtime-source-snapshot.v1":
            raise ValidationError("unsupported archived runtime index")
        expected = _object(index.get("files_sha256"))
        if set(expected) | {"source-index.json"} != set(names) or "source-index.json" in expected:
            raise ValidationError("archived runtime inventory differs from its source index")
        result = {}
        for name, digest in expected.items():
            _hex(digest, "archived source hash")
            raw = bundle.read(name)
            if hashlib.sha256(raw).hexdigest() != digest:
                raise ValidationError("archived source differs from its indexed hash")
            result[name] = raw
    if _file_hash(path) != expected_sha256:
        raise ValidationError("archived runtime changed during observation")
    return result


def _definition(raw: bytes, name: str) -> str:
    nodes = ast.parse(raw).body
    selected: ast.FunctionDef | ast.ClassDef | None = None
    for part in name.split("."):
        matches = [
            node
            for node in nodes
            if isinstance(node, (ast.FunctionDef, ast.ClassDef)) and node.name == part
        ]
        if len(matches) != 1:
            raise ValidationError("scientific source definition is absent or ambiguous")
        selected = matches[0]
        nodes = selected.body
    if selected is None:
        raise ValidationError("scientific source definition is absent")
    return ast.dump(selected, include_attributes=False)


def _scientific_module(raw: bytes, module_name: str) -> str:
    """Exclude only reviewed host changes; retain imports, assignments and wrappers."""
    tree = ast.parse(raw)
    nodes = []
    for node in tree.body:
        if isinstance(node, (ast.FunctionDef, ast.ClassDef)) and (
            node.name in _HOST_DEFINITIONS[module_name]
        ):
            continue
        if (
            module_name == "buddha.provider"
            and isinstance(node, ast.ClassDef)
            and (node.name in _HOST_METHODS)
        ):
            node.body = [
                member
                for member in node.body
                if not (
                    isinstance(member, ast.FunctionDef) and member.name in _HOST_METHODS[node.name]
                )
            ]
        if (
            module_name in {"buddha.run", "buddha.search"}
            and isinstance(node, ast.ImportFrom)
            and node.level == 0
            and node.module == "buddha.authorization"
            and [(name.name, name.asname) for name in node.names] == [("Authorization", None)]
        ):
            continue
        if (
            module_name == "buddha.provider"
            and isinstance(node, ast.ImportFrom)
            and node.level == 0
            and node.module == "dataclasses"
        ):
            node.names = [
                name for name in node.names if (name.name, name.asname) != ("field", None)
            ]
        nodes.append(node)
    tree.body = nodes
    return ast.dump(tree, include_attributes=False)


def _science(snapshot: dict[str, bytes], contracts: object) -> None:
    from buddha import search

    protected = _object(contracts)
    if set(protected) != _OLD_CONTRACT_KEYS:
        raise ValidationError("unsupported original policy-search contract")
    original_files = _object(protected["source_sha256"])
    expected_modules = {
        "buddha." + name
        for name in (
            "archive",
            "benchmark",
            "evaluation",
            "ledger",
            "policy",
            "provider",
            "run",
            "splits",
        )
    }
    if set(original_files) != expected_modules:
        raise ValidationError("original runtime source inventory differs")
    for module_name, digest in original_files.items():
        _hex(digest, "original source hash")
        if hashlib.sha256(snapshot[module_name.replace(".", "/") + ".py"]).hexdigest() != digest:
            raise ValidationError("original contract does not match the preserved runtime")
    if hashlib.sha256(snapshot["buddha/search.py"]).hexdigest() != protected["controller_sha256"]:
        raise ValidationError("original controller differs from the preserved runtime")
    current = search._contracts()
    for key in _OLD_CONTRACT_KEYS - {"source_sha256", "controller_sha256"}:
        if protected[key] != current[key]:
            raise ValidationError("protected original search controls changed")
    for module in _CORE_MODULES:
        path = Path(_text(module.__file__, "scientific source path"))
        if (
            _file_hash(path)
            != hashlib.sha256(snapshot[module.__name__.replace(".", "/") + ".py"]).hexdigest()
        ):
            raise ValidationError("scientific evaluator, policy or archive source changed")
    for module in (provider, run, search):
        path = Path(_text(module.__file__, "scientific source path"))
        _plain(path)
        raw = path.read_bytes()
        archived = snapshot[module.__name__.replace(".", "/") + ".py"]
        if _scientific_module(raw, module.__name__) != _scientific_module(
            archived, module.__name__
        ):
            raise ValidationError("scientific code or module-level bindings changed")
        for name in ("BudgetBroker._bounds", "HTTPTransport._reply") if module is provider else ():
            if _definition(raw, name) != _definition(archived, name):
                raise ValidationError(
                    "scientific request constructor or evaluation semantics changed"
                )


def _source_prompt(history: History, directory: Path) -> tuple[RunSettings, SearchSpec, Prompt]:
    from buddha.search import SearchSpec, _comparison

    manifest = history.manifest
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
        or manifest["population"] != "development"
        or type(manifest["synthetic"]) is not bool
    ):
        raise ValidationError("unsupported original search manifest")
    settings = RunSettings.from_record(manifest["settings"])
    spec = SearchSpec.from_record(manifest["spec"])
    if spec.iterations != 1 or spec.screen_size != 1:
        raise ValidationError("continuation supports the one-prompt, one-proposal original pilot")
    source_hash = _text(manifest["source_sha256"], "source dataset hash")
    _hex(source_hash, "source dataset hash")
    dataset = directory / "dataset.jsonl"
    _plain(dataset)
    prompts = load_prompts(dataset, expected_sha256=source_hash)
    if not manifest["synthetic"] and source_hash not in {item[1] for item in run.DATASETS.values()}:
        raise ValidationError("original source is not the pinned official dataset")
    raw_families = manifest["families"]
    families = (
        None
        if raw_families is None
        else {key: _text(value, "prompt family") for key, value in _object(raw_families).items()}
    )
    assigned = splits.validate_splits(prompts, manifest["splits"], families=families)
    ids = assigned["development"][:1]
    if manifest["screen_ids"] != ids or len(ids) != 1:
        raise ValidationError("original screen differs from its frozen development split")
    prompt = next(item for item in prompts if item.id == ids[0])
    if manifest["comparison_key"] != _comparison(
        settings, source_hash, (prompt,), manifest["contracts"]
    ):
        raise ValidationError("original scientific comparison identity differs")
    if _file_hash(dataset) != source_hash:
        raise ValidationError("source dataset changed during observation")
    return settings, spec, prompt


def read_source(
    source: Path,
    *,
    manifest_sha256: str,
    ledger_sha256: str,
    archived_runtime_zip: Path,
    archived_runtime_sha256: str,
) -> Source:
    """Validate exactly nine completed initial answers and an uncertain tenth.

    This function never allocates funding, modifies source evidence or calls a
    provider. Historical pricing dates are preserved, not treated as permission
    to spend; live execution must independently recheck its applicable bounds.
    """
    try:
        history = read_history(source, manifest_sha256=manifest_sha256, ledger_sha256=ledger_sha256)
        snapshot = _snapshot(archived_runtime_zip, archived_runtime_sha256)
        _science(snapshot, history.manifest["contracts"])
        settings, spec, prompt = _source_prompt(history, source)
        call = _generation(settings.generation, prompt.prompt)
        candidate_id = Policy().fingerprint()
        expected = [
            _sha([history.run_id, "candidate", candidate_id, prompt.id, "generation", index])
            for index in range(10)
        ]
        operations = {item.operation_id: item for item in history.operations}
        if set(operations) != set(expected):
            raise ValidationError(
                "original source must contain exactly the ten initial answer slots"
            )
        completed = []
        for index, operation_id in enumerate(expected):
            operation = operations[operation_id]
            if operation.request_sha256 != call.fingerprint() or (
                operation.reserve_microusd != call.spec.reserve_microusd()
            ):
                raise ValidationError(
                    "original request or reservation differs from its scientific slot"
                )
            if index == 9:
                if (
                    operation.status != "unknown"
                    or operation.reply is not None
                    or (
                        operation.provider_request_id is not None
                        or operation.actual_microusd is not None
                    )
                ):
                    raise ValidationError(
                        "the tenth original answer must remain receiptless and unknown"
                    )
                continue
            if operation.status != "completed" or operation.reply is None:
                raise ValidationError("the first nine original answers require completed receipts")
            reply = operation.reply
            BudgetBroker._bounds(call, reply)
            expected_tier = {"openai": "default", "anthropic": "standard", "replay": ""}[
                call.spec.provider
            ]
            if reply.service_tier not in {"", expected_tier} or reply.finish_reason not in {
                "stop",
                "end_turn",
                "length",
                "max_tokens",
                "model_context_window_exceeded",
                "content_filter",
                "refusal",
            }:
                raise ValidationError(
                    "original receipt has an unsupported tier or completion status"
                )
            if operation.actual_microusd != call.spec.cost_microusd(
                reply.input_tokens, reply.output_tokens
            ):
                raise ValidationError("original known charge differs from its recorded usage")
            completed.append(operation)
        # Recheck source identity and inactivity after all external artifact reads.
        if (
            read_history(source, manifest_sha256=manifest_sha256, ledger_sha256=ledger_sha256)
            != history
        ):
            raise ValidationError("original source changed during validation")
        return Source(
            history,
            settings,
            spec,
            prompt,
            tuple(completed),
            operations[expected[9]],
            archived_runtime_sha256,
        )
    except (
        OSError,
        ValueError,
        TypeError,
        KeyError,
        SyntaxError,
        sqlite3.Error,
        zipfile.BadZipFile,
        zlib.error,
        EOFError,
        RuntimeError,
        NotImplementedError,
    ) as error:
        if isinstance(error, ValidationError):
            raise
        raise ValidationError(
            "continuation source or preserved runtime could not be validated"
        ) from None
