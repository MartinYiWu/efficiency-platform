"""Prompt Runtime 的不可变版本化契约。"""

from __future__ import annotations

import re
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


def _require_text(field_name: str, value: str) -> None:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{field_name} 必须为非空字符串")


def _require_string_set(field_name: str, value: frozenset[str]) -> None:
    if not isinstance(value, frozenset):
        raise TypeError(f"{field_name} 必须为 frozenset")
    for item in value:
        _require_text(field_name, item)
