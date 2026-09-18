"""X03 真实会话/Supervisor/Research 子图/ToolRuntime 的离线闭环。"""

from __future__ import annotations

import json
import time
from datetime import UTC, datetime

import pytest

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
from efficiency_platform_agent.capabilities.research.v2.acquisition import (
    AcquisitionExecutor,
    AcquisitionRuntimeContextV2,
    DiscoveryActionV2,
)
from efficiency_platform_agent.capabilities.research.v2.attempts import (
    InMemorySourceAttemptLedger,
)
from efficiency_platform_agent.capabilities.research.v2.delivery import (
    DeliveryPackBuilder,
)
from efficiency_platform_agent.capabilities.research.v2.evidence import (
    build_evidence_ref,
)
from efficiency_platform_agent.configuration.research import ResearchPipelineSettings
from efficiency_platform_agent.contracts.conversation import ConversationMessageV1
from efficiency_platform_agent.contracts.intent_v2 import (
    BudgetLeaseReferenceV2,
    FieldOperation,
    FieldValue,
    GoalNodeV2,
    IntentParameterV2,
    IntentPatchV2,
    OutputRequirementsV2,
    SourceConstraintsV2,
    SourceSpan,
)
from efficiency_platform_agent.contracts.research_evidence_v2 import (
    ClaimRecordV2,
    CoverageSnapshotV2,
    EventClusterV2,
    EvidenceSnapshotV2,
    SourceDocumentV2,
)
from efficiency_platform_agent.contracts.research_sources_v2 import (
    CandidateRecordV2,
    DiscoveryBatchV2,
    SourceAttemptV2,
    SourceUsageV2,
)
from efficiency_platform_agent.contracts.research_v2 import (
    BudgetSnapshotV2,
    QualityGapV2,
    ResearchOutcomeV2,
    ResearchUsageV2,
)
from efficiency_platform_agent.contracts.temporal_v2 import (
    CalendarPeriodExpression,
    ResolvedTimeWindow,
)
from efficiency_platform_agent.conversation.service import ConversationSubmissionStore
from efficiency_platform_agent.core.budget import RemainingBudget
from efficiency_platform_agent.core.enums import RunStatus
from efficiency_platform_agent.core.run import (
    ProviderMessage,
    ProviderResult,
    ProviderUsage,
    RunContext,
)
from efficiency_platform_agent.core.runtime import UsageSnapshot
from efficiency_platform_agent.harness.intent_v2_delegate import (
    InMemoryIntentV2TrustedInputFactory,
    IntentV2RunPreparationDelegate,
    ResearchScenarioSubmissionBuilderV2,
)
from efficiency_platform_agent.harness.local_real_factory import (
    build_local_agent_application,
)
from efficiency_platform_agent.harness.research_v2_adapter import (
    InMemoryResearchBriefStoreV2,
)
from efficiency_platform_agent.orchestration.intent_v2.binding import (
    CapabilityBinderV2,
    build_operation_parameter_schema_registry,
)
from efficiency_platform_agent.orchestration.intent_v2.decision import (
    IntentDecisionPolicyV2,
)
from efficiency_platform_agent.orchestration.intent_v2.interpreter import (
    IntentInterpretationV2Execution,
)
from efficiency_platform_agent.orchestration.intent_v2.patch_validation import (
    IntentPatchValidator,
)
from efficiency_platform_agent.orchestration.intent_v2.pipeline import (
    InMemoryIntentTaskRepositoryV2,
    IntentPipelineV2,
)
from efficiency_platform_agent.orchestration.intent_v2.reducer import IntentStateReducer
from efficiency_platform_agent.orchestration.intent_v2.research_bridge import (
    ResearchBriefBuilderV2,
)
from efficiency_platform_agent.orchestration.intent_v2.scenario_adapter import (
    ScenarioInputAdapter,
)
from efficiency_platform_agent.orchestration.intent_v2.temporal import TemporalResolver
from efficiency_platform_agent.orchestration.research_v2.graph import (
    ResearchStageUpdateV2,
)
from efficiency_platform_agent.orchestration.research_v2.service import (
    LangGraphResearchServiceV2,
)
from efficiency_platform_agent.tools.external.research import (
    ExplicitDocumentFetcherRegistry,
    ExplicitSourceProviderRegistry,
    ResearchDiscoverArgumentsV2,
    TrustedResearchToolScope,
    research_tool_entries,
)
from efficiency_platform_agent.tools.runtime.registry import ToolRegistry
from efficiency_platform_agent.tools.runtime.service import ToolRuntime
from tests.unit.harness.test_local_real_factory import synthetic_settings

