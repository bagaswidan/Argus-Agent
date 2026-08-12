"""Lock Manager — Argus Runtime (Spec §22).

Prevents double-execution of the same capability/workflow.
"""
from __future__ import annotations

import threading
import time
import uuid
from dataclasses import dataclass, field


class LockError(Exception):
    """Raised when a lock cannot be acquired."""


@dataclass
class LockHandle:
    """A held lock."""

    lock_id: str
    key: str
    owner: str
    acquired_at: float = field(default_factory=time.monotonic)
    ttl: float = 300.0

    @property
    def expired(self) -> bool:
        return time.monotonic() - self.acquired_at > self.ttl


class LockManager:
    """Distributed-ish lock manager with TTL (single-process)."""

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._locks: dict[str, LockHandle] = {}
        self._default_ttl = 300.0

    def acquire(self, key: str, owner: str = "", ttl: float | None = None, wait: float = 0.0) -> LockHandle:
        """Acquire lock on key. If wait>0, retry until available or timeout."""
        ttl = ttl or self._default_ttl
        deadline = time.monotonic() + wait
        while True:
            with self._lock:
                existing = self._locks.get(key)
                if existing is None or existing.expired:
                    handle = LockHandle(
                        lock_id=uuid.uuid4().hex[:12],
                        key=key,
                        owner=owner,
                        ttl=ttl,
                    )
                    self._locks[key] = handle
                    return handle
            if time.monotonic() >= deadline:
                raise LockError(f"Lock already held on '{key}' by {existing.owner}")
            time.sleep(0.05)

    def try_acquire(self, key: str, owner: str = "", ttl: float | None = None) -> LockHandle | None:
        """Non-blocking acquire; returns None if held."""
        try:
            return self.acquire(key, owner, ttl, wait=0.0)
        except LockError:
            return None

    def release(self, handle: LockHandle) -> bool:
        with self._lock:
            current = self._locks.get(handle.key)
            if current is not None and current.lock_id == handle.lock_id:
                del self._locks[handle.key]
                return True
            return False

    def is_locked(self, key: str) -> bool:
        with self._lock:
            existing = self._locks.get(key)
            if existing is None:
                return False
            if existing.expired:
                del self._locks[key]
                return False
            return True

    def owner_of(self, key: str) -> str | None:
        with self._lock:
            existing = self._locks.get(key)
            return existing.owner if existing and not existing.expired else None

    def active_count(self) -> int:
        with self._lock:
            # cleanup expired
            expired = [k for k, v in self._locks.items() if v.expired]
            for k in expired:
                del self._locks[k]
            return len(self._locks)


def create_lock_manager() -> LockManager:
    return LockManager()
