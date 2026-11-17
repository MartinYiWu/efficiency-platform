"""受治理 Tool Runtime 的版本化契约。"""

from __future__ import annotations

from dataclasses import dataclass

from pydantic import BaseModel

from efficiency_platform_agent.core.context_projection import (
    ToolProjection,
    ToolProjectionPort,
)
from efficiency_platform_agent.core.memory import require_count, require_id
from efficiency_platform_agent.core.run import JsonObject, ToolResult

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
    projection_port: ToolProjectionPort | None = None
    projection_schema: str | None = None
    projection_version: str | None = None
    model_visible_token_upper_bound: int | None = None

    def __post_init__(self) -> None:
        projection_fields = (
            self.projection_schema,
            self.projection_version,
            self.model_visible_token_upper_bound,
        )
        if self.projection_port is None:
            if any(value is not None for value in projection_fields):
                raise ValueError("TOOL_PROJECTION_PUBLICATION_INVALID")
        else:
            if any(value is None for value in projection_fields):
                raise ValueError("TOOL_PROJECTION_PUBLICATION_REQUIRED")
            require_id(self.projection_schema)  # type: ignore[arg-type]
            require_id(self.projection_version)  # type: ignore[arg-type]
            require_count(self.model_visible_token_upper_bound)  # type: ignore[arg-type]
            if not callable(getattr(self.projection_port, "project", None)):
                raise ValueError("TOOL_PROJECTION_PORT_INVALID")
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


@dataclass(frozen=True, slots=True)
class ProjectedToolResult:
    """完整受治理结果留在程序侧，模型只读 projection。"""

    full_result: ToolResult
    projection: ToolProjection | None

    def __post_init__(self) -> None:
        if not isinstance(self.full_result, ToolResult):
            raise TypeError("PROJECTED_TOOL_RESULT_INVALID")
        if (self.full_result.error is None) != isinstance(
            self.projection, ToolProjection
        ):
            raise ValueError("PROJECTED_TOOL_RESULT_INVALID")
