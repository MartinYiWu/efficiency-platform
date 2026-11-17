"""checkpoint位置AAD、缺key拒绝与官方primitive旁路的真实内存Saver红绿。"""

import base64
from contextlib import asynccontextmanager
from dataclasses import replace
from types import SimpleNamespace

import pytest
from langgraph.checkpoint.base import empty_checkpoint
from langgraph.checkpoint.memory import InMemorySaver

from efficiency_platform_agent.core.budget import BudgetCharge, BudgetState
from efficiency_platform_agent.core.enums import RunStatus
from efficiency_platform_agent.core.run import JsonObject
from tests.integration.memory.test_context_refresh_resume import synthetic_record


def test_checkpoint_cipher_binds_scope_thread_namespace_and_exact_coordinate():
    from efficiency_platform_agent.core.memory_thread import CheckpointLocation
    from efficiency_platform_agent.orchestration.fenced_checkpoint import (
        CheckpointPayloadSerializer,
    )
    from efficiency_platform_agent.persistence.memory_checkpoint_cipher import (
        AesGcmCheckpointBodyCipher,
    )

    scope, _ = synthetic_record()
    location = CheckpointLocation(scope, "root", "ns", ("checkpoint", "id-1"))
    cipher = AesGcmCheckpointBodyCipher(b"k" * 32, "synthetic-v1")
    serializer = CheckpointPayloadSerializer(cipher)
    value = {"private": "SYNTHETIC_CHECKPOINT_MARKER"}
    envelope = serializer.encode(location, value)
    assert "SYNTHETIC_CHECKPOINT_MARKER" not in str(envelope)
    assert serializer.decode(location, envelope) == value
    for wrong in (
        replace(location, thread_id="other"),
        replace(location, checkpoint_ns="other"),
        replace(location, coordinate=("checkpoint", "other")),
        replace(location, scope=replace(scope, execution_id="other")),
        replace(
            location,
            scope=replace(
                scope, conversation=replace(scope.conversation, user_id="other")
            ),
        ),
    ):
        with pytest.raises(ValueError, match="CHECKPOINT_BODY_UNAVAILABLE"):
            serializer.decode(wrong, envelope)
    with pytest.raises(ValueError, match="CHECKPOINT_BODY_UNAVAILABLE"):
        CheckpointPayloadSerializer(
            AesGcmCheckpointBodyCipher(b"z" * 32, "synthetic-v2")
        ).decode(location, envelope)
    with pytest.raises(ValueError, match="CHECKPOINT_ENCRYPTION_KEY_REQUIRED"):
        AesGcmCheckpointBodyCipher(b"short", "v1")
    with pytest.raises(ValueError, match="CHECKPOINT_BODY_UNAVAILABLE"):
        serializer.decode(location, {"plaintext": "legacy"})


@pytest.mark.asyncio
async def test_fenced_saver_encrypts_scalars_metadata_and_writes_before_raw_saver():
    from efficiency_platform_agent.core.memory_thread import CheckpointLocation
    from efficiency_platform_agent.orchestration.fenced_checkpoint import (
        CheckpointPayloadSerializer,
        FencedCheckpointSaver,
    )
    from efficiency_platform_agent.persistence.memory_checkpoint_cipher import (
        AesGcmCheckpointBodyCipher,
    )

    scope, _ = synthetic_record()

    class Registry:
        requires_encrypted_checkpoints = True

        @asynccontextmanager
        async def guard(self, thread_id, backend, namespace, **kwargs):
            yield CheckpointLocation(scope, thread_id, namespace, ())

    registry, raw = Registry(), InMemorySaver()
    codec = CheckpointPayloadSerializer(
        AesGcmCheckpointBodyCipher(b"k" * 32, "synthetic-v1")
    )
    with pytest.raises(ValueError, match="CHECKPOINT_ENCRYPTION_REQUIRED"):
        FencedCheckpointSaver(raw, registry, "official")
    saver = FencedCheckpointSaver(raw, registry, "official", serializer=codec)
    checkpoint = empty_checkpoint()
    marker = "SYNTHETIC_CHECKPOINT_MARKER"
    checkpoint["channel_values"] = {"scalar": marker}
    checkpoint["channel_versions"] = {"scalar": "1"}
    config = await saver.aput(
        {"configurable": {"thread_id": "root", "checkpoint_ns": "ns"}},
        checkpoint,
        {"private": marker},
        {"scalar": "1"},
    )
    await saver.aput_writes(config, [("pending", marker)], "task")
    stored = await raw.aget_tuple(config)
    assert marker not in str(stored)
    restored = await saver.aget_tuple(config)
    assert restored.checkpoint["channel_values"]["scalar"] == marker
    assert restored.metadata["private"] == marker
    assert restored.pending_writes == [("task", "pending", marker)]
    copied = stored.checkpoint | {"id": "different-checkpoint"}
    foreign = await raw.aput(config, copied, stored.metadata, {"scalar": "1"})
    with pytest.raises(ValueError, match="CHECKPOINT_BODY_UNAVAILABLE"):
        await saver.aget_tuple(foreign)


