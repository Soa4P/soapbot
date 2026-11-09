"""Reading, diffing and atomically replacing the provider configuration file.

Why this module exists at all
-----------------------------
``docs/architecture.md`` used to say configuration is never written through the API,
because a file in version control is reviewed before it takes effect. That reasoning
was sound but the premise was wrong: the files are *not* in version control in a
typical single-host deployment, so the review never happened — the operator just
edited a file over SSH with no second pair of eyes and no record.

Writing through the panel is not a relaxation of that rule, it is the first time the
rule can actually be honoured: a diff is shown, the operator confirms it, and the
change is written to the audit log. The review surface moved from "the file in git"
to "the diff you just read", which is stricter than what was really happening.

The hazard this design exists to prevent
----------------------------------------
``providers.yaml`` holds API keys. A read endpoint that masks them and a save endpoint
that writes back whatever it received will replace every real key with ``***``. That
bug is silent at save time and fatal at next start, which is the worst possible
combination: the panel says "saved", and the service stops answering hours later.

So writes are **field patches applied to the on-disk document**, never a whole-file
overwrite of something previously read back:

* the candidate document is always ``current_file + patch``;
* a secret that arrives as :data:`UNCHANGED` keeps whatever was on disk;
* a secret the operator retyped replaces it;
* ``env:VAR`` and ``enc:v1:`` are stored verbatim — they are references, safe to see
  and safe to round-trip.

Nothing in this module imports FastAPI. It takes paths and dictionaries and returns
results, so the same code is used by the endpoint and by the tests without an app.
"""

from __future__ import annotations

import contextlib
import copy
import difflib
import hashlib
import logging
import os
import stat
import tempfile
import threading
import time
from collections.abc import Callable, Iterator, Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import yaml

from soapbot.core.config_files import (
    SECRET_KEYS,
    ConfigError,
    parse_providers,
    resolve_secret,
)

logger = logging.getLogger(__name__)

#: Sentinel a client sends to mean "keep the value that is on disk".
#:
#: A magic string rather than an omission because omission has to stay available: a
#: patch that leaves out ``api_key`` also keeps the old key, but it cannot express
#: "the operator looked at this field and chose not to change it". More practically,
#: form bindings round-trip every field, so an empty input means "clear it" and this
#: sentinel is the only way to say "untouched" in the same payload.
UNCHANGED = "__UNCHANGED__"

#: Shown in place of a literal secret. Never written back — see :func:`apply_patch`.
MASK = "********"


class ConfigConflictError(RuntimeError):
    """The file changed underneath the caller; the patch was computed against a stale base."""

    def __init__(self, current_hash: str, diff: str) -> None:
        super().__init__("configuration file changed since it was read")
        self.current_hash = current_hash
        self.diff = diff


@dataclass(slots=True)
class PatchResult:
    """Outcome of applying a patch in memory. Nothing has been written."""

    document: dict[str, Any]
    rendered: str
    diff: str
    changed_fields: list[str]
    base_hash: str
    new_hash: str

    @property
    def empty(self) -> bool:
        return not self.changed_fields


def _canonical_hash(text: str) -> str:
    """Hash the parsed content, not the bytes.

    Editing a file's whitespace or comment ordering via the panel rewrites it with
    ``yaml.safe_dump``, so a byte hash would report a conflict against an unchanged
    document the first time anything is saved. Hashing the semantic content makes
    "unchanged" mean unchanged.
    """
    return hashlib.sha256(text.encode("utf-8")).hexdigest()[:16]


def file_hash(path: Path) -> str:
    """Hash of the *normalised* document, used as the optimistic-lock token.

    Must go through the same ``render`` step as :func:`build_patch`, otherwise the
    token handed out by the read endpoint can never match the one computed at write
    time and every save reports a conflict. That divergence existed for exactly one
    test run: hashing raw text seemed equivalent until the file contained comments or
    non-canonical spacing, which ``render`` drops.
    """
    return _hash_document(read_document(path))


def _hash_document(document: dict[str, Any]) -> str:
    return _canonical_hash(render(document))


