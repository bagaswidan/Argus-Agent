"""Multi-Agent Orchestrator — Argus Phase 2.

Orchestrates multiple agents working together on complex tasks.
Builds on Capability Engine + Sandbox for isolated execution.
"""
from __future__ import annotations

from argus.orchestrator.agent import AgentRole, AgentSpec, AgentState
from argus.orchestrator.communication import AgentMessage, MessageBus
from argus.orchestrator.orchestrator import MultiAgentOrchestrator, OrchestrationResult

__all__ = [
    "AgentMessage",
    "AgentRole",
    "AgentSpec",
    "AgentState",
    "MessageBus",
    "MultiAgentOrchestrator",
    "OrchestrationResult",
]
