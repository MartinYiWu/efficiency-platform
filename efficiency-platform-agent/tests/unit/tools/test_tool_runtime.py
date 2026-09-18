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
from efficiency_platform_agent.core.budget_execution import (
    BudgetExecutionBinding,
    bind_budget_execution,
)
from efficiency_platform_agent.core.budget_lease import (
    BudgetLimits,
    BudgetScope,
    InMemoryBudgetLeaseRepository,
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
from efficiency_platform_agent.tools.runtime.service import (
    ToolBudgetContext,
    ToolLeaseContext,
    ToolRuntime,
)


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


@dataclass
class TerminalTool:
    descriptor: ExtensionDescriptor
    repository: InMemoryBudgetLeaseRepository
    scope: BudgetScope
    calls: int = 0

    async def invoke(self, request: ToolRequest, context: RunContext) -> ToolResult:
        del request, context
        self.calls += 1
        await self.repository.mark_scope_terminal(self.scope, "cancelled")
        return ToolResult("1", JsonObject((("lookup", "late"),)), None, 16, False)


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


@pytest.mark.asyncio
async def test_tool_runtime_uses_task_local_live_acceptance_lease() -> None:
    registry = ToolRegistry()
    tool = CountingTool(descriptor())
    registry.register(spec(), tool)
    repository = InMemoryBudgetLeaseRepository(
        BudgetLimits(max_calls=2, max_bytes=1_000, max_cost_microunits=100)
    )
    scope = BudgetScope("tenant-1", "acceptance-1", "live_acceptance", "all")
    binding = BudgetExecutionBinding(
        repository,
        scope,
        "lease-live-1",
        "a" * 64,
    )
    runtime = ToolRuntime(registry)

    with bind_budget_execution(binding):
        result, records = await runtime.invoke(
            request(),
            RunContext("acceptance-1", "tenant-1", "user-1", "trace-1"),
            allowed_tools=frozenset({"synthetic.lookup"}),
            granted_permissions=frozenset({"lookup:read"}),
            remaining_budget=RemainingBudget(10, 10, 100, 100, 100, 1_000),
        )

    snapshot = await repository.snapshot(scope)
    assert result.error is None
    assert len(records) == 1
    assert tool.calls == 1
    assert snapshot.used.calls == 1
    assert binding.version == snapshot.version


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
    budget_context = ToolBudgetContext(guard, budget, state)
    rt = ToolRuntime(ToolRegistry(), clock=lambda: 1_001)
    rt.registry.register(spec(), tool)
    result, _ = await rt.invoke(
        request(),
        ctx(),
        allowed_tools=frozenset({"synthetic.lookup"}),
        granted_permissions=frozenset({"lookup:read"}),
        remaining_budget=remaining(),
        budget_context=budget_context,
    )
    assert result.error is None
    assert guard.before_calls == 1
    assert guard.after_calls == 1
    assert budget_context.state.consumed.tool_calls == 1


@pytest.mark.asyncio
async def test_concurrent_invocations_keep_budget_contexts_isolated() -> None:
    budget = ExecutionBudget(3, 2, 20, 20, 500, 20)
    first_guard = BudgetGuard()
    second_guard = BudgetGuard()
    first_context = ToolBudgetContext(
        first_guard,
        budget,
        first_guard.start(budget, now_epoch_ms=1_000),
    )
    second_context = ToolBudgetContext(
        second_guard,
        budget,
        second_guard.start(budget, now_epoch_ms=1_000),
    )
    tool = CountingTool(descriptor(), delay=0.01)
    rt = runtime(tool, clock=lambda: 1_001)

    async def invoke(context: ToolBudgetContext):
        return await rt.invoke(
            request(),
            ctx(),
            allowed_tools=frozenset({"synthetic.lookup"}),
            granted_permissions=frozenset({"lookup:read"}),
            remaining_budget=remaining(),
            budget_context=context,
        )

    await asyncio.gather(invoke(first_context), invoke(second_context))
    assert first_context.state.consumed.tool_calls == 1
    assert second_context.state.consumed.tool_calls == 1
    assert tool.calls == 2


@pytest.mark.asyncio
async def test_lease_rejection_prevents_tool_dispatch() -> None:
    repository = InMemoryBudgetLeaseRepository(
        BudgetLimits(max_calls=0, max_bytes=1_000, max_cost_microunits=100)
    )
    scope = BudgetScope("tenant-1", "run-1", "research", "tool")
    tool = CountingTool(descriptor())
    result, _ = await runtime(tool).invoke(
        request(),
        ctx(),
        allowed_tools=frozenset({"synthetic.lookup"}),
        granted_permissions=frozenset({"lookup:read"}),
        remaining_budget=remaining(),
        lease_context=ToolLeaseContext(repository, scope, "tool-call", 0),
    )
    assert result.error is not None and result.error.code == "BUDGET_EXHAUSTED"
    assert tool.calls == 0
    assert repository.dispatched_invocation_count == 0


@pytest.mark.asyncio
async def test_successful_tool_attempt_uses_parent_lease_once() -> None:
    repository = InMemoryBudgetLeaseRepository(
        BudgetLimits(max_calls=1, max_bytes=1_000, max_cost_microunits=100)
    )
    scope = BudgetScope("tenant-1", "run-1", "research", "tool")
    lease_context = ToolLeaseContext(repository, scope, "tool-call", 0)
    tool = CountingTool(descriptor())
    result, _ = await runtime(tool).invoke(
        request(),
        ctx(),
        allowed_tools=frozenset({"synthetic.lookup"}),
        granted_permissions=frozenset({"lookup:read"}),
        remaining_budget=remaining(),
        lease_context=lease_context,
    )
    snapshot = await repository.snapshot(scope)
    assert result.error is None
    assert tool.calls == 1
    assert repository.dispatched_invocation_count == 1
    assert snapshot.used.calls == 1
    assert snapshot.used.bytes == 14
    assert snapshot.reserved.calls == 0
    assert lease_context.version == snapshot.version


@pytest.mark.asyncio
async def test_lease_is_the_only_budget_path() -> None:
    repository = InMemoryBudgetLeaseRepository(
        BudgetLimits(max_calls=1, max_bytes=1_000, max_cost_microunits=100)
    )
    scope = BudgetScope("tenant-1", "run-1", "research", "tool")
    budget = ExecutionBudget(3, 2, 20, 20, 100, 20)
    guard = BudgetGuard()
    context = ToolBudgetContext(
        guard,
        budget,
        guard.start(budget, now_epoch_ms=1_000),
    )
    with pytest.raises(ValueError, match="唯一预算计账路径"):
        await runtime(CountingTool(descriptor())).invoke(
            request(),
            ctx(),
            allowed_tools=frozenset({"synthetic.lookup"}),
            granted_permissions=frozenset({"lookup:read"}),
            remaining_budget=remaining(),
            budget_context=context,
            lease_context=ToolLeaseContext(repository, scope, "tool-call", 0),
        )


@pytest.mark.asyncio
async def test_late_tool_success_is_audit_only_and_not_delivered() -> None:
    repository = InMemoryBudgetLeaseRepository(
        BudgetLimits(max_calls=1, max_bytes=1_000, max_cost_microunits=100)
    )
    scope = BudgetScope("tenant-1", "run-1", "research", "tool")
    tool = TerminalTool(descriptor(), repository, scope)
    result, _ = await runtime(tool).invoke(
        request(),
        ctx(),
        allowed_tools=frozenset({"synthetic.lookup"}),
        granted_permissions=frozenset({"lookup:read"}),
        remaining_budget=remaining(),
        lease_context=ToolLeaseContext(repository, scope, "tool-call", 0),
    )
    assert tool.calls == 1
    assert result.output is None
    assert result.error is not None and result.error.code == "TOOL_CANCELLED"
    assert repository.audit_records[-1].delivery_allowed is False


@pytest.mark.asyncio
async def test_lease_path_does_not_early_return_on_stale_legacy_remaining() -> None:
    repository = InMemoryBudgetLeaseRepository(
        BudgetLimits(
            max_calls=1,
            max_bytes=1_000,
            max_cost_microunits=100,
            max_output_tokens=100,
        )
    )
    scope = BudgetScope("tenant-1", "run-1", "research", "tool")
    tool_result = ToolResult(
        "1",
        JsonObject((("lookup", "ok"),)),
        None,
        14,
        False,
        JsonObject((("output_tokens", 5), ("cost_microunits", 7))),
    )
    tool = CountingTool(descriptor(), result=tool_result)
    result, _ = await runtime(tool).invoke(
        request(),
        ctx(),
        allowed_tools=frozenset({"synthetic.lookup"}),
        granted_permissions=frozenset({"lookup:read"}),
        remaining_budget=remaining(tool_calls=0, output_tokens=0, cost_microunits=0),
        lease_context=ToolLeaseContext(repository, scope, "tool-call", 0),
    )
    snapshot = await repository.snapshot(scope)
    assert result.error is None
    assert snapshot.used.calls == 1
    assert snapshot.used.output_tokens == 5
    assert snapshot.used.cost_microunits == 7
    assert snapshot.reserved.calls == 0


@pytest.mark.asyncio
async def test_concurrent_parent_lease_calls_retry_fresh_cas_version() -> None:
    repository = InMemoryBudgetLeaseRepository(
        BudgetLimits(max_calls=2, max_bytes=1_000, max_cost_microunits=100)
    )
    scope = BudgetScope("tenant-1", "run-1", "research", "tool")
    tool = CountingTool(descriptor(), delay=0.01)
    rt = runtime(tool)

    async def invoke(prefix: str):
        return await rt.invoke(
            request(),
            ctx(),
            allowed_tools=frozenset({"synthetic.lookup"}),
            granted_permissions=frozenset({"lookup:read"}),
            remaining_budget=remaining(),
            lease_context=ToolLeaseContext(repository, scope, prefix, 0),
        )

    first, second = await asyncio.gather(invoke("first"), invoke("second"))
    snapshot = await repository.snapshot(scope)
    assert first[0].error is None
    assert second[0].error is None
    assert tool.calls == 2
    assert snapshot.used.calls == 2
    assert snapshot.reserved.calls == 0


@pytest.mark.asyncio
async def test_constructor_budget_accumulates_across_tool_calls() -> None:
    budget = ExecutionBudget(3, 1, 20, 20, 1_000, 20)
    guard = BudgetGuard()
    tool = CountingTool(descriptor())
    rt = runtime(
        tool,
        budget_guard=guard,
        budget=budget,
        budget_state=guard.start(budget, now_epoch_ms=1_000),
        clock=lambda: 1_001,
    )

    async def invoke():
        return await rt.invoke(
            request(),
            ctx(),
            allowed_tools=frozenset({"synthetic.lookup"}),
            granted_permissions=frozenset({"lookup:read"}),
            remaining_budget=remaining(),
        )

    first = await invoke()
    second = await invoke()
    assert first[0].error is None
    assert second[0].error is not None
    assert second[0].error.code == "BUDGET_EXHAUSTED"
    assert tool.calls == 1
    assert rt.budget_state is not None
    assert rt.budget_state.consumed.tool_calls == 1


@pytest.mark.asyncio
async def test_tool_settlement_overrun_closes_dispatched_reservation() -> None:
    repository = InMemoryBudgetLeaseRepository(
        BudgetLimits(
            max_calls=1,
            max_bytes=1_000,
            max_cost_microunits=0,
            max_output_tokens=100,
        )
    )
    scope = BudgetScope("tenant-1", "run-1", "research", "tool")
    tool_result = ToolResult(
        "1",
        JsonObject((("lookup", "secret"),)),
        None,
        18,
        False,
        JsonObject((("cost_microunits", 7),)),
    )
    tool = CountingTool(descriptor(), result=tool_result)
    result, _ = await runtime(tool).invoke(
        request(),
        ctx(),
        allowed_tools=frozenset({"synthetic.lookup"}),
        granted_permissions=frozenset({"lookup:read"}),
        remaining_budget=remaining(),
        lease_context=ToolLeaseContext(
            repository,
            scope,
            "tool-overrun",
            0,
            reserve_cost_microunits=0,
        ),
    )
    snapshot = await repository.snapshot(scope)
    assert result.output is None
    assert result.error is not None and result.error.code == "BUDGET_EXHAUSTED"
    assert snapshot.reserved.calls == 0
    assert snapshot.used.calls == 1
    assert snapshot.used.cost_microunits == 7
    assert repository.audit_records[-1].actual.cost_microunits == 7
    assert repository.audit_records[-1].over_limit is True
    assert repository.audit_records[-1].outcome == "success"
