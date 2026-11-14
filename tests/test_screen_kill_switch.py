"""The control kill switch and the operation log: the operator's hand on the gate.

Two of the three control-plane preconditions, in software: an emergency stop the
operator holds (a file under data/, read fresh per call — the runtime cannot talk
itself out of it, and nothing chat- or plugin-reachable can remove it), and a
live, metadata-only operation log the operator can watch.
"""

from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace
from typing import ClassVar

import httpx
import pytest
from fastapi import FastAPI

from soapbot.api.auth import require_api_auth, require_role
from soapbot.screen.capture import (
    ScreenPolicy,
    ScreenRefusedError,
    capture_tile,
)
from soapbot.screen.kill import engage, is_killed, kill_file, revive
from soapbot.screen.opslog import SCREEN_OPS


@pytest.fixture(autouse=True)
def _clean_ops():
    SCREEN_OPS.clear()
    yield
    SCREEN_OPS.clear()


@pytest.fixture
def data_dir(tmp_path) -> Path:
    d = tmp_path / "data"
    d.mkdir()
    return d


def _settings(data_dir: Path, *, enabled: bool = True, machine: str = "BOT-WORKER") -> SimpleNamespace:
    return SimpleNamespace(
        data_dir=data_dir,
        screen_enabled=enabled,
        screen_dedicated_machine=machine,
        screen_frames_max=4,
        screen_capture_interval_ms=0,
    )


class _FakeMss:
    counter = 0

    class _Shot:
        def __init__(self, n: int) -> None:
            self.size = (16, 12)
            v = (n * 40) % 256
            self.bgra = bytes([v, v, v, 255]) * (16 * 12)

    class _Scanner:
        monitors: ClassVar[list] = [None, {"left": 0, "top": 0, "width": 16, "height": 12}]

        def __enter__(self):
            return self

        def __exit__(self, *exc):
            return False

        def grab(self, monitor):
            _FakeMss.counter += 1
            return _FakeMss._Shot(_FakeMss.counter)

    def mss(self):
        return _FakeMss._Scanner()


@pytest.fixture
def fake_mss(monkeypatch):
    import sys

    monkeypatch.setitem(sys.modules, "mss", _FakeMss())
    from PIL import Image

    import soapbot.screen.capture as capture_module

    def _grab(mss_module):
        with mss_module.mss() as scanner:
            shot = scanner.grab(scanner.monitors[1])
        return Image.frombytes("RGBA", shot.size, shot.bgra, "raw", "BGRA").convert("RGB")

    monkeypatch.setattr(capture_module, "_grab_image", _grab)


# ------------------------------------------------------------------ the gate
def test_kill_file_is_derived_from_data_dir(tmp_path) -> None:
    assert kill_file(_settings(tmp_path)) == tmp_path / "control_kill.switch"


def test_not_killed_when_no_file(data_dir) -> None:
    assert is_killed(_settings(data_dir)) is None


async def test_engaged_switch_stops_capture_immediately(data_dir, fake_mss) -> None:
    settings = _settings(data_dir)
    await capture_tile(ScreenPolicy.from_settings(settings), hostname="BOT-WORKER")
    engage(settings, reason="离开座位", by="owner")
    with pytest.raises(ScreenRefusedError, match="control_killed"):
        await capture_tile(ScreenPolicy.from_settings(settings), hostname="BOT-WORKER")


async def test_flipping_the_flag_back_on_cannot_revive_capture(data_dir) -> None:
    """The switch outranks the flag: a compromised runtime that re-enables the flag
    is still stopped — the gate checks the file first."""
    settings = _settings(data_dir)
    engage(settings, reason="operator", by="owner")
    tampered = _settings(data_dir, enabled=True)
    with pytest.raises(ScreenRefusedError, match="control_killed"):
        await capture_tile(ScreenPolicy.from_settings(tampered), hostname="BOT-WORKER")


def test_a_corrupt_switch_file_still_counts_as_killed(data_dir) -> None:
    """Fail closed: the operator wrote something; a parse error must not re-arm."""
    (data_dir / "control_kill.switch").write_bytes(b"\xff\xfe not json")
    killed = is_killed(_settings(data_dir))
    assert killed is not None and killed["reason"] == "control_killed"


def test_only_file_removal_revives(data_dir) -> None:
    """No command or plugin path leads to revive(); it lives behind the owner API
    and the operator's own hands."""
    settings = _settings(data_dir)
    engage(settings, reason="x", by="owner")
    revive(settings)  # what the owner-only API calls
    assert is_killed(settings) is None


# ------------------------------------------------------------------ the ops log
def test_ops_log_is_bounded_and_keeps_metadata_only() -> None:
    box = SCREEN_OPS
    box.clear()
    png = "iVBORw0KGgo" * 10  # pretend pixel bytes
    for i in range(250):
        entry = box.record(
            action="screen.capture", outcome="allow", session=f"s{i}",
            frames=3, bytes_written=1024,
        )
        entry["payload"] = png  # an attempt to smuggle pixels into the ring
    recent = box.recent(500)
    assert len(recent) == 200  # bounded
    assert all("payload" not in e for e in recent)  # the smuggled key never persisted
    assert recent[0]["session"] == "s249"  # newest first


