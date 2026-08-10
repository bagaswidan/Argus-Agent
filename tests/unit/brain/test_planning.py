"""Test Planning Engine — Argus."""
from __future__ import annotations

import pytest

from argus.brain.planning import PlanningEngine, PlanError, create_planning_engine


class TestPlanningEngine:
    def test_simple_plan(self):
        engine = create_planning_engine()
        plan = engine.create_plan(
            "deploy",
            [
                {"action": "build", "id": "build"},
                {"action": "test", "id": "test", "depends_on": ["build"]},
            ],
        )
        assert plan.goal == "deploy"
        assert len(plan.steps) == 2
        assert plan.steps[1].depends_on == ["build"]

    def test_auto_step_ids(self):
        engine = create_planning_engine()
        plan = engine.create_plan("g", [{"action": "a"}, {"action": "b"}])
        assert all(s.id for s in plan.steps)

    def test_ready_steps(self):
        engine = create_planning_engine()
        plan = engine.create_plan(
            "g",
            [
                {"action": "a", "id": "a"},
                {"action": "b", "id": "b", "depends_on": ["a"]},
            ],
        )
        ready = plan.ready_steps()
        assert [s.id for s in ready] == ["a"]
        # Complete a, then b becomes ready
        plan.steps[0].status = "completed"
        assert [s.id for s in plan.ready_steps()] == ["b"]

    def test_is_complete(self):
        engine = create_planning_engine()
        plan = engine.create_plan("g", [{"action": "a", "id": "a"}])
        assert plan.is_complete() is False
        plan.steps[0].status = "completed"
        assert plan.is_complete() is True

    def test_missing_dependency_raises(self):
        engine = create_planning_engine()
        with pytest.raises(PlanError):
            engine.create_plan(
                "g",
                [{"action": "a", "id": "a", "depends_on": ["ghost"]}],
            )

    def test_circular_dependency_raises(self):
        engine = create_planning_engine()
        with pytest.raises(PlanError):
            engine.create_plan(
                "g",
                [
                    {"action": "a", "id": "a", "depends_on": ["b"]},
                    {"action": "b", "id": "b", "depends_on": ["a"]},
                ],
            )

    def test_estimates(self):
        engine = create_planning_engine()
        plan = engine.create_plan(
            "g",
            [
                {"action": "a", "id": "a", "estimated_cost": 0.5, "estimated_duration_ms": 100},
                {"action": "b", "id": "b", "estimated_cost": 1.5, "estimated_duration_ms": 200},
            ],
        )
        assert plan.estimated_total_cost == 2.0
        # parallel: critical path = max(100, 200) = 200
        assert plan.estimated_duration_ms == 200

    def test_sequential_duration(self):
        engine = create_planning_engine()
        plan = engine.create_plan(
            "g",
            [
                {"action": "a", "id": "a", "estimated_duration_ms": 100},
                {"action": "b", "id": "b", "depends_on": ["a"], "estimated_duration_ms": 200},
            ],
        )
        assert plan.estimated_duration_ms == 300

    def test_dependency_graph(self):
        engine = create_planning_engine()
        plan = engine.create_plan(
            "g",
            [
                {"action": "a", "id": "a"},
                {"action": "b", "id": "b", "depends_on": ["a"]},
            ],
        )
        graph = plan.dependency_graph()
        assert graph == {"a": [], "b": ["a"]}

    def test_replan(self):
        engine = create_planning_engine()
        plan = engine.create_plan(
            "g",
            [
                {"action": "build", "id": "build"},
                {"action": "deploy", "id": "deploy", "depends_on": ["build"]},
            ],
        )
        plan.steps[0].status = "completed"
        plan.steps[1].status = "failed"

        new_plan = engine.replan(
            plan,
            failed_step_ids=["deploy"],
            replacement_actions=[
                {"action": "deploy-fallback", "id": "deploy2", "depends_on": ["build"]}
            ],
        )
        assert new_plan.plan_id != plan.plan_id
        assert any(s.id == "deploy2" for s in new_plan.steps)
        failed = [s for s in new_plan.steps if s.id == "deploy"]
        assert failed[0].status == "failed"

    def test_get_plan(self):
        engine = create_planning_engine()
        plan = engine.create_plan("g", [{"action": "a"}])
        assert engine.get_plan(plan.plan_id) is plan
        assert engine.get_plan("nope") is None


if __name__ == "__main__":
    pytest.main([__file__, "-v"])