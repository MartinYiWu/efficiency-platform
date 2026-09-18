"""X05 V2 发布、关闭与回滚的离线演练。"""

from __future__ import annotations

import asyncio
from dataclasses import dataclass, field

import pytest

from efficiency_platform_agent.contracts.conversation import ConversationMessageV1
from efficiency_platform_agent.contracts.requests import (
    CancelRunRequestV1,
    CreateRunRequestV1,
)
from efficiency_platform_agent.conversation.intent_v2_adapter import (
    IntentV2ConversationAdapter,
    PipelineVersionSnapshotV2,
)
from efficiency_platform_agent.conversation.service import (
    ConversationService,
    ConversationSubmissionStore,
)
from efficiency_platform_agent.core.budget import BudgetGuard
from efficiency_platform_agent.core.enums import RunStatus, StrategyMode
from efficiency_platform_agent.core.run import ExecutionBudget, JsonObject
from efficiency_platform_agent.core.runtime import UsageSnapshot
from efficiency_platform_agent.harness.service import (
    AgentRuntimeService,
    RunPipelinePreparation,
)
from efficiency_platform_agent.orchestration.cancellation import (
    InMemoryCancellationSignal,
)
from efficiency_platform_agent.orchestration.contracts import (
    CheckpointView,
    GraphExecutionResult,
)
from efficiency_platform_agent.orchestration.scenario_resolver import ScenarioResolver
from efficiency_platform_agent.persistence.in_memory import (
    FixedClock,
    InMemoryRunEventStore,
    InMemoryRunRepository,
    SequenceIdGenerator,
)
from efficiency_platform_agent.routing.strategy_router import StrategyRouter


def _snapshot(
    *,
    intent: str = "intent-v2",
    research: str = "research-v2",
    replan: bool = True,
    rollout_mode: str = "all",
    tenants: tuple[str, ...] = (),
) -> PipelineVersionSnapshotV2:
    return PipelineVersionSnapshotV2(
        intent_pipeline_version=intent,
        research_pipeline_version=research,
        research_replan_enabled=replan,
        research_source_allowlist=("source-free",) if research == "research-v2" else (),
        research_policy_version=(
            "research-policy-v2" if research == "research-v2" else "policy-disabled"
        ),
        state_backend="memory",
        rollout_mode=rollout_mode,
        rollout_tenant_allowlist=tenants,
    )


def _message(request_id: str) -> ConversationMessageV1:
    return ConversationMessageV1(
        message="收集昨天 AI 新闻",
        request_id=request_id,
        user_id="user-1",
    )


@dataclass
class _RolloutProbeDelegate:
    source_registry: object = field(default_factory=object)
    tool_runtime: object = field(default_factory=object)
    research_service: object = field(default_factory=object)
    intent_state_store: object = field(default_factory=object)
    research_state_store: object = field(default_factory=object)
    submissions: ConversationSubmissionStore = field(
        default_factory=ConversationSubmissionStore
    )
    versions: list[PipelineVersionSnapshotV2] = field(default_factory=list)
    v1_checkpoint_reads: int = 0
    unverified_search_calls: int = 0
    evidence_ids: tuple[str, ...] = ("evidence-1", "evidence-2")

    async def prepare_v2(self, pipeline, tenant_id, conversation_id, message, versions):
        del pipeline, conversation_id
        self.versions.append(versions)
        return RunPipelinePreparation(
            CreateRunRequestV1(
                request_id=message.request_id,
                tenant_id=tenant_id,
                user_id=message.user_id,
                input_text=message.message,
                requested_strategy=StrategyMode.DIRECT,
            )
        )


class _ForbiddenV1Interpreter:
    async def execute(self, *args, **kwargs):
        raise AssertionError("活动 V2 回滚演练不得转交 V1 意图解释器")


class _RolloutBranchGraph:
    def __init__(
        self,
        target: RunStatus,
        cancellation: InMemoryCancellationSignal,
    ) -> None:
        self.target = target
        self.cancellation = cancellation
        self.started = asyncio.Event()
        self.release = asyncio.Event()

    async def execute(self, selection, initial_state):
        run_id = initial_state["run_id"]
        self.started.set()
        if self.target is RunStatus.CANCELLED:
            await self.cancellation.wait_requested(run_id)
        else:
            await self.release.wait()
        return GraphExecutionResult(
            usage=UsageSnapshot(1, 1, 0, estimated=True),
            budget_state=BudgetGuard().start(
                ExecutionBudget(10, 2, 100, 100, 100, 100),
                now_epoch_ms=initial_state["budget_state"]["started_at_epoch_ms"],
            ),
            checkpoint=CheckpointView(
                run_id,
                f"s2:{selection.mode}:1",
                f"cp-x05-{self.target.value}",
            ),
            facts=(),
            next_status=self.target,
            output=(
                JsonObject((("content", "V2 研究完成"),))
                if self.target is RunStatus.SUCCEEDED
                else None
            ),
        )


