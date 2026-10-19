"""Paid-operation invariants using local SQLite only; no provider calls."""

import hashlib
import json
import sqlite3
import tempfile
import unittest
from concurrent.futures import ThreadPoolExecutor
from contextlib import closing
from dataclasses import FrozenInstanceError
from pathlib import Path

from buddha.evaluation import ValidationError
from buddha.ledger import BudgetExceeded, Ledger, OperationConflict, UnknownOperation


def digest(text):
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


class LedgerTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.path = Path(temporary.name) / "run.sqlite3"

    def ledger(self, **changes):
        config = {
            "run_id": "run-1",
            "manifest_sha256": digest("immutable manifest"),
            "budget_microusd": 1000,
            "max_calls": 10,
        }
        config.update(changes)
        return Ledger(self.path, **config)

    def reserve(self, ledger, operation_id="operation-1", amount=100):
        return ledger.reserve(operation_id, digest(operation_id), amount)

    def complete(self, ledger, operation_id="operation-1", cost=60, **changes):
        values = {
            "response": {"answer": "durable answer", "usage": {"tokens": 5}},
            "actual_microusd": cost,
            "provider_request_id": "provider-1",
        }
        values.update(changes)
        return ledger.complete(operation_id, **values)

    def test_new_ledger_has_zero_totals_and_versioned_schema(self):
        ledger = self.ledger()
        self.assertEqual(
            ledger.totals(),
            {
                "committed_microusd": 0,
                "spent_microusd": 0,
                "reserved_microusd": 0,
                "operation_count": 0,
            },
        )
        with closing(sqlite3.connect(self.path)) as connection, connection:
            self.assertEqual(connection.execute("PRAGMA user_version").fetchone()[0], 2)

    def test_reservation_and_completion_account_for_true_cost(self):
        ledger = self.ledger()
        operation = self.reserve(ledger)
        self.assertEqual(operation.status, "reserved")
        self.assertIsNone(operation.response)
        self.assertIsNone(operation.actual_microusd)
        self.assertIsNone(operation.provider_request_id)
        self.assertEqual(ledger.totals()["committed_microusd"], 100)
        self.assertTrue(ledger.dispatch(operation.operation_id))
        completed = self.complete(ledger)
        self.assertEqual(completed.status, "completed")
        self.assertEqual(completed.actual_microusd, 60)
        self.assertEqual(completed.provider_request_id, "provider-1")
        self.assertEqual(
            ledger.totals(),
            {
                "committed_microusd": 60,
                "spent_microusd": 60,
                "reserved_microusd": 0,
                "operation_count": 1,
            },
        )

    def test_reservation_replay_is_idempotent_at_the_cap(self):
        ledger = self.ledger(budget_microusd=100, max_calls=1)
        first = self.reserve(ledger)
        event_count = len(ledger.events())
        self.assertEqual(self.reserve(ledger), first)
        self.assertEqual(len(ledger.events()), event_count)
        self.assertEqual(ledger.totals()["operation_count"], 1)
        for request_hash, amount in [(digest("different"), 100), (digest("operation-1"), 99)]:
            with self.subTest(request_hash=request_hash, amount=amount):
                with self.assertRaises(OperationConflict):
                    ledger.reserve("operation-1", request_hash, amount)

    def test_call_and_dollar_caps_are_independent(self):
        ledger = self.ledger(budget_microusd=100, max_calls=2)
        self.reserve(ledger)
        with self.assertRaises(BudgetExceeded):
            self.reserve(ledger, "over-dollars", 1)
        self.reserve(ledger, "zero-cost", 0)
        with self.assertRaises(BudgetExceeded):
            self.reserve(ledger, "over-calls", 0)
        self.assertEqual(ledger.totals()["operation_count"], 2)

    def test_zero_caps_disable_the_corresponding_resource(self):
        ledger = self.ledger(budget_microusd=0, max_calls=0)
        with self.assertRaises(BudgetExceeded):
            self.reserve(ledger, amount=0)
        second_path = self.path.with_name("zero-dollar.sqlite3")
        zero_dollar = Ledger(
            second_path,
            run_id="free",
            manifest_sha256=digest("free"),
            budget_microusd=0,
            max_calls=1,
        )
        with self.assertRaises(BudgetExceeded):
            self.reserve(zero_dollar, amount=1)
        self.reserve(zero_dollar, amount=0)

    def test_invalid_configuration_fails_before_creating_a_database(self):
        cases = {
            "run_id": ["", " \t", None, 3],
            "manifest_sha256": ["", "g" * 64, "a" * 63, None],
            "budget_microusd": [-1, True, 0.5, 1 << 63],
            "max_calls": [-1, True, 0.5, 1 << 63],
        }
        for field, values in cases.items():
            for value in values:
                with self.subTest(field=field, value=value):
                    with self.assertRaises(ValidationError):
                        self.ledger(**{field: value})
                    self.assertFalse(self.path.exists())

    def test_invalid_or_ephemeral_paths_have_typed_errors(self):
        for path in ["", ":memory:", True, None, "bad\x00file"]:
            with self.subTest(path=path):
                with self.assertRaises(ValidationError):
                    Ledger(
                        path,
                        run_id="run",
                        manifest_sha256=digest("manifest"),
                        budget_microusd=1,
                        max_calls=1,
                    )

    def test_invalid_reservations_do_not_change_totals(self):
        ledger = self.ledger()
        for operation_id, request_hash, amount in [
            ("", digest("x"), 1),
            (True, digest("x"), 1),
            ("x", "invalid", 1),
            ("x", digest("x"), -1),
            ("x", digest("x"), True),
            ("x", digest("x"), 0.5),
            ("x", digest("x"), 1 << 63),
        ]:
            with self.subTest(operation_id=operation_id, amount=amount):
                with self.assertRaises(ValidationError):
                    ledger.reserve(operation_id, request_hash, amount)
        self.assertEqual(ledger.totals()["operation_count"], 0)

    def test_reopening_requires_exact_immutable_run_configuration(self):
        ledger = self.ledger()
        self.reserve(ledger)
        event_count = len(ledger.events())
        self.assertEqual(self.ledger().totals(), ledger.totals())
        self.assertEqual(len(self.ledger().events()), event_count)
        for changes in [
            {"run_id": "another"},
            {"manifest_sha256": digest("another")},
            {"budget_microusd": 2000},
            {"max_calls": 20},
        ]:
            with self.subTest(changes=changes):
                with self.assertRaises(OperationConflict):
                    self.ledger(**changes)

    def test_unknown_schema_and_unowned_database_are_rejected(self):
        with closing(sqlite3.connect(self.path)) as connection, connection:
            connection.execute("PRAGMA user_version=99")
        with self.assertRaises(ValidationError):
            self.ledger()
        other_path = self.path.with_name("foreign.sqlite3")
        with closing(sqlite3.connect(other_path)) as connection, connection:
            connection.execute("CREATE TABLE existing_data(value TEXT)")
        with self.assertRaises(ValidationError):
            Ledger(
                other_path, run_id="x", manifest_sha256=digest("x"), budget_microusd=1, max_calls=1
            )

    def test_dispatch_claim_is_exactly_once(self):
        ledger = self.ledger()
        self.reserve(ledger)
        self.assertTrue(ledger.dispatch("operation-1"))
        self.assertFalse(ledger.dispatch("operation-1"))
        self.assertFalse(self.ledger().dispatch("operation-1"))
        self.assertEqual(ledger.get("operation-1").status, "dispatched")
        self.assertEqual(ledger.totals()["reserved_microusd"], 100)

    def test_unknown_operations_have_typed_errors(self):
        ledger = self.ledger()
        self.assertIsNone(ledger.get("missing"))
        for action in [
            lambda: ledger.dispatch("missing"),
            lambda: ledger.mark_unknown("missing"),
            lambda: self.complete(ledger, "missing"),
        ]:
            with self.subTest(action=action):
                with self.assertRaises(UnknownOperation):
                    action()

    def test_unknown_and_dispatched_exposure_is_held_across_reopen(self):
        ledger = self.ledger(budget_microusd=100, max_calls=2)
        self.reserve(ledger)
        ledger.dispatch("operation-1")
        ledger.mark_unknown("operation-1")
        event_count = len(ledger.events())
        ledger.mark_unknown("operation-1")
        self.assertEqual(len(ledger.events()), event_count)
        resumed = self.ledger(budget_microusd=100, max_calls=2)
        self.assertEqual(resumed.get("operation-1").status, "unknown")
        self.assertFalse(resumed.dispatch("operation-1"))
        with self.assertRaises(BudgetExceeded):
            self.reserve(resumed, "unsafe-retry", 1)
        self.complete(resumed)
        self.assertEqual(resumed.totals()["spent_microusd"], 60)

    def test_unknown_receipt_preserves_evidence_without_guessing_a_charge(self):
        ledger = self.ledger()
        self.reserve(ledger)
        ledger.dispatch("operation-1")
        receipt = {"text": "PRIVATE_UNKNOWN_RECEIPT", "usage": {"tokens": 5}, "tier": "other"}
        ledger.mark_unknown("operation-1", response=receipt, provider_request_id=None)
        receipt["usage"]["tokens"] = 999
        operation = self.ledger().get("operation-1")
        self.assertEqual(operation.status, "unknown")
        self.assertIsNone(operation.actual_microusd)
        self.assertIsNone(operation.provider_request_id)
        self.assertEqual(operation.response["usage"], {"tokens": 5})
        operation.response["usage"]["tokens"] = 222
        self.assertEqual(ledger.get("operation-1").response["usage"], {"tokens": 5})
        self.assertEqual(ledger.totals()["reserved_microusd"], 100)
        self.assertEqual(ledger.totals()["spent_microusd"], 0)
        self.assertNotIn("PRIVATE_UNKNOWN_RECEIPT", json.dumps(ledger.events()))
        completed = self.complete(ledger, response={"reconciled": True})
        self.assertEqual(completed.status, "completed")
        self.assertEqual(completed.response, {"reconciled": True})
        self.assertEqual(completed.provider_request_id, "provider-1")
        self.assertEqual(ledger.totals()["spent_microusd"], 60)

    def test_unreconciled_receipt_stops_new_and_reserved_unsent_work(self):
        ledger = self.ledger()
        self.reserve(ledger)
        self.reserve(ledger, "operation-2", 10)
        ledger.dispatch("operation-1")
        ledger.mark_unknown("operation-1", response={"model": "unexpected"})
        with self.assertRaises(BudgetExceeded):
            self.reserve(ledger, "operation-3", 10)
        with self.assertRaises(BudgetExceeded):
            ledger.dispatch("operation-2")
        self.complete(ledger, response={"reconciled": True})
        self.assertTrue(ledger.dispatch("operation-2"))

    def test_unknown_receipt_is_idempotent_and_cannot_be_overwritten(self):
        ledger = self.ledger()
        self.reserve(ledger)
        ledger.dispatch("operation-1")
        receipt = {"usage": 5}
        ledger.mark_unknown("operation-1", response=receipt, provider_request_id="req-unknown")
        event_count = len(ledger.events())
        ledger.mark_unknown("operation-1")
        ledger.mark_unknown("operation-1", response=receipt, provider_request_id="req-unknown")
        self.assertEqual(len(ledger.events()), event_count)
        for changes in [
            {"response": {"usage": 6}, "provider_request_id": "req-unknown"},
            {"response": receipt, "provider_request_id": "another-request"},
        ]:
            with self.subTest(changes=changes), self.assertRaises(OperationConflict):
                ledger.mark_unknown("operation-1", **changes)
        with closing(sqlite3.connect(self.path)) as connection, connection:
            for sql in [
                "DELETE FROM unknown_receipts",
                "UPDATE unknown_receipts SET response_json='{}'",
            ]:
                with self.subTest(sql=sql), self.assertRaises(sqlite3.IntegrityError):
                    connection.execute(sql)

    def test_unknown_without_receipt_can_later_record_one(self):
        ledger = self.ledger()
        self.reserve(ledger)
        ledger.dispatch("operation-1")
        ledger.mark_unknown("operation-1")
        ledger.mark_unknown("operation-1", response={"usage": 5}, provider_request_id="req-later")
        self.assertEqual(ledger.get("operation-1").response, {"usage": 5})
        self.assertEqual(ledger.get("operation-1").provider_request_id, "req-later")
        self.assertEqual(ledger.totals()["reserved_microusd"], 100)

    def rollback_empty_receipts(self):
        # The guarded rollback path documented in ledger.py; no paid data is removed.
        with closing(sqlite3.connect(self.path)) as connection, connection:
            connection.execute("BEGIN IMMEDIATE")
            if connection.execute("SELECT COUNT(*) FROM unknown_receipts").fetchone()[0]:
                raise ValidationError("cannot roll back a schema containing unknown receipts")
            connection.execute("DROP TABLE unknown_receipts")
            connection.execute("PRAGMA user_version=1")

    def test_schema_one_two_empty_rollback_two_preserves_existing_operations(self):
        ledger = self.ledger()
        self.reserve(ledger)
        ledger.dispatch("operation-1")
        ledger.mark_unknown("operation-1")
        totals = ledger.totals()
        events = ledger.events()
        self.rollback_empty_receipts()
        with closing(sqlite3.connect(self.path)) as connection, connection:
            self.assertEqual(connection.execute("PRAGMA user_version").fetchone()[0], 1)
        migrated = self.ledger()
        self.assertEqual(migrated.get("operation-1").status, "unknown")
        self.assertEqual(migrated.totals(), totals)
        self.assertEqual(migrated.events(), events)
        with closing(sqlite3.connect(self.path)) as connection, connection:
            self.assertEqual(connection.execute("PRAGMA user_version").fetchone()[0], 2)

    def test_schema_rollback_refuses_to_remove_any_receipt(self):
        ledger = self.ledger()
        self.reserve(ledger)
        ledger.dispatch("operation-1")
        ledger.mark_unknown("operation-1", response={"usage": 5})
        with self.assertRaises(ValidationError):
            self.rollback_empty_receipts()
        self.assertEqual(self.ledger().get("operation-1").response, {"usage": 5})

    def test_invalid_state_transitions_are_rejected(self):
        ledger = self.ledger()
        self.reserve(ledger)
        with self.assertRaises(OperationConflict):
            self.complete(ledger)
        with self.assertRaises(OperationConflict):
            ledger.mark_unknown("operation-1")
        ledger.dispatch("operation-1")
        self.complete(ledger)
        self.assertFalse(ledger.dispatch("operation-1"))
        with self.assertRaises(OperationConflict):
            ledger.mark_unknown("operation-1")

    def test_terminal_completion_replay_is_exact_and_conflicts_fail(self):
        ledger = self.ledger()
        self.reserve(ledger)
        ledger.dispatch("operation-1")
        completed = self.complete(ledger)
        event_count = len(ledger.events())
        self.assertEqual(self.complete(self.ledger()), completed)
        self.assertEqual(len(ledger.events()), event_count)
        for changes in [
            {"actual_microusd": 61},
            {"response": {"answer": "different"}},
            {"provider_request_id": "provider-2"},
        ]:
            with self.subTest(changes=changes):
                with self.assertRaises(OperationConflict):
                    self.complete(ledger, **changes)

    def test_response_objects_are_detached_from_durable_state(self):
        ledger = self.ledger()
        self.reserve(ledger)
        ledger.dispatch("operation-1")
        response = {"choices": [{"text": "original"}]}
        operation = self.complete(ledger, response=response)
        response["choices"][0]["text"] = "changed original input"
        operation.response["choices"][0]["text"] = "changed returned object"
        self.assertEqual(
            ledger.get("operation-1").response,
            {"choices": [{"text": "original"}]},
        )
        with self.assertRaises((FrozenInstanceError, AttributeError)):
            operation.status = "reserved"

    def test_completion_validates_json_money_and_provider_identity(self):
        ledger = self.ledger()
        self.reserve(ledger)
        ledger.dispatch("operation-1")
        for changes in [
            {"actual_microusd": -1},
            {"actual_microusd": True},
            {"actual_microusd": 1.5},
            {"actual_microusd": 1 << 63},
            {"provider_request_id": ""},
            {"response": []},
            {"response": {"nonfinite": float("nan")}},
            {"response": {"not_json": object()}},
            {"response": {1: "nonstring-key"}},
        ]:
            with self.subTest(changes=changes):
                with self.assertRaises(ValidationError):
                    self.complete(ledger, **changes)
        self.assertEqual(ledger.get("operation-1").status, "dispatched")
        self.assertEqual(ledger.totals()["spent_microusd"], 0)

    def test_overrun_is_durable_and_blocks_subsequent_spending(self):
        ledger = self.ledger(budget_microusd=100, max_calls=10)
        self.reserve(ledger)
        ledger.dispatch("operation-1")
        with self.assertRaises(BudgetExceeded):
            self.complete(ledger, cost=150)
        completed = ledger.get("operation-1")
        self.assertEqual(completed.status, "completed")
        self.assertEqual(completed.actual_microusd, 150)
        self.assertEqual(completed.response["answer"], "durable answer")
        self.assertEqual(ledger.totals()["committed_microusd"], 150)
        self.assertEqual(ledger.totals()["reserved_microusd"], 0)
        self.assertEqual(self.complete(ledger, cost=150), completed)
        resumed = self.ledger(budget_microusd=100, max_calls=10)
        with self.assertRaises(BudgetExceeded):
            self.reserve(resumed, "after-overrun", 0)

    def test_reservation_overrun_stops_spend_even_below_total_dollar_cap(self):
        ledger = self.ledger()
        self.reserve(ledger, amount=10)
        ledger.dispatch("operation-1")
        with self.assertRaises(BudgetExceeded):
            self.complete(ledger, cost=11)
        with self.assertRaises(BudgetExceeded):
            self.reserve(ledger, "after-reservation-overrun", 1)

    def test_reservation_overrun_blocks_already_reserved_unsent_work(self):
        ledger = self.ledger()
        self.reserve(ledger, "first", 10)
        self.reserve(ledger, "second", 10)
        ledger.dispatch("first")
        with self.assertRaises(BudgetExceeded):
            self.complete(ledger, "first", cost=11)
        with self.assertRaises(BudgetExceeded):
            self.ledger().dispatch("second")
        self.assertEqual(ledger.get("second").status, "reserved")

    def test_exact_integer_totals_survive_combined_cost_above_sqlite_sum_range(self):
        maximum = (1 << 63) - 1
        ledger = self.ledger(budget_microusd=maximum, max_calls=2)
        for operation_id in ["first", "second"]:
            self.reserve(ledger, operation_id, 0)
            ledger.dispatch(operation_id)
        for operation_id in ["first", "second"]:
            with self.assertRaises(BudgetExceeded):
                self.complete(ledger, operation_id, cost=maximum)
        self.assertEqual(ledger.totals()["spent_microusd"], 2 * maximum)

    def test_events_contain_metadata_and_are_append_only(self):
        ledger = self.ledger()
        self.reserve(ledger)
        ledger.dispatch("operation-1")
        self.complete(ledger, response={"answer": "PRIVATE_RESPONSE_MARKER"})
        events = ledger.events()
        self.assertNotIn("PRIVATE_RESPONSE_MARKER", json.dumps(events))
        self.assertEqual(len({event["event_id"] for event in events}), len(events))
        with closing(sqlite3.connect(self.path)) as connection, connection:
            with self.assertRaises(sqlite3.IntegrityError):
                connection.execute("DELETE FROM events")
            with self.assertRaises(sqlite3.IntegrityError):
                connection.execute("UPDATE events SET event_type='rewritten'")
        self.assertEqual(ledger.events(), events)

    def test_reservation_and_its_event_commit_atomically(self):
        ledger = self.ledger()
        with closing(sqlite3.connect(self.path)) as connection, connection:
            connection.execute("""CREATE TRIGGER fail_reservation_event BEFORE INSERT ON events
                WHEN NEW.event_type='reserved' BEGIN
                SELECT RAISE(ABORT, 'injected event failure'); END""")
        original_events = ledger.events()
        with self.assertRaises(ValidationError):
            self.reserve(ledger)
        self.assertIsNone(ledger.get("operation-1"))
        self.assertEqual(ledger.totals()["operation_count"], 0)
        self.assertEqual(ledger.events(), original_events)

    def test_completion_and_its_event_commit_atomically(self):
        ledger = self.ledger()
        self.reserve(ledger)
        ledger.dispatch("operation-1")
        with closing(sqlite3.connect(self.path)) as connection, connection:
            connection.execute("""CREATE TRIGGER fail_completion_event BEFORE INSERT ON events
                WHEN NEW.event_type='completed' BEGIN
                SELECT RAISE(ABORT, 'injected event failure'); END""")
        with self.assertRaises(ValidationError):
            self.complete(ledger)
        self.assertEqual(ledger.get("operation-1").status, "dispatched")
        self.assertEqual(ledger.totals()["reserved_microusd"], 100)
        self.assertEqual(ledger.totals()["spent_microusd"], 0)

    def test_independent_connections_cannot_overspend_concurrently(self):
        self.ledger(max_calls=100)

        def reserve_one(index):
            ledger = self.ledger(max_calls=100)
            try:
                self.reserve(ledger, f"parallel-{index}", 100)
                return True
            except BudgetExceeded:
                return False

        with ThreadPoolExecutor(max_workers=12) as pool:
            accepted = list(pool.map(reserve_one, range(30)))
        self.assertEqual(sum(accepted), 10)
        self.assertEqual(self.ledger(max_calls=100).totals()["committed_microusd"], 1000)

    def test_independent_connections_cannot_exceed_call_cap_concurrently(self):
        self.ledger(max_calls=3)

        def reserve_one(index):
            ledger = self.ledger(max_calls=3)
            try:
                self.reserve(ledger, f"parallel-{index}", 0)
                return True
            except BudgetExceeded:
                return False

        with ThreadPoolExecutor(max_workers=8) as pool:
            accepted = list(pool.map(reserve_one, range(16)))
        self.assertEqual(sum(accepted), 3)

    def test_independent_connections_claim_one_dispatch_concurrently(self):
        ledger = self.ledger()
        self.reserve(ledger)

        def dispatch_one(_index):
            return self.ledger().dispatch("operation-1")

        with ThreadPoolExecutor(max_workers=8) as pool:
            claimed = list(pool.map(dispatch_one, range(16)))
        self.assertEqual(sum(claimed), 1)


if __name__ == "__main__":
    unittest.main()
