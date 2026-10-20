"""Read and bind the nine preserved pilot replies without granting paid authority.

The archived program is inspected as bounded data; it is never extracted or
executed here. Source seals establish consistency, not provider authentication.
"""

from __future__ import annotations

import ast
import hashlib
import io
import platform
import sqlite3
import stat
import uuid
import zipfile
import zlib
from collections.abc import Mapping
from dataclasses import asdict, dataclass, replace
from pathlib import Path, PurePosixPath
from types import MappingProxyType
from typing import TYPE_CHECKING

from buddha import archive, benchmark, common, evaluation, policy, provider, run, splits
from buddha.benchmark import Prompt, _canonical, _object, _parse, load_prompts
from buddha.evaluation import ValidationError, _hex, _text
from buddha.history import HistoricalOperation, History, _plain, read_history
from buddha.ledger import _amount
from buddha.policy import Policy
from buddha.provider import BudgetBroker, Reply
from buddha.run import RunSettings, _generation, _sha

if TYPE_CHECKING:
    from buddha.authorization import Authorization
    from buddha.search import SearchSpec

_MAX_ARCHIVE = 64 * 1024 * 1024
_MAX_MEMBER = 16 * 1024 * 1024
_CORE_MODULES = (archive, benchmark, evaluation, policy, splits)
# NB-01: the reviewed compatibility exception tightens artifact input checks.
# Requests, prompt text, grouping and metric arithmetic are unchanged. No other
# source revision is accepted; see docs/NOVELTYBENCH-CONFORMANCE.md.
_BENCHMARK_VALIDATION_REVISION = (
    "9e131a9f4fd92197b256518ea778984875d9aee2a58efb3ccc759d6553a79ae2",
    "15b57b974c702d69c7b9e172c73798bd555db5eedb3286bd8c792d1fe0568763",
)
# BENCH-03C: only these exact files move unchanged helpers into the sealed common
# module. Normalize to their reviewed predecessors before applying the old guard.
_GENERIC_EXTRACTION_MODULES = {
    "buddha.benchmark": (
        "15b57b974c702d69c7b9e172c73798bd555db5eedb3286bd8c792d1fe0568763",
        "b72c74a0b9b7e786b9969c72a400f449ab5758938ee9f24af660a887d866c2a9",
    ),
    "buddha.evaluation": (
        "87e23a9afbdbc466da7ed44cc1bb2b2fd8622d480efd9db95155d75ddda77e78",
        "4cabb1a48689a140fc6f6129ed8d9eae1d047d3e09eae794170c74479413b8d6",
    ),
}
_GENERIC_COMMON_SHA256 = "3a0a693a0f4a0f2eed3b858d0b3ac42148871dbca284e56e0e368726309393c0"
# REC-05B: only this exact refactor accepts already-buffered artifacts. The
# original importer AST and remaining scientific module are preserved in tests.
_BENCHMARK_BYTES_REVISION = (
    "b72c74a0b9b7e786b9969c72a400f449ab5758938ee9f24af660a887d866c2a9",
    "7ef7e26b2ef3cbf4119118a985334048fd30b68a5629f3e3196fa77e8200c49f",
)
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
    "buddha.search": {"run_search", "load_search", "_configuration", "_walk"},
}
_METADATA_KEYS = {
    "format",
    "source_directory",
    "source_run_id",
    "source_manifest_sha256",
    "source_ledger_sha256",
    "archived_runtime_file",
    "archived_runtime_sha256",
    "runtime_sha256",
    "runtime_archive_file",
    "runtime_archive_sha256",
    "authorization_path",
    "acceptance_reason",
    "authorization_context",
    "inherited",
    "replacement",
}
_ACCEPTANCE_REASON = (
    "Reviewed linked continuation: retain the original unknown liability, reuse nine authentic "
    "receipts and issue a separately identified replacement tenth request."
)
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


@dataclass(frozen=True)
class Continuation:
    source: Source
    replies: Mapping[str, InheritedReference]
    replacement: ReplacementReference
    authorization_context_json: str

    @property
    def authorization_context(self) -> dict[str, object]:
        return _object(_parse(self.authorization_context_json.encode("utf-8")))


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
    if not path.is_file() or path.stat().st_size > _MAX_ARCHIVE:
        raise ValidationError("archived runtime seal or size differs")
    with path.open("rb") as stream:
        raw = stream.read(_MAX_ARCHIVE + 1)
    result = _snapshot_bytes(raw, expected_sha256)
    _plain(path)
    if not path.is_file() or path.stat().st_size > _MAX_ARCHIVE:
        raise ValidationError("archived runtime changed during observation")
    with path.open("rb") as stream:
        observed = stream.read(_MAX_ARCHIVE + 1)
    if observed != raw:
        raise ValidationError("archived runtime changed during observation")
    return result