def read_document(path: Path) -> dict[str, Any]:
    """Parse the file for editing. Absent file is an empty document, not an error."""
    if not path.exists():
        return {}
    raw = path.read_text(encoding="utf-8")
    if not raw.strip():
        return {}
    try:
        data = yaml.safe_load(raw)
    except yaml.YAMLError as exc:
        # A file that no longer parses cannot be patched — every patch would be
        # computed against a document we cannot read. Surface it so the operator
        # fixes it in an editor rather than seeing an empty form and "saving" over it.
        raise ConfigError(f"{path} is not valid YAML: {exc}") from exc
    if data is None:
        return {}
    if not isinstance(data, dict):
        raise ConfigError(f"{path} must contain a mapping at the top level")
    return data


def _is_secret_key(key: str) -> bool:
    return key in SECRET_KEYS


def mask_document(document: dict[str, Any]) -> dict[str, Any]:
    """Copy of the document with literal secrets replaced by the mask.

    References (``env:`` / ``enc:v1:``) are returned as-is: they contain no credential,
    and hiding them would leave the operator unable to tell which variable a provider
    is wired to — the most common thing they open this page to check.
    """
    out: dict[str, Any] = {}
    for key, value in document.items():
        if _is_secret_key(key) and isinstance(value, str) and _is_literal_secret(value):
            out[key] = MASK
        elif isinstance(value, dict):
            out[key] = mask_document(value)
        elif isinstance(value, list):
            out[key] = [mask_document(v) if isinstance(v, dict) else v for v in value]
        else:
            out[key] = value
    return out


def _is_literal_secret(value: str) -> bool:
    text = str(value or "").strip()
    if not text:
        return False
    return not (text.startswith("env:") or text.startswith("enc:v1:"))


def provider_index(document: dict[str, Any]) -> dict[str, dict[str, Any]]:
    """Providers keyed by id, in file order. Used to build a patch from the form."""
    entries = document.get("providers") or []
    if not isinstance(entries, list):
        return {}
    return {
        str(item.get("id")): item
        for item in entries
        if isinstance(item, dict) and item.get("id")
    }


def apply_provider_patch(
    document: dict[str, Any],
    patch: list[dict[str, Any]],
) -> tuple[dict[str, Any], list[str]]:
    """Merge ``patch`` into ``document``, returning a new document and changed fields.

    The patch is a list of provider objects, each with an ``id``. Semantics:

    * providers present in the patch are updated **field by field** — a key that is
      absent from a patch entry keeps its on-disk value;
    * ``UNCHANGED`` in a secret field keeps the on-disk value;
    * ``""`` in a secret field clears it (so a key can actually be removed);
    * providers in the document but not in the patch are left alone (deleting is its
      own explicit operation, not a side effect of a partial payload);
    * a patch entry whose id is not in the document is appended (adding a provider).
    """
    result = _deep_copy(document)
    entries: list[Any] = result.get("providers")
    if not isinstance(entries, list):
        entries = []
        result["providers"] = entries

    by_id = {
        str(item.get("id")): item
        for item in entries
        if isinstance(item, dict) and item.get("id")
    }

    changed: list[str] = []
    seen_in_patch: set[str] = set()
    for incoming in patch:
        pid = str(incoming.get("id") or "").strip()
        if not pid:
            raise ConfigError("provider patch entry requires 'id'")
        if pid in seen_in_patch:
            # Two entries for one id in a single patch means the client built the
            # payload wrong (a duplicated row, a merged list). Applying them in order
            # would make the last one win silently — and the diff would show only that
            # outcome, hiding the fact that half the payload was discarded.
            raise ConfigError(f"provider patch 中 id {pid!r} 出现多次")
        seen_in_patch.add(pid)
        target = by_id.get(pid)
        if target is None:
            # New provider: a secret cannot be "unchanged", there is nothing to keep.
            fresh = {k: v for k, v in incoming.items() if k != "api_key"}
            key = incoming.get("api_key")
            fresh["api_key"] = "" if key == UNCHANGED else key
            entries.append(fresh)
            by_id[pid] = fresh
            changed.append(f"providers[{pid}] (added)")
            continue

        for field, value in incoming.items():
            if field == "id":
                continue
            if _is_secret_key(field):
                if value == UNCHANGED:
                    continue  # explicit "leave the credential alone"
                if value == MASK:
                    # A client that echoed back what it was shown. Treat as unchanged
                    # rather than writing the mask — this is the exact trap described
                    # in the module docstring, and it can arrive from any hand-written
                    # client, not just ours.
                    continue
            if target.get(field) == value:
                continue
            target[field] = value
            # Record the field name, never the value: this string reaches the audit log.
            changed.append(f"providers[{pid}].{field}")

    return result, changed


