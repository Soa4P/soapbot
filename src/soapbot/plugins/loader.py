"""Plugin discovery, loading, unloading and hot reload.

Security posture of this module
-------------------------------
Loading a plugin is **executing third-party code**. The loader is therefore the
highest-risk component in the plugin system, and every decision here is made to
keep that execution predictable and reversible:

1. **Nothing loads implicitly.** A plugin present on disk is *discovered*, not
   loaded. Enabling is an explicit operator action. A plugin dropped into
   ``data/plugins/`` by an attacker who has write access to the data directory must
   not run on the next restart.

2. **Untrusted trust level requires opt-in.** ``trust: untrusted`` (the default)
   combined with any sensitive capability is refused unless the operator set
   ``allow_untrusted`` explicitly. This makes "install a plugin that can make HTTP
   requests and read memory" a deliberate, recorded choice.

3. **Manifest validated before import.** The name, entry point and dependency
   declarations are checked *before* the module is imported, so a hostile manifest
   never reaches the import machinery.

4. **Import is scoped and reversible.** Each plugin gets its own package namespace
   under ``soapbot_plugins.<name>``; unload removes exactly those modules. A
   plugin cannot shadow a stdlib or soapbot module by choosing a clever name,
   because its modules are always imported under that prefix.

5. **Failure is contained and rolled back.** If ``setup()`` raises, the plugin is
   unloaded, its registrations are discarded and the previous state is restored —
   a broken plugin update must not take the bot down or leave half-registered
   commands behind.

6. **Reload is ordered.** Old instance is torn down (``teardown()``, cron jobs
   cancelled, modules purged) *before* the new one is constructed. The reverse
   order leaves two instances holding the same command names and double-firing
   cron jobs.

7. **Every step is audited.** Load, unload, refusal and failure all produce an
   audit record naming the plugin and the reason.
"""

from __future__ import annotations

import asyncio
import importlib
import logging
import re
import shutil
import sys
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml

from soapbot.plugins.context import PluginContext
from soapbot.plugins.isolation import DEFAULT_PLUGIN_MEMORY_BYTES
from soapbot.plugins.manifest import (
    MANIFEST_ALT_FILENAME,
    MANIFEST_FILENAME,
    ManifestError,
    PluginManifest,
    TrustLevel,
    check_host_compatibility,
    digest_bytes,
    parse_manifest,
)
from soapbot.plugins.sandbox import (
    CapabilityGrant,
    CapabilityGuard,
    PluginInvocation,
)
from soapbot.security.audit import AuditLog, get_audit_log

logger = logging.getLogger(__name__)

#: Root package under which every plugin module is imported. Fixed, so a plugin's
#: modules can never collide with ``soapbot.*`` or the standard library.
PLUGIN_NAMESPACE = "soapbot_plugins"

#: Plugin ids are directory names. Mirrors ``manifest._NAME_RE`` but is kept
#: local because ``load()`` must reject a hostile name even when no manifest is
#: ever read (e.g. a name that escapes the root but has no plugin.yaml).
_PLUGIN_NAME_RE = re.compile(r"^[a-z][a-z0-9_-]{1,40}$")

MAX_MANIFEST_BYTES = 64 * 1024
"""A manifest is metadata, not content. A large one is either a mistake or an
attempt to make validation read attacker-sized input."""


class PluginLoadError(RuntimeError):
    """Raised when a plugin cannot be loaded. Never swallowed silently."""


@dataclass(slots=True)
class LoadedPlugin:
    """A plugin instance plus everything needed to tear it down cleanly."""

    manifest: PluginManifest
    path: Path
    instance: Any
    context: PluginContext
    module_names: list[str] = field(default_factory=list)
    """Fully-qualified module names created by this load, for exact unloading."""

    loaded_at: float = field(default_factory=time.time)
    last_error: str = ""
    invocations: int = 0

    worker: Any = None
    """Non-``None`` when this plugin runs in an isolated worker process.

    When set, ``instance`` is ``None`` — the plugin's code is *not* in this
    interpreter, so dispatch must go through ``worker.invoke``. Keeping both fields
    on one record (rather than a subclass) means every call site that asks "is this
    plugin loaded?" keeps working, and the isolation decision is visible where the
    plugin is represented instead of being spread across the dispatcher.
    """

    @property
    def isolated(self) -> bool:
        return self.worker is not None

    @property
    def name(self) -> str:
        return self.manifest.name

    def to_dict(self) -> dict[str, Any]:
        data = self.manifest.to_dict()
        data.update(
            {
                "path": str(self.path),
                "loaded_at": self.loaded_at,
                "last_error": self.last_error,
                "invocations": self.invocations,
                "api": self.context.exported_api(),
            }
        )
        return data


