"""Static verification of the container deployment profile.

Why this exists
---------------
`docker` is not available on the development machine and cannot be installed (the
account is a standard user, WSL has no distro, and the CPU reports
``VirtualizationFirmwareEnabled = False``). That leaves two dishonest options and one
useful one:

* claim the container config is "verified" — false, and the project's own rule forbids it;
* leave it entirely unchecked until a server appears — also bad, because the config has
  real defects that are findable without a daemon.

This script is the third option. It cannot prove the image *runs*; it can prove the
specific mistakes that make `docker compose up` fail or silently weaken the profile:

1. a secret bind-mount whose source does not exist (Docker creates a **directory** at
   the path, the app then reads a directory as a key file, and plugin secrets fall back
   to plaintext);
2. a base image that cannot be pulled where the operator actually is;
3. `CMD`/`--host` mismatch between the Dockerfile and the CLI parser;
4. a published port that contradicts the bind address inside the container;
5. a missing `USER`, `read_only`, `cap_drop`, or `no-new-privileges`, each of which is
   load-bearing for the plugin-isolation story;
6. a `.dockerignore` that would leak or bloat the build context.

Every check prints the line it relied on, so a reviewer can confirm the reasoning
without trusting this script. Exit code is non-zero only for findings that *block* a
deployment; warnings are reported and listed in the assessment as unverified.
"""

from __future__ import annotations

import argparse
import re
import sys
from dataclasses import dataclass, field
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DOCKERFILE = ROOT / "deploy" / "Dockerfile"
COMPOSE = ROOT / "deploy" / "docker-compose.yml"
CLI = ROOT / "src" / "soapbot" / "cli.py"


@dataclass
class Finding:
    level: str  # "block" | "warn" | "ok"
    code: str
    message: str
    evidence: str = ""


@dataclass
class Report:
    findings: list[Finding] = field(default_factory=list)

    def add(self, level: str, code: str, message: str, evidence: str = "") -> None:
        self.findings.append(Finding(level, code, message, evidence))

    def count(self, level: str) -> int:
        return sum(1 for f in self.findings if f.level == level)


def _read(path: Path) -> str:
    if not path.is_file():
        return ""
    return path.read_text(encoding="utf-8")


def _line_with(text: str, pattern: str) -> str:
    """Return the first matching line, stripped — used as evidence."""
    for line in text.splitlines():
        if re.search(pattern, line):
            return line.strip()
    return ""


# --------------------------------------------------------------------------- checks


def _strip_comments(text: str) -> str:
    """Remove YAML/Dockerfile comments before structural checks.

    Necessary because the compose file documents *how* to enable file-based secrets
    inside a comment block. A naive regex finds the commented example, reports a
    missing bind source, and the check loses the ability to be trusted — a false
    positive is not cheaper than a miss, it is what teaches people to ignore the tool.
    """
    out = []
    for line in text.splitlines():
        stripped = line.lstrip()
        if stripped.startswith("#"):
            continue
        # Trailing comment: cut at the first ` #` that is not inside quotes. Good enough
        # for these two files, which have no `#` inside quoted values.
        out.append(re.sub(r"\s+#\s.*$", "", line))
    return "\n".join(out)


def check_secret_mount(report: Report) -> None:
    """A bind-mount source that does not exist is not a warning in Docker: it is
    created as an empty *directory*, and the app then tries to read it as a file."""
    compose = _strip_comments(_read(COMPOSE))
    if not compose.strip():
        report.add("block", "compose.missing", "deploy/docker-compose.yml 不存在")
        return

    # Collect `- ./x:/y:ro` style relative binds (not named volumes).
    mounts = re.findall(r"-\s+(\.{1,2}/[^:\s]+):([^:\s]+)(?::([a-z,]+))?", compose)
    if not mounts:
        report.add("ok", "compose.no-bind", "compose 未使用相对路径 bind mount")
        return

    missing = []
    for host_path, container_path, mode in mounts:
        resolved = (COMPOSE.parent / host_path).resolve()
        # `.. /config` is the repository config dir; it exists.
        if not resolved.exists():
            missing.append((host_path, container_path, mode))

    if missing:
        for host_path, container_path, mode in missing:
            report.add(
                "block",
                "compose.missing-bind",
                f"bind mount 源不存在：{host_path} → {container_path}。"
                "Docker 会创建一个空**目录**在该路径，容器内读取密钥文件会失败",
                evidence=f"- {host_path}:{container_path}:{mode or ''}".rstrip(":"),
            )
    else:
        report.add("ok", "compose.bind-ok", "所有 bind mount 源均存在")


