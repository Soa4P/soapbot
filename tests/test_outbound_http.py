"""Outbound HTTP: the properties that are easy to lose and expensive to lose.

Each test here corresponds to a defect that existed before ``soapbot.net`` was
introduced, or to a way of "simplifying" the module that would bring one back.

Modules under test: ``soapbot.net.client`` (pool, timeouts, limits, trace header,
redirect policy, TLS) and the retry policy in ``soapbot.providers.base``.
"""

from __future__ import annotations

import ast
import asyncio
import inspect
from pathlib import Path
from typing import Any

import httpx
import pytest

from soapbot.net import (
    TRACE_HEADER,
    build_limits,
    build_timeout,
    get_outbound,
    outbound_client,
    reset_outbound,
    reset_trace_id,
    set_trace_id,
    trace_headers,
)
from soapbot.net import client as net_client
from soapbot.providers.base import (
    ProviderConfig,
    ProviderError,
    is_retryable_exception,
    is_retryable_status,
    retry_async,
)


@pytest.fixture(autouse=True)
async def _clean_pool():
    yield
    await reset_outbound()


# ------------------------------------------------------------------ reuse


@pytest.mark.asyncio
async def test_the_client_is_reused_across_calls() -> None:
    """A fresh client per call pays a TCP and TLS handshake per completion.

    That was the original defect: every provider did
    ``async with httpx.AsyncClient(...)`` inside the method it was about to call.
    """
    first = get_outbound()
    second = get_outbound()
    assert first is second


@pytest.mark.asyncio
async def test_leaving_the_context_manager_does_not_close_the_client() -> None:
    """``outbound_client`` must not close what it did not open.

    The old shape was ``async with httpx.AsyncClient() as client``, which closed the
    pool at the end of every request. Keeping the ``async with`` syntax while closing
    the shared client would reproduce the same defect with extra steps.
    """
    async with outbound_client() as client:
        pass
    assert not client.is_closed
    assert get_outbound() is client


@pytest.mark.asyncio
async def test_an_injected_client_is_left_open() -> None:
    """Callers that own a client keep ownership of it."""
    owned = httpx.AsyncClient(transport=httpx.MockTransport(lambda r: httpx.Response(200)))
    async with outbound_client(client=owned) as yielded:
        assert yielded is owned
    assert not owned.is_closed
    await owned.aclose()


# ------------------------------------------------------------------ timeouts


def test_connect_timeout_is_shorter_than_the_read_budget() -> None:
    """Layering is the point: a dead host must fail fast, a slow model must not.

    With a single flat timeout, discovering that an endpoint is unreachable costs the
    entire completion budget before failover can start.
    """
    timeout = build_timeout(read=60.0)
    assert timeout.connect is not None and timeout.read is not None
    assert timeout.connect < timeout.read
    assert timeout.read == 60.0


def test_a_provider_read_budget_overrides_only_the_read_leg() -> None:
    short = build_timeout(read=3.0)
    assert short.read == 3.0
    assert short.connect == build_timeout(read=99.0).connect


def test_pool_wait_is_bounded() -> None:
    timeout = build_timeout()
    assert timeout.pool is not None and timeout.pool <= 10.0


# ------------------------------------------------------------------ limits


def test_the_pool_has_a_ceiling() -> None:
    limits = build_limits()
    assert limits.max_connections is not None
    assert limits.max_connections > 0
    assert limits.max_keepalive_connections is not None
    assert limits.max_keepalive_connections <= limits.max_connections


def test_keepalive_outlives_the_gap_between_two_messages() -> None:
    """Session reuse only happens if the connection survives until the next message."""
    limits = build_limits()
    assert limits.keepalive_expiry is not None
    assert limits.keepalive_expiry >= 10.0


# ------------------------------------------------------------------ trace


@pytest.mark.asyncio
async def test_the_trace_id_is_sent_as_a_header() -> None:
    """Every outbound request must be correlatable with the audit log entry."""
    seen: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        return httpx.Response(200, json={})

    client = httpx.AsyncClient(
        transport=httpx.MockTransport(handler),
        event_hooks={"request": [net_client._inject_trace]},
    )
    token = set_trace_id("trace-abc")
    try:
        await client.post("https://example.test/v1/chat", json={})
    finally:
        reset_trace_id(token)
        await client.aclose()

    assert seen[0].headers[TRACE_HEADER] == "trace-abc"


