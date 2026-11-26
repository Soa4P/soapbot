"""QQ official bot menu: a local schema, validator and store. **No API calls yet.**

Why a local skeleton
--------------------
The official bot's custom menu is configured by uploading one JSON document. Doing that
live needs an AppID/Secret this deployment does not have, and an unverified upload path
would be "documented but never run". What *can* be built and verified locally is the part
with the failure modes: the document's shape, the text that ends up rendered inside the
user's chat client, and where it is stored.

So this module owns:

* the document schema (:func:`validate`) — depth and fan-out caps, unique names, and the
  rule that a ``send`` item carries exactly one of ``reply``/``url``;
* text safety — menu names are rendered by the platform's client, so control characters
  and markup are refused here rather than trusted to a remote validator;
* the store (:class:`MenuStore`) — one JSON file, atomic replace, ``0600``, because the
  file is operator configuration and half-written config is worse than none.

Wiring the upload is a separate change: :func:`to_api_payload` already produces the shape
the platform expects, so that change is a transport, not a redesign. The caps below are
deliberately conservative and documented as *ours*: the platform's own limits must be
re-checked when the upload path is written, and this validator is the floor, not the
authority.
"""

from __future__ import annotations

import json
import logging
import os
import re
import tempfile
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

#: Menu depth. The client renders a nested list; three levels is one more than any
#: deployment has needed and keeps the document readable in a diff.
MAX_DEPTH = 3
#: Items per level.
MAX_ITEMS_PER_LEVEL = 5
#: A menu label is a button, not a paragraph.
MAX_NAME_CHARS = 16
#: Reply text is sent as a message, so the message cap applies; this is the menu-side floor.
MAX_REPLY_CHARS = 500
MAX_URL_CHARS = 512

#: Control characters (including the invisible ones used to smuggle direction overrides),
#: plus markup characters that a chat client would render.
_CONTROL_RE = re.compile(r"[\x00-\x1f\x7f\u200b-\u200f\u202a-\u202e\u2060-\u206f]")
_MARKUP_RE = re.compile(r"[<>]")

ITEM_TYPES = frozenset({"send", "link", "menu"})
_SCHEMA = 1


class MenuError(ValueError):
    """The document is not a valid menu. Carries every problem, not just the first."""

    def __init__(self, problems: list[str]) -> None:
        self.problems = problems
        super().__init__("; ".join(problems))


@dataclass(slots=True)
class MenuItem:
    name: str
    type: str
    reply: str = ""
    url: str = ""
    children: list[MenuItem] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        out: dict[str, Any] = {"name": self.name, "type": self.type}
        if self.reply:
            out["reply"] = self.reply
        if self.url:
            out["url"] = self.url
        if self.children:
            out["children"] = [child.to_dict() for child in self.children]
        return out


def _clean_text(value: str, label: str, problems: list[str]) -> str:
    text = str(value or "").strip()
    if _CONTROL_RE.search(text):
        problems.append(f"{label} 含控制字符或不可见字符")
    if _MARKUP_RE.search(text):
        problems.append(f"{label} 含 < 或 >：菜单文本由平台客户端渲染，不允许标记")
    return text


