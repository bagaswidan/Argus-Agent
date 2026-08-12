"""Test Lifecycle Manager — Argus Core Foundation."""
from __future__ import annotations

import asyncio
import time
from typing import Any

import pytest

from argus.common.lifecycle import LifecycleError, LifecycleManager, LifecycleState


@pytest.fixture
def lifecycle() -> LifecycleManager:
    return LifecycleManager(name="test-manager", hook_timeout=5.0)


class TestLifecycleState:
    def test_all_state_values(self) -> None:
        assert LifecycleState.CREATED == "created"
        assert LifecycleState.STARTING == "starting"
        assert LifecycleState.RUNNING == "running"
        assert LifecycleState.STOPPING == "stopping"
        assert LifecycleState.STOPPED == "stopped"
        assert LifecycleState.FAILED == "failed"


class TestLifecycleManagerInitial:
    def test_initial_state_is_created(self, lifecycle: LifecycleManager) -> None:
        assert lifecycle.state == LifecycleState.CREATED

    def test_initial_status_structure(self, lifecycle: LifecycleManager) -> None:
        status = lifecycle.status
        assert status["state"] == "created"
        assert status["running"] is False
        assert status["started_at"] is None
        assert status["stopped_at"] is None
        assert status["last_error"] is None
        assert status["startup_hooks"] == []
        assert status["shutdown_hooks"] == []


class TestLifecycleStart:
    def test_start_transitions_to_running(self, lifecycle: LifecycleManager) -> None:
        assert lifecycle.start() is True
        assert lifecycle.state == LifecycleState.RUNNING
        assert lifecycle.status["running"] is True

    def test_start_sets_started_at(self, lifecycle: LifecycleManager) -> None:
        lifecycle.start()
        assert isinstance(lifecycle.status["started_at"], str)

    def test_start_runs_startup_hooks_in_order(self, lifecycle: LifecycleManager) -> None:
        calls: list[str] = []
        lifecycle.register_startup_hook("first", lambda: calls.append("first"))
        lifecycle.register_startup_hook("second", lambda: calls.append("second"))
        lifecycle.register_startup_hook("third", lambda: calls.append("third"))
        lifecycle.start()
        assert calls == ["first", "second", "third"]

    def test_async_startup_hook(self, lifecycle: LifecycleManager) -> None:
        calls: list[str] = []

        async def hook() -> None:
            calls.append("async")

        lifecycle.register_startup_hook("async-hook", hook)
        lifecycle.start()
        assert calls == ["async"]

    def test_sync_hook_returning_coroutine(self, lifecycle: LifecycleManager) -> None:
        calls: list[str] = []

        async def inner() -> None:
            calls.append("inner")

        def outer() -> Any:
            return inner()

        lifecycle.register_startup_hook("outer", outer)
        lifecycle.start()
        assert calls == ["inner"]


class TestLifecycleStop:
    def test_stop_transitions_to_stopped(self, lifecycle: LifecycleManager) -> None:
        lifecycle.start()
        assert lifecycle.stop() is True
        assert lifecycle.state == LifecycleState.STOPPED
        assert lifecycle.status["running"] is False

    def test_stop_sets_stopped_at(self, lifecycle: LifecycleManager) -> None:
        lifecycle.start()
        lifecycle.stop()
        assert isinstance(lifecycle.status["stopped_at"], str)

    def test_stop_runs_shutdown_hooks_in_order(self, lifecycle: LifecycleManager) -> None:
        calls: list[str] = []
        lifecycle.register_shutdown_hook("first", lambda: calls.append("first"))
        lifecycle.register_shutdown_hook("second", lambda: calls.append("second"))
        lifecycle.start()
        lifecycle.stop()
        assert calls == ["first", "second"]

    def test_async_shutdown_hook(self, lifecycle: LifecycleManager) -> None:
        calls: list[str] = []

        async def hook() -> None:
            calls.append("async-stop")

        lifecycle.register_shutdown_hook("async-stop", hook)
        lifecycle.start()
        lifecycle.stop()
        assert calls == ["async-stop"]


