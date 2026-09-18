"""Intent V2 到既有 Conversation/Supervisor 生命周期的受控接线。"""

from __future__ import annotations

import hashlib
from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Protocol, runtime_checkable

from efficiency_platform_agent.agents.operation.contracts.task import (
    ConditionImportance,
    KeyCondition,
    OperationDomain,
    OperationGoal,
    OperationGoalKind,
    OperationIntent,
    OperationRequest,
    SourceScope,
)
from efficiency_platform_agent.agents.operation.definition import (
    OperationSpecialistCapabilityId,
)
from efficiency_platform_agent.agents.operation.scenarios.contracts import (
    ScenarioPackRegistry,
    ScenarioSubmission,
)
from efficiency_platform_agent.contracts.conversation import ConversationMessageV1
from efficiency_platform_agent.contracts.intent_v2 import (
    BudgetLeaseReferenceV2,
    CapabilityCatalogSnapshot,
    IntentContextV2,
    PermissionSnapshotV2,
    TrustedMessageV2,
)
from efficiency_platform_agent.contracts.requests import CreateRunRequestV1
from efficiency_platform_agent.contracts.research_v2 import (
    ResearchBriefV2,
    ResearchPolicySnapshotV2,
    TrustedResearchContextV2,
)
from efficiency_platform_agent.core.budget import BudgetCharge
from efficiency_platform_agent.core.enums import StrategyMode
from efficiency_platform_agent.core.run import JsonObject, RunRequest
from efficiency_platform_agent.harness.errors import HarnessError
from efficiency_platform_agent.harness.service import (
    RunPipelineContext,
    RunPipelinePreparation,
)
from efficiency_platform_agent.orchestration.intent_v2.pipeline import (
    IntentPipelineContextV2,
    IntentPipelineV2,
)
from efficiency_platform_agent.orchestration.intent_v2.scenario_adapter import (
    ScenarioProjectionV2,
)

from .research_v2_adapter import ResearchBriefStoreV2


@dataclass(frozen=True, slots=True)
class IntentV2PreparedInput:
    message: TrustedMessageV2
    context: IntentPipelineContextV2


@runtime_checkable
class IntentV2TrustedInputFactory(Protocol):
    def build(
        self,
        pipeline: RunPipelineContext,
        tenant_id: str,
        conversation_id: str,
        message: ConversationMessageV1,
        versions: object,
    ) -> IntentV2PreparedInput: ...


class InMemoryIntentV2TrustedInputFactory:
    """X03 离线可信输入装配；跨进程会话恢复仍由 X01 门禁。"""

    def __init__(
        self,
        *,
        catalog: CapabilityCatalogSnapshot,
        policy: ResearchPolicySnapshotV2,
        lease_factory: Callable[[RunPipelineContext], BudgetLeaseReferenceV2],
        timezone: str = "Asia/Shanghai",
        now: Callable[[], datetime] = lambda: datetime.now(UTC),
        allowed_default_policy_ids: frozenset[str] = frozenset(),
        allowed_normalizer_versions: frozenset[str] = frozenset(),
        allowed_intent_parameter_names: frozenset[str] = frozenset(
            {"count", "objective"}
        ),
    ) -> None:
        self.catalog = catalog
        self.policy = policy
        self.lease_factory = lease_factory
        self.timezone = timezone
        self.now = now
        self.allowed_default_policy_ids = allowed_default_policy_ids
        self.allowed_normalizer_versions = allowed_normalizer_versions
        self.allowed_intent_parameter_names = allowed_intent_parameter_names
        self._messages: dict[tuple[str, str], dict[str, str]] = {}

    def build(
        self,
        pipeline: RunPipelineContext,
        tenant_id: str,
        conversation_id: str,
        message: ConversationMessageV1,
        versions: object,
    ) -> IntentV2PreparedInput:
        configured_policy = getattr(versions, "research_policy_version", None)
        if configured_policy != self.policy.policy_version:
            raise RuntimeError("INTENT_V2_POLICY_VERSION_MISMATCH")
        key = (tenant_id, conversation_id)
        visible = self._messages.setdefault(key, {})
        existing = visible.get(message.request_id)
        if existing is not None and existing != message.message:
            raise HarnessError(
                "INTENT_MESSAGE_ID_CONFLICT",
                "消息标识已用于其他内容",
                category="request",
            )
        visible[message.request_id] = message.message
        if len(visible) > 128:
            oldest = next(iter(visible))
            visible.pop(oldest)
        message_ids = tuple(visible)
        task_id = _stable_id("task", conversation_id)
        lease = self.lease_factory(pipeline)
        trusted_message = TrustedMessageV2(
            task_id=task_id,
            message_id=message.request_id,
            text=message.message,
            received_at=self.now(),
            timezone=self.timezone,
            referenced_task_ids=(task_id,),
        )
        context = IntentPipelineContextV2(
            intent_context=IntentContextV2(
                current_message_id=message.request_id,
                visible_message_ids=message_ids,
                context_version=_context_version(message_ids),
            ),
            visible_user_messages=dict(visible),
            catalog=self.catalog,
            permissions=PermissionSnapshotV2(
                version=f"permission/{self.catalog.catalog_version}",
                allowed_capability_ids=tuple(
                    item.capability_id for item in self.catalog.capabilities
                ),
            ),
            lease=lease,
            research_context=TrustedResearchContextV2(
                tenant_id=tenant_id,
                run_id=pipeline.run_id,
                task_id=task_id,
                budget_lease_id=lease.lease_id,
            ),
            research_policy=self.policy,
            proposed_run_id=pipeline.run_id,
            allowed_default_policy_ids=self.allowed_default_policy_ids,
            allowed_normalizer_versions=self.allowed_normalizer_versions,
            allowed_intent_parameter_names=self.allowed_intent_parameter_names,
        )
        return IntentV2PreparedInput(trusted_message, context)


