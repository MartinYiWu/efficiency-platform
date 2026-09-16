"""Strategy Router 的确定性路由契约测试。"""

from dataclasses import dataclass

import pytest

from efficiency_platform_agent.core.enums import StrategyMode


@dataclass(frozen=True)
class _Request:
    """最小入站请求替身，不触碰网络或运行时。"""

    requested_strategy: StrategyMode | None = None
    workflow_id: str | None = None


def test_defaults_to_direct_without_workflow() -> None:
    from efficiency_platform_agent.routing.strategy_router import StrategyRouter

    result = StrategyRouter(
        frozenset({StrategyMode.DIRECT, StrategyMode.WORKFLOW})
    ).select(_Request())

    assert result.mode is StrategyMode.DIRECT
    assert result.rule_version == "s2.strategy/1"
    assert result.reason_code == "simple_no_tool"


def test_explicit_workflow_is_selected_and_registered() -> None:
    from efficiency_platform_agent.routing.strategy_router import StrategyRouter

    router = StrategyRouter(
        frozenset({StrategyMode.DIRECT, StrategyMode.WORKFLOW}),
        registered_workflow_ids=frozenset({"workflow_a/1"}),
    )
    result = router.select(
        _Request(requested_strategy=StrategyMode.WORKFLOW, workflow_id="workflow_a/1")
    )

    assert result.mode is StrategyMode.WORKFLOW
    assert result.reason_code == "explicit_workflow"


@pytest.mark.parametrize(
    ("requested", "workflow_id", "code"),
    [
        (StrategyMode.DIRECT, "workflow_a/1", "STRATEGY_INPUT_CONFLICT"),
        (StrategyMode.WORKFLOW, None, "STRATEGY_INPUT_CONFLICT"),
        (StrategyMode.WORKFLOW, "unknown/1", "WORKFLOW_NOT_REGISTERED"),
        (StrategyMode.REACT, None, "STRATEGY_NOT_AVAILABLE_IN_S2"),
        (StrategyMode.PLAN_EXECUTE, None, "STRATEGY_NOT_AVAILABLE_IN_S2"),
        (StrategyMode.MULTI_AGENT, None, "STRATEGY_NOT_AVAILABLE_IN_S2"),
    ],
)
def test_invalid_or_unavailable_strategy_fails_closed(
    requested: StrategyMode,
    workflow_id: str | None,
    code: str,
) -> None:
    from efficiency_platform_agent.routing.strategy_router import (
        StrategyRouter,
        StrategyRoutingError,
    )

    router = StrategyRouter(
        frozenset({StrategyMode.DIRECT, StrategyMode.WORKFLOW}),
        registered_workflow_ids=frozenset({"workflow_a/1"}),
    )
    with pytest.raises(StrategyRoutingError) as captured:
        router.select(_Request(requested_strategy=requested, workflow_id=workflow_id))

    assert captured.value.code == code


def test_registered_future_multi_agent_is_returned_without_execution() -> None:
    from efficiency_platform_agent.routing.strategy_router import StrategyRouter

    result = StrategyRouter(
        frozenset(
            {StrategyMode.DIRECT, StrategyMode.WORKFLOW, StrategyMode.MULTI_AGENT}
        )
    ).select(_Request(requested_strategy=StrategyMode.MULTI_AGENT))

    assert result.mode is StrategyMode.MULTI_AGENT
    assert result.reason_code == "registered_requested_strategy"


def test_same_input_is_stable() -> None:
    from efficiency_platform_agent.routing.strategy_router import StrategyRouter

    router = StrategyRouter(frozenset({StrategyMode.DIRECT, StrategyMode.WORKFLOW}))
    request = _Request()

    assert router.select(request) == router.select(request)
