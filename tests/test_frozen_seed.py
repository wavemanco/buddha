"""Frozen generation recipe compared with the real historical request/reply path."""

import ast
import copy
import json
import unittest
from pathlib import Path
from unittest.mock import Mock

from agents import frozen_seed
from agents.frozen_seed import SeedError, generate, normalize, request
from buddha.policy import Policy
from buddha.provider import HTTPTransport, ModelSpec
from buddha.run import _generation


def configuration(provider="openai", sampling="regenerate", instructions=""):
    return {
        "provider": provider,
        "model": "synthetic-seed-model",
        "max_output_tokens": 100,
        "instructions": instructions,
        "sampling": sampling,
    }


def task(count=2, **changes):
    return {
        "id": "selected-task",
        "prompt": "One literal answer: café 🌱.\n",
        "count": count,
    } | changes


def response(provider, text=" answer \n", finish=None, refusal=None):
    if provider == "openai":
        return {
            "model": "synthetic-seed-model",
            "choices": [
                {
                    "message": {"content": text, "refusal": refusal},
                    "finish_reason": finish or "stop",
                }
            ],
            "usage": {"prompt_tokens": 3, "completion_tokens": 2},
        }
    return {
        "model": "synthetic-seed-model",
        "content": [{"type": "text", "text": text}],
        "stop_reason": finish or "end_turn",
        "usage": {"input_tokens": 3, "output_tokens": 2},
    }


def legacy_request(config, selected, previous):
    model = ModelSpec(
        config["provider"],
        config["model"],
        1000,
        config["max_output_tokens"],
        1,
        1,
        "https://example.org/synthetic-bounds",
    )
    return _generation(
        model,
        selected["prompt"],
        instructions=config["instructions"],
        history=previous if config["sampling"] == "in-context" else (),
    ).body_json.encode("utf-8")


def legacy_answer(provider, raw):
    reply = HTTPTransport._reply(provider, raw, "synthetic-request")
    return "[refused]" if reply.refused else (reply.text if reply.text.strip() else "[empty]")


