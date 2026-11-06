"""Kill plugin workers when the host dies, on Windows.

``start_new_session`` plus ``killpg`` covers Linux: the group dies with the parent.
Windows has no equivalent process group that survives a hard kill, so a crashed host
leaves plugin children running and holding their pipes. A Job Object with
``JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE`` is the OS-level answer: when the last handle
to the job closes (including on abnormal process exit) every assigned process dies.

The handle is created once and deliberately never closed: closing it is the kill
switch, so it has to outlive every worker.
"""

from __future__ import annotations

import ctypes
import logging
import os
from ctypes import wintypes
from typing import Any, ClassVar

logger = logging.getLogger(__name__)

_JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE = 0x00002000
_JOB_OBJECT_EXTENDED_LIMIT_INFORMATION = 9
_PROCESS_SET_QUOTA = 0x0100
_PROCESS_QUERY_LIMITED_INFORMATION = 0x1000

_job_handle: int | None = None


class _IoCounters(ctypes.Structure):
    _fields_: ClassVar[list[tuple[str, Any]]] = [
        ("ReadOperationCount", ctypes.c_ulonglong),
        ("WriteOperationCount", ctypes.c_ulonglong),
        ("OtherOperationCount", ctypes.c_ulonglong),
        ("ReadTransferCount", ctypes.c_ulonglong),
        ("WriteTransferCount", ctypes.c_ulonglong),
        ("OtherTransferCount", ctypes.c_ulonglong),
    ]


class _BasicLimit(ctypes.Structure):
    _fields_: ClassVar[list[tuple[str, Any]]] = [
        ("PerProcessUserTimeLimit", ctypes.c_longlong),
        ("PerJobUserTimeLimit", ctypes.c_longlong),
        ("LimitFlags", wintypes.DWORD),
        ("MinimumWorkingSetSize", ctypes.c_size_t),
        ("MaximumWorkingSetSize", ctypes.c_size_t),
        ("ActiveProcessLimit", wintypes.DWORD),
        ("Affinity", ctypes.c_size_t),
        ("PriorityClass", wintypes.DWORD),
        ("SchedulingClass", wintypes.DWORD),
    ]


class _ExtendedLimit(ctypes.Structure):
    _fields_: ClassVar[list[tuple[str, Any]]] = [
        ("BasicLimitInformation", _BasicLimit),
        ("IoInfo", _IoCounters),
        ("ProcessMemoryLimit", ctypes.c_size_t),
        ("JobMemoryLimit", ctypes.c_size_t),
        ("PeakProcessMemoryUsed", ctypes.c_size_t),
        ("PeakJobMemoryUsed", ctypes.c_size_t),
    ]


def assign(pid: int) -> bool:
    """Put ``pid`` in the kill-on-close job. Returns ``False`` when unsupported.

    Failure is not fatal: the worker still runs, it just lacks this last line of
    defence. Returning a bool instead of raising keeps the caller free of platform
    checks, and lets a test assert the non-Windows behaviour without a VM.
    """
    global _job_handle
    if os.name != "nt":
        return False
    try:
        kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
        kernel32.CreateJobObjectW.restype = wintypes.HANDLE
        kernel32.CreateJobObjectW.argtypes = [wintypes.LPVOID, wintypes.LPCWSTR]
        kernel32.SetInformationJobObject.restype = wintypes.BOOL
        kernel32.SetInformationJobObject.argtypes = [
            wintypes.HANDLE,
            ctypes.c_int,
            wintypes.LPVOID,
            wintypes.DWORD,
        ]
        kernel32.AssignProcessToJobObject.restype = wintypes.BOOL
        kernel32.AssignProcessToJobObject.argtypes = [wintypes.HANDLE, wintypes.HANDLE]
        kernel32.OpenProcess.restype = wintypes.HANDLE
        kernel32.OpenProcess.argtypes = [wintypes.DWORD, wintypes.BOOL, wintypes.DWORD]
        kernel32.CloseHandle.argtypes = [wintypes.HANDLE]

        if _job_handle is None:
            handle = kernel32.CreateJobObjectW(None, None)
            if not handle:
                logger.warning("job object creation failed")
                return False
            info = _ExtendedLimit()
            info.BasicLimitInformation.LimitFlags = _JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE
            if not kernel32.SetInformationJobObject(
                handle,
                _JOB_OBJECT_EXTENDED_LIMIT_INFORMATION,
                ctypes.byref(info),
                ctypes.sizeof(info),
            ):
                kernel32.CloseHandle(handle)
                logger.warning("job object limits rejected")
                return False
            _job_handle = handle

        process = kernel32.OpenProcess(
            _PROCESS_SET_QUOTA | _PROCESS_QUERY_LIMITED_INFORMATION, False, int(pid)
        )
        if not process:
            logger.warning("cannot open plugin process %s for job assignment", pid)
            return False
        try:
            if not kernel32.AssignProcessToJobObject(_job_handle, process):
                logger.warning("job assignment failed for plugin process %s", pid)
                return False
        finally:
            kernel32.CloseHandle(process)
        return True
    except Exception as exc:  # pragma: no cover - platform dependent
        logger.warning("job object unavailable: %s", type(exc).__name__)
        return False
