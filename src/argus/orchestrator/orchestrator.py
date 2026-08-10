"""Multi-Agent Orchestrator — Argus Phase 2.

Coordinates multiple agents to solve complex tasks through delegation,
collaboration, and result aggregation.
"""
from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Callable, Optional
from uuid import uuid4

from argus.capability.engine import CapabilityEngine, CapabilityRegistry
from argus.orchestrator.agent import AgentInstance, AgentRole, AgentSpec, AgentState
from argus.orchestrator.communication import AgentMessage, MessageBus, get_message_bus
from argus.runtime.sandbox import Sandbox, ResourceLimit

logger = logging.getLogger(__name__)


@dataclass
class OrchestrationTask:
    """A task to be executed by an agent."""

    id: str = field(default_factory=lambda: str(uuid4()))
    description: str = ""
    assigned_agent: str = ""  # Agent ID
    dependencies: list[str] = field(default_factory=list)  # Task IDs
    status: str = "pending"  # pending, running, completed, failed
    result: Optional[str] = None
    error: Optional[str] = None
    created_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    started_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None


@dataclass
class OrchestrationPlan:
    """Execution plan for a multi-agent task."""

    goal: str
    tasks: list[OrchestrationTask] = field(default_factory=list)
    agents: list[AgentSpec] = field(default_factory=list)
    created_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))


@dataclass
class OrchestrationResult:
    """Result of a multi-agent orchestration."""

    success: bool
    goal: str
    plan: OrchestrationPlan
    agent_results: dict[str, str] = field(default_factory=dict)  # agent_id -> result
    errors: dict[str, str] = field(default_factory=dict)
    total_duration_ms: int = 0
    started_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    completed_at: Optional[datetime] = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "success": self.success,
            "goal": self.goal,
            "plan": {
                "goal": self.plan.goal,
                "tasks": [
                    {
                        "id": t.id,
                        "description": t.description,
                        "assigned_agent": t.assigned_agent,
                        "dependencies": t.dependencies,
                        "status": t.status,
                        "result": t.result,
                        "error": t.error,
                    }
                    for t in self.plan.tasks
                ],
                "agents": [a.to_dict() for a in self.plan.agents],
            },
            "agent_results": self.agent_results,
            "errors": self.errors,
            "total_duration_ms": self.total_duration_ms,
            "started_at": self.started_at.isoformat(),
            "completed_at": self.completed_at.isoformat() if self.completed_at else None,
        }


