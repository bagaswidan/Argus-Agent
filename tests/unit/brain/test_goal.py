from argus.brain.goal import GoalEngine, GoalStatus


def test_lifecycle_reaches_ready_and_decomposes():
    engine = GoalEngine()
    goal = engine.run("implement X and test Y")

    assert goal.status == GoalStatus.READY
    assert len(goal.subtasks) >= 2
    assert any("Implement" in task for task in goal.subtasks)
    assert any("Test" in task for task in goal.subtasks)


def test_single_keyword_decomposes_correctly():
    engine = GoalEngine()

    # Single keyword with no extra content
    goal = engine.run("implement")
    assert goal.status == GoalStatus.READY
    assert goal.subtasks == ["implement"]

    # Single keyword followed by content
    goal = engine.run("write docs")
    assert goal.status == GoalStatus.READY
    assert goal.subtasks == ["Write docs"]
