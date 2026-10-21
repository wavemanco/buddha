"""Observational reads retain byte guards without blocking Windows writers."""

import ctypes
import io
import os
import sys
import tempfile
import threading
import unittest
from contextlib import contextmanager
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock, patch

from buddha import baseline, doctor, search_evidence
from buddha.common import ValidationError


class ObservationReadTests(unittest.TestCase):
    def windows(self):
        kernel = Mock()
        kernel.CreateFileW.return_value = 2**40 + 7
        kernel.CloseHandle.return_value = True
        convert = Mock(return_value=23)
        loader = self.enterContext(
            patch.object(search_evidence.ctypes, "WinDLL", return_value=kernel, create=True)
        )
        last_error = self.enterContext(
            patch.object(search_evidence.ctypes, "get_last_error", return_value=5, create=True)
        )
        self.enterContext(patch.object(search_evidence.sys, "platform", "win32"))
        self.enterContext(
            patch.dict(sys.modules, {"msvcrt": SimpleNamespace(open_osfhandle=convert)})
        )
        self.enterContext(patch.object(os, "O_BINARY", 0x8000, create=True))
        self.enterContext(patch.object(os, "O_NOINHERIT", 0x80, create=True))
        fdopen = self.enterContext(patch.object(os, "fdopen", return_value=io.BytesIO(b"literal")))
        close = self.enterContext(patch.object(os, "close"))
        return kernel, loader, last_error, convert, fdopen, close

    def test_windows_opener_requests_only_read_with_delete_sharing_and_no_inheritance(self):
        kernel, loader, _, convert, fdopen, close = self.windows()
        path = Path("selected.bin")
        with search_evidence._open_binary(path) as stream:
            self.assertEqual(stream.read(), b"literal")
        loader.assert_called_once_with("kernel32", use_last_error=True)
        kernel.CreateFileW.assert_called_once_with(
            str(path), 0x80000000, 7, None, 3, 0x00200000, None
        )
        self.assertEqual(kernel.CreateFileW.restype, ctypes.wintypes.HANDLE)
        self.assertEqual(len(kernel.CreateFileW.argtypes), 7)
        self.assertEqual(kernel.CloseHandle.argtypes, [ctypes.wintypes.HANDLE])
        self.assertEqual(kernel.CloseHandle.restype, ctypes.wintypes.BOOL)
        convert.assert_called_once_with(2**40 + 7, os.O_RDONLY | 0x8000 | 0x80)
        fdopen.assert_called_once_with(23, "rb", closefd=False)
        close.assert_called_once_with(23)
        kernel.CloseHandle.assert_not_called()
        self.assertTrue(stream.closed)

    def test_windows_invalid_handle_fails_without_conversion_close_or_fallback(self):
        kernel, _, last_error, convert, fdopen, close = self.windows()
        kernel.CreateFileW.return_value = ctypes.c_void_p(-1).value
        with (
            patch.object(Path, "open", side_effect=AssertionError("ordinary fallback")),
            self.assertRaises(OSError),
            search_evidence._open_binary(Path("missing.bin")),
        ):
            self.fail("invalid handle yielded a stream")
        last_error.assert_called_once_with()
        convert.assert_not_called()
        fdopen.assert_not_called()
        close.assert_not_called()
        kernel.CloseHandle.assert_not_called()

    def test_windows_raw_handle_closes_once_on_conversion_error_or_interruption(self):
        kernel, _, _, convert, fdopen, close = self.windows()
        for error in (OSError("conversion failed"), KeyboardInterrupt()):
            with self.subTest(error=type(error).__name__):
                kernel.CloseHandle.reset_mock()
                convert.side_effect = error
                with self.assertRaises(type(error)), search_evidence._open_binary(Path("file")):
                    self.fail("failed conversion yielded a stream")
                kernel.CloseHandle.assert_called_once_with(2**40 + 7)
        fdopen.assert_not_called()
        close.assert_not_called()

    def test_windows_raw_handle_cleanup_failure_is_explicit(self):
        kernel, _, _, convert, _, close = self.windows()
        convert.side_effect = OSError("conversion failed")
        kernel.CloseHandle.return_value = False
        with (
            self.assertRaisesRegex(OSError, "handle cleanup failed"),
            search_evidence._open_binary(Path("file")),
        ):
            self.fail("failed cleanup yielded a stream")
        kernel.CloseHandle.assert_called_once_with(2**40 + 7)
        close.assert_not_called()

    def test_windows_fd_closes_once_if_stream_construction_fails_or_is_interrupted(self):
        kernel, _, _, _, fdopen, close = self.windows()
        for error in (OSError("wrapper failed"), KeyboardInterrupt()):
            with self.subTest(error=type(error).__name__):
                close.reset_mock()
                fdopen.side_effect = error
                with self.assertRaises(type(error)), search_evidence._open_binary(Path("file")):
                    self.fail("failed stream yielded")
                close.assert_called_once_with(23)
        kernel.CloseHandle.assert_not_called()

    def test_windows_consumer_failure_or_interruption_closes_stream_and_fd(self):
        kernel, _, _, _, fdopen, close = self.windows()
        for error in (ValueError("consumer failed"), KeyboardInterrupt()):
            with self.subTest(error=type(error).__name__):
                close.reset_mock()
                fdopen.return_value = io.BytesIO(b"literal")
                with self.assertRaises(type(error)), search_evidence._open_binary(Path("file")):
                    raise error
                self.assertTrue(fdopen.return_value.closed)
                close.assert_called_once_with(23)
        kernel.CloseHandle.assert_not_called()

    def test_windows_descriptor_zero_is_owned_and_close_failure_is_explicit(self):
        kernel, _, _, convert, _, close = self.windows()
        convert.return_value = 0
        close.side_effect = OSError("descriptor cleanup failed")
        with (
            self.assertRaisesRegex(OSError, "descriptor cleanup failed"),
            search_evidence._open_binary(Path("file")),
        ):
            pass
        close.assert_called_once_with(0)
        kernel.CloseHandle.assert_not_called()

    def test_unavailable_windows_api_never_falls_back_to_ordinary_open(self):
        kernel, _, _, convert, fdopen, close = self.windows()
        with (
            patch.object(search_evidence.ctypes, "WinDLL", None),
            patch.object(Path, "open", side_effect=AssertionError("ordinary fallback")),
            self.assertRaisesRegex(OSError, "unavailable"),
            search_evidence._open_binary(Path("file")),
        ):
            pass
        kernel.CreateFileW.assert_not_called()
        convert.assert_not_called()
        fdopen.assert_not_called()
        close.assert_not_called()

    def test_non_windows_keeps_ordinary_binary_context_and_closes_it(self):
        path = Mock(spec=Path)
        path.open.return_value = io.BytesIO(b"\x00\r\n\xff\x1a")
        with (
            patch.object(search_evidence.sys, "platform", "linux"),
            search_evidence._open_binary(path) as stream,
        ):
            self.assertEqual(stream.read(), b"\x00\r\n\xff\x1a")
        path.open.assert_called_once_with("rb")
        self.assertTrue(stream.closed)

    @unittest.skipUnless(os.name == "nt", "actual Windows handle behavior")
    def test_actual_windows_binary_stream_is_noninheritable_and_descriptor_is_closed(self):
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / "literal.bin"
            raw = b"\x00\r\n\xff\x1a"
            path.write_bytes(raw)
            with search_evidence._open_binary(path) as stream:
                descriptor = stream.fileno()
                self.assertFalse(os.get_inheritable(descriptor))
                self.assertEqual(stream.read(), raw)
            self.assertTrue(stream.closed)
            with self.assertRaises(OSError):
                os.fstat(descriptor)

    def test_read_rejects_replacement_after_open_without_blocking_the_writer(self):
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / "selected.bin"
            path.write_bytes(b"olddata")
            original = search_evidence._open_binary

            class ReplaceAfterOpen:
                def __enter__(self):
                    self.context = original(path)
                    stream = self.context.__enter__()
                    path.rename(path.with_name("retired.bin"))
                    path.write_bytes(b"newdata")
                    return stream

                def __exit__(self, *args):
                    return self.context.__exit__(*args)

            with (
                patch.object(search_evidence, "_open_binary", return_value=ReplaceAfterOpen()),
                self.assertRaises(ValidationError),
            ):
                search_evidence._read(path, 7)
            self.assertEqual(path.read_bytes(), b"newdata")

    def test_nonregular_missing_and_hardlinked_inputs_fail_before_open(self):
        with tempfile.TemporaryDirectory() as temporary:
            directory = Path(temporary).resolve()
            missing = directory / "missing"
            linked = directory / "linked"
            linked.write_bytes(b"source")
            os.link(linked, directory / "alias")
            with patch.object(
                search_evidence, "_open_binary", side_effect=AssertionError("unselected open")
            ):
                for path in (directory, missing, linked):
                    with (
                        self.subTest(path=path.name),
                        self.assertRaises((OSError, ValidationError)),
                    ):
                        search_evidence._read(path, 10)
            self.assertFalse(missing.exists())

    def test_opened_handle_type_link_count_and_reparse_flags_are_checked_before_read(self):
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / "source"
            path.write_bytes(b"source")
            original_open, original_fstat = search_evidence._open_binary, os.fstat

            @contextmanager
            def selected_open(selected):
                with original_open(selected) as stream:
                    yield SimpleNamespace(
                        fileno=stream.fileno,
                        read=Mock(side_effect=AssertionError("invalid handle consumed bytes")),
                    )

            for change in ({"st_mode": 0}, {"st_nlink": 2}, {"st_file_attributes": 0x400}):

                def opened_stat(descriptor, change=change):
                    actual = original_fstat(descriptor)
                    values = {
                        name: getattr(actual, name)
                        for name in dir(actual)
                        if name.startswith("st_")
                    }
                    return SimpleNamespace(**(values | change))

                with (
                    self.subTest(change=change),
                    patch.object(search_evidence, "_open_binary", selected_open),
                    patch.object(os, "fstat", opened_stat),
                    self.assertRaises(ValidationError),
                ):
                    search_evidence._read(path, 10)

    @unittest.skipUnless(os.name == "nt", "Windows descriptor transfer is the contract under test")
    def test_fdopen_failure_never_closes_a_newly_reused_descriptor(self):
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / "source.bin"
            other = Path(temporary) / "unrelated.bin"
            path.write_bytes(b"source")
            other.write_bytes(b"unrelated")
            original = os.fdopen
            replacements = []

            def fail_after_wrapper_creation(descriptor, *args, **kwargs):
                # Match CPython's failure path after the raw stream is built:
                # it closes that wrapper before propagating the later error.
                stream = original(descriptor, *args, **kwargs)
                stream.close()
                replacements.append(os.open(other, os.O_RDONLY | os.O_BINARY))
                raise OSError("injected post-wrapper failure")

            try:
                with (
                    patch.object(os, "fdopen", fail_after_wrapper_creation),
                    self.assertRaisesRegex(OSError, "injected post-wrapper failure"),
                    search_evidence._open_binary(path),
                ):
                    self.fail("failed wrapper unexpectedly yielded a stream")
                self.assertEqual(len(replacements), 1)
                # The unrelated descriptor must survive the opener's cleanup.
                self.assertEqual(os.read(replacements[0], 9), b"unrelated")
            finally:
                for descriptor in replacements:
                    try:
                        os.close(descriptor)
                    except OSError:
                        pass

    def test_stable_actual_pid_lock_keeps_its_codec_and_closes_before_writer_exit(self):
        with tempfile.TemporaryDirectory() as temporary:
            directory = Path(temporary).resolve()
            with baseline._exclusive(directory):
                captured = doctor._Capture(directory)
                lock, writer = doctor._lock(captured)
                self.assertEqual(
                    lock, {"status": "pid_only", "name": "running.lock", "pid": os.getpid()}
                )
                self.assertEqual(writer["identity"], "unknown")
                self.assertIn("running.lock", captured.finish())
            self.assertFalse((directory / "running.lock").exists())

    @unittest.skipUnless(os.name == "nt", "Windows file sharing is the contract under test")
    def test_actual_pid_observer_does_not_prevent_writer_unlink_while_stream_is_open(self):
        with tempfile.TemporaryDirectory() as temporary:
            directory = Path(temporary).resolve()
            lock = directory / "running.lock"
            opened, release = threading.Event(), threading.Event()
            original_fstat = os.fstat
            observed, errors = [], []
            identity = None

            def fstat(descriptor):
                information = original_fstat(descriptor)
                if (
                    threading.current_thread().name == "controlled-pid-observer"
                    and (information.st_dev, information.st_ino) == identity
                    and not opened.is_set()
                ):
                    opened.set()
                    if not release.wait(10):
                        raise AssertionError("controlled reader was not released")
                return information

            def observe():
                try:
                    captured = doctor._Capture(directory)
                    state, _ = doctor._lock(captured)
                    try:
                        captured.finish()
                    except (doctor._Busy, OSError, ValidationError) as error:
                        observed.append({"lock": state, "change": type(error).__name__})
                    else:
                        observed.append({"lock": state, "change": None})
                except BaseException as error:
                    errors.append(type(error).__name__)

            worker = threading.Thread(target=observe, name="controlled-pid-observer")
            writer_error = None
            try:
                with patch.object(os, "fstat", fstat):
                    try:
                        with baseline._exclusive(directory):
                            information = lock.stat()
                            identity = (information.st_dev, information.st_ino)
                            worker.start()
                            self.assertTrue(opened.wait(5), "actual observer stream never opened")
                    except OSError as error:
                        writer_error = {"type": type(error).__name__, "winerror": error.winerror}
                    retained = lock.exists()
            finally:
                release.set()
                if worker.ident is not None:
                    worker.join(10)
            self.assertFalse(worker.is_alive())
            self.assertEqual(errors, [])
            self.assertIsNone(writer_error, {"failure": writer_error, "lock_retained": retained})
            self.assertFalse(retained)
            self.assertEqual(len(observed), 1)
            self.assertIsNotNone(observed[0]["change"], observed)


if __name__ == "__main__":
    unittest.main()
