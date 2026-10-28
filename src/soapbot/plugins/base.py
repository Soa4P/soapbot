"""Plugin base class and the contract a plugin author implements.

Why a base class at all
-----------------------
Optional, but it documents the lifecycle in one place and gives the loader a
predictable shape to call. A plugin may also be a plain object with ``setup`` —
the loader only requires ``setup(ctx)``.

Lifecycle
---------
    manifest validated -> imported -> constructed -> setup(ctx) -> [serving]
        -> teardown() -> modules purged

``setup`` is where registration happens and where a plugin should acquire
resources. ``teardown`` must be safe to call twice and must not raise: the loader
calls it during unload and during a failed reload, and a raising teardown would
otherwise prevent the plugin from being removed at all.
"""

from __future__ import annotations

from typing import Any

from soapbot.plugins.context import PluginContext


class Plugin:
    """Base class for plugins.

    Subclasses override :meth:`setup` and optionally :meth:`teardown`.
    """

    #: Filled in by the loader from the manifest, for convenience.
    name: str = ""
    version: str = ""

    def __init__(self) -> None:
        self.ctx: PluginContext | None = None
        self._teardown_done = False

    async def setup(self, ctx: PluginContext) -> None:
        """Register commands/tools/hooks. Must not perform long blocking work."""
        self.ctx = ctx

    async def teardown(self) -> None:
        """Release resources. Must be idempotent and must not raise."""
        self._teardown_done = True
        self.ctx = None

    # -- helpers a plugin may use ------------------------------------------------
    def require_ctx(self) -> PluginContext:
        if self.ctx is None:
            raise RuntimeError(
                "plugin is not set up; setup() has not run or teardown() already did"
            )
        return self.ctx


def ok(reply: str = "", **extras: Any) -> dict[str, Any]:
    """Conventional success return value for a plugin handler.

    Handlers may return a plain string, this dict, or a
    :class:`soapbot.plugins.context.PluginResult`. The host normalises all three,
    so plugin authors are not forced to learn one shape — but the host always
    applies scrubbing and length limits regardless of what is returned.
    """
    return {"reply": reply, "extras": extras}


def fail(reason: str = "操作失败") -> dict[str, Any]:
    """Conventional failure return value. ``reason`` is shown to the user.

    Never pass an exception message here: it can contain SQL, paths or data the
    caller must not see.
    """
    return {"reply": reason, "error": True}