class TestLifecycleRestart:
    def test_restart_sequence_from_running(self, lifecycle: LifecycleManager) -> None:
        observed: list[LifecycleState] = []
        lifecycle.register_shutdown_hook("shutdown", lambda: observed.append(lifecycle.state))
        lifecycle.register_startup_hook("startup", lambda: observed.append(lifecycle.state))
        lifecycle.start()
        observed.clear()
        assert lifecycle.restart() is True
        assert lifecycle.state == LifecycleState.RUNNING
        assert observed == [LifecycleState.STOPPING, LifecycleState.STARTING]

    def test_restart_reruns_hooks(self, lifecycle: LifecycleManager) -> None:
        calls: list[str] = []
        lifecycle.register_startup_hook("startup", lambda: calls.append("start"))
        lifecycle.register_shutdown_hook("shutdown", lambda: calls.append("stop"))
        lifecycle.start()
        lifecycle.restart()
        assert calls == ["start", "stop", "start"]

    def test_restart_from_stopped(self, lifecycle: LifecycleManager) -> None:
        lifecycle.start()
        lifecycle.stop()
        assert lifecycle.restart() is True
        assert lifecycle.state == LifecycleState.RUNNING

    def test_restart_recovers_from_failed(self, lifecycle: LifecycleManager) -> None:
        lifecycle.register_startup_hook("boom", lambda: 1 / 0)
        with pytest.raises(LifecycleError):
            lifecycle.start()
        assert lifecycle.state == LifecycleState.FAILED
        lifecycle.register_startup_hook("boom", lambda: None)
        assert lifecycle.restart() is True
        assert lifecycle.state == LifecycleState.RUNNING


class TestLifecycleFailure:
    def test_startup_hook_failure_sets_failed(self, lifecycle: LifecycleManager) -> None:
        lifecycle.register_startup_hook("bad", lambda: 1 / 0)
        with pytest.raises(LifecycleError):
            lifecycle.start()
        assert lifecycle.state == LifecycleState.FAILED
        assert lifecycle.status["running"] is False

    def test_shutdown_hook_failure_sets_failed_from_running(
        self, lifecycle: LifecycleManager,
    ) -> None:
        lifecycle.register_shutdown_hook("bad", lambda: 1 / 0)
        lifecycle.start()
        with pytest.raises(LifecycleError):
            lifecycle.stop()
        assert lifecycle.state == LifecycleState.FAILED
        assert lifecycle.status["running"] is False

    def test_hook_failure_error_is_recorded(self, lifecycle: LifecycleManager) -> None:
        def fail() -> None:
            raise ValueError("boom")

        lifecycle.register_startup_hook("bad", fail)
        with pytest.raises(LifecycleError):
            lifecycle.start()
        assert lifecycle.last_error is not None
        assert lifecycle.last_error.details["hook"] == "bad"
        assert lifecycle.status["last_error"] is not None

    def test_failed_error_carries_cause(self, lifecycle: LifecycleManager) -> None:
        def fail() -> None:
            raise ValueError("boom")

        lifecycle.register_startup_hook("bad", fail)
        with pytest.raises(LifecycleError) as exc_info:
            lifecycle.start()
        assert isinstance(exc_info.value.__cause__, ValueError)


class TestLifecycleIdempotency:
    def test_start_twice_is_safe(self, lifecycle: LifecycleManager) -> None:
        assert lifecycle.start() is True
        assert lifecycle.start() is False
        assert lifecycle.state == LifecycleState.RUNNING

    def test_start_running_does_not_rerun_hooks(self, lifecycle: LifecycleManager) -> None:
        calls: list[str] = []
        lifecycle.register_startup_hook("startup", lambda: calls.append("x"))
        lifecycle.start()
        lifecycle.start()
        assert calls == ["x"]

    def test_stop_when_stopped_is_safe(self, lifecycle: LifecycleManager) -> None:
        lifecycle.start()
        lifecycle.stop()
        assert lifecycle.stop() is False
        assert lifecycle.state == LifecycleState.STOPPED

    def test_stop_when_created_is_safe(self, lifecycle: LifecycleManager) -> None:
        assert lifecycle.stop() is False
        assert lifecycle.state == LifecycleState.CREATED


class TestLifecycleTimeout:
    def test_async_hook_timeout_sets_failed(self) -> None:
        manager = LifecycleManager(hook_timeout=0.05)

        async def slow() -> None:
            await asyncio.sleep(1)

        manager.register_startup_hook("slow", slow)
        with pytest.raises(LifecycleError) as exc_info:
            manager.start()
        assert exc_info.value.code == "LIFECYCLE_HOOK_TIMEOUT"
        assert manager.state == LifecycleState.FAILED
        assert manager.last_error is not None

    def test_sync_hook_timeout_sets_failed(self) -> None:
        manager = LifecycleManager(hook_timeout=0.05)

        def slow() -> None:
            time.sleep(0.3)

        manager.register_startup_hook("slow", slow)
        with pytest.raises(LifecycleError):
            manager.start()
        assert manager.state == LifecycleState.FAILED
        assert manager.last_error is not None
        assert manager.last_error.details["hook"] == "slow"

    def test_default_hook_timeout_is_30_seconds(self) -> None:
        manager = LifecycleManager()
        assert manager.hook_timeout == 30.0


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
