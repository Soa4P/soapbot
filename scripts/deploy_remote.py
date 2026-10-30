"""Drive the container deployment over ssh, one attributable step at a time.

Why a driver instead of a long shell one-liner
----------------------------------------------
The last time this deployment was attempted, the interesting question was never "did
the command finish" — it was "which layer said no": the private key's file mode, the
outbound policy, a missing Docker, or the app itself. A single `&&`-chained command
answers that with one exit code and no attribution.

So each step is its own ssh invocation with its own captured output. A step that fails
stops the run and prints the diagnosis for *that* layer, which is the whole point.

The checklist is `docs/deploy-layer.md` §8, in order. Items that need eyes on a browser
are reported as MANUAL rather than quietly counted as passing.

Usage
-----
    python scripts/deploy_remote.py --host 1.2.3.4 --user root --dry-run
    python scripts/deploy_remote.py --host 1.2.3.4 --user root --key C:\\path\\key.pem

`--key` is passed to ssh as `-i <path>`; this script never opens the file.
"""

from __future__ import annotations

import argparse
import shlex
import subprocess
import sys
from dataclasses import dataclass, field
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

#: Loopback publish from `deploy/docker-compose.yml`; the container listens on 6185.
PORT = 6185


@dataclass
class Step:
    """One remotely executed command and what its result means."""

    title: str
    command: str
    expectation: str
    diagnosis: str
    #: Filled in once the step has run.
    ok: bool | None = None
    output: str = ""


@dataclass
class Run:
    host: str
    user: str
    key: str | None
    directory: str
    commit: str
    repo: str
    port: int = 22
    steps: list[Step] = field(default_factory=list)


def ssh_command(run: Run, script: str) -> list[str]:
    """Build argv for one remote execution.

    ``BatchMode=yes`` turns any interactive prompt into an immediate failure instead of
    a hang: a deploy script that stops to ask for a passphrase looks identical to a
    broken network from the outside.
    """
    argv = [
        "ssh",
        "-o",
        "BatchMode=yes",
        "-o",
        "ConnectTimeout=10",
        "-o",
        "StrictHostKeyChecking=accept-new",
        "-p",
        str(run.port),
    ]
    if run.key:
        argv += ["-i", run.key]
    argv += [f"{run.user}@{run.host}", "bash -s"]
    return argv


def build_steps(run: Run) -> list[Step]:
    directory = shlex.quote(run.directory)
    repo = shlex.quote(run.repo)
    commit = shlex.quote(run.commit)

    return [
        Step(
            "连通性与身份",
            "whoami && uname -sr && id -u",
            "打印用户名、内核版本、uid",
            "连不上：区分「TCP 不通」（出向策略/防火墙）与「认证失败」（密钥或用户不对）。"
            "密钥本身被 ssh 拒收时会报 UNPROTECTED PRIVATE KEY FILE。",
        ),
        Step(
            "Docker 可用性",
            "command -v docker && docker --version && docker compose version",
            "两条版本号都打印",
            "缺依赖：先装 Docker Engine 与 compose 插件；不同时具备则无法用 compose 起服务。",
        ),
        Step(
            "取代码到目标 commit",
            f"mkdir -p {directory} && cd {directory} && "
            f"(git rev-parse --git-dir >/dev/null 2>&1 || git clone {repo} .) && "
            f"git fetch --all --quiet && git checkout {commit} && git rev-parse --short HEAD",
            f"打印 {run.commit} 的前 7 位",
            "服务器无外网出口时 git clone 会超时：改为本地打包上传，而不是重试。",
        ),
        Step(
            "构建镜像（§8 #1）",
            f"cd {directory} && docker compose -f deploy/docker-compose.yml build",
            "退出码 0，末尾 naming to ... soapbot:hardened",
            "基础镜像拉不到（看 deploy/daemon-mirror.md 的镜像加速）；或缺编译工具链。",
        ),
        Step(
            "启动并等健康（§8 #2）",
            f"cd {directory} && docker compose -f deploy/docker-compose.yml up -d "
            f"&& sleep 25 && docker compose -f deploy/docker-compose.yml ps",
            "服务状态含 Up (healthy)",
            "start_period 太短，或进程没监听 6185：docker compose logs 里会有 traceback。",
        ),
        Step(
            "非 root 运行（§8 #3）",
            f"cd {directory} && docker compose -f deploy/docker-compose.yml exec -T soapbot id",
            "uid=10001 gid=10001，不是 root",
            "compose 的 user: 没生效。",
        ),
        Step(
            "根文件系统只读（§8 #4）",
            f"cd {directory} && docker compose -f deploy/docker-compose.yml exec -T soapbot "
            "sh -c 'touch /app/x' 2>&1 || true",
            "报 Read-only file system",
            "read_only: true 没生效——这一条不通过意味着容器内可以持久化写入。",
        ),
        Step(
            "健康端点（§8 #5）",
            f"curl -fsS --max-time 10 http://127.0.0.1:{PORT}/api/health",
            '{"status":"ok",...}',
            "端口映射方向反了，或容器内绑到了 loopback；也可能是反代把它劫走了。",
        ),
        Step(
            "init 是 tini（§8 #9）",
            f"cd {directory} && docker compose -f deploy/docker-compose.yml exec -T soapbot "
            "cat /proc/1/comm",
            "tini",
            "ENTRYPOINT 被覆盖，插件子进程会成为孤儿。",
        ),
        Step(
            "自检 doctor",
            f"cd {directory} && docker compose -f deploy/docker-compose.yml exec -T soapbot "
            "python -m soapbot.cli doctor",
            "输出各检查项；critical/high 应为 0",
            "doctor 本身就是归因工具：哪一条红，就说明哪一层不安全或没生效。",
        ),
    ]


