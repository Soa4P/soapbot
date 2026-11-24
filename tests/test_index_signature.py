"""Index signing (S-SUP-01): a valid signature is what makes the catalogue a claim.

The digest chain refuses a modified *download*. Without a signature, whoever serves a
modified *catalogue* simply declares their own digest, and every downstream check
agrees with them. These tests pin the verifier from the attacker's side: what happens
when the documents change, when the signature belongs to another key, and when the
signature is well-formed but covers the wrong files.

The tests generate their own keypair — the production private key is offline and must
never be needed by a test.
"""

from __future__ import annotations

import base64
import json

import pytest
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

from soapbot.plugins.index_signature import (
    MAX_SIGNATURE_BYTES,
    canonical_payload,
    document_digest,
    verify_documents,
)

PLUGINS = b'{"plugins": [{"name": "weather"}]}'
VERSIONS = b'{"versions": {"weather": []}}'


@pytest.fixture(scope="module")
def signer():
    key = Ed25519PrivateKey.generate()
    raw = key.public_key().public_bytes(
        encoding=serialization.Encoding.Raw, format=serialization.PublicFormat.Raw
    )
    return key, base64.b64encode(raw).decode()


def _document(key, covers: dict[str, str], *, key_id: str = "test-key", **overrides) -> bytes:
    body = {
        "version": 1,
        "algorithm": "ed25519",
        "key_id": key_id,
        "covers": dict(sorted(covers.items())),
        "signature": base64.b64encode(key.sign(canonical_payload(covers))).decode(),
    }
    body.update(overrides)
    return json.dumps(body).encode()


def _good(signer, documents=None) -> tuple[bytes, dict[str, bytes]]:
    key, _pubkey = signer
    documents = documents or {"plugins.json": PLUGINS, "plugin_versions.json": VERSIONS}
    covers = {name: document_digest(body) for name, body in documents.items()}
    return _document(key, covers), documents


def _verify(signer, document: bytes, documents: dict[str, bytes]):
    _key, pubkey = signer
    return verify_documents(document, documents, public_key_b64=pubkey, key_id="test-key")


def test_a_valid_signature_verifies(signer) -> None:
    document, documents = _good(signer)
    verdict = _verify(signer, document, documents)
    assert verdict.ok, verdict.reason
    assert verdict.covered == ("plugin_versions.json", "plugins.json")


def test_a_modified_catalogue_is_refused(signer) -> None:
    """The attack this exists for: same signature, one entry added to the catalogue."""
    document, documents = _good(signer)
    tampered = dict(documents)
    tampered["plugins.json"] = PLUGINS.replace(b"weather", b"weather-plus-backdoor")
    verdict = _verify(signer, document, tampered)
    assert not verdict.ok
    assert "plugins.json" in verdict.reason


def test_a_rewritten_digest_inside_the_signature_is_refused(signer) -> None:
    """An attacker who can edit the signature file can also edit its digest claims —
    but not re-sign the canonical payload without the key."""
    document, documents = _good(signer)
    payload = json.loads(document)
    payload["covers"]["plugins.json"] = document_digest(b'{"plugins": []}')
    verdict = _verify(signer, json.dumps(payload).encode(), documents)
    assert not verdict.ok
    assert verdict.reason in {"签名校验失败", "plugins.json 与签名不一致"} or "签名" in verdict.reason


def test_a_signature_from_another_key_is_refused(signer) -> None:
    """Two layers, both refusals: an unknown ``key_id`` is someone else's index, and a
    signature that claims our key but was made with another one fails the maths."""
    other = Ed25519PrivateKey.generate()
    documents = {"plugins.json": PLUGINS}
    covers = {name: document_digest(body) for name, body in documents.items()}

    foreign = _verify(signer, _document(other, covers, key_id="someone-else"), documents)
    assert not foreign.ok
    assert "密钥" in foreign.reason

    forged = _verify(signer, _document(other, covers), documents)  # claims our key_id
    assert not forged.ok
    assert forged.reason == "签名校验失败"


def test_a_signature_that_does_not_cover_the_catalogue_is_refused(signer) -> None:
    """Authenticating only the metadata would leave the catalogue forgeable."""
    key, _pub = signer
    covers = {"plugin_versions.json": document_digest(VERSIONS)}
    document = _document(key, covers)
    verdict = _verify(signer, document, {"plugins.json": PLUGINS, "plugin_versions.json": VERSIONS})
    assert not verdict.ok
    assert "plugins.json" in verdict.reason


