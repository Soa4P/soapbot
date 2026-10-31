"""FastAPI application factory and process lifecycle.

What the lifespan does, and why it is the most important function here
---------------------------------------------------------------------
Before this wiring existed the app started an HTTP server and a plugin manager, and
nothing else. Every module needed to answer a QQ message — the pipeline, the adapter
registry, the memory stack — was reachable only from tests. ``soapbot start`` produced a
process with a green health check and no ability to receive a single message.

So the lifespan now builds the real thing:

    logging -> dirs -> auth -> database -> memory -> runtime (pipeline + plugins)
            -> adapters from config -> runtime.start() -> scheduler.start()

and unwinds it in the opposite order. Startup failures are of two kinds and are treated
differently on purpose:

* **Configuration that cannot be understood** (malformed YAML, a referenced environment
  variable that is not set) aborts startup with the file and field named. Half-honouring
  an unparseable intent would leave a service whose behaviour does not match its
  configuration, which is worse than not starting.
* **One adapter that fails to construct** is recorded and skipped. The rest of the
  service still runs, and the error is visible at ``/api/runtime`` — the operator needs a
  working UI precisely when something is broken.

Plugin management runs in three separate steps, and the split is the security
argument: **discover** reads manifests and imports nothing, **approve** records an
operator decision, **load** executes code. A bot that loaded whatever it found in
``data/plugins`` would run any code an attacker could write there — that directory
is writable by the service itself.

Startup loads exactly the plugins that carry a persisted approval (see
``_autoload_approved_plugins``). That is not a step back towards auto-loading:
the selector is a durable human decision living in
``data/plugin-approvals.json``, not the presence of a directory. A plugin dropped
into ``data/plugins`` still has no approval record and is still refused.
"""

from __future__ import annotations

import logging
import os
import time
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Any

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, HTMLResponse, JSONResponse
from fastapi.staticfiles import StaticFiles

from soapbot import __version__
from soapbot.api.admin import router as admin_router
from soapbot.api.auth import configure_auth
from soapbot.api.auth import router as auth_router
from soapbot.api.bilibili import router as bilibili_router
from soapbot.api.config_adapters import router as config_adapters_router
from soapbot.api.config_probe import router as config_probe_router
from soapbot.api.config_write import router as config_write_router
from soapbot.api.napcat import router as napcat_router
from soapbot.api.pipeline import router as pipeline_router
from soapbot.api.plugins import router as plugins_router
from soapbot.api.protocol import router as protocol_router
from soapbot.api.security import router as security_router
from soapbot.api.settings import router as settings_router
from soapbot.config import settings
from soapbot.logging_setup import setup_logging
from soapbot.security.tokens import BootstrapToken, TokenService

logger = logging.getLogger(__name__)

_STARTED_AT: dict[str, Any] = {}
_PLUGIN_MANAGER: Any = None
_RUNTIME: Any = None
_SCHEDULER: Any = None
_STARTUP_ERRORS: list[str] = []

_WEBUI_DIST = Path(__file__).resolve().parent / "webui" / "dist"


# --------------------------------------------------------------------- accessors
def get_plugin_manager():
    """Process-wide plugin manager, or ``None`` if the app is not started.

    A module-level accessor rather than a FastAPI dependency so non-HTTP callers
    (tests, CLI) can reach the same instance.
    """
    return _PLUGIN_MANAGER


def get_runtime():
    """Process-wide :class:`soapbot.core.runtime.BotRuntime`, or ``None``.

    ``None`` is a legitimate state (runtime disabled, or startup failed) and every
    caller must handle it: a 503 with "runtime is not initialised" is a better answer
    than an ``AttributeError`` rendered as a 500.
    """
    return _RUNTIME


def get_scheduler():
    return _SCHEDULER


def get_startup_errors() -> list[str]:
    """Errors accumulated during this process's startup, newest last."""
    return list(_STARTUP_ERRORS)


# -------------------------------------------------------------------------- auth
def _init_auth() -> None:
    """Create the token service and the one-time bootstrap credential."""
    service = TokenService(secret=settings.jwt_secret, ttl_hours=settings.jwt_ttl_hours)
    bootstrap = BootstrapToken(settings.init_token)

    if bootstrap.generated:
        # Written to a file rather than only logged. A credential in the log stream
        # ends up in whatever collects logs — often a shared system — and stays valid
        # for as long as the process runs. A 0600 file next to the database is the same
        # convenience without that reach.
        path = settings.data_dir / "init_token.txt"
        try:
            _write_private_file(path, bootstrap.reveal())
            logger.warning(
                "generated a one-time bootstrap token at %s — POST it to /api/auth/login "
                "to obtain an API token; the file is not a permanent credential",
                path,
            )
        except OSError as exc:  # pragma: no cover - read-only or full filesystem
            logger.error("could not write bootstrap token file (%s); it is lost", exc)

    configure_auth(service=service, bootstrap=bootstrap)
    logger.info("auth ready (jwt secret from %s)", service.secret_source)


