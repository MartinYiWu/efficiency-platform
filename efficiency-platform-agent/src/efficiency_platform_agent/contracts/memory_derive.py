"""既有 Skill 传输的中立摘要合同；引用不能创建运行或付费授权。"""

import hashlib
import json
from typing import Annotated, Literal, Self

from pydantic import BaseModel, ConfigDict, Field, model_validator

from efficiency_platform_agent.contracts.memory import (
    ExecutionScopeModel,
    SourceDependencyModel,
)
from efficiency_platform_agent.contracts.memory_summary import (
    RejectedOption,
    SummaryBasisEvent,
    SummaryEntry,
    SummaryInputSource,
)
from efficiency_platform_agent.core.derive_ports import DeriveOperation

Identifier = Annotated[str, Field(min_length=1, max_length=128, pattern=r"\S")]
Digest = Annotated[str, Field(pattern=r"^[0-9a-f]{64}$")]


class _Boundary(BaseModel):
    model_config = ConfigDict(
        strict=True, extra="forbid", frozen=True, hide_input_in_errors=True
    )


class DeriveAssetRefs(_Boundary):
    memory_policy_version: Identifier
    window_policy_version: Identifier
    model_ref: Identifier
    prompt_ref: Identifier
    schema_ref: Identifier


class FrozenDeriveSource(_Boundary):
    metadata: SummaryInputSource
    body: str = Field(max_length=20000, repr=False)
    body_sha256: Digest

    @model_validator(mode="after")
    def verify_body(self) -> Self:
        if hashlib.sha256(self.body.encode("utf-8")).hexdigest() != self.body_sha256:
            raise ValueError("DERIVE_SOURCE_BODY_MISMATCH")
        return self


class MemoryDeriveRequest(_Boundary):
    contract_version: Literal["memory-derive/1"]
    plan_id: Identifier
    plan_fingerprint: Digest
    runtime_id: Identifier
    runtime_kind: Literal["OPERATIONS", "CUSTOMER_SERVICE"]
    run_id: Identifier
    operation_id: Identifier
    authorization_ref: Identifier
    budget_id: Identifier
    deadline_epoch_seconds: int = Field(gt=0)
    execution_scope: ExecutionScopeModel
    mode: Literal["SUMMARY", "PROPOSALS", "BOTH"]
    baseline_ref: Identifier
    assets: DeriveAssetRefs
    sources: tuple[FrozenDeriveSource, ...] = Field(
        min_length=1, max_length=128, repr=False
    )
    events: tuple[SummaryBasisEvent, ...] = Field(max_length=897, repr=False)
    required_entries: tuple[SummaryEntry | RejectedOption, ...] = Field(
        min_length=0, max_length=897, repr=False
    )
    session_revision: int = Field(ge=0)
    source_revision: int = Field(ge=0)
    authority_ref: Identifier

    @model_validator(mode="after")
    def require_source_epochs(self) -> Self:
        def visit(item: object) -> None:
            if isinstance(item, BaseModel):
                if isinstance(item, SourceDependencyModel) and not {
                    "grant_epoch",
                    "source_epoch",
                    "deletion_epoch",
                }.issubset(item.model_fields_set):
                    raise ValueError("DERIVE_SOURCE_EPOCH_REQUIRED")
                for name in type(item).model_fields:
                    visit(getattr(item, name))
            elif isinstance(item, (tuple, list, frozenset)):
                for child in item:
                    visit(child)

        visit(self)
        return self

    @model_validator(mode="after")
    def verify_scope(self) -> Self:
        scope = self.execution_scope.conversation
        if scope.session_kind != "CONVERSATION" or scope.domain == "hr":
            raise ValueError("DERIVE_SCOPE_MISMATCH")
        if self.mode != "PROPOSALS" and not self.required_entries:
            raise ValueError("SUMMARY_SOURCE_PROJECTION_REQUIRED")
        domain = (
            "operations" if self.runtime_kind == "OPERATIONS" else "customer-service"
        )
        if scope.domain != domain or any(
            s.metadata.scope != scope for s in self.sources
        ):
            raise ValueError("DERIVE_SCOPE_MISMATCH")
        return self

    def operation(self) -> DeriveOperation:
        return DeriveOperation(
            self.execution_scope.to_core(),
            self.run_id,
            self.operation_id,
            self.authorization_ref,
            self.budget_id,
            self.deadline_epoch_seconds,
        )

    def fingerprint(self) -> str:
        # 正文由 SHA 绑定，规范指纹不持有第二份原文明文。
        data = self.model_dump(mode="json", exclude={"plan_fingerprint"})
        for source in data["sources"]:
            source.pop("body")
            source["metadata"]["allowed_purposes"].sort()
        return hashlib.sha256(
            json.dumps(
                data,
                ensure_ascii=False,
                sort_keys=True,
                separators=(",", ":"),
                allow_nan=False,
            ).encode("utf-8")
        ).hexdigest()


class MemorySkillContext(_Boundary):
    traceId: Identifier
    userId: Identifier
    sourceModule: Identifier
    actionType: Identifier


class MemorySkillExecuteRequest(_Boundary):
    context: MemorySkillContext
    skillId: Literal[6201]
    input: str = Field(max_length=1048576, repr=False)
