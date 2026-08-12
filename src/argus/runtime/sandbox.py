"""Sandbox Runtime — Argus.

Isolated capability execution with resource limits, timeout enforcement,
and structured audit logging. Built from zero, no external sandbox deps.
"""
from __future__ import annotations

import asyncio
import json
import sys
import time
import uuid
from dataclasses import dataclass, field
from datetime import UTC, datetime
from enum import StrEnum
from typing import TYPE_CHECKING, Any

from argus.common.errors import ArgusError
from argus.common.events import Event, EventBus, EventPriority
from argus.common.logging import get_logger

if TYPE_CHECKING:
    from collections.abc import Callable
    from pathlib import Path

logger = get_logger(__name__)


class SandboxMode(StrEnum):
    """Execution isolation mode."""

    SUBPROCESS = "subprocess"  # Full process isolation (default)
    THREAD = "thread"  # Thread-based (lighter, less isolation)


class ResourceLimit:
    """Resource limits for sandboxed execution."""

    def __init__(
        self,
        max_cpu_seconds: int = 30,
        max_memory_mb: int = 512,
        max_output_bytes: int = 1024 * 1024,  # 1MB
        max_files: int = 100,
        allow_network: bool = False,
        allow_fs_write: bool = False,
    ):
        self.max_cpu_seconds = max_cpu_seconds
        self.max_memory_mb = max_memory_mb
        self.max_output_bytes = max_output_bytes
        self.max_files = max_files
        self.allow_network = allow_network
        self.allow_fs_write = allow_fs_write

    @classmethod
    def default(cls) -> ResourceLimit:
        return cls()

    @classmethod
    def strict(cls) -> ResourceLimit:
        return cls(
            max_cpu_seconds=10,
            max_memory_mb=128,
            max_output_bytes=64 * 1024,
            max_files=10,
            allow_network=False,
            allow_fs_write=False,
        )

    @classmethod
    def relaxed(cls) -> ResourceLimit:
        return cls(
            max_cpu_seconds=120,
            max_memory_mb=2048,
            max_output_bytes=10 * 1024 * 1024,
            max_files=500,
            allow_network=True,
            allow_fs_write=True,
        )



@dataclass
class ExecutionResult:
    """Result of sandboxed execution."""

    success: bool
    output: str = ""
    error: str = ""
    exit_code: int = 0
    duration_ms: int = 0
    memory_peak_mb: int = 0
    correlation_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "success": self.success,
            "output": self.output,
            "error": self.error,
            "exit_code": self.exit_code,
            "duration_ms": self.duration_ms,
            "memory_peak_mb": self.memory_peak_mb,
            "correlation_id": self.correlation_id,
            "metadata": self.metadata,
        }


@dataclass
class AuditEntry:
    """Audit log entry for capability execution."""

    correlation_id: str
    capability_name: str
    input_summary: str
    result: ExecutionResult
    started_at: datetime
    completed_at: datetime
    resource_limit: ResourceLimit
    mode: SandboxMode

    def to_dict(self) -> dict[str, Any]:
        return {
            "correlation_id": self.correlation_id,
            "capability_name": self.capability_name,
            "input_summary": self.input_summary,
            "result": self.result.to_dict(),
            "started_at": self.started_at.isoformat(),
            "completed_at": self.completed_at.isoformat(),
            "resource_limit": {
                "max_cpu_seconds": self.resource_limit.max_cpu_seconds,
                "max_memory_mb": self.resource_limit.max_memory_mb,
                "max_output_bytes": self.resource_limit.max_output_bytes,
                "max_files": self.resource_limit.max_files,
                "allow_network": self.resource_limit.allow_network,
                "allow_fs_write": self.resource_limit.allow_fs_write,
            },
            "mode": self.mode.value,
        }


