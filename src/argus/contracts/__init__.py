"""Contracts — Argus.

Typed contracts for inter-module communication: requests, decisions,
capability requests, and failure objects. Modules talk through contracts,
never raw dicts.
"""
from __future__ import annotations

from argus.contracts.types import (
    CapabilityRequest,
    ContractValidationError,
    Decision,
    ExecutionResultContract,
    FailureObject,
    Request,
    validate_contract,
)

__all__ = [
    "CapabilityRequest",
    "ContractValidationError",
    "Decision",
    "ExecutionResultContract",
    "FailureObject",
    "Request",
    "validate_contract",
]
