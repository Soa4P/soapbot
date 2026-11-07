#!/usr/bin/env python3
"""Verify, on a real deployment host, that a restart actually comes back.

Everything else in the test suite can prove the two halves separately: the panel exits
the way its supervisor expects (``tests/test_restart_supervisor_contract.py``), and the
supervisor's config asks for a restart (the static checks in that file). Neither can
prove the middle — that *this host's* systemd/compose really does bring the service
back, with the right unit name and enough permission to do it. That needs the host.

Use this once after installing or after changing the service definition:

    sudo python scripts/verify_restart.py --yes                  # systemd
    python scripts/verify_restart.py --mode compose --yes       # docker compose
    python scripts/verify_restart.py --unit soapbot-prod --yes  # renamed unit

It deliberately sends a REAL SIGTERM / performs a REAL compose restart, so the service
is briefly unavailable. Run it in a maintenance window. Without ``--yes`` it asks first.

Exit codes: 0 = verified, 1 = the restart did not come back, 2 = cannot even attempt
it (missing tooling, wrong unit, no permission). Standard library only — this has to
run on a freshly installed host that may not have the project's dependencies yet.
"""

from __future__ import annotations

import argparse
import os
import signal
import subprocess
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path

DEFAULT_UNIT = "soapbot"
DEFAULT_SERVICE = "soapbot"
DEFAULT_HEALTH = "http://127.0.0.1:6185/api/health"
POLL_SECONDS = 1.0


def _force_utf8_streams() -> None:
    """Make Chinese output safe on a console whose locale is cp1252.

    This must run before `argparse` builds the parser: `--help` is printed directly to
    `sys.stdout` by `print_help()`, bypassing `_out()`, so reconfiguring there is too
    late. Measured on the Windows CI runner: `python verify_restart.py --help` exited
    1 with `UnicodeEncodeError: 'charmap' codec can't encode characters`, which is a
    false failure for a script whose only job is to be run by a human on a host.
    """
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            stream.reconfigure(encoding="utf-8", errors="replace")


def _out(text: str = "") -> None:
    print(text, flush=True)


def _run(argv: list[str], *, cwd: Path | None = None, timeout: float = 20.0):
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
    except (FileNotFoundError, subprocess.TimeoutExpired) as exc:
        return subprocess.CompletedProcess(argv, 127, "", str(exc))


def _available(argv: list[str]) -> bool:
    return _run(argv).returncode == 0


def _health(url: str) -> tuple[bool, float]:
    """Return (reachable, uptime_seconds). Uptime proves a *new* process answered."""
    try:
        import json

        with urllib.request.urlopen(url, timeout=2) as response:
            if response.status != 200:
                return False, 0.0
            body = json.loads(response.read() or b"{}")
            return True, float(body.get("uptime_seconds") or 0)
    except (urllib.error.URLError, OSError, ValueError):
        # Expected while the process is down or half-started.
        return False, 0.0


def _wait_health(url: str, before: float, timeout: float) -> bool:
    """A 200 alone is not enough: the old process could still be answering it."""
    deadline = time.time() + timeout
    while time.time() < deadline:
        reachable, uptime = _health(url)
        if reachable and (before <= 0 or uptime < before - 0.5):
            return True
        time.sleep(POLL_SECONDS)
    return False


def _main_pid(unit: str) -> int:
    result = _run(["systemctl", "show", unit, "--property=MainPID", "--value"])
    if result.returncode != 0:
        return -1
    try:
        return int((result.stdout or "").strip().splitlines()[0])
    except (ValueError, IndexError):
        return 0


def verify_systemd(unit: str, health: str, timeout: float) -> int:
    if not _available(["systemctl", "--version"]):
        _out("[FAIL] systemctl 不可用；这不是 systemd 部署，或脚本跑在容器里。")
        _out("       容器请用 --mode compose。")
        return 2

    before_pid = _main_pid(unit)
    if before_pid <= 0:
        _out(f"[FAIL] 找不到正在运行的 unit {unit!r}（MainPID={before_pid}）。")
        _out(f"       systemctl status {unit}")
        return 2

    active = _run(["systemctl", "is-active", unit]).stdout.strip()
    if active != "active":
        _out(f"[FAIL] {unit} 状态是 {active!r}，不是 active。")
        return 2

    reachable, before_uptime = _health(health)
    if not reachable:
        _out(f"[FAIL] 重启前 {health} 就不可达，先修好服务再验收。")
        return 2

    _out(f"unit={unit} pid={before_pid} uptime={before_uptime:.1f}s")
    _out("发送 SIGTERM（等价于面板 POST /api/system/restart 的 Linux 分支）…")

    killed = _run(["systemctl", "kill", "-s", "SIGTERM", unit])
    if killed.returncode != 0:
        try:
            os.kill(before_pid, signal.SIGTERM)
        except (ProcessLookupError, PermissionError, OSError) as exc:
            _out(f"[FAIL] 无法向 {before_pid} 发信号：{exc}")
            _out("       用 sudo 运行：sudo python scripts/verify_restart.py --yes")
            return 2

    deadline = time.time() + timeout
    new_pid = 0
    while time.time() < deadline:
        candidate = _main_pid(unit)
        if candidate > 0 and candidate != before_pid:
            new_pid = candidate
            break
        time.sleep(POLL_SECONDS)

    if not new_pid:
        _out(f"[FAIL] {timeout:.0f}s 内 systemd 没有拉起新进程。")
        _out(f"       systemctl status {unit}")
        _out("       journalctl -u " + unit + " -n 50 --no-pager")
        _out("       检查 unit 里是否有 Restart=always / RestartSec=")
        return 1

    _out(f"systemd 已拉起新进程 pid={new_pid}")
    if not _wait_health(health, before_uptime, timeout):
        _out(f"[FAIL] 新进程已存在，但 {health} 在 {timeout:.0f}s 内未恢复。")
        return 1

    _out("[PASS] systemd 在 SIGTERM 后拉起了服务，且健康接口由新进程应答。")
    _out("       面板的「保存授权名单 → 自动重启 → 生效」链路在本机成立。")
    return 0


