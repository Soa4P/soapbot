"""Bracket-depth check for JSON that arrives from outside the process.

Why this exists at all: ``json.loads`` recurses. A payload of ``[[[[…`` a few thousand
levels deep raises ``RecursionError`` from inside the C accelerator — a ``RuntimeError``
subclass, *not* a ``ValueError``, so the ``except json.JSONDecodeError`` that every caller
writes around a decode does not catch it. The result is a coroutine that dies with a
traceback pointing at the parser, in a task nobody awaited, and in the plugin supervisor's
case the child process exits and takes the plugin's whole session with it.

Counting brackets first is one linear pass over bytes we already have in memory. It is
cheaper than the parse it precedes, and it converts an uncatchable crash into an ordinary
rejection that names the limit and the actual depth — which is the difference between
"the plugin crashed" and "the plugin sent a frame nested 900 deep, limit is 32".

The scan is deliberately naive about strings: a ``[`` inside a string literal is counted.
That over-counts rather than under-counts, so a payload full of ``"[[[["`` is rejected
even though it is technically flat. Rejecting a pathological-but-legal frame is the right
trade here — no legitimate IPC message or API body is 32 levels deep, let alone one that
spends its depth budget inside string literals.
"""

from __future__ import annotations

from soapbot.config import settings

_OPEN = frozenset(b"{[")
_CLOSE = frozenset(b"}]")


class JsonTooDeepError(ValueError):
    """Raised when a payload nests deeper than ``settings.max_json_depth``.

    A ``ValueError`` on purpose: every caller already handles ``ValueError`` around a
    decode (``json.JSONDecodeError`` is one), so this slots into the existing error path
    instead of introducing a new exception type each caller has to remember.
    """


def depth_of(raw: bytes | str) -> int:
    """Maximum bracket nesting depth, counting only structural characters.

    Returns 0 for anything with no brackets, which is the correct answer for a scalar
    document and keeps the caller's comparison a single ``>``.
    """
    data = raw.encode("utf-8", "replace") if isinstance(raw, str) else raw
    depth = 0
    deepest = 0
    for byte in data:
        if byte in _OPEN:
            depth += 1
            if depth > deepest:
                deepest = depth
        elif byte in _CLOSE:
            # Clamped at zero: an unbalanced ``}`` is a syntax error the parser will
            # report properly, and letting depth go negative would hide a later run of
            # opens behind the earlier closes.
            if depth:
                depth -= 1
    return deepest


def check_depth(raw: bytes | str, *, limit: int | None = None) -> int:
    """Reject a payload that nests too deep; return its depth when it is acceptable.

    Call this immediately before ``json.loads`` on any bytes that came from a socket, a
    child process, or an HTTP body. It is not a substitute for the parser — malformed
    JSON still has to be caught — it only removes the one malformed shape that cannot be
    caught.
    """
    ceiling = settings.max_json_depth if limit is None else limit
    deepest = depth_of(raw)
    if deepest > ceiling:
        raise JsonTooDeepError(
            f"JSON nested {deepest} levels deep, limit is {ceiling}; refusing to parse"
        )
    return deepest
