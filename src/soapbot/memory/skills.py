"""Turning what a scene has learned into a private skill.

The idea, borrowed from how an Obsidian vault accumulates structure
-------------------------------------------------------------------
A vault does not stay a pile of notes. Notes get promoted: a recurring way of answering a
question becomes a template, a set of related notes becomes a MOC, a repeated procedure
becomes a checklist. The structure is *earned* by what the vault already contains, not
declared up front.

The same promotion is what memory needs. Today every turn re-derives the same answers from
the same fragments: the group asks "how do I deploy" for the fifth time and recall returns
five slightly different fragments of the same answer. The knowledge exists; it is just
never consolidated. A **private skill** is that consolidation — a Markdown file, scoped to
one scene, that says "here is how this group answers this question".

Why a file and not a row
------------------------
Because a skill is meant to be read, edited and deleted by the operator. A row in a table
is ours; a Markdown file in ``<data>/skills/<scope>/`` is theirs, and it can be opened in
Obsidian, which is where this idea came from. It also means a bad skill is fixed with a
text editor rather than a migration.

Why these are *private* skills
------------------------------
Scoped to one scene, never shared. A skill distilled from group A's conversation is group
A's, and copying it to group B would leak both the content and the fact that A discussed
it. The directory layout enforces this: one folder per scope, and the loader only ever
reads the folder for the scope it was asked about.

What is deliberately not here
-----------------------------
No model call. A skill is assembled from memories that already passed ``vet_memory``, so
the consolidation cannot introduce text that was never vetted. A model-written skill would
be a new, unvetted write path into the prompt — the exact thing the memory quarantine
exists to prevent.
"""

from __future__ import annotations

import hashlib
import logging
import re
import time
from dataclasses import dataclass, field
from pathlib import Path
from urllib.parse import quote

logger = logging.getLogger(__name__)

#: A skill needs this many supporting memories before it is worth writing.
#:
#: Two is not a pattern, it is a coincidence. Three is the smallest number where "this
#: keeps coming up" is a claim the evidence supports.
MIN_SUPPORT = 3

#: Characters kept from each supporting memory. A skill is a summary; the full text stays
#: in the memory table and is still reachable by recall.
_SNIPPET = 160

#: Longest a generated skill may be. Bounded because skills are injected into the prompt
#: when relevant, and an unbounded one is a prompt-stuffing vector.
MAX_SKILL_CHARS = 4000

#: Scope ids are validated before they are used as a path component. Anything else — a
#: slash, a ``..`` — would let a scope escape its folder, and the scope comes from a
#: session key which is derived from transport input.
#:
#: Note what is *not* in this set: ``:``. Session keys look like ``group:12345``, and a
#: colon is legal in this regex but illegal in a Windows path — ``mkdir`` fails with
#: ``WinError 267``. The scope is therefore encoded with :func:`_dir_name` before it
#: touches the filesystem, which is both portable and reversible.
_SCOPE_RE = re.compile(r"^[A-Za-z0-9_.:-]{1,128}$")

#: Skill ids come from :func:`_slug`, which keeps Chinese characters on purpose (the
#: operator reads these file names). They are still path components, so separators and
#: traversal sequences are excluded.
_SKILL_ID_RE = re.compile(r"^[\w\u4e00-\u9fff-]{1,80}$")


def _is_traversal(name: str) -> bool:
    """Whether a single path component is ``.`` or ``..``.

    ``_SCOPE_RE`` admits both, and ``quote('..', safe='')`` returns ``'..'`` unchanged —
    ``.`` is in the RFC 3986 unreserved set, so percent-encoding does not neutralise it.
    The result was a real traversal: a scope of ``..`` resolved to the parent of the
    skills root, and ``save`` would have written outside the vault.

    Checked separately from the charset because it is a different question. The regex asks
    "is this a legal identifier"; this asks "does this identifier name a directory".
    """
    return name in (".", "..")


def _dir_name(scope: str) -> str:
    """Encode a scope into a portable directory name.

    Percent-encoding rather than ``replace(':', '_')``: the latter is not reversible, so
    ``group:1`` and ``group_1`` would share a folder and each would see the other's
    skills. Reversibility matters because the folder name is the only record of which
    scope a skill belongs to when the front matter is missing or hand-edited.
    """
    return quote(scope, safe="")


