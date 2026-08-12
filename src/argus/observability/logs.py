"""Logs — Argus Observability.

Structured log collection with levels and filtering.
"""
from __future__ import annotations

import threading
from dataclasses import dataclass, field
from datetime import UTC, datetime
from enum import Enum
from typing import Any


class LogLevel(str, Enum):
    DEBUG = "debug"
    INFO = "info"
    WARNING = "warning"
    ERROR = "error"
    CRITICAL = "critical"

    @property
    def rank(self) -> int:
        return {"debug": 0, "info": 1, "warning": 2, "error": 3, "critical": 4}[self.value]


@dataclass
class LogEntry:
    """A single log entry."""

    message: str
    level: LogLevel = LogLevel.INFO
    logger: str = "argus"
    timestamp: datetime = field(default_factory=lambda: datetime.now(UTC))
    attributes: dict[str, Any] = field(default_factory=dict)
    trace_id: str | None = None
    span_id: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "message": self.message,
            "level": self.level.value,
            "logger": self.logger,
            "timestamp": self.timestamp.isoformat(),
            "attributes": self.attributes,
            "trace_id": self.trace_id,
            "span_id": self.span_id,
        }


class LogCollector:
    """Collects structured logs in memory."""

    def __init__(self, max_entries: int = 10_000):
        self._lock = threading.Lock()
        self._entries: list[LogEntry] = []
        self._max_entries = max_entries

    def log(
        self,
        message: str,
        level: LogLevel = LogLevel.INFO,
        logger: str = "argus",
        attributes: dict[str, Any] | None = None,
        trace_id: str | None = None,
        span_id: str | None = None,
    ) -> LogEntry:
        entry = LogEntry(
            message=message,
            level=level,
            logger=logger,
            attributes=attributes or {},
            trace_id=trace_id,
            span_id=span_id,
        )
        with self._lock:
            self._entries.append(entry)
            if len(self._entries) > self._max_entries:
                self._entries = self._entries[-self._max_entries:]
        return entry

    def debug(self, message: str, **kwargs: Any) -> LogEntry:
        return self.log(message, LogLevel.DEBUG, **kwargs)

    def info(self, message: str, **kwargs: Any) -> LogEntry:
        return self.log(message, LogLevel.INFO, **kwargs)

    def warning(self, message: str, **kwargs: Any) -> LogEntry:
        return self.log(message, LogLevel.WARNING, **kwargs)

    def error(self, message: str, **kwargs: Any) -> LogEntry:
        return self.log(message, LogLevel.ERROR, **kwargs)

    def critical(self, message: str, **kwargs: Any) -> LogEntry:
        return self.log(message, LogLevel.CRITICAL, **kwargs)

    def query(
        self,
        level: LogLevel | None = None,
        min_level: LogLevel | None = None,
        logger: str | None = None,
        message_contains: str | None = None,
        trace_id: str | None = None,
        limit: int = 100,
    ) -> list[LogEntry]:
        """Query logs with filters."""
        with self._lock:
            entries = list(self._entries)

        if level is not None:
            entries = [e for e in entries if e.level == level]
        if min_level is not None:
            entries = [e for e in entries if e.level.rank >= min_level.rank]
        if logger is not None:
            entries = [e for e in entries if e.logger == logger]
        if message_contains is not None:
            entries = [e for e in entries if message_contains.lower() in e.message.lower()]
        if trace_id is not None:
            entries = [e for e in entries if e.trace_id == trace_id]

        # Newest first
        entries.reverse()
        return entries[:limit]

    def count_by_level(self) -> dict[str, int]:
        with self._lock:
            counts: dict[str, int] = {}
            for e in self._entries:
                counts[e.level.value] = counts.get(e.level.value, 0) + 1
            return counts

    def clear(self) -> None:
        with self._lock:
            self._entries.clear()


def create_log_collector(max_entries: int = 10_000) -> LogCollector:
    return LogCollector(max_entries=max_entries)
