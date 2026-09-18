"""本地实时研究组合根：应用共享限流，每个 Run 独立事实与同一父预算。"""

from __future__ import annotations

import asyncio
import time
from collections.abc import Callable
from contextvars import ContextVar
from dataclasses import dataclass, replace
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from efficiency_platform_agent.agents.operation.scenarios.manifests import (
    build_s6_manifests,
)
from efficiency_platform_agent.agents.operation.scenarios.registry import (
    InMemoryScenarioPackRegistry,
)
from efficiency_platform_agent.agents.operation.scenarios.semantic_catalog import (
    build_operation_semantic_catalog,
)
from efficiency_platform_agent.capabilities.model.runtime import ModelRuntime
from efficiency_platform_agent.capabilities.research.v2.acquisition import (
    AcquisitionExecutor,
    AcquisitionRuntimeContextV2,
)
from efficiency_platform_agent.capabilities.research.v2.attempts import (
    InMemorySourceAttemptLedger,
)
from efficiency_platform_agent.capabilities.research.v2.content_acquisition import (
    ResearchContentAcquirer,
)
from efficiency_platform_agent.capabilities.research.v2.model_decisions import (
    ResearchModelDecisions,
)
from efficiency_platform_agent.capabilities.research.v2.sources import (
    VerifiedSourceRegistry,
)
from efficiency_platform_agent.configuration.research import ResearchPipelineSettings
from efficiency_platform_agent.configuration.research_local_sources import (
    load_local_source_descriptors,
)
from efficiency_platform_agent.context.builder import ContextBuilder
from efficiency_platform_agent.contracts.conversation import ConversationMessageV1
from efficiency_platform_agent.contracts.intent_v2 import (
    BudgetLeaseReferenceV2,
    IntentContextV2,
)
from efficiency_platform_agent.contracts.research_sources_v2 import (
    SourceDescriptorV2,
    SourceRuntimeContextV2,
)
from efficiency_platform_agent.contracts.research_v2 import (
    ResearchBriefV2,
    ResearchOutcomeV2,
    ResearchPolicySnapshotV2,
    ResearchRuntimeContextV2,
)
from efficiency_platform_agent.conversation.service import ConversationSubmissionStore
from efficiency_platform_agent.core.budget import RemainingBudget
from efficiency_platform_agent.core.budget_execution import (
    BudgetExecutionBinding,
    bind_budget_execution,
)
from efficiency_platform_agent.core.run import ExecutionBudget, RunContext, RunRequest
from efficiency_platform_agent.orchestration.intent_v2.binding import (
    CapabilityBinderV2,
    build_operation_parameter_schema_registry,
)
from efficiency_platform_agent.orchestration.intent_v2.decision import (
    IntentDecisionPolicyV2,
)
from efficiency_platform_agent.orchestration.intent_v2.interpreter import (
    ControlledIntentInterpreterV2,
    IntentV2ContextBuildScope,
)
from efficiency_platform_agent.orchestration.intent_v2.patch_validation import (
    IntentPatchValidator,
)
from efficiency_platform_agent.orchestration.intent_v2.pipeline import (
    InMemoryIntentTaskRepositoryV2,
    IntentPipelineV2,
    IntentTaskSnapshotV2,
)
from efficiency_platform_agent.orchestration.intent_v2.reducer import IntentStateReducer
from efficiency_platform_agent.orchestration.intent_v2.research_bridge import (
    ResearchBriefBuilderV2,
)
from efficiency_platform_agent.orchestration.intent_v2.scenario_adapter import (
    ScenarioInputAdapter,
)
from efficiency_platform_agent.orchestration.intent_v2.temporal import TemporalResolver
from efficiency_platform_agent.orchestration.research_v2.materializer import (
    LocalLiveResearchOutcomeMaterializer,
)
from efficiency_platform_agent.orchestration.research_v2.service import (
    LangGraphResearchServiceV2,
)
from efficiency_platform_agent.orchestration.research_v2.stage_runner import (
    LocalLiveResearchStageRunner,
)
from efficiency_platform_agent.persistence.research_local_memory import (
    LocalResearchRunStore,
)
from efficiency_platform_agent.prompts.registry import (
    PromptRegistry,
    register_intent_v2_prompts,
)
from efficiency_platform_agent.prompts.runtime import PromptRuntime
from efficiency_platform_agent.tools.runtime.service import (
    ToolLeaseContext,
    ToolRuntime,
)

