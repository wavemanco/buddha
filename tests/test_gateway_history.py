"""Sealed raw accounting remains readable after its executing runtime is removed."""

import base64
import hashlib
import json
import sqlite3
import unittest
import zlib
from contextlib import closing
from dataclasses import replace
from pathlib import Path
from unittest.mock import patch

import test_gateway as fixtures

from buddha import gateway_history
from buddha.gateway_history import GatewayHistoryError, read_gateway_history
from buddha.ledger import BudgetExceeded
from buddha.provider import ProviderUncertain
from buddha.releases import _json
from buddha.wire import RawEnvelope


def sha(raw):
    return hashlib.sha256(raw).hexdigest()


class GatewayHistoryTests(unittest.TestCase):
    def setUp(self):
        self.fixture = self.new_fixture()
        self.directory = self.fixture.directory

    def new_fixture(self):
        fixture = fixtures.GatewayTests("runTest")
        fixture.setUp()
        self.addCleanup(fixture.doCleanups)
        return fixture

    def seals(self, directory=None):
        directory = directory or self.directory
        record = json.loads((directory / "manifest.json").read_bytes())
        return {
            "manifest_sha256": record["record_sha256"],
            "ledger_sha256": sha((directory / "operations.sqlite3").read_bytes()),
        }

    def read(self, directory=None, **changes):
        directory = directory or self.directory
        return read_gateway_history(directory, **(self.seals(directory) | changes))

    def complete(self):
        self.fixture.send()
        return self.fixture.gateway().operation_id(self.fixture.call)

    def mutate(self, sql, parameters=()):
        # Corrupt only this synthetic local evidence, retaining the exact original DDL.
        with (
            closing(sqlite3.connect(self.directory / "operations.sqlite3")) as connection,
            connection,
        ):
            triggers = connection.execute(
                "SELECT name,sql FROM sqlite_master WHERE type='trigger'"
            ).fetchall()
            for name, _ in triggers:
                connection.execute('DROP TRIGGER "' + name.replace('"', '""') + '"')
            connection.execute(sql, parameters)
            for _, statement in triggers:
                connection.execute(statement)

    def test_normal_completion_retains_checkpoint_and_terminal_but_charges_once(self):
        operation_id = self.complete()
        history = self.read()
        self.assertEqual(history.run_id, "run")
        self.assertEqual((history.budget_microusd, history.max_calls), (10_000, 20))
        self.assertEqual(history.manifest_sha256, self.seals()["manifest_sha256"])
        self.assertEqual(history.ledger_sha256, self.seals()["ledger_sha256"])
        self.assertEqual(len(history.operations), 1)
        operation = history.operations[0]
        self.assertEqual((operation.operation_id, operation.status), (operation_id, "completed"))
        self.assertEqual((operation.reserve_microusd, operation.actual_microusd), (300, 11))
        self.assertEqual(operation.receipt, operation.checkpoint)
        self.assertEqual(operation.receipt["request"], self.fixture.call.to_record())
        self.assertEqual(
            (operation.provider_request_id, operation.checkpoint_request_id),
            ("req-synthetic", "req-synthetic"),
        )
        self.assertEqual(
            history.totals(),
            {
                "committed_microusd": 11,
                "spent_microusd": 11,
                "reserved_microusd": 0,
                "operation_count": 1,
            },
        )

    def test_reconciled_completion_keeps_different_checkpoint_and_recorded_actual_without_repricing(
        self,
    ):
        gateway = self.fixture.gateway()
        with self.assertRaises(ProviderUncertain):
            self.fixture.send(
                gateway, connection=self.fixture.connection(self.fixture.response(usage={}))
            )
        operation_id = gateway.operation_id(self.fixture.call)
        raw = self.fixture.response().read.return_value
        terminal = {
            "format": "buddha.gateway-receipt.v1",
            "request": self.fixture.call.to_record(),
            "envelope": RawEnvelope(
                "openai", 200, raw, (("x-request-id", "req-reconciled"),)
            ).to_record(),
        }
        gateway.ledger.complete(
            operation_id,
            response=terminal,
            actual_microusd=17,
            provider_request_id="req-reconciled",
        )
        operation = self.read().operations[0]
        self.assertNotEqual(operation.receipt, operation.checkpoint)
        self.assertEqual(operation.receipt["request"], operation.checkpoint["request"])
        self.assertEqual(
            (operation.provider_request_id, operation.checkpoint_request_id),
            ("req-reconciled", "req-synthetic"),
        )
        self.assertEqual(operation.actual_microusd, 17)
        self.assertEqual(self.read().totals()["spent_microusd"], 17)

    def test_reserved_dispatched_and_unknown_states_keep_full_hold_with_optional_checkpoint(self):
        for status in ("reserved", "dispatched", "unknown-no-reply", "unknown-raw-reply"):
            fixture = self.new_fixture()
            gateway = fixture.gateway(live=False if status in {"reserved", "dispatched"} else True)
            if status in {"reserved", "dispatched"}:
                with self.assertRaises(ValueError):
                    fixture.send(gateway)
                if status == "dispatched":
                    self.assertTrue(gateway.ledger.dispatch(gateway.operation_id(fixture.call)))
            else:
                response = fixture.response(usage={})
                connection = fixture.connection(response)
                if status == "unknown-no-reply":
                    connection.getresponse.side_effect = TimeoutError("synthetic interruption")
                with self.assertRaises(ProviderUncertain):
                    fixture.send(gateway, connection=connection)
            with self.subTest(status=status):
                history = self.read(fixture.directory)
                operation = history.operations[0]
                self.assertEqual(operation.status, status.split("-")[0])
                self.assertIsNone(operation.receipt)
                self.assertIsNone(operation.actual_microusd)
                self.assertIsNone(operation.provider_request_id)
                self.assertEqual(operation.checkpoint is not None, status == "unknown-raw-reply")
                self.assertEqual(
                    history.totals(),
                    {
                        "committed_microusd": 300,
                        "spent_microusd": 0,
                        "reserved_microusd": 300,
                        "operation_count": 1,
                    },
                )

    def test_known_overrun_preserves_true_charge_above_the_reservation(self):
        response = self.fixture.response(usage={"prompt_tokens": 400, "completion_tokens": 3})
        with self.assertRaises(BudgetExceeded):
            self.fixture.send(connection=self.fixture.connection(response))
        operation = self.read().operations[0]
        self.assertEqual(
            (operation.status, operation.reserve_microusd, operation.actual_microusd),
            ("completed", 300, 406),
        )
        self.assertEqual(self.read().totals()["spent_microusd"], 406)

    def test_frozen_history_and_nested_copies_cannot_change_evidence_or_totals(self):
        self.complete()
        history = self.read()
        operation = history.operations[0]
        self.assertIsInstance(history.operations, tuple)
        with self.assertRaises(AttributeError):
            history.run_id = "changed"
        with self.assertRaises(AttributeError):
            operation.status = "reserved"
        manifest = history.manifest
        manifest["settings"]["budget_microusd"] = 0
        receipt, checkpoint = operation.receipt, operation.checkpoint
        receipt["request"]["logical_id"] = "changed-terminal"
        checkpoint["envelope"]["body_base64"] = "changed-checkpoint"
        totals = history.totals()
        totals["spent_microusd"] = 999
        self.assertEqual(history.manifest["settings"]["budget_microusd"], 10_000)
        self.assertEqual(operation.receipt["request"], self.fixture.call.to_record())
        self.assertNotEqual(operation.checkpoint["envelope"]["body_base64"], "changed-checkpoint")
        self.assertEqual(history.totals()["spent_microusd"], 11)

    def test_reader_uses_memory_deserialize_query_only_and_never_live_runtime_or_keys(self):
        self.complete()
        allowed = {self.directory / name for name in ("manifest.json", "operations.sqlite3")}
        before = {path: (sha(path.read_bytes()), path.stat().st_mtime_ns) for path in allowed}
        entries = sorted(path.name for path in self.directory.iterdir())
        connect, opened, open_path = sqlite3.connect, [], Path.open

        class TrackedConnection(sqlite3.Connection):
            def deserialize(self, *args, **kwargs):
                opened.append("deserialize")
                return super().deserialize(*args, **kwargs)

            def execute(self, statement, *args, **kwargs):
                if statement.replace(" ", "").upper() == "PRAGMAQUERY_ONLY=ON":
                    opened.append("query-only")
                return super().execute(statement, *args, **kwargs)

        def memory_only(database, *args, **kwargs):
            self.assertEqual(database, ":memory:")
            kwargs["factory"] = TrackedConnection
            return connect(database, *args, **kwargs)

        def evidence_only(path, *args, **kwargs):
            self.assertIn(path.absolute(), allowed)
            mode = args[0] if args else kwargs.get("mode", "r")
            self.assertNotIn("w", mode)
            self.assertNotIn("+", mode)
            return open_path(path, *args, **kwargs)

        with (
            patch("buddha.gateway.Gateway.__init__", side_effect=AssertionError("live Gateway")),
            patch("buddha.ledger.Ledger.__init__", side_effect=AssertionError("live Ledger")),
            patch(
                "buddha.authorization.AuthorizedLedger.__init__",
                side_effect=AssertionError("live authority"),
            ),
            patch("buddha.gateway.execution_identity", side_effect=AssertionError("source lookup")),
            patch("os.environ.get", side_effect=AssertionError("credential lookup")),
            patch("http.client.HTTPSConnection", side_effect=AssertionError("network lookup")),
            patch.object(Path, "open", new=evidence_only),
            patch("sqlite3.connect", side_effect=memory_only),
        ):
            history = self.read()
        self.assertEqual(history.totals()["spent_microusd"], 11)
        self.assertIn("deserialize", opened)
        self.assertIn("query-only", opened)
        self.assertEqual(sorted(path.name for path in self.directory.iterdir()), entries)
        self.assertEqual(
            {path: (sha(path.read_bytes()), path.stat().st_mtime_ns) for path in allowed}, before
        )

    def test_actual_old_core_ten_fixture_is_self_contained_and_needs_no_old_source(self):
        fixture_path = Path(__file__).parent / "fixtures/gateway-v1-old-core.json"
        record = json.loads(fixture_path.read_bytes())
        directory = self.fixture.root / "retired-old-owner"
        directory.mkdir()
        for name, payload in [
            ("manifest.json", record["manifest"]),
            ("operations.sqlite3", record["ledger"]),
        ]:
            raw = zlib.decompress(base64.b64decode(payload["data"], validate=True))
            self.assertEqual((len(raw), sha(raw)), (payload["bytes"], payload["sha256"]))
            (directory / name).write_bytes(raw)
        with patch(
            "buddha.gateway.validate_manifest", side_effect=AssertionError("current CORE validator")
        ):
            history = read_gateway_history(
                directory,
                manifest_sha256=record["manifest_sha256"],
                ledger_sha256=record["ledger"]["sha256"],
            )
        self.assertEqual(history.run_id, record["expected"]["run_id"])
        self.assertEqual(len(history.manifest["core"]), 10)
        self.assertIn("buddha.benchmark", history.manifest["core"])
        self.assertIn("buddha.evaluation", history.manifest["core"])
        self.assertNotIn("buddha.common", history.manifest["core"])
        self.assertEqual(history.totals()["operation_count"], 4)
        self.assertEqual(history.totals()["spent_microusd"], 20)
        self.assertTrue(
            all(
                item.checkpoint is not None and item.receipt is not None
                for item in history.operations
            )
        )
        self.assertEqual(
            sorted(path.name for path in directory.iterdir()),
            ["manifest.json", "operations.sqlite3"],
        )

    def test_incorrect_operator_seals_and_drift_during_deserialization_are_denied(self):
        self.complete()
        for changes in [
            {"manifest_sha256": "0" * 64},
            {"ledger_sha256": "0" * 64},
            {"manifest_sha256": "wrong"},
        ]:
            with self.subTest(changes=changes), self.assertRaises(GatewayHistoryError):
                self.read(**changes)
        seals, connect = self.seals(), sqlite3.connect
        path = self.directory / "operations.sqlite3"
        original, drifted = path.read_bytes(), False

        def drift(database, *args, **kwargs):
            nonlocal drifted
            if not drifted:
                drifted = True
                path.write_bytes(original + b"changed-after-snapshot")
            return connect(database, *args, **kwargs)

        with patch("sqlite3.connect", side_effect=drift), self.assertRaises(GatewayHistoryError):
            read_gateway_history(self.directory, **seals)
        self.assertTrue(drifted)

    def test_active_sqlite_sidecars_reject_without_modifying_any_source_bytes(self):
        self.complete()
        for suffix in ("-wal", "-journal", "-shm"):
            sidecar = self.directory / ("operations.sqlite3" + suffix)
            sidecar.write_bytes(b"unsealed active state")
            before = {path: path.read_bytes() for path in self.directory.iterdir()}
            with self.subTest(suffix=suffix), self.assertRaises(GatewayHistoryError):
                self.read()
            self.assertEqual({path: path.read_bytes() for path in self.directory.iterdir()}, before)
            sidecar.unlink()

    def test_sealed_malformed_schema_or_orphan_checkpoint_is_rejected(self):
        self.complete()
        path = self.directory / "operations.sqlite3"
        original = path.read_bytes()
        receipt = json.dumps(self.read().operations[0].receipt)
        for sql, parameters in [
            ("PRAGMA user_version=77", ()),
            ("DROP TABLE unknown_receipts", ()),
            ("INSERT INTO unknown_receipts VALUES (?,?,?)", ("f" * 64, receipt, "req-orphan")),
            ("UPDATE operations SET response_json=?", ("{malformed JSON",)),
        ]:
            path.write_bytes(original)
            if sql == "DROP TABLE unknown_receipts":
                with closing(sqlite3.connect(path)) as connection, connection:
                    connection.execute(sql)
            else:
                self.mutate(sql, parameters)
            with self.subTest(sql=sql), self.assertRaises(GatewayHistoryError):
                self.read()
        path.write_bytes(b"not a SQLite database")
        with self.assertRaises(GatewayHistoryError):
            self.read()

    def test_terminal_and_checkpoint_request_binding_and_recorded_identity_mismatches_are_rejected(
        self,
    ):
        self.complete()
        path = self.directory / "operations.sqlite3"
        original = path.read_bytes()
        terminal = self.read().operations[0].receipt
        for table in ("operations", "unknown_receipts"):
            changed = json.loads(json.dumps(terminal))
            changed["request"]["logical_id"] = "different-physical-operation"
            path.write_bytes(original)
            self.mutate("UPDATE " + table + " SET response_json=?", (json.dumps(changed),))
            with self.subTest(table=table), self.assertRaises(GatewayHistoryError):
                self.read()
        path.write_bytes(original)
        self.mutate("UPDATE operations SET provider_request_id='different-provider-id'")
        with self.assertRaises(GatewayHistoryError):
            self.read()

    def test_limits_preserve_legal_receipt_above_32_mib_and_reject_smaller_reviewed_bounds(self):
        self.assertEqual(gateway_history.MAX_LEDGER_BYTES, 512 * 1024**2)
        self.assertEqual(gateway_history.MAX_RECEIPT_BYTES, 64 * 1024**2)
        # Both raw bodies remain below the actual 16 MiB wire ceiling. Their
        # combined base64 receipt legally exceeds the old 32 MiB JSON helper cap.
        text = "x" * (12 * 1024**2)
        body = _json({"model": "test-model", "messages": [{"role": "user", "content": text}]})
        call = replace(self.fixture.call, body=body)
        response = self.fixture.response(choices=[{"message": {"content": text}}])
        self.fixture.send(call=call, connection=self.fixture.connection(response))
        history = self.read()
        operation = history.operations[0]
        self.assertGreater(len(json.dumps(operation.receipt).encode()), 32 * 1024**2)
        self.assertEqual(
            RawEnvelope.from_record(operation.receipt["envelope"]).body, response.read.return_value
        )
        self.assertEqual(base64.b64decode(operation.receipt["request"]["body_base64"]), body)
        self.assertEqual(history.totals()["spent_microusd"], 11)
        with (
            patch.object(gateway_history, "MAX_LEDGER_BYTES", 1),
            self.assertRaises(GatewayHistoryError),
        ):
            self.read()
        with (
            patch.object(gateway_history, "MAX_RECEIPT_BYTES", 32 * 1024**2),
            self.assertRaises(GatewayHistoryError),
        ):
            self.read()


if __name__ == "__main__":
    unittest.main()
