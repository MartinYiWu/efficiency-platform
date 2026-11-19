from efficiency_platform_agent.context.growth import GrowthBound, evaluate_growth
from efficiency_platform_agent.core.context_control import (
    TokenMeasurement,
    WindowLimits,
)


def measured(tokens):
    return TokenMeasurement(tokens, (("request", tokens),), "counter/1", True)


def test_thresholds_use_published_input_cap_and_keep_unknown_separate():
    limits = WindowLimits(1200, 1000, 100, 100, 1000)
    assert evaluate_growth(limits, measured(700)).actual_pressure == "NORMAL"
    assert evaluate_growth(limits, measured(701)).actual_pressure == "PREPARE"
    assert evaluate_growth(limits, measured(850)).actual_pressure == "PREPARE"
    result = evaluate_growth(limits, measured(851))
    assert result.actual_pressure == "INTERVENE"
    assert result.predicted_pressure == "UNKNOWN" and result.G is None


def test_growth_provenance_and_materialized_result_are_not_actual_usage():
    limits = WindowLimits(1000, None, 0, 0, 1000)
    bound = GrowthBound(400, "tool/result-projection", "projection/2")
    predicted = evaluate_growth(limits, measured(650), generation_bound=bound)
    assert predicted.T == 650 and predicted.predicted_total == 1050
    assert predicted.predicted_pressure == "OVERFLOW"
    actual = evaluate_growth(
        limits, measured(650), generation_bound=bound, materialized=measured(720)
    )
    assert actual.T == 720 and actual.actual_pressure == "PREPARE"
    assert (
        actual.predicted_total is None and actual.predicted_pressure == "MATERIALIZED"
    )


def test_unknown_or_unverified_growth_cannot_invent_a_number():
    import pytest

    with pytest.raises(ValueError):
        GrowthBound(1, "", "version")
    with pytest.raises(ValueError):
        GrowthBound(-1, "tool", "version")
    with pytest.raises(ValueError, match="CONTEXT_CAPACITY_UNVERIFIED"):
        evaluate_growth(
            WindowLimits(1000, None, 0, 0, 1000),
            TokenMeasurement(1, (), "counter/1", False),
        )
