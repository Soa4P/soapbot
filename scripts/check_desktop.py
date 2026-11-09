"""Static gate for the Tauri desktop shell.

Why a static gate and not a build
---------------------------------
`cargo check` needs the Rust toolchain and a WebView2 SDK; CI runs it in its own job, but
`make check` has to work on a machine that has neither. What is left is the class of
defect that a successful build would not catch anyway, because it is a *policy* mistake
rather than a compile error:

1. **CSP with a wildcard.** `connect-src *` type-checks, builds, and quietly turns the
   shell into a browser that can talk to any origin. The whole reason the shell exists is
   that the panel is local.
2. **A remote resource.** A `<script src="https://…">` or a `frontendDist` pointing at a
   URL means the shell renders code nobody in this repository reviewed.
3. **No single-instance plugin.** Without it, launching twice gives two windows on one
   backend, and the second one's tray icon silently replaces the first.
4. **No health probe.** The shell then shows the webview's connection error, which reads
   as "the app is broken" instead of "the service is not running".
5. **A missing icon.** Tauri fails at bundle time with an error that does not name the
   file, so this reports it in one line instead.
6. **An unguarded spawn.** The shell may own the backend's lifecycle for a bare desktop
   install, but only through `spawn_decision` (probe first) and `taskkill /T` (the
   onefile bootloader forks, so killing the direct child leaves the server holding the
   port). A `Command::new` anywhere else is a second supervisor waiting to race.

Every finding prints the file and the line it relied on. Exit code is non-zero when any
check fails; there is no warning tier, because each of these is a one-line fix.
"""

from __future__ import annotations

import json
import re
import sys
from dataclasses import dataclass
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DESKTOP = ROOT / "desktop"
CONF = DESKTOP / "src-tauri" / "tauri.conf.json"
CARGO = DESKTOP / "src-tauri" / "Cargo.toml"
MAIN_RS = DESKTOP / "src-tauri" / "src" / "main.rs"
UI = DESKTOP / "ui"
ICONS = DESKTOP / "src-tauri" / "icons"

#: The only origin the shell may reach. Kept next to the CSP check so a port change is a
#: one-line edit in two places rather than a silent mismatch.
PANEL_ORIGIN = "http://127.0.0.1:6185"

#: Directives that must never carry a wildcard. `img-src data:` is allowed because the
#: offline page has no images; a `*` anywhere here means the CSP is decorative.
WILDCARD_FORBIDDEN = ("default-src", "connect-src", "script-src", "style-src", "img-src")

REMOTE = re.compile(r"https?://(?!127\.0\.0\.1[:/]|localhost[:/])[a-z0-9.-]+", re.I)


@dataclass
class Finding:
    ok: bool
    code: str
    detail: str
    evidence: str = ""


def _text(path: Path) -> str:
    return path.read_text(encoding="utf-8-sig") if path.is_file() else ""


def _line_of(text: str, needle: str) -> str:
    for number, line in enumerate(text.splitlines(), 1):
        if needle in line:
            return f"line {number}: {line.strip()[:110]}"
    return f"missing {needle!r}"


def _rel(path: Path) -> str:
    """Path relative to the repo, or absolute when it is outside it.

    ``tests/test_desktop_config.py`` points these constants at a temporary copy, and a
    bare ``relative_to`` raises there — a checker that crashes on its own fixture is not
    a checker.
    """
    try:
        return str(path.relative_to(ROOT))
    except ValueError:
        return str(path)


def check_conf_exists() -> Finding:
    if not CONF.is_file():
        return Finding(False, "conf.missing", f"{_rel(CONF)} 不存在")
    try:
        json.loads(_text(CONF))
    except json.JSONDecodeError as exc:
        return Finding(False, "conf.json", f"tauri.conf.json 不是合法 JSON：{exc}")
    return Finding(True, "conf.exists", "tauri.conf.json 存在且可解析")


def _csp() -> str:
    try:
        conf = json.loads(_text(CONF))
    except json.JSONDecodeError:
        return ""
    return str(conf.get("app", {}).get("security", {}).get("csp", ""))


