from datetime import UTC, datetime

import pytest
from pydantic import TypeAdapter, ValidationError

from efficiency_platform_agent.contracts.deliverables import (
    ArticleDraftV1,
    ContentCalendarV1,
    DeliverableSetV3,
    DeliverySummaryV2,
    IndustryDigestV1,
    OperationContentV3,
    OperationDeliverableV3,
    OperationReviewV1,
    render_operation_content_v3,
)


def test_industry_digest_requires_closed_count_and_continuous_ranks() -> None:
    with pytest.raises(ValidationError, match="INDUSTRY_ACTUAL_COUNT_INVALID"):
        IndustryDigestV1.model_validate(
            {
                "topic": "AI",
                "time_window": "最近7天",
                "actual_count": 2,
                "items": [
                    {
                        "rank": 1,
                        "title": "发布",
                        "event_summary": "事实",
                        "why_it_matters": "影响",
                        "operator_insight": "运营观察",
                    }
                ],
            }
        )


def test_industry_digest_renders_as_compact_ranked_paragraphs() -> None:
    digest = IndustryDigestV1(
        topic="AI 热点",
        time_window=(
            "2026-10-16T08:10:03+00:00 至 2026-10-19T08:10:03+00:00"
            "（左闭右开，最近3天）"
        ),
        actual_count=2,
        items=[
            {
                "rank": 1,
                "title": "OpenAI 发布新模型",
                "event_summary": "模型能力获得提升。",
                "why_it_matters": "内容生产门槛进一步降低。",
                "operator_insight": "可优先验证选题生成效率。",
            },
            {
                "rank": 2,
                "title": "Meta 更新智能体产品",
                "event_summary": "产品覆盖更多消费场景。",
                "why_it_matters": "智能体开始进入大众应用。",
                "operator_insight": "适合持续观察用户反馈。",
            },
        ],
    )

    markdown = render_operation_content_v3(digest)

    assert markdown == (
        "最近3天，AI 热点已整理完成，共 2 条，按重要性排序：\n\n"
        "1. **OpenAI 发布新模型：** 模型能力获得提升。 "
        "内容生产门槛进一步降低。 可优先验证选题生成效率。\n\n"
        "2. **Meta 更新智能体产品：** 产品覆盖更多消费场景。 "
        "智能体开始进入大众应用。 适合持续观察用户反馈。"
    )


def test_calendar_rejects_entry_outside_requested_period() -> None:
    with pytest.raises(ValidationError, match="CALENDAR_ENTRY_OUT_OF_RANGE"):
        ContentCalendarV1.model_validate(
            {
                "period": {
                    "start_date": "2026-10-01",
                    "end_date": "2026-10-07",
                    "timezone": "Asia/Shanghai",
                },
                "cadence": [{"platform": "wechat", "frequency": "weekly"}],
                "entries": [
                    {
                        "publish_at": datetime(2026, 10, 8, tzinfo=UTC),
                        "platform": "wechat",
                        "topic": "主题",
                        "format": "长文",
                        "objective": "认知",
                        "angle": "行业影响",
                        "cta": "留言",
                    }
                ],
            }
        )


def test_review_confirmed_cause_requires_evidence() -> None:
    with pytest.raises(ValidationError):
        OperationReviewV1.model_validate(
            {
                "review_period": "2026-10",
                "comparison_period": "2026-09",
                "metric_table": [
                    {
                        "name": "点击率",
                        "definition": "点击/曝光",
                        "current_value": "5%",
                        "data_source": "用户数据",
                    }
                ],
                "confirmed_causes": [{"cause": "选题改善", "evidence_refs": []}],
                "next_actions": [{"action": "继续验证"}],
            }
        )


def test_operation_content_v3_discriminator_accepts_all_eight_kinds() -> None:
    kinds = {
        schema["properties"]["kind"]["const"]
        for schema in TypeAdapter(OperationContentV3).json_schema()["$defs"].values()
        if "kind" in schema.get("properties", {})
    }
    assert {
        "ranked_digest",
        "platform_content",
        "brand_plan",
        "ip_plan",
        "campaign_plan",
        "content_calendar",
        "growth_experiment",
        "operation_review",
    }.issubset(kinds)


def test_v3_article_has_public_scenario_platform_and_deterministic_markdown() -> None:
    article = ArticleDraftV1(
        platform="xiaohongshu",
        title="AI 运营周报",
        introduction="本周值得关注。",
        sections=[
            {
                "heading": "模型更新",
                "facts": ["事实一"],
                "analysis": ["影响一"],
                "operator_takeaway": "建议持续观察。",
            }
        ],
        closing="欢迎交流。",
        hashtags=["AI", "运营"],
    )

    markdown = render_operation_content_v3(article)
    deliverable = OperationDeliverableV3(
        deliverable_id="article-1",
        scenario="multi_platform_content",
        platform="xiaohongshu",
        title=article.title,
        copy_text=markdown,
        content=article,
    )
    value = DeliverableSetV3(
        run_id="run-1",
        intent_revision=1,
        summary=DeliverySummaryV2(
            message="已生成 1 份交付物。", result_count=1, complete=True
        ),
        deliverables=[deliverable],
    )

    assert value.contract_version == "deliverable-set/3"
    assert deliverable.content.kind == "platform_content"
    assert markdown == (
        "# AI 运营周报\n\n本周值得关注。\n\n"
        "## 模型更新\n\n### 事实\n\n- 事实一\n\n"
        "### 分析\n\n- 影响一\n\n### 运营建议\n\n建议持续观察。\n\n"
        "欢迎交流。\n\n#AI #运营"
    )
