"""Application-level backup and restore for the data directory.

Deploy-level snapshots (``deploy_remote.py --backup``) tar the whole docker
volume — a plausible-size file is all they promise, and a raw tar of a running
WAL database can capture it mid-write. This module is the application layer:

* the database goes through SQLite's **online backup API**, so the archive holds
  a consistent snapshot even while the service is running and writing;
* every archive gets a SHA-256 sidecar — restore verifies what it opens;
* restore takes an automatic **pre-restore snapshot** first, supports
  ``--dry-run``, and refuses archive members that escape the target directory
  (same traversal discipline as the plugin installer).

Storage layout: ``<data_dir>/backups/soapbot-backup-<ts>.tar.gz`` plus
``.sha256`` sidecars, rotated to the N most recent.
"""

from __future__ import annotations

import hashlib
import sqlite3
import tarfile
from pathlib import Path
from typing import Any

#: The database file name inside the data directory.
DB_NAME = "soapbot.db"

#: Directory name (inside the data directory) where backups land. Excluded from
#: every backup, or backups would recurse into themselves.
BACKUP_DIR_NAME = "backups"

#: How many archives (counting sidecars separately) rotation keeps by default.
DEFAULT_KEEP = 7


class BackupError(RuntimeError):
    """A backup or restore was rejected; the message is operator-facing."""


def _now_stamp() -> str:
    """Second resolution plus milliseconds: two backups in the same second must
    not share a name (the second would silently overwrite the first)."""
    import datetime as dt

    now = dt.datetime.now()
    return now.strftime("%Y%m%d-%H%M%S") + f"-{now.microsecond // 1000:03d}"


def _copy_tree(src: Path, dest: Path) -> list[str]:
    """Copy ``src``'s tree under ``dest``, excluding the backups directory.

    Returns the relative paths copied. Symlinks are skipped: a symlink inside
    the data directory could point anywhere, and an archive that follows it
    silently grows a traversal surface.
    """
    copied: list[str] = []
    for path in sorted(src.rglob("*")):
        rel = path.relative_to(src)
        if path.is_symlink():
            continue
        if rel.parts and rel.parts[0] == BACKUP_DIR_NAME:
            continue
        target = dest / rel
        if path.is_dir():
            target.mkdir(parents=True, exist_ok=True)
        elif path.is_file():
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(path.read_bytes())
            copied.append(rel.as_posix())
    return copied


def _snapshot_database(db_path: Path, dest_path: Path) -> None:
    """Consistent copy of a live SQLite database via the online backup API."""
    src = sqlite3.connect(str(db_path))
    try:
        dest = sqlite3.connect(str(dest_path))
        try:
            src.backup(dest)
        finally:
            dest.close()
    finally:
        src.close()


def create_backup(data_dir: Path, out_dir: Path | None = None, *,
                  keep: int = DEFAULT_KEEP) -> Path:
    """Archive the data directory; return the archive path."""
    data_dir = Path(data_dir)
    if not data_dir.is_dir():
        raise BackupError(f"data directory does not exist: {data_dir}")
    out_dir = Path(out_dir) if out_dir else data_dir / BACKUP_DIR_NAME
    out_dir.mkdir(parents=True, exist_ok=True)
    # The archive carries secret.key — it is a credential, not a data file.
    # 0700 on the directory keeps other local users out of the listing.
    import contextlib

    with contextlib.suppress(OSError):  # Windows/limited FS: modes are POSIX-only
        out_dir.chmod(0o700)

    stamp = _now_stamp()
    staging = out_dir / f".staging-{stamp}"
    staging.mkdir()
    try:
        for path in sorted(data_dir.iterdir()):
            name = path.name
            if name == BACKUP_DIR_NAME:
                continue
            if path.is_symlink():
                continue
            if path.is_dir():
                _copy_tree(path, staging / name)
            elif path.is_file():
                if name == DB_NAME:
                    _snapshot_database(path, staging / name)
                elif name.startswith(DB_NAME) and name[len(DB_NAME):] in ("-wal", "-shm"):
                    # The online-backup snapshot already contains these pages; a raw
                    # copy would be a stale WAL that overrides the restored db.
                    continue
                else:
                    staging.joinpath(name).write_bytes(path.read_bytes())

        archive = out_dir / f"soapbot-backup-{stamp}.tar.gz"
        with tarfile.open(archive, "w:gz") as tar:
            for member in sorted(staging.rglob("*")):
                if member.is_file():
                    tar.add(member, arcname=member.relative_to(staging).as_posix())
    finally:
        import shutil
        shutil.rmtree(staging, ignore_errors=True)

    digest = hashlib.sha256(archive.read_bytes()).hexdigest()
    sidecar = archive.with_suffix(archive.suffix + ".sha256")
    sidecar.write_text(f"{digest}  {archive.name}\n", encoding="utf-8")
    # 世界可读的归档 = 主密钥公开（S-DEP-06 的同款缺口）。两侧都收紧到 0600。
    archive.chmod(0o600)
    sidecar.chmod(0o600)
    rotate_backups(out_dir, keep)
    return archive


