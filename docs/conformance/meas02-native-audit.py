"""Bounded supplied-control study over the unchanged, funded native partition CLI.

This is a development audit, not generated C1 Answers or a benchmark baseline.
No keys are read and no authorization is created here. The caller supplies the
reviewed Selection, shared authority and transport. There is no paid CLI shortcut.
"""

import hashlib
import importlib.util
import sys
import uuid
from functools import wraps
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from buddha.baseline import (  # noqa: E402
    _absolute,
    _component,
    _exclusive,
    _read,
    _same_or_write,
    _write,
)
from buddha.gateway import (  # noqa: E402
    CAPABILITIES,
    Gateway,
    RawHTTPTransport,
    _read_manifest,
    _review,
    _spec,
    execution_identity,
    prepare_gateway,
)
from buddha.native_run import RUNNER_FILES, NativeSession  # noqa: E402
from buddha.releases import (  # noqa: E402
    ReleaseError,
    _json,
    _load,
    _object,
    _path,
    _root,
    file_hash,
    inventory,
)

MATERIALIZER = Path(__file__).with_name("meas02-materialize.py")
SPEC = importlib.util.spec_from_file_location("_meas02_native_materializer", MATERIALIZER)
if SPEC is None or SPEC.loader is None:
    raise RuntimeError("MEAS02_MATERIALIZER_UNAVAILABLE")
materializer = importlib.util.module_from_spec(SPEC)
MATERIALIZER_SHA256 = "361ec95b56802eb018681113f012d0f4efaec48d587e556bc6df9993aae26c7d"
# Compile the exact reviewed engineering bytes: an adjacent .pyc is not evidence
# of this source, even when Python considers its timestamp/size current.
exec(  # nosec B102 - hash-bound first-party engineering source, never official/LLM code
    compile(_read(MATERIALIZER, MATERIALIZER_SHA256), str(MATERIALIZER), "exec"),
    materializer.__dict__,
)

PROVENANCE_SHA256 = "31a8ed84887cf85a391b2729e8cb0ea656fa331e82b413d8b954c7c9f0c294a3"
CLAIM = "supplied audit controls; no C1 generation, quality score or improvement claim"


class NativeAuditError(ReleaseError):
    """The frozen study cannot safely prepare, continue or publish coverage."""


def checked(function):
    @wraps(function)
    def invoke(*args, **kwargs):
        try:
            return function(*args, **kwargs)
        except (ValueError, TypeError, KeyError, OSError) as error:
            if isinstance(error, NativeAuditError):
                raise
            raise NativeAuditError(
                "invalid study configuration or evidence; state retained"
            ) from None

    return invoke


def arguments(model, seed):
    argv = [
        "--eval-dir",
        "{artifacts}",
        "--version",
        "1.1",
        "--alg",
        "llm",
        "--judge-model",
        model,
        "--concurrency",
        "1",
    ]
    return argv if seed is None else argv + ["--seed", str(seed)]


def _reference(release):
    pins = {
        "common.py": "ba60bf0f2a409c3774d75880f305325a28ed34320610667542a4596c41f424af",
        "judge.py": "4decf04790b90a03368eb792dfe29045435914a73ab83a52185d9dd0d1613902",
        "partition.py": "263970891ff3ee1cc8df369a33beefe5cb5de618b5dd146a5234536d97954aca",
    }
    if release["upstream"] != {
        "url": "https://github.com/novelty-bench/novelty-bench",
        "revision": "64a23be6b18ec1dacc298830aab276061b6e143c",
    } or any(release["source"].get("src/" + name) != digest for name, digest in pins.items()):
        raise NativeAuditError("MEAS02 requires its pinned official reference sources")


def _sources():
    if file_hash(MATERIALIZER) != MATERIALIZER_SHA256:
        raise NativeAuditError("consumed materializer source changed before invocation binding")
    package = ROOT / "buddha"
    return [
        Path(__file__).resolve(),
        MATERIALIZER,
        Path(__file__).with_name("meas02-run.py"),
        Path(__file__).with_name("meas02-live.py"),
    ] + [
        package / (name + ".py")
        for name in (*RUNNER_FILES, "executor", "native_run", "baseline", "__main__")
    ]


