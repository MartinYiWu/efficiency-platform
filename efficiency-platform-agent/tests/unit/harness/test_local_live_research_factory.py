"""正式本地实时组合根必须独立于测试模式与生产持久化门。"""

from importlib import import_module, util

import httpx
import pytest

from efficiency_platform_agent.configuration.research import ResearchPipelineSettings
from efficiency_platform_agent.harness.local_real_factory import (
    build_local_agent_application,
)
from tests.unit.harness.test_local_real_factory import synthetic_settings


def settings():
    return ResearchPipelineSettings(
        runtime_mode="local_live",
        intent_pipeline_version="intent-v2",
        research_pipeline_version="research-v2",
        state_backend="memory",
        research_source_allowlist=("google_blog_rss",),
        research_policy_version="local-live-research/1",
        research_replan_enabled=True,
        rollout_mode="tenant_allowlist",
        rollout_tenant_allowlist=("tenant-1",),
    )


def module():
    name = "efficiency_platform_agent.harness.local_live_research_factory"
    assert util.find_spec(name) is not None, "LOCAL_LIVE_COMPOSITION_MISSING"
    return import_module(name)


async def test_formal_factory_assembles_disabled_sources_without_bypass():
    module()
    async with httpx.AsyncClient(
        transport=httpx.MockTransport(lambda request: pytest.fail("装配不可发起网络"))
    ) as client:
        app = build_local_agent_application(
            synthetic_settings(), http_client=client, research_v2_settings=settings()
        )
        components = app.app.state.local_live_research_components
        assert app.app.state.local_test_mode is False
        assert app.app.state.research_v2_production_ready is False
        assert components.delegate.research_service is components.research_service
        assert components.delegate.source_registry is components.registry
        assert components.delegate.research_state_store is components.research_service
        assert components.research_service.store is components.state_store
        assert components.delegate.submissions is app.conversation.submissions
        assert app.runtime.budget.max_tool_calls == 60
        assert app.runtime.budget.timeout_ms == 180_000
        await app.close()


async def test_local_live_rollout_is_run_scoped_and_never_falls_back():
    from dataclasses import replace

    from efficiency_platform_agent.contracts.conversation import ConversationMessageV1
    from efficiency_platform_agent.conversation.intent_v2_adapter import (
        IntentV2ConversationAdapter,
        PipelineVersionSnapshotV2,
    )
    from efficiency_platform_agent.harness.errors import HarnessError
    from efficiency_platform_agent.harness.service import RunPipelineContext
    from tests.unit.harness.test_research_local_tools import REMAINING

    class Delegate:
        def __init__(self):
            self.calls = []

        async def prepare_v2(self, pipeline, tenant, conversation, message, versions):
            self.calls.append(versions)

    async def cancelled():
        return False

    async def wait():
        return None

    cfg = PipelineVersionSnapshotV2(**settings().model_dump())
    delegate = Delegate()
    adapter = IntentV2ConversationAdapter(cfg, delegate)
    message = ConversationMessageV1(
        message="研究最近一周AI动态", request_id="r1", user_id="u"
    )
    p1 = RunPipelineContext("run1", REMAINING, cancelled, wait)
    await adapter.prepare(p1, "tenant-1", "conversation", message)
    await adapter.update_rollout_settings(
        replace(cfg, research_policy_version="new-policy")
    )
    await adapter.prepare(
        replace(p1, run_id="run2"), "tenant-1", "conversation", message
    )
    assert [x.research_policy_version for x in delegate.calls] == [
        "local-live-research/1",
        "new-policy",
    ]
    with pytest.raises(HarnessError) as error:
        await adapter.prepare(
            replace(p1, run_id="run3"), "foreign", "conversation", message
        )
    assert error.value.code == "RESEARCH_LOCAL_LIVE_TENANT_NOT_ALLOWED"


async def test_auto_composition_rejects_partial_foreign_dependencies():
    async with httpx.AsyncClient(
        transport=httpx.MockTransport(lambda request: pytest.fail("禁止网络"))
    ) as client:
        with pytest.raises(
            RuntimeError, match="RESEARCH_V2_COMPOSITION_BINDING_MISMATCH"
        ):
            build_local_agent_application(
                synthetic_settings(),
                http_client=client,
                research_v2_settings=settings(),
                research_v2_source_registry=object(),
            )


async def test_local_intent_repository_is_bounded_and_expires_without_evicting_live_tasks():
    factory = module()
    assert hasattr(factory, "_LocalIntentTaskRepositoryV2")
    clock = [0.0]
    repository = factory._LocalIntentTaskRepositoryV2(monotonic=lambda: clock[0])
    for index in range(100):
        await repository.begin("tenant", f"task-{index}")
    with pytest.raises(ValueError, match="LOCAL_RESEARCH_CAPACITY"):
        await repository.begin("tenant", "overflow")
    await repository.begin("tenant", "task-0")
    clock[0] = 1801
    await repository.begin("tenant", "new-task")
    assert len(repository._expires) == 1
