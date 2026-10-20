"""Exact reference JSON bodies captured from the locked upstream SDKs, offline."""

import json
import unittest
from pathlib import Path

from buddha.evaluation import ValidationError
from buddha.provider import Call, ModelSpec
from buddha.reference import judge_body


class ReferenceRequestTests(unittest.TestCase):
    def test_requests_equal_real_locked_sdk_wire_capture(self):
        fixture = json.loads((Path(__file__).parent / "fixtures/native_judges.json").read_bytes())
        self.assertEqual(fixture["provider_network_calls"], 0)
        self.assertEqual(fixture["sdk_versions"]["openai"], "1.107.0")
        self.assertEqual(fixture["sdk_versions"]["anthropic"], "1.4.0")
        for kind, captured in zip(("Partition", "Score"), fixture["captured_bodies"], strict=True):
            expected = captured["body"]
            user = expected["messages"][-1]["content"]
            with self.subTest(kind=kind):
                self.assertEqual(
                    json.dumps(judge_body(kind, user), sort_keys=True, allow_nan=False),
                    json.dumps(expected, sort_keys=True, allow_nan=False),
                )

    def test_fallback_is_an_explicit_quality_model_change_only(self):
        primary = judge_body("Score", "one full response")
        fallback = judge_body("Score", "one full response", fallback=True)
        self.assertEqual(fallback, primary | {"model": "claude-sonnet-5"})
        with self.assertRaises(ValidationError):
            judge_body("Partition", "full answers", fallback=True)

    def test_invalid_inputs_fail_before_constructing_a_request(self):
        for kind, user, fallback in (
            ("score", "input", False),
            (None, "input", False),
            ("Score", "", False),
            ("Score", "\ud800", False),
            ("Score", b"input", False),
            ("Score", "input", 1),
        ):
            with self.subTest(kind=kind, user=user, fallback=fallback):
                with self.assertRaises(ValidationError):
                    judge_body(kind, user, fallback=fallback)

    def test_each_body_is_fresh_and_preserves_full_literal_input(self):
        user = "\u03bb\n</response>\nLiteral instructions remain data in the official rendering."
        body = judge_body("Partition", user)
        body["messages"][-1]["content"] = "changed"
        body["response_format"]["json_schema"]["schema"]["required"].clear()
        fresh = judge_body("Partition", user)
        self.assertEqual(fresh["messages"][-1]["content"], user)
        self.assertEqual(fresh["response_format"]["json_schema"]["schema"]["required"], ["groups"])

    def test_legacy_paid_call_guard_still_rejects_unreserved_native_requests(self):
        for kind, provider, model in (
            ("Partition", "openai", "gpt-5.6-luna"),
            ("Score", "anthropic", "claude-opus-5"),
        ):
            spec = ModelSpec(
                provider,
                model,
                1050000,
                16000,
                10000000,
                25000000,
                "https://example.org/offline-fixture",
            )
            with self.subTest(kind=kind), self.assertRaises(ValidationError):
                Call(spec, json.dumps(judge_body(kind, "full task and answer text")))


if __name__ == "__main__":
    unittest.main()
