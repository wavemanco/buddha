"""The study reader observes original native records without executing or writing."""

import base64
import copy
import hashlib
import json
import sqlite3
import unittest
from contextlib import ExitStack, contextmanager
from dataclasses import replace
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock, patch

import test_history as history_fixtures
import test_policy_run as fixtures

from buddha import native_evaluation, policy_results
from buddha.answers import TaskSet
from buddha.authorization import Authorization
from buddha.gateway import Gateway
from buddha.policy_results import PolicyResultsError, analyze_study
from buddha.releases import _json
from buddha.search_evidence import _open_binary


def sha(raw):
    return hashlib.sha256(raw).hexdigest()


class PolicyResultsTests(unittest.TestCase):
    def setUp(self):
        self.fixture = f = fixtures.PolicyRunTests("runTest")
        f.setUp()
        self.addCleanup(f.doCleanups)
        self.root = f.root
        self.protocol = self.root / "protocol.md"
        self.protocol.write_bytes(
            b"Development comparison: native distinct and utility remain separate. "
            b"J0 is primary, means over both R then equal prompt weights; "
            b"no winner from an incomplete schedule.\n"
        )
        source = TaskSet.from_bytes(_json(f.study_record["source"]))
        study = copy.deepcopy(f.study_record)
        del study["source"]
        self.intent_record = {
            "format": "buddha.policy-study-intent.v1",
            "protocol_sha256": sha(self.protocol.read_bytes()),
            "release": source.to_record()["release"],
            "study": study,
            "expected": {
                "release_sha256": source.release_sha256,
                "source_tasks_sha256": source.fingerprint(),
                "selected_tasks_sha256": f.study.tasks.fingerprint(),
                "study_sha256": f.study.fingerprint(),
                "arm_ids": [arm["arm_id"] for arm in f.study.arms],
                "cell_ids": [cell["cell_id"] for cell in f.study.schedule()],
            },
        }
        self.intent = self.root / "intent.json"
        self.intent.write_bytes(_json(self.intent_record))
        self.expected_intent = sha(self.intent.read_bytes())
        self.expected_protocol = sha(self.protocol.read_bytes())
        original = f.fixture.execute_worker

        def finite_native(spec, *, initial, handle, **kwargs):
            if spec.role == "agent":
                return original(spec, initial=initial, handle=handle, **kwargs)
            session = handle.__self__
            original_file = session._file

            def native_file(frame):
                frame = copy.deepcopy(frame)
                if frame["path"] in {"partitions.jsonl", "scores.jsonl"}:
                    raw = base64.b64decode(frame["data_base64"])
                    rows = [json.loads(line) for line in raw.splitlines()]
                    for row in rows:
                        # Explicit synthetic native records, not executed benchmark math.
                        row.update(
                            distinct=2,
                            partition_key="a" * 64,
                            partition_config={
                                "version": "1.1",
                                "alg": "llm",
                                "seed": None,
                                "judge_model": "test-model",
                            },
                        )
                        if frame["path"] == "scores.jsonl":
                            row.update(
                                utility=7.0,
                                generation_scores=[7, 7],
                                partition_scores=[7, 7],
                                score_key="b" * 64,
                                score_config={"version": "1.1", "scorer": "llm", "patience": 0.8},
                            )
                    frame["data_base64"] = base64.b64encode(
                        b"".join(_json(row) + b"\n" for row in rows)
                    ).decode()
                return original_file(frame)

            with patch.object(session, "_file", side_effect=native_file):
                return original(spec, initial=initial, handle=handle, **kwargs)

        self.worker = patch.object(f.fixture, "execute_worker", side_effect=finite_native)
        self.worker.start()
        self.addCleanup(self.worker.stop)

    def read(self, **changes):
        arguments = {
            "intent": self.intent,
            "protocol": self.protocol,
            "expected_intent_sha256": self.expected_intent,
            "expected_protocol_sha256": self.expected_protocol,
            "authorization": self.fixture.authority.path,
        }
        arguments.update(changes)
        before = self.files()
        sends = self.fixture.fixture.physical_sends
        try:
            with self.readonly():
                return analyze_study(self.fixture.directory, **arguments)
        finally:
            self.assertEqual(self.files(), before)
            self.assertEqual(self.fixture.fixture.physical_sends, sends)

    def files(self):
        return {
            path.relative_to(self.root).as_posix(): (
                sha(path.read_bytes()),
                path.stat().st_mtime_ns,
            )
            for path in self.root.rglob("*")
            if path.is_file()
        }

    @contextmanager
    def readonly(self):
        def forbidden(*args, **kwargs):
            raise AssertionError("passive reader executed, read credentials or wrote")

        real_connect, real_open = sqlite3.connect, Path.open

        def connect(path, *args, **kwargs):
            if path != ":memory:":
                forbidden()
            return real_connect(path, *args, **kwargs)

        def opened(path, mode="r", *args, **kwargs):
            if any(character in mode for character in "wax+"):
                forbidden()
            if path.suffix in {".py", ".pyc", ".pyo"}:
                raise AssertionError("passive reader reopened an executable source")
            return real_open(path, mode, *args, **kwargs)

        @contextmanager
        def opened_binary(path):
            if path.suffix in {".py", ".pyc", ".pyo"}:
                raise AssertionError("passive reader reopened an executable source")
            with _open_binary(path) as stream:
                yield stream

        with ExitStack() as stack:
            stack.enter_context(patch.object(Authorization, "__init__", side_effect=forbidden))
            stack.enter_context(patch.object(Gateway, "__init__", side_effect=forbidden))
            for target in (
                "buddha.agent_run.AgentSession.__init__",
                "buddha.native_run.NativeSession.__init__",
                "buddha.executor.run_container",
                "buddha.gateway.execution_identity",
                "buddha.releases.verify_selection",
                "buddha.native_pipeline.verify_selection",
                "buddha.policy_run.prepare_study",
                "buddha.policy_run.run_study",
                "buddha.policy_run._definition",
                "buddha.policy_run._preflight",
                "getpass.getpass",
                "os.environ.get",
                "http.client.HTTPSConnection",
                "socket.create_connection",
                "subprocess.Popen",
            ):
                stack.enter_context(patch(target, side_effect=forbidden))
            stack.enter_context(patch("sqlite3.connect", side_effect=connect))
            stack.enter_context(patch.object(Path, "open", opened))
            stack.enter_context(patch("buddha.search_evidence._open_binary", opened_binary))
            yield

    def rejected_change(self, path, mutate):
        original = path.read_bytes()
        try:
            path.write_bytes(mutate(original))
            with self.assertRaises(PolicyResultsError):
                self.read()
        finally:
            path.write_bytes(original)

    def change_authority(self, sql, arguments=()):
        history_fixtures.HistoryTests.corrupt(
            SimpleNamespace(path=self.fixture.authority.path), sql, arguments
        )

    def complete(self):
        self.fixture.prepare()
        self.assertEqual(self.fixture.run_study()["status"], "complete")

    def test_complete_native_study_retains_typed_population_and_registered_metrics(self):
        self.complete()
        result = self.read()
        self.assertEqual(result["format"], "buddha.policy-results.v1")
        self.assertEqual(result["publication_status"], "complete")
        analysis = result["analysis"]
        self.assertEqual(analysis["status"], "complete")
        self.assertEqual(analysis["coverage"], {"expected": 32, "observed": 32, "usable": 32})
        self.assertEqual(
            {(type(row["task_id"]), row["task_id"]) for row in analysis["assessments"]},
            {(str, "1"), (int, 1)},
        )
        for values in analysis["mean_contrasts"].values():
            self.assertTrue(all(value == 0 for value in values.values()))
        self.assertIn("provenance", result)
        self.assertIn("accounting", result)
        self.assertTrue(result["limitations"])

    def test_publication_pins_and_original_registered_controls_are_required(self):
        self.complete()
        self.assertEqual(self.read()["publication_status"], "complete")
        for field in ("expected_intent_sha256", "expected_protocol_sha256"):
            with self.subTest(field=field), self.assertRaises(PolicyResultsError):
                self.read(**{field: "0" * 64})
        with self.assertRaises(PolicyResultsError):
            self.read(authorization=self.root / "baseline-authorization.sqlite3")
        for path in (self.protocol, self.fixture.study_path, self.fixture.template):
            with self.subTest(path=path.name):
                self.rejected_change(path, lambda raw: raw + b"\n")

        changed = copy.deepcopy(self.intent_record)
        changed["study"]["generation"]["model"] = "unregistered-model"
        original = self.intent.read_bytes()
        try:
            self.intent.write_bytes(_json(changed))
            with self.assertRaises(PolicyResultsError):
                self.read(expected_intent_sha256=sha(self.intent.read_bytes()))
        finally:
            self.intent.write_bytes(original)
        recipe = self.fixture.directory / "cells/0/generation.json"

        def config_change(raw):
            record = json.loads(raw)
            record["config"]["instructions"] = "Different treatment"
            return _json(record)

        self.rejected_change(recipe, config_change)

    def test_saved_seals_reports_summaries_and_authority_anchors_are_verified(self):
        self.complete()
        self.assertEqual(self.read()["publication_status"], "complete")
        directory = self.fixture.directory
        report = json.loads((directory / "report.json").read_bytes())
        child = Path(report["cells"][0]["occasions"][0]["directory"])

        def wrong_index(raw):
            record = json.loads(raw)
            record["index"] = False
            return _json(record)

        self.rejected_change(child / "completed/0.json", wrong_index)

        def wrong_arm(raw):
            record = json.loads(raw)
            record["cells"][0]["arm_index"] = False
            return _json(record)

        self.rejected_change(directory / "report.json", wrong_arm)

        def invalid_observation(raw):
            record = json.loads(raw)
            record["authorization"] = False
            return _json(record)

        with self.subTest(snapshot="false"):
            self.rejected_change(directory / "report.json", invalid_observation)
        for key, value in (("terms_sha256", "0" * 64), ("event_count", False)):

            def invalid_snapshot(raw, key=key, value=value):
                record = json.loads(raw)
                record["authorization"][key] = value
                return _json(record)

            with self.subTest(snapshot=key):
                self.rejected_change(directory / "report.json", invalid_snapshot)
        self.rejected_change(child / "report.json", lambda raw: raw + b"\n")
        summary = Path(report["cells"][0]["occasions"][0]["summary"]["path"])
        self.rejected_change(summary, lambda raw: raw + b"\n")
        manifest = json.loads((child / "owners/0/manifest.json").read_bytes())
        authority = self.fixture.authority.path
        original = authority.read_bytes()
        try:
            self.change_authority(
                "UPDATE auth_deactivations SET reason=? WHERE run_id=?",
                ("baseline completed: " + "0" * 64, manifest["run_id"]),
            )
            with self.assertRaises(PolicyResultsError):
                self.read()
        finally:
            authority.write_bytes(original)

    def test_retired_original_programs_are_not_needed_but_retained_data_is(self):
        self.complete()
        baseline = self.fixture.fixture
        roots = set(baseline.generation_roots.values()) | set(baseline.native_roots.values())
        archive = self.root / "retired-programs"
        archive.mkdir()
        moved = []
        for root in sorted(roots):
            self.assertTrue(root.resolve().is_relative_to(self.root.resolve()))
            for source in sorted(root.rglob("*.py")):
                target = archive / source.relative_to(self.root)
                target.parent.mkdir(parents=True, exist_ok=True)
                digest = sha(source.read_bytes())
                source.rename(target)
                self.assertEqual(sha(target.read_bytes()), digest)
                moved.append((source, target))
        self.assertTrue(moved)
        result = self.read()
        self.assertEqual(result["publication_status"], "complete")
        self.assertEqual(result["analysis"]["coverage"]["usable"], 32)
        # Executable retirement is distinct from dropping still required data.
        self.rejected_change(baseline.agent.tasks_path, lambda raw: b"{}")

    def test_explicit_genuine_partial_keeps_full_grid_without_a_headline(self):
        self.fixture.prepare()
        self.fixture.fixture.timeout_native_once = True
        stopped = self.fixture.run_study()
        self.assertEqual(stopped["status"], "incomplete")
        self.assertEqual(stopped["reason"], "unknown")
        self.assertEqual(self.fixture.fixture.physical_sends, 5)
        observation = self.fixture.directory / stopped["observation"]
        result = self.read(observation=observation)
        self.assertEqual(result["publication_status"], "incomplete")
        analysis = result["analysis"]
        self.assertEqual(analysis["status"], "incomplete")
        self.assertIsNone(analysis["mean_contrasts"])
        self.assertEqual(len(analysis["assessments"]), 32)
        self.assertEqual(analysis["coverage"], {"expected": 32, "observed": 0, "usable": 0})
        self.assertTrue(all(row["status"] == "missing" for row in analysis["assessments"]))
        self.assertEqual(result["accounting"]["current_study"]["operation_count"], 5)
        self.assertGreater(result["accounting"]["current_study"]["reserved_microusd"], 0)
        with self.assertRaises(PolicyResultsError):
            self.read()
        outside = self.root / "copied-observation.json"
        outside.write_bytes(observation.read_bytes())
        with self.assertRaises(PolicyResultsError):
            self.read(observation=outside)

    def test_partial_fresh_judge_keeps_original_primary_without_filling_missing_occasions(self):
        self.fixture.prepare()
        original = native_evaluation.run_evaluation

        def stopped_judging(*args, **kwargs):
            self.fixture.fixture.fail_native_once = True
            return original(*args, **kwargs)

        with patch.object(native_evaluation, "run_evaluation", side_effect=stopped_judging):
            stopped = self.fixture.run_study()
        self.assertEqual((stopped["cell_index"], stopped["occasion_index"]), (0, 1))
        self.assertEqual(stopped["reason"], "native_error")
        self.assertEqual(self.fixture.fixture.physical_sends, 7)
        observation = self.fixture.directory / stopped["observation"]
        original_observation = observation.read_bytes()
        result = self.read(observation=observation)
        self.assertEqual(result["publication_status"], "incomplete")
        analysis = result["analysis"]
        self.assertIsNone(analysis["mean_contrasts"])
        self.assertEqual(analysis["coverage"], {"expected": 32, "observed": 2, "usable": 2})
        observed = [row for row in analysis["assessments"] if row["status"] == "observed"]
        self.assertEqual(len(observed), 2)
        for row in observed:
            self.assertEqual(
                (row["arm_index"], row["generation_repeat"], row["judge_occasion"]), (0, 0, 0)
            )
            self.assertEqual((row["distinct"], row["utility"]), (2, 7.0))
        self.assertEqual(self.fixture.run_study()["status"], "complete")
        self.assertEqual(self.fixture.fixture.physical_sends, 64)
        self.assertEqual(observation.read_bytes(), original_observation)
        older = self.read(observation=observation)
        self.assertEqual(older["analysis"]["coverage"], analysis["coverage"])
        self.assertIsNone(older["analysis"]["mean_contrasts"])
        self.assertEqual(self.read()["analysis"]["coverage"]["usable"], 32)

    def test_actual_generation_error_is_a_retained_incomplete_observation(self):
        self.fixture.prepare()
        self.fixture.fixture.fail_generation_once = True
        stopped = self.fixture.run_study()
        self.assertEqual(stopped["reason"], "agent_error")
        self.assertEqual(self.fixture.fixture.physical_sends, 3)
        result = self.read(observation=self.fixture.directory / stopped["observation"])
        self.assertEqual(result["publication_status"], "incomplete")
        analysis = result["analysis"]
        self.assertIsNone(analysis["mean_contrasts"])
        self.assertEqual(analysis["coverage"], {"expected": 32, "observed": 0, "usable": 0})
        accounting = result["accounting"]["current_study"]
        self.assertEqual(accounting["operation_count"], 3)
        self.assertGreater(accounting["spent_microusd"], 0)
        self.assertEqual(accounting["reserved_microusd"], 0)

    def test_reader_reuses_bounded_capture_instead_of_an_unbounded_second_walk(self):
        self.fixture.prepare()
        run_evaluation = native_evaluation.run_evaluation

        def stopped_judging(*args, **kwargs):
            self.fixture.fixture.fail_native_once = True
            return run_evaluation(*args, **kwargs)

        with patch.object(native_evaluation, "run_evaluation", side_effect=stopped_judging):
            stopped = self.fixture.run_study()
        self.assertEqual((stopped["cell_index"], stopped["occasion_index"]), (0, 1))
        self.assertEqual(stopped["reason"], "native_error")
        self.assertEqual(self.fixture.fixture.physical_sends, 7)
        original_analyze = analyze_study

        def captured_only(*args, **kwargs):
            # Fixture construction and our own preservation snapshots remain
            # outside this check on the passive reader's tree traversal.
            with patch.object(
                Path, "rglob", side_effect=AssertionError("unbounded second observation walk")
            ):
                return original_analyze(*args, **kwargs)

        with patch(f"{__name__}.analyze_study", side_effect=captured_only):
            result = self.read(observation=self.fixture.directory / stopped["observation"])
        self.assertEqual(result["publication_status"], "incomplete")
        self.assertEqual(
            result["analysis"]["coverage"], {"expected": 32, "observed": 2, "usable": 2}
        )
        self.assertIsNone(result["analysis"]["mean_contrasts"])

    def test_shared_owner_scan_retains_controls_roots_and_local_ceiling_validation(self):
        scan = policy_results._Reader.scheduled_owners
        self.fixture.prepare()
        directory = self.fixture.directory
        before = self.files()
        with self.readonly():
            reader = policy_results._Reader(directory, self.fixture.authority.path)
            path = directory / "cells/0/baseline/owners/0"
            owner = reader.owner(path)
            study, _execution = reader.definition(owner)
            roles = ["grouping", "quality", "summary"]
            coordinates, planned = scan(reader, study, roles)
            self.assertEqual(planned, 56)
            self.assertEqual(set(coordinates), {path})
            self.assertEqual(coordinates[path]["stage_role"], "generation")
            self.assertIsNone(coordinates[path]["judge_occasion"])
            # Isolate the shared semantic checks after the real read-only history
            # decoder. These fixture variants are not claims of newly sealed rows.
            variants = []
            manifest = copy.deepcopy(owner.manifest)
            control = next(iter(reader.controls))
            manifest["invocation"]["inputs"] = [
                item for item in manifest["invocation"]["inputs"] if item["path"] != control
            ]
            variants.append(manifest)
            manifest = copy.deepcopy(owner.manifest)
            manifest["roots"]["agent"] = str(self.root / "foreign-agent")
            variants.append(manifest)
            manifest = copy.deepcopy(owner.manifest)
            manifest["settings"]["max_calls"] += 1
            variants.append(manifest)
            for index, manifest in enumerate(variants):
                with self.subTest(variant=index), self.assertRaises(PolicyResultsError):
                    reader.owners[path] = replace(owner, manifest=manifest)
                    scan(reader, study, roles)
            reader.owners[path] = owner
            reader.capture.finish()
        self.assertEqual(self.files(), before)
        self.assertEqual(self.fixture.fixture.physical_sends, 0)

    def test_retained_owner_directory_requires_its_canonical_original_manifest(self):
        for relative in (
            "cells/0/baseline/owners/0",
            "cells/0/baseline/owners/00",
            "cells/0/judgments/1/owners/1",
        ):
            reader = SimpleNamespace(
                root=self.fixture.directory,
                template=self.fixture.fixture.record,
                release=self.fixture.fixture.agent.release,
                capture=SimpleNamespace(entries={relative: ()}),
                funding=Mock(side_effect=AssertionError("funding reached malformed owner")),
            )
            reader.scheduled_owners = lambda study, roles, reader=reader: (
                policy_results._Reader.scheduled_owners(reader, study, roles)
            )
            # Exercise the public reader's pre-funding path without constructing
            # any owner or running a source-bound generation fixture.
            with self.subTest(relative=relative):
                with self.assertRaises(PolicyResultsError):
                    policy_results._analyze(reader, self.fixture.study, {}, None)
                reader.funding.assert_not_called()

    def test_shared_generation_helpers_work_before_any_completed_child_publication(self):
        cell_definition = policy_results._Reader.cell_definition
        generation_reference = policy_results._Reader.generation_reference
        self.fixture.prepare()
        self.fixture.fixture.timeout_native_once = True
        stopped = self.fixture.run_study()
        self.assertEqual((stopped["cell_index"], stopped["occasion_index"]), (0, 0))
        base = self.fixture.directory / "cells/0/baseline"
        self.assertFalse((base / "report.json").exists())
        before = self.files()
        with self.readonly():
            reader = policy_results._Reader(self.fixture.directory, self.fixture.authority.path)
            owner = reader.owner(base / "owners/0")
            study, execution = reader.definition(owner)
            reader.scheduled_owners(study, ["grouping", "quality", "summary"])
            reader.funding(execution, study)
            cell_definition(reader, 0, study.schedule()[0])
            reference = generation_reference(reader, base)
            self.assertEqual(
                reference,
                {
                    "baseline_directory": str(base),
                    "stage_seal_sha256": sha(reader.raw(base / "completed/0.json")),
                    "owner_manifest_sha256": owner.manifest_sha256,
                    "owner_ledger_sha256": owner.ledger_sha256,
                },
            )
            source = native_evaluation._read_generation(reference, self.fixture.authority.path)
            self.assertEqual(source.tasks.fingerprint(), study.tasks.fingerprint())
            for path, digest in source.files.items():
                reader.raw(path, digest)
            reader.capture.finish()
        self.assertEqual(self.files(), before)
        self.assertEqual(self.fixture.fixture.physical_sends, 5)
        recipe = base.parent / "generation.json"
        original = recipe.read_bytes()
        try:
            changed = json.loads(original)
            changed["config"]["instructions"] = "unregistered per-cell policy"
            recipe.write_bytes(_json(changed))
            with self.readonly():
                reader = policy_results._Reader(self.fixture.directory, self.fixture.authority.path)
                study, _ = reader.definition(reader.owner(base / "owners/0"))
                with self.assertRaises(PolicyResultsError):
                    reader.cell_definition(0, study.schedule()[0])
        finally:
            recipe.write_bytes(original)

    def test_cell_definition_joins_the_original_producer_paths_and_bound_bytes(self):
        cell = self.fixture.study.schedule()[0]
        cell_root = self.fixture.directory / "cells/0"
        baseline_path = cell_root / "baseline.json"
        recipe_path = cell_root / "generation.json"
        context_path = cell_root / "baseline/context.json"
        template = self.fixture.fixture.record
        recipe = self.fixture.fixture.agent.record
        expected_recipe = recipe | {"config": cell["generation_config"]}
        expected_baseline = template | {
            "generation": template["generation"] | {"descriptor": str(recipe_path)}
        }
        expected = {
            context_path: {
                "format": "buddha.baseline-context.v1",
                "descriptor": str(baseline_path),
            },
            baseline_path: expected_baseline,
            recipe_path: expected_recipe,
        }
        owner = object()
        for variant in ("alternate_context", "unbound_recipe", "alternate_recipe", "wrong_config"):
            consumed = copy.deepcopy(expected)
            if variant == "alternate_context":
                consumed[context_path]["descriptor"] = str(self.root / "alternate-baseline.json")
            elif variant == "unbound_recipe":
                del consumed[recipe_path]
            elif variant == "alternate_recipe":
                consumed[baseline_path]["generation"]["descriptor"] = str(
                    self.root / "alternate-generation.json"
                )
            else:
                consumed[recipe_path]["config"]["instructions"] = "alternate original treatment"

            def bound(observed, path, consumed=consumed):
                self.assertIs(observed, owner)
                if path not in consumed:
                    raise PolicyResultsError("not an original owner input")
                return _json(consumed[path])

            reader = SimpleNamespace(
                root=self.fixture.directory,
                recipe=recipe,
                template=template,
                record=lambda path: copy.deepcopy(expected[path]),
                owner=Mock(return_value=owner),
                bound=bound,
            )
            # Expected cell files are intact in every case. Only the producer's
            # original context/descriptor/recipe binding is different.
            with self.subTest(variant=variant), self.assertRaises(PolicyResultsError):
                policy_results._Reader.cell_definition(reader, 0, cell)

    def test_missing_funded_owner_cannot_hide_its_hold_from_an_old_observation(self):
        self.fixture.prepare()
        self.fixture.fixture.timeout_native_once = True
        stopped = self.fixture.run_study()
        self.assertEqual(stopped["reason"], "unknown")
        self.assertEqual(self.fixture.fixture.physical_sends, 5)
        observation = self.fixture.directory / stopped["observation"]
        control = self.read(observation=observation)
        accounting = control["accounting"]
        self.assertEqual(accounting["current_study"], accounting["current_shared"])
        self.assertGreater(accounting["current_study"]["reserved_microusd"], 0)
        owner = self.fixture.directory / "cells/0/baseline/owners/1"
        destination = self.root / "removed-owner-1-evidence"
        fixture_root = self.root.resolve()
        self.assertTrue(owner.resolve().is_relative_to(fixture_root))
        self.assertTrue(destination.parent.resolve().is_relative_to(fixture_root))
        self.assertFalse(destination.exists())
        original_authority = self.fixture.authority.summary()
        owner.rename(destination)
        try:
            with self.assertRaises(PolicyResultsError):
                self.read(observation=observation)
            self.assertEqual(self.fixture.authority.summary(), original_authority)
        finally:
            destination.rename(owner)
        self.assertEqual(self.read(observation=observation)["accounting"], accounting)
        self.assertEqual(self.fixture.fixture.physical_sends, 5)


if __name__ == "__main__":
    unittest.main()
