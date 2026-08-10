"""Test Runtime Monitor — Argus (Refinement 2)."""
from __future__ import annotations

import pytest

from argus.runtime.monitor import RuntimeMonitor, create_runtime_monitor


class TestRuntimeMonitor:
    def test_start_returns_id_and_tracks_active(self):
        mon = create_runtime_monitor()
        tid = mon.start("deploy")
        assert tid
        assert mon.get(tid) is not None
        assert mon.get(tid).status == "running"
        assert len(mon.active_tasks()) == 1

    def test_finish_moves_to_history(self):
        mon = create_runtime_monitor()
        tid = mon.start("deploy")
        assert mon.finish(tid, "completed") is True
        assert mon.get(tid) is None
        assert len(mon.history()) == 1
        assert mon.history()[0].status == "completed"

    def test_finish_unknown_returns_false(self):
        mon = create_runtime_monitor()
        assert mon.finish("nope") is False

    def test_failed_task_records_error(self):
        mon = create_runtime_monitor()
        tid = mon.start("deploy")
        mon.finish(tid, "failed", error="boom")
        task = mon.history()[0]
        assert task.status == "failed"
        assert task.error == "boom"

    def test_summary_counts(self):
        mon = create_runtime_monitor()
        for i in range(3):
            tid = mon.start(f"task-{i}")
            mon.finish(tid, "completed")
        tid = mon.start("bad")
        mon.finish(tid, "failed")
        summary = mon.summary()
        assert summary["completed"] == 3
        assert summary["failed"] == 1
        assert summary["total_tasks"] == 4
        assert summary["active"] == 0

    def test_summary_counts_active(self):
        mon = create_runtime_monitor()
        mon.start("running-task")
        summary = mon.summary()
        assert summary["active"] == 1

    def test_history_capped(self):
        mon = create_runtime_monitor(max_history=5)
        for i in range(10):
            tid = mon.start(f"t{i}")
            mon.finish(tid, "completed")
        assert len(mon.history()) == 5

    def test_on_update_hook_fires(self):
        mon = create_runtime_monitor()
        events = []
        mon.on_update(lambda task: events.append(task.status))
        tid = mon.start("x")
        mon.finish(tid, "completed")
        assert "running" in events
        assert "completed" in events

    def test_duration_recorded(self):
        mon = create_runtime_monitor()
        tid = mon.start("slow")
        mon.finish(tid, "completed")
        assert mon.history()[0].duration_ms >= 0

    def test_avg_runtime(self):
        mon = create_runtime_monitor()
        tid = mon.start("a")
        mon.finish(tid, "completed")
        summary = mon.summary()
        assert summary["avg_runtime_ms"] >= 0


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
