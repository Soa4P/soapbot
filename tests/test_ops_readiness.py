"""Operational surface: probes a load balancer uses, and backup/restore.

The backup test deliberately mutates the database between backup and restore. A test
that only asserts "the file came back" passes just as well when the archive captured
the pre-write state by accident, which is exactly the WAL bug the backup API is there
to prevent.
"""

from __future__ import annotations

import contextlib
import importlib.util
import json
import sqlite3
import zipfile
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from soapbot.app import create_app
from soapbot.config import settings


def _load_script(name: str):
    path = Path(__file__).resolve().parent.parent / "scripts" / f"{name}.py"
    spec = importlib.util.spec_from_file_location(f"soapbot_script_{name}", path)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


# ------------------------------------------------------------------- readiness


@pytest.fixture
def client(tmp_path, monkeypatch) -> TestClient:
    monkeypatch.setattr(settings, "data_dir", tmp_path)
    app = create_app()
    with TestClient(app) as c:
        yield c


def test_healthz_matches_the_documented_health_route(client: TestClient) -> None:
    health = client.get("/api/health")
    alias = client.get("/healthz")
    assert alias.status_code == 200
    assert alias.json()["status"] == health.json()["status"] == "ok"


def test_the_csp_allows_no_websocket_to_any_host(client: TestClient) -> None:
    """S-FE-04: bare ``ws:``/``wss:`` scheme sources are permission to any host.

    The panel opens no WebSocket of its own — every ws:// string in the UI is
    placeholder text for NapCat's config, not a connection this page makes. The
    scheme sources therefore existed only for an injected script, which is exactly
    who CSP is supposed to refuse. ``form-action`` joins the policy so a forged form
    cannot POST the page's cookies anywhere either.
    """
    policy = client.get("/api/health").headers["Content-Security-Policy"]
    assert "connect-src 'self'" in policy
    assert "form-action 'self'" in policy
    assert "ws:" not in policy, "裸 ws:/wss: 是给任意主机的 WebSocket 许可"
    assert "wss:" not in policy


def test_readyz_reports_ready_when_the_data_dir_is_writable(
    client: TestClient, tmp_path: Path, monkeypatch
) -> None:
    # The suite turns strict loopback off (loopback == owner); production defaults to
    # on. Pin the production posture here, because the redaction is about *that* case.
    monkeypatch.setattr(settings, "strict_loopback_auth", True)

    response = client.get("/readyz")
    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "ok"
    assert body["problems"] == []
    # An anonymous probe learns the verdict, not where the machine keeps its files.
    assert "data_dir" not in body
    assert "startup_errors" not in body
    # The probe file must not survive its own check.
    assert not list(tmp_path.glob(".readyz-*"))


def test_readyz_fails_when_the_data_dir_cannot_be_created(
    client: TestClient, tmp_path: Path, monkeypatch
) -> None:
    """A file where the data directory should be is the cheapest reliable way to make
    mkdir fail on every platform, including Windows where chmod proves nothing."""
    monkeypatch.setattr(settings, "strict_loopback_auth", True)
    blocked = tmp_path / "blocked"
    blocked.write_text("not a directory", encoding="utf-8")
    monkeypatch.setattr(settings, "data_dir", blocked)

    response = client.get("/readyz")
    assert response.status_code == 503
    assert response.json()["status"] == "unavailable"
    assert "data_dir_not_writable" in response.json()["problems"]
    # The OS message embeds the path; an anonymous caller must not receive it (S-AUTH-07).
    assert "blocked" not in response.text


def test_a_trusted_loopback_still_sees_the_full_diagnosis(
    client: TestClient, tmp_path: Path, monkeypatch
) -> None:
    """Gating the detail must not take it away from the person who needs it.

    A deployment that has turned strict loopback off has already declared local
    clients to be owners; the readiness probe follows that same decision instead of
    inventing a second rule.
    """
    monkeypatch.setattr(settings, "strict_loopback_auth", False)
    monkeypatch.setattr(settings, "data_dir", tmp_path / "ops")

    body = client.get("/readyz").json()
    assert body["data_dir"] == str(tmp_path / "ops")
    assert body["startup_errors"] == []
    assert body["details"] == []


