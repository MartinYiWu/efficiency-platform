"""验证等待、同 Run 恢复和协作取消边界。"""

from __future__ import annotations

import pytest
from support.runtime_fakes import build_suspendable_service


@pytest.mark.asyncio
async def test_wait_resume_and_running_cancel_reuse_run_checkpoint() -> None:
    """恢复沿原 Checkpoint 继续，取消可唤醒正在等待的调用。"""
    service = build_suspendable_service()
    request = service.make_create_request(requested_strategy="direct")

    waiting = await service.create_and_execute(request)
    assert waiting.status.value == "waiting_input"
    checkpoint_id = waiting.checkpoint_id

    resumed = await service.resume_run(
        waiting.run_id,
        service.make_resume_request(request.tenant_id, checkpoint_id),
    )
    assert resumed.run_id == waiting.run_id
    assert resumed.checkpoint_id == checkpoint_id
    assert resumed.budget_deadline == waiting.budget_deadline

    cancelled = await service.cancel_run(
        resumed.run_id, service.make_cancel_request(request.tenant_id)
    )
    assert cancelled.status.value == "cancelled"