@pytest.mark.asyncio
async def test_no_header_is_sent_when_no_trace_is_bound() -> None:
    """An empty value would be worse than none: it looks like a real id."""
    assert trace_headers() == {}


@pytest.mark.asyncio
async def test_the_hook_does_not_overwrite_a_caller_supplied_id() -> None:
    """A caller that already decided the id knows more than the ambient context."""
    seen: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        return httpx.Response(200)

    client = httpx.AsyncClient(
        transport=httpx.MockTransport(handler),
        event_hooks={"request": [net_client._inject_trace]},
    )
    token = set_trace_id("ambient")
    try:
        await client.get("https://example.test/", headers={TRACE_HEADER: "explicit"})
    finally:
        reset_trace_id(token)
        await client.aclose()

    assert seen[0].headers[TRACE_HEADER] == "explicit"


def test_the_trace_hook_is_awaitable() -> None:
    """httpx awaits every request hook unconditionally.

    A plain function here fails at send time with "object NoneType can't be used in
    'await' expression" — which surfaces as *every* provider call failing, not as a
    tracing problem.
    """
    assert inspect.iscoroutinefunction(net_client._inject_trace)


# ------------------------------------------------------------------ retry policy


@pytest.mark.parametrize("status", [408, 429, 500, 502, 503, 504])
def test_transient_statuses_are_retried(status: int) -> None:
    assert is_retryable_status(status)


@pytest.mark.parametrize("status", [400, 401, 403, 404, 422])
def test_client_errors_are_not_retried(status: int) -> None:
    """Retrying a 400 re-sends a request the server already rejected.

    Retrying a 401 is worse: some vendors treat repeated bad credentials as an attack.
    """
    assert not is_retryable_status(status)


def test_a_provider_error_carries_its_status_into_the_policy() -> None:
    assert is_retryable_exception(ProviderError("boom", status=503))
    assert not is_retryable_exception(ProviderError("boom", status=400))
    assert not is_retryable_exception(ProviderError("no status"))


def test_configuration_errors_are_not_retried() -> None:
    """An invalid URL fails identically every time; retrying only delays failover."""
    assert not is_retryable_exception(httpx.InvalidURL("nope"))
    assert not is_retryable_exception(httpx.UnsupportedProtocol("nope"))


def test_connection_failures_are_retried() -> None:
    assert is_retryable_exception(httpx.ConnectError("refused"))
    assert is_retryable_exception(httpx.ReadTimeout("slow"))


@pytest.mark.asyncio
async def test_retry_stops_after_the_configured_attempts() -> None:
    calls = 0

    async def always_fails() -> None:
        nonlocal calls
        calls += 1
        raise httpx.ConnectError("refused")

    with pytest.raises(httpx.ConnectError):
        await retry_async(always_fails, attempts=3, what="test", base_delay=0.0)
    assert calls == 3


@pytest.mark.asyncio
async def test_a_non_retryable_error_is_raised_immediately() -> None:
    calls = 0

    async def fails_with_400() -> None:
        nonlocal calls
        calls += 1
        raise ProviderError("bad request", status=400)

    with pytest.raises(ProviderError):
        await retry_async(fails_with_400, attempts=3, what="test", base_delay=0.0)
    assert calls == 1, "a 400 must not be sent three times"


@pytest.mark.asyncio
async def test_a_successful_retry_returns_the_value() -> None:
    calls = 0

    async def fails_once() -> str:
        nonlocal calls
        calls += 1
        if calls == 1:
            raise httpx.ConnectError("refused")
        return "ok"

    assert await retry_async(fails_once, attempts=3, what="test", base_delay=0.0) == "ok"
    assert calls == 2


@pytest.mark.asyncio
async def test_cancellation_is_not_swallowed_by_the_retry_loop() -> None:
    """A cancelled handler must stop, not retry. Otherwise shutdown hangs."""

    async def cancelled() -> None:
        raise asyncio.CancelledError()

    with pytest.raises(asyncio.CancelledError):
        await retry_async(cancelled, attempts=3, what="test", base_delay=0.0)