def test_operator_detail_is_not_granted_to_an_unverified_credential(
    monkeypatch,
) -> None:
    """A junk bearer token is not an operator.

    The case that matters is strict loopback: a caller from 127.0.0.1 that *presents*
    a credential is asking to be treated as authenticated, and the gate must verify it
    rather than take the header as proof. (With strict loopback off, loopback is owner
    by configuration and the token is irrelevant — that is the deployment's own choice,
    not this helper's.)
    """
    from types import SimpleNamespace

    from soapbot.api.auth import operator_detail_allowed

    monkeypatch.setattr(settings, "strict_loopback_auth", True)
    request = SimpleNamespace(
        headers={"Authorization": "Bearer not-a-real-token"},
        cookies={},
        client=SimpleNamespace(host="127.0.0.1"),
        app=SimpleNamespace(state=SimpleNamespace()),
        url="http://127.0.0.1:6185/readyz",
    )
    assert operator_detail_allowed(request) is False


class _BrokenDatabase:
    """A database whose session fails on entry, like a corrupt or unopenable file."""

    @contextlib.asynccontextmanager
    async def session(self):
        raise RuntimeError("disk I/O error")
        yield  # pragma: no cover - unreachable; keeps this an async generator


def test_readyz_fails_when_the_database_cannot_be_queried(
    client: TestClient, monkeypatch
) -> None:
    """A writable directory is a proxy, not the property. This is the proxy failing.

    The data directory in this fixture is perfectly writable, so only the query reveals
    the problem — which is precisely the case the old probe reported as healthy.
    """
    from soapbot.memory import db as db_module

    monkeypatch.setattr(db_module, "_db", _BrokenDatabase())

    response = client.get("/readyz")
    assert response.status_code == 503
    body = response.json()
    assert "database_not_usable" in body["problems"]
    # /readyz is unauthenticated; the driver message can carry a path.
    assert "disk I/O error" not in response.text


async def test_readyz_with_a_real_initialised_database(tmp_path, monkeypatch) -> None:
    """The regression the fake could not catch: a REAL Database's ``session`` is a
    bare async generator (no ``__aenter__``), so the production readiness probe
    raised TypeError and /readyz returned 503 on every healthy deployment. The
    ``_BrokenDatabase`` fake above carries ``@asynccontextmanager``, so it passed
    the very branch this test exercises — the fake had a protocol the real thing
    lacks."""
    from soapbot.memory.db import get_database

    monkeypatch.setattr(settings, "data_dir", tmp_path)
    db = await get_database(
        url=f"sqlite+aiosqlite:///{(tmp_path / 'probe.db').as_posix()}")
    try:
        app = create_app()
        with TestClient(app) as c:
            response = c.get("/readyz")
            assert response.status_code == 200
            assert response.json()["problems"] == []
    finally:
        await db.engine.dispose()


def test_readyz_does_not_require_a_database_before_one_exists(
    client: TestClient, monkeypatch
) -> None:
    """The probe must not be the thing that creates the schema it observes."""
    from soapbot.memory import db as db_module

    monkeypatch.setattr(db_module, "_db", None)

    assert client.get("/readyz").status_code == 200


def test_readyz_reports_degraded_without_failing(
    client: TestClient, monkeypatch
) -> None:
    """A broken plugin or offline adapter is degraded, not unavailable.

    Failing readiness there would pull the console out of service exactly when someone
    needs it to diagnose the plugin.
    """
    from soapbot import app as app_module

    monkeypatch.setattr(settings, "strict_loopback_auth", True)
    monkeypatch.setattr(app_module, "get_startup_errors", lambda: ["adapter qq is offline"])

    response = client.get("/readyz")
    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "ok"
    assert body["degraded"] is True
    # Anonymous: how many, not which ones. The text names the adapter.
    assert body["startup_error_count"] == 1
    assert "startup_errors" not in body
    assert "adapter qq is offline" not in response.text


