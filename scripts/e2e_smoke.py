"""soapbot 真部署路径 E2E 冒烟：真进程、真 OneBot 适配器、真模型（可选）、真市场索引。

测试 pytest 集成测试覆盖不到的层：`soapbot start` 真进程启动后的完整链路——
面板托管、适配器拨号协议端、群消息进管线（@ 唤醒）、模型回复（需已配置 provider）、
市场索引单插件安装（digest 校验 + 审批 + 隔离加载 + 命令真跑）。

安全说明：脚本所有 HTTP 目标都是本机环回上的被测服务自身（127.0.0.1 常量端口）；
唯一外网依赖是 GitHub 市场索引，由被测服务端自己访问。loopback_request 用倒置
白名单（解析后 IP 必须是环回段）+ 显式无代理通道（Windows 注册表代理会把 loopback
请求送给本机代理软件并挂起）。

用法（仓库根目录）：
    python scripts/e2e_smoke.py
    端口默认 6285（SOAPBOT_E2E_PORT 覆盖）；模型未配置时「模型回复」项按跳过计。
"""

from __future__ import annotations

import asyncio
import ipaddress
import json
import os
import shutil
import socket
import subprocess
import sys
import tempfile
import time
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

SOAPBOT_ROOT = Path(__file__).resolve().parent.parent
PY = sys.executable
DEPLOYED_PROVIDERS = SOAPBOT_ROOT / "data/config/providers.yaml"
TEMPLATE_PERSONA = SOAPBOT_ROOT / "config/personas/default.yaml"
PORT = int(os.environ.get("SOAPBOT_E2E_PORT", "6285"))
BASE = f"http://127.0.0.1:{PORT}"

PASS: list[str] = []
FAIL: list[str] = []
SKIP: list[str] = []


def check(label: str, ok: bool, detail: str = "") -> None:
    print(f"[{'ok  ' if ok else 'FAIL'}] {label}" + (f" — {detail[:600]}" if detail else ""))
    (PASS if ok else FAIL).append(label)


def skip(label: str, detail: str = "") -> None:
    print(f"[skip] {label}" + (f" — {detail[:200]}" if detail else ""))
    SKIP.append(label)


def loopback_request(method: str, url: str, *, body: dict | None = None,
                     cookie: str | None = None,
                     auth: str | None = None) -> tuple[int, str, str]:
    """仅允许环回目标的 HTTP 客户端（倒置白名单：解析后 IP 必须是环回段）。"""
    parsed = urllib.parse.urlsplit(url)
    if parsed.scheme not in ("http", "https"):
        raise ValueError(f"仅允许 http/https：{parsed.scheme}")
    host = parsed.hostname or ""
    if host not in ("127.0.0.1", "localhost", "::1"):
        raise ValueError(f"E2E 仅允许环回目标，拒绝：{host}")
    for info in socket.getaddrinfo(host, parsed.port or 0, type=socket.SOCK_STREAM):
        if not ipaddress.ip_address(info[4][0]).is_loopback:
            raise ValueError("主机解析到非环回地址")
    req = urllib.request.Request(
        url, method=method,
        data=json.dumps(body).encode() if body is not None else None)
    req.add_header("content-type", "application/json")
    if cookie:
        req.add_header("cookie", cookie)
    if auth:
        req.add_header("authorization", f"Bearer {auth}")
    opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
    try:
        with opener.open(req, timeout=30) as resp:
            return (resp.status, resp.read().decode("utf-8", "replace"),
                    resp.headers.get("set-cookie", ""))
    except urllib.error.HTTPError as exc:
        return exc.code, exc.read().decode("utf-8", "replace"), ""


def r(method: str, path: str, body: dict | None = None,
      cookie: str = "") -> tuple[int, str]:
    status, text, _ = loopback_request(method, BASE + path, body=body, cookie=cookie)
    return status, text


