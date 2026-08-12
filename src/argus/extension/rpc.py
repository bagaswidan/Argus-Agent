"""Extension RPC Contract — Argus (Spec §38).

Required endpoints: Initialize(), Execute(), Health(), Configure(), Shutdown().
Response must have: Status, Evidence, Metrics, Error Object (optional).
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


class RpcError(Exception):
    """Raised when an RPC call fails."""

    def __init__(self, code: str, message: str, evidence: list[str] | None = None):
        super().__init__(message)
        self.code = code
        self.message = message
        self.evidence = evidence or []


@dataclass
class RpcResponse:
    """Standard RPC response (Spec §38)."""

    status: str  # ok | error
    evidence: list[str] = field(default_factory=list)
    metrics: dict[str, float] = field(default_factory=dict)
    error: dict[str, Any] | None = None
    data: Any = None

    @property
    def ok(self) -> bool:
        return self.status == "ok"

    def to_dict(self) -> dict[str, Any]:
        return {
            "status": self.status,
            "evidence": list(self.evidence),
            "metrics": dict(self.metrics),
            "error": self.error,
            "data": self.data,
        }


class ExtensionRpc:
    """Contract for extension communication (Spec §38).

    Extensions implement these methods; the manager calls them.
    """

    def initialize(self, config: dict[str, Any] | None = None) -> RpcResponse:
        raise NotImplementedError

    def execute(self, params: dict[str, Any]) -> RpcResponse:
        raise NotImplementedError

    def health(self) -> RpcResponse:
        raise NotImplementedError

    def configure(self, config: dict[str, Any]) -> RpcResponse:
        raise NotImplementedError

    def shutdown(self) -> RpcResponse:
        raise NotImplementedError


def create_rpc_response(
    status: str = "ok",
    evidence: list[str] | None = None,
    metrics: dict[str, float] | None = None,
    error: dict[str, Any] | None = None,
    data: Any = None,
) -> RpcResponse:
    return RpcResponse(
        status=status,
        evidence=evidence or [],
        metrics=metrics or {},
        error=error,
        data=data,
    )
