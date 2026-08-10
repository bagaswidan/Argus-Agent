from argus.brain.decision import DecisionEngine


def test_weight_respect_and_record():
    engine = DecisionEngine(
        weights={
            "confidence": 1.0,
            "cost": 2.0,
            "risk": 1.0,
            "reliability": 1.0,
            "latency": 1.0,
        }
    )
    low_cost = engine.score_decision(
        goal_id="goal-1",
        candidate_id="low-cost",
        scores={
            "confidence": 0.8,
            "cost": 0.1,
            "risk": 0.3,
            "reliability": 0.8,
            "latency": 0.2,
        },
    )
    high_cost = engine.score_decision(
        goal_id="goal-1",
        candidate_id="high-cost",
        scores={
            "confidence": 0.8,
            "cost": 0.9,
            "risk": 0.3,
            "reliability": 0.8,
            "latency": 0.2,
        },
    )

    assert low_cost.confidence > high_cost.confidence
    assert len(engine.recent_decisions()) == 2
    assert engine.recent_decisions()[0].choice == "high-cost"
