"""Prospective transfer evaluation keeps its own checked public interface."""

import copy
import json
import os
import shutil
import sqlite3
import unittest
from contextlib import contextmanager
from pathlib import Path
from unittest.mock import patch

import test_final_evaluation as final_fixtures

files, sha = final_fixtures.files, final_fixtures.sha


class TransferEvaluationTests(unittest.TestCase):
    def test_public_transfer_interfaces_exist(self):
        from buddha.final_evaluation import (
            inspect_transfer_evaluation,
            run_transfer_evaluation,
        )

        self.assertTrue(callable(run_transfer_evaluation))
        self.assertTrue(callable(inspect_transfer_evaluation))

    def fixture(self, *, dataset="data/transfer.jsonl", extra_member=False):
        from buddha.answers import TaskSet
        from buddha.authorization import Authorization
        from buddha.releases import Release, inventory, prepare_selection
        from buddha.trial_fence import _scope_text, _TrialScope

        c = self.c = final_fixtures.FinalEvaluationTests("runTest")
        c.setUp()
        self.addCleanup(c.doCleanups)
        c.fixture()
        self.module, self.Error, self.json = c.module, c.Error, c.json
        f, e = c.f, c.engine
        self.legacy_grants = dict(c.authorities)
        self.legacy_definition = copy.deepcopy(c.definition)
        c.definition.update(format="buddha.evaluation-trial.v2", final_ids=["final-a"])
        for member in f.custody["population"]:
            if member["task_id"] == "final-b":
                member.update(phase="development", exposure="exposed")
        f.record["custody"] = f.reference(f.write("custody.json", f.custody))

        # The old official tree remains byte-for-byte unchanged. The new release
        # retains it and adds one separately declared, non-executable dataset.
        official = f.root / "transfer-official"
        shutil.copytree(e.fixture.roots["official"], official)
        rows = [{"id": "final-a", "prompt": "TRANSFER-ONLY: describe a clockwork orchard."}]
        if extra_member:
            rows.append({"id": "unselected", "prompt": "Synthetic validation task."})
        data = b"".join(self.json(row) + b"\n" for row in rows)
        target = official / dataset
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(data)
        release_record = copy.deepcopy(e.fixture.release_record)
        release_record.update(release="separate-transfer-source", source=inventory(official))
        release_record["task"]["dataset"] = dataset
        release = Release.from_record(release_record)
        self.transfer_tasks = TaskSet.from_dataset(release, data)
        self.transfer_custody = copy.deepcopy(f.custody)
        self.transfer_custody["population"] = [
            {
                "task_id": task.id,
                "task_sha256": sha(self.json(task.to_record())),
                "family_id": "independent-transfer-family-" + str(index),
                "source": "synthetic transfer source",
                "task_type": "fixture",
                "phase": "transfer" if index == 0 else "development",
                "exposure": "eligible" if index == 0 else "exposed",
            }
            for index, task in enumerate(self.transfer_tasks.tasks)
        ]
        roots = e.fixture.roots | {"official": official}
        native_roots = {name: Path(value) for name, value in e.native["roots"].items()} | {
            "official": official
        }
        generation = copy.deepcopy(f.record["generation"])
        generation.update(
            selection=prepare_selection(
                release, roots, capabilities={"openai.chat-completions.v1": "profiles/openai.json"}
            ).to_record(),
            roots={name: str(path) for name, path in roots.items()},
        )
        native = copy.deepcopy(e.native)
        native.update(
            selection=prepare_selection(
                release,
                native_roots,
                capabilities={"openai.chat-completions.v1": "profiles/openai.json"},
            ).to_record(),
            roots={name: str(path) for name, path in native_roots.items()},
        )
        c.definition["transfer"] = {
            "tasks": f.reference(f.write("transfer-tasks.json", self.transfer_tasks.to_record())),
            "custody": f.reference(f.write("transfer-custody.json", self.transfer_custody)),
            "selected_ids": ["final-a"],
            "repetitions": 1,
            "generation": generation,
            "native": native,
            "stages": copy.deepcopy(e.stages),
        }
        self.plan = json.loads(Path(f.record["analysis_plan"]["path"]).read_bytes())
        self.plan.update(
            format="buddha.validation-analysis-plan.v2",
            transfer_projection_release_sha256=release.fingerprint(),
            transfer_repetitions=1,
        )
        self.plan["alpha"]["transfer"] = {"numerator": 1, "denominator": 64}
        f.record["analysis_plan"] = f.reference(f.write("analysis-plan.json", self.plan))
        f.declaration = f.write("declaration.json", f.record)
        c.definition["validation"] = f.reference(f.declaration)
        c.definition["phase_limits"]["transfer"] = copy.deepcopy(
            c.definition["phase_limits"]["final"]
        )
        c.declaration.write_bytes(self.json(c.definition))
        identity = sha(self.json(c.definition))
        # The helper's three old v1 grants stay untouched as foreign controls.
        # All actual trial grants are fresh and bind the final v2 definition.
        c.authorities = {
            phase: Authorization.create(
                f.root / ("v2-" + phase + ".sqlite3"),
                authorization_id="synthetic-v2-" + phase,
                **limits,
                scope=_scope_text(_TrialScope(c.root, identity, phase, version=2)),
            )
            for phase, limits in c.definition["phase_limits"].items()
        }
        c.execute = self.execute
        return c

    def execute(self, spec, *, initial, handle, **kwargs):
        from buddha.releases import Selection

        c, e = self.c, self.c.engine
        session = handle.__self__
        if spec.role == "agent":
            task = session.tasks.tasks[0]
            population = (
                self.transfer_tasks
                if session.tasks.release_sha256 == self.transfer_tasks.release_sha256
                else c.f.tasks
            )
            self.assertEqual(initial["task"], population.select([task.id]).tasks[0].to_record())
            self.assertNotIn(b"dataset_base64", self.json(initial))
            c.events.append(("generation", task.id, str(session.gateway.directory)))
            e.candidate.tasks = session.tasks
            manifest = json.loads((session.gateway.directory / "manifest.json").read_bytes())
            e.fixture.selection = Selection.from_bytes(self.json(manifest["selection"]))
            e.directory = session.output.parents[2]
        else:
            c.events.append(("native", initial["command"]["index"], str(session.gateway.directory)))
            e.directory = session.gateway.directory.parents[2] / "generation"
        return e.execute(spec, initial=initial, handle=handle, **kwargs)

    def run_transfer(self, *, authorization=None):
        from buddha.gateway import RawHTTPTransport

        c = self.c
        return self.module.run_transfer_evaluation(
            c.root,
            authorization=authorization or c.authorities["transfer"],
            review=c.engine.fixture.review,
            transport=RawHTTPTransport(allow_paid=True),
        )

    @contextmanager
    def passive(self):
        from buddha.authorization import Authorization
        from buddha.ledger import Ledger

        connect = sqlite3.connect

        def memory_only(path, *args, **kwargs):
            self.assertEqual(path, ":memory:", "passive replay opened an on-disk database")
            return connect(path, *args, **kwargs)

        with (
            patch.dict(os.environ, {}, clear=True),
            patch("sqlite3.connect", side_effect=memory_only),
            patch.object(Authorization, "__init__", side_effect=AssertionError("active authority")),
            patch.object(Ledger, "__init__", side_effect=AssertionError("active ledger")),
            patch("buddha.gateway.Gateway", side_effect=AssertionError("active gateway")),
            patch("buddha.executor.run_container", side_effect=AssertionError("worker")),
            patch("http.client.HTTPSConnection", side_effect=AssertionError("provider")),
        ):
            yield

    def test_two_source_scoped_panels_resume_original_transfer_owners_and_replay_passively(self):
        c = self.fixture()
        self.assertNotEqual(c.f.tasks.release_sha256, self.transfer_tasks.release_sha256)
        self.assertNotEqual(
            c.f.tasks.select(["final-a"]).tasks[0].prompt,
            self.transfer_tasks.tasks[0].prompt,
        )
        c.prepare()
        validation = c.validate()
        schedule = c.freeze(validation)
        self.assertEqual(schedule["format"], "buddha.sealed-schedule.v2")
        self.assertEqual(set(schedule["panels"]), {"final", "transfer"})
        self.assertEqual(len(schedule["arms"]), 2)
        self.assertEqual(len(list((c.root / "freeze/sources").glob("*.py"))), 2)
        for phase, tasks in (("final", c.f.tasks), ("transfer", self.transfer_tasks)):
            panel = schedule["panels"][phase]
            self.assertEqual(panel["selected_ids"], ["final-a"])
            self.assertEqual(panel["tasks_sha256"], tasks.fingerprint())
            self.assertEqual(panel["counts"], {"cells": 2})
            self.assertEqual(panel["grant"]["path"], str(c.authorities[phase].path))
        frozen = files(c.root / "freeze")
        c.events.clear()
        with c.offline():
            final = c.run_final()
        self.assertEqual(final["coverage"], {"expected": 2, "generated": 2, "evaluated": 2})
        final_files = files(c.root / "final")
        final_funding = c.authorities["final"].summary()
        before = files(c.f.root)
        self.assertEqual(c.freeze(validation), schedule)
        changed_results = [validation[0] | {"result_sha256": "0" * 64}]
        with self.assertRaises(self.Error):
            c.freeze(changed_results)
        self.assertEqual(files(c.f.root), before)
        for foreign in (self.legacy_grants["final"], c.authorities["final"]):
            with self.subTest(foreign_grant=foreign.path), self.assertRaises(self.Error):
                self.run_transfer(authorization=foreign)
            self.assertEqual(files(c.f.root), before)

        # A genuine confirmed freeze and exact producer inputs are still no
        # permission to create a direct, unscheduled transfer Gateway owner.
        from buddha.gateway import prepare_gateway

        state, occasion, pins = self.module._restore_transfer_grid(c.root)
        cell = self.module.study._location(state, occasion, 0, 0, 0)
        generation, selected, controls = self.module.study._materialize(
            state, occasion, occasion["arms"][0], "final-a", cell, receipts=pins
        )
        destination = cell / "generation/owners/0"
        before = files(c.f.root)
        with self.assertRaises(ValueError):
            prepare_gateway(
                destination,
                selection=selected,
                roots={name: Path(value) for name, value in generation["roots"].items()},
                authorization=c.authorities["transfer"],
                budget_microusd=generation["budget_microusd"],
                max_calls=generation["max_calls"],
                input_files=list(controls),
                expected_input_hashes=controls,
                review=occasion["review"],
            )
        self.assertFalse(destination.exists())
        self.assertEqual(files(c.f.root), before)

        original_row = c.engine.native_row

        def missing_utility(row, stage):
            value = original_row(row, stage)
            if stage == 1 and c.engine.directory.is_relative_to(c.root / "transfer/arms/1"):
                value["utility"] = float("nan")
            return value

        c.engine.native_row = missing_utility
        original_native = self.module.native_evaluation.run_evaluation
        stopped = []

        def interrupt_after_native(*args, **kwargs):
            result = original_native(*args, **kwargs)
            if not stopped:
                self.assertEqual(result["status"], "complete")
                stopped.append(True)
                raise KeyboardInterrupt
            return result

        c.events.clear()
        with (
            c.offline(),
            patch.object(
                self.module.native_evaluation, "run_evaluation", side_effect=interrupt_after_native
            ),
            self.assertRaises(KeyboardInterrupt),
        ):
            self.run_transfer()
        self.assertEqual(stopped, [True])
        transfer = c.root / "transfer"
        manifests = {path: path.read_bytes() for path in transfer.rglob("manifest.json")}
        self.assertEqual(len(manifests), 4)
        first_cell = transfer / "arms/0/tasks/0/repetitions/0"
        immutable_cell = files(first_cell)
        journal = files(transfer / "observations")
        partial = json.loads(next(iter(journal.values())))
        self.assertEqual(partial["format"], "buddha.sealed-evaluation-partial.v2")
        self.assertEqual((partial["phase"], partial["reason"]), ("transfer", "cancelled"))
        self.assertEqual(partial["release_sha256"], self.transfer_tasks.release_sha256)
        self.assertEqual(partial["tasks_sha256"], self.transfer_tasks.fingerprint())
        self.assertFalse((transfer / "report.json").exists())
        c.events.clear()
        with c.offline():
            result = self.run_transfer()
        self.assertEqual(result["coverage"], {"expected": 2, "generated": 2, "evaluated": 2})
        self.assertEqual(len(list(transfer.rglob("manifest.json"))), 8)
        self.assertTrue(all(path.read_bytes() == raw for path, raw in manifests.items()))
        self.assertEqual(files(first_cell), immutable_cell)
        self.assertEqual(files(transfer / "observations"), journal)
        self.assertTrue(all(str(transfer) in owner for _, _, owner in c.events))
        self.assertEqual(sum(role == "generation" for role, _, _ in c.events), 1)
        self.assertEqual(files(c.root / "final"), final_files)
        self.assertEqual(c.authorities["final"].summary(), final_funding)
        self.assertEqual(files(c.root / "freeze"), frozen)
        global_sha = sha((c.root / "freeze/schedule.json").read_bytes())
        for phase, report, tasks in (
            ("final", final, c.f.tasks),
            ("transfer", result, self.transfer_tasks),
        ):
            self.assertEqual(report["format"], "buddha.sealed-evaluation-report.v2")
            self.assertEqual(report["status"], "complete")
            self.assertEqual(report["phase"], phase)
            self.assertEqual(report["release_sha256"], tasks.release_sha256)
            self.assertEqual(report["tasks_sha256"], tasks.fingerprint())
            self.assertEqual(report["schedule_sha256"], global_sha)
            self.assertEqual(report["arms"], schedule["arms"])
            self.assertEqual(report["selected_ids"], ["final-a"])
            for owner in (c.root / phase).rglob("manifest.json"):
                manifest = json.loads(owner.read_bytes())
                inputs = {row["path"]: row["sha256"] for row in manifest["invocation"]["inputs"]}
                self.assertEqual(inputs[str(c.root / "freeze/schedule.json")], global_sha)
                self.assertEqual(manifest["authorization_path"], str(c.authorities[phase].path))
        self.assertEqual(partial["schedule_sha256"], global_sha)
        contrast = result["analysis"]["contrasts"][0]
        self.assertEqual(contrast["rule"]["status"], "inconclusive")
        self.assertIsNone(contrast["axes"]["utility"]["lower_bound"])
        self.assertEqual(contrast["axes"]["utility"]["reason"], "required_native_scalar_missing")
        self.assertEqual(contrast["axes"]["utility"]["tail"], {"numerator": 1, "denominator": 128})
        self.assertEqual(
            final["analysis"]["contrasts"][0]["axes"]["utility"]["tail"],
            {"numerator": 1, "denominator": 64},
        )

        before = files(c.f.root)
        funding = {phase: grant.summary() for phase, grant in c.authorities.items()}
        counts = c.engine.workers, c.engine.physical_sends
        with self.passive():
            for phase, report in (("final", final), ("transfer", result)):
                inspector = getattr(self.module, "inspect_" + phase + "_evaluation")
                self.assertEqual(
                    inspector(c.root, expected_report_sha256=sha(self.json(report))), report
                )
            self.assertEqual(self.run_transfer(), result)
        self.assertEqual(files(c.f.root), before)
        self.assertEqual((c.engine.workers, c.engine.physical_sends), counts)
        self.assertEqual(
            {phase: grant.summary() for phase, grant in c.authorities.items()}, funding
        )
        self.assertTrue(
            all(grant.summary()["operation_count"] == 0 for grant in self.legacy_grants.values())
        )

        # The real public outer reader must retain consumed bytes and SQLite
        # sidecar absence until its final check, after inner analysis returns.
        original_result = self.module._result
        task_file = transfer / "arms/0/tasks/0/repetitions/0/task.json"
        sidecar = c.authorities["transfer"].path.with_name(
            c.authorities["transfer"].path.name + "-wal"
        )
        custody = Path(c.definition["transfer"]["custody"]["path"])
        copied_arm = Path(schedule["arms"][0]["path"])
        for target, raw in (
            (task_file, task_file.read_bytes() + b" "),
            (sidecar, b"late"),
            (custody, custody.read_bytes() + b" "),
            (copied_arm, copied_arm.read_bytes() + b"\n# late change\n"),
        ):
            original = target.read_bytes() if target.exists() else None
            touched = []

            def late_change(*args, target=target, raw=raw, touched=touched, **kwargs):
                report = original_result(*args, **kwargs)
                target.write_bytes(raw)
                touched.append(True)
                return report

            try:
                with self.passive(), patch.object(self.module, "_result", side_effect=late_change):
                    with self.assertRaises(self.Error):
                        self.module.inspect_transfer_evaluation(
                            c.root, expected_report_sha256=sha(self.json(result))
                        )
                self.assertEqual(touched, [True])
            finally:
                if original is None:
                    target.unlink(missing_ok=True)
                else:
                    target.write_bytes(original)
        self.assertEqual(files(c.f.root), before)

        # This is an actual complete custody observation, with only cell
        # enumeration faulted: the numeric kernel must never see a dropped arm.
        state, occasion, pins = self.module._restore_transfer_grid(c.root)
        reader, current = self.module._census(state, occasion, pins)
        original_cells = self.module.study._cells
        with (
            patch.object(
                self.module.study,
                "_cells",
                side_effect=lambda *a: (
                    row for row in original_cells(*a) if row[0]["role"] != "candidate"
                ),
            ),
            patch.object(self.module.analysis, "_aggregate_contrast") as kernel,
            self.assertRaises(self.Error),
        ):
            self.module._analysis(state, occasion, reader, current)
        kernel.assert_not_called()
        reader.finish()
        self.assertEqual(files(c.f.root), before)

    def test_prospective_custody_resources_and_v1_schema_refuse_before_trial_publication(self):
        from buddha.validation_analysis import ValidationAnalysisError, ValidationAnalysisPlan

        c = self.fixture()
        controls = {
            path: path.read_bytes()
            for path in (
                c.declaration,
                c.f.declaration,
                Path(c.f.record["analysis_plan"]["path"]),
                Path(c.definition["transfer"]["custody"]["path"]),
            )
        }
        changes = (
            ("missing_final_member", lambda d, custody, plan: d.update(final_ids=[])),
            (
                "missing_transfer_member",
                lambda d, custody, plan: d["transfer"].update(selected_ids=[]),
            ),
            (
                "exposed",
                lambda d, custody, plan: custody["population"][0].update(exposure="exposed"),
            ),
            (
                "named_process_disclosure",
                lambda d, custody, plan: custody["disclosures"].append(
                    {
                        "task_id": "final-a",
                        "process_id": custody["process_id"],
                        "recipient": "synthetic adaptive process",
                        "channel": "fixture",
                        "basis": "prospectively disclosed before preparation",
                    }
                ),
            ),
            (
                "cross_phase_family",
                lambda d, custody, plan: custody["population"][0].update(family_id="family-2"),
            ),
            (
                "different_resources",
                lambda d, custody, plan: d["transfer"]["generation"].update(max_calls=21),
            ),
            (
                "wrong_projection",
                lambda d, custody, plan: plan.update(
                    transfer_projection_release_sha256=c.f.tasks.release_sha256
                ),
            ),
            ("wrong_repetitions", lambda d, custody, plan: plan.update(transfer_repetitions=2)),
            (
                "v1_extra_transfer",
                lambda d, custody, plan: d.update(format="buddha.evaluation-trial.v1"),
            ),
        )
        for name, change in changes:
            with self.subTest(case=name):
                definition, custody, plan = copy.deepcopy(
                    (c.definition, self.transfer_custody, self.plan)
                )
                change(definition, custody, plan)
                try:
                    definition["transfer"]["custody"] = c.f.reference(
                        c.f.write("transfer-custody.json", custody)
                    )
                    record = copy.deepcopy(c.f.record)
                    record["analysis_plan"] = c.f.reference(c.f.write("analysis-plan.json", plan))
                    definition["validation"] = c.f.reference(c.f.write("declaration.json", record))
                    c.declaration.write_bytes(self.json(definition))
                    before = files(c.f.root)
                    funding = {phase: grant.summary() for phase, grant in c.authorities.items()}
                    with (
                        patch.object(
                            self.module,
                            "_prepare_trial_root",
                            side_effect=AssertionError(
                                "invalid declaration reached root publication"
                            ),
                        ) as publish,
                        self.assertRaises(self.Error),
                    ):
                        c.prepare()
                    publish.assert_not_called()
                    self.assertFalse(c.root.exists())
                    self.assertEqual(files(c.f.root), before)
                    self.assertEqual(
                        {phase: grant.summary() for phase, grant in c.authorities.items()}, funding
                    )
                finally:
                    for path, raw in controls.items():
                        path.write_bytes(raw)
        for change in (
            lambda plan: plan.update(format="buddha.validation-analysis-plan.v1"),
            lambda plan: plan.pop("transfer_repetitions"),
            lambda plan: plan["alpha"].update(transfer={"numerator": 0, "denominator": 1}),
        ):
            plan = copy.deepcopy(self.plan)
            change(plan)
            with self.assertRaises(ValidationAnalysisError):
                ValidationAnalysisPlan.from_bytes(self.json(plan))

    def test_importable_dataset_and_unselected_cross_phase_duplicate_refuse_before_owners(self):
        for options in ({"dataset": "separate.py"}, {"extra_member": True}):
            with self.subTest(options=options):
                c = self.fixture(**options)
                before = files(c.f.root)
                funding = {phase: grant.summary() for phase, grant in c.authorities.items()}
                with (
                    patch.object(
                        self.module,
                        "_prepare_trial_root",
                        side_effect=AssertionError("unsafe source reached root publication"),
                    ) as publish,
                    self.assertRaises(self.Error),
                ):
                    c.prepare()
                publish.assert_not_called()
                self.assertFalse(c.root.exists())
                self.assertEqual(files(c.f.root), before)
                self.assertEqual(
                    {phase: grant.summary() for phase, grant in c.authorities.items()}, funding
                )

    def test_joint_freeze_checks_both_capacities_then_poisoned_confirmation_stays_closed(self):
        c = self.fixture()
        before = files(c.f.root)
        funding = {phase: grant.summary() for phase, grant in c.authorities.items()}
        counts = c.engine.workers, c.engine.physical_sends
        for transfer_grant in (self.legacy_grants["final"], c.authorities["final"]):
            with self.subTest(foreign_or_reused=transfer_grant.path):
                grants = c.authorities | {"transfer": transfer_grant}
                with self.assertRaises(self.Error):
                    c.prepare(authorizations=grants)
                self.assertFalse(c.root.exists())
                self.assertEqual(files(c.f.root), before)
                self.assertEqual(
                    {phase: grant.summary() for phase, grant in c.authorities.items()}, funding
                )
                self.assertEqual((c.engine.workers, c.engine.physical_sends), counts)

        c.prepare()
        validation = c.validate()
        before = files(c.f.root)
        funding = {phase: grant.summary() for phase, grant in c.authorities.items()}
        counts = c.engine.workers, c.engine.physical_sends
        original_capacity = self.module.study._capacity
        checked_panels = []

        def transfer_capacity_failure(state, occasion, **kwargs):
            # Both panels run the actual input-capacity calculation. Only the
            # final transfer boundary is faulted; no eligible grid is invented.
            original_capacity(state, occasion, **kwargs)
            checked_panels.append(state["sealed_phase"])
            if state["sealed_phase"] == "transfer":
                raise self.module.study.ValidationStudyError("synthetic transfer capacity refusal")

        with (
            patch.object(self.module.study, "_capacity", side_effect=transfer_capacity_failure),
            self.assertRaises(self.Error),
        ):
            c.freeze(validation)
        self.assertEqual(checked_panels, ["final", "transfer"])
        self.assertFalse((c.root / "freeze").exists())
        self.assertEqual(files(c.f.root), before)
        self.assertEqual(
            {phase: grant.summary() for phase, grant in c.authorities.items()}, funding
        )
        self.assertEqual((c.engine.workers, c.engine.physical_sends), counts)

        original_write = self.module.pipeline._write
        failed_ready = []

        def fail_confirmation(path, raw):
            if path == c.root / "freeze/ready.json":
                # The original schedule and copied sources have actually been
                # published, but the positive confirmation has not.
                self.assertTrue((c.root / "freeze/schedule.json").is_file())
                self.assertEqual(len(list((c.root / "freeze/sources").glob("*.py"))), 2)
                failed_ready.append(True)
                raise OSError("synthetic joint confirmation failure")
            return original_write(path, raw)

        with (
            patch.object(self.module.pipeline, "_write", side_effect=fail_confirmation),
            self.assertRaises(self.Error),
        ):
            c.freeze(validation)
        self.assertEqual(failed_ready, [True])
        freeze = c.root / "freeze"
        self.assertTrue(freeze.is_dir())
        self.assertFalse((freeze / "ready.json").exists())
        schedule = json.loads((freeze / "schedule.json").read_bytes())
        self.assertEqual(schedule["format"], "buddha.sealed-schedule.v2")
        self.assertEqual(set(schedule["panels"]), {"final", "transfer"})
        for phase in ("final", "transfer"):
            self.assertEqual(schedule["panels"][phase]["counts"], {"cells": 2})
            self.assertEqual(list((c.root / phase).rglob("manifest.json")), [])
        after = files(c.f.root)
        self.assertTrue(all(after[name] == raw for name, raw in before.items()))
        self.assertEqual(
            {phase: grant.summary() for phase, grant in c.authorities.items()}, funding
        )
        self.assertEqual((c.engine.workers, c.engine.physical_sends), counts)
        alternate = c.f.reference(c.engine.fixture.roots["official"] / "src/partition.py")
        with (
            patch.dict(os.environ, {}, clear=True),
            patch("buddha.executor.run_container", side_effect=AssertionError("poisoned worker")),
            patch("buddha.gateway.Gateway", side_effect=AssertionError("poisoned Gateway")),
            patch("http.client.HTTPSConnection", side_effect=AssertionError("poisoned provider")),
            patch.object(
                self.module.candidate_generation,
                "prepare_candidate_generation",
                side_effect=AssertionError("replacement owner"),
            ),
            patch.object(
                self.module.native_evaluation,
                "prepare_evaluation",
                side_effect=AssertionError("replacement native owner"),
            ),
        ):
            for action in (
                lambda: c.freeze(validation),
                lambda: c.freeze(validation, finalist_refs=[alternate]),
                c.run_final,
                self.run_transfer,
            ):
                with self.subTest(action=action), self.assertRaises(self.Error):
                    action()
                self.assertEqual(files(c.f.root), after)
        self.assertEqual(
            {phase: grant.summary() for phase, grant in c.authorities.items()}, funding
        )
        self.assertEqual((c.engine.workers, c.engine.physical_sends), counts)


if __name__ == "__main__":
    unittest.main()
