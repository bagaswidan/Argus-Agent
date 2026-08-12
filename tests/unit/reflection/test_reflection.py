"""Test Reflection / Critic Loop — Argus Phase 2."""
from __future__ import annotations

import pytest

from argus.reflection.critic import (
    Critic,
    CritiqueCategory,
    CritiqueConfig,
    CritiqueFinding,
    CritiqueResult,
    CritiqueSeverity,
)
from argus.reflection.loop import (
    ReflectionConfig,
    ReflectionLoop,
    ReflectionResult,
    ReflectionStep,
)


class TestCritiqueFinding:
    """Test CritiqueFinding dataclass."""

    def test_creation(self):
        finding = CritiqueFinding(
            category=CritiqueCategory.CORRECTNESS,
            severity=CritiqueSeverity.ERROR,
            message="Test error",
            location="line 1",
            suggestion="Fix it",
            confidence=0.9,
        )
        assert finding.category == CritiqueCategory.CORRECTNESS
        assert finding.severity == CritiqueSeverity.ERROR
        assert finding.confidence == 0.9

    def test_to_dict(self):
        finding = CritiqueFinding(
            category=CritiqueCategory.SECURITY,
            severity=CritiqueSeverity.CRITICAL,
            message="API key exposed",
        )
        d = finding.to_dict()
        assert d["category"] == "security"
        assert d["severity"] == "critical"
        assert d["message"] == "API key exposed"


class TestCritiqueResult:
    """Test CritiqueResult."""

    def test_initial_passed(self):
        result = CritiqueResult(original_output="Test output")
        assert result.passed is True
        assert result.overall_score == 1.0
        assert result.findings == []

    def test_add_finding_lowers_score(self):
        result = CritiqueResult(original_output="Test")
        finding = CritiqueFinding(
            category=CritiqueCategory.CORRECTNESS,
            severity=CritiqueSeverity.ERROR,
            message="Error",
        )
        result.add_finding(finding)
        assert result.overall_score < 1.0
        assert result.passed is False

    def test_critical_fails(self):
        result = CritiqueResult(original_output="Test")
        finding = CritiqueFinding(
            category=CritiqueCategory.SECURITY,
            severity=CritiqueSeverity.CRITICAL,
            message="Critical issue",
        )
        result.add_finding(finding)
        assert result.passed is False
        assert result.overall_score < 0.5

    def test_filter_by_severity(self):
        result = CritiqueResult(original_output="Test")
        result.add_finding(
            CritiqueFinding(
                category=CritiqueCategory.CORRECTNESS,
                severity=CritiqueSeverity.INFO,
                message="Info",
            ),
        )
        result.add_finding(
            CritiqueFinding(
                category=CritiqueCategory.CORRECTNESS,
                severity=CritiqueSeverity.ERROR,
                message="Error",
            ),
        )
        errors = result.get_findings_by_severity(CritiqueSeverity.ERROR)
        assert len(errors) == 1

    def test_filter_by_category(self):
        result = CritiqueResult(original_output="Test")
        result.add_finding(
            CritiqueFinding(
                category=CritiqueCategory.SECURITY,
                severity=CritiqueSeverity.WARNING,
                message="Security",
            ),
        )
        result.add_finding(
            CritiqueFinding(
                category=CritiqueCategory.CLARITY,
                severity=CritiqueSeverity.WARNING,
                message="Clarity",
            ),
        )
        security = result.get_findings_by_category(CritiqueCategory.SECURITY)
        assert len(security) == 1


class TestCritic:
    """Test Critic."""

    @pytest.mark.asyncio
    async def test_critique_empty_output(self):
        critic = Critic()
        result = await critic.critique("")
        assert result.overall_score < 1.0

    @pytest.mark.asyncio
    async def test_critique_completeness(self):
        critic = Critic()
        context = {"required_sections": ["Introduction", "Conclusion"]}
        result = await critic.critique("Just some content", context=context)
        completeness_findings = result.get_findings_by_category(CritiqueCategory.COMPLETENESS)
        assert len(completeness_findings) >= 2  # Missing both sections

    @pytest.mark.asyncio
    async def test_critique_short_output(self):
        critic = Critic()
        context = {"min_length": 100}
        result = await critic.critique("Short", context=context)
        completeness_findings = result.get_findings_by_category(CritiqueCategory.COMPLETENESS)
        assert any("too short" in f.message for f in completeness_findings)

    @pytest.mark.asyncio
    async def test_critique_security_api_key(self):
        critic = Critic()
        result = await critic.critique("My api_key = 'sk-1234567890abcdef'")
        security_findings = result.get_findings_by_category(CritiqueCategory.SECURITY)
        assert len(security_findings) > 0
        assert any("api_key" in f.message for f in security_findings)

    @pytest.mark.asyncio
    async def test_critique_security_password(self):
        critic = Critic()
        result = await critic.critique("password = 'secret123'")
        security_findings = result.get_findings_by_category(CritiqueCategory.SECURITY)
        assert any("password" in f.message.lower() for f in security_findings)

    @pytest.mark.asyncio
    async def test_critique_expected_output(self):
        critic = Critic()
        # Low overlap should trigger finding
        result = await critic.critique(
            "The dog ran fast",
            expected_output="The cat sat on the mat and purred loudly",
        )
        correctness = result.get_findings_by_category(CritiqueCategory.CORRECTNESS)
        assert len(correctness) > 0

    @pytest.mark.asyncio
    async def test_critique_min_severity_filter(self):
        config = CritiqueConfig(min_severity=CritiqueSeverity.ERROR)
        critic = Critic(config=config)
        result = await critic.critique("This is a test with some unclear references here and there and everywhere")
        # INFO findings should be filtered out
        info_findings = result.get_findings_by_severity(CritiqueSeverity.INFO)
        assert len(info_findings) == 0


