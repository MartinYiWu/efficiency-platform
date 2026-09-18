"""X04 事件聚类冻结合成基准与真实模型返回门禁。"""

from __future__ import annotations

import hashlib
import json
import time
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from efficiency_platform_agent.capabilities.model.runtime import (
    ModelLeaseContext,
)
from efficiency_platform_agent.capabilities.research.v2.clustering import (
    CLUSTER_PROMPT_VERSION,
    ClusterMemberJudgementV2,
    ClusterProposalV2,
    EventClusterer,
    evaluate_pairwise_clusters,
)
from efficiency_platform_agent.contracts.intent_v2 import (
    BudgetLeaseReferenceV2,
    OutputRequirementsV2,
    SourceConstraintsV2,
)
from efficiency_platform_agent.contracts.research_evidence_v2 import (
    SourceDocumentV2,
)
from efficiency_platform_agent.contracts.research_v2 import (
    CountPolicy,
    ResearchBriefV2,
    TrustedResearchContextV2,
)
from efficiency_platform_agent.contracts.temporal_v2 import ResolvedTimeWindow
from efficiency_platform_agent.core.budget import RemainingBudget
from efficiency_platform_agent.core.budget_execution import BudgetExecutionBinding
from efficiency_platform_agent.core.model import ModelDemand, ModelTier
from efficiency_platform_agent.core.run import (
    JsonObject,
    ProviderMessage,
    ProviderRequest,
)
from efficiency_platform_agent.core.runtime import UsageSnapshot

BENCHMARK_GENERATOR_VERSION = "research-cluster-benchmark/1"
_COMPANIES = (
    "Aster Labs",
    "Beacon AI",
    "Cedar Systems",
    "Delta Compute",
    "Ember Research",
    "Fjord Models",
    "Grove Intelligence",
    "Harbor ML",
    "Ion Robotics",
    "Juniper Cloud",
    "Kite Analytics",
    "Lumen Agents",
    "Mesa Inference",
    "Nova Language",
    "Orchid AI",
)


@dataclass(frozen=True, slots=True)
class FrozenClusterBenchmark:
    corpus_id: str
    corpus_sha256: str
    documents: tuple[SourceDocumentV2, ...]
    gold_clusters: tuple[tuple[str, ...], ...]
    brief: ResearchBriefV2


