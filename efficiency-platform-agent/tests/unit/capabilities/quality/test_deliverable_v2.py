"""Deliverable V2 展示验证、复制文本和 V1 投影测试。"""

from __future__ import annotations

from datetime import UTC, datetime

import pytest
from pydantic import ValidationError

from efficiency_platform_agent.capabilities.quality.deliverable_v2 import (
    DeliveryPresentationValidator,
    assemble_set_v2,
    project_set_v2_to_v1,
    render_copy_text,
)
from efficiency_platform_agent.contracts.deliverables import (
    ActionPhaseV2,
    ActionPlanContentV2,
    ActionPlanDeliverableV2,
    CitationV2,
    DeliverableSetV2,
    DeliveryProvenanceV2,
    DeliverySummaryV2,
    DiagnosisContentV2,
    DiagnosisDeliverableV2,
    FindingV2,
    NextActionV2,
    OperationDeliverableV2,
    PlatformContentDeliverableV2,
    PlatformContentV2,
    RankedDigestContentV2,
    RankedDigestDeliverableV2,
    RankedItemV2,
    RankingBasisV2,
    RetrospectiveContentV2,
    RetrospectiveDeliverableV2,
    WarningV2,
)


def citation(
    citation_id: str = "citation-1", *, supports: list[str] | None = None
) -> CitationV2:
    """构造离线引用样本。"""

    return CitationV2(
        citation_id=citation_id,
        url="https://example.test/a",
        title="来源 A",
        source="示例站点",
        published_at="2026-09-16T08:00:00Z",
        source_type="official",
        source_tier="primary",
        verification_status="verified",
        supports_item_ids=supports or ["item-1"],
        independent_source_group="example.test",
    )


def item(
    *,
    item_id: str = "item-1",
    rank: int = 1,
    title: str = "事件 A",
    summary: str = "摘要 A",
    refs: list[str] | None = None,
) -> RankedItemV2:
    """构造离线排名条目。"""

    return RankedItemV2(
        item_id=item_id,
        rank=rank,
        title=title,
        occurred_at="2026-09-16T08:00:00Z",
        summary=summary,
        why_it_matters=f"{title} 的运营价值",
        content_angles=["产品观察", "行业趋势"],
        metrics=["来源数=1"],
        source_refs=["citation-1"] if refs is None else refs,
        confidence="high",
        verification_status="verified",
    )


def ranked_deliverable(
    *,
    items: list[RankedItemV2] | None = None,
    deliverable_id: str = "d-1",
    warnings: list[WarningV2] | None = None,
) -> RankedDigestDeliverableV2:
    """构造排名摘要交付物。"""

    return RankedDigestDeliverableV2(
        deliverable_id=deliverable_id,
        platform="research",
        title="热点摘要",
        lead="按重要性整理候选事件。",
        citations=[citation()],
        copy_text="待重算",
        warnings=warnings or [],
        content=RankedDigestContentV2(
            selection_summary="保留经过核验的候选事件。",
            ranking_basis="importance",
            items=items or [item()],
        ),
    )


def platform_deliverable(
    platform: str,
    body: str,
    *,
    deliverable_id: str | None = None,
) -> PlatformContentDeliverableV2:
    """构造平台内容交付物。"""

    return PlatformContentDeliverableV2(
        deliverable_id=deliverable_id or f"d-{platform}",
        platform=platform,
        title=f"{platform} 标题",
        lead="平台内容导语。",
        citations=[citation()],
        copy_text="待重算",
        warnings=[],
        content=PlatformContentV2(
            body_markdown=body,
            hashtags=["#AI", "#运营"],
            format_notes=["短段落", "发布前复核事实"],
        ),
    )


def provenance(
    *, ranking_basis: RankingBasisV2 | None = "importance"
) -> DeliveryProvenanceV2:
    """构造完整研究 provenance。"""

    return DeliveryProvenanceV2(
        source_count=1,
        verified_source_count=1,
        candidate_count=1,
        merged_event_count=1,
        retained_count=1,
        eliminated_count=0,
        collection_window_start=datetime(2026, 9, 15, tzinfo=UTC),
        collection_window_end=datetime(2026, 9, 17, tzinfo=UTC),
        ranking_basis=ranking_basis,
    )


_DEFAULT_PROVENANCE = provenance()


def deliverable_set_v2(
    *,
    deliverables: list[OperationDeliverableV2] | None = None,
    provenance_value: DeliveryProvenanceV2 | None = _DEFAULT_PROVENANCE,
    next_actions: list[NextActionV2] | None = None,
    complete: bool = True,
    degraded: bool = False,
    warnings: list[WarningV2] | None = None,
) -> DeliverableSetV2:
    """构造 V2 集合，允许测试覆盖集合级不变量。"""

    values: list[OperationDeliverableV2] = (
        deliverables if deliverables is not None else [ranked_deliverable()]
    )
    return DeliverableSetV2(
        run_id="run-1",
        intent_revision=1,
        summary=DeliverySummaryV2(
            message="已完成结构化交付。",
            result_count=len(values),
            complete=complete,
        ),
        deliverables=values,
        next_actions=next_actions or [],
        provenance=provenance_value,
        degraded=degraded,
        warnings=warnings or [],
    )


