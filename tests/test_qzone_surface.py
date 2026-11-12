"""QQ 空间 gateway: default-off, split capabilities, explicit write confirmation.

The risk here is account safety, not parsing. A plugin must not be able to turn a
read grant into a post, guess a protocol action that is not allow-listed, publish
without a second human step, or see the endpoint token in any response.
"""

from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

import pytest
from pydantic import SecretStr

from soapbot.plugins.manifest import SENSITIVE_CAPABILITIES, Capability
from soapbot.plugins.sandbox import CapabilityDeniedError, CapabilityGrant, CapabilityGuard
from soapbot.plugins.supervisor import ALLOWED_SURFACES, arg_violation
from soapbot.plugins.surfaces import _SURFACE_TABLE, SurfaceRouter
from soapbot.qzone import QzoneGateway, QzoneUnavailableError

URL = "https://qzone.internal.example/api"
TOKEN = "protocol-token-must-stay-host-side"


def _settings(**kw):
    values = {
        "qzone_via_protocol": True,
        "qzone_api_url": URL,
        "qzone_access_token": SecretStr(TOKEN),
    }
    values.update(kw)
    return SimpleNamespace(**values)


class _Client:
    def __init__(self, *, status: int = 200, body: str = '{"data": []}') -> None:
        self.calls: list[tuple[str, dict, dict]] = []
        self.status = status
        self.body = body

    async def post(self, url, json=None, headers=None):
        self.calls.append((url, dict(json or {}), dict(headers or {})))
        return SimpleNamespace(status_code=self.status, text=self.body)


class _Audit:
    def __init__(self) -> None:
        self.entries: list[dict] = []

    def record(self, **kwargs):
        self.entries.append(kwargs)


def _guard(*caps: Capability):
    entries: list[dict] = []

    class _A:
        def record(self, **kwargs):
            entries.append(kwargs)

    grant = CapabilityGrant(
        plugin="p", declared=frozenset(caps), approved=frozenset(caps)
    )
    return CapabilityGuard(grant, audit=_A()), entries


def _router(caps, *, client=None, settings=None, audit=None):
    guard, _ = _guard(*caps)
    client = client or _Client()
    audit = audit or _Audit()
    gateway = QzoneGateway(settings=settings or _settings(), client=client)
    return SurfaceRouter(guard=guard, plugin="p", audit=audit, qzone=gateway), client, audit


# ------------------------------------------------------------------ default off

async def test_the_gateway_is_off_until_explicitly_enabled() -> None:
    gateway = QzoneGateway(
        settings=_settings(qzone_via_protocol=False), client=_Client()
    )
    assert gateway.enabled() is False
    with pytest.raises(QzoneUnavailableError, match="disabled"):
        await gateway.call("get_friend_feeds", {}, write=False)


async def test_a_disabled_deployment_refuses_the_surface() -> None:
    router, _, _ = _router(
        (Capability.QZONE_READ,), settings=_settings(qzone_via_protocol=False)
    )
    with pytest.raises(QzoneUnavailableError):
        await router.dispatch("qzone.read", {"action": "get_friend_feeds"}, None)


# ------------------------------------------------------------------ action split

async def test_a_read_grant_cannot_call_a_write_action() -> None:
    gateway = QzoneGateway(settings=_settings(), client=_Client())
    with pytest.raises(ValueError, match="not allow-listed"):
        await gateway.call("send_qzone_post", {"text": "hi", "confirm": True}, write=False)


async def test_a_write_grant_cannot_call_a_read_action() -> None:
    gateway = QzoneGateway(settings=_settings(), client=_Client())
    with pytest.raises(ValueError, match="not allow-listed"):
        await gateway.call("get_friend_feeds", {}, write=True)


async def test_an_unknown_protocol_action_is_refused() -> None:
    gateway = QzoneGateway(settings=_settings(), client=_Client())
    with pytest.raises(ValueError, match="not allow-listed"):
        await gateway.call("delete_account", {}, write=False)


# ------------------------------------------------------------------ write gates

