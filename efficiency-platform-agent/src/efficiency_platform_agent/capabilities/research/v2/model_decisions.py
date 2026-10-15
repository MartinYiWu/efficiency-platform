"""统一 ContextBuilder/ModelRuntime 上的研究候选端口；候选不成为事实。"""

from __future__ import annotations

import json
import hashlib
import logging
import re
import time
from dataclasses import replace
from typing import Protocol
from urllib.parse import urlsplit

from pydantic import BaseModel, ConfigDict, Field, TypeAdapter, ValidationError

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
from efficiency_platform_agent.prompts.registry import (
    PromptRegistry,
    register_research_v2_prompts,
)
from efficiency_platform_agent.prompts.runtime import PromptRuntime

from .claims import ClaimProposalV2
from .clustering import ClusterBucketV2, ClusterProposalV2
from .evidence import EvidenceContextV2
from .filtering import RELEVANCE_PROMPT_VERSION, SemanticRelevanceDecisionV2

logger = logging.getLogger(__name__)


class ResearchModelRuntime(Protocol):
    async def complete(
        self,
        demand: ModelDemand,
        request: ProviderRequest,
        *,
        remaining_budget: RemainingBudget,
        lease_context: ModelLeaseContext,
    ) -> ModelExecutionResult: ...


class PlanSelectionV2(BaseModel):
    """只允许模型选择服务端生成的有限动作，不能生成 URL 或查询。"""

    model_config = ConfigDict(extra="forbid", frozen=True)
    action_ids: tuple[str, ...] = Field(default=(), max_length=128)
    stop_reason: str | None = Field(default=None, max_length=128)


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
        registry = PromptRegistry()
        register_research_v2_prompts(registry)
        self.prompts = prompt_runtime or PromptRuntime(registry)
        self.model_calls = 0

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
        prompt = self.prompts.render(prompt_id, variables)
        body = json.dumps(payload, ensure_ascii=False)
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
        input_tokens = built.estimated_input_tokens + (prompt.rendered_chars + 3) // 4
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
            (*prompt.messages, ProviderMessage("user", body)),
            JsonObject(),
            min(90_000, remaining.timeout_ms),
        )
        started = time.monotonic()
        logger.info(
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
                "event=research_model_failed run_id=%s prompt_id=%s reason=DECISION_INVALID attempts=%s elapsed_ms=%s",
                self.run_context.run_id,
                prompt_id,
                len(execution.attempts),
                int((time.monotonic() - started) * 1000),
            )
            raise ValueError("RESEARCH_MODEL_DECISION_INVALID")
        logger.info(
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
            return self._deterministic_claims(payload)
        raise ValueError("RESEARCH_MODEL_DECISION_INVALID")

    def _deterministic_claims(self, payload: dict[str, object]) -> list[dict[str, object]]:
        events = payload.get("events")
        context = payload.get("evidence_context")
        if not isinstance(events, list) or not isinstance(context, dict):
            raise ValueError("RESEARCH_MODEL_DECISION_INVALID")
        refs = context.get("evidence_refs")
        documents = context.get("documents")
        if not isinstance(refs, list) or not isinstance(documents, list):
            raise ValueError("RESEARCH_MODEL_DECISION_INVALID")
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
        results = []
        for document in documents:
            value = await self.invoke(
                "research.v2.relevance",
                {
                    "brief_schema": _schema(ResearchBriefV2),
                    "decision_schema": _schema(SemanticRelevanceDecisionV2),
                },
                {
                    "brief": brief.model_dump(mode="json"),
                    "document": document.model_dump(mode="json"),
                    "prompt_version": RELEVANCE_PROMPT_VERSION,
                },
                lease,
            )
            decision = _parse(SemanticRelevanceDecisionV2, value)
            if (
                decision.document_id != document.document_id
                or decision.document_content_hash != document.content_hash
                or decision.brief_digest != brief.canonical_digest()
                or decision.prompt_version != RELEVANCE_PROMPT_VERSION
                or decision.source_excerpt not in document.text
                or not set(decision.requirement_ids).issubset(
                    item.requirement_id for item in brief.hard_requirements
                )
            ):
                raise ValueError("RESEARCH_MODEL_DECISION_INVALID")
            results.append(decision)
        return tuple(results)


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
                "action_policy": "仅选择 allowed_actions 中原样存在的 action_id；无动作返回 PLAN_EXHAUSTED。",
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
        if len(set(selected.action_ids)) != len(selected.action_ids) or not set(
            selected.action_ids
        ).issubset(available):
            raise ValueError("RESEARCH_MODEL_DECISION_INVALID")
        return CollectionPlanV2(
            actions=tuple(available[item] for item in selected.action_ids),
            stop_reason=selected.stop_reason
            or (None if selected.action_ids else "PLAN_EXHAUSTED"),
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
                "proposal_schema": json.dumps(
                    TypeAdapter(tuple[ClusterProposalV2, ...]).json_schema()
                ),
            },
            {
                "brief": brief.model_dump(mode="json"),
                "bucket": bucket.model_dump(mode="json"),
                "prompt_version": "research.v2.cluster@1.0.0",
            },
            lease,
        )
        proposals = _parse_many(ClusterProposalV2, value)
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
    def __init__(self, decisions: ResearchModelDecisions) -> None:
        self.decisions = decisions

    async def propose(
        self,
        events: tuple[EventClusterV2, ...],
        evidence_context: EvidenceContextV2,
        lease: BudgetLeaseReferenceV2,
    ) -> tuple[ClaimProposalV2, ...]:
        value = await self.decisions.invoke(
            "research.v2.claims",
            {
                "event_schema": _schema(EventClusterV2),
                "evidence_schema": _schema(EvidenceRefV2),
                "claim_schema": json.dumps(
                    TypeAdapter(tuple[ClaimProposalV2, ...]).json_schema()
                ),
            },
            {
                "events": [item.model_dump(mode="json") for item in events],
                "evidence_context": evidence_context.model_dump(mode="json"),
                "prompt_version": "research.v2.claims@1.0.0",
            },
            lease,
        )
        proposals = _parse_many(ClaimProposalV2, value)
        if any(
            proposal.event_id not in {event.event_id for event in events}
            or re.search(r"https?://", proposal.model_dump_json(), flags=re.IGNORECASE)
            is not None
            or not set(proposal.support_refs).issubset(
                ref.evidence_id for ref in evidence_context.evidence_refs
            )
            for proposal in proposals
        ):
            raise ValueError("RESEARCH_MODEL_DECISION_INVALID")
        return proposals


def _schema(model: type[BaseModel]) -> str:
    return json.dumps(model.model_json_schema(), ensure_ascii=False)


def _parse[T: BaseModel](model: type[T], value: object) -> T:
    result = None
    try:
        result = model.model_validate(value)
    except ValidationError:
        pass
    if result is None:
        raise ValueError("RESEARCH_MODEL_DECISION_INVALID")
    return result


def _parse_many[T: BaseModel](model: type[T], value: object) -> tuple[T, ...]:
    if not isinstance(value, list) or len(value) > 128:
        raise ValueError("RESEARCH_MODEL_DECISION_INVALID")
    return tuple(_parse(model, item) for item in value)
