"""Prospective comparison versions keep exact aggregate funding and old schemas."""

import copy
import unittest

import test_improver_assessment as assessment_fixtures
import test_improver_study as finite_fixtures
from test_improver_study import sha

from buddha import improver_assessment, improver_study
from buddha.authorization import Authorization
from buddha.releases import ReleaseError, _json

COMPARISON_POLICY = {
    "format": "buddha.improver-study-feedback-comparison.v1",
    "measurements": "complete_literal_outputs",
    "parent": "original_immediate_counted_edge_in_same_cell",
    "root": "no_counted_parent_in_this_cell",
    "counted_failures": "complete_original_cell_history",
    "mutation_witness": "complete_absolute_outputs",
}


class ImproverComparisonContractTests(unittest.TestCase):
    def assessment_fixture(self):
        f = assessment_fixtures.ImproverAssessmentTests("runTest")
        self.addCleanup(f.doCleanups)
        f.setUp()
        f.fixture(observer=self)
        return f

    @staticmethod
    def development(f, version):
        record = copy.deepcopy(f.finite)
        record["format"] = "buddha.improver-study.v" + str(version)
        if version >= 2:
            for key in ("budget_microusd", "max_calls"):
                record["limits"]["study"][key] -= 1
        if version == 3:
            record["feedback_comparison"] = dict(COMPARISON_POLICY)
        return record

    @staticmethod
    def definition(f, version, development, label):
        record = copy.deepcopy(f.definition)
        record["format"] = "buddha.improver-assessment-trial.v" + str(version)
        record["development"] = f.write(label + ".json", development)
        record["phase_limits"]["search"] = copy.deepcopy(development["limits"]["study"])
        if version >= 2:
            for key in ("budget_microusd", "max_calls"):
                record["phase_limits"]["final"][key] -= 1
        return record

    def test_all_nine_genuine_declaration_pairs_require_matching_versions(self):
        f = self.assessment_fixture()
        runtime = f.engine.candidate.expected_runtime
        before = f.engine.physical_sends, len(f.f.events)
        for assessment_version in (1, 2, 3):
            for study_version in (1, 2, 3):
                with self.subTest(assessment=assessment_version, study=study_version):
                    development = self.development(f, study_version)
                    # Every inner declaration must first be valid on its own;
                    # malformed inputs do not establish strict version pairing.
                    self.assertEqual(
                        improver_study._declaration(development, runtime)[0], development
                    )
                    definition = self.definition(
                        f,
                        assessment_version,
                        development,
                        "pair-" + str(assessment_version) + "-" + str(study_version),
                    )
                    if assessment_version == study_version:
                        parsed = improver_assessment._definition(
                            _json(definition), runtime, active=False
                        )
                        self.assertEqual(parsed["record"], definition)
                        self.assertEqual(parsed["development"], development)
                    else:
                        with self.assertRaisesRegex(ReleaseError, "versions must match"):
                            improver_assessment._definition(
                                _json(definition), runtime, active=False
                            )
        self.assertFalse(f.trial.exists())
        self.assertEqual((f.engine.physical_sends, len(f.f.events)), before)

    def test_comparison_policy_is_exact_and_legacy_schema_bytes_stay_unchanged(self):
        f = self.assessment_fixture()
        runtime = f.engine.candidate.expected_runtime
        before = f.engine.physical_sends, len(f.f.events)
        for version in (1, 2):
            legacy = self.development(f, version)
            original = _json(legacy)
            parsed, _ = improver_study._declaration(legacy, runtime)
            self.assertEqual(_json(parsed), original)
            with self.assertRaises(ReleaseError):
                improver_study._declaration(
                    legacy | {"feedback_comparison": dict(COMPARISON_POLICY)}, runtime
                )
        comparison = self.development(f, 3)
        self.assertEqual(improver_study._declaration(comparison, runtime)[0], comparison)
        invalid = copy.deepcopy(comparison)
        invalid.pop("feedback_comparison")
        cases = [invalid]
        for key in COMPARISON_POLICY:
            invalid = copy.deepcopy(comparison)
            invalid["feedback_comparison"][key] = "changed"
            cases.append(invalid)
        invalid = copy.deepcopy(comparison)
        invalid["feedback_comparison"]["extra"] = True
        cases.append(invalid)
        for invalid in cases:
            with self.subTest(policy=invalid.get("feedback_comparison")):
                with self.assertRaises(ReleaseError):
                    improver_study._declaration(invalid, runtime)
        self.assertFalse(f.trial.exists())
        self.assertEqual((f.engine.physical_sends, len(f.f.events)), before)

    def test_comparison_study_and_final_caps_are_positive_bounded_aggregates(self):
        f = self.assessment_fixture()
        runtime = f.engine.candidate.expected_runtime
        before = f.engine.physical_sends, len(f.f.events)
        development = self.development(f, 3)
        nominal = copy.deepcopy(f.finite["limits"])
        development["limits"]["study"] = {"budget_microusd": 1, "max_calls": 1}
        definition = self.definition(f, 3, development, "bounded-v3")
        definition["phase_limits"]["final"] = {"budget_microusd": 1, "max_calls": 1}
        parsed = improver_assessment._definition(_json(definition), runtime, active=False)
        self.assertEqual(parsed["record"], definition)
        for section in ("common_cell", "arm_cell"):
            self.assertEqual(parsed["development"]["limits"][section], nominal[section])
        for key in ("budget_microusd", "max_calls"):
            for value in (0, -1, True, 1.0, "1", nominal["study"][key] + 1):
                bad = copy.deepcopy(development)
                bad["limits"]["study"][key] = value
                with self.subTest(phase="study", key=key, value=value):
                    with self.assertRaises(ReleaseError):
                        improver_study._declaration(bad, runtime)
            maximum = f.definition["phase_limits"]["final"][key]
            for value in (0, -1, True, 1.0, "1", maximum + 1):
                bad = copy.deepcopy(definition)
                bad["phase_limits"]["final"][key] = value
                with self.subTest(phase="final", key=key, value=value):
                    with self.assertRaises(ReleaseError):
                        improver_assessment._definition(_json(bad), runtime, active=False)
        for section in ("common_cell", "arm_cell"):
            bad = copy.deepcopy(development)
            bad["limits"][section]["max_calls"] -= 1
            with self.subTest(section=section), self.assertRaises(ReleaseError):
                improver_study._declaration(bad, runtime)
        for phase in ("search", "validation"):
            for key in ("budget_microusd", "max_calls"):
                bad = copy.deepcopy(definition)
                bad["phase_limits"][phase][key] += 1
                with self.subTest(phase=phase, key=key), self.assertRaises(ReleaseError):
                    improver_assessment._definition(_json(bad), runtime, active=False)
        self.assertFalse(f.trial.exists())
        self.assertEqual((f.engine.physical_sends, len(f.f.events)), before)

    def test_comparison_prepare_requires_exact_grant_before_writes_or_owner_creation(self):
        f = finite_fixtures.FiniteImproverStudyTests("runTest")
        self.addCleanup(f.doCleanups)
        f.fixture_before_new_api()
        finite_fixtures.observe_fixture_workers(f, self)
        before_preparation = f.engine.physical_sends, len(f.events)
        f.api = improver_study
        record = f.declaration(improver_study)
        record.update(
            format="buddha.improver-study.v3",
            starts=record["starts"][:1],
            repetitions=1,
            descendant_opportunities=1,
            feedback_comparison=dict(COMPARISON_POLICY),
        )
        record["selection"]["finalist_iteration"] = 1
        f.recompute_limits(record)
        for key in ("budget_microusd", "max_calls"):
            record["limits"]["study"][key] -= 1
        declaration = f.root / "comparison-development.json"
        declaration.write_bytes(_json(record))
        for key in ("budget_microusd", "max_calls"):
            for adjustment in (-1, 1):
                label = key + str(adjustment)
                limits = dict(record["limits"]["study"])
                limits[key] += adjustment
                authority = Authorization.create(
                    f.root / (label + ".sqlite3"),
                    authorization_id=label,
                    scope="source screen: " + f.base.comparison_key(),
                    **limits,
                )
                directory = f.root / label
                before = authority.summary(), f.engine.physical_sends, len(f.events)
                with self.subTest(key=key, adjustment=adjustment):
                    with self.assertRaisesRegex(ReleaseError, "aggregate"):
                        improver_study.prepare_improver_study(
                            directory,
                            declaration=declaration,
                            expected_sha256=sha(declaration.read_bytes()),
                            authorization=authority,
                            review=f.engine.fixture.review,
                            expected_runtime_sha256=f.engine.candidate.expected_runtime,
                        )
                    self.assertFalse(directory.exists())
                    self.assertEqual(
                        (authority.summary(), f.engine.physical_sends, len(f.events)), before
                    )
                    self.assertEqual(authority.summary()["runs"], [])
        directory, _, authority = f.prepare_study("exact-comparison-grant", record)
        self.assertTrue((directory / "common/0/0/screen/tasks/0/generation/owners/0").is_dir())
        self.assertEqual(len(authority.summary()["runs"]), 1)
        self.assertEqual(authority.summary()["operation_count"], 0)
        self.assertEqual((f.engine.physical_sends, len(f.events)), before_preparation)


if __name__ == "__main__":
    unittest.main()
