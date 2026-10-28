"""A real failed edge keeps its control marker through a comparison wrapper."""

import hashlib
import json
import unittest
from pathlib import Path
from unittest.mock import patch

import test_source_comparison_feedback_boundaries as frozen_fixtures
import test_source_screen as screen_fixtures

from buddha import source_feedback as feedback
from buddha import source_screen as screens
from buddha.releases import _json


class ScreenControlFailureTests(unittest.TestCase):
    def test_measured_failure_marker_survives_uniform_comparison_and_exact_rebuild(self):
        case = frozen_fixtures.SourceComparisonFeedbackBoundaryTests("runTest")
        self.addCleanup(case.doCleanups)
        original_prepare = screen_fixtures.SourceScreenTests.prepare

        def prepare(h, screen, directory=None, authority=None, **changes):
            study = h.root / "study"
            if screen.to_record()["lineage"] is None:
                directory = study / "common/0/0/screen"
            elif directory.name == "detached-failed-screen":
                directory = study / "cells/0/0/0/0/screen"
                control = h.root / "continued-failure-host-note.txt"
                control.write_bytes(b"literal additional failed-child fixture control")
                changes["input_bindings"] = {
                    control: hashlib.sha256(control.read_bytes()).hexdigest()
                }
            else:
                directory = study / "cells/0/0/0/1/screen"
            directory.parent.mkdir(parents=True, exist_ok=True)
            return original_prepare(h, screen, directory, authority, **changes)

        # Retarget only the existing test helper; source identity and custody
        # checks still inspect actual manifests, workers and saved replies.
        with patch.object(screen_fixtures.SourceScreenTests, "prepare", new=prepare):
            case.fixture()
        frozen, h = case.frozen, case.h
        authority = frozen.authority
        parent = h.inspect(Path(frozen.reference["directory"]), authority)
        current = h.inspect(Path(case.reference["directory"]), authority)
        failed = h.inspect(Path(frozen.history[0]["screen"]["directory"]), authority)
        before, after = parent["controls_sha256"], failed["controls_sha256"]
        self.assertNotEqual(before, after)
        self.assertEqual(current["controls_sha256"], before)
        self.assertEqual(parent["comparison_key"], failed["comparison_key"])
        self.assertEqual(current["comparison_key"], parent["comparison_key"])
        self.assertEqual(failed["disposition"], "candidate_execution_failed")
        self.assertEqual(failed["failure"]["task_id"], "1")

        anchor_path = h.root / "explicit-failure-continuation.json"
        anchor_path.write_bytes(b"{}")
        anchor = {"path": str(anchor_path), "sha256": hashlib.sha256(b"{}").hexdigest()}
        marker = {
            "format": "buddha.host-control-relation.v1",
            "continuation": anchor,
            "before_controls_sha256": before,
            "after_controls_sha256": after,
        }
        historical = frozen.original_packet
        historical_bytes = {p.name: p.read_bytes() for p in historical.iterdir()}
        historical_pin = hashlib.sha256((historical / "provenance.json").read_bytes()).hexdigest()
        study = h.root / "study"
        unchanged = h.files(study), authority.summary(), authority.path.read_bytes()
        sends = h.engine.physical_sends
        destinations = (h.root / "continued-failure-feedback", h.root / "wrapped-failure-feedback")
        arguments = {
            "reference": case.reference,
            "failure_history": frozen.history,
            "improver_agent_sha256": case.actor_id,
        }
        with h.readonly(), self.assertRaises(feedback.SourceFeedbackError):
            feedback.build_source_feedback(destinations[0], **arguments)
        self.assertFalse(destinations[0].exists())

        with (
            screens._screen_control_profiles(
                study, authority.path, before=before, after=after, continuation=anchor
            ),
            h.readonly(),
        ):
            base = feedback.build_source_feedback(destinations[0], **arguments)
            self.assertEqual(base["provenance"]["format"], "buddha.source-screen-feedback.v5")
            self.assertEqual(base["provenance"]["controls_sha256"], before)
            self.assertEqual(base["provenance"]["policy"]["host_control_relation"], marker)
            comparison_base = feedback.build_source_feedback(destinations[1], **arguments)
            bundles = [base]
            bundles.append(
                feedback.build_source_feedback(
                    destinations[1], **arguments, comparison=case.comparison
                )
            )
            wrapper = bundles[1]["provenance"]
            self.assertEqual(wrapper["format"], "buddha.source-screen-feedback.v6")
            self.assertEqual(wrapper["base_format"], base["provenance"]["format"])
            self.assertEqual(
                wrapper["base_provenance_sha256"],
                hashlib.sha256(_json(comparison_base["provenance"])).hexdigest(),
            )
            self.assertEqual(wrapper["controls_sha256"], before)
            self.assertEqual(wrapper["policy"]["host_control_relation"], marker)
            self.assertEqual(wrapper["failure_history"], frozen.history)
            self.assertEqual(wrapper["comparison"], case.comparison)
            for row in bundles[1]["feedback"]["records"]:
                note = json.loads(row["note"])
                failure = note["measurements"]["newest_failure"]
                self.assertEqual(failure["source"], frozen.returned["source"])
                self.assertEqual(failure["hypothesis"], frozen.returned["hypothesis"])
                self.assertEqual(failure["source_omitted_utf8_bytes"], 0)
                self.assertEqual(note["measurements"]["failures"][0]["improver_id"], case.actor_id)
                self.assertEqual(note["comparison"]["distinct_delta"], -1)
                self.assertEqual(note["comparison"]["utility_delta"], -3)
            written = []
            for index, (destination, expected) in enumerate(
                zip(destinations, bundles, strict=True)
            ):
                options = {} if index == 0 else {"comparison": case.comparison}
                published = feedback.write_source_feedback(destination, **arguments, **options)
                written.append(published)
                self.assertEqual(
                    feedback.inspect_source_feedback(
                        destination, expected_provenance_sha256=published["provenance"]["sha256"]
                    ),
                    expected,
                )
                self.assertEqual(
                    feedback.build_source_feedback(
                        destination, **arguments, **options, existing=True
                    ),
                    expected,
                )
            old = feedback.inspect_source_feedback(
                historical, expected_provenance_sha256=historical_pin
            )
            self.assertNotIn("host_control_relation", old["provenance"]["policy"])

        with h.readonly():
            for index, destination in enumerate(destinations):
                options = {} if index == 0 else {"comparison": case.comparison}
                with self.subTest(packet=index), self.assertRaises(feedback.SourceFeedbackError):
                    feedback.inspect_source_feedback(
                        destination,
                        expected_provenance_sha256=written[index]["provenance"]["sha256"],
                    )
                with self.subTest(rebuild=index), self.assertRaises(feedback.SourceFeedbackError):
                    feedback.build_source_feedback(
                        destination, **arguments, **options, existing=True
                    )
            old = feedback.inspect_source_feedback(
                historical, expected_provenance_sha256=historical_pin
            )
            self.assertNotIn("host_control_relation", old["provenance"]["policy"])
        self.assertEqual(historical_bytes, {p.name: p.read_bytes() for p in historical.iterdir()})
        self.assertEqual(
            (h.files(study), authority.summary(), authority.path.read_bytes()), unchanged
        )
        self.assertEqual(h.engine.physical_sends, sends)
        self.assertEqual(h.inspect(Path(frozen.reference["directory"]), authority), parent)
        self.assertEqual(
            h.inspect(Path(frozen.history[0]["screen"]["directory"]), authority), failed
        )


if __name__ == "__main__":
    unittest.main()
