"""A direct paid Gateway owns the trial through send and original settlement."""

import threading
import unittest
from unittest.mock import patch

from test_trial_fence import TrialFixture

from buddha import trial_fence
from buddha.common import ValidationError


class TrialFenceGatewayTests(unittest.TestCase):
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
