"""Write secret files with permissions narrowed as far as the platform allows.

Why this is a module rather than three copies
--------------------------------------------
Three places write key material: the Fernet master key (``security.crypto``), the JWT
signing key and the one-time bootstrap token. Each of them previously (or would have)
re-derived the same ``os.open(..., 0o600)`` dance, and each would have independently
discovered the same platform trap described below.

The trap
--------
On POSIX the mode passed to ``os.open`` is masked by the process umask, so a file can be
created group-readable even though ``0o600`` was requested — which is why the mode is
re-applied with ``chmod`` afterwards. On Windows, ``os.chmod`` only toggles the
read-only attribute; group and other bits are not a thing, and the real access control
is the inherited NTFS ACL of the parent directory. Silently claiming "mode 0600" there
would be exactly the kind of security theatre this project tries to avoid, so the
limitation is logged once and reported by ``soapbot doctor``.
"""

from __future__ import annotations

import logging
import os
from pathlib import Path

logger = logging.getLogger(__name__)

POSIX = os.name == "posix"
_warned_about_platform = False


def write_private_file(path: Path, data: bytes, *, what: str = "secret") -> None:
    """Create or replace ``path`` with ``data``, restricting access where possible.

    The file is opened with ``0o600`` *at creation time* so it is never briefly
    world-readable on a permissive umask, then narrowed again explicitly.
    """
    path.parent.mkdir(parents=True, exist_ok=True)
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    try:
        os.write(fd, data)
    finally:
        os.close(fd)
    tighten(path, what=what)


def tighten(path: Path, *, what: str = "secret") -> None:
    """Re-apply owner-only permissions, reporting when that is not enforceable."""
    global _warned_about_platform

    if POSIX:
        try:
            os.chmod(path, 0o600)
        except OSError:  # pragma: no cover - exotic filesystem
            logger.warning("could not tighten permissions on %s", path)
        return

    if not _warned_about_platform:
        _warned_about_platform = True
        # Logged once per process: repeating it for every key would be noise, and the
        # operator only needs to learn it once to decide whether to rely on directory
        # ACLs or mount the key from a secret store.
        logger.warning(
            "file permissions for %s cannot be enforced on this platform; the %s file "
            "relies on the parent directory's ACL. Prefer SOAPBOT_MASTER_KEY_FILE from a "
            "secret store on any shared host.",
            path,
            what,
        )


def is_owner_only(path: Path) -> bool:
    """Whether the file is owner-only, for ``soapbot doctor`` and tests."""
    if not POSIX:
        return True  # not enforceable; not a failure to report
    try:
        return (path.stat().st_mode & 0o077) == 0
    except OSError:
        return False


__all__ = ["POSIX", "is_owner_only", "tighten", "write_private_file"]
