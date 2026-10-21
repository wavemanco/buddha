"""The declared comparison composes genuine accounting and mocked worker/HTTPS paths."""

import copy
import hashlib
import json
import os
import unittest
from pathlib import Path
from unittest.mock import patch

import test_baseline as baseline_fixtures
import test_gateway as gateway_fixtures

from buddha import baseline, native_evaluation, policy_run
from buddha.answers import TaskSet
from buddha.authorization import Authorization
from buddha.gateway import RawHTTPTransport
from buddha.policy_run import PolicyRunError, prepare_study, run_study
from buddha.policy_study import PolicyStudy
from buddha.releases import _json, inventory, prepare_selection


def sha(raw):
    return hashlib.sha256(raw).hexdigest()


class PolicyRunTests(unittest.TestCase):
    def setUp(self):
        self.fixture = f = baseline_fixtures.BaselineTests("runTest")
        f.setUp()
        self.addCleanup(f.doCleanups)
        self.root = f.root
        f.agent.dataset += _json({"qid": "final", "question": "FINAL-ONLY-SENTINEL"}) + b"\n"
        (f.fixture.roots["official"] / "data/tasks.jsonl").write_bytes(f.agent.dataset)
        f.fixture.release_record["source"] = inventory(f.fixture.roots["official"])
        f.agent.configure_tasks()
        f.agent.descriptor.write_bytes(_json(f.agent.record))
        selections = [
            prepare_selection(
                f.agent.release,
                roots,
                capabilities={gateway_fixtures.CAPABILITY: "profiles/openai.json"},
            )
            for roots in (f.generation_roots, f.native_roots)
        ]
        f.agent_selection = selections[0]
        f.record["generation"]["selection"] = selections[0].to_record()
        f.record["native"]["selection"] = selections[1].to_record()
        source = TaskSet.from_dataset(f.agent.release, f.agent.dataset)
        self.study_record = {
            "format": "buddha.policy-study.v1",
            "source": source.to_record(),
            "split": {
                "release_sha256": source.release_sha256,
                "dataset_sha256": source.dataset_sha256,
                "partitions": {
                    "development": ["1", 1],
                    "validation": ["private"],
                    "final": ["final"],
                },
                "families": [
                    {"id": task.id, "family": "family-" + str(index)}
                    for index, task in enumerate(source.tasks)
                ],
            },
            "selected_ids": ["1", 1],
            "child_policy": {
                "instructions": "Use a concrete original mechanism and preserve task requirements.",
                "sampling": "regenerate",
            },
            "generation": {"provider": "openai", "model": "test-model", "max_output_tokens": 100},
            "generation_repeats": 2,
            "judge_occasions": 2,
            "execution_order": [
                {"arm": arm, "repeat": repeat} for repeat in range(2) for arm in range(4)
            ],
        }
        self.study = PolicyStudy.from_bytes(_json(self.study_record))
        self.study_path = self.root / "study.json"
        self.study_path.write_bytes(self.study.to_bytes())
        self.template = self.root / "baseline-template.json"
        self.template.write_bytes(_json(f.record))
        self.authority = f.authority = Authorization.create(
            self.root / "study-authorization.sqlite3",
            authorization_id="controlled-policy-synthetic",
            budget_microusd=1_000_000,
            max_calls=1000,
            scope="policy study: " + self.study.fingerprint(),
        )
        terms = self.authority.summary()
        self.record = {
            "format": "buddha.policy-execution.v1",
            "study": {"path": str(self.study_path), "sha256": sha(self.study_path.read_bytes())},
            "baseline": {"path": str(self.template), "sha256": sha(self.template.read_bytes())},
            "authorization": {
                "path": str(self.authority.path),
                "id": terms["authorization_id"],
                "terms_sha256": terms["terms_sha256"],
                "scope": terms["scope"],
            },
        }
        self.descriptor = self.root / "execution.json"
        self.directory = self.root / "comparison"
        self.generation_configs = []

    def prepare(self):
        self.descriptor.write_bytes(_json(self.record))
        return prepare_study(
            self.directory,
            descriptor=self.descriptor,
            authorization=self.authority,
            review=self.fixture.fixture.review,
        )

    def execute(self, spec, *, initial, **kwargs):
        if spec.role == "agent":
            self.fixture.agent.config = copy.deepcopy(initial["config"])
            self.generation_configs.append(copy.deepcopy(initial["config"]))
        return self.fixture.execute(spec, initial=initial, **kwargs)

    def run_study(self, *, paid=True):
        with (
            patch.dict(
                os.environ,
                {"OPENAI_API_KEY": gateway_fixtures.KEY} if paid else {},
                clear=True,
            ),
            patch("buddha.executor.run_container", side_effect=self.execute),
        ):
            return run_study(self.directory, transport=RawHTTPTransport(allow_paid=paid))

    def test_declared_eight_cells_generate_once_and_rejudge_same_answers_in_new_owners(self):
        self.prepare()
        report = self.run_study()
        self.assertEqual(report["format"], "buddha.policy-run-report.v1")
        self.assertEqual(report["status"], "complete")
        self.assertEqual(report["study_sha256"], self.study.fingerprint())
        schedule = self.study.schedule()
        self.assertEqual(
            [row["cell_id"] for row in report["cells"]], [row["cell_id"] for row in schedule]
        )
        self.assertEqual(self.fixture.physical_sends, 64)
        self.assertEqual(self.authority.summary()["operation_count"], 64)
        self.assertEqual(len(self.authority.summary()["runs"]), 56)
        self.assertTrue(all(not row["active"] for row in self.authority.summary()["runs"]))
        expected_configs = [row["generation_config"] for row in schedule for _ in range(2)]
        self.assertEqual(self.generation_configs, expected_configs)
        self.assertEqual(len([e for e in self.fixture.events if e["role"] == "evaluator"]), 48)
        package = Path(__file__).resolve().parents[1] / "buddha"
        controls = (
            self.descriptor,
            self.study_path,
            self.template,
            self.fixture.agent.tasks_path,
            self.fixture.agent.descriptor,
            package / "policy_run.py",
            package / "policy_study.py",
            package / "native_evaluation.py",
        )
        for index, row in enumerate(report["cells"]):
            with self.subTest(cell=index):
                self.assertEqual(row["arm_index"], schedule[index]["arm_index"])
                self.assertEqual(row["generation_repeat"], schedule[index]["generation_repeat"])
                self.assertEqual(
                    [x["occasion_id"] for x in row["occasions"]],
                    [x["occasion_id"] for x in schedule[index]["judge_occasions"]],
                )
                self.assertEqual([x["index"] for x in row["occasions"]], [0, 1])
                original = Path(row["source_generation"]["baseline_directory"])
                for occasion in row["occasions"]:
                    child = Path(occasion["directory"])
                    for owner in (child / "owners").iterdir():
                        manifest = json.loads((owner / "manifest.json").read_bytes())
                        bound = {
                            item["path"]: item["sha256"]
                            for item in manifest["invocation"]["inputs"]
                        }
                        for control in controls:
                            self.assertEqual(bound.get(str(control)), sha(control.read_bytes()))
                    self.assertEqual(
                        sha((child / "report.json").read_bytes()), occasion["report_sha256"]
                    )
                    self.assertEqual(
                        (child / "native-answers.jsonl").read_bytes(),
                        (original / "native-answers.jsonl").read_bytes(),
                    )
                    self.assertEqual(
                        Path(occasion["summary"]["path"]).read_bytes(), self.fixture.summary_bytes
                    )
        before = self.authority.path.read_bytes()
        stored = (self.directory / "report.json").read_bytes()
        with patch.object(self, "execute", side_effect=AssertionError("completed study executed")):
            self.assertEqual(self.run_study(paid=False), report)
        self.assertEqual(self.fixture.physical_sends, 64)
        self.assertEqual(self.authority.path.read_bytes(), before)
        self.assertEqual((self.directory / "report.json").read_bytes(), stored)

    def test_wrong_study_scope_is_rejected_before_creating_any_owner(self):
        self.record["authorization"]["scope"] = "unrelated authorization"
        with self.assertRaises(PolicyRunError):
            self.prepare()
        self.assertEqual(self.authority.summary()["runs"], [])
        self.assertEqual(self.fixture.physical_sends, 0)

    def check_observation(self, result):
        self.assertEqual(result["status"], "incomplete")
        observed = self.directory / result["observation"]
        self.assertEqual(json.loads(observed.read_bytes()), result)
        self.assertTrue(Path(result["child_directory"]).is_dir())
        return observed

    def test_declared_file_and_authority_pins_fail_before_any_new_owner(self):
        original = copy.deepcopy(self.record)
        mutations = [
            ("study", "sha256", "0" * 64),
            ("baseline", "sha256", "0" * 64),
            ("authorization", "id", "another-grant"),
            ("authorization", "terms_sha256", "0" * 64),
        ]
        for index, (section, field, value) in enumerate(mutations):
            with self.subTest(section=section, field=field):
                self.record = copy.deepcopy(original)
                self.record[section][field] = value
                self.directory = self.root / ("invalid-pins-" + str(index))
                with self.assertRaises(PolicyRunError):
                    self.prepare()
                self.assertEqual(self.authority.summary()["runs"], [])
                self.assertEqual(self.fixture.physical_sends, 0)

    def test_first_template_config_must_equal_the_declared_first_condition(self):
        record = copy.deepcopy(self.fixture.agent.record)
        record["config"]["instructions"] = "undeclared first treatment"
        self.fixture.agent.descriptor.write_bytes(_json(record))
        with self.assertRaises(PolicyRunError):
            self.prepare()
        self.assertEqual(self.authority.summary()["runs"], [])

    def test_first_template_tasks_must_equal_the_study_selection(self):
        selected = self.study.tasks.select([1])
        self.fixture.agent.tasks_path.write_bytes(selected.to_bytes())
        with self.assertRaises(PolicyRunError):
            self.prepare()
        self.assertEqual(self.authority.summary()["runs"], [])

    def test_template_change_after_preparation_stops_before_a_provider_send(self):
        self.prepare()
        changed = copy.deepcopy(self.fixture.record)
        changed["native"]["max_calls"] += 1
        self.template.write_bytes(_json(changed))
        with self.assertRaises(PolicyRunError):
            self.run_study()
        self.assertEqual(self.fixture.physical_sends, 0)
        self.assertEqual(self.authority.summary()["operation_count"], 0)

    def test_later_cell_cannot_adopt_changed_original_study_controls(self):
        self.prepare()
        original = self.study_path.read_bytes()
        prepare_gateway = baseline.prepare_gateway
        later_owner = self.directory / "cells/1/baseline/owners/0"
        changed = False

        def change_before_first_owner(directory, **kwargs):
            nonlocal changed
            if directory == later_owner:
                changed = True
                self.study_path.write_bytes(original + b"\n")
            return prepare_gateway(directory, **kwargs)

        try:
            with (
                patch("buddha.baseline.prepare_gateway", side_effect=change_before_first_owner),
                self.assertRaises(PolicyRunError),
            ):
                self.run_study()
            self.assertTrue(changed)
            self.assertEqual(self.fixture.physical_sends, 8)
            self.assertEqual(len(self.generation_configs), 2)
            self.assertFalse((self.directory / "cells/2").exists())
        finally:
            self.study_path.write_bytes(original)

    def test_child_report_typed_amount_change_is_rejected_before_fresh_judging(self):
        self.prepare()
        run_baseline = baseline.run_baseline

        def change_after_completion(directory, **kwargs):
            report = run_baseline(directory, **kwargs)
            self.assertEqual(report["status"], "complete")
            changed = copy.deepcopy(report)
            self.assertEqual(changed["authorization"]["reserved_microusd"], 0)
            changed["authorization"]["reserved_microusd"] = False
            (directory / "report.json").write_bytes(_json(changed))
            self.fixture.fail_native_once = True
            return report

        rejected = False
        with patch("buddha.baseline.run_baseline", side_effect=change_after_completion):
            try:
                self.run_study()
            except PolicyRunError:
                rejected = True
        self.assertEqual(self.fixture.physical_sends, 6)
        self.assertTrue(rejected)

    def test_changed_prior_child_report_blocks_final_study_publication(self):
        self.prepare()
        run_evaluation = native_evaluation.run_evaluation
        final_child = self.directory / "cells/7/judgments/1"
        changed = False

        def change_before_publication(directory, **kwargs):
            nonlocal changed
            report = run_evaluation(directory, **kwargs)
            if directory == final_child:
                changed = True
                original = self.directory / "cells/0/baseline/report.json"
                original.write_bytes(original.read_bytes() + b"\n")
            return report

        rejected = False
        with patch(
            "buddha.native_evaluation.run_evaluation", side_effect=change_before_publication
        ):
            try:
                self.run_study()
            except PolicyRunError:
                rejected = True
        self.assertTrue(changed)
        self.assertEqual(self.fixture.physical_sends, 64)
        self.assertFalse((self.directory / "report.json").exists())
        self.assertTrue(rejected)

    def test_foreign_future_cells_or_occasions_fail_before_starting_earlier_generation(self):
        for index, relative in enumerate(("cells/07", "cells/7", "cells/1", "cells/0/judgments/2")):
            with self.subTest(relative=relative):
                self.directory = self.root / ("invalid-layout-" + str(index))
                self.prepare()
                (self.directory / relative).mkdir(parents=True, exist_ok=True)
                with self.assertRaises(PolicyRunError):
                    self.run_study()
                self.assertEqual(self.fixture.physical_sends, 0)
                self.assertEqual(self.authority.summary()["operation_count"], 0)

    def test_retained_future_work_cannot_skip_an_incomplete_execution_prefix(self):
        self.prepare()
        definition = policy_run._definition(self.descriptor, self.authority)
        descriptor = policy_run._materialize(
            self.directory, 1, self.study.schedule()[1], definition
        )
        baseline.prepare_baseline(
            descriptor.parent / "baseline",
            descriptor=descriptor,
            authorization=self.authority,
            review=self.fixture.fixture.review,
            input_files=policy_run._controls(self.directory, definition),
        )
        self.fixture.fail_generation_once = True
        with (
            patch.dict(os.environ, {"OPENAI_API_KEY": gateway_fixtures.KEY}, clear=True),
            patch("buddha.executor.run_container", side_effect=self.execute),
        ):
            future = baseline.run_baseline(
                descriptor.parent / "baseline", transport=RawHTTPTransport(allow_paid=True)
            )
        self.assertEqual(future["status"], "incomplete")
        sent = self.fixture.physical_sends
        self.assertEqual(sent, 3)
        self.fixture.fail_generation_once = True
        rejected = False
        try:
            self.run_study()
        except PolicyRunError:
            rejected = True
        self.assertEqual(self.fixture.physical_sends, sent)
        self.assertTrue(rejected)

    def test_unknown_baseline_judging_stops_resume_without_releasing_or_replacing_work(self):
        self.prepare()
        self.fixture.timeout_native_once = True
        first = self.run_study()
        observed = self.check_observation(first)
        self.assertEqual(first["reason"], "unknown")
        self.assertEqual((first["cell_index"], first["occasion_index"]), (0, 0))
        self.assertEqual(first["child_report"]["status"], "incomplete")
        self.assertEqual(self.fixture.physical_sends, 5)
        held = self.authority.summary()["reserved_microusd"]
        self.assertGreater(held, 0)
        owners = self.authority.summary()["runs"]
        original_observation = observed.read_bytes()
        second = self.run_study()
        self.check_observation(second)
        self.assertEqual(second["reason"], "unknown")
        self.assertEqual(self.fixture.physical_sends, 5)
        self.assertEqual(self.authority.summary()["reserved_microusd"], held)
        self.assertEqual(self.authority.summary()["runs"], owners)
        self.assertEqual(observed.read_bytes(), original_observation)
        self.assertFalse((self.directory / "cells/1").exists())

    def test_fresh_judgment_failure_resumes_original_receipt_and_keeps_completed_generation(self):
        self.prepare()
        original_execute = self.execute
        stopped = False

        def stop_first_fresh_partition(spec, *, initial, **kwargs):
            nonlocal stopped
            session = kwargs["handle"].__self__
            if (
                not stopped
                and spec.role == "evaluator"
                and "judgments" in session.gateway.directory.parts
            ):
                self.fixture.fail_native_once = stopped = True
            return original_execute(spec, initial=initial, **kwargs)

        with patch.object(self, "execute", side_effect=stop_first_fresh_partition):
            first = self.run_study()
        observed = self.check_observation(first)
        self.assertEqual(first["reason"], "native_error")
        self.assertEqual((first["cell_index"], first["occasion_index"]), (0, 1))
        self.assertEqual(self.fixture.physical_sends, 7)
        baseline = self.directory / "cells/0/baseline"
        baseline_report = (baseline / "report.json").read_bytes()
        owner = Path(first["child_directory"]) / "owners/1/manifest.json"
        owner_bytes = owner.read_bytes()
        original_observation = observed.read_bytes()
        self.fixture.fail_generation_once = True
        second = self.run_study()
        self.check_observation(second)
        self.assertEqual((second["cell_index"], second["occasion_index"]), (1, 0))
        self.assertEqual(self.fixture.physical_sends, 11)
        self.assertEqual((baseline / "report.json").read_bytes(), baseline_report)
        self.assertEqual(owner.read_bytes(), owner_bytes)
        self.assertEqual(observed.read_bytes(), original_observation)
        self.assertFalse((self.directory / "cells/2").exists())

    def test_cancellation_keeps_known_child_without_inventing_a_returned_report(self):
        self.prepare()
        original_execute = self.execute
        interrupted = False

        def interrupt_after_first_received_task(spec, *, initial, **kwargs):
            nonlocal interrupted
            result = original_execute(spec, initial=initial, **kwargs)
            if not interrupted and spec.role == "agent":
                interrupted = True
                raise KeyboardInterrupt
            return result

        with (
            patch.object(self, "execute", side_effect=interrupt_after_first_received_task),
            self.assertRaises(KeyboardInterrupt),
        ):
            self.run_study()
        observations = list((self.directory / "observations").glob("*.json"))
        self.assertEqual(len(observations), 1)
        observed = json.loads(observations[0].read_bytes())
        self.check_observation(observed)
        self.assertEqual(observed["reason"], "cancelled")
        self.assertEqual((observed["cell_index"], observed["occasion_index"]), (0, 0))
        self.assertIsNone(observed["child_report"])
        self.assertEqual(self.fixture.physical_sends, 2)
        original_observation = observations[0].read_bytes()
        self.fixture.timeout_native_once = True
        resumed = self.run_study()
        self.check_observation(resumed)
        self.assertEqual(resumed["reason"], "unknown")
        self.assertEqual(self.fixture.physical_sends, 5)
        self.assertEqual(observations[0].read_bytes(), original_observation)


if __name__ == "__main__":
    unittest.main()
