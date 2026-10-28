"""Background scheduling for the running bot.

What actually needs a clock
---------------------------
Three things, and each was previously documented as "driven by the app" while no such
driver existed:

1. **Plugin cron jobs.** ``PluginCronRunner.run_due`` checks expressions but has to be
   called by something; without a tick, a plugin's ``@ctx.cron("0 9 * * *")`` is a
   function nobody ever runs.
2. **Expired budget reservations.** ``BudgetStore.sweep_expired`` releases quota for
   requests nobody answered. The read path also expires what it touches, but relying
   on that means an idle group keeps its allowance locked until someone happens to
   look at it — which is exactly when it does not matter.
3. Nothing else. Persona and config files are read at startup; session locks are
   per-event.

Why one tick instead of one scheduler job per plugin job
--------------------------------------------------------
Plugins are loaded and unloaded at runtime through the API. Registering a scheduler
entry per job means every lifecycle event has to add or remove jobs, and a window
exists where a half-registered job fires or is silently lost. A single tick over the
*current* loaded set has one source of truth and cannot drift from it.

Why APScheduler at all, if there is only one job
------------------------------------------------
It brings misfire policy, single-instance enforcement and next-run introspection. The
alternative is a hand-rolled ``asyncio.sleep`` loop that reinvents those and, on a
long-running deployment, quietly accumulates drift. It is also already a declared
dependency; leaving it unused while writing a bespoke timer is the pattern that
produced the "isolation layer nobody called" problem in this project once already.
"""

from __future__ import annotations

import logging
from typing import Any
from zoneinfo import ZoneInfo

from apscheduler.schedulers.asyncio import AsyncIOScheduler

from soapbot.config import settings

logger = logging.getLogger(__name__)

JOB_TICK = "runtime-tick"


class RuntimeScheduler:
    """Drives the periodic work of a :class:`soapbot.core.runtime.BotRuntime`."""

    def __init__(self, runtime, *, tick_seconds: float | None = None, timezone: str = "") -> None:
        self.runtime = runtime
        self.tick_seconds = float(
            settings.scheduler_tick_seconds if tick_seconds is None else tick_seconds
        )
        self._tz = ZoneInfo(timezone or settings.default_timezone)
        self._scheduler = AsyncIOScheduler(timezone=self._tz)
        self._started = False
        self.ticks = 0
        self.last_error = ""

    # ------------------------------------------------------------------ lifecycle
    def start(self) -> None:
        """Begin ticking. Must be called from inside a running event loop."""
        if self._started:
            return
        self._scheduler.add_job(
            self.tick,
            trigger="interval",
            seconds=self.tick_seconds,
            id=JOB_TICK,
            name="plugin cron + budget expiry",
            # ``coalesce`` collapses missed runs into one: after a suspend or a long
            # stall we want the current state handled, not a burst replaying every
            # interval that was skipped.
            coalesce=True,
            # One at a time. Two overlapping ticks could run the same cron job twice,
            # because the due-time bookkeeping happens at the start of the run.
            max_instances=1,
            misfire_grace_time=max(1, int(self.tick_seconds)),
            replace_existing=True,
        )
        self._scheduler.start()
        self._started = True
        logger.info("runtime scheduler started (tick=%.1fs, tz=%s)", self.tick_seconds, self._tz)

    def shutdown(self, *, wait: bool = False) -> None:
        if not self._started:
            return
        try:
            self._scheduler.shutdown(wait=wait)
        except Exception as exc:  # pragma: no cover - shutdown must not raise
            logger.warning("scheduler shutdown failed: %s", exc)
        self._started = False
        logger.info("runtime scheduler stopped after %d tick(s)", self.ticks)

    # ---------------------------------------------------------------------- work
    async def tick(self) -> None:
        """One pass over everything periodic.

        Each unit is isolated: a plugin whose cron job explodes must not prevent the
        budget sweep from releasing quota, and neither may kill the scheduler loop.
        """
        self.ticks += 1

        plugins = getattr(self.runtime, "plugins", None)
        if plugins is not None:
            try:
                ran = await plugins.cron.run_due()
                if ran:
                    logger.info("plugin cron ran %d job(s)", ran)
            except Exception as exc:
                self.last_error = f"cron: {type(exc).__name__}: {exc}"
                logger.exception("plugin cron tick failed")

        budget = getattr(self.runtime, "budget", None)
        if budget is not None:
            try:
                expired = await budget.sweep_expired()
                if expired:
                    logger.info("budget sweep expired %d request(s)", expired)
            except Exception as exc:
                self.last_error = f"budget: {type(exc).__name__}: {exc}"
                logger.exception("budget sweep failed")

    # ------------------------------------------------------------- introspection
    def status(self) -> dict[str, Any]:
        jobs: list[dict[str, Any]] = []
        if self._started:
            for job in self._scheduler.get_jobs():
                nxt = getattr(job, "next_run_time", None)
                jobs.append(
                    {
                        "id": job.id,
                        "name": job.name or "",
                        "next_run_at": nxt.timestamp() if nxt else 0.0,
                        "next_run_iso": nxt.isoformat() if nxt else "",
                    }
                )
        plugins = getattr(self.runtime, "plugins", None)
        return {
            "running": self._started,
            "tick_seconds": self.tick_seconds,
            "timezone": str(self._tz),
            "ticks": self.ticks,
            "last_error": self.last_error,
            "jobs": jobs,
            "plugin_cron": plugins.cron.schedule() if plugins is not None else [],
        }


__all__ = ["JOB_TICK", "RuntimeScheduler"]