def _owner_id(directory, descriptor, index):
    return (
        "meas02-"
        + hashlib.sha256(_json([str(directory), file_hash(descriptor), index])).hexdigest()
    )


def _definition(descriptor, bindings=None):
    def consume(path):
        return _read(path, None if bindings is None else bindings[str(path)])

    definition = _object(
        _load(consume(descriptor)), {"format", "pack", "proposal", "provenance", "native"}
    )
    if definition["format"] != "buddha.meas02-native-audit.v1":
        raise NativeAuditError("unsupported study descriptor")
    sources = [_absolute(definition[name]) for name in ("pack", "proposal", "provenance")]
    pack, proposal, provenance = [consume(path) for path in sources]
    if hashlib.sha256(provenance).hexdigest() != PROVENANCE_SHA256:
        raise NativeAuditError("study provenance differs from frozen development references")
    _load(provenance)
    batches = materializer.materialize(pack, proposal)
    native = _object(
        definition["native"],
        {
            "selection",
            "roots",
            "environment",
            "hooks",
            "executor",
            "profiles",
            "budget_microusd",
            "max_calls",
        },
    )
    selection, roots = _component(native)
    release = selection.to_record()["release"]
    _reference(release)
    models = _object(_object(native["profiles"], {"openai"})["openai"])
    if len(models) != 1:
        raise NativeAuditError("study requires one explicit reviewed OpenAI judge")
    model = next(iter(models))
    if release["commands"] != [
        {"module": "src.partition", "argv": arguments(model, batch["seed"])} for batch in batches
    ] or release["artifacts"] != {
        "answers": "generations.jsonl",
        "results": ["v1.1/partitions.jsonl"],
        "summary": "v1.1/summary.json",
    }:
        raise NativeAuditError("study commands or artifact paths differ from declared occasions")
    return definition, sources, batches, selection, roots


def _files(directory, descriptor, definition, sources, batches, selection, roots, *, create=False):
    """One deterministic byte layout; reruns compare instead of rewriting any input."""
    context = directory / "context.json"
    metadata = directory / "targets.json"
    expected = {
        context: _json(
            {
                "format": "buddha.meas02-study-context.v1",
                "descriptor": str(descriptor.absolute()),
                "claim": CLAIM,
            }
        ),
        metadata: _json(
            [
                {key: value for key, value in batch.items() if key != "native_bytes"}
                for batch in batches
            ]
        ),
    }
    native = definition["native"]
    components = selection.to_record()["components"]
    release = selection.to_record()["release"]
    descriptors = []
    for index, batch in enumerate(batches):
        staging = directory / "inputs" / str(index)
        if create:
            staging.mkdir()
        raw = batch["native_bytes"]
        data = staging / "generations.jsonl"
        expected[data] = raw
        command = {
            "index": index,
            "module": "src.partition",
            "argv": [
                "/scratch/artifacts" if item == "{artifacts}" else item
                for item in release["commands"][index]["argv"]
            ],
        }
        command["sha256"] = hashlib.sha256(_json(command)).hexdigest()
        description = {
            "format": "buddha.native-command.v1",
            "worker": {
                "type": "configure",
                "format": "buddha.native-worker.v1",
                "command": command,
                "release_sha256": selection.release_sha256,
                "answers_sha256": hashlib.sha256(raw).hexdigest(),
                "roots": {
                    "official": "/official",
                    "runner": "/runner",
                    "environment": "/opt/venv",
                    "inputs": "/inputs",
                    "artifacts": "/scratch/artifacts",
                },
                "inventories": {
                    "official": components["official"],
                    "runner": components["runner"],
                    "environment": native["environment"],
                },
                "inputs": [
                    {
                        "source": "generations.jsonl",
                        "destination": "generations.jsonl",
                        "sha256": hashlib.sha256(raw).hexdigest(),
                    }
                ],
                "hooks": native["hooks"],
            },
            "executor": _object(native["executor"])
            | {
                "mounts": [
                    ["/official", str(roots["official"])],
                    ["/runner", str(roots["runner"])],
                    ["/inputs", str(staging)],
                ],
            },
            "profiles": native["profiles"],
        }
        target = directory / ("command-" + str(index) + ".json")
        expected[target] = _json(description)
        descriptors.append(target)
    for path, raw in expected.items():
        if create:
            _write(path, raw)
        elif _read(path) != raw:
            raise NativeAuditError("materialized study input differs from original sources")
    for index in range(4):
        staging = directory / "inputs" / str(index)
        if inventory(staging) != {"generations.jsonl": file_hash(staging / "generations.jsonl")}:
            raise NativeAuditError("native study staging contains unexpected files")
    bound = [context, descriptor, *sources, *expected.keys(), *_sources()]
    # context occurs in both layout and pointer list; bind each input exactly once.
    return list(dict.fromkeys(bound)), descriptors


