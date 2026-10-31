"""Reuse immutable witness declarations while preserving full fresh screen custody."""

import json
import unittest
from pathlib import Path
from unittest.mock import patch

import test_source_screen as fixtures
import test_source_screen_outcome as outcome_fixtures

from buddha import answers, doctor, source_feedback, source_screen, source_search
from buddha.native_evidence import NativeEvidence
from buddha.releases import ReleaseError, _json


class FeedbackParentReuseTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.outcome = outcome_fixtures.SourceScreenOutcomeTests("runTest")
        cls.addClassCleanup(cls.outcome.doCleanups)
        cls.h = h = cls.outcome.fixture()
        h.record["format"] = "buddha.source-screen.v2"
        cls.scope = h.root / "supplied-study"
        cls.scope.mkdir()
        (cls.scope / "witness").mkdir()
        screen = h.screen()
        generation = screen.to_record()["generation"]
        controls = {
            path: fixtures.sha(path.read_bytes())
            for path in [
                *source_search._sources(),
                Path(generation["runtime"]["path"]),
            ]
        }
        cls.directory, cls.authority = h.prepare(
            screen, cls.scope / "common", input_bindings=controls
        )
        h.assertEqual(h.run_screen(cls.directory)["status"], "complete")
        cls.reference = h.reference(cls.directory, cls.authority)
        cls.treatment = source_search._witness_declaration(
            scope=cls.scope,
            directory=cls.scope / "witness",
            parent=cls.reference,
            base_screen=screen,
            proposal_template={
                name: generation[name]
                for name in ("config", "profile", "max_callbacks", "budget_microusd", "max_calls")
            },
            review=h.engine.fixture.review,
            expected_runtime_sha256=h.engine.candidate.expected_runtime,
            controls=controls,
            source_copy=False,
        )

    def parent(self):
        reader = NativeEvidence(self.scope, self.authority.path)
        parent = source_search._witness_parent(reader, self.treatment)
        reader.finish()
        return parent

    def test_witness_reuses_parent_without_changing_packet_inspection_or_finish(self):
        before = self.h.files(self.h.root), self.authority.summary(), self.h.engine.physical_sends
        ordinary_bundle, ordinary_finish = source_search._bundle, doctor._Capture.finish

        def measured(*, force_default):
            parent = self.parent()
            finishes = []

            def finish(capture):
                finishes.append(capture.root)
                return ordinary_finish(capture)

            def bundle(*args, **kwargs):
                if force_default:
                    kwargs.pop("parent_screen", None)
                return ordinary_bundle(*args, **kwargs)

            with (
                self.h.readonly(),
                patch.object(source_search, "_bundle", side_effect=bundle),
                patch.object(doctor._Capture, "finish", finish),
                patch.object(
                    source_screen,
                    "inspect_source_screen",
                    wraps=source_screen.inspect_source_screen,
                ) as inspect,
                patch.object(
                    source_screen.SourceScreen,
                    "from_bytes",
                    wraps=source_screen.SourceScreen.from_bytes,
                ) as parsed,
                patch.object(answers, "_population", wraps=answers._population) as populations,
            ):
                _, plan, packet = source_search._witness_materials(self.treatment, parent)
            return (
                plan,
                packet,
                inspect.call_count,
                parsed.call_count,
                populations.call_count,
                finishes,
            )

        default = measured(force_default=True)
        reused = measured(force_default=False)
        self.assertEqual(_json(default[0]), _json(reused[0]))
        self.assertEqual(_json(default[1]), _json(reused[1]))
        self.assertEqual(default[2], 1)
        self.assertEqual(reused[2], 1)
        self.assertEqual(default[5], reused[5])
        self.assertGreater(len(reused[5]), 0)
        self.assertEqual(reused[3], 1)  # Full collector parses its own original screen once.
        self.assertGreater(default[3], reused[3])
        self.assertGreater(default[4], reused[4])
        self.assertEqual(
            (self.h.files(self.h.root), self.authority.summary(), self.h.engine.physical_sends),
            before,
        )
        print(
            "[feedback-parent] "
            + str(
                {
                    "default_constructions": default[3:5],
                    "reused_constructions": reused[3:5],
                    "inspections": reused[2],
                    "finishes": len(reused[5]),
                }
            ),
            flush=True,
        )

    def test_wrong_or_untyped_declaration_is_not_accepted_as_evidence(self):
        parent = self.parent()
        wrong = parent.to_record()
        wrong["selected_ids"].reverse()
        wrong = source_screen.SourceScreen.from_bytes(_json(wrong))
        for value in (wrong, parent.to_record(), {"status": "complete"}):
            with (
                self.subTest(kind=type(value).__name__),
                self.h.readonly(),
                self.assertRaises(source_feedback.SourceFeedbackError),
            ):
                source_feedback._build(
                    self.scope / "unused-feedback", self.reference, parent_screen=value
                )

    def test_reused_declaration_does_not_bypass_changed_custody_or_sidecars(self):
        parent = self.parent()
        partition = next(self.directory.rglob("partitions.jsonl"))
        owner = self.directory / "tasks/0/generation/owners/0/manifest.json"
        paths = [
            self.directory / "report.json",
            self.directory / "screen.json",
            partition,
            owner,
            self.authority.path,
        ]
        for path in paths:
            original = path.read_bytes()
            if path == owner:
                manifest = json.loads(original)
                manifest["run_id"] = "0" * 32
                changed = _json(manifest)
            else:
                changed = b"X" + original[1:] if path == self.authority.path else original + b"\n"
            try:
                path.write_bytes(changed)
                with (
                    self.subTest(name=path.name),
                    self.h.readonly(),
                    self.assertRaises(ReleaseError),
                ):
                    source_feedback._build(
                        self.scope / "unused-feedback", self.reference, parent_screen=parent
                    )
            finally:
                path.write_bytes(original)
        sidecar = self.authority.path.with_name(self.authority.path.name + "-wal")
        self.assertFalse(sidecar.exists())
        try:
            sidecar.write_bytes(b"unsettled supplied sidecar")
            with self.h.readonly(), self.assertRaises(ReleaseError):
                source_feedback._build(
                    self.scope / "unused-feedback", self.reference, parent_screen=parent
                )
        finally:
            sidecar.unlink()

    def test_late_report_drift_is_still_rechecked_after_feedback_derivation(self):
        parent = self.parent()
        report = self.directory / "report.json"
        original = report.read_bytes()
        read = source_feedback.candidate_generation.read_candidate_generation_source
        changed = False

        def late(*args, **kwargs):
            nonlocal changed
            result = read(*args, **kwargs)
            if not changed:
                report.write_bytes(original + b"\n")
                changed = True
            return result

        try:
            with (
                self.h.readonly(),
                patch.object(
                    source_feedback.candidate_generation,
                    "read_candidate_generation_source",
                    side_effect=late,
                ),
                self.assertRaises(ReleaseError),
            ):
                source_feedback._build(
                    self.scope / "unused-feedback", self.reference, parent_screen=parent
                )
            self.assertTrue(changed)
        finally:
            report.write_bytes(original)