class Sandbox:
    """Isolated execution environment for capabilities."""

    def __init__(
        self,
        resource_limit: ResourceLimit | None = None,
        mode: SandboxMode = SandboxMode.THREAD,  # Default to thread mode for local functions
        event_bus: EventBus | None = None,
        audit_log_path: Path | None = None,
    ) -> None:
        self.resource_limit = resource_limit or ResourceLimit.default()
        self.mode = mode
        self.event_bus = event_bus
        self.audit_log_path = audit_log_path
        self._audit_buffer: list[AuditEntry] = []

    async def execute(
        self,
        capability_name: str,
        func: Callable[..., Any],
        *args: Any,
        input_summary: str = "",
        correlation_id: str | None = None,
        **kwargs: Any,
    ) -> ExecutionResult:
        """Execute a capability function in sandbox."""
        cid = correlation_id or str(uuid.uuid4())
        started_at = datetime.now(UTC)

        # Emit start event
        if self.event_bus:
            await self.event_bus.publish(
                Event(
                    type="capability.execution.started",
                    payload={
                        "capability_name": capability_name,
                        "correlation_id": cid,
                        "input_summary": input_summary,
                    },
                    priority=EventPriority.NORMAL,
                ),
            )

        try:
            if self.mode == SandboxMode.SUBPROCESS:
                result = await self._execute_subprocess(
                    capability_name, func, args, kwargs, cid,
                )
            else:
                result = await self._execute_thread(
                    capability_name, func, args, kwargs, cid,
                )

            result.correlation_id = cid
            completed_at = datetime.now(UTC)

            # Audit log
            audit = AuditEntry(
                correlation_id=cid,
                capability_name=capability_name,
                input_summary=input_summary,
                result=result,
                started_at=started_at,
                completed_at=completed_at,
                resource_limit=self.resource_limit,
                mode=self.mode,
            )
            self._audit_buffer.append(audit)
            await self._flush_audit(audit)

            # Emit completion event
            if self.event_bus:
                await self.event_bus.publish(
                    Event(
                        type="capability.execution.completed",
                        payload={
                            "capability_name": capability_name,
                            "correlation_id": cid,
                            "success": result.success,
                            "duration_ms": result.duration_ms,
                        },
                        priority=EventPriority.NORMAL,
                    ),
                )

            return result

        except Exception as e:
            completed_at = datetime.now(UTC)
            result = ExecutionResult(
                success=False,
                error=str(e),
                exit_code=-1,
                correlation_id=cid,
                duration_ms=int((completed_at - started_at).total_seconds() * 1000),
            )

            audit = AuditEntry(
                correlation_id=cid,
                capability_name=capability_name,
                input_summary=input_summary,
                result=result,
                started_at=started_at,
                completed_at=completed_at,
                resource_limit=self.resource_limit,
                mode=self.mode,
            )
            self._audit_buffer.append(audit)
            await self._flush_audit(audit)

            if self.event_bus:
                await self.event_bus.publish(
                    Event(
                        type="capability.execution.failed",
                        payload={
                            "capability_name": capability_name,
                            "correlation_id": cid,
                            "error": str(e),
                        },
                        priority=EventPriority.HIGH,
                    ),
                )

            return result

    async def _execute_subprocess(
        self,
        capability_name: str,
        func: Callable[..., Any],
        args: tuple,
        kwargs: dict,
        correlation_id: str,
    ) -> ExecutionResult:
        """Execute in isolated subprocess."""
        # Serialize function call to JSON for subprocess
        import base64
        import pickle

        serialized = base64.b64encode(pickle.dumps((func, args, kwargs))).decode()

        # Create subprocess script: capture stdout / stderr so that
        # capability output does not corrupt the JSON result line.
        script = f"""
import sys, pickle, base64, json, time, resource, io
from pathlib import Path

# Set resource limits
resource.setrlimit(resource.RLIMIT_CPU, ({self.resource_limit.max_cpu_seconds}, {self.resource_limit.max_cpu_seconds}))
resource.setrlimit(resource.RLIMIT_AS, ({self.resource_limit.max_memory_mb * 1024 * 1024}, {self.resource_limit.max_memory_mb * 1024 * 1024}))

# Deserialize and execute
data = base64.b64decode('{serialized}')
func, args, kwargs = pickle.loads(data)

# Redirect stdout/stderr to capture capability output safely
old_stdout = sys.stdout
old_stderr = sys.stderr
sys.stdout = io.StringIO()
sys.stderr = io.StringIO()

start = time.time()
try:
    result = func(*args, **kwargs)
    output = str(result) if result is not None else ""
    exit_code = 0
    error = ""
except Exception as e:
    output = ""
    exit_code = 1
    error = str(e)

# Restore original streams
captured_stdout = sys.stdout.getvalue()
captured_stderr = sys.stderr.getvalue()
sys.stdout = old_stdout
sys.stderr = old_stderr

if output:
    output = captured_stdout + output
else:
    output = captured_stdout

if error and captured_stderr:
    error = error + "\\n" + captured_stderr
elif captured_stderr:
    error = captured_stderr

duration = int((time.time() - start) * 1000)

print(json.dumps({{
    "output": output,
    "error": error,
    "exit_code": exit_code,
    "duration_ms": duration
}}))
"""

        start_time = time.time()
        try:
            proc = await asyncio.create_subprocess_exec(
                sys.executable,
                "-c",
                script,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
                limit=self.resource_limit.max_output_bytes,
            )

            try:
                stdout, stderr = await asyncio.wait_for(
                    proc.communicate(),
                    timeout=self.resource_limit.max_cpu_seconds + 5,
                )
            except TimeoutError:
                proc.kill()
                await proc.wait()
                return ExecutionResult(
                    success=False,
                    error=f"Execution timeout ({self.resource_limit.max_cpu_seconds}s)",
                    exit_code=-1,
                    duration_ms=int((time.time() - start_time) * 1000),
                )

            duration_ms = int((time.time() - start_time) * 1000)

            if proc.returncode != 0 and not stdout:
                return ExecutionResult(
                    success=False,
                    error=stderr.decode()[: self.resource_limit.max_output_bytes],
                    exit_code=proc.returncode if proc.returncode is not None else 1,
                    duration_ms=duration_ms,
                )

            try:
                result_data = json.loads(stdout.decode())
                return ExecutionResult(
                    success=result_data.get("exit_code", 0) == 0,
                    output=result_data.get("output", "")[
                        : self.resource_limit.max_output_bytes
                    ],
                    error=result_data.get("error", "")[
                        : self.resource_limit.max_output_bytes
                    ],
                    exit_code=result_data.get("exit_code", 0),
                    duration_ms=result_data.get("duration_ms", duration_ms),
                )
            except json.JSONDecodeError:
                return ExecutionResult(
                    success=False,
                    error="Invalid subprocess output format",
                    exit_code=-1,
                    duration_ms=duration_ms,
                )

        except Exception as e:
            return ExecutionResult(
                success=False,
                error=f"Subprocess execution failed: {e}",
                exit_code=-1,
                duration_ms=int((time.time() - start_time) * 1000),
            )

    async def _execute_thread(
        self,
        capability_name: str,
        func: Callable[..., Any],
        args: tuple,
        kwargs: dict,
        correlation_id: str,
    ) -> ExecutionResult:
        """Execute in thread (lighter isolation)."""
        start_time = time.time()
        loop = asyncio.get_event_loop()
        max_output = self.resource_limit.max_output_bytes

        try:
            if asyncio.iscoroutinefunction(func):
                result = await asyncio.wait_for(
                    func(*args, **kwargs),
                    timeout=self.resource_limit.max_cpu_seconds,
                )
            else:
                result = await asyncio.wait_for(
                    loop.run_in_executor(None, lambda: func(*args, **kwargs)),
                    timeout=self.resource_limit.max_cpu_seconds,
                )

            duration_ms = int((time.time() - start_time) * 1000)
            output = str(result) if result is not None else ""
            return ExecutionResult(
                success=True,
                output=output[:max_output],
                exit_code=0,
                duration_ms=duration_ms,
            )

        except TimeoutError:
            return ExecutionResult(
                success=False,
                error=f"Execution timeout ({self.resource_limit.max_cpu_seconds}s)",
                exit_code=-1,
                duration_ms=int((time.time() - start_time) * 1000),
            )
        except Exception as e:
            error = str(e)
            return ExecutionResult(
                success=False,
                error=error[:max_output],
                exit_code=-1,
                duration_ms=int((time.time() - start_time) * 1000),
            )

    async def _flush_audit(self, entry: AuditEntry) -> None:
        """Write audit entry to log file."""
        if not self.audit_log_path:
            return
        try:
            await asyncio.to_thread(self._write_audit_entry, entry)
        except Exception as e:
            logger.warning(f"Failed to write audit log: {e}")

    def _write_audit_entry(self, entry: AuditEntry) -> None:
        if not self.audit_log_path:
            return
        self.audit_log_path.parent.mkdir(parents=True, exist_ok=True)
        with open(self.audit_log_path, "a") as f:
            f.write(json.dumps(entry.to_dict()) + "\n")

    def get_audit_log(self) -> list[AuditEntry]:
        """Get in-memory audit buffer."""
        return list(self._audit_buffer)

    def clear_audit_log(self) -> None:
        """Clear in-memory audit buffer."""
        self._audit_buffer.clear()


class CapabilitySandboxError(ArgusError):
    """Sandbox-specific errors."""

    code = "SANDBOX_ERROR"


__all__ = [
    "AuditEntry",
    "CapabilitySandboxError",
    "ExecutionResult",
    "ResourceLimit",
    "Sandbox",
    "SandboxMode",
]