@checked
def prepare_native_audit(directory, *, descriptor, authorization, review):
    """Freeze all four original owners; no credentials, calls or new allocation."""
    if not isinstance(directory, Path) or not isinstance(descriptor, Path):
        raise NativeAuditError("study requires Path locations")
    descriptor = descriptor.absolute()
    definition, sources, batches, selection, roots = _definition(descriptor)
    directory = directory.absolute()
    _root(directory.parent)
    _path(directory.name)
    if any(directory.is_relative_to(root) for root in roots.values()):
        raise NativeAuditError("study output must be outside selected components")
    directory.mkdir()
    for name in ("owners", "inputs", "attempts", "completed"):
        (directory / name).mkdir()
    bound, _ = _files(
        directory, descriptor, definition, sources, batches, selection, roots, create=True
    )
    native = definition["native"]
    for index in range(4):
        prepare_gateway(
            directory / "owners" / str(index),
            selection=selection,
            roots=roots,
            authorization=authorization,
            budget_microusd=native["budget_microusd"],
            max_calls=native["max_calls"],
            input_files=bound,
            review=review,
            run_id=_owner_id(directory, descriptor, index),
        )
    return directory


def _partition_ids(raw, batch, *, complete):
    """Validate literal native rows; a partial file never establishes batch completion."""
    rows = [_load(line) for line in raw.splitlines()]
    expected = {_load(line)["id"]: _load(line) for line in batch["native_bytes"].splitlines()}
    found = set()
    for row in rows:
        row = _object(row)
        identity = row["id"]
        if type(identity) is not str or identity not in expected or identity in found:
            raise NativeAuditError("native study output changes, repeats or adds target IDs")
        source = expected[identity]
        labels = row["partition"]
        if (
            row["prompt"] != source["prompt"]
            or row["generations"] != source["generations"]
            or type(labels) is not list
            or len(labels) != len(source["generations"])
            or any(type(value) is not int or value < 0 for value in labels)
            or type(row["distinct"]) is not int
            or row["distinct"] != len(set(labels))
        ):
            raise NativeAuditError("native study output changes source bytes or partition coverage")
        found.add(identity)
    if complete and found != set(expected):
        raise NativeAuditError("native study output omits selected targets")
    return [identity for identity in expected if identity in found]


def _coverage(attempt, report, batch):
    if report["status"] != "complete":
        raise NativeAuditError("an incomplete native command cannot publish study coverage")
    name = "v1.1/partitions.jsonl"
    return _partition_ids(
        _read(attempt / "artifacts" / name, report["artifacts"][name]), batch, complete=True
    )


@checked
def run_native_audit(directory, *, transport):
    """Run/resume original owners; fresh occasions are never reconstructed as resume."""
    if not isinstance(directory, Path) or not isinstance(transport, RawHTTPTransport):
        raise NativeAuditError("study needs its original directory and raw transport")
    directory = directory.absolute()
    with _exclusive(directory):
        return _run(directory, transport)