# ------------------------------------------------------------------ /metrics


def test_metrics_exposes_build_and_uptime(client: TestClient) -> None:
    """Prometheus needs the text format, not JSON, and a stable metric name."""
    response = client.get("/metrics")

    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/plain")
    assert "version=0.0.4" in response.headers["content-type"]
    body = response.text
    assert 'soapbot_info{version="' in body
    assert "# TYPE soapbot_uptime_seconds gauge" in body


def test_metrics_publishes_empty_provider_families_without_a_runtime(
    client: TestClient,
) -> None:
    """Switching the runtime off must not leave a stale series on a dashboard.

    The families are emitted with no samples, so Prometheus records "no data" instead
    of continuing to draw the last value from before the runtime was disabled.
    """
    body = client.get("/metrics").text

    assert "# TYPE soapbot_provider_calls_total counter" in body
    assert "# TYPE soapbot_provider_latency_p95_ms gauge" in body


def test_metrics_label_values_are_escaped() -> None:
    """A provider id is operator-controlled config; it must not break the format."""
    from soapbot.app import _prometheus_label

    assert _prometheus_label('a"b') == 'a\\"b'
    assert _prometheus_label("a\\b") == "a\\\\b"
    assert _prometheus_label("a\nb") == "a\\nb"


# -------------------------------------------------------------- backup/restore


