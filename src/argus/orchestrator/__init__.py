"""Multi-Agent Orchestrator — Argus Phase 2.

Orchestrates multiple agents working together on complex tasks.
Builds on Capability Engine + Sandbox for isolated execution.
"""
from __future__ import annotations

from argus.orchestrator.agent import AgentSpec, AgentRole, AgentState
from argus.orchestrator.orchestrator import MultiAgentOrchestrator, OrchestrationResult
from argus.orchestrator.communication import MessageBus, AgentMessage

__all__ = [
    "AgentSpec",
    "AgentRole",
    "AgentState",
    "MultiAgentOrchestrator",
    "OrchestrationResult",
    "MessageBus",
    "AgentMessage",
]