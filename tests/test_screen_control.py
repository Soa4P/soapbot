"""Control plane phase 2: keyboard/mouse injection under the full gate chain.

The trust chain, tested link by link: 急停文件现读 > flag + 专用机器双门 > 授权持有
（内存态、重启即失效、时长钳制）。Actions land in SCREEN_OPS with metadata only —
typed text never reaches any log, audit or exception message.

Two seams, both cross-platform:

* ``_dispatch`` — the act()-level seam. Patched in gate/logging tests so the
  real platform check inside it never runs (CI's Linux backend has no SendInput).
* ``_send`` / ``_move_and_click`` with a fake ``user32`` — the ctypes-level
  helpers take the target as a parameter, so ordering/flag tests call them with
  a recorder object; nothing touches ``ctypes.windll`` (which does not even
  exist off-Windows, and hands out a fresh instance per access on Windows).
"""

from __future__ import annotations

import time
from types import SimpleNamespace

import pytest

import soapbot.screen.control as control
from soapbot.screen.control import (
    _CONTROL_HOLDER,
    KEY_CODES,
    ControlGate,
    ControlHolder,
    ControlRefusedError,
    act,
)
from soapbot.screen.opslog import SCREEN_OPS
from soapbot.security.audit import get_audit_log


@pytest.fixture(autouse=True)
def _clean_state():
    holder = _CONTROL_HOLDER
    holder.disengage()
    SCREEN_OPS.clear()
    yield
    holder.disengage()
    SCREEN_OPS.clear()


def _gate(*, enabled: bool = True, machine: str = "BOT-WORKER") -> ControlGate:
    return ControlGate(
        enabled=enabled,
        dedicated_machine=machine,
        kill_file=None,
        hold_minutes=15,
        hold_max_minutes=60,
    )


def _holder(minutes: int = 15) -> ControlHolder:
    h = ControlHolder()
    h.engage(minutes=minutes, by="owner", max_minutes=60)
    return h


def _patch_dispatch(monkeypatch) -> list[tuple[str, int]]:
    """Replace the whole platform-specific dispatch with a recorder."""
    calls: list[tuple[str, int]] = []

    def fake_dispatch(action, *, x, y, text, key, delta, hostname=None):
        if action in ("click", "double_click"):
            calls.append(("click", x))
            return {"x": x, "y": y, "double": action == "double_click"}
        if action == "type_text":
            calls.append(("type", len(text)))
            return {"chars": len(text)}
        if action == "key":
            code = KEY_CODES.get(key.lower())
            if code is None:
                raise ControlRefusedError("control_unknown_key")
            calls.append(("key", code))
            return {"key": key.lower()}
        if action == "scroll":
            calls.append(("scroll", delta))
            return {"delta": delta}
        raise ControlRefusedError("control_unknown_action")

    monkeypatch.setattr(control, "_dispatch", fake_dispatch)
    return calls


def _fake_user32() -> tuple[SimpleNamespace, list[tuple[str, int]]]:
    """A user32 double: SendInput records (kind, code_or_flags); move succeeds."""
    calls: list[tuple[str, int]] = []
    moves: list[tuple[int, int]] = []

    def fake_send_input(n, arr, size):
        # ``_send`` passes ``ctypes.byref(inp)``; cast it back to read the record.
        import ctypes as _ct

        inp = _ct.cast(arr, _ct.POINTER(control._SendInput))[0]
        if inp.type == control._INPUT_MOUSE:
            calls.append(("mouse", inp.mi.dwFlags))
        else:
            calls.append(("key", inp.ki.wVk or inp.ki.wScan))
        return 1

    user32 = SimpleNamespace(
        SendInput=fake_send_input,
        SetCursorPos=lambda x, y: moves.append((x, y)) or 1,
        SetCursorPos_calls=moves,
    )
    return user32, calls


# ------------------------------------------------------------------ gate chain
def test_gate_refuses_when_disabled() -> None:
    gate = _gate(enabled=False)
    with pytest.raises(ControlRefusedError, match="control_disabled"):
        gate.check(hostname="BOT-WORKER", grant={"until": time.time() + 600, "by": "owner"})


