"""Memory Store — Argus.

SQLite + FTS5 based memory storage with full-text search and metadata filtering.
"""
from __future__ import annotations

import json
import sqlite3
import uuid
from contextlib import contextmanager
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from collections.abc import Iterator


@dataclass
class MemoryEntry:
    """A single memory entry."""

    id: str
    content: str
    metadata: dict[str, Any] = field(default_factory=dict)
    tags: list[str] = field(default_factory=list)
    created_at: datetime = field(default_factory=lambda: datetime.now(UTC))
    updated_at: datetime = field(default_factory=lambda: datetime.now(UTC))
    embedding: list[float] | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "content": self.content,
            "metadata": self.metadata,
            "tags": self.tags,
            "created_at": self.created_at.isoformat(),
            "updated_at": self.updated_at.isoformat(),
            "has_embedding": self.embedding is not None,
        }


@dataclass
class SearchResult:
    """Result of a memory search."""

    entry: MemoryEntry
    score: float
    match_type: str  # "fts", "vector", "hybrid"

    def to_dict(self) -> dict[str, Any]:
        return {
            "entry": self.entry.to_dict(),
            "score": self.score,
            "match_type": self.match_type,
        }


SCHEMA_SQL = """
PRAGMA journal_mode = WAL;
PRAGMA synchronous = NORMAL;
PRAGMA foreign_keys = ON;

CREATE TABLE IF NOT EXISTS memories (
    id TEXT PRIMARY KEY,
    content TEXT NOT NULL,
    metadata TEXT NOT NULL DEFAULT '{}',
    tags TEXT NOT NULL DEFAULT '[]',
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    embedding BLOB
);

CREATE VIRTUAL TABLE IF NOT EXISTS memories_fts USING fts5(
    content,
    metadata,
    tags,
    content=memories,
    content_rowid=rowid
);

CREATE TRIGGER IF NOT EXISTS memories_ai AFTER INSERT ON memories BEGIN
    INSERT INTO memories_fts(rowid, content, metadata, tags)
    VALUES (new.rowid, new.content, new.metadata, new.tags);
END;

CREATE TRIGGER IF NOT EXISTS memories_ad AFTER DELETE ON memories BEGIN
    INSERT INTO memories_fts(memories_fts, rowid, content, metadata, tags)
    VALUES ('delete', old.rowid, old.content, old.metadata, old.tags);
END;

CREATE TRIGGER IF NOT EXISTS memories_au AFTER UPDATE ON memories BEGIN
    INSERT INTO memories_fts(memories_fts, rowid, content, metadata, tags)
    VALUES ('delete', old.rowid, old.content, old.metadata, old.tags);
    INSERT INTO memories_fts(rowid, content, metadata, tags)
    VALUES (new.rowid, new.content, new.metadata, new.tags);
END;

CREATE INDEX IF NOT EXISTS idx_memories_created_at ON memories(created_at);
CREATE INDEX IF NOT EXISTS idx_memories_updated_at ON memories(updated_at);
"""


