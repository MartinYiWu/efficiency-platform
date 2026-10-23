"""原文抽取只接受完整句段编号。"""

from hashlib import sha256
from uuid import uuid4

import pytest

from efficiency_platform_agent.agents.customer_service.evidence_extract import (
    ExtractionSelection,
    select_spans,
    split_sentences,
)


def test_selected_sentences_follow_source_order_with_exact_offsets_and_hashes():
    text = "第一句。第二句！\n\n第三段？"
    sentences = split_sentences(text)
    parent_id = uuid4()
    selection = ExtractionSelection(
        parent_id=parent_id, selected_sentence_ids=(3, 1), reason="相关"
    )
    spans = select_spans(text, parent_id, sentences, selection)
    assert [(s.start_offset, s.end_offset) for s in spans] == [(0, 4), (10, 14)]
    assert all(
        s.content_hash
        == sha256(text[s.start_offset : s.end_offset].encode()).hexdigest()
        for s in spans
    )
    assert all("\n" not in s.text for s in sentences)


@pytest.mark.parametrize("ids", [(), (99,), (1, 1)])
def test_empty_unknown_and_repeated_ids_reject_entire_parent(ids):
    parent_id = uuid4()
    with pytest.raises(ValueError):
        select_spans(
            "第一句。",
            parent_id,
            split_sentences("第一句。"),
            ExtractionSelection(
                parent_id=parent_id, selected_sentence_ids=ids, reason="相关"
            ),
        )


def test_tampered_offsets_and_parent_id_are_rejected():
    parent_id = uuid4()
    selection = ExtractionSelection(
        parent_id=parent_id, selected_sentence_ids=(1,), reason="相关"
    )
    sentences = split_sentences("第一句。")
    with pytest.raises(ValueError):
        select_spans(
            "第一句。",
            parent_id,
            (sentences[0].model_copy(update={"start_offset": 1}),),
            selection,
        )
    with pytest.raises(ValueError):
        select_spans("第一句。", uuid4(), sentences, selection)


@pytest.mark.parametrize(
    "text", ["没有完整句号", "结束。剩余残句", "English abbreviation e.g. unsafe."]
)
def test_unreliable_sentence_boundaries_fail_closed(text):
    with pytest.raises(ValueError):
        split_sentences(text)
