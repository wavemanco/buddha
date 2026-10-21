"""Fresh full native judging reuses anchored generation, never generation requests."""

import base64
import copy
import hashlib
import json
import os
import sqlite3
import tempfile
import unittest
from contextlib import closing
from pathlib import Path
from unittest.mock import patch

import test_baseline as baseline_fixtures
import test_gateway as gateway_fixtures

from buddha.answers import Answers
from buddha.gateway import RawHTTPTransport
from buddha.native_evaluation import EvaluationError, prepare_evaluation, run_evaluation
from buddha.native_pipeline import PipelineError
from buddha.releases import Release, _json, prepare_selection


def sha(raw):
    return hashlib.sha256(raw).hexdigest()


class NativeEvaluationFixture(unittest.TestCase):
    def setUp(self):
        self.fixture = baseline_fixtures.BaselineTests("runTest")
        self.fixture.setUp()
        self.addCleanup(self.fixture.doCleanups)
        self.configure_source(self.fixture)
        self.fixture.prepare()
        self.assertEqual(self.fixture.run_pipeline()["status"], "complete")
        self.root = self.fixture.root
        self.source = self.fixture.directory
        self.seal = json.loads((self.source / "completed/0.json").read_bytes())
        self.attempt = self.source / self.seal["attempt"]
        self.answers_path = self.attempt / "answers.json"
        self.answers = Answers.from_bytes(self.answers_path.read_bytes())
        self.owner = self.source / "owners/0"
        self.manifest = json.loads((self.owner / "manifest.json").read_bytes())
        self.record = {
            "format": "buddha.native-evaluation.v1",
            "source_generation": {
                "baseline_directory": str(self.source),
                "stage_seal_sha256": sha((self.source / "completed/0.json").read_bytes()),
                "owner_manifest_sha256": self.manifest["record_sha256"],
                "owner_ledger_sha256": sha((self.owner / "operations.sqlite3").read_bytes()),
            },
            "native": copy.deepcopy(self.fixture.record["native"]),
            "stages": copy.deepcopy(self.fixture.record["stages"]),
        }
        self.descriptor = self.root / "evaluation.json"
        self.directory = self.root / "evaluation"
        self.fixture.events.clear()
        self.before_sends = self.fixture.physical_sends

    def configure_source(self, fixture):
        pass

    def prepare(self, *, directory=None, descriptor=None, authority=None):
        path = descriptor or self.descriptor
        path.write_bytes(_json(self.record))
        return prepare_evaluation(
            directory or self.directory,
            descriptor=path,
            authorization=authority or self.fixture.authority,
            review=self.fixture.fixture.review,
        )

    def execute(self, spec, **kwargs):
        self.assertEqual(spec.role, "evaluator", "rejudging must not generate answers")
        return self.fixture.execute(spec, **kwargs)

    def run_evaluation(self, *, directory=None, paid=True):
        with (
            patch.dict(
                os.environ,
                {"OPENAI_API_KEY": gateway_fixtures.KEY} if paid else {},
                clear=True,
            ),
            patch("buddha.executor.run_container", side_effect=self.execute),
            patch(
                "buddha.agent_run.AgentSession",
                side_effect=AssertionError("generation is forbidden in evaluation-only route"),
            ),
        ):
            return run_evaluation(
                directory or self.directory, transport=RawHTTPTransport(allow_paid=paid)
            )

    def check_observation(self, result, *, directory=None):
        directory = directory or self.directory
        path = directory / result["observation"]
        self.assertEqual(json.loads(path.read_bytes()), result)
        self.assertEqual(result["status"], "incomplete")
        self.assertIn(
            result["reason"], {"unknown", "authority", "protocol", "cancelled", "native_error"}
        )
        self.assertTrue((directory / result["owner"] / "manifest.json").is_file())
        if result["attempt"] is not None:
            self.assertTrue((directory / result["attempt"]).is_dir())
        return path