class MultiAgentOrchestrator:
    """Orchestrates multiple agents to achieve a goal."""

    def __init__(
        self,
        capability_engine: CapabilityEngine,
        capability_registry: CapabilityRegistry,
        sandbox: Sandbox,
        message_bus: Optional[MessageBus] = None,
    ):
        self.capability_engine = capability_engine
        self.capability_registry = capability_registry
        self.sandbox = sandbox
        self.message_bus = message_bus or get_message_bus()

        self._agents: dict[str, AgentInstance] = {}
        self._tasks: dict[str, OrchestrationTask] = {}
        self._running = False

    async def create_plan(
        self,
        goal: str,
        agent_specs: list[AgentSpec],
    ) -> OrchestrationPlan:
        """Create an execution plan from goal and agent specs.
        
        In a full implementation, this would use an LLM to decompose the goal
        into tasks and assign them to agents. For now, we create a simple
        sequential plan where each agent gets one task.
        """
        plan = OrchestrationPlan(goal=goal, agents=agent_specs)

        # Create one task per agent (simple delegation)
        for i, spec in enumerate(agent_specs):
            task = OrchestrationTask(
                description=f"{spec.role.value}: {goal}",
                assigned_agent=spec.id,
            )
            # Chain tasks sequentially for now
            if i > 0:
                task.dependencies = [plan.tasks[i - 1].id]
            plan.tasks.append(task)
            self._tasks[task.id] = task

        return plan

    async def execute_plan(self, plan: OrchestrationPlan) -> OrchestrationResult:
        """Execute an orchestration plan."""
        start_time = datetime.now(timezone.utc)
        agent_results = {}
        errors = {}

        # Initialize agents
        for spec in plan.agents:
            instance = AgentInstance(spec=spec)
            self._agents[spec.id] = instance

        # Subscribe agents to message bus
        agent_queues = {}
        for agent_id in self._agents:
            agent_queues[agent_id] = await self.message_bus.subscribe(agent_id)

        try:
            self._running = True

            # Execute tasks in dependency order
            for task in plan.tasks:
                # Wait for dependencies, handling failures
                deps_ok = True
                for dep_id in task.dependencies:
                    dep_task = self._tasks[dep_id]
                    while dep_task.status not in ("completed", "failed"):
                        await asyncio.sleep(0.1)
                    if dep_task.status != "completed":
                        task.status = "failed"
                        task.error = (
                            f"Dependency task {dep_id} failed: "
                            f"{dep_task.error or 'unknown'}"
                        )
                        errors[task.assigned_agent] = task.error
                        deps_ok = False
                        break

                # If any dependency failed, skip this task
                if not deps_ok:
                    continue

                # Execute task
                agent = self._agents.get(task.assigned_agent)
                if not agent:
                    task.status = "failed"
                    task.error = f"Agent {task.assigned_agent} not found"
                    errors[task.assigned_agent] = task.error
                    continue

                await self._execute_task(agent, task)
                agent_results[agent.spec.id] = task.result or ""

                if task.status == "failed":
                    errors[agent.spec.id] = task.error or "Unknown error"

            success = all(t.status == "completed" for t in plan.tasks)

        finally:
            self._running = False
            # Cleanup subscriptions
            for agent_id, queue in agent_queues.items():
                self.message_bus.unsubscribe(agent_id, queue)

        end_time = datetime.now(timezone.utc)
        duration_ms = int((end_time - start_time).total_seconds() * 1000)

        return OrchestrationResult(
            success=success,
            goal=plan.goal,
            plan=plan,
            agent_results=agent_results,
            errors=errors,
            total_duration_ms=duration_ms,
            started_at=start_time,
            completed_at=end_time,
        )

    async def _execute_task(self, agent: AgentInstance, task: OrchestrationTask) -> None:
        """Execute a single task with an agent."""
        agent.state = AgentState.RUNNING
        agent.assigned_task = task.description
        task.status = "running"
        task.started_at = datetime.now(timezone.utc)

        # Build context from dependencies
        context = {}
        for dep_id in task.dependencies:
            dep_task = self._tasks[dep_id]
            if dep_task.result:
                context[f"dep_{dep_id}"] = dep_task.result

        try:
            # Execute via capability engine (simplified - would use LLM in real impl)
            # For now, simulate by running a capability if available
            if agent.spec.capabilities:
                cap_name = agent.spec.capabilities[0]
                result = await self.capability_engine.execute(
                    cap_name,
                    input_summary=task.description,
                    **context,
                )
                if result.success:
                    task.result = result.output
                    task.status = "completed"
                else:
                    task.status = "failed"
                    task.error = result.error
            else:
                # No capabilities - just return simulated result
                task.result = f"[Simulated] Completed: {task.description}"
                task.status = "completed"

            agent.result = task.result
            agent.state = AgentState.COMPLETED

        except Exception as e:
            task.status = "failed"
            task.error = str(e)
            agent.error = str(e)
            agent.state = AgentState.FAILED
            logger.error(f"Task {task.id} failed: {e}")

        finally:
            task.completed_at = datetime.now(timezone.utc)
            agent.completed_at = task.completed_at

    def get_agent(self, agent_id: str) -> Optional[AgentInstance]:
        return self._agents.get(agent_id)

    def get_task(self, task_id: str) -> Optional[OrchestrationTask]:
        return self._tasks.get(task_id)

    def get_all_tasks(self) -> list[OrchestrationTask]:
        return list(self._tasks.values())


def create_orchestrator(
    capability_engine: CapabilityEngine,
    capability_registry: CapabilityRegistry,
    sandbox: Sandbox,
    message_bus: Optional[MessageBus] = None,
) -> MultiAgentOrchestrator:
    """Factory function to create an orchestrator."""
    return MultiAgentOrchestrator(
        capability_engine=capability_engine,
        capability_registry=capability_registry,
        sandbox=sandbox,
        message_bus=message_bus,
    )