def _write_private_file(path: Path, text: str) -> None:
    """Write a secret with owner-only permissions from the moment it exists."""
    from soapbot.security.files import write_private_file

    write_private_file(path, text.encode("utf-8"), what="bootstrap token")


# ---------------------------------------------------------------------- startup
async def _start_plugins_only() -> None:
    """Minimal startup for deployments with the runtime switched off.

    Also what the HTTP-only test suite exercises: routes and the plugin manager work,
    but no database is opened and no adapter is dialled.
    """
    from soapbot.core.builder import build_plugin_manager

    plugins_dir = settings.data_dir / "plugins"
    plugins_dir.mkdir(parents=True, exist_ok=True)
    manager = build_plugin_manager(
        plugins_dir, allow_untrusted=settings.allow_untrusted_plugins
    )
    _install_plugin_manager(manager)
    await _autoload_approved_plugins(manager)


async def _start_runtime() -> None:
    global _RUNTIME, _SCHEDULER

    from soapbot.core.builder import (
        build_memory_stack,
        build_runtime,
        load_dotenv_if_present,
    )
    from soapbot.core.config_files import build_router, load_providers
    from soapbot.core.config_seed import seed_config_dir
    from soapbot.core.scheduler import RuntimeScheduler
    from soapbot.memory.db import get_database

    # Already seeded in `lifespan`, before the runtime switch — kept here only because this
    # function can be reached by tests directly. It is idempotent.
    seed_config_dir(settings.config_dir, settings.config_template_dir)

    # Before any config is parsed: `api_key: env:NAME` reads os.environ, and in a
    # container the file holding those variables is on the data volume, not next to the
    # source tree. Loading it later would be loading it after the value was already
    # needed.
    load_dotenv_if_present()

    provider_configs = load_providers(settings.providers_file)
    router = build_router(provider_configs)
    logger.info("providers configured: %d", len(provider_configs))

    db = await get_database()
    memory, kb = build_memory_stack(db, router)

    plugins_dir = settings.data_dir / "plugins"
    plugins_dir.mkdir(parents=True, exist_ok=True)

    runtime = build_runtime(
        router=router,
        memory=memory,
        kb=kb,
        plugins_dir=plugins_dir,
        allow_untrusted_plugins=settings.allow_untrusted_plugins,
        allow_unknown_private=settings.allow_unknown_private,
        enable_budget=settings.enable_budget,
        enable_bilibili=settings.enable_bilibili,
    )
    _install_plugin_manager(runtime.plugins)
    # Before adapters: a message that arrives in the first second must not find an
    # empty command table for a plugin the operator already approved.
    await _autoload_approved_plugins(runtime.plugins)

    await _attach_adapters(runtime)

    _RUNTIME = runtime
    await runtime.start()

    scheduler = RuntimeScheduler(runtime)
    scheduler.start()
    _SCHEDULER = scheduler


def _install_plugin_manager(manager) -> None:
    global _PLUGIN_MANAGER
    _PLUGIN_MANAGER = manager
    if manager is None:
        return
    report = manager.loader.discover()
    logger.info(
        "plugins installed=%d rejected=%d", len(report.found), len(report.rejected)
    )
    for path, reason in report.rejected:
        logger.warning("plugin rejected path=%s reason=%s", path, reason)


async def _autoload_approved_plugins(manager) -> None:
    """Start plugins the operator approved in a previous run.

    Discovery is still the only way a plugin is *found*, and an unapproved
    directory is still never executed — that rule is unchanged and is what keeps a
    dropped-in plugin from running. What this adds is the other half of the
    contract: an approval, once given, is a standing instruction. Without it the
    service came up with every plugin idle after each restart, so a deployment
    could not actually depend on one, and the persisted approval file had no
    effect beyond being displayed.
    """
    if manager is None:
        return
    report = await manager.loader.load_approved()
    if report.loaded:
        logger.info("plugins autoloaded: %s", ", ".join(report.loaded))
    for name, reason in report.failed:
        _STARTUP_ERRORS.append(f"plugin {name}: {reason}")
        logger.error("approved plugin failed to autoload: %s -> %s", name, reason)


