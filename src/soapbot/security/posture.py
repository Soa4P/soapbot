"""Deployment posture checks — security you can *run*, not just document.

Why this module exists
----------------------
The isolation review ended with a set of deployment requirements: run as non-root,
bind the control API to loopback, keep secrets out of the container environment,
use a read-only root filesystem. Those are correct and none of them are verifiable
from inside the application, so in practice they were **aspirations**. A deployment
that skipped all of them looked identical to one that followed every rule, right up
until someone found the exposed port.

The fix is the same one applied to capabilities: turn the requirement into a check
with a name, a severity and a remediation string, and let a command run it. A finding
an operator can act on is worth more than a paragraph they can skip.

What is checkable from inside the process
-----------------------------------------
* **privilege** — effective uid/gid, and whether the host is uid 0;
* **filesystem mode** — is the plugin directory writable by the host user (a plugin
  that can write its own ``main.py`` can rewrite itself between restarts);
* **key material** — is the master key a file readable by group/other, is it passed
  through the environment (visible in ``/proc/<pid>/environ`` and ``docker inspect``);
* **bind address** — the control API must not listen on a public interface;
* **secret env leakage** — are host secrets present in the process environment at all
  (the exact thing measured leaking to plugin children before the allowlist);
* **container signals** — cgroup membership and read-only rootfs, used to report
  whether the *deployment-layer* mitigations the docs require are actually in place.

What is not checkable
---------------------
Whether a reverse proxy in front of the API enforces auth, and whether the network
policy isolates containers. Those are reported as ``unknown`` with a remediation
line instead of being silently marked "pass" — a checklist that lies is worse than
no checklist.
"""

from __future__ import annotations

import os
import stat
import sys
from collections.abc import Callable
from dataclasses import dataclass, field
from enum import StrEnum
from pathlib import Path
from typing import Any
from urllib.parse import urlsplit

import yaml


class Severity(StrEnum):
    CRITICAL = "critical"
    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"
    INFO = "info"


class Status(StrEnum):
    PASS = "pass"
    FAIL = "fail"
    WARN = "warn"
    UNKNOWN = "unknown"


@dataclass(slots=True)
class Finding:
    check: str
    status: Status
    severity: Severity
    detail: str
    remediation: str = ""

    def to_dict(self) -> dict[str, str]:
        return {
            "check": self.check,
            "status": str(self.status),
            "severity": str(self.severity),
            "detail": self.detail,
            "remediation": self.remediation,
        }


@dataclass(slots=True)
class PostureReport:
    findings: list[Finding] = field(default_factory=list)

    @property
    def failed(self) -> list[Finding]:
        return [f for f in self.findings if f.status is Status.FAIL]

    @property
    def critical(self) -> list[Finding]:
        return [f for f in self.findings if f.status is Status.FAIL and f.severity is Severity.CRITICAL]

    @property
    def ok(self) -> bool:
        """True when nothing serious is wrong.

        Deliberately not "no findings at all": a medium warning (say, the plugin dir
        being writable by the deployment user, normal in a container) should not fail
        a deploy gate and train operators to ignore it.

        The rule is severity-first, not status-first: anything at CRITICAL or HIGH
        that is not a PASS fails the gate. An earlier version keyed only on
        ``Status.FAIL``, so a HIGH-severity ``WARN`` — which is what ``secrets.env``
        used to return — passed silently. Severity is the thing that expresses "how
        bad if wrong", so it should decide the gate; status is just the wording.
        """
        return not any(
            f.severity in (Severity.CRITICAL, Severity.HIGH)
            and f.status not in (Status.PASS, Status.UNKNOWN)
            for f in self.findings
        )

    def summary(self) -> dict[str, int]:
        out: dict[str, int] = {}
        for f in self.findings:
            key = f"{f.severity}:{f.status}"
            out[key] = out.get(key, 0) + 1
        return out


#: Environment variable names that must never be visible to a plugin or, ideally, to
#: the host process at all. Matched case-insensitively by substring, because the set
#: of provider-specific names is unbounded (``AWS_SECRET_ACCESS_KEY``,
#: ``AZURE_CLIENT_SECRET``, ``HF_TOKEN``, ...).
_SECRET_MARKERS = ("SECRET", "PASSWORD", "PASSWD", "APIKEY", "API_KEY", "TOKEN", "MASTER_KEY", "PRIVATE_KEY")


