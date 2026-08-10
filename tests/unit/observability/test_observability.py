"""Test Observability — Argus Phase 2."""
from __future__ import annotations

import pytest
import tempfile
from pathlib import Path

from argus.observability.metrics import MetricsCollector, Metric, MetricType, create_metrics_collector
from argus.observability.traces import Tracer, Span, Trace, TraceStatus, create_tracer
from argus.observability.logs import LogCollector, LogEntry, LogLevel, create_log_collector
from argus.observability.store import ObservabilityStore, create_obs_store


class TestMetricsCollector:
    """Test metrics collection."""

    def test_counter(self):
        mc = create_metrics_collector()
        mc.increment("requests")
        mc.increment("requests")
        mc.increment("requests", 3)
        assert mc.get_counter("requests") == 5.0

    def test_counter_with_labels(self):
        mc = create_metrics_collector()
        mc.increment("requests", labels={"path": "/api"})
        mc.increment("requests", labels={"path": "/api"})
        mc.increment("requests", labels={"path": "/health"})
        assert mc.get_counter("requests", labels={"path": "/api"}) == 2.0
        assert mc.get_counter("requests", labels={"path": "/health"}) == 1.0
        assert mc.get_counter("requests") == 0.0

    def test_gauge(self):
        mc = create_metrics_collector()
        mc.set_gauge("memory_used", 128.5)
        assert mc.get_gauge("memory_used") == 128.5
        mc.set_gauge("memory_used", 256.0)
        assert mc.get_gauge("memory_used") == 256.0

    def test_histogram_stats(self):
        mc = create_metrics_collector()
        for i in range(1, 101):
            mc.observe("latency", float(i))
        stats = mc.get_histogram_stats("latency")
        assert stats["count"] == 100
        assert stats["min"] == 1.0
        assert stats["max"] == 100.0
        assert stats["mean"] == 50.5
        assert stats["p50"] == 50.0
        assert stats["p95"] == 95.0
        assert stats["p99"] == 99.0

    def test_histogram_empty(self):
        mc = create_metrics_collector()
        stats = mc.get_histogram_stats("nonexistent")
        assert stats["count"] == 0

    def test_snapshot(self):
        mc = create_metrics_collector()
        mc.increment("a")
        mc.set_gauge("b", 1.0)
        mc.observe("c", 2.0)
        snap = mc.snapshot()
        assert len(snap) == 3

    def test_reset(self):
        mc = create_metrics_collector()
        mc.increment("a")
        mc.reset()
        assert mc.get_counter("a") == 0.0

    def test_metric_to_dict(self):
        m = Metric(name="test", value=1.5)
        d = m.to_dict()
        assert d["name"] == "test"
        assert d["value"] == 1.5
        assert d["type"] == "counter"


class TestTracer:
    """Test tracing."""

    def test_start_trace(self):
        tracer = create_tracer()
        trace = tracer.start_trace("request")
        assert trace.trace_id
        assert trace.name == "request"

    def test_start_end_span(self):
        tracer = create_tracer()
        trace = tracer.start_trace("request")
        span = tracer.start_span("db_query", trace=trace)
        assert span.parent_id is None
        assert len(trace.spans) == 1
        tracer.end_span(span, TraceStatus.OK)
        assert span.end_time is not None
        assert span.status == TraceStatus.OK

    def test_nested_spans(self):
        tracer = create_tracer()
        trace = tracer.start_trace("request")
        parent = tracer.start_span("handler", trace=trace)
        child = tracer.start_span("db_query", trace=trace, parent=parent)
        assert child.parent_id == parent.span_id
        assert len(trace.spans) == 2
        assert trace.root_span is parent

    def test_trace_status_error(self):
        tracer = create_tracer()
        trace = tracer.start_trace("request")
        span = tracer.start_span("db_query", trace=trace)
        tracer.end_span(span, TraceStatus.ERROR)
        assert trace.status == TraceStatus.ERROR

    def test_trace_to_dict(self):
        tracer = create_tracer()
        trace = tracer.start_trace("request")
        span = tracer.start_span("db_query", trace=trace)
        span.add_event("query_started")
        tracer.end_span(span)
        trace.finish()
        d = trace.to_dict()
        assert d["trace_id"] == trace.trace_id
        assert d["span_count"] == 1
        assert d["status"] == "ok"
        assert len(d["spans"]) == 1

    def test_list_traces(self):
        tracer = create_tracer()
        tracer.start_trace("t1")
        tracer.start_trace("t2")
        traces = tracer.list_traces()
        assert len(traces) == 2

    def test_span_duration(self):
        span = Span(name="test", trace_id="t", span_id="s")
        assert span.duration_ms >= 0


