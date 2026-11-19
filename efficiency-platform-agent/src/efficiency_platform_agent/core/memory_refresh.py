"""原执行TTL刷新协议；值对象只核对身份，不授予发送权限。"""

import hashlib
import json
from dataclasses import dataclass, field, replace
from enum import StrEnum
from typing import TYPE_CHECKING, Protocol

from .memory import ConversationScope, require_count, require_id
from .memory_execution import MemoryExecutionContext

if TYPE_CHECKING:
    from .context_control import ContextManifest
    from .memory_execution import MemoryExecutionRecord


class WaitPhase(StrEnum):
    BEFORE_PREPARE = "BEFORE_PREPARE"
    PREPARED = "PREPARED"
    RESERVED = "RESERVED"


class CheckpointMode(StrEnum):
    GRAPH = "GRAPH"
    NONE = "NONE"


class ResumeMode(StrEnum):
    CPU = "cpu"
    PAID = "paid"
    REFRESH = "refresh"


class CandidatePhase(StrEnum):
    PENDING = "PENDING"
    ACKED = "ACKED"
    EXPIRED_UNAPPLIED = "EXPIRED_UNAPPLIED"
    APPLIED_EXPIRED = "APPLIED_EXPIRED"
    ABORTED = "ABORTED"


class RefreshRecordKind(StrEnum):
    WAIT = "WAIT"
    REFRESH = "REFRESH"
    RESULT = "RESULT"


class ResultPhase(StrEnum):
    CAPTURED = "CAPTURED"


class RefreshState(StrEnum):
    ACTIVE = "ACTIVE"
    WAITING_CONTEXT = "WAITING_CONTEXT"
    REFRESH_PENDING = "REFRESH_PENDING"
    BLOCKED = "BLOCKED"
    EXPIRED = "EXPIRED"
    REVOKED = "REVOKED"
    SCRUBBED = "SCRUBBED"
    DELETED = "DELETED"


class ResumeCode(StrEnum):
    CONTEXT_REFRESHED = "CONTEXT_REFRESHED"
    CPU_CONFIRMED = "CPU_CONFIRMED"
    MEMORY_REFRESH_PENDING = "MEMORY_REFRESH_PENDING"
    MEMORY_RESUME_CONFLICT = "MEMORY_RESUME_CONFLICT"
    MEMORY_WAIT_CONSUMED = "MEMORY_WAIT_CONSUMED"
    MEMORY_REVISION_CONFLICT = "MEMORY_REVISION_CONFLICT"
    MEMORY_REFRESH_PACKET_EXPIRED = "MEMORY_REFRESH_PACKET_EXPIRED"
    CONTEXT_REFRESH_LIMIT = "CONTEXT_REFRESH_LIMIT"
    EXECUTION_EXPIRED = "EXECUTION_EXPIRED"
    SOURCE_CHANGED = "SOURCE_CHANGED"
    SOURCE_REVOKED = "SOURCE_REVOKED"
    ACCESS_REVOKED = "ACCESS_REVOKED"
    CONTINUATION_AUTH_UNSUPPORTED = "CONTINUATION_AUTH_UNSUPPORTED"
    MEMORY_REFRESH_CAPABILITY_UNSUPPORTED = "MEMORY_REFRESH_CAPABILITY_UNSUPPORTED"
    MEMORY_REFRESH_SCHEMA_REQUIRED = "MEMORY_REFRESH_SCHEMA_REQUIRED"
    MEMORY_AUTHORITY_UNAVAILABLE = "MEMORY_AUTHORITY_UNAVAILABLE"
    CONTEXT_INTERNAL_AUTH_REQUIRED = "CONTEXT_INTERNAL_AUTH_REQUIRED"
    CONTEXT_SCOPE_MISMATCH = "CONTEXT_SCOPE_MISMATCH"
    MEMORY_RESULT_UNAVAILABLE = "MEMORY_RESULT_UNAVAILABLE"

    @property
    def http_status(self) -> int:
        if self in {self.CONTEXT_REFRESHED, self.CPU_CONFIRMED}:
            return 200
        if self == self.MEMORY_REFRESH_PENDING:
            return 202
        if self in {
            self.MEMORY_REFRESH_SCHEMA_REQUIRED,
            self.MEMORY_AUTHORITY_UNAVAILABLE,
        }:
            return 503
        if self == self.CONTEXT_INTERNAL_AUTH_REQUIRED:
            return 401
        if self == self.CONTEXT_SCOPE_MISMATCH:
            return 403
        return 409


def _digest(value: str) -> None:
    if (
        type(value) is not str
        or len(value) != 64
        or any(c not in "0123456789abcdef" for c in value)
    ):
        raise ValueError("MEMORY_DIGEST_INVALID")


