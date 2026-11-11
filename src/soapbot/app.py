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
import secrets
import time
from collections.abc import AsyncIterator, Callable
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Any

from fastapi import Depends, FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, HTMLResponse, JSONResponse, Response
from fastapi.staticfiles import StaticFiles
from starlette.middleware.gzip import GZipMiddleware

from soapbot import __version__
from soapbot.api.admin import router as admin_router
from soapbot.api.auth import configure_auth, require_api_auth
from soapbot.api.auth import router as auth_router
from soapbot.api.bilibili import router as bilibili_router
from soapbot.api.config_adapters import router as config_adapters_router
from soapbot.api.config_probe import router as config_probe_router
from soapbot.api.config_write import router as config_write_router
from soapbot.api.errors import install_error_handlers
from soapbot.api.napcat import router as napcat_router
from soapbot.api.pipeline import router as pipeline_router
from soapbot.api.plugins import router as plugins_router
from soapbot.api.protocol import router as protocol_router
from soapbot.api.security import router as security_router
from soapbot.api.settings import router as settings_router
from soapbot.config import settings
from soapbot.core import log_context
from soapbot.logging_setup import setup_logging
from soapbot.security.tokens import (
    BOOTSTRAP_FILE,
    TokenService,
    bootstrap_for_data_dir,
)

logger = logging.getLogger(__name__)

_STARTED_AT: dict[str, Any] = {}

#: Largest request body the API will read, in bytes.
#:
#: 8 MiB is chosen against the largest legitimate body this API receives — a plugin
#: upload — with room to spare, and far below anything that would matter to RSS. The
#: point is not a precise quota but a ceiling: before this, a JSON endpoint would buffer
#: whatever it was sent, so "how much memory can a stranger make this process allocate"
#: had no answer.
MAX_REQUEST_BODY_BYTES = 8 * 1024 * 1024

#: The Vite dev server only. In production the panel is served from this same origin.
#: Kept as one constant so the non-wildcard assertion and the middleware cannot drift.
_CORS_ORIGINS = ["http://localhost:5173", "http://127.0.0.1:5173"]

_PLUGIN_MANAGER: Any = None
_RUNTIME: Any = None
_SCHEDULER: Any = None
_GATEWAY: Any = None
"""OneBot 11 gateway, when enabled. Stopped before the runtime drains: an action
arriving during shutdown would send through an adapter that is closing."""
_STARTUP_ERRORS: list[str] = []

_WEBUI_DIST = Path(__file__).resolve().parent / "webui" / "dist"

# Metric families exposed on /metrics, as (name, type, help, key in ProviderStat.stats()).
# Declared once so the disabled-runtime branch can still publish empty families: a
# dashboard should show "no data" after the runtime is switched off, not keep drawing a
# stale series from before.
_PROVIDER_METRICS: tuple[tuple[str, str, str, str], ...] = (
    ("soapbot_provider_calls_total", "counter", "Attempts per provider.", "calls"),
    ("soapbot_provider_failures_total", "counter", "Failed attempts per provider.", "failures"),
    (
        "soapbot_provider_prompt_tokens_total",
        "counter",
        "Prompt tokens consumed per provider.",
        "prompt_tokens",
    ),
    (
        "soapbot_provider_completion_tokens_total",
        "counter",
        "Completion tokens produced per provider.",
        "completion_tokens",
    ),
    ("soapbot_provider_latency_p50_ms", "gauge", "Median recent latency per provider.", "p50_latency_ms"),
    ("soapbot_provider_latency_p95_ms", "gauge", "p95 recent latency per provider.", "p95_latency_ms"),
    ("soapbot_provider_cooling_down", "gauge", "1 while the provider is in cooldown.", "cooling_down"),
)


