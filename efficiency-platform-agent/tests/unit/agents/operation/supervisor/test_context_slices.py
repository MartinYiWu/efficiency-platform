"""专家最小输入与部分覆盖的父聚合行为。"""

from dataclasses import replace

import pytest

from efficiency_platform_agent.core.run import JsonObject
from tests.unit.context.test_projection import fixture


def slice_fixture():
    from efficiency_platform_agent.agents.operation.specialists.contracts import (
        SpecialistContextSlice,
    )

    policy, _ = fixture()
    return SpecialistContextSlice(
        "specialist-context-slice/1",
        policy.binding.scope,
        "goal",
        ("read-only",),
        policy.authorized_dependencies,
        (),
        frozenset({"synthetic.read"}),
        "synthetic-output/1",
        "window-policy/1",
        "parent-budget-ref",
        ("a", "b"),
    )


def test_slice_serialization_has_no_parent_history_or_checkpoint():
    view = slice_fixture().to_json()
    assert isinstance(view, JsonObject)
    assert set(dict(view.items)) == {
        "contract_version",
        "scope",
        "goal",
        "constraints",
        "source_dependencies",
        "preferences",
        "allowed_tools",
        "output_contract",
        "window_policy_ref",
        "parent_budget_ref",
        "requested_scope",
    }


def test_new_dispatch_accepts_only_minimal_slice_and_rechecks_tools_and_target():
    from efficiency_platform_agent.agents.factory import AgentFactory
    from efficiency_platform_agent.agents.operation.supervisor.budget import (
        BudgetLedger,
    )
    from efficiency_platform_agent.agents.operation.supervisor.dispatch import (
        DispatchBuilder,
    )
    from efficiency_platform_agent.agents.operation.supervisor.selection import (
        SpecialistSelector,
    )
    from efficiency_platform_agent.core.run import ExecutionBudget
    from tests.support.supervisor_fakes import (
        build_specialist_spec,
        build_task_node,
        register_specialists,
    )

    slice_ = slice_fixture()
    node = build_task_node(task_id="subtask")
    registry = register_specialists((build_specialist_spec("expert"),))
    selected = SpecialistSelector(registry).rank(node)[0]
    ledger = BudgetLedger.allocate(
        ExecutionBudget(10, 10, 1000, 1000, 30000, 100),
        ((node.task_id, node.requested_budget),),
    )
    builder = DispatchBuilder(AgentFactory(registry), ledger)
    kwargs = {
        "parent_run_id": "run",
        "parent_deadline_epoch_ms": 99,
        "input_data": JsonObject(),
        "context_slice": slice_,
    }
    dispatched = builder.build(node, selected, **kwargs)
    assert dispatched.task.context_view == slice_.to_json()
    with pytest.raises(ValueError, match="SLICE"):
        builder.build(
            node,
            selected,
            **{**kwargs, "input_data": JsonObject((("history", "secret"),))},
        )
    with pytest.raises(ValueError, match="SLICE"):
        builder.build(
            node,
            selected,
            **{
                **kwargs,
                "context_slice": replace(slice_, allowed_tools=frozenset({"write"})),
            },
        )


@pytest.mark.parametrize("completeness", ["PARTIAL", "UNKNOWN"])
def test_partial_expert_does_not_become_complete_even_if_outcome_succeeded(
    completeness,
):
    from efficiency_platform_agent.agents.operation.specialists.contracts import (
        SpecialistResultProjection,
    )
    from efficiency_platform_agent.agents.operation.supervisor.aggregation import (
        ResultAggregator,
    )
    from efficiency_platform_agent.core.multi_agent import (
        CompletionStatus,
        TaskExecutionStatus,
    )
    from tests.unit.agents.operation.supervisor.test_aggregation import (
        _graph,
        _node,
        _outcome,
    )

    slice_ = slice_fixture()
    projection = SpecialistResultProjection(
        "specialist-result-projection/1",
        "subtask",
        slice_.scope,
        ("finding",),
        ("reference",),
        ("unresolved",),
        ("risk",),
        (("recommendation", "PROPOSED"),),
        ("artifact-ref",),
        completeness,
        ("a",),
        ("b",),
        slice_.source_dependencies,
        slice_.source_dependencies,
    )
    result = ResultAggregator().aggregate(
        _graph(_node("subtask")),
        (_outcome("subtask", TaskExecutionStatus.SUCCEEDED),),
        (projection,),
        context_slices=(slice_,),
    )
    assert result.completion_status is CompletionStatus.PARTIAL
    assert result.missing_scope == ("b",)
    assert result.safety_dependencies == projection.safety_dependencies
    with pytest.raises(ValueError, match="SLICE"):
        ResultAggregator().aggregate(
            _graph(_node("subtask")),
            (_outcome("subtask", TaskExecutionStatus.SUCCEEDED),),
            (projection,),
        )


def test_projected_output_roundtrips_through_versioned_decoder_and_cannot_drop_dependencies():
    from efficiency_platform_agent.agents.operation.specialists.contracts import (
        SpecialistResultProjection,
    )
    from efficiency_platform_agent.agents.operation.supervisor.dispatch import (
        SpecialistResultDecoder,
    )
    from efficiency_platform_agent.core.enums import RunStatus, StrategyMode
    from efficiency_platform_agent.core.run import RunResult

    slice_ = slice_fixture()
    projection = SpecialistResultProjection(
        "specialist-result-projection/1",
        "subtask",
        slice_.scope,
        ("finding",),
        ("reference",),
        (),
        (),
        (),
        ("artifact",),
        "COMPLETE",
        ("a", "b"),
        (),
        slice_.source_dependencies,
        slice_.source_dependencies,
    )
    result = RunResult(
        "run", RunStatus.SUCCEEDED, StrategyMode.MULTI_AGENT, projection.to_json()
    )
    assert SpecialistResultDecoder().decode_projected(result, slice_) == projection
    with pytest.raises(ValueError, match="SLICE"):
        replace(
            projection, source_dependencies=(), safety_dependencies=()
        ).validate_slice(slice_)


def test_legacy_success_with_missing_scope_remains_partial():
    from efficiency_platform_agent.agents.operation.supervisor.aggregation import (
        ResultAggregator,
    )
    from efficiency_platform_agent.core.multi_agent import (
        CompletionStatus,
        TaskExecutionStatus,
    )
    from tests.unit.agents.operation.supervisor.test_aggregation import (
        _envelope,
        _graph,
        _node,
        _outcome,
    )

    envelope = replace(_envelope("subtask"), missing_scope=("unresolved",))
    result = ResultAggregator().aggregate(
        _graph(_node("subtask")),
        (_outcome("subtask", TaskExecutionStatus.SUCCEEDED),),
        (envelope,),
    )
    assert result.completion_status is CompletionStatus.PARTIAL
    assert result.missing_scope == ("unresolved",)
