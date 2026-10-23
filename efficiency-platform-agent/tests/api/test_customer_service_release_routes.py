from __future__ import annotations

import json
from hashlib import sha256
from types import SimpleNamespace

import httpx
import pytest

from efficiency_platform_agent.agents.customer_service.model_gateway import (
    ReleaseStructuredModelGateway,
)
from efficiency_platform_agent.agents.customer_service.release_bundle import (
    CustomerServiceReleaseBundle,
)
from efficiency_platform_agent.agents.customer_service.release_repository import (
    InMemoryReleaseRepository,
    _decode_snapshot,
)
from efficiency_platform_agent.agents.customer_service.state import IntentDecision
from efficiency_platform_agent.api.app import create_app
from efficiency_platform_agent.core.run import (
    ProviderError,
    ProviderMessage,
    ProviderResult,
    ProviderUsage,
)


def _payload() -> dict[str, object]:
    value: dict[str, object] = {
        "contract_version": "customer-service-release/1",
        "agent_key": "customer-service",
        "agent_version": "1.0.0",
        "graph_key": "customer-service",
        "graph_version": "1",
        "environment": "dev",
        "prompt_bindings": [
            {
                "stage_key": "identity",
                "ordinal": 1,
                "prompt_key": "customer_service.identity.system",
                "prompt_version": "1.0.0",
                "checksum": "a" * 64,
                "messages": [
                    {
                        "ordinal": 1,
                        "role": "SYSTEM",
                        "message_key": "identity",
                        "content_template": "你是内部智能客服",
                        "content_format": "TEXT",
                        "trusted_instruction": True,
                        "checksum": "b" * 64,
                        "variables": [],
                    }
                ],
            }
        ],
        "model_policy": {
            "policy_key": "primary",
            "semantic_version": "1.0.0",
            "provider": "DEEPSEEK",
            "model_name": "deepseek-chat",
            "temperature": 0.1,
            "top_p": 0.9,
            "max_input_tokens": 32000,
            "max_output_tokens": 4096,
            "connect_timeout_ms": 5000,
            "read_timeout_ms": 120000,
            "max_retries": 1,
            "checksum": "c" * 64,
        },
        "rag_policy": {
            "policy_key": "default",
            "semantic_version": "1.0.0",
            "rewrite_query_limit": 3,
            "vector_top_k": 30,
            "fts_top_k": 30,
            "fusion_top_k": 40,
            "rerank_top_k": 12,
            "context_token_limit": 12000,
            "citation_limit": 12,
            "checksum": "d" * 64,
        },
        "knowledge_bindings": [
            {
                "knowledge_base_id": "22222222-2222-2222-2222-222222222222",
                "index_release_id": "33333333-3333-3333-3333-333333333333",
                "priority": 1,
                "required": True,
            }
        ],
        "tool_allowlist": [],
        "output_contract_version": "customer-service-answer/1",
        "safety_rule_version": "1",
    }
    canonical = json.dumps(
        value, ensure_ascii=False, sort_keys=True, separators=(",", ":")
    )
    value["snapshot_checksum"] = sha256(canonical.encode()).hexdigest()
    return value


def _rechecksum(value: dict[str, object]) -> None:
    content = {key: item for key, item in value.items() if key != "snapshot_checksum"}
    canonical = json.dumps(
        content, ensure_ascii=False, sort_keys=True, separators=(",", ":")
    )
    value["snapshot_checksum"] = sha256(canonical.encode()).hexdigest()


def _v2_payload():
    value = _payload()
    value["contract_version"] = "customer-service-release/2"
    value["rag_policy"].update(
        final_evidence_top_k=8,
        similarity_candidate_threshold=0.96,
        similarity_pair_limit=20,
        adjacent_group_max_parents=3,
    )
    for stage in (
        "equivalence",
        "conflict_screen",
        "evidence_extract",
        "answer_company",
        "answer_mixed",
        "answer_repair",
    ):
        value["prompt_bindings"].append(
            {
                "stage_key": stage,
                "ordinal": 1,
                "prompt_key": stage,
                "prompt_version": "1.0.0",
                "checksum": "a" * 64,
                "messages": [
                    {
                        "ordinal": 1,
                        "role": "SYSTEM",
                        "message_key": "customer_service.evidence_scope.v1"
                        if stage.startswith("answer_")
                        else "instruction",
                        "content_template": "仅判断原文",
                        "content_format": "TEXT",
                        "trusted_instruction": True,
                        "checksum": "b" * 64,
                        "variables": [],
                    },
                    {
                        "ordinal": 2,
                        "role": "USER",
                        "message_key": "input",
                        "content_template": "{{input_json}}",
                        "content_format": "JSON",
                        "trusted_instruction": False,
                        "checksum": "b" * 64,
                        "variables": [],
                    },
                ],
            }
        )
    value["prompt_bindings"].sort(key=lambda item: item["stage_key"])
    _rechecksum(value)
    return value


