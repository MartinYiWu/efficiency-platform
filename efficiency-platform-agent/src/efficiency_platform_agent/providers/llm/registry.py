"""显式注册的模型 Provider 表。"""

from __future__ import annotations

from types import MappingProxyType

from ...core.ports import ModelProvider


class ModelProviderRegistry:
    """通过显式 ID 管理 Provider，禁止重复注册和动态扫描。"""

    def __init__(self) -> None:
        self._providers: dict[str, ModelProvider] = {}

    def register(self, provider_id: str, provider: ModelProvider) -> None:
        """注册唯一 Provider ID。"""
        if not isinstance(provider_id, str) or not provider_id.strip():
            raise ValueError("provider_id 必须是非空字符串")
        if not isinstance(provider, ModelProvider):
            raise TypeError("provider 必须实现 ModelProvider")
        if provider_id in self._providers:
            raise ValueError(f"Provider ID 已注册: {provider_id}")
        self._providers[provider_id] = provider

    def get(self, provider_id: str) -> ModelProvider:
        """按显式 ID 取得 Provider。"""
        try:
            return self._providers[provider_id]
        except KeyError as exc:
            raise KeyError(f"未知 Provider ID: {provider_id}") from exc

    @property
    def providers(self) -> MappingProxyType[str, ModelProvider]:
        """返回只读 Provider 映射，便于组合根检查。"""
        return MappingProxyType(self._providers)
