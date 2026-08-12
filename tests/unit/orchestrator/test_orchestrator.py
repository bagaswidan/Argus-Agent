"""Test Multi-Agent Orchestrator — Argus Phase 2."""
from __future__ import annotations

import asyncio

import pytest

from argus.capability.engine import (
    CapabilityEngine,
    CapabilityRegistry,
    CapabilitySpec,
    ExecutionPolicy,
)
from argus.orchestrator.agent import AgentInstance, AgentRole, AgentSpec, AgentState
from argus.orchestrator.communication import AgentMessage, MessageBus
from argus.orchestrator.orchestrator import (
    OrchestrationPlan,
    OrchestrationResult,
    OrchestrationTask,
    create_orchestrator,
)
from argus.runtime.sandbox import ResourceLimit, Sandbox


class TestAgentSpec:
    """Test AgentSpec dataclass."""

    def test_default_values(self):
        spec = AgentSpec(name="Test Agent", role=AgentRole.WORKER)
        assert spec.id is not None
        assert spec.name == "Test Agent"
        assert spec.role == AgentRole.WORKER
        assert spec.capabilities == []

    def test_to_dict(self):
        spec = AgentSpec(
            id="test-id",
            name="Test",
            role=AgentRole.ORCHESTRATOR,
            capabilities=["cap1", "cap2"],
        )
        d = spec.to_dict()
        assert d["id"] == "test-id"
        assert d["name"] == "Test"
        assert d["role"] == "orchestrator"
        assert d["capabilities"] == ["cap1", "cap2"]


class TestAgentInstance:
    """Test AgentInstance dataclass."""

    def test_initial_state(self):
        spec = AgentSpec(name="Test")
        instance = AgentInstance(spec=spec)
        assert instance.state == AgentState.IDLE
        assert instance.result is None
        assert instance.error is None


class TestMessageBus:
    """Test MessageBus."""

    @pytest.mark.asyncio
    async def test_subscribe_and_send(self):
        bus = MessageBus()
        queue = await bus.subscribe("agent1")

        msg = AgentMessage(from_agent="agent2", to_agent="agent1", payload={"text": "hello"})
        await bus.send(msg)

        received = await queue.get()
        assert received.from_agent == "agent2"
        assert received.payload["text"] == "hello"

    @pytest.mark.asyncio
    async def test_broadcast(self):
        bus = MessageBus()
        q1 = await bus.subscribe("agent1")
        q2 = await bus.subscribe("agent2")

        msg = AgentMessage(from_agent="system", to_agent="", payload={"broadcast": True})
        await bus.broadcast(msg)

        r1 = await q1.get()
        r2 = await q2.get()
        assert r1.payload["broadcast"] is True
        assert r2.payload["broadcast"] is True

    @pytest.mark.asyncio
    async def test_request_response(self):
        bus = MessageBus()

        # Test direct send/receive between agents
        agent2_queue = await bus.subscribe("agent2")
        agent1_queue = await bus.subscribe("agent1")

        # Send from agent1 to agent2
        msg = AgentMessage(from_agent="agent1", to_agent="agent2", payload={"data": "ping"})
        await bus.send(msg)

        # Agent2 receives
        received = await agent2_queue.get()
        assert received.from_agent == "agent1"
        assert received.payload["data"] == "ping"

        # Agent2 responds to agent1
        response = AgentMessage(
            from_agent="agent2",
            to_agent="agent1",
            payload={"answer": "pong"},
        )
        await bus.send(response)

        # Agent1 receives response
        received_response = await agent1_queue.get()
        assert received_response.from_agent == "agent2"
        assert received_response.payload["answer"] == "pong"


class TestOrchestrationTask:
    """Test OrchestrationTask."""

    def test_creation(self):
        task = OrchestrationTask(description="Test task", assigned_agent="agent1")
        assert task.id is not None
        assert task.status == "pending"
        assert task.dependencies == []


class TestOrchestrationPlan:
    """Test OrchestrationPlan."""

    def test_creation(self):
        plan = OrchestrationPlan(goal="Test goal")
        assert plan.goal == "Test goal"
        assert plan.tasks == []
        assert plan.agents == []


