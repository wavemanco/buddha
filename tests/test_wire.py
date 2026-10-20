"""Spec-defined raw response/billing checks; no provider or benchmark executes."""

import base64
import copy
import hashlib
import json
import unittest
from dataclasses import FrozenInstanceError
from unittest.mock import patch

from buddha.releases import ReleaseError
from buddha.wire import RawEnvelope, Usage, WireError, extract_usage


class RawEnvelopeTests(unittest.TestCase):
    def envelope(self, body=b"\x00\xffexact raw bytes\n", **changes):
        return RawEnvelope("openai", 200, body, **changes)

    def test_binary_body_lossless_roundtrip_and_digest(self):
        envelope = self.envelope()
        record = envelope.to_record()
        self.assertEqual(record["format"], "buddha.raw-envelope.v1")
        self.assertEqual(base64.b64decode(record["body_base64"]), envelope.body)
        self.assertEqual(record["received_sha256"], hashlib.sha256(envelope.body).hexdigest())
        self.assertEqual(RawEnvelope.from_record(record), envelope)
        self.assertEqual(RawEnvelope.from_record(json.loads(json.dumps(record))), envelope)

    def test_immutable_fields_and_detached_records(self):
        envelope = self.envelope(headers=(("X-Request-Id", "rid"),))
        with self.assertRaises(FrozenInstanceError):
            envelope.body = b"changed"
        record = envelope.to_record()
        record["headers"][0][1] = "changed"
        self.assertEqual(envelope.headers, (("x-request-id", "rid"),))
        restored = RawEnvelope.from_record(envelope.to_record())
        record = restored.to_record()
        record["headers"].append(["retry-after", "4"])
        self.assertEqual(restored, envelope)

    def test_header_names_normalize_values_duplicates_and_order_preserved(self):
        headers = (
            ("Retry-After", "Wed, 21 Oct 2026 07:28:00 GMT"),
            ("retry-after", "3"),
            ("X-Should-Retry", "false"),
            ("Retry-After-Ms", "125.5"),
            ("Content-Type", "application/json; charset=utf-8"),
        )
        envelope = self.envelope(headers=headers)
        self.assertEqual(envelope.headers, tuple((name.lower(), value) for name, value in headers))
        self.assertEqual(RawEnvelope.from_record(envelope.to_record()).headers, envelope.headers)

    def test_unknown_headers_controls_and_oversize_ids_fail_without_echo(self):
        secret = "secret-key-never-echo"
        for headers in (
            (("authorization", secret),),
            (("set-cookie", secret),),
            (("x-request-id", secret + "\r\nInjected: yes"),),
            (("retry-after", secret + "\x00"),),
            (("content-type", secret + "\t"),),
            (("x-request-id", secret * 3000),),
        ):
            with self.subTest(header=headers[0][0]):
                with self.assertRaises(WireError) as caught:
                    self.envelope(headers=headers)
                self.assertNotIn(secret, str(caught.exception))

    def test_strict_constructor_types_status_flags_and_provider(self):
        for changes in (
            {"provider": "other"},
            {"provider": True},
            {"status": True},
            {"status": 99},
            {"status": 600},
            {"body": bytearray(b"mutable")},
            {"body": "text"},
            {"headers": [["retry-after", "1"]]},
            {"headers": (("retry-after", 1),)},
            {"headers": (("retry-after",),)},
            {"truncated": 1},
            {"withheld": 0},
            {"headers_complete": 0},
            {"headers_complete": None},
        ):
            values = {"provider": "openai", "status": 200, "body": b""} | changes
            with self.subTest(changes=changes), self.assertRaises(WireError):
                RawEnvelope(**values)

    def test_wrong_original_digest_is_rejected_for_stored_body(self):
        for digest in ("f" * 64, "A" * 64, "x", True):
            with self.subTest(digest=digest), self.assertRaises(WireError):
                self.envelope(received_sha256=digest)

    def test_explicit_correct_digest_and_truncated_partial_bytes_roundtrip(self):
        digest = hashlib.sha256(b"partial").hexdigest()
        envelope = self.envelope(b"partial", received_sha256=digest, truncated=True)
        self.assertEqual(RawEnvelope.from_record(envelope.to_record()), envelope)

    def test_incomplete_headers_are_explicit_without_claiming_body_truncation(self):
        envelope = self.envelope(headers=(("x-request-id", "rid"),), headers_complete=False)
        self.assertFalse(envelope.headers_complete)
        self.assertFalse(envelope.truncated)
        self.assertFalse(envelope.withheld)
        self.assertEqual(envelope.body, b"\x00\xffexact raw bytes\n")
        self.assertFalse(envelope.to_record()["headers_complete"])
        self.assertEqual(RawEnvelope.from_record(envelope.to_record()), envelope)
        complete = self.envelope()
        self.assertTrue(complete.headers_complete)
        record = complete.to_record()
        for value in (None, 1, "false"):
            with self.subTest(value=value), self.assertRaises(WireError):
                RawEnvelope.from_record(record | {"headers_complete": value})
        with self.assertRaises(WireError):
            RawEnvelope.from_record(
                {key: value for key, value in record.items() if key != "headers_complete"}
            )

    def test_withheld_has_original_digest_and_no_payload_or_headers(self):
        digest = hashlib.sha256(b"response echoed secret").hexdigest()
        envelope = self.envelope(b"", withheld=True, received_sha256=digest)
        self.assertEqual(envelope.received_sha256, digest)
        self.assertEqual(RawEnvelope.from_record(envelope.to_record()), envelope)
        for changes in (
            {"body": b"leaked"},
            {"headers": (("request-id", "leaked"),)},
            {"received_sha256": None},
        ):
            values = {
                "provider": "openai",
                "status": 200,
                "body": b"",
                "withheld": True,
                "received_sha256": digest,
            } | changes
            with self.subTest(changes=changes), self.assertRaises(WireError):
                RawEnvelope(**values)

    def test_provider_request_id_uses_only_single_proper_provider_header(self):
        headers = (("request-id", "anthropic-id"), ("x-request-id", "openai-id"))
        self.assertEqual(self.envelope(headers=headers).provider_request_id, "openai-id")
        self.assertEqual(
            RawEnvelope("anthropic", 200, b"", headers=headers).provider_request_id,
            "anthropic-id",
        )
        self.assertEqual(self.envelope().provider_request_id, "")
        self.assertEqual(self.envelope(headers=(("x-request-id", ""),)).provider_request_id, "")
        for values in (("same", "same"), ("one", "two")):
            envelope = self.envelope(headers=tuple(("x-request-id", value) for value in values))
            with self.subTest(values=values), self.assertRaises(WireError):
                _ = envelope.provider_request_id

    def test_repr_hides_raw_payload_and_all_header_values(self):
        secret = "secret-key-never-echo"
        envelope = self.envelope(secret.encode(), headers=(("x-request-id", secret),))
        self.assertNotIn(secret, repr(envelope))

    def test_record_keys_types_base64_and_digest_are_strict(self):
        record = self.envelope().to_record()
        bad = []
        for key, value in (
            ("format", "future"),
            ("body_base64", "***"),
            ("body_base64", "YQ==\n"),
            ("body_base64", "YR=="),
            ("body_base64", 1),
            ("received_sha256", "0" * 64),
            ("received_sha256", None),
            ("headers", {"retry-after": "1"}),
            ("headers", [["retry-after", 1]]),
        ):
            bad.append(record | {key: value})
        bad.extend((record | {"extra": True}, {k: v for k, v in record.items() if k != "status"}))
        for row in bad:
            with self.subTest(row=row), self.assertRaises(WireError):
                RawEnvelope.from_record(row)
        for row in (None, [], b"record"):
            with self.subTest(row=row), self.assertRaises(WireError):
                RawEnvelope.from_record(row)

    def test_bounds_apply_to_actual_body_and_headers(self):
        with patch("buddha.wire.MAX_BODY_BYTES", 3):
            with self.assertRaises(WireError):
                self.envelope(b"1234")
        with patch("buddha.wire.MAX_HEADERS", 1):
            with self.assertRaises(WireError):
                self.envelope(headers=(("retry-after", "1"), ("x-should-retry", "false")))
        self.assertTrue(issubclass(WireError, ReleaseError))


