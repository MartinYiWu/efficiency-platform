from dataclasses import FrozenInstanceError

import pytest
from sqlalchemy.exc import OperationalError

from efficiency_platform_agent.core.context_ports import ContextOperation
from tests.unit.persistence.test_context_manifest import setup as setup  # noqa: PLC0414


def test_operation_is_immutable_and_has_absolute_deadline():
    op = ContextOperation("op", 1, 100, True)
    assert op.deadline_epoch_seconds == 100
    with pytest.raises(FrozenInstanceError):
        op.attempt = 2


@pytest.mark.parametrize(
    "attempt,deadline", [(True, 100), (-1, 100), (0, 100), (4, 100), (1, True), (1, -1)]
)
def test_operation_rejects_invalid_counters(attempt, deadline):
    with pytest.raises(ValueError):
        ContextOperation("op", attempt, deadline, True)


from dataclasses import replace


async def test_finalize_recounts_and_blocks_second_dispatch(setup):
    s = setup
    kwargs = {
        "scope": s["scope"],
        "capacity": s["capacity"],
        "limits": s["limits"],
        "metadata": s["metadata"],
        "operation": s["operation"],
    }
    assert await s["controller"].finalize(s["prepared"], **kwargs)
    with pytest.raises(ValueError, match="OPERATION_BLOCKED"):
        await s["controller"].finalize(s["prepared"], **kwargs)


async def test_finalize_detects_full_schema_or_count_change(setup):
    s = setup
    s["counter"].extra = 1000
    with pytest.raises(ValueError, match="COUNT_DRIFT"):
        await s["controller"].finalize(
            s["prepared"],
            s["scope"],
            s["capacity"],
            s["limits"],
            s["metadata"],
            operation=s["operation"],
        )
    assert (
        await s["store"].get_operation_receipt(s["scope"], "op")
    ).status == "NOT_SENT"


async def test_finalize_rejects_changed_deadline_and_request(setup):
    s = setup
    for prepared, op in [
        (s["prepared"], replace(s["operation"], deadline_epoch_seconds=101)),
        (
            replace(s["prepared"], request=replace(s["request"], timeout_ms=900)),
            s["operation"],
        ),
    ]:
        with pytest.raises(ValueError, match="REQUEST_CHANGED"):
            await s["controller"].finalize(
                prepared,
                s["scope"],
                s["capacity"],
                s["limits"],
                s["metadata"],
                operation=op,
            )


async def test_prepare_rejects_missing_packet_without_explicit_memory_disable(setup):
    s = setup
    with pytest.raises(ValueError, match="PACKET_REQUIRED"):
        await s["prepare"](operation=replace(s["operation"], memory_disabled=False))


async def test_prepare_rejects_mismatched_binding(setup):
    s = setup
    with pytest.raises(ValueError, match="BINDING_MISMATCH"):
        await s["prepare"](metadata=replace(s["metadata"], node_id="other"))


async def test_prepare_persistence_failure_propagates(setup):
    s = setup
    s["engine"].engine.dispose()
    with s["engine"].engine.begin() as conn:
        from sqlalchemy import text

        conn.execute(text("DROP TABLE agent_context_manifest"))
    with pytest.raises(OperationalError):
        await s["prepare"]()
    assert (
        await s["store"].get_operation_receipt(s["scope"], "op")
    ).status == "NOT_SENT"


async def test_finalize_rejects_manifest_model_metadata_tampering(setup):
    s = setup
    forged = replace(
        s["prepared"], manifest=replace(s["prepared"].manifest, model_version="other")
    )
    with pytest.raises(ValueError, match="BINDING_MISMATCH"):
        await s["controller"].finalize(
            forged,
            s["scope"],
            s["capacity"],
            s["limits"],
            s["metadata"],
            operation=s["operation"],
        )


@pytest.mark.parametrize("status", ["UNKNOWN", "SUCCEEDED"])
async def test_finalize_blocks_terminal_receipt(setup, status):
    s = setup
    assert await s["store"].mark_sending(s["prepared"].manifest, s["operation"])
    assert await s["store"].record_receipt(s["prepared"].manifest, status)
    with pytest.raises(ValueError, match="OPERATION_BLOCKED"):
        await s["controller"].finalize(
            s["prepared"],
            s["scope"],
            s["capacity"],
            s["limits"],
            s["metadata"],
            operation=s["operation"],
        )


