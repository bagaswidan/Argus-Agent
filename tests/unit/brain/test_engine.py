"""Test Capability Engine — Argus."""
from __future__ import annotations

import asyncio

import pytest

from argus.capability.engine import (
    CapabilityEngine,
    CapabilityRegistry,
    CapabilitySpec,
    ExecutionPolicy,
    RetryPolicy,
)
from argus.common.events import EventBus
from argus.runtime.sandbox import ResourceLimit, Sandbox


class TestCapabilityEngineExecution:
    """High-level engine execution with retry and policy."""

    @pytest.mark.asyncio
    async def test_basic_execute_success(self):
        registry = CapabilityRegistry()
        sandbox = Sandbox(resource_limit=ResourceLimit.default())

        def add(a: int, b: int) -> int:
            return a + b

        spec = CapabilitySpec(
            name="add",
            description="Add two numbers",
            parameters={"type": "object", "properties": {"a": {"type": "integer"}, "b": {"type": "integer"}}},
            returns={"type": "integer"},
        )
        registry.register(spec, add, ExecutionPolicy.default())

        engine = CapabilityEngine(registry, sandbox)
        result = await engine.execute("add", 2, 3)

        assert result.success is True
        assert result.output == "5"

    @pytest.mark.asyncio
    async def test_execute_with_retry_linear(self):
        registry = CapabilityRegistry()
        sandbox = Sandbox(resource_limit=ResourceLimit.default())
        event_bus = EventBus()

        call_count = 0

        def flaky() -> str:
            nonlocal call_count
            call_count += 1
            if call_count < 3:
                raise ValueError("not ready")
            return "success"

        spec = CapabilitySpec(
            name="flaky",
            description="Flaky capability",
            parameters={},
            returns={"type": "string"},
            retryable=True,
        )
        policy = ExecutionPolicy(
            max_retries=3,
            retry_policy=RetryPolicy.LINEAR,
            retry_delay_seconds=0.01,
        )
        registry.register(spec, flaky, policy)

        engine = CapabilityEngine(registry, sandbox, event_bus)
        result = await engine.execute("flaky")

        assert result.success is True
        assert result.output == "success"
        assert call_count == 3

    @pytest.mark.asyncio
    async def test_execute_retry_exponential(self):
        registry = CapabilityRegistry()
        sandbox = Sandbox(resource_limit=ResourceLimit.default())

        def fail_twice_then_ok() -> str:
            if fail_twice_then_ok.count < 2:
                fail_twice_then_ok.count += 1
                raise ValueError("fail")
            return "ok"
        fail_twice_then_ok.count = 0

        spec = CapabilitySpec(
            name="flaky_exp",
            description="Exponential retry",
            parameters={},
            returns={"type": "string"},
            retryable=True,
        )
        policy = ExecutionPolicy(
            max_retries=3,
            retry_policy=RetryPolicy.EXPONENTIAL,
            retry_delay_seconds=0.01,
            max_retry_delay_seconds=0.05,
        )
        registry.register(spec, fail_twice_then_ok, policy)

        engine = CapabilityEngine(registry, sandbox)
        result = await engine.execute("flaky_exp")

        assert result.success is True
        assert result.output == "ok"

    @pytest.mark.asyncio
    async def test_non_retryable_fails_fast(self):
        registry = CapabilityRegistry()
        sandbox = Sandbox(resource_limit=ResourceLimit.default())

        def fail() -> str:
            raise ValueError("permanent failure")

        spec = CapabilitySpec(
            name="fail",
            description="Always fails",
            parameters={},
            returns={"type": "string"},
            retryable=False,
        )
        registry.register(spec, fail, ExecutionPolicy(max_retries=3))

        engine = CapabilityEngine(registry, sandbox)
        result = await engine.execute("fail")

        assert result.success is False
        assert "permanent failure" in result.error

    @pytest.mark.asyncio
    async def test_capability_not_found(self):
        registry = CapabilityRegistry()
        sandbox = Sandbox(resource_limit=ResourceLimit.default())
        engine = CapabilityEngine(registry, sandbox)
        result = await engine.execute("missing")
        assert result.success is False
        assert "not found" in result.error.lower()

    @pytest.mark.asyncio
    async def test_engine_audit_log(self):
        registry = CapabilityRegistry()
        sandbox = Sandbox(
            resource_limit=ResourceLimit.default(),
            audit_log_path=None,
        )

        def ping() -> str:
            return "pong"

        spec = CapabilitySpec(
            name="ping",
            description="Test ping",
            parameters={},
            returns={"type": "string"},
        )
        registry.register(spec, ping)

        engine = CapabilityEngine(registry, sandbox)
        await engine.execute("ping")

        audits = engine.get_audit_log()
        assert len(audits) >= 1
        assert audits[0].capability_name == "ping"


class TestExecutionPolicyTimeouts:
    """Policy timeout behavior."""

    @pytest.mark.asyncio
    async def test_enforces_policy_timeout(self):
        registry = CapabilityRegistry()
        sandbox = Sandbox(resource_limit=ResourceLimit.default())

        async def slow() -> str:
            await asyncio.sleep(0.5)
            return "done"

        spec = CapabilitySpec(
            name="slow",
            description="Slow",
            parameters={},
            returns={"type": "string"},
        )
        policy = ExecutionPolicy(timeout_seconds=0.05)
        registry.register(spec, slow, policy)

        engine = CapabilityEngine(registry, sandbox)
        result = await engine.execute("slow")

        assert result.success is False
        assert "timeout" in result.error.lower()


class TestCapabilityRegistry:
    """Registry lifecycle and lookups."""

    def test_unregister_removes_all(self):
        registry = CapabilityRegistry()

        spec = CapabilitySpec(name="temp", description="t", parameters={}, returns={})
        registry.register(spec, lambda: None)
        assert registry.unregister("temp") is True
        assert registry.get_spec("temp") is None
        assert registry.unregister("temp") is False

    def test_register_duplicate_raises(self):
        registry = CapabilityRegistry()
        spec = CapabilitySpec(name="dup", description="", parameters={}, returns={})
        registry.register(spec, lambda: None)
        with pytest.raises(Exception):
            registry.register(spec, lambda: None)

    def test_list_capabilities_sorted(self):
        registry = CapabilityRegistry()
        specs = [
            CapabilitySpec(name="z", description="", parameters={}, returns={}),
            CapabilitySpec(name="a", description="", parameters={}, returns={}),
        ]
        registry.register(specs[0], lambda: None)
        registry.register(specs[1], lambda: None)
        names = [c.name for c in registry.list_capabilities()]
        assert names == ["z", "a"]


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
