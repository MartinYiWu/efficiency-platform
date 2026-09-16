"""Tool Runtime 的治理顺序、预算、超时和重试行为测试。"""

from __future__ import annotations

import asyncio
import time
from dataclasses import dataclass

import pytest
from pydantic import BaseModel

from efficiency_platform_agent.core.budget import (
    BudgetGuard,
    BudgetState,
    RemainingBudget,
)
from efficiency_platform_agent.core.run import (
    ExecutionBudget,
    ExtensionDescriptor,
    JsonObject,
    RunContext,
    ToolError,
    ToolRequest,
    ToolResult,
)
from efficiency_platform_agent.tools.runtime.contracts import ToolSpec
from efficiency_platform_agent.tools.runtime.registry import ToolRegistry
from efficiency_platform_agent.tools.runtime.service import ToolRuntime


class QueryArguments(BaseModel):
    query: str


class LookupResult(BaseModel):
    lookup: str


def descriptor(
    name: str = "synthetic.lookup", *, side_effect: bool = False
) -> ExtensionDescriptor:
    return ExtensionDescriptor(
        name=name,
        semantic_version="1.0.0",
        input_schema_version="1",
        output_schema_version="1",
        permissions=frozenset({"lookup:read"}),
        budget=ExecutionBudget(3, 5, 100, 100, 500, 100),
        termination_conditions=frozenset({"completed", "failed"}),
        checkpoint_version="1",
    )


@dataclass
class CountingTool:
    descriptor: ExtensionDescriptor
    result: ToolResult | None = None
    delay: float = 0
    calls: int = 0

    async def invoke(self, request: ToolRequest, context: RunContext) -> ToolResult:
        self.calls += 1
        if self.delay:
            await asyncio.sleep(self.delay)
        if self.result is not None:
            return self.result
        return ToolResult("1", JsonObject((("lookup", "ok"),)), None, 14, False)


def spec(
    name: str = "synthetic.lookup",
    *,
    side_effects: bool = False,
    attempts: int = 2,
    timeout_ms: int = 100,
) -> ToolSpec:
    return ToolSpec(
        tool_name=name,
        semantic_version="1.0.0",
        owner="s2",
        argument_schema_version="1",
        result_schema_version="1",
        argument_model=QueryArguments,
        result_model=LookupResult,
        required_permissions=frozenset({"lookup:read"}),
        has_side_effects=side_effects,
        max_attempts=attempts,
        timeout_ms=timeout_ms,
        max_output_bytes=128,
    )


def request(
    name: str = "synthetic.lookup",
    arguments: JsonObject | None = None,
    timeout_ms: int = 100,
) -> ToolRequest:
    return ToolRequest(
        "1",
        name,
        arguments or JsonObject((("query", "hello"),)),
        timeout_ms,
        None,
        None,
        False,
        128,
    )


def remaining(**changes: int) -> RemainingBudget:
    values = {
        "iterations": 3,
        "tool_calls": 2,
        "input_tokens": 20,
        "output_tokens": 20,
        "cost_microunits": 20,
        "timeout_ms": 100,
    }
    values.update(changes)
    return RemainingBudget(**values)


def runtime(
    tool: CountingTool, tool_spec: ToolSpec | None = None, **kwargs: object
) -> ToolRuntime:
    registry = ToolRegistry()
    registry.register(tool_spec or spec(), tool)
    return ToolRuntime(registry, **kwargs)


def ctx() -> RunContext:
    return RunContext("run-1", "tenant-1", "user-1", "trace-1")


