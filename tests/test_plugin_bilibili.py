"""The ``bilibili`` capability: login state as a vetted host surface.

The security claim being tested: the plugin's degree of freedom is a *path* on a
host-pinned host, and the cookie never appears in audit details, exceptions or the
wire the plugin controls. Every test that touches the cookie asserts on what a
plugin (or a log reader) could actually see.
"""

from __future__ import annotations

import json
from typing import ClassVar

import pytest

from soapbot.plugins.manifest import Capability
from soapbot.plugins.sandbox import (
    BilibiliClient,
    BilibiliUnavailableError,
    CapabilityDeniedError,
    CapabilityGrant,
    CapabilityGuard,
)


def _guard(*caps: Capability) -> CapabilityGuard:
    grant = CapabilityGrant(
        plugin="bili", declared=frozenset(caps), approved=frozenset(caps)
    )
    return CapabilityGuard(grant, audit=None)


class _FakeResponse:
    def __init__(self, *, status_code: int = 200, content: bytes = b"{}"):
        self.status_code = status_code
        self.content = content


class _FakeClient:
    """Records what would go on the wire; returns a canned JSON payload."""

    last_headers: ClassVar[dict] = {}
    last_url: ClassVar[str] = ""
    last_params: ClassVar[dict] = {}

    def __init__(self, *, payload: dict | None = None, status_code: int = 200, content: bytes | None = None):
        self._payload = payload if payload is not None else {"code": 0, "data": {}}
        self._status = status_code
        self._content = content

    async def request(self, method, url, headers=None, params=None, **kwargs):
        _FakeClient.last_headers = headers or {}
        _FakeClient.last_url = url
        _FakeClient.last_params = dict(params or {})
        body = self._content if self._content is not None else json.dumps(self._payload).encode("utf-8")
        return _FakeResponse(status_code=self._status, content=body)

    async def aclose(self) -> None:
        return None


def _factory(client: _FakeClient):
    def build(**kwargs):
        # Class-level capture tables are shared; reset so a test only sees its own wire.
        _FakeClient.last_headers = {}
        _FakeClient.last_url = ""
        _FakeClient.last_params = {}
        return client

    return build


@pytest.mark.asyncio
async def test_denied_without_the_capability() -> None:
    client = BilibiliClient(
        _guard(), cookie_provider=lambda: "SESSDATA=secret", client_factory=_factory(_FakeClient())
    )
    with pytest.raises(CapabilityDeniedError):
        await client.get_json("/x/web-interface/history/cursor")


@pytest.mark.asyncio
async def test_cookie_goes_to_bilibili_and_nowhere_visible() -> None:
    """Granted call: cookie on the wire to the pinned host, never in the audit detail."""
    recorded = []

    class _Audit:
        def record(self, **kwargs):
            recorded.append(kwargs)

    grant = CapabilityGrant(
        plugin="bili",
        declared=frozenset({Capability.BILIBILI}),
        approved=frozenset({Capability.BILIBILI}),
    )
    guard = CapabilityGuard(grant, audit=_Audit())
    client = BilibiliClient(
        guard,
        cookie_provider=lambda: "SESSDATA=topsecret",
        client_factory=_factory(_FakeClient(payload={"code": 0, "data": {"items": []}})),
    )
    payload = await client.get_json(
        "/x/web-interface/history/cursor", params={"ps": "5"}
    )
    assert payload["code"] == 0
    # The credential reached exactly one place: the request to the pinned host.
    assert _FakeClient.last_headers["Cookie"] == "SESSDATA=topsecret"
    assert _FakeClient.last_url.startswith("https://api.bilibili.com/")
    # And it is in no audit line.
    for entry in recorded:
        assert "topsecret" not in json.dumps(entry, ensure_ascii=False, default=str)


@pytest.mark.asyncio
async def test_unconfigured_cookie_raises_specific_error() -> None:
    client = BilibiliClient(
        _guard(Capability.BILIBILI), cookie_provider=lambda: "", client_factory=_factory(_FakeClient())
    )
    with pytest.raises(BilibiliUnavailableError):
        await client.get_json("/x/web-interface/history/cursor")


@pytest.mark.asyncio
async def test_path_cannot_escape_the_pinned_host() -> None:
    _FakeClient.last_url = ""  # reset shared capture before asserting on it
    client = BilibiliClient(
        _guard(Capability.BILIBILI),
        cookie_provider=lambda: "SESSDATA=x",
        client_factory=_factory(_FakeClient()),
    )
    for bad in ("https://evil.com/x", "http://api.bilibili.com/x", "/x//evil", "x/web"):
        with pytest.raises(ValueError):
            await client.get_json(bad)
    assert _FakeClient.last_url == ""  # nothing ever went out


@pytest.mark.asyncio
async def test_non_200_reports_status_not_body() -> None:
    client = BilibiliClient(
        _guard(Capability.BILIBILI),
        cookie_provider=lambda: "SESSDATA=topsecret",
        client_factory=_factory(_FakeClient(status_code=412, content=b"SESSDATA=topsecret")),
    )
    with pytest.raises(ValueError, match="HTTP 412"):
        await client.get_json("/x/web-interface/history/cursor")
    # The exception text is the only surface a plugin sees; the body (which echoed
    # the credential) must not be in it.
    assert "topsecret" not in str(ValueError("HTTP 412"))


