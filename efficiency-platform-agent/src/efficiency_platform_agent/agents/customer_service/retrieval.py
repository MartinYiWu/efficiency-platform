"""冻结索引范围内的查询改写、双路召回、RRF 与重排。"""

from __future__ import annotations

import asyncio
from dataclasses import dataclass, replace
from typing import Protocol
from uuid import UUID

from .chunking import count_tokens
from .conflict_screen import ConflictScreen, screen_conflicts
from .equivalence import EquivalenceDecision, validate_parents, verify_equivalence
from .evidence_assembly import EvidenceAssembly, assemble_evidence
from .intent import StructuredStageGateway
from .release_bundle import CustomerServiceReleaseBundle
from .state import (
    Evidence,
    EvidenceContractError,
    EvidencePack,
    ParentEvidence,
    QueryRewrite,
)


class EmbeddingPort(Protocol):
    async def embed(self, texts: tuple[str, ...]) -> tuple[tuple[float, ...], ...]: ...


class RerankPort(Protocol):
    async def rerank(
        self, query: str, documents: tuple[str, ...], *, top_n: int
    ) -> tuple[tuple[int, float], ...]: ...


class RetrievalRepository(Protocol):
    async def get_index_members(
        self, *, index_release_ids: tuple[UUID, ...]
    ) -> tuple[tuple[UUID, UUID, UUID, UUID], ...]: ...

    async def get_chunk_vectors(
        self,
        *,
        tenant_id: str,
        index_release_ids: tuple[UUID, ...],
        chunk_ids: tuple[UUID, ...],
    ) -> dict[UUID, tuple[float, ...]]: ...

    async def get_parents(
        self,
        *,
        tenant_id: str,
        index_release_ids: tuple[UUID, ...],
        parent_ids: tuple[UUID, ...],
    ) -> tuple[ParentEvidence, ...]: ...

    async def vector_search(
        self,
        *,
        tenant_id: str,
        index_release_ids: tuple[UUID, ...],
        vector: tuple[float, ...],
        limit: int,
    ) -> tuple[Evidence, ...]: ...

    async def fts_search(
        self,
        *,
        tenant_id: str,
        index_release_ids: tuple[UUID, ...],
        query: str,
        limit: int,
    ) -> tuple[Evidence, ...]: ...


@dataclass(frozen=True, slots=True)
class RetrievalTrace:
    original_query: str
    rewritten_queries: tuple[str, ...]
    index_release_ids: tuple[UUID, ...]
    vector_candidates: tuple[Evidence, ...]
    fts_candidates: tuple[Evidence, ...]
    fused_candidates: tuple[Evidence, ...]
    reranked_evidence: tuple[Evidence, ...]
    assembly: EvidenceAssembly | None = None
    equivalence_decisions: tuple[EquivalenceDecision, ...] = ()
    version_exclusions: tuple[Evidence, ...] = ()
    equivalence_errors: tuple[str, ...] = ()
    conflict_screen: ConflictScreen | None = None
    evidence_pack: EvidencePack | None = None


