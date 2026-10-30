"""Seeding the runtime config directory from the shipped template.

The panel writes configuration, so that directory is on the writable volume. What the
image ships is a template, copied once. These tests pin the two properties that make
that safe: an existing file is never overwritten, and a missing template is not an error
(a deployment may mount nothing at all and configure everything by hand).
"""

from __future__ import annotations

from pathlib import Path

from soapbot.core.config_seed import seed_config_dir


def test_copies_missing_files(tmp_path: Path) -> None:
    template = tmp_path / "template"
    template.mkdir()
    (template / "providers.yaml").write_text("providers: []\n", encoding="utf-8")
    (template / "adapters.yaml").write_text("adapters: []\n", encoding="utf-8")
    target = tmp_path / "runtime"

    copied = seed_config_dir(target, template)

    assert sorted(copied) == ["adapters.yaml", "providers.yaml"]
    assert (target / "providers.yaml").read_text(encoding="utf-8") == "providers: []\n"


def test_never_overwrites_an_edited_file(tmp_path: Path) -> None:
    """The whole point of seeding: the operator's edit outlives a container rebuild."""
    template = tmp_path / "template"
    template.mkdir()
    (template / "providers.yaml").write_text("providers: []\n", encoding="utf-8")
    target = tmp_path / "runtime"
    target.mkdir()
    (target / "providers.yaml").write_text("providers: [mine]\n", encoding="utf-8")

    copied = seed_config_dir(target, template)

    assert copied == []
    assert "mine" in (target / "providers.yaml").read_text(encoding="utf-8")


def test_missing_template_is_not_an_error(tmp_path: Path) -> None:
    assert seed_config_dir(tmp_path / "runtime", tmp_path / "nope") == []
    assert (tmp_path / "runtime").is_dir()
