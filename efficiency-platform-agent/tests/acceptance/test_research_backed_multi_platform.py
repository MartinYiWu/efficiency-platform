"""受控混合模式下研究前置和多平台证据复用验收。"""

from __future__ import annotations

from dataclasses import replace

import pytest

from efficiency_platform_agent.capabilities.model.runtime import ModelRuntime
from efficiency_platform_agent.core.runtime import UsageSnapshot
from efficiency_platform_agent.harness.operation_agent_factory import (
    build_operation_agent,
)
from efficiency_platform_agent.providers.llm.registry import ModelProviderRegistry
from tests.integration.test_operation_agent_runtime import (
    ContentProvider,
    ResearchProvider,
    Selector,
    submission,
)


def _build_agent(content: ContentProvider, research: ResearchProvider):
    """构造带研究端口的离线 Agent，避免测试访问外部服务。"""

    registry = ModelProviderRegistry()
    registry.register("offline", content)
    return build_operation_agent(
        ModelRuntime(Selector(), registry),
        research_provider=research,
        deliverable_set_contract_version="deliverable-set/1",
    )


def _research_submission():
    """复制固定多平台请求，并显式打开研究前置标记。"""

    source = submission()
    return replace(
        source,
        task_spec=replace(source.task_spec, requires_research=True),
    )


@pytest.mark.asyncio
async def test_research_precedes_parallel_platform_generation_and_reuses_one_pack():
    """研究只调用一次，三个平台均收到同一组证据来源。"""

    content = ContentProvider()
    research = ResearchProvider()

    agent = _build_agent(content, research)
    execution = await agent.execute(_research_submission())
    result = execution.deliverables
    assert result is not None

    assert len(research.calls) == 1
    assert len(content.calls) == 3
    citation_sets = {
        tuple(item["url"] for item in call["citations"]) for call in content.calls
    }
    assert citation_sets == {("https://example.com/source",)}
    assert all(call["research"] is True for call in content.calls)
    assert {item.platform for item in result.deliverables} == {
        "xiaohongshu",
        "wechat_official_account",
        "toutiao",
    }
    assert all(
        item.kind.value == "copy"
        for item in execution.scenario_result.deliverable_bundle.deliverables
    )


@pytest.mark.asyncio
async def test_research_failure_closes_before_any_platform_generation():
    """研究失败必须关闭，不能生成无来源的平台成品。"""

    class FailedResearch(ResearchProvider):
        async def research(self, request):
            result = await super().research(request)
            from efficiency_platform_agent.capabilities.research.contracts import (
                ResearchResult,
                ResearchStatus,
            )

            return ResearchResult(
                "research-result/1",
                result.request_id,
                result.task_id,
                result.tenant_id,
                ResearchStatus.FAILED,
                (),
                ("研究服务不可用",),
                "RESEARCH_UNAVAILABLE",
            )

    content = ContentProvider()
    research = FailedResearch()

    with pytest.raises(ValueError, match="RESEARCH_UNAVAILABLE"):
        await _build_agent(content, research).handle(_research_submission())

    assert len(research.calls) == 1
    assert content.calls == []


@pytest.mark.asyncio
async def test_without_research_requirement_does_not_call_research_provider():
    """普通多平台请求保持离线行为，不因接入研究 Provider 而额外联网。"""

    content = ContentProvider()
    research = ResearchProvider()

    result = await _build_agent(content, research).handle(submission())

    assert len(research.calls) == 0
    assert len(result.deliverables) == 3


@pytest.mark.asyncio
async def test_research_usage_is_recorded_in_operation_execution():
    """研究阶段的 Provider 用量必须进入当前 Run 账本。"""

    class BilledResearch(ResearchProvider):
        async def research(self, request):
            return replace(
                await super().research(request),
                usage=UsageSnapshot(11, 7, 2),
            )

    content = ContentProvider()
    execution = await _build_agent(content, BilledResearch()).execute(
        _research_submission()
    )

    assert execution.usage.input_tokens == 41
    assert execution.usage.output_tokens == 67
    assert execution.usage.cost_microunits == 2


@pytest.mark.asyncio
async def test_large_server_side_search_usage_does_not_block_content_generation():
    """服务端搜索工具链用量很大时，仍应保留内容生成阶段。"""

    class LargeSearchUsage(ResearchProvider):
        async def research(self, request):
            return replace(
                await super().research(request),
                usage=UsageSnapshot(300_000, 11_267, 0, True),
            )

    content = ContentProvider()
    execution = await _build_agent(content, LargeSearchUsage()).execute(
        _research_submission()
    )

    assert execution.deliverables is not None
    assert len(content.calls) == 3
