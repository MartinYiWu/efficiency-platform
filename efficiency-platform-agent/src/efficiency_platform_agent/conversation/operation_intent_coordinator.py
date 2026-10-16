"""统一 IntentPlanV1 到现有会话执行入口的兼容投影。"""

from __future__ import annotations

import asyncio

from efficiency_platform_agent.contracts.conversation import ConversationMessageV1
from efficiency_platform_agent.contracts.intent import (
    IntentEnvelopeV1,
    IntentRequirementsV1,
)
from efficiency_platform_agent.contracts.operation_intent import IntentPlanV1
from efficiency_platform_agent.core.budget import BudgetCharge
from efficiency_platform_agent.harness.intent_v2_delegate import (
    IntentV2ConversationDecision,
)
from efficiency_platform_agent.harness.service import RunPipelineContext
from efficiency_platform_agent.orchestration.intent_v2.interpreter import (
    OperationIntentPlanningAgent,
)


class OperationIntentPlanningCoordinator:
    """保证每条新消息先经过统一意图与任务规划 Agent。"""

    def __init__(self, planner: OperationIntentPlanningAgent) -> None:
        self._planner = planner
        self._history: dict[tuple[str, str], tuple[str, ...]] = {}
        self._lock = asyncio.Lock()

    async def prepare(
        self,
        pipeline: RunPipelineContext,
        tenant_id: str,
        conversation_id: str,
        message: ConversationMessageV1,
    ) -> IntentV2ConversationDecision:
        key = (tenant_id, conversation_id)
        async with self._lock:
            history = self._history.get(key, ())
        execution = await self._planner.execute(
            run_id=pipeline.run_id,
            user_text=message.message,
            visible_history=history,
            remaining_budget=pipeline.remaining_budget,
        )
        async with self._lock:
            self._history[key] = (*history, message.message)[-128:]
        return IntentV2ConversationDecision(
            intent=_project_intent(execution.plan),
            usage=execution.usage,
            charge=BudgetCharge(
                iterations=max(1, execution.provider_calls),
                input_tokens=execution.usage.input_tokens,
                output_tokens=execution.usage.output_tokens,
                cost_microunits=execution.usage.cost_microunits,
            ),
            clarification_question=execution.plan.clarification_question,
        )


def _project_intent(plan: IntentPlanV1) -> IntentEnvelopeV1:
    if plan.route_kind == "general_chat":
        return IntentEnvelopeV1(
            domain="conversation",
            goal=plan.user_goal,
            task_type="general_chat",
            confidence=plan.confidence,
        )
    requirements = plan.requirements
    scenario = plan.primary_scenario
    assert scenario is not None
    projected = IntentRequirementsV1(
        topic=requirements.topic,
        time_window=requirements.date_range,
        platforms=requirements.platforms,
        brand=requirements.brand,
        product=requirements.product,
        goal=plan.user_goal if scenario == "brand_operation_plan" else None,
        planning_window=(
            requirements.date_range if scenario == "brand_operation_plan" else None
        ),
        ip=requirements.ip_name,
        audience=requirements.target_audience,
        incubation_window=(
            requirements.date_range if scenario == "ip_operation_plan" else None
        ),
        campaign_goal=requirements.campaign_goal,
        campaign_window=(
            requirements.date_range if scenario == "campaign_plan" else None
        ),
        topic_scope=(
            requirements.topic if scenario == "content_calendar" else None
        ),
        calendar_window=(
            requirements.date_range if scenario == "content_calendar" else None
        ),
        growth_goal=requirements.growth_goal,
        funnel_stage=requirements.funnel_stage,
        experiment_window=(
            requirements.date_range if scenario == "growth_experiment" else None
        ),
        review_window=(
            requirements.date_range if scenario == "operation_review" else None
        ),
        metric_definition=requirements.metric_definition,
    )
    capability_ids = {item.capability_id for item in plan.planned_capabilities}
    return IntentEnvelopeV1(
        domain="operations",
        goal=plan.user_goal,
        task_type=scenario,
        channels=list(requirements.platforms),
        audience=requirements.target_audience,
        time_range=requirements.date_range,
        needs_research="research" in capability_ids
        or scenario == "industry_digest",
        needs_multi_agent=True,
        missing_fields=list(plan.required_missing_fields),
        needs_clarification=plan.next_step == "clarify",
        confidence=plan.confidence,
        requirements=projected,
    )


__all__ = ["OperationIntentPlanningCoordinator"]
