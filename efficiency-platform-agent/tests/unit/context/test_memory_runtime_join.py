import asyncio
import hashlib
import json
from dataclasses import replace

import pytest

from efficiency_platform_agent.core.execution_control import (
    current_run_control,
    execution_scope,
)
from efficiency_platform_agent.core.memory_execution import MemoryExecutionRecord
from efficiency_platform_agent.core.run import ProviderMessage
from efficiency_platform_agent.core.run_context_binding import (
    bind_run_context,
    current_run_context,
)
from efficiency_platform_agent.harness.memory_derive_runtime import (
    LiveOriginalDeriveFrames,
)
from efficiency_platform_agent.harness.memory_summary_context import (
    OriginalMessageProjection,
    project_original_messages,
)
from tests.api.test_memory_derive_contract import fixture


class Store:
    def __init__(self, frame):
        self.record = MemoryExecutionRecord(
            frame.binding.memory_context,
            frame.runtime_id,
            frame.runtime_kind,
            "a" * 64,
            frame.binding.deadline_epoch_seconds,
            "ACTIVE",
            1,
            1,
            2,
            3,
        )

    async def get(self, *_):
        return self.record


class Validator:
    async def validate(self, *_):
        return None


async def test_live_original_frame_reuses_control_and_rejects_changed_plan_and_exit():
    from efficiency_platform_agent.capabilities.model.memory_derive_handler import (
        MemoryDeriveHandler,
    )
    from efficiency_platform_agent.core.context_dispatch import (
        current_model_stage,
        model_stage,
    )
    from efficiency_platform_agent.core.context_ports import ContextOperation

    request, original, gateway, _ = fixture()
    frame, control = original.bound_frame, original.control

    class OriginalNodeValidator:
        async def validate(self, *_):
            assert current_model_stage().node_id == frame.operation.scope.subtask_id

    frames = LiveOriginalDeriveFrames(Store(frame), validator=OriginalNodeValidator())
    with execution_scope(control), bind_run_context(frame.binding):
        handle = frames.register_scope(
            frame, control, asyncio.current_task(), frozen_request=request
        )
    async with frames.bind(request) as bound:
        assert bound.baseline is frame.baseline
        assert current_run_control() is control
        assert current_run_context() is frame.binding
        with model_stage("derive", b"", node_id="memory.derive"):
            await bound.source_checker.check(request, bound)
            await frames.validate(
                frame.operation.scope,
                frame.binding.memory_context.packet,
                frame.baseline.window_policy.authorized_dependencies,
                ContextOperation(
                    request.operation_id, 1, request.deadline_epoch_seconds, False
                ),
            )
            assert current_model_stage().node_id == "memory.derive"
    assert control.stopped is None
    result = await MemoryDeriveHandler(
        frames, lambda *_: gateway, enabled=True
    ).execute("tenant", request)
    assert result["benefit"]["status"] == "BENEFICIAL"
    assert gateway.calls == 1 and control.calls == 0
    changed = request.model_copy(update={"runtime_id": "other"})
    changed = changed.model_copy(update={"plan_fingerprint": changed.fingerprint()})
    with pytest.raises(ValueError, match="ORIGINAL_FRAME|BINDING"):
        async with frames.bind(changed):
            pass
    handle.close()
    with pytest.raises(ValueError, match="ORIGINAL_FRAME"):
        async with frames.bind(request):
            pass


async def test_live_frame_rechecks_execution_and_stop_without_new_control():
    request, original, _, _ = fixture()
    frame, control = original.bound_frame, original.control
    store = Store(frame)
    frames = LiveOriginalDeriveFrames(store, validator=Validator())
    with execution_scope(control), bind_run_context(frame.binding):
        handle = frames.register_scope(
            frame, control, asyncio.current_task(), frozen_request=request
        )
    store.record = replace(store.record, state="REVOKED")
    with pytest.raises(ValueError, match="ORIGINAL_EXECUTION"):
        async with frames.bind(request):
            pass
    store.record = replace(store.record, state="ACTIVE")
    control.stop()
    with pytest.raises(Exception, match="任务已停止"):
        async with frames.bind(request):
            pass
    handle.close()