def _safe_scope(scope: str) -> bool:
    """Whether ``scope`` may be used as a directory name.

    One predicate for both the charset and the traversal check, so no call site can apply
    half of the rule. Every filesystem-touching method goes through this.
    """
    return bool(_SCOPE_RE.match(scope)) and not _is_traversal(scope)


def _safe_skill_id(skill_id: str) -> bool:
    return bool(_SKILL_ID_RE.match(skill_id)) and not _is_traversal(skill_id)

_FRONT_MATTER = """---
id: {skill_id}
scope: {scope}
kind: memory-skill
generated: {generated}
support: {support}
confidence: {confidence}
---

"""


@dataclass(slots=True)
class Skill:
    """A consolidated answer, scoped to one scene."""

    skill_id: str
    scope: str
    title: str
    body: str
    support: int = 0
    """How many memories this skill was distilled from."""
    confidence: float = 0.0
    created_at: float = 0.0
    path: Path | None = None

    def to_markdown(self) -> str:
        return _FRONT_MATTER.format(
            skill_id=self.skill_id,
            scope=self.scope,
            generated=time.strftime("%Y-%m-%dT%H:%M:%S", time.localtime(self.created_at or time.time())),
            support=self.support,
            confidence=self.confidence,
        ) + f"# {self.title}\n\n{self.body}\n"


@dataclass(slots=True)
class SkillCandidate:
    """A cluster of memories that looks like it wants to become a skill."""

    topic: str
    memories: list[str] = field(default_factory=list)

    @property
    def support(self) -> int:
        return len(self.memories)


