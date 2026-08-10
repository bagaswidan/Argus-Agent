"""Brain Module — Argus.

Model router, planner, provider, and reasoning orchestration.

"""
from __future__ import annotations

from argus.brain.router import ModelRouter, ModelResolution
from argus.brain.provider import OmniRouteProvider, ChatMessage, ChatResponse, create_provider
from argus.brain.thinking import ThinkingMode, ThinkingSelector
from argus.brain.decision import Decision, DecisionEngine, DecisionMemory
from argus.brain.goal import Goal, GoalEngine, GoalStatus
from argus.brain.planning import PlanningEngine, ExecutionPlan, PlanStep, create_planning_engine
from argus.brain.intent import IntentParser, ParsedIntent, create_intent_parser
from argus.brain.solver import ProblemSolver, FailureAnalysis, create_problem_solver

__all__ = [
    "ModelRouter",
    "ModelResolution",
    "OmniRouteProvider",
    "ChatMessage",
    "ChatResponse",
    "create_provider",
    "ThinkingMode",
    "ThinkingSelector",
    "Decision",
    "DecisionEngine",
    "DecisionMemory",
    "Goal",
    "GoalEngine",
    "GoalStatus",
    "PlanningEngine",
    "ExecutionPlan",
    "PlanStep",
    "create_planning_engine",
    "IntentParser",
    "ParsedIntent",
    "create_intent_parser",
    "ProblemSolver",
    "FailureAnalysis",
    "create_problem_solver",
]