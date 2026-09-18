"""R06 来源家族与独立性测试。"""

from __future__ import annotations

from datetime import UTC, datetime

from efficiency_platform_agent.capabilities.research.v2.source_families import (
    SourceFamilyResolver,
)
from efficiency_platform_agent.contracts.research_evidence_v2 import SourceDocumentV2


def _document(index: int, **changes: object) -> SourceDocumentV2:
    values: dict[str, object] = {
        "document_id": f"doc-{index}",
        "candidate_id": f"candidate-{index}",
        "source_id": f"source-{index}",
        "source_item_id": f"item-{index}",
        "original_url": f"https://site{index}.example/story",
        "canonical_url": f"https://site{index}.example/story",
        "publisher_id": f"site{index}.example",
        "title": "Title",
        "text": "Wire copy",
        "content_hash": "a" * 64,
        "artifact_ref": f"inline:{index}",
        "discovered_via": "api",
        "content_scope": "full",
        "published_at": datetime(2026, 9, 15, tzinfo=UTC),
        "published_timezone_known": True,
        "time_precision": "exact",
        "extractor_version": "extractor/2",
        "source_role": "reporting",
    }
    values.update(changes)
    return SourceDocumentV2.model_validate(values)


def test_ten_wire_reposts_are_one_unknown_origin_family() -> None:
    documents = tuple(_document(index) for index in range(10))

    result = SourceFamilyResolver().resolve(documents)

    assert result.family_count == 1
    assert result.confirmed_independent_count == 0
    assert result.families[0].independence_status == "unknown"


def test_known_ownership_group_merges_domains_and_confirms_family() -> None:
    first = _document(1, ownership_group="group-a", content_hash="1" * 64)
    second = _document(2, ownership_group="group-a", content_hash="2" * 64)

    result = SourceFamilyResolver().resolve((first, second))

    assert result.family_count == 1
    assert result.confirmed_independent_count == 1
    assert "ownership_group" in result.families[0].basis


def test_different_domains_do_not_automatically_count_as_independent() -> None:
    first = _document(1, content_hash="1" * 64)
    second = _document(2, content_hash="2" * 64)

    result = SourceFamilyResolver().resolve((first, second))

    assert result.family_count == 2
    assert result.confirmed_independent_count == 0


def test_distinct_primary_publishers_are_confirmed_independent_families() -> None:
    first = _document(1, content_hash="1" * 64, source_role="primary")
    second = _document(2, content_hash="2" * 64, source_role="primary")

    result = SourceFamilyResolver().resolve((first, second))

    assert result.family_count == 2
    assert result.confirmed_independent_count == 2
