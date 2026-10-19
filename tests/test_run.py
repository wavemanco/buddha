"""Slice 2 end-to-end acceptance: no credentials or network needed."""

import hashlib
import json
import tempfile
import unittest
from dataclasses import replace
from pathlib import Path

from authorization_helpers import authorized_run

from buddha.authorization import Authorization, runtime_fingerprint
from buddha.benchmark import Prompt
from buddha.evaluation import ValidationError
from buddha.ledger import Ledger
from buddha.provider import BudgetBroker, HTTPTransport, ModelSpec, Reply
from buddha.run import (
    ReplayTransport,
    RunSettings,
    _generation,
    _protocol,
    _sha,
    evaluate_prompts,
    operation_executor,
    prepare_run,
    run_baseline,
)


def settings():
    profiles = [
        ModelSpec("replay", model, 100000, cap, 1000000, 1000000, "offline fixture")
        for model, cap in [("generator", 4096), ("partition", 16000), ("quality", 16000)]
    ]
    return RunSettings(*profiles, budget_microusd=1000000, max_calls=64, bounds_verified=False)


class BaselineRunTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)
        self.dataset = self.root / "prompts.jsonl"
        self.dataset.write_text(
            json.dumps({"id": "example-1", "prompt": "Offer a useful alternative."}) + "\n",
            encoding="utf-8",
        )
        self.dataset_hash = hashlib.sha256(self.dataset.read_bytes()).hexdigest()
        self.destination = self.root / "run"

    def prepare(self, selected=None):
        return prepare_run(
            self.destination,
            dataset_path=self.dataset,
            expected_dataset_sha256=self.dataset_hash,
            settings=settings() if selected is None else selected,
            synthetic=True,
        )

    def test_complete_offline_pipeline_and_resume_make_no_duplicate_calls(self):
        self.prepare()
        transport = ReplayTransport()
        summary = run_baseline(self.destination, transport=transport)
        self.assertEqual(summary.scored_count, 1)
        self.assertEqual(summary.mean_distinct, 1)
        self.assertEqual(transport.calls, 12)
        resumed = run_baseline(self.destination, transport=transport)
        self.assertEqual(resumed, summary)
        self.assertEqual(transport.calls, 12)
        for relative in [
            "generations.jsonl",
            "v1.1/partitions.jsonl",
            "v1.1/scores.jsonl",
            "v1.1/summary.json",
            "provenance.json",
        ]:
            self.assertTrue((self.destination / "evaluation" / relative).is_file())

    def test_corrupt_dataset_and_unknown_prompt_ids_fail_before_run_creation(self):
        for changes in [
            {"expected_dataset_sha256": "0" * 64},
            {"prompt_ids": ["missing"]},
            {"prompt_ids": ["example-1", "example-1"]},
        ]:
            args = {
                "dataset_path": self.dataset,
                "expected_dataset_sha256": self.dataset_hash,
                "settings": settings(),
                "synthetic": True,
            } | changes
            with self.subTest(changes=changes), self.assertRaises(ValidationError):
                prepare_run(self.destination, **args)
            self.assertFalse(self.destination.exists())

    def test_completed_replay_does_not_preflight_credentials(self):
        self.prepare()
        manifest = json.loads((self.destination / "manifest.json").read_text())
        selected = settings()
        Ledger(
            self.destination / "operations.sqlite3",
            run_id=manifest["run_id"],
            manifest_sha256=_sha(manifest),
            budget_microusd=selected.budget_microusd,
            max_calls=selected.max_calls,
        )
        authority = Authorization.create(
            self.root / "authorization.sqlite3",
            authorization_id="cached-replay",
            budget_microusd=selected.budget_microusd,
            max_calls=selected.max_calls,
            scope="offline cached-receipt integration fixture",
        )
        authority.bind_run(self.destination, runtime_sha256=runtime_fingerprint())
        expected = run_baseline(
            self.destination, transport=ReplayTransport(), authorization=authority
        )
        actual = run_baseline(
            self.destination,
            transport=HTTPTransport(allow_paid=False),
            authorization=authority,
        )
        self.assertEqual(expected, actual)

    def test_embedded_prompt_substitution_cannot_claim_verified_dataset(self):
        self.prepare()
        path = self.destination / "manifest.json"
        manifest = json.loads(path.read_text(encoding="utf-8"))
        manifest["prompts"][0]["prompt"] = "A substituted task."
        canonical = json.dumps(manifest["prompts"], sort_keys=True, separators=(",", ":")).encode()
        manifest["protocol"]["split_sha256"] = hashlib.sha256(canonical).hexdigest()
        path.write_text(json.dumps(manifest), encoding="utf-8")
        transport = ReplayTransport()
        with self.assertRaises(ValidationError):
            run_baseline(self.destination, transport=transport)
        self.assertEqual(transport.calls, 0)

    def test_manifest_tampering_after_dispatch_cannot_reset_accounting(self):
        self.prepare()
        run_baseline(self.destination, transport=ReplayTransport())
        path = self.destination / "manifest.json"
        manifest = json.loads(path.read_text(encoding="utf-8"))
        manifest["settings"]["budget_microusd"] += 1
        path.write_text(json.dumps(manifest), encoding="utf-8")
        with self.assertRaises(ValidationError):
            run_baseline(self.destination, transport=ReplayTransport())

    def test_synthetic_dataset_cannot_be_labeled_as_an_official_run(self):
        with self.assertRaises(ValidationError):
            prepare_run(
                self.destination,
                dataset_path=self.dataset,
                expected_dataset_sha256=self.dataset_hash,
                settings=settings(),
                synthetic=False,
            )

    def test_invalid_judge_response_is_billed_and_not_reissued(self):
        class BadJudge(ReplayTransport):
            def send(self, call):
                reply = super().send(call)
                if call.spec.model == "partition":
                    return replace(reply, text='{"groups":[[0,0]]}')
                return reply

        self.prepare()
        transport = BadJudge()
        for _ in range(2):
            with self.assertRaises(ValidationError):
                run_baseline(self.destination, transport=transport)
        self.assertEqual(transport.calls, 11)
        self.assertFalse((self.destination / "evaluation").exists())

    def test_interruption_after_one_generation_stops_ambiguous_reissue(self):
        class Interrupting(ReplayTransport):
            def send(self, call):
                if self.calls == 1:
                    raise KeyboardInterrupt
                return super().send(call)

        self.prepare()
        with self.assertRaises(KeyboardInterrupt):
            run_baseline(self.destination, transport=Interrupting())
        with self.assertRaises(ValidationError):
            run_baseline(self.destination, transport=ReplayTransport())

    def test_empty_generation_attempts_are_preserved(self):
        class EmptyGenerator(ReplayTransport):
            def send(self, call):
                reply = super().send(call)
                if call.spec.model == "generator":
                    return Reply(
                        "",
                        reply.model,
                        reply.provider_request_id,
                        reply.input_tokens,
                        reply.output_tokens,
                        "stop",
                        False,
                    )
                return reply

        self.prepare()
        run_baseline(self.destination, transport=EmptyGenerator())
        path = self.destination / "evaluation" / "generations.jsonl"
        row = json.loads(path.read_text(encoding="utf-8"))
        self.assertEqual(row["generations"], ["[empty]"] * 10)

    def test_no_live_execution_without_explicit_gate_and_verified_bounds(self):
        offline = settings()
        live = replace(
            offline,
            generation=replace(
                offline.generation,
                provider="openai",
                model="gpt-5.6-luna",
                bounds_source="https://developers.openai.com/api/docs/models/gpt-5.6-luna",
            ),
            partition=replace(
                offline.partition,
                provider="openai",
                model="gpt-5.6-luna",
                bounds_source="https://developers.openai.com/api/docs/models/gpt-5.6-luna",
            ),
            quality=replace(
                offline.quality,
                provider="anthropic",
                model="claude-opus-5",
                bounds_source="https://platform.claude.com/docs/en/about-claude/models/overview",
            ),
        )
        self.prepare(live)
        transport = ReplayTransport()
        for allow_paid in [False, True]:
            with self.subTest(allow_paid=allow_paid), self.assertRaises(ValidationError):
                run_baseline(self.destination, transport=transport, allow_paid=allow_paid)
        self.assertEqual(transport.calls, 0)


class SharedExecutionTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)

    def broker(self, transport):
        if isinstance(transport, HTTPTransport):
            _, ledger = authorized_run(self.root / "run", budget_microusd=1000000, max_calls=64)
            return BudgetBroker(ledger, transport)
        return BudgetBroker(
            Ledger(
                self.root / "operations.sqlite3",
                run_id="run",
                manifest_sha256="0" * 64,
                budget_microusd=1000000,
                max_calls=64,
            ),
            transport,
        )

    def test_default_generation_call_preserves_baseline_request(self):
        body = json.loads(_generation(settings().generation, "A literal task.").body_json)
        self.assertEqual(
            body,
            {
                "model": "generator",
                "messages": [{"role": "user", "content": "A literal task."}],
                "max_completion_tokens": 4096,
                "reasoning_effort": "low",
                "service_tier": "default",
            },
        )

    def test_in_context_generation_preserves_original_task_and_actual_prior_answers(self):
        model = settings().generation
        call = _generation(
            model, "Reply with one digit.", instructions="Preserve task form.", history=("1", "")
        )
        body = json.loads(call.body_json)
        self.assertEqual(
            body["messages"],
            [
                {"role": "system", "content": "Preserve task form."},
                {"role": "user", "content": "Reply with one digit."},
                {"role": "assistant", "content": "1"},
                {"role": "user", "content": "Can you generate a different answer?"},
                {"role": "assistant", "content": ""},
                {"role": "user", "content": "Can you generate a different answer?"},
            ],
        )

    def test_anthropic_history_caches_only_last_user_and_uses_top_level_system(self):
        model = replace(
            settings().generation, provider="anthropic", bounds_source="https://example.org/bounds"
        )
        body = json.loads(
            _generation(
                model, "Original task", instructions="Follow the task.", history=["Actual response"]
            ).body_json
        )
        self.assertEqual(body["system"], "Follow the task.")
        self.assertEqual(
            body["messages"],
            [
                {"role": "user", "content": "Original task"},
                {"role": "assistant", "content": "Actual response"},
                {
                    "role": "user",
                    "content": [
                        {
                            "type": "text",
                            "text": "Can you generate a different answer?",
                            "cache_control": {"type": "ephemeral"},
                        }
                    ],
                },
            ],
        )

    def test_generation_inputs_are_validated_before_request_construction(self):
        for changes in [
            {"instructions": None},
            {"instructions": "\ud800"},
            {"history": "text"},
            {"history": [None]},
            {"history": ["\ud800"]},
        ]:
            with self.subTest(changes=repr(changes)), self.assertRaises(ValidationError):
                _generation(settings().generation, "Original task", **changes)

    def test_executor_namespace_is_frozen_and_replays_without_duplicate_calls(self):
        transport = ReplayTransport()
        broker = self.broker(transport)
        namespace = ["run", {"candidate": 1}]
        execute = operation_executor(broker, settings(), namespace=namespace)
        namespace[1]["candidate"] = 2
        call = _generation(settings().generation, "Original task")
        first = execute("dev-1", "generation", 0, call)
        expected_id = _sha(["run", {"candidate": 1}, "dev-1", "generation", 0])
        self.assertEqual(broker.ledger.get(expected_id).status, "completed")
        self.assertEqual(execute("dev-1", "generation", 0, call), first)
        other = operation_executor(broker, settings(), namespace=("run", {"candidate": 2}))
        other("dev-1", "generation", 0, call)
        self.assertEqual(transport.calls, 2)

    def test_executor_checks_all_roles_before_dispatch_and_completed_replay_needs_no_keys(self):
        class RecordingHTTP(HTTPTransport):
            def __init__(self):
                super().__init__(allow_paid=False)
                self.checked = []

            def preflight(self, call):
                self.checked.append(call.spec.model)
                if call.spec.model == "quality":
                    raise ValidationError("quality credential missing")

            def send(self, call):
                raise AssertionError("preflight failure must prevent dispatch")

        transport = RecordingHTTP()
        broker = self.broker(transport)
        execute = operation_executor(broker, settings(), namespace=("run",))
        with self.assertRaises(ValidationError):
            execute("dev-1", "generation", 0, _generation(settings().generation, "Task"))
        self.assertEqual(transport.checked, ["generator", "partition", "quality"])
        self.assertEqual(broker.ledger.totals()["operation_count"], 0)

    def test_shared_evaluator_supplies_upstream_normalized_history_and_keeps_full_coverage(self):
        configured = settings()
        prompts = (Prompt("dev-1", "Reply with one digit."),)
        protocol = _protocol(configured, "0" * 64, prompts)
        previous = []
        transport = ReplayTransport()

        def generate(prompt, history):
            self.assertIsInstance(history, tuple)
            previous.append(history)
            return _generation(configured.generation, prompt.prompt, history=history)

        def execute(prompt_id, stage, index, call):
            reply = transport.send(call)
            if stage == "generation":
                if index == 1:
                    return replace(reply, text="Provider refusal details", refused=True)
                return replace(reply, text="" if index == 0 else str(index))
            return reply

        rows = evaluate_prompts(
            prompts, settings=configured, protocol=protocol, execute=execute, generate=generate
        )
        self.assertEqual(previous[0], ())
        self.assertEqual(previous[1], ("[empty]",))
        self.assertEqual(previous[2], ("[empty]", "[refused]"))
        self.assertEqual(previous[9], ("[empty]", "[refused]", "2", "3", "4", "5", "6", "7", "8"))
        self.assertEqual(rows[0]["generations"], ["[empty]", "[refused]", *map(str, range(2, 10))])
        self.assertEqual(rows[0]["distinct"], 1)
        self.assertEqual(transport.calls, 12)

    def test_generation_callback_cannot_change_model_or_request_accounting_bounds(self):
        configured = settings()
        prompts = (Prompt("dev-1", "Original task"),)
        protocol = _protocol(configured, "0" * 64, prompts)
        transport = ReplayTransport()
        for altered in [
            replace(configured.generation, model="different-model"),
            replace(configured.generation, max_output_tokens=2048),
            replace(configured.generation, input_microusd_per_million=1),
            None,
        ]:
            with self.subTest(altered=altered), self.assertRaises(ValidationError):
                evaluate_prompts(
                    prompts,
                    settings=configured,
                    protocol=protocol,
                    execute=lambda prompt_id, stage, index, call: transport.send(call),
                    generate=lambda prompt, previous, altered=altered: (
                        None if altered is None else _generation(altered, prompt.prompt)
                    ),
                )
            self.assertEqual(transport.calls, 0)

    def test_invalid_unicode_stops_after_first_billed_generation_and_preserves_receipt(self):
        class InvalidUnicode(ReplayTransport):
            def send(self, call):
                return replace(super().send(call), text="\ud800")

        configured = settings()
        prompts = (Prompt("dev-1", "Original task"),)
        protocol = _protocol(configured, "0" * 64, prompts)
        transport = InvalidUnicode()
        broker = self.broker(transport)
        execute = operation_executor(broker, configured, namespace=("run",))
        with self.assertRaises(ValidationError):
            evaluate_prompts(prompts, settings=configured, protocol=protocol, execute=execute)
        self.assertEqual(transport.calls, 1)
        saved = broker.ledger.get(_sha(["run", "dev-1", "generation", 0]))
        self.assertEqual(saved.status, "completed")
        self.assertEqual(saved.response["text"], "\ud800")


if __name__ == "__main__":
    unittest.main()
