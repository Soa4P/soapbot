"""soapbot.memory package.

The memory layer is three things stacked:

* :mod:`soapbot.memory.store` — individual memories, retrieval, and RAG.
* :mod:`soapbot.memory.scene` — the derived view: a per-scene index card, a portrait, and
  typed links between memories. This is the Obsidian-shaped part: structure earned from
  content rather than declared up front.
* :mod:`soapbot.memory.skills` — consolidation: recurring memory clusters promoted into
  scene-private Markdown skills.

Exports are listed explicitly rather than left to ``import *`` so that ``from
soapbot.memory import X`` is a stable surface and the package's own modules stay private.
"""

from soapbot.memory.scene import (
    LINK_KINDS,
    MemoryLink,
    SceneCard,
    SceneMemory,
    ScenePortrait,
)
from soapbot.memory.skills import Skill, SkillCandidate, SkillForge

__all__ = [
    "LINK_KINDS",
    "MemoryLink",
    "SceneCard",
    "SceneMemory",
    "ScenePortrait",
    "Skill",
    "SkillCandidate",
    "SkillForge",
]
