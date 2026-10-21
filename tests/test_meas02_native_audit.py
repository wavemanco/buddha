"""Supplied-control study composition; mocked containers and HTTPS, real owners."""

import copy
import hashlib
import importlib.util
import json
import os
import unittest
from pathlib import Path
from unittest.mock import patch

import test_gateway as gateway_fixtures
import test_native_run as native_fixtures

from buddha.authorization import Authorization
from buddha.executor import ExecutionResult
from buddha.gateway import RawHTTPTransport
from buddha.releases import Release, _json, inventory, prepare_selection

ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / "docs/conformance/meas02-native-audit.py"
SPEC = importlib.util.spec_from_file_location("meas02_native_audit_tests", SOURCE)
assert SPEC is not None and SPEC.loader is not None
audit = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(audit)


class NativeAuditTests(unittest.TestCase):
    def setUp(self):
        self.native = native = native_fixtures.NativeSessionTests("runTest")
        native.setUp()
        self.addCleanup(native.doCleanups)
        self.fixture = fixture = native.fixture
        self.root = fixture.root.resolve()
        self.directory = self.root / "study"
        self.descriptor = self.root / "audit.json"
        self.authority = Authorization.create(
            self.root / "study-authorization.sqlite3",
            authorization_id="synthetic-judge-audit",
            budget_microusd=100_000,
            max_calls=20,
            scope="portable supplied-controls fixture; no real provider calls",
        )
        fixture.write("official", "src/partition.py", "def main():\n    pass\n")
        fixture.release_record["source"] = inventory(fixture.roots["official"])
        fixture.release_record["commands"] = [
            {
                "module": "src.partition",
                "argv": audit.arguments("test-model", seed),
            }
            for seed in (None, None, 0, 20261020)
        ]
        fixture.release_record["artifacts"] = {
            "answers": "generations.jsonl",
            "results": ["v1.1/partitions.jsonl"],
            "summary": "v1.1/summary.json",
        }
        selected = prepare_selection(
            Release.from_record(fixture.release_record),
            fixture.roots,
            capabilities={gateway_fixtures.CAPABILITY: "profiles/openai.json"},
        )
        executor = copy.deepcopy(native.record["executor"])
        executor.pop("mounts")
        self.record = {
            "format": "buddha.meas02-native-audit.v1",
            "pack": str(ROOT / "docs/conformance/meas01-study/pack.json"),
            "proposal": str(ROOT / "docs/conformance/meas02-target-proposal.json"),
            "provenance": str(ROOT / "docs/conformance/meas01-adjudication-review.json"),
            "native": {
                "selection": selected.to_record(),
                "roots": {name: str(path) for name, path in fixture.roots.items()},
                "environment": native.worker["inventories"]["environment"],
                "hooks": {"modules": ["src.partition"], "cache": None, "calls": [], "sdk": []},
                "executor": executor,
                "profiles": {"openai": {"test-model": "primary"}},
                "budget_microusd": 100_000,
                "max_calls": 20,
            },
        }
        self.batches = []
        self.failure_once = False
        self.output_mutation = None
        self.connection = fixture.connection()
        # Synthetic sources do not impersonate the pinned reference. The separate
        # Docker probe uses the real pin with this check enabled.
        self.reference = patch.object(audit, "_reference", return_value=None)
        self.reference.start()
        self.addCleanup(self.reference.stop)

    def prepare(self):
        self.descriptor.write_bytes(_json(self.record))
        return audit.prepare_native_audit(
            self.directory,
            descriptor=self.descriptor,
            authorization=self.authority,
            review=self.fixture.review,
        )

    def container(self, spec, *, initial, handle, limits, docker_endpoint):
        index = initial["command"]["index"]
        self.batches.append(index)
        audit_entry = {
            "src.partition": {
                "kind": "official",
                "path": "/official/src/partition.py",
                "sha256": initial["inventories"]["official"]["src/partition.py"],
            }
        }
        handle({"type": "ready", "aliases": [], "audit": audit_entry})
        result = handle(self.native.request())
        stopped = result["type"] == "stop"
        if self.failure_once and index == 1:
            self.failure_once = False
            raise RuntimeError("synthetic process interruption after completed receipt")
        if not stopped:
            input_root = dict(spec.mounts)["/inputs"]
            raw = (input_root / "generations.jsonl").read_bytes()
            rows = [json.loads(line) for line in raw.splitlines()]
            for row in rows:
                count = len(row["generations"])
                row.update(partition=list(range(count)), distinct=count)
            if self.output_mutation is not None:
                self.output_mutation(rows)
            body = b"".join(_json(row) + b"\n" for row in rows)
            handle(self.native.file("v1.1/partitions.jsonl", body))
        handle(
            {
                "type": "done",
                "status": "stopped" if stopped else "complete",
                "reason": result["reason"] if stopped else "complete",
                "audit": audit_entry,
            }
        )
        return ExecutionResult(
            0,
            "fixture",
            "sha256:" + "a" * 64,
            0,
            0,
            hashlib.sha256(b"").hexdigest(),
            0,
            0.01,
            b"{}",
        )

    def run_study(self, *, keys=True):
        with (
            patch.dict(
                os.environ, {"OPENAI_API_KEY": gateway_fixtures.KEY} if keys else {}, clear=True
            ),
            patch("http.client.HTTPSConnection", return_value=self.connection),
            patch("buddha.native_run.executor.run_container", side_effect=self.container),
        ):
            return audit.run_native_audit(
                self.directory, transport=RawHTTPTransport(allow_paid=True)
            )

    def test_all_four_bound_owners_and_exact_40_outputs_then_keyless_no_send_resume(self):
        self.prepare()
        self.assertEqual(len(self.authority.summary()["runs"]), 4)
        result = self.run_study()
        self.assertEqual(result["status"], "complete")
        self.assertEqual(result["target_count"], 40)
        self.assertEqual(self.batches, [0, 1, 2, 3])
        self.assertEqual(self.connection.request.call_count, 4)
        self.assertEqual(self.authority.summary()["operation_count"], 4)
        self.assertTrue(all(not row["active"] for row in self.authority.summary()["runs"]))
        original = (self.directory / "report.json").read_bytes()
        repeated = self.run_study(keys=False)
        self.assertEqual(repeated["status"], "complete")
        self.assertEqual(self.batches, [0, 1, 2, 3])
        self.assertEqual(self.connection.request.call_count, 4)
        self.assertEqual((self.directory / "report.json").read_bytes(), original)

    def test_partial_attempt_resumes_original_owner_receipt_without_second_send(self):
        self.prepare()
        self.failure_once = True
        with self.assertRaises(RuntimeError):
            self.run_study()
        self.assertEqual(self.connection.request.call_count, 2)
        result = self.run_study()
        self.assertEqual(result["status"], "complete")
        self.assertEqual(self.batches, [0, 1, 1, 2, 3])
        self.assertEqual(self.connection.request.call_count, 4)
        self.assertTrue((self.directory / "attempts/1-0").exists())

    def test_missing_later_owner_or_changed_bound_metadata_stops_before_first_send(self):
        self.prepare()
        later = self.directory / "owners/3"
        later.rename(self.root / "retained-owner-3")
        with self.assertRaises(audit.NativeAuditError):
            self.run_study()
        self.assertEqual(self.connection.request.call_count, 0)

    def test_changed_materialized_bytes_are_rejected_before_first_send(self):
        self.prepare()
        path = self.directory / "inputs/3/generations.jsonl"
        path.write_bytes(path.read_bytes() + b"\n")
        with self.assertRaises(audit.NativeAuditError):
            self.run_study()
        self.assertEqual(self.connection.request.call_count, 0)

    def test_complete_native_report_cannot_bless_wrong_population_or_source(self):
        mutations = [
            lambda rows: rows.pop(),
            lambda rows: rows.append(copy.deepcopy(rows[0])),
            lambda rows: rows[0].update(prompt="changed task"),
            lambda rows: rows[0]["generations"].__setitem__(0, "changed answer"),
            lambda rows: rows[0].update(partition=[False, 1]),
            lambda rows: rows[0].update(distinct=999),
        ]
        for ordinal, mutation in enumerate(mutations):
            with self.subTest(ordinal=ordinal):
                self.directory = self.root / ("invalid-study-" + str(ordinal))
                self.prepare()
                self.output_mutation = mutation
                with self.assertRaises(audit.NativeAuditError):
                    self.run_study()
                self.assertFalse((self.directory / "completed/0.json").exists())

    def test_unknown_preserves_hold_and_prevents_later_owner_dispatch_even_on_resume(self):
        self.prepare()
        self.connection.getresponse.return_value.read.return_value = b"{}"
        result = self.run_study()
        self.assertEqual(result["status"], "incomplete")
        self.assertEqual(self.batches, [0])
        self.assertEqual(self.authority.summary()["operation_count"], 1)
        self.assertGreater(self.authority.summary()["reserved_microusd"], 0)
        self.run_study()
        self.assertEqual(self.connection.request.call_count, 1)
        self.assertNotIn(1, self.batches)

    def test_shared_physical_attempt_cap_stops_second_owner(self):
        self.authority = Authorization.create(
            self.root / "one-call.sqlite3",
            authorization_id="one-physical-call",
            budget_microusd=100_000,
            max_calls=1,
            scope="synthetic shared call exhaustion",
        )
        self.prepare()
        result = self.run_study()
        self.assertEqual(result["status"], "incomplete")
        self.assertEqual(self.connection.request.call_count, 1)
        self.assertNotIn(2, self.batches)

    def test_completion_seal_drift_and_unanchored_record_refuse_resume(self):
        self.prepare()
        original = self.authority.deactivate

        def interrupt(run_id, reason):
            raise RuntimeError("synthetic interruption before authority anchor")

        with patch.object(Authorization, "deactivate", side_effect=interrupt):
            with self.assertRaises(RuntimeError):
                self.run_study()
        self.assertTrue((self.directory / "completed/0.json").is_file())
        self.assertEqual(self.connection.request.call_count, 1)
        with self.assertRaises(audit.NativeAuditError):
            self.run_study()
        self.assertEqual(self.connection.request.call_count, 1)
        self.assertIsNotNone(original)

    def test_real_reference_guard_rejects_synthetic_sources(self):
        self.reference.stop()
        with self.assertRaises(audit.NativeAuditError):
            self.prepare()
        self.assertFalse(self.directory.exists())


if __name__ == "__main__":
    unittest.main()