def _prometheus_label(value: Any) -> str:
    """Escape a label value per the Prometheus text exposition format."""
    return str(value).replace("\\", "\\\\").replace('"', '\\"').replace("\n", "\\n")


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
def _init_auth(app: Any = None) -> None:
    """Create the token service and the one-time bootstrap credential."""
    from soapbot.security.revocation import RevocationStore, default_path

    revocations = RevocationStore(default_path(settings.data_dir))
    # Prune on boot rather than on every verify: an expired entry is already rejected by
    # the signature check, so the only reason to keep the file tidy is that a list an
    # operator never sees grow is one they will edit by hand or delete.
    try:
        pruned = revocations.prune()
        if pruned:
            logger.info("pruned %d expired token revocation(s)", pruned)
    except RuntimeError as exc:
        # A corrupt revocation file must stop startup: continuing would treat every
        # revoked token as valid, which is the one outcome this must not have.
        logger.error("%s", exc)
        raise

    service = TokenService(
        secret=settings.jwt_secret.get_secret_value(),
        ttl_hours=settings.jwt_ttl_hours,
        idle_hours=settings.jwt_idle_hours,
        revocations=revocations,
    )
    # The credential lives on disk, not in this process. It used to be regenerated on
    # every start, so each deploy silently invalidated whatever the operator had saved;
    # the log showed six startups and six "generated a one-time bootstrap token" lines.
    # bootstrap_for_data_dir reuses an unredeemed value and refuses to mint a new one
    # after it has been spent — that now requires an explicit `soapbot token --reset`.
    bootstrap = bootstrap_for_data_dir(
        settings.data_dir, settings.init_token.get_secret_value()
    )
    path = settings.data_dir / BOOTSTRAP_FILE

    if bootstrap.generated:
        logger.warning(
            "generated a one-time bootstrap token at %s — POST it to /api/auth/login "
            "to obtain an API token; it stays valid across restarts until redeemed",
            path,
        )
    elif not bootstrap.available:
        logger.info(
            "bootstrap token was already redeemed; login stays closed until "
            "`soapbot token --reset` is run on the host and the service restarted"
        )
    else:
        logger.info("reusing the unredeemed bootstrap token at %s", path)

    configure_auth(
        service=service, bootstrap=bootstrap, revocations=revocations, app=app
    )
    logger.info("auth ready (jwt secret from %s)", service.secret_source)


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

    await _start_onebot_gateway(runtime)

    scheduler = RuntimeScheduler(runtime)
    scheduler.start()
    _SCHEDULER = scheduler


async def _start_onebot_gateway(runtime: Any) -> None:
    """Start the OneBot bridge when configured, or say why it did not start.

    A misconfiguration here must not abort boot: the chat works without the bridge,
    and an operator who cannot open the panel cannot fix a setting that stopped the
    panel from starting.
    """
    global _GATEWAY

    if not settings.onebot_gateway_enabled:
        return

    adapter = runtime.adapters.get("qq_official")
    if adapter is None:
        logger.warning(
            "onebot gateway is enabled but no qq_official adapter is registered; "
            "the bridge only speaks for the official bot"
        )
        return

    from soapbot.gateway import GatewayError, OneBot11Gateway

    gateway = OneBot11Gateway(
        adapter,
        access_token=settings.onebot_gateway_token.get_secret_value(),
        host=settings.onebot_gateway_host,
        port=settings.onebot_gateway_port,
        path=settings.onebot_gateway_path,
    )
    try:
        await gateway.start()
    except GatewayError as exc:
        logger.error("onebot gateway refused to start: %s", exc)
        return
    _GATEWAY = gateway


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
            # Recorded, and only raised when strict_startup is on. The default keeps
            # the management API available — it is how the operator finds out — while
            # an operator who wants a hard boundary can make a broken adapter abort
            # boot instead of surfacing hours later as a missing connection.
            message = f"adapter {config.kind}: {type(exc).__name__}: {exc}"
            _STARTUP_ERRORS.append(message)
            logger.error("adapter construction failed: %s", message)
            if settings.strict_startup:
                raise RuntimeError(f"strict startup refused: {message}") from exc
            continue
        await runtime.add_adapter(adapter)
        logger.info("adapter registered: %s", config.kind)


