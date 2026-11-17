from __future__ import annotations

from typing import Literal, Self, cast

from pydantic import BaseModel, ConfigDict, Field, model_validator

from efficiency_platform_agent.core import memory as core


class _Boundary(BaseModel):
    model_config = ConfigDict(
        extra="forbid", strict=True, frozen=True, hide_input_in_errors=True
    )


class ConversationScopeModel(_Boundary):
    tenant_id: str
    user_id: str
    domain: Literal["operations", "customer-service", "hr"]
    top_level_agent_id: Literal["operations", "customer-service", "hr"]
    session_kind: Literal["CONVERSATION", "TASK_ONLY"]
    session_id: str | None

    @model_validator(mode="after")
    def validate_core(self) -> Self:
        self.to_core()
        return self

    def to_core(self) -> core.ConversationScope:
        return core.ConversationScope(
            tenant_id=self.tenant_id,
            user_id=self.user_id,
            domain=self.domain,
            top_level_agent_id=self.top_level_agent_id,
            session_kind=self.session_kind,
            session_id=self.session_id,
        )

    @classmethod
    def from_core(cls, value: core.ConversationScope) -> Self:
        return cls(
            tenant_id=value.tenant_id,
            user_id=value.user_id,
            domain=cast(Literal["operations", "customer-service", "hr"], value.domain),
            top_level_agent_id=cast(
                Literal["operations", "customer-service", "hr"],
                value.top_level_agent_id,
            ),
            session_kind=cast(Literal["CONVERSATION", "TASK_ONLY"], value.session_kind),
            session_id=value.session_id,
        )


class ExecutionScopeModel(_Boundary):
    conversation: ConversationScopeModel
    task_id: str
    execution_id: str
    subtask_id: str
    purpose: str
    execution_agent_id: str

    @model_validator(mode="after")
    def validate_core(self) -> Self:
        self.to_core()
        return self

    def to_core(self) -> core.ExecutionScope:
        return core.ExecutionScope(
            conversation=self.conversation.to_core(),
            task_id=self.task_id,
            execution_id=self.execution_id,
            subtask_id=self.subtask_id,
            purpose=self.purpose,
            execution_agent_id=self.execution_agent_id,
        )

    @classmethod
    def from_core(cls, value: core.ExecutionScope) -> Self:
        return cls(
            conversation=ConversationScopeModel.from_core(value.conversation),
            task_id=value.task_id,
            execution_id=value.execution_id,
            subtask_id=value.subtask_id,
            purpose=value.purpose,
            execution_agent_id=value.execution_agent_id,
        )


class SourceDependencyModel(_Boundary):
    source_type: str
    source_id: str
    source_version: str
    grant_epoch: int = 0
    source_epoch: int = 0
    deletion_epoch: int = 0

    @model_validator(mode="after")
    def validate_core(self) -> Self:
        self.to_core()
        return self

    def to_core(self) -> core.SourceDependency:
        return core.SourceDependency(
            source_type=self.source_type,
            source_id=self.source_id,
            source_version=self.source_version,
            grant_epoch=self.grant_epoch,
            source_epoch=self.source_epoch,
            deletion_epoch=self.deletion_epoch,
        )

    @classmethod
    def from_core(cls, value: core.SourceDependency) -> Self:
        return cls(
            source_type=value.source_type,
            source_id=value.source_id,
            source_version=value.source_version,
            grant_epoch=value.grant_epoch,
            source_epoch=value.source_epoch,
            deletion_epoch=value.deletion_epoch,
        )


class MemoryReferenceModel(_Boundary):
    item_id: str
    version: str
    field_key: str
    value: str = Field(repr=False)
    safety_dependencies: tuple[SourceDependencyModel, ...] = ()

    @model_validator(mode="after")
    def validate_core(self) -> Self:
        self.to_core()
        return self

    def to_core(self) -> core.MemoryReference:
        return core.MemoryReference(
            item_id=self.item_id,
            version=self.version,
            field_key=self.field_key,
            value=self.value,
            safety_dependencies=tuple(
                item.to_core() for item in self.safety_dependencies
            ),
        )

    @classmethod
    def from_core(cls, value: core.MemoryReference) -> Self:
        return cls(
            item_id=value.item_id,
            version=value.version,
            field_key=value.field_key,
            value=value.value,
            safety_dependencies=tuple(
                SourceDependencyModel.from_core(item)
                for item in value.safety_dependencies
            ),
        )