@pytest.mark.asyncio
async def test_valid_read_only_invocation_returns_structured_result() -> None:
    tool = CountingTool(descriptor())
    result, records = await runtime(tool).invoke(
        request(),
        ctx(),
        allowed_tools=frozenset({"synthetic.lookup"}),
        granted_permissions=frozenset({"lookup:read"}),
        remaining_budget=remaining(),
    )
    assert result.error is None
    assert result.output == JsonObject((("lookup", "ok"),))
    assert tool.calls == 1
    assert records[-1].status == "succeeded"


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("case", "allowed", "permissions", "tool_spec", "arguments", "expected", "name"),
    [
        (
            "not registered",
            frozenset({"missing"}),
            frozenset(),
            None,
            None,
            "TOOL_NOT_REGISTERED",
            "missing",
        ),
        (
            "not allowed",
            frozenset(),
            frozenset({"lookup:read"}),
            None,
            None,
            "TOOL_NOT_ALLOWED",
            "synthetic.lookup",
        ),
        (
            "permission denied",
            frozenset({"synthetic.lookup"}),
            frozenset(),
            None,
            None,
            "TOOL_PERMISSION_DENIED",
            "synthetic.lookup",
        ),
        (
            "side effect",
            frozenset({"synthetic.lookup"}),
            frozenset({"lookup:read"}),
            spec(side_effects=True),
            None,
            "TOOL_SIDE_EFFECT_FORBIDDEN",
            "synthetic.lookup",
        ),
        (
            "invalid arguments",
            frozenset({"synthetic.lookup"}),
            frozenset({"lookup:read"}),
            None,
            JsonObject((("wrong", "x"),)),
            "TOOL_ARGUMENT_INVALID",
            "synthetic.lookup",
        ),
    ],
)
async def test_rejection_paths_do_not_call_tool(
    case: str,
    allowed: frozenset[str],
    permissions: frozenset[str],
    tool_spec: ToolSpec | None,
    arguments: JsonObject | None,
    expected: str,
    name: str,
) -> None:
    del case
    tool = CountingTool(descriptor())
    rt = runtime(tool, tool_spec=tool_spec)
    result, _ = await rt.invoke(
        request(name=name, arguments=arguments),
        ctx(),
        allowed_tools=allowed,
        granted_permissions=permissions,
        remaining_budget=remaining(),
    )
    assert result.error is not None and result.error.code == expected
    assert tool.calls == 0


@pytest.mark.asyncio
async def test_budget_rejection_is_before_tool_call() -> None:
    tool = CountingTool(descriptor())
    result, _ = await runtime(tool).invoke(
        request(),
        ctx(),
        allowed_tools=frozenset({"synthetic.lookup"}),
        granted_permissions=frozenset({"lookup:read"}),
        remaining_budget=remaining(tool_calls=0),
    )
    assert result.error is not None and result.error.code == "BUDGET_EXHAUSTED"
    assert tool.calls == 0


@pytest.mark.asyncio
async def test_timeout_is_deterministic_and_does_not_expose_input() -> None:
    tool = CountingTool(descriptor(), delay=0.05)
    result, records = await runtime(tool, tool_spec=spec(timeout_ms=5)).invoke(
        request(timeout_ms=5),
        ctx(),
        allowed_tools=frozenset({"synthetic.lookup"}),
        granted_permissions=frozenset({"lookup:read"}),
        remaining_budget=remaining(timeout_ms=50),
    )
    assert result.error is not None and result.error.code == "TOOL_TIMEOUT"
    assert "hello" not in result.error.safe_message
    assert records[-1].status == "timeout"


@pytest.mark.asyncio
async def test_retryable_failure_retries_once_and_non_retryable_does_not() -> None:
    failure = ToolResult(
        "1",
        None,
        ToolError("TEMP", "execution", True, "工具暂时不可用", "none"),
        0,
        False,
    )
    retry_tool = CountingTool(descriptor(), result=failure)
    retry_result, retry_records = await runtime(retry_tool).invoke(
        request(),
        ctx(),
        allowed_tools=frozenset({"synthetic.lookup"}),
        granted_permissions=frozenset({"lookup:read"}),
        remaining_budget=remaining(),
    )
    assert retry_tool.calls == 2
    assert retry_result.error is not None and len(retry_records) == 2

    permanent = ToolResult(
        "1",
        None,
        ToolError("BAD", "execution", False, "工具执行失败", "none"),
        0,
        False,
    )
    permanent_tool = CountingTool(descriptor(), result=permanent)
    await runtime(permanent_tool).invoke(
        request(),
        ctx(),
        allowed_tools=frozenset({"synthetic.lookup"}),
        granted_permissions=frozenset({"lookup:read"}),
        remaining_budget=remaining(),
    )
    assert permanent_tool.calls == 1


