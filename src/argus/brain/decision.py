"""Decision Engine — Argus Brain.

Pure deterministic scoring of candidate options on five factors.
Every recorded decision is stored in an in-memory DecisionMemory.
"""
from __future__ import annotations

import copy
import uuid
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Mapping, Optional


@dataclass
class Decision:
    id: str
    goal_id: str
    choice: str
    confidence: float
    scores: dict[str, float]
    reasoning: str = ""
    created_at: str = field(default_factory=lambda: datetime.now().isoformat())
    metadata: dict[str, Any] = field(default_factory=dict)


class DecisionMemory:
    """Append-only in-memory store of decisions."""

    def __init__(self, max_size: Optional[int] = None) -> None:
        self._decisions: list[Decision] = []
        self.max_size = max_size

    def add(self, decision: Decision) -> None:
        self._decisions.append(decision)
        if self.max_size is not None and len(self._decisions) > self.max_size:
            self._decisions.pop(0)

    def recent(self, n: int = 5) -> list[Decision]:
        """Return up to `n` most recent decisions, newest first."""
        return list(reversed(self._decisions[-n:]))


class DecisionEngine:
    """Scores candidates and records decisions."""

    _INVERTED_FACTORS = {"cost", "risk", "latency"}

    def __init__(
        self,
        weights: Optional[Mapping[str, float]] = None,
    ) -> None:
        default_weights = {
            "confidence": 1.0,
            "cost": 1.0,
            "risk": 1.0,
            "reliability": 1.0,
            "latency": 1.0,
        }
        # Treat None *and* empty dict as "use defaults"
        if weights is not None and weights:
            default_weights.update(weights)
        self.weights = default_weights
        self.memory = DecisionMemory()

    def score_decision(
        self,
        goal_id: str,
        candidate_id: str,
        scores: Mapping[str, float],
        reasoning: str = "",
        metadata: Optional[dict[str, Any]] = None,
    ) -> Decision:
        """Evaluate one candidate and record the resulting Decision.

        Each factor must be in the range 0..1. For cost, risk, and latency
        lower values are better because we invert them inside the scoring.
        """
        normalized: dict[str, float] = {}
        for factor in self.weights:
            raw = scores.get(factor, 0.5)
            # Validate numeric and range before clamping.
            if not isinstance(raw, (int, float)):
                raise TypeError(
                    f"Score for factor '{factor}' must be a number, "
                    f"got {type(raw).__name__}: {raw!r}"
                )
            # Detect NaN (the only value where value != value).
            if raw != raw:
                raise ValueError(f"Score for factor '{factor}' is NaN")
            if not (0.0 <= raw <= 1.0):
                raise ValueError(
                    f"Score for factor '{factor}' must be between 0.0 and 1.0, "
                    f"got {raw}"
                )
            normalized[factor] = max(0.0, min(1.0, raw))

        total_weight = sum(self.weights.values())
        weighted = 0.0
        for factor, weight in self.weights.items():
            raw = normalized[factor]
            if factor in self._INVERTED_FACTORS:
                good = 1.0 - raw
            else:
                good = raw
            weighted += weight * good

        confidence = weighted / total_weight if total_weight else 0.0
        # Shallow-copy metadata to prevent external mutation from affecting stored history.
        stored_meta = dict(metadata) if metadata else {}
        decision = Decision(
            id=uuid.uuid4().hex,
            goal_id=goal_id,
            choice=candidate_id,
            confidence=confidence,
            scores=normalized,
            reasoning=reasoning,
            metadata=stored_meta,
        )
        self.memory.add(decision)
        return decision

    def recent_decisions(self, n: int = 5) -> list[Decision]:
        """Convenience wrapper around DecisionMemory.recent()."""
        return self.memory.recent(n)
