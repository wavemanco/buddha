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
from buddha.policy_study import PolicyStudy
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
)
from buddha.search_evidence import MAX_FILE_BYTES, _absolute

_AMOUNTS = ("committed_microusd", "spent_microusd", "reserved_microusd", "operation_count")


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


def _intent(reader: _Reader, study: PolicyStudy, raw: bytes, protocol_sha256: str) -> None:
    record = _object(_load(raw), {"format", "protocol_sha256", "release", "study", "expected"})
    source = TaskSet.from_bytes(_json(study.to_record()["source"]))
    declaration = study.to_record()
    del declaration["source"]
    expected = {
        "release_sha256": reader.release.fingerprint(),
        "source_tasks_sha256": source.fingerprint(),
        "selected_tasks_sha256": study.tasks.fingerprint(),
        "study_sha256": study.fingerprint(),
        "arm_ids": [row["arm_id"] for row in study.arms],
        "cell_ids": [row["cell_id"] for row in study.schedule()],
    }
    if (
        record["format"] != "buddha.policy-study-intent.v1"
        or record["protocol_sha256"] != protocol_sha256
        or not _same(record["release"], reader.release.to_record())
        or not _same(record["study"], declaration)
        or not _same(record["expected"], expected)
    ):
        raise PolicyResultsError("original execution differs from its reviewed publication")


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
        _intent(reader, study, intent_raw, expected_protocol_sha256)
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
    # Read only schedule-derived owner paths, including incomplete original owners.
    schedule = study.schedule()
    # Enforce the pure analysis ceiling before traversing a potentially large grid.
    analyze_metrics(study, [])
    stages = _rows(reader.template["stages"])
    if len(stages) != 3:
        raise PolicyResultsError("this scientific projection requires the three-stage schema")
    allowed_owners: set[str] = set()
    for i, cell in enumerate(schedule):
        for j, _occasion in enumerate(_rows(cell["judge_occasions"])):
            child = reader.root / "cells" / str(i) / ("baseline" if j == 0 else f"judgments/{j}")
            for index in range(0 if j == 0 else 1, len(stages) + 1):
                path = child / "owners" / str(index)
                allowed_owners.add((path / "manifest.json").relative_to(reader.root).as_posix())
                if (path / "manifest.json").exists():
                    owner = reader.owner(path)
                    bindings = _bindings(owner)
                    if any(
                        bindings.get(name) != digest for name, digest in reader.controls.items()
                    ):
                        raise PolicyResultsError("child changes an original study control")
                    section = "generation" if index == 0 else "native"
                    template = _object(reader.template[section])
                    if not _same(owner.manifest["selection"], template["selection"]) or not _same(
                        owner.manifest["roots"], template["roots"]
                    ):
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
    for name in reader.capture.entries:
        if (
            re.fullmatch(
                r"cells/[^/]+/(?:baseline|judgments/[^/]+)/owners/[^/]+/manifest\.json", name
            )
            and name not in allowed_owners
        ):
            raise PolicyResultsError("study contains an owner outside its declared schedule")
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
            original = reader.owner(base / "owners/0")
            reference = {
                "baseline_directory": str(base),
                "stage_seal_sha256": _sha(reader.raw(base / "completed/0.json")),
                "owner_manifest_sha256": original.manifest_sha256,
                "owner_ledger_sha256": original.ledger_sha256,
            }
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
    for path, owner in reader.owners.items():
        receipts = []
        for op in owner.operations:
            if not isinstance(op, HistoricalGatewayOperation):
                raise PolicyResultsError("study requires original Gateway evidence")
            receipt = op.receipt if op.status == "completed" else op.checkpoint
            if receipt is not None:
                request = _object(receipt["request"])
                body = _load(base64.b64decode(cast(str, request["body_base64"]), validate=True))
                receipts.append(
                    {
                        "operation_id": op.operation_id,
                        "request_sha256": op.request_sha256,
                        "receipt_sha256": _sha(_canonical(receipt)),
                        "model": body.get("model"),
                        "status": op.status,
                    }
                )
        owner_rows.append(
            {
                "directory": str(path),
                "run_id": owner.run_id,
                "manifest_sha256": owner.manifest_sha256,
                "ledger_sha256": owner.ledger_sha256,
                "accounting": owner.accounting(),
                "receipts": receipts,
            }
        )
    reader.capture.finish()
    return {
        "format": "buddha.policy-results.v1",
        "publication_status": "complete" if complete else "incomplete",
        "reason": saved.get("reason"),
        "analysis": analysis,
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
    cell_root = reader.root / "cells" / str(i)
    recipe = reader.record(cell_root / "generation.json")
    if not _same(recipe, reader.recipe | {"config": cell["generation_config"]}):
        raise PolicyResultsError("cell generation changes its declared treatment")
    producer = _object(reader.template["generation"]) | {
        "descriptor": str(cell_root / "generation.json")
    }
    baseline = reader.template | {"generation": producer}
    if not _same(reader.record(cell_root / "baseline.json"), baseline):
        raise PolicyResultsError("cell baseline differs from the original template")
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