def test_ops_log_clock_is_injectable() -> None:
    now = [1000.0]
    log = SCREEN_OPS.__class__(clock=lambda: now[0])
    log.record(action="screen.look", outcome="allow")
    now[0] += 5.0
    log.record(action="screen.look", outcome="deny", reason="control_killed")
    entries = log.recent()
    assert entries[0]["ts"] == 1005.0 and entries[1]["ts"] == 1000.0


# ------------------------------------------------------------------ the API
@pytest.fixture
async def api_env(tmp_path, monkeypatch):
    import json

    database = None  # no db needed; auth is overridden
    settings_ns = _settings(tmp_path / "data")
    (tmp_path / "data").mkdir()
    monkeypatch.setattr("soapbot.api.screen.settings", settings_ns)

    from soapbot.api.screen import router as screen_router

    app = FastAPI()
    app.include_router(screen_router)
    current = {"subject": "1", "role": "owner", "mode": "token"}

    async def fake_auth() -> dict[str, str]:
        return dict(current)

    app.dependency_overrides[require_api_auth] = fake_auth
    app.dependency_overrides[require_role(__import__("soapbot.security.principal", fromlist=["Role"]).Role.OWNER, require_credential=True)] = fake_auth
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        yield SimpleNamespace(
            client=client,
            current=current,
            data_dir=tmp_path / "data",
            settings=settings_ns,
            db=database,
            json=json,
        )


async def test_owner_can_engage_and_revive_via_the_api(api_env) -> None:
    killed = await api_env.client.post("/api/screen/kill", json={"reason": "离开座位"})
    assert killed.status_code == 200
    assert killed.json()["killed"] is True
    # The file is real state on disk, 0600-style, independent of the process.
    assert (api_env.data_dir / "control_kill.switch").is_file()

    ops = (await api_env.client.get("/api/screen/ops")).json()
    assert ops["killed"] is True and ops["kill"]["reason"] == "离开座位"
    assert any(e["action"] == "screen.kill" for e in ops["ops"])

    revived = await api_env.client.delete("/api/screen/kill")
    assert revived.status_code == 200
    assert revived.json()["killed"] is False
    assert not (api_env.data_dir / "control_kill.switch").exists()


async def test_a_member_cannot_touch_the_switch(api_env) -> None:
    api_env.current.update(subject="2", role="member")
    killed = await api_env.client.post("/api/screen/kill", json={"reason": "x"})
    assert killed.status_code == 403
    revived = await api_env.client.delete("/api/screen/kill")
    assert revived.status_code == 403
    ops = await api_env.client.get("/api/screen/ops")
    assert ops.status_code == 403


async def test_a_cookie_credential_cannot_engage_the_switch(api_env) -> None:
    """Token credential required — the same bar as budget decisions."""
    api_env.current.update(mode="cookie")
    killed = await api_env.client.post("/api/screen/kill", json={"reason": "x"})
    assert killed.status_code == 401


async def test_kill_requires_a_reason(api_env) -> None:
    blank = await api_env.client.post("/api/screen/kill", json={"reason": ""})
    assert blank.status_code == 422


# ------------------------------------------------------------------ /panic command
async def test_panic_command_engages_the_switch_from_any_chat_end(data_dir, monkeypatch) -> None:
    from soapbot.core.message import IncomingMessage, MessageScene, MessageSegment, Sender
    from soapbot.core.pipeline import PipelineContext
    from soapbot.memory.stages import CommandStage

    settings = _settings(data_dir)
    monkeypatch.setattr("soapbot.config.settings", settings)
    stage = CommandStage(store=None, kb=None)
    event = IncomingMessage(
        adapter="onebot11",
        message_id="m1",
        scene=MessageScene.PRIVATE,
        sender=Sender(user_id="10000", nickname="owner"),
        segments=[MessageSegment.text("/panic 检修")],
    )
    ctx = PipelineContext(event=event, adapter=SimpleNamespace())
    ctx.extras["principal"] = "owner"
    reply = await stage._cmd_panic(ctx, ["检修"])
    assert "急停已拉下" in reply
    killed = is_killed(settings)
    assert killed is not None and killed["reason"] == "检修"
    assert any(e["action"] == "screen.kill" for e in SCREEN_OPS.recent())
    # And the gate bites immediately: /look now refuses with the switch token.
    from soapbot.screen.capture import ScreenPolicy

    with pytest.raises(ScreenRefusedError, match="control_killed"):
        await capture_tile(ScreenPolicy.from_settings(settings), hostname="BOT-WORKER")


async def test_panic_is_idempotent(data_dir, monkeypatch) -> None:
    from soapbot.core.message import IncomingMessage, MessageScene, MessageSegment, Sender
    from soapbot.core.pipeline import PipelineContext
    from soapbot.memory.stages import CommandStage

    settings = _settings(data_dir)
    monkeypatch.setattr("soapbot.config.settings", settings)
    stage = CommandStage(store=None, kb=None)
    event = IncomingMessage(
        adapter="onebot11",
        message_id="m2",
        scene=MessageScene.PRIVATE,
        sender=Sender(user_id="10000", nickname="owner"),
        segments=[MessageSegment.text("/panic")],
    )
    ctx = PipelineContext(event=event, adapter=SimpleNamespace())
    first = await stage._cmd_panic(ctx, [])
    assert "急停已拉下" in first
    second = await stage._cmd_panic(ctx, [])
    assert "已经拉下" in second  # engaged already: no double-write, just a reminder
