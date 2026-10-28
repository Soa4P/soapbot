"""Wave 0 smoke tests: the app boots and the health endpoint answers."""

from __future__ import annotations

import pytest
from httpx import ASGITransport, AsyncClient

from soapbot.app import create_app


@pytest.fixture
async def client():
    app = create_app()
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac


async def test_health_returns_ok(client: AsyncClient) -> None:
    resp = await client.get("/api/health")
    assert resp.status_code == 200
    body = resp.json()
    assert body["status"] == "ok"
    assert "version" in body
    assert isinstance(body["uptime_seconds"], int | float)


async def test_unknown_route_is_404(client: AsyncClient) -> None:
    resp = await client.get("/api/definitely-not-a-route")
    assert resp.status_code == 404