def _identity(value: str) -> None:
    require_id(value)
    if any(0xD800 <= ord(c) <= 0xDFFF for c in value):
        raise ValueError("IDENTIFIER_INVALID")


@dataclass(frozen=True, slots=True)
class MemoryContextWait:
    contract_version: str
    wait_event_id: str
    runtime_id: str
    task_id: str
    execution_id: str
    scope: ConversationScope
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

    def __post_init__(self) -> None:
        if self.contract_version != "memory-context-wait/1" or not isinstance(
            self.scope, ConversationScope
        ):
            raise ValueError("MEMORY_WAIT_INVALID")
        for value in (
            self.wait_event_id,
            self.runtime_id,
            self.task_id,
            self.execution_id,
            self.logical_operation_id,
        ):
            _identity(value)
        for value in (self.scope.tenant_id, self.scope.user_id):
            _identity(value)
        if self.scope.session_id is not None:
            _identity(self.scope.session_id)
        for count in (
            self.expected_packet_revision,
            self.expected_execution_revision,
            self.attempt,
            self.original_deadline,
            self.refresh_count,
        ):
            require_count(count)
        if (
            min(
                self.expected_packet_revision,
                self.expected_execution_revision,
                self.original_deadline,
            )
            <= 0
            or not 1 <= self.attempt <= 3
        ):
            raise ValueError("MEMORY_WAIT_ANCHOR_INVALID")
        if self.refresh_count > 3:
            raise ValueError("CONTEXT_REFRESH_LIMIT")
        for value in (
            self.operation_hash,
            self.semantic_input_hash,
            self.expected_current_context_fingerprint,
        ):
            _digest(value)
        if (
            type(self.wait_phase) is not WaitPhase
            or type(self.checkpoint_mode) is not CheckpointMode
        ):
            raise ValueError("MEMORY_WAIT_PHASE_INVALID")
        if self.wait_phase == WaitPhase.BEFORE_PREPARE:
            if self.canonical_request_hmac is not None:
                raise ValueError("MEMORY_WAIT_HMAC_INVALID")
        else:
            _digest(self.canonical_request_hmac)  # type: ignore[arg-type]
        if (self.stage_id is None) != (self.stage_slot is None):
            raise ValueError("MEMORY_STAGE_INVALID")
        if self.stage_id is not None:
            _identity(self.stage_id)
            require_count(self.stage_slot)  # type: ignore[arg-type]
            if not 1 <= self.stage_slot <= 3:  # type: ignore[operator]
                raise ValueError("MEMORY_STAGE_INVALID")
        if self.checkpoint_mode == CheckpointMode.GRAPH:
            if self.checkpoint_ns != "":
                _identity(self.checkpoint_ns)  # type: ignore[arg-type]
            _identity(self.checkpoint_id)  # type: ignore[arg-type]
        elif self.checkpoint_ns is not None or self.checkpoint_id is not None:
            raise ValueError("MEMORY_CHECKPOINT_INVALID")


