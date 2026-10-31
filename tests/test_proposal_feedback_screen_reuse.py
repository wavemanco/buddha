"""Completed witness proposals retain full feedback derivation and original custody."""

import json
import unittest
from unittest.mock import patch

import test_improver_screen_replay as replay_fixtures

from buddha import (
    candidate_improvement,
    doctor,
    source_feedback,
    source_screen,
    source_screen_results,
)
from buddha.releases import ReleaseError, _json, file_hash


class ProposalFeedbackScreenReuseTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.case = case = replay_fixtures.CompletedImproverScreenReplayTests("runTest")
        cls.addClassCleanup(case.doCleanups)
        cls.f, cls.directory, cls.screen_root, cls.authority = case.fixture()
        case.complete(cls.f, cls.screen_root)
        cls.witness = cls.screen_root.parent / "witness"
        for _ in range(2):
            reader, state = cls.f.api._restore(cls.directory, cls.authority.path)
            case.assertEqual(state["action"]["kind"], "witness")
            reader.finish()
            with cls.f.supplied():
                cls.f.api._advance_action(reader, state, cls.authority, cls.f.transport())
        case.assertEqual(
            json.loads((cls.witness / "proposal/report.json").read_bytes())["disposition"],
            "materialized",
        )

    def test_completed_proposal_restore_collects_its_screen_once(self):
        with (
            self.f.h.readonly(),
            patch.object(
                source_screen_results,
                "_collect_source_screen",
                wraps=source_screen_results._collect_source_screen,
            ) as collect,
        ):
            reader, state = self.f.api._restore(self.directory, self.authority.path)
            self.assertEqual(state["action"]["kind"], "witness")
            reader.finish()
        self.assertEqual(collect.call_count, 1)

    def completed(self):
        reader, state = self.case.observation(self.f, self.directory, self.authority)
        retained = []
        self.f.api._screen(reader, state, self.screen_root, self.f.base, retained=retained)
        self.assertEqual(len(retained), 1)
        return reader, retained[0]

    def inspect_proposal(self, completed):
        return candidate_improvement.inspect_candidate_improvement(
            self.witness / "proposal",
            authorization=self.authority.path,
            expected_report_sha256=file_hash(self.witness / "proposal/report.json"),
            _feedback_screen=completed,
        )

    def inspect_feedback(self, completed, directory=None):
        directory = self.witness / "feedback" if directory is None else directory
        return source_feedback.inspect_source_feedback(
            directory,
            expected_provenance_sha256=file_hash(directory / "provenance.json"),
            _completed_screen=completed,
        )

    def test_state_packet_source_bytes_and_receipt_topology_match_default(self):
        before = (
            self.f.h.files(self.directory),
            self.authority.path.read_bytes(),
            self.f.engine.physical_sends,
        )
        inspect = candidate_improvement.inspect_candidate_improvement
        build = source_feedback._build
        views = []
        for force_default in (True, False):
            packets = []

            def proposal(*args, force_default=force_default, **kwargs):
                if force_default:
                    kwargs.pop("_feedback_screen", None)
                return inspect(*args, **kwargs)

            def full_packet(*args, packets=packets, **kwargs):
                value = build(*args, **kwargs)
                packets.append(_json(value))
                return value

            with (
                self.f.h.readonly(),
                patch.object(
                    candidate_improvement, "inspect_candidate_improvement", side_effect=proposal
                ),
                patch.object(source_feedback, "_build", side_effect=full_packet),
            ):
                reader, state = self.f.api._restore(self.directory, self.authority.path)
                action = state["action"]
                views.append(
                    (
                        _json(
                            {
                                "coverage": state["coverage"],
                                "authorization": state["authorization"],
                                "checked": sorted(str(path) for path in state["checked"]),
                                "action": {
                                    "kind": action["kind"],
                                    "position": action["position"],
                                    "treatment": action["treatment"].to_record(),
                                },
                            }
                        ),
                        packets,
                        dict(reader.capture._receipts),
                        reader.capture.total,
                        set(reader.capture.databases),
                    )
                )
                reader.finish()
            self.assertEqual(
                len(packets), 2, "rederive the entire witness and proposal feedback packets"
            )
        self.assertEqual(views[0], views[1])
        self.assertEqual(
            before,
            (
                self.f.h.files(self.directory),
                self.authority.path.read_bytes(),
                self.f.engine.physical_sends,
            ),
        )

    def test_wrong_type_reference_profile_and_policy_are_refused(self):
        with self.f.h.readonly():
            _, completed = self.completed()
            with self.assertRaises(source_feedback.SourceFeedbackError):
                self.inspect_feedback({"status": "complete"})
            with self.assertRaises(source_feedback.SourceFeedbackError):
                self.inspect_feedback(completed, self.f.root / "bootstrap-feedback")
            with (
                doctor._observation_policy(
                    {
                        "format": "buddha.evidence-observation-policy.v2",
                        "max_total_bytes": 1,
                        "max_tree_entries": 1,
                        "max_consumed_paths": 1,
                        "max_resident_bytes": 0,
                    }
                ),
                self.assertRaises(source_feedback.SourceFeedbackError),
            ):
                self.inspect_feedback(completed)
            token = source_screen._CONTROL_PROFILES.set(object())
            try:
                with self.assertRaises(source_feedback.SourceFeedbackError):
                    self.inspect_feedback(completed)
            finally:
                source_screen._CONTROL_PROFILES.reset(token)
            with (
                patch.object(doctor, "_tree_context", return_value=None),
                self.assertRaises(source_feedback.SourceFeedbackError),
            ):
                self.inspect_feedback(completed)

    def test_source_custody_authority_sidecar_and_packet_tampering_are_refused(self):
        paths = [
            next(self.screen_root.rglob("partitions.jsonl")),
            self.authority.path,
            self.witness / "feedback/provenance.json",
            self.witness / "feedback/feedback.json",
        ]
        for path in paths:
            with self.f.h.readonly():
                _, completed = self.completed()
                raw = path.read_bytes()
                try:
                    path.write_bytes(b"X" + raw[1:])
                    with self.subTest(path=path.name), self.assertRaises(ReleaseError):
                        self.inspect_proposal(completed)
                finally:
                    path.write_bytes(raw)
        for path in [
            self.authority.path.with_name(self.authority.path.name + "-wal"),
            self.witness / "feedback/orphan.json",
        ]:
            with self.f.h.readonly():
                _, completed = self.completed()
                self.assertFalse(path.exists())
                try:
                    path.write_bytes(b"unexpected")
                    with self.subTest(path=path.name), self.assertRaises(ReleaseError):
                        self.inspect_proposal(completed)
                finally:
                    path.unlink()

    def test_late_provenance_and_packet_changes_keep_all_rechecks(self):
        provenance = self.witness / "feedback/provenance.json"
        raw = provenance.read_bytes()
        build = source_feedback._build

        def late_provenance(*args, **kwargs):
            value = build(*args, **kwargs)
            provenance.write_bytes(raw + b"\n")
            return value

        with self.f.h.readonly():
            _, completed = self.completed()
            try:
                with (
                    patch.object(source_feedback, "_build", side_effect=late_provenance),
                    self.assertRaises(source_feedback.SourceFeedbackError),
                ):
                    self.inspect_feedback(completed)
            finally:
                provenance.write_bytes(raw)
        feedback = self.witness / "feedback/feedback.json"
        raw = feedback.read_bytes()
        files = source_feedback._packet_files
        calls = []

        def after_last_packet_check(*args, **kwargs):
            result = files(*args, **kwargs)
            calls.append(True)
            if len(calls) == 3:
                feedback.write_bytes(raw + b"\n")
            return result

        with self.f.h.readonly():
            _, completed = self.completed()
            try:
                with (
                    patch.object(
                        source_feedback, "_packet_files", side_effect=after_last_packet_check
                    ),
                    self.assertRaises(candidate_improvement.CandidateImprovementError),
                ):
                    self.inspect_proposal(completed)
                self.assertEqual(len(calls), 3)
            finally:
                feedback.write_bytes(raw)


if __name__ == "__main__":
    unittest.main()
