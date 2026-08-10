"""Reflection / Critic Loop — Argus Phase 2.

Self-correction mechanism where agents review and improve their own outputs
before finalizing.
"""
from __future__ import annotations

from argus.reflection.critic import Critic, CritiqueResult, CritiqueConfig
from argus.reflection.loop import ReflectionLoop, ReflectionConfig, ReflectionResult

__all__ = [
    "Critic",
    "CritiqueResult",
    "CritiqueConfig",
    "ReflectionLoop",
    "ReflectionConfig",
    "ReflectionResult",
]