class FrozenSeedTests(unittest.TestCase):
    def test_exact_final_legacy_request_bytes_for_providers_modes_and_unicode(self):
        selected = task()
        previous = ["  déjà vu 🐕\n", "[empty]"]
        for provider in ["openai", "anthropic"]:
            for sampling in ["regenerate", "in-context"]:
                for instructions in ["", "Retain literal form. 雪\n"]:
                    with self.subTest(
                        provider=provider, sampling=sampling, instructions=instructions
                    ):
                        config = configuration(provider, sampling, instructions)
                        actual = request(config, selected, previous)
                        self.assertEqual(actual, legacy_request(config, selected, previous))
                        self.assertIn("café 🌱".encode(), actual)
                        self.assertNotIn(b"\\ud83c", actual)

    def test_empty_regenerate_baseline_matches_policy_default(self):
        policy = Policy()
        config = configuration()
        self.assertEqual(config["instructions"], policy.instructions)
        self.assertEqual(config["sampling"], policy.sampling)
        self.assertEqual(request(config, task()), legacy_request(config, task(), ()))
        body = json.loads(request(config, task()))
        self.assertEqual(body["messages"], [{"role": "user", "content": task()["prompt"]}])

    def test_count_two_and_ten_preserve_order_and_exact_history_for_each_provider_mode(self):
        texts = ["  first 🌱\n", "", "same", "same", "half sentence", "5", "bad answer"]
        for provider in ["openai", "anthropic"]:
            for sampling in ["regenerate", "in-context"]:
                for count in [2, 10]:
                    with self.subTest(provider=provider, sampling=sampling, count=count):
                        config, selected = configuration(provider, sampling), task(count)
                        raw = [
                            response(provider, texts[index % len(texts)]) for index in range(count)
                        ]
                        expected = [legacy_answer(provider, item) for item in raw]
                        complete = Mock(side_effect=raw)
                        self.assertEqual(generate(selected, config, complete), expected)
                        self.assertEqual(complete.call_count, count)
                        seen = []
                        for index, call in enumerate(complete.call_args_list):
                            self.assertEqual(
                                call.args,
                                (provider, legacy_request(config, selected, expected[:index])),
                            )
                            seen.append(call.args[1])
                        self.assertEqual(len(set(seen)), count if sampling == "in-context" else 1)

    def test_normalization_matches_legacy_for_every_accepted_finish_reason(self):
        finishes = [
            "stop",
            "end_turn",
            "length",
            "max_tokens",
            "model_context_window_exceeded",
            "content_filter",
            "refusal",
        ]
        for provider in ["openai", "anthropic"]:
            for finish in finishes:
                for text in ["  literal\n雪  ", "", " \t\r\n", "incomplete and", "same dog plot"]:
                    with self.subTest(provider=provider, finish=finish, text=text):
                        raw = response(provider, text, finish)
                        self.assertEqual(normalize(provider, raw), legacy_answer(provider, raw))

    def test_refusal_and_empty_placeholders_match_legacy_without_rewriting_raw_response(self):
        cases = [
            ("openai", response("openai", None)),
            ("openai", response("openai", "  answer  ", refusal="Cannot comply.")),
            ("openai", response("openai", "  answer  ", "content_filter")),
            ("anthropic", response("anthropic", "  answer  ", "refusal")),
        ]
        for provider, raw in cases:
            with self.subTest(provider=provider, raw=raw):
                before = copy.deepcopy(raw)
                self.assertEqual(normalize(provider, raw), legacy_answer(provider, raw))
                self.assertEqual(raw, before)
        self.assertEqual(normalize("openai", cases[0][1]), "[empty]")
        self.assertEqual(normalize("openai", cases[1][1]), "[refused]")

    def test_anthropic_text_blocks_are_joined_literally_and_thinking_is_not_an_answer(self):
        raw = response("anthropic")
        raw["content"] = [
            {"type": "thinking", "thinking": "private reasoning", "signature": "synthetic"},
            {"type": "text", "text": "  first\n"},
            {"type": "redacted_thinking", "data": "synthetic"},
            {"type": "text", "text": "second  "},
        ]
        self.assertEqual(normalize("anthropic", raw), legacy_answer("anthropic", raw))
        self.assertEqual(normalize("anthropic", raw), "  first\nsecond  ")

    def test_placeholders_and_duplicates_are_literal_next_request_history(self):
        for provider in ["openai", "anthropic"]:
            with self.subTest(provider=provider):
                config, selected = configuration(provider, "in-context"), task(4)
                replies = [
                    response(provider, " \n"),
                    response(
                        provider, "hidden", "content_filter" if provider == "openai" else "refusal"
                    ),
                    response(provider, "same"),
                    response(provider, "same"),
                ]
                complete = Mock(side_effect=replies)
                self.assertEqual(
                    generate(selected, config, complete), ["[empty]", "[refused]", "same", "same"]
                )
                seen = [call.args[1] for call in complete.call_args_list]
                self.assertTrue(all(call.args[0] == provider for call in complete.call_args_list))
                self.assertEqual(
                    seen[-1], legacy_request(config, selected, ["[empty]", "[refused]", "same"])
                )

    def test_config_and_task_require_exact_fields_and_valid_boundary_values_before_calls(self):
        bad_configs = [
            None,
            [],
            {},
            configuration() | {"extra": "forbidden"},
            {key: value for key, value in configuration().items() if key != "model"},
        ]
        for key, values in {
            "provider": [None, [], "replay", "unknown"],
            "model": [None, [], "", " \t", "\ud800"],
            "max_output_tokens": [None, True, 0, -1, 2**63, 1.5],
            "instructions": [None, [], "\ud800", "x" * 4001],
            "sampling": [None, [], "in_context", "unknown"],
        }.items():
            bad_configs.extend(configuration() | {key: value} for value in values)
        bad_tasks = [None, [], {}, task() | {"source": "host-only"}]
        for key, values in {
            "id": [None, True, [], "", " \t", "\x00", "x" * 4097, 2**63, -(2**63) - 1],
            "prompt": [None, [], "", " \t", "\ud800"],
            "count": [None, True, 0, -1, 1001, 1.5],
        }.items():
            bad_tasks.extend(task() | {key: value} for value in values)
        for config in bad_configs:
            complete = Mock()
            with self.subTest(config=repr(config)), self.assertRaises(SeedError):
                generate(task(), config, complete)
            complete.assert_not_called()
        for selected in bad_tasks:
            complete = Mock()
            with self.subTest(task=repr(selected)), self.assertRaises(SeedError):
                generate(selected, configuration(), complete)
            complete.assert_not_called()
        with self.assertRaises(SeedError):
            generate(task(), configuration(), None)

    def test_typed_ids_and_existing_numeric_boundaries_do_not_change_requests(self):
        config = configuration() | {"max_output_tokens": 2**63 - 1, "instructions": "雪" * 4000}
        for identifier in ["雪", 0, -(2**63), 2**63 - 1]:
            selected = task(1000, id=identifier)
            with self.subTest(identifier=identifier):
                self.assertEqual(request(config, selected), legacy_request(config, selected, ()))

    def test_history_requires_literal_utf8_text_without_mutating_inputs(self):
        config, selected, previous = configuration("anthropic", "in-context"), task(), [" \n"]
        before = copy.deepcopy((config, selected, previous))
        request(config, selected, previous)
        self.assertEqual((config, selected, previous), before)
        for invalid in [None, "answer", {}, [None], [1], ["\ud800"]]:
            with self.subTest(history=repr(invalid)), self.assertRaises(SeedError):
                request(config, selected, invalid)

    def test_generation_snapshots_config_and_task_before_untrusted_callback(self):
        config, selected = configuration("openai", "in-context"), task()
        original_config, original_task = copy.deepcopy((config, selected))
        bodies = []

        def complete(provider, body):
            self.assertEqual(provider, "openai")
            bodies.append(body)
            config["model"] = "mutated-model"
            config["sampling"] = "regenerate"
            selected["prompt"] = "mutated prompt"
            selected["count"] = 1000
            return response("openai", "same")

        self.assertEqual(generate(selected, config, complete), ["same", "same"])
        self.assertEqual(len(bodies), 2)
        self.assertEqual(bodies[1], legacy_request(original_config, original_task, ["same"]))

    def test_malformed_response_shapes_and_unknown_finish_do_not_return_answers(self):
        for provider in ["openai", "anthropic"]:
            bad = [
                None,
                [],
                {},
                response(provider) | {"model": None},
                response(provider) | {"usage": None},
            ]
            bad.extend(
                response(provider, finish=value)
                for value in ["tool_calls", "pause_turn", "future_status"]
            )
            if provider == "openai":
                bad.extend(
                    response(provider) | {"choices": value}
                    for value in [None, [], [{}, {}], [None]]
                )
                for change in [
                    {"message": None},
                    {"message": {}},
                    {"message": {"content": 0}},
                    {"message": {"content": []}},
                    {"message": {"content": "answer", "refusal": {}}},
                    {"finish_reason": None},
                    {"finish_reason": []},
                ]:
                    item = response(provider)
                    item["choices"][0].update(change)
                    bad.append(item)
                for change in [
                    {"prompt_tokens": True},
                    {"completion_tokens": -1},
                    {"prompt_tokens": 2**63},
                ]:
                    item = response(provider)
                    item["usage"].update(change)
                    bad.append(item)
            else:
                bad.extend(
                    response(provider) | {"content": value}
                    for value in [
                        None,
                        {},
                        [None],
                        [{}],
                        [{"type": "text"}],
                        [{"type": "text", "text": []}],
                        [{"type": "future_block"}],
                    ]
                )
                bad.extend(response(provider) | {"stop_reason": value} for value in [None, []])
                for change in [
                    {"input_tokens": True},
                    {"output_tokens": -1},
                    {"cache_read_input_tokens": 2**63},
                ]:
                    item = response(provider)
                    item["usage"].update(change)
                    bad.append(item)
            for raw in bad:
                with self.subTest(provider=provider, raw=repr(raw)), self.assertRaises(SeedError):
                    normalize(provider, raw)
        for provider in [None, [], "replay", "future-provider"]:
            with self.subTest(provider=provider), self.assertRaises(SeedError):
                normalize(provider, response("openai"))

    def test_malformed_utf8_response_and_later_failure_stop_without_retry_or_partial_return(self):
        for provider in ["openai", "anthropic"]:
            complete = Mock(side_effect=[response(provider, "first"), response(provider, "\ud800")])
            with self.subTest(provider=provider), self.assertRaises(SeedError):
                generate(task(10), configuration(provider), complete)
            self.assertEqual(complete.call_count, 2)

    def test_callback_errors_and_host_baseexception_escape_without_retry(self):
        class HostStop(BaseException):
            pass

        for error in [RuntimeError("synthetic failure"), HostStop()]:
            complete = Mock(side_effect=error)
            with self.subTest(error=type(error).__name__), self.assertRaises(type(error)):
                generate(task(10), configuration(), complete)
            self.assertEqual(complete.call_count, 1)

    def test_seed_has_only_stdlib_imports_and_no_file_network_or_environment_calls(self):
        tree = ast.parse(Path(frozen_seed.__file__).read_bytes())
        allowed = {"collections.abc", "json", "typing"}
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                self.assertTrue(all(alias.name in allowed for alias in node.names))
            elif isinstance(node, ast.ImportFrom):
                self.assertIn(node.module, allowed)
                self.assertEqual(node.level, 0)
            elif isinstance(node, ast.Call) and isinstance(node.func, ast.Name):
                self.assertNotIn(node.func.id, {"open", "exec", "eval", "compile", "__import__"})


if __name__ == "__main__":
    unittest.main()
