"""QQ official menu: the local document, its validator, and the API around it.

No platform call exists yet (that needs an AppID/Secret), so what is proven here is the
part that fails silently otherwise: a menu with duplicate labels, a ``javascript:`` link
in a button, markup inside a name the platform's client will render, or a half-written
config file after a crash. The upload becomes a transport change; these rules stay.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import pytest

import soapbot.api.qq_menu  # noqa: F401  dotted path: check_test_gaps counts references by it
from soapbot.adapters.qq_menu import (
    MAX_DEPTH,
    MAX_ITEMS_PER_LEVEL,
    MAX_NAME_CHARS,
    MenuError,
    MenuStore,
    parse,
    to_api_payload,
    validate,
)

GOOD = {
    "items": [
        {"name": "帮助", "type": "send", "reply": "发送 /help 查看命令"},
        {"name": "官网", "type": "link", "url": "https://example.com"},
        {
            "name": "更多",
            "type": "menu",
            "children": [{"name": "群规", "type": "send", "reply": "友善发言"}],
        },
    ]
}


# ------------------------------------------------------------------ validation
def test_a_well_formed_menu_round_trips() -> None:
    items = parse(GOOD)
    payload = to_api_payload(items)
    assert [item["name"] for item in payload["items"]] == ["帮助", "官网", "更多"]
    assert payload["items"][2]["children"][0]["reply"] == "友善发言"


def test_every_problem_is_reported_at_once() -> None:
    """One round trip per mistake is how an operator gives up on a form."""
    problems = validate(
        {
            "items": [
                {"name": "<b>粗体</b>", "type": "send"},
                {"name": "帮助", "type": "send", "reply": "ok"},
                {"name": "帮助", "type": "send", "reply": "重复"},
                {"name": "跳转", "type": "link", "url": "javascript:alert(1)"},
                {"name": "空的", "type": "menu", "children": []},
            ]
        }
    )
    joined = "\n".join(problems)
    assert "含 < 或 >" in joined
    assert "需要 reply" in joined
    assert "重复" in joined
    assert "必须是 http(s)" in joined
    assert "没有任何子项" in joined


def test_control_and_invisible_characters_are_refused() -> None:
    """A right-to-left override in a button label reorders the text the user reads."""
    problems = validate(
        {"items": [{"name": "帮助\u202e", "type": "send", "reply": "ok"}]}
    )
    assert any("控制字符" in p for p in problems)


def test_type_specific_fields_are_enforced() -> None:
    assert any("不能带 url" in p for p in validate(
        {"items": [{"name": "a", "type": "send", "reply": "x", "url": "https://x"}]}
    ))
    assert any("不能带 reply" in p for p in validate(
        {"items": [{"name": "a", "type": "link", "url": "https://x", "reply": "x"}]}
    ))
    assert any("不能同时带" in p for p in validate(
        {"items": [{"name": "a", "type": "menu", "reply": "x", "children": [
            {"name": "b", "type": "send", "reply": "y"}]}]}
    ))


def test_caps_are_enforced() -> None:
    too_many = {"items": [
        {"name": f"i{n}", "type": "send", "reply": "x"} for n in range(MAX_ITEMS_PER_LEVEL + 1)
    ]}
    assert any("最多" in p for p in validate(too_many))

    deep = {"name": "l1", "type": "menu", "children": [
        {"name": "l2", "type": "menu", "children": [
            {"name": "l3", "type": "menu", "children": [
                {"name": "l4", "type": "send", "reply": "x"}]}]}]}
    assert MAX_DEPTH == 3
    assert any("层级超过" in p for p in validate({"items": [deep]}))

    too_long = {"items": [{"name": "x" * (MAX_NAME_CHARS + 1), "type": "send", "reply": "y"}]}
    assert any("超过" in p for p in validate(too_long))


def test_an_empty_menu_is_refused() -> None:
    assert validate({"items": []}) == ["菜单至少要有一项"]


# ------------------------------------------------------------------ storage
def test_a_saved_menu_is_reloaded_and_is_private(tmp_path: Path) -> None:
    import os

    store = MenuStore(tmp_path / "qq_menu.json")
    saved = store.save(GOOD)
    assert saved["items"][0]["name"] == "帮助"
    assert json.loads((tmp_path / "qq_menu.json").read_text(encoding="utf-8"))["schema"] == 1
    if os.name == "posix":
        assert oct((tmp_path / "qq_menu.json").stat().st_mode & 0o777) == "0o600"


def test_an_invalid_menu_is_not_written(tmp_path: Path) -> None:
    store = MenuStore(tmp_path / "qq_menu.json")
    store.save(GOOD)
    before = (tmp_path / "qq_menu.json").read_text(encoding="utf-8")
    with pytest.raises(MenuError):
        store.save({"items": [{"name": "x", "type": "link", "url": "ftp://x"}]})
    assert (tmp_path / "qq_menu.json").read_text(encoding="utf-8") == before


def test_a_corrupt_file_reads_as_empty(tmp_path: Path) -> None:
    path = tmp_path / "qq_menu.json"
    path.write_text("{not json", encoding="utf-8")
    assert MenuStore(path).load() == {"items": []}


# ------------------------------------------------------------------ API
@pytest.fixture
def client(tmp_path, monkeypatch):
    from fastapi.testclient import TestClient

    from soapbot.app import create_app
    from soapbot.config import settings

    config_dir = tmp_path / "config"
    config_dir.mkdir()
    monkeypatch.setattr(settings, "config_dir", config_dir)
    monkeypatch.setattr(settings, "enable_runtime", False)
    with TestClient(create_app()) as test_client:
        token = test_client.app.state.soapbot_auth_state.token_service  # noqa: F841
        yield test_client


def test_the_menu_api_round_trips_and_rejects_problems(client) -> None:
    response = client.get("/api/config/qq-menu")
    assert response.status_code == 200
    assert response.json()["document"] == {"items": []}

    bad = client.put("/api/config/qq-menu", json={"items": [{"name": "", "type": "send"}]})
    assert bad.status_code == 422
    assert bad.json()["detail"]["problems"]

    ok = client.put("/api/config/qq-menu", json=GOOD)
    assert ok.status_code == 200, ok.text
    assert ok.json()["document"]["items"][0]["name"] == "帮助"

    assert client.get("/api/config/qq-menu").json()["document"]["items"] != []

    probe = client.post("/api/config/qq-menu/validate", json=GOOD)
    assert probe.json()["ok"] is True
