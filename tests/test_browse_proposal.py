"""Public-page browsing: compliance, capability, and the quota pre-check.

The failure modes worth pinning are not parsing details. They are: an empty allow-list
that accidentally means "anywhere", a robots.txt denial that gets ignored, a fetch
that consumes the HTTP capability instead of BROWSE, and a proposal that is created
before anyone checked whether it could ever be approved.
"""

from __future__ import annotations

from types import SimpleNamespace

import pytest

from soapbot.browse.proposal import propose_purchase
from soapbot.browse.reader import (
    _ROBOTS,
    USER_AGENT,
    BrowsePolicy,
    PageSnapshot,
    ReadError,
    parse_page,
    read_public_page,
)
from soapbot.budget.events import APPROVAL_BUS, REQUESTED, ApprovalEvent
from soapbot.budget.policy import BudgetPolicy
from soapbot.budget.store import BudgetStore
from soapbot.memory.db import Database
from soapbot.plugins.manifest import SENSITIVE_CAPABILITIES, Capability
from soapbot.plugins.sandbox import CapabilityDeniedError, CapabilityGrant, CapabilityGuard
from soapbot.plugins.supervisor import ALLOWED_SURFACES, arg_violation
from soapbot.security.audit import AuditLog

SCOPE = "onebot11:group:100"
URL = "https://shop.example.com/item/1"
PAGE_HTML = (
    b"<html><head><title>Blue Cup 300ml</title>"
    b'<meta name="description" content="A blue cup">'
    b"</head><body><p>Price &#165;25.50 today</p>"
    b'<script>document.write("PRICE 999999")</script>'
    b'<img src="/cup.png"></body></html>'
)


@pytest.fixture(autouse=True)
def _clear_state():
    _ROBOTS._entries.clear()
    APPROVAL_BUS.clear()
    yield
    _ROBOTS._entries.clear()
    APPROVAL_BUS.clear()


def _policy(**kw) -> BrowsePolicy:
    return BrowsePolicy(allowed_hosts=frozenset({"shop.example.com"}), **kw)


def _guard(*caps: Capability):
    entries: list[dict] = []

    class _Audit:
        def record(self, **kwargs):
            entries.append(kwargs)

    grant = CapabilityGrant(
        plugin="p", declared=frozenset(caps), approved=frozenset(caps)
    )
    return CapabilityGuard(grant, audit=_Audit()), entries


def _fetcher(*, robots: bytes = b"User-agent: *\nAllow: /\n", status: int = 200, body=PAGE_HTML):
    calls: list[str] = []

    async def fetch(url: str, headers: dict, timeout: float):
        calls.append(url)
        if url.endswith("/robots.txt"):
            return 200, robots
        return status, body

    return fetch, calls


# ------------------------------------------------------------------ parsing

def test_parse_page_extracts_title_price_and_image_without_running_scripts() -> None:
    page = parse_page(URL, PAGE_HTML, status=200)
    assert page.title == "Blue Cup 300ml"
    assert page.description == "A blue cup"
    assert page.price_minor == 2550
    assert page.images == ("https://shop.example.com/cup.png",)
    assert "999999" not in page.text
    assert page.static_only is True


def test_parse_page_bounds_the_text() -> None:
    page = parse_page(URL, b"<html><body>" + b"word " * 5000 + b"</body></html>", status=200)
    assert len(page.text) <= 4000


def test_snapshot_to_dict_is_a_whitelist() -> None:
    page = parse_page(URL, PAGE_HTML, status=200)
    assert "raw_html" not in page.to_dict()
    assert set(page.to_dict()) == {
        "url", "host", "status", "title", "description", "text",
        "price_minor", "currency", "images", "bytes_read", "static_only",
    }


# ------------------------------------------------------------------ compliance

async def test_an_empty_allow_list_refuses_every_destination() -> None:
    fetch, _ = _fetcher()
    with pytest.raises(ValueError):
        await read_public_page(URL, policy=BrowsePolicy(allowed_hosts=frozenset()), fetcher=fetch)