def _deep_copy(value: Any) -> Any:
    if isinstance(value, dict):
        return {k: _deep_copy(v) for k, v in value.items()}
    if isinstance(value, list):
        return [_deep_copy(v) for v in value]
    return value


def render(document: dict[str, Any]) -> str:
    """Serialise for disk: stable key order, unicode intact, no YAML aliases."""
    return yaml.safe_dump(
        document,
        allow_unicode=True,
        sort_keys=False,
        default_flow_style=False,
        width=100,
    )


def render_masked(document: dict[str, Any]) -> str:
    return render(mask_document(document))


def unified_diff(before: str, after: str, filename: str = "providers.yaml") -> str:
    """Line diff for the confirmation screen.

    Always rendered from the *masked* documents by the caller; this function does not
    know about secrets and must not be given raw ones.
    """
    return "".join(
        difflib.unified_diff(
            before.splitlines(keepends=True),
            after.splitlines(keepends=True),
            fromfile=f"{filename} (当前)",
            tofile=f"{filename} (保存后)",
            n=3,
        )
    )


def validate_providers(document: dict[str, Any]) -> list[str]:
    """Run the startup parser over a candidate document.

    Returns a list of human-readable problems. Uses :func:`parse_providers`, so
    "references an unset environment variable" fails here exactly as it would at
    boot — closing the hole where the panel could save a file that kills the next
    start.
    """
    problems: list[str] = []
    try:
        parse_providers(document, source="<提交的配置>")
    except ConfigError as exc:
        problems.append(str(exc))
        return problems
    except Exception as exc:  # pragma: no cover - defensive
        problems.append(f"校验时发生未预期的错误：{exc}")
        return problems

    # `parse_providers` resolves every secret it is given, which already covers the
    # unset-env case. The extra pass below exists for one thing it cannot see: a
    # provider whose *id* survives but whose kind would fail to construct. That needs
    # the registry, so it is left to a dry-run at the call site rather than duplicated
    # here.
    return problems


def adapter_index(document: dict[str, Any]) -> dict[str, dict[str, Any]]:
    """Adapters keyed by ``kind``, in file order.

    ``kind`` is the identity here, not ``id``: the runtime registers one adapter per
    kind, so two entries with the same kind silently collapse into one at startup. That
    is the rule `load_adapters` enforces by raising, and it is why the editor's primary
    key is the kind rather than a free-form name.
    """
    entries = document.get("adapters") or []
    if not isinstance(entries, list):
        return {}
    return {
        str(item.get("kind")): item
        for item in entries
        if isinstance(item, dict) and item.get("kind")
    }


def apply_adapter_patch(
    document: dict[str, Any], patch: list[dict[str, Any]]
) -> tuple[dict[str, Any], list[str]]:
    """Merge adapter entries by ``kind``. Unknown options are kept, not dropped.

    Adapter options are a free-form bag (``ws_url``, ``token``, ``self_id`` ...), so this
    cannot validate field names the way the provider patch does. What it can enforce is
    the one rule that breaks startup: two entries with the same kind.
    """
    result = copy.deepcopy(document)
    entries = result.get("adapters")
    if not isinstance(entries, list):
        entries = []
        result["adapters"] = entries

    by_kind = adapter_index(result)
    changed: list[str] = []
    for incoming in patch:
        kind = str(incoming.get("kind") or "").strip()
        if not kind:
            raise ConfigError("adapter entry requires 'kind'")
        current = by_kind.get(kind)
        if current is None:
            fresh = {key: value for key, value in incoming.items() if value is not None}
            fresh["kind"] = kind
            entries.append(fresh)
            by_kind[kind] = fresh
            changed.append(kind)
            continue
        for key, value in incoming.items():
            if key == "kind" or value is None:
                continue
            if current.get(key) != value:
                current[key] = value
                changed.append(f"{kind}.{key}")
    return result, changed


