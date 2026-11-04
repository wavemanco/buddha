"""A full prospective final grid uses real owners and simulated execution only."""

import copy
import hashlib
import json
import os
import unittest
from contextlib import contextmanager
from fractions import Fraction
from pathlib import Path
from unittest.mock import patch


def sha(raw):
    return hashlib.sha256(raw).hexdigest()


def files(root):
    return {
        path.relative_to(root).as_posix(): path.read_bytes()
        for path in root.rglob("*")
        if path.is_file()
    }


class FinalEvaluationTests(unittest.TestCase):
    def setUp(self):
        # The initial missing-interface RED precedes fixture files, SQL or workers.
        from buddha import final_evaluation

        self.module = final_evaluation
        self.Error = final_evaluation.FinalEvaluationError

    def fixture(self):
        import test_validation_analysis
        import test_validation_study

        from buddha.answers import TaskSet
        from buddha.authorization import Authorization
        from buddha.improvement_rule import ImprovementRule
        from buddha.releases import Release, _json, inventory, prepare_selection
        from buddha.trial_fence import _scope_text, _TrialScope

        self.json = _json
        self.f = f = test_validation_study.ValidationStudyTests("runTest")
        f.setUp()
        self.addCleanup(f.doCleanups)
        e = self.engine = f.engine
        self.root = f.root / "trial"
        rows = [
            {"id": 1, "prompt": "Synthetic validation task."},
            {"id": "1", "prompt": "Synthetic development task."},
            {"id": "final-a", "prompt": "FIRST FINAL-ONLY SENTINEL"},
            {"id": "final-b", "prompt": "SECOND FINAL-ONLY SENTINEL"},
        ]
        data = b"".join(_json(row) + b"\n" for row in rows)
        official = e.fixture.roots["official"]
        (official / "data/tasks.jsonl").write_bytes(data)
        e.fixture.release_record["source"] = inventory(official)
        release = Release.from_record(e.fixture.release_record)
        f.tasks = TaskSet.from_dataset(release, data)
        e.candidate.release = release
        e.candidate.tasks = f.tasks.select([1])
        e.candidate.task_path.write_bytes(e.candidate.tasks.to_bytes())
        e.fixture.selection = prepare_selection(
            release,
            e.fixture.roots,
            capabilities={"openai.chat-completions.v1": "profiles/openai.json"},
        )
        native_roots = {key: Path(value) for key, value in e.native["roots"].items()}
        e.native["selection"] = prepare_selection(
            release,
            native_roots,
            capabilities={"openai.chat-completions.v1": "profiles/openai.json"},
        ).to_record()
        f.record["tasks"] = f.reference(f.write("all-tasks.json", f.tasks.to_record()))
        f.record["generation"]["selection"] = e.fixture.selection.to_record()
        f.record["native"] = copy.deepcopy(e.native)
        f.record["repetitions"] = 1
        f.custody["population"] = [
            {
                "task_id": task.id,
                "task_sha256": sha(_json(task.to_record())),
                "family_id": "family-" + str(index),
                "source": "synthetic",
                "task_type": "fixture",
                "phase": "validation" if index == 0 else "development" if index == 1 else "final",
                "exposure": "exposed" if index == 1 else "eligible",
            }
            for index, task in enumerate(f.tasks.tasks)
        ]
        f.record["custody"] = f.reference(f.write("custody.json", f.custody))
        analysis = test_validation_analysis.ValidationAnalysisTests("runTest")
        analysis.setUp()
        plan = analysis.plan_record(
            projection_release_sha256=release.fingerprint(),
            max_looks=1,
            max_candidates=1,
            comparator_count=1,
            repetitions=1,
            finalist_count=1,
            improvement_rule_sha256=ImprovementRule.from_bytes(_json(f.rule)).fingerprint(),
        )
        f.record["analysis_plan"] = f.reference(f.write("analysis-plan.json", plan))
        f.declaration = f.write("declaration.json", f.record)
        self.definition = {
            "format": "buddha.evaluation-trial.v1",
            "experiment_id": "synthetic-full-final-grid",
            "validation": f.reference(f.declaration),
            "final_ids": ["final-a", "final-b"],
            "finalist_count": 1,
            "finalist_policy": {
                "method": "explicit_ordered_finalists",
                "eligible_pool": "complete-original-validation-candidates",
            },
            "search_purpose": "synthetic unused development allowance",
            "phase_limits": {
                phase: {"budget_microusd": 1_000_000, "max_calls": 1000}
                for phase in ("search", "validation", "final")
            },
            "consumer_sources": self.module._source_hashes(),
        }
        self.declaration = f.write("trial-declaration.json", self.definition)
        identity = sha(_json(self.definition))
        self.authorities = {
            phase: Authorization.create(
                f.root / ("trial-" + phase + ".sqlite3"),
                authorization_id="synthetic-trial-" + phase,
                budget_microusd=1_000_000,
                max_calls=1000,
                scope=_scope_text(_TrialScope(self.root, identity, phase)),
            )
            for phase in ("search", "validation", "final")
        }
        self.events = []
        e.native_row = lambda row, index: (
            row
            | (
                {"distinct": 2}
                if index == 0
                else {
                    "distinct": 2,
                    "generation_scores": [7, 7],
                    "partition_scores": [7, 7],
                    "utility": 7.0,
                }
            )
        )
        return self

    def prepare(self, **changes):
        return self.module.prepare_evaluation_trial(
            self.root,
            **(
                {
                    "declaration": self.declaration,
                    "expected_sha256": sha(self.declaration.read_bytes()),
                    "expected_runtime_sha256": self.engine.candidate.expected_runtime,
                    "authorizations": self.authorities,
                }
                | changes
            ),
        )

    def execute(self, spec, *, initial, handle, **kwargs):
        from buddha.releases import Selection

        e, f = self.engine, self.f
        session = handle.__self__
        if spec.role == "agent":
            task = session.tasks.tasks[0]
            self.assertEqual(initial["task"], f.tasks.select([task.id]).tasks[0].to_record())
            self.assertNotIn(b"dataset_base64", self.json(initial))
            self.events.append(("generation", task.id, str(session.gateway.directory)))
            e.candidate.tasks = session.tasks
            manifest = json.loads((session.gateway.directory / "manifest.json").read_bytes())
            e.fixture.selection = Selection.from_bytes(self.json(manifest["selection"]))
            e.directory = session.output.parents[2]
        else:
            self.events.append(
                ("native", initial["command"]["index"], str(session.gateway.directory))
            )
            e.directory = session.gateway.directory.parents[2] / "generation"
        return e.execute(spec, initial=initial, handle=handle, **kwargs)

    @contextmanager
    def offline(self):
        import test_gateway

        with (
            patch.dict(os.environ, {"OPENAI_API_KEY": test_gateway.KEY}, clear=True),
            patch("buddha.executor.run_container", side_effect=self.execute),
            patch(
                "http.client.HTTPSConnection", side_effect=AssertionError("real HTTPS forbidden")
            ),
        ):
            yield

    def validate(self):

        f = self.f
        f.directory = self.root / "validation/study"
        with self.offline():
            result = f.run_occasion(self.authorities["validation"])
        self.assertEqual(result["status"], "complete")
        return [
            {
                "ordinal": 0,
                "result_sha256": sha((f.directory / "validation/0/result.json").read_bytes()),
            }
        ]

    def freeze(self, results, **changes):
        return self.module.freeze_finalists(
            self.root,
            **(
                {
                    "finalist_refs": [self.f.source_ref],
                    "validation_results": results,
                    "review": self.engine.fixture.review,
                }
                | changes
            ),
        )

    def run_final(self):
        from buddha.gateway import RawHTTPTransport

        return self.module.run_final_evaluation(
            self.root,
            authorization=self.authorities["final"],
            review=self.engine.fixture.review,
            transport=RawHTTPTransport(allow_paid=True),
        )

    def test_full_grid_has_every_final_task_and_original_owner_then_passive_replay(self):
        self.fixture().prepare()
        validation = self.validate()
        self.freeze(validation)
        self.events.clear()
        with self.offline():
            result = self.run_final()
        self.assertEqual(result["status"], "complete")
        self.assertEqual(result["selected_ids"], ["final-a", "final-b"])
        self.assertEqual(result["coverage"], {"expected": 4, "generated": 4, "evaluated": 4})
        generated = [(task, owner) for role, task, owner in self.events if role == "generation"]
        self.assertEqual([task for task, _ in generated], ["final-a", "final-b"] * 2)
        self.assertEqual(len({owner for _, owner in generated}), 4)
        pins = {
            path: sha(path.read_bytes())
            for path in (
                self.root / ".buddha-evaluation-trial.json",
                self.root / "definition.json",
                self.root / "funding.json",
                self.root / "freeze/schedule.json",
                self.root / "freeze/ready.json",
            )
        }
        owners = list((self.root / "final").rglob("manifest.json"))
        self.assertEqual(len(owners), 16)
        for owner in owners:
            manifest = json.loads(owner.read_bytes())
            inputs = {row["path"]: row["sha256"] for row in manifest["invocation"]["inputs"]}
            self.assertTrue(all(inputs[str(path)] == digest for path, digest in pins.items()))
            self.assertEqual(manifest["authorization_path"], str(self.authorities["final"].path))
        before = files(self.f.root)
        with (
            patch.dict(os.environ, {}, clear=True),
            patch("buddha.executor.run_container", side_effect=AssertionError("passive worker")),
            patch("buddha.gateway.Gateway", side_effect=AssertionError("passive gateway")),
        ):
            replay = self.module.inspect_final_evaluation(
                self.root,
                expected_report_sha256=sha((self.root / "final/report.json").read_bytes()),
            )
        self.assertEqual(replay, result)
        self.assertEqual(files(self.f.root), before)
        self.assertEqual(self.authorities["final"].summary()["reserved_microusd"], 0)

    def test_omitted_final_member_and_changed_original_definition_refuse_before_use(self):
        self.fixture()
        self.definition["final_ids"] = ["final-a"]
        self.declaration.write_bytes(self.json(self.definition))
        before = {phase: grant.summary() for phase, grant in self.authorities.items()}
        with self.assertRaises(self.Error):
            self.prepare()
        self.assertFalse(self.root.exists())
        self.assertEqual(
            {phase: grant.summary() for phase, grant in self.authorities.items()}, before
        )

    def test_final_direct_preparation_and_copied_ready_never_enable_public_gateway(self):
        from buddha.gateway import prepare_gateway

        self.fixture().prepare()
        f = self.engine.fixture
        for fake in (False, True):
            with self.subTest(fake_ready=fake):
                if fake:
                    (self.root / "freeze").mkdir()
                    (self.root / "freeze/ready.json").write_bytes(b'{"ready":true}')
                destination = self.root / "final/foreign"
                before = files(self.f.root)
                with self.assertRaises(ValueError):
                    prepare_gateway(
                        destination,
                        selection=f.selection,
                        roots=f.roots,
                        authorization=self.authorities["final"],
                        budget_microusd=10000,
                        max_calls=20,
                        input_files=[self.declaration],
                        review=f.review,
                    )
                self.assertFalse(destination.exists())
                self.assertEqual(files(self.f.root), before)

    def test_freeze_confirmation_failure_is_irreversible_and_never_reselected(self):
        self.fixture().prepare()
        validation = self.validate()
        original = self.module.pipeline._write

        def fail_ready(path, raw):
            if path.name == "ready.json":
                raise OSError("synthetic confirmation failure")
            return original(path, raw)

        with patch.object(self.module.pipeline, "_write", side_effect=fail_ready):
            with self.assertRaises(self.Error):
                self.freeze(validation)
        self.assertTrue((self.root / "freeze").is_dir())
        self.assertTrue((self.root / "freeze/schedule.json").is_file())
        self.assertFalse((self.root / "freeze/ready.json").exists())
        before = files(self.f.root)
        with self.assertRaises(self.Error):
            self.freeze(validation)
        with self.assertRaises(self.Error):
            self.run_final()
        self.assertEqual(files(self.f.root), before)
        self.assertEqual(self.authorities["final"].summary()["operation_count"], 0)

    def test_interrupted_native_keeps_original_owner_and_resumes_exact_full_grid(self):
        self.fixture().prepare()
        self.freeze(self.validate())
        original = self.execute
        stopped = []

        def interrupt(spec, **kwargs):
            if spec.role != "agent" and not stopped:
                stopped.append(True)
                raise KeyboardInterrupt
            return original(spec, **kwargs)

        with self.offline(), patch("buddha.executor.run_container", side_effect=interrupt):
            with self.assertRaises(KeyboardInterrupt):
                self.run_final()
        manifests = {
            path: path.read_bytes() for path in (self.root / "final").rglob("manifest.json")
        }
        self.assertEqual(len(manifests), 2)
        with self.offline():
            result = self.run_final()
        self.assertEqual(result["status"], "complete")
        self.assertTrue(all(path.read_bytes() == raw for path, raw in manifests.items()))
        self.assertEqual(result["coverage"]["evaluated"], 4)
        self.assertEqual(self.authorities["final"].summary()["reserved_microusd"], 0)

    def test_freeze_rejects_foreign_finalist_without_spending_or_consuming_freeze(self):
        self.fixture().prepare()
        validation = self.validate()
        unknown = self.f.root / "unmeasured.py"
        unknown.write_bytes(b"# Not an original validation candidate.\n")
        before = files(self.f.root)
        with self.assertRaises(self.Error):
            self.freeze(validation, finalist_refs=[self.f.reference(unknown)])
        self.assertEqual(files(self.f.root), before)
        self.assertFalse((self.root / "freeze").exists())
        self.assertEqual(self.authorities["final"].summary()["operation_count"], 0)

    def test_original_owners_resume_at_each_durable_publication_boundary(self):
        for boundary in ("generation_return", "native_return", "final_publication"):
            with self.subTest(boundary=boundary):
                self.fixture().prepare()
                self.freeze(self.validate())
                stopped = []
                if boundary == "generation_return":
                    owner = self.module.candidate_generation
                    name = "run_candidate_generation"
                elif boundary == "native_return":
                    owner = self.module.native_evaluation
                    name = "run_evaluation"
                else:
                    owner, name = self.module, "_result"
                original = getattr(owner, name)

                def interrupt_once(
                    *args, boundary=boundary, stopped=stopped, original=original, **kwargs
                ):
                    if boundary == "final_publication" and not stopped:
                        self.assertEqual(
                            len(list((self.root / "final").rglob("manifest.json"))), 16
                        )
                        stopped.append(True)
                        raise KeyboardInterrupt
                    result = original(*args, **kwargs)
                    if not stopped:
                        self.assertEqual(result["status"], "complete")
                        stopped.append(True)
                        raise KeyboardInterrupt
                    return result

                with (
                    self.offline(),
                    patch.object(owner, name, side_effect=interrupt_once),
                    self.assertRaises(KeyboardInterrupt),
                ):
                    self.run_final()
                self.assertTrue(stopped)
                self.assertFalse((self.root / "final/report.json").exists())
                # Every retained owner is complete at these exact injection points.
                # Their original manifests/ledgers/seals/publications must survive.
                immutable = {
                    path: path.read_bytes()
                    for path in (self.root / "final").rglob("*")
                    if path.is_file()
                    and (
                        path.name in {"manifest.json", "operations.sqlite3", "report.json"}
                        or path.parent.name == "completed"
                    )
                }
                original_owners = {
                    str(path.parent) for path in immutable if path.name == "manifest.json"
                }
                journal = files(self.root / "final/observations")
                self.assertTrue(
                    any(json.loads(raw)["reason"] == "cancelled" for raw in journal.values())
                )
                self.events.clear()
                with self.offline():
                    result = self.run_final()
                self.assertEqual(result["status"], "complete")
                self.assertEqual(
                    result["coverage"], {"expected": 4, "generated": 4, "evaluated": 4}
                )
                self.assertTrue(all(path.read_bytes() == raw for path, raw in immutable.items()))
                self.assertTrue(all(owner not in original_owners for _, _, owner in self.events))
                self.assertEqual(files(self.root / "final/observations"), journal)
                self.assertEqual(self.authorities["final"].summary()["reserved_microusd"], 0)
                if boundary == "final_publication":
                    self.assertEqual(self.events, [], "all original cells already completed")

    def test_every_later_orphan_is_refused_before_earlier_preparation_or_mutation(self):
        for arm, role in ((1, "generation"), (1, "evaluation"), (2, "generation")):
            with self.subTest(arm=arm, role=role):
                self.fixture().prepare()
                self.freeze(self.validate())
                orphan = self.root / "final/arms" / str(arm) / "tasks/1/repetitions/0" / role
                orphan.mkdir(parents=True)
                before = files(self.f.root)
                funding = self.authorities["final"].summary()
                with patch.object(
                    self.module.candidate_generation,
                    "prepare_candidate_generation",
                    side_effect=self.Error("earlier preparation sentinel"),
                ) as prepare:
                    with self.assertRaises(self.Error):
                        self.run_final()
                prepare.assert_not_called()
                self.assertTrue(orphan.is_dir())
                self.assertEqual(files(self.f.root), before)
                self.assertEqual(self.authorities["final"].summary(), funding)

    def test_both_arms_missing_the_same_final_task_refuse_before_contrast_kernel(self):
        self.fixture().prepare()
        self.freeze(self.validate())
        with self.offline():
            self.assertEqual(self.run_final()["status"], "complete")
        state = self.module._state(self.root)
        occasion, pins = self.module._schedule(state)
        reader, current = self.module._census(state, occasion, pins)
        original = self.module.study._cells

        def omit_last_task(*args, **kwargs):
            for row in original(*args, **kwargs):
                if row[2] != "final-b":
                    yield row

        # Remaining task_index=0 is contiguous in both arms. A kernel that infers
        # its universe from observed rows alone could otherwise call this complete.
        before = files(self.f.root)
        with (
            patch.object(self.module.study, "_cells", side_effect=omit_last_task),
            patch.object(self.module.analysis, "_aggregate_contrast") as kernel,
            self.assertRaises(self.Error),
        ):
            self.module._analysis(state, occasion, reader, current)
        kernel.assert_not_called()
        reader.capture.finish()
        self.assertEqual(files(self.f.root), before)

    def test_genuine_confirmed_freeze_and_exact_pins_do_not_enable_direct_gateway(self):
        from buddha.gateway import prepare_gateway

        self.fixture().prepare()
        self.freeze(self.validate())
        state = self.module._state(self.root)
        occasion, pins = self.module._schedule(state)
        arm = occasion["arms"][0]
        cell = self.module.study._location(state, occasion, 0, 0, 0)
        generation, selected, controls = self.module.study._materialize(
            state, occasion, arm, occasion["selected_ids"][0], cell, receipts=pins
        )
        destination = cell / "generation/owners/0"
        before = files(self.f.root)
        funding = self.authorities["final"].summary()
        with self.assertRaises(ValueError):
            prepare_gateway(
                destination,
                selection=selected,
                roots={key: Path(value) for key, value in generation["roots"].items()},
                authorization=self.authorities["final"],
                budget_microusd=generation["budget_microusd"],
                max_calls=generation["max_calls"],
                input_files=list(controls),
                expected_input_hashes=controls,
                review=occasion["review"],
            )
        self.assertFalse(destination.exists())
        self.assertEqual(files(self.f.root), before)
        self.assertEqual(self.authorities["final"].summary(), funding)

    def test_missing_required_native_scalar_keeps_full_grid_final_tail_and_inconclusive_rule(self):
        self.fixture().prepare()
        self.freeze(self.validate())
        original = self.engine.native_row

        def missing_utility(row, stage):
            value = original(row, stage)
            location = self.engine.directory.relative_to(self.root / "final")
            if stage == 1 and location.parts[:4] == ("arms", "1", "tasks", "0"):
                value["utility"] = float("nan")
            return value

        plan = json.loads(Path(self.f.record["analysis_plan"]["path"]).read_bytes())
        allocation = plan["alpha"]["final"]
        tail = Fraction(allocation["numerator"], allocation["denominator"]) / (
            2 * plan["finalist_count"] * plan["comparator_count"]
        )
        expected_tail = {"numerator": tail.numerator, "denominator": tail.denominator}
        self.engine.native_row = missing_utility
        with self.offline():
            result = self.run_final()
        self.assertEqual(result["status"], "complete")
        self.assertEqual(result["coverage"]["evaluated"], 4)
        self.assertEqual(len(result["analysis"]["matrix"]), 4)
        self.assertEqual(
            {row["task_id"] for row in result["analysis"]["matrix"]}, {"final-a", "final-b"}
        )
        contrast = result["analysis"]["contrasts"][0]
        self.assertEqual(contrast["rule"]["status"], "inconclusive")
        self.assertIsNone(contrast["axes"]["utility"]["lower_bound"])
        self.assertEqual(contrast["axes"]["utility"]["reason"], "required_native_scalar_missing")
        self.assertEqual(contrast["axes"]["utility"]["tail"], expected_tail)
        self.assertEqual(contrast["axes"]["distinct"]["tail"], expected_tail)

    def test_cancel_after_checked_failed_generation_preserves_both_facts_and_original_owner(self):
        self.fixture().prepare()
        self.freeze(self.validate())
        original = self.module.candidate_generation.run_candidate_generation
        stopped = []
        workers = self.engine.workers
        sends = self.engine.physical_sends

        def cancel_after_failure(*args, **kwargs):
            result = original(*args, **kwargs)
            self.assertEqual(result["status"], "complete")
            self.assertEqual(result["disposition"], "candidate_execution_failed")
            stopped.append(result)
            raise KeyboardInterrupt

        # Existing public lower producer validates and publishes this actual
        # failure frame; no final report or generation result is fabricated.
        with (
            self.offline(),
            patch("buddha.executor.run_container", side_effect=self.f.failed_generation_worker),
            patch.object(
                self.module.candidate_generation,
                "run_candidate_generation",
                side_effect=cancel_after_failure,
            ),
            patch.object(
                self.module.native_evaluation,
                "prepare_evaluation",
                side_effect=AssertionError("checked failed generation reached native"),
            ) as native,
            self.assertRaises(KeyboardInterrupt),
        ):
            self.run_final()
        native.assert_not_called()
        self.assertEqual(len(stopped), 1)
        self.assertEqual(self.engine.workers - workers, 1)
        self.assertEqual(self.engine.physical_sends, sends)
        final = self.root / "final"
        manifests = list(final.rglob("manifest.json"))
        self.assertEqual(len(manifests), 1)
        generation = final / "arms/0/tasks/0/repetitions/0/generation"
        self.assertEqual(
            json.loads((generation / "report.json").read_bytes())["disposition"],
            "candidate_execution_failed",
        )
        first_path = final / "observations/0.json"
        first_raw = first_path.read_bytes()
        first = json.loads(first_raw)
        self.assertEqual(first["reason"], "cancelled")
        self.assertEqual(first["coverage"], {"expected": 4, "generated": 0, "evaluated": 0})
        self.assertIsNotNone(first["failed_generation"])
        self.assertEqual(first["failed_generation"]["generation"]["directory"], str(generation))
        self.assertEqual(
            first["failed_generation"]["generation"]["report_sha256"],
            sha((generation / "report.json").read_bytes()),
        )
        before = files(final)
        funding = self.authorities["final"].summary()
        with (
            patch.dict(os.environ, {}, clear=True),
            patch("buddha.executor.run_container", side_effect=AssertionError("new worker")),
            patch("http.client.HTTPSConnection", side_effect=AssertionError("new request")),
            patch.object(
                self.module.candidate_generation,
                "prepare_candidate_generation",
                side_effect=AssertionError("replacement owner"),
            ),
            patch.object(
                self.module.candidate_generation,
                "run_candidate_generation",
                side_effect=AssertionError("failed generation rerun"),
            ),
            patch.object(
                self.module.native_evaluation,
                "prepare_evaluation",
                side_effect=AssertionError("failed source evaluated"),
            ),
        ):
            result = self.run_final()
            after = files(final)
            replay_before = files(self.f.root)
            replay = self.run_final()
        self.assertEqual(result["status"], "incomplete")
        self.assertEqual(result["reason"], "candidate_execution_failed")
        self.assertEqual(result["failed_generation"], first["failed_generation"])
        self.assertEqual(result["coverage"], first["coverage"])
        self.assertEqual(first_path.read_bytes(), first_raw)
        self.assertTrue(all(after[name] == raw for name, raw in before.items()))
        self.assertEqual(set(after) - set(before), {"observations/1.json"})
        self.assertEqual(replay, result)
        self.assertEqual(files(self.f.root), replay_before)
        self.assertEqual(self.authorities["final"].summary(), funding)
        self.assertFalse((final / "report.json").exists())
