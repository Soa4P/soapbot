"""Command line entry point: ``soapbot start`` / ``setup`` / ``token`` / ``doctor``.

``setup`` lives in :mod:`soapbot.cli_setup`: this module stays a parser plus delegation,
so the wizard can be tested without going through argv.
"""

from __future__ import annotations

import argparse
import sys

from soapbot import __version__


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="soapbot", description="QQ group chat AI bot")
    sub = parser.add_subparsers(dest="cmd")

    p_start = sub.add_parser("start", help="start the bot service")
    p_start.add_argument("--host", default=None)
    p_start.add_argument("--port", type=int, default=None)
    p_start.add_argument("--reload", action="store_true")

    sub.add_parser("version", help="print version")

    sub.add_parser("token", help="print the one-time bootstrap login token")

    p_doctor = sub.add_parser(
        "doctor", help="check deployment security posture"
    )
    p_doctor.add_argument(
        "--json", action="store_true", help="machine-readable output"
    )
    p_doctor.add_argument(
        "--strict",
        action="store_true",
        help="exit non-zero on any high/critical failure (for CI/deploy gates)",
    )
    p_doctor.add_argument(
        "--host", default=None, help="bind address to check (defaults to settings)"
    )
    p_doctor.add_argument(
        "--probe",
        action="store_true",
        help="also send one request to each provider base_url (network I/O)",
    )

    p_setup = sub.add_parser(
        "setup",
        help="configure a provider and a QQ adapter from the terminal (no browser needed)",
    )
    p_setup.add_argument("--provider-id", default="")
    p_setup.add_argument("--base-url", default="", help="e.g. https://api.deepseek.com/v1")
    p_setup.add_argument("--model", default="")
    p_setup.add_argument(
        "--api-key-env",
        default="",
        help="name of the environment variable holding the key (preferred: nothing secret on disk)",
    )
    p_setup.add_argument(
        "--api-key",
        default="",
        help="literal key; written to the file, so prefer --api-key-env",
    )
    p_setup.add_argument("--kind", default="onebot11")
    p_setup.add_argument("--mode", default="", help="forward or reverse")
    p_setup.add_argument("--ws-url", default="", help="forward mode: ws://host:port")
    p_setup.add_argument("--host", default="", help="reverse mode: listen address")
    p_setup.add_argument("--port", type=int, default=None, help="reverse mode: listen port")
    p_setup.add_argument("--account-id", default="")
    p_setup.add_argument("--access-token-env", default="")
    p_setup.add_argument("--access-token", default="")
    p_setup.add_argument("--skip-provider", action="store_true")
    p_setup.add_argument("--skip-adapter", action="store_true")
    p_setup.add_argument(
        "--non-interactive",
        action="store_true",
        help="never prompt; fail if a required value is missing (for Ansible/CI)",
    )

    args = parser.parse_args(argv)

    if args.cmd == "version" or args.cmd is None:
        print(f"soapbot {__version__}")
        return 0

    if args.cmd == "token":
        return _run_token()

    if args.cmd == "doctor":
        return _run_doctor(args)

    if args.cmd == "setup":
        from soapbot.cli_setup import run as run_setup

        return run_setup(args)

    if args.cmd == "start":
        import uvicorn

        from soapbot.config import settings

        uvicorn.run(
            "soapbot.app:app",
            host=args.host or settings.host,
            port=args.port or settings.port,
            reload=args.reload,
        )
        return 0

    parser.print_help()
    return 1


def _run_token() -> int:
    """Print the bootstrap token from ``<data>/init_token.txt``.

    ``.env.example`` promised this command ("``soapbot token`` reprints it") while the
    parser had no such subcommand, so the one documented recovery path for a lost login
    token was a dead end. Adding the command is the smaller change than rewriting the
    documentation, and the file already exists — it is written mode 0600 on first start.

    The file is a *bootstrap* credential, not a session token, and it is single-use:
    once redeemed, the in-memory copy is marked consumed and the file is left behind,
    stale. So this command prints the value **and** says which state it is in, rather
    than letting someone paste a dead token into the login form and conclude the
    service is broken. Detecting "already consumed" reliably is not possible from
    outside the running process (the flag is in memory), so the honest thing is to
    state that the file may be stale and how to reset it.
    """
    from soapbot.config import settings

    # Match ``doctor``: the console encoding on Windows is cp936 by default, and a
    # Chinese hint written to stderr with ``errors="strict"`` either raises or renders
    # as mojibake — which looks like the command is broken rather than the terminal.
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
        sys.stderr.reconfigure(encoding="utf-8", errors="replace")

    path = settings.data_dir / "init_token.txt"
    if not path.is_file():
        print(
            f"没有找到引导令牌文件：{path}\n"
            "\n"
            "可能的原因：\n"
            "  · 服务还没启动过（该文件在首次启动时生成）\n"
            "  · 已通过 SOAPBOT_INIT_TOKEN 自行指定了令牌，此时不会写文件\n"
            "  · 使用了不同的 SOAPBOT_DATA_DIR\n",
            file=sys.stderr,
        )
        return 1

    try:
        token = path.read_text(encoding="utf-8").strip()
    except OSError as exc:
        print(f"无法读取 {path}：{exc}", file=sys.stderr)
        return 1

    if not token:
        print(f"{path} 是空文件；删除它并重启服务可重新生成。", file=sys.stderr)
        return 1

    print(token)
    print(
        "\n"
        "这是一次性引导令牌，用于换取访问令牌：\n"
        "  curl -X POST http://<host>:<port>/api/auth/login \\\n"
        '    -H "Content-Type: application/json" \\\n'
        f'    -d \'{{"init_token": "{token[:4]}…"}}\'\n'
        "\n"
        "如果登录返回 401，说明该令牌已被消费过（文件不会自动删除，仍留在磁盘上）。\n"
        "重置方法：删除该文件并重启服务。",
        file=sys.stderr,
    )
    return 0


