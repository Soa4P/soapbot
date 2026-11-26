"""The single backup implementation: zip archive + manifest with per-file digests.

History that matters
--------------------
There used to be two implementations. This module wrote ``tar.gz`` with a ``.sha256``
sidecar over ``data/``; ``scripts/backup.py`` wrote ``zip`` + ``manifest.json`` over
``data/`` *and* ``config/``, and it was the one the systemd timer ran. So "the
documented restore procedure" depended on which side produced the archive, and
restoring a timer backup with the CLI (or the reverse) was a support incident waiting
to happen (audit S-DEP-12).

Converged on the zip+manifest format, because that is what production archives
already are: changing the writer would mean changing the timer's rotation, its
``chmod 600`` and the restore runbook all at once. ``scripts/backup.py`` and
``scripts/restore.py`` are now thin shims over this module, so the deployment keeps
its exact command line while there is still exactly one implementation.

Why the archive is a credential
-------------------------------
It carries ``data/secret.key``, ``data/jwt.key`` and ``data/.env``. Every ``enc:``
value in the database is encrypted with that key, so a database-only archive is not a
restore. The file is written 0600 and the enclosing directory 0700, because a
world-readable archive is the master key published (the same gap as S-DEP-06).

What the manifest buys
----------------------
A zip's CRC catches a flipped bit; it does not catch a file replaced with a different
valid one. The manifest records ``sha256`` per member and the database
``schema_version``, so restore can refuse an archive from a newer schema *before*
touching a working install, and can name exactly which member does not match.
"""

from __future__ import annotations

import contextlib
import hashlib
import json
import logging
import os
import sqlite3
import tempfile
import time
import zipfile
from dataclasses import dataclass, field
from pathlib import Path, PurePosixPath
from typing import Any

logger = logging.getLogger(__name__)

#: The database file name inside the data directory.
DB_NAME = "soapbot.db"

#: Directory name (inside the data directory) where backups land. Excluded from
#: every backup, or backups would recurse into themselves.
BACKUP_DIR_NAME = "backups"

#: How many archives rotation keeps by default.
DEFAULT_KEEP = 7

#: Manifest format. Bumped when a reader could get the manifest wrong; restore
#: refuses an archive from the future rather than guessing what a missing key means.
ARCHIVE_FORMAT = 2

MANIFEST_NAME = "manifest.json"

#: Ceiling for a single member read into memory during verification or staging (audit
#: S-DEP-18). A backup archive is operator-supplied, which means it is *not* trusted:
#: a zip can declare a multi-gigabyte member and the old code did ``handle.read(name)``
#: — the restore process allocated it, and an archive chosen to exhaust memory could not
#: be diagnosed because the process was gone. Half a gigabyte is far above a real
#: database and far below what makes a restore host swap.
MAX_MEMBER_BYTES = 512 * 1024 * 1024

#: The manifest is a few kilobytes of JSON; anything larger is a mistake or an attack.
MAX_MANIFEST_BYTES = 8 * 1024 * 1024

#: Members that must come back *with* the database. Keys are what makes an ``enc:``
#: value readable; ``.env`` holds the master-key reference and the panel's settings.
DATA_SIBLINGS = ("secret.key", "jwt.key", ".env")

#: Member roots restore is willing to write. An allowlist, not ``data/*``: an archive
#: that could write any path under data/ could plant a file the service later executes.
_ARCHIVE_PREFIXES = ("data/", "config/")


class BackupError(RuntimeError):
    """A backup or restore was rejected; the message is operator-facing."""


@dataclass
class BackupReport:
    path: Path
    files: int = 0
    schema_version: int = 0
    verified: bool = False
    dry_run: bool = False
    pre_restore_snapshot: str = ""
    restored: bool = False
    members: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "path": str(self.path),
            "files": self.files,
            "schema_version": self.schema_version,
            "verified": self.verified,
            "dry_run": self.dry_run,
            "pre_restore_snapshot": self.pre_restore_snapshot,
            "restored": self.restored,
            "members": list(self.members),
        }