@dataclass(frozen=True, slots=True)
class MemoryContextResume:
    wait_event_id: str
    packet_revision: int
    expected_execution_revision: int
    resume_request_id: str
    operation_hash: str
    mode: ResumeMode
    new_content: bool
    contract_version: str
    logical_operation_id: str
    canonical_request_hmac: str | None
    attempt: int
    expected_current_context_fingerprint: str
    refreshed_context: MemoryExecutionContext | None = field(repr=False)

    def __post_init__(self) -> None:
        if (
            self.contract_version != "memory-context-resume/2"
            or type(self.new_content) is not bool
            or self.new_content
            or type(self.mode) is not ResumeMode
        ):
            raise ValueError("MEMORY_RESUME_INVALID")
        for value in (
            self.wait_event_id,
            self.resume_request_id,
            self.logical_operation_id,
        ):
            _identity(value)
        for count in (
            self.packet_revision,
            self.expected_execution_revision,
            self.attempt,
        ):
            require_count(count)
        if (
            min(self.packet_revision, self.expected_execution_revision) <= 0
            or not 1 <= self.attempt <= 3
        ):
            raise ValueError("MEMORY_RESUME_ANCHOR_INVALID")
        for value in (self.operation_hash, self.expected_current_context_fingerprint):
            _digest(value)
        if self.canonical_request_hmac is not None:
            _digest(self.canonical_request_hmac)
        if self.mode == ResumeMode.REFRESH:
            if not isinstance(self.refreshed_context, MemoryExecutionContext):
                raise ValueError("MEMORY_AUTHORIZATION_REQUIRED")
            packet = self.refreshed_context.packet
            if (
                packet.packet_revision <= self.packet_revision
                or packet.execution_revision != self.expected_execution_revision
            ):
                raise ValueError("MEMORY_REVISION_CONFLICT")
        elif self.refreshed_context is not None:
            raise ValueError("MEMORY_RESUME_CONTEXT_INVALID")

    def validate_binding(
        self,
        wait: MemoryContextWait,
        route_scope: ConversationScope,
        execution_id: str,
        current_fingerprint: str,
        original_context: MemoryExecutionContext | None,
    ) -> None:
        if route_scope != wait.scope or execution_id != wait.execution_id:
            raise ValueError("CONTEXT_SCOPE_MISMATCH")
        if (
            (
                self.wait_event_id,
                self.packet_revision,
                self.expected_execution_revision,
                self.operation_hash,
                self.logical_operation_id,
                self.canonical_request_hmac,
                self.attempt,
            )
            != (
                wait.wait_event_id,
                wait.expected_packet_revision,
                wait.expected_execution_revision,
                wait.operation_hash,
                wait.logical_operation_id,
                wait.canonical_request_hmac,
                wait.attempt,
            )
            or self.expected_current_context_fingerprint != current_fingerprint
            or self.expected_current_context_fingerprint
            != wait.expected_current_context_fingerprint
        ):
            raise ValueError("MEMORY_RESUME_CONFLICT")
        if self.refreshed_context is None:
            return
        if original_context is None:
            raise ValueError("MEMORY_AUTHORITY_UNAVAILABLE")
        old, new = original_context, self.refreshed_context
        packet = new.packet
        if (
            old.packet.scope != wait.scope
            or old.packet.task_id != wait.task_id
            or old.packet.execution_id != wait.execution_id
            or old.packet.packet_revision != wait.expected_packet_revision
            or old.packet.execution_revision != wait.expected_execution_revision
            or old.packet.semantic_input_hash != wait.semantic_input_hash
            or packet.expires_at > wait.original_deadline
        ):
            raise ValueError("MEMORY_RESUME_CONFLICT")
        # 比较完整原包与授权，仅允许批准的时间/版本外壳和其派生包摘要变化。
        normalized = replace(
            packet,
            packet_revision=old.packet.packet_revision,
            execution_revision=old.packet.execution_revision,
            issued_at=old.packet.issued_at,
            expires_at=old.packet.expires_at,
        )
        if (
            normalized != old.packet
            or replace(new, packet=old.packet, packet_digest=old.packet_digest) != old
        ):
            raise ValueError("SOURCE_CHANGED")

    def canonical_fingerprint(self) -> str:
        from dataclasses import asdict

        raw = asdict(self)
        if self.refreshed_context is not None:
            context = self.refreshed_context.metadata()
            raw["refreshed_context"] = {
                "schema_version": "memory-context/1",
                "memory_mode": "EXACT_ONLY",
                "scope": context["packet"]["scope"],
                "packet": context["packet"],
                "authorization": {
                    key: value for key, value in context.items() if key != "packet"
                },
            }
        return hashlib.sha256(
            json.dumps(
                raw, sort_keys=True, ensure_ascii=False, separators=(",", ":")
            ).encode("utf-8")
        ).hexdigest()


