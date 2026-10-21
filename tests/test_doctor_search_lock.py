"""Observing legacy lock metadata cannot hold Windows writer deletion open."""

import io
import os
import threading
import unittest
from contextlib import contextmanager, redirect_stderr, redirect_stdout
from pathlib import Path
from unittest.mock import patch

import test_continuation as continuation
from doctor_helpers import legacy

from buddha import doctor, search, search_evidence
from buddha.__main__ import main


class DoctorSearchLockTests(unittest.TestCase):
    def test_legacy_empty_and_invalid_nonempty_lock_never_open_for_observation(self):
        fixture = legacy(self)
        lock = fixture.directory / ".search.lock"
        opened = Path.open
        observational_open = search_evidence._open_binary

        def unrelated_only(path, *args, **kwargs):
            if path == lock:
                raise AssertionError("observer opened the writer's content-free lock")
            return opened(path, *args, **kwargs)

        def unrelated_observation(path):
            if path == lock:
                raise AssertionError("observer opened the writer's content-free lock")
            return observational_open(path)

        for raw, expected in ((b"", "legacy_empty"), (b"invalid", "invalid")):
            with self.subTest(raw=raw):
                lock.write_bytes(raw)
                with (
                    patch.object(Path, "open", unrelated_only),
                    patch.object(search_evidence, "_open_binary", unrelated_observation),
                ):
                    result = doctor.observe(fixture.directory)
                self.assertEqual(result["status"], "observed")
                self.assertEqual(result["lock"]["status"], expected)
                self.assertNotIn(".search.lock", result["observed_sha256"])
                self.assertEqual(lock.read_bytes(), raw)

    def test_directory_named_legacy_lock_is_invalid_without_opening_it(self):
        fixture = legacy(self)
        (fixture.directory / ".search.lock").mkdir()
        result = doctor.observe(fixture.directory)
        self.assertEqual(result["status"], "observed")
        self.assertEqual(result["lock"]["status"], "invalid")
        self.assertTrue(result["needs_review"])

    def test_hardlinked_legacy_lock_is_rejected_without_opening_it(self):
        fixture = legacy(self)
        lock = fixture.directory / ".search.lock"
        lock.write_bytes(b"")
        os.link(lock, fixture.directory.parent / "lock-alias")
        result = doctor.observe(fixture.directory)
        self.assertEqual(result["status"], "unavailable")
        self.assertIsNone(result["accounting"])

    def test_legacy_metadata_still_has_a_before_and_after_change_guard(self):
        fixture = legacy(self)
        lock = fixture.directory / ".search.lock"
        lock.write_bytes(b"")
        original = doctor._lock

        def changed(capture):
            result = original(capture)
            lock.write_bytes(b"changed while observed")
            return result

        with patch.object(doctor, "_lock", changed):
            result = doctor.observe(fixture.directory)
        self.assertEqual(result["status"], "busy_or_changing")
        self.assertIsNone(result["accounting"])

    def test_pid_lock_still_reads_and_validates_its_actual_ascii_content(self):
        fixture = legacy(self)
        lock = fixture.directory / "running.lock"
        lock.write_bytes(str(os.getpid()).encode("ascii"))
        read = doctor._read
        consumed = []

        def observe_read(path, maximum):
            if path == lock:
                consumed.append(path)
            return read(path, maximum)

        with patch.object(doctor, "_read", observe_read):
            result = doctor.observe(fixture.directory)
        self.assertEqual(result["lock"]["status"], "pid_only")
        self.assertEqual(result["lock"]["pid"], os.getpid())
        self.assertEqual(len(consumed), 2)
        self.assertIn("running.lock", result["observed_sha256"])

    @unittest.skipUnless(os.name == "nt", "Windows denies deletion while an ordinary read is open")
    def test_actual_cli_finishes_when_observer_reaches_legacy_lock_at_writer_exit(self):
        fixture = continuation.ContinuationTests()
        fixture.setUp()
        self.addCleanup(fixture.doCleanups)
        fixture.prepare()
        lock = fixture.out / ".search.lock"
        opened, walk = Path.open, search._walk
        observer_ready, release = threading.Event(), threading.Event()
        observers, observations = [], []

        @contextmanager
        def controlled_open(path, *args, **kwargs):
            with opened(path, *args, **kwargs) as stream:
                if path == lock and threading.current_thread().name == "controlled-observer":
                    observer_ready.set()
                    release.wait(15)
                yield stream

        def observe():
            try:
                observations.append(doctor.observe(fixture.out))
            finally:
                observer_ready.set()

        def finish_walk(*args, **kwargs):
            result = walk(*args, **kwargs)
            worker = threading.Thread(target=observe, name="controlled-observer")
            observers.append(worker)
            worker.start()
            if not observer_ready.wait(5):
                raise AssertionError("observer did not reach the controlled writer boundary")
            return result

        arguments = [
            "search-run",
            "--run",
            str(fixture.out),
            "--authorization",
            str(fixture.authority_path),
        ]
        try:
            with (
                patch(
                    "buddha.__main__._SearchReplay", return_value=continuation.SyntheticTransport()
                ),
                patch.object(search, "_walk", finish_walk),
                patch.object(Path, "open", controlled_open),
                redirect_stdout(io.StringIO()) as output,
                redirect_stderr(io.StringIO()) as errors,
            ):
                result = main(arguments)
            self.assertEqual(result, 0, output.getvalue() + errors.getvalue())
            self.assertFalse(lock.exists())
        finally:
            release.set()
            for observer in observers:
                observer.join(10)
                self.assertFalse(observer.is_alive())
        self.assertEqual(len(observations), 1)


if __name__ == "__main__":
    unittest.main()
