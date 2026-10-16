"""ModelProvider 与显式 Registry 的契约测试。"""

import pytest

from efficiency_platform_agent.core.ports import ModelProvider
from efficiency_platform_agent.core.run import (
    JsonObject,
    ProviderMessage,
    ProviderToolCall,
)
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


def test_provider_message_supports_developer_and_correlated_tool_calls() -> None:
    call = ProviderToolCall(
        "call-1",
        "search_web",
        JsonObject((("query", "AI 行业动态"),)),
    )

    developer = ProviderMessage("developer", "只使用可引用事实")
    assistant = ProviderMessage("assistant", None, tool_calls=(call,))
    tool = ProviderMessage("tool", JsonObject((("items", ()),)), "call-1")

    assert developer.role == "developer"
    assert assistant.tool_calls == (call,)
    assert tool.tool_call_id == "call-1"


def test_provider_message_rejects_invalid_tool_correlation() -> None:
    call = ProviderToolCall("call-1", "search_web", JsonObject())

    with pytest.raises(ValueError, match="tool_call_id"):
        ProviderMessage("tool", "result")
    with pytest.raises(ValueError, match="duplicate"):
        ProviderMessage("assistant", None, tool_calls=(call, call))
    with pytest.raises(ValueError, match="assistant"):
        ProviderMessage("user", "request", tool_calls=(call,))
