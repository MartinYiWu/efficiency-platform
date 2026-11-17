"""只有原运行owner实际退出后才可擦本进程输出缓存。"""
from dataclasses import replace
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from efficiency_platform_agent.core.enums import RunStatus
from efficiency_platform_agent.core.memory_execution import MemoryExecutionRecord
from efficiency_platform_agent.harness.service import _json_object
from efficiency_platform_agent.runtime.event_hub import EventHub
from tests.integration.context_control.test_memory_execution_mysql import context
from tests.unit.harness.test_memory_run_binding import service


@pytest.mark.asyncio
async def test_owner_scrubs_hub_but_foreign_worker_cannot_ack_shared_terminal_state():
    memory = context()
    packet = memory.packet
    runtime = service()
    runtime.graph_runtime = SimpleNamespace(scrub_memory_run=lambda run: True)
    runtime.event_hub = EventHub()
    record = MemoryExecutionRecord(memory, "actual-run", "OPERATIONS", "a" * 64, memory.deadline_epoch_seconds, "REVOKED", packet.execution_revision, 1, 2, 1)
    from dataclasses import asdict
    original = SimpleNamespace(status=RunStatus.SUCCEEDED,
        request=SimpleNamespace(user_id=packet.scope.user_id, metadata=_json_object({"context_scope": asdict(packet.scope), "memory_execution": memory.metadata()})),
        budget_state=SimpleNamespace(deadline_epoch_ms=memory.deadline_epoch_seconds * 1000))
    runtime.repository = SimpleNamespace(get=AsyncMock(return_value=original))
    await runtime.event_hub.publish_next(record.runtime_id, "assistant_delta", {"text": "private-marker"})
    assert not await runtime.scrub_memory_execution(record)
    assert await runtime.event_hub.replay(record.runtime_id, 0)
    runtime._background_exits[(packet.scope.tenant_id, record.runtime_id)] = None
    assert not await runtime.scrub_memory_execution(replace(record, runtime_id="foreign-run"))
    assert await runtime.scrub_memory_execution(record)
    assert not await runtime.event_hub.replay(record.runtime_id, 0)


@pytest.mark.asyncio
async def test_conversation_scrub_clears_original_scope_body_but_keeps_fingerprint_and_other_scope():
    from efficiency_platform_agent.contracts.conversation import ConversationSubmitViewV1
    from efficiency_platform_agent.conversation.context import ConversationContext, ConversationTurn
    from efficiency_platform_agent.conversation.service import ConversationService, ConversationSubmissionStore, _ContextEntry, _IdempotencyEntry

    memory = context()
    scope = memory.packet.scope
    conversation = ConversationService(runtime=service(), interpreter=None, resolver=None, submissions=ConversationSubmissionStore())
    owned, other = ConversationContext(), ConversationContext()
    owned.append(ConversationTurn("assistant", "synthetic-forget-marker"))
    other.append(ConversationTurn("assistant", "unrelated-marker"))
    conversation._contexts[scope.history_key] = _ContextEntry(owned, 1000)
    conversation._contexts[("other",)] = _ContextEntry(other, 1000)
    view = ConversationSubmitViewV1(conversation_id=scope.session_id, turn_id="turn", run_id="run", status="queued")
    conversation._requests[(scope.tenant_id, "request")] = _IdempotencyEntry(scope.session_id, scope.user_id, "private-request-marker", view, 1000, "a" * 64)
    record = MemoryExecutionRecord(memory, "run", "OPERATIONS", "a" * 64, memory.deadline_epoch_seconds, "REVOKED", memory.packet.execution_revision, 1, 2, 1)
    assert await conversation.scrub_memory_execution(record)
    assert not owned.turns and other.turns
    retained = conversation._requests[(scope.tenant_id, "request")]
    assert retained.message == "" and retained.fingerprint == "a" * 64
