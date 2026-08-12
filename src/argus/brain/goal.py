"""Goal Engine — Argus Brain.

Pure deterministic lifecycle for goals, no LLM involvement.
"""
from __future__ import annotations

import re
import uuid
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum


class GoalStatus(Enum):
    RECEIVED = "received"
    ANALYZED = "analyzed"
    VALIDATED = "validated"
    DECOMPOSED = "decomposed"
    READY = "ready"


@dataclass
class Goal:
    id: str
    description: str
    status: GoalStatus = GoalStatus.RECEIVED
    subtasks: list[str] = field(default_factory=list)
    created_at: str = field(default_factory=lambda: datetime.now().isoformat())


class GoalEngine:
    """Lifecycle manager that moves a Goal through its states."""

    _KEYWORDS = ("implement", "test", "write", "refactor")

    def __init__(self) -> None:
        # Precompile the splitting pattern for performance.
        pattern = r"\b(" + "|".join(self._KEYWORDS) + r")\b"
        self._split_re = re.compile(pattern, flags=re.IGNORECASE)

    def receive_goal(self, description: str) -> Goal:
        if not isinstance(description, str):
            raise TypeError("Goal description must be a string")
        return Goal(id=uuid.uuid4().hex, description=description)

    def analyze_goal(self, goal: Goal) -> Goal:
        if goal.status != GoalStatus.RECEIVED:
            raise RuntimeError(
                f"Cannot analyze goal with status {goal.status.value}",
            )
        goal.status = GoalStatus.ANALYZED
        return goal

    def validate_goal(self, goal: Goal) -> Goal:
        if goal.status != GoalStatus.ANALYZED:
            raise RuntimeError(
                f"Cannot validate goal with status {goal.status.value}",
            )
        goal.status = GoalStatus.VALIDATED
        return goal

    def decompose_goal(self, goal: Goal) -> Goal:
        if goal.status != GoalStatus.VALIDATED:
            raise RuntimeError(
                f"Cannot decompose goal with status {goal.status.value}",
            )
        goal.subtasks = self._split_subtasks(goal.description)
        goal.status = GoalStatus.DECOMPOSED
        return goal

    def ready_goal(self, goal: Goal) -> Goal:
        if goal.status != GoalStatus.DECOMPOSED:
            raise RuntimeError(
                f"Cannot ready goal with status {goal.status.value}",
            )
        goal.status = GoalStatus.READY
        return goal

    def run(self, description: str) -> Goal:
        """Run the full lifecycle: RECEIVED -> ANALYZED -> VALIDATED -> DECOMPOSED -> READY."""
        goal = self.receive_goal(description)
        self.analyze_goal(goal)
        self.validate_goal(goal)
        self.decompose_goal(goal)
        self.ready_goal(goal)
        return goal

    def _split_subtasks(self, description: str) -> list[str]:
        if not description.strip():
            return []   # empty description yields no subtasks
        parts = self._split_re.split(description)
        tasks: list[str] = []
        # Odd indices are the captured keywords; the following entry is its content.
        for i in range(1, len(parts), 2):
            # Guard against a keyword being the very last token (no following content).
            if i + 1 >= len(parts):
                break
            keyword = parts[i]
            content = parts[i + 1].strip(" .,;")
            if content:
                tasks.append(f"{keyword.capitalize()} {content}")
        if not tasks:
            tasks.append(description.strip())
        return tasks
