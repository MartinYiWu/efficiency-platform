"""运营主链真实组件的离线集成，模型边界使用明确的固定替身。"""

import json
from dataclasses import replace

import pytest

from efficiency_platform_agent.capabilities.model.runtime import ModelRuntime
from efficiency_platform_agent.core.model import ModelCandidate, ModelTier
from efficiency_platform_agent.core.run import (
    ProviderMessage,
    ProviderResult,
    ProviderUsage,
)
from efficiency_platform_agent.core.runtime import UsageSnapshot
from efficiency_platform_agent.providers.llm.registry import ModelProviderRegistry
from tests.support.s6_scenario_samples import sample_by_id, submission_from_sample


class ResearchProvider:
    """返回固定可信来源的离线研究端口。"""

    def __init__(self):
        self.calls = []

    async def research(self, request):
        self.calls.append(request)
        from efficiency_platform_agent.agents.operation.contracts.evidence import (
            EvidenceDuplicateStatus,
            EvidenceQualityStatus,
        )
        from efficiency_platform_agent.agents.operation.contracts.task import (
            SourceScope,
        )
        from efficiency_platform_agent.capabilities.research.contracts import (
            ResearchObservation,
            ResearchResult,
            ResearchStatus,
        )

        return ResearchResult(
            "research-result/1",
            request.request_id,
            request.task_id,
            request.tenant_id,
            ResearchStatus.SUCCEEDED,
            (
                ResearchObservation(
                    "observation-source-1",
                    "行业来源",
                    "公开机构",
                    "https://example.com/source",
                    1,
                    2,
                    SourceScope.EXTERNAL_REFERENCE,
                    frozenset(request.expected_conclusion_ids),
                    True,
                    EvidenceDuplicateStatus.UNIQUE,
                    EvidenceQualityStatus.VALID,
                ),
            ),
            (),
            None,
        )


class ContentProvider:
    """按平台生成独立输出，可指定一次平台故障或非法输出。"""

    descriptor = None

    def __init__(self, failure=None, extra=False):
        self.failure = failure
        self.extra = extra
        self.calls = []

    async def complete(self, request):
        value = json.loads(request.messages[-1].content)
        self.calls.append(value)
        if value["platform"] == self.failure:
            raise RuntimeError("离线故障")
        result = {
            "platform": value["platform"],
            "title": value["platform"] + " 新品发布",
            "body": value["platform"] + " 专属内容。\n\n面向该渠道的独立方案。",
            "hashtags": ["新品"],
            "format_notes": ["按平台分段"],
            "citations": value.get("citations", []),
            "warnings": [],
        }
        if self.extra:
            result["hidden_reasoning"] = "禁止输出"
        return ProviderResult(
            "operation-model/1",
            ProviderMessage("assistant", json.dumps(result)),
            ProviderUsage(10, 20, 0, 0, 0),
        )


class Selector:
    def candidates(self, *_args, **_kwargs):
        return (
            ModelCandidate(
                "offline",
                "offline",
                "offline",
                ModelTier.BALANCED,
                True,
                False,
                100000,
                True,
                False,
            ),
        )


def build_agent(provider):
    from efficiency_platform_agent.harness.operation_agent_factory import (
        build_operation_agent,
    )

    registry = ModelProviderRegistry()
    registry.register("offline", provider)
    return build_operation_agent(ModelRuntime(Selector(), registry))


def build_research_agent(provider):
    from efficiency_platform_agent.harness.operation_agent_factory import (
        build_operation_agent,
    )

    registry = ModelProviderRegistry()
    registry.register("offline", provider)
    research = ResearchProvider()
    agent = build_operation_agent(
        ModelRuntime(Selector(), registry), research_provider=research
    )
    agent._test_research_provider = research
    return agent


async def test_research_specialist_uses_provider_sources_and_model_output():
    provider = ContentProvider()
    source = submission_from_sample(sample_by_id("industry_digest.complete/1"))
    result = await build_research_agent(provider).handle(source)
    assert result.deliverables[0].citations[0].url == "https://example.com/source"
    assert result.degraded is False
    assert provider.calls[0]["citations"][0]["url"] == "https://example.com/source"


