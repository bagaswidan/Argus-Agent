"""Test Workspace Context Manager — Argus."""
from __future__ import annotations

import tempfile
from pathlib import Path

import pytest

from argus.workspace.context import (
    CONTEXT_FILES,
    ContextFile,
    get_workspace_context_for_prompt,
    load_workspace_context,
)


class TestContextFile:
    """Test ContextFile dataclass."""

    def test_truncated_content_short(self):
        cf = ContextFile(
            path=Path("/test/AGENTS.md"),
            name="AGENTS.md",
            content="short",
            size_bytes=5,
            priority=0,
        )
        assert cf.truncated_content() == "short"

    def test_truncated_content_long(self):
        long_content = "x" * 10000
        cf = ContextFile(
            path=Path("/test/AGENTS.md"),
            name="AGENTS.md",
            content=long_content,
            size_bytes=10000,
            priority=0,
        )
        truncated = cf.truncated_content(100)
        assert len(truncated) <= 100 + 50  # Allow for truncation indicator
        assert "[truncated" in truncated


class TestWorkspaceContext:
    """Test WorkspaceContext aggregation."""

    def test_empty_workspace(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            ctx = load_workspace_context(tmpdir)
            assert ctx.root == Path(tmpdir).resolve()
            assert ctx.files == []
            assert ctx.get_combined() == ""
            assert "No context files" in ctx.get_summary()

    def test_single_file(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            (root / "AGENTS.md").write_text("# Agents\n\nTest instructions")

            ctx = load_workspace_context(tmpdir)
            assert len(ctx.files) == 1
            assert ctx.files[0].name == "AGENTS.md"
            assert "Test instructions" in ctx.files[0].content

    def test_multiple_files_priority(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            (root / "AGENTS.md").write_text("# AGENTS")
            (root / "CLAUDE.md").write_text("# CLAUDE")
            (root / ".cursorrules").write_text("# CURSOR")

            ctx = load_workspace_context(tmpdir)
            assert len(ctx.files) == 3
            # AGENTS.md should be first (highest priority)
            assert ctx.files[0].name == "AGENTS.md"
            assert ctx.files[1].name == "CLAUDE.md"
            assert ctx.files[2].name == ".cursorrules"

    def test_get_combined_truncation(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            (root / "AGENTS.md").write_text("x" * 10000)
            (root / "CLAUDE.md").write_text("y" * 10000)

            ctx = load_workspace_context(tmpdir)
            combined = ctx.get_combined(max_total_chars=1000)
            assert len(combined) <= 1000
            assert "AGENTS.md" in combined

    def test_get_summary(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            (root / "AGENTS.md").write_text("# AGENTS")

            ctx = load_workspace_context(tmpdir)
            summary = ctx.get_summary()
            assert "1 context file" in summary
            assert "AGENTS.md" in summary


class TestConvenienceFunction:
    """Test get_workspace_context_for_prompt."""

    def test_returns_string(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            (root / "AGENTS.md").write_text("# AGENTS\n\nInstructions")

            result = get_workspace_context_for_prompt(tmpdir)
            assert isinstance(result, str)
            assert "AGENTS.md" in result
            assert "Instructions" in result

    def test_respects_max_chars(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            (root / "AGENTS.md").write_text("x" * 20000)

            result = get_workspace_context_for_prompt(tmpdir, max_chars=500)
            assert len(result) <= 500

    def test_empty_returns_empty(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            result = get_workspace_context_for_prompt(tmpdir)
            assert result == ""


class TestKnownContextFiles:
    """Test the known context file list."""

    def test_known_files_order(self):
        # AGENTS.md should be first (highest priority)
        assert CONTEXT_FILES[0] == "AGENTS.md"
        assert "CLAUDE.md" in CONTEXT_FILES
        assert ".cursorrules" in CONTEXT_FILES

    def test_load_workspace_context_invalid_root(self):
        with pytest.raises(ValueError):
            load_workspace_context("/nonexistent/path/that/does/not/exist")


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