@runtime_checkable
class WritableResearchBriefStoreV2(ResearchBriefStoreV2, Protocol):
    async def put_brief(self, brief: ResearchBriefV2) -> None: ...


@runtime_checkable
class ScenarioSubmissionSink(Protocol):
    async def put(self, submission: ScenarioSubmission) -> None: ...


class ResearchScenarioSubmissionBuilderV2:
    """将单一研究投影映射到既有 industry_digest，不伪造 V1 意图。"""

    def __init__(self, registry: ScenarioPackRegistry) -> None:
        if not isinstance(registry, ScenarioPackRegistry):
            raise TypeError("registry 必须实现 ScenarioPackRegistry")
        self.registry = registry

    def build(
        self,
        brief: ResearchBriefV2,
        projection: ScenarioProjectionV2,
        *,
        conversation_id: str,
        message: ConversationMessageV1,
    ) -> tuple[OperationRequest, ScenarioSubmission]:
        research_capability = OperationSpecialistCapabilityId.RESEARCH_INSIGHT.value
        if (
            not projection.supported
            or len(projection.steps) != 1
            or projection.steps[0].capability_id != research_capability
        ):
            raise HarnessError(
                "RESEARCH_V2_SCENARIO_UNSUPPORTED",
                "当前离线接线仅支持单一研究任务",
                category="request",
            )
        manifest = self.registry.get("industry_digest", "1.0.0")
        if manifest.profile_requirements:
            raise RuntimeError("RESEARCH_V2_PROFILE_REQUIREMENT_UNEXPECTED")
        operation = OperationRequest(
            "operation-request/1",
            RunRequest(
                message.request_id,
                brief.trusted_context.tenant_id,
                message.user_id,
                message.message,
            ),
            _stable_id("operation", message.request_id),
            _stable_id("session", conversation_id),
            None,
            frozenset({OperationDomain.CONTENT}),
            manifest.output_requirements,
        )
        values = {
            "topic": JsonObject((("topic", brief.topic),)),
            "time-window": JsonObject(
                (
                    ("start", brief.time_window.start.isoformat()),
                    ("end", brief.time_window.end.isoformat()),
                    ("timezone", brief.time_window.timezone),
                )
            ),
        }
        conditions = tuple(
            KeyCondition(
                item.condition_id,
                item.label,
                ConditionImportance.CRITICAL,
                values.get(item.condition_id),
            )
            for item in manifest.trigger_conditions
        )
        task = operation.to_task_spec(
            task_id=brief.trusted_context.task_id,
            tenant_id=brief.trusted_context.tenant_id,
            user_id=message.user_id,
            intent=OperationIntent.RESEARCH,
            domains=frozenset({OperationDomain.CONTENT}),
            goals=(
                OperationGoal(
                    "goal-primary",
                    OperationGoalKind.EFFICIENCY,
                    None,
                    brief.topic,
                ),
            ),
            objects=(),
            key_conditions=conditions,
            assumptions=(),
            source_scopes=frozenset({SourceScope.USER_INPUT}),
            missing_critical_condition_ids=(),
            requires_user_input=False,
            requires_research=True,
        )
        submission = ScenarioSubmission(
            "scenario-submission/1",
            _stable_id("submission", message.request_id),
            manifest.scenario_id,
            manifest.semantic_version,
            _stable_id("plan", message.request_id),
            operation,
            task,
            (),
            None,
        )
        return operation, submission


