"""What the panel actually costs to deliver.

Measured before these headers existed: the entry chunk is 241 KB of text, the first load
pulls ~273 KB, and none of it was compressed — `StaticFiles` sends no `Cache-Control`, so
every visit also revalidated all ~24 hashed assets one round trip at a time. Both fixes
are about the delivery layer, which is why they belong in their own test file rather than
mixed into the panel's behaviour tests.
"""

from __future__ import annotations

from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from soapbot.app import app

DIST = Path(__file__).resolve().parents[1] / "src" / "soapbot" / "webui" / "dist"


@pytest.fixture
def client() -> TestClient:
    return TestClient(app)


def _entry_asset() -> str:
    assets = sorted((DIST / "assets").glob("index-*.js"))
    if not assets:
        pytest.skip("panel not built")
    return assets[0].name


def test_asset_is_served_gzipped(client: TestClient) -> None:
    """Uncompressed, this is the ~273 KB first load described above."""
    response = client.get(f"/assets/{_entry_asset()}", headers={"Accept-Encoding": "gzip"})

    assert response.status_code == 200
    assert response.headers.get("content-encoding") == "gzip"


def test_asset_is_immutably_cached(client: TestClient) -> None:
    """The filename carries a content hash; revalidating it is pure waste."""
    cache = client.get(f"/assets/{_entry_asset()}").headers.get("cache-control", "")

    assert "immutable" in cache
    assert "max-age=31536000" in cache


def test_shell_stays_uncached(client: TestClient) -> None:
    """Caching index.html is exactly how a rebuild keeps serving the old bundle."""
    response = client.get("/")

    assert response.headers.get("cache-control") == "no-store"


def test_small_responses_are_not_compressed(client: TestClient) -> None:
    """The 1 KB floor keeps framing overhead from exceeding the saving."""
    response = client.get("/api/health", headers={"Accept-Encoding": "gzip"})

    assert response.status_code == 200
    assert response.headers.get("content-encoding") is None


def test_event_streams_are_never_compressed() -> None:
    """SSE frames are small by design; buffering them would trade latency for bytes.

    Exercised at the middleware level rather than through a route, because the project
    has no event-stream endpoint today — the exclusion exists so adding one later cannot
    silently inherit a compressor that holds frames back.
    """
    from soapbot.app import _CompressExceptEvents

    seen: list[str] = []

    async def downstream(scope, receive, send) -> None:
        seen.append("downstream")

    middleware = _CompressExceptEvents(app=downstream, minimum_size=1024)
    scope = {
        "type": "http",
        "headers": [(b"accept", b"text/event-stream")],
        "method": "GET",
    }

    import asyncio

    asyncio.run(middleware(scope, None, None))

    assert seen == ["downstream"], "event stream must bypass the compressor"