class TestLogCollector:
    """Test log collection."""

    def test_log_levels(self):
        lc = create_log_collector()
        lc.debug("debug msg")
        lc.info("info msg")
        lc.warning("warn msg")
        lc.error("error msg")
        lc.critical("critical msg")
        assert lc.count_by_level()["debug"] == 1
        assert lc.count_by_level()["info"] == 1
        assert lc.count_by_level()["error"] == 1
        assert lc.count_by_level()["critical"] == 1

    def test_query_by_level(self):
        lc = create_log_collector()
        lc.info("one")
        lc.error("two")
        errors = lc.query(level=LogLevel.ERROR)
        assert len(errors) == 1
        assert errors[0].message == "two"

    def test_query_min_level(self):
        lc = create_log_collector()
        lc.debug("d")
        lc.info("i")
        lc.error("e")
        results = lc.query(min_level=LogLevel.ERROR)
        assert len(results) == 1
        assert results[0].message == "e"

    def test_query_message_contains(self):
        lc = create_log_collector()
        lc.info("connection established")
        lc.info("connection closed")
        lc.info("other event")
        results = lc.query(message_contains="connection")
        assert len(results) == 2

    def test_query_trace_id(self):
        lc = create_log_collector()
        lc.info("a", trace_id="trace-1")
        lc.info("b", trace_id="trace-2")
        results = lc.query(trace_id="trace-1")
        assert len(results) == 1
        assert results[0].message == "a"

    def test_max_entries(self):
        lc = LogCollector(max_entries=5)
        for i in range(10):
            lc.info(f"msg-{i}")
        entries = lc.query(limit=100)
        assert len(entries) == 5
        assert entries[0].message == "msg-9"

    def test_log_entry_to_dict(self):
        entry = LogEntry(message="test", level=LogLevel.WARNING)
        d = entry.to_dict()
        assert d["message"] == "test"
        assert d["level"] == "warning"

    def test_level_rank(self):
        assert LogLevel.DEBUG.rank < LogLevel.INFO.rank < LogLevel.WARNING.rank < LogLevel.ERROR.rank < LogLevel.CRITICAL.rank


class TestObservabilityStore:
    """Test persistent store."""

    def test_save_query_metrics(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            store = create_obs_store(Path(tmpdir) / "obs.db")
            mc = create_metrics_collector()
            mc.increment("requests", 5)
            for m in mc.snapshot():
                store.save_metric(m)
            metrics = store.query_metrics(name="requests")
            assert len(metrics) == 1
            assert metrics[0].value == 5.0
            store.close()

    def test_save_get_trace(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            store = create_obs_store(Path(tmpdir) / "obs.db")
            tracer = create_tracer()
            trace = tracer.start_trace("request")
            span = tracer.start_span("db_query", trace=trace)
            tracer.end_span(span)
            trace.finish()
            store.save_trace(trace)

            loaded = store.get_trace(trace.trace_id)
            assert loaded is not None
            assert loaded["name"] == "request"
            assert loaded["span_count"] == 1
            store.close()

    def test_list_traces(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            store = create_obs_store(Path(tmpdir) / "obs.db")
            tracer = create_tracer()
            for i in range(3):
                t = tracer.start_trace(f"trace-{i}")
                t.finish()
                store.save_trace(t)
            traces = store.list_traces()
            assert len(traces) == 3
            store.close()

    def test_save_query_logs(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            store = create_obs_store(Path(tmpdir) / "obs.db")
            lc = create_log_collector()
            lc.info("started", logger="argus.core")
            lc.error("failed", logger="argus.core", trace_id="trace-1")
            for e in lc.query(limit=100):
                store.save_log(e)

            logs = store.query_logs(level=LogLevel.ERROR)
            assert len(logs) == 1
            assert logs[0]["message"] == "failed"

            trace_logs = store.query_logs(trace_id="trace-1")
            assert len(trace_logs) == 1
            store.close()

    def test_summary(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            store = create_obs_store(Path(tmpdir) / "obs.db")
            mc = create_metrics_collector()
            mc.increment("a")
            for m in mc.snapshot():
                store.save_metric(m)

            lc = create_log_collector()
            lc.error("boom")
            for e in lc.query(limit=100):
                store.save_log(e)

            summary = store.get_summary()
            assert summary["metric_count"] == 1
            assert summary["log_count"] == 1
            assert summary["error_count"] == 1
            store.close()


if __name__ == "__main__":
    pytest.main([__file__, "-v"])