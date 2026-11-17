from dataclasses import replace

import pytest

from efficiency_platform_agent.context.budget import evaluate_window, window_pressure
from efficiency_platform_agent.core.context_control import WindowLimits


def limits():
    return WindowLimits(120, None, 10, 10, 100)


@pytest.mark.parametrize(
    ("total", "fixed", "status"),
    [
        (100, 100, "ALLOW"),
        (101, 90, "REJECT"),
        (90, 101, "REJECT"),
        (70, 10, "ALLOW"),
        (85, 10, "TRIM"),
    ],
)
def test_window_boundaries(total, fixed, status):
    decision = evaluate_window(limits(), total, fixed)
    assert (decision.H_ctx, decision.T, decision.F, decision.status) == (
        100,
        total,
        fixed,
        status,
    )


@pytest.mark.parametrize(
    ("total", "pressure"),
    [
        (70, "NORMAL"),
        (71, "CPU_TRIM"),
        (85, "CPU_TRIM"),
        (86, "CPU_PREPARE"),
        (100, "CPU_PREPARE"),
    ],
)
def test_pressure_has_no_llm_state(total, pressure):
    assert window_pressure(limits(), total) == pressure


@pytest.mark.parametrize("value", [True, -1, 1.5])
def test_invalid_counts(value):
    with pytest.raises(ValueError):
        evaluate_window(limits(), value, 0)
    with pytest.raises(ValueError):
        evaluate_window(limits(), 0, value)


def test_formula_and_zero_cap():
    assert WindowLimits(32768, None, 4096, 1639, 24000).input_cap() == 24000
    assert WindowLimits(32768, 23000, 4096, 1639, 24000).input_cap() == 23000
    assert (
        evaluate_window(replace(limits(), node_input_limit=0), 0, 0).status == "REJECT"
    )


def test_fixed_content_cannot_exceed_total():
    assert evaluate_window(limits(), 10, 20).status == "REJECT"
