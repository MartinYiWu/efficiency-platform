"""统一 IntentPlanV1 到现有会话执行入口的兼容投影。"""

from __future__ import annotations

import asyncio
import logging
from dataclasses import replace
from typing import Any

from efficiency_platform_agent.contracts.conversation import ConversationMessageV1
from efficiency_platform_agent.contracts.intent import (
    IntentEnvelopeV1,
    IntentRequirementsV1,
)
from efficiency_platform_agent.contracts.operation_intent import IntentPlanV1
from efficiency_platform_agent.contracts.referenced_inputs import (
    ReferencedArtifactInput,
)
from efficiency_platform_agent.core.budget import BudgetCharge
from efficiency_platform_agent.harness.intent_v2_delegate import (
    IntentV2ConversationDecision,
)
from efficiency_platform_agent.harness.service import (
    RunPipelineContext,
    RunPipelinePreparation,
)
from efficiency_platform_agent.orchestration.intent_v2.interpreter import (
    OperationIntentPlanningAgent,
)

logger = logging.getLogger("efficiency_platform_agent.execution")


class OperationIntentPlanningCoordinator:
    """保证每条新消息先经过统一意图与任务规划 Agent。"""

    def __init__(
        self,
        planner: OperationIntentPlanningAgent,
        research_coordinator: Any | None = None,
    ) -> None:
        self._planner = planner
        self._research_coordinator = research_coordinator
        self._history: dict[tuple[str, str], tuple[str, ...]] = {}
        self._lock = asyncio.Lock()

    async def prepare(
        self,
        pipeline: RunPipelineContext,
        tenant_id: str,
        conversation_id: str,
        message: ConversationMessageV1,
    ) -> IntentV2ConversationDecision | RunPipelinePreparation:
        key = (tenant_id, conversation_id)
        async with self._lock:
            history = self._history.get(key, ())
        execution = await self._planner.execute(
            run_id=pipeline.run_id,
            user_text=message.message,
            visible_history=history,
            remaining_budget=pipeline.remaining_budget,
            available_artifacts=tuple(
                {
                    "artifact_id": item.artifact_id,
                    "root_artifact_id": item.root_artifact_id,
                    "version": item.version,
                    "artifact_type": item.artifact_type,
                    "scenario": item.scenario,
                    "platform": item.platform,
                    "title": item.title,
                }
                for item in message.artifacts
            ),
        )
        logger.info(
            "event=operation_intent_planned run_id=%s scenario=%s action=%s "
            "next_step=%s capabilities=%s artifact_resolved=%s",
            pipeline.run_id,
            execution.plan.primary_scenario or "general_chat",
            execution.plan.action_mode,
            execution.plan.next_step,
            ",".join(
                item.capability_id for item in execution.plan.planned_capabilities
            )
            or "none",
            execution.plan.artifact_reference.resolved,
        )
        async with self._lock:
            self._history[key] = (*history, message.message)[-128:]
        referenced_artifact = None
        reference = execution.plan.artifact_reference
        if reference.artifact_id is not None:
            selected = next(
                (
                    item
                    for item in message.artifacts
                    if item.artifact_id == reference.artifact_id
                    and (reference.version is None or item.version == reference.version)
                ),
                None,
            )
            if selected is not None:
                referenced_artifact = ReferencedArtifactInput(
                    tenant_id=tenant_id,
                    user_id=message.user_id,
                    conversation_id=conversation_id,
                    artifact=selected,
                )
        projected_intent = _project_intent(execution.plan)
        clarification_question = execution.plan.clarification_question
        if referenced_artifact is not None and execution.plan.next_step == "execute":
            projected_intent = _inherit_artifact_requirements(
                projected_intent,
                execution.plan,
                referenced_artifact,
            )
        if reference.artifact_id is not None and referenced_artifact is None:
            projected_intent = projected_intent.model_copy(
                update={
                    "missing_fields": ["artifact_reference"],
                    "needs_clarification": True,
                }
            )
            clarification_question = "请从当前会话已有交付物中确认需要修改的版本？"
        decision = IntentV2ConversationDecision(
            intent=projected_intent,
            usage=execution.usage,
            charge=BudgetCharge(
                iterations=max(1, execution.provider_calls),
                input_tokens=execution.usage.input_tokens,
                output_tokens=execution.usage.output_tokens,
                cost_microunits=execution.usage.cost_microunits,
            ),
            clarification_question=clarification_question,
            referenced_artifact=referenced_artifact,
        )
        if not decision.intent.needs_research or self._research_coordinator is None:
            return decision
        prepared = await self._research_coordinator.prepare(
            pipeline, tenant_id, conversation_id, message
        )
        if isinstance(prepared, RunPipelinePreparation):
            return replace(
                prepared,
                usage=_sum_usage(decision.usage, prepared.usage),
                charge=_sum_charge(decision.charge, prepared.charge),
            )
        if isinstance(prepared, IntentV2ConversationDecision):
            return IntentV2ConversationDecision(
                intent=prepared.intent,
                usage=_sum_usage(decision.usage, prepared.usage),
                charge=_sum_charge(decision.charge, prepared.charge),
                clarification_question=prepared.clarification_question,
            )
        return decision