MANUAL = [
    ("§8 #6", "浏览器打开 http://<服务器>:6185 登录，在第 12 页切一次语言、开一次语音开关，"
              "再 docker compose exec soapbot cat /data/.env 看有没有对应行",
     "唯一能证明 SOAPBOT_ENV_FILE 真的指向可写卷的方法"),
    ("§8 #7", "docker compose restart soapbot 后再看第 12 页", "验证读回路径与写入路径一致"),
    ("§8 #8", "docker compose down && docker compose up -d，再看数据与设置是否还在", "验证卷生效"),
]


def run_step(run: Run, step: Step) -> Step:
    argv = ssh_command(run, step.command)
    completed = subprocess.run(
        argv,
        input=step.command,
        capture_output=True,
        text=True,
        timeout=1800,
    )
    step.output = (completed.stdout + completed.stderr).strip()
    step.ok = completed.returncode == 0
    return step


def report(run: Run) -> int:
    failed = [s for s in run.steps if s.ok is False]
    for index, step in enumerate(run.steps, 1):
        mark = "PASS  " if step.ok else "FAIL  "
        print(f"[{index}/{len(run.steps)}] {mark}{step.title}")
        if step.output:
            for line in step.output.splitlines()[-12:]:
                print(f"         {line}")
        if step.ok is False:
            print(f"         → 判据：{step.expectation}")
            print(f"         → 归因：{step.diagnosis}")
            break

    print()
    print("需要人工的三条（脚本不代劳，也不假装通过）：")
    for tag, what, why in MANUAL:
        print(f"  {tag}  {what}")
        print(f"         理由：{why}")

    if failed:
        print(f"\n第 {run.steps.index(failed[0]) + 1} 步失败，后续步骤未执行。")
        return 1
    print("\n自动化可判定的七步全部通过。")
    return 0


def main(argv: list[str]) -> int:
    # Same guard as every other scripts/*.py: cp1252 stdout raises on the first Chinese
    # character, and a deploy log that dies on its own output is indistinguishable from
    # a failed step.
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")

    parser = argparse.ArgumentParser(description="Deploy soapbot over ssh, step by step.")
    parser.add_argument("--host", required=True, help="IP or hostname of the Ubuntu box")
    parser.add_argument("--user", default="root")
    parser.add_argument("--port", type=int, default=22)
    parser.add_argument("--key", default=None, help="path passed to ssh -i; never read here")
    parser.add_argument("--dir", dest="directory", default="/opt/soapbot")
    parser.add_argument("--repo", default="https://github.com/Soa4P/soapbot.git")
    parser.add_argument("--commit", default="02ad519")
    parser.add_argument(
        "--dry-run", action="store_true", help="print the steps and exit without connecting"
    )
    args = parser.parse_args(argv)

    run = Run(
        host=args.host,
        user=args.user,
        key=args.key,
        directory=args.directory,
        commit=args.commit,
        repo=args.repo,
        port=args.port,
    )
    run.steps = build_steps(run)

    if args.dry_run:
        print(f"目标：{args.user}@{args.host}:{args.port}  密钥：{args.key or '(ssh 默认)'}")
        print(f"目录：{args.directory}  commit：{args.commit}\n")
        for index, step in enumerate(run.steps, 1):
            print(f"[{index}] {step.title}")
            print(f"    $ {step.command}")
        print(f"\n另有 {len(MANUAL)} 条需人工在浏览器里验证。")
        return 0

    for step in run.steps:
        run_step(run, step)
        if step.ok is False:
            break
    return report(run)


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