# ------------------------------------------------------------------ redirects


@pytest.mark.asyncio
async def test_redirects_are_not_followed_by_default() -> None:
    """The shared client must not follow redirects on its own.

    A public endpoint answering ``302 -> http://169.254.169.254/`` would otherwise turn
    any request into a metadata read, and the hop count would be the server's choice.
    """
    client = get_outbound()
    assert client.follow_redirects is False


def test_there_is_exactly_one_redirect_following_implementation() -> None:
    """Two implementations of the same safety rule drift, and the dead one drifts first.

    ``net.client`` used to export ``request_following_redirects`` while production
    actually went through ``security.posture._get_same_host``. Nothing called the
    former, so nothing would have caught it diverging — including diverging into
    following a cross-host hop. The bounded, re-validated version lives in
    ``security.posture``; this test keeps it the only one.
    """
    assert not hasattr(net_client, "request_following_redirects")

    source = Path(net_client.__file__).read_text(encoding="utf-8-sig")
    tree = ast.parse(source)
    defined = {
        node.name
        for node in ast.walk(tree)
        if isinstance(node, ast.AsyncFunctionDef | ast.FunctionDef)
    }
    assert "request_following_redirects" not in defined


# ------------------------------------------------------------------ TLS


def test_no_module_disables_certificate_verification() -> None:
    """A guard against the "just make it work" fix.

    ``verify=False`` and a permissive ``ssl`` context both turn every provider call into
    an unauthenticated channel. Nothing in this codebase should ever need them, so a
    future edit that adds one fails here rather than in production.
    """
    root = Path(__file__).resolve().parents[1] / "src" / "soapbot"
    offenders: list[str] = []
    for path in root.rglob("*.py"):
        # ``utf-8-sig`` because a couple of files carry a BOM, which ``ast.parse``
        # rejects as a non-printable character.
        source = path.read_text(encoding="utf-8-sig")
        # Parsed, not grepped: the module docstring in ``net/client.py`` names the
        # pattern in order to explain why it is forbidden, and a text search cannot
        # tell that apart from a call. ``ast`` can.
        tree = ast.parse(source)
        for node in ast.walk(tree):
            if not isinstance(node, ast.Call):
                continue
            for keyword in node.keywords:
                if (
                    keyword.arg == "verify"
                    and isinstance(keyword.value, ast.Constant)
                    and keyword.value.value is False
                ):
                    offenders.append(f"{path.relative_to(root)}:{node.lineno}: verify=False")
            func = node.func
            name = getattr(func, "attr", None) or getattr(func, "id", None)
            if name in {"_create_unverified_context"}:
                offenders.append(f"{path.relative_to(root)}:{node.lineno}: {name}()")
    assert not offenders, "TLS verification must never be disabled: " + ", ".join(offenders)


def test_no_module_switches_the_tls_context_to_cert_none() -> None:
    """``ssl.CERT_NONE`` is the other way to disable verification."""
    root = Path(__file__).resolve().parents[1] / "src" / "soapbot"
    offenders: list[str] = []
    for path in root.rglob("*.py"):
        tree = ast.parse(path.read_text(encoding="utf-8-sig"))
        for node in ast.walk(tree):
            if isinstance(node, ast.Attribute) and node.attr == "CERT_NONE":
                offenders.append(f"{path.relative_to(root)}:{node.lineno}")
    assert not offenders, "CERT_NONE turns every provider call into a plaintext channel: " + ", ".join(
        offenders
    )


@pytest.mark.asyncio
async def test_the_client_ignores_proxy_environment_variables() -> None:
    """A proxy from the environment would route around any allow-list decision."""
    client = get_outbound()
    assert client.trust_env is False


# ------------------------------------------------------------------ provider wiring