def test_gate_refuses_an_empty_declaration() -> None:
    gate = _gate(machine="")
    with pytest.raises(ControlRefusedError, match="control_machine_undeclared"):
        gate.check(hostname="anywhere", grant={"until": time.time() + 600, "by": "owner"})


def test_gate_refuses_a_mismatched_machine() -> None:
    gate = _gate(machine="BOT-WORKER")
    with pytest.raises(ControlRefusedError, match="control_machine_mismatch"):
        gate.check(hostname="OTHER", grant={"until": time.time() + 600, "by": "owner"})


def test_gate_passes_when_everything_holds() -> None:
    gate = _gate()
    grant = {"until": time.time() + 600, "by": "owner"}
    gate.check(hostname="BOT-WORKER", grant=grant)  # no raise


def test_the_kill_switch_outranks_the_flag_and_the_grant(tmp_path) -> None:
    from soapbot.screen.kill import kill_file

    path = kill_file(SimpleNamespace(data_dir=tmp_path))
    path.write_text("{}")
    gate = ControlGate(
        enabled=True,
        dedicated_machine="BOT-WORKER",
        kill_file=path,
        hold_minutes=15,
        hold_max_minutes=60,
    )
    grant = {"until": time.time() + 600, "by": "owner"}
    with pytest.raises(ControlRefusedError, match="control_killed"):
        gate.check(hostname="BOT-WORKER", grant=grant)


def test_missing_or_expired_grant_is_refused() -> None:
    gate = _gate()
    with pytest.raises(ControlRefusedError, match="control_no_grant"):
        gate.check(hostname="BOT-WORKER", grant=None)
    with pytest.raises(ControlRefusedError, match="control_no_grant"):
        gate.check(hostname="BOT-WORKER", grant={"until": time.time() - 1, "by": "owner"})


def test_the_hold_is_dropped_by_a_restart() -> None:
    """内存态 fail closed：新 ControlHolder 实例 = 重启 = 无授权。"""
    h1 = ControlHolder()
    h1.engage(minutes=30, by="owner", max_minutes=60)
    assert ControlHolder().active() is None  # 新实例（=重启后）没有持有


def test_hold_minutes_are_clamped_to_the_cap() -> None:
    h = ControlHolder()
    hold = h.engage(minutes=999, by="owner", max_minutes=60)
    assert hold["minutes"] == 60


def test_hold_floor_is_one_minute() -> None:
    h = ControlHolder()
    hold = h.engage(minutes=0, by="owner", max_minutes=60)
    assert hold["minutes"] == 1


def test_the_hold_expires_and_the_gate_refuses_afterwards() -> None:
    hold = _holder(minutes=10)
    assert hold.active(now=time.time()) is not None
    assert hold.active(now=time.time() + 11 * 60) is None


# ------------------------------------------------------------------ act() + logging
def test_act_click_dispatches_and_records_metadata(monkeypatch) -> None:
    calls = _patch_dispatch(monkeypatch)
    result = act(_gate(), _holder(), "click", x=120, y=300, hostname="BOT-WORKER")
    assert result["action"] == "click" and result["x"] == 120
    assert calls == [("click", 120)]
    ops = SCREEN_OPS.recent()
    assert ops and ops[-1]["action"] == "control.click"
    assert ops[-1]["outcome"] == "allow"


def test_act_double_click_flagged(monkeypatch) -> None:
    _patch_dispatch(monkeypatch)
    result = act(_gate(), _holder(), "double_click", x=5, y=6, hostname="BOT-WORKER")
    assert result["double"] is True


def test_act_type_text_records_length_never_content(monkeypatch) -> None:
    _patch_dispatch(monkeypatch)
    secret = "机密文本 password=abc123"
    result = act(_gate(), _holder(), "type_text", text=secret, hostname="BOT-WORKER")
    assert result["chars"] == len(secret)
    audit = get_audit_log().recent(kind="screen")
    assert audit and all(secret not in str(e) for e in audit)  # 零泄漏：键入文本不进任何记录


def test_act_key_uppercase_is_normalized(monkeypatch) -> None:
    _patch_dispatch(monkeypatch)
    result = act(_gate(), _holder(), "key", key="ESC", hostname="BOT-WORKER")
    assert result["key"] == "esc"


