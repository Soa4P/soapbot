"""One command from nothing to a running panel — on Windows and on Linux.

Why a Python installer instead of two shell scripts: the earlier ``install.sh`` only spoke
systemd and bash, which quietly left Windows as a second-class target — the one people
actually first try this on — and made every future fix a coin toss between two copies of
the same logic with different bugs. Both platforms now run *this file*, so a fix made for
one is made for both, and the part that genuinely differs (how something survives logout)
is one branch at the end instead of a whole separate script.

It is deliberately boring: create the environment, install, ensure the built UI exists,
write absolute paths into ``.env``, hand the panel to whatever supervises processes on
this platform, then poll ``/api/health`` until it answers. Idempotent by construction —
running it twice upgrades rather than duplicating, because the second run of an installer
is where setups usually get destroyed.

    python scripts/bootstrap.py                 # install here (or into --dir)
    python scripts/bootstrap.py --autostart     # also survive logoff / reboot
    python scripts/bootstrap.py --check         # audit an existing install instead

It cannot do the two things that need credentials it does not have: fetch a model API key,
and log a QQ account in on the protocol side. Stopping there is the honest answer.
"""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path
from typing import NoReturn

MIN_PYTHON = (3, 12)
DEFAULT_PORT = 6185
DEFAULT_HOST = "127.0.0.1"
UNIT_MARKER = "# Managed by soapbot bootstrap.py — this installer rewrites it, nothing else does"
WINDOWS_TASK = "soapbot-panel"

# Written into .env so nothing downstream re-derives them. Relative paths are the trap:
# a service started by systemd or by Task Scheduler does not run from the checkout, so a
# relative data directory silently creates a second database beside the unit file and the
# panel then looks mysteriously empty after every restart.
ENV_KEYS = (
    "SOAPBOT_HOST",
    "SOAPBOT_PORT",
    "SOAPBOT_DATA_DIR",
    "SOAPBOT_CONFIG_DIR",
    "SOAPBOT_ENV_FILE",
)


def say(step: str, message: str) -> None:
    print(f"\n[{step}] {message}")


def die(message: str) -> NoReturn:
    print(f"\n  FAILED: {message}", file=sys.stderr)
    raise SystemExit(1)


def run(*args: str, cwd: Path | None = None, check: bool = True) -> subprocess.CompletedProcess[str]:
    """Run and stream nothing: every command here either works or is explained."""
    printable = " ".join(args)
    print(f"      {printable[:120]}")
    result = subprocess.run(
        [str(a) for a in args],
        cwd=str(cwd) if cwd else None,
        capture_output=True,
        text=True,
    )
    if check and result.returncode != 0:
        tail = (result.stderr or result.stdout or "").strip().splitlines()[-15:]
        die(f"{args[0]} exited {result.returncode}\n      " + "\n      ".join(tail))
    return result


def which(name: str) -> str | None:
    from shutil import which as _which

    return _which(name)


def ensure_source(args: argparse.Namespace) -> Path:
    target = Path(args.dir).expanduser().resolve() if args.dir else Path.cwd().resolve()

    if args.repo and not (target / ".git").exists():
        if not which("git"):
            die("git is required to clone; install it or drop --repo to install this checkout")
        target.mkdir(parents=True, exist_ok=True)
        run("git", "clone", "--quiet", "--branch", args.branch, args.repo, str(target))
    elif (target / ".git").exists():
        # A second run is an upgrade. `git pull` can fail offline or on local commits, and
        # neither is a reason to abandon an install that already has a working tree.
        pull = run("git", "-C", str(target), "pull", "--ff-only", check=False)
        if pull.returncode != 0:
            print("      (git pull skipped: using the checkout already on disk)")
    elif not (target / "pyproject.toml").exists():
        die(f"{target} is not a soapbot checkout and --repo was not given")

    return target


def _check_interpreter_can_venv() -> None:
    """Debian ships ``python3`` without ``ensurepip``, so ``-m venv`` fails with a message
    telling you to install a package — after the installer has already printed three
    reassuring steps. Saying it first is the difference between a fix and a mystery."""
    probe = subprocess.run(
        [sys.executable, "-c", "import ensurepip"], capture_output=True, text=True
    )
    if probe.returncode != 0:
        die(
            f"{sys.executable} cannot create virtual environments (ensurepip missing).\n"
            "      Fix: apt install python3-venv   (Fedora/RHEL: python3-pip python3-devel),\n"
            "      then run this installer again."
        )