def _is_secret_env_name(name: str) -> bool:
    upper = name.upper()
    # ``*_FILE`` / ``*_PATH`` variables hold a *location*, not a secret. Flagging them
    # is actively harmful: ``SOAPBOT_MASTER_KEY_FILE`` is the remediation this very
    # check recommends, so counting it made the correct deployment fail the gate and
    # told the operator to do the thing they had already done.
    if upper.endswith(("_FILE", "_PATH", "_DIR", "_FILENAME")):
        return False
    return any(marker in upper for marker in _SECRET_MARKERS)


def check_privilege() -> Finding:
    """Running as root inside a container is the single most common way a plugin
    escape becomes a host escape."""
    if sys.platform == "win32":
        return Finding(
            check="privilege.uid",
            status=Status.UNKNOWN,
            severity=Severity.MEDIUM,
            detail="Windows: uid model does not apply; run the service as a dedicated "
            "low-privilege account instead",
            remediation="Create a dedicated service account and run the bot under it.",
        )
    getuid = getattr(os, "getuid", None)
    if getuid is None:  # pragma: no cover - exotic platform
        return Finding(
            check="privilege.uid",
            status=Status.UNKNOWN,
            severity=Severity.MEDIUM,
            detail="uid unavailable on this platform",
        )
    uid = getuid()
    if uid == 0:
        return Finding(
            check="privilege.uid",
            status=Status.FAIL,
            severity=Severity.CRITICAL,
            detail="process runs as uid 0 (root)",
            remediation="Run as a non-root user (USER 10001 in the Dockerfile, or "
            "'user:' in compose). A plugin writing to its own directory would "
            "otherwise be able to modify host files.",
        )
    return Finding(
        check="privilege.uid",
        status=Status.PASS,
        severity=Severity.CRITICAL,
        detail=f"running as uid {uid} (non-root)",
    )


def check_plugin_dir_writable(plugin_dir: Path | None) -> Finding:
    """A plugin that can write its own source can rewrite itself between restarts.

    This is a *supply-chain* issue rather than a runtime one, which is why it is
    medium: the code already runs, so the immediate gain is small. It matters because
    it survives restarts and defeats a "reviewed the plugin once" assumption.
    """
    if plugin_dir is None or not plugin_dir.exists():
        return Finding(
            check="fs.plugin_dir",
            status=Status.UNKNOWN,
            severity=Severity.LOW,
            detail="plugin directory not present",
        )
    writable = os.access(plugin_dir, os.W_OK)
    if writable:
        return Finding(
            check="fs.plugin_dir",
            status=Status.WARN,
            severity=Severity.MEDIUM,
            detail=f"{plugin_dir} is writable by the bot process",
            remediation="Mount the plugin directory read-only for the bot if plugins "
            "are deployed as artefacts (':ro' in compose), so a compromised plugin "
            "cannot persist changes to its own code.",
        )
    return Finding(
        check="fs.plugin_dir",
        status=Status.PASS,
        severity=Severity.MEDIUM,
        detail=f"{plugin_dir} is not writable",
    )


def check_key_file_mode(key_path: Path | None) -> Finding:
    """The master key decrypts every stored API key, so its file mode matters."""
    if key_path is None or not key_path.exists():
        return Finding(
            check="secrets.key_file",
            status=Status.UNKNOWN,
            severity=Severity.HIGH,
            detail="master key file not found (key may be supplied another way)",
        )
    if sys.platform == "win32":  # pragma: no cover - Windows ACLs need a different API
        return Finding(
            check="secrets.key_file",
            status=Status.UNKNOWN,
            severity=Severity.HIGH,
            detail="Windows: verify the key file ACL manually",
            remediation="Use icacls to restrict the key file to the service account.",
        )
    mode = key_path.stat().st_mode
    if mode & (stat.S_IRGRP | stat.S_IROTH):
        return Finding(
            check="secrets.key_file",
            status=Status.FAIL,
            severity=Severity.HIGH,
            detail=f"{key_path} is readable by group/other (mode {oct(mode & 0o777)})",
            remediation=f"chmod 600 {key_path}",
        )
    return Finding(
        check="secrets.key_file",
        status=Status.PASS,
        severity=Severity.HIGH,
        detail=f"{key_path} mode {oct(mode & 0o777)}",
    )


