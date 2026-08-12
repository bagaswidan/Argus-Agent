"""Error Model — Argus Core Foundation.

Typed exception hierarchy with error codes, retryability, and structured details.
All errors are JSON-serializable for observability.
"""
from __future__ import annotations

import json
from datetime import datetime
from enum import StrEnum
from typing import Any
from uuid import uuid4


class ErrorCode(StrEnum):
    """Standard error codes."""

    CONFIGURATION_ERROR = "CONFIGURATION_ERROR"
    VALIDATION_ERROR = "VALIDATION_ERROR"
    NOT_FOUND = "NOT_FOUND"
    CONFLICT = "CONFLICT"
    UNAUTHORIZED = "UNAUTHORIZED"
    FORBIDDEN = "FORBIDDEN"
    TIMEOUT = "TIMEOUT"
    INTERNAL_ERROR = "INTERNAL_ERROR"
    EXTERNAL_SERVICE_ERROR = "EXTERNAL_SERVICE_ERROR"


class ArgusError(Exception):
    """Base exception for all Argus errors."""

    code: str = "ARGUS_ERROR"
    retryable: bool = False

    def __init__(
        self,
        message: str,
        *,
        code: str | None = None,
        details: dict[str, Any] | None = None,
        cause: BaseException | None = None,
        correlation_id: str | None = None,
    ):
        super().__init__(message)
        self.message = message
        if code:
            self.code = code
        self.details = details or {}
        self.correlation_id = correlation_id or str(uuid4())
        if cause:
            self.__cause__ = cause

    def with_cause(self, cause: BaseException) -> ArgusError:
        """Attach a cause and return self for chaining."""
        self.__cause__ = cause
        return self

    def to_dict(self) -> dict[str, Any]:
        """Serialize to dictionary for logging/transport."""
        return {
            "code": self.code,
            "message": self.message,
            "details": self.details,
            "correlation_id": self.correlation_id,
            "retryable": self.retryable,
            "timestamp": datetime.utcnow().isoformat() + "Z",
        }

    def to_json(self) -> str:
        return json.dumps(self.to_dict(), default=str)

    def __str__(self) -> str:
        return f"[{self.code}] {self.message}"


# ----- Configuration -----

class ConfigurationError(ArgusError):
    """Configuration loading/validation error."""

    code = ErrorCode.CONFIGURATION_ERROR


# ----- Validation -----

class ValidationError(ArgusError):
    """Input/output validation error."""

    code = ErrorCode.VALIDATION_ERROR


# ----- Resource -----

class NotFoundError(ArgusError):
    """Resource not found."""

    code = ErrorCode.NOT_FOUND


class ConflictError(ArgusError):
    """Resource conflict (already exists, version mismatch)."""

    code = ErrorCode.CONFLICT


# ----- Authentication / Authorization -----

class UnauthorizedError(ArgusError):
    """Authentication required or invalid."""

    code = ErrorCode.UNAUTHORIZED


class ForbiddenError(ArgusError):
    """Authenticated but not authorized."""

    code = ErrorCode.FORBIDDEN


# ----- Timeouts -----

class TimeoutError(ArgusError):
    """Operation timed out."""

    code = ErrorCode.TIMEOUT
    retryable = True


# ----- Internal / External -----

class InternalError(ArgusError):
    """Unexpected internal error."""

    code = ErrorCode.INTERNAL_ERROR


class ExternalServiceError(ArgusError):
    """Downstream service error."""

    code = ErrorCode.EXTERNAL_SERVICE_ERROR
    retryable = True
