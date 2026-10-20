import json

import pytest

from efficiency_platform_agent.agents.operation.specialists.scenario_model_executor import (
    ScenarioModelExecutor,
)
from efficiency_platform_agent.core.model import ModelExecutionResult
from efficiency_platform_agent.core.run import (
    ProviderMessage,
    ProviderResult,
    ProviderUsage,
)
from efficiency_platform_agent.core.runtime import UsageSnapshot
from efficiency_platform_agent.prompts.contracts import (
    AssembledPrompt,
    ModelPolicy,
    OutputContract,
    PromptMessage,
)


class _Assembler:
    def __init__(self) -> None:
        self.calls = []

    async def assemble(self, **kwargs):
        self.calls.append(kwargs)
        return AssembledPrompt(
            "brand.plan",
            "1.0.0",
            (
                PromptMessage("system", "s"),
                PromptMessage("developer", "d"),
                PromptMessage("user", "u"),
            ),
            ModelPolicy(1, "p", "1.0.0", "deepseek", "deepseek-chat", 0.2, None, 8000, 4000, 1000, 60000, 0, 0, "d" * 64),
            OutputContract(1, "brand-plan", "1.0.0", {"type": "object"}, "fields", "a" * 64),
            "b" * 64,
            "c" * 64,
        )


class _Model:
    def __init__(self, outputs: list[str]) -> None:
        self.outputs = outputs
        self.requests = []
        self.executions = []

    async def complete(self, demand, request, *, remaining_budget):
        self.requests.append(request)
        execution = ModelExecutionResult(
            ProviderResult(
                "model-result/1", ProviderMessage("assistant", self.outputs.pop(0)), ProviderUsage(0, 0, 0, 0, 0)
            ),
            (),
            UsageSnapshot(),
            False,
        )
        self.executions.append(execution)
        return execution


def _brand_payload() -> dict:
    metric = {
        "name": "内容互动率",
        "definition": "互动数/曝光数",
        "observation_period": "每周",
        "purpose": "判断内容有效性",
    }
    return {
        "kind": "brand_plan",
        "current_context": ["处于冷启动阶段"],
        "objectives": ["建立品牌认知"],
        "positioning": "面向运营团队的效率助手",
        "audience_segments": [{"name": "运营负责人"}],
        "value_proposition": ["减少重复工作"],
        "content_pillars": [{"name": "实战方法"}],
        "channel_strategy": [{"channel": "公众号"}],
        "roadmap": [{"phase": "验证"}],
        "metric_framework": [metric],
        "risks": ["样本不足"],
        "next_actions": ["访谈 5 位用户"],
    }


@pytest.mark.asyncio
async def test_scenario_executor_uses_dedicated_database_prompt() -> None:
    assembler = _Assembler()
    model = _Model([json.dumps(_brand_payload(), ensure_ascii=False)])
    executor = ScenarioModelExecutor(model, assembler)

    generation = await executor.generate_with_usage(
        run_id="run-1",
        scenario="brand_operation_plan",
        stage="plan",
        platform=None,
        user_request="为效率产品做品牌运营方案",
        input_artifact_ids=(),
        evidence=None,
    )

    result = generation.deliverable
    assert assembler.calls[0]["prompt_key"] == "brand.plan"
    assert result.contract_version == "deliverable/3"
    assert result.content.kind == "brand_plan"
    assert result.title == "品牌运营方案"
    assert generation.executions == tuple(model.executions)
    assert [message.role for message in model.requests[0].messages] == [
        "system",
        "developer",
        "user",
    ]


@pytest.mark.asyncio
async def test_scenario_executor_repairs_once_with_exact_validation_errors() -> None:
    assembler = _Assembler()
    model = _Model(["{}", json.dumps(_brand_payload(), ensure_ascii=False)])
    executor = ScenarioModelExecutor(model, assembler)

    await executor.generate(
        run_id="run-2",
        scenario="brand_operation_plan",
        stage="plan",
        platform=None,
        user_request="品牌方案",
        input_artifact_ids=(),
        evidence=None,
    )

    assert [call["prompt_key"] for call in assembler.calls] == [
        "brand.plan",
        "brand.repair",
    ]
    repair_values = assembler.calls[1]["variables"]
    assert repair_values["previous_output"].source == "artifact"
    assert repair_values["validation_errors"].source == "system_context"
    assert len(model.requests) == 2


@pytest.mark.asyncio
async def test_industry_digest_ignores_internal_research_platform_for_prompt_route() -> None:
    assembler = _Assembler()
    executor = ScenarioModelExecutor(_Model([]), assembler)

    await executor._assemble(
        run_id="run-research",
        scenario="industry_digest",
        stage="compose",
        platform="research",
        user_request="收集今天的 AI 热点",
        context={},
    )

    assert assembler.calls[0]["prompt_key"] == "industry_digest.compose"


@pytest.mark.asyncio
async def test_industry_digest_uses_authoritative_research_window() -> None:
    assembler = _Assembler()
    output = {
        "kind": "ranked_digest",
        "topic": "AI 行业热点",
        "time_window": "最近7天",
        "items": [
            {
                "rank": 1,
                "title": "事件",
                "event_summary": "事实",
                "why_it_matters": "影响",
                "operator_insight": "观察",
                "occurred_at": None,
            }
        ],
        "actual_count": 1,
    }
    model = _Model([json.dumps(output, ensure_ascii=False)])
    executor = ScenarioModelExecutor(model, assembler)
    constraints = {
        "start": "2026-10-05T03:00:00+00:00",
        "end": "2026-10-19T03:00:00+00:00",
        "timezone": "Asia/Shanghai",
        "boundary": "left_closed_right_open",
        "original_text": "近2周",
    }

    result = await executor.generate(
        run_id="run-research-window",
        scenario="industry_digest",
        stage="compose",
        platform=None,
        user_request="收集近2周 AI 热点",
        input_artifact_ids=(),
        evidence={"research_constraints": constraints},
    )

    assert result.content.time_window == (
        "2026-10-05T03:00:00+00:00 至 2026-10-19T03:00:00+00:00"
        "（左闭右开，近2周）"
    )
    assembled_context = assembler.calls[0]["variables"]["context_payload"].value
    assert assembled_context["evidence"]["research_constraints"] == constraints
