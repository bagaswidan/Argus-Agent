"""Test Intent Parser + Problem Solver — Argus (Refinement 3)."""
from __future__ import annotations

import pytest

from argus.brain.intent import create_intent_parser
from argus.brain.solver import create_problem_solver


class TestIntentParser:
    def test_execute_intent(self):
        parsed = create_intent_parser().parse("deploy argus to staging")
        assert parsed.intent == "execute"
        assert "staging" in parsed.goal

    def test_plan_intent(self):
        parsed = create_intent_parser().parse("plan the migration steps")
        assert parsed.intent == "plan"

    def test_explain_intent(self):
        parsed = create_intent_parser().parse("what is the architecture?")
        assert parsed.intent == "explain"

    def test_search_intent(self):
        parsed = create_intent_parser().parse("find invoices from last month")
        assert parsed.intent == "search"

    def test_fix_intent(self):
        parsed = create_intent_parser().parse("fix the failing test")
        assert parsed.intent == "fix"

    def test_unknown_intent_low_confidence(self):
        parsed = create_intent_parser().parse("blorp quibble frobnicate")
        assert parsed.intent == "unknown"
        assert parsed.confidence < 0.5

    def test_extracts_email(self):
        parsed = create_intent_parser().parse("send report to bagas@example.com")
        assert parsed.entities.get("email") == "bagas@example.com"

    def test_extracts_url(self):
        parsed = create_intent_parser().parse("check https://example.com status")
        assert "https://example.com" in parsed.entities.get("url", [])

    def test_confidence_high_for_clear_intent(self):
        parsed = create_intent_parser().parse("deploy the application to production now")
        assert parsed.confidence > 0.5

    def test_tokens(self):
        parsed = create_intent_parser().parse("run the smoke test")
        assert "smoke" in parsed.tokens


class TestProblemSolver:
    def test_timeout_is_retryable(self):
        analysis = create_problem_solver().analyze("request timed out after 30s")
        assert analysis.category == "timeout"
        assert analysis.retryable is True
        assert "backoff" in analysis.suggestion

    def test_connection_is_retryable(self):
        analysis = create_problem_solver().analyze("connection refused on 127.0.0.1:20128")
        assert analysis.category == "connection"
        assert analysis.retryable is True

    def test_validation_not_retryable(self):
        analysis = create_problem_solver().analyze("invalid schema: missing field")
        assert analysis.category == "validation"
        assert analysis.retryable is False

    def test_logic_not_retryable(self):
        analysis = create_problem_solver().analyze("unexpected value in response")
        assert analysis.category == "logic"
        assert analysis.retryable is False

    def test_unknown_category_low_confidence(self):
        analysis = create_problem_solver().analyze("something weird happened")
        assert analysis.category == "unknown"
        assert analysis.confidence < 0.5

    def test_custom_actions_used(self):
        analysis = create_problem_solver().analyze(
            "timed out", available_actions=["custom-retry", "abort"],
        )
        assert analysis.alternative_actions == ["custom-retry", "abort"]

    def test_to_dict_shape(self):
        analysis = create_problem_solver().analyze("timed out")
        d = analysis.to_dict()
        assert set(d) == {"category", "retryable", "suggestion", "alternatives", "confidence"}


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
