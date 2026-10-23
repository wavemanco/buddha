"""Full measured outputs must reach prospective improvement without excerpts."""

import json
import unittest
from unittest.mock import patch

import test_source_feedback as fixtures
import test_source_search as search_fixtures

from buddha.releases import _json


class FullOutputFeedbackTests(unittest.TestCase):
    def setUp(self):
        self.f = fixtures.SourceFeedbackTests("runTest")
        self.f.setUp()
        self.addCleanup(self.f.doCleanups)

    def completed_answers(self, answers):
        f = self.f
        f.source(count=len(answers))
        screen = f.h.screen()
        f.h.programs[screen.candidate_id]["answers"] = answers
        engine = f.h.engine
        original = engine.execute_native

        def execute(spec, initial, handle):
            original_row = engine.native_row

            def extend(row, index):
                row = original_row(row, index)
                row["partition"] = [0, 1] + [0] * (len(answers) - 2)
                if index == 1:
                    row["generation_scores"] = [7, 7] + [None] * (len(answers) - 2)
                return row

            # Modify supplied rows before the existing simulator chunks their bytes.
            with patch.object(engine, "native_row", side_effect=extend):
                return original(spec, initial, handle)

        directory, authority = f.h.prepare(screen)
        with patch.object(engine, "execute_native", side_effect=execute):
            self.assertEqual(f.h.run_screen(directory)["status"], "complete")
        return authority, f.h.reference(directory, authority)

    def test_complete_long_answer_including_ending_survives_write_and_passive_inspection(self):
        answers = ["  Beginning. " + "é雪 end\n" * 700 + "THE ACTUAL RESOLUTION.  ", ""]
        authority, reference = self.completed_answers(answers)
        destination = self.f.h.root / "full-output-feedback"
        before = authority.summary(), self.f.h.engine.physical_sends
        result = self.f.write_api(destination, reference=reference)
        packet = json.loads((destination / "feedback.json").read_bytes())
        for row in packet["records"]:
            note = json.loads(row["note"])
            self.assertEqual([x["text"] for x in note["answers"]], answers)
            self.assertGreater(len(row["note"].encode()), 4096)
            self.assertEqual(note["omitted_answer_positions"], 0)
        from buddha.source_feedback import inspect_source_feedback

        with self.f.passive():
            inspected = inspect_source_feedback(
                destination, expected_provenance_sha256=result["provenance"]["sha256"]
            )
        self.assertEqual(inspected["feedback"], packet)
        for task in inspected["provenance"]["tasks"]:
            self.assertTrue(all(x["omitted_utf8_bytes"] == 0 for x in task["answers"]))
        self.assertEqual((authority.summary(), self.f.h.engine.physical_sends), before)

    def test_every_answer_and_diagnostic_position_is_supplied_in_original_order(self):
        answers = ["é雪" * 60, "\x01" * 60, "", " \n", "[refused]", "same", "same"]
        answers += [f"Full answer {i}, with its ending intact." for i in range(7, 12)]
        _, reference = self.completed_answers(answers)
        bundle = self.f.build_api(self.f.h.root / "all-output-positions", reference=reference)
        for row, provenance in zip(
            bundle["feedback"]["records"], bundle["provenance"]["tasks"], strict=True
        ):
            note = json.loads(row["note"])
            self.assertEqual(
                note["answers"], [{"position": i, "text": text} for i, text in enumerate(answers)]
            )
            self.assertEqual(note["partition"], [0, 1] + [0] * 10)
            self.assertEqual(note["generation_scores"], [7, 7] + [None] * 10)
            for key in (
                "omitted_answer_positions",
                "omitted_partition_positions",
                "omitted_score_positions",
            ):
                self.assertEqual(note[key], 0)
            self.assertTrue(
                all(
                    x["omitted_utf8_bytes"] == 0 and x["omission"] is None
                    for x in provenance["answers"]
                )
            )

    def test_oversized_full_output_refuses_before_packet_write_without_shortening(self):
        from buddha.source_feedback import SourceFeedbackTooLarge

        _, reference = self.completed_answers(["x" * (1 << 20), ""])
        destination = self.f.h.root / "oversized-full-outputs"
        before = self.f.h.files(self.f.h.root), self.f.h.engine.physical_sends
        with self.f.passive(), self.assertRaises(SourceFeedbackTooLarge):
            self.f.write_api(destination, reference=reference)
        self.assertFalse(destination.exists())
        self.assertEqual((self.f.h.files(self.f.h.root), self.f.h.engine.physical_sends), before)

    def test_legacy_search_keeps_original_feedback_versions_during_read_and_replay(self):
        from buddha import source_search

        case = search_fixtures.SourceSearchTests("runTest").fixture(iterations=2)
        self.addCleanup(case.doCleanups)
        case.proposals = [search_fixtures.BROKEN, search_fixtures.REPAIRED]
        with patch.object(source_search, "_MANIFEST", source_search._LEGACY_MANIFEST):
            case.prepare()
        self.assertEqual(case.run_search()["status"], "complete")
        first = case.directory / "iterations/0/feedback/provenance.json"
        second = case.directory / "iterations/1/feedback/provenance.json"
        self.assertEqual(
            json.loads(first.read_bytes())["format"], "buddha.source-screen-feedback.v1"
        )
        self.assertEqual(
            json.loads(second.read_bytes())["format"], "buddha.source-screen-feedback.v2"
        )
        before = case.h.files(case.root), case.authority.summary(), case.engine.physical_sends
        self.assertEqual(case.inspect()["status"], "complete")
        self.assertEqual(case.run_search()["status"], "complete")
        self.assertEqual(
            (case.h.files(case.root), case.authority.summary(), case.engine.physical_sends), before
        )

    def test_capacity_stop_is_saved_as_feedback_partial_before_any_proposal_owner(self):
        from buddha import source_feedback, source_search

        case = search_fixtures.SourceSearchTests("runTest").fixture(iterations=1)
        self.addCleanup(case.doCleanups)
        case.prepare()
        # Exercise the real controller stop at its first feedback-producing plan.
        with (
            patch.object(
                source_feedback,
                "_build",
                side_effect=source_feedback.SourceFeedbackTooLarge(
                    "complete outputs exceed declared capacity"
                ),
            ),
            self.assertRaises(source_search.SourceSearchStopped) as stopped,
        ):
            case.run_search()
        partial = stopped.exception.partial
        self.assertEqual((partial["stage"], partial["reason"]), ("feedback", "feedback_capacity"))
        self.assertFalse((case.directory / "iterations/0/proposal").exists())
        self.assertEqual(case.proposal_events, [])
        self.assertTrue(
            any(
                json.loads(x.read_bytes()) == partial
                for x in (case.directory / "observations").glob("*.json")
            )
        )

    def test_failed_child_keeps_full_parent_outputs_and_legacy_failure_packet_still_inspects(self):
        from buddha.source_feedback import _build_failures, inspect_source_feedback

        case = search_fixtures.SourceSearchTests("runTest").fixture(iterations=2)
        self.addCleanup(case.doCleanups)
        broken = search_fixtures.BROKEN + "# failure context\n" * 100 + "# FINAL FAILURE LINE\n"
        case.programs[search_fixtures.sha(broken.encode())] = ("checked-failure", 0)
        case.proposals = [broken, search_fixtures.REPAIRED]
        case.prepare()
        self.assertEqual(case.run_search()["status"], "complete")
        packet = case.directory / "iterations/1/feedback"
        provenance = json.loads((packet / "provenance.json").read_bytes())
        self.assertEqual(provenance["format"], "buddha.source-screen-feedback.v4")
        first = case.proposal_events[0]["feedback"]
        for before, after in zip(first, case.proposal_events[1]["feedback"], strict=True):
            note = json.loads(after["note"])
            self.assertEqual(note["measurements"], json.loads(before["note"]))
            self.assertEqual(note["newest_failure"]["source"], broken)
            self.assertEqual(note["newest_failure"]["source_omitted_utf8_bytes"], 0)
        # Reconstruct the explicitly selected old failure policy from retained edges.
        # This is a separate synthetic compatibility packet, not an edited search input.
        destination = case.root / "legacy-failure-packet"
        before = case.authority.path.read_bytes(), case.engine.physical_sends
        legacy = _build_failures(
            destination, provenance["reference"], provenance["failure_history"], full_answers=False
        )
        self.assertEqual(legacy["provenance"]["format"], "buddha.source-screen-feedback.v2")
        destination.mkdir()
        for name in ("source", "split", "feedback", "provenance"):
            (destination / (name + ".json")).write_bytes(_json(legacy[name]))
        inspected = inspect_source_feedback(
            destination, expected_provenance_sha256=search_fixtures.sha(_json(legacy["provenance"]))
        )
        self.assertEqual(inspected, legacy)
        self.assertEqual((case.authority.path.read_bytes(), case.engine.physical_sends), before)
