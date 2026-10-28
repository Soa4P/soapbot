"""QQ official bot adapter — group + private (C2C) only.

Scope decisions (frozen by the user):
- **No guild / channel support.** ``Guild`` intents are never requested and no
  child-channel API is implemented. ``MessageScene.CHANNEL`` does not exist.
- ``qq-botpy`` is an *optional* dependency and is imported lazily inside
  ``start()`` so its dormant maintenance cannot break the core import graph.

Platform limits encoded here (from QQ open platform docs):
- proactive push: 20 messages per group per day
- passive reply window: 5 minutes after the user message
- per-group rate: 5 messages / second

These are surfaced through ``quota_hint`` so the limiter can queue rather than
fail. Enforcement lives in ``soapbot.core.ratelimit``.
"""

from __future__ import annotations

import asyncio
import contextlib
import logging
import re
import time
from typing import Any

from soapbot.core.adapter import Adapter, AdapterMeta, Capability
from soapbot.core.message import (
    EventType,
    IncomingMessage,
    MessageReceipt,
    MessageScene,
    MessageSegment,
    OutgoingMessage,
    SegmentType,
    Sender,
)

logger = logging.getLogger(__name__)

_CAPABILITIES = frozenset(
    {
        Capability.TEXT,
        Capability.IMAGE,
        Capability.AT,
        Capability.REPLY,
        Capability.RECORD,
        Capability.FILE,
    }
)
"""No MARKDOWN (falls back to plain text), no FORWARD, no MUTE/KICK/RECALL."""

PASSIVE_WINDOW_SECONDS = 300
"""Official passive reply window. Replies later than this need proactive quota."""

DAILY_PROACTIVE_PER_GROUP = 20
PER_GROUP_QPS = 5


