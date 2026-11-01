"""Content integrity for installed plugins.

The gap this closes, stated plainly in ``approvals.py``'s own docstring: *changing a
plugin's code does not revoke its approval*. ``ApprovalRecord.digest`` covers the
manifest, so a plugin that swaps ``main.py`` while leaving ``plugin.yaml`` alone keeps
loading as approved and trusted. Approval is meant to be a decision about *code the
operator reviewed*; without a content digest it is a decision about a filename.

Two design choices worth stating up front:

**Non-source files are excluded.** ``__pycache__`` is rewritten by the interpreter on
every import. Hashing it would make each successful load look like tampering on the next
one, and the fix an operator would reach for is turning the check off — which is how a
control dies. ``*.pyc``/``*.pyo`` and VCS metadata are skipped for the same reason.

**``unknown`` is not ``changed``.** An approval recorded before this module existed has
no content digest. Treating that as tampering would refuse every plugin on upgrade and
teach the operator to disable the check; the honest answer is "we never recorded this",
which is reported rather than blocked. ``Approvals.drift()`` already takes the same
position for manifests.
"""

from __future__ import annotations

import asyncio
import hashlib
import logging
from dataclasses import dataclass
from pathlib import Path

logger = logging.getLogger(__name__)

#: Directories whose contents are build artefacts rather than plugin source.
_IGNORED_DIRS = frozenset(
    {"__pycache__", ".git", ".hg", ".svn", ".pytest_cache", ".mypy_cache", ".ruff_cache"}
)

#: Byte-compiled artefacts, which the interpreter rewrites on its own schedule.
_IGNORED_SUFFIXES = frozenset({".pyc", ".pyo"})

#: ``{resolved root: (fingerprint, digest)}`` — see :func:`digest_tree`.
#:
#: A reload re-hashes the same tree that ``load`` just hashed. The fingerprint is
#: ``(name, size, mtime_ns)`` per file, which costs one ``stat`` per file instead of a
#: full read, and it is invalidated by anything that would change the bytes we care
#: about. Kept process-local on purpose: a cache on disk would be one more thing an
#: attacker with write access could edit.
_CACHE: dict[str, tuple[tuple[tuple[str, int, int], ...], str]] = {}


@dataclass(slots=True)
class IntegrityVerdict:
    """Outcome of comparing a plugin directory against its approved digest."""

    state: str
    """``"ok"``, ``"changed"`` or ``"unknown"``.

    ``unknown`` means no digest was recorded (approved before this check existed, or
    approved through a loader with no persistent store). It is reported, never blocked.
    """
    recorded: str = ""
    current: str = ""

    @property
    def blocks(self) -> bool:
        """Whether this verdict is grounds for refusing a load."""
        return self.state == "changed"


def _source_files(directory: Path) -> list[tuple[Path, str]]:
    """Regular files that belong to the plugin, paired with their relative path."""
    out: list[tuple[Path, str]] = []
    for path in sorted(directory.rglob("*")):
        if not path.is_file():
            continue
        relative = path.relative_to(directory)
        if any(part in _IGNORED_DIRS for part in relative.parts):
            continue
        if path.suffix in _IGNORED_SUFFIXES:
            continue
        out.append((path, relative.as_posix()))
    return out


def digest_tree(directory: Path) -> str:
    """SHA-256 over every source file under ``directory``, ordered by relative path.

    The relative path is hashed alongside the content so that renaming a file changes
    the digest — otherwise ``a.py`` and ``b.py`` could be swapped and the tree would
    still verify.

    Returns ``"sha256:<hex>"`` to match the manifest digest's shape, so an operator
    reading two digests side by side can tell they are the same kind of thing.
    """
    root = Path(directory).resolve()
    files = _source_files(root)

    # One stat per file, reused for the cache fingerprint.
    stats: list[tuple[str, int, int, Path]] = []
    for path, relative in files:
        try:
            stat = path.stat()
        except OSError:  # pragma: no cover - file vanished mid-walk
            continue
        stats.append((relative, stat.st_size, stat.st_mtime_ns, path))

    fingerprint = tuple((rel, size, mtime) for rel, size, mtime, _ in stats)
    cached = _CACHE.get(str(root))
    if cached is not None and cached[0] == fingerprint:
        return cached[1]

    hasher = hashlib.sha256()
    for relative, _size, _mtime, path in stats:
        hasher.update(relative.encode("utf-8"))
        hasher.update(b"\0")
        try:
            hasher.update(path.read_bytes())
        except OSError:  # pragma: no cover - unreadable file
            # An unreadable file cannot be verified, and skipping it would let an
            # attacker *remove* read permission to hide a change. Fold the failure
            # into the digest instead.
            hasher.update(b"<unreadable>")
        hasher.update(b"\0")

    digest = "sha256:" + hasher.hexdigest()
    _CACHE[str(root)] = (fingerprint, digest)
    return digest


async def compare_async(directory: Path, recorded: str) -> IntegrityVerdict:
    """``compare`` off the event loop.

    ``digest_tree`` reads every byte of the plugin tree. The cache means it usually
    only stats files, but the first call after any edit is a full read — and both call
    sites (``PluginLoader.load`` and the ``/api/plugins`` listing) are async, so running
    it inline stalls every other task, including chat replies and the WebUI, for as
    long as the disk takes. ``to_thread`` keeps the synchronous function usable from
    tests and sync callers without a second implementation.
    """
    return await asyncio.to_thread(compare, directory, recorded)


def compare(directory: Path, recorded: str) -> IntegrityVerdict:
    """Compare the tree under ``directory`` against a previously recorded digest.

    Synchronous by design: hashing is CPU/disk bound and this is the version a sync
    caller wants. Async callers must use :func:`compare_async` so the read does not
    happen on the loop.
    """
    if not recorded:
        return IntegrityVerdict(state="unknown", recorded="", current="")

    root = Path(directory)
    if not root.is_dir():
        # ``load()`` refuses a missing directory before this is reached; reporting
        # ``unknown`` rather than ``changed`` keeps the two failures distinguishable
        # in the audit log if that ever stops being true.
        return IntegrityVerdict(state="unknown", recorded=recorded, current="")

    current = digest_tree(root)
    return IntegrityVerdict(
        state="ok" if current == recorded else "changed",
        recorded=recorded,
        current=current,
    )


def forget(directory: Path) -> None:
    """Drop the cached digest for ``directory``. For tests and for ``approve``."""
    _CACHE.pop(str(Path(directory).resolve()), None)


__all__ = ["IntegrityVerdict", "compare", "compare_async", "digest_tree", "forget"]
