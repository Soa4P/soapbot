#!/usr/bin/env python3
"""Answer one question on a deployment host: *what is this host actually running?*

The failure this exists for is not a crash, it is a stale success. The panel answers
200, the operator sees an old page, and every layer has a plausible excuse: the checkout
was never pulled, the service was never restarted, the committed `dist/` was never
rebuilt, or the browser cached `index.html`. Those four look identical from outside and
need different fixes, so this prints each layer separately instead of a single "ok".

Runs on Windows and Linux with the standard library only: a deployment host may have
never installed this project's dependencies, let alone npm. It never writes anything and
never needs credentials.

    python scripts/verify_deployment.py                  # human-readable report
    python scripts/verify_deployment.py --json          # for pasting into an issue
    python scripts/verify_deployment.py --repo /opt/soapbot --health http://127.0.0.1:6185/api/health

Exit codes: 0 = all layers agree and the service is healthy; 1 = a mismatch was found;
2 = the check itself could not run (no git, no dist, no reachable service).
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import subprocess
import sys
import urllib.error
import urllib.request
from pathlib import Path

DEFAULT_HEALTH = "http://127.0.0.1:6185/api/health"
DEFAULT_READY = "http://127.0.0.1:6185/readyz"
DIST = Path("src/soapbot/webui/dist")
_ASSET_RE = re.compile(r'(?:src|href)="(/assets/[^"]+)"')


def _force_utf8_streams() -> None:
    """Chinese output must survive a cp1252 console (measured on the Windows runner)."""
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            stream.reconfigure(encoding="utf-8", errors="replace")


def _out(text: str = "") -> None:
    print(text, flush=True)


def _run(argv: list[str], cwd: Path, timeout: float = 15.0):
    try:
        return subprocess.run(
            argv,
            cwd=cwd,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=timeout,
            check=False,
        )
    except (FileNotFoundError, subprocess.TimeoutExpired, OSError):
        return None


def _sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def check_repo(repo: Path) -> dict:
    """Which commit is on disk, and does it match what is committed?"""
    head = _run(["git", "rev-parse", "HEAD"], repo)
    if head is None or head.returncode != 0:
        return {"available": False, "reason": "git 不可用或不是 git 仓库"}
    branch = _run(["git", "rev-parse", "--abbrev-ref", "HEAD"], repo)
    dirty = _run(["git", "status", "--porcelain", "--untracked-files=no"], repo)
    return {
        "available": True,
        "head": (head.stdout or "").strip(),
        "branch": (branch.stdout or "").strip() if branch else "",
        "dirty_files": len([x for x in (dirty.stdout or "").splitlines() if x.strip()]) if dirty else -1,
    }


def _committed_bytes(repo: Path, rel: Path) -> bytes | None:
    """Raw blob bytes, not `git show`.

    `git show` goes through text conversion, and on a Windows host with autocrlf the
    same committed file can come back with different line endings than the working
    tree — a hash "mismatch" that means nothing. `cat-file blob` returns the exact
    bytes git stored, which is what we actually want to compare.
    """
    try:
        result = subprocess.run(
            ["git", "cat-file", "blob", f"HEAD:{rel.as_posix()}"],
            cwd=repo,
            capture_output=True,
            timeout=15.0,
            check=False,
        )
    except (FileNotFoundError, subprocess.TimeoutExpired, OSError):
        return None
    if result.returncode != 0:
        return None
    return result.stdout


def check_dist(repo: Path) -> dict:
    """Compare the committed panel with the panel actually on disk.

    The wheel/UI is shipped from `src/soapbot/webui/dist`, which is committed to the
    repository. A source edit that forgets to rebuild leaves HEAD pointing at a commit
    whose index.html still names old asset hashes — CI cannot see that because the
    package job rebuilds the panel before checking it. Comparing HEAD's index.html with
    the working tree's index.html is the missing gate, and this is its host-side twin.
    """
    root = repo / DIST
    index = root / "index.html"
    if not index.is_file():
        return {"available": False, "reason": f"找不到 {index}"}

    on_disk = index.read_bytes()
    committed = _committed_bytes(repo, DIST / "index.html")
    referenced = _ASSET_RE.findall(on_disk.decode("utf-8", "replace"))
    missing_assets = [
        name for name in referenced if not (root / name.lstrip("/")).is_file()
    ]

    return {
        "available": True,
        "index_sha256": _sha256(on_disk)[:16],
        "committed_index_sha256": _sha256(committed)[:16] if committed is not None else None,
        "matches_committed": committed is not None and _sha256(committed) == _sha256(on_disk),
        "referenced_assets": referenced,
        "missing_assets": missing_assets,
        "asset_count": len(list((root / "assets").glob("*"))) if (root / "assets").is_dir() else 0,
    }


def _http(url: str) -> dict:
    try:
        with urllib.request.urlopen(url, timeout=3) as response:
            raw = response.read()
            try:
                body = json.loads(raw or b"{}")
            except (ValueError, TypeError):
                body = {}
            return {"reachable": True, "status": response.status, "body": body}
    except urllib.error.HTTPError as exc:
        return {"reachable": True, "status": exc.code, "body": {}}
    except (urllib.error.URLError, OSError, ValueError):
        return {"reachable": False, "status": 0, "body": {}}


def check_service(health: str, ready: str) -> dict:
    probe = _http(health)
    ready_probe = _http(ready)
    body = probe.get("body") or {}
    return {
        "health": probe,
        "ready": ready_probe,
        "version": body.get("version", ""),
        "uptime_seconds": float(body.get("uptime_seconds") or 0),
        "ready_status": ready_probe.get("status", 0),
    }


def check_process() -> dict:
    """Best-effort service identity; never fatal if the platform differs."""
    if os.name == "nt":
        result = _run(
            ["schtasks", "/Query", "/TN", "SoapbotBot", "/FO", "LIST", "/V"],
            Path.cwd(),
        )
        if result is None or result.returncode != 0:
            return {"available": False, "reason": "计划任务 SoapbotBot 不存在或查询失败"}
        text = result.stdout or ""
        pid = re.search(r"PID:\s*(\d+)", text)
        return {
            "available": True,
            "supervisor": "schtasks:SoapbotBot",
            "pid": int(pid.group(1)) if pid else 0,
        }
    result = _run(["systemctl", "show", "soapbot", "--property=MainPID", "--value"], Path.cwd())
    if result is None or result.returncode != 0:
        return {"available": False, "reason": "systemctl 不可用或 unit 不存在"}
    try:
        return {"available": True, "supervisor": "systemd:soapbot", "pid": int((result.stdout or "").strip())}
    except ValueError:
        return {"available": True, "supervisor": "systemd:soapbot", "pid": 0}


def diagnose(report: dict) -> list[str]:
    """Turn the layers into the four concrete stale-page causes, in likely order."""
    problems: list[str] = []
    repo = report["repo"]
    dist = report["dist"]
    svc = report["service"]

    if repo.get("available") and not repo.get("head"):
        problems.append("git HEAD 读不到，先确认部署目录是不是仓库")
    if dist.get("available") and dist.get("committed_index_sha256") is None:
        problems.append("HEAD 里没有提交 dist/index.html —— 这个 checkout 从没带过前端产物")
    elif dist.get("available") and not dist.get("matches_committed"):
        problems.append(
            "磁盘上的 dist/index.html 与 HEAD 提交的不一致：要么产物没提交，要么本地被重建过。"
            "无 npm 的部署会拿到旧面板。"
        )
    if dist.get("available") and dist.get("missing_assets"):
        problems.append(
            f"index.html 引用了缺失的 asset：{dist['missing_assets']}；浏览器会白屏或部分功能失效"
        )
    if not svc["health"].get("reachable"):
        problems.append(f"{DEFAULT_HEALTH} 不可达：服务未启动、端口不对，或重启后没回来")
    elif svc["health"].get("status") != 200:
        problems.append(f"/api/health 返回 {svc['health'].get('status')}，不是 200")
    if svc["ready_status"] not in (0, 200):
        problems.append(f"/readyz 返回 {svc['ready_status']}：进程在但依赖未就绪")
    return problems


def _print_text(report: dict) -> None:
    repo, dist, svc, proc = report["repo"], report["dist"], report["service"], report["process"]
    _out("== 部署自检 ==")
    if repo.get("available"):
        _out(f"git HEAD      : {repo.get('head', '?')[:12]}  branch={repo.get('branch', '?')}  dirty={repo.get('dirty_files')}")
    else:
        _out(f"git           : 无法检查（{repo.get('reason')}）")
    if dist.get("available"):
        _out(f"dist index    : 磁盘 {dist.get('index_sha256')}  HEAD {dist.get('committed_index_sha256')}  一致={dist.get('matches_committed')}")
        _out(f"assets        : 引用 {len(dist.get('referenced_assets', []))} 个，磁盘 {dist.get('asset_count')} 个，缺失 {len(dist.get('missing_assets', []))} 个")
    else:
        _out(f"dist          : 无法检查（{dist.get('reason')}）")
    _out(f"health        : reachable={svc['health'].get('reachable')} status={svc['health'].get('status')} version={svc.get('version') or '?'} uptime={svc.get('uptime_seconds', 0):.1f}s")
    _out(f"readyz        : status={svc['ready_status']}")
    if proc.get("available"):
        _out(f"supervisor    : {proc.get('supervisor')} pid={proc.get('pid')}")
    else:
        _out(f"supervisor    : 无法检查（{proc.get('reason')}）")
    problems = report["problems"]
    _out("")
    if problems:
        _out(f"发现 {len(problems)} 项需要核对：")
        for index, item in enumerate(problems, 1):
            _out(f"  {index}. {item}")
    else:
        _out("[PASS] 各层一致，服务健康。")
    _out("")
    _out("若面板仍显示旧内容：uptime 很大 = 代码更新后没重启服务；uptime 很小但仍旧 = 浏览器缓存 index.html（Ctrl+F5 强刷）。")
    _out(f"当前 uptime = {svc.get('uptime_seconds', 0):.1f}s，可据此区分。")


def main() -> int:
    _force_utf8_streams()
    parser = argparse.ArgumentParser(
        description="核对部署主机上「代码 / 前端产物 / 运行进程」是否同一版本",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )
    parser.add_argument("--repo", default=".", help="仓库根目录")
    parser.add_argument("--health", default=DEFAULT_HEALTH, help="liveness URL")
    parser.add_argument("--ready", default=DEFAULT_READY, help="readiness URL")
    parser.add_argument("--json", action="store_true", help="输出 JSON，便于贴回排查")
    args = parser.parse_args()

    repo = Path(args.repo).resolve()
    if not repo.is_dir():
        _out(f"[FAIL] 仓库目录不存在：{repo}")
        return 2

    report = {
        "repo": check_repo(repo),
        "dist": check_dist(repo),
        "service": check_service(args.health, args.ready),
        "process": check_process(),
    }
    report["problems"] = diagnose(report)

    if args.json:
        _out(json.dumps(report, ensure_ascii=False, indent=2))
    else:
        _print_text(report)

    if not report["dist"].get("available") or not report["service"]["health"].get("reachable"):
        return 2
    return 1 if report["problems"] else 0


if __name__ == "__main__":
    sys.exit(main())