def validate_adapters(document: dict[str, Any]) -> list[str]:
    """The subset of `load_adapters` that can be checked without a live connection."""
    entries = document.get("adapters")
    if entries is None:
        return []
    if not isinstance(entries, list):
        return ["adapters 必须是列表"]

    problems: list[str] = []
    seen: set[str] = set()
    for index, item in enumerate(entries):
        if not isinstance(item, dict):
            problems.append(f"adapters[{index}] 必须是映射")
            continue
        kind = str(item.get("kind") or "").strip()
        if not kind:
            problems.append(f"adapters[{index}] 缺少 kind")
            continue
        if kind in seen:
            problems.append(f"重复的 adapter kind：{kind}（运行时按 kind 唯一注册）")
        seen.add(kind)
    return problems


def build_patch(
    *,
    path: Path,
    patch: list[dict[str, Any]],
    base_hash: str,
    apply_fn: Callable[..., tuple[dict[str, Any], list[str]]] = apply_provider_patch,
    validate_fn: Callable[[dict[str, Any]], list[str]] = validate_providers,
    diff_render: Callable[[dict[str, Any]], str] = render_masked,
    filename: str = "providers.yaml",
) -> PatchResult:
    """Compute the candidate document and its diff. **Does not write.**

    Raises :class:`ConfigConflictError` if the file moved since ``base_hash`` was taken,
    and :class:`ConfigError` if the candidate would not boot. Both are raised before
    anything touches the filesystem, which is what makes "confirm then save" honest:
    the diff the operator approves is a diff that already passed validation.

    The three injection points default to the provider behaviour, so existing callers
    are unchanged. They exist because ``mcp.yaml`` needs the same three steps with three
    different rules: list items merged by name instead of by id, a parser that also
    spawns-args-checks, and a diff renderer that must redact every ``env`` value rather
    than only the keys named like secrets.
    """
    current = read_document(path)
    current_hash = _hash_document(current)
    if base_hash and base_hash != current_hash:
        raise ConfigConflictError(current_hash, "")

    candidate, changed = apply_fn(current, patch)
    problems = validate_fn(candidate)
    if problems:
        raise ConfigError("; ".join(problems))

    diff = unified_diff(diff_render(current), diff_render(candidate), filename)
    return PatchResult(
        document=candidate,
        rendered=render(candidate),
        diff=diff,
        changed_fields=changed,
        base_hash=current_hash,
        new_hash=_hash_document(candidate),
    )


def write_atomic(path: Path, text: str) -> None:
    """Replace ``path`` with ``text`` without ever exposing a partial file.

    ``os.replace`` is atomic on both POSIX and Windows (via ``MoveFileEx``), so a
    reader — including our own startup path on another process — sees either the old
    file or the new one, never a half-written one. The original mode is preserved:
    a config file that was ``0600`` because it holds an API key must not become
    ``0644`` as a side effect of being edited through a web form.
    """
    path.parent.mkdir(parents=True, exist_ok=True)
    mode = None
    if path.exists():
        mode = path.stat().st_mode & 0o777

    fd, tmp_name = tempfile.mkstemp(dir=str(path.parent), prefix=".tmp-", suffix=".yaml")
    tmp = Path(tmp_name)
    # Windows refuses to replace a read-only destination (WinError 5). That is a real
    # situation here: an operator who chmod 0444's a config to stop accidental edits
    # would otherwise find the panel silently unable to save, with only "写入失败" to go
    # on. Clear the bit for the duration of the replace, then put it back — the file
    # ends up exactly as locked as it started.
    was_readonly = path.exists() and not (path.stat().st_mode & stat.S_IWRITE)
    try:
        with os.fdopen(fd, "w", encoding="utf-8", newline="\n") as handle:
            handle.write(text)
            handle.flush()
            os.fsync(handle.fileno())
        if mode is not None:
            # POSIX honours the full mode. Windows maps only the read-only bit, so the
            # 0600 a deployment relies on cannot be reproduced there — the file ends up
            # owner-only by virtue of NTFS inheritance instead. Attempting to fake it
            # with icacls would make this function depend on the platform's ACL tooling
            # for a guarantee it cannot verify; the honest statement is in the docs:
            # on Windows, protect the volume, not the file.
            os.chmod(tmp, mode)
        if was_readonly:
            os.chmod(path, mode | stat.S_IWRITE)
        os.replace(tmp, path)
    except Exception:
        tmp.unlink(missing_ok=True)
        raise
    finally:
        if was_readonly and path.exists():
            os.chmod(path, mode if mode is not None else 0o444)
    logger.info("configuration written: %s (%d bytes)", path, len(text))


