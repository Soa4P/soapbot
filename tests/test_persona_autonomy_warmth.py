"""Persona autonomy knobs, host warmth, version-safe extras, and WBI subtitles.

The shared property: none of these values are authored by a model or a plugin.
Persona knobs come from a file the operator edits, warmth is a deterministic
function of delivered replies, and subtitles are a whitelisted L2 view of one
signed request.
"""

from __future__ import annotations

import time
from pathlib import Path
from types import SimpleNamespace

import pytest

from soapbot.ai.autonomy import (
    WARMTH_TRACKER,
    AutonomyConfig,
    WarmthParams,
    compute_warmth,
    parse_autonomy,
)
from soapbot.ai.persona import (
    Persona,
    dump_persona_file,
    load_persona_file,
    persona_from_payload,
    persona_to_payload,
)
from soapbot.bilibili.client import BilibiliClient
from soapbot.core.message import IncomingMessage, MessageScene, MessageSegment, Sender
from soapbot.core.pipeline import PipelineContext
from soapbot.memory.stages import PersistReplyStage
from soapbot.plugins.context import CallerContext
from soapbot.plugins.memory_api import build_session_view
from soapbot.plugins.sandbox import CapabilityGrant, CapabilityGuard
from soapbot.plugins.surfaces import SurfaceRouter


@pytest.fixture(autouse=True)
def _clear_warmth():
    WARMTH_TRACKER.clear()
    yield
    WARMTH_TRACKER.clear()


# ------------------------------------------------------------------ persona knobs

def _persona(extra: dict) -> Persona:
    return Persona(id="demo", name="demo", system_prompt="hello", extra=extra)


def test_defaults_are_conservative() -> None:
    config = parse_autonomy(_persona({}))
    assert config == AutonomyConfig()
    assert config.sessions == ()
    assert config.daily_limit == 2
    assert config.voice_self_select is False
    assert config.allows_session("onebot11:group:1") is False


def test_valid_autonomy_and_warmth_are_parsed() -> None:
    config = parse_autonomy(
        _persona(
            {
                "autonomy": {
                    "sessions": ["onebot11:group:1"],
                    "daily_limit": 4,
                },
                "warmth": {"baseline": 0.2, "growth": 0.3, "threshold": 0.7},
                "voice_self_select": True,
            }
        )
    )
    assert config.allows_session("onebot11:group:1") is True
    assert config.daily_limit == 4
    assert config.warmth.threshold == 0.7
    assert config.voice_self_select is True


def test_malformed_values_fall_back_instead_of_widening() -> None:
    config = parse_autonomy(
        _persona({"autonomy": {"sessions": "anywhere", "daily_limit": "many"}})
    )
    assert config.sessions == ()
    assert config.daily_limit == 2
    # A numeric but excessive limit is clamped, never used as written.
    capped = parse_autonomy(_persona({"autonomy": {"daily_limit": 9999}}))
    assert capped.daily_limit == 20


def test_front_matter_survives_a_save_and_a_rollback() -> None:
    card = _persona(
        {
            "autonomy": {"daily_limit": 3},
            "warmth": {"decay_per_hour": 0.02},
            "voice_self_select": True,
            "unknown_future_key": "keep me",
        }
    )
    path = Path(__file__).parent / "_persona_tmp.md"
    try:
        path.write_text(dump_persona_file(card), encoding="utf-8")
        reloaded = load_persona_file(path)
        assert parse_autonomy(reloaded).daily_limit == 3
        assert reloaded.extra["unknown_future_key"] == "keep me"
    finally:
        path.unlink(missing_ok=True)

    restored = persona_from_payload(persona_to_payload(card), "demo")
    assert parse_autonomy(restored).daily_limit == 3
    assert restored.extra["voice_self_select"] is True
    assert restored.extra["unknown_future_key"] == "keep me"


# ------------------------------------------------------------------ warmth

def test_warmth_is_deterministic_bounded_and_decays() -> None:
    p = WarmthParams()
    fresh = compute_warmth(5, 0.0, p)
    idle = compute_warmth(5, 48.0, p)
    assert 0.0 <= idle < fresh <= 1.0
    assert compute_warmth(0, 0.0, p) == p.baseline
    assert compute_warmth(10**9, 0.0, p) <= 1.0


def test_tracker_counts_only_delivered_replies_in_the_window() -> None:
    WARMTH_TRACKER.record("onebot11:group:1", now=1000.0)
    WARMTH_TRACKER.record("onebot11:group:1", now=1001.0)
    assert WARMTH_TRACKER.warmth("onebot11:group:1", now=1002.0) > 0
    assert WARMTH_TRACKER.warmth("onebot11:group:2", now=1002.0) == 0.0
    assert WARMTH_TRACKER.warmth("onebot11:group:1", now=1002.0 + 8 * 86400) == 0.0