class MemoryPolicyModel(_Boundary):
    policy_id: str
    version: str
    domain: Literal["operations", "customer-service", "hr"]
    agent_ids: frozenset[str]
    enabled: bool = True
    readable_layers: frozenset[str] = frozenset()
    writable_kinds: frozenset[str] = frozenset()
    allowed_scopes: frozenset[str] = frozenset()
    field_allowlist: frozenset[str] = frozenset()
    sensitivity_levels: frozenset[str] = frozenset()
    confirmation_required: bool = True
    auto_extract: bool = False
    shared_approval_required: bool = True
    source_types: frozenset[str] = frozenset()
    retention_days: int = 0
    recall_top_k: int = 0
    recall_token_limit: int = 0
    max_paid_operations: int = 0
    degradation_mode: str = "disabled"
    source_deletion_mode: str = "block"
    schema_version: str = "1"
    model_version: str = "none"
    tokenizer_version: str = "none"

    @model_validator(mode="after")
    def validate_core(self) -> Self:
        self.to_core()
        return self

    def to_core(self) -> core.MemoryPolicy:
        return core.MemoryPolicy(
            policy_id=self.policy_id,
            version=self.version,
            domain=self.domain,
            agent_ids=self.agent_ids,
            enabled=self.enabled,
            readable_layers=self.readable_layers,
            writable_kinds=self.writable_kinds,
            allowed_scopes=self.allowed_scopes,
            field_allowlist=self.field_allowlist,
            sensitivity_levels=self.sensitivity_levels,
            confirmation_required=self.confirmation_required,
            auto_extract=self.auto_extract,
            shared_approval_required=self.shared_approval_required,
            source_types=self.source_types,
            retention_days=self.retention_days,
            recall_top_k=self.recall_top_k,
            recall_token_limit=self.recall_token_limit,
            max_paid_operations=self.max_paid_operations,
            degradation_mode=self.degradation_mode,
            source_deletion_mode=self.source_deletion_mode,
            schema_version=self.schema_version,
            model_version=self.model_version,
            tokenizer_version=self.tokenizer_version,
        )

    @classmethod
    def from_core(cls, value: core.MemoryPolicy) -> Self:
        return cls(
            policy_id=value.policy_id,
            version=value.version,
            domain=cast(Literal["operations", "customer-service", "hr"], value.domain),
            agent_ids=value.agent_ids,
            enabled=value.enabled,
            readable_layers=value.readable_layers,
            writable_kinds=value.writable_kinds,
            allowed_scopes=value.allowed_scopes,
            field_allowlist=value.field_allowlist,
            sensitivity_levels=value.sensitivity_levels,
            confirmation_required=value.confirmation_required,
            auto_extract=value.auto_extract,
            shared_approval_required=value.shared_approval_required,
            source_types=value.source_types,
            retention_days=value.retention_days,
            recall_top_k=value.recall_top_k,
            recall_token_limit=value.recall_token_limit,
            max_paid_operations=value.max_paid_operations,
            degradation_mode=value.degradation_mode,
            source_deletion_mode=value.source_deletion_mode,
            schema_version=value.schema_version,
            model_version=value.model_version,
            tokenizer_version=value.tokenizer_version,
        )


class MemoryProposalModel(_Boundary):
    kind: str
    field_key: str
    value: str = Field(repr=False)

    @model_validator(mode="after")
    def validate_core(self) -> Self:
        self.to_core()
        return self

    def to_core(self) -> core.MemoryProposal:
        return core.MemoryProposal(
            kind=self.kind,
            field_key=self.field_key,
            value=self.value,
        )

    @classmethod
    def from_core(cls, value: core.MemoryProposal) -> Self:
        return cls(
            kind=value.kind,
            field_key=value.field_key,
            value=value.value,
        )


class MemoryContextPacketModel(_Boundary):
    packet_id: str
    packet_revision: int
    scope: ConversationScopeModel
    task_id: str
    execution_id: str
    policy_version: str
    execution_revision: int
    issued_at: int
    expires_at: int
    grant_epoch: int
    source_epoch: int
    deletion_epoch: int
    semantic_input_hash: str
    parent_authorization_ref: str
    items: tuple[MemoryReferenceModel, ...] = ()
    safety_dependencies: tuple[SourceDependencyModel, ...] = ()

    @model_validator(mode="after")
    def validate_core(self) -> Self:
        self.to_core()
        return self

    def to_core(self) -> core.MemoryContextPacket:
        return core.MemoryContextPacket(
            packet_id=self.packet_id,
            packet_revision=self.packet_revision,
            scope=self.scope.to_core(),
            task_id=self.task_id,
            execution_id=self.execution_id,
            policy_version=self.policy_version,
            execution_revision=self.execution_revision,
            issued_at=self.issued_at,
            expires_at=self.expires_at,
            grant_epoch=self.grant_epoch,
            source_epoch=self.source_epoch,
            deletion_epoch=self.deletion_epoch,
            semantic_input_hash=self.semantic_input_hash,
            parent_authorization_ref=self.parent_authorization_ref,
            items=tuple(item.to_core() for item in self.items),
            safety_dependencies=tuple(
                item.to_core() for item in self.safety_dependencies
            ),
        )

    @classmethod
    def from_core(cls, value: core.MemoryContextPacket) -> Self:
        return cls(
            packet_id=value.packet_id,
            packet_revision=value.packet_revision,
            scope=ConversationScopeModel.from_core(value.scope),
            task_id=value.task_id,
            execution_id=value.execution_id,
            policy_version=value.policy_version,
            execution_revision=value.execution_revision,
            issued_at=value.issued_at,
            expires_at=value.expires_at,
            grant_epoch=value.grant_epoch,
            source_epoch=value.source_epoch,
            deletion_epoch=value.deletion_epoch,
            semantic_input_hash=value.semantic_input_hash,
            parent_authorization_ref=value.parent_authorization_ref,
            items=tuple(MemoryReferenceModel.from_core(item) for item in value.items),
            safety_dependencies=tuple(
                SourceDependencyModel.from_core(item)
                for item in value.safety_dependencies
            ),
        )
