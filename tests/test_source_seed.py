"""Trusted composed seed only; model-returned child text never executes here."""

import ast
import copy
import hashlib
import json
import unittest
from pathlib import Path
from types import ModuleType
from unittest.mock import Mock, patch

from agents import frozen_seed
from buddha.source_seed import (
    FRAGMENT_VERSION,
    FROZEN_SEED_SHA256,
    SourceSeedError,
    compose_source_seed,
)

ROOT = Path(__file__).resolve().parents[1]
FROZEN = ROOT / "agents/frozen_seed.py"
CHILD = (
    "def generate(task, config, complete):\n"
    "    return [str(i) for i in range(task['count'])]\n"
    "def propose_improvement(parent, feedback, config, complete):\n"
    "    return {'source': parent['source'] + '\\n# next', 'hypothesis': 'Next change.'}\n"
)


def configuration(provider="openai", sampling="in-context"):
    return {
        "provider": provider,
        "model": "synthetic-source-seed",
        "max_output_tokens": 4096,
        "instructions": "Preserve the literal task. 雪",
        "sampling": sampling,
    }


def response(provider, text, *, finish=None, refused=False):
    if provider == "openai":
        return {
            "model": "synthetic-source-seed",
            "choices": [
                {
                    "message": {"content": text, "refusal": "denied" if refused else None},
                    "finish_reason": finish or "stop",
                }
            ],
            "usage": {"prompt_tokens": 5, "completion_tokens": 3},
            "service_tier": "default",
        }
    return {
        "model": "synthetic-source-seed",
        "content": [{"type": "text", "text": text}],
        "stop_reason": "refusal" if refused else (finish or "end_turn"),
        "usage": {"input_tokens": 5, "output_tokens": 3},
    }