ANCHOR = datetime.fromisoformat("2026-09-16T09:41:00+08:00")
WINDOW = ResolvedTimeWindow(
    start=datetime(2026, 9, 14, 16, tzinfo=UTC),
    end=datetime(2026, 9, 15, 16, tzinfo=UTC),
    timezone="Asia/Shanghai",
    precision="day",
    original_text="昨天",
    anchor=datetime(2026, 9, 16, 1, 41, tzinfo=UTC),
)
RESEARCH_CAPABILITY = "operation.research.insight"


class _IntentInterpreter:
    async def execute(self, text, context, previous, catalog, lease):
        del previous
        span = SourceSpan(
            message_id=context.current_message_id,
            start=0,
            end=len(text),
            quoted_text=text,
        )
        patch = IntentPatchV2(
            base_revision=0,
            dialog_act="new_task",
            goal_updates=(
                GoalNodeV2(
                    goal_id="goal-research",
                    description="收集昨天 AI 行业新闻",
                    candidate_capability_ids=(RESEARCH_CAPABILITY,),
                    parameters=(IntentParameterV2(name="count", value=5),),
                ),
            ),
            field_operations=(
                FieldOperation(
                    operation="set",
                    field_name="topic",
                    value=FieldValue(
                        value="AI 行业新闻", origin="explicit", source_span=span
                    ),
                ),
                FieldOperation(
                    operation="set",
                    field_name="temporal",
                    value=FieldValue(
                        value=CalendarPeriodExpression(
                            text="昨天", period="day", offset=-1
                        ),
                        origin="explicit",
                        source_span=span,
                    ),
                ),
                FieldOperation(
                    operation="set",
                    field_name="source_constraints",
                    value=FieldValue(
                        value=SourceConstraintsV2(allowed_source_ids=("source-free",)),
                        origin="explicit",
                        source_span=span,
                    ),
                ),
                FieldOperation(
                    operation="set",
                    field_name="output_requirements",
                    value=FieldValue(
                        value=OutputRequirementsV2(
                            output_types=("digest",), language="zh-CN"
                        ),
                        origin="explicit",
                        source_span=span,
                    ),
                ),
            ),
        )
        return IntentInterpretationV2Execution(
            patch=patch,
            usage=UsageSnapshot(input_tokens=10, output_tokens=5),
            degraded=False,
            attempts=(),
            provider_calls=1,
            repair_attempted=False,
            review_attempted=False,
            review_applied=False,
            prompt_versions=("intent.v2.interpret@2.0.0",),
            catalog_version=catalog.catalog_version,
            context_version=context.context_version,
            lease_id=lease.lease_id,
            lease_version=lease.version,
        )


class _FreeSourceProvider:
    def __init__(self) -> None:
        self.calls = []

    async def discover(self, request):
        self.calls.append(request)
        counts = (3, 1, 0)
        count = counts[len(self.calls) - 1]
        start = sum(counts[: len(self.calls) - 1]) + 1
        candidates = tuple(_candidate(index) for index in range(start, start + count))
        now = datetime(2026, 9, 15, 12, tzinfo=UTC)
        return DiscoveryBatchV2(
            request_id=request.request_id,
            candidates=candidates,
            completeness="complete",
            coverage="complete",
            attempts=(
                SourceAttemptV2(
                    attempt_id=f"attempt-{len(self.calls)}",
                    action_id=request.request_id,
                    source_id=request.source_id,
                    status="success" if count else "success_empty",
                    started_at=now,
                    finished_at=now,
                    returned_count=count,
                    filtered_count=0,
                    coverage="complete",
                    lease_id=request.lease_id,
                    usage=SourceUsageV2(
                        requests=1,
                        returned_items=count,
                        downloaded_bytes=count * 100,
                    ),
                ),
            ),
        )


class _UnusedFetcher:
    async def fetch(self, request):
        raise AssertionError(f"unexpected fetch: {request.request_id}")


class _AnyScopeResolver:
    async def resolve(self, context, source_id):
        del context, source_id
        return TrustedResearchToolScope("lease-x03", "d" * 64)


