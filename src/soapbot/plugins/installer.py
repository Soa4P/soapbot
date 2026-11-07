"""Install a plugin package from an uploaded zip.

The security model here is that **installation is not approval**. This module only
lands bytes on disk and reports what the manifest claims; it never writes an approval
record. If it did, uploading a package would be enough to obtain every capability the
package asks for, and the approval screen — the one place a human is supposed to look
at capability changes — would be decorative.

Each check below exists because of a specific way a package can be hostile:

===================================  =============================================
attack                               defence
===================================  =============================================
``../../etc/cron.d/x``               every extracted path must stay under the target
symlink pointing outside the tree     symlink entries are rejected outright
zip bomb (small file, huge output)    streamed byte counter, not the header's claim
thousands of tiny files               entry-count cap before extraction
manifest swapped after review         digest is recomputed from the bytes written
half-installed directory after error  extract to a staging dir, move into place last
===================================  =============================================
"""

from __future__ import annotations

import logging
import shutil
import uuid
import zipfile
from collections.abc import Mapping
from dataclasses import dataclass, field
from pathlib import Path, PurePosixPath

from soapbot.plugins.loader import PluginLoader
from soapbot.plugins.manifest import (
    MANIFEST_ALT_FILENAME,
    MANIFEST_FILENAME,
    ManifestError,
    PluginManifest,
    block_key,
)

logger = logging.getLogger(__name__)

#: A plugin package is source code; 50 MB is already generous and keeps an uploaded
#: file from becoming a memory problem before it is even inspected.
MAX_ARCHIVE_BYTES = 50 * 1024 * 1024

#: Uncompressed total. The ratio against MAX_ARCHIVE_BYTES is the bomb defence.
MAX_UNCOMPRESSED_BYTES = 200 * 1024 * 1024

MAX_ENTRIES = 500

#: Zip local-file header, empty archive, and spanned marker. Checking the bytes is
#: cheaper than handing a 50 MB blob of anything-else to zipfile, and it rejects a
#: renamed executable before it reaches any parser.
_ZIP_MAGIC = (b"PK\x03\x04", b"PK\x05\x06", b"PK\x07\x08")

#: A plugin package is source code and small assets. Executables, shared objects,
#: shell scripts and archives-within-archives have no place in one. Files with no
#: suffix (LICENSE, Makefile) are allowed — only a *known* suffix is judged.
_ALLOWED_SUFFIXES = frozenset(
    {
        ".py", ".pyi", ".yaml", ".yml", ".json", ".md", ".txt", ".toml",
        ".ini", ".cfg", ".csv", ".example", ".gitignore",
        ".png", ".jpg", ".jpeg", ".gif", ".svg", ".webp", ".ico",
        ".css", ".js", ".ts", ".html", ".wav", ".mp3", ".ogg",
    }
)

_ZIP_SYMLINK_MODE = 0o120000


class InstallError(RuntimeError):
    """A package was rejected. The message is shown to the operator verbatim."""


@dataclass(slots=True)
class InstallResult:
    name: str
    version: str
    digest: str
    capabilities: list[str] = field(default_factory=list)
    path: str = ""
    replaced: bool = False
    files: int = 0

    def to_dict(self) -> dict:
        return {
            "name": self.name,
            "version": self.version,
            "digest": self.digest,
            "capabilities": list(self.capabilities),
            "path": self.path,
            "replaced": self.replaced,
            "files": self.files,
            # Stated in the payload, not just the docs: the UI renders "installed"
            # next to "approved" and they must never look like the same thing.
            "approved": False,
        }


