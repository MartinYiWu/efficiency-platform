"""X02 V2 默认关闭、版本冻结和生产存储门禁。"""

from datetime import UTC, datetime, timedelta

import pytest

from efficiency_platform_agent.configuration.research import ResearchPipelineSettings
from efficiency_platform_agent.contracts.conversation import ConversationMessageV1
from efficiency_platform_agent.conversation.intent_v2_adapter import (
    IntentV2ConversationAdapter,
    PipelineVersionSnapshotV2,
)
from efficiency_platform_agent.conversation.service import ConversationSubmissionStore
from efficiency_platform_agent.harness.live_acceptance import (
    InMemoryLiveAcceptanceAuthorizationStore,
    InMemoryLiveAcceptanceBudgetBinder,
    LiveAcceptanceAuthorization,
    LiveAcceptanceService,
)
from efficiency_platform_agent.harness.local_real_factory import (
    build_local_agent_application,
)
from efficiency_platform_agent.harness.research_v2_adapter import (
    ResearchV2ProviderAdapter,
)
from efficiency_platform_agent.providers.llm.fake import FakeModelProvider
from tests.unit.harness.test_local_real_factory import synthetic_settings


class _Delegate:
    def __init__(
        self,
        source_registry=None,
        tool_runtime=None,
        research_service=None,
        intent_state_store=None,
        research_state_store=None,
    ) -> None:
        self.versions = []
        self.submissions = ConversationSubmissionStore()
        self.source_registry = source_registry
        self.tool_runtime = tool_runtime
        self.research_service = research_service
        self.intent_state_store = intent_state_store
        self.research_state_store = research_state_store

    async def prepare_v2(self, pipeline, tenant_id, conversation_id, message, versions):
        del pipeline, tenant_id, conversation_id, message
        self.versions.append(versions)


class _ResearchStateStore:
    async def get_brief(self, tenant_id, task_id):
        del tenant_id, task_id


def _message(request_id: str = "request-1") -> ConversationMessageV1:
    return ConversationMessageV1(
        message="收集昨天 AI 新闻", request_id=request_id, user_id="user-1"
    )


def _snapshot(**changes) -> PipelineVersionSnapshotV2:
    values = {
        "intent_pipeline_version": "intent-v1",
        "research_pipeline_version": "research-v1",
        "research_replan_enabled": False,
        "research_source_allowlist": (),
        "research_policy_version": "policy-disabled",
        "state_backend": "memory",
    }
    values.update(changes)
    return PipelineVersionSnapshotV2(**values)


@pytest.mark.asyncio
async def test_v2_is_disabled_by_default() -> None:
    delegate = _Delegate()
    adapter = IntentV2ConversationAdapter(_snapshot(), delegate)
    assert (
        await adapter.prepare(object(), "tenant-1", "conversation-1", _message())
        is None
    )
    assert delegate.versions == []


@pytest.mark.asyncio
async def test_enabled_task_freezes_versions_for_conversation() -> None:
    delegate = _Delegate()
    settings = ResearchPipelineSettings(
        intent_pipeline_version="intent-v2",
        research_pipeline_version="research-v2",
        research_replan_enabled=True,
        research_source_allowlist=("source-free",),
        research_policy_version="policy-v2",
        state_backend="memory",
    )
    adapter = IntentV2ConversationAdapter(
        _snapshot(
            intent_pipeline_version=settings.intent_pipeline_version,
            research_pipeline_version=settings.research_pipeline_version,
            research_replan_enabled=settings.research_replan_enabled,
            research_source_allowlist=settings.research_source_allowlist,
            research_policy_version=settings.research_policy_version,
            state_backend=settings.state_backend,
        ),
        delegate,
    )
    await adapter.prepare(object(), "tenant-1", "conversation-1", _message())
    await adapter.prepare(object(), "tenant-1", "conversation-1", _message("request-2"))
    assert delegate.versions[0] is delegate.versions[1]
    assert delegate.versions[0].research_source_allowlist == ("source-free",)


