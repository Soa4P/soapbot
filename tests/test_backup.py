"""Application-level backup/restore: roundtrip, integrity, rotation, traversal.

The roundtrip test carries the same insight as its dsh-backup reference: a test
that only asserts "the file came back" passes just as well when the restore was
a no-op — so it writes a marker AFTER the backup and proves the restore removed
it (the restore returned the *backed-up* state, not the accidental current one).
"""

from __future__ import annotations

import sqlite3
import sys
import tarfile
from pathlib import Path

import pytest

from soapbot.backup import (
    BACKUP_DIR_NAME,
    BackupError,
    create_backup,
    list_backups,
    restore_backup,
    rotate_backups,
    verify_backup,
)


@pytest.fixture
def data_dir(tmp_path: Path) -> Path:
    """A data directory shaped like a real one: db, key material, config, plugins."""
    d = tmp_path / "data"
    (d / "config").mkdir(parents=True)
    (d / "plugins" / "demo").mkdir(parents=True)
    (d / "secret.key").write_text("key-material", encoding="utf-8")
    (d / "config" / "providers.yaml").write_text("providers: []", encoding="utf-8")
    (d / "plugins" / "demo" / "main.py").write_text("# demo", encoding="utf-8")
    _real_db(d / "soapbot.db")
    return d


def _real_db(path: Path) -> None:
    conn = sqlite3.connect(str(path))
    try:
        conn.execute("CREATE TABLE IF NOT EXISTS marker (v TEXT)")
        conn.commit()
    finally:
        conn.close()


def test_roundtrip_restore_returns_the_backed_up_state(data_dir: Path, tmp_path: Path) -> None:
    """备份 → 再写一个 marker → 恢复 → marker 必须消失（恢复的是备份态，不是碰巧的现态）。"""
    _real_db(data_dir / "soapbot.db")
    archive = create_backup(data_dir)

    conn = sqlite3.connect(str(data_dir / "soapbot.db"))
    try:
        conn.execute("INSERT INTO marker VALUES ('post-backup')")
        conn.commit()
    finally:
        conn.close()

    report = restore_backup(archive, data_dir, keep=3)
    assert report["restored"] is True
    assert report["pre_restore_snapshot"].startswith("soapbot-backup-")

    check = sqlite3.connect(str(data_dir / "soapbot.db"))
    try:
        rows = check.execute("SELECT v FROM marker").fetchall()
    finally:
        check.close()
    assert rows == [], "post-backup marker survived the restore"


def test_backup_captures_keys_config_and_plugins(data_dir: Path) -> None:
    _real_db(data_dir / "soapbot.db")
    archive = create_backup(data_dir)
    with tarfile.open(archive) as tar:
        members = tar.getnames()
    assert "soapbot.db" in members
    assert "secret.key" in members
    assert "config/providers.yaml" in members
    assert "plugins/demo/main.py" in members
    assert not any(m.startswith(BACKUP_DIR_NAME) for m in members), "backups 不递归"


def test_live_wal_database_is_consistent(data_dir: Path) -> None:
    """在线备份 API：未 checkpoint 的 WAL 内容也进归档。"""
    conn = sqlite3.connect(str(data_dir / "soapbot.db"))
    try:
        conn.execute("INSERT INTO marker VALUES ('wal-write')")
        conn.commit()  # 留在 WAL 里，不 checkpoint
    finally:
        conn.close()

    archive = create_backup(data_dir)
    staging = data_dir / BACKUP_DIR_NAME / "inspect"
    staging.mkdir()
    with tarfile.open(archive) as tar:
        tar.extract("soapbot.db", staging)
    check = sqlite3.connect(str(staging / "soapbot.db"))
    try:
        rows = check.execute("SELECT v FROM marker").fetchall()
    finally:
        check.close()
    assert rows == [("wal-write",)]


def test_verify_detects_tampering(data_dir: Path) -> None:
    _real_db(data_dir / "soapbot.db")
    archive = create_backup(data_dir)
    verify_backup(archive)  # 完整时通过
    archive.write_bytes(archive.read_bytes() + b"tampered")
    with pytest.raises(BackupError, match="digest mismatch"):
        verify_backup(archive)


def test_rotation_keeps_n(data_dir: Path) -> None:
    for _ in range(5):
        create_backup(data_dir, keep=3)
    backups = data_dir / BACKUP_DIR_NAME
    archives = list(backups.glob("soapbot-backup-*.tar.gz"))
    sidecars = list(backups.glob("*.sha256"))
    assert len(archives) == 3
    assert len(sidecars) == 3
    removed = rotate_backups(backups, keep=1)
    assert len(removed) == 2
    assert len(list(backups.glob("*.tar.gz"))) == 1


def test_restore_dry_run_touches_nothing(data_dir: Path, tmp_path: Path) -> None:
    _real_db(data_dir / "soapbot.db")
    archive = create_backup(data_dir)
    before = sorted(p.name for p in data_dir.rglob("*"))
    report = restore_backup(archive, data_dir, dry_run=True)
    assert report["dry_run"] is True
    assert report["members"] > 0
    after = sorted(p.name for p in data_dir.rglob("*"))
    assert before == after, "dry-run 改动了数据目录"


def test_restore_refuses_escaping_members(data_dir: Path, tmp_path: Path) -> None:
    _real_db(data_dir / "soapbot.db")
    create_backup(data_dir)
    evil = tmp_path / "evil.tar.gz"
    with tarfile.open(evil, "w:gz") as tar:
        payload = b"owned"
        import io
        info = tarfile.TarInfo("../escape.txt")
        info.size = len(payload)
        tar.addfile(info, io.BytesIO(payload))
    import hashlib as _hl
    evil.with_suffix(evil.suffix + ".sha256").write_text(
        _hl.sha256(evil.read_bytes()).hexdigest() + "  evil.tar.gz\n", encoding="utf-8")
    with pytest.raises(BackupError, match="escapes"):
        restore_backup(evil, data_dir)


def test_list_backups_newest_first_with_digest(data_dir: Path) -> None:
    _real_db(data_dir / "soapbot.db")
    first = create_backup(data_dir)
    second = create_backup(data_dir)
    entries = list_backups(data_dir / BACKUP_DIR_NAME)
    assert [e["name"] for e in entries] == [second.name, first.name]
    assert all(isinstance(e["sha256"], str) and len(e["sha256"]) == 64 for e in entries)


@pytest.mark.skipif(sys.platform == "win32", reason="POSIX mode bits")
def test_archive_and_sidecar_are_owner_only(data_dir: Path) -> None:
    """归档含 secret.key——世界可读的备份 = 主密钥公开（S-DEP-06 同款缺口）。"""
    import stat as stat_module

    archive = create_backup(data_dir)
    assert archive.parent.stat().st_mode & 0o777 == 0o700
    assert archive.stat().st_mode & 0o777 == 0o600
    sidecar = archive.with_suffix(archive.suffix + ".sha256")
    assert sidecar.stat().st_mode & 0o777 == 0o600
    # 目录位不再包含任何 world/group 写或读位
    assert not stat_module.S_IRWXO & archive.parent.stat().st_mode
