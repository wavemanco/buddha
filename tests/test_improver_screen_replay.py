"""Completed finite-screen replay: real original custody, supplied workers only."""

import copy
import json
import unittest
from pathlib import Path
from unittest.mock import patch


class CompletedImproverScreenReplayTests(unittest.TestCase):
    def fixture(self):
        import test_improver_study

        from buddha import improver_study

        f = test_improver_study.FiniteImproverStudyTests("runTest")
        self.addCleanup(f.doCleanups)
        f.fixture_before_new_api()
        f.api = improver_study
        record = f.declaration(improver_study)
        record.update(starts=record["starts"][:1], repetitions=1, descendant_opportunities=1)
        record["selection"]["finalist_iteration"] = 1
        f.recompute_limits(record)
        directory, _, authority = f.prepare_study("study", record)
        return f, directory, directory / "common/0/0/screen", authority

    @staticmethod
    def observation(f, directory, authority):
        from buddha.native_evidence import NativeEvidence

        reader = NativeEvidence(directory, authority.path, error_type=f.api.ImproverStudyError)
        state = f.api._original(reader)
        f.api._census(reader, state)
        return reader, state

    def complete(self, f, screen_root):
        from buddha import source_screen

        with f.supplied():
            report = source_screen.run_source_screen(screen_root, transport=f.transport())
        self.assertEqual(report["status"], "complete")
        return report

    def test_completed_common_screen_replays_canonical_bytes_once_without_outer_stage_walk(self):
        from buddha import candidate_generation, source_screen_results
        from buddha.native_evidence import NativeEvidence
        from buddha.releases import _json

        f, directory, screen_root, authority = self.fixture()
        # Unpublished originals continue through the existing pending-owner path.
        with f.h.readonly():
            reader, state = self.observation(f, directory, authority)
            self.assertIsNone(f.api._screen(reader, state, screen_root, f.base))
            self.assertEqual(state["checked"], state["owner_paths"])
            reader.capture.finish()
        report = self.complete(f, screen_root)
        before = f.h.files(directory), authority.path.read_bytes(), f.engine.physical_sends
        # Passive replay must not need the external selected producer program.
        producer = Path(f.base.to_record()["generation"]["roots"]["agent"]) / "candidate.py"
        producer.rename(producer.with_name("retired-candidate.txt"))
        stages = []
        original_stage = NativeEvidence.stage

        def stage(reader, *args, **kwargs):
            stages.append(reader.root)
            return original_stage(reader, *args, **kwargs)

        with (
            f.h.readonly(),
            patch.object(
                candidate_generation, "_read_evidence", wraps=candidate_generation._read_evidence
            ) as sources,
            patch.object(
                source_screen_results,
                "collect_source_screen",
                wraps=source_screen_results.collect_source_screen,
            ) as screens,
            patch.object(NativeEvidence, "stage", autospec=True, side_effect=stage),
        ):
            reader, state = self.observation(f, directory, authority)
            result = f.api._screen(reader, state, screen_root, f.base)
            self.assertEqual(_json(result), (screen_root / "report.json").read_bytes())
            self.assertEqual(result, report)
            self.assertEqual(state["checked"], state["owner_paths"])
            self.assertFalse(state["inactive"])
            reader.capture.finish()
        self.assertEqual(screens.call_count, 1, "retain the actual authoritative full inspector")
        self.assertEqual(
            sources.call_count,
            2,
            "the full v2 inspector reads C1 twice; do not add an outer third read",
        )
        self.assertNotIn(
            directory, stages, "completed screen must not repeat the outer native stage walk"
        )
        self.assertEqual(
            (f.h.files(directory), authority.path.read_bytes(), f.engine.physical_sends), before
        )

    def test_completed_owner_provenance_matches_exact_original_census(self):
        f, directory, screen_root, authority = self.fixture()
        self.complete(f, screen_root)
        original = f.shared._read_ref
        foreign = json.loads((f.bootstrap_directories[0] / "report.json").read_bytes())[
            "provenance"
        ]["owners"][0]
        before = f.h.files(directory), authority.path.read_bytes(), f.engine.physical_sends

        def missing(rows):
            rows.pop()

        def extra(rows):
            rows.append(copy.deepcopy(foreign))

        def duplicate(rows):
            rows.append(copy.deepcopy(rows[0]))

        def changed_ledger(rows):
            rows[-1]["ledger_sha256"] = "0" * 64

        for label, change in (
            ("missing", missing),
            ("foreign", extra),
            ("duplicate", duplicate),
            ("ledger", changed_ledger),
        ):
            calls = []

            def corrupted(reader, reference, *, change=change, calls=calls, **kwargs):
                # Post-verification seam fault: the real lower inspector runs
                # first. No stored report, original manifest or SQL is forged.
                result = original(reader, reference, **kwargs)
                self.assertEqual(reference["directory"], str(screen_root))
                calls.append(reference)
                result = copy.deepcopy(result)
                change(result["provenance"]["owners"])
                return result

            with (
                self.subTest(provenance=label),
                f.h.readonly(),
                patch.object(f.shared, "_read_ref", side_effect=corrupted),
            ):
                reader, state = self.observation(f, directory, authority)
                with self.assertRaises(f.api.ImproverStudyError):
                    f.api._screen(reader, state, screen_root, f.base)
                self.assertEqual(len(calls), 1)
                reader.capture.finish()
        self.assertEqual(
            (f.h.files(directory), authority.path.read_bytes(), f.engine.physical_sends), before
        )

    def test_completed_failed_screen_still_rejects_empty_native_directory(self):
        from buddha import source_screen

        f, directory, screen_root, authority = self.fixture()
        failed = f.outcome.failed_worker(f.h, "1", f.execute)
        with patch.object(f, "execute", side_effect=failed):
            report = self.complete(f, screen_root)
        self.assertEqual(report["disposition"], "candidate_execution_failed")
        empty = screen_root / "tasks/0/evaluation"
        empty.mkdir()
        before = f.h.files(directory), authority.path.read_bytes(), f.engine.physical_sends
        with f.h.readonly():
            # This is a real finite-only distinction: lower complete custody
            # rejects descendants after failure but permits this empty directory.
            self.assertEqual(
                source_screen.inspect_source_screen(
                    screen_root,
                    authorization=authority.path,
                    expected_report_sha256=f.h.reference(screen_root, authority)["report_sha256"],
                ),
                report,
            )
            reader, state = self.observation(f, directory, authority)
            with self.assertRaises(f.api.ImproverStudyError):
                f.api._screen(reader, state, screen_root, f.base)
            reader.capture.finish()
        self.assertEqual(
            (f.h.files(directory), authority.path.read_bytes(), f.engine.physical_sends), before
        )

    def test_completed_later_native_owner_retains_finite_only_task_binding(self):
        from buddha import candidate_generation, native_evaluation, native_pipeline, source_screen
        from buddha.source_screen_results import collect_source_screen

        f, directory, screen_root, authority = self.fixture()
        location = screen_root / "tasks/0"
        task_path = location / "task.json"
        original_stage = native_evaluation._owner_stage
        original_prepare = native_evaluation.prepare_gateway
        created = []

        class CapturedPreparation(Exception):
            pass

        def supplied_owner(*args, **kwargs):
            if args[2] != 2:
                return original_stage(*args, **kwargs)
            captured = []

            def capture(owner, **values):
                captured.append((owner, values))
                raise CapturedPreparation

            # Ask the existing constructor for its real planned descriptor and
            # inputs, then supply a genuinely funded Gateway owner omitting one
            # finite-only binding. Other lower stages and inspectors are real.
            with patch.object(native_evaluation, "prepare_gateway", side_effect=capture):
                with self.assertRaises(CapturedPreparation):
                    original_stage(*args, **kwargs)
            self.assertEqual(len(captured), 1)
            owner, values = captured[0]
            self.assertIn(task_path, values["input_files"])
            values["input_files"] = [path for path in values["input_files"] if path != task_path]
            values["expected_input_hashes"].pop(task_path)
            original_prepare(owner, **values)
            created.append(owner)
            return owner, args[0] / "command-2.json"

        with f.supplied():
            generated = candidate_generation.run_candidate_generation(
                location / "generation", transport=f.transport()
            )
            self.assertEqual(generated["disposition"], "generated")
            descriptor = source_screen._evaluation_recipe(location, f.base)
            reader, state = self.observation(f, directory, authority)
            context = json.loads((screen_root / "context.json").read_bytes())
            controls = {Path(path): digest for path, digest in context["controls"].items()}
            controls |= {
                screen_root / "screen.json": f.base.fingerprint(),
                screen_root / "context.json": native_pipeline._sha(context),
            }
            controls |= source_screen._task_controls(location, f.base, 0)
            controls[descriptor] = native_pipeline._sha(
                source_screen._evaluation_record(location, f.base)
            )
            reader.capture.finish()
            native_evaluation.prepare_evaluation(
                location / "evaluation",
                descriptor=descriptor,
                authorization=authority,
                review=state["review"],
                input_files=list(controls),
                expected_input_hashes=controls,
            )
            with patch.object(native_evaluation, "_owner_stage", side_effect=supplied_owner):
                native = native_evaluation.run_evaluation(
                    location / "evaluation", transport=f.transport()
                )
            self.assertEqual(native["status"], "complete")
        self.assertEqual(created, [location / "evaluation/owners/2"])
        report = collect_source_screen(screen_root, authorization=authority.path)
        native_pipeline.publish_complete(
            screen_root / "report.json",
            report,
            authority,
            {row["run_id"] for row in report["provenance"]["owners"]},
        )
        self.assertEqual(f.h.inspect(screen_root, authority), report)
        manifest = json.loads((created[0] / "manifest.json").read_bytes())
        self.assertNotIn(str(task_path), {row["path"] for row in manifest["invocation"]["inputs"]})
        before = f.h.files(directory), authority.path.read_bytes(), f.engine.physical_sends
        with f.h.readonly():
            reader, state = self.observation(f, directory, authority)
            with self.assertRaisesRegex(
                f.shared.SourceSearchError, "prepared owner omits an original input"
            ):
                f.api._screen(reader, state, screen_root, f.base)
            reader.capture.finish()
        self.assertEqual(
            (f.h.files(directory), authority.path.read_bytes(), f.engine.physical_sends), before
        )

    def test_completed_screen_retains_native_bytes_through_outer_observation_finish(self):
        from buddha import doctor
        from buddha.releases import _json

        f, directory, screen_root, authority = self.fixture()
        report = self.complete(f, screen_root)
        artifact = Path(report["tasks"][0]["summary"]["path"])
        self.assertTrue(artifact.is_relative_to(screen_root / "tasks/0/evaluation"))
        original = artifact.read_bytes()
        self.assertTrue(original)
        before = f.h.files(directory), authority.path.read_bytes(), f.engine.physical_sends
        with f.h.readonly():
            reader, state = self.observation(f, directory, authority)
            # The genuine nested inspector and its own finish run before this
            # post-inspection metadata seam. No saved custody is mocked.
            result = f.api._screen(reader, state, screen_root, f.base)
            self.assertEqual(_json(result), _json(report))
            inventory = reader.capture.entries

            def unchanged_outer_inventory(root):
                self.assertEqual(root, directory)
                return inventory

            # Hold only the outer final metadata observation constant; this is
            # an explicit fault seam, not a claim that ctime was restored.
            # The ordinary final byte reads remain real and must detect drift.
            try:
                artifact.write_bytes(bytes([original[0] ^ 1]) + original[1:])
                with patch.object(doctor, "_entries", side_effect=unchanged_outer_inventory):
                    with self.assertRaisesRegex(doctor._Busy, "consumed input changed"):
                        reader.capture.finish()
            finally:
                artifact.write_bytes(original)
            self.assertEqual(reader.capture.raw[artifact], original)
        self.assertEqual(
            (f.h.files(directory), authority.path.read_bytes(), f.engine.physical_sends), before
        )


if __name__ == "__main__":
    unittest.main()
