"""Event Bus — Argus Core Foundation.

High-performance async event bus with:
- Priority-based delivery (CRITICAL > HIGH > NORMAL > LOW)
- Wildcard subscriptions (test.*)
- Dead letter queue for unhandled events
- Backpressure handling
- Sync + async handler support
"""
from __future__ import annotations

import asyncio
import fnmatch
import logging
import uuid
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import datetime
from enum import IntEnum
from typing import Any, Callable, Awaitable

from pydantic import BaseModel, Field

log = logging.getLogger("argus.events")


class EventPriority(IntEnum):
    """Event delivery priority."""

    LOW = 0
    NORMAL = 50
    HIGH = 100
    CRITICAL = 200


class Event(BaseModel):
    """Immutable event."""

    type: str
    payload: dict[str, Any] = Field(default_factory=dict)
    source: str = "unknown"
    correlation_id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    timestamp: datetime = Field(default_factory=datetime.utcnow)
    metadata: dict[str, Any] = Field(default_factory=dict)

    model_config = {"frozen": True}


Handler = Callable[[Event], Any] | Callable[[Event], Awaitable[Any]]


@dataclass
class Subscription:
    """Active subscription."""

    event_pattern: str
    handler: Handler
    priority: EventPriority = EventPriority.NORMAL
    _active: bool = True
    _bus: Any = None  # set by bus on subscribe

    def unsubscribe(self) -> None:
        """Mark subscription as inactive and remove from bus."""
        if not self._active:
            return
        self._active = False
        if self._bus:
            bus = self._bus
            self._bus = None
            bus._remove_subscription(self)

    @property
    def active(self) -> bool:
        return self._active

    def matches(self, event_type: str) -> bool:
        """Check if event type matches pattern (supports wildcards)."""
        return fnmatch.fnmatch(event_type, self.event_pattern)

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.unsubscribe()
        return False


class EventBus:
    """Async event bus with priority delivery."""

    def __init__(
        self,
        max_queue_size: int = 10000,
        worker_count: int = 4,
        enable_priority: bool = True,
        dead_letter_enabled: bool = True,
        dead_letter_max_size: int = 1000,
    ):
        self._max_queue_size = max_queue_size
        self._worker_count = worker_count
        self._enable_priority = enable_priority
        self._dead_letter_enabled = dead_letter_enabled
        self._dead_letter_max_size = dead_letter_max_size

        self._subscriptions: dict[str, list[Subscription]] = defaultdict(list)
        self._wildcard_subscriptions: list[Subscription] = []
        self._queue: asyncio.PriorityQueue[tuple[int, int, Event]] = asyncio.PriorityQueue(
            maxsize=max_queue_size
        )
        self._dead_letters: list[Event] = []
        self._workers: list[asyncio.Task] = []
        self._running = False
        self._seq = 0  # for FIFO within same priority
        self._lock = asyncio.Lock()

    async def start(self) -> None:
        """Start worker tasks."""
        if self._running:
            return
        self._running = True
        self._workers = [
            asyncio.create_task(self._worker(f"worker-{i}")) for i in range(self._worker_count)
        ]

    async def stop(self) -> None:
        """Stop worker tasks."""
        self._running = False
        # Wait for queue to drain
        await self._queue.join()
        for w in self._workers:
            w.cancel()
        await asyncio.gather(*self._workers, return_exceptions=True)
        self._workers.clear()

    # ----- subscription -----

    def subscribe(
        self,
        event_pattern: str,
        handler: Handler,
        priority: EventPriority = EventPriority.NORMAL,
    ) -> Subscription:
        """Subscribe to events matching pattern."""
        sub = Subscription(event_pattern, handler, priority)
        sub._bus = self
        if "*" in event_pattern or "?" in event_pattern:
            self._wildcard_subscriptions.append(sub)
        else:
            self._subscriptions[event_pattern].append(sub)
        # Sort by priority (highest first)
        self._sort_subscriptions(event_pattern)
        return sub

    def _sort_subscriptions(self, pattern: str) -> None:
        subs = self._subscriptions.get(pattern, [])
        subs.sort(key=lambda s: s.priority, reverse=True)

    def unsubscribe(self, subscription: Subscription) -> None:
        """Remove a subscription."""
        subscription.unsubscribe()

    def _remove_subscription(self, sub: Subscription) -> None:
        """Internal: remove subscription from internal structures."""
        if sub in self._wildcard_subscriptions:
            self._wildcard_subscriptions.remove(sub)
        else:
            for subs in self._subscriptions.values():
                if sub in subs:
                    subs.remove(sub)
                    break

    # ----- publishing -----

    async def publish(self, event: Event) -> None:
        """Publish an event to the bus."""
        if not self._running:
            await self.start()

        # Priority queue: lower number = higher priority
        # We use negative priority so higher priority comes first
        priority_key = -event.metadata.get("priority", EventPriority.NORMAL)
        if isinstance(priority_key, EventPriority):
            priority_key = -priority_key

        await self._queue.put((priority_key, self._seq, event))
        self._seq += 1

    async def flush(self) -> None:
        """Wait for all queued events to be processed."""
        await self._queue.join()

    # ----- worker -----

    async def _worker(self, name: str) -> None:
        while self._running:
            try:
                _, _, event = await asyncio.wait_for(self._queue.get(), timeout=0.1)
                await self._deliver(event)
                self._queue.task_done()
            except asyncio.TimeoutError:
                continue
            except asyncio.CancelledError:
                break
            except Exception as e:
                log.exception("Worker %s error: %s", name, e)

    async def _deliver(self, event: Event) -> None:
        # Find matching subscriptions
        handlers = self._get_matching_handlers(event.type)

        if not handlers and self._dead_letter_enabled:
            self._add_dead_letter(event)
            return

        # Deliver to all matching handlers
        tasks = []
        for sub in handlers:
            if not sub.active:
                continue
            tasks.append(self._call_handler(sub, event))

        if tasks:
            await asyncio.gather(*tasks, return_exceptions=True)

    def _get_matching_handlers(self, event_type: str) -> list[Subscription]:
        handlers = []

        # Exact match
        for sub in self._subscriptions.get(event_type, []):
            if sub.active:
                handlers.append(sub)

        # Wildcard matches
        for sub in self._wildcard_subscriptions:
            if sub.active and sub.matches(event_type):
                handlers.append(sub)

        # Sort by priority
        handlers.sort(key=lambda s: s.priority, reverse=True)
        return handlers

    async def _call_handler(self, sub: Subscription, event: Event) -> None:
        try:
            result = sub.handler(event)
            if asyncio.iscoroutine(result):
                await result
        except Exception as e:
            log.exception("Handler error for %s: %s", event.type, e)
            # Handler exceptions don't stop other handlers

    def _add_dead_letter(self, event: Event) -> None:
        if len(self._dead_letters) >= self._dead_letter_max_size:
            self._dead_letters.pop(0)
        self._dead_letters.append(event)

    # ----- utilities -----

    def get_dead_letters(self) -> list[Event]:
        """Get dead letter events."""
        return list(self._dead_letters)

    def clear_dead_letters(self) -> None:
        """Clear dead letter queue."""
        self._dead_letters.clear()

    @property
    def queue_size(self) -> int:
        return self._queue.qsize()

    @property
    def subscription_count(self) -> int:
        count = len(self._wildcard_subscriptions)
        for subs in self._subscriptions.values():
            count += len(subs)
        return count
