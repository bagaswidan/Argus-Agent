"""Curator — Argus (Phase 11: Self Evolution).

The curator turns execution history into change. It tracks how often
capabilities and skills are actually used, then periodically reviews that
usage: rarely-used items get archived (never deleted — archives are
restorable), frequently-used items get promoted, and recurring failures
produce a "lesson" record that feeds back into future runs.

This is the "Learn From Every Execution" constitution principle made concrete.
"""
from __future__ import annotations

import json
import threading
import time
import uuid
from dataclasses import asdict, dataclass, field
from datetime import UTC, datetime, timezone
from pathlib import Path
from typing import Any, Optional


@dataclass
class UsageRecord:
    """Usage stats for one capability/skill."""

    name: str
    kind: str  # capability | skill
    use_count: int = 0
    success_count: int = 0
    last_used_at: str | None = None
    last_status: str | None = None
    archived: bool = False
    archived_at: str | None = None


@dataclass
class Lesson:
    """A lesson learned from repeated failures."""

    lesson_id: str = field(default_factory=lambda: uuid.uuid4().hex[:10])
    source: str = ""
    failure_count: int = 0
    summary: str = ""
    created_at: str = field(default_factory=lambda: datetime.now(UTC).isoformat())


class UsageTracker:
    """Persists usage records to a JSON sidecar (thread-safe)."""

    def __init__(self, path: Path | str):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._lock = threading.Lock()
        self._records: dict[str, UsageRecord] = {}
        self._lessons: list[Lesson] = []
        self._load()

    def _load(self) -> None:
        if not self.path.exists():
            return
        try:
            data = json.loads(self.path.read_text())
            for item in data.get("records", []):
                rec = UsageRecord(**item)
                self._records[rec.name] = rec
            self._lessons = [Lesson(**l) for l in data.get("lessons", [])]
        except Exception:
            # Corrupt sidecar: start fresh rather than crash the agent.
            self._records = {}
            self._lessons = []

    def _save(self) -> None:
        payload = {
            "records": [asdict(r) for r in self._records.values()],
            "lessons": [asdict(l) for l in self._lessons],
        }
        tmp = self.path.with_suffix(".tmp")
        tmp.write_text(json.dumps(payload, indent=2, default=str))
        tmp.replace(self.path)

    def record_use(
        self,
        name: str,
        kind: str = "capability",
        success: bool = True,
        status: str = "ok",
    ) -> None:
        with self._lock:
            rec = self._records.get(name)
            if rec is None:
                rec = UsageRecord(name=name, kind=kind)
                self._records[name] = rec
            rec.use_count += 1
            if success:
                rec.success_count += 1
            rec.last_used_at = datetime.now(UTC).isoformat()
            rec.last_status = status
            self._save()

    def get(self, name: str) -> UsageRecord | None:
        with self._lock:
            rec = self._records.get(name)
            return rec

    def all(self) -> list[UsageRecord]:
        with self._lock:
            return list(self._records.values())

    def archive(self, name: str) -> bool:
        with self._lock:
            rec = self._records.get(name)
            if rec is None:
                return False
            rec.archived = True
            rec.archived_at = datetime.now(UTC).isoformat()
            self._save()
            return True

    def restore(self, name: str) -> bool:
        with self._lock:
            rec = self._records.get(name)
            if rec is None:
                return False
            rec.archived = False
            rec.archived_at = None
            self._save()
            return True

    def add_lesson(self, source: str, summary: str, failure_count: int) -> Lesson:
        with self._lock:
            lesson = Lesson(source=source, summary=summary, failure_count=failure_count)
            self._lessons.append(lesson)
            self._save()
            return lesson

    def lessons(self) -> list[Lesson]:
        with self._lock:
            return list(self._lessons)


class Curator:
    """Reviews usage and decides what to archive/promote.

    Policy (matching the spec's curator behavior):
    - never deletes, max action is archive (restorable)
    - pinned names are exempt from archiving
    - low usage + old last use -> archive candidate
    - failure rate above threshold -> lesson candidate
    """

    def __init__(
        self,
        tracker: UsageTracker,
        stale_after_days: float = 30.0,
        min_uses: int = 3,
        failure_rate_threshold: float = 0.5,
        pinned: list[str] | None = None,
    ):
        self.tracker = tracker
        self.stale_after_days = stale_after_days
        self.min_uses = min_uses
        self.failure_rate_threshold = failure_rate_threshold
        self.pinned = set(pinned or [])

    def _days_since(self, iso: str | None) -> float:
        if not iso:
            return float("inf")
        try:
            ts = datetime.fromisoformat(iso)
            return (datetime.now(UTC) - ts).total_seconds() / 86400.0
        except ValueError:
            return float("inf")

    def review(self, now: float | None = None) -> dict[str, Any]:
        """Run one review pass. Returns a report dict."""
        archived: list[str] = []
        lessons: list[dict[str, Any]] = []

        for rec in self.tracker.all():
            if rec.archived or rec.name in self.pinned:
                continue
            idle_days = self._days_since(rec.last_used_at)
            if rec.use_count < self.min_uses and idle_days > self.stale_after_days:
                self.tracker.archive(rec.name)
                archived.append(rec.name)
            elif rec.use_count >= self.min_uses:
                failure_rate = 1.0 - (rec.success_count / rec.use_count)
                if failure_rate > self.failure_rate_threshold:
                    lesson = self.tracker.add_lesson(
                        source=rec.name,
                        summary=(
                            f"{rec.name} fails {failure_rate:.0%} of the time "
                            f"({rec.use_count - rec.success_count}/{rec.use_count})"
                        ),
                        failure_count=rec.use_count - rec.success_count,
                    )
                    lessons.append(asdict(lesson))

        return {"archived": archived, "lessons": lessons}


def create_usage_tracker(path: Path | str) -> UsageTracker:
    return UsageTracker(path)


def create_curator(
    tracker: UsageTracker,
    stale_after_days: float = 30.0,
    min_uses: int = 3,
    failure_rate_threshold: float = 0.5,
    pinned: list[str] | None = None,
) -> Curator:
    return Curator(
        tracker,
        stale_after_days=stale_after_days,
        min_uses=min_uses,
        failure_rate_threshold=failure_rate_threshold,
        pinned=pinned,
    )