class _StageRunner:
    def __init__(self, acquisition: AcquisitionExecutor, run_holder: dict[str, str]):
        self.acquisition = acquisition
        self.run_holder = run_holder
        self.round = 0
        self.candidate_ids: list[str] = []

    async def run_stage(self, stage, state):
        if stage == "plan":
            self.round += 1
            return ResearchStageUpdateV2(planned_action_ids=(f"action-{self.round}",))
        if stage == "acquire":
            action = DiscoveryActionV2(
                f"action-{self.round}",
                ResearchDiscoverArgumentsV2(
                    request_id=f"request-source-{self.round}",
                    source_id="source-free",
                    brief_digest=state["brief_digest"],
                    query="AI 行业新闻",
                    time_window=WINDOW,
                    limit=5,
                ),
            )
            result = await self.acquisition.execute_discovery(
                action,
                AcquisitionRuntimeContextV2(
                    run_context=RunContext(
                        self.run_holder["run_id"],
                        "tenant-1",
                        "user-1",
                        "trace-x03",
                    ),
                    allowed_source_ids=frozenset({"source-free"}),
                    granted_permissions=frozenset({"research:read"}),
                    remaining_budget=RemainingBudget(20, 10, 10_000, 10_000, 1, 60_000),
                    deadline_monotonic=time.monotonic() + 30,
                    max_attempts=1,
                ),
            )
            assert result.batch is not None
            self.candidate_ids.extend(
                item.candidate_id for item in result.batch.candidates
            )
            document_ids = tuple(
                item.replace("candidate", "doc") for item in self.candidate_ids
            )
            return ResearchStageUpdateV2(
                candidate_ids=tuple(self.candidate_ids),
                acquired_document_ids=document_ids,
            )
        document_ids = tuple(
            item.replace("candidate", "doc") for item in self.candidate_ids
        )
        event_ids = tuple(
            item.replace("candidate", "event") for item in self.candidate_ids
        )
        claim_ids = tuple(
            item.replace("candidate", "claim") for item in self.candidate_ids
        )
        evidence_ids = tuple(
            build_evidence_ref(item, 0, len(item.text)).evidence_id
            for item in _documents()[: len(self.candidate_ids)]
        )
        updates = {
            "normalize": ResearchStageUpdateV2(normalized_document_ids=document_ids),
            "filter": ResearchStageUpdateV2(filtered_document_ids=document_ids),
            "deduplicate": ResearchStageUpdateV2(
                deduplicated_document_ids=document_ids
            ),
            "cluster": ResearchStageUpdateV2(event_ids=event_ids),
            "claims": ResearchStageUpdateV2(
                claim_ids=claim_ids, evidence_ids=evidence_ids
            ),
            "quality": ResearchStageUpdateV2(
                qualified_event_ids=event_ids,
                quality_report_id=f"quality-{self.round}",
                hard_gap_ids=("gap-count",),
            ),
        }
        return updates.get(stage, ResearchStageUpdateV2())


class _Materializer:
    async def materialize(self, brief, state):
        snapshot = _snapshot(brief)
        gaps = (
            QualityGapV2(
                gap_id="gap-count",
                requirement_id="count_policy",
                code="COUNT_EXACT_UNMET",
                detail="精确 5 条仅获得 4 条",
                recoverable=True,
            ),
        )
        base = ResearchOutcomeV2(
            outcome="PARTIAL",
            usable_event_ids=tuple(item.event_id for item in snapshot.events),
            evidence_ids=tuple(item.evidence_id for item in snapshot.evidence_refs),
            gaps=gaps,
            stop_reason="ROUND_LIMIT",
            usage=ResearchUsageV2(
                source_requests=3, model_calls=0, downloaded_bytes=400
            ),
        )
        return base.model_copy(
            update={"delivery": DeliveryPackBuilder().build(brief, base, snapshot)}
        )


class _ContentProvider:
    descriptor = None

    async def complete(self, request):
        payload = json.loads(request.messages[-1].content)
        result = {
            "platform": payload["platform"],
            "title": "AI 行业新闻简报",
            "body": "已整理 4 条带来源的昨日 AI 行业新闻。",
            "hashtags": [],
            "format_notes": ["精确 5 条未满足"],
            "citations": payload["citations"],
            "warnings": ["ROUND_LIMIT"],
        }
        return ProviderResult(
            "operation-model/1",
            ProviderMessage("assistant", json.dumps(result, ensure_ascii=False)),
            ProviderUsage(10, 20, 0, 0, 0),
        )


