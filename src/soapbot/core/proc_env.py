"""The environment a third-party child process is allowed to see.

Plugins and MCP servers both run code the operator did not write, and both used to
inherit the host environment wholesale. The plugin side had an allowlist; the MCP side
did not — it passed ``{**os.environ, **server.env}``, so a server started from
``npx -y <some-package>`` could read ``SOAPBOT_MASTER_KEY``, ``SOAPBOT_MASTER_KEY_FILE``
and every provider API key that happened to be exported into the host process.

``SECURITY.md`` grades MCP servers as *untrusted*. A trust grade the implementation
contradicts is worse than no grade at all, because it invites the reader to rely on it.

Both sides import this one module. A copy per side is how the two allowlists would drift
again, and drift in this direction fails open rather than closed.
"""

from __future__ import annotations

import os

#: Environment variables a child may see: everything needed to start an interpreter and
#: resolve system libraries, and nothing that identifies or authorises the host.
SAFE_ENV_KEYS = frozenset(
    {
        # Required for the interpreter to start and for system libraries to resolve.
        "PATH",
        "SYSTEMROOT",  # Windows: winsock/dll loading fails without it
        "SYSTEMDRIVE",
        "WINDIR",
        "COMSPEC",
        "PATHEXT",
        # Locale / encoding: without these a plugin writing Chinese text crashes on
        # a POSIX box with a C locale, which reads as "the plugin is broken".
        "LANG",
        "LC_ALL",
        "LC_CTYPE",
        "PYTHONIOENCODING",
        "PYTHONUTF8",
        # Temp + home: tmpfile() and ~ expansion need these to resolve. They are
        # not secrets (the child can reach the same paths from Python anyway).
        "TMPDIR",
        "TEMP",
        "TMP",
        "HOME",
        "USERPROFILE",
        # Certificate store location; without it outbound TLS fails confusingly.
        "SSL_CERT_FILE",
        "SSL_CERT_DIR",
        "REQUESTS_CA_BUNDLE",
    }
)

#: Prefix forwarded so operators can pass *plugin* config deliberately.
SAFE_ENV_PREFIX = "SOAPBOT_PLUGIN_"


def sanitize_env(
    base: dict[str, str] | None = None,
    extra: dict[str, str] | None = None,
    *,
    prefix: str = SAFE_ENV_PREFIX,
) -> dict[str, str]:
    """Return the environment a third-party child process may see.

    Keeps :data:`SAFE_ENV_KEYS` and the ``prefix`` family, drops everything else.
    ``extra`` is applied last for values the host wants to inject (resource caps, a
    server's own configuration) — host code controls it, never the child.

    Pass ``prefix=""`` to forward no prefixed variables at all. Note that an empty
    prefix cannot mean "match everything": ``str.startswith("")`` is true for every
    key, so an empty prefix is treated as "no prefix rule" rather than as a wildcard.
    """
    src = os.environ if base is None else base
    env = {
        k: v
        for k, v in src.items()
        if k in SAFE_ENV_KEYS or (prefix and k.startswith(prefix))
    }
    if extra:
        env.update({str(k): str(v) for k, v in extra.items()})
    return env
