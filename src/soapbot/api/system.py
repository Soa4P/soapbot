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
    """Hand the restart to a process that survives this one."""
    task = service_name()
    command = (
        f'timeout /t 1 /nobreak >nul & schtasks /End /TN "{task}" & '
        f'timeout /t 2 /nobreak >nul & schtasks /Run /TN "{task}"'
    )
    flags = 0
    if sys.platform == "win32":
        flags = getattr(subprocess, "CREATE_NO_WINDOW", 0) | getattr(
            subprocess, "DETACHED_PROCESS", 0
        )
    # Fixed argv; the task name comes from configuration, not from a request.
    subprocess.Popen(["cmd.exe", "/c", command], creationflags=flags, close_fds=True)


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
