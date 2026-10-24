"""One genuine generation observation per published consumer; supplied workers only."""

import copy
import os
import unittest
from functools import partial
from unittest.mock import patch

import test_source_launch_state as launch_fixtures
import test_source_screen_outcome as screen_fixtures
import test_validation_study as validation_fixtures

from buddha import (
    candidate_generation,
    doctor,
    native_pipeline,
    source_screen_results,
    validation_study,
)
from buddha.gateway import RawHTTPTransport
from buddha.releases import _json


class GenerationEvidenceCompositionTests(unittest.TestCase):
    def setUp(self):
        for name in (
            "subprocess.Popen",
            "socket.socket",
            "socket.create_connection",
            "socket.socket.connect",
            "socket.getaddrinfo",
        ):
            self.enterContext(patch(name, side_effect=AssertionError("real I/O forbidden")))

    def screen(self, *, prospective=True, failed=False):
        fixture = screen_fixtures.SourceScreenOutcomeTests("runTest")
        self.addCleanup(fixture.doCleanups)
        h = fixture.fixture()
        record = copy.deepcopy(h.record)
        record["format"] = "buddha.source-screen.v2" if prospective else "buddha.source-screen.v1"
        record["selected_ids"] = ["1"]
        screen = h.screen(record)
        directory, authority = h.prepare(screen)
        if failed:
            with patch.object(h, "execute", side_effect=fixture.failed_worker(h, "1", h.execute)):
                report = h.run_screen(directory)
        else:
            report = h.run_screen(directory)
        self.assertEqual(report["status"], "complete")
        return h, directory, authority, report

    def paired_walks(self, module, name, inspect):
        consume = getattr(module, name)
        deltas = []
        with patch.object(
            candidate_generation, "_read_evidence", wraps=candidate_generation._read_evidence
        ) as walks:

            def paired(*args, **kwargs):
                before = walks.call_count
                result = consume(*args, **kwargs)
                deltas.append(walks.call_count - before)
                return result

            with patch.object(module, name, side_effect=paired):
                result = inspect()
        self.assertTrue(deltas, "the genuine paired consumer must be exercised")
        self.assertEqual(deltas, [1] * len(deltas))
        return result

    def test_complete_screen_reads_each_generation_once_and_keeps_v1_compatibility(self):
        for prospective in (False, True):
            with self.subTest(prospective=prospective):
                h, directory, authority, report = self.screen(prospective=prospective)
                self.assertEqual(len(report["tasks"]), 1)
                self.assertEqual(
                    self.paired_walks(
                        source_screen_results, "_source", partial(h.inspect, directory, authority)
                    ),
                    report,
                )

    def test_completed_validation_replay_reads_once_per_paired_consumption(self):
        h = validation_fixtures.ValidationStudyTests("runTest")
        h.setUp()
        self.addCleanup(h.doCleanups)
        h.record["repetitions"] = 1
        h.declaration = h.write("declaration.json", h.record)
        h.prepare()
        authority = h.authority()
        with h.offline():
            report = h.run_occasion(authority)
        self.assertEqual(report["status"], "complete")
        self.assertEqual(len(h.generation_events), 2)
        before = (
            {str(p): p.read_bytes() for p in h.directory.rglob("*") if p.is_file()},
            authority.path.read_bytes(),
            h.engine.physical_sends,
        )
        with (
            patch.dict(os.environ, {}, clear=True),
            patch("buddha.gateway.Gateway.__init__", side_effect=AssertionError("active gateway")),
            patch(
                "buddha.authorization.Authorization.__init__",
                side_effect=AssertionError("active authorization"),
            ),
            patch("buddha.executor.run_container", side_effect=AssertionError("worker executed")),
            patch("http.client.HTTPSConnection", side_effect=AssertionError("HTTPS constructed")),
            patch("buddha.native_pipeline._exclusive", side_effect=AssertionError("writer lock")),
        ):
            replay = self.paired_walks(
                validation_study,
                "_generation",
                lambda: h.run_occasion(authority, transport=RawHTTPTransport(allow_paid=False)),
            )
        self.assertEqual(replay, report)
        self.assertEqual(
            (
                {str(p): p.read_bytes() for p in h.directory.rglob("*") if p.is_file()},
                authority.path.read_bytes(),
                h.engine.physical_sends,
            ),
            before,
        )

    def test_pending_native_launch_inspection_reads_published_generation_once(self):
        fixture = launch_fixtures.SourceLaunchStateTests("runTest")
        self.addCleanup(fixture.doCleanups)
        h = fixture.fixture()
        h.prepare()
        h.engine.native_fail_once = True
        self.assertEqual(h.run_search()["status"], "incomplete")
        generation = h.directory / "seed/tasks/0/generation"
        self.assertTrue((generation / "report.json").is_file())
        self.assertFalse((h.directory / "seed/report.json").exists())
        with patch.object(
            candidate_generation, "_read_evidence", wraps=candidate_generation._read_evidence
        ) as walks:
            report = fixture.inspect(h)
        self.assertEqual(report["next_role"], "native")
        self.assertEqual(walks.call_count, 1)

    def test_public_screen_final_check_rejects_late_consumed_bytes_and_sqlite_sidecar(self):
        h, directory, authority, report = self.screen()
        generation = directory / "tasks/0/generation"
        consumed = generation / "completed/0.json"
        original = consumed.read_bytes()
        sidecar = generation / "owners/0/operations.sqlite3-wal"
        self.assertFalse(sidecar.exists())
        before = h.files(directory), authority.path.read_bytes(), h.engine.physical_sends
        source = source_screen_results._source
        finish = doctor._Capture.finish
        for fault in ("consumed_bytes", "sqlite_sidecar"):
            outer_finish = []
            inner_complete = []

            def late_fault(*args, _fault=fault, _inner=inner_complete, **kwargs):
                result = source(*args, **kwargs)
                self.assertEqual(result[0].tasks.tasks[0].id, "1")
                _inner.append(True)
                if _fault == "consumed_bytes":
                    consumed.write_bytes(bytes([original[0] ^ 1]) + original[1:])
                else:
                    sidecar.write_bytes(b"late nonempty SQLite sidecar")
                return result

            def final_check(capture, _outer=outer_finish):
                if capture.root == directory:
                    _outer.append(True)
                return finish(capture)

            with self.subTest(fault=fault):
                try:
                    with (
                        h.readonly(),
                        patch.dict(os.environ, {}, clear=True),
                        patch.object(source_screen_results, "_source", side_effect=late_fault),
                        patch.object(doctor._Capture, "finish", new=final_check),
                        self.assertRaises(h.Error),
                    ):
                        h.inspect_api(
                            directory,
                            authorization=authority.path,
                            expected_report_sha256=screen_fixtures.fixtures.sha(_json(report)),
                        )
                finally:
                    consumed.write_bytes(original)
                    if sidecar.exists():
                        sidecar.unlink()
                self.assertEqual(inner_complete, [True])
                self.assertTrue(outer_finish, "the whole public reader must reach its final check")
                self.assertEqual(
                    (h.files(directory), authority.path.read_bytes(), h.engine.physical_sends),
                    before,
                )
        self.assertEqual(h.inspect(directory, authority), report)

    def test_failed_screen_replay_has_no_c1_or_native_consumption(self):
        h, directory, authority, report = self.screen(failed=True)
        self.assertEqual(report["disposition"], "candidate_execution_failed")
        self.assertEqual(report["tasks"], [])
        self.assertEqual(h.native_events, [])
        self.assertFalse((directory / "tasks/0/evaluation").exists())
        with (
            patch.object(
                source_screen_results, "_read_generation", side_effect=AssertionError("failed C1")
            ),
            patch.object(
                source_screen_results, "_native", side_effect=AssertionError("failed native")
            ),
        ):
            self.assertEqual(h.inspect(directory, authority), report)

    def test_sealed_unpublished_launch_keeps_bare_evidence_and_no_new_attempt(self):
        fixture = launch_fixtures.SourceLaunchStateTests("runTest")
        self.addCleanup(fixture.doCleanups)
        h = fixture.fixture()
        h.prepare()
        generation = h.directory / "seed/tasks/0/generation"
        publish = native_pipeline.publish_complete

        def before_publication(path, *args, **kwargs):
            if path == generation / "report.json":
                self.assertTrue((generation / "completed/0.json").is_file())
                raise KeyboardInterrupt("synthetic sealed generation publication stop")
            return publish(path, *args, **kwargs)

        with (
            patch.object(native_pipeline, "publish_complete", side_effect=before_publication),
            self.assertRaises(KeyboardInterrupt),
        ):
            h.run_search()
        self.assertTrue((generation / "completed/0.json").is_file())
        self.assertFalse((generation / "report.json").exists())
        before = h.engine.workers, h.engine.native_workers
        with patch.object(
            candidate_generation, "_read_evidence", wraps=candidate_generation._read_evidence
        ) as walks:
            report = fixture.inspect(h)
        self.assertEqual(walks.call_count, 1)
        self.assertEqual(report["next_role"], "native")
        self.assertEqual(
            report["next_owner"], str(h.directory / "seed/tasks/0/evaluation/owners/1")
        )
        self.assertFalse(report["inactive_pending"])
        self.assertEqual((h.engine.workers, h.engine.native_workers), before)
        self.assertEqual([path.name for path in (generation / "attempts").iterdir()], ["0-0"])
        self.assertFalse((generation / "report.json").exists())


if __name__ == "__main__":
    unittest.main()
