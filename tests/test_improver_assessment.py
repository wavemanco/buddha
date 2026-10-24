"""Real finite/final custody with supplied workers; no selected source host execution.

One positive fixture supplies recovery and passive corruption controls. Null
selection and irreversible first-freeze failure retain separate genuine histories.
"""

import copy
import hashlib
import json
import os
import unittest
from contextlib import ExitStack, contextmanager
from fractions import Fraction
from pathlib import Path
from unittest.mock import patch

from buddha.releases import Selection, _json


def sha(raw):
    return hashlib.sha256(raw).hexdigest()


def ratio(value):
    return {"numerator": value.numerator, "denominator": value.denominator}


def files(root):
    return {path: sha(path.read_bytes()) for path in root.rglob("*") if path.is_file()}


class ImproverAssessmentTests(unittest.TestCase):
    def setUp(self):
        # Honest missing-interface RED occurs before fixtures, SQL or supplied workers.
        from buddha import improver_assessment

        self.api = improver_assessment
        self.Error = improver_assessment.ImproverAssessmentError

    def write(self, name, value):
        path = self.root / name
        path.write_bytes(_json(value))
        return {"path": str(path), "sha256": sha(path.read_bytes())}

    def fixture(self):
        import test_improver_study as finite_fixtures
        import test_source_screen

        from buddha import improver_analysis, improver_study
        from buddha.improvement_rule import ImprovementRule

        original_setup = test_source_screen.SourceScreenTests.setUp

        def sealed_split(h):
            original_setup(h)
            h.record["split"]["partitions"] = {
                "development": ["1"],
                "validation": ["private"],
                "final": [1, "final"],
            }
            h.record["selected_ids"] = ["1"]

        self.f = f = finite_fixtures.FiniteImproverStudyTests("runTest")
        self.addCleanup(f.doCleanups)
        with patch.object(test_source_screen.SourceScreenTests, "setUp", sealed_split):
            f.fixture_before_new_api()
        f.api = improver_study
        self.root, self.engine = f.root, f.engine
        self.finite = f.declaration(improver_study)
        self.finite.update(
            starts=self.finite["starts"][:1], repetitions=1, descendant_opportunities=1
        )
        self.finite["selection"]["finalist_iteration"] = 1
        f.recompute_limits(self.finite)
        f.outcomes.clear()
        self.final_events, self.missing_scalar = [], False
        tasks = f.h.source
        self.tasks_ref = self.write("assessment-tasks.json", tasks.to_record())
        evidence = self.write("assessment-custody-evidence.json", {"kind": "supplied test custody"})
        self.custody = {
            "format": "buddha.validation-custody.v1",
            "process_id": "supplied-improver-process",
            "custodian": "test fixture; no independent scientific attestation",
            "basis": "complete source assigned before any actual trial owner",
            "evidence": [evidence],
            "disclosures": [],
            "population": [
                {
                    "task_id": task.id,
                    "task_sha256": sha(_json(task.to_record())),
                    "family_id": "family-" + str(index),
                    "source": "synthetic",
                    "task_type": "fixture",
                    "phase": "development"
                    if task.id == "1"
                    else "validation"
                    if task.id == "private"
                    else "final",
                    "exposure": "exposed" if task.id == "1" else "eligible",
                }
                for index, task in enumerate(tasks.tasks)
            ],
        }
        self.custody_ref = self.write("assessment-custody.json", self.custody)
        self.rule = ImprovementRule.from_bytes(
            _json(
                {
                    "format": "buddha.improvement-rule.v1",
                    "primary_metric": "utility",
                    "minimum_gain": 0,
                    "max_other_loss": 0,
                }
            )
        )
        rule_ref = self.write("assessment-rule.json", self.rule.to_record())
        self.population = self.numerical_population([1, "final"])
        self.plan = {
            "format": "buddha.improver-analysis-plan.v1",
            "method": "fixed_panel_family_hoeffding_shared_starter.v1",
            "projection_release_sha256": tasks.release_sha256,
            "improvement_rule_sha256": self.rule.fingerprint(),
            "population_sha256": sha(_json(self.population)),
            "counts": {
                "starts": 1,
                "development_repetitions": 1,
                "m": 1,
                "tasks": 2,
                "sealed_repetitions": 1,
            },
            "weights": "equal_conditions_then_equal_prompts",
            "alpha_total": ratio(Fraction(1, 10)),
            "tail_allocations": {
                name: {axis: ratio(Fraction(1, 100)) for axis in ("utility", "distinct")}
                for name in ("initial_gain", "evolved_gain", "improver_effect")
            },
            "analyzer_sources": improver_analysis._source_hashes(),
        }
        plan_ref = self.write("assessment-analysis.json", self.plan)
        improver_analysis.ImproverAnalysisPlan.from_bytes(_json(self.plan))
        development = self.write("assessment-development.json", self.finite)
        generation, native = (
            self.finite["starts"][0]["screen"][name] for name in ("generation", "native")
        )
        cells = 3 * 2
        final_limits = {
            key: cells * (generation[key] + 2 * native[key] + 1)
            for key in ("budget_microusd", "max_calls")
        }
        self.definition = {
            "format": "buddha.improver-assessment-trial.v1",
            "experiment_id": "supplied-sealed-improver-comparison",
            "development": development,
            "tasks": self.tasks_ref,
            "custody": self.custody_ref,
            "final_ids": [1, "final"],
            "sealed_repetitions": 1,
            "generation": copy.deepcopy(generation),
            "native": copy.deepcopy(native),
            "stages": copy.deepcopy(self.finite["starts"][0]["screen"]["stages"]),
            "analysis_plan": plan_ref,
            "improvement_rule": rule_ref,
            "selection_policy": "confirmed_finite_c_only_slots.v1",
            "phase_limits": {
                "search": copy.deepcopy(self.finite["limits"]["study"]),
                "validation": {"budget_microusd": 0, "max_calls": 0},
                "final": final_limits,
            },
            "consumer_sources": self.api._source_hashes(),
        }
        self.bind("assessment")
        return self

    def numerical_population(self, identifiers):
        members = {row["task_id"]: row for row in self.custody["population"]}
        known = {task.id: task for task in self.f.h.source.tasks}
        return {
            "format": "buddha.improver-analysis-population.v1",
            "taskset_sha256": self.f.h.source.fingerprint(),
            "custody_sha256": self.custody_ref["sha256"],
            "tasks": [
                {
                    "task_id": identifier,
                    "family_id": members[identifier]["family_id"],
                    "count": known[identifier].count,
                }
                for identifier in identifiers
            ],
        }

    def bind(self, label, definition=None):
        from buddha.authorization import Authorization
        from buddha.trial_fence import _scope_text, _TrialScope

        self.trial = self.root / label
        self.study = self.trial / "search/study"
        self.declaration = self.root / (label + "-trial.json")
        self.bound_definition = copy.deepcopy(self.definition if definition is None else definition)
        self.declaration.write_bytes(_json(self.bound_definition))
        identity = sha(_json(self.bound_definition))
        self.authorities = {
            phase: Authorization.create(
                self.root / (label + "-" + phase + ".sqlite3"),
                authorization_id="supplied-" + label + "-" + phase,
                scope=_scope_text(_TrialScope(self.trial, identity, phase)),
                **limits,
            )
            for phase, limits in self.bound_definition["phase_limits"].items()
        }
        self.f.expected_common[self.study] = [(0, 0)]

    def prepare(self):
        return self.api.prepare_improver_assessment_trial(
            self.trial,
            declaration=self.declaration,
            expected_sha256=sha(self.declaration.read_bytes()),
            expected_runtime_sha256=self.engine.candidate.expected_runtime,
            authorizations=self.authorities,
            development_review=self.engine.fixture.review,
        )

    @contextmanager
    def supplied(self):
        import test_improver_study as finite_fixtures

        original_source = finite_fixtures.source

        def equal_counted_source(label):
            return original_source(
                "OWN-C-same-bytes-in-two-roles" if label.startswith("OWN-C-") else label
            )

        with (
            self.f.supplied(),
            patch.object(finite_fixtures, "source", side_effect=equal_counted_source),
            patch("buddha.executor.run_container", side_effect=self.execute),
        ):
            yield

    def execute(self, spec, *, initial, handle, **kwargs):
        session = handle.__self__
        owner = session.gateway.directory
        if not owner.is_relative_to(self.trial / "final"):
            return self.f.execute(spec, initial=initial, handle=handle, **kwargs)
        self.assertNotIn("improvement", initial["format"])
        self.assertNotIn(b"dataset_base64", _json(initial))
        arm = self.schedule["arms"][int(owner.relative_to(self.trial / "final").parts[1])]
        self.final_events.append((str(owner), spec.role, arm["role"], copy.deepcopy(initial)))
        e = self.engine
        if spec.role == "agent":
            self.assertIn(initial["task"]["id"], [1, "final"])
            e.candidate.tasks = session.tasks
            e.candidate.record["config"] = copy.deepcopy(initial["config"])
            manifest = json.loads((owner / "manifest.json").read_bytes())
            e.fixture.selection = Selection.from_bytes(_json(manifest["selection"]))
            e.directory = session.output.parents[2]
            e.callbacks = 1
            e.weak_answers = (
                ["1", "2"] if initial["task"]["id"] == 1 else ["sealed first", "sealed second"]
            )
            return e.execute(spec, initial=initial, handle=handle, **kwargs)
        e.directory = owner.parents[2] / "generation"

        def native_row(row, stage):
            quality = {"starter": 5, "initial": 6, "evolved": 8}[arm["role"]]
            row.update(partition=[0, 1], distinct=2)
            row.pop("score", None)
            if stage == 1:
                row.update(
                    generation_scores=[quality, quality],
                    partition_scores=[quality, quality],
                    utility=None if self.missing_scalar and arm["role"] == "starter" else quality,
                )
            return row

        with patch.object(e, "native_row", side_effect=native_row):
            return e.execute(spec, initial=initial, handle=handle, **kwargs)

    def develop(self):
        with self.supplied():
            self.development = self.f.api.run_improver_study(
                self.study, transport=self.f.transport()
            )
        self.assertEqual(self.development["status"], "complete")
        return self.development

    def freeze(self):
        self.schedule = self.api.freeze_improver_descendants(
            self.trial,
            expected_development_report_sha256=sha((self.study / "report.json").read_bytes()),
            review=self.engine.fixture.review,
        )
        return self.schedule

    def run_assessment(self):
        return self.api.run_improver_assessment(
            self.trial,
            authorization=self.authorities["final"],
            review=self.engine.fixture.review,
            transport=self.f.transport(),
        )

    def inspect(self):
        return self.api.inspect_improver_assessment(
            self.trial, expected_report_sha256=sha((self.trial / "final/report.json").read_bytes())
        )

    def test_real_prospective_shared_starter_grid_recovery_and_passive_integrity(self):
        from buddha import candidate_generation, improver_analysis
        from buddha.gateway import prepare_gateway

        self.fixture()
        self.assertEqual(self.prepare(), self.trial)
        self.develop()
        for event in self.f.improvements:
            for sentinel in (
                b"VALIDATION-ONLY-SENTINEL",
                b"FINAL-ONLY-SENTINEL",
                b"dataset_base64",
            ):
                self.assertNotIn(sentinel, _json(event["feedback"]))
        schedule = self.freeze()
        self.assertEqual(
            schedule["counts"],
            {
                "cells": 6,
                "maximum_cells": 6,
                "conditions": 1,
                "descendant_slots": 2,
                "no_valid_descendant_slots": 0,
            },
        )
        self.assertEqual(
            [arm["role"] for arm in schedule["arms"]], ["starter", "initial", "evolved"]
        )
        self.assertEqual(schedule["arms"][1]["sha256"], schedule["arms"][2]["sha256"])
        original_improvements = len(self.f.improvements)
        original = candidate_generation.run_candidate_generation
        stopped = []

        def stop_after_known_generation(*args, **kwargs):
            result = original(*args, **kwargs)
            if not stopped and Path(args[0]).is_relative_to(self.trial / "final"):
                self.assertEqual(result["status"], "complete")
                stopped.append(True)
                raise KeyboardInterrupt
            return result

        with (
            self.supplied(),
            patch.object(
                candidate_generation,
                "run_candidate_generation",
                side_effect=stop_after_known_generation,
            ),
            self.assertRaises(KeyboardInterrupt),
        ):
            self.run_assessment()
        self.assertTrue(stopped)
        retained = {
            path: path.read_bytes()
            for path in (self.trial / "final").rglob("*")
            if path.is_file()
            and (
                path.name in {"manifest.json", "operations.sqlite3", "report.json"}
                or path.parent.name == "completed"
            )
        }
        self.assertTrue(retained)
        self.final_events.clear()
        with self.supplied():
            result = self.run_assessment()
        self.assertTrue(all(path.read_bytes() == raw for path, raw in retained.items()))
        old_owners = {str(path.parent) for path in retained if path.name == "manifest.json"}
        self.assertTrue(all(owner not in old_owners for owner, *_ in self.final_events))
        self.assertEqual(
            (result["format"], result["status"]),
            ("buddha.improver-assessment-report.v1", "complete"),
        )
        self.assertEqual(result["coverage"]["evaluated"], 6)
        self.assertEqual(len(result["cells"]), 6)
        self.assertEqual(len(result["slots"]), 2)
        self.assertTrue(result["analysis"]["coverage"]["complete"])
        self.assertEqual(
            result["analysis"]["contrasts"]["improver_effect"]["utility"]["point"],
            ratio(Fraction(2)),
        )
        self.assertEqual(len(self.f.improvements), original_improvements)
        self.assertEqual(len(self.f.owner_paths(self.trial / "final")), 24)
        self.assertEqual(self.authorities["final"].summary()["reserved_microusd"], 0)
        required = {self.declaration: sha(self.declaration.read_bytes())}
        required.update(
            {
                self.trial / name: sha((self.trial / name).read_bytes())
                for name in (
                    ".buddha-evaluation-trial.json",
                    "definition.json",
                    "context.json",
                    "funding.json",
                )
            }
        )
        for owner in self.f.owner_paths(self.trial / "search") | self.f.owner_paths(
            self.trial / "final"
        ):
            bindings = {
                row["path"]: row["sha256"]
                for row in json.loads((owner / "manifest.json").read_bytes())["invocation"][
                    "inputs"
                ]
            }
            self.assertTrue(
                all(bindings.get(str(path)) == digest for path, digest in required.items())
            )
        before = files(self.root), self.engine.physical_sends
        with ExitStack() as stack:
            stack.enter_context(patch.dict(os.environ, {}, clear=True))
            for target in (
                "buddha.authorization.Authorization.__init__",
                "buddha.gateway.Gateway.__init__",
                "buddha.executor.run_container",
                "buddha.trial_fence.lease",
            ):
                stack.enter_context(
                    patch(
                        target, side_effect=AssertionError("passive read invoked writer or worker")
                    )
                )
            self.assertEqual(self.inspect(), result)
            self.assertEqual(
                self.api.inspect_improver_assessment_freeze(
                    self.trial,
                    expected_schedule_sha256=sha(
                        (self.trial / "freeze/schedule.json").read_bytes()
                    ),
                ),
                schedule,
            )
            self.assertEqual(self.freeze(), schedule)
        self.assertEqual((files(self.root), self.engine.physical_sends), before)
        native_reports = [
            self.trial / "final/arms" / str(arm) / "tasks/1/repetitions/0/evaluation/report.json"
            for arm in range(3)
        ]
        for corrupt in ([self.declaration], native_reports):
            saved = {path: path.read_bytes() for path in corrupt}
            try:
                for path in corrupt:
                    path.unlink()
                with (
                    patch.object(
                        improver_analysis.bounds,
                        "_hoeffding_lower_bound",
                        side_effect=AssertionError("invalid custody reached arithmetic"),
                    ),
                    self.assertRaises(self.Error),
                ):
                    self.inspect()
            finally:
                for path, raw in saved.items():
                    path.write_bytes(raw)
        self.assertEqual((files(self.root), self.engine.physical_sends), before)
        final = self.authorities["final"]
        original_owner = json.loads(
            (
                self.trial / "final/arms/0/tasks/0/repetitions/0/generation/owners/0/manifest.json"
            ).read_bytes()
        )
        original_inputs = {
            Path(row["path"]): row["sha256"] for row in original_owner["invocation"]["inputs"]
        }
        with self.assertRaisesRegex(ValueError, "checked original consumer episode"):
            prepare_gateway(
                self.trial / "final/foreign",
                selection=Selection.from_bytes(_json(original_owner["selection"])),
                roots={role: Path(path) for role, path in original_owner["roots"].items()},
                authorization=final,
                **original_owner["settings"],
                input_files=list(original_inputs),
                expected_input_hashes=original_inputs,
                review=original_owner["review"],
            )
        self.assertFalse((self.trial / "final/foreign").exists())
        self.assertEqual((files(self.root), self.engine.physical_sends), before)

    def test_completed_assessment_replays_after_original_producer_sources_retire(self):
        from buddha import candidate_generation
        from buddha.gateway import RawHTTPTransport

        self.fixture()
        self.f.outcomes.update({(0, 0, arm, 0): "rejected" for arm in range(2)})
        original = self.trial, self.study, self.declaration, self.bound_definition, self.authorities
        self.bind("fresh-retirement-assessment")
        fresh_root, fresh_declaration, fresh_authorities = (
            self.trial,
            self.declaration,
            self.authorities,
        )
        self.trial, self.study, self.declaration, self.bound_definition, self.authorities = original
        self.prepare()
        self.develop()
        schedule = self.freeze()
        self.assertEqual(schedule["selected_ids"], [1, "final"])
        self.assertEqual(schedule["counts"]["cells"], 2)
        self.assertEqual(schedule["counts"]["maximum_cells"], 6)
        self.assertEqual([arm["role"] for arm in schedule["arms"]], ["starter"])
        self.assertEqual(
            [slot["status"] for slot in schedule["slots"]], ["no_valid_descendant"] * 2
        )

        def snapshot():
            return (
                files(self.root),
                tuple(sorted(str(path.relative_to(self.root)) for path in self.root.rglob("*"))),
                [
                    authority.summary()
                    for group in (self.authorities, fresh_authorities)
                    for authority in group.values()
                ],
                self.engine.physical_sends,
                self.engine.workers,
                len(self.f.events),
                len(self.f.improvements),
                len(self.f.generated),
                len(self.final_events),
            )

        @contextmanager
        def retired_producers():
            retired = []
            try:
                for name in ("I0", "I1", "S0", "S1"):
                    source, destination = self.root / name, self.root / (name + "-retired")
                    source.rename(destination)
                    retired.append((source, destination))
                before = snapshot()
                with (
                    self.f.h.readonly(),
                    patch.dict(os.environ, {}, clear=True),
                    ExitStack() as stack,
                ):
                    for target in (
                        "buddha.trial_fence.lease",
                        "buddha.trial_fence.work",
                        "buddha.native_pipeline._exclusive",
                    ):
                        stack.enter_context(
                            patch(target, side_effect=AssertionError("retirement reached writer"))
                        )
                    yield
                self.assertEqual(snapshot(), before)
            finally:
                for source, destination in reversed(retired):
                    destination.rename(source)

        original_generation = candidate_generation.run_candidate_generation
        stopped = []

        def stop_after_first_final_generation(*args, **kwargs):
            result = original_generation(*args, **kwargs)
            if not stopped and Path(args[0]).is_relative_to(self.trial / "final"):
                self.assertEqual(result["status"], "complete")
                stopped.append(True)
                raise KeyboardInterrupt
            return result

        with (
            self.supplied(),
            patch.object(
                candidate_generation,
                "run_candidate_generation",
                side_effect=stop_after_first_final_generation,
            ),
            self.assertRaises(KeyboardInterrupt),
        ):
            self.run_assessment()
        self.assertTrue(stopped)
        self.assertFalse((self.trial / "final/report.json").exists())
        with retired_producers():
            # Missing original controls still stop unfinished and fresh work.
            with self.assertRaises(self.Error):
                self.run_assessment()
            with self.assertRaises(self.Error):
                self.api.prepare_improver_assessment_trial(
                    fresh_root,
                    declaration=fresh_declaration,
                    expected_sha256=sha(fresh_declaration.read_bytes()),
                    expected_runtime_sha256=self.engine.candidate.expected_runtime,
                    authorizations=fresh_authorities,
                    development_review=self.engine.fixture.review,
                )
            self.assertFalse(fresh_root.exists())

        with self.supplied():
            result = self.run_assessment()
        self.assertEqual(result["status"], "complete")
        self.assertEqual(result["coverage"]["evaluated"], 2)
        self.assertEqual(result["analysis"]["coverage"]["null_slots"], 2)
        self.assertEqual(result["analysis"]["rule"]["status"], "inconclusive")
        with retired_producers():
            self.assertEqual(self.inspect(), result)
            self.assertEqual(
                self.api.inspect_improver_assessment_freeze(
                    self.trial,
                    expected_schedule_sha256=sha(
                        (self.trial / "freeze/schedule.json").read_bytes()
                    ),
                ),
                schedule,
            )
            self.assertEqual(self.freeze(), schedule)
            self.assertEqual(
                self.api.run_improver_assessment(
                    self.trial,
                    authorization=self.authorities["final"],
                    review=self.engine.fixture.review,
                    transport=RawHTTPTransport(allow_paid=False),
                ),
                result,
            )
            retained_source = self.trial / "freeze/sources/0.py"
            raw = retained_source.read_bytes()
            try:
                retained_source.write_bytes(raw + b"\n# changed retained source\n")
                with self.assertRaises(self.Error):
                    self.inspect()
            finally:
                retained_source.write_bytes(raw)

    def test_genuine_null_descendant_and_undefined_scalar_preserve_planned_comparison(self):
        self.fixture()
        self.f.outcomes[(0, 0, 0, 0)] = "failed"
        self.prepare()
        self.develop()
        schedule = self.freeze()
        self.assertEqual(
            schedule["counts"],
            {
                "cells": 4,
                "maximum_cells": 6,
                "conditions": 1,
                "descendant_slots": 2,
                "no_valid_descendant_slots": 1,
            },
        )
        self.assertEqual(
            [row["status"] for row in schedule["slots"]], ["no_valid_descendant", "selected"]
        )
        self.assertEqual([arm["role"] for arm in schedule["arms"]], ["starter", "evolved"])
        self.missing_scalar = True
        with self.supplied():
            result = self.run_assessment()
        self.assertEqual(result["status"], "complete")
        self.assertEqual(result["coverage"]["evaluated"], 4)
        analysis = result["analysis"]
        self.assertEqual(analysis["coverage"]["maximum_rows"], 6)
        self.assertEqual(analysis["coverage"]["null_slots"], 1)
        self.assertFalse(analysis["coverage"]["complete"])
        self.assertEqual(analysis["rule"]["status"], "inconclusive")
        self.assertIsNone(analysis["contrasts"]["improver_effect"]["utility"]["point"])
        self.assertIsNone(analysis["contrasts"]["evolved_gain"]["utility"]["point"])
        self.assertEqual(analysis["tail_allocations"], self.plan["tail_allocations"])
        self.assertEqual(self.inspect(), result)
        self.assertEqual(self.authorities["final"].summary()["reserved_microusd"], 0)

    def test_conflicting_explicit_source_pins_refuse_before_new_study_work(self):
        from buddha import trial_fence

        self.fixture()
        self.prepare()
        generation = self.finite["starts"][0]["screen"]["generation"]
        sources = {
            "starter": Path(generation["roots"]["agent"]) / "candidate.py",
            "runtime": Path(generation["runtime"]["path"]),
            **{
                "improver-" + str(index): Path(actor["roots"]["agent"]) / actor["entrypoint"]
                for index, actor in enumerate(self.finite["improvers"])
            },
        }
        for label, path in sources.items():
            destination = self.trial / "search" / ("conflicting-" + label)
            before = (
                files(self.root),
                self.engine.physical_sends,
                self.authorities["search"].summary(),
            )
            with (
                self.subTest(explicit_binding=label),
                patch.object(
                    trial_fence,
                    "lease",
                    side_effect=AssertionError("conflicting pin reached writer"),
                ),
                self.assertRaises(self.f.api.ImproverStudyError),
            ):
                self.f.api.prepare_improver_study(
                    destination,
                    declaration=Path(self.bound_definition["development"]["path"]),
                    expected_sha256=self.bound_definition["development"]["sha256"],
                    authorization=self.authorities["search"],
                    review=self.engine.fixture.review,
                    expected_runtime_sha256=self.engine.candidate.expected_runtime,
                    input_bindings={path: "0" * 64},
                )
            self.assertFalse(destination.exists())
            self.assertEqual(
                (
                    files(self.root),
                    self.engine.physical_sends,
                    self.authorities["search"].summary(),
                ),
                before,
            )

    def test_preparation_projects_finite_inputs_and_all_maximum_frozen_copies(self):
        from buddha import validation_study

        self.fixture()
        extra = self.root / "separate-original-finite-input.json"
        extra.write_bytes(_json({"kind": "additional original finite metadata"}))
        finite = copy.deepcopy(self.finite)
        finite["consumer_sources"][str(extra)] = sha(extra.read_bytes())
        definition = copy.deepcopy(self.definition)
        definition["development"] = self.write("capacity-development.json", finite)
        self.bind("capacity-envelope", definition)
        generation = finite["starts"][0]["screen"]["generation"]
        required = {
            extra,
            Path(generation["runtime"]["path"]),
            Path(generation["roots"]["agent"]) / "candidate.py",
            *[Path(name) for name in finite["consumer_sources"]],
            *[Path(actor["roots"]["agent"]) / actor["entrypoint"] for actor in finite["improvers"]],
            *[self.trial / "freeze/sources" / (str(index) + ".py") for index in range(3)],
        }
        before = files(self.root), self.authorities["search"].summary()

        def check_envelope(state, occasion, *, receipts=None):
            envelope = {Path(name) for name in occasion["controls"]} | set(receipts or {})
            self.assertTrue(required <= envelope, sorted(str(p) for p in required - envelope))
            self.assertFalse(self.trial.exists())
            self.assertEqual(self.authorities["search"].summary()["runs"], [])
            raise AssertionError("complete capacity projection before first trial write")

        with (
            patch.object(validation_study, "_capacity", side_effect=check_envelope) as checking,
            self.assertRaisesRegex(
                AssertionError, "complete capacity projection before first trial write"
            ),
        ):
            self.prepare()
        checking.assert_called_once()
        self.assertFalse(self.trial.exists())
        self.assertEqual((files(self.root), self.authorities["search"].summary()), before)

    def test_unsupported_prospective_inputs_refuse_and_first_freeze_failure_stays_poisoned(self):
        from buddha import native_pipeline, source_screen

        self.fixture()
        for case in ("unknown_method", "omitted_final", "wrong_source", "insufficient_final"):
            definition = copy.deepcopy(self.definition)
            if case == "unknown_method":
                plan = copy.deepcopy(self.plan)
                plan["method"] = "not-implemented"
                definition["analysis_plan"] = self.write("bad-method.json", plan)
            elif case == "omitted_final":
                definition["final_ids"] = [1]
                plan = copy.deepcopy(self.plan)
                plan["counts"]["tasks"] = 1
                plan["population_sha256"] = sha(_json(self.numerical_population([1])))
                definition["analysis_plan"] = self.write("bad-final-subset.json", plan)
            elif case == "wrong_source":
                definition["consumer_sources"]["buddha/improver_assessment.py"] = "0" * 64
            else:
                definition["phase_limits"]["final"]["budget_microusd"] -= 1
                definition["phase_limits"]["final"]["max_calls"] -= 1
            self.bind("bad-" + case.replace("_", "-"), definition)
            before = files(self.root), self.engine.physical_sends
            with self.subTest(case=case), self.assertRaises(self.Error):
                self.prepare()
            self.assertFalse(self.trial.exists())
            self.assertEqual((files(self.root), self.engine.physical_sends), before)
        self.bind("poisoned-assessment")
        self.prepare()
        self.develop()
        original = native_pipeline._write

        def fail_ready(path, raw):
            if path == self.trial / "freeze/ready.json":
                raise OSError("supplied first-freeze confirmation failure")
            return original(path, raw)

        with (
            patch.object(native_pipeline, "_write", side_effect=fail_ready),
            self.assertRaises(self.Error),
        ):
            self.freeze()
        self.assertTrue((self.trial / "freeze/schedule.json").is_file())
        self.assertFalse((self.trial / "freeze/ready.json").exists())
        before = files(self.root), self.engine.physical_sends
        with self.assertRaises(self.Error):
            self.freeze()
        with self.assertRaises(self.Error):
            self.run_assessment()
        with self.assertRaises(ValueError):
            source_screen.prepare_source_screen(
                self.trial / "search/forbidden",
                screen=self.f.base,
                authorization=self.authorities["search"],
                review=self.engine.fixture.review,
                expected_runtime_sha256=self.engine.candidate.expected_runtime,
            )
        self.assertEqual((files(self.root), self.engine.physical_sends), before)
        self.assertEqual(self.authorities["final"].summary()["operation_count"], 0)

    def test_outer_consumed_roles_override_retirable_producer_classification(self):
        import copy
        import hashlib
        import shutil
        from pathlib import Path
        from tempfile import TemporaryDirectory

        from buddha.releases import _json, prepare_selection

        self.fixture()

        def snapshot():
            return (
                {
                    path: hashlib.sha256(path.read_bytes()).hexdigest()
                    for path in self.root.rglob("*")
                    if path.is_file()
                },
                tuple(sorted(str(path.relative_to(self.root)) for path in self.root.rglob("*"))),
                [authority.summary() for authority in self.authorities.values()],
                self.engine.physical_sends,
                self.engine.workers,
                len(self.f.events),
                len(self.f.improvements),
                len(self.f.generated),
            )

        before = snapshot()
        release = self.engine.candidate.release
        runtime = self.engine.candidate.expected_runtime
        original_actor = self.finite["improvers"][0]
        original_source = Path(original_actor["roots"]["agent"]) / original_actor["entrypoint"]
        source_raw = original_source.read_bytes()
        runtime_raw = Path(self.definition["generation"]["runtime"]["path"]).read_bytes()

        for case in (
            "generation-runtime",
            "generation-runner",
            "native-runner",
            "native-runner-parent-spelling",
        ):
            with self.subTest(consumed_role=case), TemporaryDirectory(dir=self.root) as temporary:
                temporary_root = Path(temporary)
                definition = copy.deepcopy(self.definition)
                finite = copy.deepcopy(self.finite)
                if case == "generation-runtime":
                    actor_root = temporary_root / "runtime-producer"
                    actor_root.mkdir()
                    alias = actor_root / "candidate.py"
                    # Fixed-I source is permitted literal UTF-8 data here; no selected
                    # program is imported, compiled or executed by this test.
                    alias.write_bytes(runtime_raw)
                    outer = definition["generation"]
                    outer["roots"]["environment"] = str(actor_root)
                    outer["runtime"] = {"path": str(alias), "sha256": runtime}
                else:
                    role = "generation" if case == "generation-runner" else "native"
                    outer = definition[role]
                    runner = temporary_root / "selected-runner"
                    shutil.copytree(Path(outer["roots"]["runner"]), runner)
                    actor_root = runner / "fixed-improver"
                    actor_root.mkdir()
                    alias = actor_root / "candidate.py"
                    alias.write_bytes(source_raw)
                    outer["roots"]["runner"] = str(runner)
                    if case == "native-runner-parent-spelling":
                        (runner / "existing").mkdir()
                        outer["roots"]["runner"] = str(runner / "existing" / "..")

                actor = finite["improvers"][0]
                actor["roots"]["agent"] = str(actor_root)
                actor["selection"] = prepare_selection(
                    release,
                    {key: Path(value) for key, value in actor["roots"].items()},
                    capabilities=actor["selection"]["capabilities"],
                ).to_record()
                outer["selection"] = prepare_selection(
                    release,
                    {key: Path(value) for key, value in outer["roots"].items()},
                    capabilities=outer["selection"]["capabilities"],
                ).to_record()
                if not case.startswith("native-runner"):
                    outer["executor"]["mounts"] = [
                        ["/agent", outer["roots"]["agent"]],
                        ["/runner", outer["roots"]["runner"]],
                    ]
                declaration = temporary_root / "development.json"
                declaration.write_bytes(_json(finite))
                definition["development"] = {
                    "path": str(declaration),
                    "sha256": hashlib.sha256(declaration.read_bytes()).hexdigest(),
                }

                # All actual declaration, selection, runtime, profile and native
                # checks remain enabled. No classification result is mocked.
                with self.f.h.readonly():
                    state = self.api._definition(_json(definition), runtime, active=False)
                self.assertEqual(
                    state["controls"][alias], hashlib.sha256(alias.read_bytes()).hexdigest()
                )
                self.assertNotIn(alias, state["retirable_producers"])
                other_actor = self.finite["improvers"][1]
                other_source = Path(other_actor["roots"]["agent"]) / other_actor["entrypoint"]
                self.assertIn(other_source, state["retirable_producers"])
                self.assertEqual(state["record"]["final_ids"], [1, "final"])
                self.assertFalse(self.trial.exists())

        self.assertEqual(snapshot(), before)


if __name__ == "__main__":
    unittest.main()