@pytest.mark.parametrize("stage", ["answer_company", "answer_mixed", "answer_repair"])
@pytest.mark.parametrize("mutation", ["old_key", "untrusted", "user_role", "missing"])
def test_v2_requires_versioned_answer_evidence_scope_capability(stage, mutation):
    payload = _v2_payload()
    binding = next(b for b in payload["prompt_bindings"] if b["stage_key"] == stage)
    if mutation == "old_key":
        binding["messages"][0]["message_key"] = "legacy_instruction"
    elif mutation == "untrusted":
        binding["messages"][0]["trusted_instruction"] = False
    elif mutation == "user_role":
        binding["messages"][0].update(role="USER", trusted_instruction=False)
    else:
        payload["prompt_bindings"].remove(binding)
    with pytest.raises(ValueError, match="ANSWER_EVIDENCE_SCOPE_CAPABILITY_REQUIRED"):
        CustomerServiceReleaseBundle.model_validate(payload)
    with pytest.raises(ValueError, match="ANSWER_EVIDENCE_SCOPE_CAPABILITY_REQUIRED"):
        _decode_snapshot(json.dumps(payload))


@pytest.mark.parametrize("role", ["SYSTEM", "DEVELOPER"])
def test_new_answer_capability_passes_and_v1_keeps_legacy_prompts(role):
    payload = _v2_payload()
    for binding in payload["prompt_bindings"]:
        if binding["stage_key"] in {"answer_company", "answer_mixed", "answer_repair"}:
            binding["messages"][0]["role"] = role
    _rechecksum(payload)
    CustomerServiceReleaseBundle.model_validate(payload).assert_checksum()
    CustomerServiceReleaseBundle.model_validate(_payload()).assert_checksum()


def test_v2_release_and_v1_roundtrip_keep_frozen_checksums():
    for payload in (_payload(), _v2_payload()):
        bundle = CustomerServiceReleaseBundle.model_validate(payload)
        bundle.assert_checksum()
        restored = _decode_snapshot(bundle.model_dump_json())
        restored.assert_checksum()
        assert set(json.loads(bundle.model_dump_json())) == set(payload)
        assert set(bundle.model_dump()["rag_policy"]) == set(payload["rag_policy"])


@pytest.mark.parametrize(
    "field,value",
    [
        ("final_evidence_top_k", 0),
        ("final_evidence_top_k", 21),
        ("similarity_candidate_threshold", 0.84),
        ("similarity_candidate_threshold", 1.01),
        ("similarity_pair_limit", 0),
        ("similarity_pair_limit", 51),
        ("adjacent_group_max_parents", 0),
        ("adjacent_group_max_parents", 6),
    ],
)
def test_v2_rejects_policy_out_of_bounds(field, value):
    payload = _v2_payload()
    payload["rag_policy"][field] = value
    with pytest.raises(ValueError):
        CustomerServiceReleaseBundle.model_validate(payload)


def test_v2_large_model_is_frozen_and_must_have_larger_input():
    payload = _v2_payload()
    payload["large_context_model_policy"] = payload["model_policy"] | {
        "policy_key": "large",
        "max_input_tokens": 64000,
    }
    _rechecksum(payload)
    bundle = CustomerServiceReleaseBundle.model_validate(payload)
    bundle.assert_checksum()
    payload["large_context_model_policy"]["max_input_tokens"] = 32000
    with pytest.raises(ValueError):
        CustomerServiceReleaseBundle.model_validate(payload)


def test_v2_requires_all_evidence_stages_and_system_user_order():
    payload = _v2_payload()
    payload["prompt_bindings"].pop(0)
    with pytest.raises(ValueError):
        CustomerServiceReleaseBundle.model_validate(payload)
    payload = _v2_payload()
    payload["prompt_bindings"][0]["messages"].reverse()
    with pytest.raises(ValueError):
        CustomerServiceReleaseBundle.model_validate(payload)


def test_mysql_json_text_is_decoded_into_release_bundle() -> None:
    decoded = _decode_snapshot(json.dumps(_payload(), ensure_ascii=False))
    assert decoded.agent_key == "customer-service"
    assert decoded.snapshot_checksum == _payload()["snapshot_checksum"]


