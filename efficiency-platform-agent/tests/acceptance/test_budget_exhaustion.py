"""验证各预算维度在执行前后失败关闭。"""

from __future__ import annotations

import pytest
from support.runtime_fakes import build_budget_service


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "dimension",
    [
        "iteration",
        "tool_call",
        "input_token",
        "output_token",
        "cost",
        "absolute_timeout",
    ],
)
async def test_budget_exhaustion_is_terminal_and_has_no_follow_up_call(
    dimension: str,
) -> None:
    """预算耗尽统一返回安全错误且不再启动后继调用。"""
    service = build_budget_service(exhaust_dimension=dimension)
    request = service.make_create_request(requested_strategy="direct")

    result = await service.create_and_execute(request)

    assert result.status.value in {"failed", "timed_out"}
    assert result.failure.code == "BUDGET_EXHAUSTED"
    assert service.calls_after_exhaustion(result.run_id) == 0