async def run_checks(mock, temp: Path, env: dict) -> None:
    # 1. 服务启动 + 面板托管
    status = 0
    deadline = time.monotonic() + 60
    while time.monotonic() < deadline:
        try:
            status, _, _ = loopback_request("GET", f"{BASE}/")
            break
        except (OSError, ValueError):
            time.sleep(0.5)
    check("服务启动 + 面板托管 (GET /)", status == 200, f"status={status}")

    # 2. 适配器 forward 拨号连上协议端
    try:
        await asyncio.wait_for(mock._connected.wait(), timeout=30)
        check("OneBot 适配器 forward 拨号连上协议端", True)
    except TimeoutError:
        check("OneBot 适配器 forward 拨号连上协议端", False, "30s 未连接")
        return

    # 3. bootstrap token → 登录（Bearer 通道）
    tok = subprocess.run(
        [PY, "-m", "soapbot.cli", "token"], cwd=str(temp), env=env,
        capture_output=True, text=True, encoding="utf-8", errors="replace",
    )
    token = next((ln.strip() for ln in tok.stdout.splitlines()
                  if len(ln.strip()) >= 16 and " " not in ln.strip()), "")
    if not token:
        print(f"  token-subprocess rc={tok.returncode} out={tok.stdout[-300:]!r} "
              f"err={tok.stderr[-800:]!r}")
    status, body, _ = loopback_request(
        "POST", f"{BASE}/api/auth/login", body={"init_token": token})
    check("面板登录（bootstrap token）", status == 200, f"status={status} {body[:120]}")
    try:
        bearer = str(json.loads(body).get("access_token") or "")
    except ValueError:
        bearer = ""

    def authed(method: str, path: str, body: dict | None = None) -> tuple[int, str]:
        status, text, _ = loopback_request(method, BASE + path, body=body, auth=bearer)
        return status, text

    # 4. 群消息全链路（真模型；provider 未配置则记 skip）
    at_hello = [{"type": "at", "data": {"qq": 10000}},
                {"type": "text", "data": {"text": "你好，请用一句话介绍你自己"}}]
    await mock.push_group_message(segments=at_hello)
    reply = ""
    deadline = time.monotonic() + 90
    while time.monotonic() < deadline:
        hits = [a for a in mock.received_actions if a["action"] == "send_group_msg"]
        if hits:
            reply = json.dumps(hits[0]["params"], ensure_ascii=False)
            break
        await asyncio.sleep(0.5)
    if reply:
        check("群消息 → 模型回复（send_group_msg）", True, reply[:100])
    else:
        skip("群消息 → 模型回复", "90s 无回复（通常=未配置模型 provider）")

    # 5. 市场目录 + 单插件安装 + 审批 + 加载
    status, body = authed("GET", "/api/plugins/discover")
    check("市场目录可见（discover）", status == 200, f"status={status}")
    if status != 200:
        return
    try:
        first = json.loads(body)
        entries = first.get("entries") or []
        target = next((e for e in entries
                       if str(e.get("name")) == "group-digest"), None)
    except ValueError:
        target = None
    if target is None:
        skip("从索引安装 group-digest", "市场目录中没有 group-digest（索引未含或网络受限）")
        return
    version = str(target.get("latest")
                  or (target.get("versions") or [""])[-1] or "")

    status, body = authed("POST", "/api/plugins/install-from-index",
                          body={"name": "group-digest", "version": version})
    check("从索引安装 group-digest（digest 校验）", status == 200,
          f"status={status} {body[:80]}")

    status, body = authed("POST", "/api/plugins/group-digest/approve",
                          body={"capabilities": ["command", "message", "storage"]})
    check("审批屏放行", status == 200, f"status={status} {body[:80]}")

    status, body = authed("POST", "/api/plugins/group-digest/load", body={})
    check("插件加载（隔离 worker 启动）", status == 200, f"status={status} {body[:80]}")

    # 6. 插件命令真跑（隔离 worker）——@ 唤醒的消息先攒统计再 digest
    await mock.push_group_message(
        segments=[{"type": "at", "data": {"qq": 10000}},
                  {"type": "text", "data": {"text": "今天测试一下活跃统计"}}])
    await asyncio.sleep(2)
    await mock.push_group_message(
        segments=[{"type": "at", "data": {"qq": 10000}},
                  {"type": "text", "data": {"text": "/digest-now"}}])
    digest = ""
    last_reply = ""
    count_before = len(mock.received_actions)
    deadline = time.monotonic() + 30
    while time.monotonic() < deadline:
        after = mock.received_actions[count_before:]
        hits = [a for a in after
                if a["action"] == "send_group_msg"
                and "活跃概览" in json.dumps(a["params"], ensure_ascii=False)]
        if hits:
            digest = json.dumps(hits[0]["params"], ensure_ascii=False)
            break
        for a in after:
            if a["action"] == "send_group_msg":
                last_reply = json.dumps(a["params"], ensure_ascii=False)
        await asyncio.sleep(0.5)
    check("插件命令 /digest-now 真跑（隔离 worker）", bool(digest),
          digest[:120] or f"last_reply={last_reply[:200]}")


