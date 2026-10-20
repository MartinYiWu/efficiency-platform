from __future__ import annotations

import json
from hashlib import sha256
from types import SimpleNamespace

import httpx
import pytest

from efficiency_platform_agent.agents.customer_service.release_repository import (
    InMemoryReleaseRepository,
)
from efficiency_platform_agent.api.app import create_app


def _payload() -> dict[str, object]:
    value: dict[str, object] = {
        "contract_version": "customer-service-release/1",
        "agent_key": "customer-service",
        "agent_version": "1.0.0",
        "graph_key": "customer-service",
        "graph_version": "1",
        "environment": "dev",
        "prompt_bindings": [{
            "stage_key": "identity", "ordinal": 1,
            "prompt_key": "customer_service.identity.system",
            "prompt_version": "1.0.0", "checksum": "a" * 64,
            "messages": [{
                "ordinal": 1, "role": "SYSTEM", "message_key": "identity",
                "content_template": "你是内部智能客服", "content_format": "TEXT",
                "trusted_instruction": True, "checksum": "b" * 64,
                "variables": [],
            }],
        }],
        "model_policy": {
            "policy_key": "primary", "semantic_version": "1.0.0",
            "provider": "DEEPSEEK", "model_name": "deepseek-chat",
            "temperature": 0.1, "top_p": 0.9, "max_input_tokens": 32000,
            "max_output_tokens": 4096, "connect_timeout_ms": 5000,
            "read_timeout_ms": 120000, "max_retries": 1, "checksum": "c" * 64,
        },
        "rag_policy": {
            "policy_key": "default", "semantic_version": "1.0.0",
            "rewrite_query_limit": 3, "vector_top_k": 30, "fts_top_k": 30,
            "fusion_top_k": 40, "rerank_top_k": 12,
            "context_token_limit": 12000, "citation_limit": 12,
            "checksum": "d" * 64,
        },
        "knowledge_bindings": [{
            "knowledge_base_id": "22222222-2222-2222-2222-222222222222",
            "index_release_id": "33333333-3333-3333-3333-333333333333",
            "priority": 1, "required": True,
        }],
        "tool_allowlist": [],
        "output_contract_version": "customer-service-answer/1",
        "safety_rule_version": "1",
    }
    canonical = json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    value["snapshot_checksum"] = sha256(canonical.encode()).hexdigest()
    return value


def _rechecksum(value: dict[str, object]) -> None:
    content = {key: item for key, item in value.items() if key != "snapshot_checksum"}
    canonical = json.dumps(
        content, ensure_ascii=False, sort_keys=True, separators=(",", ":")
    )
    value["snapshot_checksum"] = sha256(canonical.encode()).hexdigest()


@pytest.mark.asyncio
async def test_release_is_idempotent_and_rejects_checksum_conflict() -> None:
    repository = InMemoryReleaseRepository()
    app = create_app(
        SimpleNamespace(event_hub=None),  # type: ignore[arg-type]
        customer_service_release_repository=repository,
    )
    release_id = "11111111-1111-1111-1111-111111111111"
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://test"
    ) as client:
        first = await client.put(
            f"/internal/v1/customer-service/releases/{release_id}", json=_payload()
        )
        duplicate = await client.put(
            f"/internal/v1/customer-service/releases/{release_id}", json=_payload()
        )
        changed = _payload()
        changed["graph_version"] = "2"
        _rechecksum(changed)
        conflict = await client.put(
            f"/internal/v1/customer-service/releases/{release_id}", json=changed
        )

    expected = {
        "contract_version": "customer-service-release-ack/1",
        "release_id": release_id,
        "checksum": _payload()["snapshot_checksum"],
        "status": "ACKNOWLEDGED",
    }
    assert first.status_code == duplicate.status_code == 200
    assert first.json() == duplicate.json() == expected
    assert conflict.status_code == 409
    assert conflict.json()["error"]["code"] == "CS_AGENT_RELEASE_CONFLICT"


@pytest.mark.asyncio
async def test_release_rejects_tampered_snapshot_and_extra_fields() -> None:
    app = create_app(
        SimpleNamespace(event_hub=None),  # type: ignore[arg-type]
        customer_service_release_repository=InMemoryReleaseRepository(),
    )
    tampered = _payload() | {"graph_version": "2"}
    extra = _payload() | {"unknown": True}
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://test"
    ) as client:
        digest = await client.put(
            "/internal/v1/customer-service/releases/11111111-1111-1111-1111-111111111111",
            json=tampered,
        )
        validation = await client.put(
            "/internal/v1/customer-service/releases/11111111-1111-1111-1111-111111111111",
            json=extra,
        )
    assert digest.status_code == 422
    assert digest.json()["error"]["code"] == "CS_AGENT_RELEASE_CHECKSUM_INVALID"
    assert validation.status_code == 422