class SkillForge:
    """Distils recurring memory clusters into scene-private Markdown skills.

    The detection rule is deliberately simple: group memories by their dominant keyword,
    and promote any group with at least :data:`MIN_SUPPORT` members. Simple because it is
    auditable — an operator can look at a skill and see exactly which memories produced it
    — and because a cleverer rule (embeddings, clustering) would produce skills whose
    provenance is a float.
    """

    def __init__(self, root: Path) -> None:
        self.root = root

    # ------------------------------------------------------------- detection
    def candidates(self, memories: list[tuple[int, str, str]]) -> list[SkillCandidate]:
        """Group ``(id, content, keywords)`` triples into skill candidates.

        Keyword-based rather than embedding-based on purpose: the grouping has to be
        explainable. "These four memories all mention 部署" is a sentence an operator can
        check; "these four vectors had cosine > 0.82" is not.
        """
        buckets: dict[str, list[str]] = {}
        for _mid, content, keywords in memories:
            text = (content or "").strip()
            if not text:
                continue
            for token in (keywords or "").split()[:3]:
                buckets.setdefault(token, []).append(text[:_SNIPPET])

        out: list[SkillCandidate] = []
        for topic, items in buckets.items():
            if len(items) >= MIN_SUPPORT:
                # De-duplicate: the same sentence extracted twice is one piece of
                # evidence, not two, and counting it twice would inflate confidence.
                unique = list(dict.fromkeys(items))
                if len(unique) >= MIN_SUPPORT:
                    out.append(SkillCandidate(topic=topic, memories=unique))
        out.sort(key=lambda c: c.support, reverse=True)
        return out

    # --------------------------------------------------------------- writing
    def build(self, scope: str, candidate: SkillCandidate) -> Skill:
        """Assemble a skill from a candidate cluster."""
        body_lines = [
            f"本场景在「{candidate.topic}」上反复出现以下要点：",
            "",
        ]
        for item in candidate.memories:
            body_lines.append(f"- {item}")

        body = "\n".join(body_lines)
        if len(body) > MAX_SKILL_CHARS:
            body = body[:MAX_SKILL_CHARS] + "\n\n（已截断）"

        return Skill(
            skill_id=_slug(candidate.topic),
            scope=scope,
            title=f"{candidate.topic}",
            body=body,
            support=candidate.support,
            confidence=round(min(1.0, candidate.support / (candidate.support + 5.0)), 3),
            created_at=time.time(),
        )

    def save(self, skill: Skill) -> Path:
        """Write a skill to its scene's folder.

        The scope is re-validated here even though it was validated on the way in. This is
        the last point before a filesystem write, and a scope containing ``..`` would put
        the file outside the vault — a path traversal whose only symptom is that the skill
        "does not load".
        """
        if not _safe_scope(skill.scope):
            raise ValueError(f"unsafe scope for skill directory: {skill.scope!r}")
        if not _safe_skill_id(skill.skill_id):
            raise ValueError(f"unsafe skill id: {skill.skill_id!r}")
        directory = self.root / _dir_name(skill.scope)
        directory.mkdir(parents=True, exist_ok=True)
        path = directory / f"{skill.skill_id}.md"

        # Belt and braces: resolve the final path and confirm it is still under the root.
        # The checks above are the real defence; this one catches a mistake in them. A
        # path that escapes the vault is a write outside the operator's data directory,
        # and the only symptom would be a skill that never appears.
        resolved_root = self.root.resolve()
        if not path.resolve().is_relative_to(resolved_root):
            raise ValueError(
                f"skill path escapes the skills root: {path} (root {resolved_root})"
            )

        path.write_text(skill.to_markdown(), encoding="utf-8")
        skill.path = path
        return path

    # --------------------------------------------------------------- reading
    def load(self, scope: str) -> list[Skill]:
        """Every skill stored for one scene.

        Reads only that scope's folder. There is no "load all" method on purpose: a caller
        that could enumerate every scope's skills would have a cross-scene read primitive,
        and the whole point of a private skill is that it is private.
        """
        if not _safe_scope(scope):
            return []
        directory = self.root / _dir_name(scope)
        if not directory.is_dir():
            return []

        resolved_root = self.root.resolve()
        out: list[Skill] = []
        for path in sorted(directory.glob("*.md")):
            try:
                # A symlinked ``.md`` would otherwise be followed out of this scope and
                # read another scene's skill — a cross-scene read through the one API
                # that is supposed to be scope-private.
                if not path.resolve().is_relative_to(resolved_root):
                    logger.warning("skipping skill outside the vault: %s", path.name)
                    continue
                out.append(self._parse(path, scope))
            except Exception as exc:
                # A malformed skill must not take out the rest: one bad file would
                # otherwise make the whole scene's skills unreadable.
                logger.warning("skipping unreadable skill %s: %s", path.name, exc)
        return out

    def _parse(self, path: Path, scope: str) -> Skill:
        raw = path.read_text(encoding="utf-8")
        meta: dict[str, str] = {}
        body = raw
        if raw.startswith("---"):
            parts = raw.split("---", 2)
            if len(parts) >= 3:
                for line in parts[1].strip().splitlines():
                    if ":" in line:
                        key, value = line.split(":", 1)
                        meta[key.strip()] = value.strip()
                body = parts[2].lstrip("\n")

        title = ""
        for line in body.splitlines():
            if line.startswith("# "):
                title = line[2:].strip()
                break

        return Skill(
            skill_id=meta.get("id") or path.stem,
            scope=meta.get("scope") or scope,
            title=title or path.stem,
            body=body,
            support=int(meta.get("support") or 0),
            confidence=float(meta.get("confidence") or 0.0),
            path=path,
        )

    def delete(self, scope: str, skill_id: str) -> bool:
        """Remove one skill. Returns whether a file was actually removed.

        ``skill_id`` is checked against :data:`_SKILL_ID_RE`, not :data:`_SCOPE_RE`: a
        slug may legitimately contain Chinese (see :func:`_slug`), while a scope may not.
        Sharing one pattern here rejected every skill whose topic was Chinese — the delete
        simply returned ``False`` and the file stayed, which looks like a permissions
        problem rather than a validation one.
        """
        if not _safe_scope(scope) or not _safe_skill_id(skill_id):
            return False
        path = self.root / _dir_name(scope) / f"{skill_id}.md"
        if not path.is_file():
            return False
        path.unlink()
        return True


def _slug(text: str) -> str:
    """Filesystem-safe identifier for a topic.

    Chinese topics are kept as-is rather than transliterated: the operator reads these
    file names, and ``bu-shu`` is harder to recognise than ``部署``. Only characters that
    are unsafe in a path are replaced.

    Truncation appends a short digest of the *full* topic. Without it, two topics sharing
    a 60-character prefix produced the same file name and the second ``save`` silently
    overwrote the first — a skill disappearing with no error, which is the worst shape a
    data-loss bug can take.
    """
    cleaned = re.sub(r"[^\w\u4e00-\u9fff-]+", "-", text, flags=re.UNICODE).strip("-")
    cleaned = cleaned or "skill"
    if len(cleaned) <= 60:
        return cleaned
    digest = hashlib.sha1(text.encode("utf-8")).hexdigest()[:8]
    return f"{cleaned[:51]}-{digest}"
