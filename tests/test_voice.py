"""Voice in and out, with the failure paths as the point.

Three properties are being pinned, and each one maps to a way this feature goes wrong
in production:

* **The audio URL is untrusted.** A member supplies it; the bot fetches it with the
  server's network position. Private, loopback and link-local addresses are refused,
  which is what stops "send a voice message" becoming "read the cloud metadata
  endpoint".
* **A failed transcription never becomes words.** The placeholder is visible to
  everyone; invented text would be attributed to a user who never typed it.
* **A failed synthesis never means silence.** The reply must still arrive, as text.
"""

from __future__ import annotations

import pytest

from soapbot.core.message import (
    MessageReceipt,
    MessageScene,
    MessageSegment,
    OutgoingMessage,
    SegmentType,
)
from soapbot.core.stages import ReplyStage
from soapbot.providers.base import BaseProvider, CapabilitySlot, ProviderConfig, ProviderError
from soapbot.providers.router import ProviderRouter
from soapbot.voice.stt import (
    PLACEHOLDER,
    ProviderTranscriber,
    Transcription,
    VoiceError,
    check_audio_url,
    render_prompt,
)
from soapbot.voice.tts import EdgeTts, VoiceUnavailableError

# ------------------------------------------------------------------ url safety


@pytest.mark.parametrize(
    "url",
    [
        "http://127.0.0.1/x.amr",
        "http://localhost/x.amr",
        "http://169.254.169.254/latest/meta-data/",
        "http://10.0.0.5/x.amr",
        "http://192.168.1.1/x.amr",
        "http://[::1]/x.amr",
    ],
)
def test_private_targets_are_refused(url: str) -> None:
    with pytest.raises(VoiceError):
        check_audio_url(url)


@pytest.mark.parametrize("url", ["file:///etc/passwd", "ftp://example.com/a", "//x/y", ""])
def test_non_http_schemes_are_refused(url: str) -> None:
    with pytest.raises(VoiceError):
        check_audio_url(url)


def test_a_public_address_is_allowed() -> None:
    # A literal public IP: no DNS needed, so this does not depend on the network.
    assert check_audio_url("https://8.8.8.8/a.amr") == "https://8.8.8.8/a.amr"


# ------------------------------------------------------------- transcription


class _FakeRouter:
    def __init__(self, *, text: str = "", error: Exception | None = None) -> None:
        self.text = text
        self.error = error
        self.calls: list[tuple[int, str]] = []

    async def transcribe(self, audio: bytes, *, mime: str = "", language: str = "") -> str:
        self.calls.append((len(audio), mime))
        if self.error is not None:
            raise self.error
        return self.text


def _record(url: str = "https://8.8.8.8/a.amr") -> MessageSegment:
    return MessageSegment(SegmentType.RECORD, {"url": url, "file": "a.amr"})


async def _fetch_ok(url: str, *, max_bytes: int) -> tuple[bytes, str]:
    return b"audio-bytes", "audio/amr"


async def test_transcription_success_is_labelled_as_speech() -> None:
    transcriber = ProviderTranscriber(_FakeRouter(text="今天下午三点开会"), fetcher=_fetch_ok)
    result = await transcriber.transcribe_segment(_record())

    assert result.ok and result.text == "今天下午三点开会"
    # Labelled, so the model does not answer "as you wrote" about spoken words.
    assert render_prompt(result).startswith("[语音转写]")


async def test_a_refused_url_degrades_to_the_placeholder() -> None:
    async def _refuse(url: str, *, max_bytes: int) -> tuple[bytes, str]:
        raise VoiceError("resolves to a non-public address")

    transcriber = ProviderTranscriber(_FakeRouter(text="never"), fetcher=_refuse)
    result = await transcriber.transcribe_segment(_record("http://169.254.169.254/x"))

    assert not result.ok
    assert result.reason.startswith("fetch:")
    assert render_prompt(result) == PLACEHOLDER


async def test_a_provider_failure_never_yields_invented_text() -> None:
    transcriber = ProviderTranscriber(
        _FakeRouter(error=ProviderError("upstream 500")), fetcher=_fetch_ok
    )
    result = await transcriber.transcribe_segment(_record())

    assert not result.ok
    # Type only: the provider message can echo the request body, and the audio is
    # private.
    assert result.reason == "provider:ProviderError"
    assert result.text == ""
    assert render_prompt(result) == PLACEHOLDER


async def test_a_segment_without_audio_is_reported_not_fetched() -> None:
    transcriber = ProviderTranscriber(_FakeRouter(text="x"), fetcher=_fetch_ok)
    result = await transcriber.transcribe_segment(
        MessageSegment(SegmentType.RECORD, {})
    )
    assert not result.ok and result.reason == "no_audio_url"


# -------------------------------------------------------------------- router


class _DeclaringProvider(BaseProvider):
    kind = "fake"
    slots = frozenset({CapabilitySlot.CHAT, CapabilitySlot.TRANSCRIBE})

    def __init__(self, config: ProviderConfig, *, fail: bool = False) -> None:
        super().__init__(config)
        self.fail = fail
        self.seen: list[str] = []

    async def chat(self, request):  # pragma: no cover - unused
        raise ProviderError("no chat here")

    async def transcribe(self, audio: bytes, *, mime="", language="") -> str:
        self.seen.append(mime)
        if self.fail:
            raise ProviderError("boom")
        return "transcribed"


class _ChatOnlyProvider(BaseProvider):
    kind = "chatonly"

    async def chat(self, request):  # pragma: no cover - unused
        raise ProviderError("no chat here")


