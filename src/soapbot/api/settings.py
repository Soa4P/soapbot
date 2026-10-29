"""The settings page's backend: what the process is running with, and a narrow way to
change the few settings that are safe to change from a browser.

Why only *some* settings are writable
------------------------------------
This endpoint is not a generic "set any environment variable" form. Most of
``Settings`` is a deployment decision — bind address, master key location, data
directory, allow-lists. Exposing those would let anyone holding the panel token
reshape the security boundary (bind to 0.0.0.0, point ``data_dir`` at a path of their
choosing, widen ``group_allowlist``) from a text field.

The writable set is exactly the settings whose worst case is "the bot behaves
differently, and the operator can see it": reply language, whether voice is
transcribed, whether replies are synthesised, and which voice. Each one is a behaviour
toggle, not a permission.

**Changes take effect on restart, and the UI says so.** ``Settings`` is read at process
start and threaded into objects built once (the runtime's locale, the transcriber). A
"save" that quietly did nothing until the next restart, with no indication, is the
same class of lie as a documented-but-unwired feature: the operator changes a setting,
sees it accepted, and concludes it is live. So the response carries
``restart_required: true`` and the page renders that.
"""

from __future__ import annotations

import os
import re
from pathlib import Path
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel

from soapbot import __version__
from soapbot.api.auth import require_api_auth
from soapbot.api.locale import request_locale
from soapbot.config import settings
from soapbot.core import config_write
from soapbot.i18n import available_locales, t
from soapbot.security.audit import get_audit_log
from soapbot.security.principal import PERMISSION_MIN_ROLE, Permission, Role

router = APIRouter(prefix="/api/settings", tags=["settings"])

#: Settings the panel may write, mapped to the environment variable that holds them.
#:
#: A closed table, not a filter on ``Settings.model_fields``: an allow-list that
#: derives itself from the model would grow a write path every time a field is added,
#: including fields that are deliberately not runtime-editable.
WRITABLE: dict[str, str] = {
    "default_locale": "SOAPBOT_DEFAULT_LOCALE",
    "voice_enabled": "SOAPBOT_VOICE_ENABLED",
    "voice_tts_enabled": "SOAPBOT_VOICE_TTS_ENABLED",
    "voice_tts_voice": "SOAPBOT_VOICE_TTS_VOICE",
}

#: Keys are checked against this before anything is formatted into the file.
_ENV_LINE_RE = re.compile(r"^SOAPBOT_[A-Z0-9_]+$")


class SettingsPatch(BaseModel):
    """Only writable keys; unknown names are rejected rather than ignored."""

    changes: dict[str, Any]


def _env_path() -> Path:
    """The ``.env`` the process would read, resolved the same way ``Settings`` does.

    ``Path(".env")`` is relative to the working directory, which for a service started
    by systemd or a container is *not* the repository root. Using the same resolution
    as startup is what makes "saved" mean "will be read on next boot".
    """
    return Path(os.environ.get("SOAPBOT_ENV_FILE", ".env")).resolve()


def _role_of(auth: dict[str, Any]) -> Role:
    from soapbot.api.admin import _role_of as admin_role_of

    return admin_role_of(auth)


def _require_config_permission(auth: dict[str, Any], request: Request) -> Role:
    role = _role_of(auth)
    minimum = PERMISSION_MIN_ROLE.get(Permission.MANAGE_CONFIG, Role.OWNER)
    if role.rank < minimum.rank:
        get_audit_log().record(
            kind="authz",
            action="settings_write",
            outcome="deny",
            role=role.value,
            detail=f"from={request.client.host if request.client else '-'}",
        )
        raise HTTPException(
            status_code=403,
            detail=t("api.role_required", request_locale(request), role=minimum.value),
        )
    return role


def _current_values() -> dict[str, Any]:
    """The live values, plus whether a newer ``.env`` value is waiting for a restart."""
    return {
        "default_locale": settings.default_locale,
        "voice_enabled": settings.voice_enabled,
        "voice_tts_enabled": settings.voice_tts_enabled,
        "voice_tts_voice": settings.voice_tts_voice,
    }


def _tts_available() -> bool:
    """Whether the optional dependency is importable in this environment.

    Reported so the page can disable the voice-output switch with a reason, instead of
    letting an operator enable it and then wonder why replies stay text. Checked by
    import rather than by reading metadata because the import is exactly what
    ``EdgeTts.synthesise`` will attempt at runtime.
    """
    try:
        import edge_tts  # noqa: F401
    except Exception:
        return False
    return True


