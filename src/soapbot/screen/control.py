"""Control plane phase 2: keyboard/mouse injection on the dedicated machine.

The three preconditions from ``docs/autonomous-capabilities-design.md`` §1.1, checked
at gate time in this order (fail closed, short tokens):

1. **专用机器**：same hostname gate as capture — ``CONTROL_ENABLED`` flag AND the
   declared hostname must match this host; an empty declaration refuses everything.
2. **急停优先于一切**：the ``control_kill.switch`` file is read fresh per call, and
   ``/panic`` (or the panel) engaging it cuts injection instantly. Engage/revive
   asymmetry is unchanged: nothing chat- or plugin-reachable can remove the file.
3. **授权持有**：injection only runs inside a time-boxed hold the operator explicitly
   started (default 15 min, cap 60) — a hold the process can never extend itself, and
   a restart drops it (fail closed). Coopanion's tier table collapses into this single
   hold because the operator's other tiers (per-action confirm) are covered by the
   /act command's own confirmation flow.

What this module does NOT do (registered as future increments): UIA control-tree
queries, window enumeration/binding, browser channels. Actions are coordinate /
text / named-key / scroll only, on the primary display.

Audit discipline: every action lands in ``SCREEN_OPS`` with the action type, target
coordinates and the *length* of typed text — never the text itself.
"""

from __future__ import annotations

import ctypes
import logging
import sys
import time
from ctypes import wintypes
from dataclasses import dataclass
from typing import Any

from soapbot.screen.opslog import SCREEN_OPS

logger = logging.getLogger(__name__)

HOLD_DEFAULT_MINUTES = 15
HOLD_MAX_MINUTES = 60

#: 名字 → 虚拟键码子集。够驱动常见 UI（enter/esc/tab/方向键）；完整键表是
#: SendInput 文档的事，这里只收编确定性可测的那部分。
KEY_CODES: dict[str, int] = {
    "enter": 0x0D,
    "esc": 0x1B,
    "tab": 0x09,
    "space": 0x20,
    "backspace": 0x08,
    "up": 0x26,
    "down": 0x28,
    "left": 0x25,
    "right": 0x27,
    "home": 0x24,
    "end": 0x23,
    "pageup": 0x21,
    "pagedown": 0x22,
}

#: SendInput 标志位与 INPUT.type（Windows SDK 值，写死以可测）。
_INPUT_MOUSE = 0
_INPUT_KEYBOARD = 1
_MOUSE_MOVE = 0x0001
_MOUSE_LEFT_DOWN = 0x0002
_MOUSE_LEFT_UP = 0x0004
_MOUSE_WHEEL = 0x0800
_KEY_DOWN = 0x0000
_KEY_UP = 0x0002
_KEY_UNICODE = 0x0004


class ControlRefusedError(RuntimeError):
    """A gate refused the action. ``reason`` is a short stable token."""

    def __init__(self, reason: str) -> None:
        super().__init__(reason)
        self.reason = reason


class ControlUnavailableError(RuntimeError):
    """Input injection is not available on this platform (non-Windows)."""


@dataclass(slots=True)
class ControlGate:
    """Same chain as capture, plus the time-boxed hold. Read fresh per call."""

    enabled: bool = False
    dedicated_machine: str = ""
    hold_minutes: int = 15
    hold_max_minutes: int = 60
    kill_file: Any = None

    @classmethod
    def from_settings(cls, settings: Any) -> ControlGate:
        from soapbot.screen.kill import kill_file

        return cls(
            enabled=bool(getattr(settings, "control_enabled", False)),
            dedicated_machine=str(getattr(settings, "screen_dedicated_machine", "") or "").strip(),
            hold_minutes=int(getattr(settings, "control_hold_minutes", 15) or 15),
            hold_max_minutes=int(getattr(settings, "control_hold_max_minutes", 60) or 60),
            kill_file=kill_file(settings),
        )

    def check(self, *, hostname: str | None = None, grant: dict[str, Any] | None) -> None:
        """Refuse unless everything holds, in this order (fail closed):

        1. 急停文件现读——操作者的闸高于一切（含 flag 与 hold）；
        2. flag + 专用机器主机名（与 capture 同一双门）；
        3. 授权持有且未过期——进程重启即失效（内存态，fail closed）。
        """
        if self.kill_file is not None and self.kill_file.exists():
            raise ControlRefusedError("control_killed")
        if not self.enabled:
            raise ControlRefusedError("control_disabled")
        declared = self.dedicated_machine.lower()
        if not declared:
            raise ControlRefusedError("control_machine_undeclared")
        current = (hostname if hostname is not None else _hostname()).lower()
        if current != declared:
            raise ControlRefusedError("control_machine_mismatch")
        if not grant or float(grant.get("until", 0)) <= time.time():
            raise ControlRefusedError("control_no_grant")