async def test_owned_store_encrypts_body_and_rejects_namespace_ciphertext_swap():
    from efficiency_platform_agent.core.memory_thread import CheckpointLocation
    from efficiency_platform_agent.orchestration.checkpoint import (
        InMemoryCheckpointStore,
    )
    from efficiency_platform_agent.orchestration.fenced_checkpoint import (
        CheckpointPayloadSerializer,
        FencedCheckpointStore,
    )
    from efficiency_platform_agent.persistence.memory_checkpoint_cipher import (
        AesGcmCheckpointBodyCipher,
    )

    scope, _ = synthetic_record()

    class Registry:
        requires_encrypted_checkpoints = True

        @asynccontextmanager
        async def guard(self, thread_id, backend, namespace, **kwargs):
            yield CheckpointLocation(scope, thread_id, namespace, ())

    raw = InMemoryCheckpointStore()
    store = FencedCheckpointStore(
        raw,
        Registry(),
        serializer=CheckpointPayloadSerializer(
            AesGcmCheckpointBodyCipher(b"k" * 32, "synthetic-v1")
        ),
    )
    tenant = scope.conversation.tenant_id
    marker = {"private": "SYNTHETIC_CHECKPOINT_MARKER"}
    view = await store.save("root", "ns", marker, tenant_id=tenant)
    stored = raw.get("root", "ns", tenant)
    assert "SYNTHETIC_CHECKPOINT_MARKER" not in str(stored.state)
    assert (await store.get("root", "ns", tenant)).state == marker
    raw.save(
        "root",
        "other",
        stored.state,
        tenant_id=tenant,
        checkpoint_id=view.checkpoint_id,
    )
    with pytest.raises(ValueError, match="CHECKPOINT_BODY_UNAVAILABLE"):
        await store.get("root", "other", tenant)


@pytest.mark.parametrize("kind", ["direct", "conversation"])
async def test_memory_program_never_returns_old_body_after_saver_fence_denies(kind):
    from efficiency_platform_agent.orchestration.builders.conversation_direct import (
        _ConversationDirectProgram,
    )
    from efficiency_platform_agent.orchestration.builders.direct import _Program

    async def unavailable(config):
        raise PermissionError("MEMORY_THREAD_FENCED")

    compiled = SimpleNamespace(
        checkpointer=SimpleNamespace(memory_fenced=True), aget_state=unavailable
    )
    program = (
        _ConversationDirectProgram(compiled)
        if kind == "conversation"
        else _Program(compiled, None, None)
    )
    program._last = {"private": "SYNTHETIC_CHECKPOINT_MARKER"}
    with pytest.raises(PermissionError, match="FENCED"):
        await program.get_state({})


@pytest.mark.parametrize(
    "value",
    [
        JsonObject(),
        JsonObject((("content", "synthetic-result"),)),
        JsonObject(
            (
                (
                    "nested",
                    (None, JsonObject(), JsonObject((("value", ("x", 1, True)),))),
                ),
            )
        ),
        {
            "list": [JsonObject(), ("x", None)],
            "tuple": (JsonObject((("body", "value"),)),),
        },
        {
            "budget": BudgetState(BudgetCharge(input_tokens=2), 1, 100),
            "status": RunStatus.SUCCEEDED,
        },
    ],
)
def test_checkpoint_codec_preserves_immutable_json_types(value):
    from efficiency_platform_agent.core.memory_thread import CheckpointLocation
    from efficiency_platform_agent.orchestration.fenced_checkpoint import (
        CheckpointPayloadSerializer,
    )
    from efficiency_platform_agent.persistence.memory_checkpoint_cipher import (
        AesGcmCheckpointBodyCipher,
    )

    scope, _ = synthetic_record()
    codec = CheckpointPayloadSerializer(
        AesGcmCheckpointBodyCipher(b"k" * 32, "review-v1")
    )
    location = CheckpointLocation(scope, "root", "ns", ("review",))
    restored = codec.decode(location, codec.encode(location, value))
    assert restored == value
    assert type(restored) is type(value)