def check_secrets_in_env() -> Finding:
    """Secrets in the environment leak three ways: ``/proc/<pid>/environ``, crash
    dumps, and ``docker inspect``. They are also what the child-process allowlist is
    designed to keep out of plugins — but the allowlist only helps if the host's own
    environment is the thing holding them."""
    found = sorted({k for k in os.environ if _is_secret_env_name(k)})
    if found:
        # FAIL, not WARN. This finding was previously reported as ``WARN`` at HIGH
        # severity, which made it invisible to ``PostureReport.ok``: that property
        # only counts ``FAIL``, so a deployment with the master key sitting in the
        # environment still printed "verdict: PASS" and exited 0 under ``--strict``.
        # The gate therefore passed precisely the leak it exists to catch. WARN
        # should mean "works, but could be better"; a readable master key is not in
        # that category — any process on the host can decrypt every stored API key.
        return Finding(
            check="secrets.env",
            status=Status.FAIL,
            severity=Severity.HIGH,
            detail=f"{len(found)} secret-looking variables in the environment: "
            + ", ".join(found[:6])
            + ("..." if len(found) > 6 else ""),
            remediation="Pass secrets as files (SOAPBOT_MASTER_KEY_FILE) rather than "
            "environment variables; env vars are visible to 'docker inspect' and "
            "/proc/<pid>/environ.",
        )
    return Finding(
        check="secrets.env",
        status=Status.PASS,
        severity=Severity.HIGH,
        detail="no secret-looking variables in the process environment",
    )


def check_bind_address(host: str | None, *, in_container: bool = False) -> Finding:
    """The control API manages plugins and capabilities; a public bind is an
    unauthenticated admin surface waiting to be found.

    Inside a container the reading changes, and only slightly: ``0.0.0.0`` is required
    for a published port to reach the process at all, so the question becomes "what
    did the host publish" — which is invisible from in here. That is a WARNING with an
    instruction, not a CRITICAL failure. Keeping it critical would make
    ``doctor --strict`` red on the compose file this repository ships, and a gate that
    is red on its own reference deployment is a gate people learn to skip.
    """
    if host is None:
        return Finding(
            check="net.bind",
            status=Status.UNKNOWN,
            severity=Severity.HIGH,
            detail="bind address not specified",
        )
    loopback = host in ("127.0.0.1", "::1", "localhost")
    if host in ("0.0.0.0", "::", ""):
        if in_container:
            return Finding(
                check="net.bind",
                status=Status.WARN,
                severity=Severity.MEDIUM,
                detail=(
                    f"control API binds to all interfaces ({host!r}) *inside* the "
                    "container; the real exposure is whatever the host publishes"
                ),
                remediation=(
                    "On the host run `docker port <container>`: it must show "
                    "127.0.0.1, not 0.0.0.0. A container cannot report the host's "
                    "mapping, which is why this is a warning and not a verdict."
                ),
            )
        return Finding(
            check="net.bind",
            status=Status.FAIL,
            severity=Severity.CRITICAL,
            detail=f"control API binds to all interfaces ({host!r})",
            remediation="Bind to 127.0.0.1 and put an authenticating reverse proxy in "
            "front, or keep it on a private network.",
        )
    if not loopback:
        return Finding(
            check="net.bind",
            status=Status.WARN,
            severity=Severity.MEDIUM,
            detail=f"control API binds to {host!r} (not loopback)",
            remediation="Confirm a firewall or authenticating proxy protects this address.",
        )
    return Finding(
        check="net.bind",
        status=Status.PASS,
        severity=Severity.HIGH,
        detail=f"control API bound to {host}",
    )


