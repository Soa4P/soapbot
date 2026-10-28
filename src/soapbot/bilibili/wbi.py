"""wbi request signing for Bilibili's newer web endpoints.

What "wbi" is, and why this module exists at all
-----------------------------------------------
A subset of Bilibili's public web API requires two extra query parameters: ``wts``
(a unix timestamp) and ``w_rid`` (an MD5 over the sorted query string concatenated
with a rotating key). The key is derived from two image filenames published by the
``nav`` endpoint, permuted through a fixed table and truncated to 32 characters.

This is not authentication and not an authorisation bypass: no cookie, no login, no
secret. It is a request-shape requirement on endpoints that are otherwise public
metadata. The project's L2 tier is exactly "we can produce the required request
shape"; it is deliberately *not* "we can impersonate a logged-in browser".

What is deliberately absent
---------------------------
* No cookie jar, no ``SESSDATA``, no QR login.
* No playback-URL resolution (``playurl``) — that is content delivery, not metadata,
  and it is the point where "browsing public information" becomes "fetching media".
* No retry that defeats risk control. A ``-412`` means the platform decided this
  client should stop; retrying with a different identity is evasion, and the whole
  L1/L2 framing in the README would be false.

Endpoint-level note: keep the signature implementation boring and testable. It is
checked against a fixed, published example in ``tests/test_bilibili.py`` so a typo in
the permutation table fails a test rather than silently degrading every L2 call to a
``-403``.
"""

from __future__ import annotations

import hashlib
import time
from urllib.parse import urlencode

#: Fixed permutation published in Bilibili's web bundle. Index into the concatenation
#: of the two image keys; the first 32 characters of the result form the mixin key.
MIXIN_KEY_ENC_TAB: tuple[int, ...] = (
    46, 47, 18, 2, 53, 8, 23, 32, 15, 50, 10, 31, 58, 3, 45, 35,
    27, 43, 5, 49, 33, 9, 42, 19, 29, 28, 14, 39, 12, 38, 41, 13,
    37, 48, 7, 16, 24, 55, 40, 61, 26, 17, 0, 1, 60, 51, 30, 4,
    22, 25, 54, 21, 56, 59, 6, 63, 57, 62, 11, 36, 20, 34, 44, 52,
)  # fmt: skip

MIXIN_KEY_LENGTH = 32

#: Characters Bilibili strips from values before signing. If we signed the unstripped
#: form the server's recomputation would differ and reject the request, so the
#: stripping has to happen on our side *before* the digest.
_DROP_CHARS = frozenset("!'()*")


def extract_key(image_url: str) -> str:
    """Take the filename stem out of a ``wbi_img`` URL.

    ``https://i0.hdslb.com/bfs/wbi/7cd084941338484aae1ad9425b84077c.png`` →
    ``7cd084941338484aae1ad9425b84077c``.
    """
    if not image_url:
        return ""
    tail = image_url.rsplit("/", 1)[-1]
    return tail.split(".", 1)[0]


def mixin_key(img_key: str, sub_key: str) -> str:
    """Derive the signing key from the two published image keys."""
    raw = f"{img_key}{sub_key}"
    if len(raw) < max(MIXIN_KEY_ENC_TAB) + 1:
        # A short response means the endpoint shape changed or the response was
        # truncated. Signing with a short key produces requests the server rejects,
        # which looks identical to "the endpoint is down" — fail loudly instead.
        raise ValueError(
            f"wbi keys too short ({len(raw)} chars); expected at least "
            f"{max(MIXIN_KEY_ENC_TAB) + 1}"
        )
    # The table is applied *before* truncation: it reorders the whole concatenation,
    # so truncating first would take a different set of characters.
    permuted = "".join(raw[i] for i in MIXIN_KEY_ENC_TAB)
    return permuted[:MIXIN_KEY_LENGTH]


def sign(params: dict[str, object], key: str, *, timestamp: int | None = None) -> dict[str, str]:
    """Return ``params`` with ``wts`` and ``w_rid`` added."""
    if not key:
        raise ValueError("mixin key is empty")

    cleaned: dict[str, str] = {}
    for name, value in params.items():
        if value is None:
            continue
        text = "".join(ch for ch in str(value) if ch not in _DROP_CHARS)
        cleaned[name] = text

    cleaned["wts"] = str(int(time.time()) if timestamp is None else int(timestamp))
    ordered = dict(sorted(cleaned.items()))
    query = urlencode(ordered)
    # MD5 is specified by the protocol, not chosen here. It is a request-shape
    # checksum, not a security primitive — nothing is authenticated by it.
    digest = hashlib.md5(f"{query}{key}".encode()).hexdigest()
    ordered["w_rid"] = digest
    return ordered


__all__ = [
    "MIXIN_KEY_ENC_TAB",
    "MIXIN_KEY_LENGTH",
    "extract_key",
    "mixin_key",
    "sign",
]
