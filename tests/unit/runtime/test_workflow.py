"""Test Workflow Engine — Argus."""
from __future__ import annotations

import asyncio

import pytest

from argus.runtime.state import WorkflowState
from argus.runtime.workflow import (
    WorkflowError,
    WorkflowStep,
    create_workflow_engine,
)


class TestWorkflowEngine:
    @pytest.mark.asyncio
    async def test_simple_workflow(self):
        engine = create_workflow_engine()
        results = []

        async def step_a():
            results.append("a")

        async def step_b():
            results.append("b")

        run = engine.create("wf", [WorkflowStep(name="a", fn=step_a), WorkflowStep(name="b", fn=step_b)])
        await engine.run(run.workflow_id)
        assert results == ["a", "b"]
        assert run.state == WorkflowState.COMPLETED
        assert run.completed_steps == run.steps

    @pytest.mark.asyncio
    async def test_step_result_flow(self):
        engine = create_workflow_engine()

        async def add(x):
            return x + 1

        run = engine.create("wf", [WorkflowStep(name="s1", fn=add, args=(1,))])
        await engine.run(run.workflow_id)
        assert run.steps[0].result == 2

    @pytest.mark.asyncio
    async def test_retry_success(self):
        engine = create_workflow_engine()
        attempts = {"n": 0}

        async def flaky():
            attempts["n"] += 1
            if attempts["n"] < 3:
                raise ValueError("transient")
            return "ok"

        run = engine.create("wf", [WorkflowStep(name="f", fn=flaky, retries=3)])
        await engine.run(run.workflow_id)
        assert attempts["n"] == 3
        assert run.steps[0].result == "ok"

    @pytest.mark.asyncio
    async def test_retry_exhausted_fails(self):
        engine = create_workflow_engine()

        async def always_fail():
            raise ValueError("always")

        run = engine.create("wf", [WorkflowStep(name="f", fn=always_fail, retries=1)])
        with pytest.raises(WorkflowError):
            await engine.run(run.workflow_id)
        assert run.state == WorkflowState.FAILED
        assert run.steps[0].status == "failed"

    @pytest.mark.asyncio
    async def test_timeout_fails(self):
        engine = create_workflow_engine()

        async def slow():
            await asyncio.sleep(5)

        run = engine.create("wf", [WorkflowStep(name="s", fn=slow, timeout=0.1)])
        with pytest.raises(WorkflowError):
            await engine.run(run.workflow_id)
        assert run.state == WorkflowState.FAILED

    @pytest.mark.asyncio
    async def test_pause_resume(self):
        engine = create_workflow_engine()
        entered = asyncio.Event()
        proceed = asyncio.Event()

        async def gate(x):
            if x == 2:
                entered.set()
                await proceed.wait()  # block step 2 until released
            return x

        run = engine.create(
            "wf",
            [WorkflowStep(name=f"s{i}", fn=gate, args=(i,)) for i in range(5)],
        )
        task = asyncio.create_task(engine.run(run.workflow_id))
        await asyncio.wait_for(entered.wait(), timeout=2)
        await engine.pause(run.workflow_id)
        assert run.state == WorkflowState.PAUSED
        assert run.current_step == 2
        await engine.resume(run.workflow_id)
        proceed.set()
        await asyncio.wait_for(task, timeout=5)
        assert run.state == WorkflowState.COMPLETED
        assert all(s.status == "completed" for s in run.steps)

    @pytest.mark.asyncio
    async def test_pause_when_not_running_fails(self):
        engine = create_workflow_engine()
        run = engine.create("wf", [])
        assert await engine.pause(run.workflow_id) is False

    def test_checkpoint_state(self):
        engine = create_workflow_engine()
        run = engine.create("wf", [WorkflowStep(name="a"), WorkflowStep(name="b")])
        snap = engine.checkpoint_state(run.workflow_id)
        assert snap["current_step"] == 0
        assert snap["completed_steps"] == []

    def test_archive(self):
        engine = create_workflow_engine()
        run = engine.create("wf", [])
        assert engine.archive(run.workflow_id) is True
        assert run.state == WorkflowState.ARCHIVED

    def test_unknown_workflow(self):
        engine = create_workflow_engine()
        assert engine.get("nope") is None
        with pytest.raises(WorkflowError):
            asyncio.run(engine.run("nope"))

    def test_parent_child(self):
        engine = create_workflow_engine()
        parent = engine.create("parent", [])
        child = engine.create("child", [], parent_id=parent.workflow_id)
        assert child.parent_id == parent.workflow_id


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
