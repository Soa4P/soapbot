"""Backup/restore: roundtrip, integrity, rotation, traversal, single implementation.

The roundtrip test carries the same insight as its dsh-backup reference: a test that
only asserts "the file came back" passes just as well when the restore was a no-op —
so it writes a marker AFTER the backup and proves the restore removed it (the restore
returned the *backed-up* state, not the accidental current one).

The format is the one the deployment timer already produces (zip + ``manifest.json``),
because that is what production archives are; the tar.gz writer this module used to
have is gone (audit S-DEP-12). Two tests below exist specifically for that migration:
the shim entry points must still accept the deployment's command line, and an archive
written by the old ``scripts/backup.py`` (no extra data/ members) must still restore.
"""

from __future__ import annotations

import hashlib
import io
import json
import sqlite3
import sys
import zipfile
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


def _members(archive: Path) -> list[str]:
    with zipfile.ZipFile(archive) as handle:
        return handle.namelist()


def test_roundtrip_restore_returns_the_backed_up_state(data_dir: Path) -> None:
    """备份 → 再写一个 marker → 恢复 → marker 必须消失（恢复的是备份态，不是碰巧的现态）。"""
    _real_db(data_dir / "soapbot.db")
    report = create_backup(data_dir)
    archive = report.path

    conn = sqlite3.connect(str(data_dir / "soapbot.db"))
    try:
        conn.execute("INSERT INTO marker VALUES ('post-backup')")
        conn.commit()
    finally:
        conn.close()

    restored = restore_backup(archive, data_dir, keep=3)
    assert restored["restored"] is True
    assert restored["pre_restore_snapshot"].startswith("soapbot-backup-")

    check = sqlite3.connect(str(data_dir / "soapbot.db"))
    try:
        rows = check.execute("SELECT v FROM marker").fetchall()
    finally:
        check.close()
    assert rows == [], "post-backup marker survived the restore"


def test_no_stray_sqlite_sidecars_are_left_behind(data_dir: Path) -> None:
    """A snapshot copy leaves ``-wal``/``-shm`` beside it.

    Measured on the deployment: two stray files per backup accumulated in the output
    directory, and they look like archives to anyone listing it.
    """
    create_backup(data_dir)
    leftovers = [p.name for p in (data_dir / BACKUP_DIR_NAME).iterdir() if p.name.endswith(("-wal", "-shm"))]
    assert leftovers == [], leftovers


def test_archive_is_a_zip_with_a_manifest(data_dir: Path) -> None:
    """The converged format: zip + manifest, not tar.gz + sidecar-only."""
    archive = create_backup(data_dir).path
    assert archive.suffix == ".zip"
    members = _members(archive)
    assert "manifest.json" in members
    assert "data/soapbot.db" in members
    assert "data/secret.key" in members
    assert "data/config/providers.yaml" in members
    assert "data/plugins/demo/main.py" in members, "plugins live under data/ and must travel"
    assert not any(m.startswith(f"data/{BACKUP_DIR_NAME}/") for m in members), "backups 不递归"

    with zipfile.ZipFile(archive) as handle:
        manifest = json.loads(handle.read("manifest.json"))
    assert manifest["format"] == 2
    assert isinstance(manifest["schema_version"], int)
    # The manifest is what makes substitution detectable; every listed member is hashed.
    assert set(manifest["checksums"]) == set(manifest["files"])
    assert manifest["checksums"]["data/soapbot.db"] == hashlib.sha256(
        zipfile.ZipFile(archive).read("data/soapbot.db")
    ).hexdigest()


def test_live_wal_database_is_consistent(data_dir: Path) -> None:
    """在线备份 API：未 checkpoint 的 WAL 内容也进归档。"""
    conn = sqlite3.connect(str(data_dir / "soapbot.db"))
    try:
        conn.execute("INSERT INTO marker VALUES ('wal-write')")
        conn.commit()  # 留在 WAL 里，不 checkpoint
    finally:
        conn.close()

    archive = create_backup(data_dir).path
    body = zipfile.ZipFile(archive).read("data/soapbot.db")
    staging = data_dir / BACKUP_DIR_NAME / "inspect"
    staging.mkdir()
    (staging / "soapbot.db").write_bytes(body)
    check = sqlite3.connect(str(staging / "soapbot.db"))
    try:
        rows = check.execute("SELECT v FROM marker").fetchall()
    finally:
        check.close()
    assert rows == [("wal-write",)]