async def test_persist_reply_records_warmth_only_after_a_successful_archive() -> None:
    class _Store:
        def __init__(self, *, fail: bool = False) -> None:
            self.calls = 0
            self.fail = fail

        async def archive_message(self, **kwargs):
            self.calls += 1
            if self.fail:
                raise OSError("disk full")

    def _ctx() -> PipelineContext:
        event = IncomingMessage(
            adapter="onebot11",
            message_id="m1",
            scene=MessageScene.GROUP,
            sender=Sender(user_id="u1", nickname="u1"),
            segments=[MessageSegment.text("hi")],
            group_id="123",
        )
        ctx = PipelineContext(event=event, adapter=None)
        ctx.model_reply = "hello"
        ctx.extras["send_ok"] = True
        return ctx

    good = _Store()
    await PersistReplyStage(good).run(_ctx())  # type: ignore[arg-type]
    assert good.calls == 1
    assert WARMTH_TRACKER.warmth(_ctx().event.session_key) > 0

    bad = _Store(fail=True)
    await PersistReplyStage(bad).run(_ctx())  # type: ignore[arg-type]
    assert bad.calls == 1


def test_session_view_exposes_a_host_computed_warmth_scalar() -> None:
    caller = CallerContext(
        user_id="u1", display_name="u1", role="member",
        session_key="onebot11:group:1", scene="group", group_id="1",
    )
    WARMTH_TRACKER.record(caller.session_key, now=time.time())
    view = build_session_view(caller)
    assert 0.0 < view.warmth <= 1.0
    assert build_session_view(caller, warmth=2.0).warmth == 1.0
    assert build_session_view(caller, warmth=-1.0).warmth == 0.0


async def test_the_isolated_surface_dict_lists_warmth_explicitly() -> None:
    from soapbot.plugins.manifest import Capability

    grant = CapabilityGrant(
        plugin="p",
        declared=frozenset({Capability.SESSION}),
        approved=frozenset({Capability.SESSION}),
    )
    guard = CapabilityGuard(grant, audit=None)
    router = SurfaceRouter(guard=guard, plugin="p")
    caller = CallerContext(
        user_id="u1", display_name="u1", role="member",
        session_key="onebot11:group:1", scene="group", group_id="1",
    )
    payload = await router.dispatch("session.view", {}, caller)
    assert "warmth" in payload
    assert set(payload) == {
        "session_key", "scene", "group_id", "user_id",
        "display_name", "is_group", "warmth",
    }


# ------------------------------------------------------------------ WBI subtitle

class _FakeHttp:
    def __init__(self) -> None:
        self.urls: list[str] = []
        self.params: list[dict] = []

    async def get(self, url, params=None):
        self.urls.append(url)
        self.params.append(dict(params or {}))
        if "view" in url:
            # subtitle() 现在先解析 aid/cid（只传 bvid 会被 player 端点 -400 拒绝），
            # 再打 wbi 签名的 player 端点——两段请求，形状不同。
            return SimpleNamespace(
                status_code=200,
                json=lambda: {
                    "code": 0,
                    "data": {"aid": 117, "pages": [{"cid": 55}]},
                },
            )
        return SimpleNamespace(
            status_code=200,
            json=lambda: {
                "code": 0,
                "data": {
                    "subtitle": {
                        "subtitles": [
                            {"lan": "zh-CN", "lan_doc": "中文", "subtitle_url": "//x/a.json"},
                            {"lan": "en-US", "lan_doc": "English", "subtitle_url": "//x/b.json"},
                        ]
                    },
                    "playurl": "should-not-leak",
                },
            },
        )


async def test_subtitle_uses_a_wbi_signed_l2_request_and_a_field_whitelist() -> None:
    client = BilibiliClient(tier="l2", min_interval=0.0)
    http = _FakeHttp()
    client._http = http  # type: ignore[assignment]
    client._wbi_key = "k" * 64
    client._wbi_fetched_at = time.time()
    result = await client.subtitle("BV1abc")
    assert result["has_subtitle"] is True
    assert [s["url"] for s in result["subtitles"]] == [
        "https://x/a.json", "https://x/b.json",
    ]
    assert "playurl" not in str(result)
    assert http.urls == [
        "https://api.bilibili.com/x/web-interface/view",
        "https://api.bilibili.com/x/player/wbi/v2",
    ]
    # view（第一段）拿 aid/cid；player（第二段）带上了它们 + wbi 签名
    assert http.params[0] == {"bvid": "BV1abc"}
    assert http.params[1]["aid"] == "117" and http.params[1]["cid"] == "55"
    assert "w_rid" in http.params[1] and "wts" in http.params[1]


async def test_subtitle_refuses_a_bad_bvid_without_a_network_call() -> None:
    client = BilibiliClient(tier="l2", min_interval=0.0)
    http = _FakeHttp()
    client._http = http  # type: ignore[assignment]
    with pytest.raises(ValueError, match="BV"):
        await client.subtitle("javascript:alert(1)")
    assert http.urls == []


async def test_l1_cannot_use_the_signed_subtitle_path() -> None:
    from soapbot.bilibili.client import BilibiliTierError

    client = BilibiliClient(tier="l1", min_interval=0.0)
    client._http = _FakeHttp()  # type: ignore[assignment]
    with pytest.raises(BilibiliTierError):
        await client.subtitle("BV1abc")


async def test_the_subtitle_endpoint_is_a_fixed_host_owned_path() -> None:
    from soapbot.api import bilibili as api

    assert any(
        getattr(route, "path", "") == "/api/bilibili/subtitle"
        for route in api.router.routes
    )