class NativeEvaluationTests(NativeEvaluationFixture):
    def test_two_fresh_occasions_reuse_exact_anchored_c1_and_create_distinct_paid_identities(self):
        self.prepare()
        first = self.run_evaluation()
        self.assertEqual(first["format"], "buddha.native-evaluation-report.v1")
        self.assertEqual(first["status"], "complete")
        self.assertEqual(len(first["stages"]), 3)
        self.assertEqual([event["role"] for event in self.fixture.events], ["evaluator"] * 3)
        self.assertEqual(self.fixture.physical_sends - self.before_sends, 2)
        self.assertEqual(Path(first["summary"]["path"]).read_bytes(), self.fixture.summary_bytes)
        self.assertEqual(
            (self.directory / "native-answers.jsonl").read_bytes(), self.answers.native_bytes()
        )
        self.assertEqual(json.loads(self.answers.native_bytes().splitlines()[0])["qid"], "1")
        self.assertEqual(json.loads(self.answers.native_bytes().splitlines()[1])["qid"], 1)
        first_ids = {event["session"].gateway.ledger.run_id for event in self.fixture.events}
        second_dir = self.root / "evaluation-second"
        self.prepare(directory=second_dir, descriptor=self.root / "evaluation-second.json")
        self.fixture.events.clear()
        second = self.run_evaluation(directory=second_dir)
        self.assertEqual(second["status"], "complete")
        self.assertEqual(self.fixture.physical_sends - self.before_sends, 4)
        second_ids = {event["session"].gateway.ledger.run_id for event in self.fixture.events}
        self.assertTrue(first_ids.isdisjoint(second_ids))
        self.assertEqual(self.answers_path.read_bytes(), self.answers.to_bytes() + b"\n")
        self.assertEqual(
            (second_dir / "native-answers.jsonl").read_bytes(), self.answers.native_bytes()
        )
        stored_first = (self.directory / "report.json").read_bytes()
        before_replay = self.fixture.physical_sends
        with patch(
            "buddha.executor.run_container", side_effect=AssertionError("completed replay executed")
        ):
            with patch.dict(os.environ, {}, clear=True):
                replay = run_evaluation(
                    self.directory, transport=RawHTTPTransport(allow_paid=False)
                )
        self.assertEqual(replay, first)
        self.assertEqual((self.directory / "report.json").read_bytes(), stored_first)
        self.assertEqual(self.fixture.physical_sends, before_replay)

    def test_native_selection_needs_no_retired_producer_agent_code(self):
        roots = dict(self.fixture.native_roots)
        roots["agent"] = self.root / "current-neutral-agent"
        roots["agent"].mkdir()
        (roots["agent"] / "identity.txt").write_text("not mounted or executed", encoding="utf-8")
        release = Release.from_record(self.fixture.agent.release.to_record())
        selection = prepare_selection(
            release, roots, capabilities={gateway_fixtures.CAPABILITY: "profiles/openai.json"}
        )
        self.assertNotEqual(selection.agent_sha256, self.answers.to_record()["agent_sha256"])
        self.record["native"]["roots"] = {name: str(path) for name, path in roots.items()}
        self.record["native"]["selection"] = selection.to_record()
        self.prepare()
        self.assertEqual(self.run_evaluation()["status"], "complete")
        self.assertEqual(self.fixture.physical_sends - self.before_sends, 2)
        for event in self.fixture.events:
            self.assertNotIn("/agent", dict(event["session"].spec.mounts))

    def test_completed_snapshot_cannot_claim_zero_events_for_existing_owners(self):
        self.prepare()
        report = self.run_evaluation()
        report_path = self.directory / "report.json"
        original = report_path.read_bytes()
        report["authorization"]["event_count"] = 0
        report_path.write_bytes(_json(report))
        before = self.fixture.physical_sends
        try:
            with self.assertRaises(EvaluationError):
                self.run_evaluation(paid=False)
            self.assertEqual(self.fixture.physical_sends, before)
        finally:
            report_path.write_bytes(original)
        self.assertEqual(report_path.read_bytes(), original)

    def test_corrupt_source_bindings_fail_before_creating_a_new_owner(self):
        for field in ("stage_seal_sha256", "owner_manifest_sha256", "owner_ledger_sha256"):
            record = copy.deepcopy(self.record)
            self.record["source_generation"][field] = "0" * 64
            target = self.root / ("bad-" + field)
            before = len(self.fixture.authority.summary()["runs"])
            with self.subTest(field=field), self.assertRaises(EvaluationError):
                self.prepare(directory=target, descriptor=self.root / (field + ".json"))
            self.assertFalse(target.exists())
            self.assertEqual(len(self.fixture.authority.summary()["runs"]), before)
            self.record = record
        self.assertEqual(self.fixture.physical_sends, self.before_sends)

    def test_changed_literal_c1_is_rejected_before_any_new_owner(self):
        original = self.answers_path.read_bytes()
        self.answers_path.write_bytes(b" " + original)
        before = len(self.fixture.authority.summary()["runs"])
        try:
            with self.assertRaises(EvaluationError):
                self.prepare()
        finally:
            self.answers_path.write_bytes(original)
        self.assertFalse(self.directory.exists())
        self.assertEqual(len(self.fixture.authority.summary()["runs"]), before)

    def test_source_authority_runtime_identity_must_match_its_original_manifest(self):
        with closing(sqlite3.connect(self.fixture.authority.path)) as db, db:
            triggers = db.execute(
                "SELECT name,sql FROM sqlite_master WHERE type='trigger' ORDER BY name"
            ).fetchall()
            for name, _ in triggers:
                db.execute('DROP TRIGGER "' + name.replace('"', '""') + '"')
            db.execute(
                "UPDATE auth_runs SET runtime_sha256=? WHERE run_id=?",
                ("0" * 64, self.manifest["run_id"]),
            )
            for _, sql in triggers:
                db.execute(sql)
        self.assertNotEqual(self.manifest["execution_sha256"], "0" * 64)
        with self.assertRaises(EvaluationError):
            self.prepare()
        self.assertFalse(self.directory.exists())
        self.assertEqual(self.fixture.physical_sends, self.before_sends)

    def test_first_partition_coverage_failure_cannot_start_quality_or_complete(self):
        self.prepare()
        self.fixture.override_outputs = {"partitions.jsonl": _json({"qid": "1"}) + b"\n"}
        with self.assertRaises(EvaluationError):
            self.run_evaluation()
        self.assertEqual(len(self.fixture.events), 1)
        self.assertEqual(self.fixture.physical_sends - self.before_sends, 1)
        self.assertFalse((self.directory / "completed/1.json").exists())
        observations = list((self.directory / "observations").glob("*.json"))
        self.assertEqual(len(observations), 1)
        observed = json.loads(observations[0].read_bytes())
        self.check_observation(observed)
        self.assertEqual(observed["reason"], "protocol")
        self.assertEqual(observed["stopped_stage"], 1)
        self.assertEqual(observed["stages"], [])
        self.assertTrue((self.directory / observed["attempt"] / "report.json").exists())

    def test_changed_completed_stage_is_invalid_evidence_rather_than_a_funding_stop(self):
        self.prepare()
        self.assertEqual(self.run_evaluation()["status"], "complete")
        seal_path = self.directory / "completed/1.json"
        seal = json.loads(seal_path.read_bytes())
        seal["index"] = False
        seal_path.write_bytes(_json(seal))
        before = self.fixture.physical_sends
        original_report = (self.directory / "report.json").read_bytes()
        with self.assertRaises(EvaluationError):
            self.run_evaluation(paid=False)
        self.assertEqual(self.fixture.physical_sends, before)
        self.assertEqual((self.directory / "report.json").read_bytes(), original_report)
        self.assertEqual(list((self.directory / "observations").glob("*.json")), [])

    def test_summary_request_never_reaches_paid_gateway_or_https(self):
        self.prepare()
        self.fixture.summary_attack = True
        result = self.run_evaluation()
        self.assertEqual(result["status"], "incomplete")
        self.check_observation(result)
        self.assertEqual(self.fixture.physical_sends - self.before_sends, 2)
        self.assertFalse((self.directory / "completed/3.json").exists())

    def test_known_received_reply_recovery_reuses_original_owner_then_completes(self):
        self.prepare()
        self.fixture.fail_native_once = True
        first = self.run_evaluation()
        self.assertEqual(first["status"], "incomplete")
        observed = self.check_observation(first)
        original_observation = observed.read_bytes()
        self.assertEqual(self.fixture.physical_sends - self.before_sends, 1)
        first_owner = self.fixture.events[0]["session"].gateway.directory
        second = self.run_evaluation()
        self.assertEqual(second["status"], "complete")
        self.assertEqual(self.fixture.physical_sends - self.before_sends, 2)
        self.assertEqual(self.fixture.events[1]["session"].gateway.directory, first_owner)
        self.assertEqual(
            self.fixture.events[1]["session"].gateway.ledger.totals()["operation_count"], 1
        )
        self.assertEqual(observed.read_bytes(), original_observation)

    def test_unknown_request_stops_recovery_and_other_fresh_occasion_without_releasing_hold(self):
        self.prepare()
        self.fixture.timeout_native_once = True
        stopped = self.run_evaluation()
        self.assertEqual(stopped["status"], "incomplete")
        self.check_observation(stopped)
        held = self.fixture.authority.summary()["reserved_microusd"]
        self.assertGreater(held, 0)
        after = self.fixture.physical_sends
        self.assertEqual(self.run_evaluation()["status"], "incomplete")
        other = self.root / "blocked-fresh-occasion"
        self.prepare(directory=other, descriptor=self.root / "blocked-fresh.json")
        self.assertEqual(self.run_evaluation(directory=other)["status"], "incomplete")
        self.assertEqual(self.fixture.physical_sends, after)
        self.assertEqual(self.fixture.authority.summary()["reserved_microusd"], held)

    def test_interrupt_after_reply_records_actual_attempt_without_inventing_a_native_report(self):
        self.prepare()
        worker = self.fixture.execute

        def interrupt_after_frames(spec, **kwargs):
            worker(spec, **kwargs)
            raise KeyboardInterrupt

        with (
            patch.object(self.fixture, "execute", side_effect=interrupt_after_frames),
            self.assertRaises(KeyboardInterrupt),
        ):
            self.run_evaluation()
        observations = list((self.directory / "observations").glob("*.json"))
        self.assertEqual(len(observations), 1)
        observed = json.loads(observations[0].read_bytes())
        self.check_observation(observed)
        self.assertEqual(observed["reason"], "cancelled")
        self.assertEqual(observed["owner"], "owners/1")
        self.assertEqual(observed["stages"], [])
        interrupted_attempt = self.directory / observed["attempt"]
        self.assertFalse((interrupted_attempt / "report.json").exists())
        self.assertTrue((interrupted_attempt / "artifacts/partitions.jsonl").exists())
        self.assertEqual(self.fixture.physical_sends - self.before_sends, 1)
        original_observation = observations[0].read_bytes()
        self.assertEqual(self.run_evaluation()["status"], "complete")
        self.assertEqual(self.fixture.physical_sends - self.before_sends, 2)
        self.assertEqual(observations[0].read_bytes(), original_observation)


