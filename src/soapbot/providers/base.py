"""Provider contract.

Five capability slots: ``chat`` / ``stream`` / ``vision`` / ``embed`` / ``transcribe``.
A provider declares which slots it actually implements; the router picks a
provider that satisfies the request rather than assuming every provider can do
everything (Ollama cannot embed images, many relay endpoints cannot stream).

We talk to vendor REST endpoints directly with httpx instead of binding to heavy
SDKs: fewer transitive dependencies, and the OpenAI-compatible surface alone
covers DeepSeek / Qwen / Moonshot / most relay services.
"""

from __future__ import annotations

import asyncio
import logging
import random
from abc import ABC, abstractmethod
from collections.abc import AsyncIterator, Awaitable, Callable
from dataclasses import dataclass, field
from enum import StrEnum
from typing import Any, TypeVar

import httpx

from soapbot.net import build_timeout, outbound_client

logger = logging.getLogger(__name__)

T = TypeVar("T")

#: Status codes worth trying again.
#:
#: The list is short on purpose. Retrying a 400 means re-sending a malformed request
#: the server has already rejected — three round trips to learn what the first one
#: said. Retrying a 401 means hammering with a key that is wrong, which some vendors
#: treat as credential stuffing. What *is* worth retrying is the transient set:
#: timeouts (408), rate limits (429), and the 5xx family that means "not now".
RETRYABLE_STATUS = frozenset({408, 409, 425, 429, 500, 502, 503, 504})


class ProviderError(RuntimeError):
    """Raised for any provider failure that should trigger failover.

    ``retry_after`` carries the server's own hint (``Retry-After``) when it sent one.
    It lives on the exception because the response object does not survive the raise:
    providers translate every failure into this type, so by the time the retry policy
    sees the error the headers are gone. Passing the value along is what makes the
    hint reachable at all — reading it from ``exc.response`` never worked, since this
    class has no such attribute.
    """

    def __init__(
        self,
        message: str,
        *,
        status: int | None = None,
        retry_after: float | None = None,
    ) -> None:
        super().__init__(message)
        self.status = status
        self.retry_after = retry_after


def is_retryable_status(status: int) -> bool:
    return status in RETRYABLE_STATUS


def is_retryable_exception(exc: BaseException) -> bool:
    """Whether the same request, sent again, has a chance of succeeding.

    ``ConnectError`` and ``ReadTimeout`` are transient by nature. ``InvalidURL`` and
    ``UnsupportedProtocol`` are configuration mistakes that will fail identically every
    time, so retrying them only delays the failover that would actually help.
    """
    if isinstance(exc, ProviderError):
        return exc.status is not None and is_retryable_status(exc.status)
    if isinstance(exc, httpx.HTTPStatusError):
        return is_retryable_status(exc.response.status_code)
    return isinstance(
        exc,
        httpx.ConnectError
        | httpx.ConnectTimeout
        | httpx.ReadTimeout
        | httpx.WriteTimeout
        | httpx.PoolTimeout
        | httpx.RemoteProtocolError
        | httpx.ReadError,
    )


def retry_after_of(response: Any) -> float | None:
    """Parse ``Retry-After`` off a response, if it carries a usable one.

    Only the delta-seconds form is honoured. The HTTP-date form is legal but rare, and
    parsing it would mean trusting the server's clock against ours; falling back to
    plain backoff is safer than sleeping for a duration derived from a skewed date.
    """
    headers = getattr(response, "headers", None)
    if headers is None:
        return None
    raw = headers.get("retry-after", "")
    if not raw:
        return None
    try:
        return max(0.0, float(raw))
    except ValueError:
        return None  # HTTP-date form; not worth parsing for a retry hint


def _retry_after_seconds(exc: BaseException) -> float | None:
    """Honour ``Retry-After`` when the server bothered to send one.

    A 429 that says "come back in 20 seconds" is information. Ignoring it and retrying
    after 0.5 s spends the retry budget on a request that is guaranteed to fail again.

    Two sources, because two kinds of exception reach here. ``ProviderError`` carries
    the hint as an attribute (providers attach it when they translate the response);
    ``httpx.HTTPStatusError`` still has the response itself. Reading only the latter
    meant the hint was never seen in practice — every provider raises the former.
    """
    hinted = getattr(exc, "retry_after", None)
    if isinstance(hinted, int | float):
        return max(0.0, float(hinted))
    return retry_after_of(getattr(exc, "response", None))


async def retry_async(
    operation: Callable[[], Awaitable[T]],
    *,
    attempts: int,
    what: str,
    base_delay: float = 0.5,
    max_delay: float = 8.0,
) -> T:
    """Run ``operation``, retrying only failures that could plausibly clear.

    Backoff is exponential with full jitter. Without jitter, every instance that failed
    at the same moment retries at the same moment, which turns a provider blip into a
    synchronised thundering herd — the retry storm is worse than the outage.
    """
    last: BaseException | None = None
    for attempt in range(max(1, attempts)):
        try:
            return await operation()
        except BaseException as exc:
            if isinstance(exc, asyncio.CancelledError):
                raise
            last = exc
            if not is_retryable_exception(exc) or attempt == attempts - 1:
                raise
            hinted = _retry_after_seconds(exc)
            if hinted is not None:
                delay = min(hinted, max_delay)
            else:
                delay = min(max_delay, base_delay * (2**attempt))
                delay = random.uniform(0, delay)
            logger.warning(
                "%s attempt %s/%s failed (%s); retrying in %.2fs",
                what,
                attempt + 1,
                attempts,
                exc,
                delay,
            )
            await asyncio.sleep(delay)
    raise ProviderError(f"{what} failed after {attempts} attempts: {last}")


