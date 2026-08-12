"""Test Curator — Argus (Phase 11: Self Evolution)."""
from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest

from argus.curator import create_curator, create_usage_tracker


@pytest.fixture
def tracker(tmp_path):
    return create_usage_tracker(str(tmp_path / "usage.json"))


class TestUsageTracker:
    def test_record_and_get(self, tracker):
        tracker.record_use("math.add", success=True)
        rec = tracker.get("math.add")
        assert rec is not None
        assert rec.use_count == 1
        assert rec.success_count == 1

    def test_record_failure(self, tracker):
        tracker.record_use("deploy", success=False, status="error")
        rec = tracker.get("deploy")
        assert rec.use_count == 1
        assert rec.success_count == 0
        assert rec.last_status == "error"

    def test_persistence_across_instances(self, tmp_path):
        path = tmp_path / "usage.json"
        t1 = create_usage_tracker(path)
        t1.record_use("math.add", success=True)
        t2 = create_usage_tracker(path)
        rec = t2.get("math.add")
        assert rec is not None
        assert rec.use_count == 1

    def test_corrupt_file_starts_fresh(self, tmp_path):
        path = tmp_path / "usage.json"
        path.write_text("{not json!!")
        tracker = create_usage_tracker(path)
        assert tracker.all() == []

    def test_archive_and_restore(self, tracker):
        tracker.record_use("math.add")
        assert tracker.archive("math.add") is True
        assert tracker.get("math.add").archived is True
        assert tracker.restore("math.add") is True
        assert tracker.get("math.add").archived is False

    def test_lessons(self, tracker):
        lesson = tracker.add_lesson("deploy", "fails often", 3)
        assert lesson.lesson_id
        assert tracker.lessons()[0].source == "deploy"


class TestCurator:
    def _seed_old_record(self, tracker, name, uses, days_ago):
        tracker.record_use(name, success=True)
        rec = tracker.get(name)
        old = datetime.now(UTC) - timedelta(days=days_ago)
        rec.last_used_at = old.isoformat()
        rec.use_count = uses
        rec.success_count = uses
        with tracker._lock:
            tracker._save()

    def test_archives_stale_low_usage(self, tracker):
        self._seed_old_record(tracker, "old.cap", uses=1, days_ago=40)
        curator = create_curator(tracker, stale_after_days=30, min_uses=3)
        report = curator.review()
        assert "old.cap" in report["archived"]
        assert tracker.get("old.cap").archived is True

    def test_keeps_frequently_used(self, tracker):
        for _ in range(5):
            tracker.record_use("hot.cap", success=True)
        curator = create_curator(tracker, stale_after_days=1, min_uses=3)
        report = curator.review()
        assert "hot.cap" not in report["archived"]

    def test_pinned_never_archived(self, tracker):
        self._seed_old_record(tracker, "pinned.cap", uses=1, days_ago=60)
        curator = create_curator(tracker, stale_after_days=30, min_uses=3, pinned=["pinned.cap"])
        report = curator.review()
        assert "pinned.cap" not in report["archived"]

    def test_high_failure_creates_lesson(self, tracker):
        for _ in range(2):
            tracker.record_use("flaky.cap", success=True)
        for _ in range(3):
            tracker.record_use("flaky.cap", success=False, status="error")
        curator = create_curator(tracker, failure_rate_threshold=0.4)
        report = curator.review()
        assert len(report["lessons"]) == 1
        assert "flaky.cap" in report["lessons"][0]["source"]

    def test_review_is_idempotent_for_archived(self, tracker):
        self._seed_old_record(tracker, "old.cap", uses=1, days_ago=40)
        curator = create_curator(tracker, stale_after_days=30, min_uses=3)
        curator.review()
        report2 = curator.review()
        assert "old.cap" not in report2["archived"]  # already archived, skipped

    def test_never_deletes(self, tracker):
        self._seed_old_record(tracker, "old.cap", uses=1, days_ago=40)
        curator = create_curator(tracker, stale_after_days=30, min_uses=3)
        curator.review()
        assert tracker.get("old.cap") is not None  # still present, just archived


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
