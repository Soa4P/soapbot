"""Persona cards.

A persona card is a YAML/Markdown file describing how the bot should behave in a
given scope. Cards are resolved per group / per user with a fallback chain:

    user binding  ->  group binding  ->  global default

Security note: persona text is *trusted operator input* and goes into the system
prompt. User messages never do. That separation is what stops prompt injection
from rewriting the persona.
"""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml

logger = logging.getLogger(__name__)

_FRONT_MATTER_RE = re.compile(r"^---\s*\n(.*?)\n---\s*\n?(.*)$", re.DOTALL)


@dataclass(slots=True)
class Persona:
    id: str
    name: str
    system_prompt: str = ""
    style: str = ""
    """Short speaking-style note appended to the system prompt."""
    examples: list[dict[str, str]] = field(default_factory=list)
    """Few-shot turns: [{'user': '...', 'assistant': '...'}]"""
    banned_words: list[str] = field(default_factory=list)
    wake_words: list[str] = field(default_factory=list)
    max_reply_chars: int = 500
    temperature: float | None = None
    version: int = 1
    enabled: bool = True
    locale: str = ""
    """Reply language for this card; empty means "use the process default".

    Per-persona rather than global because one bot usually serves several groups,
    and a group that speaks English should not have to change the process setting
    (which would flip every other group too).
    """
    extra: dict[str, Any] = field(default_factory=dict)

    def build_system_prompt(self, context_note: str = "") -> str:
        parts: list[str] = []
        if self.system_prompt:
            parts.append(self.system_prompt.strip())
        if self.style:
            parts.append(f"说话风格要求：{self.style.strip()}")
        if self.max_reply_chars:
            parts.append(f"回复长度控制在 {self.max_reply_chars} 字以内。")
        if self.banned_words:
            parts.append("禁止使用以下词语：" + "、".join(self.banned_words))
        if context_note:
            parts.append(context_note)
        return "\n\n".join(parts)


@dataclass(slots=True)
class PersonaBinding:
    """Which persona applies where. Empty id means 'inherit'."""

    global_default: str = ""
    groups: dict[str, str] = field(default_factory=dict)
    users: dict[str, str] = field(default_factory=dict)


class PersonaStore:
    def __init__(self, directory: Path | None = None) -> None:
        self._personas: dict[str, Persona] = {}
        self._binding = PersonaBinding()
        self._directory = directory

    # ---------------------------------------------------------------- loading
    def load_directory(self, directory: Path) -> int:
        self._directory = directory
        directory.mkdir(parents=True, exist_ok=True)
        count = 0
        files = sorted(
            [*directory.glob("*.yaml"), *directory.glob("*.yml"), *directory.glob("*.md")]
        )
        for path in files:
            try:
                persona = load_persona_file(path)
                self._personas[persona.id] = persona
                count += 1
            except Exception as exc:
                logger.error("failed to load persona %s: %s", path.name, exc)
        logger.info("loaded %d persona card(s) from %s", count, directory)
        return count

    def load_markdown(self, path: Path) -> Persona:
        persona = load_persona_file(path)
        self._personas[persona.id] = persona
        return persona

    # ---------------------------------------------------------------- CRUD
    def add(self, persona: Persona) -> None:
        self._personas[persona.id] = persona

    def get(self, persona_id: str) -> Persona | None:
        return self._personas.get(persona_id)

    def all(self) -> list[Persona]:
        return sorted(self._personas.values(), key=lambda p: p.id)

    def delete(self, persona_id: str) -> bool:
        return self._personas.pop(persona_id, None) is not None

    # ---------------------------------------------------------------- binding
    @property
    def binding(self) -> PersonaBinding:
        return self._binding

    def bind_group(self, group_id: str, persona_id: str) -> None:
        if persona_id:
            self._binding.groups[group_id] = persona_id
        else:
            self._binding.groups.pop(group_id, None)

    def bind_user(self, user_id: str, persona_id: str) -> None:
        if persona_id:
            self._binding.users[user_id] = persona_id
        else:
            self._binding.users.pop(user_id, None)

    def set_default(self, persona_id: str) -> None:
        self._binding.global_default = persona_id

    def resolve(
        self, *, group_id: str = "", user_id: str = ""
    ) -> tuple[Persona | None, str]:
        """Return (persona, source) following user -> group -> default."""
        if user_id and user_id in self._binding.users:
            p = self._personas.get(self._binding.users[user_id])
            if p and p.enabled:
                return p, "user"
        if group_id and group_id in self._binding.groups:
            p = self._personas.get(self._binding.groups[group_id])
            if p and p.enabled:
                return p, "group"
        if self._binding.global_default:
            p = self._personas.get(self._binding.global_default)
            if p and p.enabled:
                return p, "default"
        for p in self.all():
            if p.enabled:
                return p, "first_available"
        return None, "none"


def load_persona_file(path: Path) -> Persona:
    """Load a persona from YAML, or Markdown with YAML front matter."""
    text = path.read_text(encoding="utf-8")
    stem = path.stem

    if path.suffix.lower() in (".md", ".markdown"):
        match = _FRONT_MATTER_RE.match(text)
        if not match:
            return Persona(
                id=stem,
                name=stem,
                system_prompt=text.strip(),
            )
        meta = yaml.safe_load(match.group(1)) or {}
        body = match.group(2).strip()
        return _persona_from_dict(meta, body, stem)

    meta = yaml.safe_load(text) or {}
    if not isinstance(meta, dict):
        raise ValueError(f"persona file {path.name} must be a mapping")
    return _persona_from_dict(meta, "", stem)


def _persona_from_dict(meta: dict[str, Any], body: str, stem: str) -> Persona:
    system_prompt = str(meta.get("system_prompt") or body or "").strip()
    examples = meta.get("examples") or []
    if not isinstance(examples, list):
        examples = []
    return Persona(
        id=str(meta.get("id") or stem),
        name=str(meta.get("name") or stem),
        system_prompt=system_prompt,
        style=str(meta.get("style") or ""),
        examples=[
            {"user": str(e.get("user", "")), "assistant": str(e.get("assistant", ""))}
            for e in examples
            if isinstance(e, dict)
        ],
        banned_words=[str(w) for w in (meta.get("banned_words") or [])],
        wake_words=[str(w) for w in (meta.get("wake_words") or [])],
        max_reply_chars=int(meta.get("max_reply_chars", 500) or 500),
        temperature=(
            float(meta["temperature"]) if meta.get("temperature") is not None else None
        ),
        version=int(meta.get("version", 1) or 1),
        enabled=bool(meta.get("enabled", True)),
        locale=str(meta.get("locale") or ""),
        extra={k: v for k, v in meta.items() if k not in _KNOWN_KEYS},
    )


_KNOWN_KEYS = {
    "id",
    "name",
    "system_prompt",
    "style",
    "examples",
    "banned_words",
    "wake_words",
    "max_reply_chars",
    "locale",
    "temperature",
    "version",
    "enabled",
}
