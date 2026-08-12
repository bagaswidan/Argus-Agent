"""Reflection / Critic Loop — Argus Phase 2.

Self-correction mechanism where agents review and improve their own outputs
before finalizing.
"""
from __future__ import annotations

from argus.reflection.critic import Critic, CritiqueConfig, CritiqueResult
from argus.reflection.loop import ReflectionConfig, ReflectionLoop, ReflectionResult

__all__ = [
    "Critic",
    "CritiqueConfig",
    "CritiqueResult",
    "ReflectionConfig",
    "ReflectionLoop",
    "ReflectionResult",
]
