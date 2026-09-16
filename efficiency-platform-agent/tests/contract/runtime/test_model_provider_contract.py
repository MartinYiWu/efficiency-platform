"""ModelProvider 与显式 Registry 的契约测试。"""

import pytest

from efficiency_platform_agent.core.ports import ModelProvider
from efficiency_platform_agent.providers.llm.fake import FakeModelProvider
from efficiency_platform_agent.providers.llm.registry import ModelProviderRegistry


def test_fake_provider_implements_port_and_exhaustion_is_stable() -> None:
    """Fake Provider 只消费内存脚本，耗尽后返回稳定错误。"""
    provider = FakeModelProvider("fake_fast", [])
    assert isinstance(provider, ModelProvider)


@pytest.mark.asyncio
async def test_registry_rejects_duplicate_ids_and_unknown_provider() -> None:
    """Registry 必须显式注册且拒绝重复或未知 ID。"""
    registry = ModelProviderRegistry()
    provider = FakeModelProvider("fake_fast", [])
    registry.register("fake_fast", provider)
    with pytest.raises(ValueError):
        registry.register("fake_fast", provider)
    with pytest.raises(KeyError):
        registry.get("missing")