class CapabilitySlot(StrEnum):
    CHAT = "chat"
    STREAM = "stream"
    VISION = "vision"
    EMBED = "embed"
    TRANSCRIBE = "transcribe"


@dataclass(slots=True)
class ChatMessage:
    role: str
    content: str | list[dict[str, Any]]
    """String for text, or an OpenAI-style parts list for vision."""

    name: str = ""
    tool_call_id: str = ""

    def to_openai(self) -> dict[str, Any]:
        payload: dict[str, Any] = {"role": self.role, "content": self.content}
        if self.name:
            payload["name"] = self.name
        if self.tool_call_id:
            payload["tool_call_id"] = self.tool_call_id
        return payload

    def text(self) -> str:
        if isinstance(self.content, str):
            return self.content
        parts = [
            str(p.get("text", ""))
            for p in self.content
            if isinstance(p, dict) and p.get("type") == "text"
        ]
        return "".join(parts)


@dataclass(slots=True)
class ChatRequest:
    messages: list[ChatMessage]
    model: str = ""
    temperature: float = 0.8
    max_tokens: int = 1024
    tools: list[dict[str, Any]] = field(default_factory=list)
    extra: dict[str, Any] = field(default_factory=dict)


@dataclass(slots=True)
class ChatResponse:
    content: str
    model: str = ""
    prompt_tokens: int = 0
    completion_tokens: int = 0
    tool_calls: list[dict[str, Any]] = field(default_factory=list)
    finish_reason: str = ""
    provider: str = ""
    raw: dict[str, Any] = field(default_factory=dict)


@dataclass(slots=True)
class ProviderConfig:
    """Runtime configuration for one provider instance."""

    id: str
    kind: str
    label: str = ""
    base_url: str = ""
    api_key: str = ""
    model: str = ""
    embed_model: str = ""
    vision_model: str = ""
    timeout: float = 60.0
    max_retries: int = 2
    priority: int = 100
    """Lower number is tried first in the fallback chain."""

    enabled: bool = True
    extra: dict[str, Any] = field(default_factory=dict)


class BaseProvider(ABC):
    kind: str = "base"
    slots: frozenset[CapabilitySlot] = frozenset({CapabilitySlot.CHAT})

    def __init__(self, config: ProviderConfig) -> None:
        self.config = config

    # ---- outbound plumbing ----
    #
    # Every provider used to open its own ``httpx.AsyncClient`` per call, which meant a
    # fresh TCP and TLS handshake per completion and no session reuse. These helpers
    # put all providers on the one pooled client in ``soapbot.net``.

    def _timeout(self) -> httpx.Timeout:
        """Layered timeout using this provider's own read budget."""
        return build_timeout(self.config.timeout)

    async def _request(
        self,
        method: str,
        url: str,
        *,
        client: httpx.AsyncClient | None = None,
        **kwargs: Any,
    ) -> httpx.Response:
        """One request on the shared client. Never closes the client."""
        async with outbound_client(client=client) as http:
            return await http.request(method, url, timeout=self._timeout(), **kwargs)

    async def _with_retry(
        self,
        operation: Callable[[], Awaitable[T]],
        *,
        what: str,
    ) -> T:
        return await retry_async(
            operation,
            attempts=self.config.max_retries + 1,
            what=f"{self.kind}:{self.id} {what}",
        )

    @property
    def id(self) -> str:
        return self.config.id

    def supports(self, slot: CapabilitySlot) -> bool:
        return slot in self.slots

    @abstractmethod
    async def chat(self, request: ChatRequest) -> ChatResponse:
        """Non-streaming completion."""

    async def stream(self, request: ChatRequest) -> AsyncIterator[str]:
        """Yield the answer as it is produced. Default: one chunk, from ``chat``.

        Deliberately *not* abstract. A provider that cannot stream should still work,
        and the fallback belongs in the contract: as a merely-missing method it
        surfaced as ``AttributeError`` at call time, which the caller could not tell
        apart from a genuine provider failure, so it failed over to another provider
        that lacked the same method. Declaring ``STREAM`` and not implementing it is
        no longer expressible.
        """
        resp = await self.chat(request)
        yield resp.content

    async def vision(self, request: ChatRequest) -> ChatResponse:
        """Image understanding. Defaults to chat (multimodal endpoints accept parts)."""
        return await self.chat(request)

    async def embed(self, texts: list[str]) -> list[list[float]]:
        raise ProviderError(f"{self.kind} does not implement embed")

    async def transcribe(
        self, audio: bytes, *, mime: str = "audio/silk", language: str = ""
    ) -> str:
        """Speech to text. Default: refuse, explicitly.

        ``stream`` could get an honest default because a non-streaming call still
        produces the same answer. There is no such fallback here: a chat call cannot
        turn audio into words. A placeholder would put invented words into the
        conversation, attributed to a user who never typed them — worse than admitting
        the gap. The caller degrades to ``[语音]``, which is visible to everyone.
        """
        raise ProviderError(f"{self.kind} does not implement transcribe")

    def describe(self) -> dict[str, Any]:
        return {
            "id": self.config.id,
            "kind": self.kind,
            "label": self.config.label or self.config.id,
            "model": self.config.model,
            "slots": sorted(str(s) for s in self.slots),
            "enabled": self.config.enabled,
            "priority": self.config.priority,
        }
