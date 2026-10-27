import json
from types import SimpleNamespace
from uuid import uuid4

import pytest
from jsonschema import ValidationError as JsonSchemaValidationError
from jsonschema import validate
from pydantic import ValidationError

from efficiency_platform_agent.agents.customer_service.graph import CustomerServiceGraph
from efficiency_platform_agent.agents.customer_service.model_gateway import _freeze
from efficiency_platform_agent.agents.customer_service.service import (
    CustomerServiceRunService,
)
from efficiency_platform_agent.agents.customer_service.state import (
    CustomerServiceRunRequest,
    HistoryMessage,
    IntentDecision,
    RunEventPayload,
    RunStatus,
)
from efficiency_platform_agent.core.run import (
    JsonObject,
    ProviderMessage,
    ProviderRequest,
)
from efficiency_platform_agent.providers.llm.deepseek import DeepSeekModelProvider


def intent_value():
    return {
        "intent_type": "GENERAL_QUERY",
        "requires_company_knowledge": False,
        "requires_general_advice": True,
        "normalized_question": "如何安排工作？",
    }


@pytest.mark.parametrize(
    ("title", "expected"),
    [
        (None, None),
        ("", None),
        (" ", None),
        ("\t\n", None),
        ("\u3000", None),
        ("\x00\x1b\u200b", None),
        ("标" * 25, "标" * 24),
        ("  工作\r\n\t 安排\u3000建议  ", "工作 安排 建议"),
        ("工\x00作\x1b安\u200b排\x7f", "工作安排"),
        ("工作 \x00 安排", "工作 安排"),
        (42, None),
        (False, None),
        ({"title": "工作安排"}, None),
        (["工作安排"], None),
    ],
)
def test_intent_normalizes_or_discards_only_auxiliary_title(title, expected):
    validate(
        intent_value() | {"conversation_title": title},
        IntentDecision.model_json_schema(),
    )
    decision = IntentDecision(**intent_value(), conversation_title=title)
    assert decision.conversation_title == expected
    assert decision.normalized_question == "如何安排工作？"
    assert decision.intent_type == "GENERAL_QUERY"
    assert decision.requires_general_advice is True


def test_only_auxiliary_title_has_unrestricted_provider_schema():
    schema = IntentDecision.model_json_schema()
    title_schema = schema["properties"]["conversation_title"]
    assert (
        not {"type", "anyOf", "minLength", "maxLength", "pattern"} & title_schema.keys()
    )
    assert "conversation_title" not in schema["required"]
    assert "24" in title_schema["description"]
    for invalid_fields in (
        {"intent_type": "INVALID"},
        {"normalized_question": ""},
        {"requires_company_knowledge": "false"},
        {"retrieval_queries": [" "]},
        {"unexpected": True},
    ):
        with pytest.raises(JsonSchemaValidationError):
            validate(intent_value() | invalid_fields, schema)


@pytest.mark.parametrize(
    ("title", "expected"),
    [("\t\n", None), ("标" * 25, "标" * 24), (42, None), ({"title": "工作"}, None)],
)
async def test_deepseek_response_validation_allows_title_normalization(title, expected):
    response_content = json.dumps(intent_value() | {"conversation_title": title})

    class Completions:
        async def create(self, **_kwargs):
            return SimpleNamespace(
                choices=(
                    SimpleNamespace(message=SimpleNamespace(content=response_content)),
                )
            )

    client = SimpleNamespace(chat=SimpleNamespace(completions=Completions()))
    result = await DeepSeekModelProvider(client, "deepseek-chat").complete(
        ProviderRequest(
            "s2/1",
            (ProviderMessage("user", "如何安排工作？"),),
            JsonObject((("json_schema", _freeze(IntentDecision.model_json_schema())),)),
            1000,
        )
    )
    assert result.error is None
    assert result.message is not None
    assert (
        IntentDecision.model_validate_json(result.message.content).conversation_title
        == expected
    )


@pytest.mark.parametrize(
    "invalid_fields",
    [
        {"intent_type": "INVALID"},
        {"normalized_question": ""},
        {"intent_type": "AMBIGUOUS_QUERY", "missing_field": None},
    ],
)
def test_auxiliary_title_does_not_relax_other_intent_validation(invalid_fields):
    with pytest.raises(ValidationError):
        IntentDecision(**(intent_value() | invalid_fields), conversation_title="\t\n")


