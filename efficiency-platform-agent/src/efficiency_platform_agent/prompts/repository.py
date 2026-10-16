"""数据库 Prompt 资产的持久化端口与稳定错误。"""

from __future__ import annotations

from typing import Protocol, runtime_checkable

from .contracts import PromptBundle, RunPromptSnapshot


class PromptConfigurationError(ValueError):
    """阻止模型调用的 Prompt 配置错误。"""

    def __init__(self, code: str, detail: str = "") -> None:
        self.code = code
        super().__init__(f"{code}: {detail}" if detail else code)


@runtime_checkable
class PromptRepository(Protocol):
    async def resolve(self, prompt_key: str, environment: str) -> PromptBundle: ...

    async def load_snapshot(
        self, run_id: str, stage: str
    ) -> PromptBundle | None: ...

    async def save_snapshot(self, snapshot: RunPromptSnapshot) -> None: ...


__all__ = ["PromptConfigurationError", "PromptRepository"]
