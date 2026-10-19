"""Bounded policy-search acceptance using synthetic, billed replay receipts."""

import hashlib
import json
import sqlite3
import tempfile
import unittest
from contextlib import closing
from dataclasses import replace
from pathlib import Path
from unittest.mock import patch

from buddha.evaluation import ValidationError
from buddha.ledger import BudgetExceeded
from buddha.policy import Policy
from buddha.provider import BudgetBroker, ModelSpec, PendingOperation, ProviderUncertain
from buddha.run import ReplayTransport, RunSettings, _sha
from buddha.search import SearchSpec, inspect_search, load_search, prepare_search, run_search


def settings(**changes):
    profiles = [
        ModelSpec("replay", model, 100000, cap, 1000000, 1000000, "offline fixture")
        for model, cap in [("generator", 4096), ("partition", 16000), ("quality", 16000)]
    ]
    return replace(
        RunSettings(*profiles, budget_microusd=10_000_000, max_calls=1000, bounds_verified=False),
        **changes,
    )


class PolicyTransport(ReplayTransport):
    def __init__(self, proposals=None):
        super().__init__()
        self.proposals = proposals
        self.proposer_calls = 0
        self.bodies = []

    def send(self, call):
        body = json.loads(call.body_json)
        self.bodies.append(body)
        schema = body.get("response_format", {}).get("json_schema", {}).get("name")
        reply = super().send(call)
        if schema == "Policy":
            index = self.proposer_calls
            self.proposer_calls += 1
            value = (
                {"instructions": f"Variant {index}", "sampling": "regenerate"}
                if self.proposals is None
                else self.proposals[index]
            )
            return replace(reply, text=value if isinstance(value, str) else json.dumps(value))
        return reply


class SearchTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)
        self.dataset = self.root / "source.jsonl"
        self.dataset.write_text(
            "".join(
                json.dumps({"id": name, "prompt": text}) + "\n"
                for name, text in [
                    ("dev-a", "Give one short idea."),
                    ("dev-b", "Choose a useful action."),
                    ("validation", "VALIDATION_CANARY_X"),
                    ("final", "FINAL_CANARY_Y"),
                ]
            ),
            encoding="utf-8",
        )
        self.dataset_hash = hashlib.sha256(self.dataset.read_bytes()).hexdigest()
        self.directory = self.root / "search"
        self.splits = {
            "development": ["dev-a", "dev-b"],
            "validation": ["validation"],
            "final": ["final"],
        }

    def prepare(self, spec=None, selected=None):
        return prepare_search(
            self.directory,
            dataset_path=self.dataset,
            expected_dataset_sha256=self.dataset_hash,
            settings=settings() if selected is None else selected,
            spec=SearchSpec(iterations=2, screen_size=1) if spec is None else spec,
            splits=self.splits,
            synthetic=True,
        )

    def test_spec_rejects_unbounded_or_boolean_controls(self):
        for changes in (
            {"iterations": -1},
            {"iterations": True},
            {"iterations": 257},
            {"max_active": 1},
            {"max_active": 65},
            {"seed": -1},
            {"seed": False},
            {"seed": 2**63},
            {"screen_size": 0},
            {"screen_size": 1001},
            {"method": "random"},
        ):
            with self.subTest(changes=changes), self.assertRaises(ValidationError):
                SearchSpec(**changes)

    def test_prepare_freezes_verified_source_full_splits_and_common_screen(self):
        self.prepare()
        manifest, selected, spec, prompts = load_search(self.directory)
        self.assertEqual(manifest["splits"], self.splits)
        self.assertEqual(len(prompts), 1)
        self.assertIn(prompts[0].id, self.splits["development"])
        self.assertEqual((self.directory / "dataset.jsonl").read_bytes(), self.dataset.read_bytes())
        self.assertEqual(selected, settings())
        self.assertEqual(spec.iterations, 2)

    def test_complete_resume_no_duplicate_calls_and_common_coverage(self):
        self.prepare()
        transport = PolicyTransport()
        first = run_search(self.directory, transport=transport)
        self.assertEqual(first["status"], "complete")
        self.assertIs(first["synthetic"], True)
        self.assertEqual(len(first["candidates"]), 4)
        self.assertEqual(transport.calls, 50)
        self.assertEqual(run_search(self.directory, transport=transport), first)
        self.assertEqual(transport.calls, 50)
        self.assertEqual(inspect_search(self.directory), first)
        policies = list((self.directory / "candidates").glob("*/policy.json"))
        self.assertEqual(len(policies), 4)
        for candidate in first["candidates"]:
            self.assertEqual(candidate["summary"]["scored_count"], 1)

    def test_resume_after_durable_proposal_or_mid_child_completion(self):
        original = BudgetBroker.execute
        for breakpoint in (25, 29):
            with self.subTest(after_completed_operation=breakpoint):
                self.directory = self.root / f"resume-{breakpoint}"
                self.prepare()
                transport = PolicyTransport()
                interrupted = False

                def interrupt_after_receipt(
                    broker, operation_id, call, selected_transport=transport, stop_after=breakpoint
                ):
                    nonlocal interrupted
                    result = original(broker, operation_id, call)
                    if not interrupted and selected_transport.calls == stop_after:
                        interrupted = True
                        raise KeyboardInterrupt
                    return result

                with patch.object(BudgetBroker, "execute", interrupt_after_receipt):
                    with self.assertRaises(KeyboardInterrupt):
                        run_search(self.directory, transport=transport)
                report = run_search(self.directory, transport=transport)
                self.assertEqual(transport.calls, 50)
                self.assertEqual(report["costs"]["operation_count"], 50)
                self.assertEqual(report["costs"]["spent_microusd"], 750)

    def test_orphan_temporary_first_policy_file_does_not_block_resume(self):
        self.prepare()
        candidate_dir = self.directory / "candidates" / Policy().fingerprint()
        candidate_dir.mkdir(parents=True)
        orphan = candidate_dir / ".write-interrupted"
        orphan.write_text("incomplete, unpublished bytes")
        transport = PolicyTransport()
        self.assertEqual(run_search(self.directory, transport=transport)["status"], "complete")
        self.assertEqual(transport.calls, 50)
        self.assertEqual(orphan.read_text(), "incomplete, unpublished bytes")

    def test_rehashed_wrong_decision_is_rejected_before_missing_child_receipt_can_dispatch(self):
        self.prepare()
        transport = PolicyTransport()
        report = run_search(self.directory, transport=transport)
        decision_path = self.directory / "decisions" / "iteration-000000.json"
        decision = json.loads(decision_path.read_text())
        child_id = decision["candidate_id"]
        decision["policy"]["instructions"] = "Altered, self-rehashed decision"
        decision.pop("record_sha256")
        decision["record_sha256"] = _sha(decision)
        decision_path.write_text(json.dumps(decision))
        missing = _sha(
            [report["run_id"], "candidate", child_id, report["screen_ids"][0], "generation", 0]
        )
        # Deliberately corrupt the fixture's DB to model a missing durable receipt.
        # Production code keeps the append-only trigger intact.
        with closing(sqlite3.connect(self.directory / "operations.sqlite3")) as connection:
            connection.execute("DROP TRIGGER operations_no_delete")
            connection.execute("DELETE FROM operations WHERE operation_id=?", (missing,))
            connection.commit()
        with self.assertRaisesRegex(ValidationError, "saved decision differs"):
            run_search(self.directory, transport=transport)
        self.assertEqual(transport.calls, 50)

    def test_complete_cost_breakdown_accounts_for_every_completed_operation_once(self):
        self.prepare()
        report = run_search(self.directory, transport=PolicyTransport())
        costs = report["costs"]
        self.assertEqual(
            costs["by_stage_microusd"],
            {"generation": 600, "partition": 60, "score": 60, "proposal": 30},
        )
        self.assertEqual(sum(costs["by_stage_microusd"].values()), costs["spent_microusd"])
        self.assertEqual(costs["seed_evaluation_microusd"], 360)
        self.assertEqual(costs["child_evaluation_microusd"], 360)
        self.assertEqual(costs["proposal_microusd"], 30)
        self.assertEqual(sum(costs["by_candidate_microusd"].values()), 720)
        self.assertEqual(sum(item["evaluation_microusd"] for item in report["candidates"]), 720)
        self.assertEqual(inspect_search(self.directory)["costs"], costs)

    def test_critical_evaluator_and_broker_source_changes_invalidate_frozen_search(self):
        self.prepare()
        manifest, _, _, _ = load_search(self.directory)
        critical = {"benchmark", "evaluation", "provider", "ledger"}
        self.assertTrue(
            {f"buddha.{name}" for name in critical} <= set(manifest["contracts"]["source_sha256"])
        )
        altered_source = self.root / "altered-source.py"
        altered_source.write_text("# different evaluator or broker behavior\n")
        for name in critical:
            with (
                self.subTest(module=name),
                patch(f"buddha.search.{name}.__file__", str(altered_source)),
            ):
                transport = PolicyTransport()
                with self.assertRaises(ValidationError):
                    run_search(self.directory, transport=transport)
                self.assertEqual(transport.calls, 0)

    def test_seed_namespaces_prevent_reusing_same_initial_generation_requests(self):
        self.prepare(SearchSpec(iterations=0, screen_size=1))
        transport = PolicyTransport()
        report = run_search(self.directory, transport=transport)
        self.assertEqual(transport.calls, 24)
        self.assertEqual(report["costs"]["operation_count"], 24)
        self.assertNotEqual(
            report["candidates"][0]["summary"]["protocol_fingerprint"],
            report["candidates"][1]["summary"]["protocol_fingerprint"],
        )

    def test_invalid_and_duplicate_proposals_consume_iterations_and_keep_receipts(self):
        self.prepare(SearchSpec(iterations=3, screen_size=1))
        transport = PolicyTransport(
            [
                "not JSON",
                Policy().to_record(),
                {"instructions": "A valid new policy", "sampling": "regenerate"},
            ]
        )
        report = run_search(self.directory, transport=transport)
        self.assertEqual(
            [item["status"] for item in report["decisions"]], ["invalid", "duplicate", "admitted"]
        )
        self.assertEqual(len(report["candidates"]), 3)
        self.assertEqual(transport.calls, 39)
        self.assertGreater(report["costs"]["spent_microusd"], 0)
        run_search(self.directory, transport=transport)
        self.assertEqual(transport.calls, 39)

    def test_only_common_development_screen_enters_proposer_requests(self):
        self.prepare(SearchSpec(iterations=2, screen_size=1))
        transport = PolicyTransport()
        run_search(self.directory, transport=transport)
        for body in transport.bodies:
            encoded = json.dumps(body)
            self.assertNotIn("VALIDATION_CANARY_X", encoded)
            self.assertNotIn("FINAL_CANARY_Y", encoded)
        proposals = [
            body
            for body in transport.bodies
            if body.get("response_format", {}).get("json_schema", {}).get("name") == "Policy"
        ]
        self.assertEqual(len(proposals), 2)
        for body in proposals:
            packet = json.loads(body["messages"][-1]["content"])
            self.assertEqual(len(packet["feedback"]), 1)
            self.assertIn(packet["feedback"][0]["id"], self.splits["development"])

    def test_uninformed_has_initial_parent_and_no_feedback(self):
        self.prepare(SearchSpec(iterations=2, screen_size=1, method="uninformed"))
        transport = PolicyTransport()
        report = run_search(self.directory, transport=transport)
        for body in transport.bodies:
            if body.get("response_format", {}).get("json_schema", {}).get("name") == "Policy":
                packet = json.loads(body["messages"][-1]["content"])
                self.assertEqual(packet["feedback"], [])
                self.assertEqual(packet["parent"], Policy().to_record())
        self.assertEqual(len({item["parent_id"] for item in report["decisions"]}), 1)

    def test_global_call_budget_includes_both_seeds_proposal_and_child(self):
        self.prepare(selected=settings(max_calls=25))
        transport = PolicyTransport()
        with self.assertRaises(BudgetExceeded):
            run_search(self.directory, transport=transport)
        self.assertEqual(transport.calls, 25)
        with self.assertRaises(BudgetExceeded):
            run_search(self.directory, transport=transport)
        self.assertEqual(transport.calls, 25)
        self.assertEqual(inspect_search(self.directory)["status"], "incomplete")

    def test_global_money_budget_counts_all_prior_policy_costs(self):
        self.prepare(selected=settings(budget_microusd=116350))
        transport = PolicyTransport()
        with self.assertRaises(BudgetExceeded):
            run_search(self.directory, transport=transport)
        self.assertEqual(transport.calls, 35)
        report = inspect_search(self.directory)
        self.assertEqual(report["costs"]["spent_microusd"], 525)
        self.assertEqual(report["costs"]["reserved_microusd"], 0)

    def test_proposal_invalid_utf8_is_preserved_as_invalid_completed_attempt(self):
        self.prepare(SearchSpec(iterations=1, screen_size=1))
        transport = PolicyTransport(["\ud800"])
        report = run_search(self.directory, transport=transport)
        self.assertEqual(report["decisions"][0]["status"], "invalid")
        self.assertEqual(transport.calls, 25)

    def test_unknown_proposer_stops_instead_of_becoming_invalid(self):
        class FailingProposer(PolicyTransport):
            def send(self, call):
                if '"name":"Policy"' in call.body_json:
                    self.calls += 1
                    raise TimeoutError("uncertain dispatch")
                return super().send(call)

        self.prepare()
        transport = FailingProposer()
        with self.assertRaises(ProviderUncertain):
            run_search(self.directory, transport=transport)
        self.assertEqual(transport.calls, 25)
        with self.assertRaises(PendingOperation):
            run_search(self.directory, transport=transport)
        self.assertEqual(transport.calls, 25)

    def test_bad_judge_stops_and_cannot_be_regenerated_on_resume(self):
        class BadJudge(PolicyTransport):
            def send(self, call):
                reply = super().send(call)
                return (
                    replace(reply, text='{"groups":[[0,0]]}')
                    if call.spec.model == "partition"
                    else reply
                )

        self.prepare()
        transport = BadJudge()
        for _ in range(2):
            with self.assertRaises(ValidationError):
                run_search(self.directory, transport=transport)
            self.assertEqual(transport.calls, 11)
        self.assertEqual(transport.proposer_calls, 0)

    def test_manifest_or_source_tamper_rejected_before_dispatch(self):
        self.prepare()
        path = self.directory / "manifest.json"
        manifest = json.loads(path.read_text())
        manifest["screen_ids"] = ["final"]
        path.write_text(json.dumps(manifest))
        transport = PolicyTransport()
        with self.assertRaises(ValidationError):
            run_search(self.directory, transport=transport)
        self.assertEqual(transport.calls, 0)

    def test_completed_artifact_tamper_rejected_before_new_calls(self):
        self.prepare()
        transport = PolicyTransport()
        run_search(self.directory, transport=transport)
        target = next((self.directory / "candidates").glob("*/evaluation/generations.jsonl"))
        target.write_text("{}\n")
        before = transport.calls
        with self.assertRaises(ValidationError):
            run_search(self.directory, transport=transport)
        self.assertEqual(transport.calls, before)

    def test_lock_conflict_stops_before_dispatch(self):
        self.prepare()
        (self.directory / ".search.lock").write_text("another writer")
        transport = PolicyTransport()
        with self.assertRaises(ValidationError):
            run_search(self.directory, transport=transport)
        self.assertEqual(transport.calls, 0)
        self.assertEqual((self.directory / ".search.lock").read_text(), "another writer")

    def test_inspect_unstarted_run_does_not_create_paid_operations(self):
        self.prepare()
        report = inspect_search(self.directory)
        self.assertEqual(report["status"], "incomplete")
        self.assertEqual(report["costs"]["operation_count"], 0)

    def test_oversized_screen_rejected_before_destination_creation(self):
        with self.assertRaises(ValidationError):
            self.prepare(SearchSpec(screen_size=3))
        self.assertFalse(self.directory.exists())


if __name__ == "__main__":
    unittest.main()
