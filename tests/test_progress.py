"""Read-only console observation; provider execution is never involved."""

import hashlib
import io
import json
import sqlite3
import tempfile
import time
import unittest
from pathlib import Path
from unittest.mock import patch

from doctor_helpers import files, native, protected

from buddha.ledger import Ledger
from buddha.progress import Progress, snapshot, watch_run
from buddha.provider import Reply


def digest(value):
    return hashlib.sha256(
        json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=True).encode()
    ).hexdigest()


class ProgressTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.directory = Path(temporary.name).resolve()
        self.manifest = {
            "format": "buddha.policy-search.v1",
            "run_id": "run-1",
            "comparison_key": "f" * 64,
            "settings": {"budget_microusd": 50_000_000, "max_calls": 100},
            "secret_canary": "PRIVATE-PROMPT-POLICY-KEY-CANARY",
        }
        self.write_record("manifest.json", self.manifest)

    def write_record(self, name, value):
        (self.directory / name).write_text(
            json.dumps(value | {"record_sha256": digest(value)}), encoding="utf-8"
        )

    def ledger(self):
        return Ledger(
            self.directory / "operations.sqlite3",
            run_id="run-1",
            manifest_sha256=digest(self.manifest),
            budget_microusd=50_000_000,
            max_calls=100,
        )

    def complete(self, ledger, operation="op-1", amount=1_000_000):
        ledger.reserve(operation, "a" * 64, amount)
        ledger.dispatch(operation)
        ledger.complete(
            operation,
            response=Reply(
                "PRIVATE-RESPONSE-REQUEST-ID-CANARY",
                "test-model",
                "PRIVATE-RESPONSE-REQUEST-ID-CANARY",
                5,
                3,
                "stop",
            ).to_record(),
            actual_microusd=600_000,
            provider_request_id="PRIVATE-RESPONSE-REQUEST-ID-CANARY",
        )

    def report(self, **changes):
        value = {
            "format": "buddha.policy-search-report.v1",
            "status": "complete",
            "run_id": "run-1",
            "comparison_key": "f" * 64,
            "candidates": [],
        }
        self.write_record("report.json", value | changes)

    def test_missing_database_is_waiting_and_never_created(self):
        result = snapshot(self.directory)
        self.assertEqual(result["status"], "waiting")
        self.assertFalse((self.directory / "operations.sqlite3").exists())

    def test_aggregate_costs_and_unknown_reservation_are_read_only(self):
        ledger = self.ledger()
        self.complete(ledger)
        ledger.reserve("uncertain", "b" * 64, 2_000_000)
        ledger.dispatch("uncertain")
        ledger.mark_unknown("uncertain")
        events = ledger.events()
        result = snapshot(self.directory)
        self.assertEqual(result["status"], "needs_review")
        self.assertEqual(result["completed_count"], 1)
        self.assertEqual(result["unknown_count"], 1)
        self.assertEqual(result["spent_microusd"], 600_000)
        self.assertEqual(result["held_microusd"], 2_000_000)
        self.assertEqual(result["budget_microusd"], 50_000_000)
        self.assertEqual(ledger.events(), events)
        self.assertNotIn("CANARY", json.dumps(result))

    def test_busy_database_is_unavailable_without_blocking_or_writing(self):
        self.ledger()
        connection = sqlite3.connect(self.directory / "operations.sqlite3")
        self.addCleanup(connection.close)
        connection.execute("BEGIN EXCLUSIVE")
        connection.execute("INSERT INTO events(event_type) VALUES ('synthetic busy')")
        started = time.monotonic()
        result = snapshot(self.directory)
        self.assertEqual(result["status"], "busy_or_changing")
        self.assertIsNone(result["spent_microusd"])
        self.assertIsNone(result["operation_count"])
        self.assertLess(time.monotonic() - started, 0.5)

    def test_blocked_worker_has_flushed_heartbeats_and_safe_output(self):
        ledger = self.ledger()
        self.complete(ledger)
        ledger.reserve("pending", "b" * 64, 2_000_000)
        ledger.dispatch("pending")

        class Flushed(io.StringIO):
            flush_count = 0

            def flush(self):
                self.flush_count += 1
                super().flush()

        output = Flushed()
        with Progress(self.directory, stream=output, poll_seconds=0.005, heartbeat_seconds=0.02):
            time.sleep(0.075)
        printed = output.getvalue()
        self.assertIn("already recorded", printed)
        self.assertIn("still waiting", printed.lower())
        self.assertNotIn("Run complete", printed)
        self.assertIn("Execution returned; saved completion not observed.", printed)
        self.assertIn("Writer identity unknown.", printed)
        self.assertIn("recorded cost $0.600000; held $2.000000; cap $50.000000", printed)
        self.assertGreaterEqual(output.flush_count, 3)
        self.assertNotIn("CANARY", printed)

    def test_observer_failure_never_interrupts_worker_or_masks_original_error(self):
        output = io.StringIO()
        with patch("buddha.progress.snapshot", side_effect=RuntimeError("SECRET-CANARY")):
            with Progress(
                self.directory, stream=output, poll_seconds=0.005, heartbeat_seconds=0.01
            ):
                pass
        self.assertNotIn("SECRET", output.getvalue())
        with self.assertRaisesRegex(ValueError, "worker failed"):
            with Progress(self.directory, stream=output):
                raise ValueError("worker failed")
        self.assertIn("Run stopped", output.getvalue())
        self.assertFalse(output.getvalue().split("Run stopped")[-1].count("Run complete"))

    def test_broken_output_does_not_interrupt_execution(self):
        class Broken(io.StringIO):
            def write(self, value):
                raise OSError("PIPE-SECRET")

        with Progress(self.directory, stream=Broken()):
            pass

    def test_complete_operations_without_report_have_no_running_owner_claim(self):
        self.complete(self.ledger())
        result = snapshot(self.directory)
        self.assertEqual(result["status"], "observed")
        self.assertEqual(result["writer"]["identity"], "unknown")
        self.assertEqual(result["lock"]["status"], "absent")

    def test_dispatched_request_remains_observed_with_unknown_writer(self):
        ledger = self.ledger()
        ledger.reserve("pending", "b" * 64, 2_000_000)
        ledger.dispatch("pending")
        (self.directory / ".search.lock").write_bytes(b"")
        before = ledger.events()
        result = snapshot(self.directory)
        self.assertEqual(result["status"], "observed")
        self.assertEqual(result["dispatched_count"], 1)
        self.assertEqual(result["held_microusd"], 2_000_000)
        self.assertEqual(result["lock"]["status"], "legacy_empty")
        self.assertEqual(result["writer"]["identity"], "unknown")
        self.assertEqual(ledger.events(), before)

    def test_native_progress_and_watch_require_explicit_anchor_and_print_stage_caps(self):
        fixture = native(self, complete=True)
        authority = fixture.authority.path
        before = files(fixture.directory, authority)
        output = io.StringIO()
        with protected(fixture.directory, authority):
            self.assertEqual(snapshot(fixture.directory)["status"], "observed")
            result = watch_run(fixture.directory, authorization=authority, stream=output)
        self.assertEqual(result["status"], "complete")
        self.assertIsNone(result["budget_microusd"])
        self.assertIn("per-stage caps", output.getvalue())
        self.assertIn("saved local completion record", output.getvalue())
        self.assertEqual(files(fixture.directory, authority), before)

    def test_linked_completion_requires_its_v2_report_before_watcher_finishes(self):
        self.manifest["format"] = "buddha.policy-search-continuation.v1"
        self.write_record("manifest.json", self.manifest)
        ledger = self.ledger()
        self.complete(ledger)
        self.assertEqual(snapshot(self.directory)["status"], "observed")
        self.report()
        self.assertNotEqual(snapshot(self.directory)["status"], "complete")
        self.report(format="buddha.policy-search-report.v2")
        before = (self.directory / "operations.sqlite3").read_bytes()
        self.assertEqual(snapshot(self.directory)["status"], "complete")
        self.assertEqual(watch_run(self.directory, stream=io.StringIO())["status"], "complete")
        self.assertEqual((self.directory / "operations.sqlite3").read_bytes(), before)
        ledger.reserve("pending", "b" * 64, 1_000_000)
        self.assertEqual(snapshot(self.directory)["status"], "observed")

    def test_report_requires_checksum_run_identity_and_no_pending_operations(self):
        ledger = self.ledger()
        self.complete(ledger)
        self.report(run_id="other-run")
        self.assertNotEqual(snapshot(self.directory)["status"], "complete")
        self.report()
        self.assertEqual(snapshot(self.directory)["status"], "complete")
        (self.directory / "report.json").write_text('{"status":"complete"}', encoding="utf-8")
        self.assertNotEqual(snapshot(self.directory)["status"], "complete")
        self.report()
        ledger.reserve("pending", "b" * 64, 1_000_000)
        self.assertNotEqual(snapshot(self.directory)["status"], "complete")

    def test_watch_returns_for_complete_or_unknown_and_never_mutates_ledger(self):
        ledger = self.ledger()
        self.complete(ledger)
        self.report()
        before = ledger.events()
        output = io.StringIO()
        self.assertEqual(watch_run(self.directory, stream=output)["status"], "complete")
        self.assertIn("Run complete", output.getvalue())
        ledger.reserve("uncertain", "b" * 64, 2_000_000)
        ledger.dispatch("uncertain")
        ledger.mark_unknown("uncertain")
        before = ledger.events()
        result = watch_run(self.directory, stream=io.StringIO())
        self.assertEqual(result["status"], "needs_review")
        self.assertEqual(ledger.events(), before)

    def test_watch_keeps_waiting_after_all_calls_until_report_appears(self):
        self.complete(self.ledger())
        states = [snapshot(self.directory)]
        self.report()
        states.append(snapshot(self.directory))
        with patch("buddha.progress.snapshot", side_effect=states) as observed:
            result = watch_run(self.directory, stream=io.StringIO(), poll_seconds=0.001)
        self.assertEqual(result["status"], "complete")
        self.assertEqual(observed.call_count, 2)

    def test_error_exit_never_reports_success(self):
        output = io.StringIO()
        with self.assertRaises(KeyboardInterrupt):
            with Progress(self.directory, stream=output):
                raise KeyboardInterrupt
        self.assertIn("Run stopped", output.getvalue())
        self.assertNotIn("Run complete", output.getvalue())

    def test_published_candidates_count_checked_admission_records_only(self):
        self.ledger()
        (self.directory / "decisions").mkdir()
        decision = {
            "status": "admitted",
            "candidate_id": "a" * 64,
            "comparison_key": self.manifest["comparison_key"],
        }
        self.write_record("decisions/seed-0.json", decision)
        self.write_record("decisions/seed-1.json", decision)
        self.write_record("decisions/invalid.json", decision | {"status": "invalid"})
        self.assertEqual(snapshot(self.directory)["candidate_count"], 1)

    def test_baseline_requires_bound_provenance_and_matching_artifact_hashes(self):
        self.manifest = {
            "format": "buddha.baseline.v1",
            "run_id": "run-1",
            "protocol": {},
            "settings": {"budget_microusd": 50_000_000, "max_calls": 100},
        }
        (self.directory / "manifest.json").write_text(json.dumps(self.manifest), encoding="utf-8")
        self.complete(self.ledger())
        evaluation = self.directory / "evaluation"
        (evaluation / "v1.1").mkdir(parents=True)
        artifact_hashes = {}
        for name in (
            "generations.jsonl",
            "v1.1/partitions.jsonl",
            "v1.1/scores.jsonl",
            "v1.1/summary.json",
        ):
            (evaluation / name).write_bytes(b"{}\n")
            artifact_hashes[name] = hashlib.sha256(b"{}\n").hexdigest()
        provenance = {
            "format": "buddha.noveltybench.v1",
            "origin": "buddha-local",
            "protocol": {},
            "artifact_hashes": artifact_hashes,
        }
        (evaluation / "provenance.json").write_text(
            json.dumps(provenance | {"provenance_sha256": digest(provenance)}), encoding="utf-8"
        )
        self.assertEqual(snapshot(self.directory)["status"], "complete")
        (evaluation / "generations.jsonl").write_bytes(b"tampered\n")
        self.assertNotEqual(snapshot(self.directory)["status"], "complete")

    def test_corrupt_database_does_not_expose_its_contents(self):
        (self.directory / "operations.sqlite3").write_bytes(b"SECRET-CORRUPT-DATABASE")
        self.assertEqual(snapshot(self.directory)["status"], "unavailable")
        output = io.StringIO()
        with Progress(self.directory, stream=output):
            pass
        self.assertNotIn("SECRET", output.getvalue())

    def test_invalid_timing_parameters_fail_before_observation(self):
        for interval in (0, -1, True, float("nan"), float("inf"), 61):
            with self.subTest(interval=interval), self.assertRaises(ValueError):
                Progress(self.directory, poll_seconds=interval)