def _now_stamp() -> str:
    """Second resolution plus milliseconds: two backups in the same second must not
    share a name (the second would silently overwrite the first)."""
    import datetime as dt

    now = dt.datetime.now()
    return now.strftime("%Y%m%d-%H%M%S") + f"-{now.microsecond // 1000:03d}"


def _sha256_bytes(body: bytes) -> str:
    return hashlib.sha256(body).hexdigest()


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1 << 20), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _schema_version(db_path: Path) -> int:
    """The database's schema version, or 0 when it has none yet.

    Closed explicitly: ``with sqlite3.connect(...)`` commits on exit but does **not**
    close, and on Windows an open handle makes the following unlink of the snapshot
    fail with "file is in use by another process".
    """
    conn = None
    try:
        conn = sqlite3.connect(f"file:{db_path}?mode=ro", uri=True)
        row = conn.execute("SELECT version FROM schema_version LIMIT 1").fetchone()
        return int(row[0]) if row else 0
    except sqlite3.Error:
        return 0
    finally:
        if conn is not None:
            conn.close()


def _snapshot_database(source: Path, destination: Path) -> None:
    """Consistent copy of a live SQLite database via the online backup API.

    Not ``shutil.copy``: in WAL mode the newest committed pages may still live in
    ``-wal``, so a plain copy opens cleanly and is silently missing the last messages.

    The source is opened **read-write**, deliberately. ``mode=ro`` looks safer and is
    wrong here: a WAL database needs write access to its ``-shm`` sidecar to open at
    all, so a read-only connection fails with "unable to open database file" whenever
    the database is WAL and the directory is not writable for us — measured on the
    deployment, where the backup helper mounts the volume ``:ro`` and every run failed
    before this distinction was understood. The backup itself only reads; the mount
    decides what the process can do, and this code runs inside the app container.
    """
    src = sqlite3.connect(f"file:{source}?mode=rw", uri=True)
    try:
        dst = sqlite3.connect(str(destination))
        try:
            src.backup(dst)
        finally:
            dst.close()
    finally:
        src.close()


def _is_excluded(name: str) -> bool:
    """Dotfiles are skipped inside ``config/`` (editor/OS litter); ``.env`` lives under
    data/ and is handled explicitly."""
    return name.startswith(".")