async def test_live_frame_accepts_only_current_claimed_slot_of_original_derive_stage(
    tmp_path,
):
    from efficiency_platform_agent.core.context_dispatch import model_stage
    from efficiency_platform_agent.core.context_ports import ContextOperation
    from efficiency_platform_agent.persistence.context_stage import (
        MySqlContextStageStore,
    )
    from tests.unit.persistence.test_context_stage import LocalEngine

    request, original, _, _ = fixture()
    frame, control = original.bound_frame, original.control
    engine = LocalEngine(tmp_path / "stage.sqlite")
    stages = MySqlContextStageStore(engine, b"k" * 32)
    frames = LiveOriginalDeriveFrames(
        Store(frame), validator=Validator(), stage_authority=stages
    )
    try:
        with execution_scope(control), bind_run_context(frame.binding):
            handle = frames.register_scope(
                frame, control, asyncio.current_task(), frozen_request=request
            )
        request = type(request).model_validate_json(request.model_dump_json())
        async with frames.bind(request):
            with model_stage(
                request.operation_id, b"synthetic", node_id="memory.derive"
            ):
                slot = await stages.claim(
                    frame.operation.scope,
                    request.operation_id,
                    "semantic",
                    request.deadline_epoch_seconds,
                )
                operation = ContextOperation(
                    slot.operation_id, 1, request.deadline_epoch_seconds, False
                )
                assert operation.operation_id != frame.operation.operation_id
                await frames.validate(
                    frame.operation.scope,
                    frame.binding.memory_context.packet,
                    frame.baseline.window_policy.authorized_dependencies,
                    operation,
                )
                binding_json = await frames.derive_manifest_binding(
                    frame.operation.scope, operation
                )
                refs = json.loads(binding_json)
                assert refs["operation_id"] == request.operation_id
                assert refs["plan_fingerprint"] == request.plan_fingerprint
                assert refs["logical_stage_id"] == request.operation_id
                assert refs["physical_operation_id"] == operation.operation_id
                assert not {"sources", "events", "required_entries"}.intersection(refs)
                from efficiency_platform_agent.context.controller import (
                    ContextController,
                )
                from efficiency_platform_agent.context.policy import ContextPolicy
                from efficiency_platform_agent.contracts.context_control import (
                    ContextManifestModel,
                )
                from efficiency_platform_agent.core.context_ports import (
                    ContextMetadata,
                    OperationReceipt,
                )

                class ManifestStore:
                    async def save_manifest_once(self, manifest, operation):
                        self.manifest = manifest
                        return manifest

                    async def get_operation_receipt(self, *_):
                        return OperationReceipt(
                            self.manifest.canonical_request_hmac,
                            "NOT_SENT",
                            operation.deadline_epoch_seconds,
                        )

                    async def mark_sending(self, *_):
                        return True

                manifests = ManifestStore()
                controller = ContextController(
                    frame.counter, manifests, b"k" * 32, validator=frames
                )
                provider_request = frame.baseline.view.request
                metadata = ContextMetadata(
                    "memory.derive",
                    "derive/1",
                    frame.assets.prompt_ref,
                    "none/1",
                    frame.assets.schema_ref,
                    1,
                    frame.baseline.capacity,
                    frame.baseline.limits,
                    provider_request.options,
                )
                policy = ContextPolicy(
                    "memory.derive",
                    "derive/1",
                    frame.operation.scope,
                    frame.baseline.window_policy.authorized_dependencies,
                )
                prepared = await controller.prepare(
                    provider_request,
                    frame.operation.scope,
                    policy,
                    frame.baseline.view.pieces,
                    metadata.capacity,
                    metadata.limits,
                    metadata,
                    frame.binding.memory_context.packet,
                    operation=operation,
                )
                assert prepared.manifest.derive_binding_json == binding_json
                assert (
                    ContextManifestModel.model_validate_json(
                        ContextManifestModel.from_core(
                            prepared.manifest
                        ).model_dump_json()
                    ).to_core()
                    == prepared.manifest
                )
                ordinary = replace(
                    prepared.manifest, node_id="direct", derive_binding_json=None
                )
                assert "derive_binding_json" not in ContextManifestModel.from_core(
                    ordinary
                ).model_dump(mode="json")
                forged = replace(
                    prepared,
                    manifest=replace(
                        prepared.manifest,
                        derive_binding_json=binding_json.replace(
                            '"budget_id":"original-budget"', '"budget_id":"forged"'
                        ),
                    ),
                )
                with pytest.raises(ValueError, match="REQUEST_CHANGED"):
                    await controller.finalize(
                        forged,
                        frame.operation.scope,
                        metadata.capacity,
                        metadata.limits,
                        metadata,
                        operation=operation,
                        packet=frame.binding.memory_context.packet,
                    )
                await controller.finalize(
                    prepared,
                    frame.operation.scope,
                    metadata.capacity,
                    metadata.limits,
                    metadata,
                    operation=operation,
                    packet=frame.binding.memory_context.packet,
                )
                with pytest.raises(ValueError, match="BINDING"):
                    await frames.validate(
                        frame.operation.scope,
                        frame.binding.memory_context.packet,
                        frame.baseline.window_policy.authorized_dependencies,
                        replace(operation, operation_id="stage-forged"),
                    )
                other_scope = replace(frame.operation.scope, execution_id="other")
                other_slot = await stages.claim(
                    other_scope,
                    request.operation_id,
                    "semantic",
                    request.deadline_epoch_seconds,
                )
                with pytest.raises(ValueError, match="BINDING"):
                    await frames.validate(
                        frame.operation.scope,
                        frame.binding.memory_context.packet,
                        frame.baseline.window_policy.authorized_dependencies,
                        replace(operation, operation_id=other_slot.operation_id),
                    )
                assert not await stages.is_claimed_operation(
                    other_scope,
                    request.operation_id,
                    operation.operation_id,
                    operation.deadline_epoch_seconds,
                )
                assert await stages.transition(
                    frame.operation.scope,
                    request.operation_id,
                    slot.slot,
                    "CLAIMED",
                    "RETURNED",
                )
                with pytest.raises(ValueError, match="BINDING"):
                    await frames.validate(
                        frame.operation.scope,
                        frame.binding.memory_context.packet,
                        frame.baseline.window_policy.authorized_dependencies,
                        operation,
                    )
        handle.close()
    finally:
        engine.engine.dispose()


