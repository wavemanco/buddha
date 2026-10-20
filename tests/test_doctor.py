"""Read-only observations distinguish evidence, exclusion and unknown ownership."""

import copy
import hashlib
import io
import json
import os
import shutil
import tempfile
import unittest
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path
from unittest.mock import patch

from doctor_helpers import (
    baseline,
    checked,
    diagnostic,
    files,
    gateway,
    legacy,
    native,
    protected,
    search,
)
from search_verify_helpers import corrupt_database

from buddha import doctor
from buddha.__main__ import main
from buddha.common import _canonical


class DoctorTests(unittest.TestCase):
    def assert_observed(self, result, *, completion="no_completion_observed"):
        self.assertEqual(result["format"], "buddha.doctor.v1")
        self.assertEqual(result["status"], "observed")
        self.assertEqual(result["writer"]["identity"], "unknown")
        self.assertEqual(result["completion"]["status"], completion)
        self.assertTrue(result["limitations"])
        serialized = json.dumps(result)
        for secret in ("CANARY", "Saved answer", "request-0", "never-a-real-credential"):
            self.assertNotIn(secret, serialized)

    def test_missing_input_is_unavailable_without_invented_zero_accounting(self):
        with tempfile.TemporaryDirectory() as temporary:
            directory = Path(temporary).resolve() / "missing"
            result = checked(self, directory)
            self.assertEqual(result["format"], "buddha.doctor.v1")
            self.assertEqual(result["status"], "unavailable")
            self.assertIsNone(result["accounting"])
            self.assertIsNone(result["needs_review"])
            self.assertEqual(result["lock"]["status"], "unavailable")
            self.assertEqual(result["operations"], [])
            self.assertFalse(directory.exists())

    def test_unreadable_input_cannot_claim_an_absent_lock(self):
        with tempfile.TemporaryDirectory() as temporary:
            directory = Path(temporary).resolve()
            (directory / ".search.lock").write_bytes(b"")
            with patch("buddha.doctor._entries", side_effect=PermissionError("CANARY")):
                result = checked(self, directory)
            self.assertEqual(result["status"], "unavailable")
            self.assertIsNone(result["accounting"])
            self.assertEqual(result["lock"]["status"], "unavailable")
            self.assertEqual(result["writer"]["identity"], "unknown")
            self.assertNotIn("CANARY", json.dumps(result))

    def test_legacy_states_empty_exclusion_and_defensive_results(self):
        fixture = legacy(self)
        for name, amount in (("reserved", 50), ("dispatched", 60)):
            fixture.ledger.reserve(name, "f" * 64, amount)
        fixture.ledger.dispatch("dispatched")
        (fixture.directory / ".search.lock").write_bytes(b"")
        result = checked(self, fixture.directory)
        self.assert_observed(result)
        self.assertTrue(result["needs_review"])
        self.assertEqual(
            result["lock"], {"status": "legacy_empty", "name": ".search.lock", "pid": None}
        )
        self.assertIsNone(result["writer"]["pid_observation"])
        self.assertEqual(
            result["accounting"],
            {
                "committed_microusd": 534193,
                "spent_microusd": 1710,
                "reserved_microusd": 532483,
                "operation_count": 12,
                "budget_microusd": 10_000_000,
                "max_calls": 128,
                "completed_count": 9,
                "reserved_count": 1,
                "dispatched_count": 1,
                "unknown_count": 1,
            },
        )
        self.assertEqual(
            set(result["observed_sha256"]), {"manifest.json", "operations.sqlite3", ".search.lock"}
        )
        self.assertTrue(all(len(value) == 64 for value in result["observed_sha256"].values()))
        result["accounting"]["spent_microusd"] = 0
        result["operations"][0]["status"] = "FORGED"
        result["limitations"].clear()
        again = checked(self, fixture.directory)
        self.assertEqual(again["accounting"]["spent_microusd"], 1710)
        self.assertNotIn("FORGED", json.dumps(again))
        self.assertTrue(again["limitations"])

    def test_actual_legacy_baseline_observes_bound_saved_completion(self):
        fixture = baseline(self)
        result = checked(self, fixture.directory)
        self.assert_observed(result, completion="stored_completion_observed")
        self.assertEqual(result["input_format"], "buddha.baseline.v1")
        self.assertEqual(result["accounting"]["operation_count"], 12)
        self.assertEqual(result["accounting"]["spent_microusd"], 180)
        self.assertFalse(result["needs_review"])

    def test_complete_search_and_linked_owners_use_local_and_explicit_shared_data(self):
        for continuation in (False, True):
            with self.subTest(continuation=continuation):
                fixture = search(self, continuation=continuation)
                authority = fixture.authority_path if continuation else None
                result = checked(self, fixture.directory, authorization=authority)
                self.assert_observed(result, completion="stored_completion_observed")
                self.assertEqual(result["candidate_count"], 3)
                for key in ("spent_microusd", "reserved_microusd", "operation_count"):
                    self.assertEqual(result["accounting"][key], fixture.report["costs"][key])
                self.assertEqual(result["accounting"]["unknown_count"], 0)
                if continuation:
                    shared = fixture.authority.summary()
                    self.assertEqual(
                        result["shared_accounting"],
                        {
                            key: shared[key]
                            for key in (
                                "committed_microusd",
                                "spent_microusd",
                                "reserved_microusd",
                                "operation_count",
                            )
                        },
                    )
                    self.assertGreater(result["shared_accounting"]["reserved_microusd"], 0)
                    self.assertIn("authorization", result["observed_sha256"])
                else:
                    self.assertIsNone(result["shared_accounting"])

    def test_raw_gateway_receipts_are_read_without_current_selection_or_authority(self):
        fixture = gateway(self)
        result = checked(self, fixture.directory)
        self.assert_observed(result)
        self.assertEqual(result["input_format"], "buddha.gateway-run.v1")
        self.assertEqual(result["accounting"]["spent_microusd"], 11)
        self.assertEqual(result["accounting"]["operation_count"], 1)
        self.assertEqual(result["operations"][0]["status"], "completed")
        self.assertFalse(result["needs_review"])

    def test_unresolved_diagnostic_survives_newer_unrelated_success(self):
        fixture = diagnostic(self)
        value = fixture.outcome()
        value.pop("record_sha256")
        value.update(
            operation_id="b" * 64,
            at="2099-01-01T00:00:00+00:00",
            outcome="response_received",
            phase="complete",
            http_status=200,
            error_category=None,
            error_code=None,
        )
        directory = fixture.directory / "diagnostics" / ("b" * 64)
        directory.mkdir()
        value["record_sha256"] = hashlib.sha256(_canonical(value)).hexdigest()
        (directory / "outcome.json").write_bytes(_canonical(value))
        result = checked(self, fixture.directory)
        self.assert_observed(result)
        self.assertTrue(result["needs_review"])
        self.assertEqual(result["accounting"]["unknown_count"], 1)
        self.assertEqual(result["accounting"]["reserved_microusd"], 120)
        self.assertEqual(len(result["diagnostics"]), 1)
        self.assertEqual(result["diagnostics"][0]["operation_id"], fixture.operation)
        self.assertEqual(result["diagnostics"][0]["http_status"], 500)

    def test_pid_only_native_lock_never_identifies_writer(self):
        fixture = native(self)
        pid = os.getpid()
        (fixture.directory / "running.lock").write_bytes(str(pid).encode("ascii"))
        for status in ("present", "absent", "unavailable"):
            observation = {"pid": pid, "status": status}
            with (
                self.subTest(status=status),
                patch("buddha.doctor.observe_pid", return_value=observation) as probe,
            ):
                result = checked(self, fixture.directory)
            self.assert_observed(result)
            self.assertEqual(
                result["lock"], {"status": "pid_only", "name": "running.lock", "pid": pid}
            )
            self.assertEqual(result["writer"]["pid_observation"], observation)
            self.assertFalse(result["needs_review"])
            probe.assert_called_once_with(pid)

    def test_invalid_lock_is_reviewable_without_pid_probe_or_repair(self):
        fixture = legacy(self)
        for value in (b"0", b"not PID", b"12\n34", b"1" * 129):
            (fixture.directory / "running.lock").write_bytes(value)
            with (
                self.subTest(value=value[:12]),
                patch(
                    "buddha.doctor.observe_pid", side_effect=AssertionError("invalid PID probed")
                ),
            ):
                result = checked(self, fixture.directory)
            self.assert_observed(result)
            self.assertEqual(result["lock"]["status"], "invalid")
            self.assertTrue(result["needs_review"])
            self.assertIsNone(result["writer"]["pid_observation"])

    def test_native_active_owner_completion_is_retained_unanchored(self):
        fixture = native(self, unanchored=True)
        result = checked(self, fixture.directory, authorization=fixture.authority.path)
        self.assert_observed(result, completion="unanchored_completion_needs_review")
        self.assertTrue(result["needs_review"])
        self.assertEqual(
            result["stages"][0]["completion"]["status"], "unanchored_completion_needs_review"
        )
        self.assertEqual(len(result["stages"]), 1)
        self.assertTrue(fixture.owner_state(0)["active"])
        self.assertFalse((fixture.directory / "owners/1").exists())
        self.assertFalse((fixture.directory / "report.json").exists())

    def test_native_anchors_require_explicit_authority_and_preserve_stage_caps(self):
        fixture = native(self, complete=True)
        unanchored = checked(self, fixture.directory)
        self.assert_observed(unanchored, completion="anchor_not_observed")
        self.assertIsNone(unanchored["shared_accounting"])
        result = checked(self, fixture.directory, authorization=fixture.authority.path)
        self.assert_observed(result, completion="stored_completion_observed")
        self.assertIsNone(result["run_id"])
        self.assertEqual(result["input_format"], "buddha.baseline-context.v1")
        self.assertEqual(len(result["stages"]), 4)
        self.assertIsNone(result["accounting"]["budget_microusd"])
        self.assertIsNone(result["accounting"]["max_calls"])
        self.assertEqual(result["accounting"]["operation_count"], 6)
        for stage in result["stages"]:
            self.assertEqual(stage["completion"]["status"], "stored_completion_observed")
        self.assertEqual(
            [stage["accounting"]["budget_microusd"] for stage in result["stages"]],
            [10_000, 10_000, 10_000, 1],
        )
        self.assertFalse(result["needs_review"])

    def test_native_wrong_anchor_and_changed_attempt_are_distinct_failures(self):
        fixture = native(self, complete=True)
        authority = fixture.authority.path
        original = authority.read_bytes()
        corrupt_database(
            authority,
            "UPDATE auth_deactivations SET reason=? WHERE run_id=?",
            ("baseline completed: " + "0" * 64, fixture.manifest(0)["run_id"]),
        )
        result = checked(self, fixture.directory, authorization=authority)
        self.assert_observed(result, completion="anchor_mismatch")
        self.assertTrue(result["needs_review"])
        authority.write_bytes(original)
        seal = json.loads((fixture.directory / "completed/0.json").read_bytes())
        report = fixture.directory / seal["attempt"] / "report.json"
        report.write_bytes(report.read_bytes() + b" ")
        result = checked(self, fixture.directory, authorization=authority)
        self.assert_observed(result, completion="invalid_completion")
        self.assertTrue(result["needs_review"])

    def test_native_final_report_is_bound_to_sealed_summary_release_and_tasks(self):
        fixture = native(self, complete=True)
        target = fixture.directory / "report.json"
        original = json.loads(target.read_bytes())
        for separator in ("/", "\\"):
            value = copy.deepcopy(original)
            value["stage_seals"] = {
                name.replace("\\", "/").replace("/", separator): digest
                for name, digest in value["stage_seals"].items()
            }
            target.write_bytes(_canonical(value))
            with self.subTest(control_separator=separator):
                self.assert_observed(
                    checked(self, fixture.directory, authorization=fixture.authority.path),
                    completion="stored_completion_observed",
                )
        seal = json.loads((fixture.directory / "completed/0.json").read_bytes())
        generation_answers = fixture.directory / seal["attempt"] / "answers.json"
        for field in ("summary", "release_sha256", "tasks_sha256"):
            value = copy.deepcopy(original)
            if field == "summary":
                value[field] = {
                    "path": str(generation_answers),
                    "sha256": hashlib.sha256(generation_answers.read_bytes()).hexdigest(),
                }
            else:
                value[field] = "0" * 64
            target.write_bytes(_canonical(value))
            with self.subTest(mutated=field):
                result = checked(self, fixture.directory, authorization=fixture.authority.path)
                self.assert_observed(result, completion="invalid_completion")
                self.assertTrue(result["needs_review"])

    def test_native_duplicate_physical_owner_and_partial_owner_population_are_unavailable(self):
        fixture = native(self)
        source = fixture.directory / "owners/0"
        duplicate = fixture.directory / "owners/1"
        shutil.copytree(source, duplicate)
        result = checked(self, fixture.directory)
        self.assertEqual(result["status"], "unavailable")
        self.assertIsNone(result["accounting"])
        self.assertEqual(result["stages"], [])
        shutil.rmtree(duplicate)
        duplicate.mkdir()
        result = checked(self, fixture.directory)
        self.assertEqual(result["status"], "unavailable")
        self.assertIsNone(result["accounting"])
        self.assertEqual(result["stages"], [])

    def test_native_orphan_or_noncanonical_completion_cannot_be_ignored(self):
        fixture = native(self, complete=True)
        contents = (fixture.directory / "completed/0.json").read_bytes()
        for name in ("99.json", "00.json"):
            target = fixture.directory / "completed" / name
            target.write_bytes(contents)
            with self.subTest(name=name):
                result = checked(self, fixture.directory, authorization=fixture.authority.path)
                self.assertEqual(result["status"], "unavailable")
                self.assertIsNone(result["accounting"])
                self.assertEqual(result["stages"], [])
            target.unlink()

    def test_actual_doctor_cli_json_exit_codes_remain_readonly_without_keys(self):
        clean = gateway(self)
        uncertain = legacy(self)
        for directory, expected, status in (
            (clean.directory, 0, "observed"),
            (uncertain.directory, 3, "observed"),
            (clean.root / "missing", 3, "unavailable"),
        ):
            before = files(directory)
            output, errors = io.StringIO(), io.StringIO()
            with self.subTest(status=status, expected=expected):
                with (
                    protected(directory, cli=True),
                    redirect_stdout(output),
                    redirect_stderr(errors),
                ):
                    code = main(["doctor", "--run", str(directory)])
                self.assertEqual(code, expected)
                record = json.loads(output.getvalue())
                self.assertEqual(record["format"], "buddha.doctor.v1")
                self.assertEqual(record["status"], status)
                self.assertEqual(errors.getvalue(), "")
                self.assertNotIn("CANARY", output.getvalue())
                self.assertEqual(files(directory), before)

    def test_busy_corrupt_and_missing_ledger_are_not_zero_healthy_states(self):
        fixture = legacy(self)
        sidecar = fixture.path.with_name(fixture.path.name + "-journal")
        sidecar.write_bytes(b"synthetic nonempty journal")
        result = checked(self, fixture.directory)
        self.assertEqual(result["status"], "busy_or_changing")
        self.assertIsNone(result["accounting"])
        self.assertEqual(result["operations"], [])
        sidecar.unlink()
        fixture.path.write_bytes(b"PRIVATE-CORRUPT-DATABASE-CANARY")
        result = checked(self, fixture.directory)
        self.assertEqual(result["status"], "unavailable")
        self.assertIsNone(result["accounting"])
        fixture.path.unlink()
        self.assertEqual(checked(self, fixture.directory)["status"], "unavailable")

    def test_hardlinks_and_oversized_population_are_rejected_without_following(self):
        fixture = legacy(self)
        alias = fixture.directory.parent / "manifest-alias.json"
        os.link(fixture.directory / "manifest.json", alias)
        self.assertEqual(checked(self, fixture.directory)["status"], "unavailable")
        alias.unlink()
        with patch("buddha.doctor.MAX_FILES", 1):
            result = checked(self, fixture.directory)
        self.assertEqual(result["status"], "unavailable")
        self.assertIsNone(result["accounting"])

    def test_explicit_missing_or_mismatched_authority_never_invents_shared_totals(self):
        fixture = gateway(self)
        for authority in (fixture.root / "absent.sqlite3", fixture.authority.path):
            if authority == fixture.authority.path:
                corrupt_database(authority, "UPDATE auth_operations SET actual_microusd=12")
            with self.subTest(missing=not authority.exists()):
                result = checked(self, fixture.directory, authorization=authority)
            self.assertEqual(result["status"], "unavailable")
            self.assertIsNone(result["accounting"])
            self.assertIsNone(result["shared_accounting"])

    def test_consumed_input_drift_is_busy_without_partial_accounting(self):
        fixture = legacy(self)
        original = doctor._read
        count = 0

        def changing(path, maximum):
            nonlocal count
            raw = original(path, maximum)
            if path == fixture.directory / "manifest.json":
                count += 1
                if count == 2:
                    return raw[:-1] + b" "
            return raw

        with patch("buddha.doctor._read", side_effect=changing):
            result = checked(self, fixture.directory)
        self.assertEqual(count, 2)
        self.assertEqual(result["status"], "busy_or_changing")
        self.assertIsNone(result["accounting"])
        self.assertIsNone(result["needs_review"])
        self.assertEqual(result["operations"], [])

    def test_unknown_format_is_explicitly_unsupported_without_accounting(self):
        fixture = legacy(self)
        fixture.manifest["format"] = "buddha.future-driver.v9"
        fixture.write_manifest()
        result = checked(self, fixture.directory)
        self.assertEqual(result["status"], "unsupported")
        self.assertIsNone(result["accounting"])
        self.assertEqual(result["stages"], [])


if __name__ == "__main__":
    unittest.main()
