"""Problem Solver — Argus Brain (Refinement 3).

When a workflow fails, the Problem Solver proposes recovery paths instead
of just surfacing the error. It classifies the failure, suggests
alternatives, and can build a replan request for the Planning Engine.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass
class FailureAnalysis:
    """Root-cause-ish classification of a failure."""

    error: str
    category: str = "unknown"  # timeout | connection | validation | resource | logic
    retryable: bool = False
    suggestion: str = ""
    alternative_actions: list[str] = field(default_factory=list)
    confidence: float = 0.0

    def to_dict(self) -> dict[str, Any]:
        return {
            "category": self.category,
            "retryable": self.retryable,
            "suggestion": self.suggestion,
            "alternatives": self.alternative_actions,
            "confidence": self.confidence,
        }


_CATEGORY_RULES = [
    ("timeout", ["timeout", "timed out", "deadline"]),
    ("connection", ["connection", "refused", "unreachable", "503", "502", "network"]),
    ("validation", ["invalid", "validation", "schema", "not found", "404"]),
    ("resource", ["memory", "resource", "quota", "limit", "disk", "full"]),
    ("logic", ["assert", "logic", "bug", "unexpected", "wrong"]),
]

_RETRYABLE = {"timeout", "connection"}


class ProblemSolver:
    """Classifies failures and proposes recovery actions."""

    def analyze(self, error: str, available_actions: list[str] | None = None) -> FailureAnalysis:
        lower = error.lower()
        category = "unknown"
        for cat, keywords in _CATEGORY_RULES:
            if any(k in lower for k in keywords):
                category = cat
                break

        retryable = category in _RETRYABLE
        suggestions = {
            "timeout": "Increase the timeout or retry with backoff.",
            "connection": "Check the endpoint is reachable, then retry.",
            "validation": "Fix the input to match the expected contract.",
            "resource": "Reduce scope or free up resources, then retry.",
            "logic": "Review the logic; this needs a code fix, not a retry.",
            "unknown": "Inspect logs for more context.",
        }
        alternatives = {
            "timeout": ["retry", "fallback-model", "chunk-input"],
            "connection": ["retry", "fallback-endpoint", "use-cache"],
            "validation": ["re-prompt", "normalize-input"],
            "resource": ["reduce-scope", "queue-later"],
            "logic": ["replan", "escalate"],
            "unknown": ["replan"],
        }
        provided = available_actions or alternatives.get(category, ["replan"])

        return FailureAnalysis(
            error=error,
            category=category,
            retryable=retryable,
            suggestion=suggestions[category],
            alternative_actions=provided,
            confidence=0.85 if category != "unknown" else 0.4,
        )


def create_problem_solver() -> ProblemSolver:
    return ProblemSolver()
