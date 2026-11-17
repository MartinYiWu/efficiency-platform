"""已认证execution与技术thread的接合入口；不接受裸thread删除授权。"""

from efficiency_platform_agent.core.memory import ExecutionScope, SourceDependency
from efficiency_platform_agent.core.memory_thread import (
    MemoryThreadRegistry,
    ThreadCleanupReceipt,
)


class ExecutionBindingService:
    def __init__(self, registry: MemoryThreadRegistry):
        self.registry = registry

    async def enroll(self, scope: ExecutionScope, runtime_id: str) -> None:
        await self.registry.enroll(scope, runtime_id)

    async def enroll_no_checkpoint(
        self, scope: ExecutionScope, runtime_id: str
    ) -> None:
        await self.registry.enroll_no_checkpoint(scope, runtime_id)


class ThreadErasureService:
    def __init__(self, registry, eraser):
        self.registry, self.eraser = registry, eraser

    async def prepare_and_erase(
        self,
        tenant_id: str,
        execution_id: str,
        event_id: str,
        expected_execution_revision: int,
        source_dependencies: tuple[SourceDependency, ...],
    ) -> ThreadCleanupReceipt:
        try:
            prepared = await self.registry.prepare_cleanup(
                tenant_id,
                execution_id,
                event_id,
                expected_execution_revision,
                source_dependencies,
            )
            if prepared is None:
                return ThreadCleanupReceipt("DELETE_PENDING")
            scope, source, previous = prepared
            if previous is not None:
                return previous
            no_checkpoint = await self.registry.erase_if_no_checkpoint(
                scope, event_id, expected_execution_revision
            )
            if no_checkpoint is not None:
                return no_checkpoint
            result = await self.eraser.erase(scope, source)
            if result.status != "DELETED":
                return ThreadCleanupReceipt("DELETE_PENDING")
            return await self.registry.finish_cleanup(tenant_id, execution_id, event_id)
        except ValueError:
            raise
        except Exception:  # noqa: BLE001 - 回执失败不发送ACK，保留持久门禁
            return ThreadCleanupReceipt("DELETE_PENDING")