async def test_a_host_outside_the_allow_list_is_refused() -> None:
    fetch, _ = _fetcher()
    with pytest.raises(ValueError):
        await read_public_page(
            "https://elsewhere.example.com/item", policy=_policy(), fetcher=fetch
        )


async def test_robots_disallow_refuses_the_fetch() -> None:
    fetch, calls = _fetcher(robots=b"User-agent: *\nDisallow: /\n")
    with pytest.raises(ReadError, match=r"robots\.txt disallows"):
        await read_public_page(URL, policy=_policy(), fetcher=fetch)
    assert calls == ["https://shop.example.com/robots.txt"]


async def test_a_missing_robots_file_allows_the_fetch() -> None:
    async def fetch(url, headers, timeout):
        if url.endswith("/robots.txt"):
            return 404, b""
        return 200, PAGE_HTML

    page = await read_public_page(URL, policy=_policy(), fetcher=fetch)
    assert page.price_minor == 2550


async def test_a_5xx_robots_file_fails_closed() -> None:
    async def fetch(url, headers, timeout):
        if url.endswith("/robots.txt"):
            return 503, b""
        return 200, PAGE_HTML

    with pytest.raises(ReadError, match=r"robots\.txt disallows"):
        await read_public_page(URL, policy=_policy(), fetcher=fetch)


async def test_a_robots_network_error_refuses() -> None:
    async def fetch(url, headers, timeout):
        if url.endswith("/robots.txt"):
            raise OSError("network down")
        return 200, PAGE_HTML

    with pytest.raises(ReadError, match="could not be read"):
        await read_public_page(URL, policy=_policy(), fetcher=fetch)


async def test_non_200_and_oversize_are_refused() -> None:
    fetch, _ = _fetcher(status=403)
    with pytest.raises(ReadError, match="HTTP 403"):
        await read_public_page(URL, policy=_policy(), fetcher=fetch)
    big, _ = _fetcher(body=b"x" * 1024)
    with pytest.raises(ReadError, match="byte cap"):
        await read_public_page(URL, policy=_policy(max_bytes=100), fetcher=big)


async def test_no_vetted_client_is_a_hard_error() -> None:
    with pytest.raises(ReadError, match="no vetted HTTP client"):
        await read_public_page(URL, policy=_policy())


async def test_robots_is_fetched_with_our_identifiable_user_agent() -> None:
    seen: list[dict] = []

    async def fetch(url, headers, timeout):
        seen.append(dict(headers))
        if url.endswith("/robots.txt"):
            return 404, b""
        return 200, PAGE_HTML

    await read_public_page(URL, policy=_policy(), fetcher=fetch)
    assert seen and all(h.get("User-Agent") == USER_AGENT for h in seen)
    assert all("Cookie" not in h for h in seen)


# ------------------------------------------------------------------ capability

def test_browse_is_a_separate_sensitive_capability() -> None:
    assert Capability.BROWSE != Capability.HTTP
    assert Capability.BROWSE in SENSITIVE_CAPABILITIES


def test_both_surfaces_are_allowlisted_and_routed() -> None:
    from soapbot.plugins.surfaces import _SURFACE_TABLE

    for name in ("browse.read", "browse.propose"):
        assert name in ALLOWED_SURFACES
        assert name in _SURFACE_TABLE


def test_the_wire_still_rejects_scope_keys() -> None:
    assert "session_key" in arg_violation("browse.read", {"url": URL, "session_key": SCOPE})
    assert arg_violation("browse.read", {"url": URL}) == frozenset()


async def test_a_plain_http_plugin_cannot_browse() -> None:
    from soapbot.plugins.surfaces import SurfaceRouter

    guard, _ = _guard(Capability.HTTP)
    router = SurfaceRouter(guard=guard, plugin="p")
    with pytest.raises(CapabilityDeniedError):
        await router.dispatch("browse.read", {"url": URL}, SimpleNamespace(session_key=SCOPE))