# --------------------------------------------------------------------- shutdown
async def _shutdown() -> None:
    global _GATEWAY, _PLUGIN_MANAGER, _RUNTIME, _SCHEDULER

    # First, stop accepting new actions. The gateway sends through the same adapter
    # the runtime is about to close, so draining first would let a queued
    # ``send_group_msg`` race the adapter's own shutdown.
    if _GATEWAY is not None:
        try:
            await _GATEWAY.stop()
        except Exception as exc:  # pragma: no cover - shutdown must not raise
            logger.warning("onebot gateway stop failed: %s", exc)
        _GATEWAY = None

    if _SCHEDULER is not None:
        _SCHEDULER.shutdown()
        _SCHEDULER = None

    runtime = _RUNTIME
    if runtime is not None:
        # Drain before closing anything: handlers still in flight are mid-reply and
        # mid-archive, and a shutdown that closes sockets and the database first
        # turns their last write into an exception inside a cancelled task — which
        # looks like a clean stop and silently loses the replies that were underway.
        try:
            await runtime.drain(timeout=5.0)
        except Exception as exc:  # pragma: no cover - shutdown must not raise
            logger.warning("runtime drain failed: %s", exc)
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
        manager = _PLUGIN_MANAGER
        try:
            await manager.loader.unload_all()
        except Exception as exc:  # pragma: no cover
            logger.warning("plugin unload failed: %s", exc)
        finally:
            # unload_all() reaps workers too, but an exception inside it must not
            # leave resident children behind. stop_all() is idempotent.
            supervisor = getattr(manager.loader, "supervisor", None)
            if supervisor is not None:
                try:
                    await supervisor.stop_all()
                except Exception as exc:  # pragma: no cover - shutdown must not raise
                    logger.warning("plugin worker shutdown failed: %s", exc)
        _PLUGIN_MANAGER = None

    if settings.enable_runtime:
        from soapbot.memory.db import reset_database

        try:
            await reset_database()
        except Exception as exc:  # pragma: no cover
            logger.warning("database shutdown failed: %s", exc)

    # Last, after everything that might still be mid-request. Closing the shared pool
    # earlier would turn an in-flight provider call into a "client has been closed"
    # error during shutdown, which reads like a bug in the reply path.
    from soapbot.net import reset_outbound

    try:
        await reset_outbound()
    except Exception as exc:  # pragma: no cover - shutdown must not raise
        logger.warning("outbound client close failed: %s", exc)

    logger.info("soapbot stopped")


def _clean_stale_temp() -> None:
    """Delete leftovers under ``data/tmp`` older than a day.

    Uploads and probes stage files there. A process that dies mid-write leaves them
    behind forever, and on a container with a small volume that eventually fills the
    disk — a failure whose cause is a file nobody remembers creating.
    """
    import shutil
    import time

    from soapbot.config import settings

    root = settings.data_dir / "tmp"
    if not root.is_dir():
        return
    cutoff = time.time() - 24 * 3600
    removed = 0
    for entry in root.iterdir():
        try:
            if entry.stat().st_mtime >= cutoff:
                continue
            if entry.is_dir():
                shutil.rmtree(entry, ignore_errors=True)
            else:
                entry.unlink(missing_ok=True)
            removed += 1
        except OSError:
            continue
    if removed:
        logger.info("removed %d stale temporary entr(ies) from %s", removed, root)


def _audit_env_file() -> None:
    """Report misspelled ``SOAPBOT_*`` keys in the ``.env`` this process reads.

    ``Settings`` validates ``os.environ``, but the file is loaded into the environment by
    ``load_dotenv_if_present`` — after the settings object exists. A typo written into the
    file was therefore never checked by anything, and the operator's symptom was the one
    this whole hardening pass exists to remove: the process starts, reports healthy, and
    the value they set does nothing.

    A warning rather than a crash: the panel rewrites this file, and refusing to boot over
    a stray line would turn a cosmetic mistake into an outage. The message goes into the
    startup errors the panel already surfaces, so it is visible without reading logs.
    """
    from soapbot.config import unknown_env_keys

    path = Path(os.environ.get("SOAPBOT_ENV_FILE", ".env"))
    try:
        findings = unknown_env_keys(path)
    except Exception as exc:  # pragma: no cover - defensive
        logger.debug("env file audit skipped: %s", exc)
        return
    if not findings:
        return
    message = (
        f"{path}: 未知的 SOAPBOT_ 配置项，改了也不会生效 — " + ", ".join(findings)
    )
    logger.warning("%s", message)
    _STARTUP_ERRORS.append(message)


