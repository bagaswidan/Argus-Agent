"""Test Sandbox Runtime — Argus Core Foundation."""
from __future__ import annotations

import asyncio
import pytest
import tempfile
from pathlib import Path

from argus.runtime.sandbox import (
    Sandbox,
    SandboxMode,
    ResourceLimit,
    ExecutionResult,
)
from argus.capability.engine import (
    CapabilityEngine,
    CapabilityRegistry,
    CapabilitySpec,
    ExecutionPolicy,
    RetryPolicy,
    cap,
)
from argus.common.events import EventBus


def test_sandbox_basic_execution():
    """Test basic sandbox execution."""
    async def run_test():
        sandbox = Sandbox(resource_limit=ResourceLimit.default())

        def hello(name: str) -> str:
            return f"Hello, {name}!"

        result = await sandbox.execute("hello", hello, "World")
        assert result.success is True
        assert "Hello, World!" in result.output
        assert result.exit_code == 0
        assert result.duration_ms >= 0

    asyncio.run(run_test())


def test_sandbox_error_handling():
    """Test sandbox handles errors gracefully."""
    async def run_test():
        sandbox = Sandbox(resource_limit=ResourceLimit.default())

        def fail() -> str:
            raise ValueError("intentional error")

        result = await sandbox.execute("fail", fail)
        assert result.success is False
        assert "intentional error" in result.error
        assert result.exit_code != 0

    asyncio.run(run_test())


def test_sandbox_timeout():
    """Test sandbox enforces timeout."""
    async def run_test():
        sandbox = Sandbox(resource_limit=ResourceLimit(max_cpu_seconds=1))

        async def slow() -> str:
            await asyncio.sleep(5)
            return "done"

        result = await sandbox.execute("slow", slow)
        assert result.success is False
        assert "timeout" in result.error.lower()

    asyncio.run(run_test())


def test_sandbox_audit_log():
    """Test sandbox writes audit log."""
    async def run_test():
        with tempfile.TemporaryDirectory() as tmpdir:
            audit_path = Path(tmpdir) / "audit.jsonl"
            sandbox = Sandbox(
                resource_limit=ResourceLimit.default(),
                audit_log_path=audit_path,
            )

            def test_func(x: int) -> int:
                return x * 2

            await sandbox.execute("test_func", test_func, 5)
            await sandbox.execute("test_func", test_func, 10)

            # Check audit log
            content = audit_path.read_text()
            lines = content.strip().split("\n")
            assert len(lines) == 2

            import json
            entry = json.loads(lines[0])
            assert entry["capability_name"] == "test_func"
            assert entry["result"]["success"] is True
            assert entry["result"]["output"] == "10"

    asyncio.run(run_test())


def test_resource_limit_strict():
    """Test strict resource limits."""
    strict = ResourceLimit.strict()
    assert strict.max_cpu_seconds == 10
    assert strict.max_memory_mb == 128
    assert strict.allow_network is False
    assert strict.allow_fs_write is False


def test_resource_limit_relaxed():
    """Test relaxed resource limits."""
    relaxed = ResourceLimit.relaxed()
    assert relaxed.max_cpu_seconds == 120
    assert relaxed.max_memory_mb == 2048
    assert relaxed.allow_network is True
    assert relaxed.allow_fs_write is True


class TestCapabilityRegistry:
    """Test capability registry."""

    @pytest.mark.asyncio
    async def test_register_and_get(self):
        registry = CapabilityRegistry()

        @cap(
            name="echo",
            description="Echo input",
            parameters={"type": "object", "properties": {"text": {"type": "string"}}},
            returns={"type": "string"},
        )
        def echo(text: str) -> str:
            return text

        spec = CapabilitySpec(
            name="echo",
            description="Echo input",
            parameters={"type": "object", "properties": {"text": {"type": "string"}}},
            returns={"type": "string"},
        )

        registry.register(spec, echo)
        assert registry.get_spec("echo") is not None
        assert registry.get_implementation("echo") is echo
        assert len(registry.list_capabilities()) == 1

    @pytest.mark.asyncio
    async def test_duplicate_registration_fails(self):
        registry = CapabilityRegistry()

        spec = CapabilitySpec(
            name="dup",
            description="Test",
            parameters={},
            returns={},
        )

        def impl1(): pass
        def impl2(): pass

        registry.register(spec, impl1)
        with pytest.raises(Exception):  # CapabilityEngineError
            registry.register(spec, impl2)

    @pytest.mark.asyncio
    async def test_unregister(self):
        registry = CapabilityRegistry()

        spec = CapabilitySpec(name="test", description="", parameters={}, returns={})
        registry.register(spec, lambda: None)
        assert registry.unregister("test") is True
        assert registry.unregister("test") is False
        assert registry.get_spec("test") is None