def _hostname() -> str:
    import socket

    return socket.gethostname()


@dataclass(slots=True)
class ControlHold:
    """The in-memory grant. Process restart drops it — fail closed."""

    until: float
    by: str
    minutes: int

    def expired(self, now: float) -> bool:
        return now >= self.until


class ControlHolder:
    """One process-wide hold, engaged by the operator, dropped on restart."""

    def __init__(self) -> None:
        self._hold: dict[str, Any] | None = None

    def engage(self, *, minutes: int, by: str, max_minutes: int) -> dict[str, Any]:
        minutes = max(1, min(int(minutes), max(1, int(max_minutes))))
        now = time.time()
        self._hold = {"until": now + minutes * 60, "by": by, "minutes": minutes}
        return dict(self._hold)

    def disengage(self) -> None:
        self._hold = None

    def active(self, now: float | None = None) -> dict[str, Any] | None:
        now = time.time() if now is None else now
        hold = self._hold
        if hold is None or hold["until"] <= now:
            return None
        return hold


_CONTROL_HOLDER = ControlHolder()


class _MOUSEINPUT(ctypes.Structure):
    _fields_ = [
        ("dx", wintypes.LONG),
        ("dy", wintypes.LONG),
        ("mouseData", wintypes.DWORD),
        ("dwFlags", wintypes.DWORD),
        ("time", wintypes.DWORD),
        ("dwExtraInfo", ctypes.POINTER(wintypes.ULONG)),
    ]


class _KEYBDINPUT(ctypes.Structure):
    _fields_ = [
        ("wVk", wintypes.WORD),
        ("wScan", wintypes.WORD),
        ("dwFlags", wintypes.DWORD),
        ("time", wintypes.DWORD),
        ("dwExtraInfo", ctypes.POINTER(wintypes.ULONG)),
    ]


class _INPUTUNION(ctypes.Union):
    _fields_ = [("mi", _MOUSEINPUT), ("ki", _KEYBDINPUT)]


class _SendInput(ctypes.Structure):
    """Minimal Windows INPUT structure for keyboard/mouse injection."""

    _anonymous_ = ("u",)
    _fields_ = [("type", wintypes.DWORD), ("u", _INPUTUNION)]


def act(
    gate: ControlGate,
    hold: ControlHolder,
    action: str,
    *,
    x: int = 0,
    y: int = 0,
    text: str = "",
    key: str = "",
    delta: int = 0,
    hostname: str | None = None,
    now: float | None = None,
) -> dict[str, Any]:
    """Run one input action under the full gate chain. Synchronous on purpose:
    SendInput is a per-call kernel request, not an async IO wait.

    The actual injection is behind ``_dispatch`` so tests can intercept without a
    real display — the same seam pattern as ``_download_release``."""
    gate.check(hostname=hostname, grant=hold.active(now))
    if action not in ("click", "double_click", "type_text", "key", "scroll"):
        raise ControlRefusedError("control_unknown_action")

    try:
        detail = _dispatch(action, x=x, y=y, text=text, key=key, delta=delta, hostname=hostname)
    except ControlRefusedError as exc:
        # The refusal lands with its short token — never any caller text.
        SCREEN_OPS.record(action=f"control.{action}", outcome="deny", reason=exc.reason)
        _audit(action, outcome="deny", note=exc.reason)
        raise
    # Metadata only: action type, target, text *length*. The typed text itself is
    # in ``detail`` only as a count, by construction (see _dispatch).
    SCREEN_OPS.record(action=f"control.{action}", outcome="allow", reason="")
    _audit(action, outcome="allow", note=str(detail))
    return {"action": action, **detail}


