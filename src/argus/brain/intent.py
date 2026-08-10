"""Intent Parser — Argus Brain (Refinement 3).

Parses a user request into a structured intent: the goal, the verb/action
type, extracted entities, and a confidence score. Heuristic, rule-based —
the LLM does the heavy reasoning; this exists to give the Goal Engine a
typed starting point without a model call.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any, Optional


@dataclass
class ParsedIntent:
    """Structured interpretation of a user request."""

    raw: str
    intent: str = "unknown"  # execute | plan | explain | search | configure | fix
    goal: str = ""
    entities: dict[str, Any] = field(default_factory=dict)
    confidence: float = 0.0
    tokens: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "intent": self.intent,
            "goal": self.goal,
            "entities": self.entities,
            "confidence": self.confidence,
        }


# intent -> trigger words (lowercased)
_INTENT_PATTERNS: dict[str, list[str]] = {
    "execute": ["run", "execute", "deploy", "do", "start", "build", "send", "create"],
    "plan": ["plan", "schedule", "organize", "arrange", "prepare", "outline"],
    "explain": ["explain", "what is", "how does", "describe", "why", "tell me"],
    "search": ["find", "search", "look for", "lookup", "query"],
    "configure": ["configure", "setup", "set up", "install", "enable", "disable", "change"],
    "fix": ["fix", "repair", "resolve", "bug", "error", "broken", "failing"],
}

_ENTITY_PATTERNS = {
    "email": r"[\w.+-]+@[\w-]+\.[\w.]+",
    "url": r"https?://[^\s]+",
    "number": r"\b\d+(?:\.\d+)?\b",
    "path": r"(?:/[\w.\-]+)+",
}


class IntentParser:
    """Rule-based intent + entity extraction."""

    def parse(self, text: str) -> ParsedIntent:
        raw = text.strip()
        lower = raw.lower()
        tokens = re.findall(r"[\w.+-]+", lower)

        # pick intent by strongest trigger match
        best_intent = "unknown"
        best_score = 0.0
        for intent, triggers in _INTENT_PATTERNS.items():
            score = sum(1 for t in triggers if t in lower)
            # first word match counts double
            if lower.startswith(tuple(t for t in triggers if " " not in t)):
                score += 1
            if score > best_score:
                best_score = score
                best_intent = intent

        # entities
        entities: dict[str, Any] = {}
        for name, pattern in _ENTITY_PATTERNS.items():
            found = re.findall(pattern, raw)
            if found:
                entities[name] = found[0] if len(found) == 1 else found

        # goal: strip intent triggers from the start, keep the rest
        goal = raw
        if best_intent in _INTENT_PATTERNS:
            for t in sorted(_INTENT_PATTERNS[best_intent], key=len, reverse=True):
                if lower.startswith(t):
                    goal = raw[len(t):].strip(" :,-")
                    break

        confidence = min(0.95, 0.4 + best_score * 0.15)
        if best_intent == "unknown":
            confidence = 0.2

        return ParsedIntent(
            raw=raw,
            intent=best_intent,
            goal=goal or raw,
            entities=entities,
            confidence=confidence,
            tokens=tokens,
        )


def create_intent_parser() -> IntentParser:
    return IntentParser()
