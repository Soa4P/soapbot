"""The MCP patch engine: merge rules, argv enforcement, and what the diff may show.

The security-relevant assertions are the ones about ``env``. A value that reaches the
diff reaches the operator's browser, their terminal, and any screenshot of either — so
the redaction is tested from the file on disk outward, not just at the function that
happens to do it today.

The other half is ``McpManager.reload``. Its failure mode is invisible: if it replaces
the object instead of updating it, every test still passes and the bot silently stops
seeing tools it was just told about.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from soapbot.core.config_files import ConfigError
from soapbot.core.mcp_write import (
    apply_server_patch,
    build_mcp_patch,
    public_servers,
    validate_servers,
)
from soapbot.mcp.client import McpManager, McpServer

SECRET = "ghp_live_do_not_leak_9a3f"

SAMPLE = {
    "servers": [
        {
            "name": "filesystem",
            "description": "read-only share",
            "command": ["npx", "-y", "server-filesystem", "/srv/share"],
            "env": {"GITHUB_TOKEN": SECRET},
            "timeout": 20,
            "min_role": "admin",
        }
    ]
}


# ------------------------------------------------------------------ merge rules


def test_a_new_server_must_carry_a_command() -> None:
    with pytest.raises(ConfigError, match="command"):
        apply_server_patch({"servers": []}, [{"name": "fresh"}])


def test_a_new_server_gets_only_the_fields_it_sent() -> None:
    document, changed = apply_server_patch(
        {"servers": []},
        [{"name": "fresh", "command": ["npx", "thing"]}],
    )
    assert changed == ["servers[fresh] (added)"]
    # Defaults are the parser's job, not the patch engine's: writing `min_role: member`
    # here would freeze today's default into the file and make a later default change
    # silently not apply.
    assert document["servers"][0] == {"name": "fresh", "command": ["npx", "thing"]}


def test_an_omitted_field_keeps_its_on_disk_value() -> None:
    document, changed = apply_server_patch(SAMPLE, [{"name": "filesystem", "timeout": 5}])
    entry = document["servers"][0]
    assert changed == ["servers[filesystem].timeout"]
    assert entry["command"] == SAMPLE["servers"][0]["command"]
    assert entry["env"] == {"GITHUB_TOKEN": SECRET}
    assert entry["timeout"] == 5


def test_an_explicit_null_also_keeps_the_value() -> None:
    """A form binding that rendered nothing must not blank a field nobody touched."""
    document, changed = apply_server_patch(SAMPLE, [{"name": "filesystem", "description": None}])
    assert changed == []
    assert document["servers"][0]["description"] == "read-only share"


def test_env_replaces_the_whole_mapping() -> None:
    document, changed = apply_server_patch(
        SAMPLE, [{"name": "filesystem", "env": {"NEW_TOKEN": "x"}}]
    )
    assert changed == ["servers[filesystem].env"]
    # Merge-per-key is not expressible: the panel never received the old value, so it
    # cannot say "keep that one and add this one".
    assert document["servers"][0]["env"] == {"NEW_TOKEN": "x"}


def test_delete_removes_the_entry() -> None:
    document, changed = apply_server_patch(SAMPLE, [{"name": "filesystem", "delete": True}])
    assert changed == ["servers[filesystem] (removed)"]
    assert document["servers"] == []


def test_deleting_an_absent_name_is_a_noop() -> None:
    """Idempotent on purpose: two operators pressing delete must not produce an error
    for the second one, and the diff should be empty rather than wrong."""
    document, changed = apply_server_patch(SAMPLE, [{"name": "ghost", "delete": True}])
    assert changed == []
    assert document["servers"] == SAMPLE["servers"]


def test_one_name_twice_in_a_patch_is_refused() -> None:
    with pytest.raises(ConfigError, match="出现多次"):
        apply_server_patch(
            SAMPLE,
            [{"name": "filesystem", "timeout": 5}, {"name": "filesystem", "timeout": 9}],
        )


# --------------------------------------------------------------------- argv


def test_a_command_string_is_refused() -> None:
    """The one rule that keeps a config file from being able to express a shell."""
    with pytest.raises(ConfigError, match="参数数组"):
        apply_server_patch(
            {"servers": []},
            [{"name": "bad", "command": "npx -y server /srv"}],
        )


def test_an_empty_argument_is_refused() -> None:
    with pytest.raises(ConfigError, match="空参数"):
        apply_server_patch({"servers": []}, [{"name": "bad", "command": ["npx", ""]}])


def test_validation_runs_the_boot_parser() -> None:
    """Same function the process uses at start, so "saved" and "starts" cannot diverge."""
    problems = validate_servers(
        {"servers": [{"name": "x", "command": ["npx"], "min_role": "superuser"}]}
    )
    assert problems and "min_role" in problems[0]


def test_validation_accepts_a_healthy_document() -> None:
    assert validate_servers(SAMPLE) == []


# ------------------------------------------------------------------ redaction


def test_public_servers_never_include_env_values() -> None:
    rows = public_servers(SAMPLE)
    assert rows[0]["env_keys"] == ["GITHUB_TOKEN"]
    assert SECRET not in str(rows)


def test_the_diff_redacts_both_the_old_and_the_new_value(tmp_path: Path) -> None:
    path = tmp_path / "mcp.yaml"
    path.write_text(
        "servers:\n"
        "  - name: filesystem\n"
        "    command: [npx, thing]\n"
        f"    env:\n      GITHUB_TOKEN: {SECRET}\n",
        encoding="utf-8",
    )

    from soapbot.core.config_write import file_hash

    result = build_mcp_patch(
        path=path,
        patch=[{"name": "filesystem", "env": {"GITHUB_TOKEN": "new-secret-value"}}],
        base_hash=file_hash(path),
    )

    assert "GITHUB_TOKEN" in result.diff
    assert SECRET not in result.diff, "旧值出现在 diff 里，等于把它显示在屏幕上"
    assert "new-secret-value" not in result.diff, "新值同样不该回显"

    # Two different fingerprints, not two identical `***`: a flat placeholder would make
    # a changed token render as *no change at all*, and the operator would confirm an
    # empty diff for an edit that does something.
    env_lines = [line for line in result.diff.splitlines() if "GITHUB_TOKEN" in line]
    assert len(env_lines) == 2
    shown = [line.split("GITHUB_TOKEN:", 1)[1].strip() for line in env_lines]
    assert shown[0].startswith("redacted:") and shown[1].startswith("redacted:")
    assert shown[0] != shown[1]
    # The file on disk still holds the real value until apply writes it.
    assert SECRET in path.read_text(encoding="utf-8")


def test_a_stale_hash_refuses_the_patch(tmp_path: Path) -> None:
    from soapbot.core.config_write import ConfigConflictError, file_hash

    path = tmp_path / "mcp.yaml"
    path.write_text("servers: []\n", encoding="utf-8")
    stale = file_hash(path)
    path.write_text("servers: []\n# edited elsewhere\n", encoding="utf-8")

    # The hash is semantic, so a comment-only change must NOT be a conflict.
    assert file_hash(path) == stale

    path.write_text(
        "servers:\n  - name: other\n    command: [npx, x]\n", encoding="utf-8"
    )
    with pytest.raises(ConfigConflictError):
        build_mcp_patch(
            path=path,
            patch=[{"name": "other", "timeout": 3}],
            base_hash=stale,
        )


# -------------------------------------------------------------------- reload


async def _noop() -> None:
    return None


async def test_reload_keeps_unchanged_clients_and_swaps_changed_ones() -> None:
    keep = McpServer(name="keep", command=("node", "server.js"))
    swap = McpServer(name="swap", command=("node", "old.js"))
    gone = McpServer(name="gone", command=("node", "gone.js"))
    manager = McpManager([keep, swap, gone])
    manager.ensure_tools = _noop  # type: ignore[method-assign]

    keep_client = manager._clients["keep"]
    swap_client = manager._clients["swap"]

    await manager.reload(
        [
            keep,
            McpServer(name="swap", command=("node", "new.js")),
            McpServer(name="added", command=("node", "added.js")),
        ]
    )

    # Same objects: the tool registry holds *this* manager, and every caller holds the
    # client it got. Replacing either would leave live references pointing at a manager
    # nobody updates.
    assert manager._clients["keep"] is keep_client
    assert manager._clients["swap"] is swap_client
    assert manager._clients["swap"].server.command == ("node", "new.js")
    assert "gone" not in manager._clients
    assert "gone" not in manager._servers
    assert "added" in manager._clients


async def test_reload_ignores_a_description_only_change() -> None:
    """Restarting a working child because someone reworded a label would be a self
    inflicted reconnect storm."""
    before = McpServer(name="s", command=("node", "s.js"), description="old")
    manager = McpManager([before])
    manager.ensure_tools = _noop  # type: ignore[method-assign]
    client = manager._clients["s"]

    await manager.reload(
        [McpServer(name="s", command=("node", "s.js"), description="new wording")]
    )

    assert manager._clients["s"] is client
    assert manager._servers["s"].description == "new wording"


async def test_reload_copes_with_an_empty_list() -> None:
    manager = McpManager([McpServer(name="s", command=("node", "s.js"))])
    manager.ensure_tools = _noop  # type: ignore[method-assign]

    await manager.reload([])

    assert manager._clients == {}
    assert manager.status()["servers"] == []