def _is_local_endpoint(base_url: str) -> bool:
    """True when the URL cannot be reached from outside this host."""
    host = urlsplit(base_url).hostname or ""
    return (
        host in ("localhost", "127.0.0.1", "::1", "0.0.0.0")
        or host.startswith("127.")
        or host.endswith(".local")
    )


def check_provider_config(providers_file: Path | None) -> Finding:
    """Is this process actually wired to a model endpoint — and to a remote one?

    Two questions that previously had no answer anywhere in the report. ``providers: []``
    produced no finding at all, so ``doctor`` printed a clean sheet for a bot that could
    not answer a single message; and a config pointed at a local mock looked identical to
    one pointed at a real vendor. Both are the shape of defect this module exists for: a
    requirement nobody can check is an aspiration.

    An empty list is WARN, not FAIL, on purpose. A host that runs only the panel is a
    legitimate deployment, and a red gate on a fresh install teaches people to ignore the
    gate. High/critical is reserved for "the file is broken", which is always wrong.
    """
    check = "provider.upstream"
    if providers_file is None:
        return Finding(
            check=check,
            status=Status.UNKNOWN,
            severity=Severity.MEDIUM,
            detail="providers config path not supplied to the posture check",
        )

    path = Path(providers_file)
    if not path.is_file():
        return Finding(
            check=check,
            status=Status.WARN,
            severity=Severity.MEDIUM,
            detail=f"{path.name} 不存在：进程不会连接任何上游模型端点",
            remediation="添加一个 Provider，否则机器人收到消息也无法生成回复。",
        )

    try:
        document = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    except (yaml.YAMLError, OSError) as exc:
        return Finding(
            check=check,
            status=Status.FAIL,
            severity=Severity.HIGH,
            detail=f"{path} 无法解析：{exc}",
            remediation="修好 YAML 语法；启动时同样会因为这个错误拒绝加载。",
        )

    providers = document.get("providers") or [] if isinstance(document, dict) else []
    if not isinstance(providers, list) or not providers:
        return Finding(
            check=check,
            status=Status.WARN,
            severity=Severity.MEDIUM,
            detail="providers 为空：进程不连接任何上游模型端点",
            remediation="在面板第 07 页或 config/providers.yaml 添加 Provider。",
        )

    local = [
        str(item.get("id") or "?")
        for item in providers
        if isinstance(item, dict) and _is_local_endpoint(str(item.get("base_url") or ""))
    ]
    if local:
        return Finding(
            check=check,
            status=Status.WARN,
            severity=Severity.MEDIUM,
            detail=(
                f"{len(local)}/{len(providers)} 个 Provider 指向本机端点 "
                f"（{', '.join(local)}）：这不是真实云端"
            ),
            remediation="本地端点只用于开发验证；对外服务前请确认真实上游可达。",
        )

    insecure = [
        str(item.get("id") or "?")
        for item in providers
        if isinstance(item, dict) and str(item.get("base_url") or "").startswith("http://")
    ]
    if insecure:
        return Finding(
            check=check,
            status=Status.WARN,
            severity=Severity.MEDIUM,
            detail=f"{', '.join(insecure)} 使用 http:// 明文传输，且携带 API Key",
            remediation="改用 https:// —— 密钥会随每个请求发送。",
        )

    return Finding(
        check=check,
        status=Status.PASS,
        severity=Severity.HIGH,
        detail=f"已配置 {len(providers)} 个 Provider，均指向远端端点",
    )


