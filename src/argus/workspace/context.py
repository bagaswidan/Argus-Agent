"""Workspace Context Manager — Argus.

Loads and parses project context files (AGENTS.md, CLAUDE.md, .cursorrules, etc.)
for injection into system prompts.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

# Known context file names in priority order (first found wins for each type)
CONTEXT_FILES = [
    "AGENTS.md",
    "CLAUDE.md",
    ".cursorrules",
    "AGENTS.txt",
    "CLAUDE.txt",
    "instructions.md",
    "CONTRIBUTING.md",
    "DEVELOPMENT.md",
]


@dataclass
class ContextFile:
    """A single context file with its parsed content."""

    path: Path
    name: str
    content: str
    size_bytes: int
    priority: int  # Lower = higher priority

    def truncated_content(self, max_chars: int = 8000) -> str:
        """Return content truncated to max_chars with indicator."""
        if len(self.content) <= max_chars:
            return self.content
        return self.content[:max_chars] + f"\n\n... [truncated, {len(self.content)} total chars]"


@dataclass
class WorkspaceContext:
    """Aggregated workspace context from all discovered files."""

    root: Path
    files: list[ContextFile] = field(default_factory=list)
    raw_combined: str = ""

    def get_combined(self, max_total_chars: int = 16000) -> str:
        """Get combined context, truncated to budget."""
        if not self.files:
            return ""

        parts = []
        remaining = max_total_chars

        for ctx_file in self.files:
            if remaining <= 0:
                break
            header = f"\n--- {ctx_file.name} ({ctx_file.path}) ---\n"
            if len(header) >= remaining:
                break
            remaining -= len(header)
            content = ctx_file.truncated_content(remaining)
            if len(content) > remaining:
                content = content[:remaining]
            parts.append(header + content)
            remaining -= len(content)

        self.raw_combined = "".join(parts)
        return self.raw_combined

    def get_summary(self) -> str:
        """Get a brief summary of loaded context files."""
        if not self.files:
            return "No context files found"
        names = [f.name for f in self.files]
        return f"Loaded {len(self.files)} context file(s): {', '.join(names)}"


def _discover_context_files(root: Path) -> list[Path]:
    """Discover context files in the workspace root."""
    found = []
    for name in CONTEXT_FILES:
        path = root / name
        if path.is_file():
            found.append(path)
    return found


def _parse_file(path: Path, priority: int) -> ContextFile | None:
    """Parse a single context file."""
    try:
        content = path.read_text(encoding="utf-8")
        return ContextFile(
            path=path,
            name=path.name,
            content=content,
            size_bytes=len(content.encode("utf-8")),
            priority=priority,
        )
    except Exception:
        return None


def load_workspace_context(root: Path | str) -> WorkspaceContext:
    """Load all workspace context files from the given root directory."""
    root_path = Path(root).resolve()
    if not root_path.is_dir():
        raise ValueError(f"Not a directory: {root_path}")

    discovered = _discover_context_files(root_path)

    files = []
    for i, path in enumerate(discovered):
        ctx = _parse_file(path, i)
        if ctx:
            files.append(ctx)

    # Sort by priority (lower index = higher priority)
    files.sort(key=lambda f: f.priority)

    return WorkspaceContext(root=root_path, files=files)


def get_workspace_context_for_prompt(
    root: Path | str,
    max_chars: int = 16000,
) -> str:
    """Convenience function: load context and return combined string for prompt injection."""
    ctx = load_workspace_context(root)
    return ctx.get_combined(max_chars)
