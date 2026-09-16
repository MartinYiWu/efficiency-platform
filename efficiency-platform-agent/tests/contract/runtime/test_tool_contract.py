"""Tool Runtime 公共契约和合成 Tool 边界测试。"""

from __future__ import annotations

import inspect
from dataclasses import fields

from pydantic import BaseModel

from efficiency_platform_agent.core.ports import Tool
from efficiency_platform_agent.tools.internal.synthetic_lookup import (
    SyntheticLookupTool,
)
from efficiency_platform_agent.tools.runtime.contracts import (
    ToolInvocationRecord,
    ToolSpec,
)
from efficiency_platform_agent.tools.runtime.registry import ToolRegistry
from efficiency_platform_agent.tools.runtime.service import ToolRuntime


def test_tool_contract_shapes_are_stable() -> None:
    assert [field.name for field in fields(ToolSpec)] == [
        "tool_name",
        "semantic_version",
        "owner",
        "argument_schema_version",
        "result_schema_version",
        "argument_model",
        "result_model",
        "required_permissions",
        "has_side_effects",
        "max_attempts",
        "timeout_ms",
        "max_output_bytes",
    ]
    assert [field.name for field in fields(ToolInvocationRecord)] == [
        "invocation_id",
        "tool_name",
        "attempt",
        "status",
        "error_code",
        "output_bytes",
    ]
    assert isinstance(SyntheticLookupTool(), Tool)
    assert inspect.iscoroutinefunction(ToolRuntime.invoke)


def test_registry_rejects_duplicate_and_returns_registered_tool() -> None:
    from efficiency_platform_agent.core.run import (
        ExecutionBudget,
        ExtensionDescriptor,
        JsonObject,
        RunContext,
        ToolRequest,
        ToolResult,
    )
    from efficiency_platform_agent.tools.runtime.contracts import ToolSpec

    class Args(BaseModel):
        query: str

    class Result(BaseModel):
        lookup: str

    class FakeTool:
        descriptor = ExtensionDescriptor(
            "contract.tool",
            "1.0.0",
            "1",
            "1",
            frozenset(),
            ExecutionBudget(1, 1, 1, 1, 100, 1),
            frozenset({"done"}),
            "1",
        )

        async def invoke(self, request: ToolRequest, context: RunContext) -> ToolResult:
            del request, context
            return ToolResult("1", JsonObject((("lookup", "x"),)), None, 1, False)

    def make_spec() -> ToolSpec:
        return ToolSpec(
            "contract.tool",
            "1.0.0",
            "s2",
            "1",
            "1",
            Args,
            Result,
            frozenset(),
            False,
            1,
            100,
            8,
        )

    registry = ToolRegistry()
    tool = FakeTool()
    registry.register(make_spec(), tool)
    assert registry.get("contract.tool") == (make_spec(), tool)
    try:
        registry.register(make_spec(), tool)
    except ValueError:
        pass
    else:
        raise AssertionError("重复注册必须失败")