class QQOfficialAdapter(Adapter):
    meta = AdapterMeta(
        name="qq_official",
        display_name="QQ 官方机器人（群聊 + 私聊）",
        protocol="QQ Bot OpenAPI v2",
        docs_url="https://bot.q.qq.com/wiki/",
        notes="不含 QQ 频道。需开放平台审核；群聊场景需单独申请开通。",
    )
    capabilities = _CAPABILITIES

    def __init__(self, *, account_id: str, app_id: str, app_secret: str) -> None:
        super().__init__()
        self.account_id = account_id
        self.app_id = app_id
        self.app_secret = app_secret
        self._client: Any = None
        self._task: asyncio.Task[Any] | None = None
        self._last_user_msg: dict[str, float] = {}

    # ------------------------------------------------------------------ lifecycle
    async def start(self) -> None:
        try:
            import botpy  # type: ignore[import-not-found]
        except ImportError as exc:
            raise RuntimeError(
                "QQ 官方适配器需要可选依赖 qq-botpy，请执行:\n"
                "  .venv\\Scripts\\python.exe -m pip install qq-botpy\n"
                "注意包名是 qq-botpy，不是 botpy。"
            ) from exc

        adapter = self

        class _Client(botpy.Client):  # type: ignore[misc, valid-type]
            async def on_group_at_message_create(self, message: Any) -> None:
                await adapter._on_group_message(message)

            async def on_c2c_message_create(self, message: Any) -> None:
                await adapter._on_c2c_message(message)

        # Intents: group + C2C only. Guild intents are deliberately omitted.
        intents = botpy.Intents(public_messages=True, direct_message=True)
        self._client = _Client(intents=intents)
        self.health.online = True
        self.health.connected_at = time.time()
        logger.info("qq_official starting app_id=%s (group + c2c only, no guild)", self.app_id)
        self._task = asyncio.create_task(self._run())

    async def _run(self) -> None:
        try:
            await self._client.start(appid=self.app_id, secret=self.app_secret)
        except asyncio.CancelledError:
            raise
        except Exception as exc:
            self.health.online = False
            self.health.last_error = str(exc)
            logger.error("qq_official client exited: %s", exc)

    async def stop(self) -> None:
        if self._task is not None:
            self._task.cancel()
            with contextlib.suppress(asyncio.CancelledError, Exception):
                await self._task
            self._task = None
        if self._client is not None:
            with contextlib.suppress(Exception):
                await self._client.close()
            self._client = None
        self.health.online = False
        logger.info("qq_official stopped app_id=%s", self.app_id)

    async def get_self(self) -> Any:
        from soapbot.core.adapter import AccountInfo

        return AccountInfo(self_id=self.account_id, nickname="", adapter=self.meta.name)

    # ------------------------------------------------------------------ inbound
    async def _on_group_message(self, message: Any) -> None:
        raw_content = str(getattr(message, "content", "") or "")
        mentioned, content = split_leading_at(raw_content)
        group_id = str(getattr(message, "group_openid", "") or "")
        author = getattr(message, "author", None)
        user_id = str(getattr(author, "member_openid", "") or "")
        key = f"group:{group_id}"
        self._last_user_msg[key] = time.time()

        segments: list[MessageSegment] = []
        # Emit an AT segment whenever the platform addressed us, even though the
        # mention text is stripped from the body. This is what makes the event
        # self-describing.
        #
        # Why it matters: ``on_group_at_message_create`` only fires when the user
        # @-mentions the bot, so *every* message on this callback is directed at us
        # by construction. But ``WakePolicy`` cannot know that — it looks for an AT
        # segment whose target equals ``self_id``, or for a wake word in the text.
        # Stripping the mention without emitting the segment meant a normal
        # "@bot 你好" had neither, so ``WakePolicy`` returned ``(False, "")`` and the
        # bot silently ignored every correctly-addressed group message on the
        # official channel. OneBot worked because its payload carries the AT
        # segment natively, which is exactly why the defect stayed invisible: the
        # two adapters disagreed about who decides "was I addressed".
        if mentioned:
            segments.append(MessageSegment.at(self.account_id))
        if content:
            segments.append(MessageSegment.text(content))
        for att in getattr(message, "attachments", None) or []:
            url = str(getattr(att, "url", "") or "")
            ctype = str(getattr(att, "content_type", "") or "")
            if url and ctype.startswith("image"):
                segments.append(MessageSegment.image(url=url))

        await self.emit(
            IncomingMessage(
                adapter=self.meta.name,
                message_id=str(getattr(message, "id", "") or ""),
                scene=MessageScene.GROUP,
                sender=Sender(user_id=user_id, nickname=user_id),
                segments=segments,
                group_id=group_id,
                self_id=self.account_id,
                raw={"content": content},
                event_type=EventType.MESSAGE,
            )
        )

    async def _on_c2c_message(self, message: Any) -> None:
        content = str(getattr(message, "content", "") or "")
        author = getattr(message, "author", None)
        user_id = str(getattr(author, "user_openid", "") or "")
        self._last_user_msg[f"private:{user_id}"] = time.time()

        segments: list[MessageSegment] = []
        if content:
            segments.append(MessageSegment.text(content))
        for att in getattr(message, "attachments", None) or []:
            url = str(getattr(att, "url", "") or "")
            ctype = str(getattr(att, "content_type", "") or "")
            if url and ctype.startswith("image"):
                segments.append(MessageSegment.image(url=url))

        await self.emit(
            IncomingMessage(
                adapter=self.meta.name,
                message_id=str(getattr(message, "id", "") or ""),
                scene=MessageScene.PRIVATE,
                sender=Sender(user_id=user_id, nickname=user_id),
                segments=segments,
                self_id=self.account_id,
                raw={"content": content},
                event_type=EventType.MESSAGE,
            )
        )

    # ------------------------------------------------------------------ outbound
    def quota_hint(self, scene: MessageScene, target_id: str) -> dict[str, Any]:
        """Report whether the passive window is still open for this target."""
        key = f"{'group' if scene is MessageScene.GROUP else 'private'}:{target_id}"
        last = self._last_user_msg.get(key, 0.0)
        elapsed = time.time() - last
        return {
            "passive_window_open": elapsed <= PASSIVE_WINDOW_SECONDS,
            "elapsed": elapsed,
            "daily_proactive_limit": DAILY_PROACTIVE_PER_GROUP,
            "per_target_qps": PER_GROUP_QPS,
        }

    async def send(self, message: OutgoingMessage) -> MessageReceipt:
        if self._client is None:
            return MessageReceipt(ok=False, error="qq_official not started")

        segments = self.degrade(message.segments)
        content_parts: list[str] = []
        image_urls: list[str] = []
        for seg in segments:
            if seg.type is SegmentType.TEXT:
                content_parts.append(str(seg.data.get("text", "")))
            elif seg.type is SegmentType.IMAGE:
                url = str(seg.data.get("url", "") or "")
                if url:
                    image_urls.append(url)
            else:
                content_parts.append(seg.plain())

        text = "".join(content_parts).strip()
        try:
            if message.scene is MessageScene.GROUP:
                if image_urls:
                    # Rich media requires upload first; text fallback keeps the
                    # reply deliverable instead of failing the whole turn.
                    await self._send_group(message.group_id, text or "[图片已省略]")
                else:
                    await self._send_group(message.group_id, text)
            else:
                await self._send_c2c(message.user_id, text or "[图片已省略]")
        except Exception as exc:
            logger.error("qq_official send failed target=%s err=%s", message.target_id, exc)
            return MessageReceipt(ok=False, error=str(exc))
        return MessageReceipt(ok=True)

    async def _send_group(self, group_openid: str, content: str) -> None:
        await self._client.api.post_group_message(
            group_openid=group_openid, msg_type=0, content=content
        )

    async def _send_c2c(self, user_openid: str, content: str) -> None:
        await self._client.api.post_c2c_message(
            openid=user_openid, msg_type=0, content=content
        )


_AT_TOKEN_RE = re.compile(r"^\s*<@!?[^>]*>\s*", re.UNICODE)


def split_leading_at(content: str) -> tuple[bool, str]:
    """Split a leading ``<@!botid>`` mention off a group message body.

    Returns ``(mentioned, body)``. The mention is *reported*, not merely deleted —
    see the call site for why the difference decides whether the bot answers at all.

    Kept as a separate function with a name that states its contract because the
    previous version, ``_strip_at_prefix``, returned only the body and invited
    exactly the bug it then caused: a caller can only use what it is given, and
    the information "the user addressed us" was thrown away at the door.
    """
    text = content.lstrip()
    match = _AT_TOKEN_RE.match(text)
    if match is None:
        return False, text.strip()
    return True, text[match.end() :].strip()