def ensure_venv(root: Path, extras: list[str]) -> Path:
    venv = root / ".venv"
    # Windows puts the interpreter at Scripts/python.exe, POSIX at bin/python. Reusing the
    # caller's interpreter is tempting but wrong: an installer run from a system Python or
    # from inside another venv would install the project somewhere it is never used from.
    python = venv / ("Scripts" if os.name == "nt" else "bin") / (
        "python.exe" if os.name == "nt" else "python"
    )
    if not python.exists():
        _check_interpreter_can_venv()
        say("2/6", f"creating the virtual environment in {venv}")
        run(sys.executable, "-m", "venv", str(venv))

    say("3/6", "installing the project (editable, so updates are a git pull away)")
    run(str(python), "-m", "pip", "install", "--quiet", "--upgrade", "pip")
    # `-e` rather than a wheel: the panel reads git-tracked configuration, so "upgrade"
    # must stay a `git pull` with no reinstall step to forget.
    requirement = f".[{','.join(extras)}]" if extras else "."
    run(str(python), "-m", "pip", "install", "--quiet", "-e", requirement, cwd=root)
    return python


def ensure_ui(root: Path) -> None:
    say("4/6", "checking the web panel assets")
    dist = root / "src" / "soapbot" / "webui" / "dist" / "index.html"
    if dist.exists():
        print("      built assets are present")
        return

    # The built assets are committed, so this only fires for someone building from a clean
    # tree. Node is optional precisely because they are committed; when neither exists the
    # message names the missing thing instead of letting the panel open blank.
    if not (which("npm") and (root / "webui" / "package.json").exists()):
        die(
            "no built panel and no npm: install Node.js 20+ and re-run, "
            "or install from a release that ships src/soapbot/webui/dist"
        )
    run("npm", "install", "--no-audit", "--no-fund", cwd=root / "webui")
    run("npm", "run", "build", cwd=root / "webui")


def ensure_env(root: Path, python: Path, host: str, port: int) -> Path:
    say("5/6", "writing configuration")
    env_path = root / ".env"
    if not env_path.exists() and (root / ".env.example").exists():
        env_path.write_text(
            (root / ".env.example").read_text(encoding="utf-8"), encoding="utf-8"
        )
    data_dir = root / "data"
    config_dir = root / "config"
    data_dir.mkdir(exist_ok=True)
    config_dir.mkdir(exist_ok=True)

    wanted = {
        "SOAPBOT_HOST": host,
        "SOAPBOT_PORT": str(port),
        "SOAPBOT_DATA_DIR": str(data_dir),
        # SOAPBOT_CONFIG_DIR is deliberately absent: pointing it at the checkout's config/
        # makes the *template* the thing being edited, so a `git pull` can overwrite what
        # someone configured. Left unset, the app seeds that template once into its own
        # writable directory and edits live there afterwards.
        "SOAPBOT_ENV_FILE": str(env_path),
    }
    lines = env_path.read_text(encoding="utf-8").splitlines() if env_path.exists() else []
    out: list[str] = []
    seen: set[str] = set()
    for line in lines:
        key = line.split("=", 1)[0].strip()
        if key in wanted:
            out.append(f"{key}={wanted[key]}")
            seen.add(key)
        else:
            out.append(line)
    for key, value in wanted.items():
        if key not in seen:
            out.append(f"{key}={value}")
    env_path.write_text("\n".join(out) + "\n", encoding="utf-8")
    print(f"      {env_path}")
    return env_path


def python_in(root: Path) -> Path:
    return root / ".venv" / ("Scripts" if os.name == "nt" else "bin") / (
        "python.exe" if os.name == "nt" else "python"
    )


def health_ok(port: int, host: str = "127.0.0.1", timeout: float = 1.0) -> bool:
    try:
        with urllib.request.urlopen(
            f"http://{host}:{port}/api/health", timeout=timeout
        ) as response:
            payload = json.loads(response.read().decode("utf-8"))
    except (urllib.error.URLError, TimeoutError, ValueError, OSError):
        return False
    return payload.get("status") == "ok"


def start_background(root: Path, python: Path, log: Path) -> None:
    """Detach the panel so this installer can exit, on both platforms."""
    log.parent.mkdir(parents=True, exist_ok=True)
    handle = log.open("a", encoding="utf-8")
    popen_kwargs: dict[str, object] = {"stdout": handle, "stderr": handle, "cwd": str(root)}
    if os.name == "nt":
        # DETACHED_PROCESS keeps it alive when the installer's console closes; a plain
        # Popen here produces a panel that dies with the window that launched it.
        popen_kwargs["creationflags"] = (
            subprocess.DETACHED_PROCESS | subprocess.CREATE_NEW_PROCESS_GROUP  # type: ignore[attr-defined]
        )
    else:
        popen_kwargs["start_new_session"] = True
    subprocess.Popen([str(python), "-m", "soapbot.cli", "start"], **popen_kwargs)  # type: ignore[arg-type]


