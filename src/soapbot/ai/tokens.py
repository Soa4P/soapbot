"""Token counting.

Exact counting needs the vendor tokenizer; installing tiktoken for every provider
is wasteful and wrong for non-OpenAI models. So:

* If ``tiktoken`` is importable, use ``cl100k_base`` as a close approximation.
* Otherwise fall back to a calibrated heuristic: CJK chars ~1 token each,
  ASCII ~4 chars/token. This is deliberately conservative (over-counts) because
  over-counting costs a little context, under-counting costs a failed request.

The heuristic is tested against tiktoken-decoded fixtures where available.
"""

from __future__ import annotations

import functools
import logging
import re

logger = logging.getLogger(__name__)

_CJK_RE = re.compile(r"[\u3400-\u4dbf\u4e00-\u9fff\uf900-\ufaff\u3040-\u30ff\uac00-\ud7af]")
_encoder = None
_encoder_checked = False


def _get_encoder():
    global _encoder, _encoder_checked
    if _encoder_checked:
        return _encoder
    _encoder_checked = True
    try:
        import tiktoken

        _encoder = tiktoken.get_encoding("cl100k_base")
        logger.info("token counting: tiktoken cl100k_base")
    except Exception:
        _encoder = None
        logger.info("token counting: heuristic (tiktoken unavailable)")
    return _encoder


@functools.lru_cache(maxsize=4096)
def count_tokens(text: str) -> int:
    if not text:
        return 0
    enc = _get_encoder()
    if enc is not None:
        try:
            return len(enc.encode(text, disallowed_special=()))
        except Exception:  # pragma: no cover - fall through to heuristic
            pass
    return _heuristic_count(text)


def _heuristic_count(text: str) -> int:
    cjk = len(_CJK_RE.findall(text))
    rest = len(text) - cjk
    # +1 smooths out short strings; ceil keeps it conservative.
    return cjk + max(1, (rest + 3) // 4)


def count_message_tokens(role: str, content: str) -> int:
    """Per-message overhead of 4 tokens mirrors OpenAI's documented accounting."""
    return count_tokens(role) + count_tokens(content) + 4


def count_messages(messages: list[dict[str, object]]) -> int:
    total = 0
    for m in messages:
        role = str(m.get("role", ""))
        content = m.get("content", "")
        if isinstance(content, str):
            total += count_message_tokens(role, content)
        else:
            total += count_message_tokens(role, str(content))
    return total + 2
