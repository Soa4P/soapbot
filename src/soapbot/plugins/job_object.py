"""Kill a plugin worker's whole tree on Windows — at host death *and* at unload.

``start_new_session`` plus ``killpg`` covers Linux: the worker leads its own process
group, so one signal reaches every helper it forked. Windows has no such group, and
``taskkill /T`` only walks a tree whose root is still alive — after a graceful shutdown
the root is gone and its helpers survive (audit S-PLUG-02).

A Job Object with ``JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE`` is the OS-level answer: when
the last handle to the job closes, every assigned process dies. Children inherit job
membership, so a helper the plugin forks is covered without enumerating anything.

One job **per worker**, not one job for the process:

* host death closes every handle at once → every job empties, which is the original
  guarantee;
* unloading one plugin closes only that job → its helpers die and the other plugins
  keep running. A single shared job could not do this: terminating it would take down
  every plugin at once.

``attach`` returns ``None`` off Windows, so callers need no platform check and a test
can assert the non-Windows behaviour without a VM.
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


def attach(pid: int) -> int | None:
    """Create a job, put ``pid`` in it, and return the handle.

    ``None`` means the job is unavailable: not Windows, creation refused, or the process
    could not be assigned (nested jobs are fine on Windows 8+, but group policy can still
    block it). The worker runs either way — it just lacks this last line of defence — so
    failure is logged at warning level and never raised. The caller owns the handle and
    must :func:`detach` it.
    """
    if os.name != "nt":
        return None
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

        handle = kernel32.CreateJobObjectW(None, None)
        if not handle:
            logger.warning("job object creation failed")
            return None
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
            return None

        process = kernel32.OpenProcess(
            _PROCESS_SET_QUOTA | _PROCESS_QUERY_LIMITED_INFORMATION, False, int(pid)
        )
        if not process:
            kernel32.CloseHandle(handle)
            logger.warning("cannot open plugin process %s for job assignment", pid)
            return None
        try:
            if not kernel32.AssignProcessToJobObject(handle, process):
                logger.warning("job assignment failed for plugin process %s", pid)
                kernel32.CloseHandle(handle)
                return None
        finally:
            kernel32.CloseHandle(process)
        return int(handle)
    except Exception as exc:  # pragma: no cover - platform dependent
        logger.warning("job object unavailable: %s", type(exc).__name__)
        return None


def detach(handle: int | None) -> None:
    """Close the job's last handle, which kills every process still in it.

    Called on every worker exit path — graceful shutdown, crash and abandon — because
    closing late is the difference between "the plugin was unloaded" and "the plugin's
    helper is still burning CPU".

    Nothing here kills anything while the worker is meant to be running: the job only
    empties when its handle goes away, which happens on unload or when the host dies
    with the handle still open.
    """
    if handle is None or os.name != "nt":
        return
    try:
        kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
        kernel32.CloseHandle.argtypes = [wintypes.HANDLE]
        kernel32.CloseHandle(wintypes.HANDLE(handle))
    except Exception as exc:  # pragma: no cover - platform dependent
        logger.warning("closing plugin job failed: %s", type(exc).__name__)


def assign(pid: int) -> bool:
    """Boolean form of :func:`attach` for callers that only ask whether it worked.

    It creates a job and drops the handle immediately, so it cannot clean up later —
    callers that want kill-on-unload must hold the handle from :func:`attach`.
    """
    handle = attach(pid)
    if handle is None:
        return False
    detach(handle)
    return True