class SourceSeedTests(unittest.TestCase):
    def setUp(self):
        self.frozen = FROZEN.read_bytes()
        self.source = compose_source_seed(self.frozen)
        self.module = ModuleType("_trusted_composed_source_seed")
        # Only the factory-verified repository seed and trusted fixed fragment execute.
        exec(compile(self.source, "<trusted-composed-seed>", "exec"), vars(self.module))  # nosec B102
        source_hash = hashlib.sha256(self.source).hexdigest()
        self.parent = {
            "entrypoint": "candidate.py",
            "source": self.source.decode(),
            "agent_sha256": hashlib.sha256(
                json.dumps({"candidate.py": source_hash}, separators=(",", ":")).encode()
            ).hexdigest(),
        }
        self.feedback = [
            {
                "task": {"id": 1, "prompt": "Pick one of two literal choices.", "count": 10},
                "note": "Saved measurements only; no semantic diagnosis.",
            },
            {
                "task": {"id": "1", "prompt": "A complete story. 雪", "count": 10},
                "note": "A second ordered development record.",
            },
        ]

    def test_composition_has_exact_prefix_and_original_definitions(self):
        self.assertEqual(hashlib.sha256(self.frozen).hexdigest(), FROZEN_SEED_SHA256)
        self.assertTrue(self.source.startswith(self.frozen))
        self.assertEqual(compose_source_seed(self.frozen), self.source)
        self.assertLessEqual(len(self.source), 1024**2)
        original = ast.parse(self.frozen)
        composed = ast.parse(self.source)
        for before, after in zip(original.body, composed.body[: len(original.body)], strict=True):
            self.assertEqual(ast.dump(before), ast.dump(after))
        self.assertEqual(
            self.module.generate.__code__.co_code, frozen_seed.generate.__code__.co_code
        )
        imports = [
            node for node in ast.walk(composed) if isinstance(node, (ast.Import, ast.ImportFrom))
        ]
        self.assertEqual(
            [ast.dump(node) for node in imports],
            [
                ast.dump(node)
                for node in ast.walk(original)
                if isinstance(node, (ast.Import, ast.ImportFrom))
            ],
        )
        self.assertTrue(callable(self.module.propose_improvement))

    def test_factory_rejects_wrong_type_changed_invalid_or_oversized_seed(self):
        class Bytes(bytes):
            pass

        for value in (
            "source",
            bytearray(self.frozen),
            Bytes(self.frozen),
            b"\xff",
            b"x" * (1024**2 + 1),
            self.frozen + b"\n",
            self.frozen.replace(b"generate", b"GENERATE", 1),
        ):
            with self.subTest(kind=type(value).__name__, length=len(value)):
                with self.assertRaises(SourceSeedError):
                    compose_source_seed(value)

    def test_generation_requests_answers_and_history_remain_exact(self):
        task = {"id": "dev", "prompt": "Literal form. é 雪", "count": 4}
        for provider in ("openai", "anthropic"):
            for sampling in ("regenerate", "in-context"):
                with self.subTest(provider=provider, sampling=sampling):
                    config = configuration(provider, sampling)
                    texts = [" first \n", "", "refused text", "partial literal"]
                    replies = [
                        response(
                            provider,
                            text,
                            refused=index == 2,
                            finish=("length" if provider == "openai" else "max_tokens")
                            if index == 3
                            else None,
                        )
                        for index, text in enumerate(texts)
                    ]
                    expected_calls, actual_calls = [], []

                    def callback(calls, selected_replies=replies):
                        def invoke(selected, body):
                            index = len(calls)
                            calls.append((selected, body))
                            return copy.deepcopy(selected_replies[index])

                        return invoke

                    expected = frozen_seed.generate(task, config, callback(expected_calls))
                    actual = self.module.generate(task, config, callback(actual_calls))
                    self.assertEqual(actual, expected)
                    self.assertEqual(actual_calls, expected_calls)
                    self.assertEqual(
                        actual, [" first \n", "[empty]", "[refused]", "partial literal"]
                    )

    def test_proposal_uses_one_provider_callback_full_parent_and_ordered_feedback(self):
        proposal = {"source": CHILD, "hypothesis": "Change actual selection control flow. 雪"}
        for provider in ("openai", "anthropic"):
            with self.subTest(provider=provider):
                config = configuration(provider)
                complete = Mock(return_value=response(provider, json.dumps(proposal)))
                parent, feedback = copy.deepcopy(self.parent), copy.deepcopy(self.feedback)
                # Returned child source is data, even on this explicitly trusted unit path.
                with patch(
                    "builtins.compile", side_effect=AssertionError("child compile forbidden")
                ):
                    result = self.module.propose_improvement(parent, feedback, config, complete)
                self.assertEqual(result, proposal)
                complete.assert_called_once()
                selected, raw = complete.call_args.args
                self.assertEqual(selected, provider)
                body = json.loads(raw)
                self.assertEqual(body["model"], config["model"])
                prompt = body["messages"][-1]["content"]
                if provider == "anthropic":
                    prompt = prompt[0]["text"]
                instruction, payload = prompt.split("\n\nINPUT_JSON\n", 1)
                self.assertIn("procedure", instruction)
                self.assertIn("original task", instruction)
                self.assertIn("causes", instruction)
                self.assertIn("propose_improvement", instruction)
                self.assertIn("host", instruction)
                self.assertEqual(
                    json.loads(payload),
                    {
                        "format": FRAGMENT_VERSION,
                        "parent": parent,
                        "development_feedback": feedback,
                    },
                )
                self.assertEqual(parent, self.parent)
                self.assertEqual(feedback, self.feedback)
                self.assertEqual(
                    body["max_completion_tokens" if provider == "openai" else "max_tokens"],
                    config["max_output_tokens"],
                )
                self.assertEqual(
                    body["service_tier"], "default" if provider == "openai" else "standard_only"
                )

    def test_callback_failure_escapes_once_without_retry(self):
        error = RuntimeError("synthetic callback stop")
        complete = Mock(side_effect=error)
        with self.assertRaises(RuntimeError) as caught:
            self.module.propose_improvement(self.parent, self.feedback, configuration(), complete)
        self.assertIs(caught.exception, error)
        complete.assert_called_once()

    def test_malformed_duplicate_nonfinite_and_fenced_proposals_reject_once(self):
        values = [
            "not json",
            "```json\n{}\n```",
            "[]",
            "null",
            "NaN",
            '{"source":"a","source":"b","hypothesis":"x"}',
            '{"source":Infinity,"hypothesis":"x"}',
            '{"source":"a","hypothesis":-Infinity}',
            '{"source":"a","hypothesis":"x","extra":true}',
        ]
        for text in values:
            with self.subTest(text=text[:80]):
                complete = Mock(return_value=response("openai", text))
                with self.assertRaises(self.module.SeedError):
                    self.module.propose_improvement(
                        self.parent, self.feedback, configuration(), complete
                    )
                complete.assert_called_once()

    def test_refused_truncated_empty_and_bad_protocol_replies_reject_once(self):
        text = json.dumps({"source": CHILD, "hypothesis": "Changed."})
        for provider in ("openai", "anthropic"):
            replies = [
                response(provider, text, refused=True),
                response(provider, text, finish="length" if provider == "openai" else "max_tokens"),
                response(provider, " "),
                response(provider, text, finish="unsupported"),
                {"model": "wrong", "usage": {}},
                response(provider, text, finish="end_turn" if provider == "openai" else "stop"),
            ]
            for index, reply in enumerate(replies):
                with self.subTest(provider=provider, case=index):
                    complete = Mock(return_value=reply)
                    with self.assertRaises(self.module.SeedError):
                        self.module.propose_improvement(
                            self.parent, self.feedback, configuration(provider), complete
                        )
                    complete.assert_called_once()

    def test_invalid_parent_refuses_before_callback(self):
        changes = [
            {"entrypoint": "elsewhere.py"},
            {"source": ""},
            {"source": "\ud800"},
            {"source": "x" * (1024**2 + 1)},
            {"agent_sha256": ""},
            {"agent_sha256": "A" * 64},
            {"extra": "not a parent"},
        ]
        for change in changes:
            with self.subTest(fields=list(change)):
                complete = Mock()
                with self.assertRaises(self.module.SeedError):
                    self.module.propose_improvement(
                        self.parent | change, self.feedback, configuration(), complete
                    )
                complete.assert_not_called()

    def test_parent_entrypoint_requires_exact_literal_text(self):
        class Text(str):
            pass

        complete = Mock(
            return_value=response("openai", json.dumps({"source": CHILD, "hypothesis": "Changed."}))
        )
        with self.assertRaises(self.module.SeedError):
            self.module.propose_improvement(
                self.parent | {"entrypoint": Text("candidate.py")},
                self.feedback,
                configuration(),
                complete,
            )
        complete.assert_not_called()

    def test_config_limits_and_noncallable_callback_refuse_without_request(self):
        changes = [
            {"provider": "other"},
            {"model": " "},
            {"max_output_tokens": 0},
            {"max_output_tokens": True},
            {"max_output_tokens": 2**63},
            {"instructions": "x" * 4001},
            {"sampling": "other"},
            {"extra": "not config"},
        ]
        for change in changes:
            with self.subTest(fields=list(change)):
                complete = Mock()
                with self.assertRaises(self.module.SeedError):
                    self.module.propose_improvement(
                        self.parent, self.feedback, configuration() | change, complete
                    )
                complete.assert_not_called()
        with self.assertRaises(self.module.SeedError):
            self.module.propose_improvement(self.parent, self.feedback, configuration(), None)

    def test_feedback_shapes_ids_note_and_task_bounds_refuse_before_callback(self):
        first = self.feedback[0]
        values = [
            [],
            tuple(self.feedback),
            [first, first],
            [first | {"note": " "}],
            [first | {"note": "é" * 2049}],
            [first | {"note": "\ud800"}],
            [first | {"extra": 1}],
            [first | {"task": first["task"] | {"id": True}}],
            [first | {"task": first["task"] | {"count": 0}}],
            [first | {"task": first["task"] | {"count": 1001}}],
            [first | {"task": first["task"] | {"prompt": " "}}],
            [first] * 1001,
        ]
        for index, feedback in enumerate(values):
            with self.subTest(case=index):
                module = self.module
                if index == 4:
                    # This specific 4096-byte ceiling belongs to the historical fragment.
                    module = ModuleType("_trusted_legacy_source_seed")
                    source = compose_source_seed(
                        self.frozen, fragment_version="buddha.source-seed-improver.v1"
                    )
                    exec(compile(source, "<trusted-legacy-seed>", "exec"), vars(module))  # nosec B102
                complete = Mock()
                with self.assertRaises(module.SeedError):
                    module.propose_improvement(self.parent, feedback, configuration(), complete)
                complete.assert_not_called()

    def test_full_feedback_projection_bound_refuses_before_callback(self):
        feedback = copy.deepcopy(self.feedback)
        feedback[0]["task"]["prompt"] = "x" * 1024**2
        complete = Mock()
        with self.assertRaises(self.module.SeedError):
            self.module.propose_improvement(self.parent, feedback, configuration(), complete)
        complete.assert_not_called()

    def test_escaped_worker_projection_bound_precedes_callback(self):
        feedback = copy.deepcopy(self.feedback)
        feedback[0]["task"]["prompt"] = "雪" * 180000
        self.assertLess(len(feedback[0]["task"]["prompt"].encode()), 1024**2)
        self.assertGreater(len(json.dumps(feedback).encode()), 1024**2)
        complete = Mock(
            return_value=response("openai", json.dumps({"source": CHILD, "hypothesis": "Changed."}))
        )
        with self.assertRaises(self.module.SeedError):
            self.module.propose_improvement(self.parent, feedback, configuration(), complete)
        complete.assert_not_called()

    def test_proposal_source_and_utf8_hypothesis_bounds(self):
        valid = {"source": CHILD, "hypothesis": "é" * 2048}
        complete = Mock(return_value=response("openai", json.dumps(valid)))
        self.assertEqual(
            self.module.propose_improvement(self.parent, self.feedback, configuration(), complete),
            valid,
        )
        for proposal in (
            {"source": "", "hypothesis": "x"},
            {"source": "x" * (1024**2 + 1), "hypothesis": "x"},
            {"source": CHILD, "hypothesis": "é" * 2049},
            {"source": CHILD, "hypothesis": " "},
            {"source": self.parent["source"], "hypothesis": "Unchanged."},
            {"source": 1, "hypothesis": "x"},
            {"source": CHILD, "hypothesis": "\ud800"},
        ):
            with self.subTest(
                source_type=type(proposal["source"]).__name__,
                hypothesis_length=len(proposal["hypothesis"]),
            ):
                complete = Mock(return_value=response("openai", json.dumps(proposal)))
                with self.assertRaises(self.module.SeedError):
                    self.module.propose_improvement(
                        self.parent, self.feedback, configuration(), complete
                    )
                complete.assert_called_once()

    def test_invalid_python_proposal_is_returned_as_data_without_compilation(self):
        proposal = {
            "source": "this is deliberately invalid Python [",
            "hypothesis": "Literal proposal retained.",
        }
        complete = Mock(return_value=response("openai", json.dumps(proposal)))
        with patch("builtins.compile", side_effect=AssertionError("child compile forbidden")):
            self.assertEqual(
                self.module.propose_improvement(
                    self.parent, self.feedback, configuration(), complete
                ),
                proposal,
            )


if __name__ == "__main__":
    unittest.main()
