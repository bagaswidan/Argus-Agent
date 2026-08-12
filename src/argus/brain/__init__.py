"""Brain Module — Argus.

Model router, planner, provider, and reasoning orchestration.

"""
from __future__ import annotations

from argus.brain.decision import Decision, DecisionEngine, DecisionMemory
from argus.brain.goal import Goal, GoalEngine, GoalStatus
from argus.brain.intent import IntentParser, ParsedIntent, create_intent_parser
from argus.brain.planning import ExecutionPlan, PlanningEngine, PlanStep, create_planning_engine
from argus.brain.provider import ChatMessage, ChatResponse, OmniRouteProvider, create_provider
from argus.brain.router import ModelResolution, ModelRouter
from argus.brain.solver import FailureAnalysis, ProblemSolver, create_problem_solver
from argus.brain.thinking import ThinkingMode, ThinkingSelector

__all__ = [
    "ChatMessage",
    "ChatResponse",
    "Decision",
    "DecisionEngine",
    "DecisionMemory",
    "ExecutionPlan",
    "FailureAnalysis",
    "Goal",
    "GoalEngine",
    "GoalStatus",
    "IntentParser",
    "ModelResolution",
    "ModelRouter",
    "OmniRouteProvider",
    "ParsedIntent",
    "PlanStep",
    "PlanningEngine",
    "ProblemSolver",
    "ThinkingMode",
    "ThinkingSelector",
    "create_intent_parser",
    "create_planning_engine",
    "create_problem_solver",
    "create_provider",
]