def test_validator_rejects_missing_citation_before_non_contiguous_rank() -> None:
    value = ranked_deliverable(
        items=[
            item(rank=1, refs=["missing"]),
            item(item_id="item-2", rank=3, refs=[]),
        ]
    )

    with pytest.raises(ValueError, match="DELIVERY_CITATION_CLOSURE_INVALID"):
        DeliveryPresentationValidator().validate_deliverable(value)


def test_validator_rejects_non_contiguous_rank() -> None:
    value = ranked_deliverable(
        items=[item(rank=1), item(item_id="item-2", rank=3, refs=[])]
    )

    with pytest.raises(ValueError, match="DELIVERY_RANK_INVALID"):
        DeliveryPresentationValidator().validate_deliverable(value)


def test_validator_rejects_unknown_next_action() -> None:
    with pytest.raises(ValidationError):
        NextActionV2(
            action_id="publish",
            action_type="publish_now",  # type: ignore[arg-type]
            label="立即发布",
            target_deliverable_id="d-1",
            target_item_ids=[],
            intent_patch={},
            requires_user_input=False,
        )


def test_ranked_digest_copy_text_is_rendered_from_structured_items() -> None:
    value = ranked_deliverable(items=[item(rank=1, title="事件 A", summary="摘要 A")])

    assert render_copy_text(value) == (
        "1. 事件 A\n"
        "摘要：摘要 A\n"
        "运营价值：事件 A 的运营价值\n"
        "内容角度：产品观察、行业趋势\n"
        "指标：来源数=1"
    )


def test_platform_content_copy_text_keeps_body_and_hashtag_order() -> None:
    value = platform_deliverable("xiaohongshu", "第一段。\n\n第二段。")

    assert render_copy_text(value) == "第一段。\n\n第二段。\n\n#AI #运营"


def test_action_plan_copy_text_uses_fixed_section_and_item_order() -> None:
    value = ActionPlanDeliverableV2(
        deliverable_id="d-plan",
        platform="general",
        title="推广计划",
        lead="分阶段执行。",
        citations=[],
        copy_text="待重算",
        warnings=[],
        content=ActionPlanContentV2(
            goal="提升试用转化",
            audience="AI 工具新用户",
            phases=[
                ActionPhaseV2(
                    phase_id="phase-1",
                    title="准备",
                    actions=["整理素材", "确认排期"],
                    metrics=["素材完成率"],
                )
            ],
            metrics=["试用转化率"],
            assumptions=["落地页按期上线"],
        ),
    )

    assert render_copy_text(value) == (
        "目标：提升试用转化\n"
        "受众：AI 工具新用户\n\n"
        "阶段 1：准备\n"
        "1. 整理素材\n"
        "2. 确认排期\n"
        "阶段指标：素材完成率\n\n"
        "整体指标：试用转化率\n"
        "假设：落地页按期上线"
    )


def test_diagnosis_copy_text_separates_evidence_and_recommendation() -> None:
    value = DiagnosisDeliverableV2(
        deliverable_id="d-diagnosis",
        platform="general",
        title="账号诊断",
        lead="基于现有材料诊断。",
        citations=[],
        copy_text="待重算",
        warnings=[],
        content=DiagnosisContentV2(
            findings=[
                FindingV2(
                    finding_id="finding-1",
                    title="更新频率不稳定",
                    evidence=["最近四周仅发布两篇"],
                    priority="high",
                    recommendation="建立固定周更计划",
                )
            ],
            data_gaps=["缺少曝光数据"],
        ),
    )

    assert render_copy_text(value) == (
        "1. [高优先级] 更新频率不稳定\n"
        "证据：最近四周仅发布两篇\n"
        "建议：建立固定周更计划\n\n"
        "数据缺口：缺少曝光数据"
    )


def test_retrospective_copy_text_uses_fixed_section_order() -> None:
    value = RetrospectiveDeliverableV2(
        deliverable_id="d-retro",
        platform="general",
        title="活动复盘",
        lead="区分事实与推断。",
        citations=[],
        copy_text="待重算",
        warnings=[],
        content=RetrospectiveContentV2(
            objectives=["提升注册"],
            outcomes=["新增注册 100"],
            gaps=["未达目标"],
            causes=["渠道覆盖不足"],
            next_steps=["补充垂直渠道"],
        ),
    )

    assert render_copy_text(value) == (
        "目标\n1. 提升注册\n\n"
        "结果\n1. 新增注册 100\n\n"
        "差距\n1. 未达目标\n\n"
        "原因\n1. 渠道覆盖不足\n\n"
        "下一步\n1. 补充垂直渠道"
    )


