"""Plugin manifest: the declaration a plugin must make before it may load.

Threat model
------------
A plugin is **arbitrary third-party code running in-process**. There is no OS-level
sandbox in v1 (see the plan's Out of Scope), so the manifest is not a security
boundary by itself — every guarantee it claims must be backed by a runtime check in
:mod:`soapbot.plugins.sandbox`. What the manifest *does* provide is:

1. **A declarative contract** — the plugin states which capabilities it needs, so
   the operator can see the request before granting it, and the runtime can refuse
   calls the plugin never declared.
2. **A place to reject hostile metadata early** — names, versions, entry points and
   dependency lists are attacker-controlled text that reaches the filesystem and
   the import machinery. Each is validated here before anything touches disk.
3. **Pinned trust** — ``manifest_digest`` records the exact bytes that were
   reviewed, so a silent edit between review and load is detectable.

Validation rules and the attack each one closes
-----------------------------------------------
======================================  =========================================
Rule                                    Attack prevented
======================================  =========================================
``name`` matches ``^[a-z][a-z0-9_-]{1,40}$``  ``../../etc/cron.d/x`` path traversal via
                                        the plugin id (it becomes a directory name,
                                        a storage namespace and an import path)
entry point is ``module:attr`` only,     ``__import__("os").system(...)`` shipping as
  with the module inside the package     an entry "expression"; also stops loading
                                        ``os``/``sys`` as a "plugin"
no absolute/relative filesystem paths    reading ``/etc/shadow`` or ``..\\config``
  in ``entry``, ``requires`` or ``files``
``requires`` is a *declaration*, never    pip-installing at load time turns a plugin
  an install trigger                      install into arbitrary remote code exec
no ``__``-dunder in any identifier       ``__import__``/``__builtins__`` smuggling
``capabilities`` ⊆ known set             "grant me everything" manifests that would
                                        silently no-op a typo'd permission
``min_version`` checked against host     plugins written for a newer, incompatible
                                        host API
======================================  =========================================
"""

from __future__ import annotations

import hashlib
import json
import re
from dataclasses import dataclass, field
from enum import StrEnum
from typing import Any

MANIFEST_FILENAME = "plugin.yaml"
MANIFEST_ALT_FILENAME = "plugin.yml"

#: Plugin ids become directory names, storage namespaces and audit labels, so the
#: charset is deliberately narrow. A leading digit is rejected because the id is
#: also used to build Python-safe identifiers ("plugin_" + name).
_NAME_RE = re.compile(r"^[a-z][a-z0-9_-]{1,40}$")

#: ``module:attribute`` where module is a dotted path *inside the plugin package*.
#: ``$`` is excluded, as is anything that is not an identifier segment, so a
#: manifest cannot smuggle an expression such as ``os:system`` or ``a.b;c``.
_ENTRY_RE = re.compile(
    r"^[a-z_][a-z0-9_]*(\.[a-z_][a-z0-9_]*)*:[a-z_][a-z0-9_]*$",
    re.IGNORECASE,
)

_VERSION_RE = re.compile(r"^\d+\.\d+(\.\d+)?([abrc][0-9]+)?$")

#: Names that must never appear where a plugin-supplied identifier is expected.
_FORBIDDEN_TOKENS = (
    "__",
    ";",
    "&",
    "|",
    "`",
    "$(",
    "..",
    "\\",
    "/",
    "%00",
    "\x00",
    "\n",
    "\r",
)

_UNSAFE_REQ_RE = re.compile(r"[<>=!~@;\\/\s]")

#: Top-level module names a plugin entry must never point at. If the loader were
#: ever refactored to import the entry verbatim, ``os:system`` / ``sys:modules``
#: would become remote code execution; rejecting them here keeps that regression
#: from being silent.
_FORBIDDEN_ENTRY_ROOTS = frozenset(
    {
        "os",
        "sys",
        "subprocess",
        "shutil",
        "builtins",
        "importlib",
        "socket",
        "pathlib",
        "soapbot",
    }
)


