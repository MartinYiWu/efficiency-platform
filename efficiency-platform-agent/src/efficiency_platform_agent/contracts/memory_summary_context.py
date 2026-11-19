"""随Java原授权一同冻结的已提交摘要；普通模型输出不能构造此快照。"""

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from .memory import ConversationScopeModel, SourceDependencyModel
from .memory_summary import SummaryBasisEvent, SummaryInputSource, SummarySegment


class _Boundary(BaseModel):
    model_config = ConfigDict(
        extra="forbid", strict=True, frozen=True, hide_input_in_errors=True
    )


class OriginalMessageSnapshot(_Boundary):
    message_id: str = Field(min_length=1, max_length=128)
    role: Literal["user", "assistant"]
    content_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    safety_dependencies: tuple[SourceDependencyModel, ...] = Field(
        min_length=1, max_length=512
    )
    group_completed: bool


class CommittedSummarySnapshot(_Boundary):
    segment: SummarySegment
    sources: tuple[SummaryInputSource, ...] = Field(min_length=1, max_length=128)
    basis_events: tuple[SummaryBasisEvent, ...] = Field(max_length=897)
    source_revision: int = Field(ge=0)
    authority_ref: str = Field(min_length=1, max_length=128)
    commit_ref: str = Field(min_length=1, max_length=128)
    status: Literal["COMMITTED"]
    authorized: Literal[True]
    current_dependencies: tuple[SourceDependencyModel, ...] = Field(
        min_length=1, max_length=512
    )
    retention_ref: str = Field(min_length=1, max_length=128)
    expires_at: int = Field(gt=0)
    summary_dependency: SourceDependencyModel
    covered_message_ids: tuple[str, ...] = Field(min_length=1, max_length=128)


class MemorySummaryContextSnapshot(_Boundary):
    contract_version: Literal["memory-summary-context/1"]
    scope: ConversationScopeModel
    original_messages: tuple[OriginalMessageSnapshot, ...] = Field(max_length=128)
    summaries: tuple[CommittedSummarySnapshot, ...] = Field(max_length=32)
