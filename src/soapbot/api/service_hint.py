"""The command that actually restarts this deployment.

Hard-coded in the panel before, and wrong: the Windows installer registers a task
named ``SoapbotBot`` while the save message told the operator to run
``schtasks ... /TN SoapbotPanel``. Following the instructions did nothing, which
reads as "the panel did not save".

The name is taken from ``SOAPBOT_SERVICE_NAME`` when set, so a renamed unit or task
does not require a code change.
"""

from __future__ import annotations

import os
from pathlib import Path


def in_container() -> bool:
    try:
        return Path("/.dockerenv").exists()
    except OSError:  # pragma: no cover - unusual filesystems
        return False


def service_name() -> str:
    """The task or unit name this deployment actually registered.

    Shared by the hint and the restart endpoint: two places deriving the name
    separately is how the panel ended up telling operators to restart a task that
    does not exist.
    """
    name = os.environ.get("SOAPBOT_SERVICE_NAME", "").strip()
    if name:
        return name
    return "SoapbotBot" if os.name == "nt" else "soapbot"


def restart_hint() -> str:
    if in_container():
        return "docker compose restart soapbot"
    name = service_name()
    if os.name == "nt":
        return f"schtasks /End /TN {name} && schtasks /Run /TN {name}"
    return f"systemctl restart {name}"