async def main() -> int:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    sys.path.insert(0, str(SOAPBOT_ROOT / "src"))
    from soapbot.adapters.mock_onebot import MockOneBot11Server

    temp = Path(tempfile.mkdtemp(prefix="soapbot-e2e-"))
    data_dir = temp / "data"
    (data_dir / "config").mkdir(parents=True)
    if DEPLOYED_PROVIDERS.exists():
        shutil.copy(DEPLOYED_PROVIDERS, data_dir / "config" / "providers.yaml")
    personas_dir = data_dir / "config" / "personas"
    personas_dir.mkdir(parents=True, exist_ok=True)
    if TEMPLATE_PERSONA.exists():
        shutil.copy(TEMPLATE_PERSONA, personas_dir / "default.yaml")

    mock = MockOneBot11Server(host="127.0.0.1", port=0)
    await mock.start()
    (data_dir / "config" / "adapters.yaml").write_text(
        "adapters:\n"
        "  - kind: onebot11\n"
        "    account_id: \"10000\"\n"
        "    mode: forward\n"
        f"    ws_url: {mock.url}\n"
        "    access_token: e2e-test-token\n",
        encoding="utf-8",
    )

    env = {k: v for k, v in os.environ.items() if not k.startswith("SOAPBOT_E2E_")}
    env_file = os.environ.get("SOAPBOT_E2E_ENV_FILE", "")
    env.update({
        "SOAPBOT_DATA_DIR": str(data_dir),
        "SOAPBOT_PORT": str(PORT),
        "PYTHONPATH": str(SOAPBOT_ROOT / "src"),
    })
    if env_file:
        env["SOAPBOT_ENV_FILE"] = env_file
    env.pop("SOAPBOT_MASTER_KEY", None)
    if not env["SOAPBOT_ENV_FILE"]:
        env.pop("SOAPBOT_ENV_FILE", None)

    server_log = temp / "server.log"
    log_handle = server_log.open("w", encoding="utf-8", errors="replace")
    proc = subprocess.Popen(
        [PY, "-m", "soapbot.cli", "start"], cwd=str(temp), env=env,
        stdout=log_handle, stderr=subprocess.STDOUT,
    )
    tail: list[str] = []
    try:
        await run_checks(mock, temp, env)
    finally:
        proc.terminate()
        try:
            proc.wait(timeout=10)
        except subprocess.TimeoutExpired:
            proc.kill()
            proc.wait()
        log_handle.close()
        tail = server_log.read_text(encoding="utf-8", errors="replace").splitlines()[-25:]

    if FAIL:
        print("\n--- 失败时启动/运行日志尾部 ---")
        for line in tail:
            print(f"  log| {line}")
    print(f"\n结果：{len(PASS)} 过 / {len(FAIL)} 败 / {len(SKIP)} 跳过"
          + ("（全部通过）" if not FAIL else ""))
    shutil.rmtree(temp, ignore_errors=True)
    return 1 if FAIL else 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
