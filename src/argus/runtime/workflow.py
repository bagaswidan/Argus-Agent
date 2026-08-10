"""Workflow Engine — Argus (Spec §24).

Workflow properties: immutable ID, parent/child, parallel execution,
pause/resume, retry, timeout, checkpoint, completion criteria.
"""
from __future__ import annotations

import asyncio
import threading
import time
import uuid
from dataclasses import dataclass, field
from typing import Any, Awaitable, Callable, Optional

from argus.runtime.state import StateManager, WorkflowState, StateTransitionError


class WorkflowError(Exception):
    """Raised on workflow execution errors."""


@dataclass
class WorkflowStep:
    """A single step in a workflow."""

    id: str = field(default_factory=lambda: uuid.uuid4().hex[:8])
    name: str = ""
    fn: Optional[Callable[..., Awaitable[Any]]] = None
    args: tuple = ()
    kwargs: dict[str, Any] = field(default_factory=dict)
    timeout: float = 30.0
    retries: int = 0
    status: str = "pending"  # pending | running | completed | failed | skipped
    result: Any = None
    error: Optional[str] = None


@dataclass
class WorkflowRun:
    """A running workflow instance."""

    workflow_id: str
    name: str
    steps: list[WorkflowStep] = field(default_factory=list)
    state: WorkflowState = WorkflowState.CREATED
    current_step: int = 0
    data: dict[str, Any] = field(default_factory=dict)
    parent_id: Optional[str] = None
    created_at: float = field(default_factory=time.monotonic)

    @property
    def completed_steps(self) -> list[WorkflowStep]:
        return [s for s in self.steps if s.status == "completed"]


class WorkflowEngine:
    """Executes step-based workflows with checkpoint, pause/resume, retry."""

    def __init__(self, state_manager: Optional[StateManager] = None) -> None:
        self._state = state_manager or StateManager()
        self._runs: dict[str, WorkflowRun] = {}
        self._paused: dict[str, asyncio.Event] = {}
        self._max_concurrent = 4
        self._semaphore = threading.Semaphore(1)  # protect _runs dict

    def create(
        self,
        name: str,
        steps: list[WorkflowStep],
        parent_id: Optional[str] = None,
    ) -> WorkflowRun:
        run = WorkflowRun(
            workflow_id=uuid.uuid4().hex[:16],
            name=name,
            steps=steps,
            parent_id=parent_id,
        )
        with self._semaphore:
            self._runs[run.workflow_id] = run
            self._state.create(run.workflow_id, parent_id=parent_id, data={"name": name})
            self._state.transition(run.workflow_id, WorkflowState.QUEUED)
        return run

    def get(self, workflow_id: str) -> Optional[WorkflowRun]:
        with self._semaphore:
            return self._runs.get(workflow_id)

    async def run(self, workflow_id: str) -> WorkflowRun:
        """Execute all steps sequentially with retry + timeout."""
        run = self.get(workflow_id)
        if run is None:
            raise WorkflowError(f"Unknown workflow: {workflow_id}")
        if run.state == WorkflowState.RUNNING:
            raise WorkflowError(f"Workflow already running: {workflow_id}")

        self._state.transition(workflow_id, WorkflowState.RUNNING)
        run.state = WorkflowState.RUNNING

        try:
            while run.current_step < len(run.steps):
                step = run.steps[run.current_step]
                step.status = "running"

                # Pause support
                while run.state == WorkflowState.PAUSED:
                    self._state.transition(workflow_id, WorkflowState.PAUSED)  # no-op guard
                    await asyncio.sleep(0.1)
                    if workflow_id not in self._paused:
                        break

                if run.state == WorkflowState.PAUSED:
                    self._state.transition(workflow_id, WorkflowState.RUNNING)
                    run.state = WorkflowState.RUNNING

                if step.fn is None:
                    step.status = "skipped"
                    run.current_step += 1
                    continue

                # Execute with retries
                attempt = 0
                while True:
                    try:
                        step.result = await asyncio.wait_for(
                            step.fn(*step.args, **step.kwargs),
                            timeout=step.timeout,
                        )
                        step.status = "completed"
                        break
                    except Exception as e:
                        attempt += 1
                        step.error = str(e)
                        if attempt > step.retries:
                            step.status = "failed"
                            raise WorkflowError(
                                f"Step '{step.name}' failed after {attempt} attempts: {e}"
                            )
                        await asyncio.sleep(0.1 * attempt)

                run.current_step += 1
                # Checkpoint: record progress in state
                self._state.set_data(workflow_id, "completed_steps", run.current_step)

            self._state.transition(workflow_id, WorkflowState.VERIFYING)
            self._state.transition(workflow_id, WorkflowState.COMPLETED)
            run.state = WorkflowState.COMPLETED
        except WorkflowError as e:
            self._state.transition(workflow_id, WorkflowState.FAILED)
            run.state = WorkflowState.FAILED
            raise
        return run

    async def pause(self, workflow_id: str) -> bool:
        """Pause after the current step finishes."""
        run = self.get(workflow_id)
        if run is None:
            return False
        if run.state != WorkflowState.RUNNING:
            return False
        self._state.transition(workflow_id, WorkflowState.PAUSED)
        run.state = WorkflowState.PAUSED
        return True

    async def resume(self, workflow_id: str) -> bool:
        run = self.get(workflow_id)
        if run is None:
            return False
        if run.state != WorkflowState.PAUSED:
            return False
        self._state.transition(workflow_id, WorkflowState.RUNNING)
        run.state = WorkflowState.RUNNING
        return True

    def checkpoint_state(self, workflow_id: str) -> dict[str, Any]:
        """Snapshot of workflow progress (for recovery)."""
        run = self.get(workflow_id)
        if run is None:
            return {}
        return {
            "workflow_id": workflow_id,
            "current_step": run.current_step,
            "completed_steps": [s.name for s in run.completed_steps],
            "state": run.state.value,
            "data": dict(run.data),
        }

    def archive(self, workflow_id: str) -> bool:
        run = self.get(workflow_id)
        if run is None:
            return False
        try:
            self._state.transition(workflow_id, WorkflowState.ARCHIVED)
        except StateTransitionError:
            return False
        run.state = WorkflowState.ARCHIVED
        return True

    def active_count(self) -> int:
        with self._semaphore:
            return sum(
                1 for r in self._runs.values()
                if r.state in (WorkflowState.RUNNING, WorkflowState.QUEUED, WorkflowState.PAUSED)
            )


def create_workflow_engine(state_manager: Optional[StateManager] = None) -> WorkflowEngine:
    return WorkflowEngine(state_manager=state_manager)
