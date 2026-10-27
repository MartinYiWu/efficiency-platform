"""通用回答仅兼容两个显式空值元数据，规范输出仍保持原契约。"""

import json
import logging

import pytest
from pydantic import ValidationError

from efficiency_platform_agent.agents.customer_service.answer_stream import (
    AnswerSectionStream,
)
from efficiency_platform_agent.agents.customer_service.renderer import (
    answer_deltas,
    render_answer,
)
from efficiency_platform_agent.agents.customer_service.state import (
    AnswerMode,
    CustomerServiceAnswer,
    GeneralAdvice,
)


@pytest.mark.parametrize("field", ["clarification_question", "insufficiency_reason"])
def test_provider_schema_allows_only_null_for_compatible_metadata(field) -> None:
    schema = CustomerServiceAnswer.model_json_schema()
    advice_schema = schema["$defs"]["GeneralAdvice"]
    assert advice_schema["additionalProperties"] is False
    assert advice_schema["properties"][field]["type"] == "null"
    assert advice_schema["properties"][field]["default"] is None
    assert field not in advice_schema["required"]


@pytest.mark.parametrize(
    "metadata",
    [
        {"clarification_question": None},
        {"insufficiency_reason": None},
        {"clarification_question": None, "insufficiency_reason": None},
    ],
)
def test_explicit_null_metadata_is_accepted_but_excluded_from_canonical_dump(
    caplog, metadata
) -> None:
    with caplog.at_level(logging.INFO, logger="efficiency_platform_agent.execution"):
        advice = GeneralAdvice.model_validate(
            {"paragraphs": ["PRIVATE_ANSWER_BODY"], **metadata}
        )
    assert advice.model_dump() == {
        "title": "通用建议，非公司制度",
        "paragraphs": ("PRIVATE_ANSWER_BODY",),
    }
    assert json.loads(advice.model_dump_json()) == {
        "title": "通用建议，非公司制度",
        "paragraphs": ["PRIVATE_ANSWER_BODY"],
    }
    assert "customer_service_general_null_metadata_accepted" in caplog.text
    for field in metadata:
        assert field in caplog.text
    assert "PRIVATE_ANSWER_BODY" not in caplog.text


def test_omitted_metadata_does_not_emit_acceptance_event(caplog) -> None:
    with caplog.at_level(logging.INFO, logger="efficiency_platform_agent.execution"):
        advice = GeneralAdvice(paragraphs=("准备材料。",))
    assert set(advice.model_dump()) == {"title", "paragraphs"}
    assert "customer_service_general_null_metadata_accepted" not in caplog.text


@pytest.mark.parametrize("field", ["clarification_question", "insufficiency_reason"])
@pytest.mark.parametrize("value", ["不能移入这里的事实", "", 1, False, [], {}])
def test_compatible_metadata_rejects_all_non_null_values(field, value) -> None:
    with pytest.raises(ValidationError) as error:
        GeneralAdvice.model_validate({"paragraphs": ["准备材料。"], field: value})
    assert any(
        item["loc"] == (field,) and item["type"] == "none_required"
        for item in error.value.errors()
    )


def test_unrelated_unknown_fields_remain_forbidden() -> None:
    with pytest.raises(ValidationError) as error:
        GeneralAdvice.model_validate(
            {"paragraphs": ["准备材料。"], "company_fact": None}
        )
    assert error.value.errors()[0]["type"] == "extra_forbidden"


def test_stream_finish_keeps_prefix_after_null_metadata_normalization() -> None:
    value = {
        "contract_version": "customer-service-answer/1",
        "answer_mode": "GENERAL_ADVICE",
        "knowledge_gap": "公司资料尚未确认具体入口。",
        "company_sections": [],
        "general_advice": {
            "title": "通用建议，非公司制度",
            "paragraphs": ["可以先准备材料。"],
            "clarification_question": None,
            "insufficiency_reason": None,
        },
    }
    content = json.dumps(value, ensure_ascii=False)
    blocks = []
    stream = AnswerSectionStream(
        (), blocks.append, expected_mode=AnswerMode.GENERAL_ADVICE
    )
    paragraph_end = content.index('"可以先准备材料。"') + len('"可以先准备材料。"')
    stream.feed(content[:paragraph_end])
    assert blocks[-1] == "可以先准备材料。"
    stream.feed(content)
    parsed = CustomerServiceAnswer.model_validate_json(content)
    canonical = CustomerServiceAnswer.model_validate(parsed.model_dump(mode="json"))
    assert set(parsed.model_dump()["general_advice"]) == {"title", "paragraphs"}
    stream.finish(canonical)
    assert tuple(blocks) == answer_deltas(render_answer(canonical, ()))