async def probe_providers(
    providers_file: Path | None,
    *,
    timeout: float = 15.0,
    client_factory: Callable[..., Any] | None = None,
) -> list[dict[str, Any]]:
    """Ask each endpoint whether it answers at all. **Network I/O — opt-in only.**

    The timeout is generous on purpose. Measured on a real deployment: DNS 0.03 s, TCP
    to `api.deepseek.com` **4.0 s**, TLS and 401 another 1.3 s — so the old 5 s default
    reported a provider that works as `ConnectTimeout`. A probe that calls a slow link
    "unreachable" is worse than no probe, because it sends someone to audit a firewall
    over what is really a routing distance.

    Deliberately not part of :func:`run_posture_checks`: that report is used as a deploy
    gate, and a gate that needs the internet fails for reasons that have nothing to do
    with the deployment. ``doctor --probe`` exists for the moment someone actually wants
    to know whether the cloud is reachable.

    The probe never sends the API key. It calls ``/models`` and treats 401/403 as *proof
    of life* — a server that rejects you is a server that answered, and staying
    credential-free means a stolen debug log contains no secrets.
    """
    if providers_file is None or not Path(providers_file).is_file():
        return []

    import httpx

    try:
        document = yaml.safe_load(Path(providers_file).read_text(encoding="utf-8")) or {}
    except (yaml.YAMLError, OSError):
        return []
    providers = document.get("providers") or [] if isinstance(document, dict) else []
    if not isinstance(providers, list):
        return []

    out: list[dict[str, Any]] = []
    # Injectable so the "a rejection is proof of life" rule can be tested without a
    # listening socket. The live-endpoint test proves the socket; this seam keeps the
    # rule itself testable on a host that intercepts loopback HTTP (CI containers, some
    # corporate images), where a real 401 never arrives.
    open_client = client_factory or httpx.AsyncClient
    async with open_client(timeout=timeout, follow_redirects=True) as client:
        for item in providers:
            if not isinstance(item, dict):
                continue
            base_url = str(item.get("base_url") or "").rstrip("/")
            if not base_url:
                continue
            entry: dict[str, Any] = {
                "id": str(item.get("id") or "?"),
                "base_url": base_url,
                "local": _is_local_endpoint(base_url),
                "reachable": False,
                "status_code": None,
                "error": "",
            }
            try:
                response = await client.get(f"{base_url}/models")
                entry["status_code"] = response.status_code
                entry["reachable"] = response.status_code < 500
            except Exception as exc:  # every failure is reported, none raised
                entry["error"] = f"{type(exc).__name__}: {exc}"
            out.append(entry)
    return out


def _in_container() -> bool:
    """Whether this process runs under a container runtime.

    Split out so :func:`check_bind_address` can ask the same question. Inside a
    container ``0.0.0.0`` is not a choice — a published port targets the container's
    interface, and binding its own loopback would make the mapping point at nothing.
    The exposure boundary there is the *host's* port mapping, which nothing inside the
    container can see.
    """
    if Path("/.dockerenv").exists() or Path("/run/.containerenv").exists():
        return True
    if sys.platform == "win32":
        return False
    try:
        with open("/proc/1/cgroup", encoding="utf-8", errors="replace") as fh:
            content = fh.read()
    except OSError:
        return False
    return any(t in content for t in ("docker", "kubepods", "containerd", "lxc"))


def check_container() -> Finding:
    """Report whether the process is containerised, because the deployment-layer
    mitigations in the docs (read-only rootfs, network policy, seccomp) only exist
    inside a container runtime."""
    if _in_container():
        return Finding(
            check="deploy.container",
            status=Status.PASS,
            severity=Severity.MEDIUM,
            detail="running inside a container runtime",
        )
    return Finding(
        check="deploy.container",
        status=Status.WARN,
        severity=Severity.MEDIUM,
        detail="not running in a container: the deployment-layer controls "
        "(read-only rootfs, network policy, seccomp) are not being applied",
        remediation="Deploy with deploy/docker-compose.yml, which sets read_only, "
        "cap_drop: ALL, no-new-privileges and a non-root user.",
    )


def check_rootfs_readonly() -> Finding:
    """A writable root filesystem lets a compromised plugin or dependency drop a
    persistent payload outside its own directory."""
    if sys.platform == "win32":
        return Finding(
            check="deploy.readonly_rootfs",
            status=Status.UNKNOWN,
            severity=Severity.MEDIUM,
            detail="read-only rootfs is a container concept; not applicable here",
        )
    probe = Path("/usr")
    if not probe.exists():  # pragma: no cover
        return Finding(
            check="deploy.readonly_rootfs",
            status=Status.UNKNOWN,
            severity=Severity.MEDIUM,
            detail="/usr not present",
        )
    if os.access(probe, os.W_OK):
        return Finding(
            check="deploy.readonly_rootfs",
            status=Status.WARN,
            severity=Severity.MEDIUM,
            detail="/usr is writable (root filesystem not read-only)",
            remediation="Set 'read_only: true' in compose and mount explicit tmpfs "
            "for /tmp; the app writes only under /data.",
        )
    return Finding(
        check="deploy.readonly_rootfs",
        status=Status.PASS,
        severity=Severity.MEDIUM,
        detail="root filesystem appears read-only",
    )