def create_backup(
    data_dir: Path,
    out_dir: Path | None = None,
    *,
    keep: int = DEFAULT_KEEP,
    config_dir: Path | None = None,
    archive_path: Path | None = None,
) -> BackupReport:
    """Archive ``data_dir`` (and ``config_dir`` when given); return a report.

    ``archive_path`` writes to that exact file and skips rotation — that is the
    deployment timer's mode, where ``deploy/backup.sh`` owns naming and retention.
    ``keep=0`` skips rotation for the same reason.
    """
    data_dir = Path(data_dir)
    if not data_dir.is_dir():
        raise BackupError(f"数据目录不存在：{data_dir}")
    if archive_path is not None:
        out = Path(archive_path)
        out.parent.mkdir(parents=True, exist_ok=True)
    else:
        out_dir = Path(out_dir) if out_dir else data_dir / BACKUP_DIR_NAME
        out_dir.mkdir(parents=True, exist_ok=True)
        # The archive carries secret.key — it is a credential, not a data file.
        with contextlib.suppress(OSError):  # POSIX-only; Windows has no mode
            out_dir.chmod(0o700)
        out = out_dir / f"soapbot-backup-{_now_stamp()}.zip"

    tmp_fd, tmp_name = tempfile.mkstemp(suffix=".zip", dir=str(out.parent))
    os.close(tmp_fd)
    tmp_path = Path(tmp_name)

    files: list[str] = []
    checksums: dict[str, str] = {}
    schema_version = 0
    db_path = data_dir / DB_NAME

    try:
        with zipfile.ZipFile(tmp_path, "w", zipfile.ZIP_DEFLATED) as archive:
            if db_path.is_file():
                snapshot = Path(tmp_name + ".db")
                try:
                    _snapshot_database(db_path, snapshot)
                    schema_version = _schema_version(snapshot)
                    body = snapshot.read_bytes()
                    archive.writestr(f"data/{DB_NAME}", body)
                    files.append(f"data/{DB_NAME}")
                    # Hashed from the snapshot, not the live file: the live file keeps
                    # changing, so hashing it would certify bytes that are not here.
                    checksums[f"data/{DB_NAME}"] = _sha256_bytes(body)
                finally:
                    # SQLite leaves ``-shm``/``-wal`` beside a copy it opened. Observed
                    # on the deployment: two stray files per backup left in the output
                    # directory, growing with every run and looking like archives.
                    for leftover in (snapshot, Path(str(snapshot) + "-wal"), Path(str(snapshot) + "-shm")):
                        leftover.unlink(missing_ok=True)

            for name in DATA_SIBLINGS:
                source = data_dir / name
                if not source.is_file():
                    continue
                arcname = f"data/{name}"
                body = source.read_bytes()
                archive.writestr(arcname, body)
                files.append(arcname)
                checksums[arcname] = _sha256_bytes(body)

            # Everything else under data/ (plugin packages, uploaded media, notes) is
            # part of what a restore has to bring back — the tar.gz predecessor archived
            # the whole tree and the CLI documented that promise. The database and key
            # material are already handled above; backups/ is skipped so archives do not
            # recurse, and WAL/SHM are skipped because the snapshot already folded them
            # in (a stale WAL replayed over a restored db resurrects deleted rows).
            handled = {f"data/{DB_NAME}", *(f"data/{name}" for name in DATA_SIBLINGS)}
            for path in sorted(data_dir.rglob("*")):
                if not path.is_file() or path.is_symlink():
                    continue
                relative = path.relative_to(data_dir).as_posix()
                if relative.split("/", 1)[0] == BACKUP_DIR_NAME:
                    continue
                if path.name in (f"{DB_NAME}-wal", f"{DB_NAME}-shm"):
                    continue
                arcname = f"data/{relative}"
                if arcname in handled:
                    continue
                body = path.read_bytes()
                archive.writestr(arcname, body)
                files.append(arcname)
                checksums[arcname] = _sha256_bytes(body)

            if config_dir is not None:
                config_dir = Path(config_dir)
                if config_dir.is_dir():
                    for path in sorted(config_dir.rglob("*")):
                        if not path.is_file() or path.is_symlink() or _is_excluded(path.name):
                            continue
                        arcname = f"config/{path.relative_to(config_dir).as_posix()}"
                        body = path.read_bytes()
                        archive.writestr(arcname, body)
                        files.append(arcname)
                        checksums[arcname] = _sha256_bytes(body)

            manifest = {
                "tool": "soapbot-backup",
                "format": ARCHIVE_FORMAT,
                "created_at": time.time(),
                "schema_version": schema_version,
                "files": files,
                "checksums": checksums,
            }
            archive.writestr(MANIFEST_NAME, json.dumps(manifest, indent=2))

        # mkstemp already created it 0600; the explicit chmod survives a umask that
        # would otherwise widen it, and it lands before the file has a useful name.
        os.chmod(tmp_path, 0o600)
        tmp_path.replace(out)
    except BaseException:
        tmp_path.unlink(missing_ok=True)
        raise

    sidecar = out.with_suffix(out.suffix + ".sha256")
    with contextlib.suppress(OSError):
        digest = _sha256_file(out)
        # Two lines: the plain digest (interoperable with `sha256sum -c`) and a MAC keyed
        # by the master key. The digest alone proves nothing against someone who can write
        # the directory — they rewrite the archive and the sidecar together (S-DEP-13).
        lines = [f"{digest}  {out.name}"]
        mac = _archive_mac(digest)
        if mac:
            lines.append(f"{SIDECAR_MAC_PREFIX}{mac}")
        sidecar.write_text("\n".join(lines) + "\n", encoding="utf-8")
        sidecar.chmod(0o600)

    if archive_path is None and keep > 0:
        rotate_backups(out.parent, keep)
    return BackupReport(path=out, files=len(files), schema_version=schema_version)