async def test_parent_authorized_scope_does_not_survive_inherited_child_context():
    from efficiency_platform_agent.core.context_ports import ContextOperation

    request, original, _, _ = fixture()
    frame, control = original.bound_frame, original.control
    frames = LiveOriginalDeriveFrames(Store(frame), validator=Validator())
    ready = asyncio.Event()

    async def delayed_observer():
        await ready.wait()
        with pytest.raises(ValueError, match="ORIGINAL_FRAME"):
            frames.observe_baseline(
                frame.baseline,
                ContextOperation(
                    "original-op", 1, frame.binding.deadline_epoch_seconds, False
                ),
            )

    with execution_scope(control), bind_run_context(frame.binding):
        with frames.authorized_scope(lambda *_: (frame, request)):
            child = asyncio.create_task(delayed_observer())
        ready.set()
        await child


def test_original_projection_matches_every_ordered_message_and_protects_current():
    request, original, _, _ = fixture()
    scope = request.execution_scope.to_core()
    dependencies = original.bound_frame.baseline.window_policy.authorized_dependencies
    messages = (
        ProviderMessage("system", "规则"),
        ProviderMessage("user", "重复历史"),
        ProviderMessage("assistant", "重复历史"),
        ProviderMessage("user", "当前"),
    )
    projections = tuple(
        OriginalMessageProjection(
            f"message-{index}",
            message.role,
            hashlib.sha256(message.content.encode()).hexdigest(),
            dependencies,
        )
        for index, message in enumerate(messages[1:-1], start=1)
    )
    provider_request = replace(
        original.bound_frame.baseline.view.request, messages=messages
    )
    pieces = project_original_messages(provider_request, scope, projections)
    assert pieces is not None
    assert pieces[0].is_required and pieces[-1].is_required
    assert pieces[1].covered_message_ids == ("message-1",)
    assert pieces[2].covered_message_ids == ("message-2",)
    assert project_original_messages(provider_request, scope, projections[::-1]) is None
    assert project_original_messages(provider_request, scope, projections[:-1]) is None
    assert (
        project_original_messages(
            provider_request,
            scope,
            (projections[0], replace(projections[1], group_completed=False)),
        )
        is None
    )


