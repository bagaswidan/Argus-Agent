"""State Manager — Argus Runtime (Spec §22, §26).

Tracks workflow state with the workflow state machine from Spec §24:
Created, Queued, Running, Waiting, Paused, Verifying, Completed, Failed, Archived.
"""
from __future__ import annotations

import threading
import uuid
from dataclasses import dataclass, field
from datetime import UTC, datetime
from enum import Enum
from typing import Any


class WorkflowState(str, Enum):
    CREATED = "created"
    QUEUED = "queued"
    RUNNING = "running"
    WAITING = "waiting"
    PAUSED = "paused"
    VERIFYING = "verifying"
    COMPLETED = "completed"
    FAILED = "failed"
    ARCHIVED = "archived"


_VALID_TRANSITIONS: dict[WorkflowState, set[WorkflowState]] = {
    WorkflowState.CREATED: {WorkflowState.QUEUED, WorkflowState.FAILED},
    WorkflowState.QUEUED: {WorkflowState.RUNNING, WorkflowState.ARCHIVED, WorkflowState.FAILED},
    WorkflowState.RUNNING: {WorkflowState.WAITING, WorkflowState.PAUSED, WorkflowState.VERIFYING, WorkflowState.FAILED, WorkflowState.COMPLETED},
    WorkflowState.WAITING: {WorkflowState.RUNNING, WorkflowState.PAUSED, WorkflowState.FAILED},
    WorkflowState.PAUSED: {WorkflowState.RUNNING, WorkflowState.FAILED},
    WorkflowState.VERIFYING: {WorkflowState.COMPLETED, WorkflowState.FAILED, WorkflowState.RUNNING},
    WorkflowState.COMPLETED: {WorkflowState.ARCHIVED},
    WorkflowState.FAILED: {WorkflowState.ARCHIVED, WorkflowState.QUEUED},  # retry allowed
    WorkflowState.ARCHIVED: set(),
}


class StateTransitionError(Exception):
    """Raised on invalid state transition."""


@dataclass
class WorkflowRecord:
    """State record for one workflow."""

    workflow_id: str
    state: WorkflowState = WorkflowState.CREATED
    parent_id: str | None = None
    data: dict[str, Any] = field(default_factory=dict)
    created_at: datetime = field(default_factory=lambda: datetime.now(UTC))
    updated_at: datetime = field(default_factory=lambda: datetime.now(UTC))

    def touch(self) -> None:
        self.updated_at = datetime.now(UTC)


class StateManager:
    """Thread-safe workflow state store."""

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._records: dict[str, WorkflowRecord] = {}

    def create(self, workflow_id: str | None = None, parent_id: str | None = None, data: dict[str, Any] | None = None) -> WorkflowRecord:
        wid = workflow_id or uuid.uuid4().hex[:16]
        record = WorkflowRecord(
            workflow_id=wid,
            parent_id=parent_id,
            data=data or {},
        )
        with self._lock:
            self._records[wid] = record
        return record

    def transition(self, workflow_id: str, new_state: WorkflowState) -> WorkflowRecord:
        with self._lock:
            record = self._records.get(workflow_id)
            if record is None:
                raise StateTransitionError(f"Unknown workflow: {workflow_id}")
            allowed = _VALID_TRANSITIONS.get(record.state, set())
            if new_state not in allowed:
                raise StateTransitionError(
                    f"Invalid transition {record.state.value} -> {new_state.value} for {workflow_id}",
                )
            record.state = new_state
            record.touch()
            return record

    def get(self, workflow_id: str) -> WorkflowRecord | None:
        with self._lock:
            return self._records.get(workflow_id)

    def set_data(self, workflow_id: str, key: str, value: Any) -> bool:
        with self._lock:
            record = self._records.get(workflow_id)
            if record is None:
                return False
            record.data[key] = value
            record.touch()
            return True

    def list_workflows(self, state: WorkflowState | None = None) -> list[WorkflowRecord]:
        with self._lock:
            records = list(self._records.values())
        if state is not None:
            records = [r for r in records if r.state == state]
        return records

    def count(self) -> int:
        with self._lock:
            return len(self._records)


def create_state_manager() -> StateManager:
    return StateManager()
