"""Passive custody for an original-owner, independently anchored proposal outcome.

Saved consistency is not authentication of historical host state, source
authorship, child competence or improvement. Producer programs may be retired.
"""

import base64
import hashlib
import re
import sqlite3
import stat
from pathlib import Path
from typing import cast

from buddha import native_pipeline as pipeline
from buddha.candidate_generation import _recorded_sources
from buddha.doctor import _authority, _Busy, _Capture, _Unsupported
from buddha.gateway_history import read_gateway_history
from buddha.native_evidence import NativeEvidence, _adopt_capture, authority_observation
from buddha.releases import MAX_JSON_BYTES, Selection, _digest, _json, _load, _object, _path

_CLAIM = (
    "anchored proposal outcome only; no child competence, archive viability or improvement claim"
)
_AMOUNTS = ("committed_microusd", "spent_microusd", "reserved_microusd", "operation_count")


def _sha(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()


def _same(left: object, right: object) -> bool:
    return _json(left) == _json(right)


def _prefix(
    reader: NativeEvidence,
    recipe: dict[str, object],
    parent: str,
    descriptor_sha256: str,
    feedback_sha256: str,
) -> dict[str, int]:
    owner = reader.owner(reader.root / "owners/0")
    history = read_gateway_history(
        owner.directory,
        manifest_sha256=owner.manifest_sha256,
        ledger_sha256=owner.ledger_sha256,
    )
    if not _same(history.manifest, owner.manifest):
        raise reader.error_type("proposal owner changed during passive observation")
    count = len(history.operations)
    if count > cast(int, recipe["max_callbacks"]):
        raise reader.error_type("proposal callbacks exceed their original ceiling")
    expected = {
        pipeline._sha(
            [
                "buddha.candidate-improvement-call.v2"
                if recipe["format"] == "buddha.candidate-improvement.v2"
                else "buddha.candidate-improvement-call.v1",
                descriptor_sha256,
                parent,
                *(
                    [recipe["parent_agent_sha256"]]
                    if recipe["format"] == "buddha.candidate-improvement.v2"
                    else []
                ),
                feedback_sha256,
                ordinal,
            ]
        )
        for ordinal in range(count)
    }
    role, config = _object(recipe["profile"]), _object(recipe["config"])
    cap = "max_tokens" if config["provider"] == "anthropic" else "max_completion_tokens"
    observed = set()
    for operation in history.operations:
        if operation.status != "completed":
            raise reader.error_type("terminal proposal retains an unfinished original operation")
        request = _object(_object(operation.receipt)["request"])
        # History validates canonical encoding, physical identity and byte bounds.
        body = _load(base64.b64decode(cast(str, request["body_base64"]), validate=True))
        if (
            request["capability"] != role["capability"]
            or request["profile_id"] != role["profile_id"]
            or type(request["attempt"]) is not int
            or request["attempt"] != 0
            or request.get("headers", []) != []
            or body.get("model") != config["model"]
            or type(body.get(cap)) is not int
            or not 1 <= cast(int, body[cap]) <= cast(int, config["max_output_tokens"])
            or ("max_tokens" in body and "max_completion_tokens" in body)
        ):
            raise reader.error_type("proposal callback changes its original model contract")
        observed.add(request["logical_id"])
    if observed != expected or len(observed) != count:
        raise reader.error_type("proposal skipped or changed its original callback prefix")
    totals = history.totals()
    if totals != {key: owner.accounting()[key] for key in _AMOUNTS}:
        raise reader.error_type("proposal original-owner accounting changed")
    return totals


def collect_candidate_improvement(
    directory: Path,
    *,
    authorization: Path,
    expected_report_sha256: str | None = None,
    sink: _Capture | None = None,
) -> dict[str, object]:
    """Reconstruct complete custody, or verify one explicitly pinned publication."""
    from buddha import candidate_improvement as stage

    try:
        if not isinstance(directory, Path) or not isinstance(authorization, Path):
            raise stage.CandidateImprovementError("proposal evidence requires explicit Path inputs")
        if Path(stage.__file__).absolute() != Path(__file__).with_name("candidate_improvement.py"):
            raise stage.CandidateImprovementError("a different proposal stage was imported")
        directory, authorization = (
            pipeline._absolute(str(directory)),
            pipeline._absolute(str(authorization)),
        )
        if sink is not None and (
            type(sink) is not _Capture or not directory.is_relative_to(sink.root)
        ):
            raise stage.CandidateImprovementError(
                "proposal capture requires its original containing observation"
            )
        reader = NativeEvidence(
            directory, authorization, error_type=stage.CandidateImprovementError
        )
        owner_path = directory / "owners/0"
        owner_names = {
            name.split("/")[1] for name in reader.capture.entries if name.startswith("owners/")
        }
        seals = {name for name in reader.capture.entries if name.startswith("completed/")}
        if owner_names != {"0"} or seals != {"completed/0.json"}:
            raise stage.CandidateImprovementError("proposal has foreign owners or completion seals")
        owner = reader.owner(owner_path)
        funding = _authority(reader.capture, authorization, [owner])
        if funding is None or owner.manifest["authorization_path"] != str(authorization):
            raise stage.CandidateImprovementError("proposal belongs to another original authority")
        funded = []
        for row in reader._rows(funding["auth_runs"]):
            path = pipeline._absolute(row["directory"])
            if path.is_relative_to(directory) and (
                path != owner_path or row["run_id"] != owner.run_id
            ):
                raise stage.CandidateImprovementError("a retained funded proposal owner is missing")
            if row["run_id"] == owner.run_id:
                funded.append(row)
        if (
            len(funded) != 1
            or type(funded[0]["historical"]) is not int
            or funded[0]["historical"] != 0
            or funded[0]["runtime_sha256"] != owner.manifest["execution_sha256"]
        ):
            raise stage.CandidateImprovementError(
                "proposal is not its original nonhistorical owner"
            )
        context_raw = reader.bound(owner, directory / "context.json")
        context = _object(
            _load(context_raw),
            {
                "format",
                "descriptor",
                "expected_runtime_sha256",
                "expected_feedback_provenance_sha256",
            },
        )
        if context["format"] != stage.CONTEXT_FORMAT:
            raise stage.CandidateImprovementError("unsupported original proposal context")
        descriptor = pipeline._absolute(context["descriptor"])
        runtime_sha256 = _digest(context["expected_runtime_sha256"])
        provenance_sha256 = _digest(context["expected_feedback_provenance_sha256"])
        selection = Selection.from_bytes(_json(owner.manifest["selection"]))
        roots = {
            name: pipeline._absolute(path)
            for name, path in _object(owner.manifest["roots"]).items()
        }
        bindings = reader._bindings(owner)
        # Require the complete original installed helper closure as metadata;
        # retired producer/helper paths are never opened or re-inventoried here.
        source_names = {
            path.name for path in _recorded_sources(stage._sources(), owner.manifest["core"])
        }
        source_prefixes = {
            Path(path).parent
            for path in bindings
            if Path(path).name == "candidate_improvement.py"
            and all(str(Path(path).parent / name) in bindings for name in source_names)
        }
        if len(source_prefixes) != 1:
            raise stage.CandidateImprovementError("proposal omits its original installed sources")
        recipe, bundle, projected_sha256 = stage._definition(
            lambda path: reader.bound(owner, path),
            descriptor,
            selection,
            roots,
            runtime_sha256,
            provenance_sha256,
            _object(owner.manifest["profiles"]),
        )
        totals = _prefix(
            reader,
            recipe,
            selection.agent_sha256,
            _sha(reader.bound(owner, descriptor)),
            projected_sha256,
        )
        sealed = directory / "completed/0.json"
        seal_raw = reader.raw(sealed)
        seal_sha256 = _sha(seal_raw)
        anchors = [
            row["reason"]
            for row in reader._rows(funding["auth_deactivations"])
            if row["run_id"] == owner.run_id
        ]
        seal = _object(_load(seal_raw), {"format", "index", "owner_sha256", "attempt", "files"})
        relative = _path(seal["attempt"])
        if (
            seal["format"] != stage.SEAL_FORMAT
            or type(seal["index"]) is not int
            or seal["index"] != 0
            or seal["owner_sha256"] != owner.manifest_sha256
            or not re.fullmatch(r"attempts/0-(?:0|[1-9][0-9]*)", relative)
            or anchors != [stage.ANCHOR_PREFIX + seal_sha256]
        ):
            raise stage.CandidateImprovementError("proposal lacks its original terminal anchor")
        attempt = directory / relative
        files = _object(seal["files"])
        prefix = relative + "/"
        actual = {
            name.removeprefix(prefix)
            for name in reader.capture.entries
            if name.startswith(prefix) and stat.S_ISREG((directory / name).lstat().st_mode)
        }
        if set(files) != actual or "report.json" not in files:
            raise stage.CandidateImprovementError("proposal terminal attempt inventory differs")
        for name, digest in files.items():
            reader.raw(attempt / _path(name), _digest(digest))
        outcome_raw = reader.raw(attempt / "report.json")
        outcome = _load(outcome_raw)
        if outcome_raw != _json(outcome) + b"\n":
            raise stage.CandidateImprovementError(
                "proposal outcome is not its original canonical output"
            )
        stage._validate_outcome(
            attempt,
            outcome,
            recipe=recipe,
            bundle=bundle,
            runtime_sha256=runtime_sha256,
            owner=owner.manifest,
            totals=totals,
            read=reader.raw,
        )
        improvement = reader.record(attempt / "session/report.json")
        child: dict[str, object] | None = None
        if outcome["disposition"] == "materialized":
            source_sha256 = _sha(reader.raw(attempt / "session/child/candidate.py"))
            child = {
                "directory": str(attempt / "session/child"),
                "entrypoint": "candidate.py",
                "agent_sha256": pipeline._sha({"candidate.py": source_sha256}),
                "source_sha256": source_sha256,
                "lineage": {
                    "path": str(attempt / "session/lineage.json"),
                    "sha256": _sha(reader.raw(attempt / "session/lineage.json")),
                },
            }
        current = authority_observation(reader.capture, authorization, funding)
        detached = recipe["format"] == "buddha.candidate-improvement.v2"
        result: dict[str, object] = {
            "format": "buddha.candidate-improvement-stage-report.v2"
            if detached
            else "buddha.candidate-improvement-stage-report.v1",
            "status": "complete",
            "disposition": outcome["disposition"],
            "reason": outcome["reason"],
            "parent_agent_sha256": recipe["parent_agent_sha256"],
            **({"improver_agent_sha256": selection.agent_sha256} if detached else {}),
            "stage_seal_sha256": seal_sha256,
            "outcome": outcome,
            "improvement": improvement,
            "child": child,
            "authorization": current,
            "provenance": {
                "context_sha256": _sha(context_raw),
                "original_inputs": bindings,
                "owner": {
                    "directory": str(owner_path),
                    "run_id": owner.run_id,
                    "manifest_sha256": owner.manifest_sha256,
                    "ledger_sha256": owner.ledger_sha256,
                },
                "seals": {"completed/0.json": seal_sha256},
            },
            "claim": _CLAIM,
        }
        if expected_report_sha256 is not None:
            raw = reader.raw(directory / "report.json", _digest(expected_report_sha256))
            saved = _load(raw)
            snapshot = _object(saved["authorization"])
            pipeline.validate_authorization_snapshot(snapshot, current, {owner.run_id})
            if raw != _json(saved) or not _same(saved, result | {"authorization": snapshot}):
                raise stage.CandidateImprovementError(
                    "proposal publication differs from sealed evidence"
                )
            result = saved
        if len(_json(result)) > MAX_JSON_BYTES:
            raise stage.CandidateImprovementError(
                "proposal result exceeds its bounded output ceiling"
            )
        if sink is None:
            reader.capture.finish()
        else:
            _adopt_capture(reader.capture, sink)
        return _load(_json(result))
    except (
        ValueError,
        TypeError,
        KeyError,
        OSError,
        RecursionError,
        OverflowError,
        sqlite3.Error,
        _Busy,
        _Unsupported,
    ) as error:
        if isinstance(error, stage.CandidateImprovementError):
            raise
        raise stage.CandidateImprovementError("proposal evidence is invalid or changed") from None
