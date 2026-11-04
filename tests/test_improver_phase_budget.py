"""Explicit aggregate limits with real original owners and supplied workers/replies."""

import copy
import unittest

import test_improver_assessment as assessment_fixtures
import test_improver_study as finite_fixtures
from test_improver_study import sha

from buddha import improver_study
from buddha.authorization import Authorization
from buddha.releases import ReleaseError, _json


class ImproverPhaseBudgetTests(unittest.TestCase):
    def finite_fixture(self):
        f = finite_fixtures.FiniteImproverStudyTests("runTest")
        self.addCleanup(f.doCleanups)
        f.fixture_before_new_api()
        finite_fixtures.observe_fixture_workers(f, self)
        f.api = improver_study
        record = f.declaration(improver_study)
        record.update(starts=record["starts"][:1], repetitions=1, descendant_opportunities=1)
        record["selection"]["finalist_iteration"] = 1
        f.recompute_limits(record)
        return f, record

    def assessment_fixture(self):
        f = assessment_fixtures.ImproverAssessmentTests("runTest")
        self.addCleanup(f.doCleanups)
        f.setUp()
        f.fixture(observer=self)
        f.finite["format"] = "buddha.improver-study.v2"
        for key in ("budget_microusd", "max_calls"):
            f.finite["limits"]["study"][key] -= 1
        f.definition["format"] = "buddha.improver-assessment-trial.v2"
        f.definition["development"] = f.write("aggregate-development.json", f.finite)
        f.definition["phase_limits"]["search"] = copy.deepcopy(f.finite["limits"]["study"])
        for key in ("budget_microusd", "max_calls"):
            f.definition["phase_limits"]["final"][key] -= 1
        return f

    def test_aggregate_declaration_is_explicit_bounded_and_preserves_nominal_cells(self):
        f, legacy = self.finite_fixture()
        runtime = f.engine.candidate.expected_runtime
        record = copy.deepcopy(legacy)
        record["format"] = "buddha.improver-study.v2"
        record["limits"]["study"] = {"budget_microusd": 1, "max_calls": 1}
        parsed, _ = improver_study._declaration(record, runtime)
        self.assertEqual(parsed, record)
        for name in ("common_cell", "arm_cell"):
            self.assertEqual(parsed["limits"][name], legacy["limits"][name])
        bad = copy.deepcopy(record)
        bad["format"] = legacy["format"]
        cases = [bad]
        for key in ("budget_microusd", "max_calls"):
            for value in (0, -1, True, 1.0, "1", legacy["limits"]["study"][key] + 1):
                bad = copy.deepcopy(record)
                bad["limits"]["study"][key] = value
                cases.append(bad)
        for section in ("common_cell", "arm_cell"):
            bad = copy.deepcopy(record)
            bad["limits"][section]["max_calls"] -= 1
            cases.append(bad)
        for location in ((), ("study",)):
            bad = copy.deepcopy(record)
            target = bad["limits"] if not location else bad["limits"][location[0]]
            target["extra"] = 1
            cases.append(bad)
        for bad in cases:
            with self.subTest(limits=bad["limits"], format=bad["format"]):
                with self.assertRaises(ReleaseError):
                    improver_study._declaration(bad, runtime)
        self.assertEqual(improver_study._declaration(legacy, runtime)[0], legacy)

    def test_exact_aggregate_authority_and_no_send_partial_replay(self):
        f, record = self.finite_fixture()
        record["format"] = "buddha.improver-study.v2"
        record["limits"]["study"] = {"budget_microusd": 1, "max_calls": 1}
        declaration = f.root / "aggregate.json"
        declaration.write_bytes(_json(record))
        for key, adjustment in (
            ("budget_microusd", -1),
            ("budget_microusd", 1),
            ("max_calls", -1),
            ("max_calls", 1),
        ):
            limits = dict(record["limits"]["study"])
            limits[key] += adjustment
            authority = Authorization.create(
                f.root / (key + str(adjustment) + ".sqlite3"),
                authorization_id=key,
                scope="source screen: " + f.base.comparison_key(),
                **limits,
            )
            directory = f.root / (key + str(adjustment))
            before = authority.summary()
            with self.assertRaisesRegex(improver_study.ImproverStudyError, "aggregate"):
                improver_study.prepare_improver_study(
                    directory,
                    declaration=declaration,
                    expected_sha256=sha(declaration.read_bytes()),
                    authorization=authority,
                    review=f.engine.fixture.review,
                    expected_runtime_sha256=f.engine.candidate.expected_runtime,
                )
            self.assertFalse(directory.exists())
            self.assertEqual(authority.summary(), before)
        for label, limits, sends in (
            ("before-first-hold", {"budget_microusd": 1, "max_calls": 1}, 0),
            ("dollar-stop", {"budget_microusd": 300, "max_calls": 20}, 1),
            ("call-stop", {"budget_microusd": 10000, "max_calls": 1}, 1),
        ):
            with self.subTest(label=label):
                record["limits"]["study"] = limits
                directory, _, authority = f.prepare_study(label, record)
                before = f.engine.physical_sends
                partial = f.run_study(directory)
                self.assertEqual(
                    (partial["status"], partial["reason"]), ("incomplete", "authority")
                )
                self.assertEqual(partial["coverage"]["expected_common"], 1)
                self.assertEqual(partial["coverage"]["expected_opportunities"], 2)
                self.assertEqual(partial["coverage"]["completed_opportunities"], 0)
                self.assertEqual(partial["authorization"]["reserved_microusd"], 0)
                self.assertEqual(partial["authorization"]["spent_microusd"], 11 * sends)
                self.assertFalse((directory / "report.json").exists())
                owners = f.owner_paths(directory)
                repeated = f.run_study(directory)
                self.assertEqual(repeated["reason"], "authority")
                self.assertEqual(repeated["coverage"], partial["coverage"])
                self.assertEqual(f.engine.physical_sends - before, sends)
                self.assertEqual(authority.summary()["operation_count"], sends)
                self.assertEqual(f.owner_paths(directory), owners)
        legacy = f.declaration(improver_study)
        legacy.update(starts=legacy["starts"][:1], repetitions=1, descendant_opportunities=1)
        legacy["selection"]["finalist_iteration"] = 1
        f.recompute_limits(legacy)
        declaration.write_bytes(_json(legacy))
        authority = Authorization.create(
            f.root / "larger-legacy.sqlite3",
            authorization_id="larger-legacy",
            scope="source screen: " + f.base.comparison_key(),
            **{key: value + 1 for key, value in legacy["limits"]["study"].items()},
        )
        directory = f.root / "larger-legacy"
        before = f.engine.physical_sends
        self.assertEqual(
            improver_study.prepare_improver_study(
                directory,
                declaration=declaration,
                expected_sha256=sha(declaration.read_bytes()),
                authorization=authority,
                review=f.engine.fixture.review,
                expected_runtime_sha256=f.engine.candidate.expected_runtime,
            ),
            directory,
        )
        self.assertEqual(f.engine.physical_sends, before)

    def test_assessment_versions_and_each_phase_bound_refuse_mixed_semantics(self):
        f = self.assessment_fixture()
        runtime = f.engine.candidate.expected_runtime
        parsed = f.api._definition(_json(f.definition), runtime)
        self.assertEqual(parsed["record"], f.definition)
        cases = []
        bad = copy.deepcopy(f.definition)
        bad["format"] = "buddha.improver-assessment-trial.v1"
        cases.append(bad)
        legacy = copy.deepcopy(f.finite)
        legacy["format"] = "buddha.improver-study.v1"
        f.f.recompute_limits(legacy)
        bad = copy.deepcopy(f.definition)
        bad["development"] = f.write("legacy-development.json", legacy)
        bad["phase_limits"]["search"] = copy.deepcopy(legacy["limits"]["study"])
        cases.append(bad)
        for phase in ("search", "validation", "final"):
            for key in ("budget_microusd", "max_calls"):
                bad = copy.deepcopy(f.definition)
                bad["phase_limits"][phase][key] = (
                    0 if phase == "final" else bad["phase_limits"][phase][key] + 1
                )
                cases.append(bad)
        for key in ("budget_microusd", "max_calls"):
            for value in (True, "1", 1.0, 2**63, f.definition["phase_limits"]["final"][key] + 2):
                bad = copy.deepcopy(f.definition)
                bad["phase_limits"]["final"][key] = value
                cases.append(bad)
        for bad in cases:
            with self.subTest(format=bad["format"], limits=bad["phase_limits"]):
                with self.assertRaises(ReleaseError):
                    f.api._definition(_json(bad), runtime)

    def test_aggregate_complete_trial_and_passive_authority_mismatch(self):
        f = self.assessment_fixture()
        f.bind("aggregate-complete")
        f.prepare()
        f.develop()
        f.freeze()
        with f.supplied():
            result = f.run_assessment()
        self.assertEqual(result["status"], "complete")
        self.assertEqual(result["coverage"]["evaluated"], 6)
        self.assertEqual(result["analysis"]["coverage"]["maximum_rows"], 6)
        self.assertEqual(f.inspect(), result)
        before = f.engine.physical_sends
        # Narrow census probe: genuine captured funding against a smaller in-memory
        # declaration. No SQL or saved evidence is edited or substituted.
        from buddha.native_evidence import NativeEvidence

        for key in ("budget_microusd", "max_calls"):
            reader = NativeEvidence(
                f.study,
                f.authorities["search"].path,
                error_type=improver_study.ImproverStudyError,
            )
            state = improver_study._original(reader)
            state["record"]["limits"]["study"][key] -= 1
            with self.assertRaisesRegex(improver_study.ImproverStudyError, "aggregate"):
                improver_study._census(reader, state)
        self.assertEqual(f.engine.physical_sends, before)

    def test_aggregate_final_stop_keeps_full_schedule_and_original_owners(self):
        f = self.assessment_fixture()
        f.definition["phase_limits"]["final"] = {"budget_microusd": 1, "max_calls": 1}
        f.bind("aggregate-final-partial")
        f.prepare()
        f.develop()
        schedule = f.freeze()
        before = f.engine.physical_sends
        with f.supplied():
            partial = f.run_assessment()
        self.assertEqual((partial["status"], partial["reason"]), ("incomplete", "authority"))
        self.assertEqual(partial["coverage"]["expected"], 6)
        self.assertEqual(partial["coverage"]["evaluated"], 0)
        self.assertEqual(partial["authorization"]["spent_microusd"], 0)
        self.assertEqual(partial["authorization"]["reserved_microusd"], 0)
        self.assertEqual(schedule["counts"]["maximum_cells"], 6)
        owners = f.f.owner_paths(f.trial / "final")
        with f.supplied():
            repeated = f.run_assessment()
        self.assertEqual(repeated["coverage"], partial["coverage"])
        self.assertEqual(f.f.owner_paths(f.trial / "final"), owners)
        self.assertEqual(f.engine.physical_sends, before)
        self.assertFalse((f.trial / "final/report.json").exists())


if __name__ == "__main__":
    unittest.main()
