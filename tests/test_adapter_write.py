"""Adapter editing: merge by kind, refuse duplicates, never echo a token.

The panel can now write ``adapters.yaml``. What makes that safe is the same three-step
shape the provider editor uses, so these tests pin the parts that differ: the primary
key is ``kind`` (not a free-form id), the option bag is open, and a duplicate kind is
refused before the file is touched — because `load_adapters` would refuse it at startup,
and a save that bricks the next boot is worse than a save that fails now.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from soapbot.core import config_write
from soapbot.core.config_files import ConfigError


def _patch(path: Path, entries: list[dict], base_hash: str = ""):
    return config_write.build_patch(
        path=path,
        patch=entries,
        base_hash=base_hash,
        apply_fn=config_write.apply_adapter_patch,
        validate_fn=config_write.validate_adapters,
        filename="adapters.yaml",
    )


def test_adds_an_adapter_and_keeps_unknown_options(tmp_path: Path) -> None:
    path = tmp_path / "adapters.yaml"
    path.write_text("adapters: []\n", encoding="utf-8")

    result = _patch(
        path,
        [{"kind": "onebot", "ws_url": "ws://127.0.0.1:3000", "token": "s3cret"}],
    )

    assert result.changed_fields == ["onebot"]
    assert "onebot" in result.rendered
    assert "ws://127.0.0.1:3000" in result.rendered


def test_editing_one_field_leaves_the_others(tmp_path: Path) -> None:
    """A form that renders four fields must not blank the fifth it never showed."""
    path = tmp_path / "adapters.yaml"
    path.write_text(
        "adapters:\n  - kind: onebot\n    ws_url: ws://old\n    self_id: 10001\n",
        encoding="utf-8",
    )

    result = _patch(path, [{"kind": "onebot", "ws_url": "ws://new"}])

    assert result.changed_fields == ["onebot.ws_url"]
    assert "10001" in result.rendered
    assert "ws://new" in result.rendered


def test_a_duplicate_kind_is_refused(tmp_path: Path) -> None:
    """`validate_adapters` returns problems; `build_patch` turns them into a refusal."""
    problems = config_write.validate_adapters(
        {"adapters": [{"kind": "onebot"}, {"kind": "onebot"}]}
    )
    assert any("重复的 adapter kind" in problem for problem in problems)

    # The realistic path: the file on disk is already broken, and an edit must not be
    # the thing that finally writes it back with the duplicate still in it.
    path = tmp_path / "adapters.yaml"
    path.write_text("adapters:\n  - kind: onebot\n  - kind: onebot\n", encoding="utf-8")
    with pytest.raises(ConfigError, match="重复的 adapter kind"):
        _patch(path, [{"kind": "onebot", "ws_url": "ws://x"}])


def test_masking_hides_a_literal_token(tmp_path: Path) -> None:
    from soapbot.core.config_write import MASK, mask_document

    masked = mask_document({"adapters": [{"kind": "onebot", "token": "s3cret"}]})

    assert masked["adapters"][0]["token"] == MASK


def test_an_env_reference_is_shown_not_masked() -> None:
    """Hiding `env:NAME` would leave the operator unable to see what it points at."""
    from soapbot.core.config_write import mask_document

    masked = mask_document({"adapters": [{"kind": "onebot", "token": "env:OB_TOKEN"}]})

    assert masked["adapters"][0]["token"] == "env:OB_TOKEN"