async def test_json_object_roundtrip_in_real_saver_channel_metadata_and_pending():
    from efficiency_platform_agent.core.memory_thread import CheckpointLocation
    from efficiency_platform_agent.orchestration.fenced_checkpoint import (
        CheckpointPayloadSerializer,
        FencedCheckpointSaver,
    )
    from efficiency_platform_agent.persistence.memory_checkpoint_cipher import (
        AesGcmCheckpointBodyCipher,
    )

    scope, _ = synthetic_record()

    class Registry:
        @asynccontextmanager
        async def guard(self, thread, backend, namespace, **kwargs):
            yield CheckpointLocation(scope, thread, namespace, ())

    codec = CheckpointPayloadSerializer(
        AesGcmCheckpointBodyCipher(b"k" * 32, "review-v1")
    )
    saver = FencedCheckpointSaver(
        InMemorySaver(), Registry(), "official", serializer=codec
    )
    body = JsonObject(
        (("content", (None, JsonObject(), JsonObject((("text", "result"),)))),)
    )
    checkpoint = empty_checkpoint() | {
        "channel_values": {"output": body},
        "channel_versions": {"output": "1"},
    }
    config = await saver.aput(
        {"configurable": {"thread_id": "root", "checkpoint_ns": "ns"}},
        checkpoint,
        {"binding": body},
        {"output": "1"},
    )
    await saver.aput_writes(config, [("pending", body)], "task")
    restored = await saver.aget_tuple(config)
    assert restored.checkpoint["channel_values"]["output"] == body
    assert restored.metadata["binding"] == body
    assert restored.pending_writes == [("task", "pending", body)]
    assert [value.metadata async for value in saver.alist(config)] == [
        {"binding": body}
    ]


@pytest.mark.parametrize("binding_in_state", [True, False])
async def test_owned_pg_view_binding_survives_get_and_new_store_instance(
    binding_in_state,
):
    from efficiency_platform_agent.core.memory_thread import CheckpointLocation
    from efficiency_platform_agent.orchestration.fenced_checkpoint import (
        CheckpointPayloadSerializer,
        FencedCheckpointStore,
    )
    from efficiency_platform_agent.orchestration.postgres_checkpoint import (
        PostgresCheckpointStore,
    )
    from efficiency_platform_agent.persistence.memory_checkpoint_cipher import (
        AesGcmCheckpointBodyCipher,
    )

    scope, record = synthetic_record()

    class Registry:
        @asynccontextmanager
        async def guard(self, thread, backend, namespace, **kwargs):
            yield CheckpointLocation(scope, thread, namespace, ())

    class Connection:
        async def execute(self, query, params):
            if query.startswith("INSERT"):
                self.row = {"checkpoint_id": params[3], "state": params[4].obj}
            return self

        async def fetchone(self):
            return self.row

    connection = Connection()
    codec = CheckpointPayloadSerializer(
        AesGcmCheckpointBodyCipher(b"k" * 32, "review-v1")
    )

    def open_store():
        return FencedCheckpointStore(
            PostgresCheckpointStore(connection, "agent_runtime_12345678"),
            Registry(),
            serializer=codec,
        )

    binding = JsonObject((("wait_event_id", "wait"),))
    state = {"private": "value"}
    if binding_in_state:
        state["resume_binding"] = {"wait_event_id": "wait"}
    store = open_store()
    saved = await store.save(
        record.runtime_id,
        "ns",
        state,
        tenant_id=scope.conversation.tenant_id,
        resume_binding=binding,
    )
    for reader in (store, open_store()):
        restored = await reader.get(
            record.runtime_id, "ns", scope.conversation.tenant_id
        )
        assert restored.view == saved
        assert restored.view.resume_binding == binding


def test_checkpoint_codec_rejects_legacy_wire_and_unsupported_types_instead_of_null():
    from efficiency_platform_agent.core.memory_thread import CheckpointLocation
    from efficiency_platform_agent.orchestration.fenced_checkpoint import (
        CheckpointPayloadSerializer,
    )
    from efficiency_platform_agent.persistence.memory_checkpoint_cipher import (
        AesGcmCheckpointBodyCipher,
    )

    scope, _ = synthetic_record()
    cipher = AesGcmCheckpointBodyCipher(b"k" * 32, "review-v1")
    codec = CheckpointPayloadSerializer(cipher)
    location = CheckpointLocation(scope, "root", "ns", ("review",))
    sealed = cipher.seal(location, b"msgpack\0legacy-payload")
    envelope = {
        "memory_checkpoint_format": "1",
        "key_version": sealed.key_version,
        "nonce": base64.b64encode(sealed.nonce).decode(),
        "ciphertext": base64.b64encode(sealed.ciphertext).decode(),
    }
    with pytest.raises(ValueError, match="CHECKPOINT_BODY_UNAVAILABLE"):
        codec.decode(location, envelope)
    with pytest.raises(TypeError, match="CHECKPOINT_VALUE_UNSUPPORTED"):
        codec.encode(location, object())