class TrustLevel(StrEnum):
    """How much the operator vouches for this plugin's code.

    This is *metadata for the reviewer*, combined with capability checks at
    runtime. It is not a sandbox: marking a plugin ``TRUSTED`` does not make its
    ``os.system`` call safe, it only records that a human accepted the risk.
    """

    UNTRUSTED = "untrusted"
    """Default. Loaded only if explicitly enabled by the operator."""

    COMMUNITY = "community"
    """Reviewed by a human, capabilities still enforced."""

    TRUSTED = "trusted"
    """First-party. Capabilities still enforced (defence in depth)."""


class Capability(StrEnum):
    """Everything a plugin may do. Any API surface is gated by one of these."""

    COMMAND = "command"
    """Register slash commands."""

    MESSAGE = "message"
    """Observe (not intercept) inbound messages."""

    NOTICE = "notice"
    """Observe join/leave/mute events."""

    TOOL = "tool"
    """Expose function-calling tools to the model."""

    STORAGE = "storage"
    """Read/write its own key-value namespace."""

    HTTP = "http"
    """Make outbound HTTP requests."""

    CRON = "cron"
    """Register periodic jobs."""

    SESSION = "session"
    """Inspect conversation metadata for the current session."""

    MEMORY_READ = "memory_read"
    """Read memories in the caller's scope."""

    KB_READ = "kb_read"
    """Query the operator's knowledge base."""

    SEND = "send"
    """Send messages proactively (rate-limited, group-scoped)."""


#: Capabilities that can leak data or reach the network. A plugin holding any of
#: these is flagged in the WebUI, and the audit log records each use.
SENSITIVE_CAPABILITIES: frozenset[Capability] = frozenset(
    {
        Capability.HTTP,
        Capability.MEMORY_READ,
        Capability.KB_READ,
        Capability.SEND,
        Capability.STORAGE,
    }
)

#: Capabilities that can cost money or annoy users; always rate limited.
RATE_LIMITED_CAPABILITIES: frozenset[Capability] = frozenset(
    {Capability.HTTP, Capability.SEND, Capability.CRON, Capability.TOOL}
)


class ManifestError(ValueError):
    """Raised when a manifest fails validation. Always fail closed."""


@dataclass(slots=True)
class PluginManifest:
    """A validated manifest. Constructed only via :meth:`parse`."""

    name: str
    version: str
    entry: str
    description: str = ""
    author: str = ""
    capabilities: frozenset[Capability] = field(default_factory=frozenset)
    requires: tuple[str, ...] = ()
    """Declared Python dependencies. Displayed to the operator; **never installed**."""

    min_host_version: str = "0.1.0"
    trust: TrustLevel = TrustLevel.UNTRUSTED
    homepage: str = ""
    manifest_digest: str = ""
    """SHA-256 of the raw manifest bytes, for tamper detection."""

    @property
    def module(self) -> str:
        return self.entry.split(":", 1)[0]

    @property
    def attribute(self) -> str:
        return self.entry.split(":", 1)[1]

    @property
    def is_sensitive(self) -> bool:
        return bool(self.capabilities & SENSITIVE_CAPABILITIES)

    def to_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "version": self.version,
            "entry": self.entry,
            "description": self.description,
            "author": self.author,
            "capabilities": sorted(c.value for c in self.capabilities),
            "requires": list(self.requires),
            "min_host_version": self.min_host_version,
            "trust": self.trust.value,
            "homepage": self.homepage,
            "manifest_digest": self.manifest_digest,
        }


