"""Prompt Runtime 的不可变版本化契约。"""

from __future__ import annotations

import re
from collections.abc import Mapping
from dataclasses import dataclass

from efficiency_platform_agent.core.run import ProviderMessage

_SEMANTIC_VERSION = re.compile(
    r"(?:0|[1-9]\d*)\.(?:0|[1-9]\d*)\.(?:0|[1-9]\d*)"
    r"(?:-[0-9A-Za-z-]+(?:\.[0-9A-Za-z-]+)*)?"
    r"(?:\+[0-9A-Za-z-]+(?:\.[0-9A-Za-z-]+)*)?"
)


@dataclass(frozen=True, slots=True)
class PromptBundleSpec:
    """描述一个显式登记的 Prompt 版本及其变量边界。"""

    prompt_id: str
    semantic_version: str
    owner: str
    template_path: str
    variable_schema_version: str
    required_variables: frozenset[str]
    output_schema_version: str
    allowed_model_tiers: frozenset[str]
    max_rendered_chars: int

    def __post_init__(self) -> None:
        _require_text("prompt_id", self.prompt_id)
        if not _SEMANTIC_VERSION.fullmatch(self.semantic_version):
            raise ValueError("semantic_version 必须使用 MAJOR.MINOR.PATCH")
        _require_text("owner", self.owner)
        _require_text("template_path", self.template_path)
        _require_text("variable_schema_version", self.variable_schema_version)
        _require_string_set("required_variables", self.required_variables)
        _require_text("output_schema_version", self.output_schema_version)
        _require_string_set("allowed_model_tiers", self.allowed_model_tiers)
        if (
            not isinstance(self.max_rendered_chars, int)
            or isinstance(self.max_rendered_chars, bool)
            or self.max_rendered_chars <= 0
        ):
            raise ValueError("max_rendered_chars 必须为正整数")


@dataclass(frozen=True, slots=True)
class RenderedPrompt:
    """Prompt 渲染后的稳定模型消息结果。"""

    prompt_id: str
    semantic_version: str
    output_schema_version: str
    messages: tuple[ProviderMessage, ...]
    rendered_chars: int

    def __post_init__(self) -> None:
        _require_text("prompt_id", self.prompt_id)
        _require_text("semantic_version", self.semantic_version)
        _require_text("output_schema_version", self.output_schema_version)
        if not isinstance(self.messages, tuple) or not self.messages:
            raise ValueError("messages 必须为非空 tuple")
        if any(not isinstance(item, ProviderMessage) for item in self.messages):
            raise TypeError("messages 只能包含 ProviderMessage")
        if (
            not isinstance(self.rendered_chars, int)
            or isinstance(self.rendered_chars, bool)
            or self.rendered_chars < 0
        ):
            raise ValueError("rendered_chars 必须为非负整数")


@dataclass(frozen=True, slots=True)
class PromptDefinition:
    """数据库中稳定的场景 Prompt 身份。"""

    id: int
    prompt_key: str
    scenario: str
    stage: str
    platform: str | None
    name: str
    description: str
    enabled: bool


@dataclass(frozen=True, slots=True)
class PromptVersion:
    """不可变的 Prompt 发布候选版本。"""

    id: int
    prompt_definition_id: int
    semantic_version: str
    status: str
    model_policy_id: int
    output_contract_id: int
    checksum: str


@dataclass(frozen=True, slots=True)
class PromptMessageTemplate:
    """一条带角色和顺序的 Prompt 消息模板。"""

    id: int
    prompt_version_id: int
    ordinal: int
    role: str
    message_key: str
    content_template: str
    content_format: str
    trusted_instruction: bool
    checksum: str


@dataclass(frozen=True, slots=True)
class PromptVariableDefinition:
    """单条消息允许使用的类型化变量。"""

    id: int
    prompt_message_template_id: int
    variable_name: str
    value_type: str
    value_source: str
    required: bool
    sensitive: bool
    max_length: int
    allow_untrusted_content: bool


@dataclass(frozen=True, slots=True)
class ModelPolicy:
    """独立于 Prompt 正文的模型调用策略。"""

    id: int
    policy_key: str
    semantic_version: str
    provider: str
    model_name: str
    temperature: float
    top_p: float | None
    max_input_tokens: int
    max_output_tokens: int
    connect_timeout_ms: int
    read_timeout_ms: int
    max_retries: int
    max_tool_calls: int
    checksum: str


@dataclass(frozen=True, slots=True)
class OutputContract:
    """模型结构化输出的版本化 JSON Schema。"""

    id: int
    contract_key: str
    semantic_version: str
    json_schema: Mapping[str, object]
    field_description: str
    checksum: str


@dataclass(frozen=True, slots=True)
class PromptBundle:
    """一次模型调用所需的完整已发布 Prompt 资产。"""

    definition: PromptDefinition
    version: PromptVersion
    messages: tuple[PromptMessageTemplate, ...]
    variables: tuple[PromptVariableDefinition, ...]
    model_policy: ModelPolicy
    output_contract: OutputContract


@dataclass(frozen=True, slots=True)
class PromptValue:
    """携带可信来源标签的运行时变量值。"""

    value: object
    source: str


@dataclass(frozen=True, slots=True)
class PromptMessage:
    """Provider 映射前的规范化角色消息。"""

    role: str
    content: str


@dataclass(frozen=True, slots=True)
class AssembledPrompt:
    """完成版本冻结和严格渲染的模型请求资产。"""

    prompt_key: str
    semantic_version: str
    messages: tuple[PromptMessage, ...]
    model_policy: ModelPolicy
    output_contract: OutputContract
    message_checksum: str
    rendered_chars: int


@dataclass(frozen=True, slots=True)
class RunPromptSnapshot:
    """Run/Stage 首次装配后冻结的 Prompt 引用。"""

    run_id: str
    stage: str
    prompt_definition_id: int
    prompt_version_id: int
    model_policy_id: int
    output_contract_id: int
    message_checksum: str
    rendered_messages_checksum: str
    variable_values_checksum: str
    referenced_snapshot: Mapping[str, object]
    created_at_epoch_ms: int


@dataclass(frozen=True, slots=True)
class PromptRelease:
    """环境与已发布 Prompt 版本的映射。"""

    environment: str
    prompt_definition_id: int
    prompt_version_id: int


@dataclass(frozen=True, slots=True)
class PromptSeedPackage:
    """用于初始化数据库 Prompt 资产的不可变数据包。"""

    definitions: tuple[PromptDefinition, ...]
    versions: tuple[PromptVersion, ...]
    messages: tuple[PromptMessageTemplate, ...]
    variables: tuple[PromptVariableDefinition, ...]
    model_policies: tuple[ModelPolicy, ...]
    output_contracts: tuple[OutputContract, ...]
    releases: tuple[PromptRelease, ...]


def _require_text(field_name: str, value: str) -> None:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{field_name} 必须为非空字符串")


def _require_string_set(field_name: str, value: frozenset[str]) -> None:
    if not isinstance(value, frozenset):
        raise TypeError(f"{field_name} 必须为 frozenset")
    for item in value:
        _require_text(field_name, item)
