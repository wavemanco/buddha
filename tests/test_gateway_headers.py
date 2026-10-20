"""Reviewed native headers traverse real shared accounting without SDK/network."""

import base64
import copy
import gzip
import hashlib
import json
import os
import unittest
from dataclasses import replace
from unittest.mock import patch

import test_gateway as fixtures

from buddha.evaluation import ValidationError
from buddha.ledger import OperationConflict
from buddha.provider import ProviderUncertain
from buddha.releases import Release, prepare_selection
from buddha.wire import RawEnvelope


class GatewayHeaderTests(unittest.TestCase):
    def setUp(self):
        self.fixture = fixtures.GatewayTests("runTest")
        self.fixture.setUp()
        self.addCleanup(self.fixture.doCleanups)

    def prepare(self, *, profiles=None):
        fixture = self.fixture
        selected = copy.deepcopy(profiles or fixture.profiles)
        if profiles is None:
            selected["format"] = "buddha.gateway-profiles.v2"
            selected["profiles"]["primary"].update(
                headers={
                    "user-agent": ["synthetic-sdk/1.0", "synthetic-sdk/2.0"],
                    "x-stainless-lang": ["python"],
                    "x-stainless-retry-count": ["0", "1"],
                    "accept": ["application/json"],
                    "content-type": ["application/json"],
                    "accept-encoding": ["gzip, deflate", "identity"],
                },
                account_headers={
                    "openai-project": "reviewed-project",
                    "openai-organization": "reviewed-organization",
                },
            )
        fixture.write("host", "profiles/openai.json", json.dumps(selected))
        fixture.selection = prepare_selection(
            Release.from_record(fixture.release_record),
            fixture.roots,
            capabilities={fixtures.CAPABILITY: "profiles/openai.json"},
        )
        self.directory = fixture.prepare("headers-run")
        self.gateway = fixture.gateway(directory=self.directory)
        self.ledger = fixture.authority.for_run(self.directory)
        return selected

    def call(self, headers):
        return replace(self.fixture.call, headers=headers)

    def assert_unsent(self, call):
        original = os.environ.get

        def reject_credentials(name, *args):
            if name in {"OPENAI_API_KEY", "ANTHROPIC_API_KEY"}:
                self.fail("invalid headers accessed provider credentials")
            return original(name, *args)

        with (
            patch.dict("os.environ", {}, clear=True),
            patch.object(os.environ, "get", side_effect=reject_credentials),
            patch("http.client.HTTPSConnection") as connection,
            self.assertRaises(ValidationError),
        ):
            self.gateway.execute(call)
        connection.assert_not_called()
        self.assertEqual(self.ledger.totals()["operation_count"], 0)

    def test_empty_header_record_is_unchanged_and_v1_rejects_extra_headers(self):
        fixture = self.fixture
        original = fixture.call.to_record()
        self.assertNotIn("headers", original)
        self.assertEqual(self.call(()).to_record(), original)
        gateway = fixture.gateway()
        with (
            patch.dict("os.environ", {}, clear=True),
            patch("http.client.HTTPSConnection") as connection,
            self.assertRaises(ValidationError),
        ):
            gateway.execute(self.call((("user-agent", "synthetic-sdk/1.0"),)))
        connection.assert_not_called()
        self.assertEqual(fixture.ledger.totals()["operation_count"], 0)

    def test_reviewed_values_and_order_survive_actual_http_request(self):
        self.prepare()
        submitted = (
            ("User-Agent", "synthetic-sdk/1.0"),
            ("X-Stainless-Lang", "python"),
            ("Accept", "application/json"),
            ("Content-Type", "application/json"),
            ("Accept-Encoding", "gzip, deflate"),
            ("X-Stainless-Retry-Count", "0"),
        )
        call = self.call(submitted)
        expected = tuple((name.lower(), value) for name, value in submitted)
        self.assertEqual(call.headers, expected)
        self.assertEqual(call.to_record()["headers"], [list(pair) for pair in expected])
        connection = self.fixture.connection()
        self.fixture.send(self.gateway, call, connection=connection)
        actual = connection.request.call_args.kwargs["headers"]
        forwarded = tuple(
            (name.lower(), value)
            for name, value in actual.items()
            if name.lower() in {pair[0] for pair in expected}
        )
        self.assertEqual(forwarded, expected)
        self.assertEqual(connection.request.call_args.kwargs["body"], call.body)
        self.assertEqual(
            sum(name.lower() == "content-type" for name in actual),
            1,
        )
        connection.request.assert_called_once()
        operation = self.ledger.get(self.gateway.operation_id(call))
        self.assertEqual(operation.actual_microusd, 11)

    def test_account_owner_always_injects_exact_values_when_worker_omits_them(self):
        self.prepare()
        connection = self.fixture.connection()
        self.fixture.send(self.gateway, self.call(()), connection=connection)
        actual = {
            name.lower(): value
            for name, value in connection.request.call_args.kwargs["headers"].items()
        }
        self.assertEqual(actual["openai-project"], "reviewed-project")
        self.assertEqual(actual["openai-organization"], "reviewed-organization")

    def test_account_header_copy_may_match_owner_but_cannot_change_account(self):
        self.prepare()
        for name in ("openai-project", "openai-organization"):
            with self.subTest(name=name):
                self.assert_unsent(self.call(((name, "unreviewed-account"),)))
        matching = self.call(
            (
                ("OpenAI-Project", "reviewed-project"),
                ("OpenAI-Organization", "reviewed-organization"),
            )
        )
        connection = self.fixture.connection()
        self.fixture.send(self.gateway, matching, connection=connection)
        actual = connection.request.call_args.kwargs["headers"]
        self.assertEqual(sum(name.lower() == "openai-project" for name in actual), 1)
        self.assertEqual(sum(name.lower() == "openai-organization" for name in actual), 1)

    def test_header_types_controls_duplicates_and_sizes_are_denied_before_spending(self):
        self.prepare()
        invalid = (
            [("user-agent", "synthetic-sdk/1.0")],
            (("user-agent", "one", "two"),),
            (("user-agent", 1),),
            (("user-agent", "line\r\ninjection"),),
            (("user-agent", "nul\x00text"),),
            (("user-agent", "non-ascii-λ"),),
            (("user-agent", "a" * 100_000),),
            (("user-agent", "one"), ("User-Agent", "one")),
            (("bad name", "value"),),
        )
        for headers in invalid:
            with self.subTest(kind=type(headers).__name__), self.assertRaises(ValidationError):
                self.gateway.execute(self.call(headers))
        self.assertEqual(self.ledger.totals()["operation_count"], 0)

    def test_unreviewed_exact_values_encoding_and_retry_count_fail_before_keys(self):
        self.prepare()
        for headers in (
            (("user-agent", "another-sdk"),),
            (("accept-encoding", "br"),),
            (("x-stainless-retry-count", "1"),),
            (("content-type", "application/octet-stream"),),
        ):
            with self.subTest(headers=headers):
                self.assert_unsent(self.call(headers))

    def test_auth_transport_cookie_and_unknown_feature_headers_are_never_worker_inputs(self):
        self.prepare()
        names = (
            "authorization",
            "x-api-key",
            "host",
            "content-length",
            "transfer-encoding",
            "connection",
            "cookie",
            "proxy-authorization",
            "anthropic-beta",
            "x-stainless-unreviewed-paid-feature",
        )
        for name in names:
            with self.subTest(name=name):
                with self.assertRaises(ValidationError):
                    self.gateway.execute(self.call(((name, "synthetic-value"),)))
        self.assertEqual(self.ledger.totals()["operation_count"], 0)

    def test_profile_cannot_enable_forbidden_or_unbounded_headers(self):
        base = copy.deepcopy(self.fixture.profiles)
        base["format"] = "buddha.gateway-profiles.v2"
        base["profiles"]["primary"].update(headers={}, account_headers={})
        for index, entry in enumerate(
            (
                {"authorization": ["fake"]},
                {"host": ["alternate.example"]},
                {"anthropic-beta": ["unreviewed-feature"]},
                {"x-stainless-unreviewed-paid-feature": ["enabled"]},
                {"openai-project": ["worker-selected-account"]},
                {"user-agent": None},
                {"user-agent": []},
                {"user-agent": ["one", "one"]},
                {"User-Agent": ["one"]},
                {"accept-encoding": ["br"]},
            )
        ):
            with self.subTest(index=index):
                profiles = copy.deepcopy(base)
                profiles["profiles"]["primary"]["headers"] = entry
                self.fixture.write("host", "profiles/openai.json", json.dumps(profiles))
                self.fixture.selection = prepare_selection(
                    Release.from_record(self.fixture.release_record),
                    self.fixture.roots,
                    capabilities={fixtures.CAPABILITY: "profiles/openai.json"},
                )
                with self.assertRaises(ValidationError):
                    self.fixture.prepare("bad-headers-" + str(index))
        self.assertEqual(self.fixture.authority.summary()["operation_count"], 0)

    def test_changed_headers_conflict_under_same_logical_attempt(self):
        self.prepare()
        first = self.call((("user-agent", "synthetic-sdk/1.0"),))
        second = self.call((("user-agent", "synthetic-sdk/2.0"),))
        self.fixture.send(self.gateway, first)
        with self.assertRaises(OperationConflict):
            self.gateway.execute(second)
        self.assertEqual(self.ledger.totals()["operation_count"], 1)

    def test_completed_header_receipt_replays_without_key_or_paid_permission(self):
        self.prepare()
        call = self.call((("user-agent", "synthetic-sdk/1.0"),))
        expected = self.fixture.send(self.gateway, call)
        self.fixture.authority.deactivate("headers-run", "synthetic header run complete")
        with (
            patch.dict("os.environ", {}, clear=True),
            patch("http.client.HTTPSConnection") as connection,
        ):
            replay = self.fixture.gateway(live=False, directory=self.directory).execute(call)
        self.assertEqual(replay, expected)
        connection.assert_not_called()
        self.assertEqual(self.ledger.totals()["operation_count"], 1)

    def test_known_other_provider_key_is_screened_in_a_reviewed_header_before_dispatch(self):
        self.prepare()
        # The independently configured other credential occurs in an otherwise
        # exactly reviewed metadata value, exercising secret screening after profile checks.
        call = self.call((("user-agent", "synthetic-sdk/1.0"),))
        connection = self.fixture.connection()
        with (
            patch.dict(
                "os.environ",
                {"OPENAI_API_KEY": fixtures.KEY, "ANTHROPIC_API_KEY": "synthetic-sdk"},
                clear=True,
            ),
            patch("http.client.HTTPSConnection", return_value=connection),
            self.assertRaises(ValidationError),
        ):
            self.gateway.execute(call)
        connection.request.assert_not_called()
        operation = self.ledger.get(self.gateway.operation_id(call))
        self.assertEqual(operation.status, "reserved")
        self.assertIsNone(operation.response)
        for path in (self.directory / "operations.sqlite3", self.fixture.authority.path):
            self.assertNotIn(b"synthetic-sdk", path.read_bytes())

    def compressed_response(self, raw, *, status=200, coding="gzip"):
        response = self.fixture.response(
            status=status,
            headers=[("x-request-id", "req-compressed"), ("content-encoding", coding)],
        )
        response.read.return_value = raw
        return response

    def assert_encoded_withheld(self, raw, *, status=200, coding="gzip"):
        self.prepare()
        call = self.call((("accept-encoding", "gzip, deflate"),))
        response = self.compressed_response(raw, status=status, coding=coding)
        connection = self.fixture.connection(response)
        with self.assertRaises(ProviderUncertain):
            self.fixture.send(self.gateway, call, connection=connection)
        operation = self.ledger.get(self.gateway.operation_id(call))
        self.assertEqual(operation.status, "unknown")
        envelope = RawEnvelope.from_record(operation.response["envelope"])
        self.assertTrue(envelope.withheld)
        self.assertEqual(envelope.body, b"")
        self.assertEqual(envelope.headers, ())
        self.assertEqual(envelope.received_sha256, hashlib.sha256(raw).hexdigest())
        self.assertEqual(self.fixture.authority.summary()["reserved_microusd"], 300)
        self.assertEqual(self.fixture.authority.summary()["spent_microusd"], 0)
        self.assertEqual(self.fixture.authority.summary()["operation_count"], 1)
        for path in (self.directory / "operations.sqlite3", self.fixture.authority.path):
            stored = path.read_bytes()
            self.assertNotIn(base64.b64encode(raw), stored)
            self.assertNotIn(fixtures.KEY.encode(), stored)
        with self.assertRaises(ValidationError):
            self.fixture.send(self.gateway, replace(call, attempt=1), connection=connection)
        connection.request.assert_called_once()
        self.assertEqual(self.fixture.authority.summary()["operation_count"], 1)

    def test_gzip_reply_keeps_encoded_evidence_bills_and_replays_without_keys(self):
        self.prepare()
        call = self.call((("accept-encoding", "gzip, deflate"),))
        raw = gzip.compress(self.fixture.response().read.return_value, mtime=0)
        connection = self.fixture.connection(self.compressed_response(raw))
        received = self.fixture.send(self.gateway, call, connection=connection)
        self.assertEqual(received.body, raw)
        self.assertEqual(received.received_sha256, hashlib.sha256(raw).hexdigest())
        self.assertIn(("content-encoding", "gzip"), received.headers)
        operation = self.ledger.get(self.gateway.operation_id(call))
        self.assertEqual(operation.status, "completed")
        self.assertEqual(operation.actual_microusd, 11)
        self.assertEqual(RawEnvelope.from_record(operation.response["envelope"]), received)
        self.fixture.authority.deactivate("headers-run", "synthetic compressed run complete")
        with (
            patch.dict("os.environ", {}, clear=True),
            patch("http.client.HTTPSConnection") as replay_connection,
        ):
            replay = self.fixture.gateway(live=False, directory=self.directory).execute(call)
        self.assertEqual(replay, received)
        replay_connection.assert_not_called()
        connection.request.assert_called_once()
        self.assertEqual(self.fixture.authority.summary()["spent_microusd"], 11)

    def test_gzip_decoded_secret_is_withheld_even_when_status_is_successful(self):
        body = self.fixture.response(error={"message": fixtures.KEY}).read.return_value
        self.assert_encoded_withheld(gzip.compress(body, mtime=0))

    def test_gzip_decoded_secret_is_withheld_in_rate_limit_reply(self):
        body = self.fixture.response(error={"message": fixtures.KEY}).read.return_value
        self.assert_encoded_withheld(gzip.compress(body, mtime=0), status=429)

    def test_malformed_gzip_is_withheld_with_unknown_hold(self):
        self.assert_encoded_withheld(b"not a gzip response")

    def test_incomplete_gzip_is_withheld_with_unknown_hold(self):
        raw = gzip.compress(self.fixture.response().read.return_value, mtime=0)
        self.assert_encoded_withheld(raw[:-1])

    def test_trailing_encoded_data_is_withheld_with_unknown_hold(self):
        raw = gzip.compress(self.fixture.response().read.return_value, mtime=0)
        self.assert_encoded_withheld(raw + b"unverified trailing bytes")

    def test_unsupported_response_coding_is_withheld_with_unknown_hold(self):
        raw = gzip.compress(self.fixture.response().read.return_value, mtime=0)
        self.assert_encoded_withheld(raw, coding="br")

    def test_header_capture_interrupt_after_compressed_body_withholds_unscreenable_bytes(self):
        self.prepare()
        call = self.call((("accept-encoding", "gzip, deflate"),))
        body = self.fixture.response(error={"message": fixtures.KEY}).read.return_value
        raw = gzip.compress(body, mtime=0)
        response = self.compressed_response(raw)
        response.getheaders.side_effect = KeyboardInterrupt
        connection = self.fixture.connection(response)
        with self.assertRaises(KeyboardInterrupt):
            self.fixture.send(self.gateway, call, connection=connection)
        operation = self.ledger.get(self.gateway.operation_id(call))
        envelope = RawEnvelope.from_record(operation.response["envelope"])
        self.assertEqual(operation.status, "unknown")
        self.assertTrue(envelope.withheld)
        self.assertFalse(envelope.headers_complete)
        self.assertEqual(envelope.body, b"")
        self.assertEqual(envelope.headers, ())
        self.assertEqual(envelope.received_sha256, hashlib.sha256(raw).hexdigest())
        self.assertEqual(self.fixture.authority.summary()["reserved_microusd"], 300)
        self.assertEqual(self.fixture.authority.summary()["spent_microusd"], 0)
        for path in (self.directory / "operations.sqlite3", self.fixture.authority.path):
            self.assertNotIn(base64.b64encode(raw), path.read_bytes())
        connection.request.assert_called_once()

    def test_unsolicited_gzip_secret_is_withheld_when_response_headers_are_unavailable(self):
        self.prepare()
        call = self.call(())
        body = self.fixture.response(error={"message": fixtures.KEY}).read.return_value
        raw = gzip.compress(body, mtime=0)
        response = self.compressed_response(raw)
        response.getheaders.side_effect = KeyboardInterrupt
        connection = self.fixture.connection(response)
        with self.assertRaises(KeyboardInterrupt):
            self.fixture.send(self.gateway, call, connection=connection)
        sent = connection.request.call_args.kwargs["headers"]
        self.assertNotIn("accept-encoding", {name.lower() for name in sent})
        operation = self.ledger.get(self.gateway.operation_id(call))
        envelope = RawEnvelope.from_record(operation.response["envelope"])
        self.assertEqual(operation.status, "unknown")
        self.assertTrue(envelope.withheld)
        self.assertFalse(envelope.headers_complete)
        self.assertEqual(envelope.body, b"")
        self.assertEqual(envelope.headers, ())
        self.assertEqual(envelope.received_sha256, hashlib.sha256(raw).hexdigest())
        self.assertEqual(self.fixture.authority.summary()["reserved_microusd"], 300)
        self.assertEqual(self.fixture.authority.summary()["spent_microusd"], 0)
        for path in (self.directory / "operations.sqlite3", self.fixture.authority.path):
            self.assertNotIn(base64.b64encode(raw), path.read_bytes())
        connection.request.assert_called_once()

    def test_identity_header_cannot_hide_an_unsolicited_compressed_credential(self):
        body = self.fixture.response(error={"message": fixtures.KEY}).read.return_value
        self.assert_encoded_withheld(gzip.compress(body, mtime=0), coding="identity")

    def test_single_gzip_header_cannot_hide_a_nested_compressed_credential(self):
        body = self.fixture.response(error={"message": fixtures.KEY}).read.return_value
        inner = gzip.compress(body, mtime=0)
        self.assert_encoded_withheld(gzip.compress(inner, mtime=0))

    def test_complete_headers_without_coding_cannot_hide_compressed_credential(self):
        self.prepare()
        call = self.call(())
        body = self.fixture.response(error={"message": fixtures.KEY}).read.return_value
        raw = gzip.compress(body, mtime=0)
        response = self.fixture.response(headers=[("x-request-id", "req-no-coding")])
        response.read.return_value = raw
        connection = self.fixture.connection(response)
        with self.assertRaises(ProviderUncertain):
            self.fixture.send(self.gateway, call, connection=connection)
        operation = self.ledger.get(self.gateway.operation_id(call))
        envelope = RawEnvelope.from_record(operation.response["envelope"])
        self.assertEqual(operation.status, "unknown")
        self.assertTrue(envelope.withheld)
        self.assertTrue(envelope.headers_complete)
        self.assertEqual(envelope.body, b"")
        self.assertEqual(envelope.received_sha256, hashlib.sha256(raw).hexdigest())
        self.assertEqual(self.fixture.authority.summary()["reserved_microusd"], 300)
        self.assertEqual(self.fixture.authority.summary()["spent_microusd"], 0)
        for path in (self.directory / "operations.sqlite3", self.fixture.authority.path):
            self.assertNotIn(base64.b64encode(raw), path.read_bytes())
        connection.request.assert_called_once()

    def test_readable_malformed_compressed_envelope_is_retained_without_billing(self):
        self.prepare()
        call = self.call((("accept-encoding", "gzip, deflate"),))
        raw = gzip.compress(b'{"model":"test-model",\n"unfinished":', mtime=0)
        response = self.compressed_response(raw)
        connection = self.fixture.connection(response)
        with self.assertRaises(ProviderUncertain):
            self.fixture.send(self.gateway, call, connection=connection)
        operation = self.ledger.get(self.gateway.operation_id(call))
        envelope = RawEnvelope.from_record(operation.response["envelope"])
        self.assertEqual(operation.status, "unknown")
        self.assertFalse(envelope.withheld)
        self.assertTrue(envelope.headers_complete)
        self.assertEqual(envelope.body, raw)
        self.assertIn(("content-encoding", "gzip"), envelope.headers)
        self.assertEqual(envelope.received_sha256, hashlib.sha256(raw).hexdigest())
        self.assertEqual(self.fixture.authority.summary()["reserved_microusd"], 300)
        self.assertEqual(self.fixture.authority.summary()["spent_microusd"], 0)
        connection.request.assert_called_once()


if __name__ == "__main__":
    unittest.main()
