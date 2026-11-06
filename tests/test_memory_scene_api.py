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


# ------------------------------------------------------- findings from the review
#
# Each of these is a defect the cross-review found in the first version of this API. They
# are kept as tests because every one of them was invisible from the outside: the
# endpoints answered 200, the panel rendered, and the tests passed.


def test_scene_reads_require_the_config_permission(client: TestClient) -> None:
    """A card summarises a conversation; a skill body quotes it verbatim.

    The persona read already requires ``MANAGE_CONFIG``, and a scene card is strictly more
    sensitive than a persona card — it is a summary of what a group actually said. Gating
    only the mutations would leave ``/memory/scenes``, which enumerates every scope, open
    to any authenticated caller.
    """
    from soapbot.api.admin import require_api_auth

    client.app.dependency_overrides[require_api_auth] = lambda: {"role": "viewer"}
    try:
        for path in (
            "/api/memory/scenes",
            "/api/memory/scene?scope=group:api",
            "/api/memory/skills?scope=group:api",
            "/api/memory/skills/candidates?scope=group:api",
        ):
            response = client.get(path)
            assert response.status_code == 403, f"{path} was readable by a viewer"
    finally:
        client.app.dependency_overrides.pop(require_api_auth, None)


def test_an_invalid_scope_is_a_400_on_every_endpoint(client: TestClient) -> None:
    """Same input, same status.

    Before this, an unsafe scope returned an empty list from ``/skills`` (because ``load``
    swallows it), an empty list from ``/candidates``, and a 500 from ``POST /skills``. The
    empty list is the worst of the three: it reads as "this scene has no skills" rather
    than "you asked for something that cannot exist".
    """
    bad = "group:1/../../etc"
    for path in (
        f"/api/memory/skills?scope={bad}",
        f"/api/memory/skills/candidates?scope={bad}",
    ):
        response = client.get(path)
        assert response.status_code == 400, f"{path} -> {response.status_code}"

    response = client.post("/api/memory/skills", json={"scope": bad, "topic": "x"})
    assert response.status_code == 400
    response = client.delete("/api/memory/skills/x", params={"scope": bad})
    assert response.status_code == 400


def test_generation_is_idempotent_and_names_the_file_by_slug(client: TestClient) -> None:
    """Generating the same topic twice must leave one file, not two.

    The endpoint matches on the **slug** rather than the raw topic, because the slug is
    what names the file. That matters less than it looks: ``_slug`` appends a digest
    whenever the slug is not a faithful rendering of the topic, so two different topics
    almost never share a name. The property worth pinning is the one that *is* reachable —
    repeated generation is idempotent, and the id the API returns is the file name, so the
    panel's delete button addresses exactly the file it listed.
    """
    from soapbot.memory.skills import _slug

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
    candidates = client.get("/api/memory/skills/candidates", params={"scope": "group:api"}).json()[
        "candidates"
    ]
    topic = candidates[0]["topic"]

    first = client.post("/api/memory/skills", json={"scope": "group:api", "topic": topic})
    assert first.status_code == 200
    assert first.json()["skill_id"] == _slug(topic), "the id must be the file name"

    second = client.post("/api/memory/skills", json={"scope": "group:api", "topic": topic})
    assert second.status_code == 200
    assert second.json()["skill_id"] == first.json()["skill_id"]

    listed = client.get("/api/memory/skills", params={"scope": "group:api"}).json()
    assert listed["count"] == 1, "regenerating the same topic produced a second file"


def test_refresh_returns_the_same_portrait_shape_as_the_read(client: TestClient) -> None:
    """Both endpoints must describe "no portrait" the same way.

    ``refresh`` used to return an empty portrait object while ``GET /scene`` returned
    ``null`` for the same state. The panel rendered a portrait block with no content after
    a rebuild, and then made it vanish on the next read.
    """
    _seed(client, "group:api", ["一句话", "另一句话"])

    refreshed = client.post("/api/memory/scene/refresh", params={"scope": "group:api"}).json()
    read = client.get("/api/memory/scene", params={"scope": "group:api"}).json()

    assert refreshed["portrait_withheld"] is True
    assert refreshed["portrait"] is None
    assert read["portrait"] is None


def test_refresh_builds_both_views_from_one_sample(client: TestClient) -> None:
    """The card and portrait must describe the same evidence.

    They are injected together, so a card that claims a topic the portrait does not
    mention gives the model two summaries of two different moments. Both are now derived
    from a single sample inside ``refresh``.
    """
    from soapbot.memory.scene import PORTRAIT_MIN_MEMORIES

    texts = [
        "部署脚本要先跑迁移",
        "部署失败先看日志",
        "部署前备份数据库",
        "部署完成后检查健康接口",
        "部署回滚要先停服务",
        "部署前确认配置文件已更新",
        "部署窗口安排在凌晨",
        "部署后要验证核心链路",
        "部署脚本要幂等",
        "部署前通知值班同学",
        "部署日志要留档",
        "部署完成后更新变更记录",
    ]
    assert len(texts) >= PORTRAIT_MIN_MEMORIES, "seed must clear the portrait threshold"
    _seed(client, "group:api", texts)
    body = client.post("/api/memory/scene/refresh", params={"scope": "group:api"}).json()

    card = body["card"]
    portrait = body["portrait"]
    assert portrait is not None, f"{len(texts)} memories should clear the threshold"
    assert card["memory_count"] == portrait["memory_count"] == len(texts)
    # Every theme on the portrait has to be visible in the card's topics; they came from
    # the same rows, so a theme the card never saw would mean two samples.
    for theme in portrait["themes"]:
        assert theme in card["topics"], f"portrait theme {theme!r} absent from the card"


def test_the_pipeline_and_the_panel_share_one_scene_object(client: TestClient) -> None:
    """``MemoryWriteStage`` must not construct its own ``SceneMemory``.

    It was the one stage that did, so the object that *writes* the card after every turn
    was not the object the panel reads through. Harmless while ``SceneMemory`` holds only
    ``db``; a cache-coherency bug the moment it holds anything else.
    """
    from soapbot.app import get_runtime

    runtime = get_runtime()
    stages = getattr(runtime.pipeline, "stages", [])
    writers = [s for s in stages if type(s).__name__ == "MemoryWriteStage"]
    assert writers, "no MemoryWriteStage in the pipeline"
    for stage in writers:
        assert stage.scene is runtime.scene, (
            "MemoryWriteStage holds a different SceneMemory than the runtime exposes"
        )
