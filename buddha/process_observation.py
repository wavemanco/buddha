"""Read-only sampled numeric PID presence; never writer identity or health.

Linux uses os.pidfd_open, avoiding /proc hidepid absence guesses:
https://docs.python.org/3/library/os.html#os.pidfd_open
Windows waits with zero timeout on a SYNCHRONIZE-only process handle:
https://learn.microsoft.com/en-us/windows/win32/api/processthreadsapi/nf-processthreadsapi-openprocess
https://learn.microsoft.com/en-us/windows/win32/api/synchapi/nf-synchapi-waitforsingleobject
"""

import ctypes
import os
import sys
from ctypes import wintypes

from buddha.common import ValidationError


def _linux(pid: int) -> str:
    open_pid = getattr(os, "pidfd_open", None)
    if open_pid is None:
        return "unavailable"
    try:
        descriptor = open_pid(pid, 0)
    except ProcessLookupError:
        return "absent"
    except OSError:
        return "unavailable"
    try:
        os.close(descriptor)
    except OSError:
        return "unavailable"
    return "present"


def _windows(pid: int) -> str:
    try:
        loader = getattr(ctypes, "WinDLL", None)
        if loader is None:
            return "unavailable"
        kernel = loader("kernel32", use_last_error=True)
        kernel.OpenProcess.argtypes = [wintypes.DWORD, wintypes.BOOL, wintypes.DWORD]
        kernel.OpenProcess.restype = wintypes.HANDLE
        kernel.WaitForSingleObject.argtypes = [wintypes.HANDLE, wintypes.DWORD]
        kernel.WaitForSingleObject.restype = wintypes.DWORD
        kernel.CloseHandle.argtypes = [wintypes.HANDLE]
        kernel.CloseHandle.restype = wintypes.BOOL
        handle = kernel.OpenProcess(0x00100000, False, pid)  # SYNCHRONIZE only; no signals.
        if not handle:
            last_error = getattr(ctypes, "get_last_error", None)
            return "absent" if last_error is not None and last_error() == 87 else "unavailable"
        try:
            waited = kernel.WaitForSingleObject(handle, 0)
        finally:
            closed = kernel.CloseHandle(handle)
        if not closed:
            return "unavailable"
        return {0: "absent", 258: "present"}.get(waited, "unavailable")
    except (AttributeError, OSError):
        return "unavailable"


def observe_pid(pid: int) -> dict[str, object]:
    """Sample the local numeric PID without signals, waiting, or ownership claims.

    Presence may include an exited but unreaped Linux process and can change
    immediately. Existing PID-only locks cannot identify a matching writer.
    """
    if type(pid) is not int or not 1 <= pid <= 2**31 - 1:
        raise ValidationError("PID must be an integer between 1 and 2147483647")
    if sys.platform == "linux":
        status = _linux(pid)
    elif sys.platform == "win32":
        status = _windows(pid)
    else:
        status = "unavailable"
    return {"pid": pid, "status": status}
