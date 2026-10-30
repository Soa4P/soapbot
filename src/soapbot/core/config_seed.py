"""Give the runtime config directory its first files.

The service now writes its own configuration (the panel edits providers and adapters),
so that directory lives on the writable volume. The files shipped in the image are a
*template*: they are copied once, on first start, and never again.

Copied, not linked, and only when missing. Two failure modes this avoids:

* a container rebuild silently reverting an operator's edited `providers.yaml` because
  it was a symlink into the image;
* a half-written file from an interrupted first start being overwritten on every boot,
  which would look like "my settings vanish but my keys work".
"""

from __future__ import annotations

import logging
import shutil
from pathlib import Path

logger = logging.getLogger(__name__)

#: The files the panel can edit. Anything else in the template directory (personas, for
#: example) is content, not configuration, and is seeded too but logged differently.
CONFIG_FILES = ("providers.yaml", "adapters.yaml", "mcp.yaml")


def seed_config_dir(target: Path, template: Path) -> list[str]:
    """Copy missing config files from ``template`` into ``target``.

    Returns the names copied, so a caller (or a test) can assert what actually happened
    rather than "no exception was raised".
    """
    copied: list[str] = []
    target.mkdir(parents=True, exist_ok=True)
    if not template.is_dir():
        return copied

    for name in CONFIG_FILES:
        source = template / name
        destination = target / name
        if not source.is_file() or destination.exists():
            continue
        shutil.copyfile(source, destination)
        copied.append(name)

    if copied:
        logger.info("seeded config %s from %s", ", ".join(copied), template)
    return copied
