"""Bounded supplied-control study over the unchanged, funded native partition CLI.

This is a development audit, not generated C1 Answers or a benchmark baseline.
No keys are read and no authorization is created here. The caller supplies the
reviewed Selection, shared authority and transport. There is no paid CLI shortcut.
"""

import hashlib
import importlib.util
import sys
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
    Gateway,
    RawHTTPTransport,
    _read_manifest,
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
    return [Path(__file__).resolve(), MATERIALIZER] + [
        package / (name + ".py") for name in (*RUNNER_FILES, "executor", "native_run", "baseline")
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


def _coverage(attempt, report, batch):
    if report["status"] != "complete":
        raise NativeAuditError("an incomplete native command cannot publish study coverage")
    name = "v1.1/partitions.jsonl"
    raw = _read(attempt / "artifacts" / name, report["artifacts"][name])
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
    if found != set(expected):
        raise NativeAuditError("native study output omits selected targets")


@checked
def run_native_audit(directory, *, transport):
    """Run/resume original owners; fresh occasions are never reconstructed as resume."""
    if not isinstance(directory, Path) or not isinstance(transport, RawHTTPTransport):
        raise NativeAuditError("study needs its original directory and raw transport")
    directory = directory.absolute()
    with _exclusive(directory):
        return _run(directory, transport)


def _run(directory, transport):
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
    reports = []
    seals = {}
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
            report = NativeSession(gateway, descriptor=recipe, output=attempt).run()
            if report["status"] != "complete":
                return {
                    "format": "buddha.meas02-native-study-report.v1",
                    "status": "incomplete",
                    "stopped_batch": index,
                    "batches": reports + [report],
                    "authorization": authority.summary(),
                    "claim": CLAIM,
                }
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
    result = {
        "format": "buddha.meas02-native-study-report.v1",
        "status": "complete",
        "input_kind": "supplied audit controls",
        "target_count": 40,
        "batches": reports,
        "batch_seals": seals,
        "claim": CLAIM,
    }
    _same_or_write(directory / "report.json", _json(result))
    return result
