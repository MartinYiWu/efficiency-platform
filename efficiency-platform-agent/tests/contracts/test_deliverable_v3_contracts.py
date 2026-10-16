from datetime import UTC, datetime

import pytest
from pydantic import TypeAdapter, ValidationError

from efficiency_platform_agent.contracts.deliverables import (
    ContentCalendarV1,
    IndustryDigestV1,
    OperationContentV3,
    OperationReviewV1,
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
        "industry_digest",
        "article_draft",
        "brand_plan",
        "ip_plan",
        "campaign_plan",
        "content_calendar",
        "growth_experiment_backlog",
        "operation_review",
    }.issubset(kinds)
