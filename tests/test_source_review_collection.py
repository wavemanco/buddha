"""Checked review collection and separately scoped publication boundaries."""

import json
import tempfile
import unittest
from contextlib import contextmanager
from pathlib import Path
from unittest.mock import patch

from test_source_review import files, reference, sha

from buddha.releases import ReleaseError, _json


class SourceReviewCollectionTests(unittest.TestCase):
    def setUp(self):
        import test_source_review_results

        from buddha import source_review, source_review_handoff, source_review_results

        self.api, self.export, self.results = (
            source_review_handoff,
            source_review,
            source_review_results,
        )
        self.forms = test_source_review_results.SourceReviewResultsTests("runTest")
        self.forms.setUp()

    def test_collection_operator_api_is_available(self):
        from buddha.source_review_handoff import collect_source_reviews

        self.assertTrue(callable(collect_source_reviews))

    @contextmanager
    def publication_fixture(self, *, unavailable=False):
        # The checked importer is substituted here. These are filesystem and
        # publication checks, not original-owner or review-custody evidence.
        import test_source_review_handoff

        helper = test_source_review_handoff.SourceReviewHandoffTests("runTest")
        helper.setUp()
        with helper.publication_fixture() as (materialization, reader, arguments, roots):
            base = arguments["output"].parent
            published = base / "export"
            (published / "private").mkdir(parents=True)
            incoming = base / "forms"
            incoming.mkdir()
            if unavailable:
                materialization.update(packet=None, template=None, review=None)
                materialization["private"].update(
                    status="incomplete",
                    reason="no_selected_answer_sets_available",
                    packet_sha256=None,
                )
                materialization["private"]["coverage"].update(
                    available_sets=0,
                    unavailable_sets=1,
                    available_positions=0,
                    unavailable_positions=3,
                )
            round_record = self.forms.round_record(materialization)
            round_plan = published / "private/round.json"
            round_plan.write_bytes(self.export.encode_review(round_record))
            invalid = incoming / "invalid.json"
            invalid.write_bytes(b'{"format":"retained malformed supplied form"}')
            entry = reference(invalid)
            report = self.results._summarize(
                materialization, round_record, {"human-a": (entry, invalid.read_bytes())}
            )
            report["round_plan"], report["consumed_files"] = reference(round_plan), {}
            reader.capture.read(round_plan)
            reader.capture.read(invalid)
            controls = {
                Path(self.api.__file__).absolute(): sha(Path(self.api.__file__).read_bytes())
            }
            arguments.pop("reviewers")
            arguments.update(
                round_plan=round_plan,
                expected_round_plan_sha256=sha(round_plan.read_bytes()),
                submissions=[{"reviewer_id": "human-a", **entry}],
                output=base / "collection",
            )
            with patch.object(
                self.results, "_read_source_reviews", return_value=(report, reader, controls)
            ):
                yield report, reader, arguments, roots, published, incoming

    def assert_collection(self, report, reader, output, summary):
        expected = report | {
            "consumed_files": {str(path): sha(raw) for path, raw in reader.capture.raw.items()}
        }
        raw = self.export.encode_review(expected)
        self.assertEqual(
            {Path(name).as_posix() for name in files(output)}, {"report.json", "complete.json"}
        )
        self.assertEqual((output / "report.json").read_bytes(), raw)
        self.assertEqual(
            json.loads((output / "complete.json").read_bytes()),
            {
                "format": "buddha.source-review-collection.v1",
                "publication_status": "complete",
                "review_status": expected["status"],
                "reasons": expected["reasons"],
                "artifacts": {"report.json": sha(raw)},
            },
        )
        self.assertEqual(
            summary,
            {
                "format": "buddha.source-review-collection.v1",
                "status": expected["status"],
                "publication_status": "complete",
                "output": str(output),
                "complete": reference(output / "complete.json"),
                "report": reference(output / "report.json"),
            },
        )
        return expected

    def test_collection_publication_marker_last_retry_and_completed_inventory(self):
        with self.publication_fixture() as (report, reader, arguments, roots, published, incoming):
            output, publish = arguments["output"], self.api._publish

            def interrupt(path, raw):
                self.assertFalse((output / "complete.json").exists())
                if path.name == "complete.json":
                    raise KeyboardInterrupt
                publish(path, raw)

            with (
                patch.object(self.api, "_publish", side_effect=interrupt),
                self.assertRaises(KeyboardInterrupt),
            ):
                self.api.collect_source_reviews(**arguments)
            prefix = output / "report.json"
            before = prefix.read_bytes(), prefix.stat().st_mtime_ns, prefix.stat().st_ino
            summary = self.api.collect_source_reviews(**arguments)
            self.assert_collection(report, reader, output, summary)
            self.assertEqual(
                (prefix.read_bytes(), prefix.stat().st_mtime_ns, prefix.stat().st_ino), before
            )
            self.assertEqual(self.api.collect_source_reviews(**arguments), summary)
            prefix.unlink()
            broken = files(output)
            with self.assertRaises(ReleaseError):
                self.api.collect_source_reviews(**arguments)
            self.assertEqual(files(output), broken)

    def test_collection_protects_round_export_and_invalid_form_parent_without_census(self):
        with self.publication_fixture() as (report, reader, arguments, roots, published, incoming):
            # No completion marker exists: the literal private/round.json layout
            # still protects the entire operator export, including its siblings.
            forbidden = [
                published / "new",
                arguments["round_plan"].parent / "new",
                incoming / "new",
                *[root / "new" for root in roots.values()],
            ]
            for output in forbidden:
                with self.subTest(output=output), self.assertRaises(ReleaseError):
                    self.api.collect_source_reviews(**(arguments | {"output": output}))
                self.assertFalse(output.exists())
            publish = self.api._publish
            extra = incoming / "not-selected.json"

            def unrelated_arrival(path, raw):
                publish(path, raw)
                if path.name == "report.json":
                    extra.write_bytes(b"a separately arriving, unselected form")

            with patch.object(self.api, "_publish", side_effect=unrelated_arrival):
                summary = self.api.collect_source_reviews(**arguments)
            expected = self.assert_collection(report, reader, arguments["output"], summary)
            self.assertNotIn(str(extra), expected["consumed_files"])
            self.assertEqual(expected["reviews"][0]["status"], "invalid")
            self.assertEqual(
                expected["reviews"][0]["submission"], reference(incoming / "invalid.json")
            )

    def test_collection_refuses_conflicting_prefix_and_preserves_unavailable_sample(self):
        with self.publication_fixture(unavailable=True) as (
            report,
            reader,
            arguments,
            roots,
            published,
            incoming,
        ):
            output = arguments["output"]
            output.mkdir()
            artifact = output / "report.json"
            artifact.write_bytes(b"conflicting retained report")
            before = files(output)
            with self.assertRaises(ReleaseError):
                self.api.collect_source_reviews(**arguments)
            self.assertEqual(files(output), before)
            summary = self.api.collect_source_reviews(
                **(arguments | {"output": output.with_name("available-publication")})
            )
            expected = self.assert_collection(
                report, reader, output.with_name("available-publication"), summary
            )
            self.assertEqual(expected["status"], "incomplete")
            self.assertIn("source_sample_unavailable", expected["reasons"])
            self.assertEqual(expected["items"], [])

    def test_genuine_collection_preserves_originals_and_rejects_late_consumed_changes(self):
        import test_final_evaluation
        import test_source_review

        from buddha.authorization import Authorization
        from buddha.trial_fence import _scope_text, _TrialScope

        cohort = test_final_evaluation.FinalEvaluationTests("runTest")
        cohort.setUp()
        self.addCleanup(cohort.doCleanups)
        cohort.fixture()
        cohort.definition["final_ids"] = ["final-a"]
        # Prospectively declare the unused final-b exposed development, keeping
        # every assigned final task in the later frozen two-arm schedule.
        for member in cohort.f.custody["population"]:
            if member["task_id"] == "final-b":
                member.update(phase="development", exposure="exposed")
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
        cohort.declaration = cohort.f.write("review-collection-trial.json", cohort.definition)
        identity = sha(_json(cohort.definition))
        cohort.authorities = {
            phase: Authorization.create(
                cohort.f.root / ("review-collection-" + phase + ".sqlite3"),
                authorization_id="supplied-review-collection-" + phase,
                scope=_scope_text(_TrialScope(cohort.root, identity, phase)),
                **limits,
            )
            for phase, limits in cohort.definition["phase_limits"].items()
        }
        cohort.prepare()
        cohort.freeze(cohort.validate())
        with cohort.offline():
            self.assertEqual(cohort.run_final()["status"], "complete")
        common = dict(
            directory=cohort.root,
            kind="final",
            expected_report_sha256=sha((cohort.root / "final/report.json").read_bytes()),
            plan=plan,
            expected_plan_sha256=sha(plan.read_bytes()),
        )
        with tempfile.TemporaryDirectory() as temporary:
            base = Path(temporary).resolve()
            reviewers = [{"id": "human-a", "type": "human"}, {"id": "model-b", "type": "model"}]
            with exporter.passive(forbid_writes=False):
                exported = self.api.export_source_review(
                    **common, output=base / "export", reviewers=reviewers
                )
            packet = json.loads((base / "export/reviewer/pack.json").read_bytes())
            incoming = base / "forms"
            incoming.mkdir()
            responses, refs = [], []
            for reviewer in reviewers:
                response = self.forms.response(packet, reviewer["id"], reviewer["type"])
                if reviewer["type"] == "model":
                    for item in response["items"]:
                        item["groups"] = [[answer["id"]] for answer in item["answers"]]
                        item["answers"][0]["compliance"] = "violates"
                path = incoming / (reviewer["id"] + ".json")
                path.write_bytes(self.export.encode_review(response))
                responses.append(response)
                refs.append({"reviewer_id": reviewer["id"], **reference(path)})
            invalid = incoming / "human-a-original-invalid.json"
            invalid.write_bytes(b'{"format":"original malformed supplied response"}')
            invalid_ref = {"reviewer_id": "human-a", **reference(invalid)}
            arguments = common | dict(
                round_plan=Path(exported["round_plan"]["path"]),
                expected_round_plan_sha256=exported["round_plan"]["sha256"],
            )
            before = (
                files(cohort.f.root),
                files(incoming),
                files(base / "export"),
                cohort.engine.physical_sends,
                cohort.engine.workers,
            )
            original, observed = self.results._read_source_reviews, []

            def checked(*args, **kwargs):
                result = original(*args, **kwargs)
                observed.append(result)
                return result

            for label, submissions in (("empty", []), ("invalid", [invalid_ref]), ("valid", refs)):
                output = base / ("collection-" + label)
                if label == "valid":
                    previous = files(base / "collection-invalid")
                    with exporter.passive(forbid_writes=False), self.assertRaises(ReleaseError):
                        self.api.collect_source_reviews(
                            **arguments, submissions=refs, output=base / "collection-invalid"
                        )
                    self.assertEqual(files(base / "collection-invalid"), previous)
                with (
                    exporter.passive(forbid_writes=False),
                    patch.object(self.results, "_read_source_reviews", side_effect=checked),
                ):
                    summary = self.api.collect_source_reviews(
                        **arguments, submissions=submissions, output=output
                    )
                report, reader, _ = observed[-1]
                expected = self.assert_collection(report, reader, output, summary)
                self.assertEqual(
                    expected["status"], "complete" if label == "valid" else "incomplete"
                )
                self.assertEqual(
                    (
                        files(cohort.f.root),
                        files(incoming),
                        files(base / "export"),
                        cohort.engine.physical_sends,
                        cohort.engine.workers,
                    ),
                    before,
                )
                if label == "empty":
                    self.assertEqual(expected["reasons"], ["missing_reviews"])
                elif label == "invalid":
                    self.assertEqual(
                        set(expected["reasons"]), {"missing_reviews", "invalid_reviews"}
                    )
                    self.assertEqual(expected["reviews"][0]["submission"], reference(invalid))
                    self.assertIsNone(expected["reviews"][0]["response"])
                else:
                    self.assertTrue(expected["items"][0]["partition_disagreement"])
                    self.assertTrue(expected["items"][0]["compliance_disagreements"])
                    self.assertEqual([row["response"] for row in expected["reviews"]], responses)
            report = observed[-1][0]
            selected = Path(report["source"]["sets"][0]["binding"]["answers_path"])
            for index, target in enumerate(
                (selected, arguments["round_plan"], Path(refs[0]["path"]))
            ):
                raw, output, publish = (
                    target.read_bytes(),
                    base / ("late-" + str(index)),
                    self.api._publish,
                )

                def change_after_prefix(path, value, publish=publish, target=target, raw=raw):
                    publish(path, value)
                    if path.name == "report.json":
                        target.write_bytes(bytes([raw[0] ^ 1]) + raw[1:])

                try:
                    with (
                        self.subTest(late=target.name),
                        exporter.passive(forbid_writes=False),
                        patch.object(self.api, "_publish", side_effect=change_after_prefix),
                        self.assertRaises(ReleaseError),
                    ):
                        self.api.collect_source_reviews(
                            **arguments, submissions=refs, output=output
                        )
                    self.assertTrue((output / "report.json").is_file())
                    self.assertFalse((output / "complete.json").exists())
                finally:
                    target.write_bytes(raw)
            duplicate_sets = [
                refs + [refs[0]],
                [refs[0], refs[1] | {"path": refs[0]["path"]}],
                [refs[0], refs[1] | {"sha256": refs[0]["sha256"]}],
                [refs[0] | {"sha256": "0" * 64}],
            ]
            for index, submissions in enumerate(duplicate_sets):
                output = base / ("duplicate-" + str(index))
                with exporter.passive(forbid_writes=False), self.assertRaises(ReleaseError):
                    self.api.collect_source_reviews(
                        **arguments, submissions=submissions, output=output
                    )
                self.assertFalse(output.exists())
            self.assertEqual(
                (
                    files(cohort.f.root),
                    files(incoming),
                    files(base / "export"),
                    cohort.engine.physical_sends,
                    cohort.engine.workers,
                ),
                before,
            )