def _state(directory, transport):
    anchor = Gateway(directory / "owners/0", transport=transport)
    initial = _read_manifest(anchor.directory)
    bindings = {item["path"]: item["sha256"] for item in initial["invocation"]["inputs"]}
    context_path = directory / "context.json"
    context = _load(_read(context_path, bindings[str(context_path)]))
    descriptor = _absolute(context["descriptor"])
    definition, sources, batches, selection, roots = _definition(descriptor, bindings)
    bound, descriptors = _files(
        directory, descriptor, definition, sources, batches, selection, roots
    )
    if sorted(path.name for path in (directory / "owners").iterdir()) != ["0", "1", "2", "3"]:
        raise NativeAuditError("preparation lacks exactly four original study owners")
    expected_inputs = [{"path": str(path.absolute()), "sha256": file_hash(path)} for path in bound]
    owners = [directory / "owners" / str(index) for index in range(4)]
    records = [_read_manifest(owner) for owner in owners]
    from buddha.authorization import Authorization

    authority = Authorization(_absolute(records[0]["authorization_path"]))
    native = definition["native"]
    for index, (owner, record) in enumerate(zip(owners, records, strict=True)):
        execution_identity(owner, record)
        if (
            record["run_id"] != _owner_id(directory, descriptor, index)
            or record["authorization_path"] != str(authority.path)
            or record["selection"] != selection.to_record()
            or record["roots"] != {key: str(path) for key, path in roots.items()}
            or record["settings"]
            != {"budget_microusd": native["budget_microusd"], "max_calls": native["max_calls"]}
            or record["review"] != records[0]["review"]
            or record["invocation"]["inputs"] != expected_inputs
        ):
            raise NativeAuditError("study owner differs from its shared authority or frozen inputs")
    gateways = [anchor] + [Gateway(owner, transport=transport) for owner in owners[1:]]
    names = {path.name for path in (directory / "completed").iterdir()}
    if names != {str(index) + ".json" for index in range(len(names))} or len(names) > 4:
        raise NativeAuditError("study completion records are not the original ordered prefix")
    if (directory / "report.json").exists() and len(names) != 4:
        raise NativeAuditError("published study report lacks four complete anchored batches")
    protected = {}
    completions = {}
    # Validate every retained completion before any unfinished batch can spend.
    for index, (gateway, batch) in enumerate(zip(gateways, batches, strict=True)):
        sealed = directory / "completed" / (str(index) + ".json")
        if not sealed.exists():
            continue
        digest = file_hash(sealed)
        if any(
            row["run_id"] == records[index]["run_id"] and row["active"]
            for row in authority.summary()["runs"]
        ):
            raise NativeAuditError("completion is unanchored; interrupted evidence retained")
        authority.deactivate(records[index]["run_id"], "MEAS02 completed: " + digest)
        seal = _object(
            _load(_read(sealed, digest)), {"format", "index", "owner_sha256", "attempt", "files"}
        )
        attempt = directory / _path(seal["attempt"])
        if (
            seal["format"] != "buddha.meas02-batch.v1"
            or seal["index"] != index
            or seal["owner_sha256"] != gateway.manifest_sha256
            or not attempt.is_relative_to(directory / "attempts")
            or inventory(attempt) != seal["files"]
        ):
            raise NativeAuditError("completed study seal or literal artifacts changed")
        report = _load(_read(attempt / "report.json", seal["files"]["report.json"]))
        _coverage(attempt, report, batch)
        completions[index] = (report, attempt, digest)
        protected.update({attempt / name: value for name, value in seal["files"].items()})
        protected[sealed] = digest
    if len(completions) == 4 and (directory / "report.json").exists():
        expected = _result(
            [completions[index][0] for index in range(4)],
            {str(index): completions[index][2] for index in range(4)},
        )
        if _read(directory / "report.json") != _json(expected):
            raise NativeAuditError("published study report differs from anchored completion")
    active = {row["run_id"]: row["active"] for row in authority.summary()["runs"]}
    if any(not active[records[index]["run_id"]] for index in range(4) if index not in completions):
        raise NativeAuditError("an unfinished study owner is inactive; original state retained")
    return {
        "definition": definition,
        "batches": batches,
        "descriptors": descriptors,
        "records": records,
        "gateways": gateways,
        "authority": authority,
        "completions": completions,
        "protected": protected,
    }