def _run_doctor(args) -> int:
    """Print the deployment posture report.

    Exit code is 0 unless ``--strict`` is given and something failed at high or
    critical severity. Defaulting to 0 keeps ``doctor`` usable as a "show me my
    posture" command (which people run while fixing things) without making the
    deploy gate the same command — those want different ergonomics, so they get
    different flags rather than one behaviour that is wrong for one of them.
    """
    import json

    from soapbot.config import settings
    from soapbot.security.posture import run_posture_checks

    # Build a *real* plugin manager so the isolation check inspects the actual
    # configuration rather than guessing. Reporting "unknown" for the single most
    # important control would make the whole report untrustworthy — and this check
    # exists precisely because the previous isolation layer was a module nobody
    # called.
    manager = None
    try:
        from soapbot.core.builder import build_plugin_manager

        manager = build_plugin_manager(
            settings.data_dir / "plugins", allow_untrusted=False
        )
    except Exception:
        manager = None

    # Inspect the key file the process actually uses. With the recommended
    # SOAPBOT_MASTER_KEY_FILE deployment, the key lives at the mounted path, not at
    # data/secret.key — checking the wrong path reported "key file not found" and,
    # worse, left the real file's permissions unexamined.
    key_path = settings.master_key_file or (settings.data_dir / "secret.key")

    report = run_posture_checks(
        plugin_manager=manager,
        plugin_dir=settings.data_dir / "plugins",
        key_path=key_path,
        data_dir=settings.data_dir,
        bind_host=args.host or settings.host,
        providers_file=settings.providers_file,
        # Named explicitly: "saved in the panel but gone after restart" is almost always
        # this directory being read-only or not the one the process reads.
        config_dir=settings.config_dir,
    )
    if manager is not None and getattr(manager, "supervisor", None) is not None:
        # Nothing was loaded by this probe, so shut the supervisor down cleanly.
        # Failure here is not worth reporting: the probe already produced its verdict
        # and a stuck supervisor during exit must not turn a passing doctor into a
        # traceback.
        import asyncio
        import contextlib

        with contextlib.suppress(Exception):
            # ``asyncio.run`` rather than ``get_event_loop().run_until_complete``:
            # the latter is deprecated when no loop exists and silently creates one,
            # which is why ``doctor`` printed a DeprecationWarning on 3.12+.
            asyncio.run(manager.supervisor.stop_all())

    # Opt-in, because this is the only part of the report that needs the network: a
    # deploy gate that fails when an upstream has a bad afternoon is a gate people
    # disable. ``--probe`` is for the moment someone actually wants the answer.
    probes: list[dict] = []
    if getattr(args, "probe", False):
        import asyncio as _asyncio

        from soapbot.security.posture import probe_providers

        probes = _asyncio.run(probe_providers(settings.providers_file))

    if args.json:
        print(
            json.dumps(
                {
                    "ok": report.ok,
                    "summary": report.summary(),
                    "findings": [f.to_dict() for f in report.findings],
                    "probe": probes,
                },
                indent=2,
                ensure_ascii=False,
            )
        )
    else:
        import sys as _sys

        _sys.stdout.reconfigure(encoding="utf-8", errors="replace")
        symbols = {
            "pass": "[ok]  ",
            "fail": "[FAIL]",
            "warn": "[warn]",
            "unknown": "[?]   ",
        }
        print(f"soapbot {__version__} — deployment posture\n")
        for f in report.findings:
            print(f"{symbols[str(f.status)]} {f.check}  ({f.severity})")
            print(f"        {f.detail}")
            if f.remediation:
                print(f"        -> {f.remediation}")
        print()
        verdict = "PASS" if report.ok else "FAIL"
        print(f"verdict: {verdict}")
        if not report.ok:
            print("critical/high issues must be fixed before exposing this service.")

        if probes:
            print()
            print("upstream probe (no credentials sent):")
            for item in probes:
                mark = "[ok]  " if item.get("reachable") else "[FAIL]"
                where = "local" if item.get("local") else "remote"
                print(f"{mark} {item.get('id')}  ({where})  {item.get('base_url')}")
                if item.get("status_code") is not None:
                    print(f"        HTTP {item['status_code']}")
                if item.get("error"):
                    print(f"        {item['error']}")

    return 0 if (report.ok or not args.strict) else 2


if __name__ == "__main__":
    sys.exit(main())
