"""One outbound HTTP client for the whole process.

The problem this replaces
-------------------------
Every provider built its own ``httpx.AsyncClient`` inside the call it was about to
make::

    async with httpx.AsyncClient(timeout=self.config.timeout) as client:
        resp = await client.post(url, ...)

That is correct-looking and wrong in four ways that only show up under load:

* **No connection reuse.** A fresh client means a fresh pool, so every completion
  pays a TCP handshake and a TLS handshake — two round trips before the model has
  been asked anything. On a 40 ms link that is 80 ms of pure overhead per message,
  and on a chat bot the whole budget is a second or two.
* **No TLS session reuse.** Resuming a session needs the connection to survive, so
  closing the pool after each call also throws away the abbreviated handshake.
* **Unbounded concurrency.** Nothing caps how many sockets exist at once. A burst in
  a busy group opens one connection per in-flight reply, and the far side sees a
  spike that looks like an attack.
* **One flat timeout.** ``timeout=60`` applies 60 s to *connecting* as well as to
  reading. A dead host therefore costs 60 s to discover, when a connect timeout of a
  few seconds would have failed over to the next provider almost immediately.

What this module provides
-------------------------
A single lazily-built client, keyed by the running event loop (an ``AsyncClient``
holds loop-bound primitives, so a client created in one loop cannot be used in
another — tests create a loop per test and would otherwise see "attached to a
different loop" errors).

Timeouts are layered rather than flat: connect is short, read is the caller's
budget, pool acquisition is short. Redirects are never followed automatically; the
one place that follows them by hand, re-checking the host on every hop, is
``soapbot.security.posture._get_same_host``. There is deliberately only one such
implementation — two would drift, and the one nobody calls would drift unnoticed.

TLS verification is never disabled anywhere in this codebase. That is a property
worth stating in the one module that builds clients, and
``tests/test_outbound_http.py`` fails if anyone adds ``verify=False`` later.
"""

from __future__ import annotations

import asyncio
import contextvars
import logging
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

import httpx

from soapbot.config import settings

logger = logging.getLogger(__name__)

#: The trace id of the message being handled, if any.
#:
#: A ``ContextVar`` rather than a parameter because the value has to reach the HTTP
#: layer through four or five frames that have no business knowing about tracing
#: (stage -> engine -> router -> provider -> httpx). Threading it explicitly would
#: mean adding an argument to every signature in between, and the first caller that
#: forgot it would silently produce untraceable requests.
_trace_id: contextvars.ContextVar[str] = contextvars.ContextVar("soapbot_trace_id", default="")

#: Header name. ``X-Request-Id`` rather than a vendor-specific one: it is what every
#: reverse proxy, gateway and log aggregator already understands.
TRACE_HEADER = "X-Request-Id"


def current_trace_id() -> str:
    return _trace_id.get()


def set_trace_id(trace_id: str) -> contextvars.Token[str]:
    """Bind a trace id to the current context. Returns a token for :func:`reset_trace_id`."""
    return _trace_id.set(trace_id or "")


def reset_trace_id(token: contextvars.Token[str]) -> None:
    _trace_id.reset(token)


def trace_headers() -> dict[str, str]:
    """Headers to attach to an outbound request. Empty when no trace is bound."""
    tid = _trace_id.get()
    return {TRACE_HEADER: tid} if tid else {}


def build_timeout(read: float | None = None) -> httpx.Timeout:
    """Layered timeout: short connect, caller-controlled read, short pool wait.

    ``read`` is the per-provider budget from ``providers.yaml``. It deliberately does
    *not* apply to connecting: a provider that cannot be reached in a few seconds is
    down, and waiting the full completion budget to learn that turns one dead endpoint
    into a stalled conversation. The pool timeout is short for the same reason — if
    every socket is busy, queueing behind them for a minute is worse than failing over.
    """
    return httpx.Timeout(
        connect=settings.outbound_connect_timeout,
        read=read if read is not None else settings.outbound_read_timeout,
        write=settings.outbound_write_timeout,
        pool=settings.outbound_pool_timeout,
    )


def build_limits() -> httpx.Limits:
    return httpx.Limits(
        max_connections=settings.outbound_max_connections,
        max_keepalive_connections=settings.outbound_max_keepalive,
        keepalive_expiry=settings.outbound_keepalive_expiry,
    )


async def _inject_trace(request: httpx.Request) -> None:
    """Request hook: stamp the trace id on everything that leaves the process.

    A hook rather than a per-call header dict so that a request built deep inside
    httpx (a retry, a redirect hop we did not write) is stamped too.

    ``async`` because httpx awaits every request hook unconditionally — a plain
    function here fails at send time with "object NoneType can't be used in 'await'
    expression", which surfaces as every provider call failing.
    """
    tid = _trace_id.get()
    if tid and TRACE_HEADER not in request.headers:
        request.headers[TRACE_HEADER] = tid


