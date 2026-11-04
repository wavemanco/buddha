"""Supplied metadata only: no prepared inputs, accounts, workers or application calls."""

import copy
import importlib.util
import unittest
from pathlib import Path

SCRIPT = Path(__file__).resolve().parents[1] / "docs/conformance/prepare-fresh-combined.py"
spec = importlib.util.spec_from_file_location("supplied_combined_recipe", SCRIPT)
recipe = importlib.util.module_from_spec(spec)
spec.loader.exec_module(recipe)


def require(value, reason):
    if not value:
        raise ValueError(reason)


class FreshCombinedPreparationTests(unittest.TestCase):
    def fixture(self):
        assessment = {
            "phase_limits": {"search": {"budget_microusd": 1000, "max_calls": 10}},
            "generation": {
                "config": {
                    "provider": "openai",
                    "model": "supplied",
                    "max_output_tokens": 4096,
                    "instructions": "primary",
                    "sampling": "in-context",
                },
                "profile": {"capability": "openai.chat-completions.v1", "profile_id": "seed"},
                "selection": {"components": {"host": {"profiles.json": "b" * 64}}},
                "budget_microusd": 25,
                "max_calls": 12,
            },
            "native": {"instrument": "fixed-official", "budget_microusd": 30, "max_calls": 128},
            "stages": ["grouping", "quality", "summary"],
        }
        refs = {
            "assessment": {"path": "supplied-assessment", "sha256": "a" * 64},
            "task": {"path": "supplied-tasks", "sha256": "c" * 64},
        }
        handoff = {
            "format": "buddha.improver-handoff.v1",
            "assessment": refs["assessment"],
            "expected_runtime_sha256": "d" * 64,
            "directory": "absent-primary",
            "source_sha256": {"retained-control": "e" * 64},
        }
        checked = {
            "assessment_sha256": "a" * 64,
            "directory": "absent-primary",
            "funding": {"status": "unallocated"},
            "requested_phase_limits": assessment["phase_limits"],
            "reviewed_bindings": handoff["source_sha256"],
            "planned": {
                "starts": 2,
                "development_repetitions": 2,
                "opportunities_per_arm": 2,
                "development_tasks": 3,
                "final_tasks": 26,
                "sealed_repetitions": 1,
                "maximum_final_cells": 312,
            },
        }
        pairs = {}
        for mode in recipe.MODES:
            path = "supplied-" + mode + "-generation"
            refs[mode + "_generation"] = {"path": path, "sha256": "f" * 64}
            config = copy.deepcopy(assessment["generation"]["config"])
            config.update(instructions="", sampling=mode)
            generation = {
                "descriptor": path,
                "budget_microusd": 650,
                "max_calls": 312,
                "selection": {
                    "components": {
                        "agent": {"seed.py": recipe.SEED_SHA},
                        "host": {"profiles.json": "b" * 64},
                    }
                },
            }
            baseline = {
                "format": "buddha.native-baseline.v1",
                "tasks": "supplied-tasks",
                "generation": generation,
                "stages": assessment["stages"],
                "native": {
                    "instrument": "fixed-official",
                    "budget_microusd": 780,
                    "max_calls": 3328,
                },
            }
            frozen = {
                "format": "buddha.frozen-generation.v1",
                "entrypoint": "seed.py",
                "tasks": "supplied-tasks",
                "profile": assessment["generation"]["profile"],
                "config": config,
            }
            pairs[mode] = (baseline, frozen)
        return assessment, handoff, checked, pairs, refs

    def terms(self, fields):
        return recipe.metadata_terms(*fields, lambda native: native["instrument"], require)

    def test_terms_preserve_inputs_and_leave_all_allocations_unset(self):
        fields = self.fixture()
        before = copy.deepcopy(fields)
        terms = self.terms(fields)
        self.assertEqual(terms["funding_status"], "unallocated")
        self.assertIsNone(terms["shared_reference_allocation"])
        self.assertIsNone(terms["combined_allocation"])
        self.assertEqual(
            terms["plain_nominal_owner_envelopes"]["regenerate"]["generation"],
            {"budget_microusd": 650, "max_calls": 312},
        )
        terms["primary_phase_limits"]["search"]["budget_microusd"] = 999
        self.assertEqual(fields, before)

    def test_wrong_assessment_funding_or_inherited_binding_refuses(self):
        for mutation in ("assessment", "funding", "binding", "directory", "scope"):
            fields = self.fixture()
            if mutation == "assessment":
                fields[1]["assessment"] = {"path": "wrong", "sha256": "a" * 64}
            elif mutation == "funding":
                fields[2]["funding"] = {"status": "allocated"}
            elif mutation == "binding":
                fields[2]["reviewed_bindings"] = {"retained-control": "0" * 64}
            elif mutation == "directory":
                fields[2]["directory"] = "different-primary"
            else:
                fields[2]["planned"]["final_tasks"] = 25
            with self.subTest(mutation=mutation), self.assertRaises(ValueError):
                self.terms(fields)

    def test_changed_plain_model_mode_profile_seed_or_instrument_refuses(self):
        for mutation in ("model", "instructions", "sampling", "profile", "seed", "instrument"):
            fields = self.fixture()
            baseline, frozen = fields[3]["in-context"]
            if mutation in {"model", "instructions", "sampling"}:
                frozen["config"][mutation] = "changed"
            elif mutation == "profile":
                frozen["profile"] = {"profile_id": "changed"}
            elif mutation == "seed":
                baseline["generation"]["selection"]["components"]["agent"] = {"seed.py": "0" * 64}
            else:
                baseline["native"]["instrument"] = "changed"
            with (
                self.subTest(mutation=mutation),
                self.assertRaisesRegex(ValueError, "plain_reference"),
            ):
                self.terms(fields)

    def test_missing_reference_or_changed_nominal_envelope_refuses(self):
        for mutation in ("missing", "amount", "boolean"):
            fields = self.fixture()
            if mutation == "missing":
                del fields[3]["in-context"]
            else:
                fields[3]["regenerate"][0]["generation"]["max_calls"] = (
                    True if mutation == "boolean" else 313
                )
            with self.subTest(mutation=mutation), self.assertRaises(ValueError):
                self.terms(fields)

    def test_additive_handoff_preserves_every_base_field_and_denies_cycles(self):
        base = self.fixture()[1]
        before = copy.deepcopy(base)
        result = recipe.extend_handoff(base, {"new-plan": "f" * 64}, "new-handoff", require)
        self.assertEqual(
            result, base | {"source_sha256": base["source_sha256"] | {"new-plan": "f" * 64}}
        )
        result["assessment"]["path"] = "changed-return"
        self.assertEqual(base, before)
        for additions in ({"new-handoff": "f" * 64}, {"retained-control": "0" * 64}):
            with self.subTest(additions=additions), self.assertRaises(ValueError):
                recipe.extend_handoff(base, additions, "new-handoff", require)


if __name__ == "__main__":
    unittest.main()
