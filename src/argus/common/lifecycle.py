"""Lifecycle Manager — Argus Core Foundation.

Manages the application lifecycle state machine and lifecycle hooks.
Lifecycle hooks run in registration order and are subject to a configurable
timeout; failures move the manager into the FAILED state and are recorded.
"""
from __future__ import annotations

import asyncio
import inspect
from collections.abc import Callable
from datetime import UTC, datetime
from enum import Enum
from typing import Any

from argus.common.errors import ArgusError
from argus.common.logging import get_logger

logger = get_logger("argus.common.lifecycle")

type Hook = Callable[..., Any]


class LifecycleState(str, Enum):
    """Lifecycle state of an Argus component."""

    CREATED = "created"
    STARTING = "starting"
    RUNNING = "running"
    STOPPING = "stopping"
    STOPPED = "stopped"
    FAILED = "failed"


class LifecycleError(ArgusError):
    """Raised when a lifecycle operation fails."""

    code = "LIFECYCLE_ERROR"


_TRANSITIONS: dict[LifecycleState, set[LifecycleState]] = {
    LifecycleState.CREATED: {LifecycleState.STARTING},
    LifecycleState.STARTING: {LifecycleState.RUNNING, LifecycleState.FAILED},
    LifecycleState.RUNNING: {LifecycleState.STOPPING, LifecycleState.FAILED},
    LifecycleState.STOPPING: {LifecycleState.STARTING, LifecycleState.STOPPED, LifecycleState.FAILED},
    LifecycleState.STOPPED: {LifecycleState.STARTING},
    LifecycleState.FAILED: {LifecycleState.STARTING},
}


class LifecycleManager:
    """State machine that runs startup/shutdown hooks around component lifetime."""

    def __init__(self, *, name: str = "lifecycle", hook_timeout: float = 30.0) -> None:
        self._name = name
        self._hook_timeout = hook_timeout
        self._state = LifecycleState.CREATED
        self._startup_hooks: dict[str, Hook] = {}
        self._shutdown_hooks: dict[str, Hook] = {}
        self._current_hook: str | None = None
        self._started_at: datetime | None = None
        self._stopped_at: datetime | None = None
        self._last_error: LifecycleError | None = None

    # ----- read-only access -----

    @property
    def name(self) -> str:
        """Component name."""
        return self._name

    @property
    def state(self) -> LifecycleState:
        """Current lifecycle state."""
        return self._state

    @property
    def status(self) -> dict[str, Any]:
        """Structured status snapshot."""
        return {
            "name": self._name,
            "state": self._state.value,
            "running": self._state == LifecycleState.RUNNING,
            "started_at": self._started_at.isoformat() if self._started_at else None,
            "stopped_at": self._stopped_at.isoformat() if self._stopped_at else None,
            "last_error": self._last_error.to_dict() if self._last_error else None,
            "startup_hooks": list(self._startup_hooks),
            "shutdown_hooks": list(self._shutdown_hooks),
        }

    @property
    def hook_timeout(self) -> float:
        """Timeout (seconds) applied to each lifecycle hook."""
        return self._hook_timeout

    @property
    def last_error(self) -> LifecycleError | None:
        """Last lifecycle error, if any."""
        return self._last_error

    # ----- hook registration -----

    def register_startup_hook(self, name: str, fn: Hook) -> None:
        """Register a startup hook that runs on start."""
        if not callable(fn):
            raise TypeError(f"startup hook {name!r} must be callable")
        self._startup_hooks[name] = fn

    def register_shutdown_hook(self, name: str, fn: Hook) -> None:
        """Register a shutdown hook that runs on stop."""
        if not callable(fn):
            raise TypeError(f"shutdown hook {name!r} must be callable")
        self._shutdown_hooks[name] = fn

    # ----- lifecycle operations -----

    def start(self) -> bool:
        """Start the component; returns True if started, False if already running."""
        if self._state in (LifecycleState.RUNNING, LifecycleState.STARTING):
            return False
        self._transition(LifecycleState.STARTING)
        try:
            self._run_hooks(self._startup_hooks)
        except LifecycleError:
            self._transition(LifecycleState.FAILED)
            raise
        self._transition(LifecycleState.RUNNING)
        self._started_at = datetime.now(UTC)
        self._stopped_at = None
        self._last_error = None
        logger.info("lifecycle.started", name=self._name)
        return True

    def stop(self) -> bool:
        """Stop the component; returns True if stopped, False if already stopped."""
        if self._state != LifecycleState.RUNNING:
            return False
        self._transition(LifecycleState.STOPPING)
        try:
            self._run_hooks(self._shutdown_hooks)
        except LifecycleError:
            self._transition(LifecycleState.FAILED)
            raise
        self._transition(LifecycleState.STOPPED)
        self._stopped_at = datetime.now(UTC)
        self._last_error = None
        logger.info("lifecycle.stopped", name=self._name)
        return True

    def restart(self) -> bool:
        """Restart a running component, or start it if it is not running."""
        if self._state != LifecycleState.RUNNING:
            return self.start()
        self._transition(LifecycleState.STOPPING)
        try:
            self._run_hooks(self._shutdown_hooks)
        except LifecycleError:
            self._transition(LifecycleState.FAILED)
            raise
        self._transition(LifecycleState.STARTING)
        try:
            self._run_hooks(self._startup_hooks)
        except LifecycleError:
            self._transition(LifecycleState.FAILED)
            raise
        self._transition(LifecycleState.RUNNING)
        self._started_at = datetime.now(UTC)
        self._stopped_at = None
        self._last_error = None
        logger.info("lifecycle.restarted", name=self._name)
        return True

    # ----- internals -----

    def _transition(self, target: LifecycleState) -> None:
        allowed = _TRANSITIONS[self._state]
        if target not in allowed:
            raise LifecycleError(
                f"illegal transition {self._state.value} -> {target.value}",
                details={"from": self._state.value, "to": target.value},
            )
        self._state = target

    def _run_hooks(self, hooks: dict[str, Hook]) -> None:
        if not hooks:
            return
        try:
            asyncio.run(self._run_hook_sequence(hooks))
        except LifecycleError as exc:
            self._last_error = exc
            raise
        except TimeoutError as exc:
            error = LifecycleError(
                "lifecycle hook timed out",
                code="LIFECYCLE_HOOK_TIMEOUT",
                details={"hook": self._current_hook, "timeout": self._hook_timeout},
                cause=exc,
            )
            self._last_error = error
            logger.error("lifecycle.hook_timeout", name=self._name, hook=self._current_hook)
            raise error from exc
        except Exception as exc:
            error = LifecycleError(
                f"lifecycle hook {self._current_hook!r} failed",
                code="LIFECYCLE_HOOK_ERROR",
                details={"hook": self._current_hook},
                cause=exc,
            )
            self._last_error = error
            logger.error(
                "lifecycle.hook_failed", name=self._name, hook=self._current_hook, error=str(exc),
            )
            raise error from exc

    async def _run_hook_sequence(self, hooks: dict[str, Hook]) -> None:
        loop = asyncio.get_running_loop()
        for name, hook in hooks.items():
            self._current_hook = name
            if inspect.iscoroutinefunction(hook):
                await asyncio.wait_for(hook(), timeout=self._hook_timeout)
                continue
            result = await asyncio.wait_for(
                loop.run_in_executor(None, hook), timeout=self._hook_timeout,
            )
            if inspect.isawaitable(result):
                await asyncio.wait_for(result, timeout=self._hook_timeout)