class TestCapabilityEngine:
    """Test capability engine."""

    @pytest.mark.asyncio
    async def test_basic_execution(self):
        registry = CapabilityRegistry()
        sandbox = Sandbox(resource_limit=ResourceLimit.default())

        def add(a: int, b: int) -> int:
            return a + b

        spec = CapabilitySpec(
            name="add",
            description="Add two numbers",
            parameters={
                "type": "object",
                "properties": {"a": {"type": "integer"}, "b": {"type": "integer"}},
            },
            returns={"type": "integer"},
        )
        registry.register(spec, add)

        engine = CapabilityEngine(registry, sandbox)
        result = await engine.execute("add", 2, 3)

        assert result.success is True
        assert result.output == "5"

    @pytest.mark.asyncio
    async def test_retry_on_failure(self):
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
        registry.register(
            spec,
            flaky,
            ExecutionPolicy(
                max_retries=3,
                retry_policy=RetryPolicy.LINEAR,
                retry_delay_seconds=0.01,
            ),
        )

        engine = CapabilityEngine(registry, sandbox, event_bus)
        result = await engine.execute("flaky")

        assert result.success is True
        assert result.output == "success"
        assert call_count == 3

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
            retryable=False,  # Not retryable
        )
        registry.register(
            spec,
            fail,
            ExecutionPolicy(max_retries=3),
        )

        engine = CapabilityEngine(registry, sandbox)
        result = await engine.execute("fail")

        assert result.success is False
        assert "permanent failure" in result.error

    @pytest.mark.asyncio
    async def test_capability_not_found(self):
        registry = CapabilityRegistry()
        sandbox = Sandbox(resource_limit=ResourceLimit.default())

        engine = CapabilityEngine(registry, sandbox)
        result = await engine.execute("nonexistent")

        assert result.success is False
        assert "not found" in result.error.lower()

    @pytest.mark.asyncio
    async def test_execution_policy_timeout(self):
        registry = CapabilityRegistry()
        sandbox = Sandbox(resource_limit=ResourceLimit.default())

        async def slow() -> str:
            await asyncio.sleep(2)
            return "done"

        spec = CapabilitySpec(
            name="slow",
            description="Slow capability",
            parameters={},
            returns={"type": "string"},
        )
        registry.register(
            spec,
            slow,
            ExecutionPolicy(timeout_seconds=1),
        )

        engine = CapabilityEngine(registry, sandbox)
        result = await engine.execute("slow")

        assert result.success is False
        assert "timeout" in result.error.lower()


class TestExecutionPolicy:
    """Test execution policies."""

    def test_default_policy(self):
        policy = ExecutionPolicy.default()
        assert policy.max_retries == 0
        assert policy.timeout_seconds == 30
        assert policy.sandbox_mode == SandboxMode.THREAD

    def test_strict_policy(self):
        policy = ExecutionPolicy.strict()
        assert policy.max_retries == 0
        assert policy.timeout_seconds == 10
        assert policy.resource_limit.max_cpu_seconds == 10
        assert policy.resource_limit.max_memory_mb == 128

    def test_lenient_policy(self):
        policy = ExecutionPolicy.lenient()
        assert policy.max_retries == 3
        assert policy.retry_policy == RetryPolicy.EXPONENTIAL
        assert policy.timeout_seconds == 120
        assert policy.resource_limit.max_cpu_seconds == 120


if __name__ == "__main__":
    pytest.main([__file__, "-v"])