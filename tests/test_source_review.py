"""Prospectively bound current C1 is exported without changing experiment evidence."""

import unittest


class SourceReviewTests(unittest.TestCase):
    def test_current_final_c1_exports_whole_literal_sets_under_original_custody(self):
        # The initial RED is the absent API, before creating a fixture or owner.
        from buddha.source_review import materialize_source_review

        self.assertTrue(callable(materialize_source_review))


if __name__ == "__main__":
    unittest.main()