async def test_large_server_search_usage_keeps_industry_digest_generation_alive():
    """研究 Specialist 不应把服务端搜索上下文误判为生成预算耗尽。"""

    class LargeUsageResearch(ResearchProvider):
        async def research(self, request):
            return replace(
                await super().research(request),
                usage=UsageSnapshot(300_000, 11_267, 0, True),
            )

    from efficiency_platform_agent.harness.operation_agent_factory import (
        build_operation_agent,
    )

    provider = ContentProvider()
    registry = ModelProviderRegistry()
    registry.register("offline", provider)
    agent = build_operation_agent(
        ModelRuntime(Selector(), registry),
        research_provider=LargeUsageResearch(),
    )
    source = submission_from_sample(sample_by_id("industry_digest.complete/1"))

    execution = await agent.execute(source)

    assert execution.deliverables is not None


def test_industry_digest_research_step_has_search_chain_timeout_budget():
    """行业研究步骤的超时预算必须覆盖一次完整服务端搜索链。"""

    from efficiency_platform_agent.agents.operation.scenarios.manifests import (
        INDUSTRY_DIGEST_PACK_V1,
    )

    assert INDUSTRY_DIGEST_PACK_V1.plan_template.steps[0].budget.timeout_ms == 240_000


async def test_unverified_provider_source_remains_citation_with_warning():
    class UnverifiedResearch(ResearchProvider):
        async def research(self, request):
            result = await super().research(request)
            observation = replace(
                result.observations[0],
                quality_status=__import__(
                    "efficiency_platform_agent.agents.operation.contracts.evidence",
                    fromlist=["EvidenceQualityStatus"],
                ).EvidenceQualityStatus.UNVERIFIED,
            )
            return replace(result, observations=(observation,))

    provider = ContentProvider()
    source = submission_from_sample(sample_by_id("industry_digest.complete/1"))
    from efficiency_platform_agent.harness.operation_agent_factory import (
        build_operation_agent,
    )

    registry = ModelProviderRegistry()
    registry.register("offline", provider)
    agent = build_operation_agent(
        ModelRuntime(Selector(), registry), research_provider=UnverifiedResearch()
    )
    result = await agent.handle(source)
    assert result.deliverables[0].citations[0].url == "https://example.com/source"
    assert "EVIDENCE_UNVERIFIED" in result.deliverables[0].warnings


def submission():
    source = submission_from_sample(sample_by_id("multi_platform_content.complete/1"))
    requirement = replace(
        source.request.requested_deliverables[0],
        channel_ids=("xiaohongshu", "wechat_official_account", "toutiao"),
    )
    return replace(
        source, request=replace(source.request, requested_deliverables=(requirement,))
    )


async def test_three_platforms_generate_three_independent_deliverables():
    provider = ContentProvider()
    result = await build_agent(provider).handle(submission())
    assert {item.platform for item in result.deliverables} == {
        "xiaohongshu",
        "wechat_official_account",
        "toutiao",
    }
    assert len({item.body for item in result.deliverables}) == 3
    assert len(provider.calls) == 3
    # 固定样本没有权威渠道 Profile，启用质量门后必须披露该缺口。
    assert result.degraded


async def test_one_specialist_failure_preserves_other_platforms():
    result = await build_agent(ContentProvider(failure="toutiao")).handle(submission())
    assert len(result.deliverables) == 2
    assert result.degraded
    assert "toutiao" in result.summary


async def test_unknown_model_fields_fail_closed():
    with pytest.raises(ValueError, match="OPERATION_ALL_SPECIALISTS_FAILED"):
        await build_agent(ContentProvider(extra=True)).handle(submission())


def test_assembler_rejects_unknown_nested_citation_field():
    from efficiency_platform_agent.capabilities.quality.deliverable_assembler import (
        DeliverableAssembler,
    )

    with pytest.raises(ValueError):
        DeliverableAssembler().assemble(
            [
                {
                    "platform": "research",
                    "title": "研究",
                    "body": "结果",
                    "citations": [{"url": "https://example.com", "secret": "拒绝"}],
                }
            ]
        )


