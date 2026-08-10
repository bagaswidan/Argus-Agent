"""Contracts — Argus.

Typed contracts for inter-module communication: requests, decisions,
capability requests, and failure objects. Modules talk through contracts,
never raw dicts.
"""
from __future__ import annotations

from argus.contracts.types import (
    Request,
    Decision,
    CapabilityRequest,
    ExecutionResultContract,
    FailureObject,
    ContractValidationError,
    validate_contract,
)

__all__ = [
    "Request",
    "Decision",
    "CapabilityRequest",
    "ExecutionResultContract",
    "FailureObject",
    "ContractValidationError",
    "validate_contract",
]