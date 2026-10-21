"""The study reader observes original native records without executing or writing."""

import base64
import copy
import hashlib
import json
import sqlite3
import unittest
from contextlib import ExitStack, contextmanager
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

import test_history as history_fixtures
import test_policy_run as fixtures

from buddha import native_evaluation
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


if __name__ == "__main__":
    unittest.main()
