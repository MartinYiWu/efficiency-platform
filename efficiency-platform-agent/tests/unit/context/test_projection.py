"""工具投影的范围、完整性与受控分页行为。"""

from dataclasses import FrozenInstanceError, replace

import pytest

from efficiency_platform_agent.core.memory import (
    ConversationScope,
    ExecutionScope,
    SourceDependency,
)
from efficiency_platform_agent.core.run import JsonObject


def fixture():
    from efficiency_platform_agent.core.context_projection import (
        ProjectionBinding,
        ProjectionPolicy,
        ScopedProjectionRow,
        ToolProjectionSource,
        tool_query_ref,
    )

    scope = ExecutionScope(
        ConversationScope(
            "tenant", "user", "operations", "operations", "TASK_ONLY", None
        ),
        "task",
        "run",
        "subtask",
        "lookup",
        "expert",
    )
    from tests.unit.tools.test_tool_runtime import request

    binding = ProjectionBinding(
        scope, "authorized-department", "snapshot", "1", tool_query_ref(request())
    )
    dependency = SourceDependency("tool", "lookup", "1")
    rows = tuple(
        ScopedProjectionRow(binding, JsonObject((("id", n), ("private", "hidden"))))
        for n in range(20)
    )
    policy = ProjectionPolicy(
        binding, "lookup-minimal", "1", frozenset({"id"}), 20, 5000, (dependency,)
    )
    source = ToolProjectionSource(
        binding, rows, "UNKNOWN", None, None, (dependency,), "original-policy-reference"
    )
    return policy, source


def test_unknown_twenty_rows_does_not_claim_total_twenty():
    from efficiency_platform_agent.context.projection import project_tool_source

    policy, source = fixture()
    view = project_tool_source(source, policy)
    assert view.total_count is None
    assert view.completeness == "UNKNOWN"
    assert view.returned_count == 20
    assert all(dict(row.items).keys() == {"id"} for row in view.data)
    assert view.safety_dependencies == source.safety_dependencies
    assert view.retention_ref == source.retention_ref
    with pytest.raises(FrozenInstanceError):
        view.total_count = 20


@pytest.mark.parametrize("where", ["source", "row", "total"])
def test_cross_scope_rows_counts_and_snapshot_are_rejected(where):
    from efficiency_platform_agent.context.projection import project_tool_source

    policy, source = fixture()
    other = replace(source.binding, query_scope_ref="other-department")
    with pytest.raises(ValueError, match="SCOPE"):
        if where == "source":
            source = replace(source, binding=other)
        elif where == "row":
            source = replace(source, rows=(replace(source.rows[0], binding=other),))
        else:
            source = replace(source, total_count=200, total_binding=other)
        project_tool_source(source, policy)


def test_row_selection_marks_partial_and_preserves_known_authorized_total():
    from efficiency_platform_agent.context.projection import project_tool_source

    policy, source = fixture()
    source = replace(
        source, completeness="COMPLETE", total_count=20, total_binding=source.binding
    )
    view = project_tool_source(source, replace(policy, max_rows=3))
    assert (view.completeness, view.total_count, view.returned_count) == (
        "PARTIAL",
        20,
        3,
    )
    assert view.truncated and view.truncation_reason == "RESULT_LIMIT"


def test_token_selection_does_not_cut_json_or_hide_partial_status():
    from efficiency_platform_agent.context.projection import (
        project_tool_source,
        projection_token_upper_bound,
    )

    policy, source = fixture()
    full_size = projection_token_upper_bound(project_tool_source(source, policy))
    limit = full_size - 30
    view = project_tool_source(
        source, replace(policy, model_visible_token_upper_bound=limit)
    )
    assert view.completeness in {"PARTIAL", "UNKNOWN"}
    assert view.returned_count < 20
    assert view.truncation_reason == "TOKEN_LIMIT"
    assert projection_token_upper_bound(view) <= limit


def test_cursor_is_opaque_and_bound_to_scope_query_snapshot_purpose_and_expiry():
    from efficiency_platform_agent.context.projection import CursorAuthority

    policy, _ = fixture()
    authority = CursorAuthority()
    receipt = authority.issue(policy.binding, expires_at_epoch_ms=100)
    assert "tenant" not in receipt and "snapshot" not in receipt
    assert (
        authority.validate(receipt, policy.binding, now_epoch_ms=99) == policy.binding
    )
    for binding in (
        replace(policy.binding, query_scope_ref="other"),
        replace(policy.binding, snapshot_version="2"),
        replace(policy.binding, query_ref="other-query"),
        replace(policy.binding, scope=replace(policy.binding.scope, purpose="other")),
        replace(
            policy.binding,
            scope=replace(
                policy.binding.scope,
                conversation=replace(
                    policy.binding.scope.conversation, user_id="other"
                ),
            ),
        ),
        replace(
            policy.binding,
            scope=replace(
                policy.binding.scope,
                conversation=replace(
                    policy.binding.scope.conversation, tenant_id="other"
                ),
            ),
        ),
    ):
        with pytest.raises(ValueError, match="CURSOR"):
            authority.validate(receipt, binding, now_epoch_ms=99)
    with pytest.raises(ValueError, match="CURSOR"):
        authority.validate(receipt, policy.binding, now_epoch_ms=100)


