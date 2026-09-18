"""本地实时研究模式的配置、快照与启动门测试。"""

from __future__ import annotations

from dataclasses import dataclass, field

import pytest
from pydantic import ValidationError

from efficiency_platform_agent.configuration.research import ResearchPipelineSettings
from efficiency_platform_agent.conversation.intent_v2_adapter import (
    IntentV2ConversationAdapter,
    PipelineVersionSnapshotV2,
)


@dataclass
class _CompleteDelegate:
    source_registry: object = field(default_factory=object)
    tool_runtime: object = field(default_factory=object)
    research_service: object = field(default_factory=object)
    intent_state_store: object = field(default_factory=object)
    research_state_store: object = field(default_factory=object)

    async def prepare_v2(self, pipeline, tenant_id, conversation_id, message, versions):
        del pipeline, tenant_id, conversation_id, message, versions


def _settings(**changes: object) -> ResearchPipelineSettings:
    values: dict[str, object] = {
        "runtime_mode": "local_live",
        "intent_pipeline_version": "intent-v2",
        "research_pipeline_version": "research-v2",
        "state_backend": "memory",
        "research_source_allowlist": ("google_blog_rss",),
        "research_policy_version": "local-live-research/1",
        "rollout_mode": "tenant_allowlist",
        "rollout_tenant_allowlist": ("local-team",),
    }
    values.update(changes)
    return ResearchPipelineSettings.model_validate(values)


def _snapshot(settings: ResearchPipelineSettings) -> PipelineVersionSnapshotV2:
    return PipelineVersionSnapshotV2(
        intent_pipeline_version=settings.intent_pipeline_version,
        research_pipeline_version=settings.research_pipeline_version,
        research_replan_enabled=settings.research_replan_enabled,
        research_source_allowlist=settings.research_source_allowlist,
        research_policy_version=settings.research_policy_version,
        state_backend=settings.state_backend,
        runtime_mode=settings.runtime_mode,
        rollout_mode=settings.rollout_mode,
        rollout_tenant_allowlist=settings.rollout_tenant_allowlist,
    )


def test_v1_defaults_do_not_enable_v2() -> None:
    settings = ResearchPipelineSettings()

    assert settings.runtime_mode == "production"
    assert settings.v2_enabled is False
    assert settings.local_live_ready is False
    assert settings.production_ready is False


def test_memory_local_live_is_config_ready_but_never_production_ready() -> None:
    settings = _settings()

    assert settings.v2_enabled is True
    assert settings.local_live_ready is True
    assert settings.production_ready is False


@pytest.mark.parametrize(
    ("changes", "error_code"),
    [
        ({"state_backend": "postgres"}, "RESEARCH_LOCAL_LIVE_MEMORY_REQUIRED"),
        ({"research_source_allowlist": ()}, "RESEARCH_LOCAL_LIVE_SOURCE_ALLOWLIST_REQUIRED"),
        (
            {"rollout_tenant_allowlist": ()},
            "RESEARCH_ROLLOUT_TENANT_ALLOWLIST_REQUIRED",
        ),
        ({"runtime_mode": "local-life"}, "literal_error"),
    ],
)
def test_local_live_rejects_invalid_mode_backend_or_empty_allowlists(
    changes: dict[str, object], error_code: str
) -> None:
    with pytest.raises(ValidationError, match=error_code):
        _settings(**changes)


def test_memory_production_v2_is_rejected_at_runtime_gate() -> None:
    settings = _settings(runtime_mode="production")
    adapter = IntentV2ConversationAdapter(_snapshot(settings), _CompleteDelegate())

    with pytest.raises(RuntimeError, match="RESEARCH_V2_PERSISTENCE_NOT_READY"):
        adapter.assert_runtime_ready(runtime_mode="production")


def test_local_live_runtime_gate_accepts_complete_memory_composition() -> None:
    settings = _settings()
    adapter = IntentV2ConversationAdapter(_snapshot(settings), _CompleteDelegate())

    adapter.assert_runtime_ready(runtime_mode="local_live")


def test_runtime_gate_rejects_mode_mismatch() -> None:
    settings = _settings()
    adapter = IntentV2ConversationAdapter(_snapshot(settings), _CompleteDelegate())

    with pytest.raises(RuntimeError, match="RESEARCH_RUNTIME_MODE_MISMATCH"):
        adapter.assert_runtime_ready(runtime_mode="production")


def test_legacy_production_bridge_cannot_enable_local_live() -> None:
    settings = _settings()
    adapter = IntentV2ConversationAdapter(_snapshot(settings), _CompleteDelegate())

    with pytest.raises(RuntimeError, match="RESEARCH_LOCAL_LIVE_LEGACY_BYPASS_FORBIDDEN"):
        adapter.assert_runtime_ready(production=False)


def test_production_postgres_keeps_existing_readiness_contract() -> None:
    settings = _settings(runtime_mode="production", state_backend="postgres")
    adapter = IntentV2ConversationAdapter(_snapshot(settings), _CompleteDelegate())

    assert settings.production_ready is True
    assert settings.local_live_ready is False
    adapter.assert_runtime_ready(runtime_mode="production")
