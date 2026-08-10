"""Planning Engine — Argus Brain (Spec §13).

Creates execution plans with dependency graphs, alternatives, resource
estimation, and replanning on failure.
"""
from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from typing import Any, Optional


class PlanError(Exception):
    """Raised on plan construction errors."""


@dataclass
class PlanStep:
    """One step in an execution plan."""

    id: str
    action: str
    params: dict[str, Any] = field(default_factory=dict)
    depends_on: list[str] = field(default_factory=list)
    estimated_cost: float = 0.0
    estimated_duration_ms: int = 0
    status: str = "pending"  # pending | ready | running | completed | failed | skipped


@dataclass
class ExecutionPlan:
    """A full plan with ordered steps and dependency graph."""

    goal: str
    steps: list[PlanStep] = field(default_factory=list)
    plan_id: str = field(default_factory=lambda: uuid.uuid4().hex[:12])
    created_at: float = 0.0
    estimated_total_cost: float = 0.0
    estimated_duration_ms: int = 0

    def ready_steps(self) -> list[PlanStep]:
        """Steps whose dependencies are all completed."""
        completed = {s.id for s in self.steps if s.status == "completed"}
        return [
            s for s in self.steps
            if s.status == "pending" and all(d in completed for d in s.depends_on)
        ]

    def is_complete(self) -> bool:
        return all(s.status in ("completed", "skipped") for s in self.steps)

    def failed_steps(self) -> list[PlanStep]:
        return [s for s in self.steps if s.status == "failed"]

    def dependency_graph(self) -> dict[str, list[str]]:
        return {s.id: list(s.depends_on) for s in self.steps}


class PlanningEngine:
    """Builds and manages execution plans."""

    def __init__(self) -> None:
        self._plans: dict[str, ExecutionPlan] = {}

    def create_plan(
        self,
        goal: str,
        actions: list[dict[str, Any]],
    ) -> ExecutionPlan:
        """Create a plan from action specs.

        Each action: {"action": str, "params": dict, "depends_on": [step_ids]}
        Returns plan with generated step ids and estimates.
        """
        plan = ExecutionPlan(goal=goal)
        for spec in actions:
            step_id = spec.get("id") or uuid.uuid4().hex[:8]
            step = PlanStep(
                id=step_id,
                action=spec["action"],
                params=spec.get("params", {}),
                depends_on=list(spec.get("depends_on", [])),
                estimated_cost=float(spec.get("estimated_cost", 0.0)),
                estimated_duration_ms=int(spec.get("estimated_duration_ms", 1000)),
            )
            plan.steps.append(step)

        self._validate_graph(plan)
        plan.estimated_total_cost = sum(s.estimated_cost for s in plan.steps)
        plan.estimated_duration_ms = self._estimate_duration(plan)
        self._plans[plan.plan_id] = plan
        return plan

    def get_plan(self, plan_id: str) -> Optional[ExecutionPlan]:
        return self._plans.get(plan_id)

    def _validate_graph(self, plan: ExecutionPlan) -> None:
        """Detect missing dependencies and cycles."""
        ids = {s.id for s in plan.steps}
        for s in plan.steps:
            missing = [d for d in s.depends_on if d not in ids]
            if missing:
                raise PlanError(f"Step {s.id} depends on unknown steps: {missing}")

        # cycle detection via DFS
        visited: dict[str, int] = {}  # 0=visiting, 1=done
        graph = plan.dependency_graph()

        def visit(node: str) -> None:
            if node in visited:
                if visited[node] == 1:
                    return
                raise PlanError(f"Circular dependency at step {node}")
            visited[node] = 0
            for dep in graph.get(node, []):
                visit(dep)
            visited[node] = 1

        for s in plan.steps:
            visit(s.id)

    def _estimate_duration(self, plan: ExecutionPlan) -> int:
        """Estimate critical path duration."""
        duration: dict[str, int] = {}
        for s in plan.steps:
            dep_duration = max((duration[d] for d in s.depends_on), default=0)
            duration[s.id] = dep_duration + s.estimated_duration_ms
        return max(duration.values(), default=0)

    def replan(
        self,
        plan: ExecutionPlan,
        failed_step_ids: list[str],
        replacement_actions: list[dict[str, Any]],
    ) -> ExecutionPlan:
        """Create a new plan replacing failed steps (Spec §13 replanning)."""
        # Keep steps that are completed/skipped; mark failed ones; add replacements
        new_steps: list[PlanStep] = []
        failed_set = set(failed_step_ids)
        for s in plan.steps:
            if s.id in failed_set:
                new_steps.append(
                    PlanStep(
                        id=s.id,
                        action=s.action,
                        params=s.params,
                        depends_on=s.depends_on,
                        status="failed",
                    )
                )
            else:
                new_steps.append(s)

        for spec in replacement_actions:
            new_steps.append(
                PlanStep(
                    id=spec.get("id") or uuid.uuid4().hex[:8],
                    action=spec["action"],
                    params=spec.get("params", {}),
                    depends_on=list(spec.get("depends_on", [])),
                    estimated_cost=float(spec.get("estimated_cost", 0.0)),
                    estimated_duration_ms=int(spec.get("estimated_duration_ms", 1000)),
                )
            )

        new_plan = ExecutionPlan(goal=plan.goal)
        new_plan.steps = new_steps
        self._validate_graph(new_plan)
        new_plan.estimated_total_cost = sum(s.estimated_cost for s in new_plan.steps)
        new_plan.estimated_duration_ms = self._estimate_duration(new_plan)
        self._plans[new_plan.plan_id] = new_plan
        return new_plan


def create_planning_engine() -> PlanningEngine:
    return PlanningEngine()
