"""把明确的运营研究指令投影为可审计的 IntentPatchV2。"""

from __future__ import annotations

import re
from typing import Literal

from efficiency_platform_agent.agents.operation.definition import (
    OperationSpecialistCapabilityId,
)
from efficiency_platform_agent.contracts.intent_v2 import (
    CapabilityCatalogSnapshot,
    FieldOperation,
    FieldPayload,
    FieldValue,
    GoalNodeV2,
    IntentContextV2,
    IntentFrameV2,
    IntentParameterV2,
    IntentPatchV2,
    OutputRequirementsV2,
    SourceConstraintsV2,
    SourceSpan,
)
from efficiency_platform_agent.contracts.research_request_policy import (
    has_explicit_source_count,
    requested_source_count,
)
from efficiency_platform_agent.contracts.temporal_v2 import (
    CalendarPeriodExpression,
    RollingDurationExpression,
    TemporalExpression,
)
from efficiency_platform_agent.conversation.context import ConversationContext
from efficiency_platform_agent.orchestration.intent_fast_path import (
    detect_fast_path_intent,
)


def resolve_explicit_research_patch(
    text: str,
    context: IntentContextV2,
    previous: IntentFrameV2 | None,
    catalog: CapabilityCatalogSnapshot,
) -> IntentPatchV2 | None:
    """仅接管字段完整的新研究任务，其他请求继续交给模型解释。"""
    del catalog
    if previous is not None:
        return None
    intent = detect_fast_path_intent(text, ConversationContext())
    if (
        intent is None
        or not intent.needs_research
        or intent.needs_clarification
        or intent.requirements.topic is None
    ):
        return None
    span = SourceSpan(
        message_id=context.current_message_id,
        start=0,
        end=len(text),
        quoted_text=text,
    )
    platforms = tuple(intent.requirements.platforms)
    output_type = "article" if platforms else "digest"
    topic = _normalize_topic(intent.requirements.topic)
    parameters = (
        (
            IntentParameterV2(
                name="count",
                value=requested_source_count(text, default=5),
            ),
            IntentParameterV2(name="count_mode", value="best_effort"),
        )
        if has_explicit_source_count(text)
        else ()
    )
    return IntentPatchV2(
        base_revision=0,
        dialog_act="new_task",
        goal_updates=(
            GoalNodeV2(
                goal_id="g-research",
                description=text,
                candidate_capability_ids=(
                    OperationSpecialistCapabilityId.RESEARCH_INSIGHT.value,
                ),
                parameters=parameters,
            ),
        ),
        field_operations=(
            _set("topic", topic, span),
            _set("temporal", _temporal(intent.requirements.time_window), span),
            _set("source_constraints", SourceConstraintsV2(), span),
            _set(
                "output_requirements",
                OutputRequirementsV2(
                    output_types=(output_type,),
                    target_platforms=platforms or None,
                    language="zh-CN",
                    style="标准排版成稿" if platforms else None,
                    citations_required=True,
                ),
                span,
            ),
        ),
    )


def _normalize_topic(topic: str) -> str:
    value = " ".join(topic.split())
    value = re.sub(r"^(?:一下\s*)?(?:都?有)?哪些\s*", "", value).strip()
    if "AI" in value.upper() and any(
        marker in value for marker in ("热点", "大模型", "AI 类产品", "爆火")
    ):
        return "AI 行业热点"
    return value


FieldName = Literal[
    "topic",
    "entities",
    "exclusions",
    "temporal",
    "source_constraints",
    "output_requirements",
    "source_allowed_ids",
    "source_excluded_ids",
    "source_languages",
    "event_regions",
    "publisher_regions",
    "source_primary_only",
    "output_types",
    "target_platforms",
    "output_language",
    "output_style",
    "citations_required",
]


def _set(field_name: FieldName, value: FieldPayload, span: SourceSpan) -> FieldOperation:
    return FieldOperation(
        operation="set",
        field_name=field_name,
        value=FieldValue(value=value, origin="explicit", source_span=span),
    )


def _temporal(value: str | None) -> TemporalExpression:
    if value in {"今天", "明天", "本周", "下周", "本月"}:
        period: Literal["day", "week", "month"] = (
            "day" if value in {"今天", "明天"} else "week"
        )
        if value == "本月":
            period = "month"
        return CalendarPeriodExpression(
            text=value,
            period=period,
            offset=1 if value in {"明天", "下周"} else 0,
        )
    return RollingDurationExpression(
        text=value or "最近7天",
        amount=7,
        unit="day",
    )


__all__ = ["resolve_explicit_research_patch"]
