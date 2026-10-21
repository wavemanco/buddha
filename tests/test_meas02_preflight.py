"""Native audit preflight rejects known stops before credentials or execution."""

import hashlib
import unittest
from datetime import UTC, datetime, timedelta
from pathlib import Path
from unittest.mock import patch

import test_meas02_native_audit as fixtures

from buddha.authorization import Authorization, AuthorizedLedger
from buddha.gateway import Gateway, RawHTTPTransport
from buddha.provider import ModelSpec


class NativeAuditPreflightTests(unittest.TestCase):
    def setUp(self):
        self.fixture = fixtures.NativeAuditTests("runTest")
        self.fixture.setUp()
        self.addCleanup(self.fixture.doCleanups)

    def configure(self, *, local_budget=100_000, shared_budget=100_000, local_calls=20, calls=20):
        fixture = self.fixture
        fixture.record["native"].update(budget_microusd=local_budget, max_calls=local_calls)
        fixture.authority = Authorization.create(
            fixture.root / "preflight-authorization.sqlite3",
            authorization_id="synthetic-preflight-only",
            budget_microusd=shared_budget,
            max_calls=calls,
            scope="ephemeral preflight checks, no provider calls or real allocation",
        )
        fixture.prepare()

    def gateway(self, index=0):
        return Gateway(
            self.fixture.directory / "owners" / str(index),
            transport=RawHTTPTransport(allow_paid=False),
        )

    def check(self):
        def forbidden(*args, **kwargs):
            raise AssertionError("preflight prompted, read a key or executed a request/container")

        with (
            patch("os.environ.get", side_effect=forbidden),
            patch("getpass.getpass", side_effect=forbidden),
            patch("http.client.HTTPSConnection", side_effect=forbidden),
            patch("socket.create_connection", side_effect=forbidden),
            patch("buddha.gateway.RawHTTPTransport.prepare", side_effect=forbidden),
            patch("buddha.gateway.RawHTTPTransport.send_prepared", side_effect=forbidden),
            patch("buddha.native_run.NativeSession.run", side_effect=forbidden),
            patch("buddha.executor.run_container", side_effect=forbidden),
        ):
            return fixtures.audit.check_native_audit(self.fixture.directory)

    def snapshot(self):
        directory = self.fixture.directory
        return {
            str(path.relative_to(directory)): hashlib.sha256(path.read_bytes()).hexdigest()
            for path in directory.rglob("*")
            if path.is_file()
        } | {"authority": hashlib.sha256(self.fixture.authority.path.read_bytes()).hexdigest()}

    def test_fresh_state_reports_original_profile_without_keys_or_mutation(self):
        self.fixture.prepare()
        before = self.snapshot()
        result = self.check()
        self.assertEqual(result["status"], "ready")
        self.assertEqual((result["next_batch"], result["next_occasion"]), (0, "baseline"))
        self.assertEqual(Path(result["authorization_path"]), self.fixture.authority.path)
        self.assertEqual(result["review"], self.fixture.fixture.review)
        self.assertEqual(
            result["credential_sha256"], self.fixture.fixture.review["credential_sha256"]
        )
        self.assertTrue(result["profiles"])
        self.assertTrue(all(isinstance(profile, ModelSpec) for profile in result["profiles"]))
        self.assertEqual(result["profiles"][0], self.fixture.fixture.spec)
        self.assertEqual(self.snapshot(), before)
        result["review"]["credential_sha256"].clear()
        self.assertEqual(self.check()["review"], self.fixture.fixture.review)

    def test_local_maximum_reservation_must_fit_when_no_unsent_hold_exists(self):
        maximum = self.fixture.fixture.spec.reserve_microusd()
        self.configure(local_budget=maximum - 1)
        with self.assertRaises(fixtures.audit.NativeAuditError):
            self.check()
        self.assertEqual(self.fixture.authority.summary()["operation_count"], 0)

    def test_shared_maximum_reservation_must_fit_when_no_unsent_hold_exists(self):
        maximum = self.fixture.fixture.spec.reserve_microusd()
        self.configure(shared_budget=maximum - 1)
        with self.assertRaises(fixtures.audit.NativeAuditError):
            self.check()
        self.assertEqual(self.fixture.authority.summary()["operation_count"], 0)

    def test_exact_maximum_is_potentially_fundable_without_completion_guarantee(self):
        maximum = self.fixture.fixture.spec.reserve_microusd()
        self.configure(local_budget=maximum, shared_budget=maximum)
        self.assertEqual(self.check()["status"], "ready")
        self.assertEqual(self.fixture.authority.summary()["operation_count"], 0)

    def test_another_owners_hold_cannot_evade_shared_physical_cap(self):
        self.configure(calls=1)
        self.gateway(1).ledger.reserve("other-owner-unsent", "0" * 64, 1)
        with self.assertRaises(fixtures.audit.NativeAuditError):
            self.check()
        self.assertEqual(self.fixture.authority.summary()["remaining_calls"], 0)

    def test_exhausted_local_physical_cap_is_rejected_without_new_hold(self):
        self.configure(local_calls=1)
        ledger = self.gateway().ledger
        ledger.reserve("completed-synthetic", "0" * 64, 1)
        ledger.dispatch("completed-synthetic")
        ledger.complete(
            "completed-synthetic",
            actual_microusd=1,
            response={"synthetic": "preflight fixture only"},
            provider_request_id="synthetic-completed",
        )
        with self.assertRaises(fixtures.audit.NativeAuditError):
            self.check()

    def test_own_unsent_hold_allows_potential_reuse_at_zero_new_capacity(self):
        maximum = self.fixture.fixture.spec.reserve_microusd()
        self.configure(local_budget=maximum, shared_budget=maximum, local_calls=1, calls=1)
        ledger = self.gateway().ledger
        ledger.reserve("potential-own-unsent-reuse", "0" * 64, maximum)
        before = self.snapshot()
        self.assertEqual(self.fixture.authority.summary()["available_microusd"], 0)
        self.assertEqual(self.fixture.authority.summary()["remaining_calls"], 0)
        self.assertEqual(self.check()["status"], "ready")
        self.assertEqual(self.snapshot(), before)
        self.assertEqual(ledger.get("potential-own-unsent-reuse").status, "reserved")

    def test_tiny_own_hold_cannot_cover_the_minimum_native_reservation(self):
        self.configure(local_budget=1, shared_budget=1, local_calls=1, calls=1)
        self.gateway().ledger.reserve("too-small-unsent", "0" * 64, 1)
        before = self.snapshot()
        with self.assertRaises(fixtures.audit.NativeAuditError):
            self.check()
        self.assertEqual(self.snapshot(), before)

    def test_future_inactive_unsealed_owner_stops_check_and_run_before_keys_or_sends(self):
        self.fixture.prepare()
        owner = self.gateway(3)
        self.fixture.authority.deactivate(owner.ledger.run_id, "synthetic manual stop")
        with self.subTest(entry="check"):
            with self.assertRaises(fixtures.audit.NativeAuditError):
                self.check()
        with self.subTest(entry="run"):
            with self.assertRaises(fixtures.audit.NativeAuditError):
                self.fixture.run_study()
        self.assertEqual(self.fixture.connection.request.call_count, 0)

    def test_unknown_hold_stops_preflight_even_if_totals_have_capacity(self):
        self.fixture.prepare()
        ledger = self.gateway().ledger
        ledger.reserve("unknown-synthetic", "0" * 64, 1)
        ledger.dispatch("unknown-synthetic")
        ledger.mark_unknown("unknown-synthetic")
        before = self.snapshot()
        with self.assertRaises(fixtures.audit.NativeAuditError):
            self.check()
        self.assertEqual(self.snapshot(), before)

    def test_outdated_review_stops_unfinished_work_before_keys(self):
        self.fixture.prepare()
        future = datetime.now(UTC) + timedelta(days=10)
        with patch("buddha.gateway.datetime") as clock:
            clock.now.return_value = future
            with self.assertRaises(fixtures.audit.NativeAuditError):
                self.check()

    def test_complete_state_uses_no_dispatch_guard_or_fresh_review(self):
        self.fixture.prepare()
        self.fixture.run_study()
        before = self.snapshot()
        with (
            patch.object(
                AuthorizedLedger,
                "authorize_dispatch",
                side_effect=AssertionError("completed inactive owner must not dispatch"),
            ),
            patch("buddha.gateway.datetime") as clock,
        ):
            clock.now.return_value = datetime.now(UTC) + timedelta(days=10)
            result = self.check()
        self.assertEqual(result["status"], "complete")
        self.assertIsNone(result["next_batch"])
        self.assertIsNone(result["next_occasion"])
        self.assertEqual(self.snapshot(), before)

    def test_preflight_is_not_authority_to_use_sources_changed_after_check(self):
        self.fixture.prepare()
        self.assertEqual(self.check()["status"], "ready")
        target = self.fixture.directory / "targets.json"
        original = target.read_bytes()
        target.write_bytes(original + b"\n")
        with self.assertRaises(fixtures.audit.NativeAuditError):
            self.fixture.run_study()
        self.assertEqual(self.fixture.connection.request.call_count, 0)

    def test_partial_study_reports_original_next_owner_and_occasion(self):
        self.fixture.prepare()
        self.fixture.failure_once = True
        with self.assertRaises(RuntimeError):
            self.fixture.run_study()
        result = self.check()
        self.assertEqual(result["status"], "ready")
        self.assertEqual((result["next_batch"], result["next_occasion"]), (1, "same-order-repeat"))


if __name__ == "__main__":
    unittest.main()
