"""统一 ContextBuilder/ModelRuntime 上的研究候选端口；候选不成为事实。"""

from __future__ import annotations

import hashlib
import json
import logging
import re
import time
from dataclasses import replace
from typing import Literal, Protocol
from urllib.parse import urlsplit

from pydantic import BaseModel, ConfigDict, Field, ValidationError, model_validator

from efficiency_platform_agent.capabilities.model.runtime import ModelLeaseContext
from efficiency_platform_agent.context.builder import ContextBuilder, ContextBuildError
from efficiency_platform_agent.contracts.intent_v2 import BudgetLeaseReferenceV2
from efficiency_platform_agent.contracts.research_evidence_v2 import (
    EventClusterV2,
    EvidenceRefV2,
    SourceDocumentV2,
)
from efficiency_platform_agent.contracts.research_v2 import (
    BudgetSnapshotV2,
    CollectionActionV2,
    CollectionHistoryV2,
    CollectionPlanV2,
    QualityReportV2,
    ResearchBriefV2,
    build_collection_action_id,
)
from efficiency_platform_agent.core.budget import RemainingBudget
from efficiency_platform_agent.core.budget_execution import (
    BudgetExecutionBinding,
    bind_budget_execution,
)
from efficiency_platform_agent.core.model import (
    ModelDemand,
    ModelExecutionResult,
    ModelTier,
)
from efficiency_platform_agent.core.run import (
    ExecutionBudget,
    JsonObject,
    ProviderMessage,
    ProviderRequest,
    RunContext,
    RunRequest,
)
from efficiency_platform_agent.prompts.contracts import PromptValue
from efficiency_platform_agent.prompts.registry import (
    PromptRegistry,
    register_research_v2_prompts,
)
from efficiency_platform_agent.prompts.runtime import PromptAssembler, PromptRuntime

from .claims import ClaimProposalV2, _validate_proposal
from .clustering import ClusterBucketV2, ClusterProposalV2
from .evidence import EvidenceContextV2, EvidenceValidator
from .filtering import (
    RELEVANCE_PROMPT_VERSION,
    SemanticRelevanceDecisionV2,
)

logger = logging.getLogger(__name__)
stage_logger = logging.getLogger("efficiency_platform_agent.execution")


class ResearchModelRuntime(Protocol):
    async def complete(
        self,
        demand: ModelDemand,
        request: ProviderRequest,
        *,
        remaining_budget: RemainingBudget,
        lease_context: ModelLeaseContext,
    ) -> ModelExecutionResult: ...


class SearchActionProposalV2(BaseModel):
    """模型只提出查询策略；范围、需求和动作标识由运行时注入。"""

    model_config = ConfigDict(extra="forbid", frozen=True)
    gap_id: str = Field(min_length=1, max_length=128)
    source_id: str = Field(min_length=1, max_length=128)
    action_kind: Literal[
        "search_alternative",
        "search_required_facet",
        "locate_primary",
        "fetch_content",
        "verify_time",
        "resolve_conflict",
        "observe_heat",
        "retry_or_alternate",
        "switch_free_source",
        "verify_history",
        "rerender_only",
    ]
    query: str = Field(min_length=1, max_length=2_000)
    cursor: str | None = Field(default=None, min_length=1, max_length=2_000)


class PlanSelectionV2(BaseModel):
    """兼容旧动作选择，同时允许模型提出经运行时重建的查询动作。"""

    model_config = ConfigDict(extra="forbid", frozen=True)
    action_ids: tuple[str, ...] = Field(default=(), max_length=128)
    proposals: tuple[SearchActionProposalV2, ...] = Field(default=(), max_length=128)
    stop_reason: str | None = Field(default=None, max_length=128)

    @model_validator(mode="after")
    def validate_mode(self) -> PlanSelectionV2:
        if self.action_ids and self.proposals:
            raise ValueError("PLAN_SELECTION_MODE_CONFLICT")
        return self


class RelevanceDecisionBatchV2(BaseModel):
    """一次模型调用内返回有界的相关性判定，避免重复发送相同简报。"""

    model_config = ConfigDict(extra="forbid", frozen=True)
    decisions: tuple[SemanticRelevanceDecisionV2, ...] = Field(
        default=(), max_length=20
    )


