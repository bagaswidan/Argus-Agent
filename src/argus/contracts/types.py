"""Contract types — Argus.

Typed contracts for inter-module communication per Engineering Spec §18, §29.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any


class ContractValidationError(ValueError):
    """Raised when a contract fails validation."""


def _now() -> datetime:
    return datetime.now(UTC)


@dataclass
class Request:
    """Input contract: user request object (Spec §18)."""

    message: str
    user_id: str = ""
    session_id: str = ""
    context: dict[str, Any] = field(default_factory=dict)
    memory_hints: list[str] = field(default_factory=list)
    timestamp: datetime = field(default_factory=_now)
    request_id: str = ""

    def validate(self) -> None:
        if not self.message or not self.message.strip():
            raise ContractValidationError("Request.message is required")
        if self.request_id and not self.request_id.strip():
            raise ContractValidationError("Request.request_id cannot be empty")


@dataclass
class Decision:
    """Output contract: a recorded decision (Spec §14, §18)."""

    choice: str
    reason: str = ""
    confidence: float = 0.0
    factors: dict[str, float] = field(default_factory=dict)  # confidence, cost, risk, ...
    alternatives: list[str] = field(default_factory=list)
    goal_id: str = ""
    evidence: list[str] = field(default_factory=list)
    timestamp: datetime = field(default_factory=_now)
    decision_id: str = ""

    def validate(self) -> None:
        if not self.choice:
            raise ContractValidationError("Decision.choice is required")
        if not (0.0 <= self.confidence <= 1.0):
            raise ContractValidationError("Decision.confidence must be in [0,1]")


@dataclass
class CapabilityRequest:
    """Capability execution request (Spec §18, §29)."""

    capability_id: str
    params: dict[str, Any] = field(default_factory=dict)
    correlation_id: str = ""
    policy_hints: dict[str, Any] = field(default_factory=dict)
    context: dict[str, Any] = field(default_factory=dict)
    timestamp: datetime = field(default_factory=_now)

    def validate(self) -> None:
        if not self.capability_id or not self.capability_id.strip():
            raise ContractValidationError("CapabilityRequest.capability_id is required")


@dataclass
class ExecutionResultContract:
    """Execution result output contract (Spec §29)."""

    success: bool
    output: Any = None
    error: FailureObject | None = None
    metrics: dict[str, float] = field(default_factory=dict)
    evidence: list[str] = field(default_factory=list)
    duration_ms: int = 0
    timestamp: datetime = field(default_factory=_now)


@dataclass
class FailureObject:
    """Failure object (Spec §29): code, reason, evidence, recovery suggestion."""

    code: str
    reason: str
    evidence: list[str] = field(default_factory=list)
    recovery_suggestion: str = ""
    retryable: bool = False

    def to_dict(self) -> dict[str, Any]:
        return {
            "code": self.code,
            "reason": self.reason,
            "evidence": list(self.evidence),
            "recovery_suggestion": self.recovery_suggestion,
            "retryable": self.retryable,
        }


def validate_contract(obj: Any) -> None:
    """Validate any contract object; raise ContractValidationError on failure."""
    if hasattr(obj, "validate"):
        obj.validate()
        return
    raise ContractValidationError(f"Not a contract object: {type(obj).__name__}")
