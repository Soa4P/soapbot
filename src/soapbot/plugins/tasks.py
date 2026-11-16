"""Persistent task registry: long-running plugin work with a completion timestamp.

The ops-handoff design (篇 10, absorbed as reference-ops-handoff.md 吸收 2) names a
gap: the approval bus records what the operator *approved*, but nothing records
whether the approved work *actually finished* — a task claimed done without a
completion marker is indistinguishable from a task still running.

Shape decided there and implemented here:

* a plugin **declares** a long-lived task (id, description, expected completion
  window) through the host surface, and **marks it done** when the work finishes —
  both through the same surface call, recorded per ``(plugin, task_id)`` so one
  plugin can never touch another's rows;
* the panel aggregates every task and flags the ones past their expected window
  without a ``done_at`` as 「未确认完成」 — "claimed but never confirmed finished";
* the timeout is a soft SLA signal rendered read-only, not an enforcement: the panel
  shows the state, it does not cancel anything.

Why a JSON file and not the encrypted per-plugin storage: the panel needs to read
this (that is the whole point — completion is *visible*), and plugin storage is
plugin-private by design. This file is operator-facing state, written by the host on
the plugin's behalf, at a fixed path for backup. Writes go through the same atomic
replace as the approvals file.
"""

from __future__ import annotations

import json
import logging
import os
import tempfile
import time
from dataclasses import dataclass
from pathlib import Path

logger = logging.getLogger(__name__)

_SCHEMA = 1


@dataclass(slots=True)
class TaskRecord:
    task_id: str
    description: str
    expected_within_hours: float
    declared_at: float
    done_at: float | None = None
    note: str = ""
    updated_at: float = 0.0

    def to_dict(self) -> dict[str, object]:
        return {
            "task_id": self.task_id,
            "description": self.description,
            "expected_within_hours": self.expected_within_hours,
            "declared_at": self.declared_at,
            "done_at": self.done_at,
            "note": self.note,
            "updated_at": self.updated_at,
        }

    @classmethod
    def from_dict(cls, task_id: str, entry: object) -> TaskRecord:
        data = entry if isinstance(entry, dict) else {}
        return cls(
            task_id=task_id,
            description=str(data.get("description", "")),
            expected_within_hours=float(data.get("expected_within_hours", 0)),
            declared_at=float(data.get("declared_at", 0)),
            done_at=(float(data["done_at"]) if data.get("done_at") is not None else None),
            note=str(data.get("note", "")),
            updated_at=float(data.get("updated_at", 0)),
        )

    def overdue(self, now: float) -> bool:
        """「未确认完成」: past its expected window with no done_at."""
        if self.done_at is not None:
            return False
        if self.expected_within_hours <= 0:
            return False  # no SLA declared — "running" is the honest state
        return now - self.declared_at > self.expected_within_hours * 3600


class PluginTaskStore:
    """``(plugin, task_id) -> TaskRecord``, persisted atomically to one JSON file."""

    def __init__(self, path: Path) -> None:
        self.path = path
        self._records: dict[str, dict[str, TaskRecord]] = {}
        self._loaded = False

    def _ensure_loaded(self) -> None:
        if self._loaded:
            return
        self._loaded = True
        try:
            payload = json.loads(self.path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            return  # missing or corrupt: start empty (a corrupt file is not a
            # permission record — an empty registry is the honest state)
        plugins = payload.get("plugins") if isinstance(payload, dict) else None
        if not isinstance(plugins, dict):
            return
        for plugin, tasks in plugins.items():
            if not isinstance(plugin, str) or not isinstance(tasks, dict):
                continue
            per_plugin: dict[str, TaskRecord] = {}
            for task_id, entry in tasks.items():
                if isinstance(task_id, str):
                    per_plugin[task_id] = TaskRecord.from_dict(task_id, entry)
            if per_plugin:
                self._records[plugin] = per_plugin

    def _flush(self) -> None:
        payload = {
            "schema": _SCHEMA,
            "plugins": {
                plugin: {tid: rec.to_dict() for tid, rec in sorted(tasks.items())}
                for plugin, tasks in sorted(self._records.items())
            },
        }
        data = json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n"
        self.path.parent.mkdir(parents=True, exist_ok=True)
        fd, tmp_name = tempfile.mkstemp(prefix=".plugin-tasks-", dir=str(self.path.parent))
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

    def update(
        self,
        *,
        plugin: str,
        task_id: str,
        description: str = "",
        expected_within_hours: float = 0.0,
        done: bool = False,
        note: str = "",
        now: float | None = None,
    ) -> TaskRecord:
        """Declare or update one task. ``done=True`` stamps ``done_at`` once.

        A done marker is sticky: later ``done=False`` updates change the note but
        cannot un-complete recorded work (un-claiming is /tree-undo's job in its own
        domain, and here an un-completion would be a lie about the past).
        """
        self._ensure_loaded()
        now = time.time() if now is None else now
        per_plugin = self._records.setdefault(plugin, {})
        existing = per_plugin.get(task_id)
        record = TaskRecord(
            task_id=task_id,
            description=description or (existing.description if existing else ""),
            expected_within_hours=(
                expected_within_hours if expected_within_hours > 0
                else (existing.expected_within_hours if existing else 0.0)
            ),
            declared_at=existing.declared_at if existing else now,
            done_at=(existing.done_at if existing and existing.done_at else (now if done else None)),
            note=note or (existing.note if existing else ""),
            updated_at=now,
        )
        per_plugin[task_id] = record
        self._flush()
        return record

    def for_plugin(self, plugin: str) -> dict[str, TaskRecord]:
        self._ensure_loaded()
        return dict(self._records.get(plugin, {}))

    def all_tasks(self) -> dict[str, dict[str, TaskRecord]]:
        self._ensure_loaded()
        return {
            plugin: dict(tasks) for plugin, tasks in self._records.items() if tasks
        }

    def clear(self) -> None:
        self._records.clear()
        self._loaded = True
