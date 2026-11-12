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

    def build_system_prompt(
        self,
        context_note: str = "",
        *,
        memory_note: str = "",
        timeline_note: str = "",
        task_note: str = "",
        tools_note: str = "",
    ) -> str:
        """Assemble the system prompt in fixed sections.

        Order is load-bearing: identity first, then data. Putting recalled text
        before the operator's rules makes an attacker's sentence read like one of
        them, because a flat prompt has no other cue about which is which.

        The extra sections are optional and appended only when non-empty — a heading
        with nothing under it costs tokens and tells the model nothing. ``context_note``
        keeps its existing shape (its producers already frame untrusted parts with
        ``wrap_untrusted``); wrapping it again here would nest two "this is data"
        banners around the same text.
        """
        core: list[str] = []
        if self.system_prompt:
            core.append(self.system_prompt.strip())
        if self.style:
            core.append(f"说话风格要求：{self.style.strip()}")
        if self.max_reply_chars:
            core.append(f"回复长度控制在 {self.max_reply_chars} 字以内。")
        if self.banned_words:
            core.append("禁止使用以下词语：" + "、".join(self.banned_words))

        sections: list[str] = []
        if core:
            sections.append("【核心设定】\n" + "\n".join(core))
        for heading, body in (
            ("【长期记忆】", memory_note),
            ("【近期事件】", timeline_note),
            ("【当前任务】", task_note),
            ("【工具说明】", tools_note),
        ):
            text = (body or "").strip()
            if text:
                sections.append(f"{heading}\n{text}")
        if context_note.strip():
            sections.append("【外部内容】\n" + context_note.strip())
        return "\n\n".join(sections)


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
        # Set by the runtime once version storage exists. Typed loosely because
        # persona_history imports this module; a concrete type here would be a cycle.
        self._history: Any = None
        #: ``PersonaGrowth`` when automatic growth is wired, else ``None``.
        #: Loosely typed for the same reason as ``_history``.
        self.growth: Any = None

    def attach_history(self, history: Any) -> None:
        self._history = history

    def _restore_from_history(self, persona_id: str) -> bool:
        """Rewrite an unreadable card from its newest restorable version.

        A half-written or hand-broken front matter used to mean the persona silently
        disappeared from the panel and the bot fell back to another card. Growth
        writes make that failure more likely, so a bad file now recovers itself and
        the event is logged at error level.
        """
        if self._history is None:
            return False
        latest = self._history.latest_restorable(persona_id)
        if latest is None:
            return False
        try:
            persona = persona_from_payload(latest.payload, persona_id)
            path = self.path_for(persona_id)
            if path is not None:
                from soapbot.core.config_write import write_atomic

                write_atomic(path, dump_persona_file(persona))
            self._personas[persona.id] = persona
            logger.error(
                "persona %s was unreadable; restored version %d", persona_id, latest.version
            )
            return True
        except Exception as exc:
            logger.error("persona %s restore failed: %s", persona_id, exc)
            return False

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
                if self._restore_from_history(path.stem):
                    count += 1
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

    # ---------------------------------------------------------------- persistence
    @property
    def directory(self) -> Path | None:
        return self._directory

    def path_for(self, persona_id: str) -> Path | None:
        """Where a card with this id is (or would be) stored.

        ``None`` when the store was built without a directory — a test store, or one
        assembled by hand. Callers that write must treat that as "not writable" rather
        than inventing a path.
        """
        if self._directory is None:
            return None
        return self._directory / f"{persona_id}.md"

    def save(self, persona: Persona) -> Path:
        """Write the card to disk and into the live store.

        Disk first, memory second: if the write fails the running bot keeps behaving as
        it did, instead of serving a card that will vanish on the next restart.
        """
        path = self.path_for(persona.id)
        if path is None:
            raise RuntimeError("persona store has no directory to write to")
        path.parent.mkdir(parents=True, exist_ok=True)
        from soapbot.core.config_write import write_atomic

        write_atomic(path, dump_persona_file(persona))
        self._personas[persona.id] = persona
        return path

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


def persona_to_payload(persona: Persona) -> dict[str, Any]:
    """The fields a version row stores, so a rollback can rebuild the card.

    Only data, no behaviour: a version is replayed through
    :func:`persona_from_payload`, so anything not listed here is not restorable and
    must not be offered to a growth write in the first place.
    """
    return {
        "id": persona.id,
        "name": persona.name,
        "system_prompt": persona.system_prompt,
        "style": persona.style,
        "banned_words": list(persona.banned_words),
        "wake_words": list(persona.wake_words),
        "max_reply_chars": persona.max_reply_chars,
        "temperature": persona.temperature,
        "version": persona.version,
        "enabled": persona.enabled,
        "locale": persona.locale,
        "examples": [dict(item) for item in persona.examples],
        # Hand-written front matter (including the autonomy / warmth knobs) used to
        # be dropped by a rollback: the panel preserved it on save but a version
        # restore rebuilt a card with an empty `extra`. A version must replay the
        # whole card, not just the fields this module happens to know by name.
        "extra": dict(persona.extra or {}),
    }


def persona_from_payload(payload: dict[str, Any], persona_id: str) -> Persona:
    """Rebuild a card from a stored version. Tolerates missing keys."""
    examples = payload.get("examples") or []
    return Persona(
        id=persona_id,
        name=str(payload.get("name") or persona_id),
        system_prompt=str(payload.get("system_prompt") or ""),
        style=str(payload.get("style") or ""),
        examples=[
            {"user": str(e.get("user", "")), "assistant": str(e.get("assistant", ""))}
            for e in examples
            if isinstance(e, dict)
        ],
        banned_words=[str(w) for w in (payload.get("banned_words") or [])],
        wake_words=[str(w) for w in (payload.get("wake_words") or [])],
        max_reply_chars=int(payload.get("max_reply_chars") or 500),
        temperature=(
            float(payload["temperature"])
            if payload.get("temperature") is not None
            else None
        ),
        version=int(payload.get("version") or 1),
        enabled=bool(payload.get("enabled", True)),
        locale=str(payload.get("locale") or ""),
        extra=dict(payload["extra"])
        if isinstance(payload.get("extra"), dict)
        else {},
    )


def dump_persona_file(persona: Persona) -> str:
    """Render ``persona`` as a Markdown card with YAML front matter.

    Markdown rather than YAML-on-its-own because the prompt is prose and belongs in the
    body, where an editor can show it without escaping. Round-trips through
    :func:`load_persona_file`: every field the loader reads is written here, and
    ``extra`` is carried through untouched so a hand-written key the panel does not
    know about survives a save from the panel.
    """
    meta: dict[str, Any] = {
        "id": persona.id,
        "name": persona.name,
        "style": persona.style,
        "wake_words": list(persona.wake_words),
        "banned_words": list(persona.banned_words),
        "max_reply_chars": persona.max_reply_chars,
        "enabled": persona.enabled,
        "version": persona.version,
    }
    if persona.temperature is not None:
        meta["temperature"] = persona.temperature
    if persona.locale:
        meta["locale"] = persona.locale
    if persona.examples:
        meta["examples"] = list(persona.examples)
    for key, value in (persona.extra or {}).items():
        if key not in meta and key not in _KNOWN_KEYS:
            meta[key] = value

    front = yaml.safe_dump(
        meta, allow_unicode=True, sort_keys=False, default_flow_style=False
    ).strip()
    body = (persona.system_prompt or "").strip()
    return f"---\n{front}\n---\n\n{body}\n"


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