def check_isolation_enabled(plugin_manager) -> Finding:
    """Whether plugins actually run in separate processes.

    This check exists because the *previous* iteration shipped a subprocess runner
    with zero call sites. A posture report that does not verify the boundary is
    active would have called that deployment secure.
    """
    supervisor = getattr(getattr(plugin_manager, "loader", None), "supervisor", None)
    if supervisor is None:
        return Finding(
            check="isolation.process",
            status=Status.FAIL,
            severity=Severity.CRITICAL,
            detail="plugins run in the host process (in-process mode)",
            remediation="Build the plugin manager with isolate=True (the default). "
            "In-process plugins share the host's address space, so every capability "
            "check is a speed bump rather than a boundary.",
        )
    health = supervisor.health()
    return Finding(
        check="isolation.process",
        status=Status.PASS,
        severity=Severity.CRITICAL,
        detail=f"process isolation enabled ({len(health)} plugin worker(s) registered)",
    )


def check_single_instance(data_dir: Path | None) -> Finding:
    """Two bot processes sharing a SQLite file will corrupt it or fight over the
    same session locks. Cheap to detect, expensive to debug later."""
    if data_dir is None or not data_dir.exists():
        return Finding(
            check="deploy.single_instance",
            status=Status.UNKNOWN,
            severity=Severity.LOW,
            detail="data directory not present",
        )
    lock = data_dir / "soapbot.pid"
    if not lock.exists():
        return Finding(
            check="deploy.single_instance",
            status=Status.PASS,
            severity=Severity.LOW,
            detail="no competing instance lock",
        )
    try:
        pid = int(lock.read_text(encoding="utf-8").strip() or 0)
    except (ValueError, OSError):
        pid = 0
    if pid and pid != os.getpid():
        alive = True
        if sys.platform != "win32":
            try:
                os.kill(pid, 0)
            except OSError:
                alive = False
        if alive:
            return Finding(
                check="deploy.single_instance",
                status=Status.WARN,
                severity=Severity.MEDIUM,
                detail=f"another instance appears to be running (pid {pid})",
                remediation="Run one bot process per data directory.",
            )
    return Finding(
        check="deploy.single_instance",
        status=Status.PASS,
        severity=Severity.LOW,
        detail="no competing instance",
    )


def run_posture_checks(
    *,
    plugin_manager=None,
    plugin_dir: Path | None = None,
    key_path: Path | None = None,
    data_dir: Path | None = None,
    bind_host: str | None = None,
    providers_file: Path | None = None,
) -> PostureReport:
    """Run every check and return the report. Never raises: a failing check is a
    finding, not an exception, so one broken probe cannot hide the other nine."""
    report = PostureReport()
    probes = [
        lambda: check_privilege(),
        lambda: check_isolation_enabled(plugin_manager) if plugin_manager else Finding(
            check="isolation.process",
            status=Status.UNKNOWN,
            severity=Severity.CRITICAL,
            detail="plugin manager not supplied to the posture check",
        ),
        check_secrets_in_env,
        lambda: check_provider_config(providers_file),
        lambda: check_bind_address(bind_host, in_container=_in_container()),
        lambda: check_key_file_mode(key_path),
        lambda: check_plugin_dir_writable(plugin_dir),
        check_container,
        check_rootfs_readonly,
        lambda: check_single_instance(data_dir),
    ]
    for probe in probes:
        try:
            report.findings.append(probe())
        except Exception as exc:  # pragma: no cover - defensive
            report.findings.append(
                Finding(
                    check="posture.probe",
                    status=Status.UNKNOWN,
                    severity=Severity.LOW,
                    detail=f"probe raised {type(exc).__name__}",
                )
            )
    return report
