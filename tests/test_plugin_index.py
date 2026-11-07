"""The community index is a discovery source, never a trust source.

Every test here is about a boundary that would be easy to erode later: the index must not
be able to install anything, must not be able to *unblock* a version this repository
blocked, must not take the plugin page down when it fails, and must not hand a deeply
nested document to a recursive parser.
"""

from __future__ import annotations

import json
from pathlib import Path

import httpx
import pytest

from soapbot.plugins.index_client import (
    MAX_INDEX_BYTES,
    IndexClient,
    IndexSnapshot,
    load_local_blocklist,
)
from soapbot.plugins.installer import InstallError, install_from_zip
from soapbot.plugins.manifest import Channel, ManifestError, parse_manifest


def _transport(payload: bytes | None, *, status: int = 200) -> httpx.MockTransport:
    def handler(request: httpx.Request) -> httpx.Response:
        if payload is None:
            raise httpx.ConnectError("refused", request=request)
        return httpx.Response(status, content=payload)

    return httpx.MockTransport(handler)


def _client(payload: bytes | None, *, status: int = 200, blocked: dict | None = None) -> IndexClient:
    return IndexClient(
        "https://example.invalid/plugins.json",
        timeout=1.0,
        ttl=900.0,
        transport=_transport(payload, status=status),
    )


def _index(**overrides) -> bytes:
    body = {
        "plugins": [
            {
                "name": "weather",
                "versions": ["1.0.0", "1.1.0"],
                "summary": "天气查询",
                "author": "someone",
                "repository": "https://example.invalid/weather",
            }
        ],
        "blocked_versions": [{"name": "weather", "version": "1.0.0", "reason": "凭据泄露"}],
    }
    body.update(overrides)
    return json.dumps(body).encode()


@pytest.mark.asyncio
async def test_parses_entries_and_blocks() -> None:
    snapshot = await _client(_index()).snapshot()

    assert snapshot.available
    assert [e.name for e in snapshot.entries] == ["weather"]
    assert snapshot.entries[0].versions == ("1.0.0", "1.1.0")
    assert snapshot.entries[0].latest == "1.1.0"
    assert snapshot.blocked_reason("weather", "1.0.0") == "凭据泄露"
    assert snapshot.blocked_reason("weather", "1.1.0") == ""


@pytest.mark.asyncio
async def test_unreachable_index_degrades_instead_of_raising() -> None:
    """A plugin page that 500s when GitHub is slow is worse than one without a catalogue."""
    snapshot = await _client(None).snapshot()

    assert not snapshot.available
    assert snapshot.entries == ()
    assert snapshot.error


@pytest.mark.asyncio
async def test_non_200_is_reported_with_the_status() -> None:
    snapshot = await _client(b"{}", status=503).snapshot()

    assert not snapshot.available
    assert "503" in snapshot.error


@pytest.mark.asyncio
async def test_malformed_json_is_rejected() -> None:
    snapshot = await _client(b"{not json").snapshot()

    assert not snapshot.available
    assert "JSON" in snapshot.error


@pytest.mark.asyncio
async def test_deeply_nested_document_is_refused_before_parsing() -> None:
    """`json.loads` recurses; RecursionError is not a JSONDecodeError."""
    deep = b'{"plugins":' + b"[" * 5000 + b"]" * 5000 + b"}"

    snapshot = await _client(deep).snapshot()

    assert not snapshot.available
    assert "嵌套" in snapshot.error


@pytest.mark.asyncio
async def test_oversized_index_is_refused() -> None:
    snapshot = await _client(b"x" * (MAX_INDEX_BYTES + 1)).snapshot()

    assert not snapshot.available
    assert "体积" in snapshot.error


@pytest.mark.asyncio
async def test_malformed_entries_are_skipped_not_fatal() -> None:
    payload = json.dumps(
        {
            "plugins": [
                {"name": ""},
                {"summary": "no name"},
                "not a dict",
                {"name": "good", "versions": ["2.0.0", ""]},
            ]
        }
    ).encode()

    snapshot = await _client(payload).snapshot()

    assert snapshot.available
    assert [e.name for e in snapshot.entries] == ["good"]
    assert snapshot.entries[0].versions == ("2.0.0",)


@pytest.mark.asyncio
async def test_control_characters_are_stripped_from_display_fields() -> None:
    payload = json.dumps(
        {"plugins": [{"name": "x", "summary": "line\nbreak\x00null"}]}
    ).encode()

    snapshot = await _client(payload).snapshot()

    assert snapshot.entries[0].summary == "linebreaknull"


@pytest.mark.asyncio
async def test_cache_is_reused_within_ttl() -> None:
    calls = 0

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal calls
        calls += 1
        return httpx.Response(200, content=_index())

    client = IndexClient(
        "https://example.invalid/plugins.json",
        timeout=1.0,
        ttl=900.0,
        transport=httpx.MockTransport(handler),
    )

    await client.snapshot()
    await client.snapshot()

    assert calls == 1


@pytest.mark.asyncio
async def test_force_bypasses_the_cache() -> None:
    calls = 0

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal calls
        calls += 1
        return httpx.Response(200, content=_index())

    client = IndexClient(
        "https://example.invalid/plugins.json",
        timeout=1.0,
        ttl=900.0,
        transport=httpx.MockTransport(handler),
    )

    await client.snapshot()
    await client.snapshot(force=True)

    assert calls == 2


@pytest.mark.asyncio
async def test_no_configured_index_is_not_an_error() -> None:
    """The default deployment has no index; the panel must say so, not "failed"."""
    snapshot = await IndexClient("").snapshot()

    assert not snapshot.available
    assert snapshot.error == ""