class MemoryStore:
    """SQLite + FTS5 memory store."""

    def __init__(self, db_path: Path | str):
        self.db_path = Path(db_path)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._conn: sqlite3.Connection | None = None
        self._init_db()

    def _init_db(self) -> None:
        """Initialize database schema."""
        with self._get_conn() as conn:
            conn.executescript(SCHEMA_SQL)

    @contextmanager
    def _get_conn(self) -> Iterator[sqlite3.Connection]:
        """Get database connection with row factory."""
        conn = sqlite3.connect(self.db_path, check_same_thread=False)
        conn.row_factory = sqlite3.Row
        try:
            yield conn
            conn.commit()
        except Exception:
            conn.rollback()
            raise
        finally:
            conn.close()

    def add(
        self,
        content: str,
        metadata: dict[str, Any] | None = None,
        tags: list[str] | None = None,
        embedding: list[float] | None = None,
        id: str | None = None,
    ) -> MemoryEntry:
        """Add a new memory entry."""
        now = datetime.now(UTC)
        entry_id = id or str(uuid.uuid4())

        entry = MemoryEntry(
            id=entry_id,
            content=content,
            metadata=metadata or {},
            tags=tags or [],
            created_at=now,
            updated_at=now,
            embedding=embedding,
        )

        with self._get_conn() as conn:
            conn.execute(
                """
                INSERT INTO memories (id, content, metadata, tags, created_at, updated_at, embedding)
                VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    entry.id,
                    entry.content,
                    json.dumps(entry.metadata),
                    json.dumps(entry.tags),
                    entry.created_at.isoformat(),
                    entry.updated_at.isoformat(),
                    json.dumps(entry.embedding) if entry.embedding else None,
                ),
            )

        return entry

    def get(self, id: str) -> MemoryEntry | None:
        """Get a memory entry by ID."""
        with self._get_conn() as conn:
            row = conn.execute(
                "SELECT * FROM memories WHERE id = ?", (id,),
            ).fetchone()
            if row:
                return self._row_to_entry(row)
        return None

    def update(
        self,
        id: str,
        content: str | None = None,
        metadata: dict[str, Any] | None = None,
        tags: list[str] | None = None,
        embedding: list[float] | None = None,
    ) -> MemoryEntry | None:
        """Update a memory entry."""
        entry = self.get(id)
        if not entry:
            return None

        if content is not None:
            entry.content = content
        if metadata is not None:
            entry.metadata = metadata
        if tags is not None:
            entry.tags = tags
        if embedding is not None:
            entry.embedding = embedding

        entry.updated_at = datetime.now(UTC)

        with self._get_conn() as conn:
            conn.execute(
                """
                UPDATE memories
                SET content = ?, metadata = ?, tags = ?, updated_at = ?, embedding = ?
                WHERE id = ?
                """,
                (
                    entry.content,
                    json.dumps(entry.metadata),
                    json.dumps(entry.tags),
                    entry.updated_at.isoformat(),
                    json.dumps(entry.embedding) if entry.embedding else None,
                    id,
                ),
            )

        return entry

    def delete(self, id: str) -> bool:
        """Delete a memory entry."""
        with self._get_conn() as conn:
            cursor = conn.execute("DELETE FROM memories WHERE id = ?", (id,))
            return bool(cursor.rowcount > 0)

    def search_fts(
        self,
        query: str,
        limit: int = 10,
        metadata_filter: dict[str, Any] | None = None,
        tag_filter: list[str] | None = None,
    ) -> list[SearchResult]:
        """Full-text search using FTS5."""
        # Build FTS5 query: tokenize into terms with prefix matching (term*)
        terms = [t for t in query.split() if t]
        fts_query = " AND ".join(f'"{t}"*' for t in terms) if terms else query

        needs_python_filter = bool(metadata_filter or tag_filter)

        with self._get_conn() as conn:
            if needs_python_filter:
                # Fetch all FTS matches so that Python-side filtering can
                # still honor the requested limit after filtering.
                rows = conn.execute(
                    """
                    SELECT m.*, bm25(memories_fts) as rank
                    FROM memories m
                    JOIN memories_fts ON m.rowid = memories_fts.rowid
                    WHERE memories_fts MATCH ?
                    ORDER BY rank
                    """,
                    (fts_query,),
                ).fetchall()
            else:
                rows = conn.execute(
                    """
                    SELECT m.*, bm25(memories_fts) as rank
                    FROM memories m
                    JOIN memories_fts ON m.rowid = memories_fts.rowid
                    WHERE memories_fts MATCH ?
                    ORDER BY rank
                    LIMIT ?
                    """,
                    (fts_query, limit),
                ).fetchall()

        results = []
        for row in rows:
            entry = self._row_to_entry(row)

            # Apply metadata filter
            if metadata_filter:
                match = all(
                    entry.metadata.get(k) == v for k, v in metadata_filter.items()
                )
                if not match:
                    continue

            # Apply tag filter
            if tag_filter and not all(tag in entry.tags for tag in tag_filter):
                continue

            # Convert bm25 rank to a positive score where more negative
            # rank (better match) gives a larger positive score.
            rank = row["rank"]
            score = max(0.0, -rank) if rank is not None else 0.0
            results.append(SearchResult(entry=entry, score=score, match_type="fts"))

        return results[:limit]

    def search_vector(
        self,
        query_embedding: list[float],
        limit: int = 10,
        metadata_filter: dict[str, Any] | None = None,
    ) -> list[SearchResult]:
        """Vector similarity search (cosine similarity)."""
        with self._get_conn() as conn:
            rows = conn.execute(
                "SELECT * FROM memories WHERE embedding IS NOT NULL",
            ).fetchall()

        if not rows:
            return []

        import math

        def cosine_sim(a: list[float], b: list[float]) -> float:
            if len(a) != len(b):
                return 0.0
            dot = sum(x * y for x, y in zip(a, b))
            norm_a = math.sqrt(sum(x * x for x in a))
            norm_b = math.sqrt(sum(y * y for y in b))
            if norm_a == 0 or norm_b == 0:
                return 0.0
            return dot / (norm_a * norm_b)

        results = []
        for row in rows:
            entry = self._row_to_entry(row)
            if not entry.embedding:
                continue

            # Apply metadata filter
            if metadata_filter and not all(
                entry.metadata.get(k) == v for k, v in metadata_filter.items()
            ):
                continue

            score = cosine_sim(query_embedding, entry.embedding)
            results.append(SearchResult(entry=entry, score=score, match_type="vector"))

        # Sort by score descending
        results.sort(key=lambda r: r.score, reverse=True)
        return results[:limit]

    def search_hybrid(
        self,
        query: str,
        query_embedding: list[float] | None = None,
        limit: int = 10,
        metadata_filter: dict[str, Any] | None = None,
        tag_filter: list[str] | None = None,
        fts_weight: float = 0.5,
        vector_weight: float = 0.5,
    ) -> list[SearchResult]:
        """Hybrid search combining FTS and vector."""
        fts_results = self.search_fts(query, limit * 2, metadata_filter, tag_filter)

        if query_embedding:
            vector_results = self.search_vector(query_embedding, limit * 2, metadata_filter)
        else:
            vector_results = []

        # Combine scores
        combined = {}
        for r in fts_results:
            combined[r.entry.id] = SearchResult(
                entry=r.entry, score=r.score * fts_weight, match_type="hybrid",
            )
        for r in vector_results:
            if r.entry.id in combined:
                combined[r.entry.id].score += r.score * vector_weight
            else:
                combined[r.entry.id] = SearchResult(
                    entry=r.entry, score=r.score * vector_weight, match_type="hybrid",
                )

        sorted_results = sorted(combined.values(), key=lambda r: r.score, reverse=True)
        return sorted_results[:limit]

    def list_all(self, limit: int = 100, offset: int = 0) -> list[MemoryEntry]:
        """List all memories with pagination."""
        with self._get_conn() as conn:
            rows = conn.execute(
                "SELECT * FROM memories ORDER BY created_at DESC LIMIT ? OFFSET ?",
                (limit, offset),
            ).fetchall()
        return [self._row_to_entry(row) for row in rows]

    def count(self) -> int:
        """Get total memory count."""
        with self._get_conn() as conn:
            row = conn.execute("SELECT COUNT(*) FROM memories").fetchone()
            return int(row[0]) if row is not None else 0

    def _row_to_entry(self, row: sqlite3.Row) -> MemoryEntry:
        return MemoryEntry(
            id=row["id"],
            content=row["content"],
            metadata=json.loads(row["metadata"] or "{}"),
            tags=json.loads(row["tags"] or "[]"),
            created_at=datetime.fromisoformat(row["created_at"]),
            updated_at=datetime.fromisoformat(row["updated_at"]),
            embedding=json.loads(row["embedding"]) if row["embedding"] else None,
        )

    def close(self) -> None:
        """Close any open connections (no-op with context manager)."""
        pass


def create_memory_store(db_path: Path | str) -> MemoryStore:
    """Factory function to create a memory store."""
    return MemoryStore(db_path)
