import json
from itertools import permutations
from uuid import uuid4

import pytest

from efficiency_platform_agent.agents.customer_service.answer_stream import (
    AnswerSectionStream,
)
from efficiency_platform_agent.agents.customer_service.citations import (
    CitationGuardError,
)
from efficiency_platform_agent.agents.customer_service.renderer import (
    answer_deltas,
    render_answer,
)
from efficiency_platform_agent.agents.customer_service.state import (
    AnswerMode,
    CustomerServiceAnswer,
    Evidence,
)


def evidence_item() -> Evidence:
    return Evidence(
        chunk_id=uuid4(),
        knowledge_base_id=uuid4(),
        document_id=uuid4(),
        document_version_id=uuid4(),
        index_release_id=uuid4(),
        document_title="制度",
        version_no=1,
        content="依据",
        content_hash="a" * 64,
        score=1,
    )


def payload(mode: AnswerMode, chunk_id=None) -> dict:
    return {
        "contract_version": "customer-service-answer/1",
        "answer_mode": mode.value,
        "knowledge_gap": "现有资料未说明审批时限。",
        "company_sections": []
        if chunk_id is None
        else [
            {
                "title": '公司规定 ["流程"]',
                "paragraphs": [
                    {
                        "text": '向负责人提交 {申请}，注明 "原因"。',
                        "supporting_chunk_ids": [str(chunk_id)],
                    }
                ],
            }
        ],
        "general_advice": {
            "title": "通用建议，非公司制度",
            "paragraphs": ['先整理 "背景" 与 [目标]。🙂', "第一步\n\n第二步"],
        },
    }


def test_general_releases_only_complete_strings_before_model_finishes() -> None:
    blocks: list[str] = []
    stream = AnswerSectionStream(
        (), blocks.append, expected_mode=AnswerMode.GENERAL_ADVICE
    )
    value = payload(AnswerMode.GENERAL_ADVICE)
    content = json.dumps(value, ensure_ascii=True)
    first = json.dumps(value["general_advice"]["paragraphs"][0], ensure_ascii=True)
    first_end = content.index(first) + len(first)
    stream.feed(content[: first_end - 1])
    assert blocks == ["现有资料未说明审批时限。"]
    stream.feed(content[:first_end])
    assert blocks == [
        "现有资料未说明审批时限。",
        "## 通用建议，非公司制度",
        '先整理 "背景" 与 [目标]。🙂',
    ]
    stream.feed(content[:first_end])
    assert len(blocks) == 3
    stream.feed(content)
    answer = CustomerServiceAnswer.model_validate_json(content)
    stream.finish(answer)
    assert tuple(blocks) == answer_deltas(render_answer(answer, ()))
    assert blocks[-1] == "第一步\n\n第二步"


@pytest.mark.parametrize(
    "order", list(permutations(("knowledge_gap", "company_sections", "general_advice")))
)
@pytest.mark.parametrize("ensure_ascii", [False, True])
def test_mixed_fields_always_match_final_block_order(
    order: tuple[str, ...], ensure_ascii: bool
) -> None:
    item = evidence_item()
    value = payload(AnswerMode.MIXED, item.chunk_id)
    ordered = {
        "contract_version": value["contract_version"],
        "answer_mode": value["answer_mode"],
    }
    ordered.update({key: value[key] for key in order})
    content = json.dumps(ordered, ensure_ascii=ensure_ascii)
    blocks: list[str] = []
    stream = AnswerSectionStream((item,), blocks.append, expected_mode=AnswerMode.MIXED)
    for end in range(1, len(content) + 1):
        stream.feed(content[:end])
        stream.feed(content[:end])
    answer = CustomerServiceAnswer.model_validate_json(content)
    stream.finish(answer)
    assert tuple(blocks) == answer_deltas(render_answer(answer, (item,)))
    assert blocks[0] == value["knowledge_gap"]


def test_general_waits_for_gap_and_never_exposes_reasoning() -> None:
    blocks: list[str] = []
    stream = AnswerSectionStream(
        (), blocks.append, expected_mode=AnswerMode.GENERAL_ADVICE
    )
    stream.feed(
        '{"reasoning":"do not show \\"company_sections\\": [{]","general_advice":{"title":"通用建议，非公司制度","paragraphs":["建议"]}'
    )
    assert blocks == []


