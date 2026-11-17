"""只读D13技术事件适配：Fake引擎只验证隔离与拒绝，不冒充真实MySQL。"""

from contextlib import asynccontextmanager
from dataclasses import replace
from types import SimpleNamespace

import pytest
from sqlalchemy.exc import SQLAlchemyError

from tests.integration.memory.test_context_refresh_resume import (
    SyntheticD13Store,
    synthetic_record,
)


class FakeReadEngine:
    def __init__(self, record):
        self.record = record
        self.has_receipt = False
        self.fail = False

    @asynccontextmanager
    async def connect(self):
        yield self

    async def execute(self, statement, params):
        if self.fail:
            raise SQLAlchemyError("synthetic-private-driver-detail")
        record = self.record
        packet = record.context.packet
        row = None
        if (params["tenant"], params["execution"]) == (
            packet.scope.tenant_id.encode(),
            packet.execution_id.encode(),
        ):
            if "agent_memory_invalidation_receipt" in str(statement):
                if self.has_receipt and params["event"] == b"synthetic-revoke":
                    row = {"execution_id": packet.execution_id.encode()}
            else:
                row = {
                    "state": record.state,
                    "execution_revision": record.execution_revision,
                    "grant_epoch": record.grant_epoch,
                    "source_epoch": record.source_epoch,
                    "deletion_epoch": record.deletion_epoch,
                    "runtime_id": record.runtime_id.encode(),
                }
        return SimpleNamespace(mappings=lambda: SimpleNamespace(first=lambda: row))


async def test_local_d13_current_and_exact_revocation_receipt_required():
    from efficiency_platform_agent.persistence.memory_source_epoch import (
        MySqlExecutionSourceEpochAuthority,
    )

    scope, record = synthetic_record()
    engine, store = FakeReadEngine(record), SyntheticD13Store(record)
    authority = MySqlExecutionSourceEpochAuthority(engine, store)
    deps = record.context.packet.safety_dependencies
    assert await authority.current(scope, deps)
    assert not await authority.current(replace(scope, purpose="other"), deps)
    assert not await authority.revoked(scope, deps[0], "synthetic-revoke")
    engine.record = store.record = replace(record, state="REVOKED", source_epoch=1)
    assert not await authority.current(scope, deps)
    assert not await authority.revoked(scope, deps[0], "synthetic-revoke")
    engine.has_receipt = True
    assert await authority.revoked(scope, deps[0], "synthetic-revoke")
    assert not await authority.revoked(scope, deps[0], "wrong-event")
    assert not await authority.revoked(
        replace(scope, execution_id="other-execution"), deps[0], "synthetic-revoke"
    )
    assert not await authority.revoked(
        scope, replace(deps[0], source_version="other"), "synthetic-revoke"
    )
    engine.record = store.record = replace(record, state="REVOKED")
    assert not await authority.revoked(scope, deps[0], "synthetic-revoke")


async def test_local_technical_driver_failure_does_not_imply_source_revoked():
    from efficiency_platform_agent.persistence.memory_source_epoch import (
        MySqlExecutionSourceEpochAuthority,
    )

    scope, record = synthetic_record()
    engine = FakeReadEngine(record)
    engine.fail = True
    authority = MySqlExecutionSourceEpochAuthority(engine, SyntheticD13Store(record))
    with pytest.raises(ValueError, match="MEMORY_AUTHORITY_UNAVAILABLE"):
        await authority.revoked(
            scope, record.context.packet.safety_dependencies[0], "synthetic-revoke"
        )


def test_direct_registration_uses_explicit_controlled_checkpointer():
    from langgraph.checkpoint.memory import InMemorySaver

    from efficiency_platform_agent.agents.conversation.general_agent import (
        GeneralConversationAgent,
    )
    from efficiency_platform_agent.orchestration.builders.conversation_direct import (
        build_conversation_direct_registration,
    )
    from tests.orchestration.test_conversation_direct_runtime import FakeModelRuntime

    saver = InMemorySaver()
    registration = build_conversation_direct_registration(
        GeneralConversationAgent(FakeModelRuntime()),
        lambda value: None,
        checkpointer=saver,
    )
    assert registration.builder.build()._compiled.checkpointer is saver
