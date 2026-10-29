"""Inbound speech: a voice message becomes text before the model sees it.

Two decisions shape this module.

**The audio URL is attacker-controlled.** A group member sends a voice message and the
protocol hands us a URL to fetch — with the bot's network position. Left unchecked,
"send a voice message" becomes "make the server fetch http://169.254.169.254/…", i.e.
cloud metadata theft from inside the perimeter. So the URL is parsed, its host is
resolved, and any private, loopback, link-local or reserved address is refused. This is
the same class of mistake as the plugin upload path: treat a peer-supplied reference as
untrusted input, not as a location.

**Failure must be visible, never invented.** If transcription is unavailable the
segment becomes ``[语音]``. Substituting a guess would attribute invented words to a
user who never typed them, which is worse than a gap every participant can see.
"""

from __future__ import annotations

import ipaddress
import logging
import socket
from dataclasses import dataclass
from typing import Any, Protocol
from urllib.parse import urlparse

import httpx

logger = logging.getLogger(__name__)

#: Voice notes are short; anything larger is a mistake or an attempt to make the bot
#: buffer arbitrary data before spending a provider call on it.
DEFAULT_MAX_BYTES = 8 * 1024 * 1024

#: What an untranscribed voice message looks like to everyone downstream.
PLACEHOLDER = "[语音]"


class VoiceError(RuntimeError):
    """Transcription could not be performed. Always degradable, never fatal."""


@dataclass(slots=True)
class Transcription:
    text: str
    ok: bool
    reason: str = ""

    @property
    def display(self) -> str:
        """What to put in the conversation when this is all we have."""
        return self.text if self.ok and self.text else PLACEHOLDER


class AudioFetcher(Protocol):
    async def __call__(self, url: str, *, max_bytes: int) -> tuple[bytes, str]: ...


def _address_is_public(host: str) -> bool:
    """False for anything that could reach the host's own network.

    ``is_global`` covers loopback, private, link-local (169.254.169.254), reserved and
    multicast in one predicate. Names are resolved first: checking the literal string
    alone would let ``localhost`` or a DNS name pointing inward through.
    """
    try:
        infos = socket.getaddrinfo(host, None)
    except OSError:
        return False
    for info in infos:
        raw = info[4][0]
        try:
            addr = ipaddress.ip_address(raw)
        except ValueError:
            return False
        if not addr.is_global:
            return False
    return True


def check_audio_url(url: str) -> str:
    """Return the URL if it is fetchable, else raise :class:`VoiceError`.

    Deliberately strict: only http/https, only public addresses.
    """
    parsed = urlparse(url or "")
    if parsed.scheme not in {"http", "https"}:
        raise VoiceError(f"refusing non-http audio url: {parsed.scheme or '(none)'}")
    host = parsed.hostname or ""
    if not host:
        raise VoiceError("refusing audio url without a host")
    if not _address_is_public(host):
        # Named, not censored: the operator needs to know an attempt happened, and the
        # member's client already knows the URL it sent.
        raise VoiceError(f"refusing audio url resolving to a non-public address: {host}")
    return url


async def http_fetch(url: str, *, max_bytes: int = DEFAULT_MAX_BYTES) -> tuple[bytes, str]:
    """Download with a hard size cap applied while reading, not after."""
    check_audio_url(url)
    async with (
        httpx.AsyncClient(timeout=15.0, follow_redirects=False) as client,
        client.stream("GET", url) as response,
    ):
        if response.status_code != 200:
            raise VoiceError(f"audio fetch failed: HTTP {response.status_code}")
        # A redirect would let a public URL bounce to a private one after the check
        # above has already passed, so redirects are not followed at all.
        declared = int(response.headers.get("content-length") or 0)
        if declared > max_bytes:
            raise VoiceError(f"audio too large: {declared} bytes")
        chunks: list[bytes] = []
        total = 0
        async for chunk in response.aiter_bytes():
            total += len(chunk)
            if total > max_bytes:
                raise VoiceError(f"audio exceeded {max_bytes} bytes while reading")
            chunks.append(chunk)
        mime = response.headers.get("content-type", "audio/silk").split(";")[0]
        return b"".join(chunks), mime


class ProviderTranscriber:
    """Transcribe a RECORD segment through whichever provider offers the slot."""

    def __init__(
        self,
        router: Any,
        *,
        fetcher: AudioFetcher = http_fetch,
        max_bytes: int = DEFAULT_MAX_BYTES,
        language: str = "zh",
    ) -> None:
        self._router = router
        self._fetcher = fetcher
        self._max_bytes = max_bytes
        self._language = language

    async def transcribe_segment(self, segment: Any) -> Transcription:
        """Never raises: a voice message must not take the pipeline down."""
        data = getattr(segment, "data", None) or {}
        url = str(data.get("url") or data.get("file") or "")
        if not url:
            return Transcription("", False, "no_audio_url")

        try:
            audio, mime = await self._fetcher(url, max_bytes=self._max_bytes)
        except VoiceError as exc:
            logger.warning("voice fetch refused: %s", exc)
            return Transcription("", False, f"fetch:{exc}")
        except Exception as exc:  # network, DNS, TLS
            logger.warning("voice fetch failed: %s", exc)
            return Transcription("", False, f"fetch:{type(exc).__name__}")

        if not audio:
            return Transcription("", False, "empty_audio")

        try:
            text = await self._router.transcribe(
                audio, mime=mime, language=self._language
            )
        except Exception as exc:
            # The message is not surfaced: provider errors can echo request bodies,
            # and the audio is private. Type only, as elsewhere in this codebase.
            logger.warning("transcription failed: %s", type(exc).__name__)
            return Transcription("", False, f"provider:{type(exc).__name__}")

        cleaned = " ".join(str(text or "").split())
        if not cleaned:
            return Transcription("", False, "empty_transcript")
        return Transcription(cleaned, True)


def render_prompt(transcription: Transcription) -> str:
    """Wrap transcribed speech so the model can tell it from typed text.

    The label matters: without it the model treats a spoken sentence as if the user had
    typed it, and will happily answer "as you wrote" about words nobody wrote.
    """
    if transcription.ok and transcription.text:
        return f"[语音转写] {transcription.text}"
    return PLACEHOLDER
