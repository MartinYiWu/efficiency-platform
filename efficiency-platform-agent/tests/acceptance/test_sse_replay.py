"""验证事件游标续读不会重复已确认事件。"""

from __future__ import annotations

import pytest
from support.runtime_fakes import build_success_service


@pytest.mark.asyncio
async def test_sse_replay_cursor_is_monotonic() -> None:
    """从最后一个 sequence 续读时不得重复旧事件。"""
    service = build_success_service()
    request = service.make_create_request(requested_strategy="direct")
    result = await service.create_and_execute(request)
    events = await service.list_events(result.run_id, request.tenant_id)

    replay = await service.list_events(
        result.run_id, request.tenant_id, after_sequence=events[1].sequence
    )

    assert replay
    assert all(event.sequence > events[1].sequence for event in replay)