def _cfg(pid: str, **kw) -> ProviderConfig:
    return ProviderConfig(id=pid, kind="fake", model="m", **kw)


def _router_with(*providers: BaseProvider) -> ProviderRouter:
    router = ProviderRouter(cooldown_seconds=0.0)
    for provider in providers:
        router.add(provider)
    return router


async def test_router_only_tries_providers_that_declared_the_slot() -> None:
    chat_only = _ChatOnlyProvider(_cfg("chat"))
    speaker = _DeclaringProvider(_cfg("sp"))
    router = _router_with(chat_only, speaker)

    assert await router.transcribe(b"a", mime="audio/amr") == "transcribed"
    # The chat-only provider was never asked, so it never had to fail.
    assert speaker.seen == ["audio/amr"]


async def test_router_fails_over_and_then_reports() -> None:
    bad = _DeclaringProvider(_cfg("bad", priority=0), fail=True)
    good = _DeclaringProvider(_cfg("good", priority=1))
    router = _router_with(bad, good)
    assert await router.transcribe(b"a") == "transcribed"

    only_bad = _router_with(_DeclaringProvider(_cfg("bad"), fail=True))
    with pytest.raises(ProviderError):
        await only_bad.transcribe(b"a")


async def test_router_without_the_slot_refuses_rather_than_guessing() -> None:
    router = _router_with(_ChatOnlyProvider(_cfg("chat")))
    with pytest.raises(ProviderError, match="transcription"):
        await router.transcribe(b"a")


# ----------------------------------------------------------------------- tts


async def test_missing_optional_dependency_is_actionable() -> None:
    engine = EdgeTts()
    try:
        await engine.synthesize("你好")
    except VoiceUnavailableError as exc:
        # Either not installed (the common case) or installed and the call failed;
        # both must be a VoiceUnavailableError, never a bare ImportError or a hang.
        assert "edge-tts" in str(exc) or "synthesis" in str(exc)
    else:  # pragma: no cover - only if the extra is installed and the vendor answered
        pytest.skip("edge-tts produced audio; dependency-installed path not exercised")


async def test_long_replies_stay_text() -> None:
    engine = EdgeTts(max_chars=5)
    with pytest.raises(VoiceUnavailableError, match="too long"):
        await engine.synthesize("这一句明显超过了五个字")


# ------------------------------------------------------------------ reply path


class _Adapter:
    def __init__(self, *, record: bool = True, fail_voice: bool = False) -> None:
        self._record = record
        self._fail_voice = fail_voice
        self.sent: list[list[MessageSegment]] = []
        self.meta = type("M", (), {"name": "fake"})()

    def supports_segment(self, seg_type) -> bool:
        return seg_type is not SegmentType.RECORD or self._record

    async def send(self, out: OutgoingMessage) -> MessageReceipt:
        self.sent.append(list(out.segments))
        if self._fail_voice and any(s.type is SegmentType.RECORD for s in out.segments):
            return MessageReceipt(ok=False, error="record not allowed")
        return MessageReceipt(ok=True, message_id="1")


class _Ctx:
    def __init__(self, adapter: _Adapter, reply: str = "你好呀") -> None:
        self.adapter = adapter
        self.model_reply = reply
        self.extras: dict = {}
        self.outbound = OutgoingMessage(
            scene=MessageScene.GROUP, segments=[], group_id="1"
        )


class _OkTts:
    async def synthesize(self, text: str) -> str:
        return "QUJD"


class _BrokenTts:
    async def synthesize(self, text: str) -> str:
        raise VoiceUnavailableError("edge-tts is not installed")


async def test_voice_reply_uses_a_record_segment_when_supported() -> None:
    adapter = _Adapter(record=True)
    ctx = _Ctx(adapter)
    await ReplyStage(tts=_OkTts()).run(ctx)

    assert adapter.sent[0][0].type is SegmentType.RECORD
    assert ctx.extras["send_ok"] is True
    assert ctx.extras["voice_reply"] == "voice"


async def test_adapter_without_record_support_never_pays_for_audio() -> None:
    adapter = _Adapter(record=False)
    ctx = _Ctx(adapter)
    await ReplyStage(tts=_OkTts()).run(ctx)

    assert adapter.sent[0][0].type is SegmentType.TEXT
    # Not even attempted: the segment would have been dropped by the channel.
    assert "voice_reply" not in ctx.extras


async def test_unavailable_tts_falls_back_to_text() -> None:
    adapter = _Adapter(record=True)
    ctx = _Ctx(adapter)
    await ReplyStage(tts=_BrokenTts()).run(ctx)

    assert adapter.sent[0][0].type is SegmentType.TEXT
    assert ctx.extras["voice_reply"].startswith("text:")


async def test_a_failed_voice_send_is_retried_as_text() -> None:
    """Otherwise the group receives nothing at all, which reads as the bot dying."""
    adapter = _Adapter(record=True, fail_voice=True)
    ctx = _Ctx(adapter)
    await ReplyStage(tts=_OkTts()).run(ctx)

    assert len(adapter.sent) == 2
    assert adapter.sent[0][0].type is SegmentType.RECORD
    assert adapter.sent[1][0].type is SegmentType.TEXT
    assert ctx.extras["send_ok"] is True
    assert ctx.extras["voice_reply"] == "text:send_failed"


def test_transcription_display_is_never_empty() -> None:
    assert Transcription("", False, "x").display == PLACEHOLDER
    assert Transcription("hi", True).display == "hi"
