"""Supplied recipe and executor metadata only; no frozen data or Docker."""

import copy
import importlib.util
import json
import tempfile
import unittest
from dataclasses import asdict
from pathlib import Path

SCRIPT = Path(__file__).resolve().parents[1] / "docs/conformance/prepare-fresh-plain-references.py"
spec = importlib.util.spec_from_file_location("supplied_plain_builder", SCRIPT)
builder = importlib.util.module_from_spec(spec)
spec.loader.exec_module(builder)


def require(value, code):
    if not value:
        raise ValueError(code)


class FreshPlainReferenceTests(unittest.TestCase):
    def test_parent_inventory_accepts_both_separator_spellings_and_refuses_aliases(self):
        for key in ("inputs/source.json", "inputs\\source.json"):
            for leaf in ("inputs/source.json", "inputs\\source.json"):
                with self.subTest(key=key, leaf=leaf):
                    self.assertEqual(
                        builder.inventory_pin({key: "bound-pin"}, leaf, require), "bound-pin"
                    )
        with self.assertRaisesRegex(ValueError, "missing_or_ambiguous"):
            builder.inventory_pin(
                {"inputs/source.json": "same", "inputs\\source.json": "same"},
                "inputs/source.json",
                require,
            )
        with self.assertRaisesRegex(ValueError, "missing_or_ambiguous"):
            builder.inventory_pin({"inputs/foreign.json": "other"}, "inputs/source.json", require)

    def fixture(self):
        return {
            "generation": {
                "config": {
                    "provider": "openai",
                    "model": "supplied-backbone",
                    "max_output_tokens": 4096,
                    "instructions": "Buddha instructions",
                    "sampling": "in-context",
                },
                "budget_microusd": 7,
                "max_calls": 10,
                "profile": {"capability": "openai_text", "profile_id": "seed"},
            },
            "native": {
                "budget_microusd": 13,
                "max_calls": 11,
                "hooks": {"unchanged": True},
                "profiles": {"same": "judges"},
            },
        }

    def test_both_modes_aggregate_both_envelopes_without_mutating_primary(self):
        primary = self.fixture()
        before = copy.deepcopy(primary)
        configs = []
        for mode in builder.MODES:
            generation, native, config = builder.plain_sections(primary, mode, 26, 260, require)
            self.assertEqual((generation["budget_microusd"], generation["max_calls"]), (182, 260))
            self.assertEqual((native["budget_microusd"], native["max_calls"]), (338, 286))
            self.assertEqual(native["hooks"], primary["native"]["hooks"])
            self.assertEqual(native["profiles"], primary["native"]["profiles"])
            builder.matching_config(primary["generation"]["config"], config, mode, require)
            self.assertEqual(config["instructions"], "")
            self.assertEqual(config["max_output_tokens"], 4096)
            configs.append(config)
        self.assertEqual(primary, before)
        self.assertNotEqual(configs[0], configs[1])
        self.assertEqual(set(configs[0]), set(configs[1]))

    def test_insufficient_calls_and_foreign_model_mode_or_instructions_refuse(self):
        primary = self.fixture()
        primary["generation"]["max_calls"] = 9
        with self.assertRaisesRegex(ValueError, "plain_answer_call_ceiling"):
            builder.plain_sections(primary, "regenerate", 26, 260, require)
        primary = self.fixture()
        _, _, config = builder.plain_sections(primary, "regenerate", 26, 260, require)
        for field, value in (
            ("provider", "anthropic"),
            ("model", "foreign"),
            ("max_output_tokens", 8192),
            ("instructions", "hidden harness"),
            ("sampling", "in-context"),
        ):
            with (
                self.subTest(field=field),
                self.assertRaisesRegex(ValueError, "plain_model_or_mode_changed"),
            ):
                builder.matching_config(
                    primary["generation"]["config"], config | {field: value}, "regenerate", require
                )

    def test_existing_executor_metadata_rejects_foreign_mount_worker_or_remote_endpoint(self):
        from buddha import executor

        folder = tempfile.TemporaryDirectory()
        self.addCleanup(folder.cleanup)
        base = Path(folder.name).resolve()
        agent, runner = base / "agent", base / "runner"
        agent.mkdir()
        (runner / "buddha").mkdir(parents=True)
        (runner / "buddha/agent_worker.py").write_bytes(b"# Supplied worker, never executed.\n")
        settings = {
            "image_id": "sha256:" + "a" * 64,
            "role": "agent",
            "mounts": [["/agent", str(agent)], ["/runner", str(runner)]],
            "runner_entrypoint": "buddha/agent_worker.py",
            "image_environment": [],
            "limits": asdict(executor.Limits()),
            "docker_endpoint": "unix:///var/run/docker.sock",
        }
        builder.validate_executor(settings, agent, runner, executor, require)
        for field, value in (
            ("mounts", settings["mounts"] + [["/host", str(base)]]),
            ("runner_entrypoint", "buddha/candidate_worker.py"),
            ("docker_endpoint", "tcp://foreign:2375"),
        ):
            with self.subTest(field=field), self.assertRaises(ValueError):
                builder.validate_executor(
                    settings | {field: value}, agent, runner, executor, require
                )

    def test_failure_frames_keep_suppressed_public_context_without_messages_or_locals(self):
        canary = "supplied-private-message-do-not-emit"
        try:
            try:
                raise KeyError(canary)
            except KeyError:
                raise ValueError(canary) from None
        except ValueError as error:
            result = builder.public_frames(
                error, {Path(__file__).absolute(): "supplied_public_test"}
            )
        encoded = json.dumps(result)
        self.assertNotIn(canary, encoded)
        self.assertEqual(len(result), 2)
        self.assertTrue(all(row["frames"] for row in result))
        self.assertTrue(
            all(
                set(frame) == {"module", "function", "line"}
                for row in result
                for frame in row["frames"]
            )
        )


if __name__ == "__main__":
    unittest.main()
