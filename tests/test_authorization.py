"""One shared authorization across immutable history and atomic run ledgers."""

import hashlib
import multiprocessing
import sqlite3
import tempfile
import unittest
from concurrent.futures import ThreadPoolExecutor
from contextlib import closing
from pathlib import Path
from unittest.mock import patch

from buddha.authorization import Authorization, AuthorizedLedger, runtime_fingerprint
from buddha.benchmark import _canonical
from buddha.evaluation import ValidationError
from buddha.ledger import BudgetExceeded, Ledger, OperationConflict
from buddha.provider import Reply


def sha(value):
    return hashlib.sha256(_canonical(value)).hexdigest()


def reserve_in_process(authority_path, directory, ready, start, results):
    """Separate connections/processes must serialize through the attached authority."""
    ledger = Authorization(authority_path).for_run(directory)
    ready.put(directory.name)
    start.wait(10)
    try:
        ledger.reserve(directory.name, sha(directory.name), 100)
        results.put("reserved")
    except BudgetExceeded:
        results.put("denied")


class AuthorizationTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)
        self.path = self.root / "authorization.sqlite3"
        self.authority = self.create()

    def create(self, **changes):
        values = dict(
            authorization_id="first-experiment",
            budget_microusd=50_000_000,
            max_calls=128,
            scope="reviewed scope",
        )
        values.update(changes)
        return Authorization.create(self.path, **values)

    def prepare(self, name, *, budget=50_000_000, max_calls=128, bind=True):
        directory = self.root / name
        directory.mkdir()
        manifest = {
            "format": "buddha.policy-search.v1",
            "run_id": name,
            "settings": {"budget_microusd": budget, "max_calls": max_calls},
        }
        digest = sha(manifest)
        (directory / "manifest.json").write_bytes(
            _canonical(manifest | {"record_sha256": digest}) + b"\n"
        )
        ledger = Ledger(
            directory / "operations.sqlite3",
            run_id=name,
            manifest_sha256=digest,
            budget_microusd=budget,
            max_calls=max_calls,
        )
        if bind:
            self.authority.bind_run(directory, runtime_sha256=runtime_fingerprint())
            ledger = self.authority.for_run(directory)
        return directory, ledger, digest

    def reserve(self, ledger, operation="operation", amount=100):
        return ledger.reserve(operation, sha(operation), amount)

    def complete(self, ledger, operation="operation", actual=60):
        reply = Reply("answer", "model", operation + "-receipt", 1, 1, "stop")
        return ledger.complete(
            operation,
            response=reply.to_record(),
            actual_microusd=actual,
            provider_request_id=reply.provider_request_id,
        )

    def seal(self, directory, digest):
        ledger_hash = hashlib.sha256((directory / "operations.sqlite3").read_bytes()).hexdigest()
        self.authority.import_history(directory, manifest_sha256=digest, ledger_sha256=ledger_hash)
        return ledger_hash

    def test_create_open_and_readonly_summary(self):
        before = self.path.read_bytes()
        summary = Authorization(self.path).summary()
        self.assertEqual(summary["authorization_id"], "first-experiment")
        self.assertEqual(summary["available_microusd"], 50_000_000)
        self.assertEqual(summary["remaining_calls"], 128)
        self.assertEqual(summary["runs"], [])
        self.assertEqual(summary["scope"], "reviewed scope")
        self.assertEqual(
            summary["terms_sha256"],
            sha(
                {
                    "currency": "USD",
                    "budget_microusd": 50_000_000,
                    "max_calls": 128,
                    "scope": "reviewed scope",
                }
            ),
        )
        self.assertEqual(before, self.path.read_bytes())
        with self.assertRaises(ValidationError):
            self.create()

    def test_invalid_and_missing_authority_does_not_create_storage(self):
        missing = self.root / "missing.sqlite3"
        with self.assertRaises(ValidationError):
            Authorization(missing)
        self.assertFalse(missing.exists())
        self.path.unlink()
        for changes in [
            {"budget_microusd": True},
            {"max_calls": -1},
            {"scope": ""},
            {"authorization_id": ""},
        ]:
            with self.subTest(changes=changes), self.assertRaises(ValidationError):
                self.create(**changes)
            self.assertFalse(self.path.exists())

    def test_recorded_scope_is_checked_against_its_terms_checksum(self):
        with closing(sqlite3.connect(self.path)) as connection:
            trigger = connection.execute(
                "SELECT sql FROM sqlite_master WHERE name='auth_config_no_update'"
            ).fetchone()[0]
            connection.execute("DROP TRIGGER auth_config_no_update")
            connection.execute("UPDATE auth_config SET scope='different authority'")
            connection.execute(trigger)
            connection.commit()
        with self.assertRaises(ValidationError):
            Authorization(self.path)

    def test_bind_requires_current_runtime_and_empty_new_ledger(self):
        directory, ledger, _ = self.prepare("new", bind=False)
        with self.assertRaises(ValidationError):
            self.authority.bind_run(directory, runtime_sha256="a" * 64)
        self.reserve(ledger)
        with self.assertRaises(ValidationError):
            self.authority.bind_run(directory, runtime_sha256=runtime_fingerprint())

    def test_missing_or_changed_binding_is_rejected(self):
        directory, _, _ = self.prepare("unbound", bind=False)
        with self.assertRaises(ValidationError):
            self.authority.for_run(directory)
        self.authority.bind_run(directory, runtime_sha256=runtime_fingerprint())
        self.authority.bind_run(directory, runtime_sha256=runtime_fingerprint())
        manifest = directory / "manifest.json"
        manifest.write_bytes(manifest.read_bytes() + b"tampered")
        with self.assertRaises(ValidationError):
            self.authority.for_run(directory)

    def test_atomic_completion_and_idempotent_replay(self):
        directory, ledger, _ = self.prepare("active")
        self.assertIsInstance(ledger, AuthorizedLedger)
        self.reserve(ledger)
        self.assertTrue(ledger.dispatch("operation"))
        expected = self.complete(ledger)
        events = self.authority.summary()["event_count"]
        self.assertEqual(self.reserve(ledger), expected)
        self.assertEqual(self.complete(ledger), expected)
        summary = self.authority.summary()
        self.assertEqual(summary["spent_microusd"], 60)
        self.assertEqual(summary["reserved_microusd"], 0)
        self.assertEqual(summary["operation_count"], 1)
        self.assertEqual(summary["event_count"], events)
        self.assertEqual(self.authority.for_run(directory).get("operation"), expected)

    def test_replay_at_shared_cap_and_conflicting_reservation(self):
        self.path.unlink()
        self.authority = self.create(budget_microusd=100, max_calls=1)
        _, ledger, _ = self.prepare("capped")
        first = self.reserve(ledger)
        self.assertEqual(self.reserve(ledger), first)
        with self.assertRaises(OperationConflict):
            ledger.reserve("operation", sha("changed"), 100)
        with self.assertRaises(BudgetExceeded):
            self.reserve(ledger, "another", 0)

    def test_independent_runs_share_dollar_and_call_caps(self):
        self.path.unlink()
        self.authority = self.create(budget_microusd=100, max_calls=2)
        _, first, _ = self.prepare("first")
        _, second, _ = self.prepare("second")
        self.reserve(first)
        with self.assertRaises(BudgetExceeded):
            self.reserve(second, "dollar-overrun", 1)
        self.reserve(second, "last-free-call", 0)
        with self.assertRaises(BudgetExceeded):
            self.reserve(second, "call-overrun", 0)
        self.assertEqual(self.authority.summary()["operation_count"], 2)

    def test_competing_runs_cannot_allocate_last_slot_twice(self):
        self.path.unlink()
        self.authority = self.create(budget_microusd=100, max_calls=1)
        runs = [self.prepare(name)[0] for name in ("first", "second")]

        def attempt(directory):
            try:
                self.reserve(Authorization(self.path).for_run(directory), directory.name)
                return "reserved"
            except BudgetExceeded:
                return "denied"

        with ThreadPoolExecutor(max_workers=2) as pool:
            self.assertCountEqual(list(pool.map(attempt, runs)), ["reserved", "denied"])
        self.assertEqual(self.authority.summary()["operation_count"], 1)

    def test_same_operation_identity_cannot_be_owned_by_another_run(self):
        _, first, _ = self.prepare("first")
        _, second, _ = self.prepare("second")
        self.reserve(first)
        with self.assertRaises(OperationConflict):
            self.reserve(second)
        self.assertEqual(second.totals()["operation_count"], 0)

    def test_separate_processes_cannot_allocate_the_last_slot_twice(self):
        self.path.unlink()
        self.authority = self.create(budget_microusd=100, max_calls=1)
        runs = [self.prepare(name)[0] for name in ("first", "second")]
        context = multiprocessing.get_context("spawn")
        ready, results, start = context.Queue(), context.Queue(), context.Event()
        processes = [
            context.Process(
                target=reserve_in_process,
                args=(self.path, directory, ready, start, results),
            )
            for directory in runs
        ]
        try:
            for process in processes:
                process.start()
            for _ in processes:
                ready.get(timeout=15)
            start.set()
            self.assertCountEqual(
                [results.get(timeout=15) for _ in processes], ["reserved", "denied"]
            )
            for process in processes:
                process.join(15)
                self.assertEqual(process.exitcode, 0)
        finally:
            for process in processes:
                if process.is_alive():
                    process.terminate()
                    process.join(10)
            ready.close()
            results.close()
        self.assertEqual(self.authority.summary()["operation_count"], 1)

    def test_empty_run_cannot_be_rebound_to_a_second_authority(self):
        directory, ledger, _ = self.prepare("owned")
        other = Authorization.create(
            self.root / "other.sqlite3",
            authorization_id="other",
            budget_microusd=50_000_000,
            max_calls=128,
            scope="other scope",
        )
        before = (directory / "operations.sqlite3").read_bytes()
        with self.assertRaises(ValidationError):
            other.bind_run(directory, runtime_sha256=runtime_fingerprint())
        with self.assertRaises(ValidationError):
            other.for_run(directory)
        self.assertEqual(other.summary()["runs"], [])
        self.assertEqual(before, (directory / "operations.sqlite3").read_bytes())
        self.reserve(ledger)

    def test_binding_extension_and_authority_registration_rollback_together(self):
        directory, _, _ = self.prepare("binding-fault", bind=False)
        import buddha.authorization as module

        original = module._event

        def fault_after_registration(*args, **kwargs):
            original(*args, **kwargs)
            raise RuntimeError("injected bind fault")

        with patch.object(module, "_event", side_effect=fault_after_registration):
            with self.assertRaises(RuntimeError):
                self.authority.bind_run(directory, runtime_sha256=runtime_fingerprint())
        self.assertEqual(self.authority.summary()["runs"], [])
        with closing(sqlite3.connect(directory / "operations.sqlite3")) as connection:
            self.assertIsNone(
                connection.execute(
                    "SELECT 1 FROM sqlite_master WHERE name='authorization_binding'"
                ).fetchone()
            )
        self.authority.bind_run(directory, runtime_sha256=runtime_fingerprint())

    def test_new_unknown_halts_all_runs_but_allows_existing_receipt_truth(self):
        _, first, _ = self.prepare("first")
        _, second, _ = self.prepare("second")
        self.reserve(first)
        self.reserve(second, "already-reserved")
        first.dispatch("operation")
        first.mark_unknown("operation")
        with self.assertRaises(BudgetExceeded):
            self.reserve(second, "new-work")
        with self.assertRaises(BudgetExceeded):
            second.dispatch("already-reserved")
        self.complete(first, "operation")
        self.assertEqual(self.authority.summary()["spent_microusd"], 60)

    def test_outstanding_dispatch_stops_other_work_until_receipt_is_recorded(self):
        _, first, _ = self.prepare("first")
        _, second, _ = self.prepare("second")
        self.reserve(first)
        self.reserve(second, "second-work")
        first.dispatch("operation")
        with self.assertRaises(BudgetExceeded):
            self.reserve(second, "new-work")
        with self.assertRaises(BudgetExceeded):
            second.dispatch("second-work")
        self.complete(first)
        self.assertTrue(second.dispatch("second-work"))

    def test_inactive_run_cannot_reserve_or_dispatch_but_can_record_truth(self):
        _, ledger, _ = self.prepare("inactive")
        self.reserve(ledger)
        self.reserve(ledger, "in-flight")
        ledger.dispatch("in-flight")
        self.authority.deactivate("inactive", "continuation supersedes it")
        with self.assertRaises(ValidationError):
            self.reserve(ledger, "new")
        with self.assertRaises(ValidationError):
            ledger.dispatch("operation")
        self.complete(ledger, "in-flight")
        self.assertEqual(ledger.get("in-flight").status, "completed")

    def test_known_overrun_commits_both_records_before_halting(self):
        _, ledger, _ = self.prepare("overrun")
        self.reserve(ledger)
        ledger.dispatch("operation")
        with self.assertRaises(BudgetExceeded):
            self.complete(ledger, actual=101)
        self.assertEqual(ledger.get("operation").actual_microusd, 101)
        self.assertEqual(self.authority.summary()["spent_microusd"], 101)
        with self.assertRaises(BudgetExceeded):
            self.reserve(ledger, "after-overrun")

    def test_fault_after_both_updates_rolls_back_both_records(self):
        _, ledger, _ = self.prepare("rollback")
        import buddha.authorization as module

        original = module._mirror_operation

        def fail_after_mirror(*args, **kwargs):
            original(*args, **kwargs)
            raise RuntimeError("injected fault after both writes")

        with patch.object(module, "_mirror_operation", side_effect=fail_after_mirror):
            with self.assertRaises(RuntimeError):
                self.reserve(ledger)
        self.assertEqual(ledger.totals()["operation_count"], 0)
        self.assertEqual(self.authority.summary()["operation_count"], 0)
        self.reserve(ledger)

    def test_local_tampering_is_rejected_instead_of_reducing_shared_liability(self):
        directory, ledger, _ = self.prepare("tampered")
        self.reserve(ledger)
        with closing(sqlite3.connect(directory / "operations.sqlite3")) as connection:
            connection.execute("DROP TRIGGER operation_identity_no_update")
            connection.execute("UPDATE operations SET reserve_microusd=1")
            connection.commit()
        with self.assertRaises(ValidationError):
            ledger.dispatch("operation")
        self.assertEqual(self.authority.summary()["reserved_microusd"], 100)

    def test_current_runtime_is_checked_on_execution_not_only_on_binding(self):
        _, ledger, _ = self.prepare("runtime")
        with patch("buddha.authorization.runtime_fingerprint", return_value="a" * 64):
            with self.assertRaises(ValidationError):
                self.reserve(ledger)
        self.assertEqual(self.authority.summary()["operation_count"], 0)

    def test_runtime_drift_in_flight_does_not_discard_received_usage(self):
        _, ledger, _ = self.prepare("runtime-drift")
        self.reserve(ledger)
        ledger.dispatch("operation")
        with patch("buddha.authorization.runtime_fingerprint", return_value="a" * 64):
            self.complete(ledger)
            self.assertEqual(ledger.get("operation").actual_microusd, 60)
            with self.assertRaises(ValidationError):
                self.reserve(ledger, "next-operation")
        self.assertEqual(self.authority.summary()["spent_microusd"], 60)

    def test_manifest_drift_in_flight_does_not_discard_received_usage(self):
        directory, ledger, _ = self.prepare("manifest-drift")
        self.reserve(ledger)
        ledger.dispatch("operation")
        (directory / "manifest.json").write_text("changed during HTTP response")
        self.complete(ledger)
        self.assertEqual(ledger.get("operation").actual_microusd, 60)
        with self.assertRaises(ValidationError):
            self.reserve(ledger, "next-operation")
        self.assertEqual(self.authority.summary()["spent_microusd"], 60)

    def test_drift_in_flight_still_preserves_an_unknown_reservation(self):
        _, ledger, _ = self.prepare("unknown-drift")
        self.reserve(ledger)
        ledger.dispatch("operation")
        with patch("buddha.authorization.runtime_fingerprint", return_value="a" * 64):
            ledger.mark_unknown("operation")
        self.assertEqual(self.authority.summary()["reserved_microusd"], 100)
        self.assertEqual(ledger.get("operation").status, "unknown")

    def test_historical_unknown_requires_exact_explicit_continuation_acceptance(self):
        directory, old, manifest_hash = self.prepare("old", bind=False)
        self.reserve(old)
        old.dispatch("operation")
        old.mark_unknown("operation")
        before = (directory / "operations.sqlite3").read_bytes()
        ledger_hash = self.seal(directory, manifest_hash)
        continuation, first, _ = self.prepare("continuation")
        _, other, _ = self.prepare("unrelated")
        with self.assertRaises(BudgetExceeded):
            self.reserve(first, "replacement")
        self.authority.accept_historical_unknown(
            "old",
            "operation",
            continuation_run_id=continuation.name,
            evidence_sha256=ledger_hash,
            reason="reviewed unknown remains fully held",
        )
        self.reserve(first, "replacement")
        with self.assertRaises(BudgetExceeded):
            self.reserve(other, "unrelated-call")
        with self.assertRaises(ValidationError):
            self.authority.for_run(directory)
        self.assertEqual(self.authority.summary()["reserved_microusd"], 200)
        self.assertEqual(before, (directory / "operations.sqlite3").read_bytes())

    def test_historical_import_is_idempotent_and_preserves_exact_pilot_totals(self):
        for name, count, known, unknown in [
            ("old", 10, 1709, True),
            ("recovery", 63, 300153, False),
        ]:
            directory, ledger, manifest_hash = self.prepare(name, bind=False)
            for index in range(count):
                operation = name + str(index)
                ledger.reserve(operation, sha(operation), 532373)
                ledger.dispatch(operation)
                if unknown and index == count - 1:
                    ledger.mark_unknown(operation)
                else:
                    self.complete(ledger, operation, known if index == 0 else 0)
            before = (directory / "operations.sqlite3").read_bytes()
            self.seal(directory, manifest_hash)
            events = self.authority.summary()["event_count"]
            self.seal(directory, manifest_hash)
            self.assertEqual(self.authority.summary()["event_count"], events)
            self.assertEqual(before, (directory / "operations.sqlite3").read_bytes())
        summary = self.authority.summary()
        self.assertEqual(summary["spent_microusd"], 301862)
        self.assertEqual(summary["reserved_microusd"], 532373)
        self.assertEqual(summary["available_microusd"], 49165765)
        self.assertEqual(summary["remaining_calls"], 55)

    def test_unknown_received_billing_evidence_is_preserved_and_cannot_be_whitelisted(self):
        directory, old, manifest_hash = self.prepare("old", bind=False)
        self.reserve(old)
        old.dispatch("operation")
        reply = Reply("uncertain", "unexpected-model", "receipt", 1, 2, "stop")
        old.mark_unknown("operation", response=reply.to_record(), provider_request_id="receipt")
        ledger_hash = self.seal(directory, manifest_hash)
        self.prepare("continuation")
        with self.assertRaises(ValidationError):
            self.authority.accept_historical_unknown(
                "old",
                "operation",
                continuation_run_id="continuation",
                evidence_sha256=ledger_hash,
                reason="must not waive uncertain pricing",
            )
        with closing(sqlite3.connect(self.path)) as connection:
            saved = connection.execute(
                "SELECT response_json,provider_request_id FROM auth_operations "
                "WHERE run_id='old' AND operation_id='operation'"
            ).fetchone()
        self.assertIn("unexpected-model", saved[0])
        self.assertEqual(saved[1], "receipt")
        self.assertEqual(self.authority.summary()["reserved_microusd"], 100)

    def test_wal_and_foreign_authorities_are_rejected(self):
        with closing(sqlite3.connect(self.path)) as connection:
            connection.execute("PRAGMA journal_mode=WAL")
        with self.assertRaises(ValidationError):
            Authorization(self.path)
        self.path.unlink()
        with closing(sqlite3.connect(self.path)) as connection:
            connection.execute("CREATE TABLE foreign_data(value)")
            connection.execute("PRAGMA user_version=1")
        with self.assertRaises(ValidationError):
            Authorization(self.path)

    def test_active_run_wal_and_authority_alias_are_rejected(self):
        directory, ledger, _ = self.prepare("wal")
        with closing(sqlite3.connect(directory / "operations.sqlite3")) as connection:
            connection.execute("PRAGMA journal_mode=WAL")
        with self.assertRaises(ValidationError):
            self.reserve(ledger)
        with self.assertRaises(ValidationError):
            self.authority.bind_run(self.root, runtime_sha256=runtime_fingerprint())


if __name__ == "__main__":
    unittest.main()