#: Serialises the *whole* read-modify-write transaction, not just the final replace.
#: ``write_atomic`` makes one replace atomic, but two saves that both start from the
#: same file contents still lose whichever one finishes first. A `threading.Lock` is
#: required (rather than `asyncio.Lock`) because FastAPI may run a handler in a worker
#: thread, and an asyncio lock is bound to one event loop.
_ENV_LOCK = threading.Lock()

#: How long a writer waits for the cross-process lock before giving up.
#:
#: Windows is the reason this is a number we choose rather than one the OS chooses.
#: ``msvcrt.LK_LOCK`` retries ten times one second apart and then raises, so the budget
#: was fixed at ~10 s with no way to see how close a run came to it. Four writers each
#: doing twenty saves against one file spent enough of that budget to fail the
#: concurrency test roughly once per full-suite run — a flake that looks like a race
#: bug in the lock and is really a timeout in the retry policy.
#:
#: Thirty seconds is not a guess about how long a save takes (it is milliseconds); it
#: is a bound that a contended-but-healthy system cannot reach, so exceeding it means
#: something is actually wrong and the error should say so.
_ENV_LOCK_TIMEOUT = 30.0

#: First backoff interval; doubles per attempt up to :data:`_ENV_LOCK_BACKOFF_MAX`.
_ENV_LOCK_BACKOFF = 0.005
_ENV_LOCK_BACKOFF_MAX = 0.25


class EnvLockError(TimeoutError):
    """The cross-process ``.env`` lock could not be acquired in time.

    Subclasses ``TimeoutError``, which is itself an ``OSError``: the four API writers
    already catch ``OSError`` and answer ``api.write_failed``, and a lock timeout *is*
    a write that did not happen, so that mapping is correct and needs no new handler.
    The distinct type exists so the log line says "another writer is holding it"
    instead of the generic filesystem message — same user-visible outcome, different
    diagnosis for whoever reads the log.
    """


@contextlib.contextmanager
def env_transaction(path: Path) -> Iterator[None]:
    """Hold a process-wide *and* cross-process lock around a ``.env`` update.

    The cross-process half matters with more than one uvicorn worker: a thread lock
    cannot see into another process, and both workers would still read the same old
    file. A sidecar ``<name>.lock`` file is used with the OS's advisory lock, which the
    kernel releases even if the process dies holding it — so there is no stale lock to
    clean up, unlike an ``O_EXCL`` sentinel.

    Failing to acquire the lock raises rather than silently degrading to "no lock":
    a save that reports success while another writer may be in flight is exactly the
    lost-update bug this exists to prevent. The wait is bounded by
    :data:`_ENV_LOCK_TIMEOUT` and the failure is :class:`EnvLockError`, so a
    contended-but-healthy system never trips it and a genuinely stuck one says so.
    """
    with _ENV_LOCK:
        lock_path = path.with_name(path.name + ".lock")
        lock_path.parent.mkdir(parents=True, exist_ok=True)
        fd = os.open(lock_path, os.O_CREAT | os.O_RDWR, 0o600)
        try:
            if os.name == "nt":
                import msvcrt

                _acquire_windows_lock(fd, lock_path)
                try:
                    yield
                finally:
                    with contextlib.suppress(OSError):
                        os.lseek(fd, 0, os.SEEK_SET)
                        msvcrt.locking(fd, msvcrt.LK_UNLCK, 1)
            else:
                import fcntl

                fcntl.flock(fd, fcntl.LOCK_EX)
                try:
                    yield
                finally:
                    with contextlib.suppress(OSError):
                        fcntl.flock(fd, fcntl.LOCK_UN)
        finally:
            os.close(fd)