def test_assembler_rejects_duplicate_platform_content():
    from efficiency_platform_agent.capabilities.quality.deliverable_assembler import (
        DeliverableAssembler,
    )

    result = DeliverableAssembler().assemble(
        [
            {"platform": platform, "title": "同题", "body": "完全复制正文"}
            for platform in ("xiaohongshu", "toutiao")
        ]
    )
    assert result.degraded
    assert any(
        "DUPLICATE_PLATFORM_CONTENT" in item.warnings for item in result.deliverables
    )


async def test_research_keeps_only_verified_evidence_citations():
    from efficiency_platform_agent.agents.operation.contracts.evidence import (
        EvidenceDuplicateStatus,
        EvidencePack,
        EvidenceQualityStatus,
        EvidenceRecord,
    )
    from efficiency_platform_agent.agents.operation.contracts.task import SourceScope

    source = submission_from_sample(sample_by_id("industry_digest.complete/1"))
    evidence = EvidenceRecord(
        "source-1",
        "行业公告",
        "公开机构",
        "https://example.com/report",
        1000,
        2000,
        SourceScope.EXTERNAL_REFERENCE,
        frozenset({"conclusion-1"}),
        True,
        EvidenceDuplicateStatus.UNIQUE,
        EvidenceQualityStatus.VALID,
    )
    source = replace(
        source,
        evidence_pack=EvidencePack(
            "evidence-pack/1", "evidence-1", source.task_spec.task_id, (evidence,), ()
        ),
    )
    result = await build_research_agent(ContentProvider()).handle(source)
    assert result.deliverables[0].citations
    assert (
        result.deliverables[0].citations[0].url
        == "https://example.com/source"
    )


async def test_research_injects_verified_citation_when_model_omits_citations():
    """模型未回填引用时，研究证据仍必须进入最终成品。"""

    class CitationOmittingProvider(ContentProvider):
        async def complete(self, request):
            result = await super().complete(request)
            payload = json.loads(result.message.content)
            payload["citations"] = []
            return replace(
                result,
                message=ProviderMessage("assistant", json.dumps(payload)),
            )

    source = submission_from_sample(sample_by_id("industry_digest.complete/1"))
    result = await build_research_agent(CitationOmittingProvider()).handle(source)

    assert result.deliverables[0].citations


async def test_registered_operation_graph_uses_existing_graph_runtime():
    from efficiency_platform_agent.core.enums import RunStatus, StrategyMode
    from efficiency_platform_agent.core.run import JsonObject
    from efficiency_platform_agent.orchestration.builders.operation_runtime import (
        build_operation_multi_agent_registration,
    )
    from efficiency_platform_agent.orchestration.registry import GraphRegistry
    from efficiency_platform_agent.orchestration.runtime import GraphRuntime
    from efficiency_platform_agent.routing.strategy_router import StrategySelection

    source = submission()

    async def resolve(request, state):
        assert request.operation_id == source.request.operation_id
        return source

    registry = GraphRegistry()
    registry.register(
        build_operation_multi_agent_registration(
            build_agent(ContentProvider()), resolve
        )
    )
    runtime = GraphRuntime(registry)
    result = await runtime.execute(
        StrategySelection(StrategyMode.MULTI_AGENT, "operation", "test"),
        {
            "run_id": "run-task-e",
            "tenant_id": source.task_spec.tenant_id,
            "user_id": source.task_spec.user_id,
            "request_id": source.request.request.request_id,
            "strategy_payload_schema_version": "operation-strategy-payload/1",
            "strategy_payload": JsonObject(
                (
                    (
                        "operation_request",
                        JsonObject(
                            (
                                ("operation_id", source.request.operation_id),
                                (
                                    "request",
                                    JsonObject(
                                        (
                                            (
                                                "request_id",
                                                source.request.request.request_id,
                                            ),
                                            ("tenant_id", source.task_spec.tenant_id),
                                            ("user_id", source.task_spec.user_id),
                                            ("input_text", "新品三平台文案"),
                                        )
                                    ),
                                ),
                            )
                        ),
                    ),
                )
            ),
        },
    )
    assert result.next_status is RunStatus.SUCCEEDED
    assert result.usage.input_tokens == 30
    assert result.usage.output_tokens == 60
    assert dict(result.output.items)["quality_report"] is not None
    assert "q.channel-independence/1" in dict(
        dict(result.output.items)["quality_check_report_ids"].items
    )
    assert (
        len(dict(dict(result.output.items)["deliverable_set"].items)["deliverables"])
        == 3
    )


