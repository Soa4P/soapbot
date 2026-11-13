"""The ``screen`` capability: the bot looks at its dedicated machine, view only.

Phase 1 of the autonomous-capabilities design (§1). What the tests pin is the
five-boundary contract, because every one of them is the difference between "the
bot can see" and "the operator's privacy just left the building":

* triple gate — flag + declared hostname, an empty declaration refuses everything;
* frames travel one way, into the model context via the host inbox; the plugin
  never touches pixels and no frame content reaches audit, log or exceptions;
* the ``SCREEN`` capability rides the guard's sensitive quota and the wire's
  surface allowlist like every other privileged surface;
* ``/look`` appends the tile to the model's seam without mutating the archived
  event, and does not short-circuit the model;
* disabling the flag fails in-flight requests immediately.
"""

from __future__ import annotations

import base64
from types import SimpleNamespace
from typing import Any, ClassVar

import pytest

from soapbot.core.message import IncomingMessage, MessageScene, MessageSegment, SegmentType, Sender
from soapbot.core.pipeline import PipelineContext
from soapbot.core.stages import ScreenFrameStage
from soapbot.plugins.context import CallerContext, PluginContext
from soapbot.plugins.manifest import SENSITIVE_CAPABILITIES, Capability
from soapbot.plugins.sandbox import CapabilityDeniedError, CapabilityGrant, CapabilityGuard
from soapbot.plugins.supervisor import ALLOWED_SURFACES, arg_violation
from soapbot.screen.capture import (
    MAX_FRAMES_PER_REQUEST,
    ScreenPolicy,
    ScreenRefusedError,
    ScreenUnavailableError,
    capture_tile,
)
from soapbot.screen.inbox import SCREEN_INBOX, ScreenInbox


@pytest.fixture(autouse=True)
def _clear_inbox():
    SCREEN_INBOX.clear()
    yield
    SCREEN_INBOX.clear()


def _policy(
    *, enabled: bool = True, machine: str = "BOT-WORKER", frames: int = 4, interval: int = 0
) -> ScreenPolicy:
    return ScreenPolicy(
        enabled=enabled, dedicated_machine=machine, frames_max=frames, interval_ms=interval
    )


def _caller(session_key: str = "onebot11:group:1") -> CallerContext:
    return CallerContext(
        user_id="20001",
        display_name="tester",
        role="member",
        session_key=session_key,
        scene="group",
        group_id="1",
    )


def _guard(*caps: Capability) -> tuple[CapabilityGuard, list[dict]]:
    entries: list[dict] = []

    class _Audit:
        def record(self, **kwargs):
            entries.append(kwargs)

    grant = CapabilityGrant(plugin="p", declared=frozenset(caps), approved=frozenset(caps))
    return CapabilityGuard(grant, audit=_Audit()), entries


def _audit_sink() -> tuple[Any, list[dict]]:
    entries: list[dict] = []

    class _Audit:
        def record(self, **kwargs):
            entries.append(kwargs)

    return _Audit(), entries


def _event() -> IncomingMessage:
    return IncomingMessage(
        adapter="onebot11",
        message_id="m1",
        scene=MessageScene.GROUP,
        sender=Sender(user_id="20001", nickname="tester"),
        segments=[MessageSegment.text("/look 屏幕上是什么")],
        group_id="123456",
    )


# ------------------------------------------------------------------ the triple gate
async def test_capture_refuses_when_disabled() -> None:
    with pytest.raises(ScreenRefusedError, match="screen_disabled"):
        await capture_tile(_policy(enabled=False), hostname="BOT-WORKER")


async def test_capture_refuses_an_empty_declaration() -> None:
    """An empty dedicated-machine declaration is "no machine is dedicated": fail closed
    even with the flag on — the flag alone can never activate the capability."""
    with pytest.raises(ScreenRefusedError, match="screen_machine_undeclared"):
        await capture_tile(_policy(machine=""), hostname="anywhere")


async def test_capture_refuses_an_undeclared_machine() -> None:
    with pytest.raises(ScreenRefusedError, match="screen_machine_mismatch"):
        await capture_tile(_policy(), hostname="DESKTOP-OTHER")


async def test_capture_compares_hostnames_case_insensitively(monkeypatch) -> None:
    """Windows hostnames are case-preserving; the gate must not be. A successful gate
    then fails only on the missing mss dependency (not installed in CI) — which is the
    *right* failure: it proves the gate passed."""
    with pytest.raises(ScreenUnavailableError):
        await capture_tile(_policy(machine="bot-worker"), hostname="BOT-WORKER")


