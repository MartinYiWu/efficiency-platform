"""对规范正文建立并校验证据字符锚点。"""

from __future__ import annotations

import hashlib
import re

from pydantic import BaseModel, ConfigDict, Field, model_validator

from efficiency_platform_agent.capabilities.research.v2.source_families import (
    SourceFamiliesV2,
)
from efficiency_platform_agent.contracts.research_evidence_v2 import (
    EvidenceRefV2,
    SourceDocumentV2,
)


class _FrozenContract(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


class EvidenceCheckV2(_FrozenContract):
    valid: bool
    errors: tuple[str, ...] = Field(default=(), max_length=16)

    @model_validator(mode="after")
    def validate_status(self) -> EvidenceCheckV2:
        if self.valid == bool(self.errors):
            raise ValueError("EVIDENCE_CHECK_STATUS_INVALID")
        return self


class EvidenceContextV2(_FrozenContract):
    brief_digest: str = Field(min_length=64, max_length=64)
    documents: tuple[SourceDocumentV2, ...] = Field(min_length=1, max_length=2_000)
    evidence_refs: tuple[EvidenceRefV2, ...] = Field(min_length=1, max_length=20_000)
    source_families: SourceFamiliesV2

    @model_validator(mode="after")
    def validate_identity(self) -> EvidenceContextV2:
        document_ids = [item.document_id for item in self.documents]
        ref_ids = [item.evidence_id for item in self.evidence_refs]
        family_members = {
            document_id
            for family in self.source_families.families
            for document_id in family.member_document_ids
        }
        if (
            len(set(document_ids)) != len(document_ids)
            or len(set(ref_ids)) != len(ref_ids)
            or any(item.document_id not in document_ids for item in self.evidence_refs)
            or family_members != set(document_ids)
        ):
            raise ValueError("EVIDENCE_CONTEXT_IDENTITY_INVALID")
        return self


class EvidenceValidator:
    def validate(
        self,
        ref: EvidenceRefV2,
        stored_document: SourceDocumentV2 | None,
    ) -> EvidenceCheckV2:
        if not isinstance(ref, EvidenceRefV2):
            raise TypeError("ref 必须是 EvidenceRefV2")
        if stored_document is None:
            return EvidenceCheckV2(
                valid=False, errors=("EVIDENCE_DOCUMENT_NOT_STORED",)
            )
        if not isinstance(stored_document, SourceDocumentV2):
            raise TypeError("stored_document 类型无效")
        errors: list[str] = []
        if ref.document_id != stored_document.document_id:
            errors.append("EVIDENCE_DOCUMENT_MISMATCH")
        if ref.content_hash != stored_document.content_hash:
            errors.append("EVIDENCE_HASH_MISMATCH")
        if not (0 <= ref.char_start < ref.char_end <= len(stored_document.text)):
            errors.append("EVIDENCE_SPAN_OUT_OF_RANGE")
        elif stored_document.text[ref.char_start : ref.char_end] != ref.excerpt:
            errors.append("EVIDENCE_EXCERPT_MISMATCH")
        elif ref.paragraph_index != _paragraph_index(
            stored_document.text, ref.char_start
        ):
            errors.append("EVIDENCE_PARAGRAPH_MISMATCH")
        if ref.acquisition_method != stored_document.discovered_via:
            errors.append("EVIDENCE_ACQUISITION_MISMATCH")
        return EvidenceCheckV2(valid=not errors, errors=tuple(errors))


def build_evidence_ref(
    document: SourceDocumentV2,
    char_start: int,
    char_end: int,
    *,
    paragraph_index: int | None = None,
) -> EvidenceRefV2:
    if not isinstance(document, SourceDocumentV2):
        raise TypeError("document 必须是 SourceDocumentV2")
    if not 0 <= char_start < char_end <= len(document.text):
        raise ValueError("EVIDENCE_SPAN_OUT_OF_RANGE")
    excerpt = document.text[char_start:char_end]
    actual_paragraph = _paragraph_index(document.text, char_start)
    if paragraph_index is not None and paragraph_index != actual_paragraph:
        raise ValueError("EVIDENCE_PARAGRAPH_MISMATCH")
    value = (
        f"{document.document_id}\x00{document.content_hash}\x00"
        f"{char_start}\x00{char_end}\x00{excerpt}"
    )
    digest = hashlib.sha256(value.encode("utf-8")).hexdigest()[:32]
    return EvidenceRefV2(
        evidence_id=f"evidence-{digest}",
        document_id=document.document_id,
        content_hash=document.content_hash,
        paragraph_index=actual_paragraph,
        char_start=char_start,
        char_end=char_end,
        excerpt=excerpt,
        acquisition_method=document.discovered_via,
    )


def _paragraph_index(text: str, char_start: int) -> int:
    return sum(
        1
        for match in re.finditer(r"(?:\r?\n){2,}", text)
        if match.end() <= char_start
    )


__all__ = [
    "EvidenceCheckV2",
    "EvidenceContextV2",
    "EvidenceValidator",
    "build_evidence_ref",
]
