"""X03 Intent V2 到 Supervisor 的无旁路接线测试。"""

from __future__ import annotations

from datetime import datetime

import pytest

from efficiency_platform_agent.agents.operation.definition import (
    OperationSpecialistCapabilityId,
)
from efficiency_platform_agent.agents.operation.scenarios.manifests import (
    build_s6_manifests,
)
from efficiency_platform_agent.agents.operation.scenarios.registry import (
    InMemoryScenarioPackRegistry,
)
from efficiency_platform_agent.agents.operation.scenarios.research_policy import (
    offline_research_quality_policy,
)
from efficiency_platform_agent.agents.operation.scenarios.semantic_catalog import (
    build_operation_semantic_catalog,
)
from efficiency_platform_agent.contracts.conversation import ConversationMessageV1
from efficiency_platform_agent.contracts.intent_v2 import (
    BudgetLeaseReferenceV2,
    IntentDecision,
)
from efficiency_platform_agent.core.enums import StrategyMode
from efficiency_platform_agent.core.runtime import UsageSnapshot
from efficiency_platform_agent.harness.intent_v2_delegate import (
    InMemoryIntentV2TrustedInputFactory,
    IntentV2PreparedInput,
    IntentV2RunPreparationDelegate,
    ResearchScenarioSubmissionBuilderV2,
)
from efficiency_platform_agent.harness.research_v2_adapter import (
    InMemoryResearchBriefStoreV2,
)
from efficiency_platform_agent.orchestration.intent_v2.pipeline import (
    IntentPipelineVersionsV2,
    PreparedIntentV2,
)
from efficiency_platform_agent.orchestration.intent_v2.scenario_adapter import (
    ScenarioProjectionParametersV2,
    ScenarioProjectionStepV2,
    ScenarioProjectionV2,
)
from tests.unit.capabilities.research_v2._delivery_support import delivery_facts


def _projection() -> ScenarioProjectionV2:
    return ScenarioProjectionV2(
        intent_revision=1,
        scope_hash="a" * 64,
        supported=True,
        steps=(
            ScenarioProjectionStepV2(
                goal_id="goal-research",
                capability_id=(
                    OperationSpecialistCapabilityId.RESEARCH_INSIGHT.value
                ),
                parameters=ScenarioProjectionParametersV2(),
            ),
        ),
    )


def _builder() -> ResearchScenarioSubmissionBuilderV2:
    return ResearchScenarioSubmissionBuilderV2(
        InMemoryScenarioPackRegistry(build_s6_manifests())
    )


def _message() -> ConversationMessageV1:
    return ConversationMessageV1(
        message="收集昨天 AI 行业新闻，选 5 条",
        request_id="request-1",
        user_id="user-1",
    )


def test_submission_builder_preserves_brief_task_and_exact_time_window() -> None:
    brief, *_ = delivery_facts()
    operation, submission = _builder().build(
        brief,
        _projection(),
        conversation_id="conversation-1",
        message=_message(),
    )

    assert submission.scenario_id == "industry_digest"
    assert submission.task_spec.task_id == brief.trusted_context.task_id
    assert submission.task_spec.requires_research is True
    conditions = {item.condition_id: item.value for item in submission.task_spec.key_conditions}
    assert conditions["topic"] is not None
    assert conditions["time-window"] is not None
    assert operation.request.tenant_id == brief.trusted_context.tenant_id


class _InputFactory:
    def build(self, pipeline, tenant_id, conversation_id, message, versions):
        del pipeline, tenant_id, conversation_id, message, versions
        return IntentV2PreparedInput(object(), object())


class _IntentPipeline:
    def __init__(self, prepared):
        self.prepared = prepared

    async def prepare(self, message, context):
        del message, context
        return self.prepared


class _SubmissionSink:
    def __init__(self):
        self.items = []

    async def put(self, submission):
        self.items.append(submission)


class _RunPipeline:
    run_id = "r"

    async def is_cancelled(self):
        return False


class _Versions:
    research_policy_version = offline_research_quality_policy().policy_version


def test_trusted_input_factory_preserves_multiturn_messages_and_exact_clock() -> None:
    factory = InMemoryIntentV2TrustedInputFactory(
        catalog=build_operation_semantic_catalog(),
        policy=offline_research_quality_policy(),
        lease_factory=lambda pipeline: BudgetLeaseReferenceV2(
            lease_id=f"lease-{pipeline.run_id}", version=1
        ),
        now=lambda: datetime.fromisoformat("2026-09-16T09:41:00+08:00"),
    )
    first = factory.build(
        _RunPipeline(), "tenant-1", "conversation-1", _message(), _Versions()
    )
    second_message = ConversationMessageV1(
        message="改成上周",
        request_id="request-2",
        user_id="user-1",
    )
    second = factory.build(
        _RunPipeline(),
        "tenant-1",
        "conversation-1",
        second_message,
        _Versions(),
    )

    assert first.message.received_at.isoformat() == "2026-09-16T09:41:00+08:00"
    assert second.message.task_id == first.message.task_id
    assert second.context.visible_user_messages == {
        "request-1": _message().message,
        "request-2": "改成上周",
    }


@pytest.mark.asyncio
async def test_delegate_runs_intent_pipeline_then_stores_brief_for_supervisor() -> None:
    brief, *_ = delivery_facts()
    prepared = PreparedIntentV2(
        decision=IntentDecision(outcome="READY"),
        frame=None,
        brief=brief,
        scenario_projection=_projection(),
        usage=UsageSnapshot(input_tokens=10, output_tokens=5),
        provider_calls=1,
        versions=IntentPipelineVersionsV2(
            "catalog-v2", "context-v2", "permission-v2", "lease", 1, "v2"
        ),
        lifecycle_action="START_NEW_RUN",
        run_id="r",
        replacement_run_id=None,
        committed=True,
        replayed=False,
        dispatch_allowed=True,
    )
    store = InMemoryResearchBriefStoreV2()
    sink = _SubmissionSink()
    shared = [object() for _ in range(4)]
    delegate = IntentV2RunPreparationDelegate(
        intent_pipeline=_IntentPipeline(prepared),
        input_factory=_InputFactory(),
        submission_builder=_builder(),
        submissions=sink,
        source_registry=shared[0],
        tool_runtime=shared[1],
        research_service=shared[2],
        intent_state_store=shared[3],
        research_state_store=store,
    )

    result = await delegate.prepare_v2(
        _RunPipeline(), "t", "conversation-1", _message(), object()
    )

    assert result.request.requested_strategy is StrategyMode.MULTI_AGENT
    assert len(sink.items) == 1
    assert await store.get_brief("t", "x") is brief
