"""Detached signature verification for the community plugin index (S-SUP-01).

What signing adds that digests do not
-------------------------------------
The install chain already refuses a download whose bytes differ from the digest the
index declares. That closes the case where someone edits *the download*. It does not
close the case where someone edits *the index*: whoever can serve a modified
``plugins.json`` + ``plugin_versions.json`` can publish their own plugin, with their
own digest, and the digest check passes because the index is what defined the digest.

A detached Ed25519 signature over the published documents removes that: the index
becomes "what the maintainer signed", and a modified index fails verification even
though it is internally consistent.

Key handling, stated plainly
----------------------------
The private key is **offline and never in either repository** (see
``docs/plugin-index-signing.md``). Only the public key lives here, as a constant. Loss
of the private key means a rotation: publish a release whose embedded key is the new
one, and re-sign the index with it. There is deliberately no remote key discovery —
fetching the key from the same host that serves the index would verify nothing.

What is signed
--------------
A canonical JSON document naming a SHA-256 for each covered file::

    {"algorithm":"ed25519","covers":{"plugin_versions.json":"sha256:…",
                                     "plugins.json":"sha256:…"},"version":1}

Canonicalisation (sorted keys, no whitespace, UTF-8) matters: the signature is over
bytes, and the same logical document must produce the same bytes on both sides or
every verification would fail for a reason unrelated to security.
"""

from __future__ import annotations

import base64
import binascii
import hashlib
import hmac
import json
from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any

from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PublicKey

#: Detached signature file, fetched from the same directory as the catalogue.
SIGNATURE_FILENAME = "index.sig.json"

SIGNATURE_ALGORITHM = "ed25519"

#: A signature document is a few hundred bytes. Anything larger is not one.
MAX_SIGNATURE_BYTES = 8 * 1024

#: The documents a signature may cover, in the names the signature document uses.
COVERED_DOCUMENTS = ("plugins.json", "plugin_versions.json")

#: Maintainer signing key. Rotating it is a release-level change: the private key is
#: offline, so a new key means a new embedded constant here.
MARKET_KEY_ID = "c74ba4090e4ea9ca"
MARKET_PUBLIC_KEY_B64 = "N558xgdHlVRPqUY9Z9A9WtVUbGPAJBhqr1Nkqamuy1E="


@dataclass(frozen=True)
class SignatureVerdict:
    """Whether an index document set is provably the one that was signed."""

    ok: bool
    reason: str = ""
    key_id: str = ""
    covered: tuple[str, ...] = ()

    def to_dict(self) -> dict[str, Any]:
        return {
            "ok": self.ok,
            "reason": self.reason,
            "key_id": self.key_id,
            "covered": list(self.covered),
        }


def canonical_payload(covers: Mapping[str, str]) -> bytes:
    """The exact bytes a signature covers, given ``{filename: "sha256:…"}``.

    Sorted keys and no separators: this is the canonicalisation both the signer and
    the verifier use, so a difference in the signature can only mean a difference in
    the documents.
    """
    document = {
        "algorithm": SIGNATURE_ALGORITHM,
        "covers": {name: covers[name] for name in sorted(covers)},
        "version": 1,
    }
    return json.dumps(document, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode(
        "utf-8"
    )


def document_digest(body: bytes) -> str:
    """SHA-256 of a published document, with line endings normalised to LF.

    Why normalise: the signature covers bytes, and git may check the same file out as
    CRLF (Windows, ``core.autocrlf``) or LF (Linux, CI). Hashing the raw bytes made a
    signature that verified on the maintainer's machine fail in CI — measured, and the
    failure looks exactly like tampering. Normalising to LF removes the platform from
    the equation; the only thing it stops detecting is a pure line-ending flip, which
    changes nothing a JSON parser sees.
    """
    normalised = body.replace(b"\r\n", b"\n")
    return "sha256:" + hashlib.sha256(normalised).hexdigest()


def _fail(reason: str, key_id: str = "") -> SignatureVerdict:
    return SignatureVerdict(ok=False, reason=reason, key_id=key_id)


def verify_documents(
    signature_body: bytes,
    documents: Mapping[str, bytes],
    *,
    public_key_b64: str = MARKET_PUBLIC_KEY_B64,
    key_id: str = MARKET_KEY_ID,
) -> SignatureVerdict:
    """Verify a detached signature against the documents actually received.

    Every failure is a verdict, never an exception: the caller renders the market page
    from whatever it has, and "signature invalid" must read as a state, not a 500.
    ``documents`` must contain exactly the bytes that were parsed — verifying a
    re-serialised copy would sign the parser's output instead of what the host serves.
    """
    if not signature_body:
        return _fail("索引没有签名文件")
    if len(signature_body) > MAX_SIGNATURE_BYTES:
        return _fail("签名文件体积超出上限")
    try:
        document = json.loads(signature_body.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError):
        return _fail("签名文件不是合法 JSON")
    if not isinstance(document, dict):
        return _fail("签名文件结构不正确")

    if document.get("version") != 1:
        return _fail("不认识的签名格式版本")
    if document.get("algorithm") != SIGNATURE_ALGORITHM:
        return _fail("不认识的签名算法")

    signer = str(document.get("key_id") or "")
    if not hmac.compare_digest(signer, key_id):
        # A signature from any other key is not "less trusted" — it is someone else's.
        return _fail(f"签名密钥未知（{signer or '未声明'}）", signer)

    covers_raw = document.get("covers")
    if not isinstance(covers_raw, dict) or not covers_raw:
        return _fail("签名未声明覆盖范围", signer)
    covers: dict[str, str] = {}
    for name, digest in covers_raw.items():
        if not isinstance(name, str) or not isinstance(digest, str):
            return _fail("签名覆盖范围格式不正确", signer)
        if name not in COVERED_DOCUMENTS:
            return _fail(f"签名覆盖了未知文件（{name}）", signer)
        if not digest.startswith("sha256:") or len(digest) != len("sha256:") + 64:
            return _fail(f"签名里的摘要格式不正确（{name}）", signer)
        covers[name] = digest

    # The catalogue is the document that decides what exists; a signature that does not
    # cover it would authenticate the metadata while leaving the catalogue forgeable.
    if "plugins.json" not in covers:
        return _fail("签名未覆盖 plugins.json", signer)

    for name, expected in covers.items():
        body = documents.get(name)
        if body is None:
            return _fail(f"签名覆盖了 {name}，但没有收到该文件", signer)
        actual = document_digest(body)
        if not hmac.compare_digest(actual, expected):
            return _fail(f"{name} 与签名不一致", signer)

    try:
        signature = base64.b64decode(str(document.get("signature") or ""), validate=True)
        key = Ed25519PublicKey.from_public_bytes(base64.b64decode(public_key_b64, validate=True))
        key.verify(signature, canonical_payload(covers))
    except (binascii.Error, ValueError):
        return _fail("签名不是合法的 base64 或密钥格式错误", signer)
    except InvalidSignature:
        return _fail("签名校验失败", signer)

    return SignatureVerdict(ok=True, key_id=signer, covered=tuple(sorted(covers)))
