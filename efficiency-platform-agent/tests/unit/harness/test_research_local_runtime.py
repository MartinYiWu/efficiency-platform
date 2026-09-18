"""逐 Run 装配与父预算、取消、重试的可复现检查。"""

import asyncio
import importlib
from dataclasses import replace
from datetime import timedelta

import pytest

from efficiency_platform_agent.contracts.research_v2 import (
    ResearchPolicySnapshotV2,
    ResearchRuntimeContextV2,
)
from efficiency_platform_agent.core.budget import RemainingBudget
from efficiency_platform_agent.core.budget_execution import (
    current_budget_execution_binding,
)
from efficiency_platform_agent.core.budget_lease import BudgetCharge
from efficiency_platform_agent.harness.research_v2_adapter import (
    InMemoryResearchBriefStoreV2,
)
from efficiency_platform_agent.orchestration.research_v2.service import (
    LangGraphResearchServiceV2,
)
from tests.integration.research_v2.test_local_memory_isolation import (
    NOW,
    case,
    local_types,
)
from tests.orchestration.research_v2.test_service import _Materializer, _Runner


def runtime_module():
    name = "efficiency_platform_agent.harness.research_local_runtime"
    assert importlib.util.find_spec(name), "Task3 缺少逐 Run 服务"
    return importlib.import_module(name)


async def test_same_conversation_task_keeps_briefs_separate_by_run():
    from tests.unit.capabilities.research_v2._delivery_support import delivery_facts

    first, *_ = delivery_facts()
    second = first.model_copy(
        update={
            "trusted_context": first.trusted_context.model_copy(
                update={"run_id": "second"}
            )
        }
    )
    store = InMemoryResearchBriefStoreV2()
    await store.put_brief(first)
    await store.put_brief(second)
    assert await store.get_brief("t", "x", "r") == first
    assert await store.get_brief("t", "x", "second") == second
    assert await store.get_brief("t", "x") is None


def remaining():
    return RemainingBudget(
        iterations=10,
        tool_calls=90,
        input_tokens=1000,
        output_tokens=1000,
        cost_microunits=900,
        timeout_ms=200000,
    )


async def setup_runtime(*, runner=None, max_calls=60):
    module = runtime_module()
    store_type, _ = local_types()
    store = store_type(now=lambda: NOW)
    created = []

    def factory(execution):
        created.append(execution)
        return LangGraphResearchServiceV2(
            policy=ResearchPolicySnapshotV2(
                quality_policy_id="quality-v2", policy_version="v2"
            ),
            budget=execution.budget,
            stage_runner=runner or _Runner(),
            materializer=_Materializer(),
            now=lambda: NOW,
        )

    service = module.RunScopedResearchServiceV2(
        store=store, service_factory=factory, now=lambda: NOW
    )
    key, brief = case()
    cancel = asyncio.Event()

    async def is_cancelled():
        return cancel.is_set()

    binding = module.build_local_research_binding(
        tenant_id="t",
        run_id="r",
        lease_id="lease-r",
        remaining=remaining(),
        now=NOW,
        max_calls=max_calls,
        clock_ms=lambda: int(NOW.timestamp() * 1000),
    )
    await service.register_run(
        key,
        brief,
        binding=binding,
        deadline=NOW + timedelta(seconds=180),
        is_cancelled=is_cancelled,
        wait_cancelled=cancel.wait,
    )
    context = ResearchRuntimeContextV2(
        request_id="req", started_at=NOW, deadline=NOW + timedelta(seconds=180)
    )
    return service, store, key, brief, binding, cancel, context, created


async def test_unique_graph_run_is_reused_for_concurrent_retries_and_terminal_result():
    service, store, key, brief, binding, _, context, created = await setup_runtime()
    first, second = await asyncio.gather(
        service.research(brief, context), service.research(brief, context)
    )
    assert first == second == await service.research(brief, context)
    assert len(created) == 1
    assert created[0].binding is binding
    assert (await store.get(key)).outcome == first
    assert current_budget_execution_binding() is None


async def test_local_binding_clamps_harness_limits_and_preserves_output_reserve():
    _, _, _, _, binding, *_ = await setup_runtime()
    snapshot = await binding.port.snapshot(binding.scope)
    assert snapshot.limits.max_calls == 60
    assert snapshot.limits.output_token_reserve == 250
    assert snapshot.limits.output_time_reserve_ms == 35000
    assert snapshot.limits.deadline_epoch_ms == int(
        (NOW + timedelta(seconds=180)).timestamp() * 1000
    )
    outcomes = await asyncio.gather(
        *(
            binding.port.reserve(
                binding.scope, f"attempt-{i}", BudgetCharge(calls=60), 0
            )
            for i in range(2)
        ),
        return_exceptions=True,
    )
    assert sum(not isinstance(item, Exception) for item in outcomes) == 1


