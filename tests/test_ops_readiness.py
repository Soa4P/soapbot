"""Operational surface: probes a load balancer uses, and backup/restore.

The backup test deliberately mutates the database between backup and restore. A test
that only asserts "the file came back" passes just as well when the archive captured
the pre-write state by accident, which is exactly the WAL bug the backup API is there
to prevent.
"""

from __future__ import annotations

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