class TestReflectionLoop:
    """Test ReflectionLoop."""

    @pytest.mark.asyncio
    async def test_run_passes_immediately(self):
        config = ReflectionConfig(max_iterations=3, min_score_to_pass=0.5)
        loop = ReflectionLoop(config=config)

        async def no_op_revision(output, critique):
            return output  # Don't change

        result = await loop.run("Good output that passes", no_op_revision)
        assert result.success is True
        assert result.total_iterations == 1
        assert result.stopped_reason == "passed"

    @pytest.mark.asyncio
    async def test_run_revises_and_passes(self):
        config = ReflectionConfig(max_iterations=3, min_score_to_pass=0.9)
        loop = ReflectionLoop(config=config)

        revision_called = False

        async def revision_fn(output, critique):
            nonlocal revision_called
            revision_called = True
            return "Improved output with more detail and clarity and sufficient length to pass"

        result = await loop.run("Short", revision_fn, context={"min_length": 100})
        assert revision_called is True

    @pytest.mark.asyncio
    async def test_run_max_iterations(self):
        config = ReflectionConfig(max_iterations=2, min_score_to_pass=0.95)
        loop = ReflectionLoop(config=config)

        async def revision_fn(output, critique):
            # Always return something that still has issues (short content)
            return "Still not good"

        result = await loop.run("Bad output", revision_fn, context={"min_length": 100})
        assert result.total_iterations == 2
        assert result.stopped_reason == "max_iterations"

    @pytest.mark.asyncio
    async def test_run_stops_on_critical(self):
        config = ReflectionConfig(max_iterations=3, stop_on_critical=True)
        loop = ReflectionLoop(config=config)

        async def revision_fn(output, critique):
            return "Still has api_key = 'sk-1234567890abcdef'"

        result = await loop.run("Has api_key = 'sk-1234567890abcdef'", revision_fn)
        assert result.stopped_reason == "critical_finding"
        assert result.total_iterations == 1

    @pytest.mark.asyncio
    async def test_run_stops_on_error(self):
        config = ReflectionConfig(max_iterations=3, stop_on_error=True)
        loop = ReflectionLoop(config=config)

        async def revision_fn(output, critique):
            return ""  # Empty output triggers ERROR

        # Initial output is already too short to pass min_length check
        result = await loop.run("", revision_fn, context={"min_length": 10})
        # Should stop on first iteration because ERROR finding from empty output
        assert result.stopped_reason == "error_finding"

    @pytest.mark.asyncio
    async def test_run_revision_error(self):
        config = ReflectionConfig(max_iterations=3, min_score_to_pass=0.95)
        loop = ReflectionLoop(config=config)

        async def revision_fn(output, critique):
            raise ValueError("Revision failed")

        # Use initial output that will trigger a finding but not pass
        result = await loop.run("Short content", revision_fn, context={"min_length": 100})
        assert "revision_error" in result.stopped_reason


class TestReflectionConfig:
    """Test ReflectionConfig."""

    def test_defaults(self):
        config = ReflectionConfig()
        assert config.max_iterations == 3
        assert config.min_score_to_pass == 0.7
        assert config.stop_on_critical is True
        assert config.stop_on_error is True


class TestReflectionStep:
    """Test ReflectionStep."""

    def test_to_dict(self):
        from argus.reflection.critic import CritiqueResult

        critique = CritiqueResult(original_output="test")
        step = ReflectionStep(iteration=1, output="test", critique=critique)
        d = step.to_dict()
        assert d["iteration"] == 1
        assert d["output"] == "test"
        assert d["revised"] is False


class TestReflectionResult:
    """Test ReflectionResult."""

    def test_to_dict(self):
        result = ReflectionResult(
            success=True,
            final_output="final",
            total_iterations=2,
            final_score=0.8,
        )
        d = result.to_dict()
        assert d["success"] is True
        assert d["final_output"] == "final"
        assert d["total_iterations"] == 2
        assert d["final_score"] == 0.8


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
