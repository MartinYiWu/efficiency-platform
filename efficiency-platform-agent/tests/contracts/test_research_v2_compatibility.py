"""X02 V2 配置兼容和免费来源显式允许契约。"""

from pathlib import Path

import pytest

from efficiency_platform_agent.configuration.research import ResearchPipelineSettings
from efficiency_platform_agent.contracts.research_v2 import (
    DeliveryPackV2,
    ResearchOutcomeV2,
    ResearchUsageV2,
)
from efficiency_platform_agent.conversation.intent_v2_adapter import (
    project_research_outcome_v1,
)


def test_pipeline_settings_reject_duplicate_or_blank_sources() -> None:
    with pytest.raises(ValueError, match="RESEARCH_PIPELINE_ALLOWLIST_INVALID"):
        ResearchPipelineSettings(research_source_allowlist=("source-a", "source-a"))
    with pytest.raises(ValueError, match="RESEARCH_PIPELINE_ALLOWLIST_INVALID"):
        ResearchPipelineSettings(research_source_allowlist=("",))


def test_one_sided_v2_switch_does_not_enable_pipeline() -> None:
    settings = ResearchPipelineSettings(intent_pipeline_version="intent-v2")
    assert settings.v2_enabled is False
    assert settings.production_ready is False


def test_checked_in_pipeline_config_is_disabled_and_not_production_ready() -> None:
    path = Path(__file__).parents[2] / "config" / "research_pipeline.toml"
    settings = ResearchPipelineSettings.load(path)
    assert settings.v2_enabled is False
    assert settings.research_replan_enabled is False
    assert settings.research_source_allowlist == ()
    assert settings.rollout_mode == "tenant_allowlist"
    assert settings.rollout_tenant_allowlist == ()
    assert settings.production_ready is False


def test_enabled_tenant_rollout_requires_nonempty_unique_allowlist() -> None:
    with pytest.raises(ValueError, match="RESEARCH_ROLLOUT_TENANT_ALLOWLIST_REQUIRED"):
        ResearchPipelineSettings(
            intent_pipeline_version="intent-v2",
            research_pipeline_version="research-v2",
            rollout_mode="tenant_allowlist",
        )
    with pytest.raises(ValueError, match="RESEARCH_ROLLOUT_TENANT_ALLOWLIST_INVALID"):
        ResearchPipelineSettings(
            rollout_tenant_allowlist=("tenant-1", "tenant-1"),
        )


def _delivery() -> DeliveryPackV2:
    return DeliveryPackV2(
        delivery_id="delivery-1",
        brief_digest="b" * 64,
        event_ids=("event-1", "event-2", "event-3"),
        claim_ids=("claim-1",),
        evidence_ids=("evidence-1",),
        outcome="PARTIAL",
        display_status="degraded_succeeded",
        stop_reason="ROUND_LIMIT",
        requested_count=5,
        delivered_event_count=3,
        time_window_label="2026-09-15—2026-09-16，Asia/Shanghai",
        content="范围受限的研究简报",
        limitations=("还缺 2 条",),
        renderer_version="research-markdown/2.0.0",
    )


def test_partial_projects_to_existing_v1_strategy_event_and_keeps_evidence() -> None:
    outcome = ResearchOutcomeV2(
        outcome="PARTIAL",
        delivery=_delivery(),
        usable_event_ids=("event-1", "event-2", "event-3"),
        evidence_ids=("evidence-1",),
        stop_reason="ROUND_LIMIT",
        usage=ResearchUsageV2(source_requests=3, model_calls=1, downloaded_bytes=300),
    )
    projected = project_research_outcome_v1(outcome)
    assert projected.display_status == "degraded_succeeded"
    assert projected.delivered_event_count == 3
    assert projected.evidence_ids == ("evidence-1",)
    assert [name for name, _ in projected.events] == ["strategy_event"]


@pytest.mark.parametrize("reason", ["USER_CANCELLED", "HARD_DEADLINE"])
def test_cancel_and_hard_deadline_cannot_project_to_success(reason: str) -> None:
    outcome = ResearchOutcomeV2(
        outcome="FAILED",
        stop_reason=reason,
        usage=ResearchUsageV2(source_requests=0, model_calls=0, downloaded_bytes=0),
    )
    with pytest.raises(
        ValueError, match="RESEARCH_TERMINAL_MUST_USE_EXISTING_RUN_PATH"
    ):
        project_research_outcome_v1(outcome)
