"""One local witness retains semantic validation and freshly checks its evidence."""

import unittest
from unittest.mock import patch

import test_feedback_parent_reuse as parent_fixtures

from buddha import doctor, source_feedback, source_screen_results, source_search
from buddha.native_evidence import NativeEvidence
from buddha.releases import ReleaseError, _json


class WitnessScreenReadReuseTests(unittest.TestCase):
    setUpClass = classmethod(parent_fixtures.FeedbackParentReuseTests.setUpClass.__func__)

    def reader(self):
        return NativeEvidence(self.scope, self.authority.path)

    def retained(self):
        return source_search._witness_parent_read(self.reader(), self.treatment)

    def test_one_witness_plan_collects_its_completed_screen_once(self):
        name = (
            "_collect_source_screen"
            if hasattr(source_screen_results, "_collect_source_screen")
            else "collect_source_screen"
        )
        with (
            self.h.readonly(),
            patch.object(source_search, "_search_witness_treatment", return_value=self.treatment),
            patch.object(
                source_screen_results, name, wraps=getattr(source_screen_results, name)
            ) as collect,
        ):
            source_search._witness_plan(self.reader(), {}, self.reference, self.scope / "witness")
        self.assertEqual(collect.call_count, 1)

    def test_default_and_retained_plan_and_packets_have_exact_bytes(self):
        before = self.h.files(self.h.root), self.authority.summary(), self.h.engine.physical_sends
        with self.h.readonly():
            parent = source_search._witness_parent(self.reader(), self.treatment)
            _, ordinary_plan, ordinary = source_search._witness_materials(self.treatment, parent)
            parent, completed = self.retained()
            detached = source_search._read_ref(self.reader(), self.reference, completed=completed)
            detached["tasks"] = []
            _, reused_plan, reused = source_search._witness_materials(
                self.treatment, parent, completed=completed
            )
        self.assertEqual(_json(ordinary_plan), _json(reused_plan))
        self.assertEqual(_json(ordinary), _json(reused))
        self.assertEqual(
            before,
            (self.h.files(self.h.root), self.authority.summary(), self.h.engine.physical_sends),
        )

    def test_consumed_files_authority_sidecar_and_namespace_drift_are_denied(self):
        paths = [
            self.directory / "report.json",
            self.directory / "screen.json",
            next(self.directory.rglob("partitions.jsonl")),
            self.directory / "tasks/0/generation/owners/0/manifest.json",
            self.authority.path,
        ]
        for path in paths:
            parent, completed = self.retained()
            raw = path.read_bytes()
            try:
                path.write_bytes(b"X" + raw[1:])
                with (
                    self.subTest(path=path.name),
                    self.h.readonly(),
                    self.assertRaises(ReleaseError),
                ):
                    source_feedback._build(
                        self.scope / "unused",
                        self.reference,
                        parent_screen=parent,
                        completed=completed,
                    )
            finally:
                path.write_bytes(raw)
        for path in [
            self.authority.path.with_name(self.authority.path.name + "-wal"),
            self.directory / "orphan.json",
        ]:
            parent, completed = self.retained()
            self.assertFalse(path.exists())
            try:
                path.write_bytes(b"unexpected")
                with (
                    self.subTest(path=path.name),
                    self.h.readonly(),
                    self.assertRaises(ReleaseError),
                ):
                    source_feedback._build(
                        self.scope / "unused",
                        self.reference,
                        parent_screen=parent,
                        completed=completed,
                    )
            finally:
                path.unlink()

    def test_unavailable_optional_lease_context_keeps_original_full_inspections(self):
        lock = self.scope / ".search.lock"
        self.assertFalse(lock.exists())
        try:
            lock.write_bytes(b"x" * (doctor._MAX_LOCK_BYTES + 1))
            with self.h.readonly():
                parent, completed = self.retained()
                self.assertIsNone(completed)
                source_search._witness_materials(self.treatment, parent, completed=completed)
        finally:
            lock.unlink()

    def test_scope_and_untyped_reference_reuse_are_denied(self):
        parent, completed = self.retained()
        for reference in [
            self.reference | {"report_sha256": "0" * 64},
            self.reference | {"authorization": str(self.authority.path.with_name("other.sqlite3"))},
            self.reference | {"directory": str(self.scope)},
        ]:
            with (
                self.subTest(reference=reference),
                self.h.readonly(),
                self.assertRaises(ReleaseError),
            ):
                source_feedback._build(
                    self.scope / "unused", reference, parent_screen=parent, completed=completed
                )
        with self.h.readonly(), self.assertRaises(ReleaseError):
            source_feedback._build(
                self.scope / "unused",
                self.reference,
                parent_screen=parent,
                completed={"status": "complete"},
            )
        with doctor._observation_policy(
            {
                "format": "buddha.evidence-observation-policy.v2",
                "max_total_bytes": 1,
                "max_tree_entries": 1,
                "max_consumed_paths": 1,
                "max_resident_bytes": 0,
            }
        ):
            with self.assertRaises(ReleaseError):
                source_feedback._build(
                    self.scope / "unused", self.reference, parent_screen=parent, completed=completed
                )
        with (
            patch.object(doctor, "_tree_context", return_value=None),
            self.assertRaises(ReleaseError),
        ):
            source_feedback._build(
                self.scope / "unused", self.reference, parent_screen=parent, completed=completed
            )
        marker = self.scope / ".buddha-evaluation-trial.json"
        try:
            marker.write_bytes(b"{}")
            with self.assertRaises(ReleaseError):
                source_feedback._build(
                    self.scope / "unused", self.reference, parent_screen=parent, completed=completed
                )
        finally:
            marker.unlink()

    def test_late_mutation_and_retained_sibling_namespace_are_denied(self):
        read = source_feedback.candidate_generation.read_candidate_generation_source
        parent, completed = self.retained()
        extra = self.directory / "late.json"

        def late(*args, **kwargs):
            result = read(*args, **kwargs)
            extra.write_bytes(b"{}")
            return result

        try:
            with (
                patch.object(
                    source_feedback.candidate_generation,
                    "read_candidate_generation_source",
                    side_effect=late,
                ),
                self.assertRaises(ReleaseError),
            ):
                source_feedback._build(
                    self.scope / "unused", self.reference, parent_screen=parent, completed=completed
                )
        finally:
            extra.unlink(missing_ok=True)
        parent, completed = self.retained()
        sibling = self.h.root / "retained-sibling"
        sibling.mkdir()
        completed.reader.retain_capture(doctor._Capture(sibling))
        try:
            (sibling / "unexpected").write_bytes(b"x")
            with self.assertRaises(ReleaseError):
                source_feedback._build(
                    self.scope / "unused", self.reference, parent_screen=parent, completed=completed
                )
        finally:
            (sibling / "unexpected").unlink()
            sibling.rmdir()


if __name__ == "__main__":
    unittest.main()
