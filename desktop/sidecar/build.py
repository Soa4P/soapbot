"""Freeze the backend into one executable the desktop shell can spawn.

Why one file
------------
Tauri's ``externalBin`` expects a single binary per target triple, so ``--onefile`` is a
constraint rather than a preference: an onedir build would have to be installed as a
directory tree beside the .exe and packaged differently on each platform.

What has to be declared, and why
--------------------------------
* ``soapbot/webui/dist`` — the panel is served by FastAPI from a path derived from
  ``__file__``. PyInstaller only copies what ``--add-data`` names; without this the
  frozen binary starts and shows "webui not built".
* ``config`` — the read-only templates seeded into ``<data>/config`` on first start.
* ``--collect-submodules soapbot`` — ``uvicorn.run("soapbot.app:app")`` imports the app
  by string, which no static analysis sees.
* ``--collect-submodules uvicorn`` — uvicorn picks its loop and protocol
  implementations by name at runtime; the h11 and websockets implementations are
  otherwise missing and the first request fails with an ImportError.

Not included on purpose: tests, ruff, mypy, pytest. They are dev-only and PyInstaller
only follows imports, so they never enter the bundle unless something imports them.
"""

from __future__ import annotations

import importlib.util
import os
import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SIDECAR = ROOT / "desktop" / "sidecar"
DIST = SIDECAR / "dist"
BUILD = ROOT / "build" / "sidecar"
NAME = "soapbot-backend"

#: Named explicitly because they are resolved by string at runtime. The two
#: ``--collect-submodules`` flags cover the rest; these are the ones that have failed
#: in practice and cost an afternoon to diagnose from a frozen binary's traceback.
HIDDEN_IMPORTS = (
    "soapbot.app",
    "uvicorn.logging",
    "uvicorn.loops.auto",
    "uvicorn.loops.asyncio",
    "uvicorn.protocols.http.auto",
    "uvicorn.protocols.http.h11_impl",
    "uvicorn.protocols.websockets.auto",
    "uvicorn.protocols.websockets.websockets_impl",
    "uvicorn.lifespan.on",
    # SQLAlchemy loads a dialect from the URL string ("sqlite+aiosqlite://..."), which no
    # static import graph contains. Measured: without these the frozen binary starts,
    # seeds its config, and then dies in `create_async_engine` at startup — the traceback
    # names only `db.py:358` because the real exception is a dialect lookup.
    "sqlalchemy.dialects.sqlite.aiosqlite",
    "sqlalchemy.dialects.sqlite.pysqlite",
    "aiosqlite",
)


def command() -> list[str]:
    """The exact PyInstaller invocation, so a test can assert on it without building."""
    separator = os.pathsep
    args = [
        sys.executable,
        "-m",
        "PyInstaller",
        "--noconfirm",
        "--clean",
        "--onefile",
        # Console, not windowed: the supervisor captures stdout/stderr into panel.log,
        # and a windowed build on Windows detaches from them entirely.
        "--console",
        "--name",
        NAME,
        "--distpath",
        str(DIST),
        "--workpath",
        str(BUILD / "work"),
        "--specpath",
        str(BUILD),
        "--paths",
        str(ROOT / "src"),
        "--add-data",
        f"{ROOT / 'src' / 'soapbot' / 'webui' / 'dist'}{separator}soapbot/webui/dist",
        "--add-data",
        f"{ROOT / 'config'}{separator}config",
        "--collect-submodules",
        "uvicorn",
        "--collect-submodules",
        "soapbot",
        "--collect-submodules",
        "sqlalchemy.dialects.sqlite",
    ]
    for name in HIDDEN_IMPORTS:
        args += ["--hidden-import", name]
    args.append(str(SIDECAR / "entry.py"))
    return args


def main() -> int:
    # Checked before anything expensive: CI failed on this once with a bare
    # "No module named PyInstaller" from a subprocess, which reads like a broken build
    # rather than a missing optional dependency.
    if importlib.util.find_spec("PyInstaller") is None:
        print(
            'PyInstaller is not installed; run `pip install -e ".[sidecar]"`',
            file=sys.stderr,
        )
        return 2

    dist_missing = not (ROOT / "src" / "soapbot" / "webui" / "dist" / "index.html").is_file()
    if dist_missing:
        print(
            "webui/dist is missing; run `cd webui && npm ci && npm run build` first",
            file=sys.stderr,
        )
        return 2

    DIST.mkdir(parents=True, exist_ok=True)
    completed = subprocess.run(command(), cwd=ROOT)
    if completed.returncode:
        return completed.returncode

    binary = DIST / (NAME + (".exe" if os.name == "nt" else ""))
    if not binary.is_file():
        print(f"PyInstaller reported success but {binary} does not exist", file=sys.stderr)
        return 1
    size = binary.stat().st_size / 1_048_576
    print(f"built {binary.relative_to(ROOT)} ({size:.1f} MiB)")

    # `tauri.conf.json` declares `bundle.resources: ["binaries/soapbot-backend.exe"]`,
    # which is resolved relative to `src-tauri`. Staging here means `tauri build` works
    # right after this script without the caller remembering a second copy step.
    staged = ROOT / "desktop" / "src-tauri" / "binaries" / binary.name
    staged.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(binary, staged)
    print(f"staged {staged.relative_to(ROOT)} for `tauri build`")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
