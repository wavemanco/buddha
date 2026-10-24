"""One checked generation walk supplies publication and literal C1 together."""

import json
import unittest
from unittest.mock import patch

import test_candidate_generation as fixtures

from buddha import candidate_generation, native_evaluation
from buddha.doctor import _Busy, _Capture
from buddha.native_evidence import _adopt_capture
from buddha.releases import _json, file_hash


class GenerationEvidencePairTests(unittest.TestCase):
    def setUp(self):
        self.enterContext(patch("socket.socket", side_effect=AssertionError("no network")))
        self.enterContext(
            patch("http.client.HTTPSConnection", side_effect=AssertionError("no live HTTPS"))
        )
        self.enterContext(patch("subprocess.Popen", side_effect=AssertionError("no process")))

    def fixture(self, *, callbacks=0, failed=False):
        h = fixtures.CandidateGenerationTests("runTest")
        h.setUp()
        self.addCleanup(h.doCleanups)
        h.callbacks = callbacks
        h.candidate.record["format"] = "buddha.candidate-generation.v2"
        h.candidate.descriptor.write_bytes(_json(h.candidate.record))
        h.prepare()

        def failure(spec, *, handle, **kwargs):
            handle(h.candidate.done([], "failed", "agent_error"))
            return h.execution(spec)

        if failed:
            with patch.object(h, "execute", side_effect=failure):
                report = h.run_generation()
        else:
            report = h.run_generation(paid=bool(callbacks))
        self.assertEqual(
            report["disposition"], "candidate_execution_failed" if failed else "generated"
        )
        return h, report

    def paired(self, h):
        return native_evaluation._read_published_generation(
            h.directory,
            authorization=h.fixture.authority.path,
            expected_report_sha256=file_hash(h.directory / "report.json"),
        )

    def test_one_walk_returns_original_publication_and_exact_direct_source(self):
        h, expected = self.fixture(callbacks=1)
        direct = native_evaluation._read_generation(
            expected["source_generation"], h.fixture.authority.path
        )
        with patch.object(
            candidate_generation, "_read_evidence", wraps=candidate_generation._read_evidence
        ) as walked:
            report, source, capture = self.paired(h)
        self.assertEqual(walked.call_count, 1)
        self.assertEqual(report, expected)
        self.assertEqual(source, direct)
        self.assertNotIn(h.directory / "report.json", source.files)
        self.assertEqual(capture.raw[h.directory / "report.json"], _json(expected))
        capture.finish()

    def test_checked_failure_is_a_publication_without_an_answer_source(self):
        h, expected = self.fixture(failed=True)
        with patch.object(
            candidate_generation, "_read_evidence", wraps=candidate_generation._read_evidence
        ) as walked:
            report, source, capture = self.paired(h)
        self.assertEqual(walked.call_count, 1)
        self.assertEqual(report, expected)
        self.assertIsNone(source)
        self.assertIn(h.directory / "report.json", capture.raw)
        with self.assertRaises(candidate_generation.CandidateGenerationError):
            candidate_generation.read_candidate_generation_source(
                expected["source_generation"], h.fixture.authority.path
            )
        self.assertEqual((h.native_workers, h.physical_sends), (0, 0))

    def test_separate_observations_reread_and_refuse_a_forged_publication(self):
        h, expected = self.fixture()
        with patch.object(
            candidate_generation, "_read_evidence", wraps=candidate_generation._read_evidence
        ) as walked:
            first, source, first_capture = self.paired(h)
            second, repeated, second_capture = self.paired(h)
        self.assertEqual(walked.call_count, 2)
        self.assertEqual((first, second), (expected, expected))
        self.assertEqual(source, repeated)
        self.assertIsNot(first_capture, second_capture)
        path = h.directory / "report.json"
        forged = json.loads(path.read_bytes())
        forged["authorization"]["reserved_microusd"] = False
        path.write_bytes(_json(forged))
        with self.assertRaises(native_evaluation.EvaluationError):
            self.paired(h)

    def test_both_source_routes_keep_the_imported_reader_identity_guard(self):
        h, expected = self.fixture()
        with (
            patch.object(candidate_generation, "__file__", str(h.root / "other.py")),
            patch.object(
                candidate_generation, "_read_evidence", wraps=candidate_generation._read_evidence
            ) as walked,
        ):
            with self.assertRaises(native_evaluation.EvaluationError):
                self.paired(h)
            with self.assertRaises(native_evaluation.EvaluationError):
                native_evaluation._read_generation(
                    expected["source_generation"], h.fixture.authority.path
                )
        self.assertEqual(walked.call_count, 0)

    def test_full_capture_adoption_keeps_late_byte_and_database_sidecar_checks(self):
        h, _ = self.fixture()
        for kind in ("bytes", "sidecar"):
            with self.subTest(drift=kind):
                _, _, inner = self.paired(h)
                aggregate = h.root / ("aggregate-" + kind)
                aggregate.mkdir()
                outer = _Capture(aggregate)
                _adopt_capture(inner, outer)
                self.assertTrue(inner.raw.keys() <= outer.raw.keys())
                self.assertTrue(inner.databases <= outer.databases)
                if kind == "bytes":
                    path = h.attempt() / "session/report.json"
                    original = path.read_bytes()
                    path.write_bytes(original[:-1] + (b"x" if original[-1:] != b"x" else b"y"))
                else:
                    path = h.directory / "owners/0/operations.sqlite3-wal"
                    path.write_bytes(b"pending external change")
                try:
                    with self.assertRaises(_Busy):
                        outer.finish()
                finally:
                    if kind == "bytes":
                        path.write_bytes(original)
                    else:
                        path.unlink()


if __name__ == "__main__":
    unittest.main()