def test_optional_titles_preserve_legacy_serialization():
    decision = IntentDecision(**intent_value())
    assert decision.conversation_title is None
    assert "conversation_title" not in decision.model_dump(mode="json")
    assert "conversation_title" not in IntentDecision(
        **intent_value(), conversation_title=None
    ).model_dump(mode="json")
    payload = RunEventPayload(stage="intent", phase="COMPLETED")
    assert payload.model_dump(mode="json") == {
        "stage": "intent",
        "phase": "COMPLETED",
        "progress_percent": None,
        "public_summary": None,
        "delta": None,
        "answer_mode": None,
        "citation": None,
        "error_code": None,
        "error_message": None,
        "retrieval_facts": None,
    }


def test_title_schema_limits_and_present_serialization():
    title = "标" * 24
    assert (
        IntentDecision(**intent_value(), conversation_title=title).model_dump(
            mode="json"
        )["conversation_title"]
        == title
    )
    assert (
        RunEventPayload(conversation_title="标" * 80).model_dump(mode="json")[
            "conversation_title"
        ]
        == "标" * 80
    )
    with pytest.raises(ValidationError, match="conversation_title"):
        RunEventPayload(conversation_title="标" * 81)
    assert "首轮" in IntentDecision.model_fields["conversation_title"].description


@pytest.mark.parametrize(
    "history", [(), (HistoryMessage(role="user", content="上一轮"),)]
)
@pytest.mark.parametrize(
    ("title", "expected_title"),
    [
        (None, None),
        ("工作安排", "工作安排"),
        ("\t\r\n", None),
        (123, None),
        ("标" * 25, "标" * 24),
        (" 工\x00作\r\n\t安排\u200b ", "工作 安排"),
    ],
)
async def test_real_graph_service_emits_only_first_round_model_title(
    history, title, expected_title
):
    calls = []
    bundle = SimpleNamespace(rag_policy=SimpleNamespace(rewrite_query_limit=2))

    class Releases:
        async def get(self, _release_id):
            return bundle

    class Gateway:
        async def complete(self, stage, value, output_type):
            calls.append(stage)
            if stage == "intent":
                response = intent_value()
                if title is not None:
                    response["conversation_title"] = title
                return output_type(**response)
            assert stage == "answer_general"
            return output_type(
                contract_version="customer-service-answer/1",
                answer_mode="GENERAL_ADVICE",
                general_advice={"paragraphs": ["先列出任务。"]},
            )

    request = CustomerServiceRunRequest(
        contract_version="customer-service-run/1",
        request_id="title-test",
        conversation_id=uuid4(),
        tenant_id="dev",
        user_id="1",
        agent_release_id=uuid4(),
        message="如何安排工作？",
        history=history,
    )
    service = CustomerServiceRunService(
        CustomerServiceGraph(object()), Releases(), lambda _: Gateway()
    )
    run = await service.submit(request)
    events = [event async for event in service.events(run.run_id)]
    assert events[-1].status == RunStatus.SUCCEEDED
    assert calls == ["intent", "answer_general"]
    expected_types = [
        "run.accepted",
        "run.started",
        "stage.completed",
        "stage.started",
        "answer.delta",
        "answer.completed",
    ]
    if not history and expected_title is not None:
        expected_types.insert(2, "conversation.title")
        title_event = events[2]
        assert title_event.status == RunStatus.RUNNING
        assert title_event.payload.stage == "conversation_title"
        assert title_event.payload.public_summary == "会话标题已更新"
        assert title_event.payload.conversation_title == expected_title
        assert title_event.payload.phase is None
        assert title_event.payload.delta is None
        assert (
            title_event.model_dump(mode="json")["payload"]["conversation_title"]
            == expected_title
        )
    assert [event.event_type for event in events] == expected_types
    assert [event.sequence for event in events] == list(range(1, len(events) + 1))
    assert [
        event.payload.delta for event in events if event.event_type == "answer.delta"
    ] == [
        "## 通用建议，非公司制度\n\n先列出任务。",
    ]
    assert all(
        "conversation_title" not in event.model_dump(mode="json")["payload"]
        for event in events
        if event.event_type != "conversation.title"
    )
