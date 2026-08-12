"""Logging — Argus Core Foundation.

Structured logging with structlog, JSON and console formats,
correlation IDs, and service name context.
"""
from __future__ import annotations

import logging
import sys
from enum import Enum
from typing import Any

import structlog


class LogLevel(str, Enum):
    DEBUG = "DEBUG"
    INFO = "INFO"
    WARNING = "WARNING"
    ERROR = "ERROR"
    CRITICAL = "CRITICAL"


class LogFormat(str, Enum):
    JSON = "json"
    CONSOLE = "console"


# Module-level state
_configured = False


def configure_logging(
    *,
    level: LogLevel = LogLevel.INFO,
    format: LogFormat = LogFormat.JSON,
    service_name: str = "argus",
) -> None:
    """Configure global logging for Argus.

    Call once at application startup.
    """
    global _configured

    # Configure stdlib logging
    logging.basicConfig(
        format="%(message)s",
        stream=sys.stdout,
        level=getattr(logging, level.value),
    )

    # Configure structlog
    shared_processors: list[structlog.typing.Processor] = [
        structlog.contextvars.merge_contextvars,
        structlog.processors.add_log_level,
        structlog.processors.StackInfoRenderer(),
        structlog.dev.set_exc_info,
        structlog.processors.TimeStamper(fmt="iso", utc=True),
        structlog.processors.format_exc_info,
    ]

    if format == LogFormat.JSON:
        renderer: structlog.typing.Processor = structlog.processors.JSONRenderer()
    else:
        renderer = structlog.dev.ConsoleRenderer(colors=True)

    structlog.configure(
        processors=shared_processors + [renderer],
        wrapper_class=structlog.make_filtering_bound_logger(getattr(logging, level.value)),
        context_class=dict,
        logger_factory=structlog.PrintLoggerFactory(file=sys.stdout),
        cache_logger_on_first_use=True,
    )

    # Bind service name globally
    structlog.contextvars.bind_contextvars(service=service_name)

    _configured = True


class _NamedLogger:
    """Wrapper around structlog BoundLogger that exposes .name attribute."""

    __slots__ = ("_logger", "_name")

    def __init__(self, name: str, logger: structlog.BoundLogger):
        self._name = name
        self._logger = logger

    @property
    def name(self) -> str:
        return self._name

    def __getattr__(self, attr: str) -> Any:
        return getattr(self._logger, attr)

    def bind(self, **kwargs: Any) -> _NamedLogger:
        return _NamedLogger(self._name, self._logger.bind(**kwargs))

    def new(self, **kwargs: Any) -> _NamedLogger:
        return _NamedLogger(self._name, self._logger.new(**kwargs))


def get_logger(name: str | None = None) -> _NamedLogger:
    """Get a structured logger instance with .name attribute.

    If name is None, returns a root logger wrapper.
    """
    if not _configured:
        # Auto-configure with defaults if not explicitly configured
        configure_logging()

    if name:
        return _NamedLogger(name, structlog.get_logger(name))
    return _NamedLogger("root", structlog.get_logger())


# Convenience: pre-bound root logger
logger = get_logger()


def bind_context(**kwargs: Any) -> None:
    """Bind context variables to all subsequent log calls in this context."""
    structlog.contextvars.bind_contextvars(**kwargs)


def clear_context() -> None:
    """Clear all context variables."""
    structlog.contextvars.clear_contextvars()


def unbind_context(*keys: str) -> None:
    """Remove specific context variables."""
    structlog.contextvars.unbind_contextvars(*keys)
