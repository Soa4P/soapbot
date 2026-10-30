"""Patching ``config/mcp.yaml``: the same read → diff → apply, with three different rules.

Why this is a separate engine and not a parameter of the provider one
---------------------------------------------------------------------
A provider is keyed by ``id``, an MCP server by ``name``; more importantly the two files
carry secrets differently. ``providers.yaml`` hides a credential behind a known field
(``api_key``), so the masker can be *key-driven*. ``mcp.yaml`` puts credentials in ``env``
under names the operator chooses — ``GITHUB_TOKEN``, ``FOO``, anything — so no rule about
the field name can identify them: every value has to be treated as secret.

That single difference decides the shape of the editor. Env values never leave the
server: the read endpoint returns key *names*, and a patch that omits ``env`` keeps
whatever is on disk. The panel cannot round-trip a value it was never shown, so the
"saved ``***`` over the real token, discovered at next start" failure is prevented by
construction rather than by remembering to check for a mask.

Deleting is allowed here, unlike providers
------------------------------------------
A provider's fields are shared with cooldown state and routing order, so removing one is
its own explicit operation. A server is a self-contained list item: ``{"name": x,
"delete": true}`` has exactly one reading, and the diff shows the whole entry going.
"""

from __future__ import annotations

import copy
import hashlib
import secrets
from pathlib import Path
from typing import Any

from soapbot.core.config_files import ConfigError
from soapbot.core.config_write import PatchResult, build_patch, render
from soapbot.mcp.config import McpConfigError, parse_servers

#: Prefix of every rendered env value. Not a sentinel — nothing parses it back, because
#: the panel never sends env values it did not receive from the operator. Deliberately
#: not ``***``: YAML quotes a leading ``*`` (it reads as an alias), and a diff full of
#: quoted strings is harder to scan than one that says what it is.
ENV_PLACEHOLDER = "redacted:"

#: Per-process salt for :func:`_fingerprint`. Regenerated on restart, which is fine: the
#: fingerprints only ever need to be comparable within one rendered diff.
_SALT = secrets.token_bytes(16)

#: Fields a patch entry may touch. ``name`` is the key, ``delete`` is an operation.
FIELDS = ("description", "command", "env", "timeout", "min_role")


def _coerce_command(value: Any, name: str) -> list[str]:
    if isinstance(value, str):
        # Caught earlier than the parser would so the message can say why. A string
        # would have to be split into argv, and splitting is where a config value turns
        # into a shell command.
        raise ConfigError(f"server {name!r}: command 必须是参数数组，不能是一整行字符串")
    if not isinstance(value, list) or not value:
        raise ConfigError(f"server {name!r}: command 必须是非空数组")
    argv = [str(part) for part in value]
    if any(not part.strip() for part in argv):
        raise ConfigError(f"server {name!r}: command 含空参数")
    return argv


def _coerce_env(value: Any, name: str) -> dict[str, str]:
    if not isinstance(value, dict):
        raise ConfigError(f"server {name!r}: env 必须是键值映射")
    return {str(k): str(v) for k, v in value.items()}


def server_index(document: dict[str, Any]) -> dict[str, dict[str, Any]]:
    """Servers keyed by name, in file order."""
    entries = document.get("servers") or []
    if not isinstance(entries, list):
        return {}
    return {
        str(item.get("name")): item
        for item in entries
        if isinstance(item, dict) and item.get("name")
    }


def public_servers(document: dict[str, Any]) -> list[dict[str, Any]]:
    """The file as the editor may see it: ``env`` reduced to key names, never values."""
    out: list[dict[str, Any]] = []
    for entry in document.get("servers") or []:
        if not isinstance(entry, dict):
            continue
        out.append(
            {
                "name": str(entry.get("name") or ""),
                "description": str(entry.get("description") or ""),
                "command": [str(part) for part in (entry.get("command") or [])],
                "timeout": float(entry.get("timeout", 20.0) or 20.0),
                "min_role": str(entry.get("min_role") or "member"),
                "env_keys": sorted(str(key) for key in (entry.get("env") or {})),
            }
        )
    return out


