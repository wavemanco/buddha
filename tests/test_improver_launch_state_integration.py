"""One real supplied-worker v4 path across original search, freeze and final state."""

import copy
import json
import unittest
from unittest.mock import patch

from test_improver_launch_state import expected_inputs, files, inspect_keylessly, sha


def checkpoint(label, **metadata):
    print("[improver-state-checkpoint] " + json.dumps({"label": label, **metadata}), flush=True)


class ImproverLaunchStateIntegrationTests(unittest.TestCase):
    def test_checked_failed_descendants_preserve_real_two_starter_cell_final_flow(self):
        import test_improver_assessment as assessment_fixtures
        import test_improver_study as finite_fixtures

        from buddha import candidate_generation
        from buddha.releases import _json

        fixture = assessment_fixtures.ImproverAssessmentTests("runTest")
        self.addCleanup(fixture.doCleanups)
        fixture.setUp()
        fixture.fixture(proposal_capacity=True)
        harness = finite_fixtures.ImproverStudyCapacityTests("runTest")
        _, development = harness.fixture(finite_fixture=fixture.f)
        # These are genuine terminal child-generation failures under the
        # existing supplied-worker protocol. Both declared opportunities occur;
        # no freeze, selection, report or scheduled cell is fabricated.
        fixture.f.outcomes = {(0, 0, arm, 0): "failed" for arm in range(2)}
        definition = copy.deepcopy(fixture.definition)
        definition.update(
            format="buddha.improver-assessment-trial.v4",
            development=fixture.write("state-integration-development.json", development),
        )
        definition["phase_limits"]["search"] = copy.deepcopy(development["limits"]["study"])
        fixture.bind("state-integration", definition=definition)
        outer = fixture.root / "synthetic-state-integration-launch.json"
        outer.write_bytes(b"Frozen synthetic launch input; no live spending.\n")
        bindings = {outer: sha(outer.read_bytes())}
        fixture.api.prepare_improver_assessment_trial(
            fixture.trial,
            declaration=fixture.declaration,
            expected_sha256=sha(fixture.declaration.read_bytes()),
            expected_runtime_sha256=fixture.engine.candidate.expected_runtime,
            authorizations=fixture.authorities,
            development_review=fixture.engine.fixture.review,
            input_bindings=bindings,
        )
        expected = expected_inputs(fixture, bindings)

        def inspect():
            return inspect_keylessly(self, fixture, fixture.trial, expected)

        prepared = inspect()
        self.assertEqual(prepared["phase"], "search")
        checkpoint("prepared", phase=prepared["phase"], root=str(fixture.root))
        developed = fixture.develop()
        self.assertEqual(developed["status"], "complete")
        self.assertEqual(developed["coverage"]["completed_opportunities"], 2)
        after_development = inspect()
        self.assertEqual(after_development["phase"], "freeze")
        checkpoint(
            "development_complete",
            phase=after_development["phase"],
            coverage=developed["coverage"],
            totals=after_development["totals"],
        )
        schedule = fixture.freeze()
        self.assertEqual(schedule["counts"]["maximum_cells"], 6)
        self.assertEqual(schedule["counts"]["cells"], 2)
        self.assertEqual(schedule["counts"]["no_valid_descendant_slots"], 2)
        self.assertTrue(all(arm["role"] == "starter" for arm in schedule["arms"]))
        frozen = inspect()
        self.assertEqual(frozen["phase"], "final")
        self.assertEqual(frozen["phases"]["final"]["owner_count"], 0)
        checkpoint("frozen", phase=frozen["phase"], counts=schedule["counts"])

        ready_path = fixture.trial / "freeze/ready.json"
        ready_raw = ready_path.read_bytes()
        try:
            changed = json.loads(ready_raw)
            changed["schedule_sha256"] = "0" * 64
            ready_path.write_bytes(_json(changed))
            with self.assertRaises(fixture.Error):
                inspect()
        finally:
            ready_path.write_bytes(ready_raw)

        run_generation = candidate_generation.run_candidate_generation
        stopped = []

        def stop_after_original_generation(*args, **kwargs):
            result = run_generation(*args, **kwargs)
            if not stopped and args[0].is_relative_to(fixture.trial / "final"):
                self.assertEqual(result["status"], "complete")
                stopped.append(args[0])
                raise KeyboardInterrupt("synthetic known-generation observation cut")
            return result

        with (
            fixture.supplied(),
            patch.object(
                candidate_generation,
                "run_candidate_generation",
                side_effect=stop_after_original_generation,
            ),
            self.assertRaises(KeyboardInterrupt),
        ):
            fixture.run_assessment()
        self.assertEqual(len(stopped), 1)
        partial = inspect()
        self.assertEqual(partial["phase"], "final")
        self.assertEqual(partial["next_position"]["stage"], "native")
        self.assertEqual(partial["phases"]["final"]["operation_count"], 1)
        self.assertEqual(partial["phases"]["final"]["status_counts"]["completed"], 1)
        preserved_generation = files(stopped[0])
        checkpoint("final_partial", phase=partial["phase"], position=partial["next_position"])

        with fixture.supplied():
            result = fixture.run_assessment()
        self.assertEqual(result["status"], "complete")
        self.assertEqual(result["coverage"], {"expected": 2, "generated": 2, "evaluated": 2})
        self.assertEqual(files(stopped[0]), preserved_generation)
        complete = inspect()
        self.assertEqual((complete["phase"], complete["state"]), ("complete", "complete"))
        self.assertFalse(complete["busy"])
        self.assertEqual(complete["totals"]["reserved_microusd"], 0)
        self.assertEqual(
            complete["totals"]["spent_microusd"],
            sum(
                authority.summary()["spent_microusd"] for authority in fixture.authorities.values()
            ),
        )
        self.assertEqual(inspect(), complete)
        checkpoint(
            "complete",
            phase=complete["phase"],
            coverage=result["coverage"],
            totals=complete["totals"],
        )


if __name__ == "__main__":
    unittest.main()
