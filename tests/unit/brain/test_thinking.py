from argus.brain.thinking import ThinkingMode, ThinkingSelector


def test_deep_for_high_complexity_high_ambiguity():
    selector = ThinkingSelector()
    mode = selector.select(complexity=0.9, ambiguity=0.8, novelty=0.4, risk=0.4)
    assert mode == ThinkingMode.DEEP


def test_temperature_range_and_description():
    assert ThinkingMode.DEEP.temperature_min < ThinkingMode.DEEP.temperature_max
    assert isinstance(ThinkingMode.FAST.description, str)
    assert ThinkingMode.BALANCED.temperature_min >= 0.0
    assert ThinkingMode.BALANCED.temperature_max <= 1.0