@asynccontextmanager
async def lifespan(app: FastAPI):
    setup_logging()
    settings.ensure_dirs()
    _STARTED_AT["ts"] = time.time()
    _STARTUP_ERRORS.clear()

    _audit_env_file()
    _init_auth(app)
    _clean_stale_temp()

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

    install_error_handlers(app)

    # 1 KB floor: below that the framing overhead outweighs the saving. Everything the
    # panel serves is well above it.
    app.add_middleware(_CompressExceptEvents, minimum_size=1024)

    app.add_middleware(
        CORSMiddleware,
        # The Vite dev server only. In production the UI is served from this same
        # origin, so a wider list would be permission nobody needs — and
        # ``allow_credentials`` plus a wildcard origin is rejected by browsers anyway,
        # which makes a too-generous list misleading as well as unnecessary.
        allow_origins=_CORS_ORIGINS,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    # The wildcard would be a lie: browsers reject `allow_credentials` together with
    # `*`, and an operator seeing `*` would assume the list is intentionally open.
    assert "*" not in _CORS_ORIGINS, "CORS must stay an explicit allowlist"

    @app.middleware("http")
    async def _security_headers(request: Request, call_next: Callable[[Request], Any]) -> Any:
        """Browser-side backstop for the one v-html sink and for cookie theft.

        CSP does not replace output escaping — it limits what an escaping mistake can
        do. ``connect-src 'self'`` also stops a injected script from quietly shipping
        the page's data to another host.
        """
        response = await call_next(request)
        response.headers.setdefault(
            "Content-Security-Policy",
            "default-src 'self'; script-src 'self'; style-src 'self' 'unsafe-inline'; "
            "img-src 'self' data:; connect-src 'self' ws: wss:; "
            "object-src 'none'; base-uri 'self'; frame-ancestors 'none'",
        )
        response.headers.setdefault("X-Content-Type-Options", "nosniff")
        response.headers.setdefault("Referrer-Policy", "no-referrer")
        return response

    @app.middleware("http")
    async def _limit_body_size(request: Request, call_next: Callable[[Request], Any]) -> Any:
        """Refuse an oversized request body before it is parsed.

        Starlette reads the whole body into memory for a JSON endpoint, so a 500 MB POST
        was 500 MB of RSS before any validator ran. The per-route checks that exist
        (``plugins`` upload) are the exception, not the rule: every other endpoint trusted
        ``Content-Length`` to be reasonable.

        ``Content-Length`` is checked first because it is free. It is also a claim, not a
        fact — a chunked request has none — so the header check is a fast rejection, not
        the boundary. The boundary is the streamed read below, which counts actual bytes
        and aborts mid-body rather than after buffering it.
        """
        limit = MAX_REQUEST_BODY_BYTES
        declared = request.headers.get("content-length")
        if declared is not None:
            try:
                if int(declared) > limit:
                    return JSONResponse(
                        {"detail": f"request body exceeds {limit} bytes"},
                        status_code=413,
                    )
            except ValueError:
                # A malformed Content-Length is the server's problem to reject, not to
                # guess at; let the ASGI layer decide. The fixed message (never the
                # header value) keeps a bad header from forging a log line.
                logger.debug("ignoring a malformed Content-Length header")

        # Every method that can carry a body is guarded, not just POST/PUT/PATCH. A
        # DELETE with a body is legal HTTP, and leaving it unguarded made the one method
        # with no cap the one nobody thinks to test.
        if request.method in ("POST", "PUT", "PATCH", "DELETE"):
            received = 0
            chunks: list[bytes] = []
            async for chunk in request.stream():
                received += len(chunk)
                if received > limit:
                    return JSONResponse(
                        {"detail": f"request body exceeds {limit} bytes"},
                        status_code=413,
                    )
                chunks.append(chunk)
            body = b"".join(chunks)

            # Two separate caches, because Starlette has two separate readers and filling
            # only one is a silent data-loss bug:
            #
            # * ``request.body()`` reads ``_body``.
            # * ``request.stream()`` reads ``_stream``, falling back to the ASGI
            #   ``receive`` channel — which we just drained to empty.
            #
            # Setting only ``_body`` meant a handler written against ``stream()`` (an
            # upload, a proxy) saw zero chunks and processed an empty request. Nothing
            # raised; the handler simply received nothing.
            # Both are private Starlette attributes, which is the point: they are the
            # documented cache slots ``body()`` and ``stream()`` read from, and there is
            # no public API to refill them after a middleware has consumed the channel.
            request._body = body

            async def _replay() -> AsyncIterator[bytes]:
                if body:
                    yield body

            request._stream = _replay()

        return await call_next(request)

    # Registered last so it is the outermost user middleware. Body-size rejection
    # returns 413 without calling call_next; if this ran inside that middleware,
    # the 413 response would have no request id and its log line no context.
    @app.middleware("http")
    async def _request_context(request: Request, call_next: Callable[[Request], Any]) -> Any:
        """Bind locating fields for every log line produced by this request."""
        request_id = request.headers.get("X-Request-ID", "") or secrets.token_hex(8)
        tokens = log_context.bind(
            request_id=request_id,
            trace_id=request.headers.get("X-Trace-ID", "") or request_id,
            message_id=request.headers.get("X-Message-ID", ""),
        )
        try:
            response = await call_next(request)
            response.headers.setdefault("X-Request-ID", request_id)
            return response
        finally:
            log_context.reset(tokens)

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

        # A writable directory is a proxy for "SQLite can write", which is not the same
        # thing: a database file that exists but cannot be opened — corrupt, wrong owner
        # after a volume restore, a half-applied migration — passes the directory probe
        # and then fails on the first real query. One cheap SELECT catches that.
        #
        # `current_database()` never creates the connection, so a probe cannot become
        # the thing that initialises the schema it is supposed to observe.
        from soapbot.memory.db import current_database

        database = current_database()
        if database is not None:
            try:
                from sqlalchemy import text

                async with database.session() as session:
                    await session.execute(text("SELECT 1"))
            except Exception as exc:  # a probe reports, it never raises
                # Type only: /readyz is unauthenticated and the message can carry a
                # filesystem path or SQL fragment.
                problems.append(f"database not usable ({type(exc).__name__})")

        errors = get_startup_errors()
        if errors:
            # Startup errors stay warnings by policy: an offline adapter or a plugin
            # that failed to load must not mark the whole console unusable, or a broken
            # plugin would pull it out of service exactly when someone needs to fix it.
            # `degraded` is the machine-readable middle ground — monitoring can alert on
            # it without readiness failing.
            logger.debug("readiness note: %d startup errors", len(errors))

        payload = {
            "status": "ok" if not problems else "unavailable",
            "version": __version__,
            "data_dir": str(data_dir),
            "problems": problems,
            "startup_errors": errors,
            "degraded": bool(errors),
        }
        return JSONResponse(payload, status_code=200 if not problems else 503)

    @app.get("/metrics", tags=["system"], include_in_schema=False)
    async def metrics(_: dict = Depends(require_api_auth)) -> Response:
        """Prometheus text exposition of the counters this process already keeps.

        Hand-written rather than via ``prometheus-client``. Every value here is a
        snapshot read at scrape time from the provider router and the trace store —
        they are not counter objects updated on a request hot path — so the library
        would add a dependency and a registry lifecycle in order to restate numbers
        that already exist.

        Labels are configured provider ids only, so cardinality is bounded by the
        operator's own configuration and never by request content. It requires the same
        API token as the rest of the panel: provider names, model errors and traffic
        counts are internal topology, not public build metadata.
        """
        lines: list[str] = []

        def emit(
            name: str, kind: str, help_text: str, samples: list[tuple[str, float]]
        ) -> None:
            lines.append(f"# HELP {name} {help_text}")
            lines.append(f"# TYPE {name} {kind}")
            for labels, value in samples:
                suffix = f"{{{labels}}}" if labels else ""
                lines.append(f"{name}{suffix} {value}")

        started = _STARTED_AT.get("ts", time.time())
        emit(
            "soapbot_info",
            "gauge",
            "Build information; the value is always 1.",
            [(f'version="{_prometheus_label(__version__)}"', 1)],
        )
        emit(
            "soapbot_uptime_seconds",
            "gauge",
            "Seconds since this process started.",
            [("", round(time.time() - started, 3))],
        )

        runtime = get_runtime()
        providers = getattr(runtime, "providers", None) if runtime is not None else None
        if providers is None:
            for name, kind, help_text, _key in _PROVIDER_METRICS:
                emit(name, kind, help_text, [])
        else:
            stats = providers.stats()
            for name, kind, help_text, key in _PROVIDER_METRICS:
                samples: list[tuple[str, float]] = []
                for pid, values in stats.items():
                    value = values.get(key, 0)
                    samples.append(
                        (
                            f'provider="{_prometheus_label(pid)}"',
                            int(value) if isinstance(value, bool) else value,
                        )
                    )
                emit(name, kind, help_text, samples)

            breaker = providers.breaker_status()
            emit(
                "soapbot_breaker_open",
                "gauge",
                "1 while the router refuses to try any provider.",
                [("", 1 if breaker.get("open") else 0)],
            )
            emit(
                "soapbot_breaker_retry_after_seconds",
                "gauge",
                "Seconds until the breaker allows another attempt.",
                [("", breaker.get("retry_after", 0))],
            )

        return Response(
            "\n".join(lines) + "\n",
            media_type="text/plain; version=0.0.4; charset=utf-8",
        )

    from soapbot.api.personas import router as personas_growth_router
    from soapbot.api.system import router as system_router

    app.include_router(auth_router)
    app.include_router(security_router)
    app.include_router(admin_router)
    # After the admin router: both serve /api/personas, and the growth routes add a
    # sub-path rather than replacing anything.
    app.include_router(personas_growth_router)
    app.include_router(system_router)
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


class _CompressExceptEvents(GZipMiddleware):
    """Compress responses, except the one response that must never wait for a buffer.

    Measured before adding this: the panel's entry chunk is 241 KB of text and the first
    load pulls ~273 KB, none of it compressed. Event streams are excluded by their
    ``Accept`` header because SSE frames are already small and the whole point of the
    channel is that a frame reaches the client immediately; putting them through a
    compressor trades latency for bytes on the one response that cannot afford it.
    """

    async def __call__(self, scope: dict, receive, send) -> None:
        if scope.get("type") == "http":
            accept = ""
            for name, value in scope.get("headers") or []:
                if name == b"accept":
                    accept = value.decode("latin-1", "replace")
                    break
            if "text/event-stream" in accept:
                await self.app(scope, receive, send)
                return
        await super().__call__(scope, receive, send)


class _ImmutableAssets(StaticFiles):
    """Serve hashed assets with a long-lived cache, which is what the hash is for.

    ``StaticFiles`` sends only ``ETag``/``Last-Modified``, so every page view revalidated
    all ~24 assets — cheap individually, but one round trip each. The filename contains
    a content hash, which is exactly the condition under which ``immutable`` is safe.
    ``index.html`` deliberately keeps ``no-store`` (see ``_mount_webui``): caching the
    shell is how a rebuild keeps showing the previous bundle.
    """

    async def get_response(self, path: str, scope: Any) -> Response:
        response = await super().get_response(path, scope)
        if response.status_code == 200:
            response.headers["Cache-Control"] = "public, max-age=31536000, immutable"
        return response


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
            app.mount("/assets", _ImmutableAssets(directory=assets), name="webui-assets")

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
