import json
import time
from dataclasses import replace

import pytest
from pydantic import ValidationError

from efficiency_platform_agent.capabilities.model.memory_derive_handler import (
    MemoryDeriveHandler,
)
from efficiency_platform_agent.contracts.memory_derive_template import (
    MemoryDeriveTemplate,
)
from efficiency_platform_agent.core.context_ports import (
    ContextMetadata,
    ContextOperation,
)
from efficiency_platform_agent.core.execution_control import execution_scope
from efficiency_platform_agent.core.memory_execution import MemoryExecutionGrant
from efficiency_platform_agent.core.run_context_binding import bind_run_context
from efficiency_platform_agent.harness.memory_derive_coordinator import (
    MemoryDeriveCoordinator,
)
from efficiency_platform_agent.harness.memory_derive_runtime import (
    LiveOriginalDeriveFrames,
)
from tests.api.test_memory_derive_contract import fixture
from tests.unit.context.test_memory_runtime_join import Store, Validator


class Ledger:
    active = True
    binds = 0

    def active_budget_id(self):
        return "original-budget" if self.active else None

    def snapshot(self, budget_id):
        return {
            "budget_id": budget_id,
            "remaining_calls": 1,
            "remaining_cost_microunits": 1000,
            "stopped": None,
            "deadline_epoch_ms": int((time.time() + 100) * 1000),
            "prices": [
                {
                    "provider": "deepseek",
                    "model": "deepseek-chat",
                    "pricing_version": "fixture",
                    "pricing_source": "synthetic",
                    "input_microunits_per_million": 1,
                    "output_microunits_per_million": 1,
                    "max_cost_microunits_per_attempt": 1,
                    "max_output_tokens": 1000,
                    "max_input_tokens": 100000,
                }
            ],
        }

    def bind_execution(self, *args, **kwargs):
        self.binds += 1
        return int((time.time() + 100) * 1000)

    def check_execution(self, *_):
        return None


def template_data(request):
    data = request.model_dump(mode="json")
    return {
        "contract_version": "memory-derive-template/1",
        "plan_id": data["plan_id"],
        "operation_id": data["plan_id"],
        "execution_id": data["execution_scope"]["execution_id"],
        "task_id": data["execution_scope"]["task_id"],
        "deadline_epoch_seconds": data["deadline_epoch_seconds"],
        "scope": data["execution_scope"],
        "sources": data["sources"],
        "events": data["events"],
        "required_entries": data["required_entries"],
        "session_revision": data["session_revision"],
        "source_revision": data["source_revision"],
        "authority_ref": data["plan_id"],
    }


def test_template_requires_body_hash_epoch_and_exact_original_scope():
    request, *_ = fixture()
    data = template_data(request)
    assert MemoryDeriveTemplate.model_validate_json(json.dumps(data)).plan_id == "plan"
    for field in ("body", "epoch", "task"):
        changed = json.loads(json.dumps(data))
        if field == "body":
            changed["sources"][0]["body"] += "changed"
        elif field == "epoch":
            del changed["sources"][0]["metadata"]["source_ref"]["source_epoch"]
        else:
            changed["task_id"] = "other"
        with pytest.raises(ValidationError):
            MemoryDeriveTemplate.model_validate_json(json.dumps(changed))


@pytest.mark.parametrize("budget", [True, False])
async def test_coordinator_registers_only_live_high_pressure_original_node_and_waits_for_finish(
    budget,
):
    request, original, gateway, _ = fixture()
    frame, control = original.bound_frame, original.control
    data = template_data(request)
    data["scope"]["purpose"] = "assistant_response"
    memory = replace(
        frame.binding.memory_context,
        policy=replace(frame.binding.memory_context.policy, max_paid_operations=1),
        derive_template_json=json.dumps(data),
        execution_grants=(
            MemoryExecutionGrant("subtask", "operations", "assistant_response"),
        ),
    )
    binding = replace(frame.binding, memory_context=memory)
    scope = replace(frame.operation.scope, purpose="assistant_response")
    baseline = replace(
        frame.baseline,
        window_policy=replace(frame.baseline.window_policy, scope=scope),
        view=replace(
            frame.baseline.view,
            pieces=tuple(replace(p, scope=scope) for p in frame.baseline.view.pieces),
        ),
        limits=replace(
            frame.baseline.limits,
            node_input_limit=frame.baseline.view.measurement.total_upper_bound,
        ),
    )
    store = Store(replace(frame, binding=binding))
    frames = LiveOriginalDeriveFrames(store, validator=Validator())
    ledger = Ledger()
    ledger.active = budget
    notifications = []
    coordinator = None

    async def notify(runtime_id, payload):
        notifications.append((runtime_id, payload))
        pending = await coordinator.pending("tenant", "execution")
        assert pending is not None
        with pytest.raises(ValueError, match="BINDING"):
            await coordinator.finish(
                "tenant", "execution", pending.plan_id, "0" * 64, "COMMITTED"
            )
        await coordinator.finish(
            "tenant",
            "execution",
            pending.plan_id,
            pending.plan_fingerprint,
            "COMMITTED",
        )

    metadata = ContextMetadata(
        "memory.derive",
        "derive/1",
        "derive-prompt/2",
        "none/1",
        "derive-schema/2",
        1,
        baseline.capacity,
        replace(baseline.limits, output_reserve_tokens=500),
        baseline.view.request.options,
    )
    handler = MemoryDeriveHandler(frames, lambda *_: gateway, enabled=True)
    coordinator = MemoryDeriveCoordinator(
        frames, handler, ledger, metadata, store, notify
    )
    with (
        execution_scope(control),
        bind_run_context(binding),
        coordinator.for_run(store.record),
    ):
        low_pressure = replace(baseline, limits=frame.baseline.limits)
        assert (
            frames.observe_baseline(
                low_pressure,
                ContextOperation(
                    "original-op", 1, binding.deadline_epoch_seconds, False
                ),
            )
            is None
        )
        handle = frames.observe_baseline(
            baseline,
            ContextOperation("original-op", 1, binding.deadline_epoch_seconds, False),
        )
        if budget:
            assert handle is not None
            pending = await coordinator.pending("tenant", "execution")
            assert pending is not None and pending.runtime_id == "runtime"
            assert pending.budget_id == "original-budget"
            assert pending.assets.prompt_ref == "derive-prompt/2"
            await coordinator.wait_for_derivation(
                scope,
                ContextOperation(
                    "original-op", 1, binding.deadline_epoch_seconds, False
                ),
            )
            assert notifications[0][1] == {
                "plan_id": "plan",
                "baseline_ref": pending.baseline_ref,
            }
            handle.close()
        else:
            assert handle is None and ledger.binds == 0 and not notifications
    assert await coordinator.pending("tenant", "execution") is None
    assert control.stopped is None and gateway.calls == 0
