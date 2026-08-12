"""Test Memory Store — Argus."""
from __future__ import annotations

import tempfile
from pathlib import Path

import pytest

from argus.memory.store import MemoryEntry, SearchResult, create_memory_store


class TestMemoryStoreBasics:
    """Basic memory store operations."""

    def test_create_store(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            store = create_memory_store(Path(tmpdir) / "test.db")
            assert store.db_path.exists()

    def test_add_memory(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            store = create_memory_store(Path(tmpdir) / "test.db")
            entry = store.add("Test content", metadata={"key": "value"}, tags=["tag1"])
            assert entry.id is not None
            assert entry.content == "Test content"
            assert entry.metadata == {"key": "value"}
            assert entry.tags == ["tag1"]

    def test_get_memory(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            store = create_memory_store(Path(tmpdir) / "test.db")
            entry = store.add("Test content")
            retrieved = store.get(entry.id)
            assert retrieved is not None
            assert retrieved.content == "Test content"
            assert retrieved.id == entry.id

    def test_get_nonexistent(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            store = create_memory_store(Path(tmpdir) / "test.db")
            result = store.get("nonexistent-id")
            assert result is None

    def test_update_memory(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            store = create_memory_store(Path(tmpdir) / "test.db")
            entry = store.add("Original")
            updated = store.update(entry.id, content="Updated")
            assert updated is not None
            assert updated.content == "Updated"
            assert updated.updated_at > entry.updated_at

    def test_update_nonexistent(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            store = create_memory_store(Path(tmpdir) / "test.db")
            result = store.update("nonexistent", content="Updated")
            assert result is None

    def test_delete_memory(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            store = create_memory_store(Path(tmpdir) / "test.db")
            entry = store.add("To delete")
            deleted = store.delete(entry.id)
            assert deleted is True
            assert store.get(entry.id) is None

    def test_delete_nonexistent(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            store = create_memory_store(Path(tmpdir) / "test.db")
            deleted = store.delete("nonexistent")
            assert deleted is False


class TestMemoryStoreSearch:
    """FTS5 full-text search."""

    def test_search_fts_basic(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            store = create_memory_store(Path(tmpdir) / "test.db")
            store.add("The quick brown fox jumps over the lazy dog")
            store.add("A quick brown cat")
            store.add("The slow red turtle")

            results = store.search_fts("quick")
            assert len(results) == 2
            assert all("quick" in r.entry.content.lower() for r in results)

    def test_search_fts_ranking(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            store = create_memory_store(Path(tmpdir) / "test.db")
            store.add("quick quick quick quick quick")
            store.add("quick")
            store.add("not matching")

            results = store.search_fts("quick", limit=2)
            assert len(results) == 2
            # First result should have more occurrences
            assert "quick quick" in results[0].entry.content

    def test_search_fts_with_metadata_filter(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            store = create_memory_store(Path(tmpdir) / "test.db")
            store.add("Memory A", metadata={"type": "note"})
            store.add("Memory B", metadata={"type": "task"})
            store.add("Memory C", metadata={"type": "note"})

            results = store.search_fts("Memory", metadata_filter={"type": "note"})
            assert len(results) == 2
            assert all(r.entry.metadata.get("type") == "note" for r in results)

    def test_search_fts_with_tag_filter(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            store = create_memory_store(Path(tmpdir) / "test.db")
            store.add("Memory A", tags=["work", "important"])
            store.add("Memory B", tags=["personal"])
            store.add("Memory C", tags=["work"])

            results = store.search_fts("Memory", tag_filter=["work"])
            assert len(results) == 2
            assert all("work" in r.entry.tags for r in results)

    def test_search_fts_limit(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            store = create_memory_store(Path(tmpdir) / "test.db")
            for i in range(10):
                store.add(f"Memory {i} quick")

            results = store.search_fts("quick", limit=3)
            assert len(results) == 3


class TestMemoryStoreVectorSearch:
    """Vector similarity search."""

    def test_search_vector_basic(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            store = create_memory_store(Path(tmpdir) / "test.db")
            store.add("Memory A", embedding=[1.0, 0.0, 0.0])
            store.add("Memory B", embedding=[0.0, 1.0, 0.0])
            store.add("Memory C", embedding=[0.0, 0.0, 1.0])

            results = store.search_vector([1.0, 0.0, 0.0], limit=2)
            assert len(results) == 2
            assert results[0].entry.content == "Memory A"
            assert results[0].score > 0.99  # Near perfect match

    def test_search_vector_no_embeddings(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            store = create_memory_store(Path(tmpdir) / "test.db")
            store.add("No embedding")

            results = store.search_vector([1.0, 0.0])
            assert results == []

    def test_search_vector_with_metadata_filter(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            store = create_memory_store(Path(tmpdir) / "test.db")
            store.add("A", embedding=[1.0, 0.0], metadata={"type": "note"})
            store.add("B", embedding=[0.0, 1.0], metadata={"type": "task"})

            # Search for [1.0, 0.0] should match A (note), not B (task) even though B matches metadata
            results = store.search_vector([1.0, 0.0], metadata_filter={"type": "note"})
            assert len(results) == 1
            assert results[0].entry.content == "A"
            assert results[0].score > 0.99

            # Filter by task type - B matches metadata but has 0 similarity
            results = store.search_vector([1.0, 0.0], metadata_filter={"type": "task"})
            assert len(results) == 1
            assert results[0].entry.content == "B"
            assert results[0].score == 0.0


class TestMemoryStoreHybridSearch:
    """Hybrid FTS + Vector search."""

    def test_hybrid_search(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            store = create_memory_store(Path(tmpdir) / "test.db")
            store.add("quick fox", embedding=[1.0, 0.0])
            store.add("quick cat", embedding=[0.0, 1.0])
            store.add("slow dog", embedding=[0.0, 0.0])

            results = store.search_hybrid(
                "quick", query_embedding=[1.0, 0.0], limit=2,
            )
            assert len(results) >= 1
            # Both FTS and vector should match "quick fox"

    def test_hybrid_search_only_fts(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            store = create_memory_store(Path(tmpdir) / "test.db")
            store.add("quick fox")
            store.add("slow cat")

            results = store.search_hybrid("quick", limit=2)
            assert len(results) == 1
            assert results[0].entry.content == "quick fox"


class TestMemoryStoreListAndCount:
    """List and count operations."""

    def test_list_all(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            store = create_memory_store(Path(tmpdir) / "test.db")
            store.add("A")
            store.add("B")
            store.add("C")

            all_memories = store.list_all(limit=10)
            assert len(all_memories) == 3

    def test_list_all_pagination(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            store = create_memory_store(Path(tmpdir) / "test.db")
            for i in range(5):
                store.add(f"Memory {i}")

            page1 = store.list_all(limit=2, offset=0)
            page2 = store.list_all(limit=2, offset=2)
            assert len(page1) == 2
            assert len(page2) == 2
            assert page1[0].id != page2[0].id

    def test_count(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            store = create_memory_store(Path(tmpdir) / "test.db")
            assert store.count() == 0
            store.add("A")
            assert store.count() == 1
            store.add("B")
            assert store.count() == 2


class TestMemoryEntry:
    """MemoryEntry dataclass."""

    def test_to_dict(self):
        entry = MemoryEntry(
            id="test-id",
            content="Test",
            metadata={"k": "v"},
            tags=["tag1"],
        )
        d = entry.to_dict()
        assert d["id"] == "test-id"
        assert d["content"] == "Test"
        assert d["metadata"] == {"k": "v"}
        assert d["tags"] == ["tag1"]
        assert "created_at" in d
        assert "has_embedding" in d


class TestSearchResult:
    """SearchResult dataclass."""

    def test_to_dict(self):
        entry = MemoryEntry(id="test", content="Test")
        result = SearchResult(entry=entry, score=0.9, match_type="fts")
        d = result.to_dict()
        assert d["score"] == 0.9
        assert d["match_type"] == "fts"
        assert d["entry"]["id"] == "test"


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
