"""完整包进入内部传输时必须同时携带原执行授权和内容绑定。"""

import json
from pathlib import Path

import pytest
from pydantic import ValidationError

from efficiency_platform_agent.contracts.memory_context import MemoryContextEnvelope
from efficiency_platform_agent.core.run_context_binding import (
    bind_conversation_scope,
    metadata_scope,
    binding_from_metadata,
)


def envelope():
    fixture = json.loads(
        (Path(__file__).parents[2] / "fixtures/memory_packet_transport.json").read_text(
            encoding="utf-8"
        )
    )
    packet = fixture["packet"]
    return dict(
        schema_version="memory-context/1",
        memory_mode="EXACT_ONLY",
        scope=packet["scope"],
        packet=packet,
        authorization=dict(
            policy=dict(
                policy_id="policy",
                version=packet["policy_version"],
                domain="operations",
                agent_ids=["operations"],
                readable_layers=["semantic"],
                allowed_scopes=["USER_PRIVATE"],
                field_allowlist=["response.language"],
                source_types=["USER_PREFERENCE_DECISION"],
            ),
            execution_grants=[
                dict(
                    node_id="conversation.general",
                    execution_agent_id="operations",
                    purpose="assistant_response",
                )
            ],
            deadline_epoch_seconds=200,
            packet_digest=fixture["packet_digest"],
            semantic_snapshot_digest=fixture["semantic_digest"],
            request_digest="b" * 64,
            input_dependencies=packet["safety_dependencies"],
        ),
    )


def test_complete_envelope_translates_to_neutral_core_and_preserves_java_execution():
    raw = envelope()
    model = MemoryContextEnvelope.model_validate_json(json.dumps(raw))
    context = model.to_core()
    assert context.packet.execution_id == "java-execution"
    assert context.deadline_epoch_seconds == 200
    assert context.policy.field_allowlist == frozenset({"response.language"})
    assert context.execution_grants[0].purpose == "assistant_response"
    with bind_conversation_scope(context.packet.scope, memory_context=context):
        metadata = metadata_scope(context.packet.scope)
    restored = binding_from_metadata(metadata, "python-random-run", 180)
    assert restored.execution_id == "java-execution"
    assert restored.task_id == "java-task"
    assert restored.deadline_epoch_seconds == 180
    assert restored.memory_context == context


@pytest.mark.asyncio
async def test_actual_fastapi_json_arrays_freeze_without_relaxing_scalar_validation():
    import httpx
    from fastapi import FastAPI
    from efficiency_platform_agent.contracts.conversation import ConversationMessageV1

    app = FastAPI()

    @app.post("/message")
    async def message(body: ConversationMessageV1):
        core = body.memory_context.to_core()
        return {
            "items": len(core.packet.items),
            "fields": len(core.policy.field_allowlist),
        }

    body = {
        "message": "synthetic",
        "request_id": "r",
        "user_id": "user",
        "memory_context": envelope(),
    }
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://test"
    ) as client:
        result = await client.post("/message", json=body)
        assert result.status_code == 200
        assert result.json() == {"items": 1, "fields": 1}
        body["memory_context"]["packet"]["packet_revision"] = True
        result = await client.post("/message", json=body)
        assert result.status_code == 422


@pytest.mark.parametrize(
    "mutation", ["disabled", "scope", "missing", "digest", "deadline", "grant"]
)
def test_partial_or_cross_scope_envelope_is_rejected(mutation):
    raw = envelope()
    if mutation == "disabled":
        raw["memory_mode"] = "DISABLED"
    elif mutation == "scope":
        raw["scope"] = dict(raw["scope"], user_id="other")
    elif mutation == "missing":
        raw.pop("authorization")
    elif mutation == "digest":
        raw["authorization"]["packet_digest"] = "not-a-digest"
    elif mutation == "deadline":
        raw["authorization"]["deadline_epoch_seconds"] = 159
    else:
        raw["authorization"]["execution_grants"][0]["execution_agent_id"] = "unknown"
    with pytest.raises((ValidationError, ValueError)):
        MemoryContextEnvelope.model_validate_json(json.dumps(raw))
