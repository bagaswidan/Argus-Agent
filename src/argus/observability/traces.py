"""Traces — Argus Observability.

Distributed tracing with spans and trace tree.
"""
from __future__ import annotations

import threading
import time
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Optional


class TraceStatus(str, Enum):
    OK = "ok"
    ERROR = "error"
    TIMEOUT = "timeout"
    CANCELLED = "cancelled"


@dataclass
class Span:
    """A single span in a trace."""

    name: str
    trace_id: str
    span_id: str
    parent_id: Optional[str] = None
    status: TraceStatus = TraceStatus.OK
    start_time: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    end_time: Optional[datetime] = None
    attributes: dict[str, Any] = field(default_factory=dict)
    events: list[dict[str, Any]] = field(default_factory=list)

    @property
    def duration_ms(self) -> float:
        end = self.end_time or datetime.now(timezone.utc)
        return (end - self.start_time).total_seconds() * 1000

    def add_event(self, name: str, attributes: Optional[dict[str, Any]] = None) -> None:
        self.events.append(
            {
                "name": name,
                "attributes": attributes or {},
                "timestamp": datetime.now(timezone.utc).isoformat(),
            }
        )

    def end(self, status: TraceStatus = TraceStatus.OK) -> None:
        self.end_time = datetime.now(timezone.utc)
        self.status = status

    def to_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "trace_id": self.trace_id,
            "span_id": self.span_id,
            "parent_id": self.parent_id,
            "status": self.status.value,
            "start_time": self.start_time.isoformat(),
            "end_time": self.end_time.isoformat() if self.end_time else None,
            "duration_ms": round(self.duration_ms, 3),
            "attributes": self.attributes,
            "events": self.events,
        }


@dataclass
class Trace:
    """A full trace containing spans."""

    trace_id: str
    name: str
    spans: list[Span] = field(default_factory=list)
    start_time: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    end_time: Optional[datetime] = None

    @property
    def duration_ms(self) -> float:
        end = self.end_time or datetime.now(timezone.utc)
        return (end - self.start_time).total_seconds() * 1000

    @property
    def root_span(self) -> Optional[Span]:
        for span in self.spans:
            if span.parent_id is None:
                return span
        return None

    @property
    def status(self) -> TraceStatus:
        if not self.spans:
            return TraceStatus.OK
        if any(s.status == TraceStatus.ERROR for s in self.spans):
            return TraceStatus.ERROR
        if any(s.status == TraceStatus.TIMEOUT for s in self.spans):
            return TraceStatus.TIMEOUT
        if any(s.status == TraceStatus.CANCELLED for s in self.spans):
            return TraceStatus.CANCELLED
        return TraceStatus.OK

    def finish(self) -> None:
        self.end_time = datetime.now(timezone.utc)

    def to_dict(self) -> dict[str, Any]:
        return {
            "trace_id": self.trace_id,
            "name": self.name,
            "duration_ms": round(self.duration_ms, 3),
            "status": self.status.value,
            "span_count": len(self.spans),
            "spans": [s.to_dict() for s in self.spans],
            "start_time": self.start_time.isoformat(),
            "end_time": self.end_time.isoformat() if self.end_time else None,
        }


class Tracer:
    """Creates and manages traces and spans."""

    def __init__(self):
        self._lock = threading.Lock()
        self._traces: dict[str, Trace] = {}
        self._active: dict[str, Span] = {}  # span_id -> span
        self._max_traces = 1_000

    def start_trace(self, name: str) -> Trace:
        trace = Trace(trace_id=uuid.uuid4().hex[:16], name=name)
        with self._lock:
            self._traces[trace.trace_id] = trace
            if len(self._traces) > self._max_traces:
                # Drop oldest (insertion order preserved in py3.7+)
                oldest = next(iter(self._traces))
                del self._traces[oldest]
        return trace

    def start_span(
        self,
        name: str,
        trace: Optional[Trace] = None,
        parent: Optional[Span] = None,
        trace_id: Optional[str] = None,
    ) -> Span:
        tid = trace.trace_id if trace else trace_id or uuid.uuid4().hex[:16]

        with self._lock:
            if trace is None:
                trace = self._traces.get(tid)
                if trace is None:
                    trace = Trace(trace_id=tid, name=name)
                    self._traces[tid] = trace
            else:
                # Ensure a manually provided trace is indexed too
                if trace.trace_id not in self._traces:
                    self._traces[trace.trace_id] = trace

            span = Span(
                name=name,
                trace_id=tid,
                span_id=uuid.uuid4().hex[:16],
                parent_id=parent.span_id if parent else None,
            )
            trace.spans.append(span)
            self._active[span.span_id] = span
        return span

    def end_span(self, span: Span, status: TraceStatus = TraceStatus.OK) -> None:
        span.end(status)
        with self._lock:
            self._active.pop(span.span_id, None)

    def get_trace(self, trace_id: str) -> Optional[Trace]:
        with self._lock:
            return self._traces.get(trace_id)

    def list_traces(self, limit: int = 50) -> list[Trace]:
        with self._lock:
            traces = list(self._traces.values())
        # Sort by start time descending
        traces.sort(key=lambda t: t.start_time, reverse=True)
        return traces[:limit]

    def get_active_spans(self) -> list[Span]:
        with self._lock:
            return list(self._active.values())


def create_tracer() -> Tracer:
    return Tracer()
