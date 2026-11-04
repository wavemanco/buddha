"""Current source reviews retain exact coverage and independent disagreements."""

import copy
import unittest
from pathlib import Path
from unittest.mock import patch

from test_source_review import files, reference, sha

from buddha.releases import ReleaseError, _json


class SourceReviewResultsTests(unittest.TestCase):
    def setUp(self):
        import test_meas01_pack

        from buddha import source_review, source_review_results

        self.api, self.export, self.legacy = source_review_results, source_review, test_meas01_pack

    def test_current_source_review_import_has_explicit_validation_and_inspection(self):
        # The initial missing-interface RED occurs before fixtures or owners.
        from buddha.source_review_results import (
            inspect_source_reviews,
            validate_review_submission,
        )

        self.assertTrue(callable(validate_review_submission))
        self.assertTrue(callable(inspect_source_reviews))

    def packet(self):
        return {
            "format": "buddha.meas01-pack.v1",
            "rule": {"text": "Supplied central-content rule.", "sha256": sha(b"supplied rule")},
            "items": [
                {
                    "id": "masked-item",
                    "prompt": "Give three alternatives about a café.",
                    "answers": [
                        {"id": "a", "text": "  literal café text  "},
                        {"id": "b", "text": ""},
                        {"id": "c", "text": "A different development."},
                    ],
                }
            ],
        }

    def response(self, packet, reviewer="human-a", kind="human"):
        response = self.export._template(packet)
        response["reviewer"] = {
            "id": reviewer,
            "type": kind,
            "prior_exposure": "Supplied synthetic schema fixture, not an independent human review.",
        }
        for item in response["items"]:
            item["groups"] = [[answer["id"] for answer in item["answers"]]]
            item["rationale"] = "Supplied tentative grouping."
            for answer in item["answers"]:
                answer["compliance"] = "uncertain"
                answer["compliance_rationale"] = "No independent judgment is claimed."
        return response

    def pure_materialization(self):
        packet = self.packet()
        template = self.export._template(packet)
        return {
            "packet": packet,
            "template": template,
            "review": "Supplied pure-summary data, not source-custody evidence.",
            "private": {
                "status": "complete",
                "reason": None,
                "plan_sha256": "1" * 64,
                "report_sha256": "2" * 64,
                "packet_sha256": sha(self.export.encode_review(packet)),
                "coverage": {
                    "planned_sets": 1,
                    "available_sets": 1,
                    "unavailable_sets": 0,
                    "planned_positions": 3,
                    "available_positions": 3,
                    "unavailable_positions": 0,
                },
            },
        }

    def round_record(self, materialization):
        private = materialization["private"]
        # Three declared synthetic roles exercise coverage; this is not a
        # production sample-size or independence requirement.
        return {
            "format": "buddha.source-review-round.v1",
            "plan_sha256": private["plan_sha256"],
            "report_sha256": private["report_sha256"],
            "packet_sha256": private["packet_sha256"],
            "reviewers": [
                {"id": "human-a", "type": "human"},
                {"id": "human-b", "type": "human"},
                {"id": "model-c", "type": "model"},
            ],
        }

    def records(self, responses):
        result = {}
        for response in responses:
            identifier = response["reviewer"]["id"]
            raw = self.export.encode_review(response)
            result[identifier] = (
                {
                    "path": str(Path("C:/supplied-review-data") / (identifier + ".json")),
                    "sha256": sha(raw),
                },
                raw,
            )
        return result

    def test_validator_matches_unchanged_legacy_schema_and_preserves_long_judgments(self):
        packet = self.packet()
        valid = self.response(packet)
        item = valid["items"][0]
        item["rationale"] = "Long literal rationale Ω. " * 1024
        item["uncertain_pairs"] = [{"left": "a", "right": "b", "rationale": "Uncertain."}]
        for kind in ("human", "model"):
            valid["reviewer"]["type"] = kind
            before = copy.deepcopy(valid)
            self.assertIsNone(self.legacy.validate_submission(packet, valid))
            self.assertIsNone(self.api.validate_review_submission(packet, valid))
            self.assertEqual(valid, before)
        mutations = (
            lambda row: row.update(pack_sha256="0" * 64),
            lambda row: row.update(extra="unknown schema field"),
            lambda row: row["reviewer"].update(type="unknown"),
            lambda row: row["reviewer"].update(prior_exposure=""),
            lambda row: row["items"].pop(),
            lambda row: row["items"].append(copy.deepcopy(row["items"][0])),
            lambda row: row["items"][0].update(id="foreign"),
            lambda row: row["items"][0].update(groups=None),
            lambda row: row["items"][0].update(groups=[["a", "b"]]),
            lambda row: row["items"][0].update(groups=[["a", "b", "c"], ["a"]]),
            lambda row: row["items"][0].update(groups=[["a", "b", "foreign"]]),
            lambda row: row["items"][0]["answers"].pop(),
            lambda row: row["items"][0]["answers"].append(
                copy.deepcopy(row["items"][0]["answers"][0])
            ),
            lambda row: row["items"][0]["answers"][0].update(compliance="good"),
            lambda row: row["items"][0]["answers"][0].update(compliance_rationale=""),
            lambda row: row["items"][0].update(rationale=""),
            lambda row: row["items"][0]["uncertain_pairs"].append(
                {"left": "b", "right": "a", "rationale": "Reversed duplicate."}
            ),
            lambda row: row["items"][0].update(
                uncertain_pairs=[{"left": "a", "right": "a", "rationale": "Self pair."}]
            ),
        )
        for index, mutate in enumerate(mutations):
            changed = copy.deepcopy(valid)
            mutate(changed)
            with self.subTest(mutation=index):
                with self.assertRaises(ValueError):
                    self.legacy.validate_submission(packet, changed)
                with self.assertRaises(ValueError):
                    self.api.validate_review_submission(packet, changed)

    def test_pure_summary_separates_coverage_partition_disagreement_and_uncertainty(self):
        materialization = self.pure_materialization()
        round_record = self.round_record(materialization)
        responses = [
            self.response(materialization["packet"], row["id"], row["type"])
            for row in round_record["reviewers"]
        ]
        responses[0]["items"][0]["groups"] = [["a", "b"], ["c"]]
        responses[1]["items"][0]["groups"] = [["c"], ["b", "a"]]
        responses[2]["items"][0]["groups"] = [["b", "a"], ["c"]]
        same = self.api._summarize(materialization, round_record, self.records(responses))
        self.assertEqual(same["status"], "complete")
        self.assertEqual(same["reasons"], [])
        self.assertFalse(same["items"][0]["partition_disagreement"])
        self.assertEqual(same["items"][0]["compliance_disagreements"], [])
        self.assertEqual(
            same["coverage"]["reviewers"],
            {
                "planned": 3,
                "valid": 3,
                "missing": 0,
                "invalid": 0,
                "human": {"planned": 2, "valid": 2, "missing": 0, "invalid": 0},
                "model": {"planned": 1, "valid": 1, "missing": 0, "invalid": 0},
            },
        )
        responses[2]["items"][0]["groups"] = [["a"], ["b"], ["c"]]
        responses[2]["items"][0]["answers"][1]["compliance"] = "violates"
        responses[2]["items"][0]["uncertain_pairs"] = [
            {"left": "a", "right": "b", "rationale": "Central-content boundary remains uncertain."}
        ]
        disagree = self.api._summarize(materialization, round_record, self.records(responses))
        self.assertEqual(disagree["status"], "complete")
        self.assertTrue(disagree["items"][0]["partition_disagreement"])
        self.assertEqual(disagree["items"][0]["compliance_disagreements"], ["b"])
        item_reviews = {row["reviewer_id"]: row for row in disagree["items"][0]["reviews"]}
        for response in responses:
            actual = item_reviews[response["reviewer"]["id"]]
            for field in ("groups", "uncertain_pairs", "rationale", "answers"):
                self.assertEqual(actual[field], response["items"][0][field])
        records = self.records(responses)
        del records["human-b"]
        ref, _ = records["human-a"]
        malformed = b'{"format":"one","format":"duplicate"}'
        records["human-a"] = ref | {"sha256": sha(malformed)}, malformed
        partial = self.api._summarize(materialization, round_record, records)
        self.assertEqual(partial["status"], "incomplete")
        self.assertEqual(set(partial["reasons"]), {"missing_reviews", "invalid_reviews"})
        self.assertEqual(
            partial["coverage"]["reviewers"],
            {
                "planned": 3,
                "valid": 1,
                "missing": 1,
                "invalid": 1,
                "human": {"planned": 2, "valid": 0, "missing": 1, "invalid": 1},
                "model": {"planned": 1, "valid": 1, "missing": 0, "invalid": 0},
            },
        )
        by_id = {row["reviewer"]["id"]: row for row in partial["reviews"]}
        self.assertEqual(by_id["human-a"]["reason"], "invalid_submission")
        self.assertIsNone(by_id["human-a"]["response"])
        self.assertEqual(by_id["human-b"]["status"], "missing")
        self.assertIsNone(by_id["human-b"]["submission"])
        self.assertIsNone(partial["items"][0]["partition_disagreement"])
        for field in ("plan_sha256", "report_sha256", "packet_sha256"):
            with self.subTest(round_binding=field), self.assertRaises(ReleaseError):
                self.api._summarize(
                    materialization, round_record | {field: "f" * 64}, self.records(responses)
                )
        for roster in ([], [round_record["reviewers"][0]] * 2):
            with self.subTest(roster=roster), self.assertRaises(ReleaseError):
                self.api._summarize(materialization, round_record | {"reviewers": roster}, {})
        unknown = self.records(responses)
        unknown["undeclared-reviewer"] = unknown["human-a"]
        with self.assertRaises(ReleaseError):
            self.api._summarize(materialization, round_record, unknown)
        for field, value in (("id", "another-human"), ("type", "model")):
            changed = copy.deepcopy(responses[0])
            changed["reviewer"][field] = value
            raw = self.export.encode_review(changed)
            records = self.records(responses)
            ref, _ = records["human-a"]
            records["human-a"] = ref | {"sha256": sha(raw)}, raw
            mismatch = self.api._summarize(materialization, round_record, records)
            review = next(row for row in mismatch["reviews"] if row["reviewer"]["id"] == "human-a")
            self.assertEqual(review["status"], "invalid")
            self.assertEqual(review["reason"], "invalid_submission")
        # Collection completeness does not turn model reviews into humans.
        model_only = self.api._summarize(
            materialization,
            round_record | {"reviewers": [round_record["reviewers"][2]]},
            self.records([responses[2]]),
        )
        self.assertEqual(model_only["status"], "complete")
        self.assertEqual(model_only["coverage"]["reviewers"]["human"]["valid"], 0)
        mixed = copy.deepcopy(materialization)
        mixed["private"]["status"] = "incomplete"
        mixed["private"]["coverage"].update(
            planned_sets=2, unavailable_sets=1, planned_positions=6, unavailable_positions=3
        )
        mixed_result = self.api._summarize(mixed, round_record, self.records(responses))
        self.assertEqual(mixed_result["status"], "incomplete")
        self.assertEqual(mixed_result["reasons"], ["source_sample_unavailable"])
        self.assertEqual(mixed_result["coverage"]["reviewers"]["valid"], 3)
        self.assertEqual(mixed_result["coverage"]["source"], mixed["private"]["coverage"])
        unavailable = copy.deepcopy(materialization)
        unavailable.update(packet=None, template=None, review=None)
        unavailable["private"].update(status="incomplete", packet_sha256=None)
        unavailable["private"]["coverage"].update(
            available_sets=0, unavailable_sets=1, available_positions=0, unavailable_positions=3
        )
        no_packet_round = round_record | {"packet_sha256": None}
        no_packet = self.api._summarize(unavailable, no_packet_round, self.records(responses))
        self.assertEqual(no_packet["status"], "incomplete")
        self.assertIn("source_sample_unavailable", no_packet["reasons"])
        self.assertEqual(no_packet["coverage"]["source"], unavailable["private"]["coverage"])
        self.assertEqual(no_packet["items"], [])
        self.assertTrue(all(row["reason"] == "no_available_packet" for row in no_packet["reviews"]))

    def test_genuine_original_final_import_is_passive_and_checks_late_consumed_bytes(self):
        import test_final_evaluation
        import test_source_review

        from buddha.authorization import Authorization
        from buddha.trial_fence import _scope_text, _TrialScope

        cohort = test_final_evaluation.FinalEvaluationTests("runTest")
        cohort.setUp()
        self.addCleanup(cohort.doCleanups)
        cohort.fixture()
        cohort.definition["final_ids"] = ["final-a"]
        # This small cohort prospectively assigns only one final task. The
        # unused source task is honestly development/exposed before preparation;
        # no assigned final member is later omitted from the sealed schedule.
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
        controls.append(reference(Path(self.api.__file__).absolute()))
        cohort.f.custody["evidence"].extend(controls)
        cohort.f.record["custody"] = reference(cohort.f.write("custody.json", cohort.f.custody))
        cohort.f.declaration = cohort.f.write("declaration.json", cohort.f.record)
        cohort.definition["validation"] = reference(cohort.f.declaration)
        cohort.declaration = cohort.f.write("review-results-trial.json", cohort.definition)
        identity = sha(_json(cohort.definition))
        cohort.authorities = {
            phase: Authorization.create(
                cohort.f.root / ("review-results-" + phase + ".sqlite3"),
                authorization_id="supplied-review-results-" + phase,
                scope=_scope_text(_TrialScope(cohort.root, identity, phase)),
                **limits,
            )
            for phase, limits in cohort.definition["phase_limits"].items()
        }
        cohort.prepare()
        cohort.freeze(cohort.validate())
        with cohort.offline():
            self.assertEqual(cohort.run_final()["status"], "complete")
        with exporter.passive():
            materialization = exporter.materialize(cohort.root, plan)
        round_record = self.round_record(materialization)
        round_plan = cohort.f.root / "review-round.json"
        round_plan.write_bytes(_json(round_record))
        round_sha = sha(round_plan.read_bytes())
        # The round is fixed before these separately retained responses exist.
        responses = [
            self.response(materialization["packet"], row["id"], row["type"])
            for row in round_record["reviewers"]
        ]
        submissions = []
        for response in responses:
            path = cohort.f.root / (response["reviewer"]["id"] + "-valid.json")
            path.write_bytes(self.export.encode_review(response))
            submissions.append({"reviewer_id": response["reviewer"]["id"], **reference(path)})
        invalid_path = cohort.f.root / "human-a-invalid.json"
        invalid_path.write_bytes(b'{"format":"incomplete supplied response"}')
        invalid_ref = {"reviewer_id": "human-a", **reference(invalid_path)}

        def inspect(refs):
            return self.api.inspect_source_reviews(
                cohort.root,
                kind="final",
                expected_report_sha256=sha((cohort.root / "final/report.json").read_bytes()),
                plan=plan,
                expected_plan_sha256=sha(plan.read_bytes()),
                round_plan=round_plan,
                expected_round_plan_sha256=round_sha,
                submissions=refs,
            )

        before = files(cohort.f.root), cohort.engine.physical_sends, cohort.engine.workers
        with exporter.passive():
            partial = inspect([invalid_ref, submissions[2]])
            complete = inspect(submissions)
        self.assertEqual(partial["status"], "incomplete")
        self.assertEqual(set(partial["reasons"]), {"missing_reviews", "invalid_reviews"})
        self.assertEqual(complete["status"], "complete")
        self.assertEqual(complete["format"], "buddha.source-review-report.v1")
        self.assertEqual(complete["round_plan"], reference(round_plan))
        self.assertEqual(complete["source"], materialization["private"])
        self.assertEqual(complete["coverage"]["source"], materialization["private"]["coverage"])
        self.assertEqual(
            (files(cohort.f.root), cohort.engine.physical_sends, cohort.engine.workers), before
        )

        self.assertEqual({row["status"] for row in complete["reviews"]}, {"valid"})
        self.assertEqual(len(complete["items"]), 1)
        for row in complete["reviews"]:
            self.assertEqual(
                row["response"],
                responses[
                    [r["id"] for r in round_record["reviewers"]].index(row["reviewer"]["id"])
                ],
            )
        selected = Path(materialization["private"]["sets"][0]["binding"]["answers_path"])
        original_summary = self.api._summarize
        for target in (selected, round_plan, Path(submissions[0]["path"])):
            raw = target.read_bytes()
            changed = []

            def after_reads(*args, target=target, raw=raw, changed=changed, **kwargs):
                result = original_summary(*args, **kwargs)
                # The complete source, round and submission have all been read.
                # Equal-length changed bytes must still fail at public finish.
                replacement = bytes([raw[0] ^ 1]) + raw[1:]
                self.assertEqual(len(raw), len(replacement))
                target.write_bytes(replacement)
                changed.append(True)
                return result

            try:
                with (
                    self.subTest(late_input=target.name),
                    exporter.passive(forbid_writes=False),
                    patch.object(self.api, "_summarize", side_effect=after_reads),
                    self.assertRaises(ReleaseError),
                ):
                    inspect(submissions)
                self.assertEqual(changed, [True])
            finally:
                target.write_bytes(raw)
        self.assertEqual(
            (files(cohort.f.root), cohort.engine.physical_sends, cohort.engine.workers), before
        )

    def test_duplicate_submission_id_path_or_hash_refuses_before_source_reconstruction(self):
        # The real tests directory supplies existing plain parents on every OS;
        # these placeholder files are never read or created.
        root = Path(__file__).resolve().parent
        first = {
            "reviewer_id": "human-a",
            "path": str(root / "supplied-first-review.json"),
            "sha256": "a" * 64,
        }
        second = {
            "reviewer_id": "human-b",
            "path": str(root / "supplied-second-review.json"),
            "sha256": "b" * 64,
        }
        arguments = {
            "kind": "final",
            "expected_report_sha256": "c" * 64,
            "plan": root / "supplied-plan.json",
            "expected_plan_sha256": "d" * 64,
            "round_plan": root / "supplied-round.json",
            "expected_round_plan_sha256": "e" * 64,
        }
        for duplicate in (
            second | {"reviewer_id": first["reviewer_id"]},
            second | {"path": first["path"]},
            second | {"sha256": first["sha256"]},
        ):
            with (
                self.subTest(duplicate=duplicate),
                patch.object(
                    self.export, "_read_source_review", side_effect=AssertionError("must not read")
                ) as read,
                self.assertRaisesRegex(ReleaseError, "duplicate"),
            ):
                self.api.inspect_source_reviews(
                    root / "supplied-trial", submissions=[first, duplicate], **arguments
                )
            read.assert_not_called()
        for changed in (
            {"round_plan": Path("relative-round.json"), "submissions": []},
            {"round_plan": root / ".." / "supplied-round.json", "submissions": []},
            {"submissions": [{"reviewer_id": object()}]},
        ):
            with (
                self.subTest(boundary=changed),
                patch.object(
                    self.export, "_read_source_review", side_effect=AssertionError("must not read")
                ) as read,
                self.assertRaises(ReleaseError),
            ):
                self.api.inspect_source_reviews(root / "supplied-trial", **(arguments | changed))
            read.assert_not_called()


if __name__ == "__main__":
    unittest.main()