def service_user(root: Path) -> tuple[str, str] | None:
    """A service account, so an install does not create the failure `doctor` warns about.

    The unit used to omit ``User=``, which on a systemd box means root — the exact
    "process runs as uid 0" critical finding this project's own posture check fails on.
    Creating an unprivileged account is the installer's job, not documentation the
    operator has to read.
    """
    if os.name == "nt" or not which("useradd"):
        return None

    name = "soapbot"
    exists = subprocess.run(["id", name], capture_output=True, text=True)
    if exists.returncode != 0:
        created = subprocess.run(
            [
                "useradd",
                "--system",
                "--no-create-home",
                "--shell",
                "/usr/sbin/nologin",
                name,
            ],
            capture_output=True,
            text=True,
        )
        if created.returncode != 0:
            # Not root, most likely — say so and let the unit be a user unit instead.
            print(f"      could not create {name}: {(created.stderr or '').strip()[:120]}")
            return None

    # The service writes here (SQLite, config, the .env the panel saves into), so handing
    # the account a directory it cannot write is a service that fails on first save.
    for target in (root / "data", root / "config"):
        subprocess.run(
            ["chown", "-R", f"{name}:{name}", str(target)], capture_output=True, text=True
        )
    env_file = root / ".env"
    if env_file.exists():
        subprocess.run(["chown", f"{name}:{name}", str(env_file)], capture_output=True, text=True)
        subprocess.run(["chmod", "0640", str(env_file)], capture_output=True, text=True)
    return name, name


def install_service(
    root: Path, python: Path, env_path: Path, autostart: bool, unit: str
) -> str:
    """Hand supervision to the platform's own mechanism. Returns a human sentence.

    Refusing to overwrite an existing unit is not politeness: a real host can already have
    one under the same obvious name from an earlier deployment, and replacing it silently
    would point somebody's service at a new directory while their data stayed behind. A
    unit that does not carry our marker is somebody else's file.
    """
    say("6/6", "handing the panel to the platform supervisor")

    if os.name == "nt":
        if not autostart:
            return (
                "Windows: start it by double-clicking start-panel.bat "
                "(or re-run this script with --autostart to add a logon task)."
            )
        task = f'"{python}" -m soapbot.cli start'
        created = subprocess.run(
            [
                "schtasks",
                "/Create",
                "/F",
                "/TN",
                unit,
                "/SC",
                "ONLOGON",
                "/TR",
                task,
            ],
            cwd=str(root),
            capture_output=True,
            text=True,
        )
        if created.returncode == 0:
            subprocess.run(["schtasks", "/Run", "/TN", unit], capture_output=True, text=True)
            return f"Windows: scheduled task '{unit}' runs at logon; started now."
        detail = (created.stderr or created.stdout or "").strip().splitlines()[-3:]
        return "Windows: could not register the logon task:\n      " + "\n      ".join(detail)

    if which("systemctl"):
        existing = Path(f"/etc/systemd/system/{unit}.service")
        if (
            existing.exists()
            and UNIT_MARKER not in existing.read_text(encoding="utf-8", errors="replace")
        ):
            return (
                f"Linux: {existing} already exists and was not written by this installer, "
                "so it was left alone. Use --unit <name> for a second instance, or move that "
                "file aside if it belongs to an old deployment you are replacing."
            )
        unit_path = existing
        account = service_user(root)
        run_as = f"User={account[0]}\nGroup={account[1]}" if account else "# running as the invoking user"
        if account:
            print(f"      service account: {account[0]}")
        contents = f"""{UNIT_MARKER}
[Unit]
Description=soapbot panel
After=network-online.target
Wants=network-online.target

[Service]
Type=simple
WorkingDirectory={root}
Environment=PYTHONUNBUFFERED=1
EnvironmentFile={env_path}
ExecStart={python} -m soapbot.cli start
Restart=always
RestartSec=5
{run_as}

[Install]
WantedBy=multi-user.target
"""
        wrote = subprocess.run(
            ["tee", str(unit_path)], input=contents, capture_output=True, text=True
        )
        enabled = True
        if wrote.returncode != 0:
            # Not root, most likely. A per-user unit is the honest fallback: it survives a
            # logout only with lingering enabled, which is exactly what we then say.
            user_unit = Path.home() / ".config" / "systemd" / "user"
            user_unit.mkdir(parents=True, exist_ok=True)
            (user_unit / f"{unit}.service").write_text(contents, encoding="utf-8")
            subprocess.run(
                ["systemctl", "--user", "daemon-reload"], capture_output=True, text=True
            )
            enabled = (
                subprocess.run(
                    ["systemctl", "--user", "enable", "--now", unit],
                    capture_output=True,
                    text=True,
                ).returncode
                == 0
            )
            return (
                f"Linux: user unit written to {user_unit}/{unit}.service"
                + ("" if enabled else f" — start it with: systemctl --user start {unit}")
                + "\n      Note: a user unit stops when you log out unless lingering is on: "
                "loginctl enable-linger $USER"
            )
        subprocess.run(
            ["systemctl", "daemon-reload"], capture_output=True, text=True
        )
        result = subprocess.run(
            ["systemctl", "enable", "--now", unit], capture_output=True, text=True
        )
        if result.returncode != 0:
            detail = (result.stderr or "").strip().splitlines()[-3:]
            return "Linux: unit wrote but would not start:\n      " + "\n      ".join(detail)
        return f"Linux: systemd unit {unit}.service enabled and running."

    return (
        "Linux: no systemd here. Start it with "
        f"'{python} -m soapbot.cli start', or put the Installer behind supervisor/openrc."
    )


