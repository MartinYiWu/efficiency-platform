"""受治理 Tool Runtime 的版本化契约。"""

from __future__ import annotations

from dataclasses import dataclass

from pydantic import BaseModel

from efficiency_platform_agent.core.run import JsonObject

type ToolModel = type[BaseModel]


@dataclass(frozen=True, slots=True)
class ToolSpec:
    """描述一个可注册 Tool 的治理元数据。"""

    tool_name: str
    semantic_version: str
    owner: str
    argument_schema_version: str
    result_schema_version: str
    argument_model: ToolModel
    result_model: ToolModel
    required_permissions: frozenset[str]
    has_side_effects: bool
    max_attempts: int
    timeout_ms: int
    max_output_bytes: int

    def __post_init__(self) -> None:
        for name in (
            "tool_name",
            "semantic_version",
            "owner",
            "argument_schema_version",
            "result_schema_version",
        ):
            value = getattr(self, name)
            if not isinstance(value, str) or not value.strip():
                raise ValueError(f"{name} 必须是非空字符串")
        if not isinstance(self.argument_model, type) or not issubclass(
            self.argument_model, BaseModel
        ):
            raise TypeError("argument_model 必须是 Pydantic 模型")
        if not isinstance(self.result_model, type) or not issubclass(
            self.result_model, BaseModel
        ):
            raise TypeError("result_model 必须是 Pydantic 模型")
        if not isinstance(self.required_permissions, frozenset):
            raise TypeError("required_permissions 必须是 frozenset")
        if not isinstance(self.has_side_effects, bool):
            raise TypeError("has_side_effects 必须是 bool")
        if (
            not isinstance(self.max_attempts, int)
            or isinstance(self.max_attempts, bool)
            or not 1 <= self.max_attempts <= 2
        ):
            raise ValueError("max_attempts 必须为 1 或 2")
        for name in ("timeout_ms", "max_output_bytes"):
            value = getattr(self, name)
            if not isinstance(value, int) or isinstance(value, bool) or value <= 0:
                raise ValueError(f"{name} 必须为正整数")


@dataclass(frozen=True, slots=True)
class ToolInvocationRecord:
    """一次 Tool 尝试的安全审计摘要。"""

    invocation_id: str
    tool_name: str
    attempt: int
    status: str
    error_code: str | None
    output_bytes: int

    def __post_init__(self) -> None:
        if not self.invocation_id or not self.tool_name or not self.status:
            raise ValueError("审计摘要标识和状态不能为空")
        if not isinstance(self.attempt, int) or self.attempt <= 0:
            raise ValueError("attempt 必须为正整数")
        if self.error_code is not None and not isinstance(self.error_code, str):
            raise TypeError("error_code 必须为字符串或 None")
        if not isinstance(self.output_bytes, int) or self.output_bytes < 0:
            raise ValueError("output_bytes 必须为非负整数")


JsonObjectType = JsonObject
