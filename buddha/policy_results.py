"""Passive study evidence, separate from execution and benchmark computation.

Publication pins are caller-trusted inputs, not authentication of capture time.
No current producer source, key, writable authority or execution identity is used.
"""

import base64
import hashlib
import re
import sqlite3
import stat
from contextlib import closing
from pathlib import Path
from typing import cast

from buddha.answers import TaskSet
from buddha.common import _canonical
from buddha.doctor import _authority, _Busy, _Capture, _Owner, _owner, _Unsupported
from buddha.gateway_history import HistoricalGatewayOperation
from buddha.native_evaluation import _read_generation
from buddha.native_pipeline import validate_authorization_snapshot
from buddha.policy_analysis import PolicyResultsError, analyze_metrics
from buddha.policy_study import PolicyStudy, validate_intent
from buddha.releases import (
    MAX_JSON_BYTES,
    Release,
    Selection,
    _digest,
    _json,
    _load,
    _object,
    _path,
    _root,
    _text,
)
from buddha.search_evidence import MAX_FILE_BYTES, _absolute
from buddha.wire import RawEnvelope, WireError, decoded_body, extract_usage
from buddha.wire import _text as _wire_text

_AMOUNTS = ("committed_microusd", "spent_microusd", "reserved_microusd", "operation_count")
_COORDINATES = (
    "cell_id",
    "arm_id",
    "arm_index",
    "generation_repeat",
    "judge_occasion",
    "stage_index",
    "stage_role",
)
_STAGE_ROLES = ("generation", "grouping", "quality", "summary")
MAX_OPERATIONS = 100_000