def apply_server_patch(
    document: dict[str, Any],
    patch: list[dict[str, Any]],
) -> tuple[dict[str, Any], list[str]]:
    """Merge ``patch`` into ``document``, returning a new document and changed fields.

    Semantics, mirroring the provider engine where the meaning is the same:

    * a server in the patch is updated **field by field** — a field absent from the
      entry keeps its on-disk value;
    * a field explicitly ``null`` also keeps its on-disk value: a form binding that
      rendered nothing must not blank a field the operator never touched;
    * ``env`` present as a mapping **replaces** the whole mapping (values are never
      echoed back, so merge-per-key would be impossible to express);
    * ``{"name": x, "delete": true}`` removes the entry; deleting a name that is already
      gone is a no-op rather than an error;
    * a name not in the document is appended, and must carry a ``command``.
    """
    result = copy.deepcopy(document)
    entries = result.get("servers")
    if not isinstance(entries, list):
        entries = []
        result["servers"] = entries

    by_name = server_index(result)

    changed: list[str] = []
    seen: set[str] = set()
    for incoming in patch:
        name = str(incoming.get("name") or "").strip()
        if not name:
            raise ConfigError("MCP 补丁条目缺少 name")
        if name in seen:
            # Two entries for one name means the client built the payload wrong. Applying
            # them in order would make the last one win, and the diff would show only that
            # outcome — hiding the fact that half the payload was discarded.
            raise ConfigError(f"MCP 补丁中 name {name!r} 出现多次")
        seen.add(name)

        target = by_name.get(name)

        if incoming.get("delete"):
            if target is None:
                continue
            entries.remove(target)
            by_name.pop(name, None)
            changed.append(f"servers[{name}] (removed)")
            continue

        if target is None:
            fresh: dict[str, Any] = {"name": name}
            for field in FIELDS:
                value = incoming.get(field)
                if value is None:
                    continue
                fresh[field] = (
                    _coerce_command(value, name)
                    if field == "command"
                    else _coerce_env(value, name)
                    if field == "env"
                    else value
                )
            if not fresh.get("command"):
                raise ConfigError(f"新增 server {name!r} 必须提供 command")
            entries.append(fresh)
            by_name[name] = fresh
            changed.append(f"servers[{name}] (added)")
            continue

        for field in FIELDS:
            if field not in incoming:
                continue
            value = incoming[field]
            if value is None:
                continue
            if field == "command":
                value = _coerce_command(value, name)
            elif field == "env":
                value = _coerce_env(value, name)
            if target.get(field) == value:
                continue
            target[field] = value
            # Field name only, never a value: this string reaches the audit log.
            changed.append(f"servers[{name}].{field}")

    return result, changed


def validate_servers(document: dict[str, Any]) -> list[str]:
    """Run the boot-time parser over a candidate document.

    Same function the process uses at start, so "the panel accepted it" and "it boots"
    cannot diverge. ``parse_servers`` does not spawn anything.
    """
    try:
        parse_servers(document.get("servers") or [])
    except McpConfigError as exc:
        return [str(exc)]
    except Exception as exc:  # pragma: no cover - defensive
        return [f"校验时发生未预期的错误：{exc}"]
    return []


def _fingerprint(value: str) -> str:
    """A stable, non-invertible stand-in for one env value.

    Why not a flat ``***``: it renders old and new identically, so *changing a token
    would produce an empty diff* — the operator would be asked to confirm a change the
    screen says is not there. A salted hash keeps the line comparable (changed or not)
    while staying useless to anyone who sees it: the salt lives in this process and the
    values are high-entropy tokens, not dictionary words.
    """
    digest = hashlib.sha256(_SALT + value.encode("utf-8")).hexdigest()[:8]
    return f"{ENV_PLACEHOLDER}{digest}"


def render_redacted(document: dict[str, Any]) -> str:
    """Serialise for the diff with every ``env`` value replaced by a fingerprint.

    Redacting at render time rather than at patch time is deliberate: the value the
    operator typed still has to reach :func:`write_atomic`, it just must not appear in
    the text we show them — or in any screenshot of it.
    """
    redacted = copy.deepcopy(document)
    entries = redacted.get("servers")
    if isinstance(entries, list):
        for entry in entries:
            if isinstance(entry, dict) and isinstance(entry.get("env"), dict):
                entry["env"] = {
                    key: _fingerprint(str(value)) for key, value in entry["env"].items()
                }
    return render(redacted)


def build_mcp_patch(
    *,
    path: Path,
    patch: list[dict[str, Any]],
    base_hash: str,
) -> PatchResult:
    """Compute the candidate document and its redacted diff. **Does not write.**"""
    return build_patch(
        path=path,
        patch=patch,
        base_hash=base_hash,
        apply_fn=apply_server_patch,
        validate_fn=validate_servers,
        diff_render=render_redacted,
        filename="mcp.yaml",
    )
