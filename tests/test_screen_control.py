"""Control plane phase 2: keyboard/mouse injection under the full gate chain.

The trust chain, tested link by link: 急停文件现读 > flag + 专用机器双门 > 授权持有
（内存态、重启即失效、时长钳制）。Actions land in SCREEN_OPS with metadata only —
typed text never reaches any log, audit or exception message. Injection runs behind
the module-level ``_dispatch``/``_send``/``_move_and_click`` seams so tests intercept
without touching a real display (patching ``ctypes.windll`` does not work: each
``windll.user32`` access hands out a fresh instance).
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
        enabled=enabled, dedicated_machine=machine, kill_file=None,
        hold_minutes=15, hold_max_minutes=60,
    )


def _holder(minutes: int = 15) -> ControlHolder:
    h = ControlHolder()
    h.engage(minutes=minutes, by="owner", max_minutes=60)
    return h


def _patch_injection(monkeypatch) -> list[tuple[str, int]]:
    """Replace SendInput-level injection with a recorder: (kind, code_or_flags)."""
    calls: list[tuple[str, int]] = []

    def fake_move_and_click(user32, *, x, y, double):
        calls.append(("click", x, y))
        return None

    def fake_send(user32, input_type, *, mi_flags=0, mi_mouse_data=0, ki_vk=0, ki_scan=0, ki_flags=0):
        if input_type == control._INPUT_MOUSE:
            calls.append(("mouse", mi_flags))
        else:
            calls.append(("key", ki_vk or ki_scan))
        return 1

    monkeypatch.setattr(control, "_move_and_click", fake_move_and_click)
    monkeypatch.setattr(control, "_send", fake_send)
    return calls


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
        enabled=True, dedicated_machine="BOT-WORKER", kill_file=path,
        hold_minutes=15, hold_max_minutes=60,
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


def test_act_click_dispatches_and_records_metadata(monkeypatch) -> None:
    calls = _patch_injection(monkeypatch)
    result = act(_gate(), _holder(), "click", x=120, y=300, hostname="BOT-WORKER")
    assert result["action"] == "click" and result["x"] == 120
    assert calls == [("click", 120, 300)]
    ops = SCREEN_OPS.recent()
    assert ops and ops[-1]["action"] == "control.click"
    assert ops[-1]["outcome"] == "allow"


def test_act_double_click_flagged(monkeypatch) -> None:
    _patch_injection(monkeypatch)
    result = act(_gate(), _holder(), "double_click", x=5, y=6, hostname="BOT-WORKER")
    assert result["double"] is True


def test_act_type_text_records_length_never_content(monkeypatch) -> None:
    _patch_injection(monkeypatch)
    secret = "机密文本 password=abc123"
    result = act(_gate(), _holder(), "type_text", text=secret, hostname="BOT-WORKER")
    assert result["chars"] == len(secret)
    audit = get_audit_log().recent(kind="screen")
    assert audit and all(secret not in str(e) for e in audit)  # 零泄漏：键入文本不进任何记录


def test_act_key_sends_vk_down_then_up(monkeypatch) -> None:
    calls = _patch_injection(monkeypatch)
    result = act(_gate(), _holder(), "key", key="enter", hostname="BOT-WORKER")
    assert result["key"] == "enter"
    assert calls == [("key", 0x0D), ("key", 0x0D)]  # down + up, same vk


def test_act_key_uppercase_is_normalized(monkeypatch) -> None:
    _patch_injection(monkeypatch)
    result = act(_gate(), _holder(), "key", key="ESC", hostname="BOT-WORKER")
    assert result["key"] == "esc"


def test_act_unknown_key_is_refused(monkeypatch) -> None:
    _patch_injection(monkeypatch)
    with pytest.raises(ControlRefusedError, match="control_unknown_key"):
        act(_gate(), _holder(), "key", key="f13", hostname="BOT-WORKER")
    # The refusal is visible to the operator, with the token only.
    ops = SCREEN_OPS.recent()
    assert ops and ops[-1]["action"] == "control.key" and ops[-1]["outcome"] == "deny"


def test_act_unknown_action_is_refused(monkeypatch) -> None:
    _patch_injection(monkeypatch)
    with pytest.raises(ControlRefusedError, match="control_unknown_action"):
        act(_gate(), _holder(), "format_disk", hostname="BOT-WORKER")


def test_act_scroll_sends_wheel_delta(monkeypatch) -> None:
    calls = _patch_injection(monkeypatch)
    result = act(_gate(), _holder(), "scroll", delta=-120, hostname="BOT-WORKER")
    assert result["delta"] == -120
    assert calls == [("mouse", control._MOUSE_WHEEL)]


def test_act_without_a_hold_is_refused(monkeypatch) -> None:
    with pytest.raises(ControlRefusedError, match="control_no_grant"):
        act(_gate(), ControlHolder(), "click", x=1, y=1, hostname="BOT-WORKER")


def test_act_refused_when_the_switch_flips_mid_hold(tmp_path, monkeypatch) -> None:
    """授权窗内按下急停：下一个动作立即被拒（现读闸，无缓存窗口）。"""
    _patch_injection(monkeypatch)
    from soapbot.screen.kill import kill_file

    path = kill_file(SimpleNamespace(data_dir=tmp_path))
    path.write_text("{}")
    gate = ControlGate(
        enabled=True, dedicated_machine="BOT-WORKER", kill_file=path,
        hold_minutes=15, hold_max_minutes=60,
    )
    hold = _holder()
    with pytest.raises(ControlRefusedError, match="control_killed"):
        act(gate, hold, "click", x=1, y=1, hostname="BOT-WORKER")


def test_key_codes_cover_the_common_ui_set() -> None:
    for name in ("enter", "esc", "tab", "up", "down", "left", "right"):
        assert name in KEY_CODES


def test_the_hold_expires_and_the_gate_refuses_afterwards() -> None:
    hold = _holder(minutes=10)
    assert hold.active(now=time.time()) is not None
    assert hold.active(now=time.time() + 11 * 60) is None


def test_screen_ops_records_are_metadata_only(monkeypatch) -> None:
    _patch_injection(monkeypatch)
    act(_gate(), _holder(), "type_text", text="机密内容 secret=abc", hostname="BOT-WORKER")
    ops = SCREEN_OPS.recent()
    assert all("机密内容" not in str(o) and "secret=abc" not in str(o) for o in ops)


def test_audit_for_control_actions_never_carries_text(monkeypatch) -> None:
    _patch_injection(monkeypatch)
    act(_gate(), _holder(), "type_text", text="top-secret-token-xyz", hostname="BOT-WORKER")
    audit = get_audit_log().recent(kind="screen")
    assert audit and all("top-secret-token-xyz" not in str(e) for e in audit)


# ------------------------------------------------------------------ capability + surface
def _pcaller(session_key: str = "onebot11:group:1"):
    from soapbot.plugins.context import CallerContext

    return CallerContext(
        user_id="20001", display_name="tester", role="member",
        session_key=session_key, scene="group", group_id="1",
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


async def test_control_surface_refuses_without_a_hold_and_audits_the_token(monkeypatch, tmp_path) -> None:
    from soapbot.plugins.surfaces import SurfaceRouter

    guard, _entries = _pguard(control_capability())
    audit, audit_entries = _audit_sink()
    router = SurfaceRouter(guard=guard, plugin="p", audit=audit)
    monkeypatch.setattr("soapbot.config.settings", SimpleNamespace(
        data_dir=tmp_path, control_enabled=True, screen_dedicated_machine="BOT-WORKER",
        control_hold_minutes=15, control_hold_max_minutes=60,
    ))
    monkeypatch.setattr(control, "_hostname", lambda: "BOT-WORKER")
    with pytest.raises(PermissionError, match="control_no_grant"):
        await router.dispatch("control.act", {"action": "click", "x": 1, "y": 1}, _pcaller())
    assert any(
        e.get("action") == "surface:control.act" and e.get("outcome") == "deny"
        and "control_no_grant" in str(e.get("detail"))
        for e in audit_entries
    )
    ops = SCREEN_OPS.recent()
    assert ops and ops[-1]["action"] == "control.plugin" and ops[-1]["plugin"] == "p"


async def test_control_surface_runs_inside_the_hold_and_returns_metadata_only(monkeypatch, tmp_path) -> None:
    from soapbot.plugins.surfaces import SurfaceRouter

    guard, _entries = _pguard(control_capability())
    audit, audit_entries = _audit_sink()
    router = SurfaceRouter(guard=guard, plugin="p", audit=audit)
    monkeypatch.setattr("soapbot.config.settings", SimpleNamespace(
        data_dir=tmp_path, control_enabled=True, screen_dedicated_machine="BOT-WORKER",
        control_hold_minutes=15, control_hold_max_minutes=60,
    ))
    monkeypatch.setattr(control, "_dispatch", lambda action, **kw: {"chars": len(kw.get("text", ""))})
    monkeypatch.setattr(control, "_hostname", lambda: "BOT-WORKER")
    _CONTROL_HOLDER.engage(minutes=5, by="owner", max_minutes=60)
    secret = "插件想键入的文本 secret=1"
    result = await router.dispatch(
        "control.act", {"action": "type_text", "text": secret}, _pcaller("onebot11:group:9")
    )
    assert result["chars"] == len(secret)
    assert secret not in repr(audit_entries)  # 零泄漏：文本不进 audit
    assert any(e.get("action") == "surface:control.act" and e.get("outcome") == "allow"
               for e in audit_entries)
