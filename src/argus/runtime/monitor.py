"""Runtime Monitor — Argus (Refinement 2).

Tracks active tasks, their status, and resource usage over time.
Provides snapshots for the dashboard and health checks.
"""
from __future__ import annotations

import contextlib
import threading
import uuid
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from collections.abc import Callable


@dataclass
class TaskStatus:
    """Snapshot of one task's state."""

    task_id: str
    name: str
    status: str  # running | completed | failed | cancelled
    started_at: str
    finished_at: str | None = None
    duration_ms: int = 0
    error: str | None = None
    attempts: int = 1


class RuntimeMonitor:
    """Tracks task lifecycle and produces summary snapshots."""

    def __init__(self, max_history: int = 500):
        self._lock = threading.Lock()
        self._active: dict[str, TaskStatus] = {}
        self._history: list[TaskStatus] = []
        self._max_history = max_history
        self._hooks: list[Callable[[TaskStatus], None]] = []

    def on_update(self, hook: Callable[[TaskStatus], None]) -> None:
        self._hooks.append(hook)

    def start(self, name: str, task_id: str | None = None) -> str:
        tid = task_id or uuid.uuid4().hex[:12]
        status = TaskStatus(
            task_id=tid,
            name=name,
            status="running",
            started_at=datetime.now(UTC).isoformat(),
        )
        with self._lock:
            self._active[tid] = status
        self._notify(status)
        return tid

    def finish(self, task_id: str, status: str = "completed", error: str | None = None) -> bool:
        with self._lock:
            task = self._active.pop(task_id, None)
            if task is None:
                return False
            task.status = status
            task.error = error
            task.finished_at = datetime.now(UTC).isoformat()
            start = datetime.fromisoformat(task.started_at)
            task.duration_ms = int(
                (datetime.now(UTC) - start).total_seconds() * 1000,
            )
            self._history.append(task)
            if len(self._history) > self._max_history:
                self._history = self._history[-self._max_history:]
        self._notify(task)
        return True

    def get(self, task_id: str) -> TaskStatus | None:
        with self._lock:
            return self._active.get(task_id)

    def active_tasks(self) -> list[TaskStatus]:
        with self._lock:
            return list(self._active.values())

    def history(self, limit: int = 50) -> list[TaskStatus]:
        with self._lock:
            return list(self._history[-limit:])

    def summary(self) -> dict[str, Any]:
        with self._lock:
            completed = sum(1 for t in self._history if t.status == "completed")
            failed = sum(1 for t in self._history if t.status == "failed")
            total_runtime = sum(t.duration_ms for t in self._history)
        return {
            "active": len(self._active),
            "completed": completed,
            "failed": failed,
            "total_tasks": completed + failed,
            "total_runtime_ms": total_runtime,
            "avg_runtime_ms": (total_runtime // (completed + failed)) if (completed + failed) else 0,
        }

    def _notify(self, task: TaskStatus) -> None:
        for hook in self._hooks:
            with contextlib.suppress(Exception):
                hook(task)


def create_runtime_monitor(max_history: int = 500) -> RuntimeMonitor:
    return RuntimeMonitor(max_history=max_history)
