"""验证模型临时失败时的受控一次降级。"""

from __future__ import annotations

import pytest
from support.runtime_fakes import build_degradation_service


@pytest.mark.asyncio
async def test_temporary_strong_failure_degrades_once_to_balanced() -> None:
    """strong 临时失败后应仅降级至 balanced 并保留降级事实。"""
    service = build_degradation_service()
    request = service.make_create_request(requested_strategy="direct")

    result = await service.create_and_execute(request)

    assert result.status.value == "succeeded"
    assert result.degraded is True
    assert service.provider_models(result.run_id) == ["strong", "balanced"]
