"""QQ official bot adapter — group + private (C2C) only.

Scope decisions (frozen by the user):
- **No guild / channel support.** ``Guild`` intents are never requested and no
  child-channel API is implemented. ``MessageScene.CHANNEL`` does not exist.
- ``qq-botpy`` is an *optional* dependency and is imported lazily inside
  ``start()`` so its dormant maintenance cannot break the core import graph.

Platform limits encoded here (QQ open platform docs, group scene):
- passive reply window: 5 minutes after the inbound message, at most 5 replies
  per inbound message;
- proactive messages are metered per receiver relation: 20 per minute, and a
  group may receive at most 1000 per day;
- the group message API itself allows 100 QPS.

These are surfaced through ``quota_hint`` so the limiter can queue rather than
fail. They are *reported*, not enforced here: the platform is the authority, and
pretending a local counter can grant permission would be the same mistake as
the old ``DAILY_PROACTIVE_PER_GROUP = 20`` — a guild-era number that made the
panel promise headroom the group API does not have.

Capability ceiling, stated once: no group-member join/leave events, no member
list, no kick/mute/recall, no channel, no streaming. Those are absent from the
open platform, not merely unimplemented here; an action that needs one must be
refused by the caller rather than silently degraded.
"""

from __future__ import annotations

import asyncio
import contextlib
import logging
import re
import time
from collections import OrderedDict
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
"""No MARKDOWN (falls back to plain text), no FORWARD, no MUTE/KICK/RECALL.

IMAGE/RECORD/FILE are real now: ``send()`` uploads first and sends ``msg_type=7``
instead of replacing them with ``[图片已省略]``. Advertising them before that was
true was the defect this module used to carry.
"""

PASSIVE_WINDOW_SECONDS = 300
"""Official passive reply window. Replies later than this need proactive quota."""

PASSIVE_REPLIES_PER_MESSAGE = 5
"""How many replies one inbound message may receive inside the window."""

PER_RELATION_QPM = 20
"""Proactive messages per receiver relation, per minute."""

PER_GROUP_DAILY_RECEIVE = 1000
"""How many proactive messages one group may receive per day."""

GROUP_API_QPS = 100
"""Rate limit of the group message API itself."""

STATE_CAPACITY = 512
"""Upper bound for ``_last_user_msg`` / ``_last_message``.

Both are keyed by group/private openid. Unbounded dictionaries here grow with
every group the bot has ever seen, which is invisible until a long-lived process
is restarted and the memory graph shows it.
"""