@dataclass(frozen=True, slots=True)
class MemoryContextResumeReceipt:
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

    def __post_init__(self) -> None:
        if (
            type(self.code) is not ResumeCode
            or type(self.state) is not RefreshState
            or (
                self.candidate_phase is not None
                and type(self.candidate_phase) is not CandidatePhase
            )
            or type(self.dispatch_allowed) is not bool
        ):
            raise ValueError("MEMORY_RECEIPT_INVALID")
        for value in (self.receipt_ref, self.wait_event_id, self.next_wait_event_id):
            if value is not None:
                _identity(value)
        for count in (
            self.packet_revision,
            self.execution_revision,
            self.current_packet_revision,
        ):
            if count is not None:
                require_count(count)
                if count == 0:
                    raise ValueError("MEMORY_RECEIPT_BINDING_INVALID")
        require_count(self.refresh_count)
        if self.refresh_count > 3:
            raise ValueError("CONTEXT_REFRESH_LIMIT")
        if self.candidate_phase is not None and self.refresh_count < 1:
            raise ValueError("MEMORY_RECEIPT_BINDING_INVALID")
        if self.current_context_fingerprint is not None:
            _digest(self.current_context_fingerprint)
        if self.candidate_phase is not None and any(
            value is None
            for value in (
                self.receipt_ref,
                self.wait_event_id,
                self.packet_revision,
                self.execution_revision,
                self.current_packet_revision,
                self.current_context_fingerprint,
            )
        ):
            raise ValueError("MEMORY_RECEIPT_BINDING_INVALID")
        if self.code == ResumeCode.CONTEXT_REFRESHED and (
            self.candidate_phase != CandidatePhase.ACKED
            or self.state != RefreshState.ACTIVE
            or self.current_packet_revision != self.packet_revision
        ):
            raise ValueError("MEMORY_RECEIPT_SUCCESS_INVALID")
        if self.dispatch_allowed and (
            self.code != ResumeCode.CONTEXT_REFRESHED
            or self.candidate_phase != CandidatePhase.ACKED
            or self.state != RefreshState.ACTIVE
        ):
            raise ValueError("MEMORY_RECEIPT_DISPATCH_INVALID")
        if self.candidate_phase == CandidatePhase.PENDING and (
            self.code != ResumeCode.MEMORY_REFRESH_PENDING
            or self.state != RefreshState.REFRESH_PENDING
        ):
            raise ValueError("MEMORY_RECEIPT_PENDING_INVALID")
        if (
            self.code == ResumeCode.MEMORY_REFRESH_PENDING
            and self.candidate_phase != CandidatePhase.PENDING
        ):
            raise ValueError("MEMORY_RECEIPT_PENDING_INVALID")
        if (
            self.candidate_phase == CandidatePhase.ACKED
            and self.code != ResumeCode.CONTEXT_REFRESHED
        ):
            raise ValueError("MEMORY_RECEIPT_SUCCESS_INVALID")
        if (
            self.candidate_phase
            in {CandidatePhase.EXPIRED_UNAPPLIED, CandidatePhase.APPLIED_EXPIRED}
            and self.code != ResumeCode.MEMORY_REFRESH_PACKET_EXPIRED
        ):
            raise ValueError("MEMORY_RECEIPT_EXPIRY_INVALID")
        if self.code == ResumeCode.MEMORY_REFRESH_PACKET_EXPIRED:
            if self.current_packet_revision is None or self.packet_revision is None:
                raise ValueError("MEMORY_RECEIPT_BINDING_INVALID")
            if (
                self.candidate_phase
                not in {
                    CandidatePhase.EXPIRED_UNAPPLIED,
                    CandidatePhase.APPLIED_EXPIRED,
                }
                or self.dispatch_allowed
                or self.state
                not in {RefreshState.WAITING_CONTEXT, RefreshState.BLOCKED}
            ):
                raise ValueError("MEMORY_RECEIPT_EXPIRY_INVALID")
            if self.candidate_phase == CandidatePhase.EXPIRED_UNAPPLIED and (
                self.current_packet_revision >= self.packet_revision
                or self.next_wait_event_id is not None
            ):
                raise ValueError("MEMORY_RECEIPT_EXPIRY_INVALID")
            if (
                self.candidate_phase == CandidatePhase.APPLIED_EXPIRED
                and self.current_packet_revision != self.packet_revision
            ):
                raise ValueError("MEMORY_RECEIPT_EXPIRY_INVALID")
            if (
                self.candidate_phase == CandidatePhase.EXPIRED_UNAPPLIED
                and self.refresh_count < 3
                and self.state != RefreshState.WAITING_CONTEXT
            ):
                raise ValueError("MEMORY_RECEIPT_EXPIRY_INVALID")
            if self.candidate_phase == CandidatePhase.APPLIED_EXPIRED and (
                self.state == RefreshState.WAITING_CONTEXT
            ) != (self.next_wait_event_id is not None):
                raise ValueError("MEMORY_RECEIPT_NEXT_WAIT_INVALID")
            if self.refresh_count == 3 and (
                self.state != RefreshState.BLOCKED
                or self.next_wait_event_id is not None
            ):
                raise ValueError("MEMORY_RECEIPT_LIMIT_INVALID")
        if self.next_wait_event_id is not None and (
            self.next_wait_event_id == self.wait_event_id
            or self.candidate_phase != CandidatePhase.APPLIED_EXPIRED
            or self.state != RefreshState.WAITING_CONTEXT
            or self.refresh_count >= 3
            or self.dispatch_allowed
        ):
            raise ValueError("MEMORY_RECEIPT_NEXT_WAIT_INVALID")
        if self.code in {
            ResumeCode.CPU_CONFIRMED,
            ResumeCode.CONTINUATION_AUTH_UNSUPPORTED,
        } and (self.candidate_phase is not None or self.packet_revision is not None):
            raise ValueError("MEMORY_RECEIPT_MODE_INVALID")


class MemoryContextRefreshPort(Protocol):
    async def validate_execution_manifest(
        self, manifest: "ContextManifest", current_record: "MemoryExecutionRecord"
    ) -> bool: ...

    async def get_wait(
        self,
        scope: ConversationScope,
        execution_id: str,
        wait_event_id: str | None = None,
    ) -> MemoryContextWait | None: ...

    async def resume(
        self, scope: ConversationScope, execution_id: str, command: MemoryContextResume
    ) -> MemoryContextResumeReceipt: ...
