"""X05 单租户真实灰度停止控制器测试。"""

from __future__ import annotations

import pytest

from efficiency_platform_agent.evaluation.live_canary_v2 import (
    CanaryDispatchStopped,
    CanaryObservation,
    CanaryStopController,
)


def _observation(**overrides: object) -> CanaryObservation:
    values: dict[str, object] = {
        "request_id": "canary-1",
        "case_id": "yesterday_ai",
        "status": "PASS",
        "real_model_verified": True,
        "real_source_verified": True,
        "citation_coverage": 1.0,
        "source_policy_violations": (),
        "budget_overspent": False,
    }
    values.update(overrides)
    return CanaryObservation(**values)  # type: ignore[arg-type]


def test_clean_observations_do_not_stop_canary() -> None:
    controller = CanaryStopController()

    controller.before_dispatch()
    controller.observe(_observation())

    assert controller.stopped is False
    assert controller.stop_reasons == ()
    assert controller.accepted_count == 1


@pytest.mark.parametrize(
    ("overrides", "reason"),
    [
        ({"real_model_verified": False}, "MODEL_NOT_VERIFIED"),
        ({"real_source_verified": False}, "SOURCE_NOT_VERIFIED"),
        ({"citation_coverage": 0.5}, "CITATION_COVERAGE_BELOW_ONE"),
        ({"source_policy_violations": ("paid.example",)}, "SOURCE_POLICY_VIOLATION"),
        ({"budget_overspent": True}, "BUDGET_OVERSPENT"),
    ],
)
def test_hard_failure_stops_further_dispatch(
    overrides: dict[str, object], reason: str
) -> None:
    controller = CanaryStopController()

    controller.observe(_observation(**overrides))

    assert controller.stopped is True
    assert reason in controller.stop_reasons
    with pytest.raises(CanaryDispatchStopped, match="CANARY_HARD_STOP"):
        controller.before_dispatch()


def test_ordinary_chat_does_not_require_sources() -> None:
    controller = CanaryStopController()

    controller.observe(
        _observation(
            case_id="ordinary_chat",
            real_source_verified=False,
            citation_coverage=1.0,
        )
    )

    assert controller.stopped is False