@pytest.mark.asyncio
async def test_a_provider_does_not_build_its_own_client(monkeypatch: pytest.MonkeyPatch) -> None:
    """The regression this module exists to prevent.

    If a provider goes back to ``httpx.AsyncClient(...)`` per call, the shared pool is
    bypassed and connection reuse silently stops. Counting instantiations catches that
    without asserting on internals.
    """
    from soapbot.providers.openai_compat import OpenAICompatProvider

    built: list[Any] = []
    real = httpx.AsyncClient

    def counting(*args: Any, **kwargs: Any) -> httpx.AsyncClient:
        built.append(args)
        return real(*args, **kwargs)

    monkeypatch.setattr(httpx, "AsyncClient", counting)

    provider = OpenAICompatProvider(
        ProviderConfig(
            id="p",
            kind="openai_compat",
            base_url="https://example.test/v1",
            api_key="k",
            model="m",
        )
    )

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200, json={"choices": [{"message": {"content": "hi"}, "finish_reason": "stop"}]}
        )

    async def fake_request(method: str, url: str, **kwargs: Any) -> httpx.Response:
        return handler(httpx.Request(method, url))

    monkeypatch.setattr(provider, "_request", fake_request)
    await provider.chat.__wrapped__(provider, _chat_request()) if hasattr(
        provider.chat, "__wrapped__"
    ) else await provider.chat(_chat_request())

    assert built == [], "the provider must draw from the shared pool, not build a client"


def _chat_request() -> Any:
    from soapbot.providers.base import ChatMessage, ChatRequest

    return ChatRequest(messages=[ChatMessage(role="user", content="hi")])


# ------------------------------------------------- registry lifecycle


def test_the_registry_does_not_accumulate_dead_loops() -> None:
    """A client per event loop is right; keeping the dead ones is not.

    ``asyncio.run`` is called in tests, in scripts and by anything embedding the bot,
    and each call creates a loop. The registry used to key on ``id(loop)`` and never
    remove an entry, so every such call left a client and — worse — a strong reference
    to the loop, which is what stopped the id from ever being reused. Measured before
    the fix: five loops, five clients, zero closed.
    """
    for _ in range(5):
        asyncio.run(_touch_registry())

    assert len(net_client._registry._clients) == 1, "dead loops were not reaped"
    assert len(net_client._registry._loops) == 1


async def _touch_registry() -> None:
    get_outbound()


def test_a_reaped_entry_does_not_hand_a_dead_loop_client_to_a_new_one() -> None:
    """The consequence of the leak, stated as its own property.

    Once the stale entry is gone, a new loop that happens to reuse the old ``id``
    builds a fresh client instead of inheriting one bound to a loop that no longer
    runs. Inheriting it would fail later with "attached to a different loop", far from
    the cause.
    """
    async def grab() -> tuple[int, bool]:
        client = get_outbound()
        return id(asyncio.get_running_loop()), client.is_closed

    first = asyncio.run(grab())
    second = asyncio.run(grab())

    assert first[1] is False and second[1] is False
    assert len(net_client._registry._clients) == 1


def test_closing_a_dead_loop_client_does_not_pretend_to_close_it() -> None:
    """The old ``_close_sync`` called ``transport.close()``, which does not exist.

    ``AsyncHTTPTransport`` and ``AsyncConnectionPool`` expose ``aclose`` and nothing
    else, so the ``getattr`` guard made the whole method a no-op while its docstring
    claimed the transport was closed directly. The replacement says what it does.
    """
    assert not hasattr(net_client._Registry, "_close_sync")
    assert hasattr(net_client._Registry, "_discard")

    transport = httpx.AsyncClient()._transport
    assert not hasattr(transport, "close"), (
        "if a synchronous close ever appears, _discard can be upgraded to use it"
    )


def test_outbound_client_does_not_advertise_a_timeout_it_ignores() -> None:
    """A parameter that is accepted and dropped is worse than a missing one.

    The signature promised a per-call budget; the body never read it, so a caller who
    passed one got the shared default and no indication otherwise.
    """
    signature = inspect.signature(outbound_client)
    assert "timeout" not in signature.parameters
    assert "client" in signature.parameters, "the injection seam is still needed"


# ------------------------------------------------- retry-after