def test_rejects_unbound_company_paragraph_before_emitting_header() -> None:
    blocks: list[str] = []
    value = payload(AnswerMode.MIXED, uuid4())
    stream = AnswerSectionStream((), blocks.append, expected_mode=AnswerMode.MIXED)
    with pytest.raises(CitationGuardError):
        stream.feed(json.dumps(value))
    assert blocks == [value["knowledge_gap"]]


def test_finish_rejects_a_different_final_prefix() -> None:
    blocks: list[str] = []
    value = payload(AnswerMode.GENERAL_ADVICE)
    stream = AnswerSectionStream(
        (), blocks.append, expected_mode=AnswerMode.GENERAL_ADVICE
    )
    stream.feed(json.dumps(value))
    value["general_advice"]["paragraphs"][0] = "替换内容"
    with pytest.raises(ValueError):
        stream.finish(CustomerServiceAnswer.model_validate(value))


def test_finish_rejects_truncated_or_rewritten_model_json() -> None:
    stream = AnswerSectionStream(
        (), lambda _: None, expected_mode=AnswerMode.GENERAL_ADVICE
    )
    value = payload(AnswerMode.GENERAL_ADVICE)
    content = json.dumps(value)
    stream.feed(content[:-1])
    with pytest.raises(ValueError):
        stream.finish(CustomerServiceAnswer.model_validate(value))
    with pytest.raises(ValueError):
        stream.feed(content.replace("customer-service-answer/1", "different-version"))


def test_empty_general_string_uses_the_same_blocks_as_final_render() -> None:
    value = payload(AnswerMode.GENERAL_ADVICE)
    value["general_advice"]["paragraphs"] = ["", "实际建议"]
    blocks: list[str] = []
    stream = AnswerSectionStream(
        (), blocks.append, expected_mode=AnswerMode.GENERAL_ADVICE
    )
    stream.feed(json.dumps(value))
    answer = CustomerServiceAnswer.model_validate(value)
    stream.finish(answer)
    assert tuple(blocks) == answer_deltas(render_answer(answer, ()))


def test_finish_checks_full_evidence_closure_for_tuple_evidence() -> None:
    item = evidence_item().model_copy(update={"parent_id": uuid4()})
    value = payload(AnswerMode.MIXED, item.chunk_id)
    stream = AnswerSectionStream(
        (item,), lambda _: None, expected_mode=AnswerMode.MIXED
    )
    stream.feed(json.dumps(value))
    with pytest.raises(CitationGuardError):
        stream.finish(CustomerServiceAnswer.model_validate(value))


@pytest.mark.parametrize("tail", [",", "}", "[]"])
def test_invalid_json_tail_is_rejected_after_partial_output(tail: str) -> None:
    blocks: list[str] = []
    stream = AnswerSectionStream(
        (), blocks.append, expected_mode=AnswerMode.GENERAL_ADVICE
    )
    stream.feed(json.dumps(payload(AnswerMode.GENERAL_ADVICE)))
    assert blocks
    with pytest.raises(ValueError):
        stream.feed(json.dumps(payload(AnswerMode.GENERAL_ADVICE)) + tail)


def test_duplicate_fields_are_rejected_without_replacing_visible_gap() -> None:
    blocks: list[str] = []
    stream = AnswerSectionStream(
        (), blocks.append, expected_mode=AnswerMode.GENERAL_ADVICE
    )
    prefix = (
        '{"answer_mode":"GENERAL_ADVICE",'
        '"contract_version":"customer-service-answer/1",'
        '"knowledge_gap":"资料缺口"'
    )
    stream.feed(prefix)
    assert blocks == ["资料缺口"]
    with pytest.raises(ValueError):
        stream.feed(prefix + ',"knowledge_gap":"替换"')
    assert blocks == ["资料缺口"]


def test_expected_mode_rejects_a_model_mode_change() -> None:
    stream = AnswerSectionStream(
        (), lambda _: None, expected_mode=AnswerMode.GENERAL_ADVICE
    )
    with pytest.raises(ValueError):
        stream.feed('{"answer_mode":"MIXED"')


