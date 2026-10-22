"""不可变智能客服 Release Bundle 契约与校验。"""

from __future__ import annotations

import json
from decimal import Decimal
from hashlib import sha256
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, model_serializer, model_validator

EVIDENCE_POLICY_FIELDS = frozenset(
    {
        "final_evidence_top_k",
        "similarity_candidate_threshold",
        "similarity_pair_limit",
        "adjacent_group_max_parents",
    }
)
EVIDENCE_STAGES = frozenset({"equivalence", "conflict_screen", "evidence_extract"})


class PromptVariable(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    variable_name: str = Field(min_length=1, max_length=128)
    value_type: str = Field(min_length=1, max_length=32)
    value_source: str = Field(min_length=1, max_length=64)
    required: bool
    sensitive: bool
    max_length: int | None = Field(default=None, gt=0)
    allow_untrusted_content: bool


class PromptMessage(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    ordinal: int = Field(gt=0)
    role: Literal["SYSTEM", "DEVELOPER", "USER", "ASSISTANT"]
    message_key: str = Field(min_length=1, max_length=128)
    content_template: str = Field(min_length=1)
    content_format: Literal["TEXT", "JSON"]
    trusted_instruction: bool
    checksum: str = Field(pattern=r"^[a-f0-9]{64}$")
    variables: tuple[PromptVariable, ...]

    @model_validator(mode="after")
    def validate_trust_boundary(self) -> PromptMessage:
        if self.role == "USER" and self.trusted_instruction:
            raise ValueError("USER 消息不得标记为可信指令")
        if self.role in {"SYSTEM", "DEVELOPER"} and any(
            item.allow_untrusted_content for item in self.variables
        ):
            raise ValueError("不可信变量不得进入 SYSTEM 或 DEVELOPER 消息")
        return self


class PromptBinding(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    stage_key: str = Field(min_length=1, max_length=128)
    ordinal: int = Field(gt=0)
    prompt_key: str = Field(min_length=1, max_length=160)
    prompt_version: str = Field(min_length=1, max_length=64)
    checksum: str = Field(pattern=r"^[a-f0-9]{64}$")
    messages: tuple[PromptMessage, ...] = Field(min_length=1)

    @model_validator(mode="after")
    def validate_message_order(self) -> PromptBinding:
        ordinals = [item.ordinal for item in self.messages]
        if ordinals != sorted(ordinals) or len(ordinals) != len(set(ordinals)):
            raise ValueError("Prompt 消息顺序无效")
        return self


class ModelPolicy(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    policy_key: str = Field(min_length=1)
    semantic_version: str = Field(min_length=1)
    provider: str = Field(min_length=1)
    model_name: str = Field(min_length=1)
    temperature: Decimal = Field(ge=0, le=2)
    top_p: Decimal = Field(gt=0, le=1)
    max_input_tokens: int = Field(gt=0)
    max_output_tokens: int = Field(gt=0)
    connect_timeout_ms: int = Field(gt=0)
    read_timeout_ms: int = Field(gt=0)
    max_retries: int = Field(ge=0, le=5)
    checksum: str = Field(pattern=r"^[a-f0-9]{64}$")


class RagPolicy(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    policy_key: str = Field(min_length=1)
    semantic_version: str = Field(min_length=1)
    rewrite_query_limit: int = Field(gt=0, le=10)
    vector_top_k: int = Field(gt=0, le=100)
    fts_top_k: int = Field(gt=0, le=100)
    fusion_top_k: int = Field(gt=0, le=100)
    rerank_top_k: int = Field(gt=0, le=50)
    context_token_limit: int = Field(gt=0)
    citation_limit: int = Field(gt=0, le=50)
    final_evidence_top_k: int = Field(default=8, ge=1, le=20)
    similarity_candidate_threshold: Decimal = Field(
        default=Decimal("0.96"), ge=Decimal("0.85"), le=1
    )
    similarity_pair_limit: int = Field(default=20, ge=1, le=50)
    adjacent_group_max_parents: int = Field(default=3, ge=1, le=5)
    checksum: str = Field(pattern=r"^[a-f0-9]{64}$")


class KnowledgeBinding(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    knowledge_base_id: UUID
    index_release_id: UUID
    priority: int = Field(gt=0)
    required: bool


class CustomerServiceReleaseBundle(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    contract_version: Literal[
        "customer-service-release/1", "customer-service-release/2"
    ]
    agent_key: Literal["customer-service"]
    agent_version: str = Field(min_length=1)
    graph_key: Literal["customer-service"]
    graph_version: str = Field(min_length=1)
    environment: str = Field(min_length=1, max_length=32)
    prompt_bindings: tuple[PromptBinding, ...] = Field(min_length=1)
    model_policy: ModelPolicy
    large_context_model_policy: ModelPolicy | None = None
    rag_policy: RagPolicy
    knowledge_bindings: tuple[KnowledgeBinding, ...] = Field(min_length=1)
    tool_allowlist: tuple[str, ...]
    output_contract_version: Literal["customer-service-answer/1"]
    safety_rule_version: str = Field(min_length=1)
    snapshot_checksum: str = Field(pattern=r"^[a-f0-9]{64}$")

    @model_validator(mode="after")
    def validate_checksum_and_bindings(self) -> CustomerServiceReleaseBundle:
        if self.contract_version.endswith("/1"):
            if (
                EVIDENCE_POLICY_FIELDS & self.rag_policy.model_fields_set
                or self.large_context_model_policy is not None
            ):
                raise ValueError("旧版 Release 不接受证据策略扩展")
        else:
            if not EVIDENCE_POLICY_FIELDS <= self.rag_policy.model_fields_set:
                raise ValueError("新版 Release 必须冻结全部证据策略字段")
            for stage in EVIDENCE_STAGES:
                bindings = [
                    item for item in self.prompt_bindings if item.stage_key == stage
                ]
                if len(bindings) != 1 or [
                    message.role for message in bindings[0].messages
                ] != ["SYSTEM", "USER"]:
                    raise ValueError("证据阶段必须绑定独立 SYSTEM、USER 消息")
            if (
                self.large_context_model_policy is not None
                and self.large_context_model_policy.max_input_tokens
                <= self.model_policy.max_input_tokens
            ):
                raise ValueError("备选模型输入上限必须严格大于主模型")
        stages = [(item.stage_key, item.ordinal) for item in self.prompt_bindings]
        if stages != sorted(stages) or len(stages) != len(set(stages)):
            raise ValueError("Prompt 绑定顺序无效")
        knowledge = [item.knowledge_base_id for item in self.knowledge_bindings]
        if len(knowledge) != len(set(knowledge)):
            raise ValueError("知识库绑定重复")
        return self

    @model_serializer(mode="wrap")
    def serialize_snapshot(self, handler):
        value = handler(self)
        if self.large_context_model_policy is None:
            value.pop("large_context_model_policy", None)
        if self.contract_version.endswith("/1") and "rag_policy" in value:
            for key in EVIDENCE_POLICY_FIELDS:
                value["rag_policy"].pop(key, None)
        return value

    def assert_checksum(self) -> None:
        if self.snapshot_checksum != self.computed_checksum():
            raise ReleaseChecksumError("Release checksum 无效")

    def computed_checksum(self) -> str:
        if self.contract_version.endswith("/2"):
            canonical = _canonical_json(
                self.model_dump(mode="python", exclude={"snapshot_checksum"})
            )
            return sha256(canonical.encode()).hexdigest()
        value = _canonical_value(
            self.model_dump(mode="python", exclude={"snapshot_checksum"})
        )
        canonical = json.dumps(
            value, ensure_ascii=False, sort_keys=True, separators=(",", ":")
        )
        return sha256(canonical.encode()).hexdigest()


class ReleaseChecksumError(ValueError):
    """Release 内容与 Java 声明的摘要不一致。"""


def _canonical_json(value: object) -> str:
    """新版使用十进制定点数字，避免 Java 的 1 与 Python 的 1.0 摘要不同。"""
    if isinstance(value, dict):
        return (
            "{"
            + ",".join(
                json.dumps(str(key), ensure_ascii=False)
                + ":"
                + _canonical_json(value[key])
                for key in sorted(value)
            )
            + "}"
        )
    if isinstance(value, (list, tuple)):
        return "[" + ",".join(_canonical_json(item) for item in value) + "]"
    if isinstance(value, Decimal):
        if value.is_zero():
            return "0"
        decimal_text = format(value, "f")
        return (
            decimal_text.rstrip("0").rstrip(".")
            if "." in decimal_text
            else decimal_text
        )
    if isinstance(value, UUID):
        value = str(value)
    return json.dumps(value, ensure_ascii=False, separators=(",", ":"))


def _canonical_value(value: object) -> object:
    if isinstance(value, dict):
        return {str(key): _canonical_value(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_canonical_value(item) for item in value]
    if isinstance(value, Decimal):
        return float(value)
    if isinstance(value, UUID):
        return str(value)
    return value


class ReleaseAck(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    contract_version: Literal["customer-service-release-ack/1"] = (
        "customer-service-release-ack/1"
    )
    release_id: UUID
    checksum: str = Field(pattern=r"^[a-f0-9]{64}$")
    status: Literal["ACKNOWLEDGED"] = "ACKNOWLEDGED"


__all__ = [
    "CustomerServiceReleaseBundle",
    "ReleaseAck",
    "ReleaseChecksumError",
]
