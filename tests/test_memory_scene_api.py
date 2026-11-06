"""The scene layer's management surface.

The layer was implemented, tested and injected into every prompt, and had **no API at
all** — the card could only be read by opening the database, and a skill could only be
produced by calling ``SkillForge`` from a REPL. ``SkillForge`` was never even constructed
by the service, so no running bot could produce a skill.

That is the failure these tests exist to prevent from coming back: a feature that is
"done" by every measure the test suite can see, and invisible from the panel that is
supposed to describe it. So they assert on the wiring, not just on the handlers:

* the runtime exposes ``scene`` and ``skills``, and they are the same objects the
  pipeline uses;
* every endpoint answers 503 rather than 500 when the runtime is absent;
* a skill written through the API is a real file, and deleting it removes that file;
* the scope is enforced on every path, including deletion, because a skill id is only
  unique within one scene.
"""

from __future__ import annotations

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
    """A running app with memory on, so the scene layer is constructed."""
    from soapbot.app import create_app

    data_dir = tmp_path / "data"
    data_dir.mkdir(parents=True, exist_ok=True)
    monkeypatch.setattr(settings, "enable_runtime", True)
    monkeypatch.setattr(settings, "config_dir", _config(tmp_path))
    monkeypatch.setattr(settings, "data_dir", data_dir)

    with TestClient(create_app()) as c:
        yield c


def _seed(client: TestClient, scope: str, texts: list[str]) -> None:
    """Write memories into the same database the app is serving.

    A second ``Database`` rather than the runtime's own store: ``TestClient`` runs the app
    on its own event loop in another thread, and reaching into that loop from here needs a
    portal that is not part of the public surface. A separate connection to the same file
    is the honest way to do it — WAL is already on, and it exercises the same code path a
    real write would (schema, FTS, migration state) instead of a hand-built fixture.
    """
    import asyncio

    from soapbot.memory.db import Database
    from soapbot.memory.store import MemoryStore

    async def write() -> None:
        db = Database(settings.resolved_db_url)
        try:
            store = MemoryStore(db, embedder=None)
            for text in texts:
                await store.add_memory(
                    content=text, scope=scope, importance=0.7, embed=False
                )
        finally:
            await db.close()

    asyncio.run(write())


def test_the_runtime_exposes_the_scene_layer_and_the_forge(client: TestClient) -> None:
    """Wiring, not behaviour: both must exist on a running app.

    ``SkillForge`` was fully implemented and never instantiated, so this assertion is the
    one that would have caught the original defect.
    """
    from soapbot.app import get_runtime

    runtime = get_runtime()
    assert runtime is not None
    assert runtime.scene is not None, "scene layer was never constructed"
    assert runtime.skills is not None, "SkillForge was never constructed"


def test_scenes_start_empty(client: TestClient) -> None:
    body = client.get("/api/memory/scenes").json()
    assert body["scenes"] == []
    assert body["count"] == 0


def test_a_scope_with_memories_is_listed_even_with_no_card(client: TestClient) -> None:
    """The interesting case: evidence exists, no summary yet.

    Listing only stored cards would hide exactly the conversations an operator can act
    on, and show an empty page on a bot that has been learning for a week.
    """
    _seed(client, "group:api", ["部署脚本要先跑迁移", "部署失败先看日志"])

    body = client.get("/api/memory/scenes").json()
    assert body["count"] == 1
    row = body["scenes"][0]
    assert row["scope"] == "group:api"
    assert row["memory_count"] == 2
    assert row["has_card"] is False
    assert row["has_portrait"] is False


def test_refresh_builds_and_persists_the_card(client: TestClient) -> None:
    _seed(client, "group:api", ["部署脚本要先跑迁移", "部署前备份数据库"])

    built = client.post("/api/memory/scene/refresh", params={"scope": "group:api"})
    assert built.status_code == 200
    card = built.json()["card"]
    assert card is not None
    assert card["memory_count"] == 2
    assert card["topics"], "a card with no topics is not a card"
    assert card["prompt"], "the injected text must be shown, not just the fields"

    # Persisted, not just returned: a second read must see it without rebuilding.
    detail = client.get("/api/memory/scene", params={"scope": "group:api"}).json()
    assert detail["card"]["memory_count"] == 2

    listed = client.get("/api/memory/scenes").json()["scenes"][0]
    assert listed["has_card"] is True


def test_refresh_withholds_a_portrait_below_the_threshold(client: TestClient) -> None:
    """Two memories is not a portrait. Saying so is the point of the field."""
    _seed(client, "group:api", ["一句话", "另一句话"])

    body = client.post("/api/memory/scene/refresh", params={"scope": "group:api"}).json()
    assert body["portrait_withheld"] is True
    assert body["portrait"] is None or body["portrait"]["confidence"] == 0.0


def test_scene_detail_for_an_unknown_scope_is_empty_not_404(client: TestClient) -> None:
    """A conversation with no card yet is the normal first visit, not an error."""
    response = client.get("/api/memory/scene", params={"scope": "group:nobody"})
    assert response.status_code == 200
    assert response.json()["card"] is None
    assert response.json()["portrait"] is None


