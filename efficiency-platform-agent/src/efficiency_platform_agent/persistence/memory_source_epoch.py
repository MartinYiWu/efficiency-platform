"""仅读D13本机execution级事件权威；不推断source在其他execution中的状态。"""

from sqlalchemy import text
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.ext.asyncio import AsyncEngine

from efficiency_platform_agent.core.memory import ExecutionScope, SourceDependency
from efficiency_platform_agent.core.memory_execution import (
    MemoryExecutionRecord,
    MemoryExecutionStore,
)


class MySqlExecutionSourceEpochAuthority:
    def __init__(self, engine: AsyncEngine, execution_store: MemoryExecutionStore):
        self.engine, self.execution_store = engine, execution_store

    async def _metadata(self, scope: ExecutionScope, event_id: str | None = None):
        params = {
            "tenant": scope.conversation.tenant_id.encode(),
            "execution": scope.execution_id.encode(),
        }
        try:
            async with self.engine.connect() as connection:
                row = (
                    (
                        await connection.execute(
                            text(
                                "SELECT state,execution_revision,runtime_id,grant_epoch,source_epoch,deletion_epoch "
                                "FROM agent_memory_execution WHERE tenant_id=:tenant AND execution_id=:execution"
                            ),
                            params,
                        )
                    )
                    .mappings()
                    .first()
                )
                if row is None or event_id is None:
                    return row
                receipt = (
                    (
                        await connection.execute(
                            text(
                                "SELECT execution_id FROM agent_memory_invalidation_receipt "
                                "WHERE tenant_id=:tenant AND execution_id=:execution AND event_id=:event"
                            ),
                            params | {"event": event_id.encode()},
                        )
                    )
                    .mappings()
                    .first()
                )
                return (
                    row
                    if receipt is not None
                    and bytes(receipt["execution_id"]).decode() == scope.execution_id
                    else None
                )
        except SQLAlchemyError:
            raise ValueError("MEMORY_AUTHORITY_UNAVAILABLE") from None

    @staticmethod
    def _bound(
        scope: ExecutionScope,
        dependencies: tuple[SourceDependency, ...],
        record: MemoryExecutionRecord | None,
    ) -> bool:
        if record is None:
            return False
        packet = record.context.packet
        return bool(
            dependencies
            and (packet.scope, packet.task_id, packet.execution_id)
            == (scope.conversation, scope.task_id, scope.execution_id)
            and set(dependencies).issubset(packet.safety_dependencies)
            and any(
                (grant.node_id, grant.execution_agent_id, grant.purpose)
                == (scope.subtask_id, scope.execution_agent_id, scope.purpose)
                for grant in record.context.execution_grants
            )
        )

    @staticmethod
    def _consistent(row, record: MemoryExecutionRecord) -> bool:
        return bool(
            row["state"] == record.state
            and row["execution_revision"]
            == record.execution_revision
            == record.context.packet.execution_revision
            and bytes(row["runtime_id"]).decode() == record.runtime_id
            and (row["grant_epoch"], row["source_epoch"], row["deletion_epoch"])
            == (record.grant_epoch, record.source_epoch, record.deletion_epoch)
        )

    async def current(
        self, scope: ExecutionScope, dependencies: tuple[SourceDependency, ...]
    ) -> bool:
        row = await self._metadata(scope)
        if row is None or row["state"] != "ACTIVE":
            return False
        record = await self.execution_store.get(
            scope.conversation.tenant_id, scope.execution_id
        )
        if (
            not self._bound(scope, dependencies, record)
            or record is None
            or not self._consistent(row, record)
        ):
            return False
        packet = record.context.packet
        return (record.grant_epoch, record.source_epoch, record.deletion_epoch) == (
            packet.grant_epoch,
            packet.source_epoch,
            packet.deletion_epoch,
        )

    async def revoked(
        self, scope: ExecutionScope, source: SourceDependency, event_id: str
    ) -> bool:
        row = await self._metadata(scope, event_id)
        if row is None or row["state"] != "REVOKED":
            return False
        record = await self.execution_store.get(
            scope.conversation.tenant_id, scope.execution_id
        )
        if (
            not self._bound(scope, (source,), record)
            or record is None
            or not self._consistent(row, record)
        ):
            return False
        packet = record.context.packet
        original = (packet.grant_epoch, packet.source_epoch, packet.deletion_epoch)
        current = (record.grant_epoch, record.source_epoch, record.deletion_epoch)
        return all(
            new >= old for new, old in zip(current, original, strict=True)
        ) and any(new > old for new, old in zip(current, original, strict=True))