def test_verify_detects_tampering(data_dir: Path) -> None:
    archive = create_backup(data_dir).path
    verify_backup(archive)  # 完整时通过

    # Rewrite the archive with the database substituted but the manifest left intact:
    # a zip CRC would be happy, the manifest must not be. The sidecar is removed so
    # this exercises the *manifest* layer; the next test covers the sidecar layer.
    substituted = b"tampered-database-bytes"
    tampered = archive.with_name("tampered.zip")
    with zipfile.ZipFile(archive) as source, zipfile.ZipFile(tampered, "w") as target:
        for item in source.infolist():
            body = source.read(item.filename)
            if item.filename == "data/soapbot.db":
                body = substituted
            target.writestr(item, body)
    with pytest.raises(BackupError, match=r"不一致|校验失败"):
        verify_backup(tampered)


def test_verify_detects_a_rewritten_manifest(data_dir: Path) -> None:
    """Both checks matter: rewriting the digest to match a substituted file passes the
    per-file check and is caught by the sidecar."""
    archive = create_backup(data_dir).path
    with zipfile.ZipFile(archive) as handle:
        entries = [(item, handle.read(item.filename)) for item in handle.infolist()]
    forged_db = b"not a database"
    rebuilt = archive.with_name("forged.zip")
    with zipfile.ZipFile(rebuilt, "w") as target:
        for item, body in entries:
            if item.filename == "data/soapbot.db":
                body = forged_db
            elif item.filename == "manifest.json":
                manifest = json.loads(body)
                manifest["checksums"]["data/soapbot.db"] = hashlib.sha256(forged_db).hexdigest()
                body = json.dumps(manifest).encode()
            target.writestr(item, body)
    # No sidecar: the per-file check now *passes*, which is exactly why the sidecar
    # exists. With a sidecar copied from the original archive, it fails.
    verify_backup(rebuilt)
    copied_sidecar = rebuilt.with_suffix(rebuilt.suffix + ".sha256")
    copied_sidecar.write_text(
        f"{hashlib.sha256(archive.read_bytes()).hexdigest()}  forged.zip\n", encoding="utf-8"
    )
    with pytest.raises(BackupError, match="sha256"):
        verify_backup(rebuilt)


def test_rotation_keeps_n(data_dir: Path) -> None:
    for _ in range(5):
        create_backup(data_dir, keep=3)
    backups = data_dir / BACKUP_DIR_NAME
    archives = list(backups.glob("soapbot-backup-*.zip"))
    sidecars = list(backups.glob("*.sha256"))
    assert len(archives) == 3
    assert len(sidecars) == 3
    removed = rotate_backups(backups, keep=1)
    assert len(removed) == 2
    assert len(list(backups.glob("*.zip"))) == 1


def test_restore_dry_run_touches_nothing(data_dir: Path) -> None:
    archive = create_backup(data_dir).path
    before = sorted(p.name for p in data_dir.rglob("*"))
    report = restore_backup(archive, data_dir, dry_run=True)
    assert report["dry_run"] is True
    assert report["members"]
    after = sorted(p.name for p in data_dir.rglob("*"))
    assert before == after, "dry-run 改动了数据目录"