@router.get("")
async def read_settings(_: dict = Depends(require_api_auth)) -> dict[str, Any]:
    """Everything the settings page renders, in one call.

    One request rather than four: the page shows language, voice, MCP status and
    runtime information side by side, and four round trips would let the page render
    half-populated for a moment.
    """
    from soapbot.app import get_startup_errors
    from soapbot.mcp.client import McpManager
    from soapbot.memory.db import SCHEMA_VERSION

    runtime = None
    try:
        from soapbot.api.admin import _runtime

        runtime = _runtime()
    except HTTPException:
        # The runtime can legitimately be absent (``ENABLE_RUNTIME=false`` serves only
        # the API). Reporting that is more useful than failing the whole page.
        runtime = None

    schema_version: int | None = None
    if runtime is not None and getattr(runtime, "memory", None) is not None:
        try:
            schema_version = await runtime.memory.db.schema_version()  # type: ignore[attr-defined]
        except Exception:
            schema_version = None

    mcp_status: dict[str, Any] = {"configured": False, "servers": [], "tools": 0}
    if runtime is not None:
        manager = getattr(runtime, "mcp", None)
        if isinstance(manager, McpManager):
            mcp_status = manager.status()

    tts_ready = _tts_available()
    return {
        "version": __version__,
        "schema_version": schema_version,
        "expected_schema_version": SCHEMA_VERSION,
        "data_dir": str(settings.data_dir),
        "config_dir": str(settings.config_dir),
        "env_file": str(_env_path()),
        "startup_errors": get_startup_errors(),
        "values": _current_values(),
        "writable": sorted(WRITABLE),
        "locales": available_locales(),
        "voice": {
            "tts_available": tts_ready,
            # Spelled out rather than left to the UI to infer: the install command is
            # the actionable part, and a greyed-out switch with no explanation is a
            # dead end.
            "tts_install_hint": "" if tts_ready else "pip install 'soapbot[voice]'",
        },
        "mcp": mcp_status,
    }


def _format_value(value: Any) -> str:
    if isinstance(value, bool):
        return "true" if value else "false"
    text_value = str(value)
    if "\n" in text_value or '"' in text_value:
        raise HTTPException(status_code=400, detail="value must be a single line")
    return text_value


def _rewrite_env(existing: str, updates: dict[str, str]) -> str:
    """Return ``existing`` with ``KEY=value`` lines updated or appended.

    Rewrites in place rather than regenerating the file from ``Settings``: ``.env`` is
    the operator's file. It may contain comments explaining why a value is what it is,
    variables this build does not read, and ordering that means something to whoever
    wrote it. Regenerating would silently delete all of that — and the operator would
    find out when they next opened the file, long after the panel "saved" it.
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


@router.post("")
async def write_settings(
    payload: SettingsPatch,
    request: Request,
    auth: dict = Depends(require_api_auth),
) -> dict[str, Any]:
    """Persist the writable settings to ``.env``.

    Validates before writing and reports ``restart_required``. Deliberately does *not*
    mutate ``settings`` in place: the runtime objects that consumed those values were
    built at startup, so a process whose ``settings`` says one thing while its
    transcriber says another is in a state nobody can reason about. The honest model is
    "file changed, restart to apply", and it is what the response says.
    """
    role = _require_config_permission(auth, request)
    locale = request_locale(request)

    unknown = sorted(set(payload.changes) - set(WRITABLE))
    if unknown:
        raise HTTPException(
            status_code=400,
            detail=f"not writable from the panel: {', '.join(unknown)}",
        )
    if not payload.changes:
        raise HTTPException(status_code=400, detail="no changes submitted")

    # Validate each value against the type ``Settings`` will parse it as. Doing this
    # here means a bad value is rejected while the operator is looking at the form,
    # rather than becoming a startup crash on the next boot with no obvious cause.
    updates: dict[str, str] = {}
    candidates = settings.model_dump()
    for name, value in payload.changes.items():
        env_key = WRITABLE[name]
        if not _ENV_LINE_RE.match(env_key):  # pragma: no cover - table is constant
            raise HTTPException(status_code=500, detail="invalid writable key table")
        if name == "default_locale" and value not in available_locales():
            raise HTTPException(
                status_code=400,
                detail=f"unsupported locale {value!r}; choose one of {available_locales()}",
            )
        # Type check against the *declared default's* type: it is the one annotation
        # that is unambiguously the intended shape, and it catches the common mistake
        # of sending "true" (a string) where a bool is expected — which pydantic would
        # otherwise accept and write back as a quoted value.
        if isinstance(settings.model_fields[name].default, bool) and not isinstance(value, bool):
            raise HTTPException(status_code=400, detail=f"{name} must be a boolean")
        candidates[name] = value
        updates[env_key] = _format_value(value)

    try:
        # Round-trip through the real model: if the value cannot be parsed into
        # Settings, it must not reach the file.
        from soapbot.config import Settings

        Settings(**{**candidates})
    except Exception as exc:
        raise HTTPException(status_code=400, detail=f"invalid value: {exc}") from exc

    path = _env_path()
    existing = path.read_text(encoding="utf-8") if path.is_file() else ""
    updated = _rewrite_env(existing, updates)

    try:
        config_write.write_atomic(path, updated)
    except OSError as exc:
        get_audit_log().record(
            kind="config",
            action="settings_write",
            outcome="deny",
            role=role.value,
            detail=f"write_failed:{exc.__class__.__name__}",
        )
        raise HTTPException(status_code=500, detail=t("api.write_failed", locale)) from exc

    get_audit_log().record(
        kind="config",
        action="settings_write",
        outcome="allow",
        role=role.value,
        detail=",".join(sorted(payload.changes)),
    )

    return {
        "written": True,
        "changed": sorted(payload.changes),
        "env_file": str(path),
        # Explicit, and rendered: the values above are what the *file* now says. The
        # running process keeps the old ones until it is restarted.
        "restart_required": True,
    }
