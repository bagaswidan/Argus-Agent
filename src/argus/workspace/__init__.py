"""Workspace Context Manager — Argus.

Loads and parses project context files (AGENTS.md, CLAUDE.md, .cursorrules, etc.)
for injection into system prompts.
"""
from __future__ import annotations

from argus.workspace.context import WorkspaceContext, ContextFile, load_workspace_context

__all__ = ["WorkspaceContext", "ContextFile", "load_workspace_context"]