async def test_missing_research_provider_fails_transparently():
    source = submission_from_sample(sample_by_id("industry_digest.complete/1"))
    with pytest.raises(ValueError, match="RESEARCH_UNAVAILABLE"):
        await build_agent(ContentProvider()).handle(source)


async def test_failed_research_is_not_reclassified_as_budget_exhausted():
    """研究无来源时，即使供应商 usage 异常偏大，也必须保持研究错误码。"""

    class InsufficientResearch(ResearchProvider):
        async def research(self, request):
            from efficiency_platform_agent.capabilities.research.contracts import (
                ResearchResult,
                ResearchStatus,
            )

            return ResearchResult(
                "research-result/1",
                request.request_id,
                request.task_id,
                request.tenant_id,
                ResearchStatus.FAILED,
                (),
                (),
                "RESEARCH_INSUFFICIENT",
                UsageSnapshot(300_000, 0, 0, True),
            )

    source = submission_from_sample(sample_by_id("industry_digest.complete/1"))
    from efficiency_platform_agent.harness.operation_agent_factory import (
        build_operation_agent,
    )

    execution = await build_operation_agent(
        ModelRuntime(Selector(), ModelProviderRegistry()),
        research_provider=InsufficientResearch(),
    ).execute(source)

    assert execution.error_code == "RESEARCH_UNAVAILABLE"
    assert execution.deliverables is None


async def test_single_platform_request_does_not_generate_other_platforms():
    source = submission()
    requirement = replace(
        source.request.requested_deliverables[0], channel_ids=("toutiao",)
    )
    source = replace(
        source, request=replace(source.request, requested_deliverables=(requirement,))
    )
    result = await build_agent(ContentProvider()).handle(source)
    assert [item.platform for item in result.deliverables] == ["toutiao"]


def test_quality_ids_are_collision_free_and_keep_original_metadata():
    from efficiency_platform_agent.agents.operation.contracts.profiles import (
        select_profiles_for_task,
    )
    from efficiency_platform_agent.agents.operation.contracts.scenarios import (
        compile_scenario_plan,
    )
    from efficiency_platform_agent.agents.operation.scenarios.manifests import (
        MULTI_PLATFORM_CONTENT_PACK_V1,
    )
    from efficiency_platform_agent.orchestration.supervisor import compile_runtime_plan

    source = submission()
    context = select_profiles_for_task(source.task_spec, ())
    plan = compile_scenario_plan(
        MULTI_PLATFORM_CONTENT_PACK_V1, source.task_spec, context, source.plan_id
    )
    original = frozenset({"q.test/1", "q.test.v1"})
    plan = replace(plan, steps=(replace(plan.steps[0], quality_check_ids=original),))
    graph = compile_runtime_plan(plan)
    assert len(graph.tasks[0].quality_check_ids) == 2
    assert (
        set(dict(graph.tasks[0].context_view.items)["original_quality_check_ids"])
        == original
    )
    assert plan.steps[0].quality_check_ids == original


async def test_fabricated_model_citations_are_rejected():
    class FabricatedProvider(ContentProvider):
        async def complete(self, request):
            result = await super().complete(request)
            data = json.loads(result.message.content)
            data["citations"] = [{"url": "https://invented.example/source"}]
            return replace(
                result, message=ProviderMessage("assistant", json.dumps(data))
            )

    with pytest.raises(ValueError, match="OPERATION_ALL_SPECIALISTS_FAILED"):
        await build_agent(FabricatedProvider()).handle(submission())


async def test_failed_specialist_output_still_counts_provider_usage():
    result = await build_agent(ContentProvider(extra=True)).execute(submission())
    assert result.deliverables is None
    assert result.usage.input_tokens == 30
    assert result.usage.output_tokens == 60