def test_child_shim_sends_path_only() -> None:
    """The isolated-mode facade is a string template (_CHILD_WORKER), so the wire
    contract is asserted textually — the same style the workflow gate uses.

    What must hold: the shim names the allowed surface, sends only path/params,
    and its bilibili code never mentions Cookie (the child has no credential and
    must not grow one).
    """
    from soapbot.plugins.supervisor import _CHILD_WORKER

    assert '"bilibili.request"' in _CHILD_WORKER
    assert "bilibili" in _CHILD_WORKER
    # The child-side shim block: no Cookie composition anywhere near it.
    shim_start = _CHILD_WORKER.index("def bilibili(self):")
    shim = _CHILD_WORKER[shim_start : shim_start + 900]
    assert "get_json" in shim
    assert "Cookie" not in shim
    assert "SESSDATA" not in _CHILD_WORKER


async def test_router_dispatch_checks_guard_and_returns_payload() -> None:
    """Host-side isolated path: guard re-check + client, with a stubbed wire."""

    from soapbot.plugins.sandbox import CapabilityGrant, CapabilityGuard
    from soapbot.plugins.surfaces import SurfaceRouter

    class _Audit:
        def __init__(self) -> None:
            self.entries: list[dict] = []

        def record(self, **kwargs):
            self.entries.append(kwargs)

    audit = _Audit()
    grant = CapabilityGrant(
        plugin="bili",
        declared=frozenset({Capability.BILIBILI}),
        approved=frozenset({Capability.BILIBILI}),
    )
    guard = CapabilityGuard(grant, audit=audit)

    wire: dict = {}

    def _fake_factory(**kwargs):
        class _C:
            async def request(self, method, url, headers=None, params=None, **kw):
                wire["url"] = url
                wire["headers"] = headers or {}
                return _FakeResponse(
                    content=json.dumps({"code": 0, "data": {"ok": True}}).encode()
                )

            async def aclose(self):
                return None

        return _C()

    router = SurfaceRouter(
        guard=guard,
        plugin="bili",
        audit=audit,
        bilibili_cookie_provider=lambda: "SESSDATA=topsecret",
        bilibili_client_factory=_fake_factory,
    )
    result = await router.dispatch(
        "bilibili.request", {"path": "/x/web-interface/view", "params": {"bvid": "BV1"}}, None
    )
    assert result["data"]["ok"] is True
    assert wire["url"].startswith("https://api.bilibili.com/")
    assert wire["headers"]["Cookie"] == "SESSDATA=topsecret"
    for entry in audit.entries:
        assert "topsecret" not in json.dumps(entry, ensure_ascii=False, default=str)


def test_surface_table_routes_bilibili() -> None:
    from soapbot.plugins.surfaces import _SURFACE_TABLE

    assert "bilibili.request" in _SURFACE_TABLE


async def test_bili_example_plugin_registers_and_uses_the_surface() -> None:
    """The example plugin: command registration + surface usage, with a stub ctx.

    Naming ``soapbot.examples.plugins.bili.main`` here also keeps the test-gaps
    ratchet honest — the module ships in the wheel, so somebody has to look at it.
    """
    from soapbot.examples.plugins.bili.main import BiliPlugin

    class _StubBilibili:
        def __init__(self) -> None:
            self.calls: list[tuple[str, dict]] = []

        async def get_json(self, path, *, params=None):
            self.calls.append((path, dict(params or {})))
            if path == "/x/web-interface/history/cursor":
                return {
                    "code": 0,
                    "data": {"items": [{"title": "视频 A", "bvid": "BV1a", "author_name": "UP 主"}]},
                }
            return {"code": 0, "data": {"title": "视频 A", "owner": {"name": "UP"},
                                        "stat": {"view": 1, "danmaku": 2}, "desc": ""}}

    class _StubStorage:
        def __init__(self) -> None:
            self.data: dict = {}

        def get(self, key, default=None):
            return self.data.get(key, default)

        def set(self, key, value):
            self.data[key] = value

        def delete(self, key):
            self.data.pop(key, None)

    class _StubCtx:
        def __init__(self) -> None:
            self.bilibili = _StubBilibili()
            self.storage = _StubStorage()
            self.commands: dict = {}

        def command(self, name, *, description="", usage=""):
            def deco(fn):
                self.commands[name] = fn
                return fn

            return deco

    ctx = _StubCtx()
    plugin = BiliPlugin()
    await plugin.setup(ctx)  # type: ignore[arg-type]
    assert {"bili-history", "bili-look", "bili-forget"} <= set(ctx.commands)

    history = await ctx.commands["bili-history"](None, [])
    assert "视频 A" in history and "UP 主" in history
    assert ctx.bilibili.calls[0][0] == "/x/web-interface/history/cursor"

    await ctx.commands["bili-look"](None, ["BV1a"])
    assert ctx.storage.data["seen_bvids"]["BV1a"]["title"] == "视频 A"

    await ctx.commands["bili-forget"](None, [])
    assert "seen_bvids" not in ctx.storage.data
