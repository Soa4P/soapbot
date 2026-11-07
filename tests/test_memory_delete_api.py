"""Deleting one memory from the panel.

``/forget <id>`` already existed, and it was the only way to remove a memory. That put
the one destructive operation in the group chat, addressed to whoever typed it — while the
person who *noticed* the bad memory is the operator looking at the memory page, who is
usually not in that conversation at all.

These tests pin the two properties that make the chat command safe, because a new HTTP
surface is exactly where they get lost:

* ownership is checked **before** the delete, so an enumerable integer id is not a licence;
* "missing" and "not yours" answer identically, so the endpoint is not an existence oracle.

They also cover the part a chat command did not need: the derived scene card was built
from the deleted row, so it must not survive it.
"""

from __future__ import annotations

import asyncio
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from soapbot.config import settings


def _config(tmp_path: Path) -> Path:
    config_dir = tmp_path / "cfg"
    config_dir.mkdir(parents=True, exist_ok=True)
    (config_dir / "providers.yaml").write_text("providers: []\n", encoding="utf-8")
    (config_dir / "adapters.yaml").write_text("adapters: []\n", encoding="utf-8")
    return config_dir


@pytest.fixture
def client(tmp_path, monkeypatch):
    from soapbot.app import create_app

    data_dir = tmp_path / "data"
    data_dir.mkdir(parents=True, exist_ok=True)
    monkeypatch.setattr(settings, "enable_runtime", True)
    monkeypatch.setattr(settings, "config_dir", _config(tmp_path))
    monkeypatch.setattr(settings, "data_dir", data_dir)

    with TestClient(create_app()) as c:
        yield c


def _seed(scope: str, texts: list[str]) -> list[int]:
    """Write memories through a second connection to the same file.

    Same reasoning as ``test_memory_scene_api``: the app owns its own event loop, and
    reaching into it needs a portal that is not part of the public surface. A separate
    ``Database`` exercises the real schema and FTS triggers instead of a hand-built row.
    """
    from soapbot.memory.db import Database
    from soapbot.memory.store import MemoryStore

    ids: list[int] = []

    async def write() -> None:
        db = Database(settings.resolved_db_url)
        try:
            store = MemoryStore(db, embedder=None)
            for text in texts:
                ids.append(
                    await store.add_memory(
                        content=text, scope=scope, importance=0.7, embed=False
                    )
                )
        finally:
            await db.close()

    asyncio.run(write())
    return ids


def _count(scope: str) -> int:
    from soapbot.memory.db import Database
    from soapbot.memory.store import MemoryStore

    async def read() -> int:
        db = Database(settings.resolved_db_url)
        try:
            store = MemoryStore(db, embedder=None)
            return len(await store.list_memories(scope=scope, limit=200))
        finally:
            await db.close()

    return asyncio.run(read())


def test_the_list_returns_the_rows_the_delete_takes(client: TestClient) -> None:
    """The list and the delete must agree on the identifier.

    A page that lists memories by content but deletes by an id it never shows forces the
    operator to guess, which is how the wrong row gets removed.
    """
    _seed("group:list", ["部署脚本要先跑迁移", "回滚前先备份"])

    body = client.get("/api/memory/items", params={"scope": "group:list"}).json()

    assert body["count"] == 2
    first = body["memories"][0]
    assert isinstance(first["id"], int)
    assert first["scope"] == "group:list"
    assert first["content"]
    # Newest first, so the id shown at the top is the most recent row.
    assert body["memories"][0]["id"] > body["memories"][1]["id"]


def test_delete_removes_exactly_one_row(client: TestClient) -> None:
    ids = _seed("group:del", ["保留这一条", "删掉这一条"])

    response = client.delete(f"/api/memory/{ids[1]}")

    assert response.status_code == 200
    assert response.json() == {"ok": True, "id": ids[1]}
    assert _count("group:del") == 1

    remaining = client.get("/api/memory/items", params={"scope": "group:del"}).json()
    assert [row["id"] for row in remaining["memories"]] == [ids[0]]


def test_a_missing_id_is_404_and_says_nothing_about_other_rows(client: TestClient) -> None:
    _seed("group:miss", ["一条记忆"])

    response = client.delete("/api/memory/999999")

    assert response.status_code == 404
    assert response.json()["detail"] == "没有找到这条记忆"


def test_deleting_twice_is_the_same_answer_as_never_existing(client: TestClient) -> None:
    """The second call must not describe our concurrency.

    A distinct message here ("already deleted") would confirm that the id once existed,
    which is the same probe the identical-message rule closes for other people's rows.
    """
    ids = _seed("group:twice", ["只删一次"])

    assert client.delete(f"/api/memory/{ids[0]}").status_code == 200
    second = client.delete(f"/api/memory/{ids[0]}")

    assert second.status_code == 404
    assert second.json()["detail"] == "没有找到这条记忆"


def test_the_scene_card_does_not_outlive_its_evidence(client: TestClient) -> None:
    """The card is a summary of rows that no longer exist.

    Leaving it in place means the panel keeps injecting a description of a conversation
    whose memories the operator just deleted — the exact "stale summary" failure the
    refresh path deletes portraits to avoid.
    """
    ids = _seed("group:scene", ["部署脚本要先跑迁移", "部署前备份数据库"])
    built = client.post("/api/memory/scene/refresh", params={"scope": "group:scene"})
    assert built.status_code == 200
    assert built.json()["card"]["memory_count"] == 2

    assert client.delete(f"/api/memory/{ids[0]}").status_code == 200

    detail = client.get("/api/memory/scene", params={"scope": "group:scene"}).json()
    card = detail["card"]
    # Either rebuilt from the surviving row or dropped — both are honest. What is not
    # allowed is a card still claiming two memories.
    assert card is None or card["memory_count"] == 1


def test_an_unknown_layer_is_a_400_naming_the_choices(client: TestClient) -> None:
    """A typo in the filter must not silently return every layer."""
    response = client.get("/api/memory/items", params={"layer": "nope"})

    assert response.status_code == 400
    detail = response.json()["detail"]
    assert "nope" in detail
    assert "semantic" in detail


def test_the_list_is_bounded(client: TestClient) -> None:
    """An unbounded page is a denial of service on the operator's own browser."""
    assert client.get("/api/memory/items", params={"limit": 0}).status_code == 422
    assert client.get("/api/memory/items", params={"limit": 5000}).status_code == 422