def list_backups(out_dir: Path) -> list[dict[str, Any]]:
    """Archives with size and recorded digest, newest first."""
    out_dir = Path(out_dir)
    if not out_dir.is_dir():
        return []
    entries: list[dict[str, Any]] = []
    for archive in sorted(out_dir.glob("soapbot-backup-*.tar.gz"), reverse=True):
        sidecar = archive.with_suffix(archive.suffix + ".sha256")
        entries.append({
            "name": archive.name,
            "size": archive.stat().st_size,
            "sha256": sidecar.read_text(encoding="utf-8").split()[0] if sidecar.is_file() else "",
            "modified": archive.stat().st_mtime,
        })
    return entries


def rotate_backups(out_dir: Path, keep: int) -> list[str]:
    """Keep the newest ``keep`` archives (and their sidecars); return removed names."""
    if keep <= 0:
        raise BackupError("keep must be positive")
    removed: list[str] = []
    archives = sorted(Path(out_dir).glob("soapbot-backup-*.tar.gz"))
    for archive in archives[:-keep] if keep < len(archives) else []:
        archive.unlink(missing_ok=True)
        archive.with_suffix(archive.suffix + ".sha256").unlink(missing_ok=True)
        removed.append(archive.name)
    return removed


def verify_backup(archive: Path) -> str:
    """Return the recorded digest after checking it against the archive bytes."""
    archive = Path(archive)
    sidecar = archive.with_suffix(archive.suffix + ".sha256")
    if not sidecar.is_file():
        raise BackupError(f"archive has no sha256 sidecar: {archive.name}")
    recorded = sidecar.read_text(encoding="utf-8").split()[0]
    actual = hashlib.sha256(archive.read_bytes()).hexdigest()
    if recorded != actual:
        raise BackupError(
            "digest mismatch: archive is corrupt or was modified after creation")
    return recorded


def _member_paths(archive: Path) -> list[str]:
    """Member names after rejecting anything that escapes the extraction root."""
    bad: list[str] = []
    names: list[str] = []
    with tarfile.open(archive, "r:gz") as tar:
        for member in tar.getmembers():
            if not member.isfile():
                bad.append(f"{member.name} (not a regular file)")
                continue
            name = member.name
            if name.startswith("/") or ".." in Path(name).parts or "\\" in name:
                bad.append(f"{name} (escapes the extraction root)")
                continue
            names.append(name)
    if bad:
        raise BackupError("archive rejected: " + "; ".join(bad[:5]))
    return names


def restore_backup(archive: Path, data_dir: Path, *,
                   dry_run: bool = False, keep: int = DEFAULT_KEEP) -> dict:
    """Verify, (optionally) snapshot the current state, then extract.

    The service should be stopped for a restore of the live database; the
    pre-restore snapshot exists so a botched restore is itself reversible.
    Returns a report dict; ``dry_run`` touches nothing.
    """
    archive = Path(archive)
    data_dir = Path(data_dir)
    if not archive.is_file():
        raise BackupError(f"archive does not exist: {archive}")
    verify_backup(archive)
    names = _member_paths(archive)

    report: dict[str, object] = {
        "archive": archive.name,
        "members": len(names),
        "target": str(data_dir),
    }
    if dry_run:
        report["dry_run"] = True
        report["would_snapshot"] = f"soapbot-backup-{_now_stamp()} (pre-restore)"
        return report

    pre_restore = create_backup(data_dir, keep=keep)
    report["pre_restore_snapshot"] = pre_restore.name

    with tarfile.open(archive, "r:gz") as tar:
        for member in tar.getmembers():
            target = data_dir / member.name
            target.parent.mkdir(parents=True, exist_ok=True)
            with tar.extractfile(member) as src:  # type: ignore[union-attr]
                target.write_bytes(src.read())
    for stale in ("soapbot.db-wal", "soapbot.db-shm"):
        # A WAL left from the *current* database would be replayed over the restored
        # file on next open, silently resurrecting pre-restore writes.
        stale_path = data_dir / stale
        if stale_path.is_file():
            stale_path.unlink()
    report["restored"] = True
    return report