def test_memory_v2_cannot_claim_production_readiness() -> None:
    adapter = IntentV2ConversationAdapter(
        _snapshot(
            intent_pipeline_version="intent-v2",
            research_pipeline_version="research-v2",
            research_policy_version="policy-v2",
        ),
        _Delegate(),
    )
    with pytest.raises(RuntimeError, match="RESEARCH_V2_PERSISTENCE_NOT_READY"):
        adapter.assert_runtime_ready(production=True)


def test_enabled_v2_requires_explicit_delegate() -> None:
    with pytest.raises(RuntimeError, match="RESEARCH_V2_COMPOSITION_INCOMPLETE"):
        IntentV2ConversationAdapter(
            _snapshot(
                intent_pipeline_version="intent-v2",
                research_pipeline_version="research-v2",
                research_policy_version="policy-v2",
                state_backend="postgres",
            ),
            None,
        ).assert_runtime_ready(production=True)


@pytest.mark.asyncio
async def test_local_factory_mounts_live_acceptance_only_with_explicit_binding() -> (
    None
):
    now = datetime.now(UTC)
    authorization = LiveAcceptanceAuthorization(
        authorization_id="approval-1",
        approved_by="project-owner",
        approved_at=now - timedelta(minutes=1),
        expires_at=now + timedelta(minutes=30),
        allowed_actions=frozenset({"model_evaluation", "source_read"}),
        allowed_case_ids=("ordinary_chat",),
        allowed_tenant_ids=("tenant-acceptance",),
        max_budget_microunits=100,
    )
    application = build_local_agent_application(
        synthetic_settings(),
        provider=FakeModelProvider("synthetic", []),
        test_mode=True,
        live_acceptance_authorizations=InMemoryLiveAcceptanceAuthorizationStore(
            (authorization,)
        ),
        live_acceptance_budget_binder=InMemoryLiveAcceptanceBudgetBinder(),
    )

    assert application.app.state.live_acceptance_enabled is True
    assert (
        "/v1/internal/research-v2/live-acceptance" in application.app.openapi()["paths"]
    )
    await application.close()


def test_factory_rejects_prebuilt_live_service_with_in_memory_binder() -> None:
    class Runner:
        async def run_case(self, case_id, prompt, binding):
            raise AssertionError("must fail before execution")

    service = LiveAcceptanceService(
        authorizations=InMemoryLiveAcceptanceAuthorizationStore(()),
        budget_binder=InMemoryLiveAcceptanceBudgetBinder(),
        runner=Runner(),
    )

    with pytest.raises(RuntimeError, match="LIVE_ACCEPTANCE_PERSISTENCE_NOT_READY"):
        build_local_agent_application(
            synthetic_settings(),
            live_acceptance_service=service,
        )


def test_factory_rejects_enabled_v2_with_legacy_search_gate() -> None:
    base = synthetic_settings()
    settings = base.model_copy(
        update={
            "gates": {
                **base.gates,
                "deepseek_web_search": True,
            }
        }
    )
    pipeline = ResearchPipelineSettings(
        runtime_mode="local_live",
        intent_pipeline_version="intent-v2",
        research_pipeline_version="research-v2",
        research_source_allowlist=("source-free",),
        research_policy_version="policy-v2",
        state_backend="memory",
        rollout_mode="tenant_allowlist",
        rollout_tenant_allowlist=("tenant-1",),
    )
    dependencies = [object() for _ in range(5)]
    delegate = _Delegate(*dependencies)
    with pytest.raises(ValueError, match="RESEARCH_V2_LEGACY_SEARCH_FORBIDDEN"):
        build_local_agent_application(
            settings,
            provider=FakeModelProvider("synthetic", []),
            test_mode=True,
            research_v2_settings=pipeline,
            intent_v2_delegate=delegate,
            research_v2_source_registry=dependencies[0],
            research_v2_tool_runtime=dependencies[1],
            research_service_v2=dependencies[2],
            intent_v2_state_store=dependencies[3],
            research_v2_state_store=dependencies[4],
        )