def test_restore_refuses_an_archive_with_an_escaping_member(data_dir: Path) -> None:
    """A backup arrives from somewhere else; entries are attacker-influenced input,
    exactly like an uploaded plugin package."""
    archive = create_backup(data_dir).path
    with zipfile.ZipFile(archive) as handle:
        db = handle.read("data/soapbot.db")
    evil = data_dir.parent / "evil.zip"
    checksums = {"data/soapbot.db": hashlib.sha256(db).hexdigest()}
    with zipfile.ZipFile(evil, "w") as handle:
        handle.writestr("data/soapbot.db", db)
        handle.writestr("data/../../escape.txt", b"owned")
        handle.writestr(
            "manifest.json",
            json.dumps(
                {
                    "tool": "soapbot-backup",
                    "format": 2,
                    "created_at": 0,
                    "schema_version": 0,
                    "files": ["data/soapbot.db", "data/../../escape.txt"],
                    "checksums": checksums,
                }
            ),
        )
    with pytest.raises(BackupError, match=r"越界|路径"):
        restore_backup(evil, data_dir)


def test_restore_refuses_an_undeclared_member_root(data_dir: Path) -> None:
    archive = create_backup(data_dir).path
    with zipfile.ZipFile(archive) as handle:
        entries = [(item, handle.read(item.filename)) for item in handle.infolist()]
    sneaky = data_dir.parent / "sneaky.zip"
    with zipfile.ZipFile(sneaky, "w") as handle:
        for item, body in entries:
            handle.writestr(item, body)
        handle.writestr("etc/cron.d/backdoor", b"* * * * * root id")
    with pytest.raises(BackupError, match="未声明"):
        restore_backup(sneaky, data_dir)


def test_restore_accepts_an_archive_from_the_deployment_shim_shape(data_dir: Path) -> None:
    """A zip produced by the timer's shape (db + keys + config only, no plugins dir)
    must still restore: that is what exists on disk from before this change."""
    archive = data_dir.parent / "timer-shape.zip"
    body = (data_dir / "soapbot.db").read_bytes()
    checksums = {
        "data/soapbot.db": hashlib.sha256(body).hexdigest(),
        "data/secret.key": hashlib.sha256(b"key-material").hexdigest(),
    }
    with zipfile.ZipFile(archive, "w") as handle:
        handle.writestr("data/soapbot.db", body)
        handle.writestr("data/secret.key", b"key-material")
        handle.writestr(
            "manifest.json",
            json.dumps(
                {
                    "tool": "soapbot-backup",
                    "format": 2,
                    "created_at": 0,
                    "schema_version": 0,
                    "files": list(checksums),
                    "checksums": checksums,
                }
            ),
        )
    restored = restore_backup(archive, data_dir)
    assert restored["restored"] is True
    assert (data_dir / "secret.key").read_text(encoding="utf-8") == "key-material"


def test_restore_without_config_leaves_config_alone(data_dir: Path, tmp_path: Path) -> None:
    config = tmp_path / "outside-config"
    config.mkdir()
    (config / "providers.yaml").write_text("changed-after-backup: true", encoding="utf-8")
    archive = create_backup(data_dir, config_dir=config).path
    (config / "providers.yaml").write_text("current: true", encoding="utf-8")
    restore_backup(archive, data_dir, config_dir=config, with_config=False)
    assert (config / "providers.yaml").read_text(encoding="utf-8") == "current: true"


def test_schema_from_the_future_is_refused(data_dir: Path) -> None:
    archive = create_backup(data_dir).path
    with zipfile.ZipFile(archive) as handle:
        entries = [(item, handle.read(item.filename)) for item in handle.infolist()]
    rebuilt = data_dir.parent / "from-the-future.zip"
    with zipfile.ZipFile(rebuilt, "w") as handle:
        for item, body in entries:
            if item.filename == "manifest.json":
                manifest = json.loads(body)
                manifest["schema_version"] = 9999
                body = json.dumps(manifest).encode()
            handle.writestr(item, body)
    with pytest.raises(BackupError, match="schema_version"):
        restore_backup(rebuilt, data_dir)


def test_list_backups_newest_first_with_digest(data_dir: Path) -> None:
    first = create_backup(data_dir).path
    second = create_backup(data_dir).path
    entries = list_backups(data_dir / BACKUP_DIR_NAME)
    assert [e["name"] for e in entries] == [second.name, first.name]
    assert all(isinstance(e["sha256"], str) and len(e["sha256"]) == 64 for e in entries)


