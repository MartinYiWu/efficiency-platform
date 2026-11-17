"""只消费可信登记簿的 checkpoint 整组删除适配。"""

from efficiency_platform_agent.core.checkpoint_erasure import (
    ThreadCheckpointStore,
    ThreadErasurePlan,
    ThreadErasureRegistry,
    ThreadErasureResult,
)
from efficiency_platform_agent.core.memory import ExecutionScope, SourceDependency


class CheckpointEraser:
    def __init__(
        self,
        registry: ThreadErasureRegistry,
        stores: tuple[ThreadCheckpointStore, ...],
    ) -> None:
        self._registry, self._stores = registry, stores

    async def erase(
        self, scope: ExecutionScope, source: SourceDependency
    ) -> ThreadErasureResult:
        plan = await self._registry.block_for_erasure(scope, source)
        if plan is None or plan.scope != scope:
            raise PermissionError("ERASURE_SCOPE_DENIED")
        backend_ids = tuple(store.backend_id for store in self._stores)
        if (
            not plan.registry_complete
            or not plan.unique_owner
            or not plan.write_fenced
            or plan.gate_state not in {"BLOCKED", "REVOKED"}
            or not plan.operation_id
            or type(plan.execution_revision) is not int
            or plan.execution_revision < 0
            or not backend_ids
            or len(set(backend_ids)) != len(backend_ids)
            or frozenset(backend_ids) != plan.backend_ids
            or not _complete_tree(plan)
            or source
            not in {
                dependency
                for thread in plan.threads
                for dependency in thread.safety_dependencies
            }
        ):
            return ThreadErasureResult(
                "DELETE_PENDING", plan, error_code="ERASURE_PROOF_INCOMPLETE"
            )
        verification = []
        try:
            for store in self._stores:
                for thread in plan.threads:
                    await store.delete_thread(
                        thread.thread_id,
                        scope.conversation.tenant_id,
                        authorization=plan,
                    )
            for store in self._stores:
                for thread in plan.threads:
                    residue = await store.remaining(
                        thread.thread_id,
                        scope.conversation.tenant_id,
                        authorization=plan,
                    )
                    verification.append((store.backend_id, thread.thread_id, residue))
            verified = tuple(verification)
            if any(not residue.empty for _, _, residue in verified):
                return ThreadErasureResult(
                    "DELETE_PENDING", plan, verified, "CHECKPOINT_RESIDUE"
                )
            if not await self._registry.mark_deleted(plan, verified):
                return ThreadErasureResult(
                    "DELETE_PENDING", plan, verified, "ERASURE_REVISION_CONFLICT"
                )
            return ThreadErasureResult("DELETED", plan, verified)
        except Exception:  # noqa: BLE001 - 清理失败保持已持久化门禁，不暴露驱动错误
            return ThreadErasureResult(
                "DELETE_PENDING", plan, tuple(verification), "CHECKPOINT_ERASURE_FAILED"
            )


def _complete_tree(plan: ThreadErasurePlan) -> bool:
    parents = {thread.thread_id: thread.parent_thread_id for thread in plan.threads}
    if (
        len(parents) != len(plan.threads)
        or not all(parents)
        or plan.root_thread_id not in parents
        or parents[plan.root_thread_id] is not None
    ):
        return False
    for thread_id in parents:
        seen: set[str] = set()
        current: str | None = thread_id
        while current != plan.root_thread_id:
            if current is None or current not in parents or current in seen:
                return False
            seen.add(current)
            current = parents[current]
    return True
