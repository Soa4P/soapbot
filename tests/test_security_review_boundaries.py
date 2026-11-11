import base64
from unittest.mock import patch

import pytest
from fastapi import HTTPException
from starlette.requests import Request

from soapbot.ai.engine import _load_image_bytes
from soapbot.api.admin import _require_archive_auth, _require_permission
from soapbot.core.message import MessageSegment, SegmentType
from soapbot.plugins.isolation import IsolationError
from soapbot.plugins.supervisor import PluginWorker
from soapbot.security.principal import Permission, Role


@pytest.fixture
def client(monkeypatch):
    from fastapi.testclient import TestClient

    from soapbot.app import create_app
    from soapbot.config import settings

    monkeypatch.setattr(settings, "enable_runtime", False)
    with TestClient(create_app()) as test_client:
        yield test_client


def request():
    return Request({"type": "http", "method": "GET", "path": "/", "headers": [], "client": ("127.0.0.1", 1234)})


@pytest.mark.parametrize("mode", ["loopback", "local", "loopback_bootstrap"])
def test_archive_rejects_implicit_trust(mode):
    with pytest.raises(HTTPException) as exc:
        _require_archive_auth({"mode": mode, "role": "member"}, request())
    assert exc.value.status_code == 401


def test_archive_accepts_credential():
    _require_archive_auth({"mode": "token", "role": "admin"}, request())


@pytest.mark.parametrize("role", ["guest", "member"])
def test_archive_rejects_insufficient_role(role):
    with pytest.raises(HTTPException) as exc:
        _require_archive_auth({"mode": "token", "role": role}, request())
    assert exc.value.status_code == 403


@pytest.mark.parametrize("role", ["member", "admin", "owner"])
def test_api_knowledge_permission_matrix(client, role):
    from soapbot.api.auth import _state_for

    service = _state_for(client.app).token_service
    assert service is not None, "lifespan must install a token service"
    token, _ = service.issue(role=role)
    headers = {"Authorization": f"Bearer {token}"}
    responses = [
        client.get("/api/knowledge", headers=headers),
        client.get("/api/knowledge/private", headers=headers),
        client.post(
            "/api/knowledge",
            headers=headers,
            json={"doc_id": "private", "title": "test", "content": "test"},
        ),
        client.delete("/api/knowledge/private", headers=headers),
    ]
    if role == "member":
        assert [response.status_code for response in responses] == [403] * 4
    else:
        assert all(response.status_code not in {401, 403, 405} for response in responses)


@pytest.mark.parametrize("role", [Role.GUEST, Role.MEMBER])
def test_knowledge_mutations_require_admin(role):
    with pytest.raises(HTTPException) as exc:
        _require_permission({"role": role.value}, request(), Permission.MANAGE_KNOWLEDGE, "test")
    assert exc.value.status_code == 403


def test_admin_can_manage_knowledge():
    assert _require_permission({"role": "admin"}, request(), Permission.MANAGE_KNOWLEDGE, "test") == Role.ADMIN


def test_visual_protocol_path_is_never_read(tmp_path):
    file = tmp_path / "private.png"
    file.write_bytes(b"private contents")
    with patch("pathlib.Path.read_bytes", side_effect=AssertionError("must not read")):
        assert _load_image_bytes(MessageSegment(SegmentType.IMAGE, {"path": str(file)})) is None


def test_inline_image_limits():
    assert _load_image_bytes(MessageSegment(SegmentType.IMAGE, {"base64": base64.b64encode(b"image").decode()})) == b"image"
    assert _load_image_bytes(MessageSegment(SegmentType.IMAGE, {"base64": "invalid!!"})) is None
    assert _load_image_bytes(MessageSegment(SegmentType.IMAGE, {"base64": "A" * (14 * 1024 * 1024)})) is None


@pytest.mark.asyncio
async def test_system_cannot_start_plugin(tmp_path):
    async def surface_handler(*args, **kwargs):
        raise AssertionError("worker must not execute")

    worker = PluginWorker(tmp_path, surface_handler=surface_handler)
    with (
        patch("soapbot.plugins.supervisor._running_as_windows_system", return_value=True),
        pytest.raises(IsolationError, match="SYSTEM"),
    ):
        await worker.start()
    assert not worker.alive