class CustomerServiceRetrieval:
    def __init__(
        self,
        repository: RetrievalRepository,
        embedding: EmbeddingPort,
        reranker: RerankPort,
    ) -> None:
        self.repository = repository
        self.embedding = embedding
        self.reranker = reranker

    async def search(
        self,
        *,
        tenant_id: str,
        question: str,
        gateway: StructuredStageGateway,
        bundle: CustomerServiceReleaseBundle,
        planned_queries: tuple[str, ...] | None = None,
    ) -> RetrievalTrace:
        policy = bundle.rag_policy
        if planned_queries:
            queries = planned_queries[: policy.rewrite_query_limit]
        else:
            rewrite = await gateway.complete(
                "rewrite",
                {"question": question, "rewrite_query_limit": policy.rewrite_query_limit},
                QueryRewrite,
            )
            queries = rewrite.queries[: policy.rewrite_query_limit]
        vectors = await self.embedding.embed(queries)
        release_ids = tuple(item.index_release_id for item in bundle.knowledge_bindings)
        enhanced = (
            getattr(bundle, "contract_version", "customer-service-release/1")
            == "customer-service-release/2"
        )
        members = set()
        if enhanced:
            members = set(
                await self.repository.get_index_members(index_release_ids=release_ids)
            )
            bindings = {
                (b.knowledge_base_id, b.index_release_id)
                for b in bundle.knowledge_bindings
            }
            versions: dict[UUID, UUID] = {}
            for kb, document, version, release in members:
                if (kb, release) not in bindings:
                    raise EvidenceContractError("INDEX_BINDING_MISMATCH")
                if document in versions and versions[document] != version:
                    raise EvidenceContractError("INDEX_DOCUMENT_VERSION_CONFLICT")
                versions[document] = version
        exclusions: list[Evidence] = []
        rankings: list[tuple[Evidence, ...]] = []
        vector_candidates: list[Evidence] = []
        fts_candidates: list[Evidence] = []

        async def search_query(query: str, vector: tuple[float, ...]):
            vector_items, fts_items = await asyncio.gather(
                self.repository.vector_search(
                    tenant_id=tenant_id,
                    index_release_ids=release_ids,
                    vector=vector,
                    limit=policy.vector_top_k,
                ),
                self.repository.fts_search(
                    tenant_id=tenant_id,
                    index_release_ids=release_ids,
                    query=query,
                    limit=policy.fts_top_k,
                ),
            )
            return vector_items, fts_items

        search_results = await asyncio.gather(
            *(
                search_query(query, vector)
                for query, vector in zip(queries, vectors, strict=True)
            )
        )
        for query_index, (vector_items, fts_items) in enumerate(search_results, 1):
            if enhanced:
                vector_items = tuple(
                    item.model_copy(update={"rank": rank, "query_index": query_index})
                    for rank, item in enumerate(vector_items, 1)
                )
                fts_items = tuple(
                    item.model_copy(update={"rank": rank, "query_index": query_index})
                    for rank, item in enumerate(fts_items, 1)
                )
            vector_candidates.extend(vector_items)
            fts_candidates.extend(fts_items)
            for items in (vector_items, fts_items):
                if enhanced:
                    eligible = []
                    for item in items:
                        if (
                            item.knowledge_base_id,
                            item.document_id,
                            item.document_version_id,
                            item.index_release_id,
                        ) in members:
                            eligible.append(item)
                        else:
                            exclusions.append(item)
                    rankings.append(tuple(eligible))
                else:
                    rankings.append(items)
        fused: list[Evidence] = []
        if enhanced:
            canonical: dict[tuple[UUID, UUID, UUID, str, str], Evidence] = {}
            deduplicated = []
            for ranking in rankings:
                seen_ids = set()
                unique = []
                for item in ranking:
                    key = (
                        item.knowledge_base_id,
                        item.document_id,
                        item.document_version_id,
                        item.content_hash,
                        item.content,
                    )
                    representative = canonical.setdefault(key, item)
                    if representative.chunk_id not in seen_ids:
                        unique.append(representative)
                        seen_ids.add(representative.chunk_id)
                deduplicated.append(tuple(unique))
            rankings = deduplicated
        seen_content: set[tuple[UUID, str, str]] = set()
        for item in _rrf(rankings):
            content_key = (
                item.document_version_id,
                item.content_hash,
                item.content,
            )
            if content_key in seen_content:
                continue
            seen_content.add(content_key)
            fused.append(item)
            if len(fused) >= policy.fusion_top_k:
                break
        if enhanced:
            fused = [
                item.model_copy(update={"rank": rank, "query_index": None})
                for rank, item in enumerate(fused, 1)
            ]
        if not fused:
            return RetrievalTrace(
                question,
                queries,
                release_ids,
                tuple(vector_candidates),
                tuple(fts_candidates),
                (),
                (),
                version_exclusions=tuple(exclusions),
            )
        reranked = await self.reranker.rerank(
            question,
            tuple(item.content for item in fused),
            top_n=min(policy.rerank_top_k, len(fused)),
        )
        evidence = tuple(
            fused[index].model_copy(
                update={
                    "score": score,
                    **({"rank": rank, "query_index": None} if enhanced else {}),
                }
            )
            for rank, (index, score) in enumerate(reranked, 1)
        )
        assembly = None
        decisions: tuple[EquivalenceDecision, ...] = ()
        equivalence_errors: tuple[str, ...] = ()
        conflict_result = None
        selected_evidence = evidence
        parent_ids = tuple(dict.fromkeys(item.parent_id for item in evidence))
        if parent_ids and all(item is not None for item in parent_ids):
            parents = await self.repository.get_parents(
                tenant_id=tenant_id,
                index_release_ids=release_ids,
                parent_ids=tuple(item for item in parent_ids if item is not None),
            )
            if enhanced:
                validate_parents(evidence, parents)
                try:
                    stored_vectors = await self.repository.get_chunk_vectors(
                        tenant_id=tenant_id,
                        index_release_ids=release_ids,
                        chunk_ids=tuple(item.chunk_id for item in evidence),
                    )
                    selected_evidence, decisions = await verify_equivalence(
                        evidence,
                        parents,
                        stored_vectors,
                        question=question,
                        threshold=float(policy.similarity_candidate_threshold),
                        pair_limit=policy.similarity_pair_limit,
                        gateway=gateway,
                        stage_bound=any(
                            b.stage_key == "equivalence" for b in bundle.prompt_bindings
                        ),
                    )
                # 可选向量核验失败不丢候选，父原文校验和 Rerank 仍保持失败关闭。
                except Exception as error:  # noqa: BLE001
                    equivalence_errors = (getattr(error, "code", type(error).__name__),)
            shared_prompt_tokens = sum(
                count_tokens(message.content_template)
                for binding in bundle.prompt_bindings
                if binding.stage_key in {"safety", "identity"}
                for message in binding.messages
            )
            stage_prompt_tokens = {
                stage: sum(
                    count_tokens(message.content_template)
                    for binding in bundle.prompt_bindings
                    if binding.stage_key == stage
                    for message in binding.messages
                )
                for stage in (
                    "citation",
                    "general_advice",
                    "sufficiency",
                    "answer_company",
                    "answer_mixed",
                    "answer_repair",
                )
            }
            answer_prompt_tokens = max(
                (
                    stage_prompt_tokens["answer_company"],
                    stage_prompt_tokens["answer_mixed"]
                    + stage_prompt_tokens["general_advice"],
                    stage_prompt_tokens["answer_repair"],
                ),
                default=0,
            )
            evidence_prompt_tokens = max(
                stage_prompt_tokens["sufficiency"],
                stage_prompt_tokens["citation"] + answer_prompt_tokens,
            )
            limit = min(
                policy.context_token_limit, bundle.model_policy.max_input_tokens
            )
            reserve = (
                count_tokens(question)
                + shared_prompt_tokens
                + evidence_prompt_tokens
                + bundle.model_policy.max_output_tokens
                + max(256, limit // 10)
            )
            options = (
                {
                    "final_evidence_top_k": getattr(policy, "final_evidence_top_k", 8),
                    "adjacent_group_max_parents": getattr(
                        policy, "adjacent_group_max_parents", 3
                    ),
                }
                if enhanced
                else {}
            )
            if enhanced:
                pending = assemble_evidence(
                    selected_evidence,
                    parents,
                    context_token_limit=sum(p.token_count for p in parents) + 1,
                    reserved_tokens=0,
                    **options,
                )
                conflict_result = await screen_conflicts(
                    pending.candidate_parents,
                    question=question,
                    gateway=gateway,
                    members=members,
                    stage_bound=any(
                        b.stage_key == "conflict_screen" for b in bundle.prompt_bindings
                    ),
                )
            assembly = assemble_evidence(
                selected_evidence,
                parents,
                context_token_limit=limit,
                reserved_tokens=reserve,
                **options,
            )
            if conflict_result is not None and conflict_result.blocked:
                # 冲突两侧保留供回放，Graph 禁止继续充分性和回答模型调用。
                assembly = replace(
                    pending,
                    context_token_limit=limit,
                    used_tokens=pending.used_tokens + reserve,
                )
        elif any(item is not None for item in parent_ids):
            raise ValueError("MIXED_PARENT_INDEX_INVALID")
        return RetrievalTrace(
            question,
            queries,
            release_ids,
            tuple(vector_candidates),
            tuple(fts_candidates),
            tuple(fused),
            evidence,
            assembly,
            decisions,
            tuple(exclusions),
            equivalence_errors,
            conflict_result,
        )


def _rrf(rankings: list[tuple[Evidence, ...]], constant: int = 60) -> list[Evidence]:
    scores: dict[UUID, float] = {}
    values: dict[UUID, Evidence] = {}
    for ranking in rankings:
        for rank, item in enumerate(ranking, 1):
            values[item.chunk_id] = item
            scores[item.chunk_id] = scores.get(item.chunk_id, 0.0) + 1.0 / (
                constant + rank
            )
    return [
        values[key].model_copy(update={"score": score})
        for key, score in sorted(
            scores.items(), key=lambda pair: (-pair[1], str(pair[0]))
        )
    ]


__all__ = [
    "CustomerServiceRetrieval",
    "RetrievalRepository",
    "RetrievalTrace",
]