@pytest.mark.parametrize("status", ["COMMITTED", "STALE"])
async def test_controller_uses_committed_summary_and_holds_real_baseline_until_scope_exit(
    status,
):
    from efficiency_platform_agent.context.controller import ContextController
    from efficiency_platform_agent.core.context_ports import (
        ContextMetadata,
        ContextOperation,
    )
    from efficiency_platform_agent.core.memory import MemoryContextPacket
    from tests.unit.memory.test_summary_selection import fixture as summary_fixture

    baseline, counter, policy, record, _ = summary_fixture()
    policy = replace(policy, max_history_messages=0)
    record = replace(record, status=status)
    packet = MemoryContextPacket(
        "packet",
        1,
        policy.scope.conversation,
        policy.scope.task_id,
        policy.scope.execution_id,
        "memory/2",
        1,
        0,
        100,
        1,
        2,
        3,
        "semantic",
        "parent",
        safety_dependencies=policy.authorized_dependencies,
    )
    metadata = ContextMetadata(
        policy.node_id,
        policy.version,
        "prompt",
        "tools",
        "schema",
        1,
        baseline.capacity,
        baseline.limits,
        baseline.view.request.options,
    )

    class ManifestStore:
        async def save_manifest_once(self, manifest, _):
            return manifest

    class Reader:
        async def current(self, scope, original_packet):
            assert scope == policy.scope and original_packet is packet
            return (record,)

    class Handle:
        closed = False

        def close(self):
            self.closed = True

    class Observer:
        handle = Handle()
        observed = None

        def observe_baseline(self, actual, operation):
            assert actual.view.messages == actual.view.request.messages
            assert (
                tuple(m for p in actual.view.pieces for m in p.messages)
                == actual.view.messages
            )
            self.observed = actual
            return self.handle

    observer = Observer()
    controller = ContextController(
        counter,
        ManifestStore(),
        b"k" * 32,
        validator=Validator(),
        clock=lambda: 10,
        summary_context_port=Reader(),
        derive_runtime=observer,
    )
    with controller.baseline_scope():
        result = await controller.prepare(
            baseline.view.request,
            policy.scope,
            policy,
            baseline.view.pieces,
            baseline.capacity,
            baseline.limits,
            metadata,
            packet,
            operation=ContextOperation("op", 1, 100, False),
        )
        assert observer.observed is not None and not observer.handle.closed
        assert result.manifest.prediction_basis.endswith(":UNKNOWN")
        if status == "COMMITTED":
            assert result.manifest.summary_adoption_status == "ADOPTED"
            assert result.manifest.summary_cas_status == "COMMITTED"
            assert record.summary_dependency in result.manifest.selected_sources
            assert (
                result.manifest.summary_before_tokens
                > result.manifest.summary_after_tokens
            )
        else:
            assert result.manifest.summary_adoption_status == "not-applied"
            assert record.summary_dependency not in result.manifest.selected_sources
    assert observer.handle.closed