async def _attach_adapters(runtime) -> None:
    """Construct every enabled adapter from ``adapters.yaml`` and hand it to the runtime."""
    from soapbot.adapters import create as create_adapter
    from soapbot.core.config_files import load_adapters

    for config in load_adapters(settings.adapters_file):
        if not config.enabled:
            logger.info("adapter %s disabled in configuration", config.kind)
            continue
        try:
            adapter = create_adapter(config.kind, **config.options)
        except Exception as exc:
            # Recorded, not raised: one unusable adapter must not take the management
            # API down with it, because that API is how the operator finds out.
            message = f"adapter {config.kind}: {type(exc).__name__}: {exc}"
            _STARTUP_ERRORS.append(message)
            logger.error("adapter construction failed: %s", message)
            continue
        await runtime.add_adapter(adapter)
        logger.info("adapter registered: %s", config.kind)


# --------------------------------------------------------------------- shutdown
async def _shutdown() -> None:
    global _PLUGIN_MANAGER, _RUNTIME, _SCHEDULER

    if _SCHEDULER is not None:
        _SCHEDULER.shutdown()
        _SCHEDULER = None

    runtime = _RUNTIME
    if runtime is not None:
        # Close the Bilibili HTTP pool before the runtime stops: a plugin or command
        # that is unwinding must not find a closed client mid-request.
        if getattr(runtime, "bilibili", None) is not None:
            try:
                await runtime.bilibili.close()
            except Exception as exc:  # pragma: no cover - shutdown must not raise
                logger.warning("bilibili client close failed: %s", exc)
        await runtime.stop()
        _RUNTIME = None

    if _PLUGIN_MANAGER is not None:
        try:
            await _PLUGIN_MANAGER.loader.unload_all()
        except Exception as exc:  # pragma: no cover
            logger.warning("plugin unload failed: %s", exc)
        _PLUGIN_MANAGER = None

    if settings.enable_runtime:
        from soapbot.memory.db import reset_database

        try:
            await reset_database()
        except Exception as exc:  # pragma: no cover
            logger.warning("database shutdown failed: %s", exc)

    logger.info("soapbot stopped")


@asynccontextmanager
async def lifespan(app: FastAPI):
    setup_logging()
    settings.ensure_dirs()
    _STARTED_AT["ts"] = time.time()
    _STARTUP_ERRORS.clear()

    _init_auth()

    # Seed regardless of the runtime switch. The panel edits providers/adapters whether or
    # not the bot itself is running, and on a fresh Windows install with
    # SOAPBOT_ENABLE_RUNTIME=false the config directory used to not exist at all — the page
    # then reported "not writable" and the first save had nowhere to go. Seeding only from
    # inside _start_runtime made the config directory a side effect of the bot starting.
    from soapbot.core.config_seed import seed_config_dir

    seed_config_dir(settings.config_dir, settings.config_template_dir)

    if settings.enable_runtime:
        await _start_runtime()
    else:
        await _start_plugins_only()

    logger.info(
        "soapbot %s starting on %s:%s runtime=%s",
        __version__,
        settings.host,
        settings.port,
        "on" if settings.enable_runtime else "off",
    )

    try:
        yield
    finally:
        await _shutdown()


