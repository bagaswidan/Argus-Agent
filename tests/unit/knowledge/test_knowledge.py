"""Test Knowledge Fabric — Argus (Refinement 4)."""
from __future__ import annotations

import pytest

from argus.knowledge import create_knowledge_fabric


@pytest.fixture
def fabric(tmp_path):
    return create_knowledge_fabric(str(tmp_path / "knowledge.json"))


class TestKnowledgeFabric:
    def test_add_and_get(self, fabric):
        entry = fabric.add("OmniRoute runs on port 20128", source="ops-notes", topic="infra")
        assert fabric.get(entry.fact_id).fact == "OmniRoute runs on port 20128"

    def test_confidence_clamped(self, fabric):
        entry = fabric.add("x", source="s", confidence=5.0)
        assert entry.confidence == 1.0
        entry2 = fabric.add("y", source="s", confidence=-1.0)
        assert entry2.confidence == 0.0

    def test_search_by_fact(self, fabric):
        fabric.add("Argus has 16 engines", source="spec", topic="project", confidence=0.9)
        fabric.add("Unrelated note", source="notes", topic="general", confidence=0.5)
        results = fabric.search("engines")
        assert len(results) == 1
        assert results[0].fact == "Argus has 16 engines"

    def test_search_ranks_by_confidence(self, fabric):
        fabric.add("alpha beta", source="s1", topic="t", confidence=0.4)
        fabric.add("alpha beta", source="s2", topic="t", confidence=0.9)
        fabric.add("alpha beta", source="s3", topic="t", confidence=0.7)
        results = fabric.search("alpha")
        assert [r.confidence for r in results] == [0.9, 0.7, 0.4]

    def test_min_confidence_filter(self, fabric):
        fabric.add("low confidence fact", source="s", topic="t", confidence=0.3)
        fabric.add("high confidence fact", source="s", topic="t", confidence=0.9)
        assert len(fabric.search("fact", min_confidence=0.5)) == 1

    def test_search_by_tag(self, fabric):
        fabric.add("fact with tag", source="s", topic="t", tags=["deployment"])
        assert len(fabric.search("deployment")) == 1

    def test_by_topic(self, fabric):
        fabric.add("a", source="s", topic="infra")
        fabric.add("b", source="s", topic="infra")
        fabric.add("c", source="s", topic="other")
        assert len(fabric.by_topic("infra")) == 2

    def test_persistence(self, tmp_path):
        path = tmp_path / "knowledge.json"
        f1 = create_knowledge_fabric(path)
        f1.add("persisted fact", source="s", topic="t")
        f2 = create_knowledge_fabric(path)
        assert f2.count() == 1
        assert f2.all()[0].fact == "persisted fact"

    def test_corrupt_file_starts_fresh(self, tmp_path):
        path = tmp_path / "knowledge.json"
        path.write_text("{broken")
        fabric = create_knowledge_fabric(path)
        assert fabric.count() == 0

    def test_remove(self, fabric):
        entry = fabric.add("temp fact", source="s", topic="t")
        assert fabric.remove(entry.fact_id) is True
        assert fabric.remove("nope") is False
        assert fabric.count() == 0

    def test_average_confidence(self, fabric):
        fabric.add("a", source="s", topic="t", confidence=1.0)
        fabric.add("b", source="s", topic="t", confidence=0.5)
        assert fabric.average_confidence() == 0.75

    def test_unverified_entry_allowed(self, fabric):
        entry = fabric.add("pending fact", source="s", topic="t", verified=False)
        assert entry.verified is False


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
