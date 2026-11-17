from __future__ import annotations

from dataclasses import dataclass, field

SCOPE_CATALOG = frozenset({"operations", "customer-service", "hr"})


def require_id(value: str) -> None:
    if type(value) is not str or not value.strip() or len(value) > 128:
        raise ValueError("IDENTIFIER_INVALID")


def require_count(value: int) -> None:
    if type(value) is not int or value < 0:
        raise ValueError("COUNT_INVALID")


def require_bool(value: bool) -> None:
    if type(value) is not bool:
        raise ValueError("BOOLEAN_INVALID")


def require_ids(values: frozenset[str]) -> None:
    if not isinstance(values, frozenset):
        raise TypeError("IDENTIFIERS_INVALID")
    for value in values:
        require_id(value)


@dataclass(frozen=True, slots=True)
class ConversationScope:
    tenant_id: str
    user_id: str
    domain: str
    top_level_agent_id: str
    session_kind: str
    session_id: str | None

    def __post_init__(self) -> None:
        for value in (self.tenant_id, self.user_id):
            require_id(value)
        if self.domain not in SCOPE_CATALOG or self.top_level_agent_id != self.domain:
            raise ValueError("SCOPE_CATALOG_INVALID")
        if self.session_kind == "TASK_ONLY":
            if self.session_id is not None:
                raise ValueError("SCOPE_SESSION_INVALID")
        elif self.session_kind == "CONVERSATION":
            try:
                require_id(self.session_id)  # type: ignore[arg-type]
            except ValueError:
                raise ValueError("SCOPE_SESSION_REQUIRED") from None
        else:
            raise ValueError("SCOPE_KIND_INVALID")

    @property
    def history_key(self) -> tuple[str, str, str, str, str] | None:
        if self.session_kind == "TASK_ONLY":
            return None
        assert self.session_id is not None
        return (
            self.tenant_id,
            self.user_id,
            self.domain,
            self.top_level_agent_id,
            self.session_id,
        )


@dataclass(frozen=True, slots=True)
class ExecutionScope:
    conversation: ConversationScope
    task_id: str
    execution_id: str
    subtask_id: str
    purpose: str
    execution_agent_id: str

    def __post_init__(self) -> None:
        if not isinstance(self.conversation, ConversationScope):
            raise TypeError("EXECUTION_SCOPE_INVALID")
        for value in (
            self.task_id,
            self.execution_id,
            self.subtask_id,
            self.purpose,
            self.execution_agent_id,
        ):
            require_id(value)


@dataclass(frozen=True, slots=True)
class SourceDependency:
    source_type: str
    source_id: str
    source_version: str
    grant_epoch: int = 0
    source_epoch: int = 0
    deletion_epoch: int = 0

    def __post_init__(self) -> None:
        for value in (self.source_type, self.source_id, self.source_version):
            require_id(value)
        for epoch in (self.grant_epoch, self.source_epoch, self.deletion_epoch):
            require_count(epoch)


@dataclass(frozen=True, slots=True)
class MemoryReference:
    item_id: str
    version: str
    field_key: str
    value: str = field(repr=False)
    safety_dependencies: tuple[SourceDependency, ...] = ()

    def __post_init__(self) -> None:
        for value in (self.item_id, self.version, self.field_key):
            require_id(value)
        if type(self.value) is not str:
            raise ValueError("MEMORY_VALUE_INVALID")
        require_dependencies(self.safety_dependencies)


def require_dependencies(values: tuple[SourceDependency, ...]) -> None:
    if type(values) is not tuple or any(
        not isinstance(value, SourceDependency) for value in values
    ):
        raise ValueError("DEPENDENCIES_INVALID")


@dataclass(frozen=True, slots=True)
class MemoryPolicy:
    policy_id: str
    version: str
    domain: str
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

    def __post_init__(self) -> None:
        for value in (
            self.policy_id,
            self.version,
            self.schema_version,
            self.model_version,
            self.tokenizer_version,
        ):
            require_id(value)
        if self.domain not in SCOPE_CATALOG:
            raise ValueError("POLICY_DOMAIN_INVALID")
        for values in (
            self.agent_ids,
            self.readable_layers,
            self.writable_kinds,
            self.allowed_scopes,
            self.field_allowlist,
            self.sensitivity_levels,
            self.source_types,
        ):
            require_ids(values)
        for flag in (
            self.enabled,
            self.confirmation_required,
            self.auto_extract,
            self.shared_approval_required,
        ):
            require_bool(flag)
        for count in (
            self.retention_days,
            self.recall_top_k,
            self.recall_token_limit,
            self.max_paid_operations,
        ):
            require_count(count)
        if self.degradation_mode not in {
            "disabled",
            "omit",
            "reject",
        } or self.source_deletion_mode not in {"block", "delete"}:
            raise ValueError("POLICY_MODE_INVALID")
        if not self.allowed_scopes.issubset(
            {"RUN", "SESSION", "USER_PRIVATE", "PROJECT", "DEPARTMENT", "ORGANIZATION"}
        ):
            raise ValueError("POLICY_SCOPE_INVALID")
        if not self.writable_kinds.issubset(
            {"PREFERENCE", "PROJECT_CONSTRAINT", "TASK_EPISODE", "SOURCE_REFERENCE"}
        ):
            raise ValueError("POLICY_KIND_INVALID")


@dataclass(frozen=True, slots=True)
class MemoryProposal:
    kind: str
    field_key: str
    value: str = field(repr=False)

    def __post_init__(self) -> None:
        if self.kind not in {
            "PREFERENCE",
            "PROJECT_CONSTRAINT",
            "TASK_EPISODE",
            "SOURCE_REFERENCE",
        }:
            raise ValueError("PROPOSAL_KIND_INVALID")
        require_id(self.field_key)
        if type(self.value) is not str or not self.value.strip():
            raise ValueError("PROPOSAL_VALUE_INVALID")


@dataclass(frozen=True, slots=True)
class MemoryContextPacket:
    packet_id: str
    packet_revision: int
    scope: ConversationScope
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
    items: tuple[MemoryReference, ...] = ()
    safety_dependencies: tuple[SourceDependency, ...] = ()

    def __post_init__(self) -> None:
        for value in (
            self.packet_id,
            self.task_id,
            self.execution_id,
            self.policy_version,
            self.semantic_input_hash,
            self.parent_authorization_ref,
        ):
            require_id(value)
        for count in (
            self.packet_revision,
            self.execution_revision,
            self.issued_at,
            self.expires_at,
            self.grant_epoch,
            self.source_epoch,
            self.deletion_epoch,
        ):
            require_count(count)
        if (
            not isinstance(self.scope, ConversationScope)
            or self.expires_at <= self.issued_at
        ):
            raise ValueError("PACKET_INVALID")
        if type(self.items) is not tuple or any(
            not isinstance(item, MemoryReference) for item in self.items
        ):
            raise ValueError("PACKET_ITEMS_INVALID")
        require_dependencies(self.safety_dependencies)
        if any(
            not set(item.safety_dependencies).issubset(self.safety_dependencies)
            for item in self.items
        ):
            raise ValueError("PACKET_DEPENDENCIES_INCOMPLETE")

    def validate_scope(
        self, scope: ConversationScope, task_id: str, execution_id: str
    ) -> None:
        if (self.scope, self.task_id, self.execution_id) != (
            scope,
            task_id,
            execution_id,
        ):
            raise ValueError("PACKET_SCOPE_MISMATCH")
