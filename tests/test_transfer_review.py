"""The transfer review bridge keeps its source phase explicit at every entry."""

import copy
import io
import json
import tempfile
import unittest
from contextlib import contextmanager, redirect_stderr, redirect_stdout
from pathlib import Path
from unittest.mock import patch


class TransferReviewTests(unittest.TestCase):
    def test_review_commands_forward_explicit_transfer_kind_and_status(self):
        from buddha import source_review_handoff
        from buddha.__main__ import main

        common = [
            "--run",
            "original",
            "--kind",
            "transfer",
            "--report-sha256",
            "a" * 64,
            "--plan",
            "plan.json",
            "--plan-sha256",
            "b" * 64,
            "--out",
            "review-output",
        ]
        values = {
            "kind": "transfer",
            "expected_report_sha256": "a" * 64,
            "plan": Path("plan.json"),
            "expected_plan_sha256": "b" * 64,
            "output": Path("review-output"),
        }
        for command, function, extra, arguments, status, code in (
            (
                "source-review-export",
                "export_source_review",
                ["--reviewer", "reviewer-a", "human"],
                {"reviewers": [{"id": "reviewer-a", "type": "human"}]},
                "complete",
                0,
            ),
            (
                "source-review-inspect",
                "collect_source_reviews",
                [
                    "--round-plan",
                    "round.json",
                    "--round-plan-sha256",
                    "c" * 64,
                    "--submission",
                    "reviewer-a",
                    "forms/a.json",
                    "d" * 64,
                ],
                {
                    "round_plan": Path("round.json"),
                    "expected_round_plan_sha256": "c" * 64,
                    "submissions": [
                        {
                            "reviewer_id": "reviewer-a",
                            "path": str(Path("forms/a.json").absolute()),
                            "sha256": "d" * 64,
                        }
                    ],
                },
                "incomplete",
                3,
            ),
        ):
            summary = {
                "format": "buddha.source-review-"
                + ("export" if command.endswith("export") else "collection")
                + ".v1",
                "status": status,
            }
            with (
                self.subTest(command=command),
                patch.object(source_review_handoff, function, return_value=summary) as handoff,
                patch("buddha.__main__._key_environment") as keys,
                patch("http.client.HTTPSConnection") as connection,
                redirect_stdout(io.StringIO()) as output,
                redirect_stderr(io.StringIO()),
            ):
                self.assertEqual(main([command, *common, *extra]), code)
                self.assertEqual(json.loads(output.getvalue()), summary)
                handoff.assert_called_once_with(Path("original"), **values, **arguments)
                keys.assert_not_called()
                connection.assert_not_called()

    def fixture(self, *, complete=True):
        import test_source_review
        import test_source_review_results
        import test_transfer_evaluation

        from buddha import source_review, source_review_handoff, source_review_results
        from buddha.authorization import Authorization
        from buddha.trial_fence import _scope_text, _TrialScope

        self.api, self.handoff, self.results = (
            source_review,
            source_review_handoff,
            source_review_results,
        )
        self.helper = test_source_review.SourceReviewTests("runTest")
        self.helper.setUp()
        self.addCleanup(self.helper.doCleanups)
        self.forms = test_source_review_results.SourceReviewResultsTests("runTest")
        self.forms.setUp()
        self.trial = test_transfer_evaluation.TransferEvaluationTests("runTest")
        self.addCleanup(self.trial.doCleanups)
        c = self.c = self.trial.fixture()
        self.json, self.reference, self.sha, self.files = (
            c.json,
            test_source_review.reference,
            test_source_review.sha,
            test_source_review.files,
        )
        self.texts = ["  Complete café tale: opening\nconflict, resolution and final Ω. 🐕  ", ""]
        c.engine.weak_answers = self.texts
        self.plans = {}
        helper_controls = [
            self.reference(Path(module.__file__).absolute())
            for module in (self.handoff, self.results)
        ]
        for kind, tasks, custody in (
            ("final", c.f.tasks, c.f.custody),
            ("transfer", self.trial.transfer_tasks, self.trial.transfer_custody),
        ):
            plan, controls = self.helper.controls(
                c.f.root,
                kind=kind,
                experiment=c.definition["experiment_id"],
                tasks=tasks,
                roles=("comparator", "candidate"),
                task_ids=("final-a",),
                name=kind + "-review",
            )
            self.plans[kind] = plan
            custody["evidence"].extend(controls + helper_controls)
        wrong_materials = json.loads(self.plans["transfer"].read_bytes())
        wrong_materials["materials"] = json.loads(self.plans["final"].read_bytes())["materials"]
        self.wrong_materials_plan = c.f.write(
            "transfer-with-final-materials-plan.json", wrong_materials
        )
        self.trial.transfer_custody["evidence"].append(self.reference(self.wrong_materials_plan))
        c.f.record["custody"] = self.reference(c.f.write("custody.json", c.f.custody))
        c.f.declaration = c.f.write("declaration.json", c.f.record)
        c.definition["validation"] = self.reference(c.f.declaration)
        c.definition["transfer"]["custody"] = self.reference(
            c.f.write("transfer-custody.json", self.trial.transfer_custody)
        )
        c.declaration.write_bytes(self.json(c.definition))
        # Both review samples/materials and all four review helpers precede the
        # actual trial. Earlier unused fixture grants stay at their own paths.
        self.unused_grants = list(c.authorities.values()) + list(self.trial.legacy_grants.values())
        identity = self.sha(self.json(c.definition))
        c.authorities = {
            phase: Authorization.create(
                c.f.root / ("transfer-review-" + phase + ".sqlite3"),
                authorization_id="synthetic-transfer-review-" + phase,
                scope=_scope_text(_TrialScope(c.root, identity, phase, version=2)),
                **limits,
            )
            for phase, limits in c.definition["phase_limits"].items()
        }
        if complete:
            c.prepare()
            c.freeze(c.validate())
            with c.offline():
                self.assertEqual(c.run_final()["status"], "complete")
                self.assertEqual(self.trial.run_transfer()["status"], "complete")
        return c

    def common(self, kind="transfer"):
        return {
            "directory": self.c.root,
            "kind": kind,
            "expected_report_sha256": self.sha((self.c.root / kind / "report.json").read_bytes()),
            "plan": self.plans[kind],
            "expected_plan_sha256": self.sha(self.plans[kind].read_bytes()),
        }

    @contextmanager
    def passive(self, *, writes=False):
        # Saved database bytes may be inspected in memory. No on-disk SQL,
        # active authority/session/worker/provider or credential path is allowed.
        # Patch the real Gateway initializer before the trial guard replaces
        # its class; the reverse order tries to patch Mock.__init__.
        with self.helper.passive(forbid_writes=not writes), self.trial.passive():
            yield

    def command(self, command, common, output, *, reviewers=(), submissions=(), round_plan=None):
        from buddha.__main__ import main

        argv = [
            command,
            "--run",
            str(common["directory"]),
            "--kind",
            common["kind"],
            "--report-sha256",
            common["expected_report_sha256"],
            "--plan",
            str(common["plan"]),
            "--plan-sha256",
            common["expected_plan_sha256"],
            "--out",
            str(output),
        ]
        if command == "source-review-export":
            for reviewer in reviewers:
                argv.extend(["--reviewer", reviewer["id"], reviewer["type"]])
        else:
            argv.extend(
                [
                    "--round-plan",
                    str(round_plan),
                    "--round-plan-sha256",
                    self.sha(round_plan.read_bytes()),
                ]
            )
            for ref in submissions:
                argv.extend(["--submission", ref["reviewer_id"], ref["path"], ref["sha256"]])
        with redirect_stdout(io.StringIO()) as terminal, redirect_stderr(io.StringIO()):
            code = main(argv)
        summary = json.loads(terminal.getvalue())
        self.assertEqual(code, 0 if summary["status"] == "complete" else 3)
        self.assertNotIn("reviews", summary)
        self.assertNotIn(self.texts[0], terminal.getvalue())
        return summary

    def test_genuine_transfer_review_keeps_phase_literal_sets_and_surviving_publication_capture(
        self,
    ):
        c = self.fixture()
        common = self.common()
        before = self.files(c.f.root)
        funds = {phase: grant.summary() for phase, grant in c.authorities.items()}
        counts = c.engine.workers, c.engine.physical_sends
        with self.passive():
            material = self.api.materialize_source_review(**common)
            self.helper.assert_legacy_coverage(material)
        private, packet = material["private"], material["packet"]
        self.assertEqual((private["kind"], private["status"]), ("transfer", "complete"))
        self.assertEqual(private["report_sha256"], common["expected_report_sha256"])
        self.assertEqual(private["plan_sha256"], common["expected_plan_sha256"])
        self.assertEqual(
            private["coverage"],
            dict(
                planned_sets=2,
                available_sets=2,
                unavailable_sets=0,
                planned_positions=4,
                available_positions=4,
                unavailable_positions=0,
            ),
        )
        self.assertEqual({row["role"] for row in private["sets"]}, {"comparator", "candidate"})
        self.assertEqual(len({row["id"] for row in private["sets"]}), 2)
        self.assertEqual(set(packet), {"format", "rule", "items"})
        items = {item["id"]: item for item in packet["items"]}
        for row in private["sets"]:
            self.assertEqual(row["task_id"], "final-a")
            self.assertTrue(
                Path(row["binding"]["answers_path"]).is_relative_to(c.root / "transfer")
            )
            self.assertEqual(items[row["id"]]["prompt"], self.trial.transfer_tasks.tasks[0].prompt)
            self.assertNotEqual(
                items[row["id"]]["prompt"], c.f.tasks.select(["final-a"]).tasks[0].prompt
            )
            answers = {answer["id"]: answer["text"] for answer in items[row["id"]]["answers"]}
            for answer in row["answers"]:
                self.assertEqual(answers[answer["id"]], self.texts[answer["position"]])
                self.assertEqual(
                    answer["text_utf8_sha256"], self.sha(self.texts[answer["position"]].encode())
                )
        task_ref = c.definition["transfer"]["tasks"]
        self.assertEqual(
            private["provenance"]["consumed_files"][task_ref["path"]], task_ref["sha256"]
        )
        self.assertNotEqual(self.trial.transfer_tasks.release_sha256, c.f.tasks.release_sha256)

        with tempfile.TemporaryDirectory() as temporary:
            base = Path(temporary).resolve()
            roster = [{"id": "human-a", "type": "human"}, {"id": "model-b", "type": "model"}]
            exported = base / "transfer-export"
            with self.passive(writes=True):
                summary = self.command("source-review-export", common, exported, reviewers=roster)
                final_export = self.handoff.export_source_review(
                    **self.common("final"), output=base / "final-export", reviewers=roster
                )
            self.assertEqual(
                (exported / "reviewer/pack.json").read_bytes(), self.api.encode_review(packet)
            )
            self.assertEqual(
                json.loads((exported / "private/materialization.json").read_bytes()), private
            )
            round_plan = Path(summary["round_plan"]["path"])
            final_round = Path(final_export["round_plan"]["path"])
            final_packet = json.loads((base / "final-export/reviewer/pack.json").read_bytes())
            self.assertNotEqual(
                self.sha(self.api.encode_review(packet)),
                self.sha(self.api.encode_review(final_packet)),
            )
            incoming = base / "forms"
            incoming.mkdir()
            refs, responses = [], []
            for reviewer in roster:
                response = self.forms.response(packet, reviewer["id"], reviewer["type"])
                if reviewer["type"] == "model":
                    for item in response["items"]:
                        item["groups"] = [[answer["id"]] for answer in item["answers"]]
                        item["answers"][0]["compliance"] = "violates"
                path = incoming / (reviewer["id"] + ".json")
                path.write_bytes(self.api.encode_review(response))
                responses.append(response)
                refs.append({"reviewer_id": reviewer["id"], **self.reference(path)})
            wrong_form = incoming / "model-b-original-final-form.json"
            wrong_form.write_bytes(
                self.api.encode_review(self.forms.response(final_packet, "model-b", "model"))
            )
            invalid_ref = {"reviewer_id": "model-b", **self.reference(wrong_form)}
            forms_before = self.files(incoming)
            exports_before = self.files(exported), self.files(base / "final-export")
            arguments = common | {
                "round_plan": round_plan,
                "expected_round_plan_sha256": self.sha(round_plan.read_bytes()),
            }
            with self.passive():
                imported = self.results.inspect_source_reviews(**arguments, submissions=refs)
            self.assertEqual(imported["source"]["kind"], "transfer")
            self.assertEqual(imported["status"], "complete")
            self.assertEqual([row["response"] for row in imported["reviews"]], responses)
            for label, submissions, status in (
                ("missing", refs[:1], "incomplete"),
                ("wrong-phase-form", [refs[0], invalid_ref], "incomplete"),
                ("valid", refs, "complete"),
            ):
                output = base / ("collection-" + label)
                with self.passive(writes=True):
                    collected = self.command(
                        "source-review-inspect",
                        common,
                        output,
                        submissions=submissions,
                        round_plan=round_plan,
                    )
                report = json.loads((output / "report.json").read_bytes())
                marker = json.loads((output / "complete.json").read_bytes())
                self.assertEqual(
                    (collected["status"], collected["publication_status"]), (status, "complete")
                )
                self.assertEqual(
                    marker["artifacts"],
                    {"report.json": self.sha((output / "report.json").read_bytes())},
                )
                self.assertEqual(report["source"]["kind"], "transfer")
                self.assertEqual(
                    report["source"]["report_sha256"], common["expected_report_sha256"]
                )
                coverage = report["coverage"]["reviewers"]
                self.assertEqual(coverage["human"]["valid"], 1)
                if label == "missing":
                    self.assertEqual(report["reasons"], ["missing_reviews"])
                    self.assertEqual(coverage["model"]["missing"], 1)
                elif label == "wrong-phase-form":
                    self.assertEqual(report["reasons"], ["invalid_reviews"])
                    self.assertEqual(coverage["model"]["invalid"], 1)
                    self.assertEqual(report["reviews"][1]["submission"], self.reference(wrong_form))
                    self.assertIsNone(report["reviews"][1]["response"])
                else:
                    self.assertEqual(report["reviews"], imported["reviews"])
                    self.assertTrue(all(item["partition_disagreement"] for item in report["items"]))
                    self.assertTrue(
                        all(item["compliance_disagreements"] for item in report["items"])
                    )

            wrong_plan = common | {
                "plan": self.plans["final"],
                "expected_plan_sha256": self.sha(self.plans["final"].read_bytes()),
            }
            wrong_materials = common | {
                "plan": self.wrong_materials_plan,
                "expected_plan_sha256": self.sha(self.wrong_materials_plan.read_bytes()),
            }
            wrong_report = common | {
                "expected_report_sha256": self.common("final")["expected_report_sha256"]
            }
            for index, bad in enumerate((wrong_plan, wrong_materials, wrong_report)):
                output = base / ("refused-export-" + str(index))
                with self.passive(writes=True), self.assertRaises(self.api.SourceReviewError):
                    self.handoff.export_source_review(**bad, output=output, reviewers=roster)
                self.assertFalse(output.exists())
            output = base / "refused-final-round"
            with self.passive(writes=True), self.assertRaises(self.api.SourceReviewError):
                self.handoff.collect_source_reviews(
                    **common,
                    round_plan=final_round,
                    expected_round_plan_sha256=self.sha(final_round.read_bytes()),
                    submissions=refs,
                    output=output,
                )
            self.assertFalse(output.exists())

            selected = Path(private["sets"][0]["binding"]["answers_path"])
            custody = Path(c.definition["transfer"]["custody"]["path"])
            wal = c.authorities["transfer"].path.with_name(
                c.authorities["transfer"].path.name + "-wal"
            )
            for index, (stage, target) in enumerate(
                (("export", selected), ("export", custody), ("collection", wal))
            ):
                original = target.read_bytes() if target.exists() else None
                output = base / ("late-" + str(index))
                publish, changed = self.handoff._publish, []

                def change_after_prefix(
                    path, raw, target=target, original=original, changed=changed, publish=publish
                ):
                    publish(path, raw)
                    if path.name in {"materialization.json", "report.json"} and not changed:
                        target.write_bytes(
                            b"late WAL"
                            if original is None
                            else bytes([original[0] ^ 1]) + original[1:]
                        )
                        changed.append(True)

                try:
                    with (
                        self.subTest(late=stage + ":" + target.name),
                        self.passive(writes=True),
                        patch.object(self.handoff, "_publish", side_effect=change_after_prefix),
                        self.assertRaises(self.api.SourceReviewError),
                    ):
                        if stage == "export":
                            self.handoff.export_source_review(
                                **common, output=output, reviewers=roster
                            )
                        else:
                            self.handoff.collect_source_reviews(
                                **arguments, submissions=refs, output=output
                            )
                    self.assertEqual(changed, [True])
                    self.assertFalse((output / "complete.json").exists())
                    self.assertTrue(
                        (
                            output
                            / (
                                "private/materialization.json"
                                if stage == "export"
                                else "report.json"
                            )
                        ).is_file()
                    )
                finally:
                    if original is None:
                        target.unlink(missing_ok=True)
                    else:
                        target.write_bytes(original)
            self.assertEqual(self.files(incoming), forms_before)
            self.assertEqual(
                (self.files(exported), self.files(base / "final-export")), exports_before
            )
        self.assertEqual(self.files(c.f.root), before)
        self.assertEqual({phase: grant.summary() for phase, grant in c.authorities.items()}, funds)
        self.assertEqual((c.engine.workers, c.engine.physical_sends), counts)
        self.assertTrue(
            all(grant.summary()["operation_count"] == 0 for grant in self.unused_grants)
        )

    def test_transfer_selector_and_materials_reject_primary_source_despite_same_raw_id(self):
        # This cheap contract check makes no owner or custody claim. The full
        # public flow above proves those boundaries with actual original owners.
        c = self.fixture(complete=False)
        state = {
            "definition": c.definition,
            "tasks": self.trial.transfer_tasks,
            "comparators": [{}],
        }
        schedule = {"repetitions": 1, "selected_ids": ["final-a"]}
        plan = json.loads(self.plans["transfer"].read_bytes())
        self.assertEqual(self.api._selectors(plan, state, schedule, "transfer"), plan["sets"])
        for field, value in (("kind", "final"), ("tasks_sha256", c.f.tasks.fingerprint())):
            wrong = copy.deepcopy(plan)
            wrong[field] = value
            with self.subTest(field=field), self.assertRaises(self.api.SourceReviewError):
                self.api._selectors(wrong, state, schedule, "transfer")
        for role, index in (("candidate", 1), ("starter", 0)):
            wrong = copy.deepcopy(plan)
            wrong["sets"][0].update(role=role, role_index=index)
            with (
                self.subTest(role=role, index=index),
                self.assertRaises(self.api.SourceReviewError),
            ):
                self.api._selectors(wrong, state, schedule, "transfer")
        final_materials = json.loads(self.plans["final"].read_bytes())["materials"]
        protocol = Path(plan["protocol"]["path"]).read_bytes()
        with self.assertRaises(ValueError):
            self.api._materials(
                Path(final_materials["path"]).read_bytes(),
                final_materials["sha256"],
                protocol,
                plan["protocol"]["sha256"],
                self.trial.transfer_tasks.to_record()["release"],
            )
        self.assertFalse(c.root.exists())

    def test_passive_guards_compose_and_still_refuse_active_io_and_writes(self):
        import http.client
        import sqlite3

        import test_source_review
        import test_transfer_evaluation

        from buddha import authorization, candidate_run, executor, gateway, native_run

        # No trial fixture or owner is needed to exercise the guard composition.
        self.helper = test_source_review.SourceReviewTests("runTest")
        self.helper.setUp()
        self.addCleanup(self.helper.doCleanups)
        self.trial = test_transfer_evaluation.TransferEvaluationTests("runTest")
        self.addCleanup(self.trial.doCleanups)
        with tempfile.TemporaryDirectory() as temporary:
            forbidden = Path(temporary).resolve() / "must-not-exist"
            with self.passive():
                for label, action in (
                    ("gateway", lambda: gateway.Gateway(forbidden, transport=None)),
                    ("authority", lambda: authorization.Authorization(forbidden)),
                    ("candidate-session", candidate_run.CandidateSession),
                    ("native-session", native_run.NativeSession),
                    ("worker", lambda: executor.run_container(None)),
                    ("provider", lambda: http.client.HTTPSConnection("forbidden.invalid")),
                    ("file-sql", lambda: sqlite3.connect(forbidden)),
                    ("write-bytes", lambda: forbidden.write_bytes(b"forbidden")),
                    ("write-open", lambda: forbidden.open("wb")),
                    ("mkdir", forbidden.mkdir),
                ):
                    with self.subTest(boundary=label), self.assertRaises(AssertionError):
                        action()
                connection = sqlite3.connect(":memory:")
                try:
                    self.assertEqual(connection.execute("SELECT 1").fetchone(), (1,))
                finally:
                    connection.close()
            self.assertFalse(forbidden.exists())


if __name__ == "__main__":
    unittest.main()