def test_java_golden_snapshots_cover_old_checksum_and_decimal_edges():
    from pathlib import Path

    fixtures = (
        Path(__file__).resolve().parents[3]
        / "ai-efficiency-platform/aiep-boot/src/test/resources"
    )
    for version in (1, 2):
        if version == 2:
            with pytest.raises(
                ValueError, match="ANSWER_EVIDENCE_SCOPE_CAPABILITY_REQUIRED"
            ):
                CustomerServiceReleaseBundle.model_validate_json(
                    (fixtures / "customer-service-release-v2.json").read_text(
                        encoding="utf-8"
                    )
                )
            continue
        bundle = CustomerServiceReleaseBundle.model_validate_json(
            (fixtures / f"customer-service-release-v{version}.json").read_text(
                encoding="utf-8"
            )
        )
        bundle.assert_checksum()
        _decode_snapshot(bundle.model_dump_json()).assert_checksum()

    capable = CustomerServiceReleaseBundle.model_validate_json(
        (fixtures / "customer-service-release-v2-evidence-scope.json").read_text(
            encoding="utf-8"
        )
    )
    capable.assert_checksum()
    _decode_snapshot(capable.model_dump_json()).assert_checksum()


def test_v2_negative_zero_has_same_java_canonical_number_as_zero():
    payload = _v2_payload()
    payload["model_policy"]["temperature"] = 0
    positive = CustomerServiceReleaseBundle.model_validate(payload).computed_checksum()
    payload["model_policy"]["temperature"] = "-0.0000"
    assert (
        CustomerServiceReleaseBundle.model_validate(payload).computed_checksum()
        == positive
    )


@pytest.mark.asyncio
async def test_v2_http_delivery_verifies_new_snapshot_and_rejects_tampering():
    app = create_app(
        SimpleNamespace(event_hub=None),
        customer_service_release_repository=InMemoryReleaseRepository(),
    )
    payload = _v2_payload()
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://test"
    ) as client:
        accepted = await client.put(
            "/internal/v1/customer-service/releases/11111111-1111-1111-1111-111111111111",
            json=payload,
        )
        assert accepted.status_code == 200
        assert accepted.json()["checksum"] == payload["snapshot_checksum"]
        payload["rag_policy"]["final_evidence_top_k"] = 9
        tampered = await client.put(
            "/internal/v1/customer-service/releases/11111111-1111-1111-1111-111111111112",
            json=payload,
        )
        assert tampered.status_code == 422
        assert tampered.json()["error"]["code"] == "CS_AGENT_RELEASE_CHECKSUM_INVALID"


def test_v2_canonical_decimal_does_not_round_to_python_context_precision():
    from decimal import Decimal

    from efficiency_platform_agent.agents.customer_service.release_bundle import (
        _canonical_json,
    )

    assert (
        _canonical_json(Decimal("0.96000000000000000000000000001"))
        == "0.96000000000000000000000000001"
    )


def _precise_v2_json():
    payload = _v2_payload()
    payload.pop("snapshot_checksum")
    canonical = json.dumps(
        payload, ensure_ascii=False, sort_keys=True, separators=(",", ":")
    )
    canonical = canonical.replace(
        '"similarity_candidate_threshold":0.96',
        '"similarity_candidate_threshold":0.960000000000000001',
    )
    checksum = sha256(canonical.encode()).hexdigest()
    return canonical[:-1] + ',"snapshot_checksum":"' + checksum + '"}', checksum


def test_precise_numeric_json_snapshot_read_keeps_decimal_and_checksum():
    from decimal import Decimal

    raw, checksum = _precise_v2_json()
    for snapshot in (raw, raw.encode(), bytearray(raw.encode())):
        bundle = _decode_snapshot(snapshot)
        assert bundle.rag_policy.similarity_candidate_threshold == Decimal(
            "0.960000000000000001"
        )
        bundle.assert_checksum()
        assert bundle.snapshot_checksum == checksum


@pytest.mark.asyncio
@pytest.mark.parametrize("operation", ["get", "get_active", "save"])
async def test_mysql_snapshot_read_uses_text_before_driver_float_decoding(operation):
    from contextlib import asynccontextmanager
    from uuid import UUID

    from efficiency_platform_agent.agents.customer_service.release_repository import (
        MySqlReleaseRepository,
    )

    raw, checksum = _precise_v2_json()
    release_id = UUID("11111111-1111-1111-1111-111111111111")

    class Engine:
        @asynccontextmanager
        async def connect(self):
            yield self

        begin = connect

        async def execute(self, statement, parameters=None):
            assert "CAST(snapshot_json AS CHAR)" in str(statement)
            return SimpleNamespace(
                scalar_one_or_none=lambda: raw,
                first=lambda: SimpleNamespace(
                    snapshot_json=raw, checksum=checksum, release_id=release_id
                ),
            )

    repository = MySqlReleaseRepository(Engine())
    if operation == "get":
        bundle = await repository.get(release_id)
    elif operation == "get_active":
        _, bundle = await repository.get_active()
    else:
        bundle = await repository.save(release_id, _decode_snapshot(raw))
    bundle.assert_checksum()


