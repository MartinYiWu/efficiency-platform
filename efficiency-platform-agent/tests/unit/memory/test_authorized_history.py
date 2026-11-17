"""运营仅消费Java认证正文绑定的有界合法历史，未知/超额/越包依赖拒绝。"""

import json

import pytest
from pydantic import ValidationError

from efficiency_platform_agent.contracts.conversation import ConversationMessageV1
from tests.unit.memory.test_memory_envelope import envelope


def message():
    context = envelope()
    return {
        "message": "continue",
        "request_id": "history",
        "user_id": "user",
        "memory_context": context,
        "history": [
            {
                "message_id": "U",
                "version": "digest",
                "role": "user",
                "content": "authorized previous question",
                "safety_dependencies": context["packet"]["safety_dependencies"],
            }
        ],
    }


def test_exact_history_is_explicitly_retained_in_wire_message():
    parsed = ConversationMessageV1.model_validate_json(json.dumps(message()))
    assert parsed.history[0].content == "authorized previous question"
    assert parsed.history[0].safety_dependencies


@pytest.mark.parametrize(
    "change", ["unknown", "foreign", "disabled", "oversize", "nine"]
)
def test_unknown_or_unauthorized_or_unbounded_history_fails_closed(change):
    body = message()
    if change == "unknown":
        body["history"][0]["safety_dependencies"] = []
    elif change == "foreign":
        body["history"][0]["safety_dependencies"] = [
            dict(body["history"][0]["safety_dependencies"][0], source_id="foreign")
        ]
    elif change == "disabled":
        body["memory_context"] = {"memory_mode": "DISABLED"}
    elif change == "oversize":
        body["history"][0]["content"] = "x" * 12001
    else:
        body["history"] *= 9
    with pytest.raises(ValidationError):
        ConversationMessageV1.model_validate_json(json.dumps(body))
