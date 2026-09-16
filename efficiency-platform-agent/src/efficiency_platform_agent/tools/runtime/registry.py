"""Tool 的显式注册表，不负责发现外部能力。"""

from __future__ import annotations

from efficiency_platform_agent.core.ports import Tool
from efficiency_platform_agent.tools.runtime.contracts import ToolSpec


class ToolRegistry:
    """按精确名称保存 ToolSpec 与 Tool 实例。"""

    def __init__(self) -> None:
        self._entries: dict[str, tuple[ToolSpec, Tool]] = {}

    def register(self, spec: ToolSpec, tool: Tool) -> None:
        """校验 descriptor 与契约一致后注册，拒绝覆盖。"""
        if not isinstance(spec, ToolSpec):
            raise TypeError("spec 必须是 ToolSpec")
        if not isinstance(tool, Tool):
            raise TypeError("tool 不符合 Tool 端口")
        descriptor = getattr(tool, "descriptor", None)
        if descriptor is None:
            raise ValueError("Tool 缺少 descriptor")
        expected = (
            ("name", spec.tool_name),
            ("semantic_version", spec.semantic_version),
            ("input_schema_version", spec.argument_schema_version),
            ("output_schema_version", spec.result_schema_version),
        )
        for field_name, expected_value in expected:
            if getattr(descriptor, field_name, None) != expected_value:
                raise ValueError(f"Tool descriptor 与 ToolSpec 的 {field_name} 不一致")
        if spec.tool_name in self._entries:
            raise ValueError("Tool 名称已注册")
        self._entries[spec.tool_name] = (spec, tool)

    def get(self, tool_name: str) -> tuple[ToolSpec, Tool]:
        """取得已注册 Tool，未注册时稳定抛出 KeyError。"""
        try:
            return self._entries[tool_name]
        except KeyError as exc:
            raise KeyError(tool_name) from exc

    def available_tools(self) -> frozenset[str]:
        """返回当前显式注册名称。"""
        return frozenset(self._entries)