def check_csp() -> list[Finding]:
    csp = _csp()
    if not csp:
        return [Finding(False, "csp.missing", "app.security.csp 为空，等于没有策略")]

    findings: list[Finding] = []
    for directive in WILDCARD_FORBIDDEN:
        match = re.search(rf"{directive}\s+([^;]+)", csp)
        if not match:
            findings.append(
                Finding(False, "csp.directive", f"CSP 缺少 {directive}", _line_of(_text(CONF), "csp"))
            )
            continue
        values = match.group(1).split()
        # `'self'` and `data:` are fine. A bare `*` or a scheme wildcard (`https:`) is not:
        # both make the directive allow every origin.
        bad = [v for v in values if v == "*" or (v.endswith(":") and not v.startswith("data:"))]
        findings.append(
            Finding(
                not bad,
                "csp.wildcard",
                f"{directive} 不得通配" if bad else f"{directive} 无通配",
                f"{directive} {' '.join(values)}",
            )
        )

    connect = re.search(r"connect-src\s+([^;]+)", csp)
    allowed = connect.group(1).split() if connect else []
    findings.append(
        Finding(
            PANEL_ORIGIN in allowed,
            "csp.connect",
            f"connect-src 必须精确包含 {PANEL_ORIGIN}",
            f"connect-src {' '.join(allowed) or '(absent)'}",
        )
    )
    findings.append(
        Finding(
            "frame-ancestors 'none'" in csp,
            "csp.frame",
            "CSP 必须禁止被嵌入（frame-ancestors 'none'）",
            _line_of(_text(CONF), "frame-ancestors"),
        )
    )
    return findings


def check_no_remote() -> Finding:
    """No remote origin anywhere in the shell's own assets or config.

    ``$schema`` is exempt: it is an editor hint that no runtime ever fetches, and
    flagging it would make the only finding on a correct config a false positive — which
    is how a gate gets ignored.
    """
    hits: list[str] = []
    for path in [CONF, *(sorted(UI.glob("*")) if UI.is_dir() else [])]:
        if not path.is_file():
            continue
        for number, line in enumerate(_text(path).splitlines(), 1):
            if '"$schema"' in line:
                continue
            if REMOTE.search(line):
                hits.append(f"{_rel(path)}:{number} {line.strip()[:90]}")
    return Finding(
        not hits,
        "remote.assets",
        "桌面壳不得加载远程资源" if hits else "桌面壳只引用本机资源",
        "; ".join(hits) if hits else f"{CONF.name} 与 {UI.name}/ 无远程域名",
    )


def check_single_instance() -> list[Finding]:
    cargo = _text(CARGO)
    main = _text(MAIN_RS)
    return [
        Finding(
            "tauri-plugin-single-instance" in cargo,
            "single.dependency",
            "Cargo.toml 必须声明 tauri-plugin-single-instance",
            _line_of(cargo, "single-instance"),
        ),
        Finding(
            "tauri_plugin_single_instance::init" in main,
            "single.register",
            "main.rs 必须注册单实例插件",
            _line_of(main, "single_instance"),
        ),
    ]


def check_probe() -> Finding:
    main_js = _text(UI / "main.js")
    has_probe = "/api/health" in main_js and "AbortController" in main_js
    return Finding(
        has_probe,
        "probe.health",
        "壳页面必须探测 /api/health 并带超时" if has_probe else "缺少健康探测或超时",
        _line_of(main_js, "/api/health") if has_probe else "ui/main.js 未探测",
    )


#: `Command::new` is allowed only inside these two functions. Anywhere else is a spawn
#: path nobody reviews, which is how the original "no spawn at all" rule came to exist.
_SPAWN_FUNCTIONS = ("start_sidecar", "stop_backend")


