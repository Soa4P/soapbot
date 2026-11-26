"""Persona avatars: discovery, and the file-serving surface around it.

A Live2D model is a directory of files served over HTTP. The interesting cases are not
"does it relabel Groups correctly" but the ones where that directory becomes a way to read
something else: ``../`` in the request path, a symlink inside the model directory, an
extension the asset endpoint was never meant to hand out. Rendering is deliberately absent
(no Cubism runtime yet), so what is pinned here is everything that must stay true when a
renderer is added.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from soapbot.ai.avatar import (
    MAX_ASSET_BYTES,
    avatars_root,
    describe,
    resolve_asset,
)

SETTINGS = {
    "Version": 3,
    "FileReferences": {
        "Moc": "haru.moc3",
        "Textures": ["textures/texture_00.png"],
        "Expressions": [{"Name": "smile", "File": "expressions/smile.exp3.json"}],
        "Motions": {
            "Idle": [{"File": "motions/idle.motion3.json"}],
            "TapBody": [
                {"File": "motions/tap_a.motion3.json"},
                {"File": "motions/tap_b.motion3.json"},
            ],
        },
    },
    "Groups": [{"Target": "Parameter", "Name": "EyeBlink", "Ids": ["ParamEyeLOpen"]}],
}


def _install(root: Path, persona: str = "demo", *, settings: dict | None = None) -> Path:
    directory = avatars_root(root) / persona
    (directory / "textures").mkdir(parents=True)
    (directory / "motions").mkdir(parents=True)
    (directory / "haru.moc3").write_bytes(b"MOC3")
    (directory / "textures" / "texture_00.png").write_bytes(b"\x89PNG\r\n")
    (directory / "motions" / "idle.motion3.json").write_text("{}", encoding="utf-8")
    (directory / "demo.model3.json").write_text(
        json.dumps(settings or SETTINGS), encoding="utf-8"
    )
    return directory


def test_no_model_is_a_normal_answer(tmp_path: Path) -> None:
    """The panel asks on every persona; "not installed yet" must not be an error."""
    info = describe(tmp_path, "demo")
    assert info["available"] is False
    assert info["reason"] == "no_model"


def test_a_model_is_described_with_the_parts_a_renderer_needs(tmp_path: Path) -> None:
    _install(tmp_path)
    info = describe(tmp_path, "demo")
    assert info["available"] is True
    assert info["model"] == "haru.moc3"
    assert info["motions"]["TapBody"] == [
        "motions/tap_a.motion3.json",
        "motions/tap_b.motion3.json",
    ]
    assert info["expressions"] == ["expressions/smile.exp3.json"]
    assert info["groups"]["EyeBlink"] == ["ParamEyeLOpen"]
    # The panel shows a still texture until a renderer exists, and says so.
    assert info["preview"] == "textures/texture_00.png"
    assert info["renderer"] == "none"


def test_settings_without_a_moc_are_not_a_usable_model(tmp_path: Path) -> None:
    broken = json.loads(json.dumps(SETTINGS))
    broken["FileReferences"]["Moc"] = ""
    _install(tmp_path, settings=broken)
    info = describe(tmp_path, "demo")
    assert info["available"] is False
    assert info["reason"] == "no_moc"
    assert "Moc" in info["hint"]


def test_unreadable_settings_degrade_to_unavailable(tmp_path: Path) -> None:
    directory = _install(tmp_path)
    (directory / "demo.model3.json").write_text("{not json", encoding="utf-8")
    info = describe(tmp_path, "demo")
    assert info["available"] is False
    assert info["reason"] == "settings_unreadable"


def test_an_oversized_tree_is_refused_before_serving(tmp_path: Path, monkeypatch) -> None:
    from soapbot.ai import avatar as avatar_module

    _install(tmp_path)
    monkeypatch.setattr(avatar_module, "MAX_TOTAL_BYTES", 4)
    info = describe(tmp_path, "demo")
    assert info["available"] is False
    assert info["reason"] == "too_large"


# ------------------------------------------------------------------ asset serving
def test_a_declared_asset_resolves_with_its_type(tmp_path: Path) -> None:
    _install(tmp_path)
    found = resolve_asset(tmp_path, "demo", "textures/texture_00.png")
    assert found is not None
    path, content_type = found
    assert path.name == "texture_00.png"
    assert content_type == "image/png"


@pytest.mark.parametrize(
    "relative",
    [
        "../other/secret.png",
        "textures/../../secret.png",
        "/etc/passwd",
        "..\\..\\secret.png",
        "",
    ],
)
def test_paths_outside_the_avatar_directory_are_refused(tmp_path: Path, relative: str) -> None:
    _install(tmp_path)
    (avatars_root(tmp_path) / "secret.png").write_bytes(b"secret")
    assert resolve_asset(tmp_path, "demo", relative) is None


def test_an_extension_outside_the_allowlist_is_refused(tmp_path: Path) -> None:
    directory = _install(tmp_path)
    (directory / "config.yaml").write_text("api_key: leaked", encoding="utf-8")
    assert resolve_asset(tmp_path, "demo", "config.yaml") is None


def test_a_symlink_inside_the_model_directory_is_refused(tmp_path: Path) -> None:
    directory = _install(tmp_path)
    secret = tmp_path / "outside.png"
    secret.write_bytes(b"secret")
    link = directory / "textures" / "evil.png"
    try:
        link.symlink_to(secret)
    except OSError:  # pragma: no cover - Windows without developer mode
        pytest.skip("cannot create symlinks in this environment")
    assert resolve_asset(tmp_path, "demo", "textures/evil.png") is None


def test_a_file_over_the_asset_cap_is_refused(tmp_path: Path) -> None:
    directory = _install(tmp_path)
    big = directory / "textures" / "huge.png"
    big.write_bytes(b"\x89PNG" + b"\0" * (MAX_ASSET_BYTES + 16))
    assert resolve_asset(tmp_path, "demo", "textures/huge.png") is None


def test_the_persona_id_cannot_escape_its_directory(tmp_path: Path) -> None:
    """The id comes from the URL, so it is containment-checked like any other path."""
    _install(tmp_path, persona="demo")
    for bad in ("..", "../demo", "a/b"):
        assert resolve_asset(tmp_path, bad, "textures/texture_00.png") is None
        assert describe(tmp_path, bad)["available"] is False
