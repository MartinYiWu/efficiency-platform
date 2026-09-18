"""文档版本级去重；不在本层推断真实事件等价。"""

from __future__ import annotations

import hashlib
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from efficiency_platform_agent.contracts.research_evidence_v2 import SourceDocumentV2


class _FrozenContract(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


class DuplicateDocumentV2(_FrozenContract):
    duplicate_document_id: str = Field(min_length=1, max_length=128)
    representative_document_id: str = Field(min_length=1, max_length=128)
    match_basis: Literal["source_item", "canonical_url", "content_hash"]


class DocumentVersionGroupV2(_FrozenContract):
    identity_key: str = Field(min_length=1, max_length=4_096)
    document_ids: tuple[str, ...] = Field(min_length=2, max_length=256)


class DocumentSetV2(_FrozenContract):
    documents: tuple[SourceDocumentV2, ...] = Field(default=(), max_length=2_000)
    duplicates: tuple[DuplicateDocumentV2, ...] = Field(default=(), max_length=2_000)
    version_groups: tuple[DocumentVersionGroupV2, ...] = Field(
        default=(), max_length=2_000
    )
    input_count: int = Field(ge=0)
    unique_count: int = Field(ge=0)
    duplicate_count: int = Field(ge=0)

    @model_validator(mode="after")
    def validate_counts(self) -> DocumentSetV2:
        representative_ids = {item.document_id for item in self.documents}
        duplicate_ids = [item.duplicate_document_id for item in self.duplicates]
        if (
            self.unique_count != len(self.documents)
            or self.duplicate_count != len(self.duplicates)
            or self.input_count != self.unique_count + self.duplicate_count
            or len(representative_ids) != len(self.documents)
            or len(set(duplicate_ids)) != len(duplicate_ids)
            or bool(representative_ids.intersection(duplicate_ids))
            or any(
                item.representative_document_id not in representative_ids
                for item in self.duplicates
            )
        ):
            raise ValueError("DOCUMENT_SET_COUNT_INVALID")
        return self


def deduplicate_documents(
    documents: tuple[SourceDocumentV2, ...],
) -> DocumentSetV2:
    ordered = tuple(sorted(documents, key=lambda item: item.document_id))
    identifiers = [item.document_id for item in ordered]
    if len(set(identifiers)) != len(identifiers):
        raise ValueError("DOCUMENT_ID_DUPLICATED")
    representatives: list[SourceDocumentV2] = []
    duplicates: list[DuplicateDocumentV2] = []
    for document in ordered:
        matched = _find_match(document, representatives)
        if matched is None:
            representatives.append(document)
            continue
        representative, basis = matched
        duplicates.append(
            DuplicateDocumentV2(
                duplicate_document_id=document.document_id,
                representative_document_id=representative.document_id,
                match_basis=basis,
            )
        )
    versions = _version_groups(tuple(representatives))
    return DocumentSetV2(
        documents=tuple(representatives),
        duplicates=tuple(duplicates),
        version_groups=versions,
        input_count=len(ordered),
        unique_count=len(representatives),
        duplicate_count=len(duplicates),
    )


def _find_match(
    document: SourceDocumentV2,
    representatives: list[SourceDocumentV2],
) -> tuple[SourceDocumentV2, Literal["source_item", "canonical_url", "content_hash"]] | None:
    for representative in representatives:
        if (
            representative.source_id == document.source_id
            and representative.source_item_id == document.source_item_id
            and representative.content_hash == document.content_hash
        ):
            return representative, "source_item"
    for representative in representatives:
        if (
            representative.canonical_url == document.canonical_url
            and representative.content_hash == document.content_hash
        ):
            return representative, "canonical_url"
    for representative in representatives:
        if representative.content_hash == document.content_hash:
            return representative, "content_hash"
    return None


def _version_groups(
    documents: tuple[SourceDocumentV2, ...],
) -> tuple[DocumentVersionGroupV2, ...]:
    groups: list[DocumentVersionGroupV2] = []
    consumed: set[str] = set()
    source_items: dict[tuple[str, str], list[SourceDocumentV2]] = {}
    for document in documents:
        source_items.setdefault(
            (document.source_id, document.source_item_id), []
        ).append(document)
    for key, members in sorted(source_items.items()):
        if len({item.content_hash for item in members}) < 2:
            continue
        ordered_ids = tuple(sorted(item.document_id for item in members))
        groups.append(
            DocumentVersionGroupV2(
                identity_key=f"source-item:{key[0]}:{key[1]}",
                document_ids=ordered_ids,
            )
        )
        consumed.update(ordered_ids)
    urls: dict[str, list[SourceDocumentV2]] = {}
    for document in documents:
        if document.document_id not in consumed:
            urls.setdefault(document.canonical_url, []).append(document)
    for url, members in sorted(urls.items()):
        if len({item.content_hash for item in members}) < 2:
            continue
        groups.append(
            DocumentVersionGroupV2(
                identity_key=(
                    "canonical-url:sha256:"
                    + hashlib.sha256(url.encode("utf-8")).hexdigest()
                ),
                document_ids=tuple(sorted(item.document_id for item in members)),
            )
        )
    return tuple(groups)


__all__ = [
    "DocumentSetV2",
    "DocumentVersionGroupV2",
    "DuplicateDocumentV2",
    "deduplicate_documents",
]