def list_backups(out_dir: Path) -> list[dict[str, Any]]:
    """Archives with size and recorded digest, newest first."""
    out_dir = Path(out_dir)
    if not out_dir.is_dir():
        return []
    entries: list[dict[str, Any]] = []
    for archive in sorted(out_dir.glob("soapbot-backup-*.zip"), reverse=True):
        sidecar = archive.with_suffix(archive.suffix + ".sha256")
        entries.append({
            "name": archive.name,
            "size": archive.stat().st_size,
            "sha256": (
                sidecar.read_text(encoding="utf-8").split()[0]
                if sidecar.is_file() else ""
            ),
            "modified": archive.stat().st_mtime,
        })
    return entries


def rotate_backups(out_dir: Path, keep: int) -> list[str]:
    """Keep the newest ``keep`` archives (and sidecars); return removed names."""
    if keep <= 0:
        raise BackupError("keep must be positive")
    removed: list[str] = []
    archives = sorted(Path(out_dir).glob("soapbot-backup-*.zip"))
    for archive in archives[:-keep] if keep < len(archives) else []:
        archive.unlink(missing_ok=True)
        archive.with_suffix(archive.suffix + ".sha256").unlink(missing_ok=True)
        removed.append(archive.name)
    return removed


def _read_member_capped(
    handle: zipfile.ZipFile,
    name: str,
    *,
    limit: int | None = None,
) -> bytes:
    """Read one member, refusing to hold more than ``limit`` bytes of it.

    Two checks, because each catches what the other misses: the declared size in the
    central directory is a *claim* (checked first, so an honest header is rejected before
    any work), and the streamed count bounds what is actually decompressed, so a header
    that understates its payload cannot grow the buffer past the limit either.

    ``limit`` defaults to :data:`MAX_MEMBER_BYTES` *at call time* rather than as a bound
    default: a default argument is evaluated once at import, which would leave the
    constant looking configurable while every call used the original value.
    """
    ceiling = MAX_MEMBER_BYTES if limit is None else limit
    try:
        info = handle.getinfo(name)
    except KeyError as exc:
        raise BackupError(f"归档缺少清单里列出的文件：{name}") from exc
    if info.file_size > ceiling:
        raise BackupError(
            f"归档成员过大，拒绝读入内存：{name}（声明 {info.file_size} 字节，上限 {ceiling}）"
        )
    body = bytearray()
    with handle.open(info) as stream:
        for chunk in iter(lambda: stream.read(1 << 20), b""):
            body.extend(chunk)
            if len(body) > ceiling:
                raise BackupError(f"归档成员解压后超过上限：{name}（上限 {ceiling} 字节）")
    return bytes(body)


