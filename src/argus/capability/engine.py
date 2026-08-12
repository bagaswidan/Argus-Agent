"""Capability Engine — Argus.

High-level capability execution with registry integration, retry logic,
cost tracking, and execution policies.
"""
from __future__ import annotations

import asyncio
import uuid
from dataclasses import dataclass, field
from datetime import UTC, datetime
from enum import StrEnum
from typing import TYPE_CHECKING, Any

from argus.common.errors import ArgusError
from argus.common.events import Event, EventBus, EventPriority
from argus.common.logging import get_logger
from argus.runtime.sandbox import (
    AuditEntry,
    ExecutionResult,
    ResourceLimit,
    Sandbox,
    SandboxMode,
)

if TYPE_CHECKING:
    from collections.abc import Callable

logger = get_logger(__name__)


class RetryPolicy(StrEnum):
    """Retry policy for capability execution."""

    NONE = "none"
    LINEAR = "linear"  # Fixed delay between retries
    EXPONENTIAL = "exponential"  # Exponential backoff


@dataclass
class CapabilitySpec:
    """Capability specification for registry and LLM consumption."""

    name: str
    description: str
    parameters: dict[str, Any]  # JSON Schema
    returns: dict[str, Any]  # JSON Schema
    retryable: bool = False
    estimated_cost_usd: float = 0.0
    estimated_duration_ms: int = 1000
    resource_limit: ResourceLimit | None = None
    tags: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "description": self.description,
            "parameters": self.parameters,
            "returns": self.returns,
            "retryable": self.retryable,
            "estimated_cost_usd": self.estimated_cost_usd,
            "estimated_duration_ms": self.estimated_duration_ms,
            "tags": self.tags,
        }


@dataclass
class ExecutionPolicy:
    """Execution policy for capabilities."""

    max_retries: int = 0
    retry_policy: RetryPolicy = RetryPolicy.NONE
    retry_delay_seconds: float = 1.0
    max_retry_delay_seconds: float = 60.0
    timeout_seconds: int = 30
    sandbox_mode: SandboxMode = SandboxMode.THREAD  # Default to thread for local functions
    resource_limit: ResourceLimit | None = None

    @classmethod
    def default(cls) -> ExecutionPolicy:
        return cls()

    @classmethod
    def strict(cls) -> ExecutionPolicy:
        return cls(
            max_retries=0,
            timeout_seconds=10,
            sandbox_mode=SandboxMode.SUBPROCESS,
            resource_limit=ResourceLimit.strict(),
        )

    @classmethod
    def lenient(cls) -> ExecutionPolicy:
        return cls(
            max_retries=3,
            retry_policy=RetryPolicy.EXPONENTIAL,
            retry_delay_seconds=1.0,
            max_retry_delay_seconds=30.0,
            timeout_seconds=120,
            sandbox_mode=SandboxMode.SUBPROCESS,
            resource_limit=ResourceLimit.relaxed(),
        )


@dataclass
class CapabilityExecution:
    """Track a capability execution with retries."""

    capability_name: str
    correlation_id: str
    started_at: datetime
    attempt: int = 0
    last_result: ExecutionResult | None = None
    total_duration_ms: int = 0
    total_cost_usd: float = 0.0


class CapabilityEngineError(ArgusError):
    """Capability engine errors."""

    code = "CAPABILITY_ENGINE_ERROR"


class CapabilityRegistry:
    """Registry for capability specifications."""

    def __init__(self, event_bus: EventBus | None = None):
        self._capabilities: dict[str, CapabilitySpec] = {}
        self._implementations: dict[str, Callable] = {}
        self._policies: dict[str, ExecutionPolicy] = {}
        self._tasks: set[asyncio.Task] = set()
        self.event_bus = event_bus

    def register(
        self,
        spec: CapabilitySpec,
        implementation: Callable[..., Any],
        policy: ExecutionPolicy | None = None,
    ) -> None:
        """Register a capability with its implementation."""
        if spec.name in self._capabilities:
            raise CapabilityEngineError(
                f"Capability '{spec.name}' already registered",
                code="DUPLICATE_CAPABILITY",
            )

        self._capabilities[spec.name] = spec
        self._implementations[spec.name] = implementation
        self._policies[spec.name] = policy or ExecutionPolicy.default()

        if self.event_bus:
            try:
                asyncio.get_running_loop()
            except RuntimeError:
                # No running event loop – skip event publishing to avoid
                # "no current event loop" errors during registration.
                pass
            else:
                task = asyncio.create_task(
                    self.event_bus.publish(
                        Event(
                            type="capability.registered",
                            payload={"name": spec.name, "spec": spec.to_dict()},
                            priority=EventPriority.NORMAL,
                        ),
                    ),
                )
                self._tasks.add(task)
                task.add_done_callback(self._tasks.discard)

    def get_spec(self, name: str) -> CapabilitySpec | None:
        return self._capabilities.get(name)

    def get_implementation(self, name: str) -> Callable | None:
        return self._implementations.get(name)

    def get_policy(self, name: str) -> ExecutionPolicy:
        return self._policies.get(name, ExecutionPolicy.default())

    def list_capabilities(self) -> list[CapabilitySpec]:
        return list(self._capabilities.values())

    def unregister(self, name: str) -> bool:
        if name in self._capabilities:
            del self._capabilities[name]
            del self._implementations[name]
            del self._policies[name]
            return True
        return False