async def test_provider_failure_attempt_is_counted_in_partial_result():
    from efficiency_platform_agent.core.run import ProviderError

    class BilledFailureProvider(ContentProvider):
        async def complete(self, request):
            if json.loads(request.messages[-1].content)["platform"] == "toutiao":
                return ProviderResult(
                    "operation-model/1",
                    None,
                    ProviderUsage(10, 20, 0, 0, 0),
                    ProviderError(
                        "PROVIDER_INVALID_RESPONSE", "provider", False, "离线失败"
                    ),
                )
            return await super().complete(request)

    result = await build_agent(BilledFailureProvider()).execute(submission())
    assert result.deliverables.degraded
    assert len(result.deliverables.deliverables) == 2
    assert result.usage.input_tokens == 30
    assert result.usage.output_tokens == 60


async def test_run_view_receives_nonzero_model_usage():
    from efficiency_platform_agent.contracts.requests import CreateRunRequestV1
    from efficiency_platform_agent.core.enums import StrategyMode
    from efficiency_platform_agent.harness.factory import build_s2_test_service
    from efficiency_platform_agent.orchestration.builders.operation_runtime import (
        build_operation_multi_agent_registration,
    )
    from efficiency_platform_agent.orchestration.registry import GraphRegistry
    from efficiency_platform_agent.orchestration.runtime import GraphRuntime
    from efficiency_platform_agent.routing.strategy_router import StrategyRouter

    source = submission()

    async def resolve(request, state):
        return source

    registry = GraphRegistry()
    registry.register(
        build_operation_multi_agent_registration(
            build_agent(ContentProvider()), resolve
        )
    )
    service = build_s2_test_service()
    service.graph_runtime = GraphRuntime(registry)
    service.router = StrategyRouter(registry.available_modes())
    request = CreateRunRequestV1(
        request_id=source.request.request.request_id,
        tenant_id=source.task_spec.tenant_id,
        user_id=source.task_spec.user_id,
        input_text="三平台新品文案",
        requested_strategy=StrategyMode.MULTI_AGENT,
        strategy_payload_schema_version="operation-strategy-payload/1",
        strategy_payload={
            "operation_request": {
                "operation_id": source.request.operation_id,
                "request": {
                    "request_id": source.request.request.request_id,
                    "tenant_id": source.task_spec.tenant_id,
                    "user_id": source.task_spec.user_id,
                    "input_text": "三平台新品文案",
                },
            }
        },
    )
    result = await service.create_and_execute(request)
    assert result.status.value == "succeeded"
    assert result.usage.input_tokens == 30
    assert result.usage.output_tokens == 60


async def test_unknown_platform_is_not_silently_dropped():
    source = submission()
    requirement = replace(
        source.request.requested_deliverables[0],
        channel_ids=("toutiao", "unknown_channel"),
    )
    source = replace(
        source, request=replace(source.request, requested_deliverables=(requirement,))
    )
    with pytest.raises(ValueError, match="OPERATION_PLATFORM_UNSUPPORTED"):
        await build_agent(ContentProvider()).handle(source)


async def test_concurrent_runs_keep_usage_isolated():
    import asyncio

    agent = build_agent(ContentProvider())
    results = await asyncio.gather(
        agent.execute(submission(), run_id="run-a"),
        agent.execute(submission(), run_id="run-b"),
    )
    assert [result.usage.input_tokens for result in results] == [30, 30]
    assert [result.usage.output_tokens for result in results] == [60, 60]


async def test_quality_gate_executes_and_reports_keep_authoritative_ids():
    from efficiency_platform_agent.agents.operation.scenarios.manifests import (
        MULTI_PLATFORM_CONTENT_PACK_V1,
    )

    agent = build_agent(ContentProvider())
    seen = []
    gate = agent.quality_gate

    class RecordingGate:
        def validate(self, manifest, result):
            seen.append(result)
            return gate.validate(manifest, result)

    agent.quality_gate = RecordingGate()
    execution = await agent.execute(submission())
    assert len(seen) == 1
    result = execution.scenario_result
    assert seen[0].quality_report is not None
    assert result.quality_report is not None
    assert (
        result.quality_report.report_id in result.deliverable_bundle.quality_report_ids
    )
    assert len(result.deliverable_bundle.quality_report_ids) >= 4
    messages = "\n".join(check.safe_message for check in result.quality_report.checks)
    assert all(
        check_id in messages
        for check_id in MULTI_PLATFORM_CONTENT_PACK_V1.quality_check_ids
    )
    assert (
        set(execution.quality_check_report_ids)
        == MULTI_PLATFORM_CONTENT_PACK_V1.quality_check_ids
    )
    assert all(
        report_id in result.deliverable_bundle.quality_report_ids
        for report_id in execution.quality_check_report_ids.values()
    )
    assert not any(
        report_id.startswith("q-")
        for report_id in result.deliverable_bundle.quality_report_ids
    )


