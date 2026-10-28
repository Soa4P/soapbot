"""Configuration write path: the panel must never be able to break the next boot.

The tests below are ordered by how expensive the failure they prevent is:

1. **a literal credential survives a round trip** — the one bug that is silent when
   saved and fatal at next start;
2. **a candidate that would not boot is refused** — the panel may not write a file
   the startup parser rejects;
3. **a stale base is refused, not merged** — two admins editing the same file;
4. **the write is atomic and keeps its mode** — a crash mid-write must not leave a
   truncated config, and a `0600` file must stay `0600`;
5. **the audit log records names, not values**.
"""

from __future__ import annotations

import stat
import sys
from pathlib import Path

import pytest
import yaml

from soapbot.core import config_write
from soapbot.core.config_files import ConfigError, load_providers

LITERAL_KEY = "sk-live-9f2c8a71b4e6d035"
ENV_KEY = "env:DEEPSEEK_API_KEY"


@pytest.fixture(autouse=True)
def _env_key(monkeypatch, request):
    """Set the environment variable the fixture file references.

    Autouse because almost every test in this file would otherwise fail for a reason
    unrelated to what it checks: ``backup`` points at ``env:DEEPSEEK_API_KEY``, and the
    startup parser — correctly — refuses an unresolved reference. Tests that *want*
    the unresolved case delete it themselves.
    """
    if "no_env_key" in request.keywords:
        monkeypatch.delenv("DEEPSEEK_API_KEY", raising=False)
    else:
        monkeypatch.setenv("DEEPSEEK_API_KEY", "sk-from-env")
    yield


@pytest.fixture
def providers_file(tmp_path: Path) -> Path:
    path = tmp_path / "providers.yaml"
    path.write_text(
        "providers:\n"
        "  - id: primary\n"
        "    kind: openai_compat\n"
        "    label: 主线路\n"
        "    base_url: https://api.example.com/v1\n"
        f"    api_key: {LITERAL_KEY}\n"
        "    model: deepseek-chat\n"
        "    priority: 10\n"
        "  - id: backup\n"
        "    kind: openai_compat\n"
        "    base_url: https://backup.example.com/v1\n"
        f"    api_key: {ENV_KEY}\n"
        "    model: gpt-4o-mini\n"
        "    priority: 20\n",
        encoding="utf-8",
    )
    return path


# ----------------------------------------------------------------- 1. secrets


def test_literal_secret_is_masked_on_read(providers_file: Path) -> None:
    document = config_write.read_document(providers_file)
    masked = config_write.mask_document(document)
    primary = config_write.provider_index(masked)["primary"]

    assert primary["api_key"] == config_write.MASK
    assert LITERAL_KEY not in str(masked)


def test_env_reference_is_shown_verbatim(providers_file: Path) -> None:
    """A reference is not a credential, and hiding it stops the operator from
    checking which variable a provider is wired to."""
    document = config_write.read_document(providers_file)
    masked = config_write.mask_document(document)
    assert config_write.provider_index(masked)["backup"]["api_key"] == ENV_KEY


def test_unchanged_sentinel_keeps_the_literal_key(providers_file: Path) -> None:
    """The central regression: edit a label, send __UNCHANGED__, key must survive."""
    result = config_write.build_patch(
        path=providers_file,
        patch=[{"id": "primary", "label": "主线路（已改名）", "api_key": config_write.UNCHANGED}],
        base_hash="",
    )
    config_write.write_atomic(providers_file, result.rendered)

    on_disk = providers_file.read_text(encoding="utf-8")
    assert LITERAL_KEY in on_disk, "字面量密钥被覆盖了——下次启动会拿着掩码去请求"
    assert config_write.MASK not in on_disk
    assert "已改名" in on_disk


def test_echoed_mask_also_keeps_the_key(providers_file: Path) -> None:
    """A client that posts back what the GET returned must not poison the file."""
    result = config_write.build_patch(
        path=providers_file,
        patch=[{"id": "primary", "api_key": config_write.MASK}],
        base_hash="",
    )
    assert LITERAL_KEY in result.rendered
    assert config_write.MASK not in result.rendered