from .intent_v2_delegate import (
    InMemoryIntentV2TrustedInputFactory,
    IntentV2ConversationDecision,
    IntentV2RunPreparationDelegate,
    ResearchScenarioSubmissionBuilderV2,
)
from .research_local_runtime import (
    LocalResearchExecutionV2,
    RunScopedResearchServiceV2,
    build_local_research_binding,
)
from .research_local_sources import build_local_source_registry
from .research_local_tools import (
    LocalResearchBodyHttpQuota,
    LocalResearchNetworkLimits,
    build_local_research_tools,
)
from .service import AgentRuntimeService, RunPipelineContext, RunPipelinePreparation


@dataclass(frozen=True, slots=True)
class _IntentScope:
    pipeline: RunPipelineContext
    context: RunContext
    request: RunRequest
    binding: BudgetExecutionBinding


class _IntentResolvers:
    """异步调用局部身份，禁止并发 Run 共享可变模型上下文。"""

    def __init__(self) -> None:
        self.current: ContextVar[_IntentScope] = ContextVar("local_live_intent_scope")

    async def resolve(
        self, text: str, context: IntentContextV2, lease: BudgetLeaseReferenceV2
    ) -> IntentV2ContextBuildScope:
        scope = self.current.get()
        if lease.lease_id != scope.binding.lease_id or text != scope.request.input_text:
            raise ValueError("LOCAL_RESEARCH_BINDING_MISMATCH")
        available = scope.pipeline.remaining_budget
        return IntentV2ContextBuildScope(
            context.context_version,
            scope.request,
            scope.context,
            ExecutionBudget(
                available.iterations,
                available.tool_calls,
                available.input_tokens,
                available.output_tokens,
                available.timeout_ms,
                available.cost_microunits,
            ),
        )

    async def remaining(self, lease: BudgetLeaseReferenceV2) -> RemainingBudget:
        scope = self.current.get()
        if lease.lease_id != scope.binding.lease_id:
            raise ValueError("LOCAL_RESEARCH_BINDING_MISMATCH")
        return scope.pipeline.remaining_budget

    async def wait_requested(self) -> bool:
        return await self.current.get().pipeline.is_cancelled()


class _RunCancellation:
    def __init__(self, execution: LocalResearchExecutionV2) -> None:
        self.execution = execution
        self.waiter: asyncio.Future[None] = asyncio.ensure_future(
            execution.wait_cancelled()
        )

    def is_requested(self) -> bool:
        return self.waiter.done() and not self.waiter.cancelled()

    async def wait_requested(self) -> None:
        await asyncio.shield(self.waiter)


class _LocalLiveService(LangGraphResearchServiceV2):
    """释放同 Run 取消监听，不改变正式图或父服务执行语义。"""

    def __init__(self, *, cancellation: _RunCancellation, **kwargs: Any) -> None:
        super().__init__(**kwargs)
        self.cancellation = cancellation

    async def research(
        self, brief: ResearchBriefV2, runtime_context: ResearchRuntimeContextV2
    ) -> ResearchOutcomeV2:
        try:
            return await super().research(brief, runtime_context)
        finally:
            self.cancellation.waiter.cancel()
            await asyncio.gather(self.cancellation.waiter, return_exceptions=True)