async def test_quality_failure_blocks_deliverables_instead_of_only_warning():
    from efficiency_platform_agent.agents.operation.contracts.deliverables import (
        QualityStatus,
    )
    from efficiency_platform_agent.core.multi_agent import CompletionStatus

    agent = build_agent(ContentProvider())
    gate = agent.quality_gate

    class FailingGate:
        def validate(self, manifest, result):
            return replace(
                gate.validate(manifest, result), final_status=QualityStatus.FAILED
            )

    agent.quality_gate = FailingGate()
    execution = await agent.execute(submission())
    assert execution.status is CompletionStatus.FAILED
    assert execution.deliverables is None
    assert execution.scenario_result.quality_report.final_status is QualityStatus.FAILED


async def test_running_cancellation_stops_dependent_specialists():
    import asyncio

    from efficiency_platform_agent.agents.operation.scenarios.manifests import (
        MULTI_PLATFORM_CONTENT_PACK_V1,
    )
    from efficiency_platform_agent.agents.operation.scenarios.registry import (
        InMemoryScenarioPackRegistry,
    )
    from efficiency_platform_agent.core.multi_agent import CompletionStatus
    from efficiency_platform_agent.harness.operation_agent_factory import (
        build_operation_agent,
    )
    from efficiency_platform_agent.orchestration.cancellation import (
        InMemoryCancellationSignal,
    )

    started = asyncio.Event()
    calls = []

    class WaitingProvider(ContentProvider):
        async def complete(self, request):
            calls.append(json.loads(request.messages[-1].content)["platform"])
            started.set()
            await asyncio.Event().wait()

    provider_registry = ModelProviderRegistry()
    provider_registry.register("offline", WaitingProvider())
    cancellation = InMemoryCancellationSignal()
    agent = build_operation_agent(
        ModelRuntime(Selector(), provider_registry), cancellation=cancellation
    )
    manifest = MULTI_PLATFORM_CONTENT_PACK_V1
    steps = manifest.plan_template.steps
    chained = (
        steps[0],
        replace(steps[1], depends_on_step_ids=(steps[0].step_id,)),
        replace(steps[2], depends_on_step_ids=(steps[1].step_id,)),
    )
    agent.scenarios = InMemoryScenarioPackRegistry(
        (
            replace(
                manifest, plan_template=replace(manifest.plan_template, steps=chained)
            ),
        )
    )
    pending = asyncio.create_task(agent.execute(submission(), run_id="run-cancel-e"))
    await asyncio.wait_for(started.wait(), 2)
    await cancellation.request("run-cancel-e")
    result = await asyncio.wait_for(pending, 2)
    assert result.status is CompletionStatus.CANCELLED
    assert result.deliverables is None
    assert calls == ["xiaohongshu"]


def test_runtime_warning_does_not_become_quality_failure():
    from efficiency_platform_agent.agents.operation.contracts.deliverables import (
        QualityStatus,
    )
    from efficiency_platform_agent.capabilities.quality.deliverable_assembler import (
        DeliverableAssembler,
    )

    assembler = DeliverableAssembler()
    items = [
        {
            "platform": "general",
            "title": "方案",
            "body": "正常正文",
            "warnings": ["MODEL_DEGRADED"],
        }
    ]
    report = assembler.assess(
        items,
        task_id="task-a",
        report_id="quality-a",
        deliverable_ids=("deliverable-a",),
    )
    assert report.final_status is QualityStatus.PASSED
    assert assembler.assemble(items, quality_report=report).degraded


async def test_missing_research_provider_has_no_delivery_or_quality_report():
    execution = await build_agent(ContentProvider()).execute(
        submission_from_sample(sample_by_id("industry_digest.complete/1"))
    )
    assert execution.error_code == "RESEARCH_UNAVAILABLE"
    assert execution.deliverables is None
    assert execution.scenario_result.quality_report is None