@pytest.mark.asyncio
async def test_output_size_limit_discards_output() -> None:
    oversized = ToolResult("1", JsonObject((("lookup", "x"),)), None, 129, False)
    tool = CountingTool(descriptor(), result=oversized)
    result, _ = await runtime(tool).invoke(
        request(),
        ctx(),
        allowed_tools=frozenset({"synthetic.lookup"}),
        granted_permissions=frozenset({"lookup:read"}),
        remaining_budget=remaining(),
    )
    assert result.error is not None and result.error.code == "TOOL_OUTPUT_TOO_LARGE"
    assert result.output is None


@pytest.mark.asyncio
async def test_retry_attempts_share_one_absolute_deadline() -> None:
    failure = ToolResult(
        "1", None, ToolError("TEMP", "execution", True, "暂时失败", "none"), 0, False
    )
    tool = CountingTool(descriptor(), result=failure, delay=0.06)
    started = time.monotonic()
    result, records = await runtime(tool).invoke(
        request(timeout_ms=100),
        ctx(),
        allowed_tools=frozenset({"synthetic.lookup"}),
        granted_permissions=frozenset({"lookup:read"}),
        remaining_budget=remaining(timeout_ms=100),
    )
    elapsed = time.monotonic() - started
    assert result.error is not None and result.error.code == "TOOL_TIMEOUT"
    assert tool.calls == 2
    assert records[-1].status == "timeout"
    assert elapsed < 0.125


@pytest.mark.asyncio
async def test_tool_error_output_is_governed_before_return() -> None:
    untrusted = ToolResult(
        "1",
        JsonObject((("lookup", "x"),)),
        ToolError("UNTRUSTED", "execution", False, "泄露输入 hello", "none"),
        129,
        False,
    )
    tool = CountingTool(descriptor(), result=untrusted)
    result, records = await runtime(tool).invoke(
        request(),
        ctx(),
        allowed_tools=frozenset({"synthetic.lookup"}),
        granted_permissions=frozenset({"lookup:read"}),
        remaining_budget=remaining(),
    )
    assert result.output is None
    assert result.error is not None and result.error.code == "TOOL_OUTPUT_TOO_LARGE"
    assert "hello" not in result.error.safe_message
    assert records[-1].error_code == "TOOL_OUTPUT_TOO_LARGE"


class SpyBudgetGuard(BudgetGuard):
    def __init__(self) -> None:
        self.before_calls = 0
        self.after_calls = 0

    def check_before_node(self, *args: object, **kwargs: object) -> RemainingBudget:
        self.before_calls += 1
        return super().check_before_node(*args, **kwargs)  # type: ignore[arg-type]

    def record_after_node(
        self, *args: object, **kwargs: object
    ) -> tuple[BudgetState, RemainingBudget]:
        self.after_calls += 1
        return super().record_after_node(*args, **kwargs)  # type: ignore[arg-type]


@pytest.mark.asyncio
async def test_runtime_records_tool_attempt_through_budget_guard() -> None:
    budget = ExecutionBudget(3, 2, 20, 20, 100, 20)
    guard = SpyBudgetGuard()
    state = guard.start(budget, now_epoch_ms=1_000)
    tool = CountingTool(descriptor())
    rt = ToolRuntime(
        ToolRegistry(),
        budget_guard=guard,
        budget=budget,
        budget_state=state,
        clock=lambda: 1_001,
    )
    rt.registry.register(spec(), tool)
    result, _ = await rt.invoke(
        request(),
        ctx(),
        allowed_tools=frozenset({"synthetic.lookup"}),
        granted_permissions=frozenset({"lookup:read"}),
        remaining_budget=remaining(),
    )
    assert result.error is None
    assert guard.before_calls == 1
    assert guard.after_calls == 1
    assert rt.budget_state is not None
    assert rt.budget_state.consumed.tool_calls == 1
