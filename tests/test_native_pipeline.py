"""Shared completion publication preserves types outside its financial snapshot."""

import copy
import tempfile
import unittest
from pathlib import Path

from buddha.authorization import Authorization
from buddha.native_pipeline import PipelineError, publish_complete
from buddha.releases import _json


class PublicationTests(unittest.TestCase):
    def test_replay_rejects_boolean_substitution_in_original_nonfinancial_payload(self):
        with tempfile.TemporaryDirectory() as location:
            directory = Path(location)
            authority = Authorization.create(
                directory / "authorization.sqlite3",
                authorization_id="synthetic-publication-test",
                budget_microusd=1000,
                max_calls=10,
                scope="synthetic publication integrity only",
            )
            path = directory / "report.json"
            expected = {"cells": [{"arm_index": 0}], "authorization": authority.summary()}
            self.assertEqual(publish_complete(path, expected, authority, set()), expected)
            changed = copy.deepcopy(expected)
            changed["cells"][0]["arm_index"] = False
            path.write_bytes(_json(changed))
            with self.assertRaises(PipelineError):
                publish_complete(path, expected, authority, set())


if __name__ == "__main__":
    unittest.main()