class SingleCommandEvaluationTests(NativeEvaluationFixture):
    def configure_source(self, fixture):
        fixture.fixture.release_record["commands"] = [
            {"module": "src.summarize", "argv": ["{artifacts}"]}
        ]
        fixture.fixture.release_record["artifacts"]["results"] = ["scores.jsonl"]
        fixture.agent.configure_tasks()
        fixture.agent.descriptor.write_bytes(_json(fixture.agent.record))
        selections = [
            prepare_selection(
                fixture.agent.release,
                roots,
                capabilities={gateway_fixtures.CAPABILITY: "profiles/openai.json"},
            )
            for roots in (fixture.generation_roots, fixture.native_roots)
        ]
        fixture.agent_selection = selections[0]
        fixture.record["generation"]["selection"] = selections[0].to_record()
        fixture.record["native"]["selection"] = selections[1].to_record()
        fixture.record["native"]["hooks"]["modules"] = ["src.summarize"]
        fixture.record["stages"] = [
            {
                "inputs": ["generations.jsonl"],
                "outputs": [
                    {"path": "scores.jsonl", "id_field": "qid"},
                    {"path": "summary.json", "id_field": None},
                ],
                "allow_model": False,
            }
        ]
        self.original_execute = fixture.execute
        fixture.execute = self.summary_execute

    def summary_execute(self, spec, *, initial, handle, **kwargs):
        if spec.role == "agent":
            return self.original_execute(spec, initial=initial, handle=handle, **kwargs)
        session = handle.__self__
        self.assertEqual(session.profiles, {})
        self.assertFalse(session.gateway.transport.allow_paid)
        fixture = self.fixture
        fixture.events.append({"role": spec.role, "initial": initial, "session": session})
        name = "src.summarize"
        audit = {
            name: {
                "kind": "official",
                "path": "/official/src/summarize.py",
                "sha256": initial["inventories"]["official"]["src/summarize.py"],
            }
        }
        handle({"type": "ready", "aliases": [], "audit": audit})
        inputs = dict(spec.mounts)["/inputs"]
        native = (inputs / initial["inputs"][0]["source"]).read_bytes()
        outputs = {"scores.jsonl": native, "summary.json": fixture.summary_bytes}
        for path, raw in outputs.items():
            handle(
                {
                    "type": "file",
                    "path": path,
                    "offset": 0,
                    "eof": True,
                    "data_base64": base64.b64encode(raw).decode(),
                }
            )
        handle({"type": "done", "status": "complete", "reason": "complete", "audit": audit})
        return fixture.agent.execution()

    def test_single_first_and_final_native_command_has_two_independent_no_payment_guards(self):
        self.prepare()
        report = self.run_evaluation()
        self.assertEqual(report["status"], "complete")
        self.assertEqual(len(report["stages"]), 1)
        self.assertEqual(self.fixture.physical_sends, self.before_sends)
        self.assertEqual(Path(report["summary"]["path"]).read_bytes(), self.fixture.summary_bytes)


