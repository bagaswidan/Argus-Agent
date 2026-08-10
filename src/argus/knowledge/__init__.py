"""Knowledge Fabric — Argus (Refinement 4).

A store for *validated* knowledge — facts that survived verification,
with source and confidence attached. Unlike raw memory, entries here are
meant to be trusted: they carry evidence and a confidence score, and
nothing gets in without a source.

Design: JSON-backed, thread-safe, queryable by topic. Small by default —
this is a fabric, not a database.
"""
from __future__ import annotations

import json
import re
import threading
import uuid
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional


@dataclass
class KnowledgeEntry:
    """One validated fact."""

    fact_id: str = field(default_factory=lambda: uuid.uuid4().hex[:12])
    fact: str = ""
    topic: str = "general"
    source: str = ""
    confidence: float = 1.0  # 0..1
    verified: bool = True
    created_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    tags: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


class KnowledgeFabric:
    """Validated knowledge store with confidence and source tracking."""

    def __init__(self, path: Path | str):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._lock = threading.Lock()
        self._entries: dict[str, KnowledgeEntry] = {}
        self._load()

    def _load(self) -> None:
        if not self.path.exists():
            return
        try:
            data = json.loads(self.path.read_text())
            for item in data.get("entries", []):
                entry = KnowledgeEntry(**item)
                self._entries[entry.fact_id] = entry
        except Exception:
            self._entries = {}

    def _save(self) -> None:
        payload = {"entries": [e.to_dict() for e in self._entries.values()]}
        tmp = self.path.with_suffix(".tmp")
        tmp.write_text(json.dumps(payload, indent=2, default=str))
        tmp.replace(self.path)

    def add(
        self,
        fact: str,
        source: str,
        topic: str = "general",
        confidence: float = 1.0,
        verified: bool = True,
        tags: Optional[list[str]] = None,
    ) -> KnowledgeEntry:
        entry = KnowledgeEntry(
            fact=fact,
            topic=topic,
            source=source,
            confidence=max(0.0, min(1.0, confidence)),
            verified=verified,
            tags=tags or [],
        )
        with self._lock:
            self._entries[entry.fact_id] = entry
            self._save()
        return entry

    def get(self, fact_id: str) -> Optional[KnowledgeEntry]:
        with self._lock:
            return self._entries.get(fact_id)

    def search(self, query: str, min_confidence: float = 0.0) -> list[KnowledgeEntry]:
        """Case-insensitive substring search, ranked by confidence desc."""
        q = query.lower()
        with self._lock:
            results = [
                e for e in self._entries.values()
                if e.confidence >= min_confidence
                and (
                    q in e.fact.lower()
                    or q in e.topic.lower()
                    or any(q in t.lower() for t in e.tags)
                )
            ]
        return sorted(results, key=lambda e: e.confidence, reverse=True)

    def by_topic(self, topic: str) -> list[KnowledgeEntry]:
        with self._lock:
            return [e for e in self._entries.values() if e.topic == topic]

    def all(self) -> list[KnowledgeEntry]:
        with self._lock:
            return list(self._entries.values())

    def remove(self, fact_id: str) -> bool:
        with self._lock:
            if fact_id not in self._entries:
                return False
            del self._entries[fact_id]
            self._save()
            return True

    def count(self) -> int:
        with self._lock:
            return len(self._entries)

    def average_confidence(self) -> float:
        with self._lock:
            if not self._entries:
                return 0.0
            return sum(e.confidence for e in self._entries.values()) / len(self._entries)


def create_knowledge_fabric(path: Path | str) -> KnowledgeFabric:
    return KnowledgeFabric(path)