def test_capture_frames_are_capped_by_the_policy() -> None:
    assert MAX_FRAMES_PER_REQUEST == 6
    # The policy clamps rather than widens: a bigger ask is capped, never honoured.
    policy = _policy(frames=2)
    assert policy.frames_max == 2


# ------------------------------------------------------------------ the tile
class _FakeMss:
    """Captures without mss: each grab differs in luminance (or is pinned identical)."""

    counter = 0
    fixed: int | None = None  # when set, every grab returns exactly this luminance

    class _Shot:
        def __init__(self, n: int) -> None:
            self.size = (32, 24)
            # Vary luminance strongly so distinct grabs have distinct signatures.
            v = (n * 60) % 256
            self.bgra = bytes([v, v, v, 255]) * (32 * 24)

    class _Scanner:
        monitors: ClassVar[list] = [None, {"left": 0, "top": 0, "width": 32, "height": 24}]

        def __enter__(self):
            return self

        def __exit__(self, *exc):
            return False

        def grab(self, monitor):
            if _FakeMss.fixed is not None:
                return _FakeMss._Shot(_FakeMss.fixed)
            _FakeMss.counter += 1
            return _FakeMss._Shot(_FakeMss.counter)

    def mss(self):
        return _FakeMss._Scanner()


@pytest.fixture
def fake_mss(monkeypatch):
    """Inject the fake mss module so capture_tile's lazy import resolves in CI."""
    import sys

    monkeypatch.setitem(sys.modules, "mss", _FakeMss())


async def test_capture_tiles_distinct_frames_and_reports_metadata(fake_mss, monkeypatch) -> None:
    import soapbot.screen.capture as capture_module

    _FakeMss.counter = 0
    monkeypatch.setattr(capture_module, "_grab_image", lambda mss_module: _grab_fake(mss_module))
    result = await capture_tile(_policy(), frames=3, hostname="BOT-WORKER")
    assert result.frames_captured == 3
    assert result.frames_used == 3 and result.frames_dropped == 0
    assert result.payload.width <= 1024 and result.payload.height <= 1024
    assert result.size_bytes > 0
    # The tile is a valid PNG whose bytes are NOT written anywhere — the payload
    # lives in the returned object only.
    head = base64.b64decode(result.payload.data_url.partition("base64,")[2])[:4]
    assert head == b"\x89PNG"


def _grab_fake(mss_module):
    """Mirrors capture._grab_image but over the fake scanner."""
    from PIL import Image

    with mss_module.mss() as scanner:
        shot = scanner.grab(scanner.monitors[1])
    img = Image.frombytes("RGBA", shot.size, shot.bgra, "raw", "BGRA")
    return img.convert("RGB")


async def test_identical_frames_are_deduplicated(fake_mss, monkeypatch) -> None:
    import soapbot.screen.capture as capture_module

    _FakeMss.fixed = 96  # a still screen: every grab identical → one distinct frame
    monkeypatch.setattr(capture_module, "_grab_image", lambda m: _grab_fake(m))
    result = await capture_tile(_policy(), frames=4, hostname="BOT-WORKER")
    assert result.frames_captured == 4
    assert result.frames_used == 1
    assert result.frames_dropped == 3


# ------------------------------------------------------------------ the inbox
def test_inbox_is_one_shot_per_session_and_expires() -> None:
    box = ScreenInbox()  # normal box: one-shot, not expired
    payload = SimpleNamespace(data_url="data:image/png;base64,AAAA")
    box.put("s1", payload)
    assert box.pending("s1") is True
    assert box.take("s1") is payload
    assert box.take("s1") is None  # one shot
    assert box.pending("s1") is False

    now = [100.0]
    expired = ScreenInbox(ttl=120.0, clock=lambda: now[0])  # injectable clock
    expired.put("s2", payload)
    assert expired.take("s2") is payload  # fresh
    expired.put("s2", payload)
    now[0] += 121.0
    assert expired.take("s2") is None  # TTL passed
    assert expired.pending("s2") is False


def test_inbox_replaces_the_pending_tile_instead_of_queuing() -> None:
    """The newest look wins: a plugin that captures twice before a model turn must
    not deliver a stale frame the operator can no longer see."""
    box = ScreenInbox()
    first = SimpleNamespace(data_url="first")
    second = SimpleNamespace(data_url="second")
    box.put("s1", first)
    box.put("s1", second)
    assert box.take("s1") is second


