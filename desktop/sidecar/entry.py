"""Frozen entry point for the backend the desktop shell spawns.

Why this file exists
--------------------
``Settings`` derives three paths from ``__file__``: ``PROJECT_ROOT`` is
``parents[2]`` of ``config.py``. That is correct in a checkout and wrong under
``--onefile``, where ``__file__`` lives inside a temporary extraction directory: the
data directory would land somewhere unpredictable, and the writable config would be
seeded from a path that disappears when the process exits.

The three directories are therefore pinned **before** importing anything that pulls in
``soapbot.config``. ``SOAPBOT_ENV_FILE`` matters most: ``SettingsConfigDict`` reads it at
class-definition time, so setting it after the import would silently have no effect.

Layout this produces, next to the executable::

    soapbot-backend.exe
    .env                 (optional, read if present)
    data/
      soapbot.db
      init_token.txt
      config/            seeded once from the bundled templates
"""

from __future__ import annotations

import os
import sys
from pathlib import Path


def _executable_dir() -> Path:
    """The folder holding the frozen binary; the checkout root when not frozen."""
    if getattr(sys, "frozen", False):
        return Path(sys.executable).resolve().parent
    return Path(__file__).resolve().parents[2]


def _bundle_dir() -> Path:
    """Where PyInstaller unpacked ``--add-data``; the checkout root when not frozen."""
    unpacked = getattr(sys, "_MEIPASS", None)
    if unpacked:
        return Path(unpacked)
    return Path(__file__).resolve().parents[2]


def main() -> int:
    root = _executable_dir()
    data = Path(os.environ.get("SOAPBOT_DATA_DIR") or (root / "data"))

    # setdefault, not overwrite: an operator who points SOAPBOT_DATA_DIR at a volume
    # keeps that choice, and the supervisor may pass a port or host on top.
    os.environ.setdefault("SOAPBOT_DATA_DIR", str(data))
    os.environ.setdefault("SOAPBOT_CONFIG_DIR", str(data / "config"))
    os.environ.setdefault("SOAPBOT_CONFIG_TEMPLATE_DIR", str(_bundle_dir() / "config"))
    os.environ.setdefault("SOAPBOT_ENV_FILE", str(root / ".env"))

    # Imported after the environment is final: ``soapbot.config`` resolves
    # ``SOAPBOT_ENV_FILE`` while the class is being defined.
    from soapbot.cli import main as cli_main

    # A double-clicked binary has no arguments. `start` is the only useful default —
    # printing a version to a console window that closes immediately helps nobody.
    argv = sys.argv[1:] or ["start"]
    return cli_main(argv)


if __name__ == "__main__":
    raise SystemExit(main())
