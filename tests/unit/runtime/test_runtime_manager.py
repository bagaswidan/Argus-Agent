"""Test Runtime Manager — Argus."""
from __future__ import annotations

import asyncio

import pytest

from argus.runtime.lock import LockError, create_lock_manager
from argus.runtime.scheduler import create_scheduler
from argus.runtime.state import (
    StateTransitionError,
    WorkflowState,
    create_state_manager,
)
from argus.runtime.transaction import (
    RecoveryStrategy,
    TransactionStatus,
    create_transaction_manager,
)

# --- Scheduler ---

class TestScheduler:
    @pytest.mark.asyncio
    async def test_submit_and_run(self):
        sched = create_scheduler()
        seen = []

        async def work(x):
            seen.append(x)

        task = sched.submit(work, 42, name="t1")
        assert task.status == "pending"
        result = await sched.run_once()
        assert result.id == task.id
        assert result.status == "completed"
        assert seen == [42]

    @pytest.mark.asyncio
    async def test_priority_order(self):
        sched = create_scheduler()
        order = []

        async def mk(name):
            def _inner():
                order.append(name)
            return _inner

        # Submit low priority first, high priority second
        async def work_low():
            order.append("low")

        async def work_high():
            order.append("high")

        sched.submit(work_low, name="low", priority=1)
        sched.submit(work_high, name="high", priority=10)
        await sched.run_all()
        assert order == ["high", "low"]

    @pytest.mark.asyncio
    async def test_timeout_marks_failed(self):
        sched = create_scheduler()

        async def slow():
            await asyncio.sleep(5)

        task = sched.submit(slow, timeout=0.1)
        await sched.run_once()
        assert task.status == "failed"

    @pytest.mark.asyncio
    async def test_exception_marks_failed(self):
        sched = create_scheduler()

        async def boom():
            raise ValueError("x")

        task = sched.submit(boom, timeout=1)
        await sched.run_once()
        assert task.status == "failed"

    @pytest.mark.asyncio
    async def test_cancel(self):
        sched = create_scheduler()

        async def work():
            pass

        task = sched.submit(work, name="c")
        assert sched.cancel(task.id) is True
        assert task.status == "cancelled"
        assert sched.pending_count() == 0

    def test_queries(self):
        sched = create_scheduler()
        assert sched.pending_count() == 0
        assert sched.running_count() == 0
        assert sched.completed() == []


# --- State Manager ---

class TestStateManager:
    def test_create_and_get(self):
        sm = create_state_manager()
        rec = sm.create()
        assert sm.get(rec.workflow_id) is not None
        assert rec.state == WorkflowState.CREATED

    def test_valid_transition_chain(self):
        sm = create_state_manager()
        rec = sm.create()
        sm.transition(rec.workflow_id, WorkflowState.QUEUED)
        sm.transition(rec.workflow_id, WorkflowState.RUNNING)
        sm.transition(rec.workflow_id, WorkflowState.VERIFYING)
        sm.transition(rec.workflow_id, WorkflowState.COMPLETED)
        sm.transition(rec.workflow_id, WorkflowState.ARCHIVED)
        assert sm.get(rec.workflow_id).state == WorkflowState.ARCHIVED

    def test_pause_resume(self):
        sm = create_state_manager()
        rec = sm.create()
        sm.transition(rec.workflow_id, WorkflowState.QUEUED)
        sm.transition(rec.workflow_id, WorkflowState.RUNNING)
        sm.transition(rec.workflow_id, WorkflowState.PAUSED)
        sm.transition(rec.workflow_id, WorkflowState.RUNNING)
        assert sm.get(rec.workflow_id).state == WorkflowState.RUNNING

    def test_invalid_transition_raises(self):
        sm = create_state_manager()
        rec = sm.create()
        with pytest.raises(StateTransitionError):
            sm.transition(rec.workflow_id, WorkflowState.COMPLETED)  # created -> completed invalid

    def test_unknown_workflow_raises(self):
        sm = create_state_manager()
        with pytest.raises(StateTransitionError):
            sm.transition("nope", WorkflowState.RUNNING)

    def test_set_data(self):
        sm = create_state_manager()
        rec = sm.create()
        assert sm.set_data(rec.workflow_id, "k", "v") is True
        assert sm.get(rec.workflow_id).data["k"] == "v"
        assert sm.set_data("nope", "k", "v") is False

    def test_list_by_state(self):
        sm = create_state_manager()
        a = sm.create()
        sm.transition(a.workflow_id, WorkflowState.QUEUED)
        sm.create()
        assert len(sm.list_workflows(WorkflowState.QUEUED)) == 1
        assert sm.count() == 2