def test_absent_field_is_not_cleared(providers_file: Path) -> None:
    """Editing one field must not blank the others."""
    result = config_write.build_patch(
        path=providers_file,
        patch=[{"id": "primary", "priority": 5}],
        base_hash="",
    )
    primary = config_write.provider_index(result.document)["primary"]
    assert primary["base_url"] == "https://api.example.com/v1"
    assert primary["model"] == "deepseek-chat"
    assert primary["priority"] == 5


def test_explicit_empty_string_clears_the_key(providers_file: Path) -> None:
    """Removing a credential has to be possible, and must be distinguishable from
    "leave it alone" — hence the sentinel rather than empty-means-unchanged."""
    result = config_write.build_patch(
        path=providers_file,
        patch=[{"id": "primary", "api_key": ""}],
        base_hash="",
    )
    primary = config_write.provider_index(result.document)["primary"]
    assert primary["api_key"] == ""


def test_diff_never_contains_the_literal_key(providers_file: Path) -> None:
    result = config_write.build_patch(
        path=providers_file,
        patch=[{"id": "primary", "label": "新标签"}],
        base_hash="",
    )
    assert LITERAL_KEY not in result.diff
    assert config_write.MASK in result.diff


# -------------------------------------------------------------- 2. validation


@pytest.mark.no_env_key
def test_unset_env_variable_is_refused(providers_file: Path) -> None:
    with pytest.raises(ConfigError, match="DEEPSEEK_API_KEY"):
        config_write.build_patch(path=providers_file, patch=[{"id": "primary"}], base_hash="")


def test_unset_env_variable_passes_once_set(providers_file: Path) -> None:
    """Same file, same patch — the only difference is the variable being present."""
    result = config_write.build_patch(
        path=providers_file, patch=[{"id": "primary", "label": "x"}], base_hash=""
    )
    assert config_write.provider_index(result.document)["primary"]["label"] == "x"


def test_missing_kind_is_refused(tmp_path: Path) -> None:
    path = tmp_path / "p.yaml"
    path.write_text("providers:\n  - id: broken\n    kind: openai_compat\n", encoding="utf-8")
    with pytest.raises(ConfigError):
        config_write.build_patch(
            path=path, patch=[{"id": "broken", "kind": ""}], base_hash=""
        )


def test_duplicate_id_is_refused(tmp_path: Path) -> None:
    path = tmp_path / "p.yaml"
    path.write_text("providers: []\n", encoding="utf-8")
    with pytest.raises(ConfigError):
        config_write.build_patch(
            path=path,
            patch=[
                {"id": "dup", "kind": "openai_compat", "base_url": "https://a/v1"},
                {"id": "dup", "kind": "openai_compat", "base_url": "https://b/v1"},
            ],
            base_hash="",
        )


def test_malformed_yaml_is_reported_not_emptied(tmp_path: Path) -> None:
    path = tmp_path / "p.yaml"
    path.write_text("providers:\n  - id: [unclosed\n", encoding="utf-8")
    with pytest.raises(ConfigError, match="not valid YAML"):
        config_write.read_document(path)


def test_absent_file_is_an_empty_document(tmp_path: Path) -> None:
    assert config_write.read_document(tmp_path / "nope.yaml") == {}


# ---------------------------------------------------------------- 3. conflict


def test_stale_base_hash_is_refused(providers_file: Path) -> None:
    stale = config_write.file_hash(providers_file)
    providers_file.write_text(
        providers_file.read_text(encoding="utf-8").replace("主线路", "被别人改过"),
        encoding="utf-8",
    )
    with pytest.raises(config_write.ConfigConflictError):
        config_write.build_patch(
            path=providers_file,
            patch=[{"id": "primary", "label": "我的改动"}],
            base_hash=stale,
        )


def test_current_base_hash_is_accepted(providers_file: Path) -> None:
    current = config_write.file_hash(providers_file)
    result = config_write.build_patch(
        path=providers_file, patch=[{"id": "primary", "label": "新"}], base_hash=current
    )
    assert result.new_hash != result.base_hash


def test_whitespace_only_change_does_not_conflict(tmp_path: Path) -> None:
    """Reformatting the file must not invalidate an open editor."""
    path = tmp_path / "p.yaml"
    path.write_text("providers: []\n", encoding="utf-8")
    base = config_write.file_hash(path)
    path.write_text("# a new comment\nproviders: []\n\n", encoding="utf-8")
    result = config_write.build_patch(path=path, patch=[], base_hash=base)
    assert result.base_hash == result.new_hash