class _RecordingResearchService:
    def __init__(self, delegate):
        self.delegate = delegate
        self.error = None
        self.outcome = None

    async def research(self, brief, runtime_context):
        try:
            self.outcome = await self.delegate.research(brief, runtime_context)
            return self.outcome
        except Exception as error:
            self.error = error
            raise


@pytest.mark.asyncio
async def test_exact_five_delivers_four_without_date_expansion() -> None:
    source_provider = _FreeSourceProvider()
    source_registry = ExplicitSourceProviderRegistry({"source-free": source_provider})
    tool_registry = ToolRegistry()
    tool_runtime = ToolRuntime(tool_registry)
    for spec, tool in research_tool_entries(
        source_registry,
        ExplicitDocumentFetcherRegistry({"source-free": _UnusedFetcher()}),
        _AnyScopeResolver(),
    ):
        tool_registry.register(spec, tool)
    run_holder: dict[str, str] = {}
    acquisition = AcquisitionExecutor(
        tool_runtime,
        InMemorySourceAttemptLedger(),
    )
    policy = offline_research_quality_policy()
    graph_service = LangGraphResearchServiceV2(
        policy=policy,
        budget=BudgetSnapshotV2(
            lease_id="lease-x03", version=1, remaining_calls=10, remaining_bytes=10_000
        ),
        stage_runner=_StageRunner(acquisition, run_holder),
        materializer=_Materializer(),
        now=lambda: ANCHOR,
    )
    service = _RecordingResearchService(graph_service)
    intent_repository = InMemoryIntentTaskRepositoryV2()
    intent_pipeline = IntentPipelineV2(
        repository=intent_repository,
        interpreter=_IntentInterpreter(),
        validator=IntentPatchValidator(),
        reducer=IntentStateReducer(),
        temporal_resolver=TemporalResolver(),
        binder=CapabilityBinderV2(build_operation_parameter_schema_registry()),
        decision_policy=IntentDecisionPolicyV2(),
        brief_builder=ResearchBriefBuilderV2(),
        scenario_adapter=ScenarioInputAdapter(),
    )
    input_factory = InMemoryIntentV2TrustedInputFactory(
        catalog=build_operation_semantic_catalog(),
        policy=policy,
        lease_factory=lambda pipeline: _bind_run(run_holder, pipeline.run_id),
        now=lambda: ANCHOR,
    )
    brief_store = InMemoryResearchBriefStoreV2()
    submissions = ConversationSubmissionStore()
    delegate = IntentV2RunPreparationDelegate(
        intent_pipeline=intent_pipeline,
        input_factory=input_factory,
        submission_builder=ResearchScenarioSubmissionBuilderV2(
            InMemoryScenarioPackRegistry(build_s6_manifests())
        ),
        submissions=submissions,
        source_registry=source_registry,
        tool_runtime=tool_runtime,
        research_service=service,
        intent_state_store=intent_repository,
        research_state_store=brief_store,
    )
    settings = ResearchPipelineSettings(
        intent_pipeline_version="intent-v2",
        research_pipeline_version="research-v2",
        research_replan_enabled=True,
        research_source_allowlist=("source-free",),
        research_policy_version=policy.policy_version,
        state_backend="memory",
    )
    application = build_local_agent_application(
        synthetic_settings(),
        provider=_ContentProvider(),
        test_mode=True,
        research_v2_settings=settings,
        intent_v2_delegate=delegate,
        research_v2_source_registry=source_registry,
        research_v2_tool_runtime=tool_runtime,
        research_service_v2=service,
        intent_v2_state_store=intent_repository,
        research_v2_state_store=brief_store,
    )

    submitted = await application.conversation.submit(
        "conversation-x03",
        "tenant-1",
        ConversationMessageV1(
            message="收集昨天 AI 行业新闻，选 5 条",
            request_id="request-x03",
            user_id="user-1",
        ),
    )
    await application.runtime.wait_for_background_tasks()
    run = await application.runtime.get_run(submitted.run_id, "tenant-1")
    events = await application.runtime.list_events(submitted.run_id, "tenant-1")

    if service.error is not None:
        raise service.error
    assert run.status is RunStatus.SUCCEEDED, (run.error, run.output, service.error)
    assert len(source_provider.calls) == 3
    assert all(call.time_window == WINDOW for call in source_provider.calls)
    assert service.outcome is not None
    assert service.outcome.outcome == "PARTIAL"
    assert service.outcome.stop_reason == "ROUND_LIMIT"
    assert service.outcome.delivery is not None
    assert service.outcome.delivery.delivered_event_count == 4
    assert all(event.citations for event in service.outcome.delivery.events)
    assert run.output is not None
    assert "4 条" in str(run.output)
    assert isinstance(run.output, dict)
    output = run.output
    assert output["delivery_contract_version"] == "deliverable-set/2"
    value = output["deliverable_set"]
    assert value["degraded"] is True
    assert value["summary"]["complete"] is False
    assert len(value["deliverables"][0]["content"]["items"]) == 4
    assert value["warnings"][0]["code"] == "RESEARCH_TARGET_NOT_REACHED"
    assert "精确 5 条仅获得 4 条" in value["warnings"][0]["message"]
    assert value["provenance"]["source_count"] == 4
    assert value["provenance"][
        "collection_window_start"
    ] == WINDOW.start.isoformat().replace("+00:00", "Z")
    assert tuple(event.event_type for event in events) == (
        "run_created",
        "run_queued",
        "strategy_selected",
        "run_started",
        "checkpoint_saved",
        "run_succeeded",
    )
    await application.close()