class UsageTests(unittest.TestCase):
    def raw(self, provider="openai", record=None, **changes):
        value = (
            record
            if record is not None
            else {
                "model": "fixed-model",
                "usage": {"prompt_tokens": 12, "completion_tokens": 9},
            }
        )
        body = json.dumps(value, separators=(",", ":")).encode()
        return RawEnvelope(provider, 200, body, **changes)

    def test_openai_inclusive_reasoning_and_cache_are_not_double_counted(self):
        record = {
            "model": "fixed-model",
            "service_tier": "default",
            "usage": {
                "prompt_tokens": 12,
                "completion_tokens": 9,
                "total_tokens": 21,
                "prompt_tokens_details": {"cached_tokens": 10},
                "completion_tokens_details": {"reasoning_tokens": 8},
            },
        }
        usage = extract_usage(self.raw(record=record, headers=(("x-request-id", "rid"),)))
        self.assertEqual(usage, Usage("fixed-model", "rid", 12, 9, "default"))
        with self.assertRaises(FrozenInstanceError):
            usage.input_tokens = 0

    def test_anthropic_adds_cache_creation_and_read_inclusive_inputs(self):
        record = {
            "model": "claude-fixed",
            "usage": {
                "input_tokens": 3,
                "cache_creation_input_tokens": 4,
                "cache_read_input_tokens": 5,
                "output_tokens": 9,
                "service_tier": "standard",
            },
        }
        usage = extract_usage(self.raw("anthropic", record, headers=(("request-id", "rid"),)))
        self.assertEqual(usage, Usage("claude-fixed", "rid", 12, 9, "standard"))

    def test_optional_cache_and_tier_absence_are_zero_and_empty(self):
        record = {"model": "claude-fixed", "usage": {"input_tokens": 0, "output_tokens": 0}}
        self.assertEqual(
            extract_usage(self.raw("anthropic", record)), Usage("claude-fixed", "", 0, 0, "")
        )

    def test_malformed_semantic_judgment_and_multiblock_content_do_not_block_billing(self):
        record = {
            "model": "claude-fixed",
            "usage": {"input_tokens": 1, "output_tokens": 2},
            "stop_reason": "max_tokens",
            "content": [
                {"type": "thinking", "thinking": "unfinished"},
                {"type": "text", "text": '{"score":1,"score":broken'},
                {"type": "text", "text": "another non-JSON judgment"},
            ],
        }
        usage = extract_usage(self.raw("anthropic", record))
        self.assertEqual((usage.input_tokens, usage.output_tokens), (1, 2))
        record = {"model": "fixed", "usage": {"prompt_tokens": 1, "completion_tokens": 2}}
        self.assertEqual(extract_usage(self.raw(record=record)).model, "fixed")

    def test_non200_truncated_and_withheld_cannot_establish_billable_usage(self):
        ordinary = self.raw()
        for envelope in (
            RawEnvelope("openai", 429, ordinary.body),
            RawEnvelope("openai", 200, ordinary.body, truncated=True),
            RawEnvelope("openai", 200, ordinary.body, headers_complete=False),
            RawEnvelope("openai", 200, b"", withheld=True, received_sha256="a" * 64),
        ):
            with self.subTest(envelope=envelope), self.assertRaises(WireError):
                extract_usage(envelope)

    def test_duplicate_utf8_nonfinite_deep_or_malformed_envelopes_rejected(self):
        for body in (
            b"{}",
            b"[]",
            b"null",
            b"\xff",
            b"{",
            b'{"model":"m","model":"n"}',
            b'{"model":"m","usage":{"prompt_tokens":1,"prompt_tokens":2,"completion_tokens":3}}',
            b'{"model":"m","usage":{"prompt_tokens":1,"completion_tokens":2},"meta":NaN}',
            b'{"model":"m","usage":{"prompt_tokens":1,"completion_tokens":2},"meta":1e999}',
            b"[" * 2000,
        ):
            with self.subTest(body=body[:50]), self.assertRaises(WireError):
                extract_usage(RawEnvelope("openai", 200, body))

    def test_missing_malformed_model_usage_and_tier_rejected_without_echo(self):
        valid = {"model": "fixed-model", "usage": {"prompt_tokens": 1, "completion_tokens": 2}}
        rows = [valid | {"model": v} for v in (None, "", " ", 1, "\ud800")]
        rows += [valid | {"usage": v} for v in (None, [], "secret-key-never-echo")]
        rows += [valid | {"service_tier": v} for v in (None, 1, False)]
        for row in rows:
            with self.subTest(row=row), self.assertRaises(WireError) as caught:
                extract_usage(self.raw(record=row))
            self.assertNotIn("secret-key-never-echo", str(caught.exception))

    def test_token_types_missing_negative_and_overflow_reject(self):
        for provider, required, optional in (
            ("openai", ("prompt_tokens", "completion_tokens"), ()),
            (
                "anthropic",
                ("input_tokens", "output_tokens"),
                ("cache_creation_input_tokens", "cache_read_input_tokens"),
            ),
        ):
            valid = {key: 1 for key in required}
            for key in (*required, *optional):
                for value in (None, True, -1, 1.0, "2", 2**63):
                    row = {"model": "fixed", "usage": valid | {key: value}}
                    with (
                        self.subTest(provider=provider, key=key, value=value),
                        self.assertRaises(WireError),
                    ):
                        extract_usage(self.raw(provider, row))
            for key in required:
                row = {"model": "fixed", "usage": {k: v for k, v in valid.items() if k != key}}
                with self.subTest(provider=provider, key=key), self.assertRaises(WireError):
                    extract_usage(self.raw(provider, row))
        row = {
            "model": "fixed",
            "usage": {
                "input_tokens": 2**63 - 1,
                "cache_creation_input_tokens": 1,
                "output_tokens": 0,
            },
        }
        with self.assertRaises(WireError):
            extract_usage(self.raw("anthropic", row))

    def test_duplicate_provider_request_ids_make_usage_identity_ambiguous(self):
        envelope = self.raw(headers=(("x-request-id", "one"), ("X-Request-Id", "two")))
        with self.assertRaises(WireError):
            extract_usage(envelope)

    def test_usage_validates_its_own_inputs_and_hides_provider_text_in_repr(self):
        for changes in (
            {"model": ""},
            {"provider_request_id": None},
            {"input_tokens": True},
            {"input_tokens": -1},
            {"output_tokens": 2**63},
            {"service_tier": False},
        ):
            values = {
                "model": "m",
                "provider_request_id": "",
                "input_tokens": 1,
                "output_tokens": 2,
                "service_tier": "",
            } | changes
            with self.subTest(changes=changes), self.assertRaises(WireError):
                Usage(**values)
        secret = "secret-key-never-echo"
        self.assertNotIn(secret, repr(Usage(secret, secret, 1, 2, secret)))

    def test_invalid_record_does_not_mutate_caller_data(self):
        original = self.raw().to_record()
        changed = copy.deepcopy(original)
        changed["received_sha256"] = "f" * 64
        before = copy.deepcopy(changed)
        with self.assertRaises(WireError):
            RawEnvelope.from_record(changed)
        self.assertEqual(changed, before)


if __name__ == "__main__":
    unittest.main()
