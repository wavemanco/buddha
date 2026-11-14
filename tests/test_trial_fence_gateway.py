"""A direct paid Gateway owns the trial through send and original settlement."""

import hashlib
import json
import threading
import unittest
from dataclasses import asdict, replace
from unittest.mock import Mock, patch

from test_trial_fence import TrialFixture

from buddha import authorization, gateway, trial_fence
from buddha.common import ValidationError
from buddha.ledger import BudgetExceeded, OperationConflict
from buddha.provider import ProviderUncertain
from buddha.releases import Release, prepare_selection


class TrialFenceGatewayTests(unittest.TestCase):
    def test_reviewed_503_replacement_is_atomic_and_never_redispatched(self):
        for outcome in ("success", "second_503", "owner_cap"):
            with self.subTest(outcome=outcome):
                self._check_held_replacement(outcome)

    def _check_held_replacement(self, outcome):
        fixture = TrialFixture(self)
        host = fixture.h
        capability = "anthropic.messages.v1"
        key = "anthropic-disposable-test-key-never-real"
        spec = replace(host.spec, provider="anthropic", model="test-claude")
        if outcome == "owner_cap":
            spec = replace(spec, input_microusd_per_million=60_000_000)
        profile = {
            "spec": asdict(spec),
            "response_models": ["test-claude"],
            "request_tiers": ["auto", "standard_only"],
            "response_tiers": ["", "standard"],
            "allow_omitted_tier": True,
            "headers": {"x-stainless-retry-count": ["0", "1"]},
            "account_headers": {},
        }
        host.write(
            "host",
            "profiles/anthropic.json",
            json.dumps({"format": "buddha.gateway-profiles.v2", "profiles": {"primary": profile}}),
        )
        release = Release.from_record(host.release_record | {"requires": [capability]})
        host.selection = prepare_selection(
            release, host.roots, capabilities={capability: "profiles/anthropic.json"}
        )
        success = outcome == "success"
        context = "d" * 64
        if success:
            del host.review["credential_sha256"]
            host.review.update(
                format="buddha.account-review.v2",
                credential_context=context,
                credential_fingerprints={
                    "anthropic": gateway._credential_fingerprint("anthropic", key, context)
                },
            )
        else:
            host.review["credential_sha256"] = {
                "anthropic": hashlib.sha256(key.encode()).hexdigest()
            }
        relative = "study/cells/0/0/0/0/screen/tasks/0/evaluation/owners/2"
        directory = fixture.root / "search" / relative
        directory.parent.mkdir(parents=True)
        fixture.prepare(relative)
        owner = host.gateway(directory=directory)
        call = gateway.GatewayCall(
            capability,
            "primary",
            "a" * 64,
            0,
            b'{"model":"test-claude","messages":[{"role":"user","content":"literal"}],"max_tokens":10}',
            (("x-stainless-retry-count", "0"),),
        )
        unavailable = Mock(status=503)
        unavailable.getheaders.return_value = [("request-id", "original-503")]
        unavailable.read.return_value = b"service unavailable"
        original_connection = host.connection(unavailable)
        with (
            patch.dict("os.environ", {"ANTHROPIC_API_KEY": key}, clear=True),
            patch("http.client.HTTPSConnection", return_value=original_connection),
            self.assertRaises(ProviderUncertain),
        ):
            owner.execute(call)
        original_connection.request.assert_called_once()
        decision = owner._held_replacement_candidate(owner.operation_id(call), "b" * 64)
        original = owner.ledger.get(decision.original_operation_id)
        authority = fixture.authorities["search"]
        before = authority.summary()
        with trial_fence.lease(authority.path, fixture.terms(), directory=directory):
            if outcome == "owner_cap":
                with self.assertRaises(BudgetExceeded):
                    owner.ledger.record_held_replacement(decision)
                self.assertIsNone(owner.ledger.held_replacement())
                self.assertEqual(authority.summary(), before)
                self.assertEqual(owner.ledger.get(decision.original_operation_id), original)
                return
            with (
                patch.object(authorization, "_mirror_operation", side_effect=OperationConflict),
                self.assertRaises(OperationConflict),
            ):
                owner.ledger.record_held_replacement(decision)
            self.assertIsNone(owner.ledger.held_replacement())
            self.assertEqual(authority.summary(), before)
            owner.ledger.record_held_replacement(decision)
            reserved = authority.summary()
            owner.ledger.record_held_replacement(decision)
            self.assertEqual(authority.summary(), reserved)
            self.assertEqual(reserved["reserved_microusd"], 2 * decision.reserve_microusd)
            self.assertEqual(reserved["operation_count"], 2)
            with self.assertRaises(BudgetExceeded):
                owner.ledger.reserve("unrelated", "c" * 64, 1)
            with self.assertRaises(OperationConflict):
                owner.ledger.complete(
                    decision.original_operation_id,
                    response=original.response,
                    actual_microusd=0,
                    provider_request_id="unverified",
                )
            response = Mock(status=200 if success else 503)
            response.getheaders.return_value = [("request-id", "replacement")]
            response.read.return_value = (
                b'{"model":"test-claude","usage":{"input_tokens":2,"output_tokens":3}}'
                if success
                else b"service unavailable again"
            )
            connection = host.connection(response)
            rotated = "anthropic-rotated-test-key-never-real" if success else key
            if success:
                with (
                    patch.dict("os.environ", {"ANTHROPIC_API_KEY": rotated}, clear=True),
                    patch("http.client.HTTPSConnection") as blocked,
                    self.assertRaises(gateway.GatewayError),
                ):
                    owner._prepare_held_replacement(decision)
                blocked.assert_not_called()
                self.assertEqual(authority.summary(), reserved)
            confirmed = {
                context: {
                    "anthropic": gateway._credential_fingerprint("anthropic", rotated, context)
                }
            }
            if success:
                token = gateway._CONFIRMED_PROJECT_KEYS.set(confirmed)
                try:
                    with (
                        patch.dict("os.environ", {"ANTHROPIC_API_KEY": key}, clear=True),
                        patch("http.client.HTTPSConnection") as blocked,
                        self.assertRaises(gateway.GatewayError),
                    ):
                        owner._prepare_held_replacement(decision)
                    blocked.assert_not_called()
                    self.assertEqual(authority.summary(), reserved)
                finally:
                    gateway._CONFIRMED_PROJECT_KEYS.reset(token)
            with (
                patch.dict("os.environ", {"ANTHROPIC_API_KEY": rotated}, clear=True),
                patch.object(gateway, "_CONFIRMED_PROJECT_KEYS") as session,
                patch("http.client.HTTPSConnection", return_value=connection),
                patch.object(
                    gateway,
                    "_validated_usage",
                    side_effect=KeyboardInterrupt if success else gateway.WireError,
                ),
                self.assertRaises(KeyboardInterrupt if success else ProviderUncertain),
            ):
                session.get.return_value = confirmed
                owner._prepare_held_replacement(decision)
            self.assertEqual(owner.ledger.get(decision.replacement_operation_id).status, "unknown")
            self.assertEqual(
                authority.summary()["reserved_microusd"], 2 * decision.reserve_microusd
            )
            with patch.object(
                gateway.RawHTTPTransport, "send_prepared", side_effect=AssertionError
            ) as send:
                if success:
                    replay = owner._prepare_held_replacement(decision)
                    self.assertEqual(owner._prepare_held_replacement(decision), replay)
                else:
                    with self.assertRaises(ProviderUncertain):
                        owner._prepare_held_replacement(decision)
                    with self.assertRaises(BudgetExceeded):
                        owner.ledger.authorize_dispatch("unrelated")
                send.assert_not_called()
            connection.request.assert_called_once()
            self.assertEqual(connection.request.call_args.kwargs["headers"]["x-api-key"], rotated)
            self.assertEqual(owner.ledger.get(decision.original_operation_id), original)
            self.assertEqual(
                authority.summary()["reserved_microusd"],
                decision.reserve_microusd * (1 if success else 2),
            )

    def test_direct_gateway_holds_original_trial_lease_while_send_is_in_flight(self):
        fixture = TrialFixture(self)
        directory = fixture.prepare()
        gateway = fixture.h.gateway(directory=directory)
        original_send = gateway.transport.send_prepared
        observations = []

        def contender():
            try:
                with trial_fence.lease(
                    fixture.authorities["search"].path, fixture.terms(), directory=directory
                ):
                    observations.append("acquired")
            except trial_fence.TrialFenceError:
                observations.append("blocked")

        def send(prepared):
            thread = threading.Thread(target=contender)
            thread.start()
            thread.join(timeout=5)
            self.assertFalse(thread.is_alive())
            return original_send(prepared)

        with patch.object(gateway.transport, "send_prepared", side_effect=send):
            fixture.h.send(gateway=gateway)
        self.assertEqual(observations, ["blocked"])
        operation = gateway.ledger.get(gateway.operation_id(fixture.h.call))
        self.assertEqual(operation.status, "completed")
        self.assertEqual(fixture.authorities["search"].summary()["spent_microusd"], 11)
        self.assertEqual(fixture.authorities["search"].summary()["reserved_microusd"], 0)

    def test_direct_gateway_preserves_known_reply_if_fixed_metadata_is_poisoned_in_flight(self):
        fixture = TrialFixture(self)
        directory = fixture.prepare()
        gateway = fixture.h.gateway(directory=directory)
        original_send = gateway.transport.send_prepared

        def send(prepared):
            (fixture.root / "funding.json").write_bytes(b"{")
            return original_send(prepared)

        with patch.object(gateway.transport, "send_prepared", side_effect=send):
            expected = fixture.h.send(gateway=gateway)
        operation = gateway.ledger.get(gateway.operation_id(fixture.h.call))
        self.assertEqual(operation.status, "completed")
        self.assertEqual(operation.response["envelope"], expected.to_record())
        self.assertEqual(fixture.authorities["search"].summary()["spent_microusd"], 11)
        self.assertEqual(fixture.authorities["search"].summary()["reserved_microusd"], 0)
        with self.assertRaises(ValidationError):
            fixture.prepare("cannot-continue")
