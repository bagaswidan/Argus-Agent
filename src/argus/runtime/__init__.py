"""Runtime Manager — Argus.

Runtime core per Spec §21-28: Scheduler, State Manager, Transaction Manager,
Lock Manager, Recovery Manager. Execution-only; reasoning stays in Brain.
"""
from __future__ import annotations

from argus.runtime.lock import LockManager, create_lock_manager
from argus.runtime.monitor import RuntimeMonitor, create_runtime_monitor
from argus.runtime.scheduler import ScheduledTask, Scheduler, create_scheduler
from argus.runtime.state import StateManager, WorkflowState, create_state_manager
from argus.runtime.streaming import (
    StreamChunk,
    StreamingManager,
    collect_stream,
    create_streaming_manager,
)
from argus.runtime.transaction import Transaction, TransactionManager, create_transaction_manager
from argus.runtime.workflow import WorkflowEngine, WorkflowRun, WorkflowStep, create_workflow_engine

__all__ = [
    "LockManager",
    "RuntimeMonitor",
    "ScheduledTask",
    "Scheduler",
    "StateManager",
    "StreamChunk",
    "StreamingManager",
    "Transaction",
    "TransactionManager",
    "WorkflowEngine",
    "WorkflowRun",
    "WorkflowState",
    "WorkflowStep",
    "collect_stream",
    "create_lock_manager",
    "create_runtime_monitor",
    "create_scheduler",
    "create_state_manager",
    "create_streaming_manager",
    "create_transaction_manager",
    "create_workflow_engine",
]
