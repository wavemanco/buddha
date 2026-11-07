"""Full feedback must refuse aggregate capacity before materializing oversized JSON."""

import hashlib
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import test_full_output_feedback as full_fixtures

from buddha.releases import MAX_FEEDBACK_BYTES, _json


class FullFeedbackCapacityTests(unittest.TestCase):
    def test_saved_capacity_is_whitelisted_and_restored_after_invalid_evidence(self):
        from buddha import source_feedback
        from buddha.releases import MAX_FULL_FEEDBACK_BYTES

        with tempfile.TemporaryDirectory() as temporary:
            directory = Path(temporary).resolve()
            for name in ("source", "split", "feedback"):
                (directory / (name + ".json")).write_bytes(b"{}")
            for maximum in (
                True,
                None,
                MAX_FEEDBACK_BYTES + 1,
                MAX_FULL_FEEDBACK_BYTES + 1,
                MAX_FEEDBACK_BYTES,
                MAX_FULL_FEEDBACK_BYTES,
            ):
                # Supported capacities proceed to the deliberately missing original reference.
                raw = _json(
                    {
                        "format": "buddha.source-screen-feedback.v3",
                        "policy": {
                            key: maximum
                            for key in (
                                "max_note_utf8_bytes",
                                "max_feedback_bytes",
                                "max_projected_bytes",
                            )
                        },
                    }
                )
                (directory / "provenance.json").write_bytes(raw)
                with (
                    self.subTest(maximum=maximum),
                    self.assertRaises(source_feedback.SourceFeedbackError),
                ):
                    source_feedback.inspect_source_feedback(
                        directory, expected_provenance_sha256=hashlib.sha256(raw).hexdigest()
                    )
                self.assertEqual(
                    source_feedback._FULL_FEEDBACK_BYTES.get(), MAX_FULL_FEEDBACK_BYTES
                )

    def test_two_task_aggregate_refuses_before_whole_oversized_serialization(self):
        from buddha import source_feedback

        token = source_feedback._FULL_FEEDBACK_BYTES.set(MAX_FEEDBACK_BYTES)
        self.addCleanup(source_feedback._FULL_FEEDBACK_BYTES.reset, token)
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

    def test_full_capacity_uses_json_envelope_and_still_refuses_one_extra_byte(self):
        from buddha.channel import MAX_FRAME_BYTES
        from buddha.releases import MAX_FULL_FEEDBACK_BYTES, MAX_JSON_BYTES
        from buddha.source_feedback import SourceFeedbackTooLarge, _bounded_json

        self.assertEqual(MAX_FULL_FEEDBACK_BYTES, MAX_JSON_BYTES)
        self.assertEqual(MAX_FULL_FEEDBACK_BYTES, MAX_FRAME_BYTES)
        overhead = len(_json({"value": ""}))
        value = {"value": "x" * (MAX_FULL_FEEDBACK_BYTES - overhead)}
        self.assertEqual(
            len(_bounded_json(value, MAX_FULL_FEEDBACK_BYTES)), MAX_FULL_FEEDBACK_BYTES
        )
        value["value"] += "x"
        with self.assertRaises(SourceFeedbackTooLarge):
            _bounded_json(value, MAX_FULL_FEEDBACK_BYTES)

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