class CapabilityEngine:
    """High-level capability execution engine."""

    def __init__(
        self,
        registry: CapabilityRegistry,
        sandbox: Sandbox,
        event_bus: EventBus | None = None,
    ):
        self.registry = registry
        self.sandbox = sandbox
        self.event_bus = event_bus
        self._executions: dict[str, CapabilityExecution] = {}

    async def execute(
        self,
        capability_name: str,
        *args: Any,
        correlation_id: str | None = None,
        input_summary: str = "",
        **kwargs: Any,
    ) -> ExecutionResult:
        """Execute a capability with retry logic and policy enforcement."""
        spec = self.registry.get_spec(capability_name)
        if not spec:
            return ExecutionResult(
                success=False,
                error=f"Capability '{capability_name}' not found",
                exit_code=-1,
            )

        implementation = self.registry.get_implementation(capability_name)
        if not implementation:
            return ExecutionResult(
                success=False,
                error=f"Capability '{capability_name}' has no implementation",
                exit_code=-1,
            )

        policy = self.registry.get_policy(capability_name)
        cid = correlation_id or str(uuid.uuid4())

        execution = CapabilityExecution(
            capability_name=capability_name,
            correlation_id=cid,
            started_at=datetime.now(UTC),
        )
        self._executions[cid] = execution

        last_error = None
        max_attempts = policy.max_retries + 1

        for attempt in range(max_attempts):
            execution.attempt = attempt + 1

            # Use the engine's sandbox with policy resource limits applied via execution
            exec_sandbox = Sandbox(
                resource_limit=policy.resource_limit or self.sandbox.resource_limit,
                mode=policy.sandbox_mode,
                event_bus=self.event_bus,
                audit_log_path=self.sandbox.audit_log_path,
            )

            # Execute with timeout
            try:
                result = await asyncio.wait_for(
                    exec_sandbox.execute(
                        capability_name,
                        implementation,
                        *args,
                        input_summary=input_summary,
                        correlation_id=cid,
                        **kwargs,
                    ),
                    timeout=policy.timeout_seconds,
                )
            except TimeoutError:
                result = ExecutionResult(
                    success=False,
                    error=f"Capability execution timeout ({policy.timeout_seconds}s)",
                    exit_code=-1,
                    duration_ms=policy.timeout_seconds * 1000,
                )

            execution.last_result = result
            execution.total_duration_ms += result.duration_ms
            execution.total_cost_usd += spec.estimated_cost_usd

            # Merge audit logs from exec_sandbox into engine's sandbox
            for audit in exec_sandbox.get_audit_log():
                self.sandbox._audit_buffer.append(audit)

            if result.success:
                return result

            last_error = result.error

            # Check if we should retry
            if attempt < max_attempts - 1 and spec.retryable:
                delay = self._calculate_retry_delay(policy, attempt)
                logger.info(
                    f"Retrying capability '{capability_name}' (attempt {attempt + 2}/{max_attempts}) after {delay}s",
                )
                await asyncio.sleep(delay)
            else:
                break

        # All attempts failed
        return ExecutionResult(
            success=False,
            error=last_error or "Capability execution failed after all retries",
            exit_code=-1,
            duration_ms=execution.total_duration_ms,
        )

    def _calculate_retry_delay(self, policy: ExecutionPolicy, attempt: int) -> float:
        if policy.retry_policy == RetryPolicy.LINEAR:
            delay = policy.retry_delay_seconds
        elif policy.retry_policy == RetryPolicy.EXPONENTIAL:
            delay = policy.retry_delay_seconds * (2 ** attempt)
        else:
            delay = policy.retry_delay_seconds

        return min(delay, policy.max_retry_delay_seconds)

    def get_execution(self, correlation_id: str) -> CapabilityExecution | None:
        return self._executions.get(correlation_id)

    def get_audit_log(self) -> list[AuditEntry]:
        return self.sandbox.get_audit_log()


def cap(
    name: str,
    description: str,
    parameters: dict[str, Any],
    returns: dict[str, Any],
    retryable: bool = False,
    estimated_cost_usd: float = 0.0,
    estimated_duration_ms: int = 1000,
    tags: list[str] | None = None,
    policy: ExecutionPolicy | None = None,
) -> Callable[[Callable[..., Any]], Callable[..., Any]]:
    """Decorator to register a capability."""

    def decorator(func: Callable[..., Any]) -> Callable[..., Any]:
        spec = CapabilitySpec(
            name=name,
            description=description,
            parameters=parameters,
            returns=returns,
            retryable=retryable,
            estimated_cost_usd=estimated_cost_usd,
            estimated_duration_ms=estimated_duration_ms,
            tags=tags or [],
        )
        # Registry registration happens at engine startup
        setattr(func, "_capability_spec", spec)
        setattr(func, "_capability_policy", policy)
        return func

    return decorator


__all__ = [
    "CapabilityEngine",
    "CapabilityEngineError",
    "CapabilityExecution",
    "CapabilityRegistry",
    "CapabilitySpec",
    "ExecutionPolicy",
    "ExecutionResult",
    "RetryPolicy",
    "cap",
]
