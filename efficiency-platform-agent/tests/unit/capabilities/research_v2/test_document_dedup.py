"""R05 文档级去重与版本保留测试。"""

from __future__ import annotations

from datetime import UTC, datetime

from efficiency_platform_agent.capabilities.research.v2.deduplication import (
    deduplicate_documents,
)
from efficiency_platform_agent.contracts.research_evidence_v2 import SourceDocumentV2


def _document(document_id: str, **changes: object) -> SourceDocumentV2:
    values: dict[str, object] = {
        "document_id": document_id,
        "candidate_id": f"candidate-{document_id}",
        "source_id": "source-1",
        "source_item_id": "article-1",
        "source_item_version": "v1",
        "original_url": "https://news.example/read?id=1",
        "canonical_url": "https://news.example/read?id=1",
        "publisher_id": "news.example",
        "title": "Title",
        "text": "Body",
        "content_hash": "a" * 64,
        "artifact_ref": f"inline:{document_id}",
        "discovered_via": "api",
        "content_scope": "full",
        "published_at": datetime(2026, 9, 15, tzinfo=UTC),
        "published_timezone_known": True,
        "time_precision": "exact",
        "extractor_version": "extractor/2",
    }
    values.update(changes)
    return SourceDocumentV2.model_validate(values)


def test_same_canonical_url_and_hash_deduplicates_deterministically() -> None:
    result = deduplicate_documents(
        (_document("doc-b"), _document("doc-a", candidate_id="candidate-a"))
    )

    assert [item.document_id for item in result.documents] == ["doc-a"]
    assert result.duplicates[0].duplicate_document_id == "doc-b"
    assert result.duplicates[0].representative_document_id == "doc-a"
    assert result.input_count == result.unique_count + result.duplicate_count


def test_same_url_with_different_hash_keeps_both_versions() -> None:
    first = _document("doc-a", content_hash="a" * 64, source_item_version="v1")
    second = _document("doc-b", content_hash="b" * 64, source_item_version="v2")

    result = deduplicate_documents((second, first))

    assert [item.document_id for item in result.documents] == ["doc-a", "doc-b"]
    assert result.duplicates == ()
    assert result.version_groups[0].document_ids == ("doc-a", "doc-b")


def test_same_body_hash_across_different_urls_is_one_document_version() -> None:
    first = _document("doc-a")
    second = _document(
        "doc-b",
        source_id="source-2",
        source_item_id="other-2",
        original_url="https://mirror.example/story/2",
        canonical_url="https://mirror.example/story/2",
        publisher_id="mirror.example",
    )

    result = deduplicate_documents((first, second))

    assert len(result.documents) == 1
    assert result.duplicates[0].match_basis == "content_hash"


def test_article_id_query_keeps_distinct_documents_even_when_path_matches() -> None:
    first = _document("doc-a", canonical_url="https://news.example/read?id=1")
    second = _document(
        "doc-b",
        source_item_id="article-2",
        canonical_url="https://news.example/read?id=2",
        original_url="https://news.example/read?id=2",
        content_hash="b" * 64,
    )

    result = deduplicate_documents((first, second))

    assert len(result.documents) == 2
    assert result.duplicates == ()