@pytest.mark.asyncio
@pytest.mark.parametrize("raw", ['{"invalid":', "{}"])
async def test_release_json_adapter_preserves_invalid_body_422(raw):
    app = create_app(
        SimpleNamespace(event_hub=None),
        customer_service_release_repository=InMemoryReleaseRepository(),
    )
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://test"
    ) as client:
        response = await client.put(
            "/internal/v1/customer-service/releases/11111111-1111-1111-1111-111111111111",
            content=raw,
            headers={"content-type": "application/json"},
        )
    assert response.status_code == 422


def test_release_openapi_keeps_typed_request_body():
    app = create_app(
        SimpleNamespace(event_hub=None),
        customer_service_release_repository=InMemoryReleaseRepository(),
    )
    operation = app.openapi()["paths"][
        "/internal/v1/customer-service/releases/{release_id}"
    ]["put"]
    assert operation["requestBody"]["required"] is True
    assert operation["requestBody"]["content"]["application/json"]["schema"][
        "$ref"
    ].endswith("CustomerServiceReleaseBundle")


@pytest.mark.asyncio
async def test_http_precise_numeric_json_survives_repository_roundtrip():
    from decimal import Decimal

    class SnapshotRepository(InMemoryReleaseRepository):
        async def save(self, release_id, bundle):
            bundle = _decode_snapshot(bundle.model_dump_json())
            bundle.assert_checksum()
            return await super().save(release_id, bundle)

    repository = SnapshotRepository()
    app = create_app(
        SimpleNamespace(event_hub=None), customer_service_release_repository=repository
    )
    raw, checksum = _precise_v2_json()
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://test"
    ) as client:
        response = await client.put(
            "/internal/v1/customer-service/releases/11111111-1111-1111-1111-111111111111",
            content=raw,
            headers={"content-type": "application/json"},
        )
    assert response.status_code == 200, response.text
    assert response.json()["checksum"] == checksum
    stored = next(iter(repository.values.values()))
    assert stored.rag_policy.similarity_candidate_threshold == Decimal(
        "0.960000000000000001"
    )


@pytest.mark.asyncio
async def test_structured_gateway_appends_code_owned_json_contract() -> None:
    class Provider:
        request = None

        async def complete(self, request):
            self.request = request
            return ProviderResult(
                request.contract_version,
                ProviderMessage(
                    "assistant",
                    json.dumps(
                        {
                            "intent_type": "GENERAL_QUERY",
                            "requires_company_knowledge": False,
                            "requires_general_advice": True,
                            "missing_field": None,
                            "normalized_question": "如何梳理问题？",
                        },
                        ensure_ascii=False,
                    ),
                ),
                ProviderUsage(1, 1, 0, 0, 0),
            )

    provider = Provider()
    bundle = CustomerServiceReleaseBundle.model_validate(_payload())
    gateway = ReleaseStructuredModelGateway(provider, bundle)  # type: ignore[arg-type]
    await gateway.complete("identity", {"question": "如何梳理问题？"}, IntentDecision)

    assert provider.request is not None
    contract = provider.request.messages[-1]
    assert contract.role == "developer"
    assert "JSON" in contract.content
    assert '"intent_type"' in contract.content


@pytest.mark.asyncio
async def test_structured_gateway_retries_schema_invalid_response() -> None:
    class Provider:
        calls = 0

        async def complete(self, request):
            self.calls += 1
            if self.calls == 1:
                return ProviderResult(
                    request.contract_version,
                    None,
                    ProviderUsage(1, 1, 0, 0, 0),
                    ProviderError(
                        "PROVIDER_SCHEMA_INVALID",
                        "response",
                        False,
                        "响应不符合输出契约",
                    ),
                )
            return ProviderResult(
                request.contract_version,
                ProviderMessage(
                    "assistant",
                    json.dumps(
                        {
                            "intent_type": "GENERAL_QUERY",
                            "requires_company_knowledge": False,
                            "requires_general_advice": True,
                            "missing_field": None,
                            "normalized_question": "如何梳理问题？",
                        },
                        ensure_ascii=False,
                    ),
                ),
                ProviderUsage(1, 1, 0, 0, 0),
            )

    provider = Provider()
    gateway = ReleaseStructuredModelGateway(  # type: ignore[arg-type]
        provider, CustomerServiceReleaseBundle.model_validate(_payload())
    )
    result = await gateway.complete(
        "identity", {"question": "如何梳理问题？"}, IntentDecision
    )

    assert provider.calls == 2
    assert result.intent_type.value == "GENERAL_QUERY"


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
