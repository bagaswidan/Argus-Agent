"""Store — Argus Observability.

SQLite-backed persistent store for metrics, traces, and logs.
"""
from __future__ import annotations

import json
import sqlite3
import threading
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional

from argus.observability.metrics import Metric, MetricsCollector, MetricType
from argus.observability.traces import Span, Trace, TraceStatus, Tracer
from argus.observability.logs import LogEntry, LogCollector, LogLevel


class ObservabilityStore:
    """SQLite-backed observability store."""

    def __init__(self, db_path: Path | str):
        self.db_path = Path(db_path)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._lock = threading.Lock()
        self._conn = sqlite3.connect(str(self.db_path), check_same_thread=False)
        self._conn.row_factory = sqlite3.Row
        self._init_schema()

    def _init_schema(self) -> None:
        with self._lock:
            cur = self._conn.cursor()
            cur.execute(
                """
                CREATE TABLE IF NOT EXISTS metrics (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    name TEXT NOT NULL,
                    value REAL NOT NULL,
                    type TEXT NOT NULL,
                    labels TEXT NOT NULL DEFAULT '{}',
                    timestamp TEXT NOT NULL
                )
                """
            )
            cur.execute(
                """
                CREATE TABLE IF NOT EXISTS traces (
                    trace_id TEXT PRIMARY KEY,
                    name TEXT NOT NULL,
                    status TEXT NOT NULL,
                    duration_ms REAL NOT NULL,
                    span_count INTEGER NOT NULL,
                    start_time TEXT NOT NULL,
                    end_time TEXT,
                    spans TEXT NOT NULL DEFAULT '[]'
                )
                """
            )
            cur.execute(
                """
                CREATE TABLE IF NOT EXISTS logs (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    message TEXT NOT NULL,
                    level TEXT NOT NULL,
                    logger TEXT NOT NULL,
                    timestamp TEXT NOT NULL,
                    attributes TEXT NOT NULL DEFAULT '{}',
                    trace_id TEXT,
                    span_id TEXT
                )
                """
            )
            cur.execute("CREATE INDEX IF NOT EXISTS idx_metrics_name ON metrics(name)")
            cur.execute("CREATE INDEX IF NOT EXISTS idx_logs_level ON logs(level)")
            cur.execute("CREATE INDEX IF NOT EXISTS idx_logs_trace ON logs(trace_id)")
            cur.execute("CREATE INDEX IF NOT EXISTS idx_traces_start ON traces(start_time)")
            self._conn.commit()

    @staticmethod
    def _sanitize_limit(limit: Optional[int], default: int = 100) -> int:
        if limit is None or limit <= 0:
            return default
        return limit

    # --- Metrics ---

    def save_metric(self, metric: Metric) -> None:
        with self._lock:
            self._conn.execute(
                "INSERT INTO metrics (name, value, type, labels, timestamp) VALUES (?, ?, ?, ?, ?)",
                (
                    metric.name,
                    metric.value,
                    metric.metric_type.value,
                    json.dumps(metric.labels),
                    metric.timestamp.isoformat(),
                ),
            )
            self._conn.commit()

    def query_metrics(
        self,
        name: Optional[str] = None,
        metric_type: Optional[MetricType] = None,
        limit: int = 100,
    ) -> list[Metric]:
        limit = self._sanitize_limit(limit)
        with self._lock:
            query = "SELECT * FROM metrics WHERE 1=1"
            params: list[Any] = []
            if name:
                query += " AND name = ?"
                params.append(name)
            if metric_type:
                query += " AND type = ?"
                params.append(metric_type.value)
            query += " ORDER BY id DESC LIMIT ?"
            params.append(limit)
            rows = self._conn.execute(query, params).fetchall()
        return [
            Metric(
                name=r["name"],
                value=r["value"],
                metric_type=MetricType(r["type"]),
                labels=json.loads(r["labels"]),
                timestamp=datetime.fromisoformat(r["timestamp"]),
            )
            for r in rows
        ]

    # --- Traces ---

    def save_trace(self, trace: Trace) -> None:
        with self._lock:
            self._conn.execute(
                """
                INSERT OR REPLACE INTO traces
                (trace_id, name, status, duration_ms, span_count, start_time, end_time, spans)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    trace.trace_id,
                    trace.name,
                    trace.status.value,
                    trace.duration_ms,
                    len(trace.spans),
                    trace.start_time.isoformat(),
                    trace.end_time.isoformat() if trace.end_time else None,
                    json.dumps([s.to_dict() for s in trace.spans]),
                ),
            )
            self._conn.commit()

    def get_trace(self, trace_id: str) -> Optional[dict[str, Any]]:
        with self._lock:
            row = self._conn.execute("SELECT * FROM traces WHERE trace_id = ?", (trace_id,)).fetchone()
        if not row:
            return None
        return {
            "trace_id": row["trace_id"],
            "name": row["name"],
            "status": row["status"],
            "duration_ms": row["duration_ms"],
            "span_count": row["span_count"],
            "start_time": row["start_time"],
            "end_time": row["end_time"],
            "spans": json.loads(row["spans"]),
        }

    def list_traces(self, limit: int = 50) -> list[dict[str, Any]]:
        limit = self._sanitize_limit(limit, default=50)
        with self._lock:
            rows = self._conn.execute(
                "SELECT * FROM traces ORDER BY start_time DESC LIMIT ?", (limit,)
            ).fetchall()
        return [
            {
                "trace_id": r["trace_id"],
                "name": r["name"],
                "status": r["status"],
                "duration_ms": r["duration_ms"],
                "span_count": r["span_count"],
                "start_time": r["start_time"],
                "end_time": r["end_time"],
                "spans": json.loads(r["spans"]),
            }
            for r in rows
        ]

    # --- Logs ---

    def save_log(self, entry: LogEntry) -> None:
        with self._lock:
            self._conn.execute(
                """
                INSERT INTO logs (message, level, logger, timestamp, attributes, trace_id, span_id)
                VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    entry.message,
                    entry.level.value,
                    entry.logger,
                    entry.timestamp.isoformat(),
                    json.dumps(entry.attributes),
                    entry.trace_id,
                    entry.span_id,
                ),
            )
            self._conn.commit()

    def query_logs(
        self,
        level: Optional[LogLevel] = None,
        logger: Optional[str] = None,
        trace_id: Optional[str] = None,
        limit: int = 100,
    ) -> list[dict[str, Any]]:
        limit = self._sanitize_limit(limit)
        with self._lock:
            query = "SELECT * FROM logs WHERE 1=1"
            params: list[Any] = []
            if level:
                query += " AND level = ?"
                params.append(level.value)
            if logger:
                query += " AND logger = ?"
                params.append(logger)
            if trace_id:
                query += " AND trace_id = ?"
                params.append(trace_id)
            query += " ORDER BY id DESC LIMIT ?"
            params.append(limit)
            rows = self._conn.execute(query, params).fetchall()
        return [
            {
                "id": r["id"],
                "message": r["message"],
                "level": r["level"],
                "logger": r["logger"],
                "timestamp": r["timestamp"],
                "attributes": json.loads(r["attributes"]),
                "trace_id": r["trace_id"],
                "span_id": r["span_id"],
            }
            for r in rows
        ]

    def get_summary(self) -> dict[str, Any]:
        """Return summary counts for dashboard."""
        with self._lock:
            metric_count = self._conn.execute("SELECT COUNT(*) FROM metrics").fetchone()[0]
            trace_count = self._conn.execute("SELECT COUNT(*) FROM traces").fetchone()[0]
            log_count = self._conn.execute("SELECT COUNT(*) FROM logs").fetchone()[0]
            error_count = self._conn.execute(
                "SELECT COUNT(*) FROM logs WHERE level IN ('error', 'critical')"
            ).fetchone()[0]
            slow_traces = self._conn.execute(
                "SELECT COUNT(*) FROM traces WHERE duration_ms > 1000"
            ).fetchone()[0]
        return {
            "metric_count": metric_count,
            "trace_count": trace_count,
            "log_count": log_count,
            "error_count": error_count,
            "slow_traces": slow_traces,
        }

    def close(self) -> None:
        with self._lock:
            if self._conn is not None:
                self._conn.close()
                self._conn = None


def create_obs_store(db_path: Path | str) -> ObservabilityStore:
    return ObservabilityStore(db_path)