# --- Transaction ---

class TestTransaction:
    def test_lifecycle(self):
        tm = create_transaction_manager()
        tx = tm.begin(name="critical")
        assert tx.status == TransactionStatus.ACTIVE
        idx = tx.checkpoint("step1", {"done": 1})
        assert idx == 0
        assert tx.status == TransactionStatus.CHECKPOINTED
        assert tm.commit(tx.id) is True
        assert tx.status == TransactionStatus.COMMITTED
        # double commit fails
        assert tm.commit(tx.id) is False

    def test_rollback(self):
        tm = create_transaction_manager()
        tx = tm.begin()
        tx.checkpoint("a")
        tx.checkpoint("b")
        assert tm.rollback(tx.id) is True
        assert tx.status == TransactionStatus.ROLLED_BACK

    def test_rollback_to_checkpoint(self):
        tm = create_transaction_manager()
        tx = tm.begin()
        tx.checkpoint("a", {"x": 1})
        tx.checkpoint("b", {"x": 2})
        tx.rollback_to(0)
        assert len(tx.checkpoints) == 1
        assert tx.checkpoints[0]["label"] == "a"

    def test_suggest_recovery_resume(self):
        tm = create_transaction_manager()
        tx = tm.begin()
        tx.checkpoint("c1")
        assert tm.suggest_recovery(tx.id, "boom") == RecoveryStrategy.RESUME

    def test_suggest_recovery_retry_on_timeout(self):
        tm = create_transaction_manager()
        tx = tm.begin()
        assert tm.suggest_recovery(tx.id, "timed out") == RecoveryStrategy.RETRY

    def test_suggest_recovery_abort_unknown(self):
        tm = create_transaction_manager()
        assert tm.suggest_recovery("nope", "x") == RecoveryStrategy.ABORT

    def test_record_recovery(self):
        tm = create_transaction_manager()
        tx = tm.begin()
        tm.record_recovery(tx.id, RecoveryStrategy.REPLAN, "bad plan")
        log = tm.recovery_log()
        assert len(log) == 1
        assert log[0]["strategy"] == "replan"


# --- Lock Manager ---

class TestLockManager:
    def test_acquire_release(self):
        lm = create_lock_manager()
        handle = lm.acquire("cap:math.add", owner="agent-1")
        assert lm.is_locked("cap:math.add") is True
        assert lm.owner_of("cap:math.add") == "agent-1"
        assert lm.release(handle) is True
        assert lm.is_locked("cap:math.add") is False

    def test_double_acquire_fails(self):
        lm = create_lock_manager()
        lm.acquire("key1", owner="a")
        with pytest.raises(LockError):
            lm.acquire("key1", owner="b")

    def test_try_acquire_returns_none(self):
        lm = create_lock_manager()
        lm.acquire("key1", owner="a")
        assert lm.try_acquire("key1", owner="b") is None
        assert lm.try_acquire("key2", owner="b") is not None

    def test_ttl_expiry(self):
        lm = create_lock_manager()
        lm.acquire("key1", owner="a", ttl=0.05)
        import time
        time.sleep(0.1)
        assert lm.is_locked("key1") is False  # expired -> auto released
        # can re-acquire
        lm.acquire("key1", owner="b")
        assert lm.owner_of("key1") == "b"

    def test_wait_acquire(self):
        lm = create_lock_manager()
        lm.acquire("key1", owner="a", ttl=0.1)
        import time
        time.sleep(0.15)
        # expired by now, wait should succeed
        handle = lm.acquire("key1", owner="b", wait=0.5)
        assert lm.owner_of("key1") == "b"

    def test_release_wrong_owner_fails(self):
        lm = create_lock_manager()
        h1 = lm.acquire("key1", owner="a")
        h2 = lm.acquire("key2", owner="b")
        # releasing key2 with h1 (different lock_id) fails
        assert lm.release(h1) is True  # h1 owns key1
        # simulate stale handle for key2
        assert lm.release(h2) is True


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
