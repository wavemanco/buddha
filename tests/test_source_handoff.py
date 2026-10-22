"""Keyless source proposals: real configuration checks, no preparation or dispatch."""

import copy
import hashlib
import os
import unittest
from pathlib import Path
from unittest.mock import patch

import test_source_screen as screen_fixtures

from buddha.releases import _json


def sha(raw):
    return hashlib.sha256(raw).hexdigest()


class SourceHandoffTests(unittest.TestCase):
    def setUp(self):
        # Missing API is reported as setup evidence, not a behavioral failure.
        from buddha.source_handoff import SourceHandoffError, _sources, check_source_handoff

        self.check, self.Error = check_source_handoff, SourceHandoffError
        self.h = h = screen_fixtures.SourceScreenTests("runTest")
        h.setUp()
        self.addCleanup(h.doCleanups)
        record = copy.deepcopy(h.record)
        record["format"] = "buddha.source-screen.v2"
        self.screen = h.screen(record)
        generation = record["generation"]
        runtime_path = Path(generation["runtime"]["path"])
        self.path = h.root / "source-proposal.json"
        self.extra = h.root / "reviewed-protocol.md"
        self.extra.write_bytes(b"A prospective development experiment, not an allocation.\n")
        self.record = {
            "format": "buddha.source-handoff.v1",
            "seed_screen": self.screen.to_record(),
            "proposal_template": {
                key: copy.deepcopy(generation[key])
                for key in ("config", "profile", "max_callbacks", "budget_microusd", "max_calls")
            },
            "spec": {
                "format": "buddha.source-search.v1",
                "iterations": 2,
                "method": "latest",
                "seed": 7,
                "max_active": 4,
            },
            "expected_runtime_sha256": generation["runtime"]["sha256"],
            "source_sha256": {
                str(path): sha(path.read_bytes())
                for path in (*_sources(), runtime_path, self.extra)
            },
            "requested_terms": {"budget_microusd": 50_000_000, "max_calls": 256},
        }

    def write(self, record=None):
        raw = _json(self.record if record is None else record)
        self.path.write_bytes(raw)
        return sha(raw)

    def snapshot(self):
        return {
            str(path): sha(path.read_bytes()) for path in self.h.root.rglob("*") if path.is_file()
        }

    def test_check_is_read_only_keyless_unallocated_and_does_not_execute(self):
        expected = self.write()
        before = self.snapshot()
        with (
            patch.dict(os.environ, {}, clear=True),
            patch("sqlite3.connect", side_effect=AssertionError("no database access")),
            patch("http.client.HTTPSConnection", side_effect=AssertionError("no provider")),
            patch("buddha.executor.run_container", side_effect=AssertionError("no worker")),
            patch(
                "buddha.authorization.Authorization.create", side_effect=AssertionError("no grant")
            ),
            patch(
                "buddha.source_search.prepare_source_search", side_effect=AssertionError("no owner")
            ),
        ):
            result = self.check(self.path, expected_sha256=expected)
        self.assertEqual(self.snapshot(), before)
        self.assertEqual(result["status"], "configuration_checked")
        self.assertEqual(result["funding"]["status"], "unallocated")
        self.assertEqual(
            result["funding"]["scope"], "source screen: " + self.screen.comparison_key()
        )
        self.assertEqual(result["planned"]["task_ids"], ["1", 1])
        self.assertEqual(result["planned"]["maximum_candidate_screens"], 3)
        self.assertEqual(result["planned"]["maximum_stage_owners"], 26)
        self.assertEqual(result["reviewed_bindings"][str(self.path)], expected)
        self.assertEqual(result["requested_terms"], self.record["requested_terms"])

    def test_returns_detached_literal_values(self):
        expected = self.write()
        first = self.check(self.path, expected_sha256=expected)
        first["reviewed_bindings"].clear()
        first["planned"]["task_ids"].clear()
        first["requested_terms"]["max_calls"] = 1
        again = self.check(self.path, expected_sha256=expected)
        self.assertEqual(again["planned"]["task_ids"], ["1", 1])
        self.assertEqual(again["requested_terms"]["max_calls"], 256)
        self.assertIn(str(self.path), again["reviewed_bindings"])

    def test_wrong_raw_pin_and_malformed_duplicate_or_nonfinite_json_refuse(self):
        self.write()
        with self.assertRaises(self.Error):
            self.check(self.path, expected_sha256="0" * 64)
        for raw in (b"{}", b"{", b'{"format":1,"format":2}', b'{"format":NaN}'):
            with self.subTest(raw=raw):
                self.path.write_bytes(raw)
                with self.assertRaises(self.Error):
                    self.check(self.path, expected_sha256=sha(raw))

    def test_missing_installed_helper_or_runtime_binding_refuses(self):
        for name in (
            str(Path(__file__).resolve().parents[1] / "buddha/source_handoff.py"),
            str(Path(__file__).resolve().parents[1] / "buddha/source_search.py"),
            self.record["seed_screen"]["generation"]["runtime"]["path"],
        ):
            with self.subTest(name=name):
                record = copy.deepcopy(self.record)
                del record["source_sha256"][name]
                expected = self.write(record)
                with self.assertRaises(self.Error):
                    self.check(self.path, expected_sha256=expected)

    def test_control_changes_after_review_or_during_check_refuse(self):
        expected = self.write()
        original = self.extra.read_bytes()
        self.extra.write_bytes(original + b"changed")
        with self.assertRaises(self.Error):
            self.check(self.path, expected_sha256=expected)
        self.extra.write_bytes(original)
        from buddha import source_screen

        actual = source_screen._configuration
        count = 0

        def mutate(screen, runtime):
            nonlocal count
            actual(screen, runtime)
            count += 1
            if count == 2:
                self.extra.write_bytes(original + b"changed during checking")

        with patch.object(source_screen, "_configuration", side_effect=mutate):
            with self.assertRaises(self.Error):
                self.check(self.path, expected_sha256=expected)

    def test_selected_component_drift_refuses_without_preparation(self):
        expected = self.write()
        source = Path(self.record["seed_screen"]["generation"]["roots"]["agent"]) / "candidate.py"
        source.write_bytes(source.read_bytes() + b"\n# drift\n")
        with self.assertRaises(self.Error):
            self.check(self.path, expected_sha256=expected)

    def test_late_control_change_during_final_component_check_refuses(self):
        expected = self.write()
        from buddha import source_screen

        actual = source_screen._configuration
        count = 0

        def mutate(screen, runtime):
            nonlocal count
            actual(screen, runtime)
            count += 1
            if count == 4:
                self.extra.write_bytes(b"Late change during final selected-component check")

        with patch.object(source_screen, "_configuration", side_effect=mutate):
            with self.assertRaises(self.Error):
                self.check(self.path, expected_sha256=expected)

    def test_runtime_approval_or_proposal_profile_changes_refuse(self):
        values = copy.deepcopy(self.record)
        values["expected_runtime_sha256"] = "0" * 64
        expected = self.write(values)
        with self.assertRaises(self.Error):
            self.check(self.path, expected_sha256=expected)
        for field, value in (
            ("model", "unfunded"),
            ("provider", "anthropic"),
            ("max_output_tokens", 101),
        ):
            with self.subTest(field=field):
                values = copy.deepcopy(self.record)
                values["proposal_template"]["config"][field] = value
                expected = self.write(values)
                with self.assertRaises(self.Error):
                    self.check(self.path, expected_sha256=expected)

    def test_only_prospective_one_file_initial_screen_is_supported(self):
        values = copy.deepcopy(self.record)
        values["seed_screen"]["format"] = "buddha.source-screen.v1"
        expected = self.write(values)
        with self.assertRaises(self.Error):
            self.check(self.path, expected_sha256=expected)
        values = copy.deepcopy(self.record)
        values["seed_screen"]["lineage"] = {
            "path": str(self.extra),
            "sha256": sha(self.extra.read_bytes()),
        }
        expected = self.write(values)
        with self.assertRaises(self.Error):
            self.check(self.path, expected_sha256=expected)

    def test_bad_terms_spec_and_extra_fields_refuse(self):
        for field, value in (("budget_microusd", 0), ("max_calls", True), ("max_calls", 2**63)):
            with self.subTest(field=field, value=value):
                values = copy.deepcopy(self.record)
                values["requested_terms"][field] = value
                expected = self.write(values)
                with self.assertRaises(self.Error):
                    self.check(self.path, expected_sha256=expected)
        for spec in ({"iterations": 9}, {"method": "unknown"}):
            values = copy.deepcopy(self.record)
            values["spec"].update(spec)
            expected = self.write(values)
            with self.assertRaises(self.Error):
                self.check(self.path, expected_sha256=expected)
        values = copy.deepcopy(self.record)
        values["authorization"] = "must not be adopted"
        expected = self.write(values)
        with self.assertRaises(self.Error):
            self.check(self.path, expected_sha256=expected)

    def test_relative_self_or_oversized_control_map_refuses(self):
        for mapping in (
            {"relative": "0" * 64},
            self.record["source_sha256"] | {str(self.path): "0" * 64},
            {str(self.h.root / ("file-" + str(i))): "0" * 64 for i in range(1024)},
        ):
            values = copy.deepcopy(self.record)
            values["source_sha256"] = mapping
            expected = self.write(values)
            with self.assertRaises(self.Error):
                self.check(self.path, expected_sha256=expected)

    def test_duplicate_case_alias_of_a_control_refuses(self):
        values = copy.deepcopy(self.record)
        values["source_sha256"][str(self.extra).swapcase()] = sha(self.extra.read_bytes())
        expected = self.write(values)
        with self.assertRaises(self.Error):
            self.check(self.path, expected_sha256=expected)


if __name__ == "__main__":
    unittest.main()
