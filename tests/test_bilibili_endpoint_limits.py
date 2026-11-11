"""``/api/bilibili/impression`` must be bounded before it can spend model budget.

The endpoint runs the full watch pipeline — comments, then one model call. Without a
limit it is an unmetered proxy around the chat quota: any authenticated caller (and, in
the default loopback mode, any local reader) can drive it in a loop.

These cases call the handler directly so they never touch the network or need a runtime:
the point is *ordering* (refuse before building the client) and scope (per caller).
"""

from __future__ import annotations

from types import SimpleNamespace

import pytest
from fastapi import HTTPException

from soapbot.api import bilibili as module
from soapbot.security.ratelimit import SlidingWindowLimiter


def _request(host: str) -> SimpleNamespace:
    return SimpleNamespace(client=SimpleNamespace(host=host))


@pytest.fixture(autouse=True)
def _fresh_limiter(monkeypatch: pytest.MonkeyPatch):
    """A module-level limiter would leak hits between tests in one process."""
    monkeypatch.setattr(
        module,
        "_impression_limiter",
        SlidingWindowLimiter(limit=module.IMPRESSION_LIMIT, window_seconds=60.0),
    )


@pytest.mark.asyncio
async def test_the_fourth_call_in_a_minute_is_refused_before_the_client(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    built = {"n": 0}

    def _client():
        built["n"] += 1
        raise HTTPException(status_code=503, detail="bilibili disabled")

    monkeypatch.setattr(module, "_client", _client)
    request = _request("10.0.0.9")

    for _ in range(module.IMPRESSION_LIMIT):
        with pytest.raises(HTTPException) as allowed:
            await module.bilibili_impression(request, "BV1xx", {})
        assert allowed.value.status_code == 503, "the first calls should reach _client"

    with pytest.raises(HTTPException) as limited:
        await module.bilibili_impression(request, "BV1xx", {})
    assert limited.value.status_code == 429
    assert limited.value.headers["Retry-After"]
    assert built["n"] == module.IMPRESSION_LIMIT, "the refused call still built a client"


@pytest.mark.asyncio
async def test_the_limit_is_per_caller_not_global(monkeypatch: pytest.MonkeyPatch) -> None:
    def _client():
        raise HTTPException(status_code=503, detail="bilibili disabled")

    monkeypatch.setattr(module, "_client", _client)

    for _ in range(module.IMPRESSION_LIMIT):
        with pytest.raises(HTTPException):
            await module.bilibili_impression(_request("10.0.0.9"), "BV1xx", {})

    # A second caller has its own budget; one noisy operator must not lock out another.
    with pytest.raises(HTTPException) as other:
        await module.bilibili_impression(_request("10.0.0.10"), "BV1xx", {})
    assert other.value.status_code == 503
