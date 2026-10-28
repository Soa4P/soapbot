"""Turn a token stream into sendable sentences.

The word "streaming" is borrowed from web chat, where tokens are painted into an
existing DOM node as they arrive. QQ has no such node: neither OneBot v11 nor the
official API offers a message-edit call, so a message that has been sent can only be
recalled and re-sent. Emitting after every few tokens would paint the group with
dozens of messages and run straight into the 5 msg/s ceiling.

Streaming therefore means *sentence-level progressive sending*: the first sentence
leaves as soon as it is complete, the rest follow at a paced rate. This module owns
only the split — no provider, no adapter, no clock of its own — so the rules can be
tested without a network or an event loop.

The first-packet deadline deserves its own note. Without it, a model that emits one
character every 200 ms would make time-to-first-message equal to total latency, and
the only benefit streaming has would disappear. The deadline is applied to the *first*
packet only: once something is on screen (in the group), waiting for a natural
sentence boundary is the better trade.
"""

from __future__ import annotations

#: Enders that terminate a sentence on their own, with no following space required.
#: CJK text has no word separator, so "。" is unambiguous where "." is not.
_SENTENCE_ENDERS = frozenset("。！？…\n")

#: Enders that need a following space or end-of-text to count. Without that guard,
#: "3.14", "v1.2" and "example.com" would each be split into two messages.
_LATIN_ENDERS = frozenset(".!?")

#: Closing punctuation that belongs to the sentence that just ended.
_TRAILING = frozenset("」』】”\"')）]》")

#: Preferred cut points when a sentence runs past the character budget.
_SOFT_BREAKS = frozenset("，,、；;：: ")

#: Characters that carry no content on their own. A fragment made only of these is
#: noise (a model that emits "。。。" before answering), not a sentence worth sending.
_NO_CONTENT = frozenset("。！？…!?.,;:，、；：\n\r\t ") | _SOFT_BREAKS


def _has_content(text: str) -> bool:
    """True when the fragment carries something other than punctuation/whitespace."""
    return any(ch not in _NO_CONTENT for ch in text)


class SentenceAggregator:
    """Accumulate tokens and emit finished sentences.

    Pure by design: ``now`` is passed in rather than read from a clock, so the
    deadline behaviour is testable without sleeping and without freezegun.
    """

    def __init__(
        self,
        *,
        max_chars: int = 80,
        first_packet_deadline: float = 1.2,
    ) -> None:
        if max_chars < 8:
            raise ValueError("max_chars must be at least 8")
        if first_packet_deadline <= 0:
            raise ValueError("first_packet_deadline must be positive")
        self.max_chars = max_chars
        self.first_packet_deadline = first_packet_deadline
        self._buf = ""
        self._first_token_at: float | None = None
        self._sent_any = False

    @property
    def pending(self) -> str:
        """Text held back because no boundary has been reached yet."""
        return self._buf

    @property
    def sent_any(self) -> bool:
        return self._sent_any

    def feed(self, token: str, now: float) -> list[str]:
        """Add a token; return the sentences that are ready to send, in order."""
        if not token:
            return []
        if self._first_token_at is None:
            self._first_token_at = now
        self._buf += token
        return self._drain(now)

    def flush(self) -> list[str]:
        """Return the trailing partial sentence, if any. Call once the stream ends."""
        head = self._buf.strip()
        self._buf = ""
        self._sent_any = self._sent_any or bool(head)
        return [head] if head else []

    # ------------------------------------------------------------------ internals
    def _drain(self, now: float) -> list[str]:
        out: list[str] = []
        while self._buf:
            cut = self._boundary(self._buf)
            if cut is not None:
                head, self._buf = self._buf[:cut], self._buf[cut:]
                head = head.strip()
                if _has_content(head):  # a bare "。。。" is noise, not a sentence
                    self._mark_sent()
                    out.append(head)
                continue

            if len(self._buf) >= self.max_chars:
                cut = self._soft_cut(self._buf)
                head, self._buf = self._buf[:cut], self._buf[cut:]
                head = head.strip()
                if head:
                    self._mark_sent()
                    out.append(head)
                    continue

            if self._deadline_passed(now):
                head = self._buf.strip()
                self._buf = ""
                if _has_content(head):
                    self._mark_sent()
                    out.append(head)
            break
        return out

    def _deadline_passed(self, now: float) -> bool:
        if self._sent_any or self._first_token_at is None:
            return False
        return (now - self._first_token_at) >= self.first_packet_deadline

    def _mark_sent(self) -> None:
        self._sent_any = True

    @staticmethod
    def _boundary(buf: str) -> int | None:
        """Index just past the first sentence terminator, or ``None``."""
        for i, ch in enumerate(buf):
            if ch in _SENTENCE_ENDERS:
                return SentenceAggregator._extend(buf, i + 1)
            # Needs a following space. "Last character so far" is not a boundary: the
            # next token may be a digit ("3." then "14"), and only the caller's flush
            # can decide that the text really has ended.
            if ch in _LATIN_ENDERS and i + 1 < len(buf) and buf[i + 1].isspace():
                return SentenceAggregator._extend(buf, i + 1)
        return None

    @staticmethod
    def _extend(buf: str, idx: int) -> int:
        while idx < len(buf) and buf[idx] in _TRAILING:
            idx += 1
        return idx

    def _soft_cut(self, buf: str) -> int:
        """Cut at the last comma/space inside the budget; otherwise cut hard."""
        window = buf[: self.max_chars]
        for i in range(len(window) - 1, 0, -1):
            if window[i] in _SOFT_BREAKS:
                return i + 1
        return self.max_chars