def _parse_items(raw: Any, *, depth: int, path: str, problems: list[str]) -> list[MenuItem]:
    if not isinstance(raw, list):
        problems.append(f"{path}: items 必须是数组")
        return []
    if len(raw) > MAX_ITEMS_PER_LEVEL:
        problems.append(f"{path}: 一级最多 {MAX_ITEMS_PER_LEVEL} 项，实际 {len(raw)}")
    if depth > MAX_DEPTH:
        problems.append(f"{path}: 层级超过 {MAX_DEPTH}")
        return []

    items: list[MenuItem] = []
    seen: set[str] = set()
    for index, entry in enumerate(raw):
        where = f"{path}[{index}]"
        if not isinstance(entry, dict):
            problems.append(f"{where}: 必须是对象")
            continue
        name = _clean_text(entry.get("name", ""), f"{where}.name", problems)
        if not name:
            problems.append(f"{where}.name 不能为空")
        elif len(name) > MAX_NAME_CHARS:
            problems.append(f"{where}.name 超过 {MAX_NAME_CHARS} 字")
        if name in seen:
            # Duplicate labels render as two identical buttons; the platform's own
            # validator may accept them, and the operator cannot tell which is which.
            problems.append(f"{where}.name 与同级另一项重复：{name!r}")
        seen.add(name)

        kind = str(entry.get("type") or "").strip().lower()
        if kind not in ITEM_TYPES:
            problems.append(f"{where}.type 必须是 {'/'.join(sorted(ITEM_TYPES))}")
            kind = "send"

        reply = _clean_text(entry.get("reply", ""), f"{where}.reply", problems)
        url = _clean_text(entry.get("url", ""), f"{where}.url", problems)
        if len(reply) > MAX_REPLY_CHARS:
            problems.append(f"{where}.reply 超过 {MAX_REPLY_CHARS} 字")
        if len(url) > MAX_URL_CHARS:
            problems.append(f"{where}.url 超过 {MAX_URL_CHARS} 字")

        children: list[MenuItem] = []
        if kind == "menu":
            children = _parse_items(
                entry.get("children") or [], depth=depth + 1, path=f"{where}.children",
                problems=problems,
            )
            if not children and not any(p.startswith(f"{where}.children") for p in problems):
                problems.append(f"{where}: type=menu 但没有任何子项")
            if reply or url:
                problems.append(f"{where}: type=menu 不能同时带 reply/url")
        elif kind == "send":
            if not reply:
                problems.append(f"{where}: type=send 需要 reply")
            if url:
                problems.append(f"{where}: type=send 不能带 url")
        elif kind == "link":
            if not url:
                problems.append(f"{where}: type=link 需要 url")
            if reply:
                problems.append(f"{where}: type=link 不能带 reply")
            if url and not (url.startswith("https://") or url.startswith("http://")):
                # A ``javascript:`` or ``data:`` link in a menu button is a way to run
                # something in the client; plain http(s) is the only shape this has a
                # reason to allow.
                problems.append(f"{where}.url 必须是 http(s) 链接")

        items.append(MenuItem(name=name, type=kind, reply=reply, url=url, children=children))
    return items


def parse(document: Any) -> list[MenuItem]:
    """Validate a document and return its items. Raises :class:`MenuError`."""
    problems: list[str] = []
    if not isinstance(document, dict):
        raise MenuError(["菜单必须是一个对象：{\"items\": [...]}"])
    items = _parse_items(document.get("items") or [], depth=1, path="items", problems=problems)
    if not items and not problems:
        problems.append("菜单至少要有一项")
    if problems:
        raise MenuError(problems)
    return items


def validate(document: Any) -> list[str]:
    """Problems with ``document``; empty means valid. Never raises."""
    try:
        parse(document)
    except MenuError as exc:
        return exc.problems
    return []


def to_api_payload(items: list[MenuItem]) -> dict[str, Any]:
    """The shape an upload would send.

    Kept here, and unused, so the wiring change is a transport rather than a redesign —
    and so the mapping is reviewable now, while there is no network in the loop.
    """
    return {"items": [item.to_dict() for item in items]}


def menu_path(config_dir: Path) -> Path:
    return Path(config_dir) / "qq_menu.json"


class MenuStore:
    """``data/config/qq_menu.json``: read, validate, write atomically at ``0600``."""

    def __init__(self, path: Path) -> None:
        self.path = Path(path)

    def load(self) -> dict[str, Any]:
        """The stored document, or an empty menu. A corrupt file is reported, not fatal."""
        if not self.path.exists():
            return {"items": []}
        try:
            raw = json.loads(self.path.read_text(encoding="utf-8"))
        except (OSError, ValueError) as exc:
            logger.warning("qq menu file unreadable (%s): %s", self.path, exc)
            return {"items": []}
        if not isinstance(raw, dict):
            return {"items": []}
        return {"items": raw.get("items") or []}

    def save(self, document: Any) -> dict[str, Any]:
        """Validate then persist. Raises :class:`MenuError` without touching the file."""
        items = parse(document)
        payload = {"schema": _SCHEMA, "items": [item.to_dict() for item in items]}
        data = json.dumps(payload, ensure_ascii=False, indent=2) + "\n"

        self.path.parent.mkdir(parents=True, exist_ok=True)
        fd, tmp_name = tempfile.mkstemp(prefix=".qq-menu-", dir=str(self.path.parent))
        tmp = Path(tmp_name)
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as handle:
                handle.write(data)
                handle.flush()
                os.fsync(handle.fileno())
            os.replace(tmp, self.path)
        finally:
            tmp.unlink(missing_ok=True)
        if os.name == "posix":
            try:
                os.chmod(self.path, 0o600)
            except OSError:  # pragma: no cover - exotic filesystem
                logger.warning("could not restrict permissions on %s", self.path)
        return {"items": payload["items"]}


__all__ = [
    "MAX_DEPTH",
    "MAX_ITEMS_PER_LEVEL",
    "MAX_NAME_CHARS",
    "MenuError",
    "MenuItem",
    "MenuStore",
    "menu_path",
    "parse",
    "to_api_payload",
    "validate",
]
