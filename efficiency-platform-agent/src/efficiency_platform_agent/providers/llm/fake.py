"""无外部 I/O 的确定性 Fake Model Provider。"""

from __future__ import annotations

from collections.abc import Sequence

from ...core.run import (
    ExecutionBudget,
    ExtensionDescriptor,
    ProviderError,
    ProviderRequest,
    ProviderResult,
    ProviderUsage,
)


class FakeModelProvider:
    """按内存脚本顺序返回 ProviderResult，脚本耗尽即稳定失败。"""

    def __init__(self, provider_id: str, script: Sequence[ProviderResult]) -> None:
        if not isinstance(provider_id, str) or not provider_id.strip():
            raise ValueError("provider_id 必须是非空字符串")
        if any(not isinstance(item, ProviderResult) for item in script):
            raise TypeError("script 只能包含 ProviderResult")
        self.provider_id = provider_id
        self.script: tuple[ProviderResult, ...] = tuple(script)
        self._index = 0
        self.descriptor = ExtensionDescriptor(
            name=provider_id,
            semantic_version="1.0.0",
            input_schema_version="s2.provider/1",
            output_schema_version="s2.provider/1",
            permissions=frozenset(),
            budget=ExecutionBudget(
                max_iterations=1,
                max_tool_calls=0,
                max_input_tokens=1_000_000,
                max_output_tokens=1_000_000,
                timeout_ms=60_000,
                max_cost_microunits=1_000_000_000,
            ),
            termination_conditions=frozenset({"provider_returned"}),
            checkpoint_version="s2.provider/1",
        )

    async def complete(self, request: ProviderRequest) -> ProviderResult:
        """消费一项脚本；不访问环境、文件或网络。"""
        if not isinstance(request, ProviderRequest):
            raise TypeError("request 必须是 ProviderRequest")
        if self._index >= len(self.script):
            return ProviderResult(
                contract_version=request.contract_version,
                message=None,
                usage=ProviderUsage(0, 0, 0, 0, 0),
                error=ProviderError(
                    code="FAKE_SCRIPT_EXHAUSTED",
                    category="provider",
                    retryable=False,
                    safe_message="Fake Provider 脚本已耗尽",
                ),
            )
        result = self.script[self._index]
        self._index += 1
        return result