def _spawn_calls_outside_allowed(source: str) -> list[str]:
    """`Command::new` sites, tagged with the function that encloses them.

    Line-based on purpose: a real parser would be a dependency for one file this small,
    and the approximation's failure mode is a false positive that adding the call to the
    allowed pair fixes.
    """
    offenders: list[str] = []
    current = "<top>"
    for line in source.splitlines():
        stripped = line.strip()
        if stripped.startswith("fn "):
            current = stripped[3:].split("(", 1)[0].strip()
        if "Command::new" in line and current not in _SPAWN_FUNCTIONS:
            offenders.append(f"{current}: {stripped[:48]}")
    return offenders


def check_no_spawn() -> Finding:
    """The shell may start the backend, but only as a guarded sidecar.

    The old rule banned `Command::new` outright. That was right for a supervised install
    — the scheduled task or systemd unit already owns the process, and a second backend
    either fails to bind or wins the race and leaves the supervised copy unreachable —
    and wrong for the desktop bundle, where nothing else would ever start it.

    Removing the ban would let the race back in; keeping it would force the spawn through
    an unreviewed path. So the rule now constrains the *shape* of the lifecycle: a pure
    `spawn_decision` decides from "is the port open" and "is the binary there", spawning
    and killing live only in their two functions, the Windows kill uses `taskkill /T`
    because the onefile bootloader forks, and running the source tree stays forbidden.
    """
    main = _text(MAIN_RS)
    problems = sidecar_rule_problems(main)
    return Finding(
        not problems,
        "shell.sidecar-guarded",
        "；".join(problems) if problems else "先探测、只在受控函数内启动、退出杀进程树",
        _line_of(main, "fn spawn_decision")
        if "fn spawn_decision" in main
        else "main.rs 未找到 spawn_decision",
    )


def sidecar_rule_problems(source: str) -> list[str]:
    """Pure rule body, so a reverse test can feed it a bad shell without a temp file."""
    problems: list[str] = []

    if "fn spawn_decision" not in source:
        problems.append("缺少探测优先的 spawn_decision")
    if "SpawnDecision::AlreadyRunning" not in source:
        problems.append("没有「端口已监听则不启动」分支")
    if "python -m soapbot" in source:
        problems.append("不得直接运行源码树")
    if "taskkill" not in source:
        problems.append("Windows 需用 taskkill /T 关闭进程树")

    stray = _spawn_calls_outside_allowed(source)
    if stray:
        problems.append("Command::new 出现在未受控函数 " + "; ".join(stray))
    return problems


def check_icons() -> Finding:
    try:
        conf = json.loads(_text(CONF))
    except json.JSONDecodeError:
        return Finding(False, "icons.conf", "读不到 bundle.icon")
    listed = conf.get("bundle", {}).get("icon", [])
    missing = [name for name in listed if not (DESKTOP / "src-tauri" / name).is_file()]
    return Finding(
        bool(listed) and not missing,
        "icons.present",
        "bundle.icon 列出的图标必须存在" if missing else "图标齐备",
        f"缺少 {missing}" if missing else f"{len(listed)} 个图标",
    )


def check_tray() -> Finding:
    main = _text(MAIN_RS)
    ok = "TrayIconBuilder" in main and "tray-icon" in _text(CARGO)
    return Finding(
        ok,
        "tray.registered",
        "托盘需要 Cargo feature 与 TrayIconBuilder 同时存在",
        _line_of(main, "TrayIconBuilder"),
    )


def main(argv: list[str]) -> int:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")

    findings: list[Finding] = [check_conf_exists()]
    findings.extend(check_csp())
    findings.append(check_no_remote())
    findings.extend(check_single_instance())
    findings.append(check_probe())
    findings.append(check_no_spawn())
    findings.append(check_icons())
    findings.append(check_tray())

    failed = [f for f in findings if not f.ok]
    for finding in findings:
        mark = "ok  " if finding.ok else "FAIL"
        print(f"[{mark}] {finding.code}: {finding.detail}")
        if finding.evidence:
            print(f"        {finding.evidence}")

    print(f"\n{len(findings) - len(failed)}/{len(findings)} 项通过")
    if failed:
        print("桌面壳门禁不合格。")
        return 1
    print("桌面壳门禁通过。")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