def test_act_unknown_key_is_refused(monkeypatch) -> None:
    _patch_dispatch(monkeypatch)
    with pytest.raises(ControlRefusedError, match="control_unknown_key"):
        act(_gate(), _holder(), "key", key="f13", hostname="BOT-WORKER")
    # The refusal is visible to the operator, with the token only.
    ops = SCREEN_OPS.recent()
    assert ops and ops[-1]["action"] == "control.key" and ops[-1]["outcome"] == "deny"


def test_act_unknown_action_is_refused(monkeypatch) -> None:
    _patch_dispatch(monkeypatch)
    with pytest.raises(ControlRefusedError, match="control_unknown_action"):
        act(_gate(), _holder(), "format_disk", hostname="BOT-WORKER")


def test_act_scroll_dispatches(monkeypatch) -> None:
    calls = _patch_dispatch(monkeypatch)
    result = act(_gate(), _holder(), "scroll", delta=-120, hostname="BOT-WORKER")
    assert result["delta"] == -120
    assert calls == [("scroll", -120)]


def test_act_without_a_hold_is_refused(monkeypatch) -> None:
    _patch_dispatch(monkeypatch)
    with pytest.raises(ControlRefusedError, match="control_no_grant"):
        act(_gate(), ControlHolder(), "click", x=1, y=1, hostname="BOT-WORKER")


def test_act_refused_when_the_switch_flips_mid_hold(tmp_path, monkeypatch) -> None:
    """授权窗内按下急停：下一个动作立即被拒（现读闸，无缓存窗口）。"""
    _patch_dispatch(monkeypatch)
    from soapbot.screen.kill import kill_file

    path = kill_file(SimpleNamespace(data_dir=tmp_path))
    path.write_text("{}")
    gate = ControlGate(
        enabled=True,
        dedicated_machine="BOT-WORKER",
        kill_file=path,
        hold_minutes=15,
        hold_max_minutes=60,
    )
    hold = _holder()
    with pytest.raises(ControlRefusedError, match="control_killed"):
        act(gate, hold, "click", x=1, y=1, hostname="BOT-WORKER")


def test_screen_ops_records_are_metadata_only(monkeypatch) -> None:
    _patch_dispatch(monkeypatch)
    act(_gate(), _holder(), "type_text", text="机密内容 secret=abc", hostname="BOT-WORKER")
    ops = SCREEN_OPS.recent()
    assert all("机密内容" not in str(o) and "secret=abc" not in str(o) for o in ops)


def test_audit_for_control_actions_never_carries_text(monkeypatch) -> None:
    _patch_dispatch(monkeypatch)
    act(_gate(), _holder(), "type_text", text="top-secret-token-xyz", hostname="BOT-WORKER")
    audit = get_audit_log().recent(kind="screen")
    assert audit and all("top-secret-token-xyz" not in str(e) for e in audit)


# ------------------------------------------------------------------ ctypes helpers
def test_click_helper_presses_and_releases_once() -> None:
    user32, calls = _fake_user32()
    control._click(user32, double=False)
    assert calls == [("mouse", control._MOUSE_LEFT_DOWN), ("mouse", control._MOUSE_LEFT_UP)]


def test_double_click_helper_presses_and_releases_twice() -> None:
    user32, calls = _fake_user32()
    control._click(user32, double=True)
    assert calls == [
        ("mouse", control._MOUSE_LEFT_DOWN),
        ("mouse", control._MOUSE_LEFT_UP),
        ("mouse", control._MOUSE_LEFT_DOWN),
        ("mouse", control._MOUSE_LEFT_UP),
    ]


def test_move_and_click_positions_the_cursor_first() -> None:
    user32, calls = _fake_user32()
    control._move_and_click(user32, x=44, y=55, double=False)
    assert calls[0] == ("mouse", control._MOUSE_LEFT_DOWN)  # move is SetCursorPos, not SendInput
    assert user32.SetCursorPos_calls == [(44, 55)]


def test_key_vk_send_is_down_then_up_with_the_same_code() -> None:
    user32, calls = _fake_user32()
    control._send_vk(user32, 0x0D)
    assert calls == [("key", 0x0D), ("key", 0x0D)]


