"""Outbound speech: a text reply may be delivered as a voice message.

``edge-tts`` is an **optional** dependency (``pip install soapbot[voice]``) because it
is a network client for one vendor, and making it mandatory would put a service
integration in the path of every install that will never speak.

The rule this module exists to enforce: a missing optional dependency must produce a
clear, actionable error, never silence and never a half-sent message. ``ReplyStage``
catches :class:`VoiceUnavailableError` and sends the text instead — which is what the group
would have received anyway, so the degradation is invisible but the log is not.
"""

from __future__ import annotations

import base64
import logging
from typing import Protocol

logger = logging.getLogger(__name__)

#: Speech is slower than reading. Long replies become a minute of audio nobody asked
#: for, so they stay text; the cap is deliberately low.
DEFAULT_MAX_CHARS = 200


class VoiceUnavailableError(RuntimeError):
    """Speech synthesis is not configured or not installed. Always degradable.

    ``code`` separates "this reply is not a good fit" from "speech is broken", because
    the caller logs them differently: a long reply falling back to text is normal and
    happens constantly, while a failed synthesis is worth a warning. Without the
    distinction every long answer produced an INFO line, which trains operators to
    ignore the channel that reports the real failures.
    """

    def __init__(self, message: str, *, code: str = "failed") -> None:
        super().__init__(message)
        self.code = code


class TtsEngine(Protocol):
    async def synthesize(self, text: str) -> str: ...


class EdgeTts:
    """``edge-tts`` wrapper. Imported lazily so the dependency stays optional."""

    def __init__(
        self,
        voice: str = "zh-CN-XiaoxiaoNeural",
        *,
        max_chars: int = DEFAULT_MAX_CHARS,
        rate: str = "+0%",
    ) -> None:
        self.voice = voice
        self.max_chars = max_chars
        self.rate = rate

    async def synthesize(self, text: str) -> str:
        """Return base64 audio, ready for :meth:`MessageSegment.record`.

        Base64 rather than bytes keeps the value JSON-serialisable end to end: it
        travels through the trace record and the adapter frame, and a ``bytes`` object
        in either would fail at serialisation time — after the user has waited.
        """
        cleaned = " ".join(str(text or "").split())
        if not cleaned:
            raise VoiceUnavailableError("empty text", code="empty")
        if len(cleaned) > self.max_chars:
            # Not an error: the caller's fallback is the full text, which is the
            # better answer for a long reply anyway.
            raise VoiceUnavailableError(
                f"text too long for voice: {len(cleaned)} chars", code="too_long"
            )

        try:
            import edge_tts
        except ImportError as exc:
            raise VoiceUnavailableError(
                "edge-tts is not installed; install the extra: pip install 'soapbot[voice]'",
                code="not_installed",
            ) from exc

        try:
            communicate = edge_tts.Communicate(cleaned, self.voice, rate=self.rate)
            chunks: list[bytes] = []
            async for chunk in communicate.stream():
                if chunk.get("type") == "audio" and chunk.get("data"):
                    chunks.append(chunk["data"])
        except Exception as exc:
            # Network or vendor failure. Type only: the text is user content and may
            # contain anything, and the vendor message can echo the request.
            raise VoiceUnavailableError(f"synthesis failed: {type(exc).__name__}") from exc

        audio = b"".join(chunks)
        if not audio:
            raise VoiceUnavailableError("synthesis produced no audio")
        return base64.b64encode(audio).decode("ascii")