def _read_manifest(archive: zipfile.ZipFile) -> dict[str, Any]:
    try:
        raw = _read_member_capped(archive, MANIFEST_NAME, limit=MAX_MANIFEST_BYTES)
    except KeyError as exc:
        raise BackupError("归档里没有 manifest.json，可能不是 soapbot 备份") from exc
    except BackupError as exc:
        raise BackupError(f"manifest.json 无法读取：{exc}") from exc
    try:
        manifest = json.loads(raw.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise BackupError(f"manifest.json 无法解析：{exc}") from exc
    if not isinstance(manifest, dict):
        raise BackupError("manifest.json 结构不正确")
    return manifest


def _safe_member(name: str) -> PurePosixPath:
    path = PurePosixPath(name.replace("\\", "/"))
    if path.is_absolute() or any(part == ".." for part in path.parts):
        raise BackupError(f"归档内路径越界：{name}")
    if not name.startswith(_ARCHIVE_PREFIXES):
        raise BackupError(f"归档里有未声明的成员：{name}")
    return path


SIDECAR_MAC_PREFIX = "hmac-sha256:"


def _archive_mac(digest: str) -> str:
    """MAC over the archive digest, or "" when no master key is available.

    Empty rather than raising: ``backup create`` must work before the bot has ever
    started (backing up a fresh install is a normal operation), and a sidecar without a
    MAC is still useful — it proves integrity, it just cannot prove authenticity.
    """
    try:
        from soapbot.security.crypto import get_secret_box

        return get_secret_box().mac(f"soapbot-backup-v2:{digest}".encode())
    except Exception as exc:  # pragma: no cover - key unavailable / malformed
        logger.warning("no master key for the backup MAC (%s); writing a digest only", exc)
        return ""


def _check_sidecar(archive: Path, *, allow_unverified: bool = False) -> None:
    """Whole-archive integrity and — when recorded — authenticity.

    The digest line catches corruption. The MAC line is what catches *replacement*: an
    attacker who can write the backup directory rewrites the archive and the digest
    together, and the one thing they cannot produce is a MAC under the master key (audit
    S-DEP-13). Archives from before the MAC existed have no such line; they still restore,
    with a warning — refusing them would turn a security fix into data loss.
    """
    sidecar = archive.with_suffix(archive.suffix + ".sha256")
    if not sidecar.is_file():
        logger.warning(
            "backup %s has no .sha256 sidecar: integrity cannot be checked", archive.name
        )
        return
    lines = [
        line.strip()
        for line in sidecar.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]
    recorded = lines[0].split()[0] if lines else ""
    actual = _sha256_file(archive)
    if not recorded or actual != recorded:
        raise BackupError("归档与 .sha256 不一致：备份被修改或损坏")

    mac_line = next((line for line in lines if line.startswith(SIDECAR_MAC_PREFIX)), "")
    if not mac_line:
        logger.warning(
            "backup %s predates the MAC line: integrity checked, authenticity not",
            archive.name,
        )
        return

    expected = mac_line[len(SIDECAR_MAC_PREFIX) :].strip()
    try:
        from soapbot.security.crypto import get_secret_box

        box = get_secret_box()
    except Exception:  # pragma: no cover - key unavailable
        logger.warning("cannot verify the backup MAC: no master key available")
        return
    if box.verify_mac(f"soapbot-backup-v2:{actual}".encode(), expected):
        return
    if allow_unverified:
        logger.warning(
            "backup %s: MAC mismatch ignored (--allow-unverified)", archive.name
        )
        return
    # A rotated master key looks exactly like tampering from here, so the message names
    # both possibilities rather than asserting the alarming one.
    raise BackupError(
        "备份的 HMAC 校验失败：归档或它的 .sha256 被改写，或者主密钥已轮换。"
        "确认来源后可以 --allow-unverified 跳过这一步"
    )


def _peek_manifest(archive: Path) -> dict[str, Any]:
    """Read and structurally validate the manifest without hashing every member.

    Split out because ``restore`` needs the schema version *before* it can decide
    whether hashing is even meaningful: "this archive is from a newer program" is the
    actionable message, and reporting "no checksums" for such an archive would send the
    operator looking in the wrong place.
    """
    try:
        with zipfile.ZipFile(archive) as handle:
            manifest = _read_manifest(handle)
    except zipfile.BadZipFile as exc:
        # A tar.gz from before the convergence lands here. "not a zip" is the whole
        # message an operator needs; a traceback is not.
        raise BackupError(
            "不是 zip 归档：这可能是收敛前的 tar.gz 备份，请用旧版程序恢复"
        ) from exc
    backup_format = int(manifest.get("format") or 1)
    if backup_format > ARCHIVE_FORMAT:
        raise BackupError(
            f"备份格式 version={backup_format} 高于当前程序支持的 {ARCHIVE_FORMAT}；"
            "请先升级程序再恢复"
        )
    return manifest


def _verify_checksums(archive: Path, manifest: dict[str, Any]) -> None:
    checksums = manifest.get("checksums")
    if not isinstance(checksums, dict) or not checksums:
        raise BackupError("manifest.json 里没有 checksums，无法校验备份内容")
    with zipfile.ZipFile(archive) as handle:
        for name, expected in checksums.items():
            body = _read_member_capped(handle, name)
            if _sha256_bytes(body) != expected:
                raise BackupError(
                    f"文件校验失败：{name} 的内容与清单不一致（备份被修改或损坏）"
                )


def verify_backup(archive: Path, *, allow_unverified: bool = False) -> dict[str, Any]:
    """Sidecar, manifest shape and every per-file digest; return the manifest.

    Both layers matter for different attacks: the sidecar covers the archive bytes as
    a whole (including the manifest), while the manifest covers what extraction will
    write. Rewriting every digest to match substituted files passes the per-file check
    and fails the sidecar.
    """
    archive = Path(archive)
    if not archive.is_file():
        raise BackupError(f"备份文件不存在：{archive}")
    _check_sidecar(archive, allow_unverified=allow_unverified)
    manifest = _peek_manifest(archive)
    _verify_checksums(archive, manifest)
    return manifest


def _assert_sqlite_ok(path: Path) -> None:
    """Prove the staged database opens and is internally consistent.

    A truncated or hand-edited file passes every byte-level check and only fails at
    startup, after the working database has already been moved aside.
    """
    conn = None
    try:
        conn = sqlite3.connect(f"file:{path}?mode=ro", uri=True)
        row = conn.execute("PRAGMA integrity_check").fetchone()
    except sqlite3.Error as exc:
        raise BackupError(f"备份中的数据库无法打开：{exc}") from exc
    finally:
        if conn is not None:
            conn.close()
    result = row[0] if row else "no result"
    if result != "ok":
        raise BackupError(f"备份中的数据库完整性检查失败：{result}")


def _install(staged: Path, target: Path) -> None:
    """Copy into place via a sibling temp file, so a rename is the only visible step."""
    target.parent.mkdir(parents=True, exist_ok=True)
    tmp = target.with_name(f".{target.name}.restore-tmp")
    tmp.write_bytes(staged.read_bytes())
    os.replace(tmp, target)


def harden_archives(out_dir: Path) -> dict[str, Any]:
    """Tighten permissions on archives written before the 0600/0700 discipline.

    Upgrading does not fix history: an archive created by the old deployment path is
    world-readable and contains ``secret.key``, ``.env`` and the whole database, so it
    is the master key rather than "just data" (audit S-DEP-06 residual). This makes that
    fix one command instead of a find/xargs invocation an operator has to get right.

    Returns counts so the caller can report what actually changed. Modes are POSIX-only;
    on Windows the call is a no-op that says so rather than pretending.
    """
    out_dir = Path(out_dir)
    report: dict[str, Any] = {
        "directory": str(out_dir),
        "archives": 0,
        "sidecars": 0,
        "supported": True,
    }
    if not out_dir.is_dir():
        report["supported"] = False
        report["reason"] = "目录不存在"
        return report
    if os.name == "nt":
        # NTFS ACLs are the equivalent control and are not what this function touches;
        # saying "done" would leave the operator believing something changed.
        report["supported"] = False
        report["reason"] = "Windows 不使用 POSIX 模式位，请用 icacls 收紧 ACL"
        return report
    with contextlib.suppress(OSError):
        out_dir.chmod(0o700)
    for path in sorted(out_dir.glob("soapbot-*")):
        if path.is_dir():
            continue
        with contextlib.suppress(OSError):
            path.chmod(0o600)
            # `.sha256` sidecars carry the archive digest only, but they are grouped
            # with the archives on purpose: one mode, one rule, nothing to forget.
            if path.suffix == ".sha256":
                report["sidecars"] += 1
            elif path.suffix in (".zip", ".gz"):
                report["archives"] += 1
    return report


def restore_backup(
    archive: Path,
    data_dir: Path,
    *,
    config_dir: Path | None = None,
    with_config: bool = True,
    dry_run: bool = False,
    keep: int = DEFAULT_KEEP,
    allow_unverified: bool = False,
) -> dict[str, Any]:
    """Verify, (optionally) snapshot the current state, then extract.

    Order is the whole point: validate the archive's provenance, then the schema, then
    the member names, then every digest — all **before** a single byte of the live
    install is touched; stage the extraction and prove the database opens; only then
    move the current database aside and write.

    The order is chosen for the operator, too: "from a newer program", "entry escapes
    the target" and "a file was replaced" are different incidents, and each check runs
    before the ones that would mask it with a vaguer message.
    """
    archive = Path(archive)
    data_dir = Path(data_dir)
    if not archive.is_file():
        raise BackupError(f"备份文件不存在：{archive}")
    _check_sidecar(archive, allow_unverified=allow_unverified)
    manifest = _peek_manifest(archive)

    from soapbot.memory.db import SCHEMA_VERSION

    backup_version = int(manifest.get("schema_version") or 0)
    if backup_version > SCHEMA_VERSION:
        raise BackupError(
            f"备份的 schema_version={backup_version} 高于当前程序支持的 {SCHEMA_VERSION}；"
            "请先升级程序再恢复"
        )

    with zipfile.ZipFile(archive) as handle:
        members = [n for n in handle.namelist() if not n.endswith("/") and n != MANIFEST_NAME]
    for name in members:
        _safe_member(name)
    _verify_checksums(archive, manifest)

    report = BackupReport(path=archive, members=members, schema_version=backup_version)
    if dry_run:
        report.dry_run = True
        report.pre_restore_snapshot = f"soapbot-backup-{_now_stamp()}.zip (pre-restore)"
        return report.to_dict()

    if data_dir.is_dir():
        snapshot = create_backup(data_dir, keep=keep, config_dir=config_dir)
        report.pre_restore_snapshot = snapshot.path.name

    restored: list[str] = []
    stamp = time.strftime("%Y%m%d-%H%M%S")
    with (
        zipfile.ZipFile(archive) as handle,
        tempfile.TemporaryDirectory(prefix="soapbot-restore-") as stage_name,
    ):
        stage = Path(stage_name)
        plan: list[tuple[Path, Path, bool]] = []
        for name in members:
            member = _safe_member(name)
            if member.parts[:2] == ("data", DB_NAME):
                target = data_dir / DB_NAME
                staged = stage / DB_NAME
                is_db = True
            elif member.parts[0] == "data" and len(member.parts) > 1:
                relative = Path(*member.parts[1:])
                target = data_dir / relative
                staged = stage / "data" / relative
                is_db = False
            elif member.parts[0] == "config" and with_config and config_dir is not None:
                relative = Path(*member.parts[1:])
                target = Path(config_dir) / relative
                staged = stage / "config" / relative
                is_db = False
            else:
                # Verified but not restorable here (e.g. config under --no-config).
                continue
            staged.parent.mkdir(parents=True, exist_ok=True)
            staged.write_bytes(_read_member_capped(handle, name))
            plan.append((staged, target, is_db))

        for staged, _target, is_db in plan:
            if is_db:
                _assert_sqlite_ok(staged)

        data_dir.mkdir(parents=True, exist_ok=True)
        for staged, target, is_db in plan:
            if is_db and target.exists():
                # with_name, not with_suffix: the latter *replaces* ".db", so the
                # previous copy would land beside the database as "soapbot.pre-…"
                # and nobody would find it.
                target.replace(target.with_name(f"{target.name}.pre-restore-{stamp}"))
            _install(staged, target)
            if target.name in DATA_SIBLINGS:
                # A restored key must not inherit a permissive mode from an archive
                # written where the umask was looser.
                with contextlib.suppress(OSError):
                    os.chmod(target, 0o600)
            restored.append(str(target))

    for stale in (f"{DB_NAME}-wal", f"{DB_NAME}-shm"):
        # A WAL left from the *current* database would be replayed over the restored
        # file on next open, silently resurrecting pre-restore writes.
        stale_path = data_dir / stale
        if stale_path.is_file():
            stale_path.unlink()

    report.files = len(restored)
    report.verified = True
    report.restored = True
    return report.to_dict()