@checked
def check_native_audit(directory):
    """Validate original live owners before key entry; never dispatch or create funding.

    An existing unsent reservation may be reusable. This is not a promise that
    native scheduling next requests that exact operation or completes the audit.
    Normal run validation and exact Gateway guards still repeat after key entry.
    """
    if not isinstance(directory, Path):
        raise NativeAuditError("study needs its original Path directory")
    directory = directory.absolute()
    with _exclusive(directory):
        state = _state(directory, RawHTTPTransport(allow_paid=False))
        records = state["records"]
        remaining = [index for index in range(4) if index not in state["completions"]]
        result = {
            "status": "ready" if remaining else "complete",
            "next_batch": remaining[0] if remaining else None,
            "next_occasion": state["batches"][remaining[0]]["occasion"] if remaining else None,
            "authorization_path": records[0]["authorization_path"],
            "review": _load(_json(records[0]["review"])),
            "credential_sha256": _load(_json(records[0]["review"]["credential_sha256"])),
            "source_files": [dict(item) for item in records[0]["invocation"]["inputs"]],
            "profiles": [],
        }
        if not remaining:
            return result
        index = remaining[0]
        gateway = state["gateways"][index]
        gateway.ledger.authorize_dispatch()
        _review(records[index]["review"], fresh=True)
        specs = []
        for provider, mapping in state["definition"]["native"]["profiles"].items():
            capability = next(key for key, value in CAPABILITIES.items() if value[0] == provider)
            profiles = records[index]["profiles"][capability]["profiles"]
            for model, name in mapping.items():
                spec = _spec(profiles[name]["spec"])
                if spec.model != model or spec.provider != provider:
                    raise NativeAuditError("native judge differs from reviewed model profile")
                specs.append(spec)
        if not specs:
            raise NativeAuditError("unfinished study lacks a reviewed judge profile")
        local = gateway.ledger.totals()
        shared = state["authority"].summary()
        # Own unsent holds may be reused without fresh capacity; another owner's
        # holds are not credit. Exact request identity remains Gateway-owned.
        reserve = min(spec.reserve_microusd() for spec in specs)
        if local["reserved_microusd"] < reserve:
            settings = records[index]["settings"]
            if (
                shared["remaining_calls"] == 0
                or local["operation_count"] >= settings["max_calls"]
                or shared["available_microusd"] < reserve
                or settings["budget_microusd"] - local["committed_microusd"] < reserve
            ):
                raise NativeAuditError("study lacks verified capacity for a new physical attempt")
        result["profiles"] = specs
        return result


def _result(reports, seals):
    return {
        "format": "buddha.meas02-native-study-report.v1",
        "status": "complete",
        "input_kind": "supplied audit controls",
        "target_count": 40,
        "batches": reports,
        "batch_seals": seals,
        "claim": CLAIM,
    }


def _operations(state):
    """Reference existing receipts without decoding, importing or changing them."""
    result = []
    for index, gateway in enumerate(state["gateways"]):
        identities = dict.fromkeys(
            row["operation_id"]
            for row in gateway.ledger.events()
            if row["operation_id"] is not None
        )
        for identity in identities:
            operation = gateway.ledger.get(identity)
            if operation is None:
                raise NativeAuditError("observed operation is missing from its original ledger")
            result.append(
                {
                    "owner": index,
                    "operation_id": identity,
                    "request_sha256": operation.request_sha256,
                    "status": operation.status,
                    "reserve_microusd": operation.reserve_microusd,
                    "actual_microusd": operation.actual_microusd,
                    "receipt_sha256": (
                        hashlib.sha256(_json(operation.response)).hexdigest()
                        if operation.response is not None
                        else None
                    ),
                }
            )
    return result