def test_char_send_uses_scan_codes_with_unicode_flag() -> None:
    user32, calls = _fake_user32()
    control._send_char(user32, "A")
    assert calls == [("key", ord("A")), ("key", ord("A"))]


def test_wheel_send_uses_the_wheel_flag() -> None:
    user32, calls = _fake_user32()
    control._send_wheel(user32, -120)
    assert calls == [("mouse", control._MOUSE_WHEEL)]


def test_send_failure_raises_the_refusal_token() -> None:
    user32 = SimpleNamespace(SendInput=lambda n, arr, size: 0, SetCursorPos=lambda x, y: 1)
    with pytest.raises(ControlRefusedError, match="control_send_failed"):
        control._send_vk(user32, 0x0D)


def test_dispatch_refuses_off_windows(monkeypatch) -> None:
    """非 Windows：注入本身不可用（mss 同款措辞），与门禁拒绝是两类错误。"""
    monkeypatch.setattr(control.sys, "platform", "linux")
    with pytest.raises(control.ControlUnavailableError):
        control._dispatch("click", x=1, y=1, text="", key="", delta=0)


def test_key_codes_cover_the_common_ui_set() -> None:
    for name in ("enter", "esc", "tab", "up", "down", "left", "right"):
        assert name in KEY_CODES


# ------------------------------------------------------------------ capability + surface
def _pcaller(session_key: str = "onebot11:group:1"):
    from soapbot.plugins.context import CallerContext

    return CallerContext(
        user_id="20001",
        display_name="tester",
        role="member",
        session_key=session_key,
        scene="group",
        group_id="1",
    )


def _pguard(*caps):
    from soapbot.plugins.sandbox import CapabilityGrant, CapabilityGuard

    entries: list[dict] = []

    class _Audit:
        def record(self, **kwargs):
            entries.append(kwargs)

    grant = CapabilityGrant(plugin="p", declared=frozenset(caps), approved=frozenset(caps))
    return CapabilityGuard(grant, audit=_Audit()), entries


def _audit_sink():
    entries: list[dict] = []

    class _Audit:
        def record(self, **kwargs):
            entries.append(kwargs)

    return _Audit(), entries


def control_capability():
    from soapbot.plugins.manifest import Capability

    return Capability.CONTROL


def test_control_is_a_sensitive_capability() -> None:
    from soapbot.plugins.manifest import SENSITIVE_CAPABILITIES, Capability

    assert Capability.CONTROL in SENSITIVE_CAPABILITIES


def test_control_surface_is_on_the_wire_allowlist() -> None:
    from soapbot.plugins.supervisor import ALLOWED_SURFACES
    from soapbot.plugins.surfaces import _SURFACE_TABLE

    assert "control.act" in ALLOWED_SURFACES
    assert "control.act" in _SURFACE_TABLE


async def test_control_surface_refuses_without_the_capability() -> None:
    from soapbot.plugins.sandbox import CapabilityDeniedError
    from soapbot.plugins.surfaces import SurfaceRouter

    guard, entries = _pguard()  # no CONTROL approved
    router = SurfaceRouter(guard=guard, plugin="p")
    with pytest.raises(CapabilityDeniedError):
        await router.dispatch("control.act", {"action": "click"}, _pcaller())
    assert any(e.get("outcome") == "deny" for e in entries)


async def test_control_surface_refuses_without_a_hold_and_audits_the_token(
    monkeypatch, tmp_path
) -> None:
    from soapbot.plugins.surfaces import SurfaceRouter

    guard, _entries = _pguard(control_capability())
    audit, audit_entries = _audit_sink()
    router = SurfaceRouter(guard=guard, plugin="p", audit=audit)
    monkeypatch.setattr(
        "soapbot.config.settings",
        SimpleNamespace(
            data_dir=tmp_path,
            control_enabled=True,
            screen_dedicated_machine="BOT-WORKER",
            control_hold_minutes=15,
            control_hold_max_minutes=60,
        ),
    )
    monkeypatch.setattr(control, "_hostname", lambda: "BOT-WORKER")
    with pytest.raises(PermissionError, match="control_no_grant"):
        await router.dispatch("control.act", {"action": "click", "x": 1, "y": 1}, _pcaller())
    assert any(
        e.get("action") == "surface:control.act"
        and e.get("outcome") == "deny"
        and "control_no_grant" in str(e.get("detail"))
        for e in audit_entries
    )
    ops = SCREEN_OPS.recent()
    assert ops and ops[-1]["action"] == "control.plugin" and ops[-1]["plugin"] == "p"


