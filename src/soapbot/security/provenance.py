"""Parameter-level provenance for tool arguments.

Action-level permission checks answer "may this caller use this tool?" They say
nothing about *where an argument came from*. A model-produced ``url`` is a different
object from an operator-configured one even when both parse as the same string: the
former is untrusted output selecting an external resource, the latter is configuration.
Treating them identically is the gap between action-level and parameter-level control.

Design
------
* The tag lives on a ``dict`` **subclass as an attribute**, not as a key. Model output
  is JSON and can never set a Python attribute, so the origin cannot be forged from
  the prompt, and every existing handler still sees an ordinary dict.
* Parsing (``json.loads`` in the model stage) establishes structure only. This module
  makes the authorisation decision and re-validates the tag it was handed — it does not
  trust a "already checked" claim from upstream.
* The check runs inside ``ToolRegistry.invoke``, immediately before dispatch. There is
  no check-then-act window in which another caller could swap the arguments.
* No prose inspection. The decision is set membership over a host-owned origin and a
  set of parameter names the host has actually validated.

Scope of this batch: outbound resource identifiers (``url``/``uri``/``endpoint``/
``host``/``address``), which share a boundary with ``plugins.sandbox``'s URL checks.
Local paths and command arguments need their own host-side validators before they can
join this set; leaving them out is an explicit statement of what is not yet covered,
not an implicit grant.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field
from typing import Any

OPERATOR = "operator"
MODEL = "model"
TOOL_RESULT = "tool_result"
LOG = "log"
TELEMETRY = "telemetry"

#: Measurements of the system, not instructions for it. A tool result that was fed
#: back into the prompt is still data: letting it select the next tool's resource is
#: exactly the "log/telemetry as command channel" path these rules close.
DATA_ONLY_ORIGINS = frozenset({LOG, TELEMETRY, TOOL_RESULT})
KNOWN_ORIGINS = frozenset({OPERATOR, MODEL, *DATA_ONLY_ORIGINS})

RESOURCE_PARAMETERS = frozenset({"url", "uri", "endpoint", "host", "address"})


@dataclass(frozen=True, slots=True)
class Provenance:
    origin: str
    #: Parameter names for which a host-side deterministic check has already passed.
    vetted: frozenset[str] = field(default_factory=frozenset)

    def well_formed(self) -> bool:
        return self.origin in KNOWN_ORIGINS and all(
            isinstance(name, str) and name for name in self.vetted
        )


class ToolArguments(dict[str, Any]):
    """An ordinary argument dict with a host-owned origin tag.

    Subclassing ``dict`` is deliberate: ``isinstance(arguments, dict)``, handler
    signatures, JSON serialisation and existing tests all keep working unchanged.
    """

    def __init__(
        self, *args: Any, provenance: Provenance, **kwargs: Any
    ) -> None:
        super().__init__(*args, **kwargs)
        self.provenance = provenance


def mark_vetted(arguments: ToolArguments, name: str) -> None:
    """Record that a host-side check passed for ``name``. Host code only.

    There is no way to call this from model output: the model produces JSON, and this
    mutates a Python attribute on an object the host constructed after parsing.
    """
    arguments.provenance = Provenance(
        origin=arguments.provenance.origin,
        vetted=arguments.provenance.vetted | {name},
    )


@dataclass(frozen=True, slots=True)
class Admission:
    allowed: bool
    reason: str = "ok"


def vet_arguments(
    arguments: Mapping[str, Any],
    *,
    resource_check: Any = None,
) -> Admission:
    """Deterministic admission at the action boundary.

    An untagged mapping is a call constructed by host code (a plugin command, a test,
    an internal caller) — no model output crossed this boundary, so there is nothing to
    trace. Every path that *does* carry model output must tag it; a static test pins
    that wiring so a future refactor cannot silently drop it.

    ``resource_check`` is injected by the host and returns a bool. Keeping it outside
    this module means the authorisation rule never depends on parsing, text content or
    a network call made here — and a checker that cannot run is a denial, not a pass.
    """
    provenance = getattr(arguments, "provenance", None)
    if provenance is None:
        return Admission(True, "host_constructed")
    if not isinstance(provenance, Provenance) or not provenance.well_formed():
        # Re-validated here, not trusted from the caller.
        return Admission(False, "forged_provenance")
    if provenance.origin in DATA_ONLY_ORIGINS:
        return Admission(False, "data_only_origin")
    if provenance.origin == MODEL:
        pending = RESOURCE_PARAMETERS.intersection(arguments) - provenance.vetted
        for name in sorted(pending):
            value = arguments.get(name)
            if (
                resource_check is None
                or not isinstance(value, str)
                or not value
                or not resource_check(value)
            ):
                return Admission(False, f"unvetted_resource:{name}")
    return Admission(True, f"origin={provenance.origin}")
