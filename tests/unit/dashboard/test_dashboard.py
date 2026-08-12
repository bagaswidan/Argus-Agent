"""Test Dashboard — Argus (Phase 6)."""
from __future__ import annotations

import urllib.request

import pytest

from argus.dashboard import (
    create_dashboard_store,
    render_dashboard,
    run_dashboard_in_thread,
)
from argus.observability.logs import LogCollector
from argus.observability.metrics import MetricsCollector
from argus.observability.traces import Tracer


@pytest.fixture
def store(tmp_path):
    s = create_dashboard_store(str(tmp_path / "obs.db"))
    yield s
    s.close()


def seed(store):
    collector = MetricsCollector()
    collector.increment("api.calls", labels={"route": "/v1"})
    for m in collector.snapshot():
        store.save_metric(m)

    tracer = Tracer()
    span = tracer.start_span("deploy.run")
    span.add_event("started", {"env": "staging"})
    tracer.end_span(span)
    trace = tracer.get_trace(span.trace_id)
    assert trace is not None
    trace.finish()
    store.save_trace(trace)

    logger = LogCollector()
    logger.info("capability executed", attributes={"cap": "math.add"})
    logger.error("deploy failed", attributes={"cap": "deploy"})
    for entry in logger.query():
        store.save_log(entry)


class TestRenderDashboard:
    def test_empty_dashboard_has_zeroes(self, store):
        html = render_dashboard(store)
        assert "Metrics" in html
        assert "No traces yet" in html
        assert "0" in html

    def test_seeded_dashboard_shows_data(self, store):
        seed(store)
        html = render_dashboard(store)
        assert "deploy.run" in html
        assert "capability executed" in html
        assert "deploy failed" in html

    def test_dashboard_has_theme_toggle(self, store):
        html = render_dashboard(store)
        assert "data-theme" in html
        assert "Bright" in html and "Dark" in html

    def test_traces_table_status_classes(self, store):
        seed(store)
        html = render_dashboard(store)
        assert "status ok" in html


class TestDashboardServer:
    def test_serves_http(self, store):
        seed(store)
        server, thread = run_dashboard_in_thread(store, port=0)
        port = server.server_address[1]
        try:
            with urllib.request.urlopen(f"http://127.0.0.1:{port}/", timeout=5) as resp:
                body = resp.read().decode()
                assert resp.status == 200
                assert "argus" in body.lower()
                assert "deploy.run" in body
        finally:
            server.shutdown()
            thread.join(timeout=3)

    def test_404_on_unknown_path(self, store):
        server, thread = run_dashboard_in_thread(store, port=0)
        port = server.server_address[1]
        try:
            with pytest.raises(Exception):
                urllib.request.urlopen(f"http://127.0.0.1:{port}/nope", timeout=5)
        finally:
            server.shutdown()
            thread.join(timeout=3)


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