def _snapshot_member(bundle: zipfile.ZipFile, name: str) -> bytes:
    entry = bundle.getinfo(name)
    if entry.compress_type not in {zipfile.ZIP_STORED, zipfile.ZIP_DEFLATED}:
        raise ValidationError("archived runtime requires stored or deflated ZIP members")
    maximum = min(_MAX_MEMBER, entry.file_size)
    # ZipExtFile's deflate decoder has a 4096-byte floor; the production member
    # ceiling is 16 MiB. Explicit reads bound expansion before metadata cropping.
    with bundle.open(entry) as stream:
        raw = stream.read(maximum + 1)
    if len(raw) != entry.file_size or len(raw) > _MAX_MEMBER:
        raise ValidationError("archived runtime member size differs from its bounded declaration")
    return raw


def _snapshot_bytes(raw: bytes, expected_sha256: str) -> dict[str, bytes]:
    _hex(expected_sha256, "archived runtime hash")
    if (
        not isinstance(raw, bytes)
        or len(raw) > _MAX_ARCHIVE
        or hashlib.sha256(raw).hexdigest() != expected_sha256
    ):
        raise ValidationError("archived runtime seal or size differs")
    try:
        with zipfile.ZipFile(io.BytesIO(raw)) as bundle:
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
            index = _object(_parse(_snapshot_member(bundle, "source-index.json")))
            if index.get("format") != "buddha.runtime-source-snapshot.v1":
                raise ValidationError("unsupported archived runtime index")
            expected = _object(index.get("files_sha256"))
            if (
                set(expected) | {"source-index.json"} != set(names)
                or "source-index.json" in expected
            ):
                raise ValidationError("archived runtime inventory differs from its source index")
            result = {}
            for name, digest in expected.items():
                _hex(digest, "archived source hash")
                raw = _snapshot_member(bundle, name)
                if hashlib.sha256(raw).hexdigest() != digest:
                    raise ValidationError("archived source differs from its indexed hash")
                result[name] = raw
        return result
    except (zipfile.BadZipFile, zipfile.LargeZipFile, EOFError, RuntimeError, zlib.error):
        raise ValidationError("archived runtime ZIP could not be decoded consistently") from None


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
            and node.module == "buddha.common"
            and [(name.name, name.asname) for name in node.names] == [("ValidationError", None)]
        ):
            node.module = "buddha.evaluation"
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

    if (
        _file_hash(Path(_text(common.__file__, "generic helper source path")))
        != _GENERIC_COMMON_SHA256
    ):
        raise ValidationError("generic helper source differs from the reviewed extraction")
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
    archived_common = snapshot.get("buddha/common.py")
    uses_common = (
        any(
            hashlib.sha256(snapshot[name.replace(".", "/") + ".py"]).hexdigest() == revision[1]
            for name, revision in _GENERIC_EXTRACTION_MODULES.items()
        )
        or hashlib.sha256(snapshot["buddha/benchmark.py"]).hexdigest()
        == (_BENCHMARK_BYTES_REVISION[1])
        or any(
            isinstance(node, ast.ImportFrom)
            and node.level == 0
            and node.module == "buddha.common"
            and [(name.name, name.asname) for name in node.names] == [("ValidationError", None)]
            for node in ast.parse(snapshot["buddha/provider.py"]).body
        )
    )
    if (archived_common is not None or uses_common) and (
        archived_common is None
        or hashlib.sha256(archived_common).hexdigest() != _GENERIC_COMMON_SHA256
    ):
        raise ValidationError("archived generic helpers differ from the reviewed extraction")
    if hashlib.sha256(snapshot["buddha/search.py"]).hexdigest() != protected["controller_sha256"]:
        raise ValidationError("original controller differs from the preserved runtime")
    current = search._contracts()
    for key in _OLD_CONTRACT_KEYS - {"source_sha256", "controller_sha256"}:
        if protected[key] != current[key]:
            raise ValidationError("protected original search controls changed")
    for module in _CORE_MODULES:
        path = Path(_text(module.__file__, "scientific source path"))
        previous = hashlib.sha256(snapshot[module.__name__.replace(".", "/") + ".py"]).hexdigest()
        actual = _file_hash(path)
        if module is benchmark and actual != previous and actual == _BENCHMARK_BYTES_REVISION[1]:
            actual = _BENCHMARK_BYTES_REVISION[0]
        extraction = _GENERIC_EXTRACTION_MODULES.get(module.__name__)
        if actual != previous and extraction is not None and actual == extraction[1]:
            actual = extraction[0]
        if actual != previous and not (
            module is benchmark and (previous, actual) == _BENCHMARK_VALIDATION_REVISION
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


def _context(value: object, source: Source, directory: Path) -> tuple[int, int]:
    context = _object(value)
    budget = _amount(context.get("budget_microusd"), "shared budget")
    calls = _amount(context.get("max_calls"), "shared call cap")
    scope = _text(context.get("scope"), "shared scope")
    _text(context.get("authorization_id"), "authorization ID")
    if context.get("terms_sha256") != _sha(
        {
            "currency": "USD",
            "budget_microusd": budget,
            "max_calls": calls,
            "scope": scope,
        }
    ):
        raise ValidationError("continuation authorization terms checksum differs")
    rows = context.get("runs")
    if not isinstance(rows, list):
        raise ValidationError("continuation requires its initial authorized run population")
    known, held, count = 0, 0, 0
    sources = []
    identities = set()
    for raw in rows:
        row = _object(raw)
        run_id = _text(row.get("run_id"), "authorized run ID")
        if run_id in identities:
            raise ValidationError("initial authorization population contains duplicate runs")
        identities.add(run_id)
        spent = _amount(row.get("spent_microusd"), "initial known cost")
        reserved = _amount(row.get("reserved_microusd"), "initial held cost")
        operations = _amount(row.get("operation_count"), "initial calls")
        if _amount(row.get("committed_microusd"), "initial committed cost") != spent + reserved:
            raise ValidationError("initial per-run financial totals do not reconcile")
        known += spent
        held += reserved
        count += operations
        if run_id == source.history.run_id:
            sources.append(row)
    if len(sources) != 1:
        raise ValidationError("original source must already be imported into the shared authority")
    row = sources[0]
    if (
        type(row.get("historical")) is not int
        or row.get("historical") != 1
        or row.get("active") is not False
        or row.get("directory") != str(directory)
        or row.get("manifest_sha256") != source.history.manifest_sha256
        or row.get("historical_ledger_sha256") != source.history.ledger_sha256
        or any(row.get(key) != value for key, value in source.history.totals().items())
    ):
        raise ValidationError("initial authorization does not bind the inactive sealed source")
    expected = {
        "spent_microusd": known,
        "reserved_microusd": held,
        "committed_microusd": known + held,
        "operation_count": count,
        "available_microusd": max(0, budget - known - held),
        "remaining_calls": max(0, calls - count),
    }
    if any(
        _amount(context.get(key), "initial " + key) != amount for key, amount in expected.items()
    ):
        raise ValidationError("initial combined authorization totals do not reconcile")
    if expected["available_microusd"] <= 0 or expected["remaining_calls"] <= 0:
        raise ValidationError("the shared authorization has no remaining continuation allowance")
    return expected["available_microusd"], min(55, expected["remaining_calls"])


def _runtime_archive(runtime_sha256: str) -> bytes:
    files = {}
    for source_file in sorted(Path(__file__).parent.glob("*.py")):
        _plain(source_file)
        files["buddha/" + source_file.name] = source_file.read_bytes()
    fingerprints = {
        name.removeprefix("buddha/"): hashlib.sha256(raw).hexdigest() for name, raw in files.items()
    }
    if _sha(fingerprints) != runtime_sha256:
        raise ValidationError("runtime changed while preserving continuation source")
    notices = Path(__file__).parent.parent / "THIRD_PARTY_NOTICES.md"
    _plain(notices)
    files[notices.name] = notices.read_bytes()
    index = {
        "format": "buddha.runtime-source-snapshot.v1",
        "python_version": platform.python_version(),
        "runtime_sha256": runtime_sha256,
        "files_sha256": {name: hashlib.sha256(raw).hexdigest() for name, raw in files.items()},
    }
    stream = io.BytesIO()
    with zipfile.ZipFile(stream, "w", compression=zipfile.ZIP_DEFLATED) as bundle:
        for name, raw in files.items():
            bundle.writestr(name, raw)
        bundle.writestr("source-index.json", _canonical(index) + b"\n")
    return stream.getvalue()


def _current_runtime(directory: Path, metadata: dict[str, object]) -> None:
    from buddha.authorization import runtime_fingerprint

    expected = _text(metadata["runtime_sha256"], "continuation runtime hash")
    _hex(expected, "continuation runtime hash")
    if expected != runtime_fingerprint():
        raise ValidationError("the continuation executable runtime changed")
    snapshot = _snapshot(
        directory / "runtime-source.zip",
        _text(metadata["runtime_archive_sha256"], "runtime archive hash"),
    )
    notices = Path(__file__).parent.parent / "THIRD_PARTY_NOTICES.md"
    archived_notices = snapshot.pop(notices.name, None)
    if archived_notices is None or hashlib.sha256(archived_notices).hexdigest() != _file_hash(
        notices
    ):
        raise ValidationError("runtime archive must preserve its matching third-party notices")
    prefix = "buddha/"
    if any(not name.startswith(prefix) or "/" in name[len(prefix) :] for name in snapshot):
        raise ValidationError("runtime archive must contain only package sources and their notices")
    fingerprints = {
        name.removeprefix(prefix): hashlib.sha256(raw).hexdigest() for name, raw in snapshot.items()
    }
    if _sha(fingerprints) != expected:
        raise ValidationError("runtime archive differs from the authorized executable runtime")


def load_continuation(
    directory: Path,
    manifest: dict[str, object],
    settings: RunSettings,
    spec: SearchSpec,
    prompts: tuple[Prompt, ...],
) -> Continuation:
    """Validate inherited evidence and saved sources without loading or funding a run."""
    from buddha.search import _read

    try:
        directory = directory.absolute()
        _plain(directory)
        _plain(directory / "manifest.json")
        if _read(directory / "manifest.json") != manifest or (
            manifest.get("format") != "buddha.policy-search-continuation.v1"
        ):
            raise ValidationError("continuation manifest differs from its saved identity")
        metadata = _object(manifest.get("continuation"))
        if set(metadata) != _METADATA_KEYS or metadata["format"] != "buddha.linked-continuation.v1":
            raise ValidationError("unsupported linked-continuation metadata")
        if metadata["archived_runtime_file"] != "source-runtime.zip" or (
            metadata["runtime_archive_file"] != "runtime-source.zip"
        ):
            raise ValidationError(
                "continuation source archives must use their declared local names"
            )
        source_directory = Path(_text(metadata["source_directory"], "original source directory"))
        _plain(source_directory)
        if not source_directory.is_absolute() or str(source_directory.resolve()) != str(
            source_directory
        ):
            raise ValidationError("original source directory must be its canonical absolute path")
        source = read_source(
            source_directory,
            manifest_sha256=_text(metadata["source_manifest_sha256"], "source manifest hash"),
            ledger_sha256=_text(metadata["source_ledger_sha256"], "source ledger hash"),
            archived_runtime_zip=directory / "source-runtime.zip",
            archived_runtime_sha256=_text(
                metadata["archived_runtime_sha256"], "source archive hash"
            ),
        )
        if metadata["source_run_id"] != source.history.run_id or (
            metadata["acceptance_reason"] != _ACCEPTANCE_REASON
        ):
            raise ValidationError("original identity or reviewed continuation purpose differs")
        authority_path = Path(_text(metadata["authorization_path"], "shared authorization path"))
        if not authority_path.is_absolute() or str(authority_path.resolve()) != str(authority_path):
            raise ValidationError("shared authority path must be its canonical absolute path")
        budget, calls = _context(metadata["authorization_context"], source, source_directory)
        if settings != replace(source.settings, budget_microusd=budget, max_calls=calls) or (
            spec != source.spec or tuple(prompts) != (source.prompt,)
        ):
            raise ValidationError("continuation changed frozen science or its allocated allowance")
        original = source.history.manifest
        if any(
            manifest.get(key) != original[key]
            for key in (
                "source_sha256",
                "splits",
                "families",
                "screen_ids",
                "synthetic",
                "population",
            )
        ):
            raise ValidationError("continuation changed its original dataset or screen population")
        new_run_id = _text(manifest.get("run_id"), "continuation run ID")
        references = source.references(new_run_id)
        replacement = source.replacement(new_run_id)
        if _canonical(metadata["inherited"]) != _canonical(
            [asdict(ref) for ref in references.values()]
        ) or (_canonical(metadata["replacement"]) != _canonical(asdict(replacement))):
            raise ValidationError(
                "inherited receipts or replacement lineage differ from authentic slots"
            )
        _current_runtime(directory, metadata)
        return Continuation(
            source,
            references,
            replacement,
            _canonical(metadata["authorization_context"]).decode("utf-8"),
        )
    except (
        OSError,
        TypeError,
        ValueError,
        KeyError,
        zipfile.BadZipFile,
        zlib.error,
        EOFError,
        RuntimeError,
    ) as error:
        if isinstance(error, ValidationError):
            raise
        raise ValidationError("linked continuation could not be loaded consistently") from None


def prepare_continuation(
    out: Path,
    *,
    source: Path,
    source_manifest_sha256: str,
    source_ledger_sha256: str,
    authorization: Authorization,
    archived_runtime_zip: Path,
    archived_runtime_sha256: str,
) -> Path:
    """Publish a source-linked new run, then atomically claim its shared allowance.

    Partial unbound directories are preserved for review. No automatic repair,
    provider call, unknown release or replacement dispatch happens here.
    """
    from buddha.authorization import Authorization, runtime_fingerprint
    from buddha.search import _atomic, _comparison, _contracts, _ledger, _put, load_search

    if not isinstance(authorization, Authorization) or not isinstance(out, Path):
        raise ValidationError("continuation preparation requires an authority and filesystem paths")
    try:
        origin = read_source(
            source,
            manifest_sha256=source_manifest_sha256,
            ledger_sha256=source_ledger_sha256,
            archived_runtime_zip=archived_runtime_zip,
            archived_runtime_sha256=archived_runtime_sha256,
        )
        source = source.absolute().resolve()
        out = out.absolute()
        _plain(out.parent)
        if out.exists() or out.is_symlink():
            _plain(out)
            if not (out / "manifest.json").is_file():
                raise ValidationError(
                    "partial unbound continuation requires review; directory preserved"
                )
            manifest, selected, spec, prompts = load_search(out)
            saved = load_continuation(out, manifest, selected, spec, prompts)
            metadata = _object(manifest["continuation"])
            if saved.source.history != origin.history or metadata["authorization_path"] != str(
                authorization.path
            ):
                raise ValidationError(
                    "existing continuation belongs to a different source or authority"
                )
        else:
            context = authorization.summary()
            context.pop("event_count")
            budget, calls = _context(context, origin, source)
            selected = replace(origin.settings, budget_microusd=budget, max_calls=calls)
            runtime = runtime_fingerprint()
            runtime_raw = _runtime_archive(runtime)
            new_run_id = uuid.uuid4().hex
            references = origin.references(new_run_id)
            replacement = origin.replacement(new_run_id)
            metadata = {
                "format": "buddha.linked-continuation.v1",
                "source_directory": str(source),
                "source_run_id": origin.history.run_id,
                "source_manifest_sha256": origin.history.manifest_sha256,
                "source_ledger_sha256": origin.history.ledger_sha256,
                "archived_runtime_file": "source-runtime.zip",
                "archived_runtime_sha256": archived_runtime_sha256,
                "runtime_sha256": runtime,
                "runtime_archive_file": "runtime-source.zip",
                "runtime_archive_sha256": hashlib.sha256(runtime_raw).hexdigest(),
                "authorization_path": str(authorization.path),
                "acceptance_reason": _ACCEPTANCE_REASON,
                "authorization_context": context,
                "inherited": [asdict(ref) for ref in references.values()],
                "replacement": asdict(replacement),
            }
            manifest = origin.history.manifest | {
                "format": "buddha.policy-search-continuation.v1",
                "run_id": new_run_id,
                "settings": asdict(selected),
                "contracts": _contracts(),
                "continuation": metadata,
            }
            manifest["comparison_key"] = _comparison(
                selected,
                _text(manifest["source_sha256"], "dataset hash"),
                (origin.prompt,),
                manifest["contracts"],
            )
            out.mkdir()
            _plain(out)
            original_archive = archived_runtime_zip.read_bytes()
            if hashlib.sha256(original_archive).hexdigest() != archived_runtime_sha256:
                raise ValidationError("original source archive changed during preparation")
            _atomic(out / "source-runtime.zip", original_archive)
            _atomic(out / "runtime-source.zip", runtime_raw)
            dataset = (source / "dataset.jsonl").read_bytes()
            if hashlib.sha256(dataset).hexdigest() != manifest["source_sha256"]:
                raise ValidationError("original dataset changed during preparation")
            _atomic(out / "dataset.jsonl", dataset)
            _put(out / "manifest.json", manifest)
            _ledger(out, manifest, selected)
            loaded = load_search(out)
            load_continuation(out, *loaded)
        authorization.bind_continuation(
            out,
            runtime_sha256=_text(metadata["runtime_sha256"], "continuation runtime hash"),
            source_run_id=origin.history.run_id,
            operation_id=origin.unknown.operation_id,
            evidence_sha256=origin.history.ledger_sha256,
            reason=_text(metadata["acceptance_reason"], "continuation acceptance reason"),
        )
        return out
    except (OSError, TypeError, ValueError, KeyError) as error:
        if isinstance(error, ValidationError):
            raise
        raise ValidationError(
            "continuation preparation failed; preserve any partial directory"
        ) from None
