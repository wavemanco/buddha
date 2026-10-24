"""Checked source custody and separately scoped filesystem publication controls."""

import json
import os
import tempfile
import unittest
from contextlib import contextmanager
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from test_source_review import files, reference, sha

from buddha.doctor import _Capture
from buddha.releases import MAX_JSON_BYTES, ReleaseError, _json


class SourceReviewHandoffTests(unittest.TestCase):
    def setUp(self):
        from buddha import source_review, source_review_handoff, source_review_results

        self.api, self.export, self.results = (
            source_review_handoff,
            source_review,
            source_review_results,
        )
        self.reviewers = [{"id": "human-a", "type": "human"}, {"id": "model-b", "type": "model"}]

    def test_export_operator_api_is_available(self):
        from buddha.source_review_handoff import export_source_review

        self.assertTrue(callable(export_source_review))

    @contextmanager
    def publication_fixture(self):
        # This substitutes ONLY the checked-reader handoff. It proves publication
        # boundaries, not original owners, final evidence or scientific custody.
        import test_source_review_results

        helper = test_source_review_results.SourceReviewResultsTests("runTest")
        helper.setUp()
        materialization = helper.pure_materialization()
        materialization["private"]["reason"] = None
        with tempfile.TemporaryDirectory() as temporary:
            base = Path(temporary).resolve()
            roots = {
                name: base / name
                for name in ("source", "reader", "capture", "retained", "component")
            }
            for root in roots.values():
                root.mkdir()
            plan = roots["source"] / "plan.json"
            plan.write_bytes(b"{}")
            consumed = roots["capture"] / "consumed.json"
            consumed.write_bytes(b"original consumed bytes")
            capture, retained = _Capture(roots["capture"]), _Capture(roots["retained"])
            capture.read(consumed)
            controls = {
                Path(module.__file__).absolute(): sha(Path(module.__file__).read_bytes())
                for module in (self.api, self.results)
            }
            controls[plan] = sha(plan.read_bytes())

            def raw(path, expected=None):
                value = capture.read(path)
                if expected is not None:
                    self.assertEqual(sha(value), expected)
                return value

            def finish():
                result = capture.finish()
                retained.finish()
                return result

            reader = SimpleNamespace(
                root=roots["reader"],
                capture=capture,
                _retained=[retained],
                owners={
                    "supplied": SimpleNamespace(
                        manifest={"roots": {"agent": str(roots["component"])}}
                    )
                },
                raw=raw,
                finish=finish,
            )
            arguments = dict(
                directory=roots["source"],
                kind="final",
                expected_report_sha256="2" * 64,
                plan=plan,
                expected_plan_sha256=sha(plan.read_bytes()),
                reviewers=self.reviewers,
                output=base / "output",
            )
            with patch.object(
                self.export, "_read_source_review", return_value=(materialization, reader, controls)
            ):
                yield materialization, reader, arguments, roots

    def assert_publication(self, materialization, output, summary):
        wanted = {
            "private/materialization.json": self.export.encode_review(materialization["private"]),
            "private/round.json": self.export.encode_review(
                {
                    "format": "buddha.source-review-round.v1",
                    **{
                        key: materialization["private"][key]
                        for key in ("plan_sha256", "report_sha256", "packet_sha256")
                    },
                    "reviewers": self.reviewers,
                }
            ),
        }
        if materialization["packet"] is not None:
            wanted.update(
                {
                    "reviewer/pack.json": self.export.encode_review(materialization["packet"]),
                    "reviewer/response-template.json": self.export.encode_review(
                        materialization["template"]
                    ),
                    "reviewer/review.md": materialization["review"].encode(),
                }
            )
        self.assertEqual(
            {Path(name).as_posix() for name in files(output)}, set(wanted) | {"complete.json"}
        )
        for name, raw in wanted.items():
            self.assertEqual((output / name).read_bytes(), raw)
        marker = json.loads((output / "complete.json").read_bytes())
        self.assertEqual(
            marker,
            {
                "format": "buddha.source-review-export.v1",
                "publication_status": "complete",
                "source_status": materialization["private"]["status"],
                "reason": materialization["private"]["reason"],
                "artifacts": {name: sha(raw) for name, raw in wanted.items()},
            },
        )
        self.assertEqual(
            summary,
            {
                "format": "buddha.source-review-export.v1",
                "status": materialization["private"]["status"],
                "publication_status": "complete",
                "output": str(output),
                "complete": reference(output / "complete.json"),
                "round_plan": reference(output / "private/round.json"),
                "reviewer_directory": str(output / "reviewer")
                if materialization["packet"] is not None
                else None,
            },
        )

    def test_publication_is_exact_marker_last_and_identical_prefix_resumes(self):
        with self.publication_fixture() as (materialization, reader, arguments, roots):
            output, published = arguments["output"], []
            original = self.api._publish

            def interrupt(path, raw):
                self.assertFalse((output / "complete.json").exists())
                if path.name == "complete.json":
                    raise KeyboardInterrupt
                original(path, raw)
                published.append(path)

            with (
                patch.object(self.api, "_publish", side_effect=interrupt),
                self.assertRaises(KeyboardInterrupt),
            ):
                self.api.export_source_review(**arguments)
            self.assertEqual(len(published), 5)
            prefix = {
                path: (path.read_bytes(), path.stat().st_mtime_ns, path.stat().st_ino)
                for path in published
            }
            summary = self.api.export_source_review(**arguments)
            self.assert_publication(materialization, output, summary)
            self.assertEqual(
                {
                    path: (path.read_bytes(), path.stat().st_mtime_ns, path.stat().st_ino)
                    for path in published
                },
                prefix,
            )
            before = files(output)
            self.assertEqual(self.api.export_source_review(**arguments), summary)
            self.assertEqual(files(output), before)
            # A completed marker is never permission to refill a missing file.
            (output / "reviewer/pack.json").unlink()
            broken = files(output)
            with self.assertRaises(ReleaseError):
                self.api.export_source_review(**arguments)
            self.assertEqual(files(output), broken)
            reader.finish()

    def test_publication_refuses_noncanonical_overlap_and_invalid_rosters_before_writes(self):
        with self.publication_fixture() as (_, reader, arguments, roots):
            outputs = [root / "nested" for root in roots.values()]
            outputs += [
                arguments["plan"],
                roots["source"] / ".." / "noncanonical",
                str(arguments["output"]),
            ]
            for output in outputs:
                with self.subTest(output=output), self.assertRaises(ReleaseError):
                    self.api.export_source_review(**(arguments | {"output": output}))
            bad_rosters = [
                [],
                self.reviewers * 2,
                [{"id": "", "type": "human"}],
                [{"id": "x", "type": "other"}],
                [{"id": "x", "type": "human", "extra": True}],
            ]
            for roster in bad_rosters:
                with self.subTest(roster=roster), self.assertRaises(ReleaseError):
                    self.api.export_source_review(**(arguments | {"reviewers": roster}))
            self.assertFalse(arguments["output"].exists())
            self.assertTrue(all(not (root / "nested").exists() for root in roots.values()))
            reader.finish()

    def test_publication_refuses_conflicts_unknown_links_and_oversized_files(self):
        with self.publication_fixture() as (_, reader, arguments, roots):
            base = arguments["output"].parent
            for label in ("conflict", "unknown", "link", "oversized"):
                output = base / label
                output.mkdir()
                if label == "unknown":
                    target = output / "unrecognized.tmp"
                    target.write_bytes(b"retain me")
                else:
                    (output / "reviewer").mkdir()
                    target = output / "reviewer/pack.json"
                    if label == "link":
                        external = base / "plain-link-source.txt"
                        external.write_bytes(b"unrelated link source")
                        os.link(external, target)
                    else:
                        with target.open("wb") as stream:
                            stream.write(b"conflicting bytes")
                            if label == "oversized":
                                stream.truncate(MAX_JSON_BYTES + 1)
                before = files(output)
                with self.subTest(prefix=label), self.assertRaises(ReleaseError):
                    self.api.export_source_review(**(arguments | {"output": output}))
                self.assertEqual(files(output), before)
                self.assertFalse((output / "complete.json").exists())
                target.unlink()
            reader.finish()

    def test_all_unavailable_publishes_only_private_evidence_and_marker(self):
        with self.publication_fixture() as (materialization, reader, arguments, roots):
            materialization.update(packet=None, template=None, review=None)
            materialization["private"].update(
                status="incomplete", reason="no_selected_answer_sets_available", packet_sha256=None
            )
            materialization["private"]["coverage"].update(
                available_sets=0, unavailable_sets=1, available_positions=0, unavailable_positions=3
            )
            summary = self.api.export_source_review(**arguments)
            self.assert_publication(materialization, arguments["output"], summary)
            self.assertFalse((arguments["output"] / "reviewer").exists())
            reader.finish()

    def test_genuine_final_export_retains_complete_text_custody_and_late_change_refusal(self):
        import test_final_evaluation
        import test_source_review

        from buddha.authorization import Authorization
        from buddha.trial_fence import _scope_text, _TrialScope

        cohort = test_final_evaluation.FinalEvaluationTests("runTest")
        cohort.setUp()
        self.addCleanup(cohort.doCleanups)
        cohort.fixture()
        cohort.definition["final_ids"] = ["final-a"]
        # Declare the unused final-b as exposed development before owners exist;
        # no frozen final member is omitted to make this cohort smaller.
        for member in cohort.f.custody["population"]:
            if member["task_id"] == "final-b":
                member.update(phase="development", exposure="exposed")
        texts = ["  Complete café tale: opening\nconflict and ending. 🐕  ", ""]
        cohort.engine.weak_answers = texts
        exporter = test_source_review.SourceReviewTests("runTest")
        exporter.setUp()
        self.addCleanup(exporter.doCleanups)
        plan, controls = exporter.controls(
            cohort.f.root,
            kind="final",
            experiment=cohort.definition["experiment_id"],
            tasks=cohort.f.tasks,
            roles=("candidate",),
            task_ids=("final-a",),
        )
        controls.extend(
            reference(Path(module.__file__).absolute()) for module in (self.api, self.results)
        )
        cohort.f.custody["evidence"].extend(controls)
        cohort.f.record["custody"] = reference(cohort.f.write("custody.json", cohort.f.custody))
        cohort.f.declaration = cohort.f.write("declaration.json", cohort.f.record)
        cohort.definition["validation"] = reference(cohort.f.declaration)
        cohort.declaration = cohort.f.write("review-export-trial.json", cohort.definition)
        identity = sha(_json(cohort.definition))
        cohort.authorities = {
            phase: Authorization.create(
                cohort.f.root / ("review-export-" + phase + ".sqlite3"),
                authorization_id="supplied-review-export-" + phase,
                scope=_scope_text(_TrialScope(cohort.root, identity, phase)),
                **limits,
            )
            for phase, limits in cohort.definition["phase_limits"].items()
        }
        cohort.prepare()
        cohort.freeze(cohort.validate())
        with cohort.offline():
            self.assertEqual(cohort.run_final()["status"], "complete")
        before = files(cohort.f.root), cohort.engine.physical_sends, cohort.engine.workers
        original, observed = self.export._read_source_review, []

        def checked(*args, **kwargs):
            result = original(*args, **kwargs)
            observed.append(result[0])
            return result

        with tempfile.TemporaryDirectory() as temporary:
            output = Path(temporary).resolve() / "export"
            arguments = dict(
                directory=cohort.root,
                kind="final",
                expected_report_sha256=sha((cohort.root / "final/report.json").read_bytes()),
                plan=plan,
                expected_plan_sha256=sha(plan.read_bytes()),
                reviewers=self.reviewers,
                output=output,
            )
            with (
                exporter.passive(forbid_writes=False),
                patch.object(self.export, "_read_source_review", side_effect=checked),
            ):
                summary = self.api.export_source_review(**arguments)
            self.assertEqual(len(observed), 1)
            materialization = observed[0]
            self.assert_publication(materialization, output, summary)
            self.assertEqual(
                {
                    answer["text"]
                    for item in materialization["packet"]["items"]
                    for answer in item["answers"]
                },
                set(texts),
            )
            selected = Path(materialization["private"]["sets"][0]["binding"]["answers_path"])
            raw = selected.read_bytes()
            late_output = output.with_name("late-change")

            publish = self.api._publish

            def change_during_publication(path, value):
                publish(path, value)
                if path.name == "materialization.json":
                    selected.write_bytes(bytes([raw[0] ^ 1]) + raw[1:])

            try:
                with (
                    exporter.passive(forbid_writes=False),
                    patch.object(self.api, "_publish", side_effect=change_during_publication),
                    self.assertRaises(ReleaseError),
                ):
                    self.api.export_source_review(**(arguments | {"output": late_output}))
                self.assertTrue((late_output / "private/materialization.json").is_file())
                self.assertFalse((late_output / "complete.json").exists())
            finally:
                selected.write_bytes(raw)
        self.assertEqual(
            (files(cohort.f.root), cohort.engine.physical_sends, cohort.engine.workers), before
        )
