"""Scheduler — Argus Runtime (Spec §22).

Simple async task scheduler with priority and timeout.
"""
from __future__ import annotations

import asyncio
import time
import uuid
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from typing import Any


@dataclass
class ScheduledTask:
    """A scheduled task."""

    id: str = field(default_factory=lambda: uuid.uuid4().hex[:12])
    name: str = ""
    priority: int = 0  # higher runs first
    timeout: float = 30.0
    created_at: float = field(default_factory=time.monotonic)
    status: str = "pending"  # pending | running | completed | failed | cancelled


class Scheduler:
    """Async scheduler: submit coroutine factories, run with priority."""

    def __init__(self, max_workers: int = 4) -> None:
        self._max_workers = max_workers
        self._queue: list[ScheduledTask] = []
        self._running: dict[str, ScheduledTask] = {}
        self._completed: list[ScheduledTask] = []
        self._max_completed = 100

    def submit(
        self,
        fn: Callable[..., Awaitable[Any]],
        *args: Any,
        name: str = "",
        priority: int = 0,
        timeout: float = 30.0,
        **kwargs: Any,
    ) -> ScheduledTask:
        """Submit a task. Returns the task handle immediately."""
        task = ScheduledTask(name=name, priority=priority, timeout=timeout)
        self._queue.append(task)
        self._queue.sort(key=lambda t: t.priority, reverse=True)
        # Store the coroutine factory + args on the task
        task._fn = fn  # type: ignore[attr-defined]
        task._args = args  # type: ignore[attr-defined]
        task._kwargs = kwargs  # type: ignore[attr-defined]
        return task

    async def run_once(self) -> ScheduledTask | None:
        """Execute the next highest-priority task to completion. Returns the task."""
        if not self._queue:
            return None
        if len(self._running) >= self._max_workers:
            return None
        task = self._queue.pop(0)
        fn = getattr(task, "_fn", None)
        if fn is None:
            task.status = "cancelled"
            return task
        task.status = "running"
        self._running[task.id] = task
        try:
            await asyncio.wait_for(fn(*task._args, **task._kwargs), timeout=task.timeout)  # type: ignore[attr-defined]
            task.status = "completed"
        except TimeoutError:
            task.status = "failed"
            task.timeout = task.timeout  # mark
        except Exception:
            task.status = "failed"
        finally:
            self._running.pop(task.id, None)
            self._completed.append(task)
            if len(self._completed) > self._max_completed:
                self._completed = self._completed[-self._max_completed:]
        return task

    async def run_all(self) -> list[ScheduledTask]:
        """Drain the queue (respecting worker limit)."""
        results: list[ScheduledTask] = []
        while self._queue:
            task = await self.run_once()
            if task:
                results.append(task)
            # Workers saturated; yield to let running tasks finish
            elif self._running:
                await asyncio.sleep(0.05)
            else:
                break
        return results

    def pending_count(self) -> int:
        return len(self._queue)

    def running_count(self) -> int:
        return len(self._running)

    def completed(self, limit: int = 20) -> list[ScheduledTask]:
        return list(self._completed[-limit:])

    def cancel(self, task_id: str) -> bool:
        for i, t in enumerate(self._queue):
            if t.id == task_id:
                t.status = "cancelled"
                self._queue.pop(i)
                return True
        return False


def create_scheduler(max_workers: int = 4) -> Scheduler:
    return Scheduler(max_workers=max_workers)
