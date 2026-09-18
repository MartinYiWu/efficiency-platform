"""R07 规范正文证据定位测试。"""

from __future__ import annotations

from datetime import UTC, datetime

from efficiency_platform_agent.capabilities.research.v2.evidence import (
    EvidenceValidator,
    build_evidence_ref,
)
from efficiency_platform_agent.contracts.research_evidence_v2 import (
    EvidenceRefV2,
    SourceDocumentV2,
)


def _document() -> SourceDocumentV2:
    return SourceDocumentV2(
        document_id="doc-1",
        candidate_id="candidate-1",
        source_id="source-1",
        source_item_id="item-1",
        original_url="https://official.example/release",
        canonical_url="https://official.example/release",
        publisher_id="official.example",
        title="测试结果",
        text="第一段。\n\nAcme 表示测试准确率为 9%。",
        content_hash="a" * 64,
        artifact_ref="artifact:doc-1",
        discovered_via="public_page",
        content_scope="full",
        published_at=datetime(2026, 9, 15, tzinfo=UTC),
        published_timezone_known=True,
        time_precision="exact",
        extractor_version="extractor/2",
        source_role="primary",
    )


def test_valid_unicode_span_matches_stored_canonical_text() -> None:
    document = _document()
    start = document.text.index("准确率")
    end = start + len("准确率为 9%")
    ref = build_evidence_ref(document, start, end)

    check = EvidenceValidator().validate(ref, document)

    assert check.valid is True
    assert check.errors == ()
    assert ref.excerpt == "准确率为 9%"


def test_url_without_stored_body_cannot_be_evidence() -> None:
    ref = EvidenceRefV2(
        evidence_id="evidence-1",
        document_id="doc-1",
        content_hash="a" * 64,
        char_start=0,
        char_end=2,
        excerpt="正文",
        acquisition_method="public_page",
    )

    check = EvidenceValidator().validate(ref, None)

    assert check.valid is False
    assert check.errors == ("EVIDENCE_DOCUMENT_NOT_STORED",)


def test_hash_span_excerpt_and_acquisition_are_cross_checked() -> None:
    document = _document()
    valid = build_evidence_ref(document, 0, 4)
    stale = valid.model_copy(update={"content_hash": "b" * 64})
    wrong_excerpt = valid.model_copy(update={"excerpt": "第二段"})
    wrong_method = valid.model_copy(update={"acquisition_method": "rss"})
    wrong_paragraph = valid.model_copy(update={"paragraph_index": 9})

    validator = EvidenceValidator()

    assert validator.validate(stale, document).errors == ("EVIDENCE_HASH_MISMATCH",)
    assert validator.validate(wrong_excerpt, document).errors == (
        "EVIDENCE_EXCERPT_MISMATCH",
    )
    assert validator.validate(wrong_method, document).errors == (
        "EVIDENCE_ACQUISITION_MISMATCH",
    )
    assert validator.validate(wrong_paragraph, document).errors == (
        "EVIDENCE_PARAGRAPH_MISMATCH",
    )