async def test_control_surface_runs_inside_the_hold_and_returns_metadata_only(
    monkeypatch, tmp_path
) -> None:
    from soapbot.plugins.surfaces import SurfaceRouter

    guard, _entries = _pguard(control_capability())
    audit, audit_entries = _audit_sink()
    router = SurfaceRouter(guard=guard, plugin="p", audit=audit)
    monkeypatch.setattr(
        "soapbot.config.settings",
        SimpleNamespace(
            data_dir=tmp_path,
            control_enabled=True,
            screen_dedicated_machine="BOT-WORKER",
            control_hold_minutes=15,
            control_hold_max_minutes=60,
        ),
    )
    monkeypatch.setattr(
        control, "_dispatch", lambda action, **kw: {"chars": len(kw.get("text", ""))}
    )
    monkeypatch.setattr(control, "_hostname", lambda: "BOT-WORKER")
    _CONTROL_HOLDER.engage(minutes=5, by="owner", max_minutes=60)
    secret = "插件想键入的文本 secret=1"
    result = await router.dispatch(
        "control.act", {"action": "type_text", "text": secret}, _pcaller("onebot11:group:9")
    )
    assert result["chars"] == len(secret)
    assert secret not in repr(audit_entries)  # 零泄漏：文本不进 audit
    assert any(
        e.get("action") == "surface:control.act" and e.get("outcome") == "allow"
        for e in audit_entries
    )


# ------------------------------------------------------------------ /act command stage
async def test_act_command_success_record_fits_the_opslog_contract(tmp_path, monkeypatch) -> None:
    """The v1.0 audit caught the stage-level record passing x=/y=/chars= kwargs
    that OpsLog.record does not accept — every successful /act crashed with a
    TypeError AFTER the injection had run. This pins the aligned contract."""
    from soapbot.core.message import IncomingMessage, MessageScene, MessageSegment, Sender
    from soapbot.core.pipeline import PipelineContext
    from soapbot.memory.stages import CommandStage

    settings = SimpleNamespace(
        data_dir=tmp_path, screen_enabled=True, screen_dedicated_machine="BOT-WORKER",
        control_enabled=True, control_hold_minutes=15, control_hold_max_minutes=60,
    )
    monkeypatch.setattr("soapbot.config.settings", settings)
    monkeypatch.setattr(control, "_hostname", lambda: "BOT-WORKER")
    monkeypatch.setattr(control, "_dispatch",
                        lambda action, **kw: {"chars": len(kw.get("text", ""))})
    _CONTROL_HOLDER.engage(minutes=5, by="owner", max_minutes=60)
    stage = CommandStage(store=None, kb=None)
    event = IncomingMessage(
        adapter="onebot11", message_id="m-act", scene=MessageScene.PRIVATE,
        sender=Sender(user_id="10000", nickname="owner"),
        segments=[MessageSegment.text("/act type secret-text")],
    )
    ctx = PipelineContext(event=event, adapter=SimpleNamespace())
    ctx.extras["principal"] = "owner"

    reply = await stage._cmd_act(ctx, ["type", "secret-text"])

    assert reply == ""  # 不短路模型：动作的可见效果在屏幕上
    entry = SCREEN_OPS.recent()[0]
    assert entry["action"] == "control.type_text" and entry["outcome"] == "allow"
    assert "chars=11" in entry["reason"]  # 长度并入 reason 元数据
    assert "secret-text" not in str(entry)  # 键入正文零泄漏


def test_act_command_permission_is_manage_config() -> None:
    """/act 是写面命令：必须挂在 MANAGE_CONFIG（ADMIN+）而不是普通交互权限。"""
    from soapbot.memory.stages import CommandStage
    from soapbot.security.principal import Permission

    assert CommandStage.COMMAND_PERMISSIONS.get("act") == Permission.MANAGE_CONFIG
