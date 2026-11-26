"""Persona avatars: discover a Live2D model on disk and hand it to the browser.

What this is, and what it deliberately is not
---------------------------------------------
The operator drops a Live2D model into ``data/avatars/<persona_id>/`` and the panel can
show it next to that persona. **Rendering** Live2D needs the Cubism runtime plus a JS
wrapper; neither is bundled here. What is bundled is the part that has to be trustworthy
either way:

* the asset layout and its validation (a model is a directory of files, and a directory of
  files served over HTTP is a path-traversal surface);
* the discovery result the UI renders — motions, expressions, texture count;
* a static preview (the first texture), which is enough for an operator to confirm they
  dropped in the right model.

The renderer is a drop-in later: the contract the frontend needs (where the files are, what
the model declares) does not change when a Cubism renderer is added, so this is a
placeholder in the sense of "no animation yet", not "no real code".

Layout::

    data/avatars/<persona_id>/
        model.model3.json       # Cubism settings file (required)
        <name>.moc3             # model data (required)
        textures/*.png
        motions/*.motion3.json

Caps are on entry count, per-file size and total size, because the directory is
operator-controlled but the HTTP surface is not: a 2 GB texture would otherwise be read
into memory by the request handler.
"""

from __future__ import annotations

import json
import logging
from pathlib import Path, PurePosixPath
from typing import Any

logger = logging.getLogger(__name__)

#: Cubism settings files are small; anything near this is not a model.
MAX_MODEL3_BYTES = 512 * 1024
MAX_ASSET_BYTES = 8 * 1024 * 1024
MAX_ASSETS = 400
MAX_TOTAL_BYTES = 64 * 1024 * 1024

#: Extensions the asset endpoint will serve, with their content types. An allowlist
#: because the alternative — serving whatever is in the directory — turns an operator's
#: typo into an arbitrary-file-read surface for any authenticated panel user.
ASSET_TYPES: dict[str, str] = {
    ".json": "application/json",
    ".moc3": "application/octet-stream",
    ".png": "image/png",
    ".jpg": "image/jpeg",
    ".jpeg": "image/jpeg",
    ".wav": "audio/wav",
    ".mp3": "audio/mpeg",
}


def avatars_root(data_dir: Path) -> Path:
    return Path(data_dir) / "avatars"


def _persona_dir(root: Path, persona_id: str) -> Path | None:
    """``root/persona_id`` if it is a directory that stays inside ``root``."""
    if not persona_id or "/" in persona_id or "\\" in persona_id or persona_id in (".", ".."):
        return None
    candidate = (root / persona_id).resolve()
    try:
        if not candidate.is_relative_to(root.resolve()):
            return None
    except OSError:  # pragma: no cover - exotic filesystem
        return None
    return candidate if candidate.is_dir() else None


def _find_settings(directory: Path) -> Path | None:
    """The ``*.model3.json`` file. One model per directory, so the first is it."""
    for path in sorted(directory.glob("*.model3.json")):
        if path.is_file() and not path.is_symlink():
            return path
    return None


def _declared(settings: dict[str, Any]) -> dict[str, Any]:
    """Pull the parts a renderer needs out of the model3 settings.

    Tolerant on purpose: this file is written by the Cubism authoring tool and hand-edited
    by operators, and a missing ``Groups`` must degrade to "no expressions", not to a 500.
    """
    file_refs = settings.get("FileReferences") or {}
    motions_raw = file_refs.get("Motions") or {}
    motions: dict[str, list[str]] = {}
    if isinstance(motions_raw, dict):
        for group, items in motions_raw.items():
            if not isinstance(items, list):
                continue
            names = [
                str(item.get("File", ""))
                for item in items
                if isinstance(item, dict) and item.get("File")
            ]
            if names:
                motions[str(group)] = names[:32]

    expressions: list[str] = []
    for item in file_refs.get("Expressions") or []:
        if isinstance(item, dict) and item.get("File"):
            expressions.append(str(item["File"]))

    groups = {
        str(group.get("Name", "")): [str(p) for p in (group.get("Ids") or [])]
        for group in settings.get("Groups") or []
        if isinstance(group, dict)
    }

    textures = [str(t) for t in file_refs.get("Textures") or [] if isinstance(t, str)]
    moc = str(file_refs.get("Moc") or "")
    return {
        "motions": motions,
        "expressions": expressions[:32],
        "groups": {k: v[:32] for k, v in groups.items() if k},
        "textures": textures[:32],
        "moc": moc,
    }


