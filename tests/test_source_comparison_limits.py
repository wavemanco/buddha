"""Typed feedback limits survive the public proposal-inspection boundaries."""

import unittest
from pathlib import Path
from unittest.mock import patch

from buddha import candidate_improvement, candidate_improvement_results, source_feedback


class SourceComparisonLimitTests(unittest.TestCase):
    def inspect_with_error(self, error):
        # Stop at the evidence-reader boundary: no valid evidence is invented,
        # and no filesystem, worker or provider operation is needed.
        with patch.object(candidate_improvement_results, "NativeEvidence", side_effect=error):
            return candidate_improvement.inspect_candidate_improvement(
                Path.cwd() / "unopened-proposal",
                authorization=Path.cwd() / "unopened-authorization.sqlite3",
                expected_report_sha256="0" * 64,
            )

    def assert_limit_preserved(self, error):
        with self.assertRaises(
            (
                candidate_improvement.CandidateImprovementError,
                source_feedback.SourceFeedbackTooLarge,
            )
        ) as caught:
            self.inspect_with_error(error)
        self.assertIs(caught.exception, error)

    def test_byte_limit_survives_results_collector_and_public_inspector(self):
        self.assert_limit_preserved(source_feedback.SourceFeedbackTooLarge("complete bytes"))

    def test_reconstruction_limit_survives_results_collector_and_public_inspector(self):
        self.assert_limit_preserved(
            source_feedback.SourceFeedbackReconstructionLimit("complete work")
        )

    def test_ordinary_feedback_error_keeps_proposal_error_normalization(self):
        original = source_feedback.SourceFeedbackError("invalid original evidence")
        with self.assertRaises(candidate_improvement.CandidateImprovementError) as caught:
            self.inspect_with_error(original)
        self.assertIsNot(caught.exception, original)
        self.assertEqual(str(caught.exception), "proposal evidence is invalid or changed")


if __name__ == "__main__":
    unittest.main()
