"""Workspace Context Manager — Argus.

Loads and parses project context files (AGENTS.md, CLAUDE.md, .cursorrules, etc.)
for injection into system prompts.
"""
from __future__ import annotations

from argus.workspace.context import ContextFile, WorkspaceContext, load_workspace_context

__all__ = ["ContextFile", "WorkspaceContext", "load_workspace_context"]
