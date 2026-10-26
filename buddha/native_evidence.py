"""Shared passive native-stage custody over original bounded saved evidence.

Callers validate topology, release/template and authority relationships before
supplying them. This module executes no producer, evaluator or writable owner.
"""

import hashlib
import re
import sqlite3
import stat
from collections.abc import Mapping
from contextlib import closing
from pathlib import Path
from typing import cast

from buddha.doctor import _Capture, _Owner, _owner
from buddha.releases import (
    MAX_JSON_BYTES,
    Release,
    ReleaseError,
    Selection,
    _digest,
    _json,
    _load,
    _object,
    _path,
)
from buddha.search_evidence import MAX_FILE_BYTES

_AMOUNTS = ("committed_microusd", "spent_microusd", "reserved_microusd", "operation_count")


class NativeEvidenceError(ReleaseError):
    """Original native evidence contradicts its retained custody bindings."""


def _sha(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()


def _same(left: object, right: object) -> bool:
    return _json(left) == _json(right)


def _rows(
    value: object, error_type: type[ReleaseError] = NativeEvidenceError
) -> list[dict[str, object]]:
    if type(value) is not list:
        raise error_type("expected an original record list")
    return [_object(row) for row in value]


def _adopt_capture(source: _Capture, target: _Capture) -> None:
    """Retain all consumed bytes/sidecars under the receiving aggregate limit."""
    if type(source) is not _Capture or type(target) is not _Capture or source is target:
        raise NativeEvidenceError("capture adoption needs two original bounded observations")
    source.finish()
    for path in source.databases:
        target.database(path)
    for path, raw in source.raw.items():
        if target.read(path, len(raw)) != raw:
            raise NativeEvidenceError("nested observation consumed conflicting original bytes")


class NativeEvidence:
    """Read shared custody; callers supply checked release/template/funding.

    This is not a topology, completion, population or scientific validator by
    itself. Caller-specific validation errors retain their original identity.
    """

    release: Release
    template: dict[str, object]
    funded: dict[str, object]

    def __init__(
        self,
        directory: Path,
        authorization: Path,
        *,
        error_type: type[ReleaseError] = NativeEvidenceError,
    ):
        self.error_type = error_type
        self.root, self.authorization = directory, authorization
        self.capture = _Capture(directory)
        self.owners: dict[Path, _Owner] = {}
        self.seals: dict[Path, str] = {}
        self._retained: list[_Capture] = []

    def retain_capture(self, capture: _Capture) -> None:
        """Also preserve a sibling immutable tree's original metadata snapshot."""
        _adopt_capture(capture, self.capture)
        if capture not in self._retained:
            self._retained.append(capture)

    def verify_files(self, hashes: Mapping[Path, str]) -> None:
        """Join nested evidence without narrowing an already validated file bound."""
        if not isinstance(hashes, Mapping):
            raise self.error_type("nested evidence needs a file-hash mapping")
        for path, expected in hashes.items():
            digest = _digest(expected)
            if not isinstance(path, Path):
                raise self.error_type("nested evidence needs explicit file Paths")
            raw = self.capture.raw.get(path)
            if raw is None:
                raw = self.capture.read(path, MAX_FILE_BYTES)
            if _sha(raw) != digest:
                raise self.error_type("nested evidence changed during observation")

    def finish(self) -> dict[str, str]:
        result = self.capture.finish()
        for capture in self._retained:
            capture.finish()
        return result

    def _rows(self, value: object) -> list[dict[str, object]]:
        return _rows(value, self.error_type)

    def _bindings(self, owner: _Owner) -> dict[str, str]:
        return {
            str(row["path"]): _digest(row["sha256"])
            for row in self._rows(_object(owner.manifest["invocation"])["inputs"])
        }

    def raw(self, path: Path, expected: object = None) -> bytes:
        raw = self.capture.read(path, MAX_JSON_BYTES)
        if expected is not None and _sha(raw) != _digest(expected):
            raise self.error_type("retained input differs from its original digest")
        return raw

    def record(self, path: Path, expected: object = None) -> dict[str, object]:
        return _load(self.raw(path, expected))

    def owner(self, path: Path) -> _Owner:
        if path not in self.owners:
            self.owners[path] = _owner(self.capture, path)
        return self.owners[path]

    def bound(self, owner: _Owner, path: Path) -> bytes:
        bindings = self._bindings(owner)
        if str(path) not in bindings:
            raise self.error_type("required data was not an original invocation input")
        return self.raw(path, bindings[str(path)])

    def stage(self, child: Path, index: int, *, baseline: bool) -> tuple[dict[str, object], Path]:
        owner = self.owner(child / "owners" / str(index))
        path = child / "completed" / (str(index) + ".json")
        raw = self.raw(path)
        digest = _sha(raw)
        seal = _object(_load(raw), {"format", "index", "owner_sha256", "attempt", "files"})
        prefix = "baseline" if baseline else "native evaluation"
        anchors = [
            row["reason"]
            for row in self._rows(self.funded["auth_deactivations"])
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
            raise self.error_type("stage lacks its original completion anchor")
        relative = _path(seal["attempt"])
        if not re.fullmatch(rf"attempts/{index}-(?:0|[1-9][0-9]*)", relative):
            raise self.error_type("sealed attempt belongs to another stage")
        attempt = child / relative
        files = _object(seal["files"])
        prefix = attempt.relative_to(self.root).as_posix() + "/"
        actual = {
            name[len(prefix) :]
            for name in self.capture.entries
            if name.startswith(prefix) and stat.S_ISREG((self.root / name).lstat().st_mode)
        }
        if set(files) != actual or "report.json" not in files:
            raise self.error_type("sealed attempt inventory differs")
        for name, expected in files.items():
            value = self.capture.read(attempt / _path(name), MAX_FILE_BYTES)
            if _sha(value) != _digest(expected):
                raise self.error_type("sealed attempt file differs")
        report = self.record(attempt / "report.json")
        if (
            report.get("format")
            != ("buddha.generation-report.v1" if index == 0 else "buddha.native-command-report.v1")
            or report.get("status") != "complete"
            or report.get("gateway_manifest_sha256") != owner.manifest_sha256
            or not _same(report.get("gateway_totals"), {k: owner.accounting()[k] for k in _AMOUNTS})
        ):
            raise self.error_type("stage report differs from its original owner")
        for name, expected in _object(report["artifacts"]).items():
            key = _path(name) if index == 0 else "artifacts/" + _path(name)
            if files.get(key) != expected:
                raise self.error_type("reported artifact differs from its sealed bytes")
        if index:
            execution = _object(report["execution"])
            if (
                type(execution.get("exit_code")) is not int
                or execution["exit_code"] != 0
                or execution.get("cleanup_status") != "removed"
                or _object(report["worker"]).get("status") != "complete"
            ):
                raise self.error_type("native completion lacks successful owned cleanup")
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
        expected = self.native_configuration(child, index, answers, available)
        if (
            report["descriptor_sha256"] != expected["descriptor_sha256"]
            or report["command_sha256"] != expected["command_sha256"]
            or _object(report["execution"])["image_id"] != expected["image_id"]
        ):
            raise self.error_type("native command/configuration lineage differs")

    def native_configuration(
        self,
        child: Path,
        index: int,
        answers: Path,
        available: dict[str, Path],
    ) -> dict[str, object]:
        """Check an original command and inputs, including an unsealed owner."""
        owner = self.owner(child / "owners" / str(index))
        descriptor = child / ("command-" + str(index) + ".json")
        raw = self.bound(owner, descriptor)
        description = _object(_load(raw), {"format", "worker", "executor", "profiles"})
        worker = _object(description["worker"])
        command = self._rows(self.release.to_record()["commands"])[index - 1]
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
        inputs = _object(self._rows(self.template["stages"])[index - 1])["inputs"]
        expected_inputs = []
        for ordinal, name in enumerate(cast(list[str], inputs)):
            source = child / "staging" / str(index) / (str(ordinal) + ".bin")
            source_raw = self.bound(owner, source)
            if source_raw != self.raw(available[name]):
                raise self.error_type("native stage consumed another input")
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
        last = index == len(self._rows(self.template["stages"]))
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
        ):
            raise self.error_type("native command/configuration lineage differs")
        return {
            "descriptor_sha256": _sha(raw),
            "command_sha256": expected_command["sha256"],
            "image_id": expected_executor["image_id"],
        }


def authority_observation(
    capture: _Capture, authorization: Path, funding: dict[str, object]
) -> dict[str, object]:
    """Summarize an already validated captured authority without opening its path."""
    config = _object(funding["config"])
    funded_runs = {str(row["run_id"]): row for row in _rows(funding["auth_runs"])}
    inactive = {row["run_id"] for row in _rows(funding["auth_deactivations"])}
    amounts = {identifier: dict.fromkeys(_AMOUNTS, 0) for identifier in funded_runs}
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
        connection.deserialize(capture.raw[authorization])
        connection.execute("PRAGMA query_only=ON")
        connection.execute("PRAGMA trusted_schema=OFF")
        events = connection.execute("SELECT COUNT(*) FROM auth_events").fetchone()[0]
    totals = _object(funding["totals"])
    return {
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
            for identifier, row in sorted(funded_runs.items())
        ],
        "event_count": events,
    }
