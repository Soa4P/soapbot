"""The deployment self-check must be safe to hand to an operator on any host.

It runs before the project's dependencies may exist, prints Chinese on a cp1252
console, and — most importantly — must never claim "all good" when the committed
panel and the panel on disk disagree. That last case is the one CI cannot see.
"""

from __future__ import annotations

import ast
import importlib.util
import json
import os
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "verify_deployment.py"


def _invoke(*args: str, io_encoding: str | None = None) -> subprocess.CompletedProcess[str]:
    env = dict(os.environ)
    if io_encoding:
        env["PYTHONIOENCODING"] = io_encoding
    return subprocess.run(
        [sys.executable, str(SCRIPT), *args],
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        timeout=30,
        cwd=ROOT,
        env=env,
    )


def _module():
    spec = importlib.util.spec_from_file_location("verify_deployment", SCRIPT)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _healthy_report(**dist_overrides) -> dict:
    dist = {
        "available": True,
        "index_sha256": "same",
        "committed_index_sha256": "same",
        "matches_committed": True,
        "referenced_assets": ["/assets/index-a.js"],
        "missing_assets": [],
        "asset_count": 1,
    }
    dist.update(dist_overrides)
    return {
        "repo": {"available": True, "head": "abc123", "branch": "master", "dirty_files": 0},
        "dist": dist,
        "service": {
            "health": {"reachable": True, "status": 200, "body": {"version": "0.1.0"}},
            "ready": {"reachable": True, "status": 200},
            "version": "0.1.0",
            "uptime_seconds": 12.0,
            "ready_status": 200,
        },
        "process": {"available": True, "supervisor": "systemd:soapbot", "pid": 42},
    }


def test_help_survives_a_non_utf8_console() -> None:
    """Same cp1252 trap that broke verify_restart.py on the Windows runner."""
    result = _invoke("--help", io_encoding="cp1252")

    assert result.returncode == 0, result.stderr[-400:]
    assert "--json" in result.stdout
    assert "UnicodeEncodeError" not in result.stderr


def test_standard_library_only() -> None:
    """A host that never ran `pip install -e .` must still be able to run this."""
    tree = ast.parse(SCRIPT.read_text(encoding="utf-8"))
    imported: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            imported.update(alias.name.split(".")[0] for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            imported.add(node.module.split(".")[0])
    assert imported <= set(sys.stdlib_module_names) | {"__future__"}


def test_a_missing_repo_fails_closed() -> None:
    result = _invoke("--repo", "/nonexistent-soapbot-checkout")

    assert result.returncode == 2
    assert "[FAIL]" in result.stdout


def test_json_report_parseable_and_dist_matches_head() -> None:
    """The report is meant to be pasted back into an issue, so it must be real JSON."""
    result = _invoke("--json", "--repo", str(ROOT))

    report = json.loads(result.stdout)
    assert report["repo"]["available"] is True
    assert report["repo"]["head"]
    assert report["dist"]["available"] is True
    # This repository commits its built panel; a mismatch here would mean T2's gate
    # is not being honoured even locally.
    assert report["dist"]["matches_committed"] is True
    assert report["dist"]["missing_assets"] == []


def test_a_healthy_consistent_host_has_no_problems() -> None:
    """A long uptime is a hint, not a defect — otherwise every host would exit 1."""
    module = _module()

    assert module.diagnose(_healthy_report()) == []


def test_a_dist_that_does_not_match_head_is_reported() -> None:
    module = _module()

    problems = module.diagnose(_healthy_report(matches_committed=False, committed_index_sha256="other"))

    assert any("dist/index.html" in item for item in problems)


def test_missing_assets_are_reported() -> None:
    module = _module()

    problems = module.diagnose(_healthy_report(missing_assets=["/assets/index-a.js"]))

    assert any("asset" in item for item in problems)


def test_an_unreachable_service_is_reported() -> None:
    module = _module()
    report = _healthy_report()
    report["service"]["health"] = {"reachable": False, "status": 0, "body": {}}

    problems = module.diagnose(report)

    assert any("不可达" in item for item in problems)
