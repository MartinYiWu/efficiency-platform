"""运营 Deliverable V2 契约的判别、边界与不变量测试。"""

from __future__ import annotations

from copy import deepcopy
from datetime import UTC, datetime
from typing import Any

import pytest
from pydantic import TypeAdapter, ValidationError

from efficiency_platform_agent.contracts.deliverables import (
    DeliverableSet,
    DeliverableSetV1,
    DeliverableSetV2,
    NextActionTypeV2,
    NextActionV2,
)


def ranked_digest_payload() -> dict[str, Any]:
    """返回不依赖网络的完整 V2 排名摘要样本。"""

    return {
        "contract_version": "deliverable-set/2",
        "run_id": "run-1",
        "intent_revision": 0,
        "summary": {
            "message": "已完成候选事件排序。",
            "result_count": 1,
            "complete": True,
        },
        "deliverables": [
            {
                "contract_version": "deliverable/2",
                "deliverable_id": "deliverable-1",
                "deliverable_kind": "ranked_digest",
                "platform": "research",
                "title": "本周热点摘要",
                "lead": "按重要性与时效性筛选出一个候选事件。",
                "citations": [
                    {
                        "citation_id": "citation-1",
                        "url": "https://example.com/article",
                        "title": "示例来源",
                        "source": "示例站点",
                        "published_at": "2026-09-16T08:00:00Z",
                        "source_type": "official",
                        "source_tier": "primary",
                        "verification_status": "verified",
                        "supports_item_ids": ["item-1"],
                        "independent_source_group": "example.com",
                    }
                ],
                "content": {
                    "kind": "ranked_digest",
                    "selection_summary": "保留一个已核验候选事件。",
                    "ranking_basis": "mixed",
                    "items": [
                        {
                            "item_id": "item-1",
                            "rank": 1,
                            "title": "示例事件",
                            "occurred_at": "2026-09-16T08:00:00Z",
                            "summary": "这是用于契约测试的离线事件摘要。",
                            "why_it_matters": "它可以验证类型化排名条目与引用关系。",
                            "content_angles": ["契约治理"],
                            "metrics": ["来源数=1"],
                            "source_refs": ["citation-1"],
                            "confidence": "high",
                            "verification_status": "verified",
                        }
                    ],
                },
                "copy_text": "1. 示例事件：这是用于契约测试的离线事件摘要。",
                "warnings": [],
            }
        ],
        "next_actions": [],
        "provenance": {
            "source_count": 1,
            "verified_source_count": 1,
            "candidate_count": 1,
            "merged_event_count": 1,
            "retained_count": 1,
            "eliminated_count": 0,
            "collection_window_start": "2026-09-15T00:00:00Z",
            "collection_window_end": "2026-09-17T00:00:00Z",
            "ranking_basis": "mixed",
        },
        "degraded": False,
        "warnings": [],
    }


def test_ranked_digest_v2_requires_typed_items_and_rejects_unknown_fields() -> None:
    payload = ranked_digest_payload()

    parsed = DeliverableSetV2.model_validate(payload)

    assert parsed.deliverables[0].content.kind == "ranked_digest"
    payload["deliverables"][0]["content"]["unexpected"] = True
    with pytest.raises(ValidationError):
        DeliverableSetV2.model_validate(payload)


def test_deliverable_v2_rejects_discriminator_mismatch() -> None:
    payload = ranked_digest_payload()
    payload["deliverables"][0]["deliverable_kind"] = "platform_content"

    with pytest.raises(ValidationError):
        DeliverableSetV2.model_validate(payload)


def test_deliverable_set_union_dispatches_only_by_contract_version() -> None:
    adapter: TypeAdapter[DeliverableSet] = TypeAdapter(DeliverableSet)

    parsed = adapter.validate_python(ranked_digest_payload())

    assert isinstance(parsed, DeliverableSetV2)
    v1 = adapter.validate_python(
        {
            "contract_version": "deliverable-set/1",
            "deliverables": [],
            "summary": "既有 V1 仍可解析",
            "degraded": False,
        }
    )
    assert isinstance(v1, DeliverableSetV1)


@pytest.mark.parametrize(
    "action_type",
    [
        "rewrite_for_platform",
        "expand_item",
        "generate_script",
        "replace_candidates",
        "show_sources",
        "refine_constraints",
    ],
)
def test_next_action_accepts_every_registered_action_type(
    action_type: NextActionTypeV2,
) -> None:
    action = NextActionV2(
        action_id="action-1",
        action_type=action_type,
        label="继续处理",
        target_deliverable_id=None,
        target_item_ids=[],
        intent_patch={"platform": "xiaohongshu", "research": True},
        requires_user_input=False,
    )

    assert action.action_type == action_type


def test_next_action_takes_an_isolated_strict_json_snapshot() -> None:
    intent_patch = {"nested": {"items": ["first"]}}
    action = NextActionV2(
        action_id="action-1",
        action_type="refine_constraints",
        label="调整约束",
        target_deliverable_id=None,
        target_item_ids=[],
        intent_patch=intent_patch,
        requires_user_input=True,
    )

    intent_patch["nested"]["items"].append("later")

    assert action.intent_patch == {"nested": {"items": ["first"]}}
    with pytest.raises(ValidationError):
        NextActionV2(
            action_id="action-2",
            action_type="refine_constraints",
            label="调整约束",
            target_deliverable_id=None,
            target_item_ids=[],
            intent_patch={"not_json": datetime.now(UTC)},
            requires_user_input=True,
        )


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("verified_source_count", 2),
        ("collection_window_end", None),
        ("collection_window_end", "2026-09-14T00:00:00Z"),
        ("collection_window_start", "2026-09-15T00:00:00"),
    ],
)
def test_provenance_rejects_invalid_counts_and_time_windows(
    field: str, value: object
) -> None:
    payload = ranked_digest_payload()
    payload["provenance"][field] = value

    with pytest.raises(ValidationError):
        DeliverableSetV2.model_validate(payload)


def test_v2_models_are_frozen_and_do_not_share_input_state() -> None:
    payload = ranked_digest_payload()
    parsed = DeliverableSetV2.model_validate(payload)
    original = deepcopy(parsed.model_dump())

    payload["deliverables"][0]["content"]["items"][0]["title"] = "后改标题"

    assert parsed.model_dump() == original
    with pytest.raises(ValidationError):
        parsed.degraded = True