def _stop(state, index, report, operations, summary, reason):
    native = report["worker"]["reason"] if report else None
    execution = report.get("execution", {}).get("reason") if report else None
    codes = []
    if any(row["status"] in {"unknown", "dispatched"} for row in operations):
        codes.append("unknown")
    if any(
        row["actual_microusd"] is not None and row["actual_microusd"] > row["reserve_microusd"]
        for row in operations
    ):
        codes.append("bounds")
    record = state["records"][index]
    local = state["gateways"][index].ledger.totals()
    settings = record["settings"]
    if summary["remaining_calls"] == 0 or local["operation_count"] >= settings["max_calls"]:
        codes.append("attempt_limit")
    mapping = state["definition"]["native"]["profiles"]["openai"]
    profile_name = next(iter(mapping.values()))
    profile = record["profiles"]["openai.chat-completions.v1"]["profiles"][profile_name]
    reserve = _spec(profile["spec"]).reserve_microusd()
    if (
        summary["available_microusd"] < reserve
        or settings["budget_microusd"] - local["committed_microusd"] < reserve
    ):
        codes.append("money")
    if reason == "interrupted" or native == "cancelled":
        primary = "interrupted"
    elif native == "unknown" or "unknown" in codes:
        primary = "unknown"
    elif native in {"protocol", "native_error"}:
        primary = native
    elif execution is not None:
        primary = execution
    elif report is not None and native == "complete":
        primary = "execution"
    elif native == "authority" or reason == "preflight":
        primary = codes[0] if len(codes) == 1 else "authority_undetermined"
    else:
        primary = reason
    return {
        "reason": primary,
        "codes": list(dict.fromkeys([primary, *codes])),
        "native_reason": native,
        "execution_reason": execution,
    }


def _partial(directory, state, index, *, attempt=None, report=None, reason="preflight"):
    """Append diagnostic evidence outside native inventories; never a completion seal."""
    batch = state["batches"][index]
    sealed_ids, reports, seals = [], [], {}
    for number, (completed, path, digest) in sorted(state["completions"].items()):
        sealed_ids.extend(_coverage(path, completed, state["batches"][number]))
        reports.append(completed)
        seals[str(number)] = digest
    files, partial_ids, partial_status = {}, [], "unavailable"
    if attempt is not None:
        files = inventory(attempt)
        if report is not None:
            if _read(attempt / "report.json", files["report.json"]) != _json(report) + b"\n":
                raise NativeAuditError("native partial report changed before observation")
            if any(
                files.get("artifacts/" + name) != digest
                for name, digest in report["artifacts"].items()
            ):
                raise NativeAuditError("native partial artifact differs from its report")
        names = [
            "artifacts/v1.1/partitions.jsonl",
            "artifacts/v1.1/partitions.jsonl.partial",
        ]
        present = [name for name in names if name in files]
        if present:
            try:
                if len(present) != 1:
                    raise NativeAuditError("native attempt has ambiguous result files")
                name = present[0]
                partial_ids = _partition_ids(
                    _read(attempt / name, files[name]), batch, complete=False
                )
                partial_status = "valid"
            except (ReleaseError, ValueError, KeyError, TypeError):
                partial_status = "invalid"
        for name, digest in files.items():
            _read(attempt / name, digest)
        if inventory(attempt) != files:
            raise NativeAuditError("partial attempt changed while observed")
        files = {
            (attempt / name).relative_to(directory).as_posix(): digest
            for name, digest in files.items()
        }
    expected = [target["target_id"] for group in state["batches"] for target in group["targets"]]
    operations = _operations(state)
    summary = state["authority"].summary()
    observed = set(sealed_ids + partial_ids)
    folder = directory / "observations"
    prior = {}
    if folder.exists():
        _root(folder)
        prior = {
            "observations/" + name: digest
            for name, digest in inventory(folder).items()
            if len(name) == 37
            and name.endswith(".json")
            and all(char in "0123456789abcdef" for char in name[:32])
        }
    observation = "observations/" + uuid.uuid4().hex + ".json"
    result = {
        "format": "buddha.meas02-native-study-report.v1",
        "status": "incomplete",
        "result": "partial",
        "observation": observation,
        "input_kind": "supplied audit controls",
        "target_count": 40,
        "stopped_batch": index,
        "stopped_occasion": batch["occasion"],
        "stop": _stop(state, index, report, operations, summary, reason),
        "coverage": {
            "expected_count": 40,
            "sealed_target_ids": sealed_ids,
            "partial_target_ids": partial_ids,
            "missing_target_ids": [identity for identity in expected if identity not in observed],
            "partial_status": partial_status,
            "scope": (
                "sealed batches plus THIS attempt's validated unsealed rows only; "
                "missing IDs are absent from this observation, not necessarily earlier "
                "unsealed attempts; API receipts are not target coverage"
            ),
        },
        "batches": reports + ([report] if report else []),
        "batch_seals": seals,
        "evidence": {
            "attempt": attempt.relative_to(directory).as_posix() if attempt else None,
            "files": files,
            "operations": operations,
            "prior_observations": prior,
            "receipt_hash_scope": (
                "canonical response record retained in each original owner ledger"
            ),
        },
        "authorization": summary,
        "claim": CLAIM,
    }
    if not folder.exists():
        folder.mkdir()
    _root(folder)
    _write(directory / observation, _json(result))
    return result