class TestMultiAgentOrchestrator:
    """Test MultiAgentOrchestrator."""

    def create_mock_engine(self):
        """Create a mock capability engine."""
        registry = CapabilityRegistry()
        sandbox = Sandbox(resource_limit=ResourceLimit.default())

        # Register a test capability
        def test_cap(**kwargs) -> str:
            input_summary = kwargs.get("input_summary", "")
            return f"Executed: {input_summary}"

        spec = CapabilitySpec(
            name="test_cap",
            description="Test capability",
            parameters={},
            returns={"type": "string"},
        )
        registry.register(spec, test_cap, ExecutionPolicy.default())

        engine = CapabilityEngine(registry, sandbox)
        return engine, registry, sandbox

    @pytest.mark.asyncio
    async def test_create_plan(self):
        engine, registry, sandbox = self.create_mock_engine()
        orchestrator = create_orchestrator(engine, registry, sandbox)

        spec1 = AgentSpec(name="Worker1", role=AgentRole.WORKER, capabilities=["test_cap"])
        spec2 = AgentSpec(name="Worker2", role=AgentRole.WORKER, capabilities=["test_cap"])

        plan = await orchestrator.create_plan("Test goal", [spec1, spec2])

        assert plan.goal == "Test goal"
        assert len(plan.tasks) == 2
        assert len(plan.agents) == 2
        assert plan.tasks[0].assigned_agent == spec1.id
        assert plan.tasks[1].assigned_agent == spec2.id
        assert plan.tasks[1].dependencies == [plan.tasks[0].id]

    @pytest.mark.asyncio
    async def test_execute_plan_simple(self):
        engine, registry, sandbox = self.create_mock_engine()
        orchestrator = create_orchestrator(engine, registry, sandbox)

        spec = AgentSpec(name="Worker", role=AgentRole.WORKER, capabilities=["test_cap"])
        plan = await orchestrator.create_plan("Simple task", [spec])

        result = await asyncio.wait_for(orchestrator.execute_plan(plan), timeout=10.0)

        assert result.success is True
        assert result.goal == "Simple task"
        assert spec.id in result.agent_results
        assert "Executed:" in result.agent_results[spec.id]

    @pytest.mark.asyncio
    async def test_execute_plan_multiple_agents(self):
        engine, registry, sandbox = self.create_mock_engine()
        orchestrator = create_orchestrator(engine, registry, sandbox)

        spec1 = AgentSpec(name="Worker1", role=AgentRole.WORKER, capabilities=["test_cap"])
        spec2 = AgentSpec(name="Worker2", role=AgentRole.WORKER, capabilities=["test_cap"])

        plan = await orchestrator.create_plan("Multi-agent task", [spec1, spec2])

        result = await asyncio.wait_for(orchestrator.execute_plan(plan), timeout=10.0)

        assert result.success is True
        assert spec1.id in result.agent_results
        assert spec2.id in result.agent_results

    @pytest.mark.asyncio
    async def test_execute_plan_no_capabilities(self):
        engine, registry, sandbox = self.create_mock_engine()
        orchestrator = create_orchestrator(engine, registry, sandbox)

        spec = AgentSpec(name="Worker", role=AgentRole.WORKER, capabilities=[])
        plan = await orchestrator.create_plan("No caps task", [spec])

        result = await orchestrator.execute_plan(plan)

        assert result.success is True
        assert "[Simulated]" in result.agent_results[spec.id]

    def test_get_agent(self):
        engine, registry, sandbox = self.create_mock_engine()
        orchestrator = create_orchestrator(engine, registry, sandbox)

        spec = AgentSpec(name="Worker")
        agent = AgentInstance(spec=spec)
        orchestrator._agents[spec.id] = agent

        retrieved = orchestrator.get_agent(spec.id)
        assert retrieved is agent

    def test_get_task(self):
        engine, registry, sandbox = self.create_mock_engine()
        orchestrator = create_orchestrator(engine, registry, sandbox)

        task = OrchestrationTask(id="task-1", description="Test")
        orchestrator._tasks[task.id] = task

        retrieved = orchestrator.get_task("task-1")
        assert retrieved is task


class TestOrchestrationResult:
    """Test OrchestrationResult."""

    def test_to_dict(self):
        plan = OrchestrationPlan(goal="Test")
        result = OrchestrationResult(
            success=True,
            goal="Test",
            plan=plan,
            agent_results={"agent1": "result1"},
            total_duration_ms=100,
        )

        d = result.to_dict()
        assert d["success"] is True
        assert d["goal"] == "Test"
        assert d["agent_results"]["agent1"] == "result1"
        assert d["total_duration_ms"] == 100


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
