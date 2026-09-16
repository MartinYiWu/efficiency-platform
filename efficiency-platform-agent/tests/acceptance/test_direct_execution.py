"""验证 Direct 通过统一 Harness 执行的端到端边界。"""

from __future__ import annotations

import pytest
from support.runtime_fakes import build_success_service


@pytest.mark.asyncio
async def test_direct_execution_uses_one_run_and_succeeds() -> None:
    """Direct 应在同一 Run 内完成，并留下模型、Checkpoint 与事件事实。"""
    service = build_success_service()
    request = service.make_create_request(requested_strategy="direct")

    result = await service.create_and_execute(request)

    assert result.status.value == "succeeded"
    assert result.run_id
    events = await service.list_events(result.run_id, request.tenant_id)
    assert events[-1].event_type == "run_succeeded"
    assert any(event.event_type == "checkpoint_saved" for event in events)