class LocalLiveToolRuntimeFactory:
    """工具工厂只被同 Run 单次 Service 装配调用；不保存额外正文或事实副本。"""

    def __init__(
        self,
        descriptors: tuple[SourceDescriptorV2, ...],
        network_limits: LocalResearchNetworkLimits,
    ) -> None:
        self.descriptors, self.network_limits = descriptors, network_limits

    def build(
        self,
        execution: LocalResearchExecutionV2,
        context: RunContext,
        cancellation: _RunCancellation,
        allowed_source_ids: tuple[str, ...],
    ) -> ToolRuntime:
        return build_local_research_tools(
            descriptors=tuple(
                item
                for item in self.descriptors
                if item.source_id in allowed_source_ids
            ),
            binding=execution.binding,
            run_context=context,
            cancellation_signal=cancellation,
            network_limits=self.network_limits,
            body_http_quota=LocalResearchBodyHttpQuota(execution.binding),
        )


class _LocalLiveDelegate(IntentV2RunPreparationDelegate):
    def __init__(self, *, resolvers: _IntentResolvers, **kwargs: Any) -> None:
        super().__init__(**kwargs)
        self.resolvers = resolvers
        self.run_settings: dict[
            tuple[str, str], tuple[float, ResearchPolicySnapshotV2, tuple[str, ...]]
        ] = {}
        self.pending: dict[
            tuple[str, str, str], tuple[float, IntentTaskSnapshotV2]
        ] = {}

    async def prepare_v2(
        self,
        pipeline: RunPipelineContext,
        tenant_id: str,
        conversation_id: str,
        message: ConversationMessageV1,
        versions: object,
    ) -> RunPipelinePreparation | IntentV2ConversationDecision:
        binding = build_local_research_binding(
            tenant_id=tenant_id,
            run_id=pipeline.run_id,
            lease_id=f"lease-{pipeline.run_id}",
            remaining=pipeline.remaining_budget,
            now=datetime.now(UTC),
        )
        scope = _IntentScope(
            pipeline,
            RunContext(pipeline.run_id, tenant_id, message.user_id, pipeline.run_id),
            RunRequest(message.request_id, tenant_id, message.user_id, message.message),
            binding,
        )
        token = self.resolvers.current.set(scope)
        try:
            with bind_budget_execution(binding):
                prepared_input = self.input_factory.build(
                    pipeline, tenant_id, conversation_id, message, versions
                )
                allowed = getattr(versions, "research_source_allowlist", ())
                assert isinstance(self.tool_runtime, LocalLiveToolRuntimeFactory)
                if not set(allowed).issubset(
                    item.source_id for item in self.tool_runtime.descriptors
                ):
                    raise ValueError("SOURCE_NOT_RUNTIME_ALLOWED")
                self.run_settings = {
                    key: value
                    for key, value in self.run_settings.items()
                    if value[0] > time.monotonic()
                }
                if len(self.run_settings) >= 100:
                    raise ValueError("LOCAL_RESEARCH_CAPACITY")
                self.run_settings[(tenant_id, pipeline.run_id)] = (
                    time.monotonic() + 1800,
                    prepared_input.context.research_policy,
                    allowed,
                )
                task_id = prepared_input.message.task_id
                identity = (tenant_id, message.user_id, conversation_id)
                self.pending = {
                    key: item
                    for key, item in self.pending.items()
                    if item[0] > time.monotonic()
                }
                previous = self.pending.get(identity)
                repository = self.intent_state_store
                assert isinstance(repository, _LocalIntentTaskRepositoryV2)
                await repository.begin(tenant_id, task_id)
                if (
                    previous is not None
                    and await repository.load(tenant_id, task_id) is None
                ):
                    snapshot = previous[1]
                    assert snapshot.frame is not None
                    await repository.seed(
                        replace(
                            snapshot,
                            task_id=task_id,
                            frame=snapshot.frame.model_copy(
                                update={"task_id": task_id}
                            ),
                            run_id=None,
                            run_status=None,
                        )
                    )
                result = await super().prepare_v2(
                    pipeline, tenant_id, conversation_id, message, versions
                )
                if isinstance(result, IntentV2ConversationDecision):
                    self.run_settings.pop((tenant_id, pipeline.run_id), None)
                if (
                    isinstance(result, IntentV2ConversationDecision)
                    and result.intent.needs_clarification
                ):
                    current_snapshot = await repository.load(tenant_id, task_id)
                    if current_snapshot is not None:
                        if len(self.pending) >= 100 and identity not in self.pending:
                            raise ValueError("LOCAL_RESEARCH_CAPACITY")
                        self.pending[identity] = (
                            time.monotonic() + 1800,
                            current_snapshot,
                        )
                else:
                    self.pending.pop(identity, None)
                return result
        except BaseException:
            self.run_settings.pop((tenant_id, pipeline.run_id), None)
            raise
        finally:
            self.resolvers.current.reset(token)