class LiveModelClusterDecisionPort:
    """经 ModelRuntime 和父 BudgetLease 执行盲聚类决策。"""

    def __init__(self, runtime: object, binding: BudgetExecutionBinding) -> None:
        if not callable(getattr(runtime, "complete", None)):
            raise TypeError("CLUSTER_MODEL_RUNTIME_INVALID")
        if not isinstance(binding, BudgetExecutionBinding):
            raise TypeError("CLUSTER_BUDGET_BINDING_INVALID")
        self.runtime: Any = runtime
        self.binding = binding
        self.usage = UsageSnapshot()
        self.records: list[dict[str, object]] = []

    async def propose(
        self,
        bucket: Any,
        brief: ResearchBriefV2,
        lease: object,
    ) -> tuple[ClusterProposalV2, ...]:
        del lease
        payload = json.dumps(
            {
                "task": "将同一真实事件的转载/报道合并；同公司同版本同一天的产品发布与服务故障必须分开。",
                "documents": [
                    {
                        "document_id": item.document_id,
                        "title": item.title,
                        "text": item.text,
                        "published_at": item.published_at.isoformat()
                        if item.published_at
                        else None,
                    }
                    for item in bucket.documents
                ],
            },
            ensure_ascii=False,
            separators=(",", ":"),
        )
        snapshot = await self.binding.port.snapshot(self.binding.scope)
        remaining = RemainingBudget(
            max(1, snapshot.limits.max_calls - snapshot.used.calls),
            max(1, snapshot.limits.max_calls - snapshot.used.calls),
            max(1, snapshot.limits.max_input_tokens - snapshot.used.input_tokens),
            max(1, snapshot.limits.max_output_tokens - snapshot.used.output_tokens),
            max(
                1,
                snapshot.limits.max_cost_microunits
                - snapshot.used.cost_microunits,
            ),
            max(
                1,
                (snapshot.limits.deadline_epoch_ms or int(time.time() * 1000) + 120_000)
                - int(time.time() * 1000),
            ),
        )
        prefix, version = await self.binding.next_invocation("model")
        model_lease = ModelLeaseContext(
            self.binding.port,
            self.binding.scope,
            prefix,
            version,
            reserve_cost_microunits=0,
        )
        execution = await self.runtime.complete(
            ModelDemand(
                "research-v2-cluster-benchmark/1",
                ModelTier.BALANCED,
                True,
                False,
                max(1, len(payload) // 4),
                4_000,
            ),
            ProviderRequest(
                "research-v2-cluster-benchmark/1",
                (
                    ProviderMessage(
                        "system",
                        "只输出JSON对象，顶层只含clusters数组。每个cluster必须含document_ids、"
                        "event_type、product_version、entity_names、merge_basis；document_ids、"
                        "entity_names、merge_basis都必须是字符串数组。每个输入文档必须且只能"
                        "出现一次。按事实事件聚类，不得根据文档ID连续性猜测。",
                    ),
                    ProviderMessage("user", payload),
                ),
                JsonObject(
                    (
                        ("temperature", 0),
                        ("response_format", JsonObject((("type", "json_object"),))),
                    )
                ),
                min(120_000, remaining.timeout_ms),
            ),
            remaining_budget=remaining,
            lease_context=model_lease,
        )
        self.binding.update_version(model_lease.version)
        if execution.result.error is not None or execution.result.message is None:
            raise RuntimeError("CLUSTER_MODEL_EXECUTION_FAILED")
        content = execution.result.message.content
        if not isinstance(content, str):
            raise TypeError("CLUSTER_MODEL_RESPONSE_INVALID")
        proposals = parse_cluster_proposals(
            content,
            bucket.documents,
            brief,
            bucket_id=bucket.bucket_id,
        )
        self.usage = UsageSnapshot(
            self.usage.input_tokens + execution.usage.input_tokens,
            self.usage.output_tokens + execution.usage.output_tokens,
            self.usage.cost_microunits + execution.usage.cost_microunits,
            self.usage.estimated or execution.usage.estimated,
        )
        self.records.append(
            {
                "bucket_id": bucket.bucket_id,
                "document_count": len(bucket.documents),
                "predicted_cluster_count": len(proposals),
                "input_tokens": execution.usage.input_tokens,
                "output_tokens": execution.usage.output_tokens,
                "cost_microunits": execution.usage.cost_microunits,
            }
        )
        return proposals


async def evaluate_live_cluster_benchmark(
    benchmark: FrozenClusterBenchmark,
    port: LiveModelClusterDecisionPort,
    *,
    model_id: str,
) -> dict[str, object]:
    predicted = await EventClusterer(port).cluster(
        benchmark.documents,
        benchmark.brief,
        BudgetLeaseReferenceV2(
            lease_id=port.binding.lease_id,
            version=port.binding.version,
        ),
    )
    metrics = evaluate_pairwise_clusters(predicted, benchmark.gold_clusters)
    metrics_payload = metrics.model_dump(mode="json")
    return {
        "schema_version": "research-v2-cluster-evaluation/1",
        "status": "PASS"
        if metrics.precision >= 0.98 and metrics.recall >= 0.90
        else "FAILED",
        "benchmark_type": "deterministic_synthetic_blind",
        "benchmark_generator_version": BENCHMARK_GENERATOR_VERSION,
        "corpus_id": benchmark.corpus_id,
        "corpus_sha256": benchmark.corpus_sha256,
        "model_id": model_id,
        "prompt_version": "research-v2-cluster-benchmark/1",
        "document_count": len(benchmark.documents),
        "gold_event_count": len(benchmark.gold_clusters),
        "predicted_event_count": predicted.event_count,
        "model_call_count": len(port.records),
        "metrics": metrics_payload,
        "thresholds": {"precision": 0.98, "recall": 0.90},
        "thresholds_met": metrics.precision >= 0.98 and metrics.recall >= 0.90,
        "usage": {
            "input_tokens": port.usage.input_tokens,
            "output_tokens": port.usage.output_tokens,
            "cost_microunits": port.usage.cost_microunits,
            "cost_observed": port.usage.cost_microunits > 0,
        },
        "bucket_records": port.records,
        "label_method": "deterministic fixture construction; no human labels",
        "human_missed_count": None,
        "statistical_significance_claimed": False,
    }


def build_frozen_cluster_benchmark(path: Path) -> FrozenClusterBenchmark:
    """从冻结 manifest 确定性展开正文；gold 标签不进入文档文本。"""

    raw = path.read_bytes()
    payload = json.loads(raw)
    events = payload.get("events")
    if (
        payload.get("document_count") != 100
        or payload.get("event_count") != 30
        or not isinstance(events, list)
        or len(events) != 30
    ):
        raise ValueError("CLUSTER_BENCHMARK_MANIFEST_INVALID")
    documents: list[SourceDocumentV2] = []
    gold: list[tuple[str, ...]] = []
    for event_index, event in enumerate(events, start=1):
        if not isinstance(event, dict):
            raise TypeError("CLUSTER_BENCHMARK_MANIFEST_INVALID")
        start = event.get("document_start")
        end = event.get("document_end")
        if not isinstance(start, int) or not isinstance(end, int) or start > end:
            raise ValueError("CLUSTER_BENCHMARK_MANIFEST_INVALID")
        company_index = (event_index - 1) // 2
        company = _COMPANIES[company_index]
        version = f"v{company_index + 1}.1"
        observed_at = datetime(2026, 9, company_index + 1, 8, tzinfo=UTC)
        is_release = event_index % 2 == 1
        identifiers: list[str] = []
        for sequence, document_number in enumerate(range(start, end + 1)):
            identifier = f"fixture-doc-{document_number:03d}"
            identifiers.append(identifier)
            title, text = _benchmark_text(
                company,
                version,
                is_release=is_release,
                variant=sequence,
            )
            documents.append(
                SourceDocumentV2(
                    document_id=identifier,
                    candidate_id=f"candidate-{document_number:03d}",
                    source_id=f"benchmark-source-{sequence + 1}",
                    source_item_id=f"item-{document_number:03d}",
                    original_url=(
                        f"https://news.example/{company_index + 1}/"
                        f"{document_number:03d}"
                    ),
                    canonical_url=(
                        f"https://news.example/{company_index + 1}/"
                        f"{document_number:03d}"
                    ),
                    publisher_id=f"publisher-{sequence + 1}.example",
                    title=title,
                    text=text,
                    content_hash=hashlib.sha256(text.encode()).hexdigest(),
                    artifact_ref=f"inline:{identifier}",
                    discovered_via="cache",
                    content_scope="full",
                    published_at=observed_at,
                    published_timezone_known=True,
                    time_precision="exact",
                    first_published_at=observed_at,
                    extractor_version=BENCHMARK_GENERATOR_VERSION,
                    source_role="primary" if sequence == 0 else "reporting",
                )
            )
        gold.append(tuple(identifiers))
    if len(documents) != 100:
        raise ValueError("CLUSTER_BENCHMARK_MANIFEST_INVALID")
    brief = _benchmark_brief()
    digest = hashlib.sha256(
        raw
        + BENCHMARK_GENERATOR_VERSION.encode()
        + b"\n"
        + b"\n".join(
            json.dumps(
                {
                    "id": item.document_id,
                    "title": item.title,
                    "text": item.text,
                    "published_at": item.published_at.isoformat()
                    if item.published_at
                    else None,
                },
                ensure_ascii=False,
                sort_keys=True,
            ).encode()
            for item in documents
        )
    ).hexdigest()
    return FrozenClusterBenchmark(
        corpus_id=str(payload.get("corpus_id")),
        corpus_sha256=digest,
        documents=tuple(documents),
        gold_clusters=tuple(gold),
        brief=brief,
    )


def parse_cluster_proposals(
    content: str,
    documents: tuple[SourceDocumentV2, ...],
    brief: ResearchBriefV2,
    *,
    bucket_id: str,
) -> tuple[ClusterProposalV2, ...]:
    """只接受覆盖 bucket 全集且无重复/未知成员的模型分区。"""

    try:
        decoded = json.loads(content)
    except (TypeError, json.JSONDecodeError) as exc:
        raise ValueError("CLUSTER_MODEL_RESPONSE_INVALID") from exc
    clusters = decoded.get("clusters") if isinstance(decoded, dict) else None
    if not isinstance(clusters, list) or not clusters:
        raise ValueError("CLUSTER_MODEL_RESPONSE_INVALID")
    expected = {item.document_id for item in documents}
    observed: list[str] = []
    for item in clusters:
        identifiers = item.get("document_ids") if isinstance(item, dict) else None
        if not isinstance(identifiers, list) or not identifiers or any(
            not isinstance(identifier, str) for identifier in identifiers
        ):
            raise ValueError("CLUSTER_MODEL_PARTITION_INVALID")
        observed.extend(identifiers)
    if len(observed) != len(set(observed)) or set(observed) != expected:
        raise ValueError("CLUSTER_MODEL_PARTITION_INVALID")

    proposals: list[ClusterProposalV2] = []
    for index, item in enumerate(clusters):
        identifiers = tuple(item["document_ids"])
        event_type = item.get("event_type")
        product_version = item.get("product_version")
        entity_names = item.get("entity_names")
        merge_basis = item.get("merge_basis")
        if isinstance(merge_basis, str) and merge_basis.strip():
            merge_basis = [merge_basis]
        if not (
            isinstance(event_type, str)
            and event_type.strip()
            and (product_version is None or isinstance(product_version, str))
            and isinstance(entity_names, list)
            and entity_names
            and all(isinstance(value, str) and value.strip() for value in entity_names)
            and isinstance(merge_basis, list)
            and merge_basis
            and all(isinstance(value, str) and value.strip() for value in merge_basis)
        ):
            raise ValueError("CLUSTER_MODEL_RESPONSE_INVALID")
        proposals.append(
            ClusterProposalV2(
                proposal_id=f"{bucket_id}-proposal-{index + 1}",
                brief_digest=brief.canonical_digest(),
                prompt_version=CLUSTER_PROMPT_VERSION,
                entity_names=tuple(entity_names),
                members=tuple(
                    ClusterMemberJudgementV2(
                        document_id=identifier,
                        event_type=event_type,
                        product_version=product_version,
                        semantic_equivalence="same_event",
                    )
                    for identifier in identifiers
                ),
                merge_basis=tuple(merge_basis),
            )
        )
    return tuple(proposals)


def _benchmark_text(
    company: str,
    version: str,
    *,
    is_release: bool,
    variant: int,
) -> tuple[str, str]:
    if is_release:
        titles = (
            f"{company} 发布 Atlas {version} 推理引擎",
            f"{company} launches Atlas {version} inference engine",
            f"Atlas {version} 正式上线，{company} 公布新版本",
            f"{company} details the Atlas {version} product release",
        )
        texts = (
            f"{company} announced the general availability of Atlas {version}, a new inference engine release.",
            f"The Atlas {version} launch adds lower-latency inference and a stable production API for {company} customers.",
            f"{company} 表示 Atlas {version} 已正式发布，本次是产品版本发布，不是服务事故。",
            f"A release note from {company} confirms that Atlas {version} entered general availability today.",
        )
    else:
        titles = (
            f"{company} 通报 Atlas {version} API 服务故障",
            f"{company} reports Atlas {version} API outage",
            f"Atlas {version} 出现中断，{company} 启动故障处置",
            f"{company} resolves the Atlas {version} service incident",
        )
        texts = (
            f"{company} reported an Atlas {version} API outage and opened a service incident investigation.",
            f"The Atlas {version} service incident caused elevated errors before {company} restored availability.",
            f"{company} 通报 Atlas {version} 服务中断；这是运行故障，并非新产品发布。",
            f"A status update says {company} resolved the Atlas {version} outage and continues incident review.",
        )
    return titles[variant % len(titles)], texts[variant % len(texts)]


def _benchmark_brief() -> ResearchBriefV2:
    return ResearchBriefV2(
        trusted_context=TrustedResearchContextV2(
            tenant_id="tenant-x04-acceptance",
            run_id="x04-cluster-benchmark",
            task_id="x04-cluster-benchmark",
            budget_lease_id="x04-cluster-benchmark",
        ),
        intent_revision=1,
        topic="AI 产品发布与服务故障",
        entities=_COMPANIES,
        time_window=ResolvedTimeWindow(
            start=datetime(2026, 9, 1, tzinfo=UTC),
            end=datetime(2026, 10, 1, tzinfo=UTC),
            timezone="UTC",
            precision="month",
            original_text="2026-09",
            anchor=datetime(2026, 10, 1, tzinfo=UTC),
        ),
        source_constraints=SourceConstraintsV2(),
        count_policy=CountPolicy(mode="best_effort", target=30, minimum=1),
        output_requirements=OutputRequirementsV2(
            output_types=("digest",), language="zh-CN"
        ),
        quality_policy_id="quality-v2",
        policy_version="2026-09-17",
    )


__all__ = [
    "BENCHMARK_GENERATOR_VERSION",
    "FrozenClusterBenchmark",
    "build_frozen_cluster_benchmark",
    "parse_cluster_proposals",
]
