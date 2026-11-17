"""持久恢复门禁及最后Provider边界；不创建第二执行框架。"""

from efficiency_platform_agent.core.memory_thread import (
    MemoryThreadRegistry,
    ResumeRequest,
)
from efficiency_platform_agent.core.ports import StreamingModelProvider
from efficiency_platform_agent.core.run_context_binding import current_run_context


class MemoryContextGate:
    def __init__(self, registry: MemoryThreadRegistry):
        self.registry = registry

    async def before_load(self, runtime_id: str, tenant_id: str):
        await self.registry.check_runtime(runtime_id, tenant_id)

    async def resume(self, runtime_id: str, tenant_id: str, request: ResumeRequest):
        return await self.registry.resume(runtime_id, tenant_id, request)


class FencedModelProvider:
    """仅显式登记Graph装配；Direct/HR若未登记，启用时安全拒绝。"""

    def __new__(cls, provider, registry: MemoryThreadRegistry, backend_id: str):
        if cls is FencedModelProvider and isinstance(provider, StreamingModelProvider):
            return object.__new__(FencedStreamingModelProvider)
        return object.__new__(cls)

    def __init__(self, provider, registry: MemoryThreadRegistry, backend_id: str):
        self._provider, self._registry, self._backend_id = (
            provider,
            registry,
            backend_id,
        )
        self.descriptor = provider.descriptor

    def _guard(self):
        binding = current_run_context()
        if binding is None or binding.memory_context is None:
            raise PermissionError("MEMORY_EXECUTION_OWNER_REQUIRED")
        return self._registry.guard_execution(
            binding.conversation.tenant_id,
            binding.execution_id,
            self._backend_id,
            "provider",
        )

    async def complete(self, request):
        async with self._guard():
            return await self._provider.complete(request)


class FencedStreamingModelProvider(FencedModelProvider):
    """仅底层真实支持stream时声明流式能力，关闭迭代器后才释放门禁。"""

    async def stream(self, request):
        async with self._guard():
            iterator = self._provider.stream(request)
            try:
                async for event in iterator:
                    yield event
            finally:
                close = getattr(iterator, "aclose", None)
                if close is not None:
                    await close()