def _check_text(value: Any, *, label: str, max_len: int = 200) -> str:
    """Validate a free-text field that will be stored and displayed.

    Control characters are rejected rather than stripped: a manifest with a
    newline in ``author`` is either malformed or attempting log injection
    (``author: "x\\n2026-01-01 INFO plugin loaded"`` forges a log line).
    """
    if value is None:
        return ""
    if not isinstance(value, str):
        raise ManifestError(f"{label} must be a string")
    if len(value) > max_len:
        raise ManifestError(f"{label} exceeds {max_len} characters")
    lowered = value.lower()
    for token in _FORBIDDEN_TOKENS:
        if token in lowered:
            raise ManifestError(f"{label} contains forbidden token {token!r}")
    # These fields are displayed in the plugin management UI. A plugin is untrusted
    # input, and a manifest is a file its author controls *after* any review, so
    # ``description: "<img src=x onerror=...>"`` would be stored XSS against the
    # operator's own admin panel — the worst place to have one. Escaping at parse
    # time means every consumer (UI, API response, logs, future exporters) gets
    # inert text without each having to remember.
    from soapbot.security.injection import neutralise_markup

    return neutralise_markup(value.strip())


def _parse_capabilities(raw: Any) -> frozenset[Capability]:
    """Reject unknown capability names instead of ignoring them.

    Ignoring a typo (``"HTTR"``) would produce a plugin that silently lacks the
    permission it thinks it has — or, worse, if the check were inverted, one that
    silently gains it. Failing loudly is the only safe reading of an unknown verb.
    """
    if raw is None:
        return frozenset()
    if not isinstance(raw, list | tuple):
        raise ManifestError("capabilities must be a list")
    out: set[Capability] = set()
    for item in raw:
        if not isinstance(item, str):
            raise ManifestError("capability entries must be strings")
        try:
            out.add(Capability(item.strip().lower()))
        except ValueError as exc:
            known = ", ".join(sorted(c.value for c in Capability))
            raise ManifestError(
                f"unknown capability {item!r}; known: {known}"
            ) from exc
    return frozenset(out)


def _parse_requires(raw: Any) -> tuple[str, ...]:
    """Validate the *declared* dependency list.

    Nothing here is installed. Declaring a dependency is a request for the
    operator to install it; auto-installing on load would convert "install a
    plugin" into "run arbitrary code from PyPI chosen by the plugin author",
    which is a supply-chain hole with extra steps.

    Version specifiers are parsed only for display, so the grammar accepted is
    restricted to ``name`` and ``name<op>version`` with no extras, no URLs and no
    direct references (``pkg @ https://...``).
    """
    if raw is None:
        return ()
    if not isinstance(raw, list | tuple):
        raise ManifestError("requires must be a list")
    out: list[str] = []
    for item in raw:
        if not isinstance(item, str):
            raise ManifestError("requires entries must be strings")
        text = item.strip()
        if not text or len(text) > 80:
            raise ManifestError("invalid requires entry")
        name = re.split(r"[<>=!~]", text, maxsplit=1)[0].strip()
        if not re.fullmatch(r"[A-Za-z0-9_.\-]+", name):
            raise ManifestError(f"invalid dependency name {name!r}")
        if "://" in text or "@" in text:
            # Direct URL / VCS references bypass index review entirely.
            raise ManifestError("dependency URLs are not allowed in manifests")
        if _UNSAFE_REQ_RE.search(text.replace(" ", "")) and not re.fullmatch(
            r"[A-Za-z0-9_.\-]+([<>=!~]+[A-Za-z0-9_.\-]+)*", text.replace(" ", "")
        ):
            raise ManifestError(f"invalid dependency specifier {text!r}")
        out.append(text)
    return tuple(out)


def _version_tuple(text: str) -> tuple[int, ...]:
    core = re.split(r"[abrc]", text, maxsplit=1)[0]
    return tuple(int(p) for p in core.split(".") if p.isdigit())


