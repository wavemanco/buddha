"""Versioned fixed-study declaration and original common-root custody checks."""

import copy
import unittest

import test_improver_study as finite_fixtures

from buddha import improver_study as study
from buddha.native_evidence import NativeEvidence
from buddha.releases import ReleaseError, _json

COMPARISON_POLICY = {
    "format": "buddha.improver-study-feedback-comparison.v1",
    "measurements": "complete_literal_outputs",
    "parent": "original_immediate_counted_edge_in_same_cell",
    "root": "no_counted_parent_in_this_cell",
    "counted_failures": "complete_original_cell_history",
    "mutation_witness": "complete_absolute_outputs",
}


class ImproverStudyComparisonTests(unittest.TestCase):
    def fixture(self):
        case = finite_fixtures.FiniteImproverStudyTests("runTest")
        self.addCleanup(case.doCleanups)
        case.fixture_before_new_api()
        finite_fixtures.observe_fixture_workers(case, self)
        case.api = study
        record = case.declaration(study)
        record.update(
            format="buddha.improver-study.v3",
            feedback_comparison=copy.deepcopy(COMPARISON_POLICY),
            starts=record["starts"][:1],
            repetitions=1,
            descendant_opportunities=2,
        )
        record["selection"]["finalist_iteration"] = 2
        case.recompute_limits(record)
        return case, record

    def test_v3_exact_policy_retains_aggregate_caps_and_old_declarations(self):
        case, record = self.fixture()
        nominal = copy.deepcopy(record["limits"])
        record["limits"]["study"] = {"budget_microusd": 1, "max_calls": 1}
        before = case.h.files(case.root), case.engine.physical_sends
        parsed, _ = study._declaration(record, case.engine.candidate.expected_runtime)
        self.assertEqual(parsed, record)
        self.assertEqual(study.FEEDBACK_COMPARISON_POLICY, COMPARISON_POLICY)
        self.assertEqual(parsed["limits"]["common_cell"], nominal["common_cell"])
        self.assertEqual(parsed["limits"]["arm_cell"], nominal["arm_cell"])
        study._check_funding(parsed, dict(record["limits"]["study"]))
        for key in ("budget_microusd", "max_calls"):
            wrong = dict(record["limits"]["study"])
            wrong[key] += 1
            with self.subTest(funding=wrong), self.assertRaises(ReleaseError):
                study._check_funding(parsed, wrong)
        malformed = []
        missing = copy.deepcopy(record)
        del missing["feedback_comparison"]
        malformed.append(missing)
        for key in COMPARISON_POLICY:
            changed = copy.deepcopy(record)
            changed["feedback_comparison"][key] = "changed"
            malformed.append(changed)
        for version in ("buddha.improver-study.v1", "buddha.improver-study.v2"):
            changed = copy.deepcopy(record)
            changed["format"] = version
            malformed.append(changed)
        for changed in malformed:
            with self.subTest(declaration=changed), self.assertRaises(ReleaseError):
                study._declaration(changed, case.engine.candidate.expected_runtime)
        for version in ("buddha.improver-study.v1", "buddha.improver-study.v2"):
            old = copy.deepcopy(record)
            old["format"] = version
            del old["feedback_comparison"]
            old["limits"] = copy.deepcopy(nominal)
            self.assertEqual(
                study._declaration(old, case.engine.candidate.expected_runtime)[0], old
            )
        self.assertEqual((case.h.files(case.root), case.engine.physical_sends), before)

    def test_original_common_root_binds_coordinate_actor_and_exact_occasion(self):
        case, record = self.fixture()
        directory, _, authority = case.prepare_study("comparison-root", record)
        common = directory / "common/0/0/screen"
        self.assertEqual(case.h.run_screen(common)["status"], "complete")
        reference = case.h.reference(common, authority)
        actor = case.actor_id(case.fixed[0])
        selector = {
            "directory": str(directory),
            "authorization": str(authority.path),
            "declaration_sha256": finite_fixtures.sha(_json(record)),
            "start": 0,
            "repetition": 0,
            "arm": 0,
        }
        before = case.h.files(case.root), authority.path.read_bytes(), case.engine.physical_sends
        with case.h.readonly():
            result = study._read_comparison_root(selector, reference, case.base.candidate_id, actor)
            self.assertEqual(result["reference"], reference)
            self.assertEqual(result["improver_agent_sha256"], actor)
            self.assertEqual(result["candidate_id"], case.base.candidate_id)
            reader = NativeEvidence(directory, authority.path, error_type=study.ImproverStudyError)
            state = study._original(reader)
            state["common"] = {(0, 0): reference}
            self.assertEqual(
                study._comparison_for(reader, state, (0, 0, 0, 0), reference, []),
                {"study_root": selector},
            )
            # Even an exact screen-reference match cannot authorize malformed
            # cell coordinates, future slots or a different frozen actor.
            decision = {
                "format": "buddha.improver-study-decision.v1",
                "start": 0,
                "repetition": 0,
                "arm": 0,
                "slot": 0,
                "status": "admitted",
                "improver_agent_sha256": actor,
                "screen": reference,
            }
            for changed in (
                decision | {"start": 1},
                decision | {"repetition": 1},
                decision | {"arm": 1},
                decision | {"slot": 1},
                decision | {"slot": False},
                decision | {"improver_agent_sha256": case.actor_id(case.fixed[1])},
            ):
                with (
                    self.subTest(decision=changed),
                    self.assertRaisesRegex(study.ImproverStudyError, "earlier cell decision"),
                ):
                    study._comparison_for(reader, state, (0, 0, 0, 1), reference, [changed])
            for changed in (
                selector | {"declaration_sha256": "0" * 64},
                selector | {"arm": True},
                selector | {"repetition": 1},
                selector | {"authorization": str(case.root / "another.sqlite3")},
            ):
                with self.subTest(root=changed), self.assertRaises(ReleaseError):
                    study._read_comparison_root(changed, reference, case.base.candidate_id, actor)
            with self.assertRaises(ReleaseError):
                study._read_comparison_root(
                    selector, reference, case.base.candidate_id, case.actor_id(case.fixed[1])
                )
            with self.assertRaises(ReleaseError):
                study._read_comparison_root(
                    selector,
                    reference | {"directory": str(directory / "common/0/1/screen")},
                    case.base.candidate_id,
                    actor,
                )
            failure = {
                "parent": reference,
                "proposal": reference | {"directory": str(directory / "cells/0/0/0/0/proposal")},
                "screen": reference | {"directory": str(directory / "cells/0/0/0/0/screen")},
            }
            for changed in (
                failure
                | {
                    "proposal": failure["proposal"]
                    | {"directory": str(directory / "cells/0/1/0/0/proposal")}
                },
                failure
                | {
                    "screen": failure["screen"]
                    | {"directory": str(directory / "cells/0/0/1/0/screen")}
                },
                failure
                | {"parent": reference | {"directory": str(directory / "common/0/1/screen")}},
                failure | {"parent": failure["screen"]},
            ):
                with (
                    self.subTest(failure=changed),
                    self.assertRaisesRegex(study.ImproverStudyError, "failure history"),
                ):
                    study._read_comparison_root(
                        selector,
                        reference,
                        case.base.candidate_id,
                        actor,
                        failure_history=[changed],
                    )
            reader.finish()
        self.assertEqual(
            (case.h.files(case.root), authority.path.read_bytes(), case.engine.physical_sends),
            before,
        )

    def test_valid_standalone_repeated_screen_cannot_claim_study_membership(self):
        from buddha import source_feedback

        case, record = self.fixture()
        record["repetitions"] = 2
        case.recompute_limits(record)
        directory, _, authority = case.prepare_study("comparison-membership", record)
        first = directory / "common/0/0/screen"
        self.assertEqual(case.h.run_screen(first)["status"], "complete")
        other = directory / "common/0/1/screen"
        other.parent.mkdir(parents=True)
        # This is a genuine independently owned screen under the same grant and
        # source. Deliberately omit the study's original context/declaration inputs.
        case.h.prepare(case.base, other, authority=authority)
        self.assertEqual(case.h.run_screen(other)["status"], "complete")
        reference = case.h.reference(other, authority)
        comparison = {
            "study_root": {
                "directory": str(directory),
                "authorization": str(authority.path),
                "declaration_sha256": finite_fixtures.sha(_json(record)),
                "start": 0,
                "repetition": 1,
                "arm": 0,
            }
        }
        destination = case.root / "unwritten-foreign-study-root"
        before = case.h.files(case.root), authority.path.read_bytes(), case.engine.physical_sends
        with case.h.readonly():
            standalone = source_feedback.build_source_feedback(
                case.root / "unwritten-standalone", reference=reference
            )
            self.assertEqual(standalone["provenance"]["candidate_id"], case.base.candidate_id)
            with self.assertRaises(source_feedback.SourceFeedbackError):
                source_feedback.write_source_feedback(
                    destination,
                    reference=reference,
                    comparison=comparison,
                    improver_agent_sha256=case.actor_id(case.fixed[0]),
                )
        self.assertFalse(destination.exists())
        self.assertEqual(
            (case.h.files(case.root), authority.path.read_bytes(), case.engine.physical_sends),
            before,
        )


if __name__ == "__main__":
    unittest.main()