def test_candidates_are_listed_before_anything_is_written(client: TestClient) -> None:
    _seed(
        client,
        "group:api",
        [
            "部署脚本要先跑迁移",
            "部署失败先看日志",
            "部署前备份数据库",
            "部署完成后检查健康接口",
        ],
    )

    body = client.get("/api/memory/skills/candidates", params={"scope": "group:api"}).json()
    assert body["count"] >= 1
    candidate = body["candidates"][0]
    assert candidate["support"] >= 3
    assert candidate["exists"] is False
    # Nothing on disk yet: listing must not have a side effect.
    assert client.get("/api/memory/skills", params={"scope": "group:api"}).json()["count"] == 0


def test_generating_a_skill_writes_a_real_file(client: TestClient) -> None:
    _seed(
        client,
        "group:api",
        [
            "部署脚本要先跑迁移",
            "部署失败先看日志",
            "部署前备份数据库",
            "部署完成后检查健康接口",
        ],
    )

    topic = client.get("/api/memory/skills/candidates", params={"scope": "group:api"}).json()[
        "candidates"
    ][0]["topic"]

    created = client.post("/api/memory/skills", json={"scope": "group:api", "topic": topic})
    assert created.status_code == 200
    body = created.json()
    assert body["ok"] is True

    from soapbot.app import get_runtime

    path = get_runtime().skills.root / body["file"]
    assert path.is_file(), f"skill was reported created but {path} does not exist"

    listed = client.get("/api/memory/skills", params={"scope": "group:api"}).json()
    assert listed["count"] == 1
    assert listed["skills"][0]["support"] >= 3
    assert listed["skills"][0]["body"], "a skill with an empty body teaches nothing"

    # And the candidate now reports itself as existing, so the panel offers "regenerate"
    # instead of silently overwriting a hand-edited file.
    again = client.get("/api/memory/skills/candidates", params={"scope": "group:api"}).json()
    assert again["candidates"][0]["exists"] is True


def test_a_topic_with_no_evidence_is_refused(client: TestClient) -> None:
    """The topic is re-derived, not trusted: otherwise a caller could name a topic that
    no memory supports and get an empty skill, or overwrite an existing one with nothing.
    """
    _seed(client, "group:api", ["部署脚本要先跑迁移", "部署失败先看日志"])

    response = client.post(
        "/api/memory/skills", json={"scope": "group:api", "topic": "完全不存在的主题"}
    )
    assert response.status_code == 404


def test_deleting_a_skill_removes_the_file(client: TestClient) -> None:
    _seed(
        client,
        "group:api",
        [
            "部署脚本要先跑迁移",
            "部署失败先看日志",
            "部署前备份数据库",
            "部署完成后检查健康接口",
        ],
    )
    topic = client.get("/api/memory/skills/candidates", params={"scope": "group:api"}).json()[
        "candidates"
    ][0]["topic"]
    created = client.post("/api/memory/skills", json={"scope": "group:api", "topic": topic}).json()

    from soapbot.app import get_runtime

    path = get_runtime().skills.root / created["file"]
    assert path.is_file()

    removed = client.delete(
        f"/api/memory/skills/{created['skill_id']}", params={"scope": "group:api"}
    )
    assert removed.status_code == 200
    assert not path.exists(), "the row is gone but the file is still on disk"


def test_deleting_with_the_wrong_scope_does_not_touch_another_scenes_skill(
    client: TestClient,
) -> None:
    """A skill id is only unique within a scope, so the scope must be part of the name.

    Without it, two groups that both have a skill called 部署 would be one delete away
    from each other's files.
    """
    _seed(
        client,
        "group:api",
        [
            "部署脚本要先跑迁移",
            "部署失败先看日志",
            "部署前备份数据库",
            "部署完成后检查健康接口",
        ],
    )
    topic = client.get("/api/memory/skills/candidates", params={"scope": "group:api"}).json()[
        "candidates"
    ][0]["topic"]
    created = client.post("/api/memory/skills", json={"scope": "group:api", "topic": topic}).json()

    from soapbot.app import get_runtime

    path = get_runtime().skills.root / created["file"]

    wrong = client.delete(
        f"/api/memory/skills/{created['skill_id']}", params={"scope": "group:other"}
    )
    assert wrong.status_code == 404
    assert path.is_file(), "a delete aimed at another scope removed this scene's file"


def test_skills_are_not_visible_from_another_scope(client: TestClient) -> None:
    _seed(
        client,
        "group:api",
        [
            "部署脚本要先跑迁移",
            "部署失败先看日志",
            "部署前备份数据库",
            "部署完成后检查健康接口",
        ],
    )
    topic = client.get("/api/memory/skills/candidates", params={"scope": "group:api"}).json()[
        "candidates"
    ][0]["topic"]
    client.post("/api/memory/skills", json={"scope": "group:api", "topic": topic})

    other = client.get("/api/memory/skills", params={"scope": "group:other"}).json()
    assert other["count"] == 0, "a private skill leaked into another scene"


def test_endpoints_answer_503_without_a_runtime(monkeypatch) -> None:
    """A disabled subsystem is a state, not a crash.

    The panel already treats "not initialised" as a state (see ``isUnavailable``), so the
    message has to keep that wording — a 500 here would render as a failure banner on a
    page where nothing is wrong.
    """
    from soapbot.app import create_app

    monkeypatch.setattr(settings, "enable_runtime", False)
    with TestClient(create_app()) as c:
        for path in ("/api/memory/scenes", "/api/memory/scene?scope=x", "/api/memory/skills?scope=x"):
            response = c.get(path)
            assert response.status_code == 503, path
            assert "not initialised" in response.json()["detail"]
