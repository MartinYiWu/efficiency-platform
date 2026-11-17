"""Java 内部通道的记忆边界信封，不授予运行或来源权限。"""

import json
from typing import Annotated, Literal, Self

from pydantic import BaseModel, BeforeValidator, ConfigDict, Field, model_validator

from efficiency_platform_agent.core.memory_execution import (
    MemoryExecutionContext,
    MemoryExecutionGrant,
)

from .memory import (
    ConversationScopeModel,
    MemoryContextPacketModel,
    MemoryPolicyModel,
    SourceDependencyModel,
)


class MemoryExecutionGrantModel(BaseModel):
    model_config = ConfigDict(
        extra="forbid", strict=True, frozen=True, hide_input_in_errors=True
    )
    node_id: str
    execution_agent_id: str
    purpose: str

    def to_core(self) -> MemoryExecutionGrant:
        return MemoryExecutionGrant(self.node_id, self.execution_agent_id, self.purpose)


class MemoryAuthorizationModel(BaseModel):
    model_config = ConfigDict(
        extra="forbid", strict=True, frozen=True, hide_input_in_errors=True
    )
    policy: MemoryPolicyModel
    execution_grants: tuple[MemoryExecutionGrantModel, ...]
    deadline_epoch_seconds: int
    packet_digest: str
    semantic_snapshot_digest: str
    request_digest: str
    input_dependencies: tuple[SourceDependencyModel, ...] = Field(min_length=1)


class MemoryContextEnvelope(BaseModel):
    model_config = ConfigDict(
        extra="forbid", strict=True, frozen=True, hide_input_in_errors=True
    )
    schema_version: Literal["memory-context/1"] = "memory-context/1"
    memory_mode: Literal["DISABLED", "EXACT_ONLY"] = "DISABLED"
    scope: ConversationScopeModel | None = None
    packet: MemoryContextPacketModel | None = Field(default=None, repr=False)
    authorization: MemoryAuthorizationModel | None = None

    @model_validator(mode="after")
    def validate_core(self) -> Self:
        if self.memory_mode == "DISABLED":
            if self.packet is not None or self.authorization is not None:
                raise ValueError("MEMORY_DISABLED_ENVELOPE_INVALID")
        else:
            context = self.to_core()
            if (
                context is None
                or self.scope is None
                or context.packet.scope != self.scope.to_core()
            ):
                raise ValueError("MEMORY_ENVELOPE_BINDING_INVALID")
        return self

    def to_core(self) -> MemoryExecutionContext | None:
        if self.memory_mode == "DISABLED":
            return None
        if self.packet is None or self.authorization is None:
            raise ValueError("MEMORY_AUTHORIZATION_REQUIRED")
        auth = self.authorization
        return MemoryExecutionContext(
            self.packet.to_core(),
            auth.policy.to_core(),
            tuple(grant.to_core() for grant in auth.execution_grants),
            auth.deadline_epoch_seconds,
            auth.packet_digest,
            auth.semantic_snapshot_digest,
            auth.request_digest,
            tuple(dep.to_core() for dep in auth.input_dependencies),
        )


def _wire_envelope(value: object) -> object:
    if value is None:
        return MemoryContextEnvelope()
    if isinstance(value, dict):
        # FastAPI先解码JSON为dict；重新使用严格JSON语义冻结数组，标量仍严格拒绝布尔/字符串冒充数字。
        return MemoryContextEnvelope.model_validate_json(
            json.dumps(value, ensure_ascii=False)
        )
    return value


MemoryContextInput = Annotated[MemoryContextEnvelope, BeforeValidator(_wire_envelope)]