@dataclass(frozen=True, slots=True)
class LocalLiveResearchComponents:
    delegate: IntentV2RunPreparationDelegate
    registry: VerifiedSourceRegistry
    tool_runtime: LocalLiveToolRuntimeFactory
    research_service: RunScopedResearchServiceV2
    intent_state_store: InMemoryIntentTaskRepositoryV2
    state_store: LocalResearchRunStore
    network_limits: LocalResearchNetworkLimits


class _LocalIntentTaskRepositoryV2(InMemoryIntentTaskRepositoryV2):
    """本地意图只保留 100 个、30 分钟 Run；不驱逐仍在期限内的任务。"""

    def __init__(self, *, monotonic: Callable[[], float] = time.monotonic) -> None:
        super().__init__()
        self.monotonic = monotonic
        self._expires: dict[tuple[str, str], float] = {}

    async def begin(self, tenant_id: str, task_id: str) -> None:
        async with self._lock:
            expired = {
                key
                for key, deadline in self._expires.items()
                if deadline <= self.monotonic()
            }
            for key in expired:
                self._expires.pop(key)
                self._snapshots.pop(key, None)
            self._records = {
                key: record
                for key, record in self._records.items()
                if key[:2] not in expired
            }
            key = (tenant_id, task_id)
            if key in self._expires:
                return
            if len(self._expires) >= 100:
                raise ValueError("LOCAL_RESEARCH_CAPACITY")
            self._expires[key] = self.monotonic() + 1800