# ------------------------------------------------------------------ capability + surface
def test_screen_is_a_sensitive_capability() -> None:
    assert Capability.SCREEN in SENSITIVE_CAPABILITIES


async def test_surface_refuses_without_the_capability_and_audits_the_denial() -> None:
    from soapbot.plugins.surfaces import SurfaceRouter

    guard, entries = _guard()  # no SCREEN approved
    router = SurfaceRouter(guard=guard, plugin="p")
    with pytest.raises(CapabilityDeniedError):
        await router.dispatch("screen.capture", {"frames": 1}, _caller())
    assert any(e.get("outcome") == "deny" for e in entries)


async def test_surface_put_the_tile_in_the_inbox_and_audits_metadata_only(fake_mss, monkeypatch) -> None:
    import soapbot.screen.capture as capture_module
    from soapbot.plugins.surfaces import SurfaceRouter

    guard, _guard_entries = _guard(Capability.SCREEN)
    audit, entries = _audit_sink()
    router = SurfaceRouter(guard=guard, plugin="p", audit=audit)
    monkeypatch.setattr("soapbot.config.settings", SimpleNamespace(
        screen_enabled=True, screen_dedicated_machine="BOT-WORKER",
        screen_frames_max=2, screen_capture_interval_ms=0,
    ))
    _FakeMss.counter = 200
    monkeypatch.setattr(capture_module, "_grab_image", lambda m: _grab_fake(m))
    monkeypatch.setattr("soapbot.screen.capture.socket", SimpleNamespace(gethostname=lambda: "BOT-WORKER"))
    result = await router.dispatch("screen.capture", {"frames": 1}, _caller("onebot11:group:7"))
    assert result["ref"] == "screen:pending"
    assert result["frames_used"] == 1
    assert SCREEN_INBOX.pending("onebot11:group:7") is True
    # Metadata only: no base64, no data URL, no pixels in the audit trail.
    text = repr(entries)
    assert "base64" not in text and "data:image" not in text
    assert any(e.get("action") == "surface:screen.capture" and e.get("outcome") == "allow" for e in entries)


async def test_surface_refusal_names_the_reason_and_audits_it(monkeypatch) -> None:
    from soapbot.plugins.surfaces import SurfaceRouter

    guard, _guard_entries = _guard(Capability.SCREEN)
    audit, entries = _audit_sink()
    router = SurfaceRouter(guard=guard, plugin="p", audit=audit)
    monkeypatch.setattr("soapbot.config.settings", SimpleNamespace(
        screen_enabled=False, screen_dedicated_machine="",
        screen_frames_max=2, screen_capture_interval_ms=0,
    ))
    with pytest.raises(PermissionError, match="screen_disabled"):
        await router.dispatch("screen.capture", {}, _caller())
    assert any(
        e.get("action") == "surface:screen.capture" and e.get("outcome") == "deny"
        and "screen_disabled" in str(e.get("detail"))
        for e in entries
    )


def test_the_wire_rejects_scope_keys_and_allows_the_surface() -> None:
    assert "screen.capture" in ALLOWED_SURFACES
    assert not arg_violation("screen.capture", {"frames": 2})
    assert arg_violation("screen.capture", {"session_key": "other:group:1"})


async def test_disabling_the_flag_fails_the_next_request_immediately(fake_mss, monkeypatch) -> None:
    """设计 §1.3 门槛：停用后请求立即失败——门禁在抓帧之前，不会拍完再拦。"""
    calls: list[int] = []

    def _counting_grab(mss_module):
        calls.append(1)
        return _grab_fake(mss_module)

    import soapbot.screen.capture as capture_module

    monkeypatch.setattr(capture_module, "_grab_image", _counting_grab)
    policy = _policy()
    await capture_tile(policy, hostname="BOT-WORKER")
    assert calls == [1]
    policy.enabled = False  # the operator flips the kill switch
    with pytest.raises(ScreenRefusedError, match="screen_disabled"):
        await capture_tile(policy, hostname="BOT-WORKER")
    assert calls == [1]  # no second grab happened