async def test_cancellation_marks_original_lease_terminal_and_late_charge_is_retained():
    started = asyncio.Event()

    class WaitingRunner(_Runner):
        async def run_stage(self, stage, state):
            started.set()
            await asyncio.Event().wait()

    service, store, key, brief, binding, cancel, context, _ = await setup_runtime(
        runner=WaitingRunner()
    )
    reservation = await binding.port.reserve(
        binding.scope, "dispatched", BudgetCharge(calls=1, cost_microunits=10), 0
    )
    await binding.port.mark_dispatched(reservation.reservation_id)
    pending = asyncio.create_task(service.research(brief, context))
    await started.wait()
    cancel.set()
    with pytest.raises(asyncio.CancelledError):
        await pending
    snapshot = await binding.port.settle(
        reservation.reservation_id, BudgetCharge(calls=1, cost_microunits=10), "success"
    )
    assert snapshot.settlement_late and not snapshot.delivery_allowed
    assert snapshot.used.cost_microunits == 10
    assert (await store.get(key)).status == "cancelled"
    with pytest.raises(asyncio.CancelledError):
        await service.research(brief, context)


async def test_forged_run_or_lease_never_constructs_service():
    service, _, _, brief, _, _, context, created = await setup_runtime()
    for field in ("run_id", "budget_lease_id"):
        forged = brief.model_copy(
            update={
                "trusted_context": brief.trusted_context.model_copy(
                    update={field: "foreign"}
                )
            }
        )
        with pytest.raises((KeyError, ValueError)):
            await service.research(forged, context)
    assert not created


async def test_two_registered_runs_receive_distinct_service_budget_and_context():
    service, _, _, brief, first_binding, _, context, created = await setup_runtime()
    module = runtime_module()
    key2, brief2 = case(tenant="t2", user="u2", run="r2")
    binding2 = module.build_local_research_binding(
        tenant_id="t2",
        run_id="r2",
        lease_id="lease-r2",
        remaining=remaining(),
        now=NOW,
        clock_ms=lambda: int(NOW.timestamp() * 1000),
    )
    never = asyncio.Event()

    async def not_cancelled():
        return False

    await service.register_run(
        key2,
        brief2,
        binding=binding2,
        deadline=context.deadline,
        is_cancelled=not_cancelled,
        wait_cancelled=never.wait,
    )
    await asyncio.gather(
        service.research(brief, context), service.research(brief2, context)
    )
    assert len(created) == 2
    assert {entry.budget.lease_id for entry in created} == {"lease-r", "lease-r2"}
    assert first_binding.port is not binding2.port


async def test_output_stage_also_rejects_new_reservations_after_cancellation():
    service, _, _, brief, binding, cancel, context, _ = await setup_runtime()
    cancel.set()
    with pytest.raises(asyncio.CancelledError):
        await service.research(brief, context)
    output_scope = replace(binding.scope, stage="output")
    with pytest.raises(Exception, match="终态"):
        await binding.port.reserve(
            output_scope, "late-output", BudgetCharge(calls=1), 0
        )


async def test_expired_deadline_fails_before_factory_and_retains_timeout_tombstone():
    service, store, key, brief, _, _, _, created = await setup_runtime()
    context = ResearchRuntimeContextV2(
        request_id="expired",
        started_at=NOW - timedelta(seconds=2),
        deadline=NOW - timedelta(seconds=1),
    )
    with pytest.raises(TimeoutError):
        await service.research(brief, context)
    assert not created
    assert (await store.get(key)).status == "timed_out"


async def test_registration_cannot_rebind_same_run_to_other_user_or_extend_deadline():
    service, _, key, brief, binding, _, context, _ = await setup_runtime()
    never = asyncio.Event()

    async def not_cancelled():
        return False

    with pytest.raises(ValueError, match="CONFLICT"):
        await service.register_run(
            key.model_copy(update={"user_id": "other"}),
            brief,
            binding=binding,
            deadline=context.deadline,
            is_cancelled=not_cancelled,
            wait_cancelled=never.wait,
        )


async def test_unknown_cost_preserves_original_reserved_amount():
    _, _, _, _, binding, *_ = await setup_runtime()
    reservation = await binding.port.reserve(
        binding.scope, "unknown", BudgetCharge(calls=1, cost_microunits=30), 0
    )
    await binding.port.mark_dispatched(reservation.reservation_id)
    snapshot = await binding.port.settle(
        reservation.reservation_id, BudgetCharge(unknown=True), "unknown"
    )
    assert snapshot.used.cost_microunits >= 30


