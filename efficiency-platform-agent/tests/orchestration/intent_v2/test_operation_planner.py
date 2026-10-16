"""运营助手统一意图与任务规划 Agent。"""

from __future__ import annotations

import json

import pytest

from efficiency_platform_agent.contracts.operation_intent import IntentPlanV1
from efficiency_platform_agent.core.budget import RemainingBudget
from efficiency_platform_agent.core.model import (
    ModelCandidate,
    ModelExecutionResult,
    ModelSelection,
    ModelTier,
)
from efficiency_platform_agent.core.run import (
    ProviderMessage,
    ProviderResult,
    ProviderUsage,
)
from efficiency_platform_agent.core.runtime import UsageSnapshot
from efficiency_platform_agent.orchestration.intent_v2.interpreter import (
    OperationIntentPlanningAgent,
)
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
            prompt_key=kwargs["prompt_key"],
            semantic_version="1.0.0",
            messages=(
                PromptMessage("system", "你是意图规划 Agent"),
                PromptMessage("developer", "严格返回 IntentPlanV1"),
                PromptMessage("user", "请求与上下文已经隔离"),
            ),
            model_policy=ModelPolicy(
                1,
                "intent-planning",
                "1.0.0",
                "deepseek",
                "deepseek-chat",
                0.1,
                None,
                8000,
                3000,
                5000,
                30000,
                1,
                0,
                "a" * 64,
            ),
            output_contract=OutputContract(
                1,
                "intent-plan",
                "1.0.0",
                IntentPlanV1.model_json_schema(),
                "IntentPlanV1 全部字段",
                "b" * 64,
            ),
            message_checksum="c" * 64,
            rendered_chars=60,
        )


class _ModelRuntime:
    def __init__(self, outputs: tuple[str, ...]) -> None:
        self.outputs = list(outputs)
        self.calls = []

    async def complete(self, demand, request, *, remaining_budget):
        self.calls.append((demand, request, remaining_budget))
        output = self.outputs.pop(0)
        result = ProviderResult(
            "intent-plan/1",
            ProviderMessage("assistant", output),
            ProviderUsage(10, 5, 0, 0, 0),
        )
        candidate = ModelCandidate(
            "intent",
            "fake",
            "fake-model",
            ModelTier.BALANCED,
            True,
            False,
            100_000,
            True,
            False,
        )
        return ModelExecutionResult(
            result,
            (ModelSelection(candidate, 1, None, "selected"),),
            UsageSnapshot(10, 5, 0, False),
            False,
        )


def _plan(
    scenario: str | None,
    *,
    action: str = "create",
    next_step: str = "execute",
    missing: list[str] | None = None,
    question: str | None = None,
) -> str:
    route_kind = "general_chat" if scenario is None else "operation"
    if scenario is None:
        action = "general_chat"
        next_step = "answer"
    return json.dumps(
        {
            "contract_version": "intent-plan/1",
            "route_kind": route_kind,
            "primary_scenario": scenario,
            "action_mode": action,
            "user_goal": "完成运营任务" if scenario else "回答普通问题",
            "requirements": {
                "topic": "AI 行业",
                "platforms": ["wechat"],
                "date_range": "最近7天",
                "constraints": [],
            },
            "artifact_reference": {},
            "required_missing_fields": missing or [],
            "next_step": next_step,
            "clarification_question": question,
            "planned_capabilities": (
                []
                if scenario is None or next_step == "clarify"
                else [{"capability_id": "scenario_execute", "purpose": "生成交付物"}]
            ),
            "confidence": 0.95,
        },
        ensure_ascii=False,
    )


def _budget() -> RemainingBudget:
    return RemainingBudget(3, 0, 100_000, 8_000, 1_000_000, 30_000)


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "scenario",
    [
        "industry_digest",
        "multi_platform_content",
        "brand_operation_plan",
        "ip_operation_plan",
        "campaign_plan",
        "content_calendar",
        "growth_experiment",
        "operation_review",
    ],
)
async def test_planner_accepts_all_eight_operation_scenarios(scenario: str) -> None:
    assembler = _Assembler()
    runtime = _ModelRuntime((_plan(scenario),))
    planner = OperationIntentPlanningAgent(runtime, assembler)

    plan = await planner.plan(
        run_id="run-1",
        user_text="执行运营任务",
        visible_history=("上一轮上下文",),
        remaining_budget=_budget(),
    )

    assert plan.primary_scenario == scenario
    assert plan.next_step == "execute"
    assert assembler.calls[0]["prompt_key"] == "intent.plan"
    assert [message.role for message in runtime.calls[0][1].messages] == [
        "system",
        "developer",
        "user",
    ]


@pytest.mark.asyncio
async def test_planner_repairs_invalid_output_once_and_uses_repair_prompt() -> None:
    assembler = _Assembler()
    runtime = _ModelRuntime(("{}", _plan("industry_digest")))
    planner = OperationIntentPlanningAgent(runtime, assembler)

    plan = await planner.plan(
        run_id="run-2",
        user_text="收集 AI 热点",
        visible_history=(),
        remaining_budget=_budget(),
    )

    assert plan.primary_scenario == "industry_digest"
    assert [item["prompt_key"] for item in assembler.calls] == [
        "intent.plan",
        "intent.repair",
    ]
    assert len(runtime.calls) == 2


@pytest.mark.asyncio
async def test_ambiguous_reference_returns_exactly_one_clarification_question() -> None:
    output = _plan(
        "industry_digest",
        action="revise",
        next_step="clarify",
        missing=["artifact_reference"],
        question="你说的第 3 条是本轮热点列表中的第 3 条吗？",
    )
    planner = OperationIntentPlanningAgent(_ModelRuntime((output,)), _Assembler())

    plan = await planner.plan(
        run_id="run-3",
        user_text="把第 3 条改一下",
        visible_history=(),
        remaining_budget=_budget(),
    )

    assert plan.next_step == "clarify"
    assert plan.required_missing_fields == ("artifact_reference",)
    assert plan.clarification_question.count("？") == 1