@pytest.mark.asyncio
async def test_runtime_projection_uses_governed_invoke_and_preserves_legacy_result():
    from efficiency_platform_agent.context.projection import project_tool_source
    from efficiency_platform_agent.core.budget import RemainingBudget
    from efficiency_platform_agent.core.run import RunContext
    from efficiency_platform_agent.tools.runtime.registry import ToolRegistry
    from efficiency_platform_agent.tools.runtime.service import ToolRuntime
    from tests.unit.tools.test_tool_runtime import (
        CountingTool,
        descriptor,
        request,
        spec,
    )

    policy, source = fixture()

    class OwnerProjection:
        false_bound = False

        def project(self, request, result, selection):
            assert result.output == JsonObject((("lookup", "ok"),))
            view = project_tool_source(source, selection)
            return (
                replace(view, model_visible_token_upper_bound=1)
                if self.false_bound
                else view
            )

    registry = ToolRegistry()
    tool = CountingTool(descriptor())
    owner = OwnerProjection()
    registry.register(
        replace(
            spec(),
            projection_port=owner,
            projection_schema=policy.projection_schema,
            projection_version=policy.projection_version,
            model_visible_token_upper_bound=policy.model_visible_token_upper_bound,
        ),
        tool,
    )
    runtime = ToolRuntime(registry)
    context = RunContext("run", "tenant", "user", "trace")
    kwargs = {
        "allowed_tools": frozenset({"synthetic.lookup"}),
        "granted_permissions": frozenset({"lookup:read"}),
        "remaining_budget": RemainingBudget(3, 3, 100, 100, 1000, 100),
    }
    projected, records = await runtime.invoke_projected(
        request(), context, policy=policy, **kwargs
    )
    assert tool.calls == 1 and records[-1].status == "succeeded"
    assert projected.full_result.output == JsonObject((("lookup", "ok"),))
    assert projected.projection.completeness == "UNKNOWN"
    legacy, _ = await runtime.invoke(request(), context, **kwargs)
    assert legacy == projected.full_result
    with pytest.raises(ValueError, match="SCOPE"):
        await runtime.invoke_projected(
            request(), replace(context, user_id="other"), policy=policy, **kwargs
        )
    assert tool.calls == 2
    with pytest.raises(ValueError, match="QUERY"):
        await runtime.invoke_projected(
            request(arguments=JsonObject((("query", "different"),))),
            context,
            policy=policy,
            **kwargs,
        )
    assert tool.calls == 2
    owner.false_bound = True
    with pytest.raises(ValueError, match="PROJECTION"):
        await runtime.invoke_projected(request(), context, policy=policy, **kwargs)


def test_owner_must_publish_projection_version_and_model_visible_bound():
    from tests.unit.tools.test_tool_runtime import spec

    with pytest.raises(ValueError, match="PROJECTION"):
        replace(spec(), projection_port=object())


@pytest.mark.asyncio
@pytest.mark.parametrize("failure", ["permission", "unknown", "raw_oversize"])
async def test_projection_never_changes_governed_failure_into_success(failure):
    from efficiency_platform_agent.core.budget import RemainingBudget
    from efficiency_platform_agent.core.run import RunContext, ToolError, ToolResult
    from efficiency_platform_agent.tools.runtime.registry import ToolRegistry
    from efficiency_platform_agent.tools.runtime.service import ToolRuntime
    from tests.unit.tools.test_tool_runtime import (
        CountingTool,
        descriptor,
        request,
        spec,
    )

    policy, _ = fixture()

    class OwnerProjection:
        def project(self, request, result, selection):
            raise AssertionError("失败结果不得进入模型成功投影")

    result = ToolResult(
        "1",
        JsonObject((("lookup", "ok"),)),
        ToolError("UNKNOWN", "execution", False, "未知状态", "possible")
        if failure == "unknown"
        else None,
        129 if failure == "raw_oversize" else 14,
        False,
    )
    registry = ToolRegistry()
    tool = CountingTool(descriptor(), result=result)
    registry.register(
        replace(
            spec(),
            projection_port=OwnerProjection(),
            projection_schema=policy.projection_schema,
            projection_version=policy.projection_version,
            model_visible_token_upper_bound=policy.model_visible_token_upper_bound,
        ),
        tool,
    )
    projected, records = await ToolRuntime(registry).invoke_projected(
        request(),
        RunContext("run", "tenant", "user", "trace"),
        policy=policy,
        allowed_tools=frozenset({"synthetic.lookup"}),
        granted_permissions=frozenset()
        if failure == "permission"
        else frozenset({"lookup:read"}),
        remaining_budget=RemainingBudget(3, 3, 100, 100, 1000, 100),
    )
    assert projected.full_result.error is not None and projected.projection is None
    assert not records or records[-1].status == "failed"