def build_local_live_research_components(
    settings: ResearchPipelineSettings,
    *,
    model_runtime: ModelRuntime,
    runtime: AgentRuntimeService,
    submissions: ConversationSubmissionStore,
) -> LocalLiveResearchComponents:
    """只装配显式 local_live；来源授权来自静态 TOML，禁用源保持不可用。"""
    if not settings.local_live_ready:
        raise ValueError("RESEARCH_V2_LOCAL_LIVE_NOT_READY")
    descriptors = tuple(
        item
        for item in load_local_source_descriptors(
            Path(__file__).resolve().parents[3]
            / "config/research_local_live_sources.toml"
        )
        if item.source_id in settings.research_source_allowlist
    )
    if {item.source_id for item in descriptors} != set(
        settings.research_source_allowlist
    ):
        raise ValueError("SOURCE_NOT_RUNTIME_ALLOWED")
    registry = build_local_source_registry(descriptors, now=datetime.now(UTC))
    network_limits = LocalResearchNetworkLimits()
    tools = LocalLiveToolRuntimeFactory(descriptors, network_limits)
    store = LocalResearchRunStore()
    policy = ResearchPolicySnapshotV2(
        quality_policy_id="local-live-quality/1",
        policy_version=settings.research_policy_version,
        max_collection_rounds=3 if settings.research_replan_enabled else 1,
    )

    def service_factory(
        execution: LocalResearchExecutionV2,
    ) -> LangGraphResearchServiceV2:
        key = execution.key
        _expires, run_policy, allowed_sources = delegate.run_settings.pop(
            (key.tenant_id, key.run_id)
        )
        context = RunContext(key.run_id, key.tenant_id, key.user_id, key.run_id)
        cancellation = _RunCancellation(execution)
        tool_runtime = tools.build(execution, context, cancellation, allowed_sources)
        available = RemainingBudget(
            runtime.budget.max_iterations,
            execution.budget.remaining_calls,
            runtime.budget.max_input_tokens,
            runtime.budget.max_output_tokens,
            runtime.budget.max_cost_microunits,
            max(
                0, int((execution.deadline - datetime.now(UTC)).total_seconds() * 1000)
            ),
        )
        deadline_monotonic = time.monotonic() + available.timeout_ms / 1000
        acquisition = AcquisitionRuntimeContextV2(
            context,
            frozenset(allowed_sources),
            frozenset({"research:read"}),
            available,
            deadline_monotonic,
            lease_context=ToolLeaseContext(
                execution.binding.port,
                execution.binding.scope,
                f"local-research-{key.run_id}",
                execution.binding.version,
                reserve_cost_microunits=0,
            ),
            max_attempts=1,
        )
        output = LocalLiveResearchOutcomeMaterializer(
            key=key,
            store=store,
            brief=execution.brief,
            binding=execution.binding,
            cancellation_signal=cancellation,
            deadline_monotonic=deadline_monotonic,
        )
        stages = LocalLiveResearchStageRunner(
            key=key,
            store=store,
            brief=execution.brief,
            policy=run_policy,
            binding=execution.binding,
            registry=registry,
            source_context=SourceRuntimeContextV2(
                tenant_id=key.tenant_id,
                run_id=key.run_id,
                now=datetime.now(UTC),
                allowed_source_ids=allowed_sources,
            ),
            acquisition_executor=AcquisitionExecutor(
                tool_runtime, InMemorySourceAttemptLedger()
            ),
            content_acquirer=ResearchContentAcquirer(
                tool_runtime, descriptors=descriptors
            ),
            acquisition_context=acquisition,
            decisions=ResearchModelDecisions(
                model_runtime=model_runtime,
                context_builder=ContextBuilder(),
                run_context=context,
                binding=execution.binding,
                brief=execution.brief,
                remaining_budget=available,
            ),
            output_stages=output,
        )
        return _LocalLiveService(
            cancellation=cancellation,
            policy=run_policy,
            budget=execution.budget,
            stage_runner=stages,
            materializer=output,
        )

    service = RunScopedResearchServiceV2(store=store, service_factory=service_factory)
    resolvers = _IntentResolvers()
    prompts = PromptRegistry()
    register_intent_v2_prompts(prompts)
    intent_store = _LocalIntentTaskRepositoryV2()
    pipeline = IntentPipelineV2(
        repository=intent_store,
        interpreter=ControlledIntentInterpreterV2(
            model_runtime,
            PromptRuntime(prompts),
            ContextBuilder(),
            resolvers,
            resolvers,
            cancellation_signal=resolvers,
        ),
        validator=IntentPatchValidator(),
        reducer=IntentStateReducer(),
        temporal_resolver=TemporalResolver(),
        binder=CapabilityBinderV2(build_operation_parameter_schema_registry()),
        decision_policy=IntentDecisionPolicyV2(),
        brief_builder=ResearchBriefBuilderV2(),
        scenario_adapter=ScenarioInputAdapter(),
    )
    delegate = _LocalLiveDelegate(
        resolvers=resolvers,
        intent_pipeline=pipeline,
        input_factory=InMemoryIntentV2TrustedInputFactory(
            catalog=build_operation_semantic_catalog(),
            policy=policy,
            lease_factory=lambda _: BudgetLeaseReferenceV2(
                lease_id=resolvers.current.get().binding.lease_id, version=0
            ),
            run_scoped_tasks=True,
        ),
        submission_builder=ResearchScenarioSubmissionBuilderV2(
            InMemoryScenarioPackRegistry(build_s6_manifests())
        ),
        submissions=submissions,
        source_registry=registry,
        tool_runtime=tools,
        research_service=service,
        intent_state_store=intent_store,
        research_state_store=service,
    )
    return LocalLiveResearchComponents(
        delegate, registry, tools, service, intent_store, store, network_limits
    )