def check_dockerignore(report: Report) -> None:
    """Without `.dockerignore`, `COPY src ./src` still works, but the build context
    includes `data/` (runtime DB, keys) and `.venv/` (hundreds of MB). The first is a
    leak: image layers keep deleted files."""
    ignore = ROOT / ".dockerignore"
    if not ignore.is_file():
        report.add(
            "warn",
            "build.no-dockerignore",
            "缺少 .dockerignore：构建上下文包含 data/（含数据库与密钥）与 .venv/，"
            "前者会随镜像层泄露、后者让每次构建传输数百 MB",
        )
        return
    text = _read(ignore)
    needed = {"data", ".venv", ".git", "node_modules", "dist", "tests"}
    present = {
        line.strip().rstrip("/")
        for line in text.splitlines()
        if line.strip() and not line.strip().startswith("#")
    }
    missing = sorted(n for n in needed if n not in present)
    if missing:
        report.add(
            "warn",
            "build.dockerignore-incomplete",
            f".dockerignore 未排除：{', '.join(missing)}",
        )
    else:
        report.add("ok", "build.dockerignore-ok", ".dockerignore 覆盖关键目录")


def check_host_bind(report: Report) -> None:
    """`SOAPBOT_HOST=127.0.0.1` inside a container publishes nothing outside the
    container's own loopback, so `ports:` never receives a connection."""
    compose = _strip_comments(_read(COMPOSE))
    dockerfile = _strip_comments(_read(DOCKERFILE))

    env_host = ""
    for line in compose.splitlines():
        if "SOAPBOT_HOST" in line:
            env_host = line.strip()
            break

    cmd_host = ""
    for line in dockerfile.splitlines():
        if line.strip().startswith("CMD") and "--host" in line:
            cmd_host = line.strip()
            break

    binds_loopback = bool(re.search(r"SOAPBOT_HOST:\s*127\.0\.0\.1", compose)) or bool(
        re.search(r"--host\",\s*\"127\.0\.0\.1\"", dockerfile)
    )
    publishes = bool(re.search(r"^\s+ports:", compose, re.MULTILINE))

    if binds_loopback and publishes:
        report.add(
            "block",
            "net.loopback-in-container",
            "容器内绑定 127.0.0.1 且 compose 声明了 ports：端口映射到的是容器的 loopback，"
            "宿主机连不上。容器内必须绑定 0.0.0.0（隔离仍由 `ports: 127.0.0.1:...` 保证）",
            evidence=env_host or cmd_host,
        )
    elif binds_loopback and not publishes:
        report.add("ok", "net.loopback-no-port", "容器内绑定 loopback 且未发布端口，一致")
    else:
        report.add("ok", "net.bind-ok", "容器内绑定地址与端口发布一致")


def check_cli_flags(report: Report) -> None:
    """The Dockerfile CMD must match the argument parser. A flag renamed in the CLI
    turns every container start into `unrecognized arguments`."""
    dockerfile = _strip_comments(_read(DOCKERFILE))
    cli = _read(CLI)

    cmd = ""
    for line in dockerfile.splitlines():
        if line.strip().startswith("CMD"):
            cmd = line.strip()
            break
    if not cmd:
        report.add("block", "cli.no-cmd", "Dockerfile 未声明 CMD")
        return

    flags = set(re.findall(r"--([a-z][a-z0-9-]*)", cmd))
    missing = [f for f in sorted(flags) if not re.search(rf'add_argument\(\s*"--{re.escape(f)}"', cli)]
    if missing:
        report.add(
            "block",
            "cli.flag-mismatch",
            f"Dockerfile CMD 使用了 CLI 未定义的参数：{', '.join('--' + f for f in missing)}",
            evidence=cmd,
        )
    else:
        report.add(
            "ok",
            "cli.flags-ok",
            f"Dockerfile CMD 的参数在 cli.py 中均已定义（{', '.join('--' + f for f in sorted(flags))}）",
            evidence=cmd,
        )


