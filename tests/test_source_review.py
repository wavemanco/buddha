"""Current full C1 reaches the legacy review schema under original custody.

Fixtures use genuine owners, seals, accounting and supplied worker replies.
No selected Python is imported or executed on the host; no provider is contacted.
"""

import copy
import hashlib
import os
import unittest
from contextlib import ExitStack, contextmanager
from pathlib import Path
from unittest.mock import patch

from buddha.releases import _json


def sha(raw):
    return hashlib.sha256(raw).hexdigest()


def reference(path):
    return {"path": str(path), "sha256": sha(path.read_bytes())}


def files(root):
    return {
        str(path.relative_to(root)): sha(path.read_bytes())
        for path in root.rglob("*")
        if path.is_file()
    }


class SourceReviewTests(unittest.TestCase):
    def setUp(self):
        import test_meas01_pack

        from buddha import source_review

        self.api = source_review
        self.legacy = test_meas01_pack

    @contextmanager
    def passive(self, *, forbid_writes=True):
        with ExitStack() as stack:
            stack.enter_context(patch.dict(os.environ, {}, clear=True))
            for target in (
                "buddha.gateway.Gateway.__init__",
                "buddha.authorization.Authorization.__init__",
                "buddha.candidate_run.CandidateSession",
                "buddha.native_run.NativeSession",
                "buddha.executor.run_container",
                "http.client.HTTPSConnection",
            ):
                stack.enter_context(patch(target, side_effect=AssertionError("active review I/O")))
            if forbid_writes:
                stack.enter_context(self.legacy.readonly())
            yield

    def controls(self, root, *, kind, experiment, tasks, roles, task_ids, name="source-review"):
        from buddha import policy_panel

        rule = (
            "Equivalent responses add no new central content; "
            "different central content is distinct."
        )
        rubric = "Assess literal task compliance and useful development; retain uncertainty."
        prefix = "Review protocol for synthetic supplied data.\n"
        protocol = root / (name + "-protocol.txt")
        protocol.write_bytes((prefix + rubric + "\nEnd.\n").encode())
        materials = root / (name + "-materials.json")
        release = tasks.to_record()["release"]
        materials.write_bytes(
            _json(
                {
                    "format": "buddha.policy-panel-review.v1",
                    "release_sha256": sha(_json(release)),
                    "protocol_sha256": sha(protocol.read_bytes()),
                    "rule": {
                        "text": rule,
                        "sha256": sha(rule.encode()),
                        "upstream_revision": release["upstream"]["revision"],
                    },
                    "rubric": {
                        "text": rubric,
                        "protocol_start": len(prefix.encode()),
                        "protocol_end": len((prefix + rubric).encode()),
                    },
                }
            )
        )
        plan = root / (name + "-plan.json")
        plan.write_bytes(
            _json(
                {
                    "format": "buddha.source-review-plan.v1",
                    "experiment_id": experiment,
                    "kind": kind,
                    "tasks_sha256": tasks.fingerprint(),
                    "seed": 7,
                    "protocol": reference(protocol),
                    "materials": reference(materials),
                    "sets": [
                        {"role": role, "role_index": 0, "task_id": task_id, "repetition": 0}
                        for role in roles
                        for task_id in task_ids
                    ],
                }
            )
        )
        module = Path(self.api.__file__).absolute()
        helper = Path(policy_panel.__file__).absolute()
        return plan, [reference(path) for path in (plan, protocol, materials, module, helper)]

    def materialize(self, directory, plan, kind="final"):
        return self.api.materialize_source_review(
            directory,
            kind=kind,
            expected_report_sha256=sha((directory / "final/report.json").read_bytes()),
            plan=plan,
            expected_plan_sha256=sha(plan.read_bytes()),
        )

    def assert_legacy_coverage(self, result):
        packet, template, private = (result[key] for key in ("packet", "template", "private"))
        self.assertEqual(set(result), {"packet", "template", "private", "review"})
        self.assertEqual(set(packet), {"format", "rule", "items"})
        encoded = self.legacy.namespace["encode"](packet)
        self.assertEqual(self.api.encode_review(packet), encoded)
        self.assertEqual(template["pack_sha256"], sha(encoded))
        self.assertEqual(private["packet_sha256"], sha(encoded))
        self.assertEqual(private["template_sha256"], sha(self.api.encode_review(template)))
        self.assertEqual(private["review_sha256"], sha(result["review"].encode()))
        self.assertEqual(template["reviewer"], {"id": "", "type": "", "prior_exposure": ""})
        self.assertEqual(
            [row["id"] for row in packet["items"]], sorted(row["id"] for row in packet["items"])
        )
        for item in packet["items"]:
            self.assertEqual(set(item), {"id", "prompt", "answers"})
            self.assertEqual(
                [row["id"] for row in item["answers"]], sorted(row["id"] for row in item["answers"])
            )
            self.assertTrue(all(set(row) == {"id", "text"} for row in item["answers"]))
        # A blank template is not an independent judgment or complete submission.
        with self.assertRaises(ValueError):
            self.legacy.validate_submission(packet, template)
        completed = copy.deepcopy(template)
        completed["reviewer"] = {
            "id": "supplied-schema-check-only",
            "type": "model",
            "prior_exposure": "synthetic fixture; this is not an independent review",
        }
        for item in completed["items"]:
            self.assertIsNone(item["groups"])
            item["groups"] = [[answer["id"]] for answer in item["answers"]]
            item["rationale"] = "Supplied structural check, not adjudication."
            for answer in item["answers"]:
                answer["compliance"] = "uncertain"
                answer["compliance_rationale"] = "No independent assessment supplied."
        self.legacy.validate_submission(packet, completed)
        missing = copy.deepcopy(completed)
        missing["items"][0]["answers"].pop()
        with self.assertRaises(ValueError):
            self.legacy.validate_submission(packet, missing)
        duplicate = copy.deepcopy(completed)
        duplicate["items"][0]["groups"].append(duplicate["items"][0]["groups"][0])
        with self.assertRaises(ValueError):
            self.legacy.validate_submission(packet, duplicate)

    def test_current_final_c1_exports_whole_literal_sets_under_original_custody(self):
        import test_final_evaluation

        from buddha.authorization import Authorization
        from buddha.trial_fence import _scope_text, _TrialScope

        h = test_final_evaluation.FinalEvaluationTests("runTest")
        h.setUp()
        self.addCleanup(h.doCleanups)
        h.fixture()
        texts = ["  Complete café tale: opening\nconflict and ending. 🐕  ", ""]
        h.engine.weak_answers = texts
        plan, controls = self.controls(
            h.f.root,
            kind="final",
            experiment=h.definition["experiment_id"],
            tasks=h.f.tasks,
            roles=("comparator", "candidate"),
            task_ids=("final-a", "final-b"),
        )
        h.f.custody["evidence"].extend(controls)
        h.f.record["custody"] = reference(h.f.write("custody.json", h.f.custody))
        h.f.declaration = h.f.write("declaration.json", h.f.record)
        h.definition["validation"] = reference(h.f.declaration)
        h.declaration = h.f.write("review-trial-declaration.json", h.definition)
        # Fresh original authorizations match this pre-prepare definition. The
        # fixture's earlier unused authorities are left untouched, not rebound.
        identity = sha(_json(h.definition))
        h.authorities = {
            phase: Authorization.create(
                h.f.root / ("review-trial-" + phase + ".sqlite3"),
                authorization_id="supplied-review-trial-" + phase,
                scope=_scope_text(_TrialScope(h.root, identity, phase)),
                **limits,
            )
            for phase, limits in h.definition["phase_limits"].items()
        }
        h.prepare()
        h.freeze(h.validate())
        with h.offline():
            report = h.run_final()
        self.assertEqual(report["status"], "complete")
        before = files(h.f.root), h.engine.physical_sends, h.engine.workers
        with self.passive():
            result = self.materialize(h.root, plan)
            replay = self.materialize(h.root, plan)
            self.assert_legacy_coverage(result)
        self.assertEqual(result, replay)
        self.assertEqual((files(h.f.root), h.engine.physical_sends, h.engine.workers), before)
        private = result["private"]
        self.assertEqual(private["status"], "complete")
        self.assertEqual(
            private["coverage"],
            dict(
                planned_sets=4,
                available_sets=4,
                unavailable_sets=0,
                planned_positions=8,
                available_positions=8,
                unavailable_positions=0,
            ),
        )
        self.assertEqual({row["role"] for row in private["sets"]}, {"comparator", "candidate"})
        self.assertEqual(len({row["id"] for row in private["sets"]}), 4)
        public = {item["id"]: item for item in result["packet"]["items"]}
        for row in private["sets"]:
            self.assertEqual(row["state"], "available")
            self.assertIsNone(row["reason"])
            self.assertEqual(row["arm_index"], {"comparator": 0, "candidate": 1}[row["role"]])
            answers = {answer["id"]: answer["text"] for answer in public[row["id"]]["answers"]}
            self.assertEqual(len(answers), 2)
            self.assertEqual(sorted(answers.values()), sorted(texts))
            for answer in row["answers"]:
                self.assertEqual(answers[answer["id"]], texts[answer["position"]])
                self.assertEqual(
                    answer["text_utf8_sha256"], sha(texts[answer["position"]].encode())
                )
            self.assertIn(row["binding"]["answers_path"], private["provenance"]["consumed_files"])
        # Post-hoc aliases with identical plan bytes are not original controls.
        alias = h.f.root / "unapproved-review-plan.json"
        alias.write_bytes(plan.read_bytes())
        try:
            with self.passive(), self.assertRaises(self.api.SourceReviewError):
                self.materialize(h.root, alias)
        finally:
            alias.unlink()
        self.assert_late_refusals(h, plan, result)
        self.assertEqual((files(h.f.root), h.engine.physical_sends, h.engine.workers), before)

    def assert_late_refusals(self, h, plan, result):
        original = h.module._read_final_evaluation
        selected = Path(result["private"]["sets"][0]["binding"]["answers_path"])
        for kind in ("selected-c1-bytes", "validation-sibling-wal", "validation-sibling-tree"):
            changed, cleanup = [], []

            def after_inner(*args, kind=kind, cleanup=cleanup, changed=changed, **kwargs):
                observation = original(*args, **kwargs)
                reader = observation[3]
                if kind == "selected-c1-bytes":
                    raw = selected.read_bytes()
                    replacement = raw.replace(b"Complete", b"complete", 1)
                    self.assertNotEqual(raw, replacement)
                    self.assertEqual(len(raw), len(replacement))
                    selected.write_bytes(replacement)
                    cleanup.append(lambda: selected.write_bytes(raw))
                elif kind == "validation-sibling-wal":
                    databases = sorted(
                        path
                        for path in reader.capture.databases
                        if path.is_relative_to(h.root / "validation")
                    )
                    self.assertTrue(databases, "genuine validation sibling ledger must be retained")
                    sidecar = databases[0].with_name(databases[0].name + "-wal")
                    self.assertFalse(sidecar.exists())
                    sidecar.write_bytes(b"supplied late unstable sidecar")
                    cleanup.append(sidecar.unlink)
                else:
                    extra = h.root / "validation/study/late-unapproved-tree-entry.txt"
                    self.assertFalse(extra.exists())
                    extra.write_bytes(b"late sibling tree addition")
                    cleanup.append(extra.unlink)
                changed.append(True)
                return observation

            try:
                with (
                    self.subTest(late_change=kind),
                    self.passive(forbid_writes=False),
                    patch.object(h.module, "_read_final_evaluation", side_effect=after_inner),
                    self.assertRaises(self.api.SourceReviewError),
                ):
                    self.materialize(h.root, plan)
                self.assertEqual(changed, [True])
            finally:
                for restore in reversed(cleanup):
                    restore()

    def test_complete_improver_null_slots_preserve_unavailable_logical_sets(self):
        import test_improver_assessment

        h = test_improver_assessment.ImproverAssessmentTests("runTest")
        h.setUp()
        self.addCleanup(h.doCleanups)
        h.fixture()
        plan, controls = self.controls(
            h.root,
            kind="improver",
            experiment=h.definition["experiment_id"],
            tasks=h.f.h.source,
            roles=("starter", "initial", "evolved"),
            task_ids=(1, "final"),
        )
        # Both panels are explicit original controls, before any trial owner.
        # The second declares only null descendant roles; it is not a changed
        # sample chosen after seeing the outcome.
        unavailable_plan, unavailable_controls = self.controls(
            h.root,
            kind="improver",
            experiment=h.definition["experiment_id"],
            tasks=h.f.h.source,
            roles=("initial", "evolved"),
            task_ids=(1, "final"),
            name="source-review-unavailable",
        )
        known = {row["path"] for row in controls}
        controls.extend(row for row in unavailable_controls if row["path"] not in known)
        h.custody["evidence"].extend(controls)
        h.custody_ref = h.write("review-assessment-custody.json", h.custody)
        h.definition["custody"] = h.custody_ref
        h.population = h.numerical_population([1, "final"])
        h.plan["population_sha256"] = sha(_json(h.population))
        h.definition["analysis_plan"] = h.write("review-assessment-analysis.json", h.plan)
        h.bind("review-assessment")
        h.f.outcomes.update({(0, 0, arm, 0): "rejected" for arm in range(2)})
        h.prepare()
        h.develop()
        schedule = h.freeze()
        self.assertEqual([row["role"] for row in schedule["arms"]], ["starter"])
        with h.supplied():
            report = h.run_assessment()
        self.assertEqual(report["status"], "complete")
        before = files(h.root), h.engine.physical_sends, h.engine.workers
        with self.passive():
            result = self.materialize(h.trial, plan, "improver")
            self.assert_legacy_coverage(result)
            unavailable = self.materialize(h.trial, unavailable_plan, "improver")
        self.assertEqual((files(h.root), h.engine.physical_sends, h.engine.workers), before)
        private = result["private"]
        self.assertEqual(private["status"], "incomplete")
        self.assertEqual(private["reason"], "selected_descendants_unavailable")
        self.assertEqual(
            private["coverage"],
            dict(
                planned_sets=6,
                available_sets=2,
                unavailable_sets=4,
                planned_positions=12,
                available_positions=4,
                unavailable_positions=8,
            ),
        )
        self.assertEqual(len(private["sets"]), 6)
        public = {item["id"]: item for item in result["packet"]["items"]}
        for row in private["sets"]:
            self.assertEqual(row["role_index"], 0)
            self.assertEqual(row["repetition"], 0)
            self.assertEqual(type(row["task_id"]), int if row["task_id"] == 1 else str)
            if row["role"] == "starter":
                self.assertEqual(row["state"], "available")
                self.assertEqual(row["arm_index"], 0)
                self.assertIsNone(row["reason"])
                expected = ["1", "2"] if row["task_id"] == 1 else ["sealed first", "sealed second"]
                self.assertEqual(
                    sorted(answer["text"] for answer in public[row["id"]]["answers"]),
                    sorted(expected),
                )
            else:
                self.assertEqual(row["state"], "unavailable")
                self.assertEqual(row["reason"], "no_valid_descendant")
                self.assertIsNone(row["arm_index"])
                self.assertIsNone(row["binding"])
                self.assertNotIn(row["id"], public)
                self.assertTrue(
                    all(answer["text_utf8_sha256"] is None for answer in row["answers"])
                )
        self.assertIsNone(unavailable["packet"])
        self.assertIsNone(unavailable["template"])
        self.assertIsNone(unavailable["review"])
        missing = unavailable["private"]
        self.assertEqual(missing["status"], "incomplete")
        self.assertEqual(missing["reason"], "no_selected_answer_sets_available")
        self.assertEqual(
            missing["coverage"],
            dict(
                planned_sets=4,
                available_sets=0,
                unavailable_sets=4,
                planned_positions=8,
                available_positions=0,
                unavailable_positions=8,
            ),
        )
        self.assertEqual(len(missing["sets"]), 4)
        self.assertEqual({row["role"] for row in missing["sets"]}, {"initial", "evolved"})
        for row in missing["sets"]:
            self.assertIsNone(row["arm_index"])
            self.assertEqual(row["reason"], "no_valid_descendant")
            self.assertIsNone(row["binding"])
            self.assertEqual(len(row["answers"]), 2)
        for key in ("packet_sha256", "template_sha256", "review_sha256"):
            self.assertIsNone(missing[key])

    def test_selector_boundaries_keep_whole_sets_typed_tasks_and_declared_limits(self):
        import test_answers

        from buddha.answers import TaskSet
        from buddha.releases import ReleaseError

        # The existing release fixture is pure data construction: no setup,
        # files, original owners, SQL, workers or provider requests are needed.
        dataset = b"".join(
            _json({"id": identifier, "prompt": "Supplied typed task."}) + b"\n"
            for identifier in (1, "1")
        )
        fixture = test_answers.AnswerArtifactTests("runTest")
        tasks = TaskSet.from_dataset(fixture.make_release(dataset), dataset)
        state = {
            "definition": {"experiment_id": "pure-selector-boundaries", "finalist_count": 1},
            "tasks": tasks,
            "comparators": [{}],
        }
        schedule = {"selected_ids": [1], "repetitions": 1}
        selector = {"role": "candidate", "role_index": 0, "task_id": 1, "repetition": 0}
        plan = {
            "format": "buddha.source-review-plan.v1",
            "experiment_id": state["definition"]["experiment_id"],
            "kind": "final",
            "tasks_sha256": tasks.fingerprint(),
            "seed": 0,
            "sets": [selector],
        }
        invalid = []
        duplicate = copy.deepcopy(plan)
        duplicate["sets"].append(copy.deepcopy(selector))
        invalid.append(("duplicate-whole-coordinates", duplicate))
        for field, values in (
            ("role", ("starter", "unknown")),
            ("role_index", (True, 0.0, -1, 1)),
            ("repetition", (False, 0.0, -1, 1)),
            ("task_id", (True, "1", "not-in-source")),
        ):
            for value in values:
                changed = copy.deepcopy(plan)
                changed["sets"][0][field] = value
                invalid.append((f"{field}={value!r}", changed))
        for field, values in (
            ("format", ("unknown",)),
            ("seed", (True, 0.0, -1)),
            ("kind", ("improver",)),
            ("experiment_id", ("another-experiment",)),
            ("tasks_sha256", ("0" * 64,)),
            ("sets", ([],)),
        ):
            for value in values:
                changed = copy.deepcopy(plan)
                changed[field] = value
                invalid.append((f"{field}={value!r}", changed))
        partial = copy.deepcopy(plan)
        partial["sets"][0]["position"] = 0
        invalid.append(("position-selection-is-not-a-whole-set", partial))
        with self.passive():
            self.assertEqual(self.api._selectors(plan, state, schedule, "final"), [selector])
            for name, changed in invalid:
                with self.subTest(boundary=name), self.assertRaises(ReleaseError):
                    self.api._selectors(changed, state, schedule, "final")
            # Two different logical roles remain valid even for the same task;
            # every position of both full answer sets counts toward the cap.
            two_sets = copy.deepcopy(plan)
            two_sets["sets"].append(selector | {"role": "comparator"})
            positions = 2 * tasks.tasks[0].count
            with patch.object(self.api, "MAX_PANEL_POSITIONS", positions):
                self.assertEqual(len(self.api._selectors(two_sets, state, schedule, "final")), 2)
            with (
                patch.object(self.api, "MAX_PANEL_POSITIONS", positions - 1),
                self.assertRaises(ReleaseError),
            ):
                self.api._selectors(two_sets, state, schedule, "final")
            # Logical improver coordinates span starts * development repeats;
            # they are not the compressed physical sealed-arm indexes.
            improver = copy.deepcopy(plan)
            improver["kind"] = "improver"
            improver["sets"][0].update(role="evolved", role_index=3)
            improver_state = state | {"screens": [{}, {}], "development": {"repetitions": 2}}
            self.assertEqual(
                self.api._selectors(improver, improver_state, schedule, "improver"),
                improver["sets"],
            )
            improver["sets"][0]["role_index"] = 4
            with self.assertRaises(ReleaseError):
                self.api._selectors(improver, improver_state, schedule, "improver")


if __name__ == "__main__":
    unittest.main()