async def test_packet_requires_live_validator(setup):
    from efficiency_platform_agent.core.memory import MemoryContextPacket

    s = setup
    packet = MemoryContextPacket(
        "packet",
        0,
        s["scope"].conversation,
        "task",
        "exec",
        "1",
        0,
        0,
        100,
        0,
        0,
        0,
        "semantic",
        "authority",
    )
    with pytest.raises(ValueError, match="LIVE_VALIDATOR_REQUIRED"):
        await s["prepare"](
            packet=packet, operation=replace(s["operation"], memory_disabled=False)
        )


async def test_expired_operation_never_marks_sending(setup):
    s = setup
    with pytest.raises(ValueError, match="DEADLINE_EXCEEDED"):
        await s["prepare"](operation=replace(s["operation"], deadline_epoch_seconds=10))
    assert (
        await s["store"].get_operation_receipt(s["scope"], "op")
    ).status == "NOT_SENT"


async def test_live_authority_revoked_before_finalize_blocks_sending(setup):
    from efficiency_platform_agent.context.controller import ContextController
    from efficiency_platform_agent.core.memory import MemoryContextPacket

    s = setup

    class Validator:
        revoked = False

        async def validate(self, scope, packet, dependencies, operation):
            if self.revoked:
                raise ValueError("SOURCE_REVOKED")

    validator = Validator()
    controller = ContextController(
        s["counter"], s["store"], b"k" * 32, validator=validator, clock=lambda: 10
    )
    packet = MemoryContextPacket(
        "packet",
        0,
        s["scope"].conversation,
        "task",
        "exec",
        "1",
        0,
        0,
        100,
        0,
        0,
        0,
        "semantic",
        "authority",
    )
    op = replace(s["operation"], operation_id="packet-operation", memory_disabled=False)
    prepared = await controller.prepare(
        s["request"],
        s["scope"],
        s["policy"],
        s["pieces"],
        s["capacity"],
        s["limits"],
        s["metadata"],
        packet,
        operation=op,
    )
    validator.revoked = True
    with pytest.raises(ValueError, match="SOURCE_REVOKED"):
        await controller.finalize(
            prepared,
            s["scope"],
            s["capacity"],
            s["limits"],
            s["metadata"],
            packet=packet,
            operation=op,
        )
    assert (
        await s["store"].get_operation_receipt(s["scope"], op.operation_id)
    ).status == "NOT_SENT"


async def test_deadline_rechecked_after_receipt_io(setup):
    from efficiency_platform_agent.context.controller import ContextController

    s = setup
    now = [10]
    original = s["store"].get_operation_receipt

    async def delayed_read(scope, operation_id):
        result = await original(scope, operation_id)
        now[0] = 100
        return result

    s["store"].get_operation_receipt = delayed_read
    controller = ContextController(
        s["counter"], s["store"], b"k" * 32, clock=lambda: now[0]
    )
    with pytest.raises(ValueError, match="DEADLINE_EXCEEDED"):
        await controller.finalize(
            s["prepared"],
            s["scope"],
            s["capacity"],
            s["limits"],
            s["metadata"],
            operation=s["operation"],
        )
    assert (await original(s["scope"], "op")).status == "NOT_SENT"


async def test_finalize_packet_policy_cannot_change_in_place(setup):
    from efficiency_platform_agent.context.controller import ContextController
    from efficiency_platform_agent.core.memory import MemoryContextPacket

    s = setup

    class Validator:
        async def validate(self, *args):
            return None

    controller = ContextController(
        s["counter"], s["store"], b"k" * 32, validator=Validator(), clock=lambda: 10
    )
    packet = MemoryContextPacket(
        "packet",
        0,
        s["scope"].conversation,
        "task",
        "exec",
        "1",
        0,
        0,
        100,
        0,
        0,
        0,
        "semantic",
        "authority",
    )
    op = replace(s["operation"], operation_id="packet-policy", memory_disabled=False)
    prepared = await controller.prepare(
        s["request"],
        s["scope"],
        s["policy"],
        s["pieces"],
        s["capacity"],
        s["limits"],
        s["metadata"],
        packet,
        operation=op,
    )
    with pytest.raises(ValueError, match="POLICY_MISMATCH"):
        await controller.finalize(
            prepared,
            s["scope"],
            s["capacity"],
            s["limits"],
            s["metadata"],
            packet=replace(packet, policy_version="other"),
            operation=op,
        )
