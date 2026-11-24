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


# ------------------------------------------------- isolated send scrubbing (S-PLUG-01)


async def test_isolated_send_scrubs_like_the_in_process_path() -> None:
    """Both send paths must apply the same scrub — the weaker one decides.

    ``PluginContext.send`` (in-process) always ran ``scrub_plugin_output``; the
    isolated router forwarded the worker's text verbatim. A plugin in isolated mode —
    the *default* for third-party plugins — could therefore ship bidi overrides,
    markup, or an echoed API key straight into a group.

    This also pins the import: the ceiling lived only in ``context``, so a router that
    guessed the wrong module raised ``ImportError`` on the first send, and nothing in
    the suite exercised it.
    """
    from soapbot.plugins.sandbox import MAX_REPLY_CHARS
    from soapbot.plugins.surfaces import SurfaceRouter

    guard, _ = _guard(Capability.SEND)
    sent: list[str] = []

    async def _sender(session_key: str, text: str) -> None:
        sent.append(text)

    router = SurfaceRouter(
        guard=guard, plugin="p", audit=None, ledger=_LedgerProbe(), sender=_sender
    )
    # A bidi override (RLO) that reverses how the line renders, an echoed key, and
    # enough length to exceed the cap.
    hostile = "\u202eevil" + " api_key=ABCDEF123456" + "x" * (MAX_REPLY_CHARS + 50)
    await router.dispatch(
        "send.message", {"session_key": "a:group:1", "text": hostile}, None
    )
    assert sent, "the scrubbed message was dropped entirely"
    out = sent[0]
    assert "\u202e" not in out, "a bidi override reached the group"
    assert "ABCDEF123456" not in out, "an echoed credential reached the group"
    assert len(out) <= MAX_REPLY_CHARS + 1, "the reply cap did not apply"


async def test_isolated_send_drops_a_message_that_scrubs_to_nothing() -> None:
    """Invisible-only text would still render as a bot line in the group.

    After scrubbing there is nothing left to say, so the send is a no-op rather than
    an empty message.
    """
    from soapbot.plugins.surfaces import SurfaceRouter

    guard, _ = _guard(Capability.SEND)
    sent: list[str] = []

    async def _sender(session_key: str, text: str) -> None:
        sent.append(text)

    router = SurfaceRouter(
        guard=guard, plugin="p", audit=None, ledger=_LedgerProbe(), sender=_sender
    )
    assert await router.dispatch(
        "send.message", {"session_key": "a:group:1", "text": "\u200b\u200b\u200b"}, None
    )
    assert sent == [], "an invisible-only message was still forwarded"


async def test_isolated_media_caption_is_scrubbed_too() -> None:
    """The caption is free text and reaches the same group as the image."""
    from soapbot.plugins.surfaces import SurfaceRouter

    guard, _ = _guard(Capability.SEND_MEDIA)
    delivered: list[tuple[str, str, str]] = []

    async def _media(session_key, b64, caption):
        delivered.append((session_key, b64, caption))

    router = SurfaceRouter(
        guard=guard, plugin="p", audit=None, ledger=_LedgerProbe(), sender_media=_media
    )
    await router.dispatch(
        "send_media.request",
        {
            "session_key": "a:private:1",
            "image_b64": TINY_PNG,
            "caption": "token=SEKRIT-9988776",
        },
        None,
    )
    assert delivered
    assert "SEKRIT-9988776" not in delivered[0][2]
