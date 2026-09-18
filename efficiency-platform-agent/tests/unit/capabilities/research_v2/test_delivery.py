"""R10 结构化交付与确定性 Markdown 降级。"""

from efficiency_platform_agent.capabilities.research.v2.delivery import (
    DeliveryPackBuilder,
)
from efficiency_platform_agent.capabilities.research.v2.renderer import render_markdown
from efficiency_platform_agent.contracts.research_v2 import (
    DeliveryCitationV2,
    DeliveryEventV2,
    DeliveryPackV2,
    ResearchOutcomeV2,
    ResearchUsageV2,
)
from tests.unit.capabilities.research_v2._delivery_support import (
    delivery_facts,
    research_outcome,
)


def test_partial_pack_preserves_scope_gaps_stop_reason_and_evidence() -> None:
    brief, snapshot, _, _, claim, ref = delivery_facts(target=2)
    pack = DeliveryPackBuilder().build(
        brief, research_outcome(brief, partial=True), snapshot
    )

    assert pack.outcome == "PARTIAL"
    assert pack.display_status == "degraded_succeeded"
    assert pack.requested_count == 2
    assert pack.delivered_event_count == 1
    assert pack.claim_ids == (claim.claim_id,)
    assert pack.evidence_ids == (ref.evidence_id,)
    assert pack.gap_codes == ("COUNT_EXACT_UNMET",)
    assert pack.stop_reason == "BUDGET_LIMIT"


def test_generation_failure_fallback_renders_safe_markdown_and_server_url() -> None:
    brief, snapshot, document, _, _, _ = delivery_facts()
    pack = DeliveryPackBuilder().build(brief, research_outcome(brief), snapshot)
    markdown = render_markdown(pack)

    assert "Acme 离线验证结果" in markdown
    assert "<script>" not in markdown
    assert document.canonical_url in markdown
    assert "仅代表已检查且通过证据门禁的来源范围" in markdown


def test_renderer_escapes_independently_constructed_malicious_source_title() -> None:
    pack = DeliveryPackV2(
        delivery_id="delivery-malicious-title",
        brief_digest="a" * 64,
        event_ids=("event-malicious-title",),
        claim_ids=("claim-malicious-title",),
        evidence_ids=("evidence-malicious-title",),
        outcome="COMPLETE",
        display_status="succeeded",
        stop_reason="QUALITY_MET",
        requested_count=1,
        delivered_event_count=1,
        time_window_label="2026-09-15T00:00:00+00:00—2026-09-16T00:00:00+00:00，UTC",
        events=(
            DeliveryEventV2(
                event_id="event-malicious-title",
                title="安全事件标题",
                claim_ids=("claim-malicious-title",),
                claim_texts=("已核验事实。",),
                citations=(
                    DeliveryCitationV2(
                        evidence_id="evidence-malicious-title",
                        document_id="document-malicious-title",
                        url="https://official.example/safe",
                        title="<script>alert('unsafe')</script>",
                        publisher_id="official.example",
                        source_role="primary",
                        excerpt="安全摘录。",
                    ),
                ),
            ),
        ),
        content="安全交付内容。",
        renderer_version="research-markdown/2.0.0",
    )

    markdown = render_markdown(pack)

    assert "&lt;script&gt;" in markdown
    assert "&lt;/script&gt;" in markdown
    assert "<script>" not in markdown


def test_failed_research_cannot_be_rendered_as_success() -> None:
    brief, snapshot, *_ = delivery_facts()
    failed = ResearchOutcomeV2(
        outcome="FAILED",
        stop_reason="FATAL_ERROR",
        usage=ResearchUsageV2(source_requests=1, model_calls=0, downloaded_bytes=0),
    )
    try:
        DeliveryPackBuilder().build(brief, failed, snapshot)
    except ValueError as error:
        assert str(error) == "DELIVERY_UNAVAILABLE"
    else:
        raise AssertionError("FAILED must not become delivery")