def check_only(root: Path, port: int) -> int:
    """`--check`: audit an existing install without changing it."""
    python = python_in(root)
    interpreter = str(python) if python.exists() else sys.executable
    say("check", f"python {interpreter}")
    run(interpreter, "-m", "soapbot.cli", "doctor", cwd=root, check=False)
    say("check", f"http://127.0.0.1:{port}/api/health")
    ok = health_ok(port)
    print("      ok" if ok else "      not answering — is the panel running?")
    return 0 if ok else 1


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Install (or upgrade) soapbot on this machine, Windows or Linux."
    )
    parser.add_argument("--dir", default="", help="install into this directory")
    parser.add_argument("--repo", default="", help="clone this git URL first")
    parser.add_argument("--branch", default="master")
    parser.add_argument("--host", default=DEFAULT_HOST)
    parser.add_argument("--port", type=int, default=DEFAULT_PORT)
    parser.add_argument("--autostart", action="store_true", help="register to start at logon/boot")
    parser.add_argument("--no-service", action="store_true", help="never touch the supervisor")
    parser.add_argument("--no-start", action="store_true", help="do not launch it now")
    parser.add_argument("--check", action="store_true", help="audit an install instead")
    parser.add_argument(
        "--unit",
        default="soapbot",
        metavar="NAME",
        help="service / task name to register (default soapbot; pick another for a second instance)",
    )
    parser.add_argument(
        "--extra",
        action="append",
        default=[],
        metavar="NAME",
        help="optional extras to install, e.g. --extra voice (repeatable)",
    )
    args = parser.parse_args(argv)

    if sys.version_info < MIN_PYTHON:
        die(f"Python {MIN_PYTHON[0]}.{MIN_PYTHON[1]}+ is required (running {sys.version.split()[0]})")

    say("1/6", "locating the source")
    root = ensure_source(args)

    if args.check:
        return check_only(root, args.port)

    python = ensure_venv(root, args.extra)
    ensure_ui(root)
    env_path = ensure_env(root, python, args.host, args.port)

    supervisor = (
        "Supervisor registration skipped (--no-service)."
        if args.no_service
        else install_service(root, python, env_path, args.autostart, args.unit)
    )

    if not args.no_start:
        say("start", f"waiting for http://{args.host}:{args.port}/api/health")
        log = root / "data" / "panel.log"
        if (not args.no_service and os.name == "nt" and not args.autostart) or (not args.no_service and os.name != "nt" and "no systemd" in supervisor) or args.no_service:
            start_background(root, python, log)

        for _ in range(30):
            if health_ok(args.port):
                break
            time.sleep(1)
        else:
            print(f"\n      it did not answer in 30s. Last lines of {log}:")
            if log.exists():
                tail = log.read_text(encoding="utf-8", errors="replace").splitlines()[-20:]
                print("      " + "\n      ".join(tail))
            raise SystemExit(1)

    token_cmd = f"{python} -m soapbot.cli token"
    panel = f"http://{args.host}:{args.port}"
    print("\n" + "=" * 68)
    print("  done.")
    print(f"  panel : {panel}")
    print(f"  token : {token_cmd}")
    print(f"  data  : {root / 'data'}   config: {root / 'config'}   env: {env_path}")
    print(f"  supervisor: {supervisor}")
    if args.host in {"127.0.0.1", "localhost"}:
        print(
            f"  remote view: ssh -L {args.port}:127.0.0.1:{args.port} <user>@<this-host> "
            f"then open {panel}"
        )
    print("  next: open Configure (page 07), add a Provider, then an adapter — both rows")
    print("        now show exactly what to paste into NapCat.")
    print("=" * 68)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