@pytest.mark.skipif(sys.platform == "win32", reason="POSIX mode bits")
def test_archive_and_sidecar_are_owner_only(data_dir: Path) -> None:
    """归档含 secret.key——世界可读的备份 = 主密钥公开（S-DEP-06 同款缺口）。"""
    import stat as stat_module

    archive = create_backup(data_dir).path
    assert archive.parent.stat().st_mode & 0o777 == 0o700
    assert archive.stat().st_mode & 0o777 == 0o600
    sidecar = archive.with_suffix(archive.suffix + ".sha256")
    assert sidecar.stat().st_mode & 0o777 == 0o600
    # 目录位不再包含任何 world/group 写或读位
    assert not stat_module.S_IRWXO & archive.parent.stat().st_mode


# ------------------------------------------------------- deployment shim contract


def test_the_backup_shim_writes_the_exact_file_the_timer_names(tmp_path: Path) -> None:
    """``deploy/backup.sh`` passes ``--out`` as a *file path* and owns retention.
    The shim must honour both without importing the CLI's directory semantics."""
    import importlib.util

    module_path = Path(__file__).resolve().parents[1] / "scripts" / "backup.py"
    spec = importlib.util.spec_from_file_location("deploy_backup_shim", module_path)
    assert spec and spec.loader
    shim = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(shim)

    data = tmp_path / "data"
    data.mkdir()
    _real_db(data / "soapbot.db")
    (data / "secret.key").write_text("key-material", encoding="utf-8")
    out = tmp_path / "out" / "soapbot-20260101-000000.zip"
    assert shim.main(["--data-dir", str(data), "--config-dir", str(data), "--out", str(out)]) == 0
    assert out.is_file()
    assert zipfile.is_zipfile(out)
    # Retention belongs to the timer: the shim must not rotate anything away.
    assert list(out.parent.glob("*.sha256")), "sidecar written beside the archive"


def test_the_restore_shim_reports_a_bad_archive_without_writing(tmp_path: Path, capsys) -> None:
    import importlib.util

    module_path = Path(__file__).resolve().parents[1] / "scripts" / "restore.py"
    spec = importlib.util.spec_from_file_location("deploy_restore_shim", module_path)
    assert spec and spec.loader
    shim = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(shim)

    data = tmp_path / "data"
    data.mkdir()
    _real_db(data / "soapbot.db")
    bogus = tmp_path / "bogus.zip"
    with zipfile.ZipFile(bogus, "w") as handle:
        handle.writestr("data/soapbot.db", b"nope")
    code = shim.main([str(bogus), "--data-dir", str(data), "--config-dir", str(data)])
    assert code == 1
    captured = capsys.readouterr()
    assert "恢复失败" in captured.out
    assert "没有替换任何文件" in captured.out


def test_a_tar_gz_archive_is_refused_with_a_readable_message(tmp_path: Path) -> None:
    """Convergence means one reader. A pre-convergence tar.gz must fail with a message
    an operator can act on, not a BadZipFile traceback."""
    import tarfile

    archive = tmp_path / "old.tar.gz"
    with tarfile.open(archive, "w:gz") as tar:
        payload = b"data"
        info = tarfile.TarInfo("soapbot.db")
        info.size = len(payload)
        tar.addfile(info, io.BytesIO(payload))
    with pytest.raises(BackupError, match=r"tar\.gz"):
        verify_backup(archive)


def test_a_missing_checksums_key_is_refused(data_dir: Path) -> None:
    """A manifest without digests would let restore write anything it names."""
    archive = create_backup(data_dir).path
    with zipfile.ZipFile(archive) as handle:
        entries = [(item, handle.read(item.filename)) for item in handle.infolist()]
    rebuilt = data_dir.parent / "no-checksums.zip"
    with zipfile.ZipFile(rebuilt, "w") as handle:
        for item, body in entries:
            if item.filename == "manifest.json":
                manifest = json.loads(body)
                manifest.pop("checksums", None)
                body = json.dumps(manifest).encode()
            handle.writestr(item, body)
    with pytest.raises(BackupError, match="checksums"):
        verify_backup(rebuilt)