class IntentV2RunPreparationDelegate:
    """执行真实 IntentPipelineV2，并把冻结 Brief 交给同一 Supervisor Run。"""

    def __init__(
        self,
        *,
        intent_pipeline: IntentPipelineV2,
        input_factory: IntentV2TrustedInputFactory,
        submission_builder: ResearchScenarioSubmissionBuilderV2,
        submissions: ScenarioSubmissionSink,
        source_registry: object,
        tool_runtime: object,
        research_service: object,
        intent_state_store: object,
        research_state_store: WritableResearchBriefStoreV2,
    ) -> None:
        if not isinstance(input_factory, IntentV2TrustedInputFactory):
            raise TypeError("input_factory 必须实现 IntentV2TrustedInputFactory")
        if not isinstance(submissions, ScenarioSubmissionSink):
            raise TypeError("submissions 必须实现 ScenarioSubmissionSink")
        if not isinstance(research_state_store, WritableResearchBriefStoreV2):
            raise TypeError("research_state_store 必须支持 Brief 读写")
        self.intent_pipeline = intent_pipeline
        self.input_factory = input_factory
        self.submission_builder = submission_builder
        self.submissions = submissions
        self.source_registry = source_registry
        self.tool_runtime = tool_runtime
        self.research_service = research_service
        self.intent_state_store = intent_state_store
        self.research_state_store = research_state_store

    async def prepare_v2(
        self,
        pipeline: RunPipelineContext,
        tenant_id: str,
        conversation_id: str,
        message: ConversationMessageV1,
        versions: object,
    ) -> RunPipelinePreparation:
        if await pipeline.is_cancelled():
            raise HarnessError("CANCELLED", "运行已取消", category="runtime")
        prepared_input = self.input_factory.build(
            pipeline, tenant_id, conversation_id, message, versions
        )
        prepared = await self.intent_pipeline.prepare(
            prepared_input.message, prepared_input.context
        )
        if (
            prepared.decision.outcome != "READY"
            or not prepared.dispatch_allowed
            or prepared.brief is None
            or prepared.scenario_projection is None
        ):
            code = prepared.decision.reason_codes[0] if prepared.decision.reason_codes else "INTENT_V2_NOT_READY"
            raise HarnessError(code, "当前请求尚不能执行", category="request")
        if prepared.brief.trusted_context.run_id != pipeline.run_id:
            raise HarnessError(
                "INTENT_V2_RUN_MISMATCH", "运行身份不一致", category="runtime"
            )
        operation, submission = self.submission_builder.build(
            prepared.brief,
            prepared.scenario_projection,
            conversation_id=conversation_id,
            message=message,
        )
        if submission.task_spec.task_id != prepared.brief.trusted_context.task_id:
            raise RuntimeError("RESEARCH_V2_TASK_MISMATCH")
        await self.research_state_store.put_brief(prepared.brief)
        await self.submissions.put(submission)
        usage = prepared.usage
        return RunPipelinePreparation(
            CreateRunRequestV1(
                request_id=message.request_id,
                tenant_id=tenant_id,
                user_id=message.user_id,
                input_text=message.message,
                requested_strategy=StrategyMode.MULTI_AGENT,
                strategy_payload_schema_version="operation-strategy-payload/1",
                strategy_payload={"operation_request": _operation_payload(operation)},
            ),
            (
                (
                    "intent_detected",
                    {
                        "domain": "research",
                        "task_type": "industry_digest",
                        "scenario_id": "industry_digest",
                        "intent_revision": prepared.brief.intent_revision,
                        "degraded": False,
                    },
                ),
            ),
            usage,
            False,
            BudgetCharge(
                iterations=max(1, prepared.provider_calls),
                input_tokens=usage.input_tokens,
                output_tokens=usage.output_tokens,
                cost_microunits=usage.cost_microunits,
            ),
        )


def _stable_id(prefix: str, value: str) -> str:
    digest = hashlib.sha256(value.encode("utf-8")).hexdigest()[:24]
    return f"{prefix}-{digest}"


def _operation_payload(request: OperationRequest) -> dict[str, object]:
    return {
        "contract_version": request.contract_version,
        "request": {
            "request_id": request.request.request_id,
            "tenant_id": request.request.tenant_id,
            "user_id": request.request.user_id,
            "input_text": request.request.input_text,
        },
        "operation_id": request.operation_id,
        "session_id": request.session_id,
        "parent_task_id": request.parent_task_id,
    }


def _context_version(message_ids: tuple[str, ...]) -> str:
    digest = hashlib.sha256("\x00".join(message_ids).encode("utf-8")).hexdigest()[:24]
    return f"conversation-context/{digest}"


__all__ = [
    "InMemoryIntentV2TrustedInputFactory",
    "IntentV2PreparedInput",
    "IntentV2RunPreparationDelegate",
    "IntentV2TrustedInputFactory",
    "ResearchScenarioSubmissionBuilderV2",
    "WritableResearchBriefStoreV2",
]