@checked
def record_stopped_audit(directory, *, reason="preflight"):
    """Record an actual run refusal after exact original-state validation; no key/call."""
    if not isinstance(directory, Path) or reason not in {"preflight", "interrupted", "protocol"}:
        raise NativeAuditError("invalid stopped-study observation")
    directory = directory.absolute()
    with _exclusive(directory):
        state = _state(directory, RawHTTPTransport(allow_paid=False))
        remaining = [index for index in range(4) if index not in state["completions"]]
        if not remaining:
            raise NativeAuditError("a complete study cannot be recorded as partial")
        return _partial(directory, state, remaining[0], reason=reason)


def _run(directory, transport):
    state = _state(directory, transport)
    descriptors, batches = state["descriptors"], state["batches"]
    gateways, records = state["gateways"], state["records"]
    authority, completions = state["authority"], state["completions"]
    protected = state["protected"]
    reports, seals = [], {}
    for index, (recipe, batch) in enumerate(zip(descriptors, batches, strict=True)):
        for path, digest in protected.items():
            _read(path, digest)
        gateway = gateways[index]
        sealed = directory / "completed" / (str(index) + ".json")
        if index in completions:
            report, attempt, digest = completions[index]
        else:
            ordinal = 0
            while (directory / "attempts" / f"{index}-{ordinal}").exists():
                ordinal += 1
            attempt = directory / "attempts" / f"{index}-{ordinal}"
            try:
                report = NativeSession(gateway, descriptor=recipe, output=attempt).run()
            except KeyboardInterrupt:
                _partial(
                    directory,
                    _state(directory, transport),
                    index,
                    attempt=attempt if attempt.exists() else None,
                    reason="interrupted",
                )
                raise
            if report["status"] != "complete":
                return _partial(
                    directory, _state(directory, transport), index, attempt=attempt, report=report
                )
            _coverage(attempt, report, batch)
            files = inventory(attempt)
            if _read(attempt / "report.json", files["report.json"]) != _json(report) + b"\n":
                raise NativeAuditError("native report changed before completion")
            for name, artifact_digest in report["artifacts"].items():
                if files.get("artifacts/" + name) != artifact_digest:
                    raise NativeAuditError("native artifact changed before completion")
            raw = _json(
                {
                    "format": "buddha.meas02-batch.v1",
                    "index": index,
                    "owner_sha256": gateway.manifest_sha256,
                    "attempt": attempt.relative_to(directory).as_posix(),
                    "files": files,
                }
            )
            digest = hashlib.sha256(raw).hexdigest()
            _write(sealed, raw)
            authority.deactivate(records[index]["run_id"], "MEAS02 completed: " + digest)
        _coverage(attempt, report, batch)
        protected.update({attempt / name: value for name, value in inventory(attempt).items()})
        protected[sealed] = digest
        seals[str(index)] = digest
        reports.append(report)
    for path, digest in protected.items():
        _read(path, digest)
    # A repeated read reports the same scientific completion, not later unrelated
    # authority activity. Every bound owner and completion is still revalidated.
    result = _result(reports, seals)
    _same_or_write(directory / "report.json", _json(result))
    return result
