"""Example plugins that ship **inside** the package.

Why these live under ``src/soapbot`` and not in ``data/``:

``data/`` is the writable volume — it is gitignored, it is a Docker volume, and a
compromised plugin can write to it. Anything an operator is expected to *have* on
first start must therefore not live there, or a fresh clone arrives with no
plugins at all. That was a measured defect: ``data/plugins`` was ignored by
``.gitignore``, so a clean checkout had zero working plugins and six test modules
failed with ``FileNotFoundError`` while the maintainer's tree stayed green.

Bundling them here instead means:

* ``git clone`` → ``soapbot start`` has a working example to approve;
* the wheel carries them (``packages = ["src/soapbot"]`` covers subpackages), so a
  container image is not missing them either;
* tests can point at ``bundled_plugins_dir()`` and get the same bytes everywhere.

These are *examples*, not built-ins: nothing here is auto-approved or auto-loaded.
Discovery lists them, and an operator still has to enable each one — see
``docs/plugin-security.md`` for why that separation is not negotiable.
"""

from __future__ import annotations

from pathlib import Path

__all__ = ["bundled_plugins_dir"]


def bundled_plugins_dir() -> Path:
    """Absolute path to the example plugin directory shipped with this package."""
    return Path(__file__).resolve().parent / "plugins"