# -------------------------------------------------------------------------- app
def create_app() -> FastAPI:
    app = FastAPI(
        title="soapbot",
        version=__version__,
        description="QQ group chat AI bot framework",
        lifespan=lifespan,
    )

    app.add_middleware(
        CORSMiddleware,
        # The Vite dev server only. In production the UI is served from this same
        # origin, so a wider list would be permission nobody needs — and
        # ``allow_credentials`` plus a wildcard origin is rejected by browsers anyway,
        # which makes a too-generous list misleading as well as unnecessary.
        allow_origins=[
            "http://localhost:5173",
            "http://127.0.0.1:5173",
        ],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    @app.get("/api/health", tags=["system"])
    async def health() -> JSONResponse:
        """Liveness only: the process is up and can answer HTTP.

        Deliberately does not report runtime state. A health check that goes red
        because no adapter is configured would take the management UI down exactly
        when the operator needs it; ``/api/runtime`` is where that belongs.
        """
        uptime = time.time() - _STARTED_AT.get("ts", time.time())
        return JSONResponse(
            {
                "status": "ok",
                "version": __version__,
                "uptime_seconds": round(uptime, 3),
            }
        )

    @app.get("/healthz", tags=["system"], include_in_schema=False)
    async def healthz() -> JSONResponse:
        """Kubernetes-style liveness probe: identical to ``/api/health``.

        Two paths for one fact, because the container healthcheck and every reverse
        proxy config in the wild expect different names, and "which one is it" is not
        a question an operator should answer by reading the source.
        """
        return await health()

    @app.get("/readyz", tags=["system"])
    async def readyz() -> JSONResponse:
        """Readiness: can this process do its job right now?

        Deliberately narrower than ``/api/runtime``. A readiness probe that fails
        because a QQ account is offline would pull the console out of a load balancer
        precisely when the operator needs it to investigate.

        What is checked is what makes the process useless: the data directory cannot be
        written (SQLite writes through it, so a full disk or a read-only mount shows up
        here first), or the runtime was asked for and failed to build.
        """
        problems: list[str] = []

        from soapbot.config import settings as live_settings

        data_dir = Path(live_settings.data_dir)
        try:
            data_dir.mkdir(parents=True, exist_ok=True)
            probe = data_dir / f".readyz-{os.getpid()}"
            probe.write_text("ok", encoding="utf-8")
            probe.unlink()
        except OSError as exc:
            problems.append(f"data directory not writable: {exc}")

        runtime = get_runtime()
        if live_settings.enable_runtime and runtime is None:
            problems.append("runtime was requested but is not built")
        if runtime is not None and not getattr(runtime, "_running", False):
            problems.append("runtime is built but not running")

        errors = get_startup_errors()
        if errors:
            # Startup errors are warnings by policy (a missing adapter must not stop
            # the process), so they are reported without failing readiness.
            logger.debug("readiness note: %d startup errors", len(errors))

        payload = {
            "status": "ok" if not problems else "unavailable",
            "version": __version__,
            "data_dir": str(data_dir),
            "problems": problems,
            "startup_errors": errors,
        }
        return JSONResponse(payload, status_code=200 if not problems else 503)

    app.include_router(auth_router)
    app.include_router(security_router)
    app.include_router(admin_router)
    app.include_router(plugins_router)
    app.include_router(bilibili_router)
    app.include_router(config_write_router)
    app.include_router(config_adapters_router)
    # Next to the config routes: the test buttons take the same draft payload the diff
    # endpoints take, and an operator debugging a save wants both on one page.
    app.include_router(config_probe_router)
    # "Which protocol end is already running here" — the question a person asks right
    # before they are asked to type a WebSocket URL.
    app.include_router(protocol_router)
    # Starting the protocol end and showing its QR: the step after "which port is it on".
    app.include_router(napcat_router)
    app.include_router(pipeline_router)
    app.include_router(settings_router)

    _mount_webui(app)
    return app


def _mount_webui(app: FastAPI) -> None:
    """Serve the built management panel, or explain that it is not built.

    Assets are mounted from a single directory and every other non-API path returns
    ``index.html``. Serving arbitrary files from the dist tree would be a path
    traversal waiting to happen (``../`` in the path), and a Vue router in history mode
    needs the catch-all anyway — one decision solves both.
    """
    index = _WEBUI_DIST / "index.html"
    if index.is_file():
        assets = _WEBUI_DIST / "assets"
        if assets.is_dir():
            app.mount("/assets", StaticFiles(directory=assets), name="webui-assets")

        @app.get("/{full_path:path}", include_in_schema=False)
        async def spa(full_path: str) -> FileResponse:
            if full_path.startswith("api/") or full_path == "api":
                # Unknown API route: a JSON 404, not an HTML page. Returning the SPA
                # shell here would make a typo'd endpoint look like it succeeded.
                raise HTTPException(status_code=404, detail="Not Found")
            # The shell names hashed assets, so caching it is how a rebuilt panel keeps
            # showing the previous bundle: the browser reuses an old index.html that points
            # at files which no longer exist, and the page renders empty or half-updated.
            # That is the difference between "I shipped it" and "the operator sees it".
            return FileResponse(index, headers={"Cache-Control": "no-store"})

        logger.info("serving WebUI from %s", _WEBUI_DIST)
        return

    @app.get("/", include_in_schema=False)
    async def webui_missing() -> HTMLResponse:
        return HTMLResponse(
            "<!doctype html><meta charset='utf-8'>"
            "<title>soapbot</title>"
            "<body style=\"font-family:system-ui;background:#0b0e14;color:#c9d1d9;"
            "padding:3rem;line-height:1.7\">"
            "<h1 style='font-size:1.2rem'>管理面板尚未构建</h1>"
            "<p>该安装包不包含前端产物。请在后端目录执行：</p>"
            "<pre style='background:#151a23;padding:1rem;border-radius:8px'>"
            "cd webui &amp;&amp; npm install &amp;&amp; npm run build</pre>"
            "<p>然后重启服务。API 已可用：<code>/api/health</code>，"
            "<code>/docs</code>。</p></body>",
            status_code=200,
        )

    logger.warning("WebUI bundle not found at %s", _WEBUI_DIST)


app = create_app()
