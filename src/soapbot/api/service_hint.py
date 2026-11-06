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


def restart_hint() -> str:
    name = os.environ.get("SOAPBOT_SERVICE_NAME", "").strip()
    if in_container():
        return "docker compose restart soapbot"
    if os.name == "nt":
        task = name or "SoapbotBot"
        return f"schtasks /End /TN {task} && schtasks /Run /TN {task}"
    return f"systemctl restart {name or 'soapbot'}"
