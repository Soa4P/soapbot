"""Container profile checks that do not need a Docker daemon.

Why a test file rather than only a script
-----------------------------------------
`scripts/check_deploy.py` prints a report; a human runs it once. These tests run on
every commit, and that matters because two of the defects it finds are the kind that get
reintroduced by a well-meaning edit:

* someone re-adds `SOAPBOT_HOST: 127.0.0.1` to compose because it "looks safer";
* someone re-adds the `./secrets/master.key` bind mount because the comment above it
  says that is the hardened way — not noticing the file is gitignored and will not
  exist on a fresh clone.

Both changes read as safety improvements and both break the deployment. A test is the
only thing that argues back.
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))

import check_deploy  # noqa: E402  (path has to be set first)

COMPOSE = ROOT / "deploy" / "docker-compose.yml"
DOCKERFILE = ROOT / "deploy" / "Dockerfile"


def _compose() -> str:
    return check_deploy._strip_comments(COMPOSE.read_text(encoding="utf-8"))


def _dockerfile() -> str:
    return check_deploy._strip_comments(DOCKERFILE.read_text(encoding="utf-8"))


# --------------------------------------------------------------------- the report


def test_no_blocking_findings() -> None:
    """The whole point: a blocking finding means `compose up` fails at start."""
    report = check_deploy.verify(mirror="docker.m.daocloud.io")
    blocking = [f for f in report.findings if f.level == "block"]
    assert not blocking, "容器部署存在阻断项：\n" + "\n".join(
        f"  [{f.code}] {f.message}" for f in blocking
    )


def test_script_is_clean_enough_to_be_trusted() -> None:
    """A checker that cries wolf is worse than no checker.

    This guards the specific regression already hit once: the compose file documents
    the file-secret opt-in inside a comment, and a regex that does not strip comments
    reports a missing bind source for a line that is not configuration.
    """
    report = check_deploy.verify(mirror="docker.m.daocloud.io")
    assert report.count("block") == 0
    # With a mirror supplied there is nothing left worth warning about either.
    assert report.count("warn") == 0, [f.message for f in report.findings if f.level == "warn"]


# ------------------------------------------------------- the two real regressions


def test_container_binds_all_interfaces() -> None:
    """`127.0.0.1` inside a container makes `ports:` connect to nothing.

    Verified by reasoning, not by running Docker (none available): a published port is
    forwarded to the container's eth0, and a socket listening on the container's own
    loopback is not reachable from there. This is the single most common way a
    hardened compose file silently produces an unreachable service.
    """
    compose = _compose()
    dockerfile = _dockerfile()

    host_env = re.search(r"SOAPBOT_HOST:\s*(\S+)", compose)
    assert host_env, "compose 未设置 SOAPBOT_HOST"
    assert host_env.group(1) == "0.0.0.0", (
        "容器内必须绑定 0.0.0.0；隔离由宿主机侧 ports: 127.0.0.1:... 保证，"
        f"当前为 {host_env.group(1)}"
    )

    cmd = next(line for line in dockerfile.splitlines() if line.strip().startswith("CMD"))
    assert "--host" in cmd and "0.0.0.0" in cmd, f"CMD 与 compose 不一致：{cmd.strip()}"


def test_no_bind_mount_without_source() -> None:
    """A missing bind source becomes an empty *directory*, and the app then reads a
    directory as a key file — falling back to plaintext plugin secrets while healthy."""
    compose = _compose()
    mounts = re.findall(r"-\s+(\.{1,2}/[^:\s]+):([^:\s]+)(?::([a-z,]+))?", compose)
    for host_path, _container, _mode in mounts:
        resolved = (COMPOSE.parent / host_path).resolve()
        assert resolved.exists(), (
            f"bind mount 源不存在：{host_path}。Docker 会创建空目录，"
            "应用读目录当密钥文件会失败并静默退化为明文存储"
        )


def test_secret_mount_documented_when_disabled() -> None:
    """If file-based secrets are off, the *reason* must be in the file.

    An operator who sees no key mount will assume it was forgotten and add one — the
    failure mode this test protects against, one level up.
    """
    raw = COMPOSE.read_text(encoding="utf-8")
    has_mount = re.search(r"master\.key:/run/secrets", _compose())
    if not has_mount:
        assert "secrets/master.key" in raw, "未启用密钥挂载，但也没有任何说明"
        assert "SOAPBOT_MASTER_KEY_FILE" in raw, "未说明如何启用文件式密钥"


# ------------------------------------------------------------------- other checks


def test_cli_flags_used_by_dockerfile_exist() -> None:
    """A renamed CLI flag turns every container start into 'unrecognized arguments'."""
    cmd = next(
        line.strip()
        for line in _dockerfile().splitlines()
        if line.strip().startswith("CMD")
    )
    cli_source = (ROOT / "src" / "soapbot" / "cli.py").read_text(encoding="utf-8")
    for flag in re.findall(r"--([a-z][a-z0-9-]*)", cmd):
        assert f'"{flag}"' in cli_source or f'"--{flag}"' in cli_source, (
            f"Dockerfile 使用了 CLI 未定义的参数 --{flag}"
        )


def test_hardening_controls_present() -> None:
    """Each of these closes a specific escape; the reason is in the compose comments."""
    compose = _compose()
    dockerfile = _dockerfile()
    checks = {
        "USER": (dockerfile, r"^USER\s+\S+"),
        "read_only": (compose, r"^\s+read_only:\s*true"),
        "cap_drop": (compose, r"cap_drop:"),
        "no-new-privileges": (compose, r"no-new-privileges:true"),
        "mem_limit": (compose, r"^\s+mem_limit:"),
        "pids_limit": (compose, r"^\s+pids_limit:"),
        "tmpfs": (compose, r"^\s+tmpfs:"),
        "healthcheck": (compose, r"^\s+healthcheck:"),
    }
    missing = [
        name for name, (text, pattern) in checks.items() if not re.search(pattern, text, re.M)
    ]
    assert not missing, f"缺少加固项：{missing}"


def test_dockerignore_excludes_runtime_state() -> None:
    """`data/` holds the database and the Fernet key; an image layer keeps deleted files."""
    ignore = ROOT / ".dockerignore"
    assert ignore.is_file(), "缺少 .dockerignore"
    entries = {
        line.strip().rstrip("/")
        for line in ignore.read_text(encoding="utf-8").splitlines()
        if line.strip() and not line.strip().startswith("#")
    }
    for required in ("data", ".venv", "node_modules", ".git"):
        assert required in entries, f".dockerignore 未排除 {required}"


def test_config_is_not_dockerignored() -> None:
    """The opposite mistake: excluding config/ makes the image start with no adapters."""
    ignore_text = (ROOT / ".dockerignore").read_text(encoding="utf-8")
    entries = {
        line.strip().rstrip("/")
        for line in ignore_text.splitlines()
        if line.strip() and not line.strip().startswith("#")
    }
    assert "config" not in entries, (
        "config/ 被 .dockerignore 排除会让镜像内没有 providers/adapters，"
        "容器启动后收不到任何消息"
    )


@pytest.mark.parametrize("flag", ["--host", "--port"])
def test_cli_accepts_start_flags(flag: str) -> None:
    """Belt and braces: the parser really does define them, not just mention them."""
    source = (ROOT / "src" / "soapbot" / "cli.py").read_text(encoding="utf-8")
    assert re.search(rf'add_argument\(\s*"{flag}"', source), f"cli.py 未定义 {flag}"