async def test_preparation_registers_trusted_user_and_conversation_with_current_binding():
    from efficiency_platform_agent.core.budget_execution import bind_budget_execution
    from efficiency_platform_agent.harness.service import RunPipelineContext

    service, _, _, brief, binding, _, _, _ = await setup_runtime()
    never = asyncio.Event()

    async def not_cancelled():
        return False

    with bind_budget_execution(binding), pytest.raises(ValueError, match="CONFLICT"):
        await service.prepare_research_run(
            brief,
            RunPipelineContext("r", remaining(), not_cancelled, never.wait),
            user_id="wrong-user",
            conversation_id="wrong-conversation",
        )


async def test_delegate_registers_trusted_identity_before_publishing_brief():
    from efficiency_platform_agent.contracts.intent_v2 import IntentDecision
    from efficiency_platform_agent.core.runtime import UsageSnapshot
    from efficiency_platform_agent.harness.intent_v2_delegate import (
        IntentV2RunPreparationDelegate,
    )
    from efficiency_platform_agent.orchestration.intent_v2.pipeline import (
        IntentPipelineVersionsV2,
        PreparedIntentV2,
    )
    from tests.unit.capabilities.research_v2._delivery_support import delivery_facts
    from tests.unit.harness.test_intent_v2_delegate import (
        _builder,
        _InputFactory,
        _IntentPipeline,
        _message,
        _projection,
        _RunPipeline,
        _SubmissionSink,
    )

    brief, *_ = delivery_facts()
    registrations = []
    store = InMemoryResearchBriefStoreV2()

    class Registrar:
        async def prepare_research_run(
            self, frozen_brief, pipeline, *, user_id, conversation_id
        ):
            assert await store.get_brief("t", "x", "r") is None
            registrations.append(
                (frozen_brief, pipeline.run_id, user_id, conversation_id)
            )

    prepared = PreparedIntentV2(
        decision=IntentDecision(outcome="READY"),
        frame=None,
        brief=brief,
        scenario_projection=_projection(),
        usage=UsageSnapshot(),
        provider_calls=1,
        versions=IntentPipelineVersionsV2(
            "catalog-v2", "context-v2", "permission-v2", "lease", 1, "v2"
        ),
        lifecycle_action="START_NEW_RUN",
        run_id="r",
        replacement_run_id=None,
        committed=True,
        replayed=False,
        dispatch_allowed=True,
    )
    delegate = IntentV2RunPreparationDelegate(
        intent_pipeline=_IntentPipeline(prepared),
        input_factory=_InputFactory(),
        submission_builder=_builder(),
        submissions=_SubmissionSink(),
        source_registry=object(),
        tool_runtime=object(),
        research_service=Registrar(),
        intent_state_store=object(),
        research_state_store=store,
    )
    await delegate.prepare_v2(
        _RunPipeline(), "t", "conversation-1", _message(), object()
    )
    assert registrations == [(brief, "r", "user-1", "conversation-1")]


async def test_local_brief_adapter_uses_retained_facts_and_expires_with_them():
    service, _, _, brief, _, _, context, _ = await setup_runtime()
    await service.put_brief(brief)
    assert await service.get_brief("t", "x", "r") == brief
    assert await service.get_brief("other", "x", "r") is None
    await service.research(brief, context)
    assert await service.expire(NOW + timedelta(minutes=31)) == 1
    assert await service.get_brief("t", "x", "r") is None


async def test_cancel_does_not_wait_for_cancellation_resistant_provider():
    started, release = asyncio.Event(), asyncio.Event()

    class SlowCancellationRunner(_Runner):
        async def run_stage(self, stage, state):
            if stage == "validate":
                started.set()
                try:
                    await release.wait()
                except asyncio.CancelledError:
                    await release.wait()
            return await super().run_stage(stage, state)

    service, store, key, brief, _, cancel, context, _ = await setup_runtime(
        runner=SlowCancellationRunner()
    )
    pending = asyncio.create_task(service.research(brief, context))
    await started.wait()
    cancel.set()
    try:
        done, _ = await asyncio.wait((pending,), timeout=0.1)
        assert pending in done, "取消交付不能等待不合作的外部调用"
        assert pending.cancelled()
        assert (await store.get(key)).status == "cancelled"
        assert await store.expire(NOW + timedelta(minutes=31)) == 0
    finally:
        release.set()
        await asyncio.gather(pending, return_exceptions=True)