async def test_browse_client_consumes_browse_not_http(monkeypatch) -> None:
    from soapbot.plugins import sandbox

    async def fake_resolve(host):
        return ["93.184.216.34"]

    monkeypatch.setattr(sandbox, "resolve_and_verify", fake_resolve)
    seen: list[Capability] = []

    class _Guard:
        def check(self, capability, detail=""):
            seen.append(capability)

    class _Resp:
        def __init__(self) -> None:
            self.status_code = 200
            self.content = b"ok"
            self.headers: dict = {}

    class _Client:
        async def request(self, method, url, **kwargs):
            return _Resp()

        async def aclose(self):
            return None

    client = sandbox.SafeHttpClient(
        _Guard(),  # type: ignore[arg-type]
        allowed_hosts=frozenset({"shop.example.com"}),
        capability=Capability.BROWSE,
    )
    client._client_factory = lambda timeout: _Client()  # type: ignore[assignment]
    status, body = await client.fetch(URL, method="GET")
    assert (status, body) == (200, b"ok")
    assert seen == [Capability.BROWSE]


# ------------------------------------------------------------------ proposals

@pytest.fixture
async def store(tmp_path):
    database = Database(f"sqlite+aiosqlite:///{tmp_path / 'proposal.db'}")
    await database.init()
    yield BudgetStore(
        database,
        BudgetPolicy(period_cap_minor=10_000, per_request_cap_minor=5_000),
        audit=AuditLog(),
    )
    await database.close()


def _page(price: int | None = 2550) -> PageSnapshot:
    return PageSnapshot(
        url=URL,
        host="shop.example.com",
        status=200,
        title="Blue Cup 300ml",
        description="A blue cup",
        text="Price 25.50",
        price_minor=price,
        currency="CNY",
        images=(),
        bytes_read=120,
    )


async def test_a_proposal_creates_one_request_and_one_event(store) -> None:
    seen: list[ApprovalEvent] = []

    async def capture(event):
        seen.append(event)

    APPROVAL_BUS.subscribe(capture)
    result = await propose_purchase(
        store, _page(), session_key=SCOPE, requester_id="plugin:p"
    )
    assert result.created is True
    assert result.request_id is not None
    assert len(seen) == 1
    assert seen[0].kind == REQUESTED
    assert seen[0].amount_minor == 2550
    assert "shop.example.com" in seen[0].purpose


async def test_no_price_means_no_request_and_no_event(store) -> None:
    seen: list[ApprovalEvent] = []

    async def capture(event):
        seen.append(event)

    APPROVAL_BUS.subscribe(capture)
    result = await propose_purchase(
        store, _page(None), session_key=SCOPE, requester_id="plugin:p"
    )
    assert result.created is False
    assert result.reason == "no_price_on_page"
    assert seen == []


async def test_over_the_per_request_cap_is_refused_before_reserving(store) -> None:
    result = await propose_purchase(
        store, _page(6000), session_key=SCOPE, requester_id="plugin:p"
    )
    assert result.reason == "over_per_request_cap"
    assert result.created is False
    assert (await store.snapshot(session_key=SCOPE)).reserved_minor == 0


async def test_over_the_period_cap_is_refused(store) -> None:
    # Two earlier reservations leave ¥4.00 of the ¥100.00 period, so a ¥10.00
    # proposal is within the per-request cap but cannot be approved this period.
    await store.create(
        session_key=SCOPE, requester_id="u1", amount_minor=4800, purpose="earlier-1"
    )
    await store.create(
        session_key=SCOPE, requester_id="u1", amount_minor=4800, purpose="earlier-2"
    )
    result = await propose_purchase(
        store, _page(1000), session_key=SCOPE, requester_id="plugin:p"
    )
    assert result.reason == "over_period_cap"
    assert result.created is False