def test_legacy_company_parser_ignores_nested_fields_and_quoted_json() -> None:
    item = evidence_item()
    blocks: list[str] = []
    stream = AnswerSectionStream((item,), blocks.append)
    fake = payload(AnswerMode.MIXED, uuid4())["company_sections"]
    prefix = '{"reasoning":' + json.dumps(
        {"company_sections": fake, "text": json.dumps(fake)}
    )
    stream.feed(prefix)
    assert blocks == []
    company = payload(AnswerMode.MIXED, item.chunk_id)["company_sections"]
    stream.feed(prefix + ',"company_sections":' + json.dumps(company))
    assert blocks == ['## 公司规定 ["流程"]', '向负责人提交 {申请}，注明 "原因"。[1]']


def test_gap_omitted_by_legacy_prompt_remains_compatible() -> None:
    value = payload(AnswerMode.GENERAL_ADVICE)
    del value["knowledge_gap"]
    content = json.dumps(value)
    blocks: list[str] = []
    stream = AnswerSectionStream(
        (), blocks.append, expected_mode=AnswerMode.GENERAL_ADVICE
    )
    stream.feed(content[:-1])
    assert blocks == []
    stream.feed(content)
    answer = CustomerServiceAnswer.model_validate(value)
    stream.finish(answer)
    assert tuple(blocks) == answer_deltas(render_answer(answer, ()))


@pytest.mark.parametrize(
    "missing",
    [("answer_mode",), ("contract_version",), ("answer_mode", "contract_version")],
)
def test_production_stream_missing_root_metadata_emits_nothing(
    missing: tuple[str, ...],
) -> None:
    value = payload(AnswerMode.GENERAL_ADVICE)
    answer = CustomerServiceAnswer.model_validate(value)
    for name in missing:
        del value[name]
    value["general_advice"]["answer_mode"] = AnswerMode.GENERAL_ADVICE.value
    value["general_advice"]["contract_version"] = "customer-service-answer/1"
    blocks: list[str] = []
    stream = AnswerSectionStream(
        (), blocks.append, expected_mode=AnswerMode.GENERAL_ADVICE
    )
    content = json.dumps(value)
    for end in range(1, len(content) + 1):
        stream.feed(content[:end])
    assert blocks == []
    with pytest.raises(ValueError):
        stream.finish(answer)
    assert blocks == []


@pytest.mark.parametrize(
    "field,value",
    [
        ("answer_mode", "MIXED"),
        ("answer_mode", None),
        ("contract_version", "customer-service-answer/2"),
        ("contract_version", None),
    ],
)
def test_production_stream_wrong_metadata_fails_before_emitting(
    field: str, value: str | None
) -> None:
    blocks: list[str] = []
    stream = AnswerSectionStream(
        (), blocks.append, expected_mode=AnswerMode.GENERAL_ADVICE
    )
    content = "{" + json.dumps(field) + ":" + json.dumps(value) + ","
    with pytest.raises(ValueError):
        stream.feed(content)
    assert blocks == []


def test_production_stream_waits_until_both_root_metadata_values_are_complete() -> None:
    value = payload(AnswerMode.GENERAL_ADVICE)
    del value["answer_mode"]
    del value["contract_version"]
    content = json.dumps(value)[:-1]
    blocks: list[str] = []
    stream = AnswerSectionStream(
        (), blocks.append, expected_mode=AnswerMode.GENERAL_ADVICE
    )
    stream.feed(content)
    assert blocks == []
    content += ',"answer_mode":"GENERAL_ADVICE"'
    stream.feed(content)
    assert blocks == []
    content += ',"contract_version":"customer-service-answer/1"'
    stream.feed(content[:-1])
    assert blocks == []
    stream.feed(content)
    assert blocks == [
        value["knowledge_gap"],
        "## 通用建议，非公司制度",
        *value["general_advice"]["paragraphs"],
    ]
    stream.feed(content + "}")
    stream.finish(CustomerServiceAnswer.model_validate_json(content + "}"))