def _sha(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()


def _same(left: object, right: object) -> bool:
    return _json(left) == _json(right)


def _rows(value: object) -> list[dict[str, object]]:
    if type(value) is not list:
        raise PolicyResultsError("expected an original record list")
    return [_object(row) for row in value]


def _bindings(owner: _Owner) -> dict[str, str]:
    return {
        str(row["path"]): _digest(row["sha256"])
        for row in _rows(_object(owner.manifest["invocation"])["inputs"])
    }


def _reply_status(envelope: RawEnvelope | None) -> dict[str, object]:
    """Project literal provider statuses; content and refusal text are not exported."""
    result: dict[str, object] = {
        "availability": "unavailable",
        "reason": "missing_evidence",
        "finish_reasons": None,
        "stop_reason": None,
        "refusals": None,
        "refusal_applicability": "unknown",
    }
    if envelope is None:
        return result
    if envelope.status != 200:
        return result | {"reason": "http_status"}
    try:
        body = _load(decoded_body(envelope))
    except (ValueError, TypeError, UnicodeError, RecursionError):
        return result | {"reason": "unavailable_response_status"}

    def status(value: object) -> str | None:
        try:
            return _wire_text(value)
        except WireError:
            return None

    if envelope.provider == "anthropic":
        stop = status(body.get("stop_reason"))
        return result | {
            "stop_reason": stop,
            "refusal_applicability": "stop_reason",
            "availability": "available" if stop is not None else "unavailable",
            "reason": "available" if stop is not None else "missing_or_invalid_status",
        }
    choices = body.get("choices")
    if type(choices) is not list or not 1 <= len(choices) <= 128:
        return result | {"reason": "unsupported_choice_population"}
    finishes, refusals = [], []
    complete = True
    for choice in choices:
        record = choice if type(choice) is dict else {}
        finish = status(record.get("finish_reason"))
        finishes.append(finish)
        complete = complete and finish is not None
        message = record.get("message")
        refusal: dict[str, object] = {
            "present": None,
            "is_null": None,
            "nonempty": None,
            "sha256": None,
        }
        if type(message) is dict:
            refusal["present"] = "refusal" in message
            if "refusal" in message:
                value = message["refusal"]
                refusal["is_null"] = value is None
                if value is None:
                    refusal["nonempty"] = False
                elif type(value) is str:
                    try:
                        refusal["sha256"] = _sha(value.encode("utf-8"))
                        refusal["nonempty"] = bool(value)
                    except UnicodeError:
                        complete = False
                else:
                    complete = False
        else:
            complete = False
        refusals.append(refusal)
    return result | {
        "availability": "available" if complete else "partial",
        "reason": "available" if complete else "missing_or_invalid_status",
        "finish_reasons": finishes,
        "refusals": refusals,
        "refusal_applicability": "message_field",
    }


def _operation_evidence(
    owner: _Owner, coordinates: dict[str, object], fallback_model: str | None
) -> list[dict[str, object]]:
    """Describe captured attempts without repairing or rebilling their records."""
    if len(owner.operations) > MAX_OPERATIONS:
        raise PolicyResultsError("study operation population exceeds the reporting ceiling")
    result = []
    for operation in owner.operations:
        if not isinstance(operation, HistoricalGatewayOperation):
            raise PolicyResultsError("study requires original Gateway evidence")
        completed = operation.status == "completed"
        receipt = operation.receipt if completed else operation.checkpoint
        held = 0 if completed else operation.reserve_microusd
        row: dict[str, object] = {
            **coordinates,
            "operation_id": operation.operation_id,
            "request_sha256": operation.request_sha256,
            "run_id": owner.run_id,
            "status": operation.status,
            "reserve_microusd": operation.reserve_microusd,
            "actual_microusd": operation.actual_microusd,
            "held_microusd": held,
            "committed_microusd": operation.actual_microusd if completed else held,
            "evidence_source": "receipt" if completed else "checkpoint" if receipt else "missing",
            "receipt_sha256": None if receipt is None else _sha(_canonical(receipt)),
            "checkpoint_present": operation.checkpoint_json is not None,
            "checkpoint_sha256": None
            if operation.checkpoint_json is None
            else _sha(operation.checkpoint_json.encode()),
            "capability": None,
            "profile_id": None,
            "logical_id": None,
            "attempt": None,
            "requested_model": None,
            "metadata_reason": "missing_evidence",
            "provider_request_id": operation.provider_request_id
            if completed
            else operation.checkpoint_request_id,
            "provider": None,
            "http_status": None,
            "response_sha256": None,
            "raw_flags": None,
            "usage": None,
            "usage_reason": "missing_evidence",
            "physical_retry": None,
            "fallback_model_requested": None,
            "causal_fallback": "unknown",
            "row_attribution": "unknown",
            "parser_recovery": "unknown",
            "reply_status": _reply_status(None),
        }
        if receipt is not None:
            request = _object(receipt["request"])
            row.update(
                {
                    name: request[name]
                    for name in ("capability", "profile_id", "logical_id", "attempt")
                }
            )
            row["physical_retry"] = cast(int, request["attempt"]) > 0
            try:
                body = _load(base64.b64decode(cast(str, request["body_base64"]), validate=True))
                model = body.get("model")
                if (
                    type(model) is not str
                    or not model.strip()
                    or len(model.encode()) > 4096
                    or "\x00" in model
                ):
                    raise ValueError("unavailable request model")
                row["requested_model"] = model
                row["metadata_reason"] = "available"
            except (ValueError, TypeError, UnicodeError, RecursionError):
                row["metadata_reason"] = "unavailable_request_model"
            if (
                coordinates["stage_role"] == "quality"
                and fallback_model is not None
                and row["requested_model"] is not None
            ):
                row["fallback_model_requested"] = row["requested_model"] == fallback_model
            envelope = RawEnvelope.from_record(receipt["envelope"])
            row["reply_status"] = _reply_status(envelope)
            row.update(
                {
                    "provider": envelope.provider,
                    "http_status": envelope.status,
                    "response_sha256": envelope.received_sha256,
                    "raw_flags": {
                        "truncated": envelope.truncated,
                        "withheld": envelope.withheld,
                        "headers_complete": envelope.headers_complete,
                    },
                }
            )
            try:
                usage = extract_usage(envelope)
                row["usage"] = {
                    "model": usage.model,
                    "input_tokens": usage.input_tokens,
                    "output_tokens": usage.output_tokens,
                    "service_tier": usage.service_tier,
                }
                row["usage_reason"] = "available"
            except WireError:
                row["usage_reason"] = (
                    "incomplete_evidence"
                    if envelope.truncated or envelope.withheld or not envelope.headers_complete
                    else "http_status"
                    if envelope.status != 200
                    else "unavailable_usage"
                )
        result.append(row)
    return result


def _cost_summary(rows: list[dict[str, object]]) -> dict[str, object]:
    usages = [_object(row["usage"]) for row in rows if row["usage"] is not None]
    inputs = sum(cast(int, usage["input_tokens"]) for usage in usages)
    outputs = sum(cast(int, usage["output_tokens"]) for usage in usages)
    spent = sum(cast(int, row["actual_microusd"]) for row in rows if row["status"] == "completed")
    held = sum(cast(int, row["held_microusd"]) for row in rows)
    return {
        "committed_microusd": spent + held,
        "spent_microusd": spent,
        "reserved_microusd": held,
        "operation_count": len(rows),
        "status_counts": {
            state: sum(row["status"] == state for row in rows)
            for state in ("reserved", "dispatched", "unknown", "completed")
        },
        "response_count": sum(row["evidence_source"] != "missing" for row in rows),
        "receipt_count": sum(row["evidence_source"] == "receipt" for row in rows),
        "checkpoint_count": sum(row["evidence_source"] == "checkpoint" for row in rows),
        "missing_evidence_count": sum(row["evidence_source"] == "missing" for row in rows),
        "tokens": {
            "known_operations": len(usages),
            "unknown_operations": len(rows) - len(usages),
            "known_input_tokens": inputs,
            "known_output_tokens": outputs,
            "input_tokens": inputs if len(usages) == len(rows) else None,
            "output_tokens": outputs if len(usages) == len(rows) else None,
        },
    }


def _cost_report(
    owners: list[dict[str, object]],
    operations: list[dict[str, object]],
    arm_ids: list[str],
    planned_owner_count: int,
    fallback_model: str | None,
) -> dict[str, object]:
    if len(operations) > MAX_OPERATIONS:
        raise PolicyResultsError("study operation population exceeds the reporting ceiling")
    by_owner = {str(owner["run_id"]): owner for owner in owners}
    if len(by_owner) != len(owners) or len(owners) > planned_owner_count:
        raise PolicyResultsError("reporting owner population differs")
    seen = set()
    models: dict[str | None, list[dict[str, object]]] = {}
    for row in operations:
        owner = by_owner[str(row["run_id"])]
        arm = row["arm_index"]
        if (
            row["operation_id"] in seen
            or type(arm) is not int
            or not 0 <= arm < len(arm_ids)
            or row["arm_id"] != arm_ids[arm]
            or row["stage_role"] not in _STAGE_ROLES
            or not _same(
                {key: row[key] for key in _COORDINATES}, {key: owner[key] for key in _COORDINATES}
            )
        ):
            raise PolicyResultsError("reporting operation identity or coordinates differ")
        seen.add(row["operation_id"])
        models.setdefault(cast(str | None, row["requested_model"]), []).append(row)
    summary = _cost_summary(operations)
    expected = {
        key: sum(cast(int, _object(owner["accounting"])[key]) for owner in owners)
        for key in _AMOUNTS
    }
    if not _same({key: summary[key] for key in _AMOUNTS}, expected):
        raise PolicyResultsError("reporting amounts differ from original owner accounting")
    quality = [row for row in operations if row["stage_role"] == "quality"]
    return {
        "operations": operations,
        "owner_coverage": {"planned": planned_owner_count, "present": len(owners)},
        "current_study": summary,
        "by_arm": [
            {
                "arm_index": index,
                "arm_id": identifier,
                "summary": _cost_summary([row for row in operations if row["arm_index"] == index]),
            }
            for index, identifier in enumerate(arm_ids)
        ],
        "by_stage": [
            {
                "stage_role": role,
                "summary": _cost_summary([row for row in operations if row["stage_role"] == role]),
            }
            for role in _STAGE_ROLES
        ],
        "by_arm_stage": [
            {
                "arm_index": index,
                "arm_id": identifier,
                "stage_role": role,
                "summary": _cost_summary(
                    [
                        row
                        for row in operations
                        if row["arm_index"] == index and row["stage_role"] == role
                    ]
                ),
            }
            for index, identifier in enumerate(arm_ids)
            for role in _STAGE_ROLES
        ],
        "by_requested_model": [
            {"requested_model": model, "summary": _cost_summary(models[model])}
            for model in sorted(models, key=lambda value: (value is None, value or ""))
        ],
        "physical_retry": {
            name: _cost_summary([row for row in operations if row["physical_retry"] is value])
            for name, value in (("known", True), ("not_retry", False), ("unknown", None))
        },
        "quality_fallback": {
            "declared_model": fallback_model,
            "status": "explicit" if fallback_model is not None else "unknown",
            **{
                name: _cost_summary(
                    [row for row in quality if row["fallback_model_requested"] is value]
                )
                for name, value in (
                    ("requested_fallback", True),
                    ("other_quality", False),
                    ("unclassified", None),
                )
            },
        },
        "limitations": [
            "Recorded attempts and saved responses do not establish a count of network sends.",
            "Retry and fallback views overlap arm/stage totals; they are not extra expenditure.",
            "Usage is inclusive; unknown usage leaves complete totals null and money intact.",
            "Requested models and attempt indices do not establish repair or causal fallback.",
        ],
    }


class _Reader:
    def __init__(self, directory: Path, authorization: Path):
        self.root, self.authorization = directory, authorization
        self.capture = _Capture(directory)
        self.owners: dict[Path, _Owner] = {}
        self.seals: dict[Path, str] = {}

    def raw(self, path: Path, expected: object = None) -> bytes:
        raw = self.capture.read(path, MAX_JSON_BYTES)
        if expected is not None and _sha(raw) != _digest(expected):
            raise PolicyResultsError("retained input differs from its original digest")
        return raw

    def record(self, path: Path, expected: object = None) -> dict[str, object]:
        return _load(self.raw(path, expected))

    def owner(self, path: Path) -> _Owner:
        if path not in self.owners:
            self.owners[path] = _owner(self.capture, path)
        return self.owners[path]

    def bound(self, owner: _Owner, path: Path) -> bytes:
        bindings = _bindings(owner)
        if str(path) not in bindings:
            raise PolicyResultsError("required data was not an original invocation input")
        return self.raw(path, bindings[str(path)])

    def definition(self, anchor: _Owner) -> tuple[PolicyStudy, dict[str, object]]:
        context = _object(
            _load(self.bound(anchor, self.root / "context.json")), {"format", "descriptor"}
        )
        if context["format"] != "buddha.policy-run-context.v1":
            raise PolicyResultsError("unsupported original study context")
        self.descriptor = _absolute(context["descriptor"])
        execution = _object(
            _load(self.bound(anchor, self.descriptor)),
            {"format", "study", "baseline", "authorization"},
        )
        if execution["format"] != "buddha.policy-execution.v1":
            raise PolicyResultsError("unsupported original study execution")
        declared = _object(execution["study"], {"path", "sha256"})
        study_path = _absolute(declared["path"])
        study_raw = self.bound(anchor, study_path)
        if _sha(study_raw) != _digest(declared["sha256"]):
            raise PolicyResultsError("original study declaration differs")
        study = PolicyStudy.from_bytes(study_raw)
        declared = _object(execution["baseline"], {"path", "sha256"})
        template_path = _absolute(declared["path"])
        template_raw = self.bound(anchor, template_path)
        if _sha(template_raw) != _digest(declared["sha256"]):
            raise PolicyResultsError("original baseline declaration differs")
        self.template = _object(
            _load(template_raw), {"format", "tasks", "generation", "native", "stages"}
        )
        if self.template["format"] != "buddha.native-baseline.v1":
            raise PolicyResultsError("unsupported original baseline template")
        self.tasks_path = _absolute(self.template["tasks"])
        tasks = TaskSet.from_bytes(self.bound(anchor, self.tasks_path))
        if tasks.fingerprint() != study.tasks.fingerprint():
            raise PolicyResultsError("original baseline tasks differ from the registered study")
        self.recipe_path = _absolute(_object(self.template["generation"])["descriptor"])
        self.recipe = _load(self.bound(anchor, self.recipe_path))
        if not _same(self.recipe["config"], study.schedule()[0]["generation_config"]):
            raise PolicyResultsError("original first treatment differs")
        self.controls = {
            name: digest
            for name, digest in _bindings(anchor).items()
            if not Path(name).is_relative_to(self.root) or name == str(self.root / "context.json")
        }
        self.release = Release.from_record(_object(study.to_record()["source"])["release"])
        for name in ("generation", "native"):
            selected = Selection.from_bytes(_json(_object(self.template[name])["selection"]))
            if selected.release_sha256 != self.release.fingerprint():
                raise PolicyResultsError("original selections differ from the study release")
        return study, execution

    def scheduled_owners(
        self, study: PolicyStudy, roles: list[str]
    ) -> tuple[dict[Path, dict[str, object]], int]:
        """Validate every retained schedule owner before any source projection."""
        stages = _rows(self.template["stages"])
        if len(roles) != len(stages):
            raise PolicyResultsError("declared stage roles differ from the native flow")
        coordinates: dict[Path, dict[str, object]] = {}
        planned_owner_count = 0
        operation_count = 0
        allowed_owners: set[str] = set()
        for i, cell in enumerate(study.schedule()):
            for j, _occasion in enumerate(_rows(cell["judge_occasions"])):
                child = self.root / "cells" / str(i) / ("baseline" if j == 0 else f"judgments/{j}")
                for index in range(0 if j == 0 else 1, len(stages) + 1):
                    planned_owner_count += 1
                    path = child / "owners" / str(index)
                    allowed_owners.add((path / "manifest.json").relative_to(self.root).as_posix())
                    if (path / "manifest.json").exists():
                        owner = self.owner(path)
                        operation_count += len(owner.operations)
                        if operation_count > MAX_OPERATIONS:
                            raise PolicyResultsError(
                                "study operation population exceeds the reporting ceiling"
                            )
                        coordinates[path] = {
                            **{
                                key: cell[key]
                                for key in ("cell_id", "arm_id", "arm_index", "generation_repeat")
                            },
                            "judge_occasion": None if index == 0 else j,
                            "stage_index": index,
                            "stage_role": "generation" if index == 0 else roles[index - 1],
                        }
                        bindings = _bindings(owner)
                        if any(
                            bindings.get(name) != digest for name, digest in self.controls.items()
                        ):
                            raise PolicyResultsError("child changes an original study control")
                        section = "generation" if index == 0 else "native"
                        template = _object(self.template[section])
                        if not _same(
                            owner.manifest["selection"], template["selection"]
                        ) or not _same(owner.manifest["roots"], template["roots"]):
                            raise PolicyResultsError(
                                "child changes the selected release/agent components"
                            )
                        settings = {
                            "budget_microusd": 1
                            if index == len(stages)
                            else template["budget_microusd"],
                            "max_calls": 1 if index == len(stages) else template["max_calls"],
                        }
                        if not _same(owner.manifest["settings"], settings):
                            raise PolicyResultsError("child changes its declared local ceilings")
        for name in self.capture.entries:
            manifest = (
                name + "/manifest.json"
                if re.fullmatch(r"cells/[^/]+/(?:baseline|judgments/[^/]+)/owners/[^/]+", name)
                else name
            )
            if re.fullmatch(
                r"cells/[^/]+/(?:baseline|judgments/[^/]+)/owners/[^/]+/manifest\.json", manifest
            ) and (manifest not in allowed_owners or manifest not in self.capture.entries):
                raise PolicyResultsError("study contains an owner outside its declared schedule")
        return coordinates, planned_owner_count

    def cell_definition(self, i: int, cell: dict[str, object]) -> None:
        """Join a cell's literal generation recipe and original baseline template."""
        cell_root = self.root / "cells" / str(i)
        owner = self.owner(cell_root / "baseline/owners/0")
        baseline_path = cell_root / "baseline.json"
        context = _load(self.bound(owner, cell_root / "baseline/context.json"))
        if not _same(
            context,
            {"format": "buddha.baseline-context.v1", "descriptor": str(baseline_path)},
        ):
            raise PolicyResultsError("cell producer uses another original baseline descriptor")
        recipe = _load(self.bound(owner, cell_root / "generation.json"))
        if not _same(recipe, self.recipe | {"config": cell["generation_config"]}):
            raise PolicyResultsError("cell generation changes its declared treatment")
        producer = _object(self.template["generation"]) | {
            "descriptor": str(cell_root / "generation.json")
        }
        baseline = self.template | {"generation": producer}
        if not _same(_load(self.bound(owner, baseline_path)), baseline):
            raise PolicyResultsError("cell baseline differs from the original template")

    def generation_reference(self, base: Path) -> dict[str, object]:
        """Construct the existing reference from captured bytes, not a new owner."""
        original = self.owner(base / "owners/0")
        return {
            "baseline_directory": str(base),
            "stage_seal_sha256": _sha(self.raw(base / "completed/0.json")),
            "owner_manifest_sha256": original.manifest_sha256,
            "owner_ledger_sha256": original.ledger_sha256,
        }

    def funding(self, execution: dict[str, object], study: PolicyStudy) -> None:
        funding = _authority(self.capture, self.authorization, list(self.owners.values()))
        if funding is None:
            raise PolicyResultsError("explicit original authority required")
        self.funded = funding
        config = _object(funding["config"])
        expected = {
            "path": str(self.authorization),
            "id": config["authorization_id"],
            "terms_sha256": config["terms_sha256"],
            "scope": "policy study: " + study.fingerprint(),
        }
        if not _same(execution["authorization"], expected) or config["scope"] != expected["scope"]:
            raise PolicyResultsError("study belongs to another original authority")
        self.funded_runs = {str(row["run_id"]): row for row in _rows(funding["auth_runs"])}
        planned_paths = {
            self.root
            / "cells"
            / str(i)
            / ("baseline" if j == 0 else f"judgments/{j}")
            / "owners"
            / str(index)
            for i, cell in enumerate(study.schedule())
            for j in range(len(_rows(cell["judge_occasions"])))
            for index in range(0 if j == 0 else 1, len(_rows(self.template["stages"])) + 1)
        }
        # A recorded scheduled owner remains required custody even when its
        # entire directory has disappeared. Other shared rows are not followed.
        for row in self.funded_runs.values():
            path = Path(_text(row["directory"]))
            if path in planned_paths and (
                path not in self.owners or self.owners[path].run_id != row["run_id"]
            ):
                raise PolicyResultsError("retained funded owner is missing its original evidence")
        for owner in self.owners.values():
            row = self.funded_runs[owner.run_id]
            if (
                type(row["historical"]) is not int
                or row["historical"] != 0
                or row["runtime_sha256"] != owner.manifest["execution_sha256"]
                or owner.manifest["authorization_path"] != str(self.authorization)
            ):
                raise PolicyResultsError("study owner runtime or authority differs")
        inactive = {row["run_id"] for row in _rows(funding["auth_deactivations"])}
        amounts = {identifier: dict.fromkeys(_AMOUNTS, 0) for identifier in self.funded_runs}
        for operation in _rows(funding["auth_operations"]):
            values = amounts[str(operation["run_id"])]
            values["operation_count"] += 1
            key = "spent_microusd" if operation["status"] == "completed" else "reserved_microusd"
            value = (
                operation["actual_microusd"]
                if operation["status"] == "completed"
                else operation["reserve_microusd"]
            )
            values[key] += cast(int, value)
            values["committed_microusd"] += cast(int, value)
        # The source database is never opened. Its exact schema/rows were already
        # validated by _authority; this memory connection supplies only the event count.
        with closing(sqlite3.connect(":memory:")) as connection:
            connection.deserialize(self.capture.raw[self.authorization])
            connection.execute("PRAGMA query_only=ON")
            connection.execute("PRAGMA trusted_schema=OFF")
            events = connection.execute("SELECT COUNT(*) FROM auth_events").fetchone()[0]
        totals = _object(funding["totals"])
        self.current = {
            **{
                key: config[key]
                for key in (
                    "authorization_id",
                    "budget_microusd",
                    "max_calls",
                    "scope",
                    "terms_sha256",
                )
            },
            **totals,
            "available_microusd": max(
                0, cast(int, config["budget_microusd"]) - cast(int, totals["committed_microusd"])
            ),
            "remaining_calls": max(
                0, cast(int, config["max_calls"]) - cast(int, totals["operation_count"])
            ),
            "runs": [
                row
                | {"active": not row["historical"] and identifier not in inactive}
                | amounts[identifier]
                for identifier, row in sorted(self.funded_runs.items())
            ],
            "event_count": events,
        }

    def stage(self, child: Path, index: int, *, baseline: bool) -> tuple[dict[str, object], Path]:
        owner = self.owner(child / "owners" / str(index))
        path = child / "completed" / (str(index) + ".json")
        raw = self.raw(path)
        digest = _sha(raw)
        seal = _object(_load(raw), {"format", "index", "owner_sha256", "attempt", "files"})
        prefix = "baseline" if baseline else "native evaluation"
        anchors = [
            row["reason"]
            for row in _rows(self.funded["auth_deactivations"])
            if row["run_id"] == owner.run_id
        ]
        if (
            seal["format"]
            != ("buddha.baseline-stage.v1" if baseline else "buddha.native-evaluation-stage.v1")
            or type(seal["index"]) is not int
            or seal["index"] != index
            or seal["owner_sha256"] != owner.manifest_sha256
            or anchors != [prefix + " completed: " + digest]
            or any(op.status != "completed" for op in owner.operations)
        ):
            raise PolicyResultsError("stage lacks its original completion anchor")
        relative = _path(seal["attempt"])
        if not re.fullmatch(rf"attempts/{index}-(?:0|[1-9][0-9]*)", relative):
            raise PolicyResultsError("sealed attempt belongs to another stage")
        attempt = child / relative
        files = _object(seal["files"])
        prefix = attempt.relative_to(self.root).as_posix() + "/"
        actual = {
            name[len(prefix) :]
            for name in self.capture.entries
            if name.startswith(prefix) and stat.S_ISREG((self.root / name).lstat().st_mode)
        }
        if set(files) != actual or "report.json" not in files:
            raise PolicyResultsError("sealed attempt inventory differs")
        for name, expected in files.items():
            value = self.capture.read(attempt / _path(name), MAX_FILE_BYTES)
            if _sha(value) != _digest(expected):
                raise PolicyResultsError("sealed attempt file differs")
        report = self.record(attempt / "report.json")
        if (
            report.get("format")
            != ("buddha.generation-report.v1" if index == 0 else "buddha.native-command-report.v1")
            or report.get("status") != "complete"
            or report.get("gateway_manifest_sha256") != owner.manifest_sha256
            or not _same(report.get("gateway_totals"), {k: owner.accounting()[k] for k in _AMOUNTS})
        ):
            raise PolicyResultsError("stage report differs from its original owner")
        for name, expected in _object(report["artifacts"]).items():
            key = _path(name) if index == 0 else "artifacts/" + _path(name)
            if files.get(key) != expected:
                raise PolicyResultsError("reported artifact differs from its sealed bytes")
        if index:
            execution = _object(report["execution"])
            if (
                type(execution.get("exit_code")) is not int
                or execution["exit_code"] != 0
                or execution.get("cleanup_status") != "removed"
                or _object(report["worker"]).get("status") != "complete"
            ):
                raise PolicyResultsError("native completion lacks successful owned cleanup")
        self.seals[path] = digest
        return report, attempt

    def native(
        self,
        child: Path,
        index: int,
        report: dict[str, object],
        answers: Path,
        available: dict[str, Path],
    ) -> None:
        owner = self.owner(child / "owners" / str(index))
        descriptor = child / ("command-" + str(index) + ".json")
        raw = self.bound(owner, descriptor)
        description = _object(_load(raw), {"format", "worker", "executor", "profiles"})
        worker = _object(description["worker"])
        command = _rows(self.release.to_record()["commands"])[index - 1]
        expected_command = {
            "index": index - 1,
            "module": command["module"],
            "argv": [
                "/scratch/artifacts" if x == "{artifacts}" else x
                for x in cast(list[str], command["argv"])
            ],
        }
        expected_command["sha256"] = _sha(_json(expected_command))
        native = _object(self.template["native"])
        selected = Selection.from_bytes(_json(native["selection"]))
        components = _object(selected.to_record()["components"])
        inputs = _object(_rows(self.template["stages"])[index - 1])["inputs"]
        expected_inputs = []
        for ordinal, name in enumerate(cast(list[str], inputs)):
            source = child / "staging" / str(index) / (str(ordinal) + ".bin")
            source_raw = self.bound(owner, source)
            if source_raw != self.raw(available[name]):
                raise PolicyResultsError("native stage consumed another input")
            expected_inputs.append(
                {"source": source.name, "destination": name, "sha256": _sha(source_raw)}
            )
        expected_worker = {
            "type": "configure",
            "format": "buddha.native-worker.v1",
            "command": expected_command,
            "release_sha256": self.release.fingerprint(),
            "answers_sha256": _sha(self.raw(answers)),
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
            "inputs": expected_inputs,
            "hooks": native["hooks"],
        }
        last = index == len(_rows(self.template["stages"]))
        expected_executor = _object(native["executor"]) | {
            "mounts": [
                ["/official", _object(native["roots"])["official"]],
                ["/runner", _object(native["roots"])["runner"]],
                ["/inputs", str(child / "staging" / str(index))],
            ]
        }
        if (
            description["format"] != "buddha.native-command.v1"
            or not _same(worker, expected_worker)
            or not _same(description["executor"], expected_executor)
            or not _same(description["profiles"], {} if last else native["profiles"])
            or report["descriptor_sha256"] != _sha(raw)
            or report["command_sha256"] != expected_command["sha256"]
            or _object(report["execution"])["image_id"] != expected_executor["image_id"]
        ):
            raise PolicyResultsError("native command/configuration lineage differs")


def analyze_study(
    directory: Path,
    *,
    intent: Path,
    protocol: Path,
    expected_intent_sha256: str,
    expected_protocol_sha256: str,
    authorization: Path,
    observation: Path | None = None,
) -> dict[str, object]:
    """Verify retained records, then apply the declared descriptive comparison.

    An explicit original observation limits coverage even after later recovery.
    Current source inventories are never validated/executed. Callers must supply
    reviewed pre-outcome pins and a protocol appropriate to this analysis rule.
    """
    try:
        paths = [directory, intent, protocol, authorization]
        if any(not isinstance(path, Path) for path in paths) or (
            observation is not None and not isinstance(observation, Path)
        ):
            raise PolicyResultsError("explicit evidence Paths required")
        directory, authorization = directory.absolute(), authorization.absolute()
        _root(directory)
        reader = _Reader(directory, authorization)
        intent_raw = reader.raw(intent.absolute(), _digest(expected_intent_sha256))
        reader.raw(protocol.absolute(), _digest(expected_protocol_sha256))
        anchor = reader.owner(directory / "cells/0/baseline/owners/0")
        study, execution = reader.definition(anchor)
        validate_intent(study, _load(intent_raw), expected_protocol_sha256)
        result = _analyze(reader, study, execution, observation)
        _object(result["provenance"])["publication_pins"] = {
            "intent_sha256": expected_intent_sha256,
            "protocol_sha256": expected_protocol_sha256,
        }
        return result
    except (
        ValueError,
        TypeError,
        KeyError,
        OSError,
        RecursionError,
        sqlite3.Error,
        _Busy,
        _Unsupported,
    ):
        raise PolicyResultsError(
            "study evidence is invalid or changed; original state retained"
        ) from None


def _analyze(
    reader: _Reader, study: PolicyStudy, execution: dict[str, object], observation: Path | None
) -> dict[str, object]:
    from buddha.noveltybench_results import reporting_configuration
    from buddha.policy_analysis import describe_observations

    # Read only schedule-derived owner paths, including incomplete original owners.
    schedule = study.schedule()
    # Enforce the pure analysis ceiling before traversing a potentially large grid.
    analyze_metrics(study, [])
    stages = _rows(reader.template["stages"])
    if len(stages) != 3:
        raise PolicyResultsError("this scientific projection requires the three-stage schema")
    reporting = reporting_configuration(reader.release, stages)
    roles = cast(list[str], reporting["stage_roles"])
    fallback_model = cast(str | None, reporting["fallback_model"])
    coordinates, planned_owner_count = reader.scheduled_owners(study, roles)
    reader.funding(execution, study)
    publication = reader.root / "report.json" if observation is None else observation.absolute()
    if observation is not None:
        relative = publication.relative_to(reader.root).as_posix()
        if not re.fullmatch(r"observations/(?:0|[1-9][0-9]*)\.json", relative):
            raise PolicyResultsError("select an original study observation explicitly")
    saved = reader.record(publication)
    complete = observation is None
    if (
        saved["format"] != "buddha.policy-run-report.v1"
        or saved["study_sha256"] != study.fingerprint()
        or saved["status"] != ("complete" if complete else "incomplete")
        or (not complete and saved["observation"] != relative)
    ):
        raise PolicyResultsError("selected publication identity differs")
    cells = _rows(saved["cells"])
    if len(cells) > len(schedule) or (complete and len(cells) != len(schedule)):
        raise PolicyResultsError("publication omits declared cells")
    validate_authorization_snapshot(
        saved["authorization"],
        reader.current,
        {owner.run_id for owner in reader.owners.values()} if complete else set(),
    )
    assessments: list[dict[str, object]] = []
    provenance: list[dict[str, object]] = []
    for i, cell in enumerate(cells):
        expected = schedule[i]
        identity = {k: expected[k] for k in ("cell_id", "arm_id", "arm_index", "generation_repeat")}
        if not _same({k: cell[k] for k in identity}, identity):
            raise PolicyResultsError("publication changes the ordered cell population")
        occasions = _rows(cell["occasions"])
        if len(occasions) != len(_rows(expected["judge_occasions"])):
            raise PolicyResultsError("completed cell lacks declared judging coverage")
        for j, occasion in enumerate(occasions):
            _child(
                reader,
                study,
                i,
                j,
                expected,
                occasion,
                cell["source_generation"],
                assessments,
                provenance,
            )
    if not complete:
        stopped_i, stopped_j = saved["cell_index"], saved["occasion_index"]
        if (
            type(stopped_i) is not int
            or not 0 <= stopped_i < len(schedule)
            or type(stopped_j) is not int
            or not 0 <= stopped_j < len(_rows(schedule[stopped_i]["judge_occasions"]))
        ):
            raise PolicyResultsError("partial observation has invalid stopped coordinates")
        child = (
            reader.root
            / "cells"
            / str(stopped_i)
            / ("baseline" if stopped_j == 0 else f"judgments/{stopped_j}")
        )
        if saved["cell_id"] != schedule[stopped_i]["cell_id"] or saved["child_directory"] != str(
            child
        ):
            raise PolicyResultsError("partial observation points outside its stopped cell")
        # No unsealed/newer child rows are promoted from a selected old observation.
        if len(cells) not in {stopped_i, len(schedule)}:
            raise PolicyResultsError("partial observation changes the completed prefix")
        if len(cells) == len(schedule) and (
            stopped_i != len(schedule) - 1
            or stopped_j != len(_rows(schedule[stopped_i]["judge_occasions"])) - 1
            or saved.get("reason") != "protocol"
        ):
            raise PolicyResultsError("full-prefix partial contradicts final publication failure")
        if saved.get("reason") not in {
            "unknown",
            "authority",
            "protocol",
            "cancelled",
            "native_error",
            "agent_error",
        }:
            raise PolicyResultsError("partial observation has an unsupported stop reason")
        if len(cells) == stopped_i and stopped_j:
            base = reader.root / "cells" / str(stopped_i) / "baseline"
            reference = reader.generation_reference(base)
            # The saved serial stop coordinate declares these earlier occasions.
            # Later recovered occasions and unsealed attempts remain excluded.
            for earlier in range(stopped_j):
                prior = base if earlier == 0 else base.parent / "judgments" / str(earlier)
                prior_raw = reader.raw(prior / "report.json")
                prior_report = _load(prior_raw)
                occasion = _rows(schedule[stopped_i]["judge_occasions"])[earlier] | {
                    "directory": str(prior),
                    "report_sha256": _sha(prior_raw),
                    "summary": prior_report["summary"],
                }
                _child(
                    reader,
                    study,
                    stopped_i,
                    earlier,
                    schedule[stopped_i],
                    occasion,
                    reference,
                    assessments,
                    provenance,
                )
    analysis = analyze_metrics(study, assessments)
    if not complete:
        sealed_owners = {
            reader.owner(path.parent.parent / "owners" / path.stem).run_id for path in reader.seals
        }
        validate_authorization_snapshot(saved["authorization"], reader.current, sealed_owners)
    if not complete:
        analysis["mean_contrasts"] = None
        analysis["status"] = "incomplete"
    owner_rows = []
    operation_rows = []
    for path, owner in reader.owners.items():
        rows = _operation_evidence(owner, coordinates[path], fallback_model)
        operation_rows.extend(rows)
        receipts = [
            {
                key: row[key]
                for key in ("operation_id", "request_sha256", "receipt_sha256", "status")
            }
            | {"model": row["requested_model"]}
            for row in rows
            if row["evidence_source"] != "missing"
        ]
        owner_rows.append(
            {
                **coordinates[path],
                "directory": str(path),
                "run_id": owner.run_id,
                "manifest_sha256": owner.manifest_sha256,
                "ledger_sha256": owner.ledger_sha256,
                "accounting": owner.accounting(),
                "receipts": receipts,
            }
        )
    registered = describe_observations(study, analysis, provenance)
    registered["accounting"] = _cost_report(
        owner_rows,
        operation_rows,
        [cast(str, arm["arm_id"]) for arm in study.arms],
        planned_owner_count,
        fallback_model,
    )
    reader.capture.finish()
    return {
        "format": "buddha.policy-results.v1",
        "publication_status": "complete" if complete else "incomplete",
        "reason": saved.get("reason"),
        "analysis": analysis,
        "registered": registered,
        "provenance": {
            "study_sha256": study.fingerprint(),
            "release_sha256": reader.release.fingerprint(),
            "original_control_hashes": reader.controls,
            "publication": str(publication),
            "publication_sha256": _sha(reader.capture.raw[publication]),
            "consumed_files": {str(path): _sha(raw) for path, raw in reader.capture.raw.items()},
            "occasions": provenance,
            "owners": owner_rows,
        },
        "accounting": {
            "current_study": {
                k: sum(owner.accounting()[k] for owner in reader.owners.values()) for k in _AMOUNTS
            },
            "current_shared": reader.funded["totals"],
            "historical_observation": saved["authorization"],
            "historical_observation_validation": "typed compatible snapshot; unauthenticated time",
        },
        "limitations": [
            "Stable bytes and anchors do not authenticate capture time or providers.",
            "Old observations and current liabilities are separate; neither permits spending.",
            "Retired program hashes are data; original programs were not consumed or executed.",
            "Incomplete publications keep the planned denominator; unsealed rows stay unavailable.",
            "Metrics are read without benchmark formulas; absent repair/fallback is unknown.",
        ],
    }


def _child(
    reader: _Reader,
    study: PolicyStudy,
    i: int,
    j: int,
    cell: dict[str, object],
    occasion: dict[str, object],
    source_reference: object,
    assessments: list[dict[str, object]],
    provenance: list[dict[str, object]],
) -> None:
    from buddha.noveltybench_results import project_rows

    base = reader.root / "cells" / str(i) / "baseline"
    source = _read_generation(source_reference, reader.authorization)
    if (
        _object(source_reference)["baseline_directory"] != str(base)
        or source.tasks.fingerprint() != study.tasks.fingerprint()
    ):
        raise PolicyResultsError("occasion uses another cell generation")
    for path, digest in source.files.items():
        reader.raw(path, digest)
    child = base if j == 0 else reader.root / "cells" / str(i) / "judgments" / str(j)
    expected_occasion = _rows(cell["judge_occasions"])[j]
    if not _same({k: occasion[k] for k in ("index", "occasion_id")}, expected_occasion) or occasion[
        "directory"
    ] != str(child):
        raise PolicyResultsError("judging occasion identity differs")
    reader.cell_definition(i, cell)
    cell_root = reader.root / "cells" / str(i)
    native_raw = source.answers.native_bytes()
    if reader.raw(child / "native-answers.jsonl") != native_raw:
        raise PolicyResultsError("occasion changes the original native answers")
    if j:
        expected_definition = {
            "format": "buddha.native-evaluation.v1",
            "source_generation": source_reference,
            "native": reader.template["native"],
            "stages": reader.template["stages"],
        }
        first = reader.owner(child / "owners/1")
        context = _load(reader.bound(first, child / "context.json"))
        descriptor = cell_root / "judgments" / (str(j) + ".json")
        if not _same(
            context,
            {"format": "buddha.native-evaluation-context.v1", "descriptor": str(descriptor)},
        ) or not _same(_load(reader.bound(first, descriptor)), expected_definition):
            raise PolicyResultsError(
                "fresh judging definition differs from its original generation"
            )
    available = {
        str(_object(reader.release.to_record()["artifacts"])["answers"]): child
        / "native-answers.jsonl"
    }
    reports, seals = [], {}
    for index in range(0 if j == 0 else 1, len(_rows(reader.template["stages"])) + 1):
        report, attempt = reader.stage(child, index, baseline=j == 0)
        reports.append(report)
        sealed = child / "completed" / (str(index) + ".json")
        seals[str(sealed.relative_to(child))] = reader.seals[sealed]
        if index:
            reader.native(child, index, report, source.answers_path, available)
            for output in _rows(_rows(reader.template["stages"])[index - 1]["outputs"]):
                name = _path(output["path"])
                available[name] = attempt / "artifacts" / name
                if name not in _object(report["artifacts"]):
                    raise PolicyResultsError("native stage omits a declared output")
    report_raw = reader.raw(child / "report.json", occasion["report_sha256"])
    report = _load(report_raw)
    if (
        report["format"]
        != ("buddha.native-baseline-report.v1" if j == 0 else "buddha.native-evaluation-report.v1")
        or report["status"] != "complete"
        or report["release_sha256"] != reader.release.fingerprint()
        or report["tasks_sha256"] != study.tasks.fingerprint()
        or not _same(report["stages"], reports)
        or not _same(report["stage_seals"], seals)
    ):
        raise PolicyResultsError("child publication differs from its anchored outputs")
    if j and (
        not _same(report["source_generation"], source_reference)
        or report["answers_file_sha256"] != _sha(reader.raw(source.answers_path))
        or report["answers_sha256"] != source.answers.fingerprint()
        or report["native_answers_sha256"] != _sha(native_raw)
    ):
        raise PolicyResultsError("fresh occasion changes the original C1 identity")
    validate_authorization_snapshot(
        report["authorization"],
        reader.current,
        {
            reader.owner(child / "owners" / str(index)).run_id
            for index in range(0 if j == 0 else 1, len(_rows(reader.template["stages"])) + 1)
        },
    )
    artifacts = _object(reader.release.to_record()["artifacts"])
    summary = available[_path(artifacts["summary"])]
    summary_reference = {"path": str(summary), "sha256": _sha(reader.raw(summary))}
    if not _same(occasion["summary"], summary_reference) or not _same(
        report["summary"], summary_reference
    ):
        raise PolicyResultsError("native summary reference differs")
    results = cast(list[str], artifacts["results"])
    if len(results) != 2:
        raise PolicyResultsError("native metric projection requires separate partitions and scores")
    rows = project_rows(
        study.tasks,
        source.answers,
        reader.raw(available[results[0]]),
        reader.raw(available[results[1]]),
    )
    for row in rows:
        assessments.append(
            {
                "task_id": row["task_id"],
                "arm_index": cell["arm_index"],
                "generation_repeat": cell["generation_repeat"],
                "judge_occasion": j,
                "distinct": row["distinct"],
                "utility": row["utility"],
                "status": "observed",
            }
        )
    provenance.append(
        {
            "cell_id": cell["cell_id"],
            "occasion_id": expected_occasion["occasion_id"],
            "source_generation": source_reference,
            "report_sha256": _sha(report_raw),
            "summary": summary_reference,
            "rows": rows,
        }
    )