def _audit(action: str, *, outcome: str, note: str) -> None:
    from soapbot.security.audit import get_audit_log

    get_audit_log().record(kind="screen", action=f"control.{action}", outcome=outcome, detail=note)


def _dispatch(
    action: str,
    *,
    x: int,
    y: int,
    text: str,
    key: str,
    delta: int,
    hostname: str | None = None,
) -> dict[str, Any]:
    """Platform-specific injection. Isolated so tests can monkeypatch the whole thing."""
    if sys.platform != "win32":
        raise ControlUnavailableError("input injection needs Windows (SendInput)")

    user32 = ctypes.windll.user32

    if action in ("click", "double_click"):
        _move_and_click(user32, x=int(x), y=int(y), double=action == "double_click")
        return {"x": x, "y": y, "double": action == "double_click"}
    if action == "type_text":
        for ch in text:
            _send_char(user32, ch)
        return {"chars": len(text)}
    if action == "key":
        code = KEY_CODES.get(key.lower())
        if code is None:
            raise ControlRefusedError("control_unknown_key")
        _send_vk(user32, code)
        return {"key": key.lower()}
    if action == "scroll":
        _send_wheel(user32, delta)
        return {"delta": delta}
    raise ControlRefusedError("control_unknown_action")


def _click(user32: Any, *, double: bool) -> None:
    for _ in range(2 if double else 1):
        _send(user32, _INPUT_MOUSE, mi_flags=_MOUSE_LEFT_DOWN)
        _send(user32, _INPUT_MOUSE, mi_flags=_MOUSE_LEFT_UP)


def _move_and_click(user32: Any, *, x: int, y: int, double: bool) -> None:
    if not user32.SetCursorPos(x, y):
        raise ControlRefusedError("control_move_failed")
    _click(user32, double=double)


def _send_char(user32: Any, ch: str) -> None:
    _send(user32, _INPUT_KEYBOARD, ki_scan=ord(ch), ki_flags=_KEY_UNICODE)
    _send(user32, _INPUT_KEYBOARD, ki_scan=ord(ch), ki_flags=_KEY_UNICODE | _KEY_UP)


def _send_vk(user32: Any, code: int) -> None:
    _send(user32, _INPUT_KEYBOARD, ki_vk=code, ki_flags=_KEY_DOWN)
    _send(user32, _INPUT_KEYBOARD, ki_vk=code, ki_flags=_KEY_UP)


def _send_wheel(user32: Any, delta: int) -> None:
    _send(user32, _INPUT_MOUSE, mi_flags=_MOUSE_WHEEL, mi_mouse_data=delta)


def _send(
    user32: Any,
    input_type: int,
    *,
    mi_flags: int = 0,
    mi_mouse_data: int = 0,
    ki_vk: int = 0,
    ki_scan: int = 0,
    ki_flags: int = 0,
) -> None:
    inp = _SendInput()
    inp.type = input_type
    if input_type == _INPUT_MOUSE:
        inp.u.mi.dwFlags = mi_flags
        inp.u.mi.mouseData = mi_mouse_data
    else:
        inp.u.ki.dwFlags = ki_flags
        inp.u.ki.wVk = ki_vk
        inp.u.ki.wScan = ki_scan
    sent = user32.SendInput(1, ctypes.byref(inp), ctypes.sizeof(_SendInput))
    if sent != 1:
        raise ControlRefusedError("control_send_failed")
