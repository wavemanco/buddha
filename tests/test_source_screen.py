"""Common source screening: real saved custody, mocked workers and HTTPS only."""

import copy
import hashlib
import json
import os
import shutil
import unittest
from contextlib import contextmanager
from pathlib import Path
from unittest.mock import patch

import test_candidate_generation as generation_fixtures
import test_gateway as gateway_fixtures

from buddha.answers import TaskSet
from buddha.authorization import Authorization
from buddha.gateway import RawHTTPTransport
from buddha.releases import Release, Selection, _json, inventory, prepare_selection


def sha(raw):
    return hashlib.sha256(raw).hexdigest()


class SourceScreenTests(unittest.TestCase):
    def setUp(self):
        # A missing public API is one setup/import error, not a behavioral failure.
        from buddha.source_screen import (
            SourceScreen,
            SourceScreenError,
            inspect_source_screen,
            prepare_source_screen,
            run_source_screen,
            select_source_parent,
        )

        self.Screen, self.Error = SourceScreen, SourceScreenError
        self.prepare_api, self.run_api = prepare_source_screen, run_source_screen
        self.inspect_api, self.select_api = inspect_source_screen, select_source_parent
        self.engine = e = generation_fixtures.CandidateGenerationTests("runTest")
        e.setUp()
        self.addCleanup(e.doCleanups)
        self.root = e.root
        self.rows = [
            {"id": 1, "prompt": "Give one digit, literally."},
            {"id": "1", "prompt": "Write one short greeting."},
            {"id": "private", "prompt": "VALIDATION-ONLY-SENTINEL"},
            {"id": "final", "prompt": "FINAL-ONLY-SENTINEL"},
        ]
        dataset = b"".join(_json(row) + b"\n" for row in self.rows)
        f = e.fixture
        (f.roots["official"] / "data/tasks.jsonl").write_bytes(dataset)
        f.release_record["source"] = inventory(f.roots["official"])
        release = Release.from_record(f.release_record)
        self.source = TaskSet.from_dataset(release, dataset)
        e.candidate.release = release
        e.candidate.tasks = self.source.select(["1"])
        e.candidate.task_path.write_bytes(e.candidate.tasks.to_bytes())
        f.selection = prepare_selection(
            release, f.roots, capabilities={gateway_fixtures.CAPABILITY: "profiles/openai.json"}
        )
        native_roots = {name: Path(path) for name, path in e.native["roots"].items()}
        e.native["selection"] = prepare_selection(
            release,
            native_roots,
            capabilities={gateway_fixtures.CAPABILITY: "profiles/openai.json"},
        ).to_record()
        generation = {
            name: copy.deepcopy(value)
            for name, value in e.candidate.record.items()
            if name not in {"format", "tasks"}
        }
        generation.update(
            selection=f.selection.to_record(),
            roots={name: str(path) for name, path in f.roots.items()},
            budget_microusd=10_000,
            max_calls=20,
        )
        self.record = {
            "format": "buddha.source-screen.v1",
            "source": self.source.to_record(),
            "split": {
                "release_sha256": self.source.release_sha256,
                "dataset_sha256": self.source.dataset_sha256,
                "partitions": {
                    "development": [1, "1"],
                    "validation": ["private"],
                    "final": ["final"],
                },
                "families": [
                    {"id": task.id, "family": "family-" + str(index)}
                    for index, task in enumerate(self.source.tasks)
                ],
            },
            "selected_ids": ["1", 1],
            "generation": generation,
            "native": copy.deepcopy(e.native),
            "stages": copy.deepcopy(e.stages),
            "projection": "noveltybench-1.1",
            "lineage": None,
        }
        self.programs = {}
        self.authorities = []
        self.generation_events = []
        self.native_events = []
        self.unusable_task = None

    def screen(self, record=None):
        value = copy.deepcopy(self.record if record is None else record)
        screen = self.Screen.from_bytes(_json(value))
        self.programs[screen.candidate_id] = {
            "record": value,
            "callbacks": 0,
            "answers": ["  unchanged weak text  ", ""],
            "distinct": 2,
            "utility": 7,
        }
        return screen

    def second_source(self):
        record = copy.deepcopy(self.record)
        agent = self.root / "second-source"
        agent.mkdir()
        (agent / "candidate.py").write_bytes(
            b'def generate(task, config, complete):\n    return ["same", "same"]\n'
        )
        roots = {name: Path(path) for name, path in record["generation"]["roots"].items()}
        roots["agent"] = agent
        record["generation"]["roots"] = {name: str(path) for name, path in roots.items()}
        record["generation"]["selection"] = prepare_selection(
            self.engine.candidate.release,
            roots,
            capabilities={gateway_fixtures.CAPABILITY: "profiles/openai.json"},
        ).to_record()
        record["generation"]["executor"]["mounts"] = [
            ["/agent", str(agent)],
            ["/runner", str(roots["runner"])],
        ]
        return record

    def authority(self, screen):
        authority = Authorization.create(
            self.root / ("screen-authority-" + str(len(self.authorities)) + ".sqlite3"),
            authorization_id="offline-screen-" + str(len(self.authorities)),
            budget_microusd=1_000_000,
            max_calls=1000,
            scope="source screen: " + screen.comparison_key(),
        )
        self.authorities.append(authority)
        return authority

    def prepare(self, screen, directory=None, authority=None, **changes):
        directory = directory or self.root / "screen-first"
        authority = authority or self.authority(screen)
        values = {
            "screen": screen,
            "authorization": authority,
            "review": self.engine.fixture.review,
            "expected_runtime_sha256": self.engine.candidate.expected_runtime,
        }
        self.prepare_api(directory, **(values | changes))
        return directory, authority

    def execute(self, spec, *, initial, handle, **kwargs):
        session = handle.__self__
        e = self.engine
        if spec.role == "agent":
            task = next(task for task in self.source.tasks if task.id == initial["task"]["id"])
            self.assertIn(task.id, self.record["selected_ids"])
            self.assertEqual(initial["task"], task.to_record())
            self.assertEqual({target for target, _ in spec.mounts}, {"/agent", "/runner"})
            for private in (b"VALIDATION-ONLY-SENTINEL", b"FINAL-ONLY-SENTINEL", b"dataset_base64"):
                self.assertNotIn(private, _json(initial))
            program = self.programs[initial["agent_sha256"]]
            self.assertEqual(initial["config"], program["record"]["generation"]["config"])
            self.generation_events.append((initial["agent_sha256"], copy.deepcopy(initial["task"])))
            # The original fixture consumes this checked current task/selection.
            e.candidate.tasks = session.tasks
            e.candidate.record["config"] = copy.deepcopy(initial["config"])
            e.fixture.selection = Selection.from_bytes(
                _json(program["record"]["generation"]["selection"])
            )
            e.directory = session.output.parents[1]
            e.callbacks, e.weak_answers = program["callbacks"], program["answers"]
            return e.execute(spec, initial=initial, handle=handle, **kwargs)
        e.directory = session.gateway.directory.parents[2] / "generation"
        answer_record = e.answers().to_record()
        program = self.programs[answer_record["agent_sha256"]]
        task_id = answer_record["outputs"][0]["task_id"]
        self.native_events.append(
            (answer_record["agent_sha256"], task_id, initial["command"]["index"])
        )

        def finite_row(row, index):
            # Synthetic literal saved measurements, not host benchmark math.
            row["partition"] = [0, 1] if program["distinct"] == 2 else [0, 0]
            row["distinct"] = program["distinct"]
            row.pop("score", None)
            if index == 1:
                row["generation_scores"] = [7, 7] if program["distinct"] == 2 else [7, None]
                row["partition_scores"] = [7, 7] if program["distinct"] == 2 else [7]
                row["utility"] = program["utility"]
                if row["id"] == self.unusable_task:
                    row["utility"] = float("nan")
            return row

        with patch.object(e, "native_row", side_effect=finite_row):
            return e.execute(spec, initial=initial, handle=handle, **kwargs)

    def run_screen(self, directory, *, paid=True):
        with (
            patch.dict(
                os.environ, {"OPENAI_API_KEY": gateway_fixtures.KEY} if paid else {}, clear=True
            ),
            patch("buddha.executor.run_container", side_effect=self.execute),
            patch("http.client.HTTPSConnection", side_effect=AssertionError("unexpected HTTPS")),
            patch(
                "buddha.agent_run.AgentSession", side_effect=AssertionError("fixed seed forbidden")
            ),
        ):
            return self.run_api(directory, transport=RawHTTPTransport(allow_paid=paid))

    @staticmethod
    def files(directory):
        return {
            path.relative_to(directory).as_posix(): sha(path.read_bytes())
            for path in directory.rglob("*")
            if path.is_file()
        }

    def reference(self, directory, authority):
        return {
            "directory": str(directory),
            "authorization": str(authority.path),
            "report_sha256": sha((directory / "report.json").read_bytes()),
        }

    @contextmanager
    def readonly(self):
        with (
            patch(
                "buddha.gateway.Gateway.__init__", side_effect=AssertionError("Gateway constructed")
            ),
            patch(
                "buddha.authorization.Authorization.__init__",
                side_effect=AssertionError("authority constructed"),
            ),
            patch(
                "buddha.candidate_run.CandidateSession",
                side_effect=AssertionError("producer constructed"),
            ),
            patch(
                "buddha.native_run.NativeSession",
                side_effect=AssertionError("native worker constructed"),
            ),
            patch("buddha.executor.run_container", side_effect=AssertionError("worker executed")),
            patch("http.client.HTTPSConnection", side_effect=AssertionError("HTTPS constructed")),
        ):
            yield

    def inspect(self, directory, authority):
        before = self.files(directory), sha(authority.path.read_bytes()), self.engine.physical_sends
        with self.readonly():
            result = self.inspect_api(
                directory,
                authorization=authority.path,
                expected_report_sha256=sha((directory / "report.json").read_bytes()),
            )
        self.assertEqual(
            (self.files(directory), sha(authority.path.read_bytes()), self.engine.physical_sends),
            before,
        )
        return result

    def test_development_screen_preserves_typed_order_literal_source_and_fresh_views(self):
        screen = self.screen()
        self.assertEqual([task.id for task in screen.tasks.tasks], ["1", 1])
        self.assertEqual(
            [task.prompt for task in screen.tasks.tasks],
            [self.rows[1]["prompt"], self.rows[0]["prompt"]],
        )
        self.assertEqual([task.count for task in screen.tasks.tasks], [2, 2])
        self.assertEqual(screen.candidate_id, self.engine.fixture.selection.agent_sha256)
        self.assertEqual(screen.to_record()["source"], self.source.to_record())
        changed = screen.to_record()
        changed["selected_ids"].reverse()
        changed["generation"]["config"]["instructions"] = "not the original"
        self.assertEqual(screen.to_record(), self.record)
        self.assertEqual(
            self.Screen.from_bytes(screen.to_bytes()).fingerprint(), screen.fingerprint()
        )

    def test_full_source_split_and_development_membership_are_not_scalar_claims(self):
        bad = []
        for selected in (["final"], ["private"], [True], [1, 1], ["missing"]):
            record = copy.deepcopy(self.record)
            record["selected_ids"] = selected
            bad.append(record)
        record = copy.deepcopy(self.record)
        record["source"] = self.source.select(["1", 1]).to_record()
        bad.append(record)
        record = copy.deepcopy(self.record)
        record["split"]["families"][0]["family"] = record["split"]["families"][-1]["family"]
        bad.append(record)
        for index, record in enumerate(bad):
            with self.subTest(index=index), self.assertRaises(self.Error):
                self.screen(record)
        self.assertEqual(self.engine.physical_sends, 0)

    def test_comparison_changes_controls_but_excludes_agent_identity_and_bound_root_locations(self):
        first = self.screen()
        second_record = self.second_source()
        second = self.screen(second_record)
        self.assertNotEqual(first.candidate_id, second.candidate_id)
        self.assertNotEqual(first.fingerprint(), second.fingerprint())
        self.assertEqual(first.comparison_key(), second.comparison_key())
        for field, value in (("max_callbacks", 2), ("max_calls", 19), ("budget_microusd", 9999)):
            record = copy.deepcopy(second_record)
            record["generation"][field] = value
            self.assertNotEqual(first.comparison_key(), self.screen(record).comparison_key())
        record = copy.deepcopy(second_record)
        record["generation"]["config"]["instructions"] = "a different controlled instruction"
        self.assertNotEqual(first.comparison_key(), self.screen(record).comparison_key())
        record = copy.deepcopy(second_record)
        record["native"]["executor"]["limits"]["wall_seconds"] += 1
        self.assertNotEqual(first.comparison_key(), self.screen(record).comparison_key())

    def test_two_task_screen_binds_all_owners_and_admits_only_verified_complete_native_means(self):
        screen = self.screen()
        control = self.root / "reviewed-control.txt"
        control.write_bytes(b"immutable reviewed screen control")
        directory, authority = self.prepare(
            screen, input_bindings={control: sha(control.read_bytes())}
        )
        self.assertEqual(authority.summary()["operation_count"], 0)
        self.assertEqual(self.run_screen(directory)["status"], "complete")
        self.assertEqual([task["id"] for _, task in self.generation_events], ["1", 1])
        self.assertEqual((len(self.generation_events), len(self.native_events)), (2, 6))
        self.assertEqual(self.engine.physical_sends, 4)
        funded = authority.summary()
        self.assertEqual(
            (len(funded["runs"]), funded["operation_count"], funded["reserved_microusd"]), (8, 4, 0)
        )
        self.assertTrue(all(not owner["active"] for owner in funded["runs"]))
        for owner in funded["runs"]:
            manifest = json.loads((Path(owner["directory"]) / "manifest.json").read_bytes())
            bindings = {item["path"]: item["sha256"] for item in manifest["invocation"]["inputs"]}
            self.assertEqual(bindings[str(control)], sha(control.read_bytes()))
            self.assertEqual(
                bindings[str(directory / "screen.json")],
                sha((directory / "screen.json").read_bytes()),
            )
            self.assertEqual(
                bindings[str(directory / "context.json")],
                sha((directory / "context.json").read_bytes()),
            )
        for index, identifier in enumerate(["1", 1]):
            generation = directory / "tasks" / str(index) / "generation"
            seal = json.loads((generation / "completed/0.json").read_bytes())
            answers = json.loads((generation / seal["attempt"] / "answers.json").read_bytes())
            self.assertEqual(
                answers["outputs"],
                [{"task_id": identifier, "answers": ["  unchanged weak text  ", ""]}],
            )
            self.assertEqual(seal["format"], "buddha.candidate-generation-stage.v1")
        checked = self.inspect(directory, authority)
        self.assertEqual(checked["candidate_id"], screen.candidate_id)
        self.assertEqual(checked["comparison_key"], screen.comparison_key())
        self.assertTrue(checked["admission"]["eligible"])
        self.assertEqual(checked["admission"]["mean_distinct"], 2)
        self.assertEqual(checked["admission"]["mean_utility"], 7)

    def test_distinct_sources_share_common_evidence_and_existing_parent_rules(self):
        first, second = self.screen(), self.screen(self.second_source())
        self.programs[second.candidate_id].update(
            callbacks=3, answers=["same", "same"], distinct=1, utility=4
        )
        first_dir, authority = self.prepare(first)
        self.assertEqual(self.run_screen(first_dir)["status"], "complete")
        original = (first_dir / "report.json").read_bytes()
        second_dir, _ = self.prepare(second, self.root / "screen-second", authority)
        self.assertEqual(self.run_screen(second_dir)["status"], "complete")
        self.assertEqual(len({row["run_id"] for row in authority.summary()["runs"]}), 16)
        self.assertEqual(self.engine.physical_sends, 14)
        refs = [self.reference(first_dir, authority), self.reference(second_dir, authority)]
        for method, expected in (
            ("archive", first.candidate_id),
            ("latest", second.candidate_id),
            ("uninformed", first.candidate_id),
        ):
            with self.subTest(method=method), self.readonly():
                result = self.select_api(refs, method=method, max_active=2, seed=7, iteration=0)
                self.assertEqual(result["selected_id"], expected)
                self.assertEqual(len(result["admissions"]), 2)
        before = self.files(first_dir), authority.summary(), self.engine.physical_sends
        with patch("buddha.executor.run_container", side_effect=AssertionError("keyless worker")):
            self.assertEqual(
                self.run_api(first_dir, transport=RawHTTPTransport(allow_paid=False))["status"],
                "complete",
            )
        self.assertEqual(
            (self.files(first_dir), authority.summary(), self.engine.physical_sends), before
        )
        self.assertEqual((first_dir / "report.json").read_bytes(), original)
        with self.readonly(), self.assertRaises(self.Error):
            self.select_api([refs[0], refs[0]], method="archive", max_active=2, seed=7, iteration=0)

    def test_complete_unscored_or_opaque_results_are_recorded_but_not_admitted(self):
        for projection in ("noveltybench-1.1", None):
            with self.subTest(projection=projection):
                record = copy.deepcopy(self.record)
                record["projection"] = projection
                screen = self.screen(record)
                self.unusable_task = 1
                directory, authority = self.prepare(
                    screen, self.root / ("ineligible-" + str(projection))
                )
                self.assertEqual(self.run_screen(directory)["status"], "complete")
                checked = self.inspect(directory, authority)
                self.assertFalse(checked["admission"]["eligible"])
                self.assertTrue(checked["admission"]["reasons"])
                self.assertIsNone(checked["admission"]["mean_utility"])
                with self.readonly():
                    selected = self.select_api(
                        [self.reference(directory, authority)],
                        method="archive",
                        max_active=2,
                        seed=7,
                        iteration=0,
                    )
                self.assertIsNone(selected["selected_id"])
                self.assertEqual(len(selected["admissions"]), 1)

    def test_known_native_stop_retains_observation_and_resumes_same_owners_without_rebilling(self):
        directory, authority = self.prepare(self.screen())
        self.engine.native_fail_once = True
        partial = self.run_screen(directory)
        self.assertEqual(partial["status"], "incomplete")
        observed = directory / partial["observation"]
        old_observation = observed.read_bytes()
        owners = {row["directory"]: row["run_id"] for row in authority.summary()["runs"]}
        self.assertEqual(self.engine.physical_sends, 1)
        self.assertFalse((directory / "report.json").exists())
        with self.assertRaises(self.Error), self.readonly():
            self.select_api(
                [
                    {
                        "directory": str(directory),
                        "authorization": str(authority.path),
                        "report_sha256": "0" * 64,
                    }
                ],
                method="archive",
                max_active=2,
                seed=7,
                iteration=0,
            )
        self.assertEqual(self.run_screen(directory)["status"], "complete")
        self.assertEqual(self.engine.physical_sends, 4)
        self.assertEqual(observed.read_bytes(), old_observation)
        current = {row["directory"]: row["run_id"] for row in authority.summary()["runs"]}
        self.assertTrue(all(current[path] == identifier for path, identifier in owners.items()))

    def test_unknown_source_hold_blocks_resume_and_other_candidate_without_admission(self):
        first = self.screen()
        self.programs[first.candidate_id]["callbacks"] = 1
        directory, authority = self.prepare(first)
        self.engine.generation_timeout_once = True
        partial = self.run_screen(directory)
        self.assertEqual(partial["status"], "incomplete")
        self.assertEqual(partial["reason"], "unknown")
        before = authority.summary()
        self.assertGreater(before["reserved_microusd"], 0)
        self.assertEqual(self.engine.physical_sends, 1)
        self.assertEqual(self.run_screen(directory)["status"], "incomplete")
        second = self.screen(self.second_source())
        try:
            other, _ = self.prepare(second, self.root / "blocked-second", authority)
        except self.Error:
            pass
        else:
            self.assertEqual(self.run_screen(other)["status"], "incomplete")
        after = authority.summary()
        self.assertEqual(self.engine.physical_sends, 1)
        for field in ("operation_count", "reserved_microusd", "spent_microusd"):
            self.assertEqual(after[field], before[field])
        self.assertFalse((directory / "report.json").exists())

    def test_cancellation_keeps_completed_reply_and_actual_partial_before_same_owner_resume(self):
        screen = self.screen()
        self.programs[screen.candidate_id]["callbacks"] = 1
        directory, authority = self.prepare(screen)
        self.engine.generation_interrupt_once = True
        with self.assertRaises(KeyboardInterrupt):
            self.run_screen(directory)
        observed = self.files(directory / "observations")
        self.assertTrue(observed)
        self.assertFalse((directory / "report.json").exists())
        self.assertEqual(
            (self.engine.physical_sends, authority.summary()["reserved_microusd"]), (1, 0)
        )
        self.assertEqual(self.run_screen(directory)["status"], "complete")
        self.assertEqual(self.engine.physical_sends, 6)
        self.assertTrue(observed.items() <= self.files(directory / "observations").items())

    def test_control_changed_inside_later_owner_preparation_cannot_be_adopted(self):
        from buddha import candidate_generation

        screen = self.screen()
        control = self.root / "control-publication.txt"
        control.write_bytes(b"original reviewed bytes")
        directory, _ = self.prepare(screen, input_bindings={control: sha(control.read_bytes())})
        original = candidate_generation.prepare_gateway

        def mutate(owner, **arguments):
            if owner == directory / "tasks/1/generation/owners/0":
                control.write_bytes(b"changed after preflight")
            return original(owner, **arguments)

        with patch.object(candidate_generation, "prepare_gateway", side_effect=mutate):
            with self.assertRaises(self.Error):
                self.run_screen(directory)
        self.assertEqual(self.engine.physical_sends, 2)
        self.assertFalse((directory / "tasks/1/generation/owners/0/manifest.json").exists())
        self.assertFalse((directory / "report.json").exists())

    def test_passive_inspection_survives_retired_programs_and_rejects_saved_scalar_forgery(self):
        screen = self.screen()
        directory, authority = self.prepare(screen)
        self.assertEqual(self.run_screen(directory)["status"], "complete")
        original = (directory / "report.json").read_bytes()
        for role in ("agent", "runner"):
            source = Path(self.record["generation"]["roots"][role])
            retained = self.root / ("retired-" + role)
            shutil.move(str(source), str(retained))
        self.assertTrue(self.inspect(directory, authority)["admission"]["eligible"])
        forged = json.loads(original)
        forged["admission"]["mean_utility"] = 10
        (directory / "report.json").write_bytes(_json(forged))
        with self.assertRaises(self.Error):
            self.inspect(directory, authority)
        (directory / "report.json").write_bytes(original)

    def test_missing_retained_funded_owner_is_corruption_not_partial_coverage(self):
        directory, authority = self.prepare(self.screen())
        self.engine.native_timeout_once = True
        self.assertEqual(self.run_screen(directory)["status"], "incomplete")
        owner = directory / "tasks/0/evaluation/owners/1"
        self.assertTrue(owner.is_dir())
        shutil.move(str(owner), str(self.root / "retained-missing-owner"))
        before = authority.summary(), self.engine.physical_sends
        with self.assertRaises(self.Error):
            self.run_screen(directory)
        self.assertEqual((authority.summary(), self.engine.physical_sends), before)

    def test_final_publication_rechecks_prior_native_report_after_later_task_return(self):
        from buddha import native_evaluation

        directory, _ = self.prepare(self.screen())
        original = native_evaluation.run_evaluation

        def replace_previous(child, **arguments):
            report = original(child, **arguments)
            if child == directory / "tasks/1/evaluation":
                prior = directory / "tasks/0/evaluation/report.json"
                prior.write_bytes(prior.read_bytes() + b" ")
            return report

        with patch.object(native_evaluation, "run_evaluation", side_effect=replace_previous):
            with self.assertRaises(self.Error):
                self.run_screen(directory)
        self.assertEqual(self.engine.physical_sends, 4)
        self.assertFalse((directory / "report.json").exists())

    def test_returned_child_matches_typed_saved_report_before_next_paid_stage(self):
        from buddha import candidate_generation

        directory, _ = self.prepare(self.screen())
        original = candidate_generation.run_candidate_generation
        retained_seals = {}

        def change_saved_report(child, **arguments):
            report = original(child, **arguments)
            path = child / "report.json"
            saved = json.loads(path.read_bytes())
            self.assertIs(type(saved["authorization"]["reserved_microusd"]), int)
            self.assertEqual(saved["authorization"]["reserved_microusd"], 0)
            retained_seals.update(self.files(child / "completed"))
            saved["authorization"]["reserved_microusd"] = False
            path.write_bytes(_json(saved))
            return report

        with patch.object(
            candidate_generation, "run_candidate_generation", side_effect=change_saved_report
        ):
            with self.assertRaises(self.Error):
                self.run_screen(directory)
        self.assertEqual(self.engine.physical_sends, 0)
        self.assertFalse((directory / "report.json").exists())
        self.assertEqual(retained_seals, self.files(directory / "tasks/0/generation/completed"))

    def test_generated_recipe_changes_before_real_child_preparation_are_not_adopted(self):
        from buddha import candidate_generation, native_evaluation

        for stage in ("generation", "native"):
            with self.subTest(stage=stage):
                case = type(self)("runTest")
                case.setUp()
                try:
                    directory, _ = case.prepare(case.screen())
                    module, name, child = (
                        (
                            candidate_generation,
                            "prepare_candidate_generation",
                            directory / "tasks/1/generation",
                        )
                        if stage == "generation"
                        else (
                            native_evaluation,
                            "prepare_evaluation",
                            directory / "tasks/0/evaluation",
                        )
                    )
                    original = getattr(module, name)
                    changed = []

                    def mutate(
                        location,
                        *,
                        target=child,
                        kind=stage,
                        events=changed,
                        prepare=original,
                        **arguments,
                    ):
                        if location == target:
                            descriptor = arguments["descriptor"]
                            recipe = json.loads(descriptor.read_bytes())
                            if kind == "generation":
                                recipe["config"]["instructions"] += " changed after materialization"
                            else:
                                recipe["native"]["max_calls"] += 1
                            descriptor.write_bytes(_json(recipe))
                            events.append(descriptor)
                        return prepare(location, **arguments)

                    with patch.object(module, name, side_effect=mutate):
                        with self.assertRaises(self.Error):
                            case.run_screen(directory)
                    self.assertEqual(len(changed), 1)
                    self.assertEqual(case.engine.physical_sends, 2 if stage == "generation" else 0)
                    index = "0" if stage == "generation" else "1"
                    self.assertFalse((child / "owners" / index / "manifest.json").exists())
                    self.assertFalse((directory / "report.json").exists())
                finally:
                    case.doCleanups()

    def test_wrong_authority_scope_and_unapproved_runtime_reject_before_original_owner(self):
        screen = self.screen()
        directory = self.root / "foreign-scope"
        with self.assertRaises(self.Error):
            self.prepare(screen, directory, self.engine.fixture.authority)
        self.assertFalse((directory / "tasks/0/generation/owners/0/manifest.json").exists())
        for field in ("image_id", "image_environment", "external_hash"):
            with self.subTest(field=field):
                record = copy.deepcopy(self.record)
                changes = {}
                if field == "image_id":
                    record["generation"]["executor"][field] = "sha256:" + "b" * 64
                elif field == "image_environment":
                    record["generation"]["executor"][field][0][1] += "-changed"
                else:
                    changes["expected_runtime_sha256"] = "0" * 64
                candidate = self.screen(record)
                directory = self.root / ("unapproved-" + field)
                with self.assertRaises(self.Error):
                    self.prepare(candidate, directory, **changes)
                self.assertFalse((directory / "tasks/0/generation/owners/0/manifest.json").exists())
        self.assertEqual(self.engine.physical_sends, 0)

    def test_callback_quota_is_independent_of_answer_count_and_never_becomes_admission(self):
        record = copy.deepcopy(self.record)
        record["generation"]["max_callbacks"] = 0
        screen = self.screen(record)
        self.programs[screen.candidate_id]["callbacks"] = 1
        directory, authority = self.prepare(screen)
        partial = self.run_screen(directory)
        self.assertEqual(partial["status"], "incomplete")
        self.assertEqual(partial["reason"], "quota")
        self.assertTrue((directory / partial["observation"]).is_file())
        self.assertEqual(self.engine.physical_sends, 0)
        self.assertEqual(authority.summary()["operation_count"], 0)
        self.assertFalse((directory / "report.json").exists())

    def test_genuine_complete_references_with_different_controls_cannot_share_a_parent_pool(self):
        first = self.screen()
        record = self.second_source()
        record["generation"]["config"]["instructions"] = "a separately controlled procedure"
        second = self.screen(record)
        self.assertNotEqual(first.comparison_key(), second.comparison_key())
        first_dir, first_authority = self.prepare(first)
        second_dir, second_authority = self.prepare(second, self.root / "different-controls")
        self.assertEqual(self.run_screen(first_dir)["status"], "complete")
        self.assertEqual(self.run_screen(second_dir)["status"], "complete")
        refs = [
            self.reference(first_dir, first_authority),
            self.reference(second_dir, second_authority),
        ]
        before = self.engine.physical_sends
        with self.readonly(), self.assertRaises(self.Error):
            self.select_api(refs, method="archive", max_active=2, seed=7, iteration=0)
        self.assertEqual(self.engine.physical_sends, before)

    def test_same_artifact_comparison_with_different_external_controls_cannot_share_a_pool(self):
        first = self.screen()
        second = self.screen(self.second_source())
        self.assertEqual(first.comparison_key(), second.comparison_key())
        self.assertNotEqual(first.candidate_id, second.candidate_id)
        first_control, second_control = self.root / "control-a.txt", self.root / "control-b.txt"
        first_control.write_bytes(b"reviewed external procedure A")
        second_control.write_bytes(b"reviewed external procedure B")
        authority = self.authority(first)
        first_dir, _ = self.prepare(
            first,
            authority=authority,
            input_bindings={first_control: sha(first_control.read_bytes())},
        )
        second_dir, _ = self.prepare(
            second,
            self.root / "second-external-controls",
            authority,
            input_bindings={second_control: sha(second_control.read_bytes())},
        )
        self.assertEqual(self.run_screen(first_dir)["status"], "complete")
        self.assertEqual(self.run_screen(second_dir)["status"], "complete")
        self.assertTrue(self.inspect(first_dir, authority)["admission"]["eligible"])
        self.assertTrue(self.inspect(second_dir, authority)["admission"]["eligible"])
        refs = [self.reference(first_dir, authority), self.reference(second_dir, authority)]
        before = self.files(first_dir), self.files(second_dir), authority.summary()
        sends = self.engine.physical_sends
        with self.readonly(), self.assertRaises(self.Error):
            self.select_api(refs, method="archive", max_active=2, seed=7, iteration=0)
        self.assertEqual(
            (self.files(first_dir), self.files(second_dir), authority.summary()), before
        )
        self.assertEqual(self.engine.physical_sends, sends)

    def test_recorded_lineage_parent_is_retained_and_changed_raw_bytes_are_not_adopted(self):
        record = copy.deepcopy(self.record)
        source = Path(record["generation"]["roots"]["agent"]) / "candidate.py"
        lineage = self.root / "declared-synthetic-lineage.json"
        lineage.write_bytes(
            _json(
                {
                    "format": "buddha.source-lineage.v1",
                    "parent": {
                        "entrypoint": "candidate.py",
                        "source_sha256": "b" * 64,
                        "agent_sha256": "a" * 64,
                    },
                    "child": {
                        "entrypoint": "candidate.py",
                        "source_sha256": sha(source.read_bytes()),
                        "agent_sha256": self.engine.fixture.selection.agent_sha256,
                    },
                    "descriptor_sha256": "c" * 64,
                    "feedback": {"file_sha256": "d" * 64, "input_sha256": "e" * 64},
                    "proposal_sha256": "f" * 64,
                    "owner": {
                        "path": str(self.root / "recorded-origin-owner"),
                        "manifest_sha256": "0" * 64,
                    },
                }
            )
        )
        record["lineage"] = {"path": str(lineage), "sha256": sha(lineage.read_bytes())}
        screen = self.screen(record)
        self.assertEqual(
            screen.comparison_key(), self.Screen.from_bytes(_json(self.record)).comparison_key()
        )
        directory, authority = self.prepare(screen)
        result = self.run_screen(directory)
        self.assertEqual(result["status"], "complete")
        self.assertEqual(result["parent_id"], "a" * 64)
        self.assertEqual(self.inspect(directory, authority)["parent_id"], "a" * 64)
        before = self.engine.physical_sends
        lineage.write_bytes(lineage.read_bytes() + b" ")
        with self.assertRaises(self.Error):
            self.inspect(directory, authority)
        self.assertEqual(self.engine.physical_sends, before)


if __name__ == "__main__":
    unittest.main()
