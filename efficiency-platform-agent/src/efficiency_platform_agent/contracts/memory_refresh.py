"""内部刷新边界；显式转换既有信封，不把Pydantic带入核心。"""

from typing import Literal, Self

from pydantic import BaseModel, ConfigDict, Field, model_validator

from efficiency_platform_agent.core.memory_refresh import (
    CandidatePhase,
    CheckpointMode,
    MemoryContextResume,
    MemoryContextResumeReceipt,
    MemoryContextWait,
    RefreshState,
    ResumeCode,
    ResumeMode,
    WaitPhase,
)

from .memory import ConversationScopeModel
from .memory_context import MemoryContextEnvelope


class _Boundary(BaseModel):
    model_config = ConfigDict(
        extra="forbid", strict=True, frozen=True, hide_input_in_errors=True
    )


class MemoryContextWaitModel(_Boundary):
    contract_version: Literal["memory-context-wait/1"]
    wait_event_id: str
    runtime_id: str
    task_id: str
    execution_id: str
    scope: ConversationScopeModel
    expected_packet_revision: int
    expected_execution_revision: int
    expected_current_context_fingerprint: str
    operation_hash: str
    logical_operation_id: str
    semantic_input_hash: str
    canonical_request_hmac: str | None
    attempt: int
    stage_id: str | None
    stage_slot: int | None
    checkpoint_mode: CheckpointMode
    checkpoint_ns: str | None
    checkpoint_id: str | None
    wait_phase: WaitPhase
    original_deadline: int
    refresh_count: int

    @model_validator(mode="after")
    def validate_core(self) -> Self:
        self.to_core()
        return self

    def to_core(self) -> MemoryContextWait:
        return MemoryContextWait(**(self.__dict__ | {"scope": self.scope.to_core()}))


class MemoryContextResumeModel(_Boundary):
    wait_event_id: str
    packet_revision: int
    expected_execution_revision: int
    resume_request_id: str
    operation_hash: str
    mode: ResumeMode
    new_content: bool
    contract_version: Literal["memory-context-resume/2"]
    logical_operation_id: str
    canonical_request_hmac: str | None
    attempt: int
    expected_current_context_fingerprint: str
    refreshed_context: MemoryContextEnvelope | None = Field(repr=False)

    @model_validator(mode="after")
    def validate_core(self) -> Self:
        self.to_core()
        return self

    def to_core(self) -> MemoryContextResume:
        if self.mode != ResumeMode.REFRESH and self.refreshed_context is not None:
            raise ValueError("MEMORY_RESUME_CONTEXT_INVALID")
        context = (
            self.refreshed_context.to_core()
            if self.refreshed_context is not None
            else None
        )
        return MemoryContextResume(**(self.__dict__ | {"refreshed_context": context}))


class MemoryContextResumeReceiptModel(_Boundary):
    code: ResumeCode
    receipt_ref: str | None
    wait_event_id: str | None
    packet_revision: int | None
    execution_revision: int | None
    current_packet_revision: int | None
    current_context_fingerprint: str | None
    refresh_count: int
    state: RefreshState
    candidate_phase: CandidatePhase | None
    next_wait_event_id: str | None
    dispatch_allowed: bool

    @model_validator(mode="after")
    def validate_core(self) -> Self:
        self.to_core()
        return self

    def to_core(self) -> MemoryContextResumeReceipt:
        return MemoryContextResumeReceipt(**self.__dict__)
