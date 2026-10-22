"""智能客服文档摄取与索引验证的稳定契约。"""

from __future__ import annotations

from typing import Literal
from uuid import UUID

from pydantic import AnyHttpUrl, BaseModel, ConfigDict, Field, field_validator

EvidenceMode = Literal["FULL_ONLY", "EXTRACTIVE_NARRATIVE"]
BlockKind = Literal["NUMBERED_RULE", "LIST", "TABLE", "CODE", "PARAGRAPH"]


class IngestJobRequest(BaseModel):
    """Java 提交的不可扩展文档摄取请求。"""

    model_config = ConfigDict(extra="forbid", frozen=True)

    contract_version: Literal["customer-service-ingest/1"]
    task_id: UUID
    tenant_id: str = Field(min_length=1, max_length=64)
    knowledge_base_id: UUID
    document_id: UUID
    document_version_id: UUID
    document_title: str = Field(min_length=1, max_length=255)
    version_no: int = Field(gt=0)
    file_name: str = Field(min_length=1, max_length=255)
    content_type: Literal[
        "application/pdf",
        "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        "text/markdown",
        "text/plain",
        "text/html",
    ]
    size_bytes: int = Field(ge=1, le=10 * 1024 * 1024)
    sha256: str = Field(pattern=r"^[a-f0-9]{64}$")
    download_url: AnyHttpUrl
    evidence_mode: EvidenceMode = "FULL_ONLY"

    @field_validator("file_name")
    @classmethod
    def validate_file_name(cls, value: str) -> str:
        if "/" in value or "\\" in value or value in {".", ".."}:
            raise ValueError("file_name 无效")
        return value

    @field_validator("download_url")
    @classmethod
    def require_https(cls, value: AnyHttpUrl) -> AnyHttpUrl:
        if value.scheme != "https":
            raise ValueError("download_url 必须使用 HTTPS")
        return value


IngestStatus = Literal["QUEUED", "RUNNING", "SUCCEEDED", "FAILED", "CANCELLED"]
IngestStage = Literal["PREFLIGHT", "PARSE", "OCR", "CHUNK", "EMBED", "VERIFY"]


class IngestJobView(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    contract_version: Literal["customer-service-ingest-view/1"] = (
        "customer-service-ingest-view/1"
    )
    task_id: UUID
    status: IngestStatus
    stage: IngestStage
    progress_percent: int = Field(ge=0, le=100)
    error_code: str | None = None
    error_message: str | None = None


class IndexDocumentMember(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    document_id: UUID
    document_version_id: UUID
    document_sha256: str = Field(pattern=r"^[a-f0-9]{64}$")


class IndexVerifyRequest(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    contract_version: Literal["customer-service-index-verify/1"]
    release_id: UUID
    knowledge_base_id: UUID
    documents: tuple[IndexDocumentMember, ...] = Field(min_length=1)


class IndexVerifyView(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    contract_version: Literal["customer-service-index-verify-view/1"] = (
        "customer-service-index-verify-view/1"
    )
    release_id: UUID
    status: Literal["READY", "FAILED"]
    document_count: int = Field(ge=0)
    chunk_count: int = Field(ge=0)
    checksum: str | None = None
    error_code: str | None = None
    error_message: str | None = None


class ParsedDocument(BaseModel):
    """Docling/OCR 归一化后供确定性分块消费的最小文档。"""

    model_config = ConfigDict(extra="forbid", frozen=True)

    markdown: str = Field(min_length=1)
    page_markers: tuple[tuple[int, int], ...] = ()


class ChunkDraft(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    chunk_no: int = Field(gt=0)
    section_path: str | None
    page_no: int | None = Field(default=None, gt=0)
    content: str = Field(min_length=1)
    content_hash: str = Field(pattern=r"^[a-f0-9]{64}$")
    token_count: int = Field(gt=0)
    parent_no: int | None = Field(default=None, gt=0)
    child_no: int | None = Field(default=None, gt=0)
    start_offset: int | None = Field(default=None, ge=0)
    end_offset: int | None = Field(default=None, gt=0)


class ParentDraft(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    parent_no: int = Field(gt=0)
    block_kind: BlockKind = "LIST"
    evidence_mode: EvidenceMode = "FULL_ONLY"
    section_path: str | None
    page_start: int | None = Field(default=None, gt=0)
    page_end: int | None = Field(default=None, gt=0)
    content: str = Field(min_length=1)
    content_hash: str = Field(pattern=r"^[a-f0-9]{64}$")
    token_count: int = Field(gt=0)
    children: tuple[ChunkDraft, ...] = Field(min_length=1)


class IndexVerificationResult(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    release_id: UUID
    document_count: int = Field(gt=0)
    chunk_count: int = Field(gt=0)
    checksum: str = Field(pattern=r"^[a-f0-9]{64}$")


__all__ = [
    "ChunkDraft",
    "IndexDocumentMember",
    "IndexVerificationResult",
    "IndexVerifyRequest",
    "IndexVerifyView",
    "IngestJobRequest",
    "IngestJobView",
    "IngestStage",
    "ParentDraft",
    "ParsedDocument",
]
