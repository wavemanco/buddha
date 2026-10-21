"""Cross-snapshot and actual producer relationships must match the original study."""

import copy
import json
import os
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

import test_history as history_fixtures
import test_policy_panel_read as panel_fixtures

from buddha import baseline, policy_panel_read, policy_run
from buddha.releases import _json


class PolicyPanelBoundaryTests(unittest.TestCase):
    def panel(self, *, prepare=None):
        saved = panel_fixtures.PolicyPanelReadTests("runTest")
        self.addCleanup(saved.doCleanups)
        if prepare is None:
            saved.setUp()
        else:
            with patch.object(policy_run.baseline, "prepare_baseline", side_effect=prepare):
                saved.setUp()
        return saved

    def test_inner_authority_snapshot_cannot_supply_missing_outer_completion_anchor(self):
        saved = self.panel()
        saved.stop_after_generation()
        self.assertEqual(len(saved.read()["packet"]["items"]), 1)
        authority = saved.f.authority.path
        anchored = authority.read_bytes()
        base = saved.f.directory / "cells/0/baseline"
        owner = json.loads((base / "owners/0/manifest.json").read_bytes())
        run_id = owner["run_id"]
        history_fixtures.HistoryTests.corrupt(
            SimpleNamespace(path=authority),
            "DELETE FROM auth_deactivations WHERE run_id=?",
            (run_id,),
        )
        unanchored = authority.read_bytes()
        self.assertNotEqual(unanchored, anchored)
        original = policy_panel_read._read_generation
        inner_reads = []
        # An independent concurrent fixture writer is opened before reader guards.
        # The production reader itself keeps all its no-write/no-SQLite guards.
        information = authority.stat()
        try:
            with authority.open("r+b") as writer:

                def install(raw):
                    writer.seek(0)
                    writer.write(raw)
                    writer.truncate()
                    writer.flush()

                def transient(reference, path):
                    self.assertEqual(path, authority)
                    inner_reads.append(reference)
                    install(anchored)
                    try:
                        return original(reference, path)
                    finally:
                        install(unanchored)
                        os.utime(
                            authority,
                            ns=(information.st_atime_ns, information.st_mtime_ns),
                        )

                with (
                    patch.object(policy_panel_read, "_read_generation", side_effect=transient),
                    self.assertRaises(policy_panel_read.PolicyPanelReadError),
                ):
                    saved.read()
            self.assertEqual(authority.read_bytes(), unanchored)
            self.assertEqual(inner_reads, [])
        finally:
            authority.write_bytes(anchored)

    def test_actual_alternate_producer_cannot_hide_behind_unchanged_expected_cell_files(self):
        prepare = baseline.prepare_baseline
        captured = {}

        def alternate(directory, **kwargs):
            descriptor = kwargs["descriptor"]
            definition = json.loads(descriptor.read_bytes())
            recipe_path = Path(definition["generation"]["descriptor"])
            recipe = json.loads(recipe_path.read_bytes())
            captured["expected_definition"] = descriptor.read_bytes()
            captured["expected_recipe"] = recipe_path.read_bytes()
            captured["expected_paths"] = (descriptor, recipe_path)
            alternate_recipe = recipe_path.with_name("alternate-generation.json")
            changed = copy.deepcopy(recipe)
            changed["config"]["instructions"] = "UNREGISTERED-ALTERNATE-PRODUCER"
            alternate_recipe.write_bytes(_json(changed))
            alternate_definition = descriptor.with_name("alternate-baseline.json")
            changed_definition = copy.deepcopy(definition)
            changed_definition["generation"]["descriptor"] = str(alternate_recipe)
            alternate_definition.write_bytes(_json(changed_definition))
            captured["alternate_recipe"] = alternate_recipe
            captured["alternate_definition"] = alternate_definition
            kwargs = kwargs | {
                "descriptor": alternate_definition,
                "input_files": [*kwargs["input_files"], descriptor, recipe_path],
            }
            return prepare(directory, **kwargs)

        saved = self.panel(prepare=alternate)
        original_descriptor, original_recipe = captured["expected_paths"]
        self.assertEqual(original_descriptor.read_bytes(), captured["expected_definition"])
        self.assertEqual(original_recipe.read_bytes(), captured["expected_recipe"])
        base = saved.f.directory / "cells/0/baseline"
        context = json.loads((base / "context.json").read_bytes())
        self.assertEqual(context["descriptor"], str(captured["alternate_definition"]))
        saved.f.fixture.fail_native_once = True
        # Exercise the actual prepared baseline directly: the study controller
        # correctly refuses this owner, whereas the passive reader must do so too.
        execute = saved.f.fixture.execute

        def worker(spec, *, initial, **kwargs):
            if spec.role == "agent":
                saved.f.fixture.agent.config = copy.deepcopy(initial["config"])
            return execute(spec, initial=initial, **kwargs)

        with patch.object(saved.f.fixture, "execute", side_effect=worker):
            report = saved.f.fixture.run_pipeline(directory=base)
        self.assertEqual(report["status"], "incomplete")
        self.assertEqual(saved.f.fixture.physical_sends, 5)
        self.assertTrue((base / "completed/0.json").is_file())
        self.assertEqual(original_descriptor.read_bytes(), captured["expected_definition"])
        self.assertEqual(original_recipe.read_bytes(), captured["expected_recipe"])
        with self.assertRaises(policy_panel_read.PolicyPanelReadError):
            saved.read()

    def test_retained_authority_owner_cannot_become_missing_after_directory_removal(self):
        saved = self.panel()
        saved.stop_after_generation()
        self.assertEqual(len(saved.read()["packet"]["items"]), 1)
        source = saved.f.directory / "cells/0/baseline/owners/0"
        destination = saved.root / "retired-generation-owner"
        fixture_root = saved.root.resolve(strict=True)
        for path in (source.resolve(strict=True), destination.resolve(strict=False)):
            self.assertTrue(path.is_relative_to(fixture_root))
            self.assertNotEqual(path, fixture_root)
        self.assertFalse(destination.exists())
        authority = saved.f.authority.path.read_bytes()
        source.rename(destination)
        try:
            self.assertEqual(saved.f.authority.path.read_bytes(), authority)
            with self.assertRaises(policy_panel_read.PolicyPanelReadError):
                saved.read()
        finally:
            destination.rename(source)
        self.assertEqual(saved.f.authority.path.read_bytes(), authority)

    def test_unanchored_unsealed_complete_looking_attempt_does_not_become_public(self):
        saved = self.panel()
        saved.stop_after_generation()
        self.assertEqual(len(saved.read()["packet"]["items"]), 1)
        authority = saved.f.authority.path
        authority_raw = authority.read_bytes()
        base = saved.f.directory / "cells/0/baseline"
        seal_path = base / "completed/0.json"
        seal_raw = seal_path.read_bytes()
        seal = json.loads(seal_raw)
        attempt = base / seal["attempt"]
        answers = attempt / "answers.json"
        report = attempt / "report.json"
        answers_raw, report_raw = answers.read_bytes(), report.read_bytes()
        self.assertEqual(json.loads(report_raw)["status"], "complete")
        run_id = json.loads((base / "owners/0/manifest.json").read_bytes())["run_id"]
        try:
            history_fixtures.HistoryTests.corrupt(
                SimpleNamespace(path=authority),
                "DELETE FROM auth_deactivations WHERE run_id=?",
                (run_id,),
            )
            seal_path.unlink()
            result = saved.read()
            self.assertEqual(result["packet"]["items"], [])
            private = result["private"]
            self.assertEqual(private["status"], "incomplete")
            self.assertEqual(private["coverage"]["available_sets"], 0)
            self.assertEqual(private["coverage"]["available_positions"], 0)
            self.assertEqual(len(private["sets"]), saved.plan["counts"]["sets"])
            self.assertTrue(all(row["binding"] is None for row in private["sets"]))
            self.assertTrue(all(row["state"] == "unavailable" for row in private["sets"]))
            self.assertTrue(
                all(
                    answer["text_utf8_sha256"] is None
                    for row in private["sets"]
                    for answer in row["answers"]
                )
            )
            self.assertEqual(answers.read_bytes(), answers_raw)
            self.assertEqual(report.read_bytes(), report_raw)
        finally:
            authority.write_bytes(authority_raw)
            seal_path.write_bytes(seal_raw)


if __name__ == "__main__":
    unittest.main()
