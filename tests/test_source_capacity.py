"""Frozen SRC-02 request and inclusive capacity rules; no paid transport or code execution."""

import copy
import hashlib
import json
import unittest
from dataclasses import replace
from unittest.mock import Mock

from buddha.gateway import Gateway, GatewayCall
from buddha.wire import RawEnvelope


class Text(str):
    pass


class Integer(int):
    pass


class Record(dict):
    pass


def sha(raw):
    return hashlib.sha256(raw).hexdigest()


class SourceCapacityTests(unittest.TestCase):
    def setUp(self):
        from buddha import source_capacity

        self.api = source_capacity
        self.Error = source_capacity.SourceCapacityError
        self.parent = "def generate(task, config, complete):\n    return []\n"
        self.proposal = {"source": "def generate(:\n", "hypothesis": "A literal replacement."}
        self.arguments = {
            "parent_source_sha256": sha(self.parent.encode()),
            "model": "gpt-6.1-sol",
            "context_tokens": 1_050_000,
            "output_cap_tokens": 32_768,
            "min_context_slack": 8_192,
            "min_output_slack": 8_192,
        }
        self.call = GatewayCall(
            "openai.chat-completions.v1",
            "proposal",
            "source-capacity/fixed",
            0,
            b'{"model":"gpt-6.1-sol","messages":[{"role":"user","content":"fixed"}]}',
        )
        self.expected = {
            "capability": self.call.capability,
            "profile_id": self.call.profile_id,
            "logical_id": self.call.logical_id,
            "attempt": 0,
            "body_sha256": sha(self.call.body),
        }

    def response(self, *, inputs=100, outputs=200, content=None, finish="stop"):
        return {
            "model": "gpt-6.1-sol",
            "service_tier": "default",
            "usage": {"prompt_tokens": inputs, "completion_tokens": outputs},
            "choices": [
                {
                    "finish_reason": finish,
                    "message": {
                        "content": json.dumps(self.proposal) if content is None else content,
                        "refusal": None,
                    },
                }
            ],
        }

    def envelope(self, record=None, **changes):
        body = json.dumps(self.response() if record is None else record).encode()
        return RawEnvelope("openai", 200, body, (("x-request-id", "capacity-receipt"),), **changes)

    def assess(self, record=None, **arguments):
        return self.api.assess_reply(self.envelope(record), **(self.arguments | arguments))

    def partial(self, result, reason):
        self.assertEqual(
            (result["measurement_status"], result["decision"], result["reason"]),
            ("partial", "unavailable", reason),
        )
        self.assertIsNone(result["proposal"])
        json.dumps(result, allow_nan=False)

    def test_exact_guard_delegates_once_and_all_identity_drift_stops_before_gateway(self):
        gateway = Mock(spec=Gateway)
        envelope = self.envelope()
        gateway.execute.return_value = envelope
        before = copy.deepcopy(self.expected)
        self.assertIsNone(self.api.guard_call(self.call, self.expected))
        self.assertIs(self.api.execute_guarded(gateway, self.call, self.expected), envelope)
        gateway.execute.assert_called_once_with(self.call)
        self.assertEqual(self.expected, before)
        changes = (
            {"body": self.call.body + b" "},
            {"body": self.call.body.replace(b"gpt-6.1-sol", b"another-model")},
            {"capability": "anthropic.messages.v1"},
            {"profile_id": "other-profile"},
            {"logical_id": "another-target"},
            {"attempt": 1},
            {"headers": (("accept", "application/json"),)},
        )
        for change in changes:
            with self.subTest(change=change):
                gateway.reset_mock()
                with self.assertRaises(self.Error):
                    self.api.execute_guarded(gateway, replace(self.call, **change), self.expected)
                gateway.execute.assert_not_called()

    def test_guard_rejects_unbound_or_malformed_expected_contract_without_execution(self):
        bad = [None, [], Record(self.expected), self.expected | {"extra": True}]
        bad.extend(
            {key: value for key, value in self.expected.items() if key != omitted}
            for omitted in self.expected
        )
        bad.extend(
            self.expected | change
            for change in (
                {"attempt": True},
                {"attempt": Integer(0)},
                {"attempt": 1},
                {"body_sha256": "A" * 64},
                {"body_sha256": Text(sha(self.call.body))},
                {"capability": "anthropic.messages.v1"},
                {"logical_id": ""},
                {"profile_id": Text("proposal")},
            )
        )
        for expected in bad:
            with self.subTest(expected=expected):
                gateway = Mock(spec=Gateway)
                with self.assertRaises(self.Error):
                    self.api.execute_guarded(gateway, self.call, expected)
                gateway.execute.assert_not_called()
        with self.assertRaises(self.Error):
            self.api.guard_call(object(), self.expected)

    def test_frozen_inclusive_margin_examples_and_no_visible_or_actual_output_shortcut(self):
        cases = (
            (1_009_040, 24_576, 8_192, 8_192, "pass", "capacity_pass"),
            (1_009_041, 24_576, 8_191, 8_192, "fail", "margin_failed"),
            (1_009_040, 24_577, 8_192, 8_191, "fail", "margin_failed"),
            (1_010_000, 100, 7_232, 32_668, "fail", "margin_failed"),
        )
        for inputs, outputs, context, output, decision, reason in cases:
            with self.subTest(inputs=inputs, outputs=outputs):
                record = self.response(inputs=inputs, outputs=outputs)
                before = copy.deepcopy(record)
                result = self.assess(record)
                self.assertEqual(result["measurement_status"], "complete")
                self.assertEqual((result["decision"], result["reason"]), (decision, reason))
                self.assertEqual(
                    (result["context_slack"], result["output_slack"]), (context, output)
                )
                self.assertEqual(result["proposal"], self.proposal)
                self.assertEqual(result["finish_reason"], "stop")
                self.assertEqual(result["usage"]["input_tokens"], inputs)
                self.assertEqual(result["usage"]["output_tokens"], outputs)
                self.assertEqual(result["usage"]["model"], "gpt-6.1-sol")
                self.assertEqual(result["usage"]["provider_request_id"], "capacity-receipt")
                self.assertEqual(record, before)
                json.dumps(result, allow_nan=False)
                record["usage"]["completion_tokens_details"] = {"reasoning_tokens": outputs}
                detailed = self.assess(record)
                self.assertEqual(
                    (detailed["decision"], detailed["context_slack"], detailed["output_slack"]),
                    (decision, context, output),
                )

    def test_invalid_assessment_arguments_raise_even_when_reply_evidence_is_absent(self):
        bad = (
            {"parent_source_sha256": "wrong"},
            {"parent_source_sha256": "A" * 64},
            {"parent_source_sha256": Text(self.arguments["parent_source_sha256"])},
            {"model": ""},
            {"model": Text("gpt-6.1-sol")},
            {"context_tokens": 0},
            {"output_cap_tokens": 0},
            {"min_context_slack": -1},
            {"min_output_slack": -1},
        )
        for change in bad:
            with self.subTest(change=change), self.assertRaises(self.Error):
                self.api.assess_reply(None, **(self.arguments | change))
        for name in (
            "context_tokens",
            "output_cap_tokens",
            "min_context_slack",
            "min_output_slack",
        ):
            for value in (True, 1.0, "1", Integer(1), 2**63):
                with self.subTest(name=name, value=value), self.assertRaises(self.Error):
                    self.api.assess_reply(None, **(self.arguments | {name: value}))

    def test_invalid_usage_provider_identity_or_unavailable_raw_evidence_stays_partial(self):
        for changes in ({"truncated": True}, {"headers_complete": False}):
            with self.subTest(changes=changes):
                result = self.api.assess_reply(self.envelope(**changes), **self.arguments)
                self.partial(result, "usage_unavailable")
                self.assertIsNone(result["usage"])
        for name, value in (("prompt_tokens", True), ("completion_tokens", 1.0)):
            record = self.response()
            record["usage"][name] = value
            with self.subTest(name=name):
                self.partial(self.assess(record), "usage_unavailable")
        for key, value in (("model", "unexpected-model"), ("service_tier", "priority")):
            with self.subTest(key=key):
                self.partial(self.assess(self.response() | {key: value}), "response_mismatch")
        for inputs, outputs in ((1_050_001, 1), (1, 32_769)):
            with self.subTest(inputs=inputs, outputs=outputs):
                self.partial(
                    self.assess(self.response(inputs=inputs, outputs=outputs)), "usage_bound"
                )
        for raw in (b'{"usage":{},"usage":{}}', b'{"usage":{"prompt_tokens":NaN}}'):
            envelope = RawEnvelope("openai", 200, raw, (("x-request-id", "capacity-receipt"),))
            self.partial(self.api.assess_reply(envelope, **self.arguments), "usage_unavailable")
        record = self.response()
        del record["service_tier"]
        self.assertEqual(self.assess(record)["decision"], "pass")

    def test_finish_refusal_response_shape_and_strict_proposal_fail_without_repair(self):
        for finish, reason in (
            ("length", "output_limit"),
            ("content_filter", "refusal"),
            ("tool_calls", "unsupported_finish"),
        ):
            with self.subTest(finish=finish):
                result = self.assess(self.response(finish=finish))
                self.partial(result, reason)
                self.assertEqual(result["finish_reason"], finish)
                self.assertEqual(result["usage"]["output_tokens"], 200)
        record = self.response()
        record["choices"][0]["message"]["refusal"] = "SYNTHETIC_PRIVATE_REFUSAL"
        self.partial(self.assess(record), "refusal")
        for choices in ([], [self.response()["choices"][0]] * 2):
            self.partial(self.assess(self.response() | {"choices": choices}), "invalid_response")
        for content in (
            "```json\n{}\n```",
            '{"source":"x","source":"y","hypothesis":"h"}',
            '{"source":NaN,"hypothesis":"h"}',
            "{",
            "[]",
        ):
            with self.subTest(content=content):
                self.partial(self.assess(self.response(content=content)), "invalid_proposal_json")
        for proposal in (
            {"source": "", "hypothesis": "h"},
            {"source": "x", "hypothesis": " "},
            {"source": "x" * (1024**2 + 1), "hypothesis": "h"},
            {"source": "x", "hypothesis": "h" * 4097},
            {"source": "x", "hypothesis": "h", "extra": True},
        ):
            self.partial(self.assess(self.response(content=json.dumps(proposal))), "proposal_bound")
        same = self.proposal | {"source": self.parent}
        self.partial(self.assess(self.response(content=json.dumps(same))), "source_unchanged")


if __name__ == "__main__":
    unittest.main()
