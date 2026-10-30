"""Read ``config/mcp.yaml``.

The only interesting decision here is that a server's command must be an **argv list**,
never a string. A string would have to be split into arguments, and splitting is
exactly where quoting rules turn "read a file" into "run a shell". The file is operator
controlled, but a config file that can express a shell pipeline is a config file that
will eventually be written by a script, and at that point the quoting bug is real.

Nothing in this module reaches the network or starts a process: it produces
descriptions, and ``McpManager`` decides when to connect.
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any

import yaml

from soapbot.mcp.client import McpServer

logger = logging.getLogger(__name__)

#: Roles understood by the permission filter. Kept in step with
#: ``soapbot.security.roles.Role``; an unknown value is a configuration error rather
#: than a silent "allow", because the failure mode of a typo must not be more access.
KNOWN_ROLES = frozenset({"anonymous", "member", "admin", "owner"})


class McpConfigError(ValueError):
    """The MCP configuration is unusable. Raised at load, not on first call."""


def load_config(path: Path) -> list[McpServer]:
    """Return the configured servers. A missing file means "no MCP", not an error."""
    path = Path(path)
    if not path.is_file():
        return []

    try:
        raw = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    except (yaml.YAMLError, OSError) as exc:
        raise McpConfigError(f"cannot read {path}: {exc}") from exc

    if not isinstance(raw, dict):
        raise McpConfigError(f"{path.name} must be a mapping")

    servers = parse_servers(raw.get("servers") or [])
    logger.info("mcp configuration loaded servers=%d", len(servers))
    return servers


def parse_servers(entries: Any) -> list[McpServer]:
    """Validate a ``servers`` list and build descriptions from it.

    Split out of :func:`load_config` so the write path can validate a *candidate*
    document with the exact code that runs at boot. Two parsers would eventually
    disagree, and the disagreement would look like "the panel saved it, the process
    refused to start" — the failure mode the whole diff-then-apply design exists to
    prevent.
    """
    if not isinstance(entries, list):
        raise McpConfigError("'servers' must be a list")

    servers: list[McpServer] = []
    seen: set[str] = set()
    for index, entry in enumerate(entries):
        if not isinstance(entry, dict):
            raise McpConfigError(f"servers[{index}] must be a mapping")
        name = str(entry.get("name") or "").strip()
        if not name:
            raise McpConfigError(f"servers[{index}] has no name")
        if name in seen:
            # Two servers with one name would make the tool namespace ambiguous, and
            # whichever loaded last would silently win.
            raise McpConfigError(f"duplicate server name {name!r}")
        seen.add(name)

        command = entry.get("command")
        if isinstance(command, str):
            raise McpConfigError(
                f"server {name!r}: command must be a list of arguments, not a string"
            )
        if not isinstance(command, list) or not command:
            raise McpConfigError(f"server {name!r}: command must be a non-empty list")
        argv = tuple(str(part) for part in command)
        if any(not part for part in argv):
            raise McpConfigError(f"server {name!r}: command contains an empty argument")

        role = str(entry.get("min_role") or "member").strip().lower()
        if role not in KNOWN_ROLES:
            raise McpConfigError(
                f"server {name!r}: unknown min_role {role!r} (known: {sorted(KNOWN_ROLES)})"
            )

        timeout = entry.get("timeout", 20.0)
        try:
            timeout_value = float(timeout)
        except (TypeError, ValueError) as exc:
            raise McpConfigError(f"server {name!r}: timeout must be a number") from exc
        if timeout_value <= 0:
            raise McpConfigError(f"server {name!r}: timeout must be positive")

        env = entry.get("env") or {}
        if not isinstance(env, dict):
            raise McpConfigError(f"server {name!r}: env must be a mapping")

        servers.append(
            McpServer(
                name=name,
                command=argv,
                env={str(k): str(v) for k, v in env.items()},
                timeout=timeout_value,
                min_role=role,
                description=str(entry.get("description") or ""),
            )
        )

    return servers
