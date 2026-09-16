"""会话与意图契约的边界测试。"""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from efficiency_platform_agent.contracts.conversation import (
    ConversationMessageV1,
    ConversationSubmitViewV1,
    RunDisplayStatus,
)
from efficiency_platform_agent.contracts.intent import (
    IntentEnvelopeV1,
    IntentRequirementsV1,
)


def test_conversation_message_uses_frozen_versioned_contract() -> None:
    message = ConversationMessageV1(
        message="生成新品文案",
        request_id="request-1",
        user_id="user-1",
    )

    assert message.contract_version == "conversation/1"
    with pytest.raises(ValidationError):
        message.message = "不能修改"


def test_conversation_submit_view_requires_the_run_identity() -> None:
    with pytest.raises(ValidationError):
        ConversationSubmitViewV1(
            conversation_id="conversation-1",
            turn_id="turn-1",
            status="queued",
        )


def test_conversation_submit_view_only_allows_queued_status() -> None:
    with pytest.raises(ValidationError):
        ConversationSubmitViewV1(
            conversation_id="conversation-1",
            turn_id="turn-1",
            run_id="run-1",
            status="running",
        )


def test_conversation_message_rejects_attachments_in_this_iteration() -> None:
    with pytest.raises(ValidationError):
        ConversationMessageV1(
            message="生成文案",
            request_id="request-1",
            user_id="user-1",
            attachments=[{"name": "file.txt"}],
        )


def test_run_display_status_covers_degraded_completion() -> None:
    assert set(RunDisplayStatus.__args__) == {
        "queued",
        "running",
        "waiting_input",
        "succeeded",
        "failed",
        "cancelled",
        "degraded_succeeded",
    }


def test_intent_confidence_must_be_between_zero_and_one() -> None:
    with pytest.raises(ValidationError):
        IntentEnvelopeV1(
            domain="运营",
            goal="生成文案",
            task_type="content",
            confidence=1.01,
        )


def test_intent_requirements_are_frozen_versioned_and_forbid_open_fields() -> None:
    requirements = IntentRequirementsV1(
        brand="效率品牌",
        planning_window="未来一季度",
    )

    assert requirements.contract_version == "intent.requirements/1"
    with pytest.raises(ValidationError):
        requirements.brand = "不能修改"
    with pytest.raises(ValidationError):
        IntentRequirementsV1.model_validate(
            {
                "contract_version": "intent.requirements/1",
                "brand": "效率品牌",
                "arbitrary": {"不受控": True},
            }
        )


def test_intent_rejects_unknown_requirements_contract_version() -> None:
    with pytest.raises(ValidationError):
        IntentRequirementsV1.model_validate(
            {"contract_version": "intent.requirements/2", "topic": "AI Agent"}
        )