def describe(data_dir: Path, persona_id: str) -> dict[str, Any]:
    """What the panel needs to render (or to say "no model installed")."""
    root = avatars_root(data_dir)
    directory = _persona_dir(root, persona_id)
    if directory is None:
        return {"available": False, "reason": "no_model", "persona": persona_id}

    settings_path = _find_settings(directory)
    if settings_path is None:
        return {
            "available": False,
            "reason": "no_settings",
            "persona": persona_id,
            "hint": f"在 {directory} 里放一个 *.model3.json",
        }
    try:
        if settings_path.stat().st_size > MAX_MODEL3_BYTES:
            return {"available": False, "reason": "settings_too_large", "persona": persona_id}
        settings = json.loads(settings_path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        logger.warning("avatar settings unreadable persona=%s: %s", persona_id, exc)
        return {"available": False, "reason": "settings_unreadable", "persona": persona_id}
    if not isinstance(settings, dict):
        return {"available": False, "reason": "settings_invalid", "persona": persona_id}

    declared = _declared(settings)
    if not declared["moc"]:
        return {
            "available": False,
            "reason": "no_moc",
            "persona": persona_id,
            "hint": "model3.json 的 FileReferences.Moc 为空",
        }

    assets = 0
    total = 0
    for path in directory.rglob("*"):
        if not path.is_file() or path.is_symlink():
            continue
        try:
            size = path.stat().st_size
        except OSError:  # pragma: no cover - file vanished mid-walk
            continue
        assets += 1
        total += size
        if assets > MAX_ASSETS or total > MAX_TOTAL_BYTES:
            return {"available": False, "reason": "too_large", "persona": persona_id}

    preview = declared["textures"][0] if declared["textures"] else ""
    return {
        "available": True,
        "persona": persona_id,
        "settings": settings_path.name,
        "model": declared["moc"],
        "motions": declared["motions"],
        "expressions": declared["expressions"],
        "groups": declared["groups"],
        "textures": declared["textures"],
        "preview": preview,
        "assets": assets,
        "bytes": total,
        # Said in the payload rather than only in the docs: the panel renders a static
        # preview today, and a UI that silently shows a still image where the operator
        # expects an animation is a worse experience than one that says so.
        "renderer": "none",
    }


def resolve_asset(data_dir: Path, persona_id: str, relative: str) -> tuple[Path, str] | None:
    """Resolve one asset inside a persona's avatar directory.

    Returns ``(path, content_type)`` or ``None``. Every rejection is a ``None`` — the
    caller answers 404, which leaks nothing about *why* (existence, extension or
    containment), and there is no path through here that returns a file outside the
    persona's own avatar directory.
    """
    root = avatars_root(data_dir)
    directory = _persona_dir(root, persona_id)
    if directory is None or not relative:
        return None
    # Reject the shapes before touching the disk; ``resolve`` alone would accept
    # ``textures/../../config/providers.yaml`` and then fail containment — this is the
    # clearer rejection and does not depend on how the OS treats a trailing slash.
    pure = PurePosixPath(relative.replace("\\", "/"))
    if pure.is_absolute() or any(part in ("", ".", "..") for part in pure.parts):
        return None
    content_type = ASSET_TYPES.get(pure.suffix.lower())
    if content_type is None:
        return None
    try:
        target = (directory / pure).resolve()
        if not target.is_relative_to(directory):
            return None
        if not target.is_file() or target.is_symlink():
            return None
        if target.stat().st_size > MAX_ASSET_BYTES:
            return None
    except OSError:  # pragma: no cover - exotic filesystem
        return None
    return target, content_type


__all__ = [
    "ASSET_TYPES",
    "MAX_ASSET_BYTES",
    "avatars_root",
    "describe",
    "resolve_asset",
]