async def test_ctx_method_routes_through_the_surface_router(fake_mss, monkeypatch) -> None:
    """The in-process ctx method shares the isolated path's authorization point."""
    import soapbot.screen.capture as capture_module
    from soapbot.plugins.context import bind_caller

    guard, _entries = _guard(Capability.SCREEN)
    ctx = PluginContext(plugin="p", guard=guard)
    _FakeMss.counter = 300
    monkeypatch.setattr(capture_module, "_grab_image", lambda m: _grab_fake(m))
    monkeypatch.setattr("soapbot.screen.capture.socket", SimpleNamespace(gethostname=lambda: "BOT-WORKER"))
    monkeypatch.setattr("soapbot.config.settings", SimpleNamespace(
        screen_enabled=True, screen_dedicated_machine="BOT-WORKER",
        screen_frames_max=2, screen_capture_interval_ms=0,
    ))
    with bind_caller(_caller("onebot11:group:9")):
        result = await ctx.screen_capture(2)
    assert result["ref"] == "screen:pending"
    assert result["frames_captured"] == 2
    assert SCREEN_INBOX.pending("onebot11:group:9") is True


# ------------------------------------------------------------------ the stage + /look
async def test_screen_frame_stage_moves_the_tile_into_clean_segments_only() -> None:
    payload = SimpleNamespace(
        data_url="data:image/png;base64," + base64.b64encode(b"fakepng").decode()
    )
    event = _event()
    SCREEN_INBOX.put(event.session_key, payload)
    ctx = PipelineContext(event=event, adapter=SimpleNamespace())
    ctx.extras["clean_segments"] = [MessageSegment.text("/look 屏幕上是什么")]
    await ScreenFrameStage().run(ctx)
    segments = ctx.extras["clean_segments"]
    assert len(segments) == 2 and segments[-1].type is SegmentType.IMAGE
    # The archived event is untouched — pixels never reach the archive.
    assert ctx.event.segments == [MessageSegment.text("/look 屏幕上是什么")]
    assert SCREEN_INBOX.take(event.session_key) is None  # one-shot


async def test_screen_frame_stage_is_a_noop_without_a_pending_tile() -> None:
    ctx = PipelineContext(event=_event(), adapter=SimpleNamespace())
    ctx.extras["clean_segments"] = [MessageSegment.text("hi")]
    await ScreenFrameStage().run(ctx)
    assert len(ctx.extras["clean_segments"]) == 1


async def test_look_command_appends_the_frame_and_keeps_the_model_running(fake_mss, monkeypatch) -> None:
    """The /look handler must NOT set skip_model: its product is context, not text."""
    import soapbot.screen.capture as capture_module
    from soapbot.memory.stages import CommandStage

    stage = CommandStage(store=None, kb=None)  # store unused by /look
    _FakeMss.counter = 400
    monkeypatch.setattr(capture_module, "_grab_image", lambda m: _grab_fake(m))
    monkeypatch.setattr("soapbot.screen.capture.socket", SimpleNamespace(gethostname=lambda: "BOT-WORKER"))
    monkeypatch.setattr("soapbot.config.settings", SimpleNamespace(
        screen_enabled=True, screen_dedicated_machine="BOT-WORKER",
        screen_frames_max=6, screen_capture_interval_ms=0,
    ))

    ctx = PipelineContext(event=_event(), adapter=SimpleNamespace())
    ctx.extras["clean_segments"] = [MessageSegment.text("/look 屏幕上是什么")]
    ctx.extras["principal"] = "owner"
    reply = await stage._cmd_look(ctx, [])
    assert reply is None  # fall through to the model
    assert "skip_model" not in ctx.extras
    assert not ctx.model_reply  # no fabricated text reply: the model speaks next
    segments = ctx.extras["clean_segments"]
    assert len(segments) == 2 and segments[-1].type is SegmentType.IMAGE


async def test_look_command_refuses_with_a_token_when_disabled(monkeypatch) -> None:
    from soapbot.memory.stages import CommandStage

    stage = CommandStage(store=None, kb=None)
    monkeypatch.setattr(
        "soapbot.config.settings",
        SimpleNamespace(
            screen_enabled=False,
            screen_dedicated_machine="",
            screen_frames_max=6,
            screen_capture_interval_ms=0,
        ),
    )
    ctx = PipelineContext(event=_event(), adapter=SimpleNamespace())
    reply = await stage._cmd_look(ctx, [])
    assert reply is not None and "screen_disabled" in reply
    assert "clean_segments" not in ctx.extras  # nothing was captured
