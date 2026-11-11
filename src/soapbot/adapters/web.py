"""Web conversation adapter — the archive clients as a message source.

Why an adapter at all: the pipeline is adapter-shaped end to end. ``dispatch``
looks the sender's adapter up in the registry before the event is even admitted,
``ReplyStage`` delivers through ``ctx.adapter.send``, and ``PersistReplyStage``
archives the reply only after a successful send. Standing in as that adapter is
what lets a web message pay exactly the same tolls (guard, injection screen,
whitelist, rate limit, persona, memory) as a QQ message, instead of a second,
softer path growing next to the real one.

Inbound: nothing arrives here from the network. ``POST /api/chat/messages``
constructs the event in-process and calls ``runtime.dispatch`` directly, so this
class has no socket, no polling and no login — ``start()`` only marks health, so
the panel's adapter list shows an honest "online" for the conversation surface
rather than a row that is always red while talk works fine.

Outbound: ``send()`` does **not** write to the archive. ``PersistReplyStage``
writes the assistant row after ``send_ok`` is set; a write here would be a second
copy of every reply. Delivery to the human happens through the archive itself —
the web/mobile clients already poll or subscribe to the session, so "delivered"
and "archived" are the same event, and the receipt's only job is to say ok. The
message id it returns is a trace handle, not a platform id: nothing can quote or
recall it, and pretending otherwise would promise a protocol this surface
does not have.

Session shape: ``web:private:account-<id>`` — three ``:``-separated parts, so
the plugin send path (``adapter:scene:target``) parses it without a special
case, and the sender id carries a non-numeric prefix so it can never collide
with a QQ number in the operator's owner/admin/member lists
(``normalize_id`` keeps letter-prefixed ids verbatim; the lists hold digits).
"""

from __future__ import annotations

import logging
import time
import uuid

from soapbot.core.adapter import AccountInfo, Adapter, AdapterMeta, Capability
from soapbot.core.message import MessageReceipt, OutgoingMessage

logger = logging.getLogger(__name__)

_CAPABILITIES = frozenset({Capability.TEXT, Capability.REPLY})
"""Text only. A record segment (voice reply) degrades to its text placeholder
via the base-class ``degrade`` — the archive stores text, and a client that
cannot play audio inside the timeline should not be sent an opaque row."""


class WebAdapter(Adapter):
    """In-process adapter for web/mobile conversations. See the module docstring."""

    meta = AdapterMeta(
        name="web",
        display_name="网页对话",
        protocol="internal",
        notes="API 驱动的对话端；无网络连接，健康状态即进程存活",
    )
    capabilities = _CAPABILITIES

    async def start(self) -> None:
        # There is no transport to prove liveness on, so online means "the runtime
        # attached this adapter", stamped at start. last_seen is refreshed by sends:
        # a talk surface nobody has used for a week should not read as busy.
        self.health.online = True
        self.health.connected_at = time.time()
        self.health.last_seen_at = time.time()

    async def stop(self) -> None:
        self.health.online = False

    async def get_self(self) -> AccountInfo:
        return AccountInfo(self_id="soapbot", nickname="soapbot", adapter="web")

    async def send(self, message: OutgoingMessage) -> MessageReceipt:
        self.health.last_seen_at = time.time()
        receipt_id = f"web-{uuid.uuid4().hex[:12]}"
        logger.debug(
            "web reply delivered=%s scene=%s target=%s",
            receipt_id,
            message.scene,
            message.target_id,
        )
        return MessageReceipt(ok=True, message_id=receipt_id)