def _runtime_for_rollout(
    graph: _RolloutBranchGraph,
    cancellation: InMemoryCancellationSignal,
) -> AgentRuntimeService:
    return AgentRuntimeService(
        repository=InMemoryRunRepository(),
        event_store=InMemoryRunEventStore(),
        router=StrategyRouter(frozenset({StrategyMode.DIRECT})),
        graph_runtime=graph,
        budget_guard=BudgetGuard(),
        budget=ExecutionBudget(10, 2, 100, 100, 100, 100),
        clock=FixedClock(1),
        id_generator=SequenceIdGenerator(),
        cancellation_signal=cancellation,
    )


@pytest.mark.asyncio
async def test_disabling_v2_preserves_active_snapshot_and_evidence() -> None:
    delegate = _RolloutProbeDelegate()
    adapter = IntentV2ConversationAdapter(_snapshot(), delegate)

    await adapter.prepare(object(), "tenant-1", "active-v2", _message("request-1"))
    frozen = adapter.version_for("tenant-1", "active-v2")
    before_evidence = delegate.evidence_ids

    await adapter.update_rollout_settings(
        _snapshot(intent="intent-v1", research="research-v1", replan=False)
    )
    await adapter.prepare(object(), "tenant-1", "active-v2", _message("request-2"))
    new_task = await adapter.prepare(
        object(), "tenant-1", "new-after-disable", _message("request-3")
    )

    assert frozen is not None and frozen.v2_enabled is True
    assert delegate.versions == [frozen, frozen]
    assert new_task is None
    assert adapter.version_for("tenant-1", "new-after-disable").v2_enabled is False
    assert delegate.v1_checkpoint_reads == 0
    assert delegate.unverified_search_calls == 0
    assert delegate.evidence_ids == before_evidence


@pytest.mark.asyncio
async def test_reenabling_v2_does_not_upgrade_conversation_frozen_on_v1() -> None:
    delegate = _RolloutProbeDelegate()
    adapter = IntentV2ConversationAdapter(
        _snapshot(intent="intent-v1", research="research-v1", replan=False),
        delegate,
    )

    assert (
        await adapter.prepare(object(), "tenant-1", "old-v1", _message("request-1"))
        is None
    )
    await adapter.update_rollout_settings(_snapshot())
    assert (
        await adapter.prepare(object(), "tenant-1", "old-v1", _message("request-2"))
        is None
    )
    await adapter.prepare(object(), "tenant-1", "new-v2", _message("request-3"))

    assert adapter.version_for("tenant-1", "old-v1").v2_enabled is False
    assert adapter.version_for("tenant-1", "new-v2").v2_enabled is True
    assert len(delegate.versions) == 1


@pytest.mark.asyncio
async def test_replan_change_applies_only_to_new_conversations() -> None:
    delegate = _RolloutProbeDelegate()
    adapter = IntentV2ConversationAdapter(_snapshot(replan=True), delegate)

    await adapter.prepare(object(), "tenant-1", "before", _message("request-1"))
    await adapter.update_rollout_settings(_snapshot(replan=False))
    await adapter.prepare(object(), "tenant-1", "before", _message("request-2"))
    await adapter.prepare(object(), "tenant-1", "after", _message("request-3"))

    before = adapter.version_for("tenant-1", "before")
    after = adapter.version_for("tenant-1", "after")
    assert before is not None and before.research_replan_enabled is True
    assert after is not None and after.research_replan_enabled is False
    assert delegate.versions == [before, before, after]