@dataclass(slots=True)
class DiscoveryReport:
    """Outcome of scanning the plugin directory.

    Separated from loading because "what is installed" and "what is running" are
    different questions, and conflating them is how an unvetted plugin ends up
    running.
    """

    found: list[PluginManifest] = field(default_factory=list)
    rejected: list[tuple[str, str]] = field(default_factory=list)
    """(path, reason) for manifests that failed validation."""


@dataclass(slots=True)
class LoadReport:
    """Outcome of loading the approved set at startup."""

    loaded: list[str] = field(default_factory=list)
    failed: list[tuple[str, str]] = field(default_factory=list)
    """(plugin name, reason). Reported at ``/api/plugins`` rather than raised."""


class PluginLoader:
    def __init__(
        self,
        *,
        plugins_dir: Path,
        audit: AuditLog | None = None,
        host_version: str = "0.1.0",
        allow_untrusted: bool = False,
        crypto=None,
        storage_backend: dict[str, dict[str, Any]] | None = None,
        memory=None,
        kb=None,
        supervisor=None,
        worker_timeout: float = 8.0,
        worker_memory_bytes: int = DEFAULT_PLUGIN_MEMORY_BYTES,
        approvals=None,
    ) -> None:
        self.plugins_dir = Path(plugins_dir)
        # When present, plugins load into their own process instead of this one.
        # ``None`` keeps the legacy in-process behaviour so existing tests and
        # embedded deployments (and platforms where subprocess isolation is
        # unavailable) still work — but the deployment default should be isolated.
        self.supervisor = supervisor
        self.worker_timeout = worker_timeout
        self.worker_memory_bytes = worker_memory_bytes
        # Set by ``PluginManager.install_isolation``. The loader needs it to install
        # a per-plugin surface router before a worker can issue its first callback.
        # ``None`` keeps in-process loading working unchanged.
        self.manager_ref = None
        # The stores backing ``ctx.memory`` / ``ctx.kb``. Held by the loader and
        # handed to each plugin context, so a plugin never receives the database or
        # the store itself — only the narrow APIs in ``plugins.memory_api``.
        self.memory = memory
        self.kb = kb
        self.audit = audit or get_audit_log()
        self.host_version = host_version
        self.allow_untrusted = allow_untrusted
        self.crypto = crypto
        self.storage_backend = storage_backend if storage_backend is not None else {}
        # One ledger for the whole loader: it is the host's record of which
        # sessions each plugin may send to. Created here (host side) and never
        # handed to a plugin as a writable object.
        from soapbot.plugins.isolation import SessionLedger

        self.session_ledger = SessionLedger()
        self._loaded: dict[str, LoadedPlugin] = {}
        # Approval decisions survive restarts through ``ApprovalStore``. ``None``
        # keeps the in-memory behaviour for tests and embedded use, but the
        # deployment path always supplies a store: an approval that vanishes on
        # restart is not an approval, and a headless deployment has no WebUI to
        # re-grant it.
        self.approvals = approvals
        self._approved: dict[str, frozenset[str]] = {}
        """plugin name -> approved capability values, set by the operator.

        Mirrors ``self.approvals`` for in-process lookups. Populated from the store
        on first read (see :meth:`_sync_approvals`) so a caller cannot observe an
        empty map while the file on disk says otherwise.
        """
        self._approvals_synced = approvals is None

    # ------------------------------------------------------------- discovery
    def discover(self) -> DiscoveryReport:
        """Scan for manifests. Reads metadata only; imports nothing."""
        report = DiscoveryReport()
        if not self.plugins_dir.exists():
            return report

        for entry in sorted(self.plugins_dir.iterdir()):
            if not entry.is_dir() or entry.name.startswith((".", "_")):
                continue
            # Refuse symlinks pointing outside the plugins directory: a link is
            # otherwise a way to make the loader import code from anywhere.
            if entry.is_symlink():
                report.rejected.append((str(entry), "symlinked plugin directory"))
                continue
            try:
                manifest = self._read_manifest(entry)
            except ManifestError as exc:
                report.rejected.append((str(entry), str(exc)))
                self.audit.record(
                    kind="plugin",
                    action="discover",
                    outcome="deny",
                    detail=f"dir={entry.name} {exc}",
                    plugin=entry.name,
                )
                continue
            except OSError as exc:
                report.rejected.append((str(entry), f"unreadable: {exc}"))
                continue
            report.found.append(manifest)
        return report

    def _read_manifest(self, directory: Path) -> PluginManifest:
        """Read the manifest and require its name to match the directory.

        The name/directory agreement is what makes "which plugin is this" have one
        answer, but it is checked *here* rather than in :meth:`read_manifest` because
        the installer parses the manifest before the directory has its final name.
        """
        manifest = self.read_manifest(directory)
        if manifest.name != directory.name:
            raise ManifestError(
                f"manifest name {manifest.name!r} does not match directory "
                f"{directory.name!r}"
            )
        return manifest

    def read_manifest(self, directory: Path) -> PluginManifest:
        """Parse and validate ``plugin.yaml`` in ``directory``, ignoring its name."""
        candidate = None
        for filename in (MANIFEST_FILENAME, MANIFEST_ALT_FILENAME):
            path = directory / filename
            if path.is_file():
                candidate = path
                break
        if candidate is None:
            raise ManifestError(f"no {MANIFEST_FILENAME} in {directory.name}")

        size = candidate.stat().st_size
        if size > MAX_MANIFEST_BYTES:
            raise ManifestError(f"manifest is {size} bytes (max {MAX_MANIFEST_BYTES})")

        raw_bytes = candidate.read_bytes()
        digest = digest_bytes(raw_bytes)
        try:
            # yaml.safe_load, never yaml.load: full_load can construct arbitrary
            # Python objects from tags like !!python/object/apply, which is remote
            # code execution during *parsing*, before any of our checks run.
            decoded = yaml.safe_load(raw_bytes.decode("utf-8"))
        except yaml.YAMLError as exc:
            raise ManifestError(f"malformed YAML: {exc}") from exc
        except UnicodeDecodeError as exc:
            raise ManifestError("manifest is not valid UTF-8") from exc

        manifest = parse_manifest(decoded, digest=digest)
        check_host_compatibility(manifest, self.host_version)
        return manifest

    # ---------------------------------------------------------------- loading
    def _sync_approvals(self) -> None:
        """One-shot read of the persistent store into ``_approved``.

        Lazy rather than eager so constructing a loader never touches disk: tests
        build loaders for directories that intentionally do not exist, and a
        constructor that reads a file would make ``PluginLoader(...)`` raise for
        reasons unrelated to the test's subject.
        """
        if self._approvals_synced or self.approvals is None:
            return
        self._approvals_synced = True
        for name, record in self.approvals.all().items():
            self._approved[name] = record.capabilities

    def approve(
        self,
        name: str,
        capabilities: set[str] | frozenset[str] | None = None,
        *,
        actor: str = "",
        manifest_digest: str = "",
    ) -> None:
        """Operator action: approve capabilities for a plugin.

        Approval is stored **separately from the manifest** on purpose. A plugin
        that updates its manifest to add ``HTTP`` must come back for approval; it
        cannot self-approve by editing a file it controls.

        The decision is written through to :class:`ApprovalStore`, so it holds
        across a restart. ``manifest_digest`` is recorded for drift reporting; pass
        the manifest's digest when it is known so that a later silent edit is
        visible to ``soapbot doctor``.
        """
        self._sync_approvals()
        caps = frozenset(capabilities or ())
        self._approved[name] = caps
        if self.approvals is not None:
            self.approvals.approve(
                name, caps, digest=manifest_digest, actor=actor or "loader"
            )

    def revoke(self, name: str, *, actor: str = "") -> None:
        """Withdraw approval. A loaded plugin is not unloaded by this call.

        Kept separate from :meth:`unload` deliberately: an operator may want to
        stop a plugin from coming back after a restart without interrupting the
        service right now, and an automatic unload here would make the two
        operations impossible to tell apart in the audit log.
        """
        self._sync_approvals()
        self._approved.pop(name, None)
        if self.approvals is not None:
            self.approvals.revoke(name)
        self.audit.record(
            kind="plugin",
            action="revoke",
            outcome="allow",
            detail=f"approval withdrawn by {actor or 'operator'}",
            plugin=name,
        )

    def approve_from_manifest(
        self, manifest: PluginManifest, *, actor: str = ""
    ) -> None:
        """Convenience for 'approve exactly what this manifest declares'."""
        self.approve(
            manifest.name,
            {c.value for c in manifest.capabilities},
            actor=actor,
            manifest_digest=manifest.manifest_digest,
        )

    def is_approved(self, name: str) -> bool:
        self._sync_approvals()
        return name in self._approved

    def approved_capabilities(self, name: str) -> frozenset[str]:
        self._sync_approvals()
        return self._approved.get(name, frozenset())

    def grant_for(self, manifest: PluginManifest) -> CapabilityGrant:
        from soapbot.plugins.manifest import Capability

        self._sync_approvals()
        approved = self._approved.get(manifest.name, frozenset())
        return CapabilityGrant(
            plugin=manifest.name,
            declared=manifest.capabilities,
            approved=frozenset(
                c for c in (Capability(a) for a in approved if a in {x.value for x in Capability})
            ),
        )

    async def load(self, name: str, *, force: bool = False) -> LoadedPlugin:
        """Load one plugin by name. Explicit; never triggered by discovery."""
        if name in self._loaded:
            raise PluginLoadError(f"plugin {name} is already loaded")

        # ``name`` arrives from an HTTP path parameter, so it must be validated
        # *before* being joined onto the plugins root. Joining first and relying on
        # a later check is fragile: the traversal fix in a prior review only worked
        # because the manifest's own name happened to disagree with ``../outside``.
        # A plugin directory whose manifest also says ``../outside`` — or any future
        # refactor that drops the name/directory comparison — would have executed
        # code from outside the plugins tree.
        if not isinstance(name, str) or not _PLUGIN_NAME_RE.match(name):
            self.audit.record(
                kind="plugin",
                action="load",
                outcome="deny",
                detail=f"invalid plugin name {str(name)[:64]!r}",
                plugin=str(name)[:64],
            )
            raise PluginLoadError(f"invalid plugin name {name!r}")

        directory = self.plugins_dir / name
        if not directory.is_dir():
            raise PluginLoadError(f"plugin directory not found: {directory}")

        # Symlink check repeated here (discover() also does it): load() is reachable
        # directly through the API without a discovery pass in between.
        if directory.is_symlink():
            raise PluginLoadError(f"plugin directory {name} is a symlink; refusing")
        root = self.plugins_dir.resolve()
        if root not in directory.resolve().parents:
            raise PluginLoadError(f"plugin directory {name} escapes the plugins root")

        manifest = self._read_manifest(directory)

        if not self.is_approved(name) and not force:
            self.audit.record(
                kind="plugin",
                action="load",
                outcome="deny",
                detail="not approved by operator",
                plugin=name,
            )
            raise PluginLoadError(
                f"plugin {name} is not approved; an operator must enable it explicitly"
            )

        # Untrusted code with network/data reach is refused unless explicitly allowed.
        if (
            manifest.trust is TrustLevel.UNTRUSTED
            and manifest.is_sensitive
            and not self.allow_untrusted
        ):
            self.audit.record(
                kind="plugin",
                action="load",
                outcome="deny",
                detail=f"untrusted plugin requests sensitive capabilities "
                f"{sorted(c.value for c in manifest.capabilities)}",
                plugin=name,
            )
            raise PluginLoadError(
                f"plugin {name} is marked untrusted and requests sensitive "
                "capabilities; set allow_untrusted only after reviewing the code"
            )

        grant = self.grant_for(manifest)
        guard = CapabilityGuard(grant, audit=self.audit)
        context = PluginContext(
            plugin=name,
            guard=guard,
            crypto=self.crypto,
            storage_backend=self.storage_backend,
            audit=self.audit,
            session_ledger=self.session_ledger,
            memory=self.memory,
            kb=self.kb,
        )

        # ---- isolated mode -------------------------------------------------------
        # When a supervisor is installed, the plugin's code is never imported into
        # this interpreter. That is the whole point: every in-process guarantee in
        # ``sandbox.py`` is a speed bump against ``object.__setattr__`` / ``ctypes``,
        # while a process boundary is not. The measured defect this closes: the
        # ``IsolatedRunner`` shipped earlier had **zero call sites in src/**, so
        # plugins still ran inside the host and the review's "layer 2" was a library
        # nobody used.
        if self.supervisor is not None:
            return await self._load_isolated(name, directory, manifest, context)

        try:
            module_names = self._import_plugin(manifest, directory)
        except Exception as exc:
            # An import-time failure (syntax error, bad import, deliberate raise)
            # must surface as a PluginLoadError, not as whatever the plugin's code
            # happened to throw. Otherwise a caller cannot distinguish "plugin is
            # broken" from "the host is broken", and reload handlers would leak a
            # plugin-controlled exception type into their own error paths.
            self.audit.record(
                kind="plugin",
                action="load",
                outcome="block",
                detail=f"import failed: {type(exc).__name__}",
                plugin=name,
            )
            raise PluginLoadError(
                f"plugin {name} failed to import: {type(exc).__name__}: {exc}"
            ) from exc

        instance = None
        try:
            module_name, _, attr = manifest.entry.partition(":")
            module = importlib.import_module(f"{PLUGIN_NAMESPACE}.{name}.{module_name}")
            factory = getattr(module, attr, None)
            if factory is None:
                raise PluginLoadError(
                    f"entry point {manifest.entry!r} not found in module"
                )
            instance = factory() if callable(factory) else factory

            setup = getattr(instance, "setup", None)
            if setup is not None:
                result = setup(context)
                if asyncio.iscoroutine(result):
                    await result
        except Exception as exc:
            # Roll back completely: purge modules so a retry starts clean, and do
            # not leave a half-initialised instance registered anywhere.
            self._purge_modules(module_names)
            self.audit.record(
                kind="plugin",
                action="load",
                outcome="block",
                detail=f"setup failed: {type(exc).__name__}",
                plugin=name,
            )
            raise PluginLoadError(f"plugin {name} failed to initialise: {exc}") from exc

        loaded = LoadedPlugin(
            manifest=manifest,
            path=directory,
            instance=instance,
            context=context,
            module_names=module_names,
        )
        self._loaded[name] = loaded
        self.audit.record(
            kind="plugin",
            action="load",
            outcome="allow",
            detail=f"v{manifest.version} trust={manifest.trust} "
            f"caps={sorted(c.value for c in manifest.capabilities)}",
            plugin=name,
        )
        logger.info("plugin loaded name=%s version=%s", name, manifest.version)
        return loaded

    async def load_approved(self) -> LoadReport:
        """Load every discovered plugin that the operator has approved.

        This is the step that makes an approval mean something. Discovery alone
        left the service in a state where a plugin was "enabled" on disk, reported
        as approved in the WebUI, and still not running — the operator had to
        re-click Load after every restart, and a headless deployment could never
        get a plugin running at all.

        The distinction from "auto-load everything you find" is the whole security
        argument, and it is worth stating precisely: this loads plugins whose
        selection came from a *durable operator decision*, not from the presence of
        a directory. A plugin dropped into ``data/plugins`` by an attacker has no
        approval record and is therefore still refused by :meth:`load`, exactly as
        before. What changed is only that a decision made once is not forgotten.

        Failures are collected, not raised: one broken plugin must not prevent the
        rest from starting, and the operator needs the list more than a traceback.
        """
        report = LoadReport()
        for manifest in self.discover().found:
            if not self.is_approved(manifest.name):
                continue
            if manifest.name in self._loaded:
                continue
            try:
                await self.load(manifest.name)
                report.loaded.append(manifest.name)
            except PluginLoadError as exc:
                report.failed.append((manifest.name, str(exc)))
                logger.error(
                    "approved plugin failed to load: %s -> %s", manifest.name, exc
                )
            except Exception as exc:  # pragma: no cover - defensive
                report.failed.append((manifest.name, type(exc).__name__))
                logger.exception("unexpected error loading plugin %s", manifest.name)
        return report

    async def _load_isolated(
        self,
        name: str,
        directory: Path,
        manifest: PluginManifest,
        context: PluginContext,
    ) -> LoadedPlugin:
        """Load a plugin into its own process instead of this one.

        The command table still lives in the host (``context.commands``), because the
        host must resolve ``/name`` before it can know which plugin to talk to. What
        does *not* live here is the handler code: the worker registers the names it
        implements, the host records those names, and dispatch forwards the call.

        This split is deliberate. If the host let the worker define the command table
        outright, a worker could register ``/forget`` and shadow a core command. By
        keeping registration host-side and only *accepting* a list of names, the
        existing reserved-name and duplicate checks still apply unchanged.
        """
        from soapbot.plugins.supervisor import WorkerConfig

        config = WorkerConfig(
            plugin=name,
            plugin_dir=directory,
            attr=(manifest.entry.split(":", 1)[1] if ":" in manifest.entry else "Plugin"),
            timeout=self.worker_timeout,
            memory_bytes=self.worker_memory_bytes,
        )
        self.supervisor.register(config)

        # Install the router *before* the worker starts, so the first callback it
        # makes (setup() may recall memory) already has an authorization path. Doing
        # this after start() would produce a window where a request arrives with no
        # router and is refused — which is safe, but makes a legitimate plugin fail
        # mysteriously on first load.
        attach = getattr(self.manager_ref, "attach_surface_router", None)
        if attach is not None:
            attach(name, guard=context._guard, ledger=self.session_ledger)

        # Wrap worker failures in the loader's own exception type. Callers (the API
        # layer, the CLI, existing tests) catch ``PluginLoadError`` and treat it as
        # "this plugin did not load"; leaking ``WorkerCrashedError`` would make every
        # one of them handle a second exception type that exists only because of an
        # implementation detail. The original type is preserved as the cause so the
        # distinction is still visible in the log.
        try:
            worker = await self.supervisor.start(name)
        except Exception as exc:
            # Surface the *plugin's own* exception type in the audit trail. The worker
            # deliberately reports types only (never messages — they are plugin-authored
            # and may carry credentials), so the parent re-embeds that type here. Losing
            # it would leave operators with "isolated start failed: WorkerCrashedError"
            # for every fault, which is unactionable: a syntax error and a deliberate
            # ``os._exit`` would look identical.
            reason = str(exc)
            inner = ""
            if "setup failed:" in reason:
                inner = reason.split("setup failed:", 1)[1].strip()
            detail = f"isolated start failed: {inner or type(exc).__name__}"
            self.audit.record(
                kind="plugin",
                action="load",
                outcome="block",
                detail=detail,
                plugin=name,
            )
            raise PluginLoadError(
                f"plugin {name} failed to start: {inner or type(exc).__name__}"
            ) from exc

        for entry in worker.commands:
            # Registered through the same paths as an in-process plugin, so the
            # reserved-name guard still fires (``validate_command_name``).
            spec = worker.api.get(entry) or {}
            is_tool = str(spec.get("kind") or "") == "tool"
            try:
                if is_tool:
                    context.register_proxied_tool(
                        entry, worker=worker, plugin=name, spec=spec
                    )
                else:
                    context.register_proxied_command(
                        entry, worker=worker, plugin=name, spec=spec
                    )
            except Exception as exc:
                await self.supervisor.stop(name)
                self.audit.record(
                    kind="plugin",
                    action="load",
                    outcome="block",
                    detail=f"{'tool' if is_tool else 'command'} registration failed: "
                    f"{type(exc).__name__}",
                    plugin=name,
                )
                raise PluginLoadError(
                    f"plugin {name} declared an unusable "
                    f"{'tool' if is_tool else 'command'} name: {exc}"
                ) from exc

        loaded = LoadedPlugin(
            manifest=manifest,
            path=directory,
            instance=None,
            context=context,
            module_names=[],
            worker=worker,
        )
        self._loaded[name] = loaded
        self.audit.record(
            kind="plugin",
            action="load",
            outcome="allow",
            detail=f"v{manifest.version} trust={manifest.trust} isolated=true "
            f"caps={sorted(c.value for c in manifest.capabilities)}",
            plugin=name,
        )
        logger.info(
            "plugin loaded name=%s version=%s isolated=true", name, manifest.version
        )
        return loaded

    def _import_plugin(self, manifest: PluginManifest, directory: Path) -> list[str]:
        """Import the plugin package under a fixed namespace.

        The package is registered under ``soapbot_plugins.<name>`` with its
        ``__path__`` pointing at the plugin directory. This means:

        * two plugins may both ship ``main.py`` without colliding,
        * a plugin named ``json`` cannot shadow the stdlib,
        * unloading removes only ``soapbot_plugins.<name>*`` entries.
        """
        # The namespace root is synthesised, not imported: it deliberately has no
        # filesystem presence, so ``soapbot_plugins`` can never be shadowed by a
        # directory that happens to be on sys.path.
        import types

        namespace_pkg = sys.modules.get(PLUGIN_NAMESPACE)
        if namespace_pkg is None:
            namespace_pkg = types.ModuleType(PLUGIN_NAMESPACE)
            namespace_pkg.__path__ = []  # type: ignore[attr-defined]
            namespace_pkg.__package__ = PLUGIN_NAMESPACE
            sys.modules[PLUGIN_NAMESPACE] = namespace_pkg

        pkg_name = f"{PLUGIN_NAMESPACE}.{manifest.name}"
        if pkg_name in sys.modules:
            self._purge_modules([pkg_name])

        package = types.ModuleType(pkg_name)
        package.__path__ = [str(directory)]  # type: ignore[attr-defined]
        package.__package__ = pkg_name
        sys.modules[pkg_name] = package
        setattr(namespace_pkg, manifest.name, package)

        created = [pkg_name]
        try:
            # Import the entry module explicitly so syntax errors and missing
            # imports surface here, with a clear message, rather than later inside
            # a handler.
            module_name = manifest.entry.split(":", 1)[0]
            full = f"{pkg_name}.{module_name}"
            importlib.import_module(full)
            created.extend(
                n for n in sys.modules if n == full or n.startswith(full + ".")
            )
        except Exception:
            self._purge_modules(created)
            raise
        return sorted(set(created))

    def _purge_modules(self, module_names: list[str]) -> None:
        """Remove the named modules plus any submodules of them.

        Correctness matters more than tidiness here: an over-eager purge would
        yank another *loaded* plugin's modules out of ``sys.modules`` while its
        handlers are still registered, producing an ``ImportError`` mid-conversation.
        So the sweep is restricted to roots that are not owned by any plugin still
        in ``self._loaded``.
        """
        prefixes = tuple(module_names)
        for name in sorted(module_names, key=len, reverse=True):
            sys.modules.pop(name, None)

        live_roots = {f"{PLUGIN_NAMESPACE}.{name}" for name in self._loaded}
        for name in [
            n
            for n in list(sys.modules)
            if n.startswith(f"{PLUGIN_NAMESPACE}.")
            and (n in prefixes or n.startswith(prefixes))
            and not any(n == r or n.startswith(r + ".") for r in live_roots)
        ]:
            sys.modules.pop(name, None)

    # ------------------------------------------------------------- unloading
    async def unload(self, name: str) -> None:
        """Tear a plugin down and remove every trace of it."""
        loaded = self._loaded.pop(name, None)
        if loaded is None:
            return

        # Session grants die with the plugin. A reload must start with an empty
        # allow-list: otherwise a plugin could earn a grant to a sensitive group,
        # be reloaded with different (possibly malicious) code, and keep the right
        # to send there. Revoking on unload makes the grant follow the code that
        # earned it rather than the name that happened to reuse it.
        from soapbot.plugins.isolation import HOST_AUTHORITY

        try:
            self.session_ledger.forget_plugin(name, authority=HOST_AUTHORITY)
        except PermissionError:  # pragma: no cover - ledger is host-owned
            logger.warning("could not revoke session grants for plugin=%s", name)

        # Isolated plugin: stop the worker process before anything else, so a
        # half-shut-down plugin cannot keep serving calls with a revoked ledger.
        if loaded.isolated and self.supervisor is not None:
            try:
                await self.supervisor.stop(name)
            except Exception as exc:  # pragma: no cover - defensive
                logger.warning("plugin %s worker stop failed: %s", name, exc)

        teardown = getattr(loaded.instance, "teardown", None)
        if teardown is not None:
            try:
                result = teardown()
                if asyncio.iscoroutine(result):
                    await result
            except Exception as exc:
                # Teardown failure must not prevent removal: leaving the plugin
                # registered would be worse than a leaked resource.
                logger.warning("plugin %s teardown failed: %s", name, exc)
                self.audit.record(
                    kind="plugin",
                    action="teardown",
                    outcome="block",
                    detail=type(exc).__name__,
                    plugin=name,
                )

        self._purge_modules(loaded.module_names)
        namespace_pkg = sys.modules.get(PLUGIN_NAMESPACE)
        if namespace_pkg is not None and hasattr(namespace_pkg, name):
            delattr(namespace_pkg, name)

        self.audit.record(
            kind="plugin", action="unload", outcome="allow", detail="", plugin=name
        )
        logger.info("plugin unloaded name=%s", name)

    # ---------------------------------------------------------------- reload
    async def reload(self, name: str) -> LoadedPlugin:
        """Hot reload: tear down the old instance, then load the new code.

        Order is deliberate. Loading first would leave two instances registering
        the same commands and both cron jobs firing until the old one was removed —
        visible as duplicated replies, and potentially as duplicated side effects
        (a plugin that posts to an external service would post twice).

        On failure the plugin stays *unloaded* rather than silently reverting to
        the previous code: a failed update is a state the operator must see, and
        silently running stale code hides that the update did not apply.
        """
        previous_manifest = None
        if name in self._loaded:
            previous_manifest = self._loaded[name].manifest
            await self.unload(name)

        try:
            loaded = await self.load(name, force=True)
        except PluginLoadError as exc:
            self.audit.record(
                kind="plugin",
                action="reload",
                outcome="block",
                detail=f"{type(exc).__name__}: {exc}"[:300],
                plugin=name,
            )
            logger.error("plugin reload failed name=%s err=%s", name, exc)
            raise

        if previous_manifest and previous_manifest.version != loaded.manifest.version:
            self.audit.record(
                kind="plugin",
                action="reload",
                outcome="allow",
                detail=f"{previous_manifest.version} -> {loaded.manifest.version}",
                plugin=name,
            )
        return loaded

    # ----------------------------------------------------------- introspection
    @property
    def loaded(self) -> dict[str, LoadedPlugin]:
        return dict(self._loaded)

    def get(self, name: str) -> LoadedPlugin | None:
        return self._loaded.get(name)

    def all_commands(self) -> dict[str, dict[str, Any]]:
        """Merged command table. First registration wins; conflicts are refused at
        registration time, so a collision here means a plugin bypassed ``ctx``."""
        table: dict[str, dict[str, Any]] = {}
        for loaded in self._loaded.values():
            for cmd, meta in loaded.context.commands.items():
                if cmd in table:
                    logger.error(
                        "duplicate command %s from plugin %s (already owned by %s)",
                        cmd,
                        loaded.name,
                        table[cmd]["plugin"],
                    )
                    continue
                table[cmd] = meta
        return table

    def all_tools(self) -> dict[str, dict[str, Any]]:
        table: dict[str, dict[str, Any]] = {}
        for loaded in self._loaded.values():
            for tool, meta in loaded.context.tools.items():
                if tool in table:
                    continue
                table[tool] = meta
        return table

    async def unload_all(self) -> None:
        for name in list(self._loaded):
            await self.unload(name)

    def snapshot(self) -> list[dict[str, Any]]:
        return [p.to_dict() for p in self._loaded.values()]

    @staticmethod
    def remove_from_disk(plugins_dir: Path, name: str) -> None:
        """Delete a plugin directory, refusing to escape the plugins root.

        ``name`` is attacker-influenced in the sense that it arrives from an HTTP
        path parameter. Without the containment check, ``name="../.."`` plus
        ``rmtree`` is an arbitrary directory deletion primitive.
        """
        root = Path(plugins_dir).resolve()
        target = (root / name).resolve()
        if root not in target.parents and target != root:
            raise ValueError(f"refusing to delete outside plugins dir: {target}")
        if not target.exists():
            return
        if target == root:
            raise ValueError("refusing to delete the plugins root")
        shutil.rmtree(target)


def record_invocation(
    audit: AuditLog, loaded: LoadedPlugin, invocation: PluginInvocation
) -> None:
    """Audit one plugin call. Errors are recorded without their message body.

    An exception message from a plugin can contain anything the plugin chose —
    including a credential or a fragment of another user's data. Only the type is
    recorded, so the audit trail itself cannot become a leak channel.
    """
    audit.record(
        kind="plugin",
        action=f"invoke:{invocation.entry}",
        outcome="allow" if invocation.ok else "block",
        detail=f"plugin={loaded.name} {invocation.duration_ms:.0f}ms "
        f"{invocation.error}".strip()[:300],
        plugin=loaded.name,
    )
