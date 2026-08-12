"""Critic — Argus Phase 2.

Agent that reviews and critiques outputs for quality, correctness, and completeness.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime
from enum import Enum
from typing import Any


class CritiqueSeverity(str, Enum):
    """Severity of a critique finding."""

    INFO = "info"
    WARNING = "warning"
    ERROR = "error"
    CRITICAL = "critical"


class CritiqueCategory(str, Enum):
    """Category of critique finding."""

    CORRECTNESS = "correctness"  # Factual accuracy
    COMPLETENESS = "completeness"  # Missing information
    CLARITY = "clarity"  # Unclear or ambiguous
    CONSISTENCY = "consistency"  # Internal contradictions
    STYLE = "style"  # Formatting, tone
    SECURITY = "security"  # Security concerns
    PERFORMANCE = "performance"  # Efficiency issues


@dataclass
class CritiqueFinding:
    """A single critique finding."""

    category: CritiqueCategory
    severity: CritiqueSeverity
    message: str
    location: str = ""  # Where in the output (line, section, etc.)
    suggestion: str = ""  # How to fix
    confidence: float = 1.0  # 0.0 - 1.0

    def to_dict(self) -> dict[str, Any]:
        return {
            "category": self.category.value,
            "severity": self.severity.value,
            "message": self.message,
            "location": self.location,
            "suggestion": self.suggestion,
            "confidence": self.confidence,
        }


@dataclass
class CritiqueConfig:
    """Configuration for critique behavior."""

    enabled_categories: list[CritiqueCategory] = field(default_factory=lambda: list(CritiqueCategory))
    min_severity: CritiqueSeverity = CritiqueSeverity.INFO
    max_findings: int = 20
    require_suggestions: bool = True
    custom_criteria: list[str] = field(default_factory=list)


@dataclass
class CritiqueResult:
    """Result of a critique review."""

    original_output: str
    findings: list[CritiqueFinding] = field(default_factory=list)
    overall_score: float = 1.0  # 0.0 - 1.0
    passed: bool = True
    reviewed_at: datetime = field(default_factory=lambda: datetime.now(UTC))
    reviewer_id: str = ""

    def add_finding(self, finding: CritiqueFinding) -> None:
        self.findings.append(finding)
        # Update overall score based on findings
        self._recalculate_score()

    def _recalculate_score(self) -> None:
        if not self.findings:
            self.overall_score = 1.0
            self.passed = True
            return

        # Weight by severity
        severity_weights = {
            CritiqueSeverity.INFO: 0.05,
            CritiqueSeverity.WARNING: 0.15,
            CritiqueSeverity.ERROR: 0.35,
            CritiqueSeverity.CRITICAL: 0.6,
        }

        total_penalty = sum(
            severity_weights.get(f.severity, 0.1) * f.confidence
            for f in self.findings
        )
        self.overall_score = max(0.0, 1.0 - total_penalty)
        # Fail if any CRITICAL or ERROR findings
        self.passed = not any(
            f.severity in (CritiqueSeverity.CRITICAL, CritiqueSeverity.ERROR)
            for f in self.findings
        )

    def get_findings_by_severity(self, severity: CritiqueSeverity) -> list[CritiqueFinding]:
        return [f for f in self.findings if f.severity == severity]

    def get_findings_by_category(self, category: CritiqueCategory) -> list[CritiqueFinding]:
        return [f for f in self.findings if f.category == category]

    def to_dict(self) -> dict[str, Any]:
        return {
            "original_output": self.original_output,
            "findings": [f.to_dict() for f in self.findings],
            "overall_score": self.overall_score,
            "passed": self.passed,
            "reviewed_at": self.reviewed_at.isoformat(),
            "reviewer_id": self.reviewer_id,
        }


class Critic:
    """Reviews and critiques agent outputs."""

    def __init__(
        self,
        config: CritiqueConfig | None = None,
        reviewer_id: str = "critic",
    ):
        self.config = config or CritiqueConfig()
        self.reviewer_id = reviewer_id

    async def critique(
        self,
        output: str,
        context: dict[str, Any] | None = None,
        expected_output: str | None = None,
    ) -> CritiqueResult:
        """Review an output and return critique findings."""
        result = CritiqueResult(
            original_output=output,
            reviewer_id=self.reviewer_id,
        )

        # Run built-in critique checks
        await self._check_completeness(output, context, result)
        await self._check_clarity(output, result)
        await self._check_consistency(output, result)
        await self._check_security(output, result)

        # Custom criteria
        for criterion in self.config.custom_criteria:
            await self._check_custom(output, criterion, result)

        # Compare with expected if provided
        if expected_output:
            await self._compare_with_expected(output, expected_output, result)

        # Filter by config
        result.findings = [
            f
            for f in result.findings
            if f.category in self.config.enabled_categories
            and self._severity_meets_min(f.severity)
        ][: self.config.max_findings]

        # Recalculate after filtering
        result._recalculate_score()

        return result

    def _severity_meets_min(self, severity: CritiqueSeverity) -> bool:
        order = [
            CritiqueSeverity.INFO,
            CritiqueSeverity.WARNING,
            CritiqueSeverity.ERROR,
            CritiqueSeverity.CRITICAL,
        ]
        return order.index(severity) >= order.index(self.config.min_severity)

    async def _check_completeness(
        self,
        output: str,
        context: dict[str, Any] | None,
        result: CritiqueResult,
    ) -> None:
        """Check if output is complete relative to context."""
        # Empty output should always be flagged
        if not output.strip():
            result.add_finding(
                CritiqueFinding(
                    category=CritiqueCategory.COMPLETENESS,
                    severity=CritiqueSeverity.ERROR,
                    message="Output is empty",
                    location="output",
                    suggestion="Provide substantive content",
                    confidence=1.0,
                ),
            )

        if not context:
            return

        # Check for required sections/keywords from context
        required = context.get("required_sections", [])
        for section in required:
            if section.lower() not in output.lower():
                result.add_finding(
                    CritiqueFinding(
                        category=CritiqueCategory.COMPLETENESS,
                        severity=CritiqueSeverity.WARNING,
                        message=f"Missing required section: {section}",
                        location="output",
                        suggestion=f"Add section covering {section}",
                        confidence=0.8,
                    ),
                )

        # Check minimum length - always check this even if not in context
        min_length = context.get("min_length", 10)
        if len(output) < min_length:
            result.add_finding(
                CritiqueFinding(
                    category=CritiqueCategory.COMPLETENESS,
                    severity=CritiqueSeverity.WARNING if output else CritiqueSeverity.ERROR,
                    message=f"Output too short ({len(output)} < {min_length} chars)",
                    location="output",
                    suggestion="Expand the output with more detail",
                    confidence=0.9,
                ),
            )

    async def _check_clarity(self, output: str, result: CritiqueResult) -> None:
        """Check for clarity issues."""
        # Check for very long sentences
        sentences = output.split(".")
        for i, sentence in enumerate(sentences):
            if len(sentence) > 300:
                result.add_finding(
                    CritiqueFinding(
                        category=CritiqueCategory.CLARITY,
                        severity=CritiqueSeverity.WARNING,
                        message=f"Very long sentence ({len(sentence)} chars)",
                        location=f"sentence {i + 1}",
                        suggestion="Break into shorter sentences",
                        confidence=0.7,
                    ),
                )

        # Check for unclear references
        unclear_patterns = [
            r"\bit\b",
            r"\bthis\b",
            r"\bthat\b",
            r"\bthese\b",
            r"\bthose\b",
        ]
        import re

        for pattern in unclear_patterns:
            matches = list(re.finditer(pattern, output, re.IGNORECASE))
            if len(matches) > 10:
                result.add_finding(
                    CritiqueFinding(
                        category=CritiqueCategory.CLARITY,
                        severity=CritiqueSeverity.INFO,
                        message=f"High usage of ambiguous pronouns ({pattern})",
                        location="output",
                        suggestion="Replace with specific nouns",
                        confidence=0.5,
                    ),
                )

    async def _check_consistency(self, output: str, result: CritiqueResult) -> None:
        """Check for internal consistency."""
        # Look for contradictory statements
        lines = output.split("\n")
        for i, line in enumerate(lines):
            line_lower = line.lower()
            # Simple contradiction detection (placeholder)
            if "always" in line_lower and "never" in line_lower:
                result.add_finding(
                    CritiqueFinding(
                        category=CritiqueCategory.CONSISTENCY,
                        severity=CritiqueSeverity.WARNING,
                        message="Possible contradiction: 'always' and 'never' in same line",
                        location=f"line {i + 1}",
                        suggestion="Review for logical consistency",
                        confidence=0.4,
                    ),
                )

    async def _check_security(self, output: str, result: CritiqueResult) -> None:
            """Check for security issues."""
            import re

            # Check for potential secrets/keys
            patterns = {
                "api_key": r"(api[_-]?key|apikey)[\s:=]+[\"']?[\w\-.]{16,}",
                "password": r"(password|passwd|pwd)[\s:=]+[\"']?\S+",
                "token": r"(token|secret)[\s:=]+[\"']?[\w\-.]{16,}",
                "private_key": r"-----BEGIN (RSA |EC )?PRIVATE KEY-----",
            }

            for name, pattern in patterns.items():
                if re.search(pattern, output, re.IGNORECASE):
                    result.add_finding(
                        CritiqueFinding(
                            category=CritiqueCategory.SECURITY,
                            severity=CritiqueSeverity.CRITICAL,
                            message=f"Potential {name} exposed in output",
                            location="output",
                            suggestion="Remove sensitive data before output",
                            confidence=0.8,
                        ),
                    )

    async def _check_custom(
        self,
        output: str,
        criterion: str,
        result: CritiqueResult,
    ) -> None:
        """Check custom criterion (placeholder for LLM-based checks)."""
        # In a full implementation, this would use an LLM to evaluate
        # the custom criterion against the output
        pass

    async def _compare_with_expected(
        self,
        output: str,
        expected: str,
        result: CritiqueResult,
    ) -> None:
        """Compare output with expected output."""
        # Simple similarity check
        output_words = set(output.lower().split())
        expected_words = set(expected.lower().split())

        if expected_words:
            overlap = len(output_words & expected_words) / len(expected_words)
            if overlap < 0.5:
                result.add_finding(
                    CritiqueFinding(
                        category=CritiqueCategory.CORRECTNESS,
                        severity=CritiqueSeverity.WARNING,
                        message=f"Low similarity to expected output ({overlap:.0%} overlap)",
                        location="output",
                        suggestion="Review expected content and ensure coverage",
                        confidence=0.6,
                    ),
                )