class ClusterProposalBatchV2(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    proposals: tuple[ClusterProposalV2, ...] = Field(default=(), max_length=128)


class ClaimProposalBatchV2(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    proposals: tuple[ClaimProposalV2, ...] = Field(default=(), max_length=128)


class ResearchModelDecisions:
    def __init__(
        self,
        *,
        model_runtime: ResearchModelRuntime,
        context_builder: ContextBuilder,
        run_context: RunContext,
        binding: BudgetExecutionBinding,
        brief: ResearchBriefV2,
        remaining_budget: RemainingBudget,
        prompt_runtime: PromptRuntime | None = None,
        prompt_assembler: PromptAssembler | None = None,
        deterministic_fallback: bool = False,
    ) -> None:
        if (run_context.tenant_id, run_context.run_id, binding.lease_id) != (
            brief.trusted_context.tenant_id,
            brief.trusted_context.run_id,
            brief.trusted_context.budget_lease_id,
        ) or (binding.scope.tenant_id, binding.scope.run_id) != (
            run_context.tenant_id,
            run_context.run_id,
        ):
            raise ValueError("RESEARCH_MODEL_SCOPE_MISMATCH")
        if not isinstance(context_builder, ContextBuilder):
            raise TypeError("RESEARCH_CONTEXT_BUILDER_REQUIRED")
        self.model_runtime, self.context_builder = model_runtime, context_builder
        self.run_context, self.binding, self.brief = run_context, binding, brief
        self.remaining_budget = remaining_budget
        self.deterministic_fallback = deterministic_fallback
        self.prompt_assembler = prompt_assembler
        registry = PromptRegistry()
        register_research_v2_prompts(registry)
        self.prompts = prompt_runtime or PromptRuntime(registry)
        self.model_calls = 0
        self._prompt_invocations: dict[str, int] = {}

    async def invoke(
        self,
        prompt_id: str,
        variables: dict[str, str],
        payload: dict[str, object],
        lease: BudgetLeaseReferenceV2,
    ) -> object:
        if self.deterministic_fallback:
            logger.info(
                "event=research_model_deterministic_mode run_id=%s prompt_id=%s",
                self.run_context.run_id,
                prompt_id,
            )
            return self._deterministic_decision(prompt_id, payload)
        if (
            lease.lease_id != self.binding.lease_id
            or lease.version > self.binding.version
        ):
            raise ValueError("RESEARCH_MODEL_SCOPE_MISMATCH")
        body = json.dumps(payload, ensure_ascii=False)
        prompt_messages: tuple[ProviderMessage, ...]
        if self.prompt_assembler is not None and prompt_id == "research.v2.replan":
            invocation = self._prompt_invocations.get(prompt_id, 0) + 1
            self._prompt_invocations[prompt_id] = invocation
            assembled = await self.prompt_assembler.assemble(
                run_id=self.run_context.run_id,
                stage=f"{prompt_id}.{invocation}",
                prompt_key="research.plan",
                variables={
                    "user_request": PromptValue(self.brief.topic, "user_input"),
                    "context_payload": PromptValue(
                        {"schemas": variables, "research_state": payload},
                        "research_data",
                    ),
                },
            )
            prompt_messages = tuple(
                ProviderMessage(message.role, message.content)
                for message in assembled.messages
            )
            rendered_chars = assembled.rendered_chars
        else:
            prompt = self.prompts.render(prompt_id, variables)
            prompt_messages = (*prompt.messages, ProviderMessage("user", body))
            rendered_chars = prompt.rendered_chars
        snapshot = await self.binding.port.snapshot(self.binding.scope)
        self.binding.update_version(snapshot.version)
        remaining = replace(
            self.remaining_budget,
            input_tokens=min(
                self.remaining_budget.input_tokens,
                max(
                    0,
                    snapshot.limits.max_input_tokens
                    - snapshot.used.input_tokens
                    - snapshot.reserved.input_tokens,
                ),
            ),
            output_tokens=min(
                self.remaining_budget.output_tokens,
                max(
                    0,
                    snapshot.limits.max_output_tokens
                    - snapshot.used.output_tokens
                    - snapshot.reserved.output_tokens
                    - snapshot.limits.output_token_reserve,
                ),
            ),
            cost_microunits=min(
                self.remaining_budget.cost_microunits,
                max(
                    0,
                    snapshot.limits.max_cost_microunits
                    - snapshot.used.cost_microunits
                    - snapshot.reserved.cost_microunits,
                ),
            ),
        )
        budget = ExecutionBudget(
            1,
            0,
            remaining.input_tokens,
            remaining.output_tokens,
            remaining.timeout_ms,
            remaining.cost_microunits,
        )
        built = None
        try:
            built = self.context_builder.build(
                RunRequest(
                    prompt_id,
                    self.run_context.tenant_id,
                    self.run_context.user_id,
                    body,
                ),
                self.run_context,
                budget,
                frozenset(),
            )
        except ContextBuildError:
            pass
        if built is None:
            raise ValueError("RESEARCH_MODEL_CONTEXT_TOO_LARGE")
        input_tokens = built.estimated_input_tokens + (rendered_chars + 3) // 4
        if input_tokens > remaining.input_tokens:
            raise ValueError("RESEARCH_MODEL_CONTEXT_TOO_LARGE")
        prefix, version = await self.binding.next_invocation("research-model")
        context = ModelLeaseContext(
            self.binding.port, self.binding.scope, prefix, version
        )
        demand = ModelDemand(
            prompt_id,
            ModelTier.BALANCED,
            True,
            False,
            input_tokens,
            min(8_000, remaining.output_tokens),
        )
        request = ProviderRequest(
            "2",
            prompt_messages,
            JsonObject(
                (
                    (
                        "response_format",
                        JsonObject((("type", "json_object"),)),
                    ),
                )
            ),
            min(90_000, remaining.timeout_ms),
        )
        started = time.monotonic()
        stage_logger.info(
            "event=research_model_started run_id=%s prompt_id=%s payload_fields=%s",
            self.run_context.run_id,
            prompt_id,
            len(payload),
        )
        with bind_budget_execution(self.binding):
            try:
                execution = await self.model_runtime.complete(
                    demand, request, remaining_budget=remaining, lease_context=context
                )
            except Exception as exc:
                logger.warning(
                    "event=research_model_failed run_id=%s prompt_id=%s error_type=%s elapsed_ms=%s",
                    self.run_context.run_id,
                    prompt_id,
                    type(exc).__name__,
                    int((time.monotonic() - started) * 1000),
                )
                raise
            finally:
                self.binding.update_version(context.version)
        self.model_calls += len(execution.attempts)
        if (
            execution.result.error is not None
            and execution.result.error.code == "BUDGET_EXHAUSTED"
        ):
            logger.warning(
                "event=research_model_failed run_id=%s prompt_id=%s reason=BUDGET_EXHAUSTED attempts=%s elapsed_ms=%s",
                self.run_context.run_id,
                prompt_id,
                len(execution.attempts),
                int((time.monotonic() - started) * 1000),
            )
            raise ValueError("RESEARCH_MODEL_BUDGET_EXHAUSTED")
        if execution.result.error is not None or execution.result.message is None:
            logger.warning(
                "event=research_model_failed run_id=%s prompt_id=%s reason=PROVIDER_UNAVAILABLE attempts=%s elapsed_ms=%s",
                self.run_context.run_id,
                prompt_id,
                len(execution.attempts),
                int((time.monotonic() - started) * 1000),
            )
            raise ValueError("RESEARCH_MODEL_UNAVAILABLE")
        content = execution.result.message.content
        value = None
        if isinstance(content, str) and len(content) <= 100_000:
            try:
                value = json.loads(content)
            except (ValueError, TypeError):
                pass
        if value is None:
            logger.warning(
                "event=research_model_failed run_id=%s prompt_id=%s reason=DECISION_INVALID attempts=%s content_type=%s content_chars=%s elapsed_ms=%s",
                self.run_context.run_id,
                prompt_id,
                len(execution.attempts),
                type(content).__name__,
                len(content) if isinstance(content, str) else 0,
                int((time.monotonic() - started) * 1000),
            )
            raise ValueError("RESEARCH_MODEL_DECISION_INVALID")
        stage_logger.info(
            "event=research_model_succeeded run_id=%s prompt_id=%s attempts=%s total_model_calls=%s degraded=%s elapsed_ms=%s",
            self.run_context.run_id,
            prompt_id,
            len(execution.attempts),
            self.model_calls,
            bool(getattr(execution, "degraded", False)),
            int((time.monotonic() - started) * 1000),
        )
        return value

    def _deterministic_decision(
        self, prompt_id: str, payload: dict[str, object]
    ) -> object:
        """模型不可用时只从已采集事实生成保守决策，不补充外部事实。"""
        if prompt_id == "research.v2.replan":
            actions = payload.get("allowed_actions")
            if not isinstance(actions, list):
                raise ValueError("RESEARCH_MODEL_DECISION_INVALID")
            return {
                "action_ids": [
                    item["action_id"]
                    for item in actions
                    if isinstance(item, dict) and isinstance(item.get("action_id"), str)
                ],
                "stop_reason": None,
            }
        if prompt_id == "research.v2.cluster":
            return []
        if prompt_id == "research.v2.claims":
            return self.evidence_closure_claims(payload)
        raise ValueError("RESEARCH_MODEL_DECISION_INVALID")

    def evidence_closure_claims(
        self, payload: dict[str, object]
    ) -> list[dict[str, object]]:
        """只复制已保存证据，为每个事件保留一条可追溯的最小 Claim。"""
        events = payload.get("events")
        context = payload.get("evidence_context")
        if not isinstance(events, list) or not isinstance(context, dict):
            raise ValueError("RESEARCH_MODEL_DECISION_INVALID")  # noqa: TRY004
        refs = context.get("evidence_refs")
        documents = context.get("documents")
        if not isinstance(refs, list) or not isinstance(documents, list):
            raise ValueError("RESEARCH_MODEL_DECISION_INVALID")  # noqa: TRY004
        ref_by_document = {
            item.get("document_id"): item
            for item in refs
            if isinstance(item, dict)
            and isinstance(item.get("document_id"), str)
            and isinstance(item.get("excerpt"), str)
        }
        document_by_id = {
            item.get("document_id"): item
            for item in documents
            if isinstance(item, dict) and isinstance(item.get("document_id"), str)
        }
        results: list[dict[str, object]] = []
        for event in events:
            if not isinstance(event, dict):
                continue
            event_id = event.get("event_id")
            document_id = event.get("representative_document_id")
            ref = ref_by_document.get(document_id)
            document = document_by_id.get(document_id)
            if (
                not isinstance(event_id, str)
                or not isinstance(ref, dict)
                or not isinstance(document, dict)
            ):
                continue
            excerpt = _without_urls(str(ref["excerpt"]))
            if not excerpt:
                continue
            digest = hashlib.sha256(
                f"{event_id}:{ref['evidence_id']}".encode()
            ).hexdigest()[:24]
            results.append(
                {
                    "proposal_id": f"claim-proposal-{digest}",
                    "claim_key": f"source-excerpt-{digest}",
                    "brief_digest": self.brief.canonical_digest(),
                    "prompt_version": "research.v2.claims@1.0.0",
                    "event_id": event_id,
                    "text": excerpt[:4000],
                    "claim_type": "reported_fact",
                    "subject": excerpt[: min(128, len(excerpt))],
                    "value_text": None,
                    "numeric_value": None,
                    "unit": None,
                    "claim_time": event.get("event_time"),
                    "assertion_mode": "attributed",
                    "attributed_to": str(document.get("publisher_id") or "公开来源"),
                    "support_refs": [ref["evidence_id"]],
                }
            )
        return results

    async def relevance(
        self,
        brief: ResearchBriefV2,
        documents: tuple[SourceDocumentV2, ...],
        lease: BudgetLeaseReferenceV2,
    ) -> tuple[SemanticRelevanceDecisionV2, ...]:
        if brief != self.brief:
            raise ValueError("RESEARCH_MODEL_SCOPE_MISMATCH")
        if self.deterministic_fallback:
            topic_requirement_ids = tuple(
                item.requirement_id
                for item in brief.hard_requirements
                if item.dimension == "topic"
            )
            return tuple(
                SemanticRelevanceDecisionV2(
                    document_id=document.document_id,
                    document_content_hash=document.content_hash,
                    brief_digest=brief.canonical_digest(),
                    outcome=(
                        "relevant"
                        if _deterministically_relevant(brief.topic, document)
                        else "uncertain"
                    ),
                    requirement_ids=topic_requirement_ids,
                    source_excerpt=document.text[:2000],
                    prompt_version=RELEVANCE_PROMPT_VERSION,
                )
                for document in documents
            )
        selected_documents = _select_relevance_candidates(brief, documents)
        if not selected_documents:
            return ()
        value = await self.invoke(
            "research.v2.relevance",
            {
                "brief_schema": _schema(ResearchBriefV2),
                "decision_schema": _schema(RelevanceDecisionBatchV2),
            },
            {
                "brief": brief.model_dump(mode="json"),
                "brief_digest": brief.canonical_digest(),
                "documents": [
                    document.model_dump(mode="json")
                    for document in selected_documents
                ],
                "prompt_version": RELEVANCE_PROMPT_VERSION,
            },
            lease,
        )
        batched = isinstance(value, dict) and "decisions" in value
        if batched:
            parsed_decisions = _parse(RelevanceDecisionBatchV2, value).decisions
        else:
            # 保留旧单文档模型桩兼容性；真实 Prompt 只请求批量对象。
            parsed_decisions = (_parse(SemanticRelevanceDecisionV2, value),)
        documents_by_id = {
            document.document_id: document for document in selected_documents
        }
        if len({item.document_id for item in parsed_decisions}) != len(
            parsed_decisions
        ) or not {item.document_id for item in parsed_decisions}.issubset(
            documents_by_id
        ):
            logger.warning(
                "event=research_relevance_rejected run_id=%s invalid_fields=document_set",
                self.run_context.run_id,
            )
            raise ValueError("RESEARCH_MODEL_DECISION_INVALID")
        results = []
        for decision in parsed_decisions:
            document = documents_by_id[decision.document_id]
            allowed_requirement_ids = {
                item.requirement_id for item in brief.hard_requirements
            }
            source_text = f"{document.title}\n{document.text}"
            invalid_fields = tuple(
                name
                for name, invalid in (
                    ("document_id", decision.document_id != document.document_id),
                    (
                        "document_content_hash",
                        decision.document_content_hash != document.content_hash,
                    ),
                    ("brief_digest", decision.brief_digest != brief.canonical_digest()),
                    (
                        "prompt_version",
                        decision.prompt_version != RELEVANCE_PROMPT_VERSION,
                    ),
                    ("source_excerpt", decision.source_excerpt not in source_text),
                    (
                        "requirement_ids",
                        not set(decision.requirement_ids).issubset(
                            allowed_requirement_ids
                        ),
                    ),
                )
                if invalid
            )
            if invalid_fields:
                logger.warning(
                    "event=research_relevance_rejected run_id=%s invalid_fields=%s",
                    self.run_context.run_id,
                    ",".join(invalid_fields),
                )
                if batched:
                    continue
                raise ValueError("RESEARCH_MODEL_DECISION_INVALID")
            results.append(decision)
        return tuple(results)


def _select_relevance_candidates(
    brief: ResearchBriefV2,
    documents: tuple[SourceDocumentV2, ...],
    limit: int | None = None,
) -> tuple[SourceDocumentV2, ...]:
    """先执行确定性门禁，再按来源轮询选择有界的模型复核集合。"""

    if limit is None:
        limit = max(10, min(20, brief.count_policy.target + 5))
    eligible = list(documents)
    by_source: dict[str, list[SourceDocumentV2]] = {}
    for document in eligible:
        by_source.setdefault(document.source_id, []).append(document)
    for values in by_source.values():
        values.sort(
            key=lambda item: (
                _deterministically_relevant(brief.topic, item),
                *_relevance_candidate_sort_key(item),
            ),
            reverse=True,
        )
    selected: list[SourceDocumentV2] = []
    for source_id in sorted(by_source):
        selected.append(by_source[source_id].pop(0))
        if len(selected) >= limit:
            return tuple(selected)
    for relevant in (True, False):
        active = {
            source_id: [
                item
                for item in values
                if _deterministically_relevant(brief.topic, item) is relevant
            ]
            for source_id, values in by_source.items()
        }
        active = {source_id: values for source_id, values in active.items() if values}
        while active and len(selected) < limit:
            for source_id in tuple(sorted(active)):
                values = active[source_id]
                item = values.pop(0)
                selected.append(item)
                by_source[source_id].remove(item)
                if not values:
                    del active[source_id]
                if len(selected) >= limit:
                    break
        if len(selected) >= limit:
            break
    return tuple(selected)


def _relevance_candidate_sort_key(document: SourceDocumentV2) -> tuple[float, str]:
    timestamp = (
        document.event_at
        or document.first_published_at
        or document.published_at
        or document.updated_at
        or document.first_seen_at
        or document.fetched_at
    )
    return (timestamp.timestamp() if timestamp is not None else float("-inf"), document.document_id)


def _deterministically_relevant(topic: str, document: SourceDocumentV2) -> bool:
    text = f"{document.title}\n{document.text}".casefold()
    if len(" ".join(document.text.split())) < 20:
        return False
    topic_text = topic.casefold()
    broad_ai = any(marker in topic_text for marker in ("ai", "人工智能", "大模型"))
    if broad_ai and any(
        marker in text
        for marker in (
            " ai ",
            "artificial intelligence",
            "language model",
            "llm",
            "machine learning",
            "agent",
            "模型",
            "人工智能",
        )
    ):
        return True
    terms = {
        item
        for item in re.findall(r"[a-z0-9][a-z0-9.+-]{1,31}|[\u4e00-\u9fff]{2,12}", topic_text)
        if item not in {"相关", "热点", "话题", "今天", "最新", "收集", "给出", "最热"}
    }
    return any(
        (
            re.search(rf"(?<![a-z0-9]){re.escape(term)}(?![a-z0-9])", text)
            is not None
            if term.isascii()
            else term in text
        )
        for term in terms
        if term != "ai"
    )


def _without_urls(value: str) -> str:
    """保留证据原词序，仅移除不允许进入 Claim 提案的 URL token。"""
    cleaned = re.sub(r"(?:https?://|www\.)\S+", "", value, flags=re.IGNORECASE)
    return " ".join(cleaned.split()).strip()


class ResearchPlanModelAdapter:
    def __init__(
        self, decisions: ResearchModelDecisions, actions: tuple[CollectionActionV2, ...]
    ) -> None:
        self.decisions, self.actions = decisions, actions

    async def propose(
        self,
        brief: ResearchBriefV2,
        quality: QualityReportV2,
        history: CollectionHistoryV2,
        budget: BudgetSnapshotV2,
    ) -> CollectionPlanV2:
        value = await self.decisions.invoke(
            "research.v2.replan",
            {
                "brief_schema": _schema(ResearchBriefV2),
                "quality_schema": _schema(QualityReportV2),
                "plan_schema": _schema(PlanSelectionV2),
                "action_policy": (
                    "优先返回 proposals。每项只能使用 allowed_actions 中已有的 gap_id、"
                    "source_id 和 action_kind，但 query 应根据当前缺口提出新的具体检索词；"
                    "不得生成 URL，不得扩大时间范围。兼容模式可只返回 action_ids。"
                    "无可执行动作时返回 PLAN_EXHAUSTED。"
                ),
            },
            {
                "brief": brief.model_dump(mode="json"),
                "quality": quality.model_dump(mode="json"),
                "history": history.model_dump(mode="json"),
                "budget": budget.model_dump(mode="json"),
                "allowed_actions": [
                    item.model_dump(mode="json") for item in self.actions
                ],
            },
            BudgetLeaseReferenceV2(lease_id=budget.lease_id, version=budget.version),
        )
        selected = _parse(PlanSelectionV2, value)
        available = {item.action_id: item for item in self.actions}
        if selected.proposals:
            templates = {
                (item.gap_id, item.source_id, item.action_kind): item
                for item in self.actions
            }
            gaps = {item.gap_id: item for item in quality.gaps}
            materialized: list[CollectionActionV2] = []
            for proposal in selected.proposals:
                template = templates.get(
                    (proposal.gap_id, proposal.source_id, proposal.action_kind)
                )
                gap = gaps.get(proposal.gap_id)
                if (
                    template is None
                    or gap is None
                    or re.search(r"(?:https?://|www\.)", proposal.query, re.IGNORECASE)
                ):
                    raise ValueError("RESEARCH_MODEL_DECISION_INVALID")
                action_id = build_collection_action_id(
                    brief.intent_revision,
                    gap,
                    proposal.source_id,
                    proposal.query,
                    proposal.cursor,
                )
                materialized.append(
                    template.model_copy(
                        update={
                            "action_id": action_id,
                            "query": proposal.query,
                            "cursor": proposal.cursor,
                        }
                    )
                )
            if len({item.action_id for item in materialized}) != len(materialized):
                raise ValueError("RESEARCH_MODEL_DECISION_INVALID")
            actions = tuple(materialized)
        else:
            if len(set(selected.action_ids)) != len(selected.action_ids) or not set(
                selected.action_ids
            ).issubset(available):
                raise ValueError("RESEARCH_MODEL_DECISION_INVALID")
            actions = tuple(available[item] for item in selected.action_ids)
        return CollectionPlanV2(
            actions=actions,
            stop_reason=selected.stop_reason
            or (None if actions else "PLAN_EXHAUSTED"),
        )


class ResearchClusterModelAdapter:
    def __init__(self, decisions: ResearchModelDecisions) -> None:
        self.decisions = decisions

    async def propose(
        self,
        bucket: ClusterBucketV2,
        brief: ResearchBriefV2,
        lease: BudgetLeaseReferenceV2,
    ) -> tuple[ClusterProposalV2, ...]:
        value = await self.decisions.invoke(
            "research.v2.cluster",
            {
                "brief_schema": _schema(ResearchBriefV2),
                "proposal_schema": _schema(ClusterProposalBatchV2),
            },
            {
                "brief": brief.model_dump(mode="json"),
                "bucket": bucket.model_dump(mode="json"),
                "prompt_version": "research.v2.cluster@1.0.0",
            },
            lease,
        )
        proposals = (
            _parse(ClusterProposalBatchV2, value).proposals
            if isinstance(value, dict) and "proposals" in value
            else _parse_many(ClusterProposalV2, value)
        )
        if any(
            _contains_cluster_url(proposal.model_dump(mode="json"))
            or any(
                member.document_id not in {doc.document_id for doc in bucket.documents}
                for member in proposal.members
            )
            for proposal in proposals
        ):
            raise ValueError("RESEARCH_MODEL_DECISION_INVALID")
        return proposals


def _contains_cluster_url(value: object) -> bool:
    """逐字符串解析 URL；协议相对地址只在字段开头识别，保留自然文本。"""
    if isinstance(value, dict):
        return any(_contains_cluster_url(item) for item in value.values())
    if isinstance(value, list):
        return any(_contains_cluster_url(item) for item in value)
    if not isinstance(value, str):
        return False
    candidates = re.findall(r"[a-z][a-z0-9+.-]*://[^\s<>\"']+", value, re.IGNORECASE)
    stripped = value.lstrip()
    if stripped.startswith("//"):
        candidates.append(stripped)
    candidates.extend(
        "https://" + item
        for item in re.findall(r"\bwww\.[^\s<>\"']+", value, re.IGNORECASE)
    )
    for candidate in candidates:
        try:
            parsed = urlsplit(candidate)
            if parsed.hostname and not any(char.isspace() for char in parsed.netloc):
                return True
            if parsed.scheme.lower() == "file" and parsed.path.startswith("/"):
                return True
        except ValueError:
            # URL 形式却无法解析的模型字段仍失败关闭，不作为事件事实。
            return True
    return False


class ResearchClaimModelAdapter:
    def __init__(
        self,
        decisions: ResearchModelDecisions,
        *,
        minimum_valid_event_count: int | None = None,
    ) -> None:
        self.decisions = decisions
        self.minimum_valid_event_count = minimum_valid_event_count

    async def propose(
        self,
        events: tuple[EventClusterV2, ...],
        evidence_context: EvidenceContextV2,
        lease: BudgetLeaseReferenceV2,
    ) -> tuple[ClaimProposalV2, ...]:
        schemas = {
            "event_schema": _schema(EventClusterV2),
            "evidence_schema": _schema(EvidenceRefV2),
            "claim_schema": _schema(ClaimProposalBatchV2),
        }
        event_ids = {event.event_id for event in events}
        evidence_ids = {ref.evidence_id for ref in evidence_context.evidence_refs}

        async def request(selected: tuple[EventClusterV2, ...]) -> tuple[ClaimProposalV2, ...]:
            payload: dict[str, object] = {
                "events": [item.model_dump(mode="json") for item in selected],
                "evidence_context": evidence_context.model_dump(mode="json"),
                "prompt_version": "research.v2.claims@1.0.0",
            }
            allowed_event_ids = {event.event_id for event in selected}
            for attempt in range(2):
                value = await self.decisions.invoke(
                    "research.v2.claims", schemas, payload, lease
                )
                parsed = (
                    _parse(ClaimProposalBatchV2, value).proposals
                    if isinstance(value, dict) and "proposals" in value
                    else _parse_many(ClaimProposalV2, value)
                )
                policy_results = tuple(
                    (
                        proposal.event_id in allowed_event_ids,
                        re.search(
                            r"https?://",
                            proposal.model_dump_json(),
                            flags=re.IGNORECASE,
                        )
                        is None,
                        set(proposal.support_refs).issubset(evidence_ids),
                    )
                    for proposal in parsed
                )
                unknown_events = sum(not result[0] for result in policy_results)
                urls = sum(not result[1] for result in policy_results)
                unknown_refs = sum(not result[2] for result in policy_results)
                if unknown_events == 0 and urls == 0 and unknown_refs == 0:
                    return parsed
                safe = tuple(
                    proposal
                    for proposal, result in zip(parsed, policy_results, strict=True)
                    if all(result)
                )
                logger.warning(
                    "event=research_claim_policy_rejected run_id=%s attempt=%s unknown_events=%s urls=%s unknown_refs=%s retained=%s",
                    self.decisions.run_context.run_id,
                    attempt + 1,
                    unknown_events,
                    urls,
                    unknown_refs,
                    len(safe),
                )
                if safe:
                    return safe
                payload = {
                    **payload,
                    "validation_feedback": (
                        "上次输出包含未授权事件、URL 或证据引用；"
                        "请仅使用输入原值重新输出。"
                    ),
                }
            raise ValueError("RESEARCH_MODEL_DECISION_INVALID")

        proposals = await request(events)
        events_by_id = {event.event_id: event for event in events}
        documents_by_id = {
            document.document_id: document for document in evidence_context.documents
        }
        evidence_by_id = {
            ref.evidence_id: ref for ref in evidence_context.evidence_refs
        }
        valid_proposals = tuple(
            proposal
            for proposal in proposals
            if not _validate_proposal(
                proposal,
                evidence_context,
                events_by_id,
                documents_by_id,
                evidence_by_id,
                EvidenceValidator(),
            )
        )
        valid_event_ids = {proposal.event_id for proposal in valid_proposals}
        missing = tuple(event for event in events if event.event_id not in valid_event_ids)
        required_count = min(
            len(events),
            self.minimum_valid_event_count
            if self.minimum_valid_event_count is not None
            else len(events),
        )
        if missing and len(valid_event_ids) < required_count:
            missing = missing[: required_count - len(valid_event_ids)]
            logger.info(
                "event=research_claim_model_retry_requested run_id=%s missing=%s events=%s",
                self.decisions.run_context.run_id,
                len(missing),
                len(events),
            )
            retry = await request(missing)
            valid_retry = tuple(
                proposal
                for proposal in retry
                if not _validate_proposal(
                    proposal,
                    evidence_context,
                    events_by_id,
                    documents_by_id,
                    evidence_by_id,
                    EvidenceValidator(),
                )
            )
            valid_proposals = (*valid_proposals, *valid_retry)
            valid_event_ids.update(
                proposal.event_id for proposal in valid_retry
            )
        still_missing = event_ids - valid_event_ids
        if still_missing:
            logger.warning(
                "event=research_claim_model_incomplete run_id=%s missing=%s",
                self.decisions.run_context.run_id,
                len(still_missing),
            )
        return valid_proposals


def _schema(model: type[BaseModel]) -> str:
    return json.dumps(model.model_json_schema(), ensure_ascii=False)


def _parse[T: BaseModel](model: type[T], value: object) -> T:
    result = None
    try:
        result = model.model_validate(value)
    except ValidationError as exc:
        logger.warning(
            "event=research_model_schema_rejected model=%s value_type=%s errors=%s",
            model.__name__,
            type(value).__name__,
            ",".join(
                f"{'.'.join(str(part) for part in item['loc'])}:{item['type']}"
                for item in exc.errors(include_input=False, include_url=False)[:12]
            ),
        )
    if result is None:
        raise ValueError("RESEARCH_MODEL_DECISION_INVALID")
    return result


def _parse_many[T: BaseModel](model: type[T], value: object) -> tuple[T, ...]:
    if not isinstance(value, list) or len(value) > 128:
        keys = ",".join(sorted(value)) if isinstance(value, dict) else ""
        logger.warning(
            "event=research_model_batch_rejected model=%s value_type=%s keys=%s",
            model.__name__,
            type(value).__name__,
            keys,
        )
        raise ValueError("RESEARCH_MODEL_DECISION_INVALID")
    return tuple(_parse(model, item) for item in value)
