"""Thinking Modes and Selection — Argus Brain.

Deterministic selection of a thinking mode based on task characteristics.
No LLM calls are made; this is pure scoring logic.
"""
from __future__ import annotations

import math
from enum import Enum, auto


class ThinkingMode(Enum):
    FAST = auto()
    BALANCED = auto()
    DEEP = auto()
    ANALYTICAL = auto()
    CREATIVE = auto()
    DIAGNOSTIC = auto()
    STRATEGIC = auto()

    @property
    def temperature_min(self) -> float:
        return _TEMP_RANGES[self][0]

    @property
    def temperature_max(self) -> float:
        return _TEMP_RANGES[self][1]

    @property
    def description(self) -> str:
        return _DESCRIPTIONS[self]


_TEMP_RANGES: dict[ThinkingMode, tuple[float, float]] = {
    ThinkingMode.FAST: (0.0, 0.2),
    ThinkingMode.BALANCED: (0.3, 0.6),
    ThinkingMode.DEEP: (0.7, 0.9),
    ThinkingMode.ANALYTICAL: (0.2, 0.5),
    ThinkingMode.CREATIVE: (0.8, 1.0),
    ThinkingMode.DIAGNOSTIC: (0.5, 0.8),
    ThinkingMode.STRATEGIC: (0.6, 0.9),
}

_DESCRIPTIONS: dict[ThinkingMode, str] = {
    ThinkingMode.FAST: "Quick response, minimal reasoning, best for trivial tasks.",
    ThinkingMode.BALANCED: "Moderate reasoning with a balance of speed and thoroughness.",
    ThinkingMode.DEEP: "Heavy reasoning, explores many angles, ideal for complex ambiguous work.",
    ThinkingMode.ANALYTICAL: "Structured, data-driven thinking focused on root causes.",
    ThinkingMode.CREATIVE: "Divergent, exploratory thinking for novel or open-ended problems.",
    ThinkingMode.DIAGNOSTIC: (
        "Step-by-step fault isolation, good for debugging and troubleshooting.",
    ),
    ThinkingMode.STRATEGIC: (
        "High-level planning, considers long-term consequences and risk trade-offs.",
    ),
}

# Representative profile: (complexity, ambiguity, novelty, risk)
_PROFILES: dict[ThinkingMode, tuple[float, float, float, float]] = {
    ThinkingMode.FAST: (0.1, 0.0, 0.0, 0.0),
    ThinkingMode.BALANCED: (0.5, 0.4, 0.4, 0.4),
    ThinkingMode.DEEP: (0.9, 0.9, 0.5, 0.4),
    ThinkingMode.ANALYTICAL: (0.7, 0.3, 0.2, 0.2),
    ThinkingMode.CREATIVE: (0.3, 0.7, 0.9, 0.3),
    ThinkingMode.DIAGNOSTIC: (0.8, 0.6, 0.1, 0.6),
    ThinkingMode.STRATEGIC: (0.8, 0.7, 0.8, 0.9),
}


class ThinkingSelector:
    """Selects a ThinkingMode using weighted Euclidean distance to mode profiles."""

    def __init__(
        self,
        complexity_weight: float = 1.0,
        ambiguity_weight: float = 1.0,
        novelty_weight: float = 1.0,
        risk_weight: float = 1.0,
    ) -> None:
        if complexity_weight < 0 or ambiguity_weight < 0 or novelty_weight < 0 or risk_weight < 0:
            raise ValueError("All weights must be non-negative")
        self.weights = (
            complexity_weight,
            ambiguity_weight,
            novelty_weight,
            risk_weight,
        )

    def select(
        self,
        complexity: float,
        ambiguity: float,
        novelty: float,
        risk: float,
    ) -> ThinkingMode:
        """Return the most appropriate ThinkingMode for the given task scores (0..1)."""
        # Validate inputs are in [0, 1] and not NaN.
        for name, value in [
            ("complexity", complexity),
            ("ambiguity", ambiguity),
            ("novelty", novelty),
            ("risk", risk),
        ]:
            if not isinstance(value, (int, float)):
                raise TypeError(f"{name} must be a number")
            if math.isnan(value):  # NaN detection
                raise ValueError(f"{name} must not be NaN")
            if not (0.0 <= value <= 1.0):
                raise ValueError(
                    f"{name} must be between 0.0 and 1.0, got {value}",
                )

        input_vec = (complexity, ambiguity, novelty, risk)
        # Deterministic selection with tie‑breaking using a stable secondary key.
        scored = [
            (self._distance(mode, input_vec), mode)
            for mode in ThinkingMode
        ]
        scored.sort(key=lambda item: (item[0], item[1].name))
        return scored[0][1]

    def _distance(
        self,
        mode: ThinkingMode,
        input_vec: tuple[float, ...],
    ) -> float:
        profile = _PROFILES[mode]
        return sum(
            w * (value - prof) ** 2
            for w, value, prof in zip(self.weights, input_vec, profile)
        )