def test_a_document_that_was_not_delivered_is_refused(signer) -> None:
    document, documents = _good(signer)
    verdict = _verify(signer, document, {"plugins.json": documents["plugins.json"]})
    assert not verdict.ok
    assert "没有收到" in verdict.reason


def test_unknown_covered_files_are_refused(signer) -> None:
    key, _pub = signer
    covers = {"plugins.json": document_digest(PLUGINS), "evil.json": document_digest(b"{}")}
    verdict = _verify(signer, _document(key, covers), {"plugins.json": PLUGINS})
    assert not verdict.ok
    assert "未知文件" in verdict.reason


def test_oversized_and_malformed_signature_files_are_refused(signer) -> None:
    _document, documents = _good(signer)
    assert not _verify(signer, b"x" * (MAX_SIGNATURE_BYTES + 1), documents).ok
    assert not _verify(signer, b"not json", documents).ok
    assert not _verify(signer, b"[]", documents).ok
    assert not _verify(signer, b"", documents).ok


def test_wrong_format_version_or_algorithm_is_refused(signer) -> None:
    key, _pub = signer
    documents = {"plugins.json": PLUGINS}
    covers = {"plugins.json": document_digest(PLUGINS)}
    assert not _verify(signer, _document(key, covers, version=2), documents).ok
    assert not _verify(signer, _document(key, covers, algorithm="hmac-sha256"), documents).ok


def test_canonical_payload_is_stable_across_key_order() -> None:
    """Both sides must hash the same bytes, or every verification fails for a reason
    unrelated to security."""
    a = {"plugins.json": "sha256:" + "a" * 64, "plugin_versions.json": "sha256:" + "b" * 64}
    b = {"plugin_versions.json": "sha256:" + "b" * 64, "plugins.json": "sha256:" + "a" * 64}
    assert canonical_payload(a) == canonical_payload(b)
    assert b" " not in canonical_payload(a)


# --------------------------------------------------------------- client integration


def _signed_transport(signer, *, indexed: bytes = PLUGINS, sign_versions: bool = True):
    import httpx

    key, _pub = signer
    documents = {"plugins.json": indexed}
    if sign_versions:
        documents["plugin_versions.json"] = VERSIONS
    covers = {name: document_digest(body) for name, body in documents.items()}
    signature = _document(key, covers)

    def handler(request: httpx.Request) -> httpx.Response:
        path = request.url.path
        if path.endswith("index.sig.json"):
            return httpx.Response(200, content=signature)
        if path.endswith("plugin_versions.json"):
            return httpx.Response(200, content=VERSIONS)
        return httpx.Response(200, content=indexed)

    return httpx.MockTransport(handler)


async def test_client_marks_a_signed_index(signer) -> None:
    """A valid signature surfaces as ``signed`` on the snapshot — the flag the install
    endpoint gates on."""
    from soapbot.plugins.index_client import IndexClient

    _key, pubkey = signer
    client = IndexClient(
        "https://example.invalid/plugins.json",
        timeout=1.0,
        ttl=900.0,
        transport=_signed_transport(signer),
        public_key_b64=pubkey,
        key_id="test-key",
    )
    snapshot = await client.snapshot()
    assert snapshot.available
    assert snapshot.signed is True
    assert snapshot.signature_error == ""
    assert snapshot.signature_key_id == "test-key"


async def test_client_reports_an_unsigned_index_without_failing(signer) -> None:
    """Discovery must keep working: a fork or a local file index is legitimately unsigned.
    Only one-click install is gated on this."""
    import httpx

    from soapbot.plugins.index_client import IndexClient

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path.endswith("index.sig.json"):
            return httpx.Response(404)
        if request.url.path.endswith("plugin_versions.json"):
            return httpx.Response(200, content=VERSIONS)
        return httpx.Response(200, content=PLUGINS)

    client = IndexClient(
        "https://example.invalid/plugins.json",
        timeout=1.0,
        ttl=900.0,
        transport=httpx.MockTransport(handler),
    )
    snapshot = await client.snapshot()
    assert snapshot.available is True
    assert snapshot.entries[0].name == "weather"
    assert snapshot.signed is False
    assert "签名" in snapshot.signature_error
