"""Numeric PID observations never identify the writer or signal a process."""

import gc
import json
import os
import sys
import unittest
import warnings
from unittest.mock import Mock, patch

import buddha.process_observation as observation
from buddha.common import ValidationError


class ProcessObservationTests(unittest.TestCase):
    def windows(self, *, handle=123, waited=258, closed=1, error=5):
        kernel = Mock()
        kernel.OpenProcess.return_value = handle
        kernel.WaitForSingleObject.return_value = waited
        kernel.CloseHandle.return_value = closed
        self.enterContext(patch.object(observation.sys, "platform", "win32"))
        loader = self.enterContext(
            patch.object(observation.ctypes, "WinDLL", return_value=kernel, create=True)
        )
        self.enterContext(
            patch.object(observation.ctypes, "get_last_error", return_value=error, create=True)
        )
        return kernel, loader

    def test_invalid_pid_rejected_before_platform_or_os_probe(self):
        with (
            patch.object(observation, "_linux") as linux,
            patch.object(observation, "_windows") as windows,
        ):
            for pid in (None, True, False, 0, -1, 2**31, 1.5, "123", [], {}):
                with self.subTest(pid=pid), self.assertRaises(ValidationError):
                    observation.observe_pid(pid)
            linux.assert_not_called()
            windows.assert_not_called()

    def test_unsupported_platform_is_unavailable_without_other_probes(self):
        with (
            patch.object(observation.sys, "platform", "darwin"),
            patch.object(observation, "_linux") as linux,
            patch.object(observation, "_windows") as windows,
        ):
            self.assertEqual(observation.observe_pid(7), {"pid": 7, "status": "unavailable"})
            linux.assert_not_called()
            windows.assert_not_called()

    def test_linux_opens_numeric_pid_without_signals_and_closes_descriptor(self):
        with (
            patch.object(observation.sys, "platform", "linux"),
            patch.object(observation.os, "pidfd_open", return_value=19, create=True) as opened,
            patch.object(observation.os, "close") as closed,
            patch.object(observation.os, "kill", side_effect=AssertionError("sent signal")),
        ):
            self.assertEqual(observation.observe_pid(42), {"pid": 42, "status": "present"})
            opened.assert_called_once_with(42, 0)
            closed.assert_called_once_with(19)

    def test_linux_only_process_lookup_error_establishes_absent(self):
        with patch.object(observation.sys, "platform", "linux"):
            for error, status in (
                (ProcessLookupError(3, "absent"), "absent"),
                (PermissionError(1, "private error"), "unavailable"),
                (OSError(38, "unsupported kernel"), "unavailable"),
                (OSError(24, "descriptor limit"), "unavailable"),
            ):
                with (
                    self.subTest(error=error),
                    patch.object(observation.os, "pidfd_open", side_effect=error, create=True),
                    patch.object(observation.os, "close") as closed,
                ):
                    self.assertEqual(observation.observe_pid(42), {"pid": 42, "status": status})
                    closed.assert_not_called()

    def test_linux_without_pidfd_does_not_guess_from_proc_or_signal(self):
        with (
            patch.object(observation.sys, "platform", "linux"),
            patch.object(observation.os, "pidfd_open", None, create=True),
            patch("builtins.open", side_effect=AssertionError("unexpected file read")),
            patch.object(observation.os, "kill", side_effect=AssertionError("sent signal")),
        ):
            self.assertEqual(observation.observe_pid(42), {"pid": 42, "status": "unavailable"})

    def test_linux_close_failure_is_not_reported_as_healthy_observation(self):
        with (
            patch.object(observation.sys, "platform", "linux"),
            patch.object(observation.os, "pidfd_open", return_value=19, create=True),
            patch.object(observation.os, "close", side_effect=OSError("close failed")) as closed,
        ):
            self.assertEqual(observation.observe_pid(42), {"pid": 42, "status": "unavailable"})
            closed.assert_called_once_with(19)

    def test_windows_uses_noninherited_synchronize_only_and_zero_timeout(self):
        kernel, loader = self.windows()
        with patch.object(observation.os, "kill", side_effect=AssertionError("sent signal")):
            self.assertEqual(observation.observe_pid(42), {"pid": 42, "status": "present"})
        loader.assert_called_once_with("kernel32", use_last_error=True)
        kernel.OpenProcess.assert_called_once_with(0x00100000, False, 42)
        kernel.WaitForSingleObject.assert_called_once_with(123, 0)
        kernel.CloseHandle.assert_called_once_with(123)
        self.assertEqual(len(kernel.OpenProcess.argtypes), 3)

    def test_windows_signaled_process_is_absent_even_for_exit_code_259(self):
        kernel, _ = self.windows(waited=0)
        self.assertEqual(observation.observe_pid(42), {"pid": 42, "status": "absent"})
        kernel.GetExitCodeProcess.assert_not_called()
        kernel.CloseHandle.assert_called_once_with(123)

    def test_windows_access_denied_and_other_errors_are_unavailable(self):
        for error in (5, 8, 0):
            with self.subTest(error=error):
                kernel, _ = self.windows(handle=0, error=error)
                self.assertEqual(observation.observe_pid(42), {"pid": 42, "status": "unavailable"})
                kernel.WaitForSingleObject.assert_not_called()
                kernel.CloseHandle.assert_not_called()

    def test_windows_invalid_positive_numeric_pid_is_absent(self):
        kernel, _ = self.windows(handle=0, error=87)
        self.assertEqual(observation.observe_pid(42), {"pid": 42, "status": "absent"})
        kernel.CloseHandle.assert_not_called()

    def test_windows_unknown_or_failed_wait_always_closes_handle(self):
        for waited in (0xFFFFFFFF, 128, 17):
            with self.subTest(waited=waited):
                kernel, _ = self.windows(waited=waited)
                self.assertEqual(observation.observe_pid(42), {"pid": 42, "status": "unavailable"})
                kernel.CloseHandle.assert_called_once_with(123)

    def test_windows_wait_exception_always_closes_handle(self):
        kernel, _ = self.windows()
        kernel.WaitForSingleObject.side_effect = OSError("private OS error")
        self.assertEqual(observation.observe_pid(42), {"pid": 42, "status": "unavailable"})
        kernel.CloseHandle.assert_called_once_with(123)

    def test_windows_loader_or_close_failure_is_unavailable(self):
        kernel, loader = self.windows(closed=0)
        self.assertEqual(observation.observe_pid(42), {"pid": 42, "status": "unavailable"})
        kernel.CloseHandle.assert_called_once_with(123)
        loader.side_effect = OSError("private loader error")
        self.assertEqual(observation.observe_pid(42), {"pid": 42, "status": "unavailable"})

    @unittest.skipUnless(sys.platform in {"win32", "linux"}, "supported operating system")
    def test_actual_current_pid_is_present_and_unknown_writer_identity_is_not_invented(self):
        with warnings.catch_warnings():
            warnings.simplefilter("error", ResourceWarning)
            for _ in range(20):
                result = observation.observe_pid(os.getpid())
                self.assertEqual(result, {"pid": os.getpid(), "status": "present"})
                self.assertEqual(json.loads(json.dumps(result)), result)
            gc.collect()

    @unittest.skipUnless(sys.platform in {"win32", "linux"}, "supported operating system")
    def test_actual_clearly_absent_bounded_pid(self):
        self.assertEqual(observation.observe_pid(2**31 - 1), {"pid": 2**31 - 1, "status": "absent"})


if __name__ == "__main__":
    unittest.main()
