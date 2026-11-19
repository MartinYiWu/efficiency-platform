"""原已认证请求携带的摘要模板；不含运行时、预算或模型授权。"""

import hashlib
from typing import Literal, Self

from pydantic import BaseModel, ConfigDict, Field, model_validator

from efficiency_platform_agent.contracts.memory import (
    ExecutionScopeModel,
    SourceDependencyModel,
)
from efficiency_platform_agent.contracts.memory_derive import (
    FrozenDeriveSource,
    Identifier,
)
from efficiency_platform_agent.contracts.memory_summary import (
    RejectedOption,
    SummaryBasisEvent,
    SummaryEntry,
)


class MemoryDeriveTemplate(BaseModel):
    model_config = ConfigDict(
        strict=True, extra="forbid", frozen=True, hide_input_in_errors=True
    )

    contract_version: Literal["memory-derive-template/1"]
    plan_id: Identifier
    operation_id: Identifier
    execution_id: Identifier
    task_id: Identifier
    deadline_epoch_seconds: int = Field(gt=0)
    scope: ExecutionScopeModel
    mode: Literal["SUMMARY", "PROPOSALS", "BOTH"] = "SUMMARY"
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
    def require_original_scope_and_epochs(self) -> Self:
        if self.mode != "PROPOSALS" and not self.required_entries:
            raise ValueError("SUMMARY_SOURCE_PROJECTION_REQUIRED")
        if (
            (self.task_id, self.execution_id)
            != (self.scope.task_id, self.scope.execution_id)
            or self.scope.conversation.session_kind != "CONVERSATION"
            or self.scope.conversation.domain not in {"operations", "customer-service"}
            or self.authority_ref != self.plan_id
            or self.operation_id
            not in {
                self.plan_id,
                "derive-" + hashlib.sha256(self.task_id.encode("utf-8")).hexdigest(),
            }
            or any(
                source.metadata.scope != self.scope.conversation
                for source in self.sources
            )
        ):
            raise ValueError("DERIVE_TEMPLATE_BINDING_CONFLICT")

        def visit(value: object) -> None:
            if isinstance(value, BaseModel):
                if isinstance(value, SourceDependencyModel) and not {
                    "grant_epoch",
                    "source_epoch",
                    "deletion_epoch",
                }.issubset(value.model_fields_set):
                    raise ValueError("DERIVE_SOURCE_EPOCH_REQUIRED")
                for name in type(value).model_fields:
                    visit(getattr(value, name))
            elif isinstance(value, (tuple, list, frozenset)):
                for item in value:
                    visit(item)

        visit(self)
        return self
