"""文档上传与解析链路的最小稳定契约。"""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum


class DocumentQualityStatus(StrEnum):
    ACCEPTED = "accepted"
    ACCEPTED_WITH_WARNINGS = "accepted_with_warnings"
    REVIEW_REQUIRED = "review_required"
    REJECTED = "rejected"


@dataclass(frozen=True, slots=True)
class DocumentPreflightResult:
    quality_status: DocumentQualityStatus
    reason_codes: tuple[str, ...]
    extension: str
    mime_type: str
    size_bytes: int


@dataclass(frozen=True, slots=True)
class DocumentIngestionResult:
    document_ast: object | None
    quality_status: DocumentQualityStatus
    reason_codes: tuple[str, ...]
    chunk_ids: tuple[str, ...]
    artifact_reference: str | None


__all__ = [
    "DocumentIngestionResult",
    "DocumentPreflightResult",
    "DocumentQualityStatus",
]