@pytest.mark.asyncio
async def test_remote_index_cannot_lift_a_local_block(tmp_path: Path) -> None:
    """The whole point of two lists: a remote file may add a block, never remove one."""
    local = tmp_path / "blocked.json"
    local.write_text(
        json.dumps(
            {"blocked": [{"name": "weather", "version": "1.1.0", "reason": "本地决定"}]}
        ),
        encoding="utf-8",
    )
    payload = json.dumps(
        {
            "plugins": [],
            # The remote list simply does not mention 1.1.0. If merging were a replace,
            # the local block would vanish and the version would become installable.
            "blocked_versions": [{"name": "other", "version": "9.9.9", "reason": "远程"}],
        }
    ).encode()

    client = IndexClient(
        "https://example.invalid/plugins.json",
        timeout=1.0,
        blocklist_path=local,
        transport=_transport(payload),
    )
    snapshot = await client.snapshot()

    assert snapshot.blocked_reason("weather", "1.1.0") == "本地决定"
    assert snapshot.blocked_reason("other", "9.9.9") == "远程"


def test_missing_local_blocklist_warns_but_does_not_raise(tmp_path: Path) -> None:
    """A wheel that lost the file must still start; it is logged because silence is the
    failure mode that looks identical to "nothing is blocked"."""
    assert load_local_blocklist(tmp_path / "absent.json") == {}


def test_shipped_blocklist_is_readable() -> None:
    """The file that ships with the package must parse. An empty list is fine."""
    assert isinstance(load_local_blocklist(), dict)


# ---------------------------------------------------------------- manifest channel


def _manifest(**overrides) -> dict:
    body = {
        "name": "demo",
        "version": "1.0.0",
        "entry": "main:Demo",
        "capabilities": ["command"],
    }
    body.update(overrides)
    return body


def test_channel_defaults_to_community() -> None:
    """Absent means community: the weaker claim, so a forgotten field cannot look official."""
    manifest = parse_manifest(_manifest())

    assert manifest.channel is Channel.COMMUNITY
    assert manifest.to_dict()["channel"] == "community"


def test_official_channel_round_trips() -> None:
    manifest = parse_manifest(_manifest(channel="official"))

    assert manifest.channel is Channel.OFFICIAL
    assert manifest.to_dict()["channel"] == "official"


def test_unknown_channel_is_rejected() -> None:
    """A typo like `offical` must not silently land in the community bucket."""
    with pytest.raises(ManifestError, match="unknown channel"):
        parse_manifest(_manifest(channel="offical"))


# ---------------------------------------------------------------- install refusal


def _zip(files: dict[str, str]) -> bytes:
    import io
    import zipfile

    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w") as archive:
        for name, text in files.items():
            archive.writestr(name, text)
    return buffer.getvalue()


def _package(version: str) -> bytes:
    # Quoted on purpose: YAML reads an unquoted `1.0` as a float, which the manifest
    # parser rejects as "not a string" before any blocklist is consulted. That would
    # make the short-spelling test pass for the wrong reason, so the version is always
    # written as a string here — the same thing a JSON manifest would produce.
    manifest = (
        "name: demo\n"
        f'version: "{version}"\n'
        "entry: main:Demo\n"
        "capabilities:\n"
        "  - command\n"
    )
    return _zip({"plugin.yaml": manifest, "main.py": "class Demo:\n    pass\n"})


def test_blocked_version_is_refused_before_commit(tmp_path: Path) -> None:
    """A blocked version must not replace a working install."""
    existing = tmp_path / "demo"
    existing.mkdir()
    (existing / "plugin.yaml").write_text("name: demo\nversion: 0.9.0\n", encoding="utf-8")

    with pytest.raises(InstallError, match="封禁"):
        install_from_zip(_package("1.0.0"), tmp_path, blocked={"demo@1.0.0": "凭据泄露"})

    # The old version is still there, untouched.
    assert "0.9.0" in (existing / "plugin.yaml").read_text(encoding="utf-8")


def test_unblocked_version_installs(tmp_path: Path) -> None:
    result = install_from_zip(_package("1.0.0"), tmp_path, blocked={"demo@2.0.0": "other"})

    assert result.name == "demo"
    assert (tmp_path / "demo" / "plugin.yaml").is_file()


def test_blocked_version_cannot_be_bypassed_with_short_spelling(tmp_path: Path) -> None:
    """`1.0` and `1.0.0` are the same release, so a block must cover both.

    The manifest grammar accepts either spelling, and the blocklist is keyed by string.
    A literal lookup therefore made the block advisory: publish `evil@1.0.0`, get it
    blocked, then ship a manifest that says `1.0` and install the identical bytes while
    the check appears to have run. Normalising both sides closes that.
    """
    with pytest.raises(InstallError, match="封禁"):
        install_from_zip(_package("1.0"), tmp_path, blocked={"demo@1.0.0": "凭据泄露"})

    assert not (tmp_path / "demo").exists()


def test_blocked_reason_matches_the_key_the_installer_uses() -> None:
    """The panel's answer and the installer's refusal must agree.

    If they disagree the UI says a version is fine and the upload then fails with no
    visible cause, which reads as a broken button rather than a policy.
    """
    snapshot = IndexSnapshot(available=True, blocked={"demo@1.0.0": "凭据泄露"})

    assert snapshot.blocked_reason("demo", "1.0") == "凭据泄露"
    assert snapshot.blocked_reason("demo", "1.0.0") == "凭据泄露"
    assert snapshot.blocked_reason("demo", "1.0.1") == ""
