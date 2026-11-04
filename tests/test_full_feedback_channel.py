"""Complete notes cross real host/worker contracts; only trusted seed code executes."""

import copy
import hashlib
import io
import json
import sys
import unittest
from pathlib import Path
from types import ModuleType
from unittest.mock import Mock, patch, sentinel

import test_candidate_improvement as improvement_fixtures
import test_source_seed as seed_fixtures

from buddha import source_seed
from buddha.candidate_worker import CandidateWorker, CandidateWorkerError
from buddha.channel import read_frame, write_frame
from buddha.releases import MAX_FEEDBACK_BYTES, _json

LEGACY = "buddha.source-seed-improver.v1"
CURRENT = "buddha.source-seed-improver.v2"
LEGACY_FRAGMENT_SHA256 = "3ce8b36db69a009d087ebbc0de8bd1f67234c1c090a0443feea2d80700557032"
CHILD = {"source": "MODEL_RETURNED_CHILD_IS_DATA [", "hypothesis": "Synthetic supplied change."}


def sha(raw):
    return hashlib.sha256(raw).hexdigest()


class FullFeedbackChannelTests(unittest.TestCase):
    def trusted_seed(self, *, legacy=False):
        frozen = (Path(__file__).resolve().parents[1] / "agents/frozen_seed.py").read_bytes()
        raw = (
            source_seed.compose_source_seed(frozen, fragment_version=LEGACY)
            if legacy
            else source_seed.compose_source_seed(frozen)
        )
        module = ModuleType("_trusted_full_feedback_seed")
        # Only factory-verified repository seed/fragment bytes execute, never child text.
        exec(compile(raw, "<trusted-full-feedback-seed>", "exec"), vars(module))  # nosec B102
        return frozen, raw, module

    def fixture(self, note, *, version=2, source=None):
        fixture = improvement_fixtures.ImprovementTests("runTest")
        fixture.setUp()
        self.addCleanup(fixture.doCleanups)
        fixture.feedback["format"] = "buddha.candidate-development-feedback.v" + str(version)
        fixture.feedback["records"] = [{"task_id": "a", "note": note}]
        if source is not None:
            fixture.h.source.write_bytes(source)
        fixture.freeze()
        return fixture

    def worker_dispatch(self, session, raw, trusted):
        framed = io.BytesIO()
        write_frame(framed, session.worker)
        framed.seek(0)
        initial = read_frame(framed)
        self.assertEqual(initial, session.worker)
        output = io.BytesIO()
        worker = CandidateWorker(initial, io.BytesIO(), output)
        complete = Mock(return_value=seed_fixtures.response("openai", json.dumps(CHILD)))

        def load_parent(code, namespace):
            self.assertIs(code, sentinel.trusted_parent_compile)
            namespace["generate"] = trusted.generate
            namespace["propose_improvement"] = trusted.propose_improvement

        # The worker's untrusted-code loader is intercepted; actual trusted functions
        # still receive its real detached feedback and invoke the mock model callback.
        with (
            patch.object(worker, "_sources"),
            patch.object(worker, "_runtime"),
            patch.object(worker, "_complete", complete),
            patch("buddha.candidate_worker._consume", return_value=raw),
            patch(
                "builtins.compile", return_value=sentinel.trusted_parent_compile
            ) as compile_parent,
            patch("builtins.exec", side_effect=load_parent),
            patch.dict(sys.modules),
        ):
            done = worker.run()
        compile_parent.assert_called_once()
        self.assertEqual(compile_parent.call_args.args[0], raw)
        self.assertEqual((done["status"], done["reason"]), ("complete", "complete"))
        self.assertEqual(done["proposal"]["value"], CHILD)
        complete.assert_called_once()
        output.seek(0)
        ready, saved_done = read_frame(output), read_frame(output)
        self.assertEqual(ready["feedback_sha256"], sha(_json(initial["feedback"])))
        self.assertEqual(saved_done, done)
        request = json.loads(complete.call_args.args[1])
        text = request["messages"][-1]["content"]
        payload = json.loads(text.split("\n\nINPUT_JSON\n", 1)[1])
        return initial, payload

    def test_v2_full_note_crosses_host_frame_worker_and_trusted_seed_callback(self):
        frozen, raw, trusted = self.trusted_seed()
        note = "BEGIN_FULL_OUTPUT\n" + "α雪 literal line with spaces  \n" * 400 + "END_FULL_OUTPUT"
        self.assertGreater(len(note.encode("utf-8")), 4096)
        fixture = self.fixture(note, source=raw)
        session = fixture.h.session()
        self.assertEqual(fixture.h.record["format"], "buddha.candidate-improvement.v1")
        self.assertEqual(session.worker["format"], "buddha.candidate-improvement-worker.v2")
        self.assertTrue(raw.startswith(frozen))
        self.assertNotIn(b"FINAL_SECRET", _json(session.worker))
        self.assertNotIn(b"VALIDATION_SECRET", _json(session.worker))
        initial, payload = self.worker_dispatch(session, raw, trusted)
        self.assertEqual(payload["format"], CURRENT)
        self.assertEqual(initial["feedback"][0]["note"], note)
        self.assertEqual(payload["development_feedback"], initial["feedback"])
        self.assertEqual(
            sha(payload["development_feedback"][0]["note"].encode()), sha(note.encode())
        )
        self.assertEqual(fixture.h.source.read_bytes(), raw)

    def test_v1_4096_boundary_and_literal_legacy_fragment_remain(self):
        frozen, raw, trusted = self.trusted_seed(legacy=True)
        fragment = raw[len(frozen) + 2 :]
        self.assertEqual(len(fragment), 5512)
        self.assertEqual(sha(fragment), LEGACY_FRAGMENT_SHA256)
        note = "é" * 2048
        self.assertEqual(len(note.encode()), 4096)
        fixture = self.fixture(note, version=1, source=raw)
        session = fixture.h.session()
        self.assertEqual(session.worker["format"], "buddha.candidate-improvement-worker.v1")
        _, payload = self.worker_dispatch(session, raw, trusted)
        self.assertEqual(payload["format"], LEGACY)
        self.assertEqual(payload["development_feedback"][0]["note"], note)
        oversized = note + "x"
        fixture.feedback["records"][0]["note"] = oversized
        fixture.freeze()
        with self.assertRaises(fixture.h.Error):
            fixture.h.session()
        self.assertFalse(fixture.h.output.exists())
        initial = copy.deepcopy(session.worker)
        initial["feedback"][0]["note"] = oversized
        with self.assertRaises(CandidateWorkerError):
            CandidateWorker(initial, io.BytesIO(), io.BytesIO())
        complete = Mock()
        parent = {"entrypoint": "candidate.py", "source": raw.decode(), "agent_sha256": "a" * 64}
        with self.assertRaises(trusted.SeedError):
            trusted.propose_improvement(parent, initial["feedback"], session.config, complete)
        complete.assert_not_called()

    def test_current_seed_forwards_complete_notes_to_both_provider_recipes(self):
        _, raw, trusted = self.trusted_seed()
        note = "Beginning. " + "é雪 full output\n" * 500 + " FINAL ENDING. "
        feedback = [{"task": {"id": "a", "prompt": "Original task.", "count": 2}, "note": note}]
        parent = {"entrypoint": "candidate.py", "source": raw.decode(), "agent_sha256": "a" * 64}
        for provider in ("openai", "anthropic"):
            with self.subTest(provider=provider):
                complete = Mock(return_value=seed_fixtures.response(provider, json.dumps(CHILD)))
                self.assertEqual(
                    trusted.propose_improvement(
                        parent, feedback, seed_fixtures.configuration(provider), complete
                    ),
                    CHILD,
                )
                complete.assert_called_once()
                self.assertEqual(complete.call_args.args[0], provider)
                body = json.loads(complete.call_args.args[1])
                content = body["messages"][-1]["content"]
                if provider == "anthropic":
                    content = content[0]["text"]
                packet = json.loads(content.split("\n\nINPUT_JSON\n", 1)[1])
                self.assertEqual(packet["parent"], parent)
                self.assertEqual(packet["development_feedback"], feedback)

    def test_v2_escaped_aggregate_refuses_before_host_output_or_worker_callback(self):
        _, raw, trusted = self.trusted_seed()
        note = "雪" * 180000
        feedback = [{"task": {"id": "a", "prompt": "development task", "count": 2}, "note": note}]
        self.assertLess(len(note.encode()), MAX_FEEDBACK_BYTES)
        self.assertGreater(len(_json(feedback)), MAX_FEEDBACK_BYTES)
        fixture = self.fixture(note, source=raw)
        with self.assertRaises(fixture.h.Error):
            fixture.h.session()
        self.assertFalse(fixture.h.output.exists())
        fixture.feedback["records"][0]["note"] = "short complete note"
        fixture.freeze()
        session = fixture.h.session()
        initial = copy.deepcopy(session.worker)
        initial["feedback"] = feedback
        with self.assertRaises(CandidateWorkerError):
            CandidateWorker(initial, io.BytesIO(), io.BytesIO())
        complete = Mock()
        parent = {"entrypoint": "candidate.py", "source": raw.decode(), "agent_sha256": "a" * 64}
        with self.assertRaises(trusted.SeedError):
            trusted.propose_improvement(parent, feedback, session.config, complete)
        complete.assert_not_called()

    def test_versions_invalid_notes_and_traversing_host_reference_fail_closed(self):
        _, raw, trusted = self.trusted_seed()
        fixture = self.fixture("complete note", version=1, source=raw)
        session = fixture.h.session()
        fixture.feedback["format"] = "buddha.candidate-development-feedback.v3"
        fixture.freeze()
        with self.assertRaises(fixture.h.Error):
            fixture.h.session()
        self.assertFalse(fixture.h.output.exists())
        fixture.feedback["format"] = "buddha.candidate-development-feedback.v2"
        fixture.feedback["source"]["path"] = str(fixture.source_path.parent / ".." / "source.json")
        fixture.freeze()
        with self.assertRaises(fixture.h.Error):
            fixture.h.session()
        self.assertFalse(fixture.h.output.exists())
        for version, note in (("v3", "complete"), ("v2", 7), ("v2", "\ud800"), ("v2", "  ")):
            with self.subTest(version=version, note_type=type(note).__name__):
                initial = copy.deepcopy(session.worker)
                initial["format"] = "buddha.candidate-improvement-worker." + version
                initial["feedback"][0]["note"] = note
                with self.assertRaises(CandidateWorkerError):
                    CandidateWorker(initial, io.BytesIO(), io.BytesIO())
        parent = {"entrypoint": "candidate.py", "source": raw.decode(), "agent_sha256": "a" * 64}
        for note in (7, "\ud800", "  "):
            complete = Mock()
            feedback = [
                {"task": {"id": "a", "prompt": "development task", "count": 2}, "note": note}
            ]
            with self.assertRaises(trusted.SeedError):
                trusted.propose_improvement(parent, feedback, session.config, complete)
            complete.assert_not_called()
        with self.assertRaises(source_seed.SourceSeedError):
            source_seed.compose_source_seed(
                (Path(__file__).resolve().parents[1] / "agents/frozen_seed.py").read_bytes(),
                fragment_version="buddha.source-seed-improver.v3",
            )


if __name__ == "__main__":
    unittest.main()
