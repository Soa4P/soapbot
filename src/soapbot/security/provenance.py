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

Coverage, and what each kind of parameter needs before it can be accepted from model
output (audit S-AIM-05 — the first version covered only resources):

* **resources** (``url``/``uri``/``endpoint``/``host``/``address``) — the host supplies a
  deterministic checker (the same SSRF policy the plugin sandbox uses);
* **paths** (``path``/``file``/``filename``/``dir``/``directory``) — validated here:
  relative, no ``..``, no drive letter, no NUL, bounded length. A tool that genuinely
  needs an absolute path must have the host call :func:`mark_vetted` on it;
* **amounts** (``amount``/``amount_minor``/``price``/``cost``/``quantity``) — finite,
  non-negative number. The ledger's own checks stay where they are; this only stops a
  string, ``nan`` or a negative number from reaching a spend path at all;
* **commands** (``command``/``cmd``/``script``/``shell``) — **never** accepted from model
  output. There is no validator that makes a model-authored shell string safe: any check
  is a blocklist of metacharacters, and the interpreter behind it decides what runs. A
  host that wants to run something constructs the argv itself and marks it vetted.

Leaving a parameter out of these sets is an explicit statement of what is not covered, not
an implicit grant — the sets are closed by name on purpose.
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

PATH_PARAMETERS = frozenset(
    {"path", "file", "filename", "dir", "directory", "target_path", "output_path"}
)

AMOUNT_PARAMETERS = frozenset({"amount", "amount_minor", "price", "cost", "quantity"})

COMMAND_PARAMETERS = frozenset({"command", "cmd", "script", "shell"})

#: Bound for a model-supplied path. Long enough for a nested relative path, short enough
#: that nothing downstream has to think about truncation.
MAX_PATH_CHARS = 512


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


def path_is_safe(value: object) -> bool:
    """A model-supplied path that cannot leave its intended directory.

    Relative only: an absolute path is either a host decision (mark it vetted) or an
    attempt to read ``/etc/...`` / ``C:/Windows/...``. ``..`` in any position, a NUL,
    a drive letter and over-long input are refused for the same reason. Symlinks cannot
    be judged from the string, so containment remains the caller's job — this is the
    cheap deterministic half, and saying so is better than implying it is complete.
    """
    if not isinstance(value, str) or not value or len(value) > MAX_PATH_CHARS:
        return False
    if chr(0) in value:
        return False
    normalised = value.replace("\\", "/")
    if normalised.startswith("/") or normalised.startswith("~"):
        return False
    if len(normalised) > 1 and normalised[1] == ":":
        return False
    return ".." not in normalised.split("/")


def amount_is_sane(value: object) -> bool:
    """A model-supplied amount: a real, non-negative number and nothing else.

    ``bool`` is excluded explicitly — it is an ``int`` subclass, and ``True`` as a spend
    amount is a bug that would be very hard to see afterwards.
    """
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return False
    if isinstance(value, float) and (value != value or value in (float("inf"), float("-inf"))):
        return False
    return value >= 0


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

        for name in sorted(PATH_PARAMETERS.intersection(arguments) - provenance.vetted):
            if not path_is_safe(arguments.get(name)):
                return Admission(False, f"unsafe_path:{name}")

        for name in sorted(AMOUNT_PARAMETERS.intersection(arguments) - provenance.vetted):
            if not amount_is_sane(arguments.get(name)):
                return Admission(False, f"insane_amount:{name}")

        # No validator is consulted: a model-authored command cannot be made safe by
        # checking it harder.
        for name in sorted(COMMAND_PARAMETERS.intersection(arguments) - provenance.vetted):
            return Admission(False, f"unvetted_command:{name}")
    return Admission(True, f"origin={provenance.origin}")
