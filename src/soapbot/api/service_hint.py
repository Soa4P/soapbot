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
import re
import shlex
from pathlib import Path

#: A plain task/unit name needs no quoting; anything else is quoted, and anything
#: containing a cmd.exe metacharacter is refused outright (see ``restart_hint``).
_SIMPLE_NAME = re.compile(r"[A-Za-z0-9._-]+\Z")
_CMD_META = re.compile(r'[&|<>^"%!`]')


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
    """A command an operator can copy, or an explanation of why there isn't one.

    The name comes from ``SOAPBOT_SERVICE_NAME`` in ``.env``. The automatic restart
    passes it to ``schtasks`` as argv, where it can only be a task name; a hint, however,
    is pasted into a shell by a human. Interpolating an unvalidated name there would
    hand ``SOAPBOT_SERVICE_NAME="Soapbot & calc"`` a second command to run with the
    operator's rights — the exact hole the argv version was written to close.
    """
    if in_container():
        return "docker compose restart soapbot"
    name = service_name()
    if os.name == "nt":
        if _CMD_META.search(name) or any(ord(ch) < 32 for ch in name):
            # No safe spelling exists for cmd.exe. The panel's automatic restart still
            # works because it never goes through a shell.
            return (
                "此任务名包含命令行特殊字符，无法安全地写成手动命令；"
                "请使用面板的自动重启，或在「任务计划程序」中重启该任务"
            )
        quoted = name if _SIMPLE_NAME.fullmatch(name) else f'"{name}"'
        return f"schtasks /End /TN {quoted} && schtasks /Run /TN {quoted}"
    return f"systemctl restart {shlex.quote(name)}"