async def test_writing_needs_an_explicit_confirm_flag() -> None:
    gateway = QzoneGateway(settings=_settings(), client=_Client())
    with pytest.raises(ValueError, match="confirm"):
        await gateway.call("send_qzone_post", {"text": "hi"}, write=True)


async def test_writing_needs_non_empty_bounded_text() -> None:
    gateway = QzoneGateway(settings=_settings(), client=_Client())
    with pytest.raises(ValueError, match="text"):
        await gateway.call("send_qzone_post", {"text": "", "confirm": True}, write=True)
    with pytest.raises(ValueError, match="text"):
        await gateway.call(
            "send_qzone_post", {"text": "x" * 2001, "confirm": True}, write=True
        )


async def test_a_write_does_not_mutate_the_callers_params() -> None:
    gateway = QzoneGateway(settings=_settings(), client=_Client())
    params = {"text": "hello", "confirm": True}
    await gateway.call("send_qzone_post", params, write=True)
    assert params == {"text": "hello", "confirm": True}


# ------------------------------------------------------------------ capabilities / audit

def test_both_capabilities_are_separate_and_sensitive() -> None:
    assert Capability.QZONE_READ != Capability.QZONE_WRITE
    assert Capability.QZONE_READ in SENSITIVE_CAPABILITIES
    assert Capability.QZONE_WRITE in SENSITIVE_CAPABILITIES


def test_both_surfaces_are_allowlisted_and_routed() -> None:
    for name in ("qzone.read", "qzone.write"):
        assert name in ALLOWED_SURFACES
        assert name in _SURFACE_TABLE
    assert "session_key" in arg_violation(
        "qzone.write", {"params": {}, "session_key": "a:group:1"}
    )


async def test_a_read_only_plugin_cannot_publish() -> None:
    router, _, _ = _router((Capability.QZONE_READ,))
    with pytest.raises(CapabilityDeniedError):
        await router.dispatch(
            "qzone.write",
            {"action": "send_qzone_post", "params": {"text": "hi", "confirm": True}},
            None,
        )


async def test_the_token_is_host_side_and_never_returned() -> None:
    router, client, _ = _router((Capability.QZONE_READ,))
    result = await router.dispatch("qzone.read", {"action": "get_friend_feeds"}, None)
    assert TOKEN not in str(result)
    assert client.calls[0][2]["Authorization"] == f"Bearer {TOKEN}"


async def test_the_audit_records_action_and_length_but_not_the_post_text() -> None:
    router, _, audit = _router((Capability.QZONE_WRITE,))
    result = await router.dispatch(
        "qzone.write",
        {"action": "send_qzone_post", "params": {"text": "SECRET-POST", "confirm": True}},
        None,
    )
    assert result == {"status": 200, "posted": True}
    assert "SECRET-POST" not in str(audit.entries)
    assert TOKEN not in str(audit.entries)
    assert URL not in str(audit.entries)
    assert any("chars=11" in str(e.get("detail")) for e in audit.entries)


async def test_a_non_200_is_reported_without_the_response_body() -> None:
    router, _, _ = _router(
        (Capability.QZONE_READ,), client=_Client(status=500, body="SECRET-POST echoed")
    )
    with pytest.raises(RuntimeError) as exc:
        await router.dispatch("qzone.read", {"action": "get_friend_feeds"}, None)
    assert "SECRET-POST" not in str(exc.value)


# ------------------------------------------------------------------ example plugins

def test_both_example_plugins_declare_only_the_capabilities_they_use() -> None:
    root = Path(__file__).resolve().parents[1] / "src/soapbot/examples/plugins"
    watch = (root / "qzone-watch/plugin.yaml").read_text(encoding="utf-8")
    diary = (root / "qzone-diary/plugin.yaml").read_text(encoding="utf-8")
    assert "qzone_read" in watch and "qzone_write" not in watch
    assert "qzone_write" in diary and "qzone_read" not in diary
    assert (root / "qzone-watch/main.py").is_file()
    assert (root / "qzone-diary/main.py").is_file()
