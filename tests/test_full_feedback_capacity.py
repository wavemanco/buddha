"""Full feedback must refuse aggregate capacity before materializing oversized JSON."""

import unittest
from unittest.mock import patch

import test_full_output_feedback as full_fixtures

from buddha.releases import MAX_FEEDBACK_BYTES, _json


class FullFeedbackCapacityTests(unittest.TestCase):
    def test_two_task_aggregate_refuses_before_whole_oversized_serialization(self):
        from buddha import source_feedback

        fixture = full_fixtures.FullOutputFeedbackTests("runTest")
        fixture.setUp()
        self.addCleanup(fixture.doCleanups)
        answer = "x" * 600_000
        self.assertLess(len(answer.encode()), MAX_FEEDBACK_BYTES)
        self.assertGreater(2 * len(answer.encode()), MAX_FEEDBACK_BYTES)
        authority, reference = fixture.completed_answers([answer, ""])
        f = fixture.f
        destination = f.h.root / "aggregate-capacity-feedback"
        before = f.h.files(f.h.root), authority.path.read_bytes(), f.h.engine.physical_sends
        original_json = source_feedback._json
        oversized_serializations = []

        def checked_json(value):
            records = None
            if isinstance(value, dict) and value.get("format") in {
                "buddha.candidate-development-feedback.v1",
                "buddha.candidate-development-feedback.v2",
            }:
                records = value.get("records")
            elif (
                isinstance(value, list)
                and value
                and all(isinstance(row, dict) and set(row) == {"task", "note"} for row in value)
            ):
                records = value
            if isinstance(records, list) and all(
                isinstance(row, dict) and isinstance(row.get("note"), str) for row in records
            ):
                # A lower bound suffices: JSON quoting and container bytes only add size.
                # Do not serialize the oversized object merely to measure it in this spy.
                if sum(len(row["note"].encode()) for row in records) > MAX_FEEDBACK_BYTES:
                    oversized_serializations.append(type(value).__name__)
                    self.fail("whole oversized feedback or worker projection was serialized")
            return original_json(value)

        with (
            f.passive(),
            patch.object(source_feedback, "_json", side_effect=checked_json),
            self.assertRaises(source_feedback.SourceFeedbackTooLarge),
        ):
            f.write_api(destination, reference=reference)
        self.assertEqual(oversized_serializations, [])
        self.assertFalse(destination.exists())
        self.assertEqual(
            (f.h.files(f.h.root), authority.path.read_bytes(), f.h.engine.physical_sends), before
        )

    def test_launch_relays_exact_saved_feedback_capacity_stop(self):
        from buddha.source_launch import _public_result

        partial = {
            "format": "buddha.source-search-observation.v1",
            "status": "incomplete",
            "reason": "feedback_capacity",
            "observation": "observations/7.json",
            "iteration": 2,
            "stage": "feedback",
        }
        original = dict(partial)
        self.assertEqual(
            _public_result(partial),
            {
                "status": "incomplete",
                "reason": "feedback_capacity",
                "observation": "observations/7.json",
                "iteration": 2,
                "stage": "feedback",
            },
        )
        self.assertEqual(partial, original)

    def test_bounded_encoder_preserves_canonical_bytes_at_exact_byte_ceiling(self):
        from buddha.source_feedback import SourceFeedbackTooLarge, _bounded_json

        # Include duplicated complete source context and escaped/multibyte content.
        # This is an encoder boundary check, not a fabricated failed-child provenance.
        source = 'def generate(task):\n    return ["雪\\\\é\\t\\u0001"]\n'
        failure = {"source": source, "hypothesis": "  é雪\n", "ordinal": 0}
        values = [
            {
                "records": [
                    {"task_id": "1", "newest_failure": failure},
                    {"task_id": 1, "newest_failure": failure},
                ],
                "measurements": [None, True, False, 0, 7.25],
            },
            ["", '\x00\n\t\\"', "é雪😀", {"nested": [{"finite": -0.125}]}],
        ]
        for value in values:
            expected = _json(value)
            with self.subTest(value_type=type(value).__name__):
                self.assertEqual(_bounded_json(value, len(expected)), expected)
                with self.assertRaises(SourceFeedbackTooLarge):
                    _bounded_json(value, len(expected) - 1)