def check_hardening(report: Report) -> None:
    """Each of these closes a specific escape; their absence is not cosmetic."""
    compose = _strip_comments(_read(COMPOSE))
    dockerfile = _strip_comments(_read(DOCKERFILE))

    required = [
        ("USER", r"^USER\s+\S+", dockerfile, "镜像以 root 运行"),
        ("read_only", r"^\s+read_only:\s*true", compose, "根文件系统可写，被攻陷的依赖可持久化"),
        ("cap_drop", r"cap_drop:", compose, "未丢弃 capabilities"),
        ("no-new-privileges", r"no-new-privileges:true", compose, "setuid 二进制可提权"),
        ("healthcheck", r"^\s+healthcheck:", compose, "无健康检查，编排层无法判断存活"),
        ("mem_limit", r"^\s+mem_limit:", compose, "无内存上限，插件泄漏可拖垮宿主机"),
        ("pids_limit", r"^\s+pids_limit:", compose, "无进程数上限，fork 炸弹无界"),
    ]
    for name, pattern, text, why in required:
        if re.search(pattern, text, re.MULTILINE):
            report.add("ok", f"hardening.{name}", f"{name} 已设置")
        else:
            report.add("block", f"hardening.{name}", f"{name} 缺失：{why}")

    # A tmpfs on /tmp is what makes read_only livable; without it, pip/httpx temp files fail.
    if re.search(r"^\s+tmpfs:", compose, re.MULTILINE):
        report.add("ok", "hardening.tmpfs", "tmpfs 已挂载（read_only 下可写临时目录）")
    else:
        report.add("warn", "hardening.tmpfs", "read_only 为真但未挂载 tmpfs，/tmp 不可写")


def check_image_availability(report: Report, mirror: str | None) -> None:
    """Record the registry situation as a fact, not a guess. Without a reachable
    registry the build fails at the first `FROM`, and that is worth knowing before
    renting a server."""
    dockerfile = _strip_comments(_read(DOCKERFILE))
    bases = re.findall(r"^FROM\s+(\S+)", dockerfile, re.MULTILINE)
    if not bases:
        report.add("warn", "image.no-base", "未能从 Dockerfile 解析基础镜像")
        return

    if mirror:
        report.add(
            "ok",
            "image.mirror-configured",
            f"已指定镜像加速地址 {mirror}；基础镜像：{', '.join(bases)}",
        )
    else:
        report.add(
            "warn",
            "image.mirror-unknown",
            "未指定镜像加速地址。本机直连 Docker Hub 超时（已实测），"
            "在服务器上需先配置 registry-mirrors 或改用可用的私有仓库，否则 build 在第一步失败",
            evidence=", ".join(bases),
        )


def check_ports_documented(report: Report) -> None:
    """The compose comment promises loopback-only publishing; verify the actual value
    rather than the comment."""
    compose = _strip_comments(_read(COMPOSE))
    m = re.search(r"-\s+\"?([\d.]+):(\d+):(\d+)\"?", compose)
    if not m:
        report.add("warn", "net.no-published-port", "compose 未发布端口，宿主机无法访问面板")
        return
    host_ip, host_port, container_port = m.group(1), m.group(2), m.group(3)
    if host_ip == "127.0.0.1":
        report.add(
            "ok",
            "net.publish-loopback",
            f"端口发布在宿主机 loopback（127.0.0.1:{host_port} → {container_port}）",
        )
    else:
        report.add(
            "warn",
            "net.publish-public",
            f"端口发布在 {host_ip}，等同于把管理 API 暴露到网络；必须同时启用令牌认证与反向代理",
        )


# ----------------------------------------------------------------------------- main


def verify(mirror: str | None = None) -> Report:
    report = Report()
    check_secret_mount(report)
    check_dockerignore(report)
    check_host_bind(report)
    check_cli_flags(report)
    check_hardening(report)
    check_image_availability(report, mirror)
    check_ports_documented(report)
    return report


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="静态检查容器部署配置（不起 Docker）")
    parser.add_argument(
        "--mirror",
        default=None,
        help="计划使用的镜像加速地址，例如 docker.m.daocloud.io；提供后会作为已知条件记录",
    )
    parser.add_argument("--strict", action="store_true", help="把 warn 也视为失败")
    args = parser.parse_args(argv)

    report = verify(args.mirror)

    SYMBOL = {"ok": "[ok  ]", "warn": "[warn]", "block": "[BLOCK]"}
    for f in report.findings:
        print(f"{SYMBOL[f.level]} {f.code:34s} {f.message}")
        if f.evidence:
            print(f"         证据: {f.evidence}")

    blocks = report.count("block")
    warns = report.count("warn")
    print()
    print(f"结论：{blocks} 项阻断，{warns} 项告警，{report.count('ok')} 项通过")

    if blocks:
        print("→ 存在阻断项，容器部署会在启动阶段失败，不会进入「运行但有问题」的状态。")
        return 1
    if warns and args.strict:
        print("→ --strict 下把告警视为失败。")
        return 1

    print("→ 静态检查通过。注意：这不等于容器实测通过（本机无 Docker）。")
    return 0


if __name__ == "__main__":
    sys.exit(main())