def test_factory_requires_every_v2_composition_dependency() -> None:
    pipeline = ResearchPipelineSettings(
        intent_pipeline_version="intent-v2",
        research_pipeline_version="research-v2",
        research_policy_version="policy-v2",
        state_backend="memory",
    )
    with pytest.raises(RuntimeError, match="RESEARCH_V2_COMPOSITION_INCOMPLETE"):
        build_local_agent_application(
            synthetic_settings(),
            provider=FakeModelProvider("synthetic", []),
            test_mode=True,
            research_v2_settings=pipeline,
            intent_v2_delegate=_Delegate(),
        )


def test_factory_rejects_delegate_bound_to_different_components() -> None:
    pipeline = ResearchPipelineSettings(
        intent_pipeline_version="intent-v2",
        research_pipeline_version="research-v2",
        research_policy_version="policy-v2",
        state_backend="memory",
    )
    with pytest.raises(RuntimeError, match="RESEARCH_V2_COMPOSITION_BINDING_MISMATCH"):
        build_local_agent_application(
            synthetic_settings(),
            provider=FakeModelProvider("synthetic", []),
            test_mode=True,
            research_v2_settings=pipeline,
            intent_v2_delegate=_Delegate(*[object() for _ in range(5)]),
            research_v2_source_registry=object(),
            research_v2_tool_runtime=object(),
            research_service_v2=object(),
            intent_v2_state_store=object(),
            research_v2_state_store=object(),
        )


@pytest.mark.parametrize(
    ("explicit_contract_version", "expected_contract_version"),
    (
        (None, "deliverable-set/2"),
        ("deliverable-set/1", "deliverable-set/1"),
    ),
)
def test_factory_routes_supervisor_research_through_v2_service(
    monkeypatch,
    explicit_contract_version,
    expected_contract_version,
) -> None:
    from efficiency_platform_agent.harness import local_real_factory

    pipeline = ResearchPipelineSettings(
        runtime_mode="local_live",
        intent_pipeline_version="intent-v2",
        research_pipeline_version="research-v2",
        research_source_allowlist=("source-free",),
        research_policy_version="policy-v2",
        state_backend="memory",
        rollout_mode="tenant_allowlist",
        rollout_tenant_allowlist=("tenant-1",),
    )
    source_registry = object()
    tool_runtime = object()
    research_service = object()
    intent_state_store = object()
    research_state_store = _ResearchStateStore()
    delegate = _Delegate(
        source_registry,
        tool_runtime,
        research_service,
        intent_state_store,
        research_state_store,
    )
    captured = {}
    original = local_real_factory.build_operation_agent

    def _capture(*args, **kwargs):
        captured["research_provider"] = kwargs.get("research_provider")
        captured["contract_version"] = kwargs.get("deliverable_set_contract_version")
        return original(*args, **kwargs)

    monkeypatch.setattr(local_real_factory, "build_operation_agent", _capture)
    application = build_local_agent_application(
        synthetic_settings(),
        provider=FakeModelProvider("synthetic", []),
        test_mode=True,
        research_v2_settings=pipeline,
        intent_v2_delegate=delegate,
        research_v2_source_registry=source_registry,
        research_v2_tool_runtime=tool_runtime,
        research_service_v2=research_service,
        intent_v2_state_store=intent_state_store,
        research_v2_state_store=research_state_store,
        deliverable_set_contract_version=explicit_contract_version,
    )

    provider = captured["research_provider"]
    assert isinstance(provider, ResearchV2ProviderAdapter)
    assert provider.service is research_service
    assert provider.brief_store is research_state_store
    assert captured["contract_version"] == expected_contract_version
    assert application.conversation.submissions is delegate.submissions
