"""End-to-end usage of Argus core modules.

Run with:
    PYTHONPATH=src python examples/usage/quickstart.py
"""
from __future__ import annotations

import asyncio

from argus.capability.engine import (
    CapabilityEngine,
    CapabilityRegistry,
    CapabilitySpec,
    ExecutionPolicy,
)
from argus.contracts.types import CapabilityRequest, validate_contract
from argus.runtime.sandbox import ResourceLimit, Sandbox
from argus.security.engine import create_security_engine
from argus.brain.planning import create_planning_engine
from argus.runtime.workflow import WorkflowStep, create_workflow_engine


def main() -> None:
    # 1. Contracts — typed messages
    req = CapabilityRequest(capability_id="math.add")
    validate_contract(req)
    print(f"[contracts] validated: {req.capability_id}")

    # 2. Security — default deny, grant explicitly
    sec = create_security_engine()
    sec.allow("agent", "math.*")
    print(f"[security] math.add allowed: {sec.can('agent', 'math.add')}")
    print(f"[security] secret.read denied: {sec.can('agent', 'secret.read')}")

    # 3. Capability — execute behind the security check
    if sec.can("agent", "math.add"):
        registry = CapabilityRegistry()

        def add(a: int, b: int) -> int:
            return a + b

        spec = CapabilitySpec(
            name="math.add",
            description="Add two numbers",
            parameters={"type": "object", "properties": {"a": {"type": "integer"}, "b": {"type": "integer"}}},
            returns={"type": "integer"},
        )
        registry.register(spec, add, ExecutionPolicy.default())

        sandbox = Sandbox(resource_limit=ResourceLimit.default())
        engine = CapabilityEngine(registry, sandbox)
        result = asyncio.run(engine.execute("math.add", 2, 3))
        print(f"[capability] math.add(2,3) -> {result.output}")

    # 4. Planning — dependency graph
    planner = create_planning_engine()
    plan = planner.create_plan("demo", [
        {"action": "build", "id": "build"},
        {"action": "test", "id": "test", "depends_on": ["build"]},
    ])
    print(f"[planning] steps={len(plan.steps)} est={plan.estimated_duration_ms}ms")

    # 5. Workflow — run steps with checkpoints
    engine = create_workflow_engine()

    async def step(x: int) -> int:
        return x * 2

    run = engine.create(
        "demo-wf",
        [WorkflowStep(name=f"s{i}", fn=step, args=(i,)) for i in range(3)],
    )
    asyncio.run(engine.run(run.workflow_id))
    print(f"[workflow] state={run.state.value} steps={[s.status for s in run.steps]}")


if __name__ == "__main__":
    main()