def parse_manifest(raw: dict[str, Any], *, digest: str = "") -> PluginManifest:
    """Validate a decoded manifest mapping.

    Every field is checked; there is no "unknown field is fine" path for anything
    that reaches the filesystem, the import machinery or the capability gate.
    """
    if not isinstance(raw, dict):
        raise ManifestError("manifest must be a mapping")

    name = raw.get("name")
    if not isinstance(name, str) or not _NAME_RE.match(name):
        raise ManifestError(
            "name must match ^[a-z][a-z0-9_-]{1,40}$ "
            "(it becomes a directory name and storage namespace)"
        )

    version = raw.get("version")
    if not isinstance(version, str) or not _VERSION_RE.match(version):
        raise ManifestError(f"version {version!r} is not a valid semantic version")

    entry = raw.get("entry")
    if not isinstance(entry, str) or not _ENTRY_RE.match(entry):
        raise ManifestError(
            "entry must be 'module:attribute' with an in-package dotted module name"
        )
    # Dunder smuggling: ``main:__class__`` / ``__import__:x`` are valid identifiers
    # and would pass the shape check, but they name interpreter internals rather
    # than a plugin's own class. The loader calls whatever the entry resolves to,
    # so allowing a dunder here is a gadget, not a feature.
    if "__" in entry:
        raise ManifestError("entry must not contain a dunder name")
    module = entry.split(":", 1)[0]
    # The entry module is always imported as ``soapbot_plugins.<name>.<module>``, so
    # containment inside the plugin package is guaranteed by the loader, not by
    # string inspection here. What this check adds is a reject for entries that try
    # to name a top-level module directly (``os:system``), which would only work if
    # the loader were ever changed to import the entry as given — a regression this
    # makes visible now rather than as a silent RCE later.
    if module.split(".")[0] in _FORBIDDEN_ENTRY_ROOTS:
        raise ManifestError(
            f"entry module {module!r} refers to a top-level module; "
            "plugin modules must be imported from inside the plugin package"
        )

    trust_raw = str(raw.get("trust", "untrusted")).lower()
    try:
        trust = TrustLevel(trust_raw)
    except ValueError as exc:
        raise ManifestError(f"unknown trust level {trust_raw!r}") from exc

    min_host = str(raw.get("min_host_version", "0.1.0"))
    if not _VERSION_RE.match(min_host):
        raise ManifestError("min_host_version is not a valid version")

    return PluginManifest(
        name=name,
        version=version,
        entry=entry,
        description=_check_text(raw.get("description", ""), label="description", max_len=500),
        author=_check_text(raw.get("author", ""), label="author"),
        capabilities=_parse_capabilities(raw.get("capabilities")),
        requires=_parse_requires(raw.get("requires")),
        min_host_version=min_host,
        trust=trust,
        homepage=_check_text(raw.get("homepage", ""), label="homepage", max_len=300),
        manifest_digest=digest,
    )


def digest_bytes(data: bytes) -> str:
    """SHA-256 of raw manifest bytes, used for tamper detection."""
    return hashlib.sha256(data).hexdigest()


def digest_manifest(manifest: PluginManifest) -> str:
    """Stable digest of the *semantic* content, for change detection.

    Used when the on-disk bytes differ only in whitespace or key order: what
    matters is whether the declared capabilities changed, not the formatting.
    """
    payload = json.dumps(manifest.to_dict(), sort_keys=True, ensure_ascii=False)
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def check_host_compatibility(manifest: PluginManifest, host_version: str) -> None:
    """Reject plugins that require a newer host than we are.

    Loading a plugin written against a future API produces an ``AttributeError``
    deep inside a handler at an unpredictable moment; refusing at load time makes
    the incompatibility explicit and keeps the failure away from user traffic.
    """
    try:
        required = _version_tuple(manifest.min_host_version)
        host = _version_tuple(host_version)
    except (ValueError, TypeError) as exc:
        raise ManifestError("unparsable version") from exc
    if host < required:
        raise ManifestError(
            f"plugin {manifest.name} requires host >= {manifest.min_host_version}, "
            f"host is {host_version}"
        )