def _sum_usage(left, right):
    return type(left)(
        input_tokens=left.input_tokens + right.input_tokens,
        output_tokens=left.output_tokens + right.output_tokens,
        cost_microunits=left.cost_microunits + right.cost_microunits,
        estimated=left.estimated or right.estimated,
    )


def _sum_charge(left: BudgetCharge, right: BudgetCharge) -> BudgetCharge:
    return BudgetCharge(
        iterations=left.iterations + right.iterations,
        tool_calls=left.tool_calls + right.tool_calls,
        input_tokens=left.input_tokens + right.input_tokens,
        output_tokens=left.output_tokens + right.output_tokens,
        cost_microunits=left.cost_microunits + right.cost_microunits,
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


def _inherit_artifact_requirements(
    intent: IntentEnvelopeV1,
    plan: IntentPlanV1,
    reference: ReferencedArtifactInput,
) -> IntentEnvelopeV1:
    """引用制品已包含原场景条件时，用受控来源标记满足重新生成门槛。"""
    scenario = plan.primary_scenario
    marker = (
        f"沿用制品 {reference.artifact.artifact_id} v{reference.artifact.version}"
    )
    updates: dict[str, object] = {}
    if scenario == "industry_digest":
        updates = {"topic": marker, "time_window": marker}
    elif scenario == "multi_platform_content":
        platforms = intent.requirements.platforms
        if not platforms and reference.artifact.platform in {
            "wechat_official_account",
            "xiaohongshu",
            "toutiao",
        }:
            platforms = (reference.artifact.platform,)
        updates = {
            "topic": marker,
            "platforms": platforms,
        }
    elif scenario == "brand_operation_plan":
        updates = {"brand": marker, "product": marker, "planning_window": marker}
    elif scenario == "ip_operation_plan":
        updates = {"ip": marker, "audience": marker, "incubation_window": marker}
    elif scenario == "campaign_plan":
        updates = {
            "campaign_goal": marker,
            "campaign_window": marker,
            "audience": marker,
        }
    elif scenario == "content_calendar":
        updates = {"topic_scope": marker, "calendar_window": marker}
    elif scenario == "growth_experiment":
        updates = {
            "growth_goal": marker,
            "funnel_stage": marker,
            "experiment_window": marker,
        }
    elif scenario == "operation_review":
        updates = {"review_window": marker, "metric_definition": marker}
    return intent.model_copy(
        update={
            "requirements": intent.requirements.model_copy(update=updates),
            "missing_fields": [],
            "needs_clarification": False,
        }
    )


__all__ = ["OperationIntentPlanningCoordinator"]