def verify_compose(directory: Path, service: str, health: str, timeout: float) -> int:
    compose = directory / "deploy" / "docker-compose.yml"
    if not compose.is_file():
        _out(f"[FAIL] 找不到 {compose}；用 --compose-dir 指向仓库根目录。")
        return 2
    policy = compose.read_text(encoding="utf-8", errors="replace")
    if "restart: unless-stopped" not in policy:
        _out("[FAIL] compose 里没有 restart: unless-stopped，非零退出不会被拉起。")
        return 2
    if not _available(["docker", "compose", "version"]):
        _out("[FAIL] docker compose 不可用；在宿主机上运行，不是容器内部。")
        return 2

    def container_id() -> str:
        result = _run(["docker", "compose", "ps", "-q", service], cwd=directory)
        ids = [line.strip() for line in (result.stdout or "").splitlines() if line.strip()]
        return ids[0] if ids else ""

    before_id = container_id()
    if not before_id:
        _out(f"[FAIL] 没有运行中的 service {service!r}。")
        return 2

    reachable, before_uptime = _health(health)
    if not reachable:
        _out(f"[FAIL] 重启前 {health} 就不可达。")
        return 2

    _out(f"service={service} container={before_id[:12]} uptime={before_uptime:.1f}s")
    _out("执行 docker compose restart …")
    restarted = _run(["docker", "compose", "restart", service], cwd=directory, timeout=120)
    if restarted.returncode != 0:
        _out(f"[FAIL] restart 失败：{(restarted.stderr or restarted.stdout or '').strip()[-300:]}")
        return 1

    deadline = time.time() + timeout
    after_id = ""
    while time.time() < deadline:
        candidate = container_id()
        if candidate and candidate != before_id:
            after_id = candidate
            break
        time.sleep(POLL_SECONDS)

    if not after_id:
        _out("[FAIL] 重启后容器 ID 没有变化，无法确认新容器已启动。")
        return 1

    if not _wait_health(health, before_uptime, timeout):
        _out(f"[FAIL] 新容器已启动，但 {health} 在 {timeout:.0f}s 内未恢复。")
        return 1

    _out(f"[PASS] compose 重启后由新容器应答 {after_id[:12]}。")
    _out("       注：此处验证的是重启后可达性；容器内 os._exit(75) 触发的自动拉起")
    _out("       由 restart: unless-stopped 与 tests/test_restart_supervisor_contract.py 覆盖。")
    return 0


def _detect(unit: str) -> str | None:
    if _available(["systemctl", "--version"]) and _main_pid(unit) > 0:
        return "systemd"
    if _available(["docker", "compose", "version"]):
        return "compose"
    return None


def main() -> int:
    _force_utf8_streams()
    parser = argparse.ArgumentParser(
        description="在真实部署主机上验收「自动重启后服务确实回来」",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )
    parser.add_argument("--mode", choices=("auto", "systemd", "compose"), default="auto")
    parser.add_argument("--unit", default=DEFAULT_UNIT, help="systemd unit 名（不含 .service）")
    parser.add_argument("--service", default=DEFAULT_SERVICE, help="compose service 名")
    parser.add_argument("--compose-dir", default=".", help="仓库根目录（含 deploy/）")
    parser.add_argument("--health", default=DEFAULT_HEALTH, help="健康接口 URL")
    parser.add_argument("--timeout", type=float, default=60.0, help="等待恢复的秒数")
    parser.add_argument("--yes", action="store_true", help="跳过交互确认（CI / 脚本化使用）")
    args = parser.parse_args()

    mode = args.mode
    if mode == "auto":
        mode = _detect(args.unit)
        if mode is None:
            _out("[FAIL] 既找不到运行中的 systemd unit，也找不到 docker compose。")
            _out("       显式指定 --mode systemd 或 --mode compose，并确认在有权限的宿主机上运行。")
            return 2

    if not args.yes:
        _out("这会真的重启服务，期间面板短暂不可用。请在维护窗口运行。")
        try:
            answer = input(f"模式={mode}，继续？[y/N] ")
        except EOFError:
            answer = ""
        if answer.strip().lower() not in {"y", "yes"}:
            _out("已取消。")
            return 2

    if mode == "systemd":
        if os.name == "nt":
            _out("[FAIL] systemd 验收需要在 Linux 主机上运行。")
            return 2
        return verify_systemd(args.unit, args.health, args.timeout)
    return verify_compose(Path(args.compose_dir).resolve(), args.service, args.health, args.timeout)


if __name__ == "__main__":
    sys.exit(main())