def install_from_zip(
    data: bytes,
    plugins_dir: Path,
    *,
    host_version: str = "0.1.0",
    blocked: Mapping[str, str] | None = None,
) -> InstallResult:
    """Validate and install a plugin archive. Raises :class:`InstallError`.

    ``blocked`` maps ``"name@version"`` to a reason. It is passed in rather than read here
    so the caller decides which lists apply — the local file always, the community index
    only when it was reachable — and so this function stays free of network state. The
    check runs *after* the manifest is parsed (that is where name and version come from)
    and *before* the commit, so a blocked version never replaces a working install.
    """
    if not data:
        raise InstallError("empty upload")
    if len(data) > MAX_ARCHIVE_BYTES:
        raise InstallError(
            f"archive is {len(data) // 1024} KiB (max {MAX_ARCHIVE_BYTES // 1024} KiB)"
        )
    if not data.startswith(_ZIP_MAGIC):
        raise InstallError("upload is not a zip archive (bad magic bytes)")

    plugins_dir = Path(plugins_dir)
    plugins_dir.mkdir(parents=True, exist_ok=True)
    staging = plugins_dir / f".staging-{uuid.uuid4().hex}"

    try:
        with zipfile.ZipFile(_as_file(data)) as archive:
            _validate_entries(archive)
            root_prefix = _root_prefix(archive)
            _extract(archive, staging, root_prefix)
        manifest = _read_and_check_manifest(staging, host_version)
        # Looked up by canonical key, not by the literal manifest string. The version
        # grammar accepts both `1.0` and `1.0.0`, so a literal lookup lets a package
        # spell its version the other way and walk past a block on the same release.
        reason = (blocked or {}).get(block_key(manifest.name, manifest.version))
        if reason:
            raise InstallError(
                f"{manifest.name} {manifest.version} 已被封禁，拒绝安装：{reason}"
            )
        target = plugins_dir / manifest.name
        replaced = target.exists()
        _commit(staging, target)
    except zipfile.BadZipFile as exc:
        raise InstallError(f"not a zip archive: {exc}") from exc
    except InstallError:
        raise
    except (ManifestError, ValueError) as exc:
        raise InstallError(str(exc)) from exc
    except RuntimeError as exc:
        # zipfile raises this for an encrypted or otherwise unreadable entry.
        # Without this branch it becomes an unhandled 500 with a traceback.
        raise InstallError("archive entries could not be read") from exc
    finally:
        if staging.exists():  # nothing was committed
            shutil.rmtree(staging, ignore_errors=True)

    logger.info(
        "plugin installed name=%s version=%s files=%d replaced=%s digest=%s",
        manifest.name,
        manifest.version,
        sum(1 for _ in target.rglob("*") if _.is_file()),
        replaced,
        manifest.manifest_digest[:12],
    )
    return InstallResult(
        name=manifest.name,
        version=manifest.version,
        digest=manifest.manifest_digest,
        capabilities=sorted(str(c) for c in manifest.capabilities),
        path=str(target),
        replaced=replaced,
        files=sum(1 for _ in target.rglob("*") if _.is_file()),
    )


# ------------------------------------------------------------------ validation
def _as_file(data: bytes):
    import io

    return io.BytesIO(data)


def _validate_entries(archive: zipfile.ZipFile) -> None:
    infos = archive.infolist()
    if len(infos) > MAX_ENTRIES:
        raise InstallError(f"archive has {len(infos)} entries (max {MAX_ENTRIES})")

    declared = 0
    for info in infos:
        name = info.filename
        if not name or name.endswith("/"):
            continue
        _safe_parts(name)  # raises on traversal / absolute paths
        suffix = PurePosixPath(name).suffix.lower()
        if suffix and suffix not in _ALLOWED_SUFFIXES:
            raise InstallError(f"archive contains a disallowed file type: {suffix}")
        if info.flag_bits & 0x1:
            # zipfile raises a bare RuntimeError for an encrypted entry at open()
            # time. Rejecting it here turns a 500 into a normal install refusal.
            raise InstallError(f"archive contains an encrypted entry: {name}")
        mode = (info.external_attr >> 16) & 0o170000
        if mode == _ZIP_SYMLINK_MODE:
            raise InstallError(f"archive contains a symlink: {name}")
        declared += info.file_size
        if declared > MAX_UNCOMPRESSED_BYTES:
            raise InstallError("archive expands beyond the size limit")


