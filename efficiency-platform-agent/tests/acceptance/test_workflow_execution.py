"""验证固定 Workflow 的最小合成执行链。"""

from __future__ import annotations

import pytest
from support.runtime_fakes import build_success_service


@pytest.mark.asyncio
async def test_workflow_execution_uses_shared_run_lifecycle() -> None:
    """Workflow 应在同一 Run 内完成两次模型和一次合成 Tool。"""
    service = build_success_service()
    request = service.make_create_request(
        requested_strategy="workflow", workflow_id="synthetic_review/1"
    )

    result = await service.create_and_execute(request)

    assert result.status.value == "succeeded"
    assert service.provider_call_count(result.run_id) == 2
    assert service.tool_call_count(result.run_id) == 1
