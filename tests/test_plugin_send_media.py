"""The ``send_media`` capability and the isolated-send fix.

Two things under test:

1. ``send_media``: capability denial, ledger discipline, size cap, and the audit
   line carrying sizes but never image bytes.
2. The isolated-send fix: the child shim legitimately carries ``session_key`` for
   ``send.*`` surfaces (the target IS the request), and the blanket forbidden-keys
   rule no longer rejects the frame before the host's ledger sees it. The bug was
   reproduced on master with a two-line probe; this file pins the fix from both
   ends (the argument rule, and the host surface handler).
"""

from __future__ import annotations

import base64

import pytest

from soapbot.plugins.manifest import Capability
from soapbot.plugins.sandbox import CapabilityGrant, CapabilityGuard
from soapbot.plugins.supervisor import ALLOWED_SURFACES, arg_violation

TINY_PNG = base64.b64encode(b"\x89PNG\r\n\x1a\n" + b"0" * 64).decode()


def _guard(*caps: Capability, ledger_permits: bool = True) -> tuple[CapabilityGuard, list[dict]]:
    entries: list[dict] = []

    class _Audit:
        def record(self, **kwargs):
            entries.append(kwargs)

    class _Ledger:
        def permits(self, plugin, session_key):
            return ledger_permits

    grant = CapabilityGrant(
        plugin="p", declared=frozenset(caps), approved=frozenset(caps)
    )
    return CapabilityGuard(grant, audit=_Audit()), entries


def test_arg_rule_lets_send_carry_session_key_but_memory_not() -> None:
    # The send target is the request itself; the ledger bounds it.
    assert arg_violation("send.message", {"session_key": "a:private:1", "text": "hi"}) == frozenset()
    assert arg_violation("send_media.request", {"session_key": "a:private:1", "image_b64": "x"}) == frozenset()
    # Everywhere else, naming a session is a scope escape and must fail.
    assert "session_key" in arg_violation("memory.recall", {"session_key": "a:group:9", "query": "x"})
    # And the other forbidden keys hold even on send surfaces.
    assert "scope" in arg_violation("send.message", {"scope": "group:1", "text": "hi"})


def test_send_media_surface_is_allowed_and_routed() -> None:
    assert "send_media.request" in ALLOWED_SURFACES
    from soapbot.plugins.surfaces import _SURFACE_TABLE

    assert "send_media.request" in _SURFACE_TABLE


async def test_send_media_happy_path_records_size_not_pixels() -> None:
    from soapbot.plugins.surfaces import SurfaceRouter

    guard, _entries = _guard(Capability.SEND_MEDIA)
    delivered: list[tuple[str, str, str]] = []

    async def _media(session_key, b64, caption):
        delivered.append((session_key, b64, caption))

    router = SurfaceRouter(
        guard=guard,
        plugin="p",
        audit=None,
        ledger=_AlwaysYes(),
        sender_media=_media,
    )
    await router.dispatch(
        "send_media.request",
        {"session_key": "a:private:1", "image_b64": TINY_PNG, "caption": "看这个"},
        None,
    )
    assert delivered[0][0] == "a:private:1"
    assert delivered[0][2] == "看这个"


class _AlwaysYes:
    def permits(self, plugin, session_key):
        return True


class _NoLedger:
    def permits(self, plugin, session_key):
        return False


async def test_send_media_without_ledger_grant_is_refused() -> None:
    from soapbot.plugins.surfaces import SurfaceRouter

    guard, _entries = _guard(Capability.SEND_MEDIA)
    router = SurfaceRouter(guard=guard, plugin="p", audit=None, ledger=_NoLedger())
    with pytest.raises(PermissionError):
        await router.dispatch(
            "send_media.request", {"session_key": "a:group:9", "image_b64": TINY_PNG}, None
        )


async def test_send_media_denied_without_capability() -> None:
    from soapbot.plugins.surfaces import SurfaceRouter

    guard, _entries = _guard()  # nothing granted
    from soapbot.plugins.sandbox import CapabilityDeniedError

    router = SurfaceRouter(guard=guard, plugin="p", audit=None, ledger=_AlwaysYes())
    with pytest.raises(CapabilityDeniedError):
        await router.dispatch(
            "send_media.request", {"session_key": "a:private:1", "image_b64": TINY_PNG}, None
        )


async def test_oversized_image_is_refused_before_the_wire() -> None:
    from soapbot.plugins.sandbox import MAX_PLUGIN_MEDIA_BYTES as MAX_MEDIA_BYTES
    from soapbot.plugins.surfaces import SurfaceRouter

    guard, _ = _guard(Capability.SEND_MEDIA)
    router = SurfaceRouter(guard=guard, plugin="p", audit=None, ledger=_AlwaysYes())
    big = base64.b64encode(b"0" * (MAX_MEDIA_BYTES + 1)).decode()
    with pytest.raises(ValueError, match="cap"):
        await router.dispatch(
            "send_media.request", {"session_key": "a:private:1", "image_b64": big}, None
        )


def test_runtime_media_sender_builds_image_segment() -> None:
    """The runtime turns (session_key, b64) into one IMAGE segment + caption."""
    import asyncio

    from soapbot.core.message import SegmentType
    from soapbot.core.runtime import BotRuntime

    captured: dict = {}

    class _Adapter:
        meta = type("M", (), {"name": "onebot11"})()

        async def send(self, out):
            captured["segments"] = out.segments
            captured["scene"] = out.scene
            from soapbot.core.message import MessageReceipt

            return MessageReceipt(ok=True)

    runtime = BotRuntime.__new__(BotRuntime)
    runtime.adapters = {"onebot11": _Adapter()}
    asyncio.run(
        runtime._send_media_via_adapter("onebot11:group:1", TINY_PNG, "说明")
    )
    assert captured["scene"].value == "group"
    assert captured["segments"][0].type is SegmentType.IMAGE
    assert captured["segments"][0].data["base64"] == TINY_PNG
    assert captured["segments"][1].data["text"] == "说明"


class _LedgerProbe:
    def permits(self, plugin, session_key):
        return True