def _acquire_windows_lock(fd: int, lock_path: Path) -> None:
    """Take the byte-range lock on ``fd``, retrying with backoff until the deadline.

    ``msvcrt.LK_LOCK`` is not used: it blocks for a fixed ten seconds and then raises
    ``OSError``, which is both too short under contention and indistinguishable from a
    real I/O error. ``LK_NBLCK`` is the non-blocking variant, so the retry policy is
    ours and the failure mode is a named exception instead of a bare ``OSError``.

    The sidecar file is deliberately **never written**. Windows' ``LockFile`` accepts a
    byte range past EOF, so byte 0 of a zero-length file is a valid exclusive lock —
    measured: a second process gets ``PermissionError [Errno 13]`` while the first holds
    it, succeeds after the unlock, and the file stays at zero bytes throughout.

    The old "ensure one lockable byte" ``os.write(fd, b"\\0")`` was the whole race, not
    a harmless setup step: four writers that all stat a zero-length sidecar all try to
    write byte 0, and once another process has locked that range Windows rejects the
    write instead of queuing it. That killed a child in
    ``test_separate_processes_do_not_overwrite_each_other`` on the Windows CI job
    (run 42486262686, 2026-11-08) with ``PermissionError: [Errno 13]``. A lock that
    requires writing the locked range cannot be acquired by two processes at once.
    """
    import msvcrt

    deadline = time.monotonic() + _ENV_LOCK_TIMEOUT
    delay = _ENV_LOCK_BACKOFF
    while True:
        os.lseek(fd, 0, os.SEEK_SET)
        try:
            msvcrt.locking(fd, msvcrt.LK_NBLCK, 1)
            return
        except OSError:
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                raise EnvLockError(
                    f"could not lock {lock_path} within {_ENV_LOCK_TIMEOUT:g}s; "
                    "another writer is holding it"
                ) from None
        # Sleep no longer than the budget left, so the timeout is a real bound rather
        # than "the bound plus one backoff interval".
        time.sleep(min(delay, remaining))
        delay = min(delay * 2, _ENV_LOCK_BACKOFF_MAX)


def write_env_updates(path: Path, updates: Mapping[str, str]) -> str:
    """Update ``KEY=value`` lines in a ``.env`` under one transaction.

    The single entry point every runtime writer must use. Four endpoints used to hand-
    roll ``read_text -> _rewrite_env -> write_atomic``; with no shared lock, a save of
    the authority list and a simultaneous save of group scope each rebuilt the file
    from the same pre-save text, and the last writer silently erased the other's keys.

    Rewrites in place rather than regenerating from ``Settings``: the operator's
    comments, unknown variables and line order all survive.
    """
    with env_transaction(path):
        existing = path.read_text(encoding="utf-8") if path.is_file() else ""
        updated = rewrite_env(existing, dict(updates))
        write_atomic(path, updated)
        return updated


def rewrite_env(existing: str, updates: Mapping[str, str]) -> str:
    """Return ``existing`` with ``KEY=value`` lines updated or appended.

    This is the pure string half of :func:`write_env_updates`, kept separate so it can
    be tested without touching the filesystem or a lock.
    """
    lines = existing.splitlines()
    remaining = dict(updates)
    out: list[str] = []
    for line in lines:
        stripped = line.strip()
        if not stripped or stripped.startswith("#") or "=" not in stripped:
            out.append(line)
            continue
        key = stripped.split("=", 1)[0].strip()
        if key in remaining:
            out.append(f"{key}={remaining.pop(key)}")
        else:
            out.append(line)
    if remaining:
        if out and out[-1].strip():
            out.append("")
        for key, value in remaining.items():
            out.append(f"{key}={value}")
    return "\n".join(out) + "\n"


def check_secret_resolvable(value: Any, *, field_name: str) -> str:
    """Expose :func:`resolve_secret` so callers can pre-flight a single field.

    Thin on purpose: the write path must not grow a second interpretation of what a
    secret reference means. If startup rejects ``env:UNSET_VAR``, so does this.

    Unused, and deliberately kept: :func:`validate_providers` resolves every secret
    through :func:`parse_providers`, which is the same code at the same granularity, so
    nothing needs a per-field pre-flight today. It stays because the alternative —
    calling :func:`resolve_secret` directly from the API layer — is exactly the second
    interpretation this docstring warns about.
    """
    return resolve_secret(value, field_name=field_name)
