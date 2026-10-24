"""Checked review collection and bounded private report publication."""

import unittest


class SourceReviewCollectionTests(unittest.TestCase):
    def test_collection_operator_api_is_available(self):
        from buddha.source_review_handoff import collect_source_reviews

        self.assertTrue(callable(collect_source_reviews))