_FILE_TYPES = {
    SegmentType.IMAGE: 1,
    SegmentType.VIDEO: 2,
    SegmentType.RECORD: 3,
    SegmentType.FILE: 4,
}
"""``file_type`` for the rich-media upload endpoint."""


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
        #: ``group:<openid>`` / ``private:<openid>`` -> last inbound time.
        self._last_user_msg: OrderedDict[str, float] = OrderedDict()
        #: Same key -> ``[msg_id, replies_used]``. Needed because passive replies
        #: must carry the id of the message being answered; without it every reply
        #: is a proactive message and burns the 20/min relationship budget.
        self._last_message: OrderedDict[str, list[Any]] = OrderedDict()

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
        # Cancelling ``_task`` stops the inbound reader; it does not stop the handler
        # tasks that reader already dispatched. Without this, a shutdown mid-reply
        # left those tasks to be destroyed with the loop, which is the same "reply
        # half-written, nothing in the log" outcome the OneBot adapter drains to
        # avoid. Draining must happen before ``_client.close()``: the remaining work
        # sends through that client.
        await self.drain_handlers(timeout=3.0)
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
        message_id = str(getattr(message, "id", "") or "")
        self._remember(f"group:{group_id}", message_id)

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
                message_id=message_id,
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
        message_id = str(getattr(message, "id", "") or "")
        self._remember(f"private:{user_id}", message_id)

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
                message_id=message_id,
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
        """Report the platform's limits for this target.

        Deliberately *not* an enforcement point: these numbers are the platform's,
        and a local counter that says "you may" cannot make the API agree. The
        previous version reported a guild-era 20/day for group messages, which was
        wrong in the direction that matters — it under-promised by 50x and named the
        wrong unit.
        """
        key = f"{'group' if scene is MessageScene.GROUP else 'private'}:{target_id}"
        last = self._last_user_msg.get(key, 0.0)
        elapsed = time.time() - last
        entry = self._last_message.get(key)
        used = int(entry[1]) if entry is not None else 0
        return {
            "passive_window_open": elapsed <= PASSIVE_WINDOW_SECONDS,
            "elapsed": elapsed,
            "passive_replies_left": max(0, PASSIVE_REPLIES_PER_MESSAGE - used),
            "passive_replies_per_message": PASSIVE_REPLIES_PER_MESSAGE,
            "per_relation_qpm": PER_RELATION_QPM,
            "per_group_daily_receive": PER_GROUP_DAILY_RECEIVE,
            "group_api_qps": GROUP_API_QPS,
        }

    async def send(self, message: OutgoingMessage) -> MessageReceipt:
        if self._client is None:
            return MessageReceipt(ok=False, error="qq_official not started")

        segments = self.degrade(message.segments)
        text_parts: list[str] = []
        media: list[tuple[SegmentType, str]] = []
        for seg in segments:
            if seg.type is SegmentType.TEXT:
                text_parts.append(str(seg.data.get("text", "")))
            elif seg.type in _FILE_TYPES:
                url = str(seg.data.get("url", "") or seg.data.get("file", "") or "")
                if url:
                    media.append((seg.type, url))
                else:
                    # A segment with no URL cannot be uploaded. Keep the words.
                    text_parts.append(seg.plain())
            else:
                text_parts.append(seg.plain())

        text = "".join(text_parts).strip()
        is_group = message.scene is MessageScene.GROUP
        target = message.group_id if is_group else message.user_id
        key = f"{'group' if is_group else 'private'}:{target}"

        used = self._passive_used(key)
        msg_id = self._passive_message_id(key)

        if not media:
            seq = used + 1
            # After five replies on one inbound message the platform no longer
            # accepts a passive claim; sending ``msg_seq=6`` gets the request
            # rejected as a duplicate rather than delivered as a proactive message.
            passive_id = msg_id if seq <= PASSIVE_REPLIES_PER_MESSAGE else ""
            ok = await self._send_text(
                is_group,
                target,
                text or "[空消息]",
                passive_id,
                seq if passive_id else 0,
            )
            if ok and passive_id:
                self._store_passive_used(key, seq)
            return MessageReceipt(ok=ok, error="" if ok else "send failed")

        # Rich media first: the words still have to arrive even when an upload fails,
        # which is why a failed segment becomes a text placeholder and the turn is not
        # reported as failed.
        placeholders: list[str] = []
        sent_any = False
        for seg_type, url in media[:PASSIVE_REPLIES_PER_MESSAGE]:
            seq = used + 1
            if msg_id and seq > PASSIVE_REPLIES_PER_MESSAGE:
                msg_id_for_send, seq = "", 0
            else:
                msg_id_for_send = msg_id
            ok = await self._send_media(
                is_group, target, url, _FILE_TYPES[seg_type], msg_id_for_send, seq
            )
            if ok:
                sent_any = True
                if msg_id:
                    used += 1
                    self._store_passive_used(key, used)
            else:
                placeholders.append(_placeholder(seg_type))

        final_text = "".join([text, *placeholders]).strip()
        if final_text:
            seq = used + 1
            msg_id_for_send = msg_id if msg_id and seq <= PASSIVE_REPLIES_PER_MESSAGE else ""
            ok = await self._send_text(
                is_group,
                target,
                final_text,
                msg_id_for_send,
                seq if msg_id_for_send else 0,
            )
            if ok:
                sent_any = True
                if msg_id_for_send:
                    used += 1
                    self._store_passive_used(key, used)

        if not sent_any:
            return MessageReceipt(ok=False, error="send failed")
        return MessageReceipt(ok=True)

    # ------------------------------------------------------------------ transport
    async def _send_text(
        self,
        is_group: bool,
        target: str,
        content: str,
        msg_id: str,
        msg_seq: int,
    ) -> bool:
        payload: dict[str, Any] = {"msg_type": 0, "content": content}
        if msg_id:
            payload["msg_id"] = msg_id
            payload["msg_seq"] = msg_seq
        try:
            if is_group:
                await self._client.api.post_group_message(group_openid=target, **payload)
            else:
                await self._client.api.post_c2c_message(openid=target, **payload)
        except Exception as exc:
            logger.error(
                "qq_official text send failed target=%s err=%s", target, type(exc).__name__
            )
            return False
        return True

    async def _send_media(
        self,
        is_group: bool,
        target: str,
        url: str,
        file_type: int,
        msg_id: str,
        msg_seq: int,
    ) -> bool:
        """Upload then send. Two calls, because the platform will not fetch a URL itself.

        The URL is deliberately absent from the log: media URLs are signed and often
        grant access on their own, so writing one into a log line is a credential leak
        with extra steps.
        """
        api = self._client.api
        try:
            if is_group:
                uploaded = await api.post_group_file(
                    group_openid=target, file_type=file_type, url=url
                )
            else:
                uploaded = await api.post_c2c_file(
                    openid=target, file_type=file_type, url=url
                )
        except Exception as exc:
            logger.warning(
                "qq_official media upload failed file_type=%s err=%s",
                file_type,
                type(exc).__name__,
            )
            return False

        file_info = getattr(uploaded, "file_info", None)
        if file_info is None and isinstance(uploaded, dict):
            file_info = uploaded.get("file_info")
        if not file_info:
            logger.warning("qq_official media upload returned no file_info type=%s", file_type)
            return False

        payload: dict[str, Any] = {"msg_type": 7, "media": uploaded}
        if msg_id:
            payload["msg_id"] = msg_id
            payload["msg_seq"] = msg_seq
        try:
            if is_group:
                await api.post_group_message(group_openid=target, **payload)
            else:
                await api.post_c2c_message(openid=target, **payload)
        except Exception as exc:
            logger.warning(
                "qq_official media send failed file_type=%s err=%s",
                file_type,
                type(exc).__name__,
            )
            return False
        return True

    # ------------------------------------------------------------------ state
    def _remember(self, key: str, message_id: str) -> None:
        now = time.time()
        self._last_user_msg[key] = now
        self._last_user_msg.move_to_end(key)
        while len(self._last_user_msg) > STATE_CAPACITY:
            self._last_user_msg.popitem(last=False)
        if message_id:
            self._last_message[key] = [message_id, 0]
            self._last_message.move_to_end(key)
            while len(self._last_message) > STATE_CAPACITY:
                self._last_message.popitem(last=False)

    def _passive_message_id(self, key: str) -> str:
        entry = self._last_message.get(key)
        if entry is None:
            return ""
        elapsed = time.time() - self._last_user_msg.get(key, 0.0)
        if elapsed > PASSIVE_WINDOW_SECONDS:
            return ""
        return str(entry[0] or "")

    def _passive_used(self, key: str) -> int:
        entry = self._last_message.get(key)
        return int(entry[1]) if entry is not None else 0

    def _store_passive_used(self, key: str, used: int) -> None:
        entry = self._last_message.get(key)
        if entry is not None:
            entry[1] = used


def _placeholder(seg_type: SegmentType) -> str:
    return {
        SegmentType.IMAGE: "[图片发送失败]",
        SegmentType.RECORD: "[语音发送失败]",
        SegmentType.VIDEO: "[视频发送失败]",
        SegmentType.FILE: "[文件发送失败]",
    }.get(seg_type, f"[{seg_type} 发送失败]")


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