# ------------------------------------------------------------------ 4. atomic


@pytest.mark.skipif(
    sys.platform == "win32",
    reason="Windows 只映射只读位，无法表达 0600；该平台靠 NTFS 继承，不靠文件模式",
)
def test_write_preserves_file_mode(providers_file: Path) -> None:
    providers_file.chmod(0o600)
    before = stat.S_IMODE(providers_file.stat().st_mode)
    config_write.write_atomic(providers_file, "providers: []\n")
    after = stat.S_IMODE(providers_file.stat().st_mode)
    assert before == after == 0o600, "含密钥的文件被改成了别的权限位"


def test_write_preserves_readonly_on_windows(providers_file: Path) -> None:
    """The one bit Windows does honour must survive, or a locked file unlocks itself."""
    providers_file.chmod(0o444)
    try:
        assert not providers_file.stat().st_mode & stat.S_IWRITE
        config_write.write_atomic(providers_file, "providers: []\n")
        assert not providers_file.stat().st_mode & stat.S_IWRITE
    finally:
        providers_file.chmod(0o644)


def test_write_leaves_no_temp_files(providers_file: Path) -> None:
    config_write.write_atomic(providers_file, providers_file.read_text(encoding="utf-8"))
    leftovers = [p.name for p in providers_file.parent.iterdir() if p.name.startswith(".tmp-")]
    assert leftovers == []


def test_write_creates_missing_parent(tmp_path: Path) -> None:
    target = tmp_path / "nested" / "providers.yaml"
    config_write.write_atomic(target, "providers: []\n")
    assert target.is_file()


def test_written_file_reloads_through_the_startup_parser(providers_file: Path, monkeypatch) -> None:
    """The loop the panel creates must be readable by the code that boots the service."""
    monkeypatch.setenv("DEEPSEEK_API_KEY", "sk-from-env")
    result = config_write.build_patch(
        path=providers_file,
        patch=[{"id": "primary", "api_key": config_write.UNCHANGED, "priority": 1}],
        base_hash="",
    )
    config_write.write_atomic(providers_file, result.rendered)

    configs = load_providers(providers_file)
    by_id = {c.id: c for c in configs}
    assert by_id["primary"].api_key == LITERAL_KEY
    assert by_id["primary"].priority == 1
    assert by_id["backup"].api_key == "sk-from-env"


# ------------------------------------------------------------------ 5. shape


def test_rendered_yaml_is_stable(providers_file: Path) -> None:
    """Two renders of the same document must be byte-identical, or hashes drift."""
    document = config_write.read_document(providers_file)
    assert config_write.render(document) == config_write.render(document)


def test_unicode_is_not_escaped(providers_file: Path) -> None:
    result = config_write.build_patch(
        path=providers_file, patch=[{"id": "primary", "label": "中文标签"}], base_hash=""
    )
    assert "中文标签" in result.rendered, "中文被转义成 \\uXXXX，人工读 diff 就没法看"


def test_added_provider_is_appended(providers_file: Path) -> None:
    result = config_write.build_patch(
        path=providers_file,
        patch=[{"id": "third", "kind": "openai_compat", "base_url": "https://c/v1"}],
        base_hash="",
    )
    ids = [p["id"] for p in result.document["providers"]]
    assert ids == ["primary", "backup", "third"]
    assert any("added" in c for c in result.changed_fields)


def test_changed_fields_name_paths_not_values(providers_file: Path) -> None:
    result = config_write.build_patch(
        path=providers_file,
        patch=[{"id": "primary", "api_key": "sk-brand-new-value"}],
        base_hash="",
    )
    joined = ",".join(result.changed_fields)
    assert "providers[primary].api_key" in joined
    assert "sk-brand-new-value" not in joined
    assert LITERAL_KEY not in joined


def test_no_op_patch_reports_empty(providers_file: Path) -> None:
    document = config_write.read_document(providers_file)
    primary = document["providers"][0]
    result = config_write.build_patch(
        path=providers_file,
        patch=[{"id": "primary", "label": primary["label"]}],
        base_hash="",
    )
    assert result.empty
    assert result.new_hash == result.base_hash


def test_yaml_round_trip_keeps_all_provider_keys(providers_file: Path) -> None:
    document = config_write.read_document(providers_file)
    reparsed = yaml.safe_load(config_write.render(document))
    assert reparsed == document