def test_provider_error_carries_the_servers_retry_hint() -> None:
    """The hint has to survive the translation into ``ProviderError``.

    Providers turn every failure into ``ProviderError``, which has no ``response``
    attribute — so the retry policy's old ``getattr(exc, "response", None)`` lookup
    returned ``None`` every time. A 429 saying "come back in 20 s" was retried after
    0.5 s, spending the budget on a request guaranteed to fail again.
    """
    from soapbot.providers.base import _retry_after_seconds

    assert _retry_after_seconds(ProviderError("x", status=429, retry_after=20.0)) == 20.0
    assert _retry_after_seconds(ProviderError("x", status=429)) is None


def test_retry_after_is_read_from_a_response_when_one_is_present() -> None:
    """``httpx.HTTPStatusError`` still carries the response; both paths must work."""
    from soapbot.providers.base import _retry_after_seconds, retry_after_of

    response = httpx.Response(429, headers={"retry-after": "7"})
    assert retry_after_of(response) == 7.0

    error = httpx.HTTPStatusError(
        "429", request=httpx.Request("GET", "https://example.test"), response=response
    )
    assert _retry_after_seconds(error) == 7.0


def test_an_unparseable_retry_after_falls_back_to_backoff() -> None:
    """The HTTP-date form is legal but rare; guessing from it risks a skewed clock."""
    from soapbot.providers.base import retry_after_of

    dated = httpx.Response(429, headers={"retry-after": "Wed, 21 Oct 2015 07:28:00 GMT"})
    assert retry_after_of(dated) is None
    assert retry_after_of(httpx.Response(429)) is None


@pytest.mark.asyncio
async def test_a_rate_limited_provider_waits_the_hint_out(monkeypatch: pytest.MonkeyPatch) -> None:
    """End to end: the delay actually used comes from the header, not from jitter."""
    slept: list[float] = []

    async def fake_sleep(delay: float) -> None:
        slept.append(delay)

    monkeypatch.setattr(asyncio, "sleep", fake_sleep)

    calls = {"n": 0}

    async def operation() -> str:
        calls["n"] += 1
        if calls["n"] == 1:
            raise ProviderError("429", status=429, retry_after=20.0)
        return "ok"

    assert await retry_async(operation, attempts=2, what="chat") == "ok"
    # Clamped by max_delay, but unmistakably the hint rather than a jittered 0.5 s.
    assert slept == [8.0]


# ------------------------------------------------- stream timeout


@pytest.mark.asyncio
async def test_streaming_uses_the_providers_own_budget() -> None:
    """``stream`` was the one outbound call that forgot its timeout.

    It fell back to the process-wide read timeout, so a provider configured for 20 s
    kept a dead stream open for 60. Streaming is the chat hot path, which makes this
    the most expensive place to get it wrong.
    """
    from soapbot.providers.openai_compat import OpenAICompatProvider

    seen: dict[str, Any] = {}

    provider = OpenAICompatProvider(
        ProviderConfig(
            id="p",
            kind="openai_compat",
            base_url="https://example.test/v1",
            api_key="k",
            model="m",
            timeout=20.0,
        )
    )

    class FakeStream:
        def __init__(self, **kwargs: Any) -> None:
            seen.update(kwargs)

        async def __aenter__(self) -> httpx.Response:
            return httpx.Response(
                200,
                content=b'data: {"choices":[{"delta":{"content":"hi"}}]}\n\ndata: [DONE]\n\n',
                headers={"content-type": "text/event-stream"},
            )

        async def __aexit__(self, *exc: Any) -> None:
            return None

    class FakeClient:
        def stream(self, method: str, url: str, **kwargs: Any) -> FakeStream:
            return FakeStream(method=method, url=url, **kwargs)

    from contextlib import asynccontextmanager

    @asynccontextmanager
    async def fake_outbound_client(**kwargs: Any) -> Any:
        yield FakeClient()

    import soapbot.providers.openai_compat as module

    original = module.outbound_client
    module.outbound_client = fake_outbound_client
    try:
        chunks = [chunk async for chunk in provider.stream(_chat_request())]
    finally:
        module.outbound_client = original

    assert chunks == ["hi"]
    timeout = seen.get("timeout")
    assert timeout is not None, "the stream request carried no timeout at all"
    assert timeout.read == 20.0, "the provider's own read budget was not applied"