@pytest.mark.asyncio
async def test_tenant_allowlist_freezes_unapproved_conversation_on_v1() -> None:
    delegate = _RolloutProbeDelegate()
    adapter = IntentV2ConversationAdapter(
        _snapshot(rollout_mode="tenant_allowlist", tenants=("tenant-canary",)),
        delegate,
    )

    denied = await adapter.prepare(
        object(), "tenant-other", "denied", _message("request-1")
    )
    await adapter.prepare(object(), "tenant-canary", "allowed", _message("request-2"))
    await adapter.update_rollout_settings(
        _snapshot(
            rollout_mode="tenant_allowlist",
            tenants=("tenant-canary", "tenant-other"),
        )
    )
    still_denied = await adapter.prepare(
        object(), "tenant-other", "denied", _message("request-3")
    )

    assert denied is None and still_denied is None
    assert adapter.version_for("tenant-other", "denied").v2_enabled is False
    assert adapter.version_for("tenant-canary", "allowed").v2_enabled is True
    assert len(delegate.versions) == 1


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "target",
    (RunStatus.SUCCEEDED, RunStatus.WAITING_INPUT),
    ids=("complete", "waiting-input"),
)
async def test_active_v2_complete_or_waiting_branch_survives_disable(
    target: RunStatus,
) -> None:
    cancellation = InMemoryCancellationSignal()
    graph = _RolloutBranchGraph(target, cancellation)
    runtime = _runtime_for_rollout(graph, cancellation)
    delegate = _RolloutProbeDelegate()
    adapter = IntentV2ConversationAdapter(_snapshot(), delegate)
    conversation = ConversationService(
        runtime=runtime,
        interpreter=_ForbiddenV1Interpreter(),
        resolver=ScenarioResolver(),
        submissions=delegate.submissions,
        intent_v2_coordinator=adapter,
    )
    evidence_before = delegate.evidence_ids

    submitted = await conversation.submit(
        f"x05-{target.value}",
        "tenant-1",
        _message(f"request-{target.value}"),
    )
    await asyncio.wait_for(graph.started.wait(), timeout=1)
    await adapter.update_rollout_settings(
        _snapshot(intent="intent-v1", research="research-v1", replan=False)
    )
    graph.release.set()
    await runtime.wait_for_background_tasks()

    result = await runtime.get_run(submitted.run_id, "tenant-1")
    events = await runtime.list_events(submitted.run_id, "tenant-1")
    frozen = adapter.version_for("tenant-1", f"x05-{target.value}")

    assert result.status is target
    assert result.checkpoint_id == f"cp-x05-{target.value}"
    assert frozen is not None and frozen.v2_enabled is True
    assert delegate.versions == [frozen]
    assert delegate.v1_checkpoint_reads == 0
    assert delegate.unverified_search_calls == 0
    assert delegate.evidence_ids == evidence_before
    assert [event.event_type for event in events][-2:] == [
        "checkpoint_saved",
        "run_succeeded" if target is RunStatus.SUCCEEDED else "run_waiting_input",
    ]


@pytest.mark.asyncio
async def test_active_v2_cancel_branch_survives_disable_and_keeps_record() -> None:
    cancellation = InMemoryCancellationSignal()
    graph = _RolloutBranchGraph(RunStatus.CANCELLED, cancellation)
    runtime = _runtime_for_rollout(graph, cancellation)
    delegate = _RolloutProbeDelegate()
    adapter = IntentV2ConversationAdapter(_snapshot(), delegate)
    conversation = ConversationService(
        runtime=runtime,
        interpreter=_ForbiddenV1Interpreter(),
        resolver=ScenarioResolver(),
        submissions=delegate.submissions,
        intent_v2_coordinator=adapter,
    )
    evidence_before = delegate.evidence_ids

    submitted = await conversation.submit(
        "x05-cancelled",
        "tenant-1",
        _message("request-cancelled"),
    )
    await asyncio.wait_for(graph.started.wait(), timeout=1)
    await adapter.update_rollout_settings(
        _snapshot(intent="intent-v1", research="research-v1", replan=False)
    )
    accepted = await runtime.cancel_run(
        submitted.run_id,
        CancelRunRequestV1(tenant_id="tenant-1"),
    )
    await runtime.wait_for_background_tasks()

    result = await runtime.get_run(submitted.run_id, "tenant-1")
    events = await runtime.list_events(submitted.run_id, "tenant-1")
    frozen = adapter.version_for("tenant-1", "x05-cancelled")
    event_names = [event.event_type for event in events]

    assert accepted.status is RunStatus.RUNNING
    assert result.status is RunStatus.CANCELLED
    assert frozen is not None and frozen.v2_enabled is True
    assert delegate.versions == [frozen]
    assert delegate.v1_checkpoint_reads == 0
    assert delegate.unverified_search_calls == 0
    assert delegate.evidence_ids == evidence_before
    assert event_names.count("run_cancel_requested") == 1
    assert event_names.count("run_cancelled") == 1
