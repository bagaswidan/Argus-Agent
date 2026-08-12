"""Reflection Loop — Argus Phase 2.

Iterative self-correction loop: Agent produces output → Critic reviews →
Agent revises → Repeat until passes or max iterations.
"""
from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any

from argus.reflection.critic import Critic, CritiqueConfig, CritiqueResult, CritiqueSeverity


@dataclass
class ReflectionConfig:
    """Configuration for the reflection loop."""

    max_iterations: int = 3
    min_score_to_pass: float = 0.7
    stop_on_critical: bool = True
    stop_on_error: bool = True
    critic_config: CritiqueConfig | None = None


@dataclass
class ReflectionStep:
    """A single iteration in the reflection loop."""

    iteration: int
    output: str
    critique: CritiqueResult
    revised: bool = False
    timestamp: datetime = field(default_factory=lambda: datetime.now(UTC))

    def to_dict(self) -> dict[str, Any]:
        return {
            "iteration": self.iteration,
            "output": self.output,
            "critique": self.critique.to_dict(),
            "revised": self.revised,
            "timestamp": self.timestamp.isoformat(),
        }


@dataclass
class ReflectionResult:
    """Result of the complete reflection loop."""

    success: bool
    final_output: str
    steps: list[ReflectionStep] = field(default_factory=list)
    final_score: float = 0.0
    total_iterations: int = 0
    stopped_reason: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "success": self.success,
            "final_output": self.final_output,
            "steps": [s.to_dict() for s in self.steps],
            "final_score": self.final_score,
            "total_iterations": self.total_iterations,
            "stopped_reason": self.stopped_reason,
        }


class ReflectionLoop:
    """Iterative self-correction loop for agent outputs."""

    def __init__(
        self,
        config: ReflectionConfig | None = None,
        critic: Critic | None = None,
    ):
        self.config = config or ReflectionConfig()
        self.critic = critic or Critic(self.config.critic_config)

    async def run(
        self,
        initial_output: str,
        revision_fn: Callable[[str, CritiqueResult], Any],
        context: dict[str, Any] | None = None,
        expected_output: str | None = None,
    ) -> ReflectionResult:
        """Run the reflection loop.

        Args:
            initial_output: The initial output to review
            revision_fn: Async function(output, critique) -> revised_output
            context: Optional context for critique
            expected_output: Optional expected output for comparison

        Returns:
            ReflectionResult with final output and all steps

        """
        result = ReflectionResult(
            success=False,
            final_output=initial_output,
        )

        current_output = initial_output

        for iteration in range(1, self.config.max_iterations + 1):
            # Critique current output
            critique = await self.critic.critique(
                current_output,
                context=context,
                expected_output=expected_output,
            )

            step = ReflectionStep(
                iteration=iteration,
                output=current_output,
                critique=critique,
            )

            result.steps.append(step)

            # Check if passed
            if critique.passed and critique.overall_score >= self.config.min_score_to_pass:
                result.success = True
                result.final_output = current_output
                result.final_score = critique.overall_score
                result.total_iterations = iteration
                result.stopped_reason = "passed"
                return result

            # Check stop conditions
            has_critical = any(
                f.severity == CritiqueSeverity.CRITICAL for f in critique.findings
            )
            has_error = any(
                f.severity == CritiqueSeverity.ERROR for f in critique.findings
            )

            if self.config.stop_on_critical and has_critical:
                result.stopped_reason = "critical_finding"
                result.final_output = current_output
                result.final_score = critique.overall_score
                result.total_iterations = iteration
                return result

            if self.config.stop_on_error and has_error:
                result.stopped_reason = "error_finding"
                result.final_output = current_output
                result.final_score = critique.overall_score
                result.total_iterations = iteration
                return result

            # Last iteration - return best effort
            if iteration == self.config.max_iterations:
                result.stopped_reason = "max_iterations"
                result.final_output = current_output
                result.final_score = critique.overall_score
                result.total_iterations = iteration
                return result

            # Revise
            try:
                revised = await revision_fn(current_output, critique)
                if revised and isinstance(revised, str):
                    current_output = revised
                    step.revised = True
            except Exception as e:
                result.stopped_reason = f"revision_error: {e}"
                result.final_output = current_output
                result.final_score = critique.overall_score
                result.total_iterations = iteration
                return result

        return result

    async def run_sync(
        self,
        initial_output: str,
        revision_fn: Callable[[str, CritiqueResult], str],
        context: dict[str, Any] | None = None,
        expected_output: str | None = None,
    ) -> ReflectionResult:
        """Synchronous version of run (wraps async)."""
        import asyncio

        async def async_wrapper() -> ReflectionResult:
            return await self.run(
                initial_output,
                lambda o, c: asyncio.to_thread(revision_fn, o, c),
                context,
                expected_output,
            )

        return asyncio.run(async_wrapper())
