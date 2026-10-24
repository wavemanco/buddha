"""Operator handoff for checked complete source-answer review sets."""

import unittest


class SourceReviewHandoffTests(unittest.TestCase):
    def test_export_operator_api_is_available(self):
        from buddha.source_review_handoff import export_source_review

        self.assertTrue(callable(export_source_review))
