"""无外部 I/O 的合成查询 Tool。"""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict

from efficiency_platform_agent.core.ports import Tool
from efficiency_platform_agent.core.run import (
    ExecutionBudget,
    ExtensionDescriptor,
    JsonObject,
    RunContext,
    ToolRequest,
    ToolResult,
)


class SyntheticLookupArguments(BaseModel):
    """合成查询参数。"""

    model_config = ConfigDict(extra="forbid")
    query: str


class SyntheticLookupResult(BaseModel):
    """合成查询结果。"""

    model_config = ConfigDict(extra="forbid")
    lookup: str


class SyntheticLookupTool:
    """把任意已校验 query 映射为固定结果，不访问外部系统。"""

    descriptor = ExtensionDescriptor(
        name="synthetic.lookup",
        semantic_version="1.0.0",
        input_schema_version="1",
        output_schema_version="1",
        permissions=frozenset({"lookup:read"}),
        budget=ExecutionBudget(3, 2, 100, 100, 100, 100),
        termination_conditions=frozenset({"completed", "failed"}),
        checkpoint_version="1",
    )

    async def invoke(self, request: ToolRequest, context: RunContext) -> ToolResult:
        """返回固定合成结果；参数已由 Runtime 校验。"""
        del request, context
        output = JsonObject((("lookup", "synthetic-result"),))
        return ToolResult(
            "1", output, None, len('{"lookup":"synthetic-result"}'), False
        )


assert isinstance(SyntheticLookupTool(), Tool)
