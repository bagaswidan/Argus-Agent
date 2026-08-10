"""Metrics — Argus Observability.

Counter, gauge, and histogram metric collection.
"""
from __future__ import annotations

import threading
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Optional


class MetricType(str, Enum):
    COUNTER = "counter"
    GAUGE = "gauge"
    HISTOGRAM = "histogram"


@dataclass
class Metric:
    """A single metric sample."""

    name: str
    value: float
    metric_type: MetricType = MetricType.COUNTER
    labels: dict[str, str] = field(default_factory=dict)
    timestamp: datetime = field(default_factory=lambda: datetime.now(timezone.utc))

    def to_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "value": self.value,
            "type": self.metric_type.value,
            "labels": self.labels,
            "timestamp": self.timestamp.isoformat(),
        }


class MetricsCollector:
    """Collects counters, gauges, and histograms."""

    def __init__(
        self,
        max_samples: int = 10_000,
        max_histogram_values: int = 1_000,
    ):
        if max_samples <= 0:
            raise ValueError("max_samples must be positive")
        if max_histogram_values <= 0:
            raise ValueError("max_histogram_values must be positive")

        self._lock = threading.Lock()
        self._counters: dict[tuple[str, frozenset], float] = {}
        self._gauges: dict[tuple[str, frozenset], float] = {}
        self._histograms: dict[tuple[str, frozenset], list[float]] = {}
        self._samples: list[Metric] = []
        self._max_samples = max_samples
        self._max_histogram_values = max_histogram_values

    def _labels_key(self, labels: dict[str, str]) -> frozenset:
        return frozenset(labels.items())

    def increment(
        self,
        name: str,
        value: float = 1.0,
        labels: Optional[dict[str, str]] = None,
    ) -> None:
        """Increment a counter."""
        labels = labels or {}
        key = (name, self._labels_key(labels))
        with self._lock:
            self._counters[key] = self._counters.get(key, 0.0) + value
            self._record(Metric(name, self._counters[key], MetricType.COUNTER, labels))

    def set_gauge(
        self,
        name: str,
        value: float,
        labels: Optional[dict[str, str]] = None,
    ) -> None:
        """Set a gauge value."""
        labels = labels or {}
        key = (name, self._labels_key(labels))
        with self._lock:
            self._gauges[key] = value
            self._record(Metric(name, value, MetricType.GAUGE, labels))

    def observe(
        self,
        name: str,
        value: float,
        labels: Optional[dict[str, str]] = None,
    ) -> None:
        """Record a histogram observation."""
        labels = labels or {}
        key = (name, self._labels_key(labels))
        with self._lock:
            values = self._histograms.setdefault(key, [])
            values.append(value)
            if len(values) > self._max_histogram_values:
                del values[:-self._max_histogram_values]
            self._record(Metric(name, value, MetricType.HISTOGRAM, labels))

    def _record(self, metric: Metric) -> None:
        """Record sample, trimming if needed."""
        self._samples.append(metric)
        if len(self._samples) > self._max_samples:
            self._samples = self._samples[-self._max_samples:]

    def get_counter(self, name: str, labels: Optional[dict[str, str]] = None) -> float:
        labels = labels or {}
        key = (name, self._labels_key(labels))
        with self._lock:
            return self._counters.get(key, 0.0)

    def get_gauge(self, name: str, labels: Optional[dict[str, str]] = None) -> Optional[float]:
        labels = labels or {}
        key = (name, self._labels_key(labels))
        with self._lock:
            return self._gauges.get(key)

    def get_histogram_stats(
        self,
        name: str,
        labels: Optional[dict[str, str]] = None,
    ) -> dict[str, float]:
        """Get histogram stats: count, sum, min, max, mean, p50, p95, p99."""
        labels = labels or {}
        key = (name, self._labels_key(labels))
        with self._lock:
            values = self._histograms.get(key, [])
        if not values:
            return {"count": 0, "sum": 0.0, "min": 0.0, "max": 0.0, "mean": 0.0, "p50": 0.0, "p95": 0.0, "p99": 0.0}
        sorted_vals = sorted(values)
        n = len(sorted_vals)
        total = sum(sorted_vals)

        import math

        def percentile(p: float) -> float:
            # Nearest-rank method: rank = ceil(p * n), idx = rank - 1
            rank = math.ceil(p * n)
            idx = max(0, min(rank - 1, n - 1))
            return sorted_vals[idx]

        return {
            "count": n,
            "sum": total,
            "min": sorted_vals[0],
            "max": sorted_vals[-1],
            "mean": total / n,
            "p50": percentile(0.50),
            "p95": percentile(0.95),
            "p99": percentile(0.99),
        }

    def snapshot(self, limit: int = 100) -> list[Metric]:
        """Return recent samples."""
        with self._lock:
            if limit is None or limit <= 0:
                limit = self._max_samples
            return list(self._samples[-limit:])

    def reset(self) -> None:
        with self._lock:
            self._counters.clear()
            self._gauges.clear()
            self._histograms.clear()
            self._samples.clear()


def create_metrics_collector() -> MetricsCollector:
    return MetricsCollector()
