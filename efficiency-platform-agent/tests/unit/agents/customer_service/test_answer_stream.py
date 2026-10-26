from types import SimpleNamespace
from uuid import uuid4

import pytest

from efficiency_platform_agent.agents.customer_service.answer_stream import (
    AnswerSectionStream,
)
from efficiency_platform_agent.agents.customer_service.citations import (
    CitationGuardError,
)


def test_releases_complete_supported_paragraph_before_json_finishes() -> None:
    chunk_id = uuid4()
    blocks: list[str] = []
    evidence = SimpleNamespace(entries=(SimpleNamespace(chunk_id=chunk_id),))
    stream = AnswerSectionStream(evidence, blocks.append)  # type: ignore[arg-type]
    prefix = (
        '{"company_sections":[{"title":"审查要求","paragraphs":['
        '{"text":"提交前审查代码","supporting_chunk_ids":["'
        f'{chunk_id}"' + "]}"
    )
    stream.feed(prefix[:-1])
    assert blocks == []
    stream.feed(prefix)
    assert blocks == ["## 审查要求", "提交前审查代码[1]"]


def test_rejects_streamed_paragraph_with_unbound_citation() -> None:
    evidence = SimpleNamespace(entries=(SimpleNamespace(chunk_id=uuid4()),))
    stream = AnswerSectionStream(evidence, lambda _: None)  # type: ignore[arg-type]
    content = (
        '{"company_sections":[{"title":"审查要求","paragraphs":['
        '{"text":"提交前审查代码","supporting_chunk_ids":["'
        f'{uuid4()}"' + "]}"
    )
    with pytest.raises(CitationGuardError):
        stream.feed(content)
