"""Externally sealed search evidence is consumed without reopening mutable data."""

import hashlib
import json
import os
import sqlite3
import unittest
from contextlib import closing
from dataclasses import FrozenInstanceError
from pathlib import Path, PurePosixPath
from types import SimpleNamespace
from unittest.mock import patch

import test_history

from buddha import search_evidence
from buddha.authorization import Authorization
from buddha.common import ValidationError
from buddha.search_evidence import read_authority, read_search_evidence
from buddha.wire import RawEnvelope


def sha(raw):
    return hashlib.sha256(raw).hexdigest()


class SearchEvidenceTests(unittest.TestCase):
    def setUp(self):
        self.fixture = test_history.HistoryTests("runTest")
        self.fixture.setUp()
        self.addCleanup(self.fixture.doCleanups)
        self.directory = self.fixture.directory.resolve()
        self.root = self.directory.parent
        (self.directory / "dataset.jsonl").write_bytes(b'{"id":"one","prompt":"literal"}\n')
        (self.directory / "diagnostics").mkdir()
        (self.directory / "diagnostics" / "request.json").write_bytes(b'{"data":"opaque"}')
        (self.directory / "runtime-source.zip").write_bytes(b"opaque archive, never executed")
        nested = self.directory / "candidates" / "seed" / "evaluation" / "v1.1"
        nested.mkdir(parents=True)
        (nested / "scores.jsonl").write_bytes(b'{"literal":"uninterpreted"}\n')

    def record(self, *, authorization=None, runs=None):
        roots = runs or [self.directory]
        return {
            "format": "buddha.search-verification-input.v1",
            "runs": [
                {
                    "directory": str(root),
                    "files": {
                        file.relative_to(root).as_posix(): sha(file.read_bytes())
                        for file in root.rglob("*")
                        if file.is_file()
                    },
                }
                for root in roots
            ],
            "authorization": (
                None
                if authorization is None
                else {"path": str(authorization), "sha256": sha(authorization.read_bytes())}
            ),
        }

    def files(self):
        return {
            file.relative_to(self.root).as_posix(): file.read_bytes()
            for file in self.root.rglob("*")
            if file.is_file()
        }

    def authority(self):
        authority = Authorization.create(
            self.root / "authorization.sqlite3",
            authorization_id="sealed-read",
            budget_microusd=50_000_000,
            max_calls=128,
            scope="temporary evidence boundary",
        )
        authority.import_history(
            self.directory,
            manifest_sha256=self.fixture.manifest_hash,
            ledger_sha256=sha((self.directory / "operations.sqlite3").read_bytes()),
        )
        return authority.path

    def test_exact_complete_inventory_is_immutable_and_source_is_never_written(self):
        authority = self.authority()
        supplied = self.record(authorization=authority)
        before = self.files()
        with (
            patch.dict(os.environ, {}, clear=True),
            patch("socket.create_connection", side_effect=AssertionError("network forbidden")),
            patch("buddha.ledger.Ledger.__init__", side_effect=AssertionError("writer forbidden")),
            patch(
                "buddha.authorization.runtime_fingerprint",
                side_effect=AssertionError("runtime reconstruction forbidden"),
            ),
        ):
            result = read_search_evidence(self.directory, evidence=supplied)
            run = result.run(self.directory)
            self.assertEqual(set(run.files), set(supplied["runs"][0]["files"]))
            self.assertEqual(run.blob("manifest.json"), before["original/manifest.json"])
            self.assertEqual(result.authorization, before["authorization.sqlite3"])
            self.assertEqual(result.authorization_path, authority)
            supplied["runs"][0]["files"].clear()
            self.assertIn("manifest.json", run.files)
            with self.assertRaises(TypeError):
                run.files["invented"] = b"mutated"
            with self.assertRaises(FrozenInstanceError):
                run.directory = self.root
            self.assertIsNone(result.finish())
        self.assertEqual(before, self.files())

    def test_only_explicitly_listed_roots_can_be_looked_up_without_filesystem_io(self):
        result = read_search_evidence(self.directory, evidence=self.record())
        with patch.object(Path, "open", side_effect=AssertionError("lookup cannot perform IO")):
            self.assertIs(result.run(self.directory), result.runs[0])
            with self.assertRaises(ValidationError):
                result.run(self.root / "unlisted")
            with self.assertRaises(ValidationError):
                result.runs[0].blob("../manifest.json")

    def test_missing_extra_wrong_digest_or_main_root_mismatch_is_rejected(self):
        original = self.record()
        variants = []
        for missing in ("manifest.json", "operations.sqlite3", "diagnostics/request.json"):
            changed = json.loads(json.dumps(original))
            changed["runs"][0]["files"].pop(missing)
            variants.append(changed)
        changed = json.loads(json.dumps(original))
        changed["runs"][0]["files"]["manifest.json"] = "a" * 64
        variants.append(changed)
        changed = json.loads(json.dumps(original))
        changed["runs"][0]["files"]["invented.json"] = "b" * 64
        variants.append(changed)
        for supplied in variants:
            with self.subTest(record=supplied), self.assertRaises(ValidationError):
                read_search_evidence(self.directory, evidence=supplied)
        with self.assertRaises(ValidationError):
            read_search_evidence(self.root, evidence=original)

    def test_record_shape_paths_aliases_and_overlapping_roots_are_rejected(self):
        original = self.record()
        for name in ("../outside", "/absolute", "a\\b", "a//b", "a/./b", "CON", "x."):
            changed = json.loads(json.dumps(original))
            changed["runs"][0]["files"][name] = "a" * 64
            with self.subTest(name=name), self.assertRaises(ValidationError):
                read_search_evidence(self.directory, evidence=changed)
        variants = [
            original | {"unexpected": True},
            original | {"runs": []},
            original | {"runs": original["runs"] * 2},
            original | {"runs": [original["runs"][0] | {"directory": "relative"}]},
        ]
        changed = json.loads(json.dumps(original))
        changed["runs"][0]["files"]["Manifest.json"] = "a" * 64
        variants.append(changed)
        changed = json.loads(json.dumps(original))
        changed["runs"].append({"directory": str(self.directory / "diagnostics"), "files": {}})
        variants.append(changed)
        for supplied in variants:
            with self.subTest(record=supplied), self.assertRaises(ValidationError):
                read_search_evidence(self.directory, evidence=supplied)

    def test_portable_cross_root_case_ancestry_is_rejected_before_tree_observation(self):
        record = self.record()
        record["runs"].append(dict(record["runs"][0]))
        # Model already-canonical POSIX roots even on a Windows test host.
        with (
            patch.object(
                search_evidence,
                "_absolute",
                side_effect=[
                    PurePosixPath("/explicit/CaseRoot"),
                    PurePosixPath("/explicit/caseroot/child"),
                    PurePosixPath("/explicit/CaseRoot"),
                ],
            ),
            patch.object(
                search_evidence, "_tree", side_effect=AssertionError("aliased tree observed")
            ),
            self.assertRaises(ValidationError),
        ):
            read_search_evidence(self.directory, evidence=record)

    def test_portable_authority_case_ancestry_is_rejected_before_tree_observation(self):
        record = self.record()
        record["authorization"] = {"path": str(self.root / "authority"), "sha256": "a" * 64}
        with (
            patch.object(
                search_evidence,
                "_absolute",
                side_effect=[
                    PurePosixPath("/explicit/CaseRoot"),
                    PurePosixPath("/explicit/CaseRoot"),
                    PurePosixPath("/explicit/caseroot/authority.sqlite3"),
                ],
            ),
            patch.object(
                search_evidence, "_tree", side_effect=AssertionError("aliased tree observed")
            ),
            self.assertRaises(ValidationError),
        ):
            read_search_evidence(self.directory, evidence=record)

    def test_observed_directory_entries_are_bounded_across_all_explicit_runs(self):
        roots = [self.root / "minimal-A", self.root / "minimal-B"]
        for root, folder_count in zip(roots, (2, 3), strict=True):
            root.mkdir()
            for name in ("manifest.json", "operations.sqlite3"):
                (root / name).write_bytes((self.directory / name).read_bytes())
            for index in range(folder_count):
                (root / str(index)).mkdir()
        record = self.record(runs=roots)
        # Four sealed files fit; nine actual entries must exceed the global eight.
        with patch.object(search_evidence, "MAX_FILES", 4), self.assertRaises(ValidationError):
            read_search_evidence(roots[0], evidence=record)

    def test_network_roots_are_rejected_before_any_filesystem_observation(self):
        for path in ("//unlisted-host/share/run", "\\\\unlisted-host\\share\\run"):
            record = self.record()
            record["runs"][0]["directory"] = path
            with (
                self.subTest(path=path),
                patch.object(
                    search_evidence, "_plain", side_effect=AssertionError("network path observed")
                ),
                self.assertRaises(ValidationError),
            ):
                read_search_evidence(self.directory, evidence=record)

    def test_final_bracket_detects_changed_removed_added_files_and_authority(self):
        authority = self.authority()
        record = self.record(authorization=authority)
        before = self.files()
        changes = [
            (self.directory / "dataset.jsonl", b"changed"),
            (self.directory / "new.json", b"new"),
            (self.directory / "diagnostics" / "request.json", None),
            (authority, b"changed authority"),
        ]
        for path, replacement in changes:
            with self.subTest(path=path):
                snapshot = read_search_evidence(self.directory, evidence=record)
                old = path.read_bytes() if path.exists() else None
                if replacement is None:
                    path.unlink()
                else:
                    path.write_bytes(replacement)
                with self.assertRaises(ValidationError):
                    snapshot.finish()
                if old is None:
                    path.unlink()
                else:
                    path.write_bytes(old)
        self.assertEqual(before, self.files())

    def test_search_lock_and_nonempty_sidecars_are_denied_even_if_sealed(self):
        for name in (".search.lock", "operations.sqlite3-wal", "operations.sqlite3-shm"):
            with self.subTest(name=name):
                path = self.directory / name
                path.write_bytes(b"potential active writer")
                before = self.files()
                with self.assertRaises(ValidationError):
                    read_search_evidence(self.directory, evidence=self.record())
                self.assertEqual(before, self.files())
                path.unlink()
        empty = self.directory / "operations.sqlite3-journal"
        empty.write_bytes(b"")
        record = self.record()
        record["runs"][0]["files"].pop(empty.name)
        snapshot = read_search_evidence(self.directory, evidence=record)
        snapshot.finish()
        empty.write_bytes(b"new active journal")
        with self.assertRaises(ValidationError):
            snapshot.finish()

    def test_hardlink_alias_is_rejected(self):
        path = self.directory / "alias"
        try:
            path.hardlink_to(self.directory / "dataset.jsonl")
        except OSError:
            self.skipTest("host cannot create a hard link")
        with self.assertRaises(ValidationError):
            read_search_evidence(self.directory, evidence=self.record())
        path.unlink()

    def test_symlink_is_rejected(self):
        path = self.directory / "alias"
        try:
            path.symlink_to(self.root / "outside")
        except OSError:
            self.skipTest("host cannot create a symlink")
        with self.assertRaises(ValidationError):
            read_search_evidence(self.directory, evidence=self.record())

    def test_consumed_bytes_are_checked_and_not_a_prior_file_hash(self):
        record = self.record()
        target = self.directory / "dataset.jsonl"
        original = target.read_bytes()
        original_open = Path.open

        class RestoreOnClose:
            def __init__(reader, stream):
                reader.stream = stream

            def __enter__(reader):
                reader.stream.__enter__()
                return reader.stream

            def __exit__(reader, *arguments):
                try:
                    return reader.stream.__exit__(*arguments)
                finally:
                    target.write_bytes(original)

        def open_file(path, *args, **kwargs):
            if path == target:
                with original_open(path, "wb") as output:
                    output.write(b"transient substituted bytes")
                return RestoreOnClose(original_open(path, *args, **kwargs))
            return original_open(path, *args, **kwargs)

        with patch.object(Path, "open", open_file), self.assertRaises(ValidationError):
            read_search_evidence(self.directory, evidence=record)
        self.assertEqual(target.read_bytes(), original)

    def test_actual_file_and_total_byte_limits_hold_when_stat_reports_zero(self):
        record = self.record()
        original_stat = Path.stat

        def stat(path, *args, **kwargs):
            information = original_stat(path, *args, **kwargs)
            values = {
                key: getattr(information, key) for key in dir(information) if key.startswith("st_")
            }
            return SimpleNamespace(**(values | {"st_size": 0}))

        for constant in ("MAX_LEDGER_BYTES", "MAX_TOTAL_BYTES"):
            with (
                self.subTest(constant=constant),
                patch.object(search_evidence, constant, 4),
                patch.object(Path, "stat", stat),
                self.assertRaises(ValidationError),
            ):
                read_search_evidence(self.directory, evidence=record)

    def test_authority_decodes_exact_snapshot_in_memory_without_opening_recorded_paths(self):
        path = self.authority()
        original = path.read_bytes()
        snapshot = read_search_evidence(self.directory, evidence=self.record(authorization=path))
        path.write_bytes(b"transient source change")
        original_connect = sqlite3.connect
        destinations, consumed, guards = [], [], []

        class AuditConnection(sqlite3.Connection):
            snapshot = False

            def deserialize(connection, data, /, *, name="main"):
                connection.snapshot = True
                consumed.append(data)
                return super().deserialize(data, name=name)

            def execute(connection, query, *args, **kwargs):
                if connection.snapshot and query.lstrip().upper().startswith("SELECT"):
                    guards.append(
                        (
                            super().execute("PRAGMA query_only").fetchone()[0],
                            super().execute("PRAGMA trusted_schema").fetchone()[0],
                        )
                    )
                return super().execute(query, *args, **kwargs)

        def connect(database, *args, **kwargs):
            destinations.append(database)
            kwargs["factory"] = AuditConnection
            return original_connect(database, *args, **kwargs)

        try:
            with (
                patch("buddha.search_evidence.sqlite3.connect", side_effect=connect),
                patch.object(Path, "open", side_effect=AssertionError("financial decode IO")),
            ):
                record = read_authority(snapshot.authorization)
            self.assertEqual(record["totals"]["spent_microusd"], 1710)
            self.assertEqual(record["totals"]["reserved_microusd"], 532373)
            self.assertEqual(len(record["auth_runs"]), 1)
            self.assertEqual(len(record["auth_operations"]), 10)
            self.assertTrue(destinations)
            self.assertEqual(set(destinations), {":memory:"})
            self.assertEqual(consumed, [original])
            self.assertTrue(guards)
            self.assertEqual(set(guards), {(1, 0)})
        finally:
            path.write_bytes(original)
        snapshot.finish()

    def test_authority_schema_and_foreign_key_violations_fail_without_source_writes(self):
        path = self.authority()
        original = path.read_bytes()
        for sql in (
            "CREATE VIEW sqliteXuntrusted AS SELECT 1",
            "INSERT INTO auth_deactivations VALUES ('orphan','not a known run')",
        ):
            with self.subTest(sql=sql):
                path.write_bytes(original)
                with closing(sqlite3.connect(path)) as connection, connection:
                    connection.execute(sql)
                before = path.read_bytes()
                with self.assertRaises(ValidationError):
                    read_authority(before)
                self.assertEqual(path.read_bytes(), before)

    def test_authority_decode_respects_byte_and_row_ceilings(self):
        raw = self.authority().read_bytes()
        with (
            patch.object(search_evidence, "MAX_LEDGER_BYTES", 4),
            patch(
                "buddha.search_evidence.sqlite3.connect", side_effect=AssertionError("oversized")
            ),
            self.assertRaises(ValidationError),
        ):
            read_authority(raw)
        with patch.object(search_evidence, "MAX_ROWS", 4), self.assertRaises(ValidationError):
            read_authority(raw)

    def test_authority_validates_all_declared_row_invariants_not_only_totals(self):
        path = self.authority()
        original = path.read_bytes()
        first, unknown = self.fixture.ids[0], self.fixture.ids[9]
        cases = [
            ("UPDATE auth_runs SET historical=2", ()),
            (
                "UPDATE auth_runs SET historical=0,"
                "historical_ledger_sha256=NULL,runtime_sha256=NULL",
                (),
            ),
            ("UPDATE auth_runs SET runtime_sha256='not-a-runtime-seal'", ()),
            ("UPDATE auth_runs SET manifest_sha256='not-a-manifest-seal'", ()),
            ("UPDATE auth_runs SET directory='relative/path'", ()),
            ("UPDATE auth_runs SET ledger_path='relative.sqlite3'", ()),
            ("UPDATE auth_operations SET operation_id='' WHERE operation_id=?", (first,)),
            ("UPDATE auth_operations SET response_json=NULL WHERE operation_id=?", (first,)),
            ("UPDATE auth_operations SET provider_request_id='' WHERE operation_id=?", (first,)),
            (
                "UPDATE auth_operations SET request_sha256='not-a-seal' WHERE operation_id=?",
                (first,),
            ),
            ("INSERT INTO auth_deactivations VALUES ('original-run','')", ()),
            (
                "INSERT INTO auth_acceptances VALUES ('original-run',?,'original-run',?,?)",
                (unknown, "not-a-seal", "reason"),
            ),
            (
                "INSERT INTO auth_acceptances VALUES ('original-run',?,'original-run',?,?)",
                (unknown, "a" * 64, ""),
            ),
        ]
        cases.extend(
            (
                "UPDATE auth_operations SET response_json=? WHERE operation_id=?",
                (response, first),
            )
            for response in ("not JSON", "[]", '{"value":NaN}', '{"value":1,"value":2}')
        )
        for sql, arguments in cases:
            with self.subTest(sql=sql, arguments=arguments):
                path.write_bytes(original)
                self.fixture.corrupt.__func__(SimpleNamespace(path=path), sql, arguments)
                before = path.read_bytes()
                with self.assertRaises(ValidationError):
                    read_authority(before)
                self.assertEqual(path.read_bytes(), before)

    def test_authority_receipt_objects_are_opaque_across_codecs_and_unknown_id_disagreements(self):
        path = self.authority()
        envelope = RawEnvelope(
            "openai", 200, b"literal provider bytes", (("x-request-id", "wire-id"),)
        )
        opaque = {"format": "buddha.gateway-receipt.v1", "envelope": envelope.to_record()}
        self.fixture.corrupt.__func__(
            SimpleNamespace(path=path),
            "UPDATE auth_operations SET response_json=? WHERE operation_id=?",
            (json.dumps(opaque), self.fixture.ids[0]),
        )
        self.fixture.corrupt.__func__(
            SimpleNamespace(path=path),
            "UPDATE auth_operations SET response_json=?,provider_request_id=? WHERE operation_id=?",
            (
                json.dumps({"provider_request_id": "body-id"}),
                "different-header-id",
                self.fixture.ids[9],
            ),
        )
        raw = path.read_bytes()
        result = read_authority(raw)
        by_id = {row["operation_id"]: row for row in result["auth_operations"]}
        self.assertEqual(json.loads(by_id[self.fixture.ids[0]]["response_json"]), opaque)
        unknown = by_id[self.fixture.ids[9]]
        self.assertEqual(json.loads(unknown["response_json"])["provider_request_id"], "body-id")
        self.assertEqual(unknown["provider_request_id"], "different-header-id")
        self.assertEqual(result["totals"]["spent_microusd"], 1710)
        self.assertEqual(result["totals"]["reserved_microusd"], 532373)
        self.assertEqual(path.read_bytes(), raw)

    def test_authority_foreign_absolute_owner_paths_remain_data_without_dereferencing(self):
        path = self.authority()
        self.fixture.corrupt.__func__(
            SimpleNamespace(path=path),
            "UPDATE auth_runs SET directory=?,ledger_path=?",
            (r"Z:\retired\run", r"Z:\retired\run\operations.sqlite3"),
        )
        raw = path.read_bytes()
        with patch.object(Path, "open", side_effect=AssertionError("recorded owner path IO")):
            result = read_authority(raw)
        self.assertEqual(result["auth_runs"][0]["directory"], r"Z:\retired\run")
        self.assertEqual(path.read_bytes(), raw)

    def test_authority_sidecars_and_unlisted_authority_fields_are_rejected(self):
        path = self.authority()
        record = self.record(authorization=path)
        for suffix in ("-wal", "-shm", "-journal"):
            sidecar = path.with_name(path.name + suffix)
            sidecar.write_bytes(b"potential writer")
            with self.assertRaises(ValidationError):
                read_search_evidence(self.directory, evidence=record)
            sidecar.unlink()
        for authorization in (
            {"path": str(path)},
            {"path": str(path), "sha256": "a" * 64},
            {"path": str(path), "sha256": sha(path.read_bytes()), "extra": True},
        ):
            with self.subTest(authorization=authorization), self.assertRaises(ValidationError):
                read_search_evidence(
                    self.directory, evidence=record | {"authorization": authorization}
                )


if __name__ == "__main__":
    unittest.main()
