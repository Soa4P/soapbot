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


def test_readyz_reports_ready_when_the_data_dir_is_writable(
    client: TestClient, tmp_path: Path
) -> None:
    response = client.get("/readyz")
    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "ok"
    assert body["problems"] == []
    # The probe file must not survive its own check.
    assert not list(tmp_path.glob(".readyz-*"))


def test_readyz_fails_when_the_data_dir_cannot_be_created(
    client: TestClient, tmp_path: Path, monkeypatch
) -> None:
    """A file where the data directory should be is the cheapest reliable way to make
    mkdir fail on every platform, including Windows where chmod proves nothing."""
    blocked = tmp_path / "blocked"
    blocked.write_text("not a directory", encoding="utf-8")
    monkeypatch.setattr(settings, "data_dir", blocked)

    response = client.get("/readyz")
    assert response.status_code == 503
    assert response.json()["status"] == "unavailable"
    assert any("data directory" in p for p in response.json()["problems"])


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
    assert any("database not usable" in p for p in body["problems"])
    # /readyz is unauthenticated; the driver message can carry a path.
    assert "disk I/O error" not in response.text


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

    monkeypatch.setattr(app_module, "get_startup_errors", lambda: ["adapter qq is offline"])

    response = client.get("/readyz")
    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "ok"
    assert body["degraded"] is True
    assert body["startup_errors"] == ["adapter qq is offline"]


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
