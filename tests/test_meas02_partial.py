"""Durable partial observations never grant completion or spending authority."""

import hashlib
import json
import unittest
from dataclasses import replace
from unittest.mock import patch

import test_meas02_native_audit as fixtures

from buddha.authorization import Authorization
from buddha.executor import ExecutionResult
from buddha.releases import _json


class NativeAuditPartialTests(unittest.TestCase):
    def setUp(self):
        self.fixture = fixtures.NativeAuditTests("runTest")
        self.fixture.setUp()
        self.addCleanup(self.fixture.doCleanups)

    def configure(self, *, budget=100_000, calls=20):
        fixture = self.fixture
        fixture.authority = Authorization.create(
            fixture.root / "partial-authorization.sqlite3",
            authorization_id="partial-result-fixture",
            budget_microusd=budget,
            max_calls=calls,
            scope="portable partial-record tests; no real provider calls",
        )
        fixture.prepare()

    def observation(self, result):
        path = self.fixture.directory / result["observation"]
        self.assertTrue(path.is_relative_to(self.fixture.directory / "observations"))
        self.assertEqual(json.loads(path.read_bytes()), result)
        self.assertEqual(result["status"], "incomplete")
        self.assertEqual(result["result"], "partial")
        self.assertFalse((self.fixture.directory / "report.json").exists())
        return path

    def stopped_container(self, *, partial_rows=1, invalid=False, reason=None):
        fixture = self.fixture

        def container(spec, *, initial, handle, limits, docker_endpoint):
            index = initial["command"]["index"]
            fixture.batches.append(index)
            audit = {
                "src.partition": {
                    "kind": "official",
                    "path": "/official/src/partition.py",
                    "sha256": initial["inventories"]["official"]["src/partition.py"],
                }
            }
            handle({"type": "ready", "aliases": [], "audit": audit})
            if reason is None:
                first = handle(fixture.native.request())
                self.assertEqual(first["type"], "response")
                stopped = handle(fixture.native.request(seq=1, logical_id="c" * 64))
                self.assertEqual(stopped["type"], "stop")
                stopped_reason = stopped["reason"]
            else:
                stopped_reason = reason
            raw = (dict(spec.mounts)["/inputs"] / "generations.jsonl").read_bytes()
            rows = [json.loads(line) for line in raw.splitlines()][:partial_rows]
            for row in rows:
                count = len(row["generations"])
                row.update(partition=list(range(count)), distinct=count)
            if invalid and rows:
                rows[0]["prompt"] = "changed native source"
            handle(
                fixture.native.file(
                    "v1.1/partitions.jsonl.partial",
                    b"".join(_json(row) + b"\n" for row in rows),
                )
            )
            handle(
                {
                    "type": "done",
                    "status": "failed" if reason else "stopped",
                    "reason": stopped_reason,
                    "audit": audit,
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

        return container

    def test_money_stop_saves_valid_partial_coverage_and_literal_refs(self):
        # Synthetic reservation300, actual first receipt11: only299 remain.
        self.configure(budget=310)
        self.fixture.container = self.stopped_container()
        result = self.fixture.run_study()
        self.observation(result)
        self.assertEqual(result["stop"]["reason"], "money")
        self.assertEqual(result["stop"]["native_reason"], "authority")
        self.assertEqual(result["stopped_occasion"], "baseline")
        self.assertEqual(result["coverage"]["expected_count"], 40)
        self.assertEqual(len(result["coverage"]["sealed_target_ids"]), 0)
        self.assertEqual(len(result["coverage"]["partial_target_ids"]), 1)
        self.assertEqual(len(result["coverage"]["missing_target_ids"]), 39)
        files = result["evidence"]["files"]
        for name, digest in files.items():
            self.assertEqual(
                hashlib.sha256((self.fixture.directory / name).read_bytes()).hexdigest(), digest
            )
        self.assertTrue(any(name.endswith("report.json") for name in files))
        self.assertTrue(any(name.endswith(".partial") for name in files))
        self.assertTrue(result["evidence"]["operations"])

    def test_attempt_cap_is_distinct_from_money_and_keeps_anchored_coverage(self):
        self.configure(calls=1)
        result = self.fixture.run_study()
        self.observation(result)
        self.assertEqual(result["stop"]["reason"], "attempt_limit")
        self.assertEqual(result["stop"]["native_reason"], "authority")
        self.assertEqual(len(result["coverage"]["sealed_target_ids"]), 22)
        self.assertEqual(len(result["coverage"]["missing_target_ids"]), 18)
        self.assertGreater(result["authorization"]["available_microusd"], 300)

    def test_unknown_stop_retains_hold_and_blocks_later_owners(self):
        self.configure()
        self.fixture.connection.getresponse.return_value.read.return_value = b"{}"
        result = self.fixture.run_study()
        self.observation(result)
        self.assertEqual(result["stop"]["reason"], "unknown")
        self.assertEqual(result["stop"]["native_reason"], "unknown")
        self.assertEqual(result["coverage"]["partial_target_ids"], [])
        self.assertEqual(result["authorization"]["reserved_microusd"], 300)
        self.assertEqual(self.fixture.connection.request.call_count, 1)
        self.assertEqual(self.fixture.batches, [0])

    def interrupt_after_receipt(self):
        original = self.fixture.container

        def interrupted(spec, *, initial, handle, limits, docker_endpoint):
            def handle_then_interrupt(frame):
                result = handle(frame)
                if frame.get("type") == "request" and result["type"] == "response":
                    raise KeyboardInterrupt
                return result

            return original(
                spec,
                initial=initial,
                handle=handle_then_interrupt,
                limits=limits,
                docker_endpoint=docker_endpoint,
            )

        self.fixture.container = interrupted
        with self.assertRaises(KeyboardInterrupt):
            self.fixture.run_study()
        self.fixture.container = original

    def test_interruption_saves_receipt_refs_without_inventing_native_report_or_rows(self):
        self.configure()
        self.interrupt_after_receipt()
        paths = list((self.fixture.directory / "observations").glob("*.json"))
        self.assertEqual(len(paths), 1)
        result = json.loads(paths[0].read_bytes())
        self.observation(result)
        self.assertEqual(result["stop"]["reason"], "interrupted")
        self.assertIsNone(result["stop"]["native_reason"])
        self.assertEqual(result["coverage"]["partial_target_ids"], [])
        self.assertFalse((self.fixture.directory / "attempts/0-0/report.json").exists())
        self.assertEqual(result["evidence"]["operations"][0]["status"], "completed")
        self.assertTrue(result["evidence"]["operations"][0]["receipt_sha256"])

    def test_protocol_and_invalid_partial_never_become_money_or_measured_coverage(self):
        self.configure()
        self.fixture.container = self.stopped_container(reason="protocol", invalid=True)
        result = self.fixture.run_study()
        self.observation(result)
        self.assertEqual(result["stop"]["reason"], "protocol")
        self.assertEqual(result["coverage"]["partial_status"], "invalid")
        self.assertEqual(result["coverage"]["partial_target_ids"], [])
        self.assertEqual(len(result["coverage"]["missing_target_ids"]), 40)
        self.assertEqual(self.fixture.connection.request.call_count, 0)

    def test_sealed_batch_and_partial_next_batch_are_distinct_populations(self):
        self.configure(budget=321)
        original = self.fixture.container
        partial = self.stopped_container()

        def container(spec, **kwargs):
            return (original if kwargs["initial"]["command"]["index"] == 0 else partial)(
                spec, **kwargs
            )

        self.fixture.container = container
        result = self.fixture.run_study()
        self.observation(result)
        coverage = result["coverage"]
        self.assertEqual(len(coverage["sealed_target_ids"]), 22)
        self.assertEqual(len(coverage["partial_target_ids"]), 1)
        self.assertEqual(len(coverage["missing_target_ids"]), 17)
        self.assertFalse(set(coverage["sealed_target_ids"]) & set(coverage["partial_target_ids"]))

    def test_late_execution_failure_keeps_unsealed_full_rows_without_money_mislabel(self):
        self.configure(budget=310)
        original = self.fixture.container

        def failed_exit(spec, **kwargs):
            return replace(original(spec, **kwargs), exit_code=9)

        self.fixture.container = failed_exit
        result = self.fixture.run_study()
        self.observation(result)
        self.assertEqual(result["stop"]["reason"], "execution")
        self.assertEqual(result["stop"]["native_reason"], "complete")
        self.assertEqual(result["coverage"]["sealed_target_ids"], [])
        self.assertEqual(len(result["coverage"]["partial_target_ids"]), 22)
        self.assertEqual(len(result["coverage"]["missing_target_ids"]), 18)

    def test_same_owner_resume_preserves_prior_observation_without_adopting_it(self):
        self.configure()
        self.interrupt_after_receipt()
        observation = next((self.fixture.directory / "observations").glob("*.json"))
        before = observation.read_bytes()
        result = self.fixture.run_study()
        self.assertEqual(result["status"], "complete")
        self.assertEqual(observation.read_bytes(), before)
        self.assertEqual(self.fixture.connection.request.call_count, 4)
        self.assertTrue((self.fixture.directory / "attempts/0-1/report.json").exists())

    def test_observation_write_failure_cannot_claim_a_durable_partial(self):
        self.configure(calls=1)
        write = fixtures.audit._write

        def fail_observation(path, raw):
            if path.parent.name == "observations":
                raise OSError("synthetic observation write failure")
            return write(path, raw)

        with patch.object(fixtures.audit, "_write", side_effect=fail_observation):
            with self.assertRaises(fixtures.audit.NativeAuditError):
                self.fixture.run_study()
        self.assertTrue((self.fixture.directory / "attempts/1-0/report.json").exists())
        self.assertFalse((self.fixture.directory / "report.json").exists())

    def test_prekey_recording_revalidates_sources_and_check_remains_write_free(self):
        self.configure(budget=299)
        with self.assertRaises(fixtures.audit.NativeAuditError):
            fixtures.audit.check_native_audit(self.fixture.directory)
        self.assertFalse((self.fixture.directory / "observations").exists())
        result = fixtures.audit.record_stopped_audit(self.fixture.directory)
        first = self.observation(result)
        first_bytes = first.read_bytes()
        self.assertEqual(result["stop"]["reason"], "money")
        self.assertEqual(self.fixture.connection.request.call_count, 0)
        repeated = fixtures.audit.record_stopped_audit(self.fixture.directory)
        self.observation(repeated)
        self.assertEqual(
            repeated["evidence"]["prior_observations"][result["observation"]],
            hashlib.sha256(first_bytes).hexdigest(),
        )
        self.assertEqual(first.read_bytes(), first_bytes)
        self.assertIn("THIS attempt", repeated["coverage"]["scope"])
        before = list((self.fixture.directory / "observations").iterdir())
        source = self.fixture.directory / "targets.json"
        source.write_bytes(source.read_bytes() + b"\n")
        with self.assertRaises(fixtures.audit.NativeAuditError):
            fixtures.audit.record_stopped_audit(self.fixture.directory)
        self.assertEqual(list((self.fixture.directory / "observations").iterdir()), before)


if __name__ == "__main__":
    unittest.main()
