"""Fault-inject only an outer decoded snapshot, leaving actual saved custody intact."""

import copy
import hashlib
import unittest
from unittest.mock import patch

import test_source_screen_outcome as fixtures

from buddha import source_screen_results


class SourceFailureCustodyTests(unittest.TestCase):
    def test_failed_source_requires_anchor_in_the_outer_captured_funding(self):
        helper = fixtures.SourceScreenOutcomeTests("runTest")
        self.addCleanup(helper.doCleanups)
        h, _, directory, authority = helper.prepare()
        with patch.object(h, "execute", side_effect=helper.failed_worker(h, "1", h.execute)):
            completed = h.run_screen(directory)
        self.assertEqual(h.inspect(directory, authority), completed)
        self.assertEqual(h.engine.physical_sends, 0)
        self.assertEqual((len(h.generation_events), len(h.native_events)), (1, 0))
        original = source_screen_results._owners
        before = h.files(directory), hashlib.sha256(authority.path.read_bytes()).hexdigest()
        for kind in ("missing", "wrong_reason"):
            with self.subTest(snapshot=kind):

                def changed_outer(reader, *args, kind=kind, **kwargs):
                    # Explicit internal composition fault injection, not a timed DB race.
                    # Original public inner inspector, raw authority and artifacts stay real.
                    funding = copy.deepcopy(original(reader, *args, **kwargs))
                    owner = reader.owner(reader.root / "tasks/0/generation/owners/0")
                    anchors = [
                        row
                        for row in funding["auth_deactivations"]
                        if row["run_id"] == owner.run_id
                    ]
                    self.assertEqual(len(anchors), 1)
                    if kind == "missing":
                        funding["auth_deactivations"] = [
                            row
                            for row in funding["auth_deactivations"]
                            if row["run_id"] != owner.run_id
                        ]
                    else:
                        anchors[0]["reason"] = "different terminal seal"
                    return funding

                try:
                    with (
                        h.readonly(),
                        patch("socket.socket", side_effect=AssertionError("socket forbidden")),
                        patch.object(source_screen_results, "_owners", side_effect=changed_outer),
                    ):
                        with self.assertRaises(h.Error):
                            source_screen_results.collect_source_screen(
                                directory, authorization=authority.path
                            )
                finally:
                    self.assertEqual(
                        (
                            h.files(directory),
                            hashlib.sha256(authority.path.read_bytes()).hexdigest(),
                        ),
                        before,
                    )
                    self.assertEqual(h.engine.physical_sends, 0)
        self.assertEqual(h.inspect(directory, authority), completed)