class PipelineInputTests(unittest.TestCase):
    def test_growth_after_hash_is_rejected_with_bounded_byte_consumption(self):
        from buddha import native_pipeline as pipeline

        with tempfile.TemporaryDirectory() as temporary:
            target = Path(temporary).resolve() / "growing-input.json"
            target.write_bytes(b"{}")
            original_hash = pipeline.file_hash
            original_open = Path.open
            consuming = False
            consumed = 0

            class CappedReader:
                def __init__(self, stream):
                    self.stream = stream

                def __enter__(self):
                    return self

                def __exit__(self, *args):
                    self.stream.close()

                def read(self, size=-1):
                    nonlocal consumed
                    if not 0 < size <= 9:
                        raise AssertionError("unbounded read after the file grew")
                    raw = self.stream.read(size)
                    consumed += len(raw)
                    if consumed > 9:
                        raise AssertionError("file-growth read exceeded the configured ceiling")
                    return raw

            def checked_hash(path, **kwargs):
                nonlocal consuming
                digest = original_hash(path, **kwargs)
                target.write_bytes(b"{}" + b"x" * 1024)
                consuming = True
                return digest

            def checked_open(path, *args, **kwargs):
                stream = original_open(path, *args, **kwargs)
                return CappedReader(stream) if consuming and path == target else stream

            with (
                patch.object(pipeline, "MAX_JSON_BYTES", 8),
                patch.object(pipeline, "file_hash", side_effect=checked_hash),
                patch.object(Path, "open", new=checked_open),
                self.assertRaises(PipelineError),
            ):
                pipeline._read(target)
            self.assertGreater(target.stat().st_size, 8)
            self.assertLessEqual(consumed, 9)


if __name__ == "__main__":
    unittest.main()