def _safe_parts(name: str) -> tuple[str, ...]:
    """Normalise an archive path and reject anything that escapes the target."""
    raw = name.replace("\\", "/")
    if raw.startswith("/") or (len(raw) > 1 and raw[1] == ":"):
        raise InstallError(f"absolute path in archive: {name}")
    parts = tuple(p for p in PurePosixPath(raw).parts if p not in ("", "."))
    if any(p == ".." for p in parts):
        raise InstallError(f"path traversal in archive: {name}")
    return parts


def _root_prefix(archive: zipfile.ZipFile) -> str:
    """Return the single wrapping directory, or ``""`` when files sit at the root.

    Multi-plugin archives and "manifest two levels down" layouts are rejected rather
    than guessed at: guessing is how you install the wrong plugin from a package that
    looked right in the listing.
    """
    tops = {
        _safe_parts(info.filename)[0]
        for info in archive.infolist()
        if info.filename and not info.filename.endswith("/") and _safe_parts(info.filename)
    }
    manifests = [
        info.filename
        for info in archive.infolist()
        if PurePosixPath(info.filename).name in (MANIFEST_FILENAME, MANIFEST_ALT_FILENAME)
    ]
    if len(manifests) != 1:
        raise InstallError(
            f"expected exactly one {MANIFEST_FILENAME}, found {len(manifests)}"
        )
    depth = len(_safe_parts(manifests[0]))
    if depth == 1:
        # A root manifest plus a nested directory would install both trees into
        # one plugin while the approval screen shows only the manifest. Several
        # root-level files are fine; a second *level* is not.
        nested = [
            info.filename
            for info in archive.infolist()
            if info.filename
            and not info.filename.endswith("/")
            and len(_safe_parts(info.filename)) > 1
        ]
        if nested:
            raise InstallError("archive mixes a root manifest with nested entries")
        return ""
    if depth == 2 and len(tops) == 1:
        return _safe_parts(manifests[0])[0]
    raise InstallError("plugin.yaml must be at the archive root or under one directory")


def _extract(archive: zipfile.ZipFile, staging: Path, root_prefix: str) -> None:
    written = 0
    for info in archive.infolist():
        if info.filename.endswith("/"):
            continue
        parts = _safe_parts(info.filename)
        if root_prefix:
            if not parts or parts[0] != root_prefix:
                raise InstallError(f"archive entry outside the plugin directory: {info.filename}")
            parts = parts[1:]
        if not parts:
            continue
        dest = staging.joinpath(*parts)
        # Re-checked after stripping the prefix: a prefix match on strings once let
        # "pkg/../outside" through, and joinpath resolves that happily.
        if staging.resolve() not in dest.resolve().parents:
            raise InstallError(f"path escapes the plugin directory: {info.filename}")
        dest.parent.mkdir(parents=True, exist_ok=True)
        with archive.open(info) as src, open(dest, "wb") as out:
            while chunk := src.read(64 * 1024):
                written += len(chunk)
                if written > MAX_UNCOMPRESSED_BYTES:
                    raise InstallError("archive expands beyond the size limit")
                out.write(chunk)


def _read_and_check_manifest(staging: Path, host_version: str) -> PluginManifest:
    """Parse the manifest the way the loader will, and let *it* compute the digest.

    The digest is what an approval record is keyed on, so it must hash the bytes that
    are on disk after extraction — never a value the package supplied about itself.
    ``read_manifest`` does exactly that, which is why the installer reuses it instead
    of parsing the YAML a second time with a second set of rules.
    """
    loader = PluginLoader(plugins_dir=staging.parent, host_version=host_version)
    manifest = loader.read_manifest(staging)
    if not manifest.manifest_digest:
        raise InstallError("manifest digest could not be computed")
    return manifest


def _commit(staging: Path, target: Path) -> None:
    """Move the staged directory into place, replacing an older version if present."""
    if not target.exists():
        staging.rename(target)
        return

    retired = target.with_name(f".retired-{uuid.uuid4().hex}")
    target.rename(retired)
    try:
        staging.rename(target)
    except OSError:
        # Put the previous version back rather than leaving the operator with none.
        retired.rename(target)
        raise
    shutil.rmtree(retired, ignore_errors=True)
