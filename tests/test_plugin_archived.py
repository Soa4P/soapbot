"""Withdrawn plugins: the catalogue's only non-version-specific signal (S-SUP-08).

A block says "this release is bad". Withdrawal says "stop offering this plugin" — and the
host used to ignore it entirely, so a plugin removed for a licence problem, abandonment or
a capability the marketplace no longer accepts kept running silently on every machine that
had installed it.

The positions this file pins:

* an archived entry reaches the panel with its reason;
* the archived list is *signed* like the catalogue, and is dropped when the signature does
  not cover it — otherwise it is the one document worth rewriting (to hide a withdrawal);
* nothing is enforced: the host never disables, unloads or blocks because of this field.
"""

from __future__ import annotations

import base64
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import httpx
import pytest

import soapbot.plugins.index_client  # noqa: F401  dotted path: check_test_gaps counts it
from soapbot.plugins.archived import index_archived_url, parse_archived
from soapbot.plugins.index_signature import canonical_payload, document_digest

PLUGINS = json.dumps({"plugins": [{"name": "weather", "versions": ["1.0.0"], "latest": "1.0.0"}]}).encode()
VERSIONS = json.dumps(
    {
        "versions": {
            "weather": [
                {
                    "version": "1.0.0",
                    "digest": "sha256:" + "a" * 64,
                    "download": "https://example.invalid/weather-1.0.0.zip",
                }
            ]
        }
    }
).encode()
ARCHIVED = json.dumps(
    {"archived": [{"name": "rss-digest", "reason": "作者停止维护，且不再接受其权限声明"}]}
).encode()


def test_the_archived_url_sits_next_to_the_catalogue() -> None:
    assert index_archived_url("https://example.invalid/index/plugins.json") == (
        "https://example.invalid/index/archived_plugins.json"
    )


def test_parsing_is_tolerant_and_keeps_the_reason() -> None:
    parsed = parse_archived(json.loads(ARCHIVED))
    assert parsed["rss-digest"].startswith("作者停止维护")
    # Shapes a hand-edited file can have; none may raise.
    assert parse_archived(None) == {}
    assert parse_archived({"archived": "nope"}) == {}
    assert parse_archived({"archived": [1, {"noname": 1}]}) == {}
    assert parse_archived({"archived": [{"name": "x"}]})["x"], "缺原因也要给一个默认说明"


@pytest.fixture
def signer():
    from cryptography.hazmat.primitives import serialization
    from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

    key = Ed25519PrivateKey.generate()
    raw = key.public_key().public_bytes(
        encoding=serialization.Encoding.Raw, format=serialization.PublicFormat.Raw
    )
    return key, base64.b64encode(raw).decode()


def _document(key, covers: dict[str, str], key_id: str = "test-key") -> bytes:
    payload = {
        "version": 1,
        "algorithm": "ed25519",
        "key_id": key_id,
        "covers": {name: covers[name] for name in sorted(covers)},
        "signature": base64.b64encode(key.sign(canonical_payload(covers))).decode(),
    }
    return json.dumps(payload).encode()


def _transport(signer, *, cover_archived: bool) -> httpx.MockTransport:
    key, _pub = signer
    documents = {"plugins.json": PLUGINS, "plugin_versions.json": VERSIONS}
    if cover_archived:
        documents["archived_plugins.json"] = ARCHIVED
    covers = {name: document_digest(body) for name, body in documents.items()}
    signature = _document(key, covers)

    def handler(request: httpx.Request) -> httpx.Response:
        path = request.url.path
        if path.endswith("index.sig.json"):
            return httpx.Response(200, content=signature)
        if path.endswith("plugin_versions.json"):
            return httpx.Response(200, content=VERSIONS)
        if path.endswith("archived_plugins.json"):
            return httpx.Response(200, content=ARCHIVED)
        return httpx.Response(200, content=PLUGINS)

    return httpx.MockTransport(handler)


async def _snapshot(signer, *, cover_archived: bool):
    from soapbot.plugins.index_client import IndexClient

    _key, pubkey = signer
    client = IndexClient(
        "https://example.invalid/plugins.json",
        timeout=1.0,
        ttl=900.0,
        transport=_transport(signer, cover_archived=cover_archived),
        public_key_b64=pubkey,
        key_id="test-key",
    )
    return await client.snapshot()


async def test_a_signed_archived_list_reaches_the_snapshot(signer) -> None:
    snapshot = await _snapshot(signer, cover_archived=True)
    assert snapshot.signed is True
    assert "rss-digest" in snapshot.archived
    assert "停止维护" in snapshot.archived["rss-digest"]


async def test_an_uncovered_archived_list_is_ignored(signer) -> None:
    """The signature covers the catalogue but not the withdrawal list.

    That leaves exactly the document an attacker would rewrite — to hide a withdrawal —
    unauthenticated, so it is dropped and the operator is told why.
    """
    snapshot = await _snapshot(signer, cover_archived=False)
    assert snapshot.signed is True, "目录本身仍然是签过名的"
    assert snapshot.archived == {}
    assert any("签名覆盖范围" in warning for warning in snapshot.warnings)


async def test_a_missing_archived_file_is_not_a_degraded_state(signer) -> None:
    """An index that never withdrew anything does not publish the file."""
    from soapbot.plugins.index_client import IndexClient

    _key, pubkey = signer
    documents = {"plugins.json": PLUGINS, "plugin_versions.json": VERSIONS}
    covers = {name: document_digest(body) for name, body in documents.items()}
    signature = _document(signer[0], covers)

    def handler(request: httpx.Request) -> httpx.Response:
        path = request.url.path
        if path.endswith("index.sig.json"):
            return httpx.Response(200, content=signature)
        if path.endswith("plugin_versions.json"):
            return httpx.Response(200, content=VERSIONS)
        if path.endswith("archived_plugins.json"):
            return httpx.Response(404)
        return httpx.Response(200, content=PLUGINS)

    client = IndexClient(
        "https://example.invalid/plugins.json",
        timeout=1.0,
        ttl=900.0,
        transport=httpx.MockTransport(handler),
        public_key_b64=pubkey,
        key_id="test-key",
    )
    snapshot = await client.snapshot()
    assert snapshot.signed is True
    assert snapshot.archived == {}
    assert snapshot.warnings == (), "404 是正常状态，不该产生告警"
