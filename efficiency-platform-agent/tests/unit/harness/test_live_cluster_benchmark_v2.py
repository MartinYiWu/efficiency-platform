"""X04 冻结事件聚类基准及模型返回校验测试。"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from efficiency_platform_agent.capabilities.research.v2.clustering import (
    ClusterBucketV2,
)
from efficiency_platform_agent.contracts.live_acceptance_v2 import (
    LiveAcceptanceRequestV1,
)
from efficiency_platform_agent.core.model import (
    ModelCandidate,
    ModelExecutionResult,
    ModelSelection,
    ModelTier,
)
from efficiency_platform_agent.core.run import (
    ProviderMessage,
    ProviderResult,
    ProviderUsage,
)
from efficiency_platform_agent.core.runtime import UsageSnapshot
from efficiency_platform_agent.harness.live_acceptance import (
    InMemoryLiveAcceptanceBudgetBinder,
    LiveAcceptanceAuthorization,
)
from efficiency_platform_agent.harness.live_cluster_benchmark_v2 import (
    LiveModelClusterDecisionPort,
    build_frozen_cluster_benchmark,
    evaluate_live_cluster_benchmark,
    parse_cluster_proposals,
)

ROOT = Path(__file__).parents[3]
MANIFEST = ROOT / "tests/fixtures/research_v2/corpus_manifest.json"


class _SemanticFakeRuntime:
    def __init__(self) -> None:
        self.calls = 0

    async def complete(self, demand, request, *, remaining_budget, **kwargs):
        del demand, remaining_budget, kwargs
        self.calls += 1
        payload = json.loads(request.messages[-1].content)
        incident = [
            item["document_id"]
            for item in payload["documents"]
            if any(
                token in f'{item["title"]} {item["text"]}'.lower()
                for token in ("outage", "incident", "故障", "中断")
            )
        ]
        release = [
            item["document_id"]
            for item in payload["documents"]
            if item["document_id"] not in incident
        ]
        company = payload["documents"][0]["title"].split(" 发布", 1)[0].split(
            " reports", 1
        )[0]
        version = next(
            token.rstrip(",，。")
            for token in payload["documents"][0]["title"].split()
            if token.startswith("v")
        )
        clusters = []
        for identifiers, event_type in (
            (release, "product_release"),
            (incident, "service_incident"),
        ):
            if identifiers:
                clusters.append(
                    {
                        "document_ids": identifiers,
                        "event_type": event_type,
                        "product_version": version,
                        "entity_names": [company],
                        "merge_basis": ["semantic match"],
                    }
                )
        result = ProviderResult(
            request.contract_version,
            ProviderMessage(
                "assistant",
                json.dumps({"clusters": clusters}, ensure_ascii=False),
            ),
            ProviderUsage(100, 50, 0, 0, 0),
        )
        candidate = ModelCandidate(
            "candidate",
            "provider",
            "model",
            ModelTier.BALANCED,
            True,
            False,
            64_000,
            True,
            False,
        )
        return ModelExecutionResult(
            result,
            (ModelSelection(candidate, 1, None, "requested_tier"),),
            UsageSnapshot(100, 50, 0, False),
            False,
        )


def _binding():
    from datetime import UTC, datetime, timedelta

    now = datetime.now(UTC)
    authorization = LiveAcceptanceAuthorization(
        "cluster-auth",
        "owner",
        now - timedelta(minutes=1),
        now + timedelta(hours=1),
        frozenset({"model_evaluation", "source_read"}),
        ("ordinary_chat",),
        ("tenant-x04-acceptance",),
        100_000,
    )
    request = LiveAcceptanceRequestV1(
        request_id="cluster-request",
        authorization_id="cluster-auth",
        case_ids=("ordinary_chat",),
        requested_budget_microunits=100_000,
    )
    return InMemoryLiveAcceptanceBudgetBinder().bind(
        authorization,
        request,
        tenant_id="tenant-x04-acceptance",
    )


def test_frozen_benchmark_expands_to_100_documents_and_30_gold_events() -> None:
    benchmark = build_frozen_cluster_benchmark(MANIFEST)

    assert len(benchmark.documents) == 100
    assert len(benchmark.gold_clusters) == 30
    assert {item.document_id for item in benchmark.documents} == {
        f"fixture-doc-{index:03d}" for index in range(1, 101)
    }
    assert all("fixture-event" not in item.title for item in benchmark.documents)
    assert all("fixture-event" not in item.text for item in benchmark.documents)
    assert benchmark.corpus_sha256


def test_adjacent_gold_events_share_entity_version_and_time_but_not_semantics() -> None:
    benchmark = build_frozen_cluster_benchmark(MANIFEST)
    first = benchmark.documents[:4]
    second = benchmark.documents[4:8]

    assert all("Aster Labs" in item.title for item in first + second)
    assert all("v1.1" in item.title for item in first + second)
    assert {item.published_at for item in first + second} == {
        first[0].published_at
    }
    assert all(
        any(token in item.title for token in ("发布", "launches", "release", "上线"))
        for item in first
    )
    assert all(
        any(token in item.title for token in ("故障", "outage", "incident", "中断"))
        for item in second
    )


def test_model_cluster_parser_accepts_complete_blind_partition() -> None:
    benchmark = build_frozen_cluster_benchmark(MANIFEST)
    documents = benchmark.documents[:8]
    payload = json.dumps(
        {
            "clusters": [
                {
                    "document_ids": [item.document_id for item in documents[:4]],
                    "event_type": "product_release",
                    "product_version": "v1.1",
                    "entity_names": ["Aster Labs"],
                    "merge_basis": ["同一产品发布事件"],
                },
                {
                    "document_ids": [item.document_id for item in documents[4:]],
                    "event_type": "service_incident",
                    "product_version": "v1.1",
                    "entity_names": ["Aster Labs"],
                    "merge_basis": ["同一服务故障事件"],
                },
            ]
        },
        ensure_ascii=False,
    )

    proposals = parse_cluster_proposals(
        payload,
        documents,
        benchmark.brief,
        bucket_id="bucket-1",
    )

    assert len(proposals) == 2
    assert {member.document_id for item in proposals for member in item.members} == {
        item.document_id for item in documents
    }


def test_model_cluster_parser_normalizes_single_merge_basis_string() -> None:
    benchmark = build_frozen_cluster_benchmark(MANIFEST)
    documents = benchmark.documents[:4]
    payload = json.dumps(
        {
            "clusters": [
                {
                    "document_ids": [item.document_id for item in documents],
                    "event_type": "product_release",
                    "product_version": "Atlas v1.1",
                    "entity_names": ["Aster Labs"],
                    "merge_basis": "同一产品发布事件",
                }
            ]
        },
        ensure_ascii=False,
    )

    proposals = parse_cluster_proposals(
        payload,
        documents,
        benchmark.brief,
        bucket_id="bucket-string-basis",
    )

    assert proposals[0].merge_basis == ("同一产品发布事件",)


@pytest.mark.parametrize("failure", ["unknown", "duplicate", "missing"])
def test_model_cluster_parser_rejects_invalid_partition(failure: str) -> None:
    benchmark = build_frozen_cluster_benchmark(MANIFEST)
    documents = benchmark.documents[:2]
    identifiers = [item.document_id for item in documents]
    if failure == "unknown":
        clusters = [{"document_ids": ["unknown-doc"]}]
    elif failure == "duplicate":
        clusters = [
            {"document_ids": identifiers},
            {"document_ids": [identifiers[0]]},
        ]
    else:
        clusters = [{"document_ids": [identifiers[0]]}]
    payload = json.dumps({"clusters": clusters})

    with pytest.raises(ValueError, match="CLUSTER_MODEL_PARTITION_INVALID"):
        parse_cluster_proposals(
            payload,
            documents,
            benchmark.brief,
            bucket_id="bucket-invalid",
        )


@pytest.mark.asyncio
async def test_live_model_port_uses_blind_documents_and_budget_binding() -> None:
    benchmark = build_frozen_cluster_benchmark(MANIFEST)
    runtime = _SemanticFakeRuntime()
    port = LiveModelClusterDecisionPort(runtime, _binding())

    proposals = await port.propose(
        ClusterBucketV2(bucket_id="bucket-1", documents=benchmark.documents[:8]),
        benchmark.brief,
        object(),
    )

    assert len(proposals) == 2
    assert runtime.calls == 1
    assert port.usage.input_tokens == 100
    assert port.usage.output_tokens == 50


@pytest.mark.asyncio
async def test_full_frozen_benchmark_reports_pairwise_denominators() -> None:
    benchmark = build_frozen_cluster_benchmark(MANIFEST)
    runtime = _SemanticFakeRuntime()

    report = await evaluate_live_cluster_benchmark(
        benchmark,
        LiveModelClusterDecisionPort(runtime, _binding()),
        model_id="semantic-fake",
    )

    assert report["document_count"] == 100
    assert report["gold_event_count"] == 30
    assert report["metrics"]["gold_pair_count"] == 120
    assert report["metrics"]["precision"] == 1.0
    assert report["metrics"]["recall"] == 1.0
    assert report["thresholds_met"] is True
    assert report["statistical_significance_claimed"] is False
    assert runtime.calls == 15
