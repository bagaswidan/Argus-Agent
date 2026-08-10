"""Agent Spec & State — Argus Multi-Agent Orchestrator.

Defines agent roles, capabilities, and lifecycle states.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Optional
from uuid import uuid4


class AgentRole(str, Enum):
    """Role of an agent in the orchestration."""

    ORCHESTRATOR = "orchestrator"  # Plans, delegates, coordinates
    WORKER = "worker"  # Executes assigned tasks
    SPECIALIST = "specialist"  # Domain-specific expert
    CRITIC = "critic"  # Reviews and validates outputs
    AGGREGATOR = "aggregator"  # Combines results from multiple agents


class AgentState(str, Enum):
    """Lifecycle state of an agent."""

    IDLE = "idle"
    INITIALIZING = "initializing"
    RUNNING = "running"
    WAITING = "waiting"  # Waiting for dependency/result
    COMPLETED = "completed"
    FAILED = "failed"
    TERMINATED = "terminated"


@dataclass
class AgentSpec:
    """Specification for an agent in the orchestration."""

    id: str = field(default_factory=lambda: str(uuid4()))
    name: str = ""
    role: AgentRole = AgentRole.WORKER
    description: str = ""
    capabilities: list[str] = field(default_factory=list)  # Capability names from registry
    system_prompt: str = ""
    model_override: Optional[str] = None
    max_iterations: int = 10
    timeout_seconds: int = 300
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "name": self.name,
            "role": self.role.value,
            "description": self.description,
            "capabilities": self.capabilities,
            "system_prompt": self.system_prompt,
            "model_override": self.model_override,
            "max_iterations": self.max_iterations,
            "timeout_seconds": self.timeout_seconds,
            "metadata": self.metadata,
        }


@dataclass
class AgentInstance:
    """Runtime instance of an agent."""

    spec: AgentSpec
    state: AgentState = AgentState.IDLE
    assigned_task: Optional[str] = None
    result: Optional[str] = None
    error: Optional[str] = None
    started_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None
    iteration: int = 0
    context: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "spec": self.spec.to_dict(),
            "state": self.state.value,
            "assigned_task": self.assigned_task,
            "result": self.result,
            "error": self.error,
            "started_at": self.started_at.isoformat() if self.started_at else None,
            "completed_at": self.completed_at.isoformat() if self.completed_at else None,
            "iteration": self.iteration,
            "context": self.context,
        }