def _bind_run(run_holder: dict[str, str], run_id: str) -> BudgetLeaseReferenceV2:
    run_holder["run_id"] = run_id
    return BudgetLeaseReferenceV2(lease_id="lease-x03", version=1)


def _candidate(index: int) -> CandidateRecordV2:
    return CandidateRecordV2(
        candidate_id=f"candidate-{index}",
        source_id="source-free",
        source_item_id=f"item-{index}",
        url=f"https://official.example/news/{index}",
        title=f"AI 新闻 {index}",
        raw_published_at=f"2026-09-15T0{index}:00:00+08:00",
        timestamp_semantics="published",
        discovered_via="rss",
        content_scope="full",
        inline_content=f"机构 {index} 发布了可核验的 AI 新闻。",
    )


def _snapshot(brief) -> EvidenceSnapshotV2:
    documents = _documents()
    refs = tuple(build_evidence_ref(item, 0, len(item.text)) for item in documents)
    events = tuple(
        EventClusterV2(
            event_id=f"event-{index}",
            event_type="announcement",
            entity_names=(f"机构 {index}",),
            event_time=documents[index - 1].published_at,
            member_document_ids=(f"doc-{index}",),
            representative_document_id=f"doc-{index}",
            merge_basis=("独立事件",),
            cluster_confidence="confirmed",
        )
        for index in range(1, 5)
    )
    claims = tuple(
        ClaimRecordV2(
            claim_id=f"claim-{index}",
            claim_key=f"announcement-{index}",
            event_id=f"event-{index}",
            text=f"机构 {index} 发布了可核验的 AI 新闻。",
            claim_type="announcement",
            subject=f"机构 {index}",
            assertion_mode="objective",
            support_refs=(refs[index - 1].evidence_id,),
            source_family_ids=(f"family-{index}",),
            independent_support_count=1,
        )
        for index in range(1, 5)
    )
    return EvidenceSnapshotV2(
        snapshot_id="snapshot-x03",
        brief_digest=brief.canonical_digest(),
        documents=documents,
        events=events,
        claims=claims,
        evidence_refs=refs,
        coverage=CoverageSnapshotV2(
            required_facets=(),
            covered_facets=(),
            missing_facets=(),
            historical_coverage="complete",
        ),
    )


def _documents() -> tuple[SourceDocumentV2, ...]:
    return tuple(
        SourceDocumentV2(
            document_id=f"doc-{index}",
            candidate_id=f"candidate-{index}",
            source_id="source-free",
            source_item_id=f"item-{index}",
            original_url=f"https://official.example/news/{index}",
            canonical_url=f"https://official.example/news/{index}",
            publisher_id="official.example",
            title=f"AI 新闻 {index}",
            text=f"机构 {index} 发布了可核验的 AI 新闻。",
            content_hash=f"{index}" * 64,
            artifact_ref=f"artifact:{index}",
            discovered_via="rss",
            content_scope="full",
            published_at=datetime(2026, 9, 15, index, tzinfo=UTC),
            published_timezone_known=True,
            time_precision="exact",
            extractor_version="extractor/2",
            source_role="primary",
        )
        for index in range(1, 5)
    )
