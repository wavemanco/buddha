"""One actual matched-launch lifecycle with synthetic workers and original grants.

Both declared child opportunities fail through the existing worker protocol.
The resulting two starter cells exercise final cancellation and same-owner
recovery; this is neither a full six-cell timing check nor scientific evidence.
"""

import copy
import json
import unittest
from pathlib import Path
from unittest.mock import patch

from test_improver_launch_state import files, passive_only, sha

AMOUNTS = ("spent_microusd", "reserved_microusd", "committed_microusd", "operation_count")


def checkpoint(label, **metadata):
    print("[improver-launch-checkpoint] " + json.dumps({"label": label, **metadata}), flush=True)


class ImproverLaunchIntegrationTests(unittest.TestCase):
    def test_original_launch_cancel_resume_and_keyless_completed_retirement(self):
        import test_improver_assessment as assessment_fixtures
        import test_improver_launch as launch_fixtures
        import test_improver_study as finite_fixtures

        from buddha import candidate_generation, improver_handoff, improver_launch
        from buddha.gateway import RawHTTPTransport

        fixture = assessment_fixtures.ImproverAssessmentTests("runTest")
        self.addCleanup(fixture.doCleanups)
        fixture.setUp()
        fixture.fixture(proposal_capacity=True)
        harness = finite_fixtures.ImproverStudyCapacityTests("runTest")
        _, development = harness.fixture(finite_fixture=fixture.f)
        fixture.f.outcomes = {(0, 0, arm, 0): "failed" for arm in range(2)}
        definition = copy.deepcopy(fixture.definition)
        definition.update(
            format="buddha.improver-assessment-trial.v4",
            development=fixture.write("launch-integration-development.json", development),
        )
        definition["phase_limits"]["search"] = copy.deepcopy(development["limits"]["study"])
        builder = launch_fixtures.ImproverLaunchTests("runTest")
        builder.f, builder.definition, builder.root = fixture, definition, fixture.root
        builder.api, builder.handoff = improver_launch, improver_handoff
        builder.setUp()
        bundle = builder.bundle()
        launch_pin = sha(bundle["path"].read_bytes())
        approval_raw = bundle["approval_path"].read_bytes()
        original_grants = copy.deepcopy(bundle["approval"]["authorizations"])
        first_receipt = bundle["folder"] / "cancelled-receipt.json"
        complete_receipt = bundle["folder"] / "complete-receipt.json"
        self.assertFalse(bundle["directory"].exists())
        self.assertFalse(bundle["review_path"].exists())
        checkpoint("fresh_fixture", root=str(fixture.root), phase="search")

        # The real controller publishes the schedule. The supplied executor
        # reads that actual schedule solely to choose its synthetic native row.
        execute = fixture.execute
        first_final_worker = []

        def scheduled_execute(spec, *, initial, handle, **kwargs):
            if handle.__self__.gateway.directory.is_relative_to(fixture.trial / "final"):
                fixture.schedule = json.loads((fixture.trial / "freeze/schedule.json").read_bytes())
                if not first_final_worker:
                    first_final_worker.append(True)
                    checkpoint("original_final_worker", counts=fixture.schedule["counts"])
            return execute(spec, initial=initial, handle=handle, **kwargs)

        fixture.execute = scheduled_execute
        original_generation = candidate_generation.run_candidate_generation
        stopped = []

        def stop_after_completed_final_generation(*args, **kwargs):
            result = original_generation(*args, **kwargs)
            directory = Path(args[0])
            if not stopped and directory.is_relative_to(fixture.trial / "final"):
                self.assertEqual(
                    (result["status"], result["disposition"]), ("complete", "generated")
                )
                stopped.append(directory)
                checkpoint("original_final_generation_complete", directory=str(directory))
                raise KeyboardInterrupt("synthetic known-generation observation cut")
            return result

        def launch(receipt):
            return improver_launch.launch(
                bundle["path"],
                expected_sha256=launch_pin,
                live=True,
                confirm_project_keys=True,
                receipt=receipt,
                transport=RawHTTPTransport(
                    allow_paid=True, timeout_seconds=bundle["record"]["timeout_seconds"]
                ),
                notice=lambda text: print("[improver-launch-notice] " + text, flush=True),
            )

        def assert_funding(receipt):
            funding = receipt["funding"]
            self.assertEqual(set(funding), {"phases", "totals"})
            self.assertEqual(set(funding["phases"]), set(original_grants))
            for phase, authority in bundle["authorities"].items():
                actual, expected = funding["phases"][phase], authority.summary()
                self.assertEqual(
                    {name: actual[name] for name in (*AMOUNTS, "budget_microusd", "max_calls")},
                    {name: expected[name] for name in (*AMOUNTS, "budget_microusd", "max_calls")},
                )
                for field, key in (
                    ("id", "authorization_id"),
                    ("terms_sha256", "terms_sha256"),
                    ("scope", "scope"),
                ):
                    self.assertEqual(expected[key], original_grants[phase][field])
                self.assertEqual(str(authority.path), original_grants[phase]["path"])
            self.assertEqual(
                funding["totals"],
                {name: sum(row[name] for row in funding["phases"].values()) for name in AMOUNTS},
            )
            self.assertEqual(funding["phases"]["validation"]["operation_count"], 0)
            self.assertEqual(funding["totals"]["reserved_microusd"], 0)

        with (
            fixture.supplied(),
            patch.object(
                candidate_generation,
                "run_candidate_generation",
                side_effect=stop_after_completed_final_generation,
            ),
            self.assertRaises(KeyboardInterrupt),
        ):
            launch(first_receipt)
        self.assertEqual(len(stopped), 1)
        cancelled_raw = first_receipt.read_bytes()
        cancelled = json.loads(cancelled_raw)
        self.assertEqual(cancelled["format"], "buddha.improver-launch-receipt.v1")
        self.assertEqual((cancelled["status"], cancelled["phase"]), ("cancelled", "final"))
        self.assertEqual(cancelled["reason"], "cancelled")
        self.assertTrue(cancelled["receipt_saved"])
        partial_path = fixture.trial / "final/observations/0.json"
        partial_raw = partial_path.read_bytes()
        partial = json.loads(partial_raw)
        self.assertEqual(partial["reason"], "cancelled")
        self.assertEqual(partial["position"]["stage"], "native")
        self.assertEqual(partial["coverage"], {"expected": 2, "generated": 1, "evaluated": 0})
        self.assertEqual(cancelled["position"], partial["position"])
        self.assertEqual(cancelled["coverage"], partial["coverage"])
        self.assertEqual(cancelled["observation"], "final/observations/0.json")
        assert_funding(cancelled)
        self.assertEqual(cancelled["funding"]["phases"]["final"]["operation_count"], 1)
        self.assertGreater(cancelled["funding"]["phases"]["search"]["spent_microusd"], 0)
        developed = json.loads((fixture.study / "report.json").read_bytes())
        self.assertEqual(developed["coverage"]["completed_opportunities"], 2)
        self.assertEqual(fixture.schedule["counts"]["maximum_cells"], 6)
        self.assertEqual(fixture.schedule["counts"]["cells"], 2)
        self.assertEqual(fixture.schedule["counts"]["no_valid_descendant_slots"], 2)
        self.assertTrue(all(arm["role"] == "starter" for arm in fixture.schedule["arms"]))
        self.assertEqual(
            [slot["status"] for slot in fixture.schedule["slots"]], ["no_valid_descendant"] * 2
        )
        generation_files = files(stopped[0])
        review_raw = bundle["review_path"].read_bytes()
        review = json.loads(review_raw)
        self.assertEqual(review["format"], "buddha.account-review.v2")
        self.assertEqual(review["credential_context"], launch_pin)
        self.assertEqual(fixture.schedule["review"], review)
        checkpoint(
            "cancelled",
            phase=cancelled["phase"],
            position=partial["position"],
            totals=cancelled["funding"]["totals"],
        )

        with fixture.supplied():
            complete = launch(complete_receipt)
        self.assertEqual(json.loads(complete_receipt.read_bytes()), complete)
        self.assertEqual((complete["status"], complete["phase"]), ("complete", "complete"))
        self.assertTrue(complete["receipt_saved"])
        assert_funding(complete)
        final_report = json.loads((fixture.trial / "final/report.json").read_bytes())
        self.assertEqual(final_report["coverage"], {"expected": 2, "generated": 2, "evaluated": 2})
        self.assertEqual(final_report["analysis"]["coverage"]["null_slots"], 2)
        self.assertEqual(files(stopped[0]), generation_files)
        self.assertEqual(partial_path.read_bytes(), partial_raw)
        self.assertEqual(first_receipt.read_bytes(), cancelled_raw)
        self.assertEqual(bundle["review_path"].read_bytes(), review_raw)
        self.assertEqual(bundle["approval_path"].read_bytes(), approval_raw)
        self.assertEqual(sha(bundle["path"].read_bytes()), launch_pin)
        checkpoint(
            "resumed_complete",
            phase=complete["phase"],
            coverage=final_report["coverage"],
            totals=complete["funding"]["totals"],
        )

        def keyless_complete():
            before = files(fixture.root), fixture.engine.physical_sends, fixture.engine.workers
            with passive_only(self):
                result = improver_launch.launch(
                    bundle["path"], expected_sha256=launch_pin, notice=lambda text: None
                )
            self.assertEqual(
                result, {key: value for key, value in complete.items() if key != "receipt_saved"}
            )
            self.assertEqual(
                (files(fixture.root), fixture.engine.physical_sends, fixture.engine.workers), before
            )

        keyless_complete()
        retired = []
        try:
            for name in ("I0", "I1", "S0", "S1"):
                source, destination = fixture.root / name, fixture.root / (name + "-retired")
                self.assertTrue(source.resolve().is_relative_to(fixture.root.resolve()))
                self.assertTrue(destination.resolve().is_relative_to(fixture.root.resolve()))
                self.assertFalse(destination.exists())
                source.rename(destination)
                retired.append((source, destination))
            keyless_complete()
        finally:
            for source, destination in reversed(retired):
                destination.rename(source)
        checkpoint("keyless_retired_complete", phase="complete", synthetic=True)


if __name__ == "__main__":
    unittest.main()
