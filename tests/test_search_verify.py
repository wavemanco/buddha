"""Sealed legacy search verification never reconstructs or funds a search."""

import copy
import io
import json
import sqlite3
import unittest
from contextlib import closing, redirect_stderr, redirect_stdout
from unittest.mock import patch

from search_verify_helpers import (
    corrupt_database,
    evidence_for,
    funded,
    linked,
    ordinary,
    readonly_boundary,
    record,
    rewrite_record,
    sha,
    source_snapshot,
)

from buddha.__main__ import main
from buddha.common import ValidationError, _canonical
from buddha.policy import Policy
from buddha.search_verify import verify_search

FINANCIALS = ("committed_microusd", "spent_microusd", "reserved_microusd", "operation_count")


class SearchVerificationTests(unittest.TestCase):
    def verify(self, fixture, evidence=None):
        evidence = evidence_for(fixture) if evidence is None else evidence
        before, declaration = source_snapshot(evidence), copy.deepcopy(evidence)
        try:
            with readonly_boundary():
                return verify_search(fixture.directory, evidence=evidence)
        finally:
            self.assertEqual(before, source_snapshot(evidence))
            self.assertEqual(declaration, evidence)

    def test_complete_ordinary_search_checks_real_artifacts_slots_and_costs_without_execution(self):
        fixture = ordinary(self)
        result = self.verify(fixture).to_record()
        self.assertEqual(result["format"], "buddha.search-verification-report.v1")
        self.assertEqual(result["status"], "verified")
        self.assertEqual(result["run_id"], fixture.report["run_id"])
        self.assertEqual(result["costs"], {key: fixture.report["costs"][key] for key in FINANCIALS})
        self.assertEqual(
            result["checked"]["physical_operations"], result["costs"]["operation_count"]
        )
        self.assertEqual(result["checked"]["inherited_operations"], 0)
        self.assertEqual(result["checked"]["candidates"], 3)
        self.assertEqual(result["checked"]["decisions"], 3)
        self.assertIsNone(result["missing"])
        self.assertIsNone(result["shared_accounting"])
        self.assertEqual(
            result["claim"], "saved-evidence consistency only; no provider or semantic attestation"
        )

    def test_complete_linked_search_checks_inheritance_and_real_shared_mirror_once(self):
        fixture = linked(self)
        result = self.verify(fixture).to_record()
        self.assertEqual(result["status"], "verified")
        self.assertEqual(result["checked"]["inherited_operations"], 9)
        self.assertEqual(result["checked"]["physical_operations"], 55)
        for key in FINANCIALS:
            self.assertEqual(result["costs"][key], fixture.report["costs"][key])
            self.assertEqual(result["shared_accounting"][key], fixture.report["authorization"][key])
        self.assertGreater(result["shared_accounting"]["reserved_microusd"], 0)

    def test_invalid_and_duplicate_proposal_outcomes_are_checked_without_inventing_children(self):
        for proposal, status in [
            ("not policy JSON", "invalid"),
            ({"instructions": "", "sampling": "regenerate"}, "duplicate"),
        ]:
            with self.subTest(status=status):
                fixture = ordinary(self, proposals=[proposal])
                self.assertEqual(fixture.report["decisions"][0]["status"], status)
                result = self.verify(fixture).to_record()
                self.assertEqual(result["status"], "verified")
                self.assertEqual(result["checked"]["candidates"], 2)
                self.assertEqual(result["checked"]["decisions"], 3)
                self.assertEqual(result["costs"]["operation_count"], 25)

    def test_nine_reply_interruption_is_incomplete_with_exact_next_slot_and_full_hold(self):
        fixture = ordinary(self, interrupted=True)
        with closing(sqlite3.connect(fixture.directory / "operations.sqlite3")) as connection:
            (operation_id,) = connection.execute(
                "SELECT operation_id FROM operations WHERE status='unknown'"
            ).fetchone()
        result = self.verify(fixture).to_record()
        self.assertEqual(result["status"], "incomplete")
        self.assertEqual(result["checked"]["physical_operations"], 9)
        self.assertEqual(result["checked"]["candidates"], 0)
        self.assertEqual(
            result["missing"],
            {
                "operation_id": operation_id,
                "prompt_id": "dev-a",
                "stage": "generation",
                "index": 9,
                "status": "unknown",
            },
        )
        self.assertEqual(
            result["costs"],
            {
                "committed_microusd": 104231,
                "spent_microusd": 135,
                "reserved_microusd": 104096,
                "operation_count": 10,
            },
        )
        self.assertFalse((fixture.directory / "report.json").exists())
        self.assertFalse((fixture.directory / ".search.lock").exists())

    def test_frozen_result_and_nested_output_copies_cannot_rewrite_verification(self):
        fixture = ordinary(self)
        result = self.verify(fixture)
        original = result.to_record()
        with self.assertRaises(AttributeError):
            result.status = "changed"
        changed = result.to_record()
        changed["costs"]["spent_microusd"] = 0
        changed["checked"]["candidates"] = 999
        self.assertEqual(result.to_record(), original)

    def test_stored_seed_records_work_without_today_contracts_or_default_policy_values(self):
        fixture = ordinary(self)
        original = Policy.__init__

        def explicit(instance, *args, **kwargs):
            if len(args) < 2 and not ((args or "instructions" in kwargs) and "sampling" in kwargs):
                raise AssertionError("verification used today's default seed policy")
            original(instance, *args, **kwargs)

        with patch.object(Policy, "__init__", explicit):
            self.assertEqual(self.verify(fixture).to_record()["status"], "verified")

    def test_missing_or_incorrect_operator_seal_is_invalid_instead_of_generated(self):
        fixture = ordinary(self)
        original = evidence_for(fixture)
        for missing in (False, True):
            evidence = copy.deepcopy(original)
            if missing:
                del evidence["runs"][0]["files"]["operations.sqlite3"]
            else:
                evidence["runs"][0]["files"]["operations.sqlite3"] = "0" * 64
            with self.subTest(missing=missing), self.assertRaises(ValidationError):
                self.verify(fixture, evidence)

    def test_resealed_wrong_request_fingerprint_or_semantic_slot_is_rejected(self):
        fixture = ordinary(self)
        path = fixture.directory / "operations.sqlite3"
        original = path.read_bytes()
        with closing(sqlite3.connect(path)) as connection:
            (operation_id,) = connection.execute(
                "SELECT operation_id FROM operations ORDER BY operation_id LIMIT 1"
            ).fetchone()
        for mutation in ("fingerprint", "slot"):
            with self.subTest(mutation=mutation):
                path.write_bytes(original)
                if mutation == "fingerprint":
                    corrupt_database(
                        path,
                        "UPDATE operations SET request_sha256=? WHERE operation_id=?",
                        ("f" * 64, operation_id),
                    )
                else:
                    corrupt_database(
                        path,
                        "UPDATE operations SET operation_id=? WHERE operation_id=?",
                        ("0" * 64, operation_id),
                    )
                    corrupt_database(
                        path,
                        "UPDATE events SET operation_id=? WHERE operation_id=?",
                        ("0" * 64, operation_id),
                    )
                with self.assertRaises(ValidationError):
                    self.verify(fixture)

    def test_resealed_proposal_reply_cannot_disagree_with_saved_decision(self):
        fixture = ordinary(self)
        decision = record(fixture.directory / "decisions/iteration-000000.json")
        operation_id = sha(
            _canonical([fixture.report["run_id"], "proposal", 0, "development", "proposal", 0])
        )
        path = fixture.directory / "operations.sqlite3"
        with closing(sqlite3.connect(path)) as connection:
            (saved,) = connection.execute(
                "SELECT response_json FROM operations WHERE operation_id=?", (operation_id,)
            ).fetchone()
        reply = json.loads(saved)
        reply["text"] = json.dumps(
            {"instructions": "Resealed other child", "sampling": "regenerate"}
        )
        self.assertNotEqual(sha(reply["text"].encode()), decision["proposal_sha256"])
        corrupt_database(
            path,
            "UPDATE operations SET response_json=? WHERE operation_id=?",
            (json.dumps(reply), operation_id),
        )
        with self.assertRaises(ValidationError):
            self.verify(fixture)

    def test_resealed_parent_change_in_both_decision_and_report_fails_lineage_replay(self):
        fixture = ordinary(self)
        decision_path = fixture.directory / "decisions/iteration-000000.json"
        old = record(decision_path)["parent_id"]
        alternate = next(
            item["candidate_id"]
            for item in fixture.report["candidates"][:2]
            if item["candidate_id"] != old
        )
        rewrite_record(decision_path, lambda value: value.update(parent_id=alternate))
        rewrite_record(
            fixture.directory / "report.json",
            lambda value: value["decisions"][0].update(parent_id=alternate),
        )
        with self.assertRaises(ValidationError):
            self.verify(fixture)

    def test_resealed_artifact_arithmetic_is_recomputed_not_trusted(self):
        fixture = ordinary(self)
        candidate_id = fixture.report["candidates"][0]["candidate_id"]
        directory = fixture.directory / "candidates" / candidate_id / "evaluation"
        path = directory / "v1.1/scores.jsonl"
        rows = [json.loads(line) for line in path.read_bytes().splitlines()]
        rows[0]["utility"] += 0.25
        path.write_bytes(b"".join(_canonical(row) + b"\n" for row in rows))
        rewrite_record(
            directory / "provenance.json",
            lambda value: value["artifact_hashes"].update(
                {"v1.1/scores.jsonl": sha(path.read_bytes())}
            ),
            checksum="provenance_sha256",
        )
        with self.assertRaises(ValidationError):
            self.verify(fixture)

    def test_resealed_report_costs_must_match_actual_ledger_operation_population(self):
        fixture = ordinary(self)
        rewrite_record(
            fixture.directory / "report.json",
            lambda value: value["costs"].update(
                spent_microusd=value["costs"]["spent_microusd"] + 1
            ),
        )
        with self.assertRaises(ValidationError):
            self.verify(fixture)

    def test_unknown_stored_parent_rule_is_unsupported_without_current_runtime_fallback(self):
        fixture = ordinary(self)
        path = fixture.directory / "manifest.json"
        rewrite_record(
            path, lambda value: value["contracts"].update(parent_rule="future-rule.v999")
        )
        checksum = record(path)["record_sha256"]
        corrupt_database(
            fixture.directory / "operations.sqlite3",
            "UPDATE run_config SET manifest_sha256=?",
            (checksum,),
        )
        result = self.verify(fixture).to_record()
        self.assertEqual(result["status"], "unsupported")

    def test_resealed_linked_source_reference_cannot_name_another_receipt_slot(self):
        fixture = linked(self)
        path = fixture.directory / "manifest.json"
        rewrite_record(
            path,
            lambda value: value["continuation"]["inherited"][0].update(
                source_operation_id=value["continuation"]["inherited"][1]["source_operation_id"]
            ),
        )
        checksum = record(path)["record_sha256"]
        corrupt_database(
            fixture.directory / "operations.sqlite3",
            "UPDATE run_config SET manifest_sha256=?",
            (checksum,),
        )
        with self.assertRaises(ValidationError):
            self.verify(fixture)

    def test_resealed_shared_authority_mirror_reply_must_match_owning_run_ledger(self):
        fixture = linked(self)
        with closing(sqlite3.connect(fixture.authority_path)) as connection:
            operation_id, saved = connection.execute(
                "SELECT operation_id,response_json FROM auth_operations WHERE run_id=? LIMIT 1",
                (fixture.report["run_id"],),
            ).fetchone()
        changed = json.loads(saved)
        changed["text"] = "Different but structurally valid mirrored reply"
        corrupt_database(
            fixture.authority_path,
            "UPDATE auth_operations SET response_json=? WHERE operation_id=?",
            (json.dumps(changed), operation_id),
        )
        with self.assertRaises(ValidationError):
            self.verify(fixture)

    def test_historical_recovery_funding_reconciles_source_hold_and_new_allowance(self):
        fixture = funded(self)
        funding = record(fixture.directory / "funding.json")
        self.assertEqual(funding["source_known_microusd"], 1710)
        self.assertEqual(funding["source_held_microusd"], 532373)
        self.assertEqual(funding["recovery_budget_microusd"], 9465917)
        self.assertEqual(funding["recovery_max_calls"], 118)
        result = self.verify(fixture).to_record()
        self.assertEqual(result["status"], "verified")
        self.assertEqual(result["costs"]["operation_count"], 37)
        self.assertIsNone(result["shared_accounting"])

    def test_resealed_funding_numbers_run_identity_or_source_ledger_seal_are_rejected(self):
        fixture = funded(self)
        path = fixture.directory / "funding.json"
        original = path.read_bytes()
        for name, value in [
            ("source_held_microusd", 0),
            ("source_attempted_calls", 9),
            ("recovery_run_id", "0" * 32),
            ("source_ledger_sha256", "0" * 64),
        ]:
            with self.subTest(field=name):
                path.write_bytes(original)
                rewrite_record(
                    path, lambda record, name=name, value=value: record.update({name: value})
                )
                with self.assertRaises(ValidationError):
                    self.verify(fixture)

    def cli(self, fixture, evidence=None):
        evidence = evidence_for(fixture) if evidence is None else evidence
        input_path = fixture.root / "operator-evidence.json"
        input_path.write_bytes(_canonical(evidence) + b"\n")
        before = source_snapshot(evidence)
        input_before = (input_path.read_bytes(), input_path.stat().st_mtime_ns)
        output, errors = io.StringIO(), io.StringIO()
        try:
            with (
                readonly_boundary(cli=True),
                redirect_stdout(output),
                redirect_stderr(errors),
            ):
                code = main(
                    [
                        "search-verify",
                        "--run",
                        str(fixture.directory),
                        "--evidence",
                        str(input_path),
                    ]
                )
        finally:
            self.assertEqual(before, source_snapshot(evidence))
            self.assertEqual(input_before, (input_path.read_bytes(), input_path.stat().st_mtime_ns))
        return code, json.loads(output.getvalue())

    def test_search_verify_cli_verified_json_exit_zero_is_readonly_and_needs_no_credentials(self):
        fixture = ordinary(self)
        code, result = self.cli(fixture)
        self.assertEqual(code, 0)
        self.assertEqual(result["status"], "verified")
        self.assertEqual(result["checked"]["physical_operations"], 37)

    def test_search_verify_cli_incomplete_and_invalid_evidence_have_distinct_exit_codes(self):
        for mode, expected in [("incomplete", 3), ("invalid", 2)]:
            with self.subTest(mode=mode):
                fixture = ordinary(self, interrupted=mode == "incomplete")
                evidence = evidence_for(fixture)
                if mode == "invalid":
                    evidence["runs"][0]["files"]["operations.sqlite3"] = "0" * 64
                code, result = self.cli(fixture, evidence)
                self.assertEqual(code, expected)
                if mode == "invalid":
                    self.assertIn("error", result)
                else:
                    self.assertEqual(result["status"], "incomplete")
                    self.assertEqual(result["costs"]["reserved_microusd"], 104096)


if __name__ == "__main__":
    unittest.main()