def _make_db(path: Path, marker: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    # Connections are closed explicitly: the context manager commits but keeps the
    # handle, and Windows refuses to rename a file that still has one open.
    conn = sqlite3.connect(path)
    try:
        conn.execute("CREATE TABLE IF NOT EXISTS schema_version (version INTEGER)")
        conn.execute("DELETE FROM schema_version")
        conn.execute("INSERT INTO schema_version VALUES (1)")
        conn.execute("CREATE TABLE IF NOT EXISTS notes (body TEXT)")
        conn.execute("DELETE FROM notes")
        conn.execute("INSERT INTO notes VALUES (?)", (marker,))
        conn.commit()
    finally:
        conn.close()


def _notes(path: Path) -> list[str]:
    conn = sqlite3.connect(path)
    try:
        return [row[0] for row in conn.execute("SELECT body FROM notes")]
    finally:
        conn.close()


def test_backup_restore_round_trip(tmp_path: Path) -> None:
    backup = _load_script("backup")
    restore = _load_script("restore")

    data_dir = tmp_path / "data"
    config_dir = tmp_path / "config"
    _make_db(data_dir / "soapbot.db", "before")
    config_dir.mkdir()
    (config_dir / "adapters.yaml").write_text("adapters: []\n", encoding="utf-8")

    archive = tmp_path / "backup.zip"
    result = backup.build(data_dir, config_dir, archive)
    assert archive.is_file()
    assert result["schema_version"] == 1

    # Mutate after the backup: a restore that silently keeps this state has done nothing.
    _make_db(data_dir / "soapbot.db", "after")
    (config_dir / "adapters.yaml").unlink()

    restore.restore(archive, data_dir=data_dir, config_dir=config_dir)

    assert _notes(data_dir / "soapbot.db") == ["before"]
    assert (config_dir / "adapters.yaml").is_file()
    # The old database is kept, so the wrong-backup case is one rename away.
    assert list(data_dir.glob("soapbot.db.pre-restore-*"))


def test_restore_refuses_a_newer_schema(tmp_path: Path) -> None:
    restore = _load_script("restore")
    archive = tmp_path / "future.zip"
    with zipfile.ZipFile(archive, "w") as zf:
        zf.writestr(
            "manifest.json",
            json.dumps({"schema_version": 99, "files": [], "created_at": 0}),
        )

    with pytest.raises(restore.RestoreError, match="schema_version"):
        restore.restore(archive, data_dir=tmp_path / "d", config_dir=tmp_path / "c")


def test_restore_refuses_a_traversing_entry(tmp_path: Path) -> None:
    restore = _load_script("restore")
    archive = tmp_path / "evil.zip"
    with zipfile.ZipFile(archive, "w") as zf:
        zf.writestr("manifest.json", json.dumps({"schema_version": 1, "files": []}))
        zf.writestr("../../evil.txt", "x")

    with pytest.raises(restore.RestoreError, match="越界"):
        restore.restore(archive, data_dir=tmp_path / "d", config_dir=tmp_path / "c")
    assert not (tmp_path.parent / "evil.txt").exists()


def _rebuild(source: Path, target: Path, replace: dict[str, bytes]) -> None:
    with zipfile.ZipFile(source) as src, zipfile.ZipFile(target, "w") as dst:
        for name in src.namelist():
            dst.writestr(name, replace.get(name, src.read(name)))


def test_backup_manifest_carries_per_file_checksums(tmp_path: Path) -> None:
    backup = _load_script("backup")
    data_dir, config_dir = tmp_path / "data", tmp_path / "config"
    _make_db(data_dir / "soapbot.db", "x")
    config_dir.mkdir()
    (config_dir / "adapters.yaml").write_text("adapters: []\n", encoding="utf-8")

    archive = tmp_path / "b.zip"
    backup.build(data_dir, config_dir, archive)

    with zipfile.ZipFile(archive) as zf:
        manifest = json.loads(zf.read("manifest.json"))
    assert manifest["format"] == backup.ARCHIVE_FORMAT
    assert set(manifest["checksums"]) == {"data/soapbot.db", "config/adapters.yaml"}


def test_restore_refuses_an_archive_whose_file_was_replaced(tmp_path: Path) -> None:
    """A zip CRC proves the byte was not corrupted, not that it is the right file.

    Config is what gets restored — a swapped ``adapters.yaml`` re-points the bot at an
    attacker's adapter. So the manifest's sha256 is checked, and nothing is written when
    it does not match.
    """
    backup = _load_script("backup")
    restore = _load_script("restore")
    data_dir, config_dir = tmp_path / "data", tmp_path / "config"
    _make_db(data_dir / "soapbot.db", "before")
    config_dir.mkdir()
    (config_dir / "adapters.yaml").write_text("adapters: []\n", encoding="utf-8")

    archive = tmp_path / "b.zip"
    backup.build(data_dir, config_dir, archive)

    tampered = tmp_path / "tampered.zip"
    _rebuild(archive, tampered, {"config/adapters.yaml": b"adapters: [evil]\n"})

    with pytest.raises(restore.RestoreError, match="校验失败"):
        restore.restore(tampered, data_dir=data_dir, config_dir=config_dir)
    assert (config_dir / "adapters.yaml").read_text(encoding="utf-8") == "adapters: []\n"


def test_restore_refuses_a_corrupt_database_before_replacing(tmp_path: Path) -> None:
    """Checksums can be right and the database still unusable.

    The staged copy is opened and run through ``PRAGMA integrity_check`` *before* the
    live database is moved aside; otherwise the failure surfaces at startup, with the
    working file already renamed.
    """
    import hashlib

    backup = _load_script("backup")
    restore = _load_script("restore")
    data_dir, config_dir = tmp_path / "data", tmp_path / "config"
    _make_db(data_dir / "soapbot.db", "keep-me")
    config_dir.mkdir()

    archive = tmp_path / "b.zip"
    backup.build(data_dir, config_dir, archive)

    garbage = b"SQLite format 3\x00" + b"\x00" * 200
    with zipfile.ZipFile(archive) as zf:
        manifest = json.loads(zf.read("manifest.json"))
    manifest["checksums"]["data/soapbot.db"] = hashlib.sha256(garbage).hexdigest()

    broken = tmp_path / "broken.zip"
    _rebuild(
        archive,
        broken,
        {"data/soapbot.db": garbage, "manifest.json": json.dumps(manifest).encode("utf-8")},
    )

    with pytest.raises(restore.RestoreError, match=r"完整性|无法打开"):
        restore.restore(broken, data_dir=data_dir, config_dir=config_dir)
    assert _notes(data_dir / "soapbot.db") == ["keep-me"]
    assert not list(data_dir.glob("soapbot.db.pre-restore-*")), "失败时不应挪走原库"
