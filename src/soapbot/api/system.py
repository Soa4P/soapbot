"""Restart this process the way this deployment is supervised.

The panel cannot reload its own code, and the authority lists are read into
``PrincipalResolver`` at startup, so a save needs a new process before it takes
effect. Three paths, all decided here rather than in the panel:

* Windows: the task registered by ``install.ps1`` uses ``-AtStartup`` with
  ``RestartCount``. A process that exits 0 counts as a successful run, so the task
  manager does not bring it back. A detached ``cmd.exe`` therefore runs
  ``schtasks /End`` and then ``/Run``; the child outlives the parent.
* Linux: send SIGTERM and let systemd's ``Restart=always`` do the work.
* Container: exit non-zero and let compose's ``restart: unless-stopped`` do it.

The delay before acting is not politeness: without it the browser sees a connection
reset instead of ``{ok: true}`` and the panel cannot tell "restarting" from "the save
failed".
"""

from __future__ import annotations

import asyncio
import logging
import os
import signal
import subprocess
import sys
import time

from fastapi import APIRouter, Depends

from soapbot.api.auth import require_role
from soapbot.api.service_hint import in_container, restart_hint, service_name
from soapbot.security.principal import Role

logger = logging.getLogger(__name__)

router = APIRouter(
    prefix="/api/system",
    tags=["system"],
    dependencies=[Depends(require_role(Role.ADMIN))],
)

RESTART_DELAY_SECONDS = 0.5

#: Keep a reference: a task nobody holds can be garbage-collected before it runs, and
#: the restart would silently never happen.
_pending_restarts: set[asyncio.Task] = set()


def _spawn_windows_restart() -> None:
    """Hand the restart to a process that survives this one.

    The task name is passed as ``argv`` to ``schtasks``, never interpolated into a
    command line. It comes from ``SOAPBOT_SERVICE_NAME``, which an operator sets in
    ``.env`` — and ``cmd.exe /c`` treats ``&``, ``|`` and ``>`` as operators even
    inside double quotes in some positions. A name like ``Soapbot & calc`` would have
    run ``calc`` as this process was exiting, with the service account's rights. Two
    separate ``Popen`` calls with a literal argv list remove the shell entirely, so
    the name can only ever be a task name.
    """
    task = service_name()
    flags = 0
    if sys.platform == "win32":
        flags = getattr(subprocess, "CREATE_NO_WINDOW", 0) | getattr(
            subprocess, "DETACHED_PROCESS", 0
        )

    def _detached(*args: str) -> None:
        subprocess.Popen(
            ["schtasks", *args],
            creationflags=flags,
            close_fds=True,
            stdin=subprocess.DEVNULL,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )

    # End, then Run, as two children rather than one shell pipeline. The task manager
    # needs the old process gone before /Run starts a new one; the small sleeps give
    # it that gap without a shell to sequence them.
    _detached("/End", "/TN", task)
    time.sleep(1.0)
    _detached("/Run", "/TN", task)


def _perform_now() -> None:
    if in_container():
        logger.warning("restart requested; exiting for the container runtime")
        os._exit(75)
    if os.name == "nt":
        _spawn_windows_restart()
        os._exit(75)
    logger.warning("restart requested; sending SIGTERM")
    os.kill(os.getpid(), signal.SIGTERM)


async def schedule_restart(*, delay: float = RESTART_DELAY_SECONDS) -> None:
    await asyncio.sleep(delay)
    _perform_now()


@router.post("/restart")
async def restart() -> dict:
    """Ask for a restart. Returns before the process actually goes away."""
    task = asyncio.create_task(schedule_restart())
    _pending_restarts.add(task)
    task.add_done_callback(_pending_restarts.discard)
    return {"ok": True, "scheduled": True, "hint": restart_hint()}
