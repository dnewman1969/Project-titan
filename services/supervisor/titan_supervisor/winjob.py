"""Windows job object with KILL_ON_JOB_CLOSE, so every child dies with the supervisor (M1.T3).

The supervisor puts itself in the job at startup, so every process it starts afterwards (and
their children, such as the postmaster `pg_ctl` launches) is a member from creation, with no
assign-after-spawn race. The only handle belongs to the supervisor: when it exits for any reason,
including being killed, Windows closes the handle and terminates every process still in the job.
On other platforms `create_job()` returns None and `procutil` uses PR_SET_PDEATHSIG instead.
"""

from __future__ import annotations

import sys
from typing import Protocol


class Job(Protocol):
    def assign(self, pid: int) -> None: ...

    def assign_current_process(self) -> None: ...

    def close(self) -> None: ...


if sys.platform == "win32":
    import ctypes
    from ctypes import wintypes

    _JOB_OBJECT_EXTENDED_LIMIT_INFORMATION_CLASS = 9
    _JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE = 0x2000
    _PROCESS_SET_QUOTA = 0x0100
    _PROCESS_TERMINATE = 0x0001

    class _IoCounters(ctypes.Structure):
        _fields_ = [
            ("ReadOperationCount", ctypes.c_ulonglong),
            ("WriteOperationCount", ctypes.c_ulonglong),
            ("OtherOperationCount", ctypes.c_ulonglong),
            ("ReadTransferCount", ctypes.c_ulonglong),
            ("WriteTransferCount", ctypes.c_ulonglong),
            ("OtherTransferCount", ctypes.c_ulonglong),
        ]

    class _BasicLimits(ctypes.Structure):
        _fields_ = [
            ("PerProcessUserTimeLimit", ctypes.c_int64),
            ("PerJobUserTimeLimit", ctypes.c_int64),
            ("LimitFlags", wintypes.DWORD),
            ("MinimumWorkingSetSize", ctypes.c_size_t),
            ("MaximumWorkingSetSize", ctypes.c_size_t),
            ("ActiveProcessLimit", wintypes.DWORD),
            ("Affinity", ctypes.c_size_t),
            ("PriorityClass", wintypes.DWORD),
            ("SchedulingClass", wintypes.DWORD),
        ]

    class _ExtendedLimits(ctypes.Structure):
        _fields_ = [
            ("BasicLimitInformation", _BasicLimits),
            ("IoInfo", _IoCounters),
            ("ProcessMemoryLimit", ctypes.c_size_t),
            ("JobMemoryLimit", ctypes.c_size_t),
            ("PeakProcessMemoryUsed", ctypes.c_size_t),
            ("PeakJobMemoryUsed", ctypes.c_size_t),
        ]

    _kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
    _kernel32.CreateJobObjectW.argtypes = [ctypes.c_void_p, wintypes.LPCWSTR]
    _kernel32.CreateJobObjectW.restype = wintypes.HANDLE
    _kernel32.SetInformationJobObject.argtypes = [
        wintypes.HANDLE,
        ctypes.c_int,
        ctypes.c_void_p,
        wintypes.DWORD,
    ]
    _kernel32.SetInformationJobObject.restype = wintypes.BOOL
    _kernel32.OpenProcess.argtypes = [wintypes.DWORD, wintypes.BOOL, wintypes.DWORD]
    _kernel32.OpenProcess.restype = wintypes.HANDLE
    _kernel32.AssignProcessToJobObject.argtypes = [wintypes.HANDLE, wintypes.HANDLE]
    _kernel32.AssignProcessToJobObject.restype = wintypes.BOOL
    _kernel32.GetCurrentProcess.argtypes = []
    _kernel32.GetCurrentProcess.restype = wintypes.HANDLE
    _kernel32.CloseHandle.argtypes = [wintypes.HANDLE]
    _kernel32.CloseHandle.restype = wintypes.BOOL

    def _check(ok: object, what: str) -> None:
        if not ok:
            raise ctypes.WinError(ctypes.get_last_error(), what)

    class WindowsJob:
        def __init__(self) -> None:
            handle = _kernel32.CreateJobObjectW(None, None)
            _check(handle, "CreateJobObjectW")
            self._handle: int | None = handle
            info = _ExtendedLimits()
            info.BasicLimitInformation.LimitFlags = _JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE
            _check(
                _kernel32.SetInformationJobObject(
                    handle,
                    _JOB_OBJECT_EXTENDED_LIMIT_INFORMATION_CLASS,
                    ctypes.byref(info),
                    ctypes.sizeof(info),
                ),
                "SetInformationJobObject",
            )

        def assign(self, pid: int) -> None:
            if self._handle is None:
                raise RuntimeError("job is closed")
            process = _kernel32.OpenProcess(_PROCESS_SET_QUOTA | _PROCESS_TERMINATE, False, pid)
            _check(process, "OpenProcess")
            try:
                _check(_kernel32.AssignProcessToJobObject(self._handle, process), "AssignProcessToJobObject")
            finally:
                _kernel32.CloseHandle(process)

        def assign_current_process(self) -> None:
            if self._handle is None:
                raise RuntimeError("job is closed")
            _check(
                _kernel32.AssignProcessToJobObject(self._handle, _kernel32.GetCurrentProcess()),
                "AssignProcessToJobObject(self)",
            )

        def close(self) -> None:
            """Terminates every process still in the job."""
            if self._handle is not None:
                _kernel32.CloseHandle(self._handle)
                self._handle = None


def create_job() -> Job | None:
    if sys.platform == "win32":
        return WindowsJob()
    return None
