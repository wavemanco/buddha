"""Direct finite screen-to-witness reuse preserves aggregate original custody."""

import unittest
from unittest.mock import patch

import test_improver_screen_replay as replay_fixtures

from buddha import doctor, source_screen, source_screen_results
from buddha.releases import ReleaseError, _json


class StudyScreenHandoffTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.fixture_case = case = replay_fixtures.CompletedImproverScreenReplayTests("runTest")
        cls.addClassCleanup(case.doCleanups)
        cls.f, cls.directory, cls.screen_root, cls.authority = case.fixture()
        case.complete(cls.f, cls.screen_root)

    def test_restore_collects_completed_screen_once_across_screen_and_witness(self):
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

    def observation(self):
        return self.fixture_case.observation(self.f, self.directory, self.authority)

    def handoff(self):
        reader, state = self.observation()
        retained = []
        report = self.f.api._screen(reader, state, self.screen_root, self.f.base, retained=retained)
        self.assertEqual(len(retained), 1)
        return reader, state, report, retained[0]

    def witness(self, reader, state, completed):
        return self.f.api._witness(
            reader,
            state,
            self.f.api._reference(reader, self.screen_root),
            self.screen_root.parent / "witness",
            self.f.base,
            completed=completed,
        )

    def test_default_state_packet_and_aggregate_receipts_are_byte_identical(self):
        witness = self.screen_root.parent / "witness"
        self.assertFalse(witness.exists())
        witness.mkdir()

        def cleanup():
            for name in self.f.shared._FILES:
                (witness / "feedback" / (name + ".json")).unlink(missing_ok=True)
            for name in ("plan.json", "proposal.json"):
                (witness / name).unlink(missing_ok=True)
            if (witness / "feedback").exists():
                (witness / "feedback").rmdir()
            witness.rmdir()

        self.addCleanup(cleanup)
        with self.f.h.readonly():
            reader, state = self.observation()
            self.f.api._screen(reader, state, self.screen_root, self.f.base)
            treatment, _ = self.witness(reader, state, None)
            parent = self.f.shared._witness_parent(reader, treatment)
            _, plan, packet = self.f.shared._witness_materials(treatment, parent)
            reader.finish()
        # Use the existing exact preparation bytes; no owner or API call is made.
        self.f.shared._write_witness_inputs(treatment, plan, packet)
        before = (
            self.f.h.files(self.directory),
            self.authority.path.read_bytes(),
            self.f.engine.physical_sends,
        )
        ordinary_screen = self.f.api._screen

        def default(*args, **kwargs):
            kwargs.pop("retained", None)
            return ordinary_screen(*args, **kwargs)

        views = []
        for force_default in (True, False):
            target = default if force_default else ordinary_screen
            with self.f.h.readonly(), patch.object(self.f.api, "_screen", side_effect=target):
                reader, state = self.f.api._restore(self.directory, self.authority.path)
                action = state["action"]
                treatment = action["treatment"]
                parent = self.f.shared._witness_parent(reader, treatment)
                _, plan, packet = self.f.shared._witness_materials(treatment, parent)
                views.append(
                    (
                        _json(
                            {
                                "coverage": state["coverage"],
                                "authorization": state["authorization"],
                                "checked": sorted(str(path) for path in state["checked"]),
                                "action": {
                                    "kind": action["kind"],
                                    "directory": str(action["directory"]),
                                    "position": action["position"],
                                    "treatment": treatment.to_record(),
                                },
                            }
                        ),
                        _json(plan),
                        _json(packet),
                        dict(reader.capture._receipts),
                        reader.capture.total,
                        set(reader.capture.databases),
                    )
                )
                reader.finish()
        self.assertEqual(views[0], views[1])
        self.assertEqual(
            before,
            (
                self.f.h.files(self.directory),
                self.authority.path.read_bytes(),
                self.f.engine.physical_sends,
            ),
        )

    def test_retained_collection_keeps_the_existing_aggregate_limit(self):
        with self.f.h.readonly():
            reader, state = self.observation()
            initial_total = reader.capture.total
            retained = []
            self.f.api._screen(reader, state, self.screen_root, self.f.base, retained=retained)
            source_total = retained[0].reader.capture.total
            maximum = max(initial_total, source_total)
            self.assertGreater(reader.capture.total, maximum)
        reached = []
        adopt = source_screen_results._adopt_capture
        with (
            doctor._observation_policy(
                {
                    "format": "buddha.evidence-observation-policy.v2",
                    "max_total_bytes": maximum,
                    "max_tree_entries": 100000,
                    "max_consumed_paths": 65536,
                    "max_resident_bytes": 0,
                }
            ),
            self.f.h.readonly(),
        ):
            reader, state = self.observation()

            def limited(source, target):
                if target is reader.capture:
                    reached.append(True)
                return adopt(source, target)

            with (
                patch.object(source_screen_results, "_adopt_capture", side_effect=limited),
                self.assertRaises(source_screen.SourceScreenError),
            ):
                self.f.api._screen(reader, state, self.screen_root, self.f.base, retained=[])
        self.assertEqual(reached, [True])

    def test_initial_unavailable_context_uses_the_existing_default_path(self):
        with (
            self.f.h.readonly(),
            patch.object(source_screen_results, "_read_context", return_value=None),
            patch.object(
                source_screen_results,
                "_collect_source_screen",
                wraps=source_screen_results._collect_source_screen,
            ) as collect,
        ):
            reader, state = self.f.api._restore(self.directory, self.authority.path)
            self.assertEqual(state["action"]["kind"], "witness")
            reader.finish()
        self.assertEqual(collect.call_count, 2)

    def test_retention_does_not_skip_finite_owner_checks(self):
        original = self.f.shared._read_ref

        def corrupted(*args, **kwargs):
            report = original(*args, **kwargs)
            report["provenance"]["owners"][0]["ledger_sha256"] = "0" * 64
            return report

        retained = []
        with self.f.h.readonly(), patch.object(self.f.shared, "_read_ref", side_effect=corrupted):
            reader, state = self.observation()
            with self.assertRaises(self.f.api.ImproverStudyError):
                self.f.api._screen(reader, state, self.screen_root, self.f.base, retained=retained)
        self.assertEqual(retained, [])

    def test_handoff_rejects_changed_custody_authority_sidecar_and_context(self):
        artifact = next(self.screen_root.rglob("partitions.jsonl"))
        for path in (artifact, self.authority.path):
            with self.f.h.readonly():
                reader, state, _, completed = self.handoff()
                raw = path.read_bytes()
                try:
                    path.write_bytes(b"X" + raw[1:])
                    with (
                        self.subTest(path=path.name),
                        self.assertRaises((ReleaseError, doctor._Busy)),
                    ):
                        self.witness(reader, state, completed)
                finally:
                    path.write_bytes(raw)
        with self.f.h.readonly():
            reader, state, _, completed = self.handoff()
            sidecar = self.authority.path.with_name(self.authority.path.name + "-wal")
            try:
                sidecar.write_bytes(b"unsettled")
                with self.assertRaises((ReleaseError, doctor._Busy)):
                    self.witness(reader, state, completed)
            finally:
                sidecar.unlink()
        with self.f.h.readonly():
            reader, state, _, completed = self.handoff()
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
                self.assertRaises(ReleaseError),
            ):
                self.witness(reader, state, completed)
            wrong = self.f.api._reference(reader, self.screen_root) | {"report_sha256": "0" * 64}
            with self.assertRaises(ReleaseError):
                self.f.api._witness(
                    reader,
                    state,
                    wrong,
                    self.screen_root.parent / "witness",
                    self.f.base,
                    completed=completed,
                )

    def test_late_native_drift_remains_in_the_outer_aggregate_finish(self):
        with self.f.h.readonly():
            reader, state, report, completed = self.handoff()
            from pathlib import Path

            artifact = Path(report["tasks"][0]["summary"]["path"])
            raw = artifact.read_bytes()
            funding = self.f.shared._witness_funding

            def late(*args, **kwargs):
                result = funding(*args, **kwargs)
                artifact.write_bytes(bytes([raw[0] ^ 1]) + raw[1:])
                return result

            try:
                with patch.object(self.f.shared, "_witness_funding", side_effect=late):
                    self.witness(reader, state, completed)
                with self.assertRaises(doctor._Busy):
                    reader.finish()
            finally:
                artifact.write_bytes(raw)


if __name__ == "__main__":
    unittest.main()