class _Registry:
    """Per-event-loop clients.

    Keyed by the loop rather than a single global because ``AsyncClient`` is bound to
    the loop that created it. Production has exactly one loop, so this is a one-entry
    dict there; tests get a fresh client per test without leaking sockets between them.
    """

    def __init__(self) -> None:
        self._clients: dict[int, httpx.AsyncClient] = {}
        self._loops: dict[int, asyncio.AbstractEventLoop] = {}

    def get(self) -> httpx.AsyncClient:
        loop = asyncio.get_running_loop()
        self._reap_dead_loops(loop)
        key = id(loop)
        client = self._clients.get(key)
        if client is not None and not client.is_closed:
            return client
        client = httpx.AsyncClient(
            timeout=build_timeout(),
            limits=build_limits(),
            # Never automatic. A redirect hands control of the destination to whoever
            # controls the origin, which is exactly the SSRF shape this codebase
            # refuses elsewhere (see ``plugins/sandbox.py`` and ``bilibili/client.py``).
            follow_redirects=False,
            # Proxy environment variables would route traffic around any allow-list
            # decision made here, so they are ignored by default.
            trust_env=False,
            event_hooks={"request": [_inject_trace]},
            headers={"User-Agent": settings.outbound_user_agent},
        )
        self._clients[key] = client
        self._loops[key] = loop
        return client

    def _reap_dead_loops(self, running: asyncio.AbstractEventLoop) -> None:
        """Drop entries whose loop is gone.

        Two reasons, one loop each. The obvious one is that a client holds a pool and
        a TLS context, and keeping one per dead loop is a leak. The subtle one is
        ``id(loop)``: CPython reuses an address once the object is collected, so a
        stale entry can be handed to a *new* loop that happens to land on the same id
        — and the client it returns is bound to a loop that no longer runs, which
        fails later with "attached to a different loop" far from the cause.

        The strong reference in ``_loops`` is what keeps those loops alive in the
        first place, so dropping the entry is also what makes the id reusable. That
        is safe precisely because the entry is gone by then.
        """
        for key, loop in list(self._loops.items()):
            if loop is running or not loop.is_closed():
                continue
            client = self._clients.pop(key, None)
            self._loops.pop(key, None)
            if client is not None:
                self._discard(client, "its event loop is gone")

    def _discard(self, client: httpx.AsyncClient, reason: str) -> None:
        """Let a client go without awaiting ``aclose``.

        ``aclose`` cannot be awaited on a loop that has already stopped, and there is
        no synchronous close to fall back on: ``AsyncHTTPTransport`` and
        ``AsyncConnectionPool`` expose ``aclose`` and nothing else. An earlier version
        of this method called ``transport.close()``, which does not exist — the
        ``getattr`` guard made it a no-op, so it looked like cleanup while cleaning
        nothing up.

        Dropping the last reference is the honest option. CPython closes the
        underlying file descriptors when the transport is collected, so the sockets do
        not survive; what is lost is the orderly pool shutdown, which is unavailable
        by construction here.
        """
        logger.debug("discarding outbound client: %s", reason)

    async def aclose(self) -> None:
        clients = list(self._clients.items())
        loops = dict(self._loops)
        self._clients.clear()
        self._loops.clear()
        running = asyncio.get_running_loop()
        for key, client in clients:
            loop = loops.get(key)
            if loop is not None and loop is not running and loop.is_closed():
                # Its loop died with it; awaiting aclose here would raise "Event loop
                # is closed" from inside the transport.
                self._discard(client, "its event loop is closed")
                continue
            try:
                await client.aclose()
            except Exception as exc:  # pragma: no cover - shutdown must not raise
                logger.warning("outbound client close failed: %s", exc)


_registry = _Registry()


def get_outbound() -> httpx.AsyncClient:
    """The shared client. Do **not** close it — it is not yours."""
    return _registry.get()


async def reset_outbound() -> None:
    """Close every pooled client. For shutdown and for tests."""
    await _registry.aclose()


@asynccontextmanager
async def outbound_client(
    *, client: httpx.AsyncClient | None = None
) -> AsyncIterator[httpx.AsyncClient]:
    """Yield a client for one operation.

    With ``client`` given (tests, or a caller that already owns one) it is yielded
    as-is and left open. Otherwise the shared client is yielded and **not** closed:
    closing it on every call is the defect this module exists to remove.

    There is deliberately no ``timeout`` parameter. The shared client carries a
    layered default, and a per-call override would have to be applied to the request
    (``client.post(..., timeout=...)``), not to the client — a client-level timeout
    set here would leak into every later caller. An earlier version accepted the
    argument and never used it, which is worse than not offering it: the signature
    promised a budget that was silently ignored.
    """
    if client is not None:
        yield client
        return
    yield get_outbound()
