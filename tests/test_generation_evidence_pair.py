"""One checked generation walk supplies publication and literal C1 together."""

import unittest
from unittest.mock import patch

import test_candidate_generation as fixtures

from buddha import candidate_generation, native_evaluation
from buddha.releases import _json, file_hash


class GenerationEvidencePairTests(unittest.TestCase):
    def setUp(self):
        self.enterContext(patch("socket.socket", side_effect=AssertionError("no network")))
        self.enterContext(
            patch("http.client.HTTPSConnection", side_effect=AssertionError("no live HTTPS"))
        )

    def fixture(self, *, callbacks=0):
        h = fixtures.CandidateGenerationTests("runTest")
        h.setUp()
        self.addCleanup(h.doCleanups)
        h.callbacks = callbacks
        h.candidate.record["format"] = "buddha.candidate-generation.v2"
        h.candidate.descriptor.write_bytes(_json(h.candidate.record))
        h.prepare()
        report = h.run_generation(paid=bool(callbacks))
        self.assertEqual(report["disposition"], "generated")
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


if __name__ == "__main__":
    unittest.main()
