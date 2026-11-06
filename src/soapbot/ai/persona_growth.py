"""Automatic persona growth.

The operator chose "apply immediately": a model may rewrite a card without a review
step. That removes the isolation described in :mod:`soapbot.ai.persona` — persona
text used to be trusted input, and part of it is now model output. What remains is
recoverability, so this module spends its effort there:

* every write appends an immutable version before the live card changes;
* growth may only touch the prose fields, never identity or enablement;
* a per-card hourly budget bounds a runaway loop;
* injection patterns are recorded but do not block (that was the choice), so the
  panel can show *why* a card changed rather than only that it changed.
"""

from __future__ import annotations

import logging
import time
from collections.abc import Callable
from typing import Any

from soapbot.ai.persona import (
    PersonaStore,
    dump_persona_file,
    persona_from_payload,
    persona_to_payload,
)
from soapbot.ai.persona_history import PersonaHistory, PersonaVersion
from soapbot.security.injection import redact, scan_injection

logger = logging.getLogger(__name__)

#: Fields a growth write may change.
#:
#: Everything else is either identity (``id``, ``name``), operator-owned switches
#: (``enabled``, ``wake_words``, ``locale``) or few-shot turns (``examples``) that a
#: model would read as instructions. Allowing those would let one successful
#: injection rename the card, wake it on any message, or inject fake dialogue.
GROWABLE_FIELDS = frozenset({"system_prompt", "style", "banned_words", "max_reply_chars"})


class PersonaGrowthError(RuntimeError):
    """A growth write was refused.

    Every message is constructed in this module from a fixed vocabulary plus numbers
    (budget, size), never from provider text or user content, so it is safe to show.
    ``public_detail`` exists to say that out loud: the API uses it instead of
    ``str(exc)``, which is what keeps the boundary gate from treating this as a
    leaked exception.
    """

    def public_detail(self) -> str:
        return str(self)[:200]


class PersonaGrowth:
    """Applies model-authored changes to a persona card, keeping a way back."""

    def __init__(
        self,
        history: PersonaHistory,
        *,
        max_chars: int = 2000,
        per_hour: int = 6,
        enabled: bool = True,
        clock: Callable[[], float] | None = None,
    ) -> None:
        self.history = history
        self.max_chars = max(1, int(max_chars))
        self.per_hour = max(1, int(per_hour))
        self.enabled = bool(enabled)
        # Injectable so the hourly budget can be tested without sleeping an hour.
        self._clock = clock or time.time

    # ---------------------------------------------------------------- helpers
    def usage(self, persona_id: str) -> dict[str, Any]:
        return {
            "enabled": self.enabled,
            "max_chars": self.max_chars,
            "per_hour": self.per_hour,
            "used_this_hour": self.history.count_since(
                persona_id, self._clock() - 3600, actor="model"
            ),
        }

    @staticmethod
    def _audit(action: str, outcome: str, detail: str) -> None:
        try:
            from soapbot.security.audit import get_audit_log

            get_audit_log().record(
                kind="persona", action=action, outcome=outcome, detail=detail
            )
        except Exception as exc:
            logger.warning("persona audit failed action=%s err=%s", action, type(exc).__name__)

    # ---------------------------------------------------------------- writes
    def seed_baseline(self, store: PersonaStore) -> int:
        """Record one version per card that has no history yet.

        Without this, the card as it exists on disk is not restorable: the first
        growth write would be version 2 and version 1 would point at nothing, so
        "roll back to before the model touched it" would have no target.
        """
        created = 0
        for persona in store.all():
            if self.history.list_versions(persona.id, limit=1):
                continue
            self.history.append(
                persona_id=persona.id,
                payload=persona_to_payload(persona),
                content=dump_persona_file(persona),
                actor="system",
            )
            created += 1
        return created

    def apply(
        self,
        store: PersonaStore,
        persona_id: str,
        changes: dict[str, Any],
        *,
        source_session: str = "",
        trace_id: str = "",
        actor: str = "model",
    ) -> PersonaVersion:
        """Apply ``changes`` to the live card and return the new version."""
        if not self.enabled:
            raise PersonaGrowthError("persona growth is disabled")
        persona = store.get(persona_id)
        if persona is None:
            raise PersonaGrowthError("no such persona")
        if not changes:
            raise PersonaGrowthError("no changes supplied")
        unknown = set(changes) - GROWABLE_FIELDS
        if unknown:
            raise PersonaGrowthError(
                "fields not growable: " + ", ".join(sorted(unknown))
            )

        payload = persona_to_payload(persona)
        for key, value in changes.items():
            if key == "banned_words":
                if not isinstance(value, list):
                    raise PersonaGrowthError("banned_words must be a list")
                payload[key] = [redact(str(word))[:32] for word in value][:50]
            elif key == "max_reply_chars":
                try:
                    payload[key] = max(1, min(int(value), 4000))
                except (TypeError, ValueError) as exc:
                    raise PersonaGrowthError("max_reply_chars must be an integer") from exc
            else:
                payload[key] = redact(str(value))

        payload["version"] = persona.version + 1
        candidate = persona_from_payload(payload, persona_id)
        rendered = dump_persona_file(candidate)
        if len(rendered) > self.max_chars:
            self._audit(
                "grow",
                "block",
                f"id={persona_id} reason=too_large chars={len(rendered)} limit={self.max_chars}",
            )
            raise PersonaGrowthError(
                f"card would be {len(rendered)} characters; limit is {self.max_chars}"
            )

        used = self.history.count_since(
            persona_id, self._clock() - 3600, actor="model"
        )
        if used >= self.per_hour:
            self._audit(
                "grow", "block", f"id={persona_id} reason=rate_limit used={used}"
            )
            raise PersonaGrowthError(
                f"hourly growth budget reached ({used}/{self.per_hour})"
            )

        hits = scan_injection(rendered)
        version = self.history.append(
            persona_id=persona_id,
            payload=payload,
            content=rendered,
            source_session=source_session,
            trace_id=trace_id,
            actor=actor,
            flagged=bool(hits),
        )
        # Live store last: a failed save leaves the old card serving and the version
        # row still describes what was *attempted*, which is what an operator wants
        # when asking "what happened at 03:12".
        store.save(candidate)
        self._audit(
            "grow",
            "allow",
            "id={} version={} fields={} flagged={} hits={}".format(
                persona_id,
                version.version,
                ",".join(sorted(changes)),
                1 if hits else 0,
                ",".join(hits) or "-",
            ),
        )
        return version

    def rollback(
        self,
        store: PersonaStore,
        persona_id: str,
        version: int,
        *,
        actor: str = "operator",
    ) -> PersonaVersion:
        """Restore ``version`` as a new version. History is never rewritten."""
        target = self.history.get(persona_id, version)
        if target is None:
            raise PersonaGrowthError("no such version")
        current = store.get(persona_id)
        payload = dict(target.payload)
        payload["version"] = (current.version if current else target.version) + 1
        restored = persona_from_payload(payload, persona_id)
        rendered = dump_persona_file(restored)
        created = self.history.append(
            persona_id=persona_id,
            payload=payload,
            content=rendered,
            source_session=f"rollback:{version}",
            actor=actor,
        )
        store.save(restored)
        self._audit(
            "rollback",
            "allow",
            f"id={persona_id} from={version} new_version={created.version}",
        )
        return created