def test_validator_replaces_model_copy_text_without_mutating_input() -> None:
    value = ranked_deliverable()

    validated = DeliveryPresentationValidator().validate_deliverable(value)

    assert validated.copy_text == render_copy_text(value)
    assert value.copy_text == "待重算"


def test_v1_projection_keeps_only_explicit_v2_projection_fields() -> None:
    warning = WarningV2(code="PARTIAL_RESULT", message="结果不完整。")
    value = deliverable_set_v2(
        deliverables=[
            ranked_deliverable(warnings=[warning]).model_copy(
                update={"copy_text": "1. 事件 A\n摘要：摘要 A"}
            )
        ],
        degraded=True,
        warnings=[WarningV2(code="SET_WARNING", message="集合提醒。")],
    )

    projected = project_set_v2_to_v1(value)

    assert projected.contract_version == "deliverable-set/1"
    assert projected.summary == "已完成结构化交付。"
    assert projected.degraded is True
    assert projected.deliverables[0].body == "1. 事件 A\n摘要：摘要 A"
    assert projected.deliverables[0].citations[0].url == "https://example.test/a"
    assert projected.deliverables[0].warnings == ["PARTIAL_RESULT"]
    assert projected.deliverables[0].hashtags == []
    assert projected.deliverables[0].format_notes == []


def test_v1_projection_keeps_platform_hashtags_and_format_notes() -> None:
    platform = platform_deliverable("xiaohongshu", "正文").model_copy(
        update={"copy_text": "正文\n\n#AI #运营"}
    )

    projected = project_set_v2_to_v1(
        deliverable_set_v2(deliverables=[platform], provenance_value=None)
    )

    assert projected.deliverables[0].hashtags == ["#AI", "#运营"]
    assert projected.deliverables[0].format_notes == ["短段落", "发布前复核事实"]


@pytest.mark.parametrize(
    "provenance_value",
    [None, provenance(ranking_basis=None)],
)
def test_ranked_digest_requires_collection_window_and_ranking_basis(
    provenance_value: DeliveryProvenanceV2 | None,
) -> None:
    value = deliverable_set_v2(provenance_value=provenance_value)

    with pytest.raises(ValueError, match="DELIVERY_RESEARCH_PROVENANCE_REQUIRED"):
        assemble_set_v2(value)


def test_platform_bodies_cannot_be_copied_across_platforms() -> None:
    value = deliverable_set_v2(
        deliverables=[
            platform_deliverable("xiaohongshu", "同一 正文"),
            platform_deliverable("wechat", "同一\n正文"),
        ],
        provenance_value=None,
    )

    with pytest.raises(ValueError, match="DELIVERY_PLATFORM_CONTENT_DUPLICATED"):
        assemble_set_v2(value)


def test_assemble_rejects_duplicate_deliverable_ids() -> None:
    value = deliverable_set_v2(
        deliverables=[
            platform_deliverable("xiaohongshu", "正文 A", deliverable_id="same"),
            platform_deliverable("wechat", "正文 B", deliverable_id="same"),
        ],
        provenance_value=None,
    )

    with pytest.raises(ValueError, match="DELIVERY_ID_DUPLICATED"):
        assemble_set_v2(value)


@pytest.mark.parametrize(
    ("target_deliverable_id", "target_item_ids", "error_code"),
    [
        ("missing", [], "DELIVERY_ACTION_TARGET_INVALID"),
        ("d-1", ["missing-item"], "DELIVERY_ACTION_ITEM_TARGET_INVALID"),
        (None, ["item-1"], "DELIVERY_ACTION_ITEM_TARGET_INVALID"),
    ],
)
def test_assemble_rejects_invalid_action_targets(
    target_deliverable_id: str | None,
    target_item_ids: list[str],
    error_code: str,
) -> None:
    action = NextActionV2(
        action_id="action-1",
        action_type="expand_item",
        label="展开条目",
        target_deliverable_id=target_deliverable_id,
        target_item_ids=target_item_ids,
        intent_patch={},
        requires_user_input=False,
    )
    value = deliverable_set_v2(next_actions=[action])

    with pytest.raises(ValueError, match=error_code):
        assemble_set_v2(value)


def test_assemble_recomputes_copy_text_and_degraded_from_explicit_facts() -> None:
    warning = WarningV2(code="PARTIAL_RESULT", message="结果不完整。")
    value = deliverable_set_v2(
        complete=False,
        warnings=[warning, warning],
        next_actions=[
            NextActionV2(
                action_id="action-1",
                action_type="expand_item",
                label="展开条目",
                target_deliverable_id="d-1",
                target_item_ids=["item-1"],
                intent_patch={},
                requires_user_input=False,
            )
        ],
    )

    assembled = assemble_set_v2(value)

    assert assembled.deliverables[0].copy_text.startswith("1. 事件 A")
    assert assembled.degraded is True
    assert assembled.warnings == [warning]
