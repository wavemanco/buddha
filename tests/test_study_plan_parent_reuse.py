"""Direct finite planning over two real saved source screens, not study history."""

import unittest
from dataclasses import replace
from pathlib import Path
from unittest.mock import patch

import test_source_comparison_feedback as fixtures

from buddha import doctor, improver_study, source_feedback, source_screen, source_screen_results
from buddha import source_search as shared
from buddha.native_evidence import NativeEvidence
from buddha.releases import ReleaseError, _json


class StudyPlanParentReuseTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.f = f = fixtures.SourceComparisonFeedbackTests("runTest")
        cls.addClassCleanup(f.doCleanups)
        f.fixture(literal=" full literal 雪 ")
        cls.directory, cls.authority = f.h.root, f.authority
        cls.coordinate = (0, 0, 0, 1)
        improver_study._location(cls.directory, cls.coordinate).mkdir(parents=True)
        cls.pool = [f.parent_ref, f.reference]
        cls.base = source_screen.SourceScreen.from_bytes(_json(f.parent_record))
        generation = f.parent_record["generation"]
        actor = {key: generation[key] for key in ("selection", "roots", "entrypoint")}
        cls.state = {
            "screens": [cls.base],
            "record": {
                "format": "buddha.improver-study.v1",
                "selection": {"method": "latest", "max_active": 2, "seed": 7},
                "improvers": [actor, actor],
                "proposal_template": {},
            },
        }

    def plan(self):
        reader = NativeEvidence(self.directory, self.authority.path)
        result = improver_study._plan(reader, self.state, self.coordinate, self.pool, [], [])
        reader.finish()
        return result, dict(reader.capture._receipts)

    def test_second_slot_reuses_each_direct_parent_interpretation(self):
        with (
            self.f.h.readonly(),
            patch.object(
                source_screen_results,
                "_collect_source_screen",
                wraps=source_screen_results._collect_source_screen,
            ) as collect,
        ):
            (plan, _), _ = self.plan()
        self.assertEqual(plan["parent"], self.pool[-1])
        self.assertTrue(all(row["eligible"] for row in plan["selection"]["admissions"]))
        self.assertEqual(collect.call_count, 2)

    def test_default_plan_packet_and_original_capture_have_exact_bytes(self):
        before = self.f.h.files(self.directory), self.authority.path.read_bytes()
        with self.f.h.readonly():
            reused = self.plan()
            with (
                patch.object(source_screen_results, "_read_context", return_value=None),
                patch.object(
                    source_screen_results,
                    "_collect_source_screen",
                    wraps=source_screen_results._collect_source_screen,
                ) as collect,
            ):
                ordinary = self.plan()
            self.assertEqual(collect.call_count, 7)
        self.assertEqual(_json(reused[0]), _json(ordinary[0]))
        self.assertEqual(reused[1] | ordinary[1], reused[1])
        self.assertEqual(before, (self.f.h.files(self.directory), self.authority.path.read_bytes()))

    def retained(self, reference):
        reader = NativeEvidence(self.directory, self.authority.path)
        retained = []
        shared._read_ref(reader, reference, capture=True, retained=retained)
        return retained[0]

    def test_comparative_feedback_keeps_original_edge_and_packet_bytes(self):
        with self.f.h.readonly():
            completed = self.retained(self.pool[-1])
            ordinary = source_feedback.build_source_feedback(
                self.f.destination, reference=self.f.reference, comparison=self.f.comparison
            )
            with patch.object(
                source_screen_results,
                "_collect_source_screen",
                wraps=source_screen_results._collect_source_screen,
            ) as collect:
                reused = source_feedback.build_source_feedback(
                    self.f.destination,
                    reference=self.f.reference,
                    comparison=self.f.comparison,
                    _completed_screen=completed,
                )
        self.assertEqual(_json(ordinary), _json(reused))
        self.assertEqual(reused["provenance"]["format"], "buddha.source-screen-feedback.v6")
        self.assertFalse(
            any(call.args[0] == completed.reader.root for call in collect.call_args_list)
        )

    def test_public_selector_methods_keep_seed_order_and_admissions(self):
        with self.f.h.readonly():
            completed = [self.retained(reference) for reference in self.pool]
            for method in ("archive", "latest", "uninformed"):
                settings = {"method": method, "max_active": 2, "seed": 7, "iteration": 1}
                ordinary = source_screen.select_source_parent(self.pool, **settings)
                reused = source_screen.select_source_parent(
                    self.pool, **settings, _completed_screens=completed
                )
                self.assertEqual(_json(ordinary), _json(reused), method)

    def test_carrier_type_reference_pid_thread_lease_policy_and_profile_denials(self):
        reference = self.pool[-1]
        with self.f.h.readonly():
            completed = self.retained(reference)
            context = completed.context
            self.assertIsNotNone(context)
            variants = [
                {"complete": True},
                replace(completed, reader={}),
                replace(completed, screen={}),
                replace(completed, report_raw=b"{}"),
            ]
            for index in range(4):
                changed = list(context)
                changed[index] = None
                variants.append(replace(completed, context=tuple(changed)))
            for variant in variants:
                with self.subTest(variant=type(variant).__name__), self.assertRaises(ReleaseError):
                    source_screen.select_source_parent(
                        [reference],
                        method="latest",
                        max_active=2,
                        seed=7,
                        iteration=1,
                        _completed_screens=[variant],
                    )
            for changed in (
                reference | {"directory": str(self.directory)},
                reference | {"authorization": str(self.directory / "wrong.sqlite3")},
                reference | {"report_sha256": "0" * 64},
            ):
                with self.subTest(reference=changed), self.assertRaises(ReleaseError):
                    shared._read_ref(
                        NativeEvidence(self.directory, self.authority.path),
                        changed,
                        completed=completed,
                    )
            for variable in (source_screen._CONTROL_PROFILES, source_screen._CONTROL_PROFILES_V2):
                token = variable.set(object())
                try:
                    with self.assertRaises(ReleaseError):
                        source_screen_results._reuse_completed_screen(
                            completed,
                            completed.reader.root,
                            self.authority.path,
                            reference["report_sha256"],
                        )
                finally:
                    variable.reset(token)
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
                source_screen_results._reuse_completed_screen(
                    completed,
                    completed.reader.root,
                    self.authority.path,
                    reference["report_sha256"],
                )

    def test_late_report_source_owner_authority_sidecar_and_namespace_drift_reject(self):
        selected = Path(self.pool[-1]["directory"])
        source = Path(self.f.current_record["generation"]["roots"]["agent"]) / "candidate.py"
        paths = [
            selected / "report.json",
            selected / "screen.json",
            source,
            selected / "tasks/0/generation/owners/0/manifest.json",
            self.authority.path,
            self.authority.path.with_name(self.authority.path.name + "-wal"),
            selected / "foreign.json",
        ]
        original_select = improver_study._select
        for path in paths:
            raw = path.read_bytes() if path.exists() else None

            def change(*args, path=path, raw=raw, **kwargs):
                value = original_select(*args, **kwargs)
                path.write_bytes(b"unexpected" if raw is None else b"X" + raw[1:])
                return value

            try:
                with (
                    self.subTest(path=path),
                    self.f.h.readonly(),
                    patch.object(improver_study, "_select", side_effect=change),
                    self.assertRaises((ReleaseError, doctor._Busy)),
                ):
                    self.plan()
            finally:
                if raw is None:
                    path.unlink(missing_ok=True)
                else:
                    path.write_bytes(raw)

    def test_v3_does_not_borrow_an_unrecorded_parent_from_another_cell(self):
        state = self.state | {
            "record": self.state["record"]
            | {
                "format": "buddha.improver-study.v3",
                "repetitions": 1,
                "descendant_opportunities": 2,
            },
            "common": {(0, 0): self.pool[0]},
        }
        with self.f.h.readonly(), self.assertRaises(improver_study.ImproverStudyError):
            improver_study._plan(
                NativeEvidence(self.directory, self.authority.path),
                state,
                self.coordinate,
                self.pool,
                [],
                [],
            )
