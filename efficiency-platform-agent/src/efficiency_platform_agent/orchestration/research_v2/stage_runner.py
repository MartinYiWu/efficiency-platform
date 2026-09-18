"""正式本地研究阶段；正文留在 Run 事实库，图只传递对象 ID。"""

from __future__ import annotations

import hashlib
import time
from collections.abc import Callable, Mapping, Sequence
from datetime import UTC, datetime
from email.utils import parsedate_to_datetime
from typing import Literal, Protocol, runtime_checkable

from efficiency_platform_agent.capabilities.research.v2.acquisition import (
    AcquisitionExecutor,
    AcquisitionRuntimeContextV2,
    DiscoveryActionV2,
)
from efficiency_platform_agent.capabilities.research.v2.claims import (
    ClaimExtractor,
    ConflictResolver,
)
from efficiency_platform_agent.capabilities.research.v2.clustering import EventClusterer
from efficiency_platform_agent.capabilities.research.v2.content_acquisition import (
    ResearchContentAcquirer,
)
from efficiency_platform_agent.capabilities.research.v2.deduplication import (
    deduplicate_documents,
)
from efficiency_platform_agent.capabilities.research.v2.evidence import (
    EvidenceContextV2,
    build_evidence_ref,
)
from efficiency_platform_agent.capabilities.research.v2.filtering import (
    DocumentFilterRecordV2,
    FilterResultV2,
    filter_documents,
)
from efficiency_platform_agent.capabilities.research.v2.model_decisions import (
    ResearchClaimModelAdapter,
    ResearchClusterModelAdapter,
    ResearchModelDecisions,
    ResearchPlanModelAdapter,
)
from efficiency_platform_agent.capabilities.research.v2.normalization import normalize
from efficiency_platform_agent.capabilities.research.v2.quality import (
    CollectionCoverageV2,
    SourcePolicyDecisionV2,
    evaluate_quality,
)
from efficiency_platform_agent.capabilities.research.v2.source_families import (
    SourceFamilyResolver,
)
from efficiency_platform_agent.capabilities.research.v2.sources import (
    VerifiedSourceRegistry,
)
from efficiency_platform_agent.contracts.intent_v2 import BudgetLeaseReferenceV2
from efficiency_platform_agent.contracts.research_local_runtime_v2 import (
    LocalResearchRunFactsV2,
    LocalResearchRunKeyV2,
)
from efficiency_platform_agent.contracts.research_sources_v2 import (
    SourceAttemptV2,
    SourceRuntimeContextV2,
    SourceUsageV2,
)
from efficiency_platform_agent.contracts.research_v2 import (
    BudgetSnapshotV2,
    CollectionActionV2,
    CollectionHistoryV2,
    CollectionPlanV2,
    QualityGapV2,
    QualityReportV2,
    ResearchBriefV2,
    ResearchPolicySnapshotV2,
)
from efficiency_platform_agent.core.budget_execution import (
    BudgetExecutionBinding,
    bind_budget_execution,
)
from efficiency_platform_agent.core.budget_lease import (
    BudgetLeaseError,
    BudgetLeasePort,
    SettlementAuditRecord,
)
from efficiency_platform_agent.persistence.research_local_memory import (
    LocalResearchRunStore,
)
from efficiency_platform_agent.providers.research.extraction import (
    DocumentExtractionError,
)
from efficiency_platform_agent.tools.external.research import (
    ResearchDiscoverArgumentsV2,
)

from .graph import ResearchStage, ResearchStageRunner, ResearchStageUpdateV2
from .planner import (
    ActionValidator,
    CollectionPlanner,
    PlanningSourceRegistryV2,
    PlanningSourceV2,
    action_fingerprint,
)
from .state import ResearchGraphState


@runtime_checkable
class _AuditedBudgetPort(BudgetLeasePort, Protocol):
    @property
    def audit_records(self) -> tuple[SettlementAuditRecord, ...]: ...


class LocalLiveResearchStageRunner:
    """所有依赖由组合根按同一 Run 装配，不新建 Runtime、租约或网络限流器。"""

    def __init__(
        self,
        *,
        key: LocalResearchRunKeyV2,
        store: LocalResearchRunStore,
        brief: ResearchBriefV2,
        policy: ResearchPolicySnapshotV2,
        binding: BudgetExecutionBinding,
        registry: VerifiedSourceRegistry,
        source_context: SourceRuntimeContextV2,
        acquisition_executor: AcquisitionExecutor,
        content_acquirer: ResearchContentAcquirer,
        acquisition_context: AcquisitionRuntimeContextV2,
        decisions: ResearchModelDecisions,
        output_stages: ResearchStageRunner,
        now: Callable[[], datetime] = lambda: datetime.now(UTC),
    ) -> None:
        self.key, self.store, self.brief, self.policy, self.binding = (
            key,
            store,
            brief,
            policy,
            binding,
        )
        self.registry, self.source_context = registry, source_context
        self.executor, self.acquirer, self.context = (
            acquisition_executor,
            content_acquirer,
            acquisition_context,
        )
        self.decisions, self.output_stages, self.now = decisions, output_stages, now
        if not isinstance(binding.port, _AuditedBudgetPort):
            raise TypeError("LOCAL_RESEARCH_BUDGET_AUDIT_REQUIRED")
        self._audit_port = binding.port
        self._http_baseline = self._http_usage()
        trusted, context = brief.trusted_context, acquisition_context.run_context
        lease = acquisition_context.lease_context
        if (
            (key.tenant_id, key.run_id, key.task_id, key.revision)
            != (
                trusted.tenant_id,
                trusted.run_id,
                trusted.task_id,
                brief.intent_revision,
            )
            or (key.tenant_id, key.run_id, key.user_id)
            != (context.tenant_id, context.run_id, context.user_id)
            or (key.tenant_id, key.run_id)
            != (source_context.tenant_id, source_context.run_id)
            or (key.tenant_id, key.run_id)
            != (binding.scope.tenant_id, binding.scope.run_id)
            or binding.lease_id != trusted.budget_lease_id
            or decisions.binding is not binding
            or decisions.run_context != context
            or decisions.brief != brief
            or acquisition_executor.runtime is not content_acquirer.runtime
            or (
                lease is not None
                and (lease.port is not binding.port or lease.scope != binding.scope)
            )
            or brief.quality_policy_id != policy.quality_policy_id
            or brief.policy_version != policy.policy_version
        ):
            raise ValueError("LOCAL_RESEARCH_STAGE_SCOPE_MISMATCH")

    async def run_stage(
        self, stage: ResearchStage, state: ResearchGraphState
    ) -> ResearchStageUpdateV2:
        facts = await self.store.get(self.key)
        self._validate(state, facts)
        for stopped in ("cancelled", "hard_deadline_reached", "fatal_error"):
            if state.get(stopped):
                return ResearchStageUpdateV2.model_validate({stopped: True})
        control = self._control()
        if control is not None:
            return control
        snapshot = await self.binding.port.snapshot(self.binding.scope)
        deadline_ms = snapshot.limits.deadline_epoch_ms
        if stage not in {
            "validate",
            "quality",
            "finalize",
            "compose",
            "verify",
            "render",
        } and (
            state.get("budget_exhausted")
            or state.get("soft_deadline_reached")
            or (
                deadline_ms is not None
                and int(self.now().timestamp() * 1000)
                >= deadline_ms - snapshot.limits.output_time_reserve_ms
            )
        ):
            return self._budget_stop(
                facts, soft=not state.get("budget_exhausted", False)
            )
        with bind_budget_execution(self.binding):
            try:
                update = await self._execute(stage, state, facts)
            except BudgetLeaseError:
                update = self._budget_stop(facts)
            except ValueError as exc:
                if str(exc) in {
                    "RESEARCH_MODEL_BUDGET_EXHAUSTED",
                    "RESEARCH_MODEL_CONTEXT_TOO_LARGE",
                }:
                    update = self._budget_stop(facts)
                elif str(exc) in {
                    "RESEARCH_MODEL_UNAVAILABLE",
                    "RESEARCH_MODEL_DECISION_INVALID",
                }:
                    update = ResearchStageUpdateV2(fatal_error=True)
                else:
                    raise
        control = self._control()
        if control is not None:
            return control
        after = await self.binding.port.snapshot(self.binding.scope)
        self.binding.update_version(after.version)
        current = await self.store.get(self.key)
        http_calls, http_bytes = self._http_usage()
        resources = current.resources.model_copy(
            update={
                "http_requests": http_calls - self._http_baseline[0],
                "downloaded_bytes": http_bytes - self._http_baseline[1],
                "model_calls": self.decisions.model_calls,
            }
        )
        if resources != current.resources:
            await self._save(current, resources=resources)
        return update.model_copy(update={"budget_version": self.binding.version})

    def _budget_stop(
        self, facts: LocalResearchRunFactsV2, *, soft: bool = False
    ) -> ResearchStageUpdateV2:
        # 预算耗尽时回到最近一次已核验闭包，当前未完成轮的候选不得替换它。
        return ResearchStageUpdateV2(
            planned_action_ids=(),
            budget_exhausted=not soft,
            soft_deadline_reached=soft,
            event_ids=facts.stage_artifact_ids.get("qualified_events", ()),
            qualified_event_ids=facts.stage_artifact_ids.get("qualified_events", ()),
            claim_ids=facts.stage_artifact_ids.get("qualified_claims", ()),
            evidence_ids=facts.stage_artifact_ids.get("qualified_evidence", ()),
        )

    def _http_usage(self) -> tuple[int, int]:
        records = tuple(
            item
            for item in self._audit_port.audit_records
            if item.invocation_id.startswith("research-http-")
        )
        return sum(item.actual.calls for item in records), sum(
            item.actual.bytes for item in records
        )

    def _validate(
        self, state: ResearchGraphState, facts: LocalResearchRunFactsV2
    ) -> None:
        expected = {
            "schema_version": "research-graph-state/2",
            "brief_digest": self.brief.canonical_digest(),
            "intent_revision": self.key.revision,
            "quality_policy_id": self.policy.quality_policy_id,
            "policy_version": self.policy.policy_version,
            "budget_lease_id": self.binding.lease_id,
        }
        if (
            facts.key != self.key
            or facts.brief != self.brief
            or facts.status != "active"
            or any(state.get(k) != v for k, v in expected.items())
            or not isinstance(state.get("budget_version"), int)
            or not 0 <= state["budget_version"] <= self.binding.version
            or not 0
            <= state.get("max_refill_rounds", 2)
            <= min(2, self.policy.max_collection_rounds - 1)
        ):
            raise ValueError("LOCAL_RESEARCH_STAGE_SCOPE_MISMATCH")

    def _control(self) -> ResearchStageUpdateV2 | None:
        signal = self.executor.runtime.cancellation_signal
        if signal is not None and signal.is_requested():
            return ResearchStageUpdateV2(cancelled=True)
        if time.monotonic() >= self.context.deadline_monotonic:
            return ResearchStageUpdateV2(hard_deadline_reached=True)
        return None

    async def _save(self, facts: LocalResearchRunFactsV2, **updates: object) -> None:
        if self._control() is not None:
            return
        await self.store.put(self.key, facts.model_copy(update=updates))

    async def _execute(
        self,
        stage: ResearchStage,
        state: ResearchGraphState,
        facts: LocalResearchRunFactsV2,
    ) -> ResearchStageUpdateV2:
        if stage in {"compose", "verify", "render"}:
            # Task6 端口共享同一事实库；已停止采集时禁止其重新发起采集。
            stopped = {
                name: True
                for name in (
                    "budget_exhausted",
                    "soft_deadline_reached",
                    "cancelled",
                    "hard_deadline_reached",
                    "fatal_error",
                )
                if state.get(name)
            }
            update = await self.output_stages.run_stage(stage, state)
            if update.model_fields_set - {
                "output_artifact_id",
                "output_verified",
                "output_degraded",
                "output_recollect_requested",
                "fatal_error",
                "cancelled",
                "hard_deadline_reached",
                "budget_exhausted",
                "soft_deadline_reached",
                "budget_version",
            }:
                raise ValueError("RESEARCH_OUTPUT_RECOLLECTION_FORBIDDEN")
            return update.model_copy(update=stopped)
        if stage in {"validate", "finalize"}:
            return ResearchStageUpdateV2()
        if stage == "plan":
            return await self._plan(state, facts)
        if stage == "discover":
            return await self._discover(state, facts)
        if stage == "acquire":
            return await self._acquire(state, facts)
        if stage == "normalize":
            return await self._normalize(state, facts)
        if stage == "filter":
            documents = _select(
                facts.documents, state.get("normalized_document_ids", [])
            )
            decisions = await self.decisions.relevance(
                self.brief, documents, self._lease()
            )
            result = filter_documents(self.brief, documents, decisions)
            await self._save(
                facts,
                stage_artifact_ids={
                    **facts.stage_artifact_ids,
                    "filter": result.accepted_document_ids,
                    "filter_uncertain": tuple(
                        item.document_id for item in result.uncertain
                    ),
                },
            )
            return ResearchStageUpdateV2(
                filtered_document_ids=result.accepted_document_ids
            )
        if stage == "deduplicate":
            documents = _select(facts.documents, state.get("filtered_document_ids", []))
            deduplicated = deduplicate_documents(documents)
            ids = tuple(item.document_id for item in deduplicated.documents)
            await self._save(
                facts,
                stage_artifact_ids={**facts.stage_artifact_ids, "deduplicate": ids},
            )
            return ResearchStageUpdateV2(deduplicated_document_ids=ids)
        if stage == "cluster":
            documents = _select(
                facts.documents, state.get("deduplicated_document_ids", [])
            )
            clustered = await EventClusterer(
                ResearchClusterModelAdapter(self.decisions)
            ).cluster(documents, self.brief, self._lease())
            events = {item.event_id: item for item in clustered.events}
            await self._save(
                facts,
                events={**facts.events, **events},
                stage_artifact_ids={
                    **facts.stage_artifact_ids,
                    "cluster": tuple(events),
                },
            )
            return ResearchStageUpdateV2(event_ids=tuple(events))
        if stage == "claims":
            return await self._claims(state, facts)
        if stage == "quality":
            return await self._quality(state, facts)
        raise ValueError("LOCAL_RESEARCH_STAGE_UNKNOWN")

    def _lease(self) -> BudgetLeaseReferenceV2:
        return BudgetLeaseReferenceV2(
            lease_id=self.binding.lease_id, version=self.binding.version
        )

    def _sources(self):
        context = self.source_context.model_copy(update={"now": self.now()})
        return tuple(
            item
            for item in self.registry.list_available(context, self.brief)
            if item.source_id in self.context.allowed_source_ids
        )

    async def _plan(
        self, state: ResearchGraphState, facts: LocalResearchRunFactsV2
    ) -> ResearchStageUpdateV2:
        snapshot = await self.binding.port.snapshot(self.binding.scope)
        self.binding.update_version(snapshot.version)
        budget = BudgetSnapshotV2(
            lease_id=self.binding.lease_id,
            version=snapshot.version,
            remaining_calls=max(
                0,
                snapshot.limits.max_calls
                - snapshot.used.calls
                - snapshot.reserved.calls,
            ),
            remaining_bytes=max(
                0,
                snapshot.limits.max_bytes
                - snapshot.used.bytes
                - snapshot.reserved.bytes,
            ),
        )
        if budget.remaining_calls == 0 or budget.remaining_bytes == 0:
            return ResearchStageUpdateV2(
                planned_action_ids=(), plan_exhausted=True, budget_exhausted=True
            )
        quality_id = state.get("quality_report_id")
        if quality_id is not None:
            quality = _select(facts.quality_reports, [quality_id])[0]
        else:
            gap = QualityGapV2(
                gap_id="initial-discovery",
                requirement_id="count_policy",
                code="COUNT_EXACT_UNMET",
                detail="INITIAL_DISCOVERY",
                recoverable=True,
            )
            quality = QualityReportV2(
                report_id="initial-quality",
                brief_digest=self.brief.canonical_digest(),
                policy_version=self.policy.policy_version,
                hard_gates_passed=False,
                gaps=(gap,),
                coverage_ratio=0,
            )
        history = CollectionHistoryV2(
            completed_action_ids=facts.stage_artifact_ids.get("discovered_actions", ()),
            attempted_source_ids=tuple(
                sorted({x.source_id for x in facts.attempts.values()})
            ),
            rounds=state.get("refill_rounds", 0),
            no_gain_rounds=state.get("no_gain_rounds", 0),
        )
        sources = self._sources()
        actions = []
        kinds: dict[str, Literal["search_alternative", "search_required_facet"]] = {
            "COUNT_EXACT_UNMET": "search_alternative",
            "COUNT_MINIMUM_UNMET": "search_alternative",
            "REQUIRED_FACET_UNCOVERED": "search_required_facet",
        }
        for gap in quality.gaps:
            kind = kinds.get(gap.code)
            if not gap.recoverable or kind is None:
                continue
            query = self.brief.topic
            if gap.requirement_id.startswith("facet:"):
                query += " " + gap.requirement_id.removeprefix("facet:")
            for source in sources:
                identifier = action_fingerprint(
                    self.brief.intent_revision, gap, source.source_id, query, None
                )
                if identifier in history.completed_action_ids:
                    continue
                actions.append(
                    CollectionActionV2(
                        action_id=identifier,
                        gap_id=gap.gap_id,
                        gap_code=gap.code,
                        action_kind=kind,
                        source_id=source.source_id,
                        requirement_ids=(gap.requirement_id,),
                        query=query,
                        time_window=self.brief.time_window,
                        revision=self.brief.intent_revision,
                    )
                )
        candidates = tuple(actions[: budget.remaining_calls])
        if candidates and state.get("initial_collection_done"):
            proposed = await CollectionPlanner(
                ResearchPlanModelAdapter(self.decisions, candidates)
            ).plan_gaps(self.brief, quality, history, budget)
        else:
            proposed = CollectionPlanV2(
                actions=candidates, stop_reason=None if candidates else "PLAN_EXHAUSTED"
            )
        validated = ActionValidator().validate(
            proposed,
            self.brief,
            quality,
            PlanningSourceRegistryV2(
                sources=tuple(
                    PlanningSourceV2(
                        source_id=x.source_id,
                        roles=x.roles,
                        admitted=True,
                        verified_free=True,
                        supports_history=x.admission.history_verified,
                    )
                    for x in sources
                )
            ),
            history,
            budget,
        )
        plan = CollectionPlanV2(
            actions=validated.actions,
            stop_reason=validated.stop_reason
            or (None if validated.actions else "PLAN_EXHAUSTED"),
        )
        plan_id = (
            "plan-" + hashlib.sha256(plan.model_dump_json().encode()).hexdigest()[:32]
        )
        ids = tuple(item.action_id for item in plan.actions)
        await self._save(
            facts,
            plans={**facts.plans, plan_id: plan},
            stage_artifact_ids={**facts.stage_artifact_ids, "plan": (plan_id,)},
        )
        return ResearchStageUpdateV2(planned_action_ids=ids, plan_exhausted=not ids)

    async def _discover(
        self, state: ResearchGraphState, facts: LocalResearchRunFactsV2
    ) -> ResearchStageUpdateV2:
        actions = {
            action.action_id: action
            for plan in facts.plans.values()
            for action in plan.actions
        }
        selected = _select(actions, state.get("planned_action_ids", []))
        candidates, attempts = dict(facts.candidates), dict(facts.attempts)
        completed = list(facts.stage_artifact_ids.get("discovered_actions", ()))
        incomplete = list(facts.stage_artifact_ids.get("incomplete_actions", ()))
        for action in selected:
            if self._control() is not None:
                break
            result = await self.executor.execute_discovery(
                DiscoveryActionV2(
                    action.action_id,
                    ResearchDiscoverArgumentsV2(
                        request_id=action.action_id,
                        source_id=action.source_id,
                        brief_digest=self.brief.canonical_digest(),
                        query=action.query,
                        time_window=action.time_window,
                        cursor=action.cursor,
                        limit=30,
                    ),
                ),
                self.context,
            )
            batch = result.batch
            if batch is not None:
                for item in batch.candidates:
                    if item.source_id != action.source_id:
                        raise ValueError("LOCAL_RESEARCH_CANDIDATE_SOURCE_MISMATCH")
                    if (
                        item.candidate_id in candidates
                        and candidates[item.candidate_id] != item
                    ):
                        raise ValueError("LOCAL_RESEARCH_CANDIDATE_CONFLICT")
                    candidates[item.candidate_id] = item
            if (
                batch is None
                or batch.completeness != "complete"
                or batch.coverage != "complete"
            ):
                incomplete.append(action.action_id)
            completed.append(action.action_id)
        for attempt in await self.executor.attempt_ledger.list(
            self.key.tenant_id, self.key.run_id
        ):
            if (
                attempt.attempt_id in attempts
                and attempts[attempt.attempt_id] != attempt
            ):
                raise ValueError("SOURCE_ATTEMPT_CONFLICT")
            attempts[attempt.attempt_id] = attempt
        await self._save(
            facts,
            candidates=candidates,
            attempts=attempts,
            stage_artifact_ids={
                **facts.stage_artifact_ids,
                "discover": tuple(candidates),
                "discovered_actions": tuple(dict.fromkeys(completed)),
                "incomplete_actions": tuple(dict.fromkeys(incomplete)),
            },
        )
        return ResearchStageUpdateV2(candidate_ids=tuple(candidates))

    async def _acquire(
        self, state: ResearchGraphState, facts: LocalResearchRunFactsV2
    ) -> ResearchStageUpdateV2:
        candidates = _select(facts.candidates, state.get("candidate_ids", []))
        extracted, attempts = dict(facts.extracted_documents), dict(facts.attempts)
        full = set(facts.stage_artifact_ids.get("acquired_full", ()))
        platform = set(facts.stage_artifact_ids.get("acquired_platform_text", ()))
        body_requests = facts.resources.body_requests
        exhausted = False
        for item in candidates:
            if self._control() is not None:
                break
            if item.candidate_id in extracted:
                continue
            if body_requests >= 30:
                exhausted = True
                break
            started = self.now()
            before_http, before_bytes = self._http_usage()
            error = None
            try:
                document = await self.acquirer.acquire(item, self.context)
                extracted[item.candidate_id] = document
                (platform if item.content_scope == "platform_text" else full).add(
                    item.candidate_id
                )
            except (ValueError, DocumentExtractionError) as exc:
                error = (
                    str(exc)
                    if str(exc).isascii()
                    and str(exc).replace("_", "").isalnum()
                    and len(str(exc)) <= 128
                    else "CONTENT_UNAVAILABLE"
                )
            after_http, after_bytes = self._http_usage()
            body_requests += after_http - before_http
            identifier = f"content-attempt-{facts.version}-{hashlib.sha256(item.candidate_id.encode()).hexdigest()[:24]}"
            attempts[identifier] = SourceAttemptV2(
                attempt_id=identifier,
                action_id=item.candidate_id,
                source_id=item.source_id,
                status="failed" if error else "success",
                started_at=started,
                finished_at=self.now(),
                returned_count=0 if error else 1,
                filtered_count=0,
                error_code=error,
                coverage="unknown",
                lease_id=self.binding.lease_id,
                usage=SourceUsageV2(
                    requests=after_http - before_http,
                    returned_items=0 if error else 1,
                    downloaded_bytes=after_bytes - before_bytes,
                ),
            )
        ids = tuple(
            item.candidate_id for item in candidates if item.candidate_id in extracted
        )
        await self._save(
            facts,
            extracted_documents=extracted,
            attempts=attempts,
            resources=facts.resources.model_copy(
                update={"body_requests": body_requests}
            ),
            stage_artifact_ids={
                **facts.stage_artifact_ids,
                "acquire": ids,
                "acquired_full": tuple(sorted(full)),
                "acquired_platform_text": tuple(sorted(platform)),
            },
        )
        return ResearchStageUpdateV2(
            acquired_document_ids=ids, budget_exhausted=exhausted
        )

    async def _normalize(
        self, state: ResearchGraphState, facts: LocalResearchRunFactsV2
    ) -> ResearchStageUpdateV2:
        extracted = _select(
            facts.extracted_documents, state.get("acquired_document_ids", [])
        )
        documents = dict(facts.documents)
        ids = []
        descriptors = {item.source_id: item for item in self._sources()}
        for content in extracted:
            candidate = _select(facts.candidates, [content.candidate_id])[0]
            if content.candidate_id in facts.stage_artifact_ids.get(
                "acquired_platform_text", ()
            ):
                scope = "platform_text"
            elif content.candidate_id in facts.stage_artifact_ids.get(
                "acquired_full", ()
            ):
                scope = "full"
            else:
                raise ValueError("LOCAL_RESEARCH_CONTENT_PROVENANCE_MISSING")
            # 仅本次获准抓取正文决定范围；原候选摘要在事实库内保持原样。
            # RSS 的 RFC 5322 日期是已明确的发布时间；不从 updated 字段猜测。
            normalized_content = content
            if (
                candidate.discovered_via == "rss"
                and candidate.raw_published_at
                and content.published_at is None
            ):
                published = None
                try:
                    published = parsedate_to_datetime(candidate.raw_published_at)
                except (ValueError, TypeError, IndexError):
                    pass
                if published is not None and published.tzinfo is not None:
                    normalized_content = content.model_copy(
                        update={"published_at": published}
                    )
            document = normalize(candidate, normalized_content).model_copy(
                update={"content_scope": scope}
            )
            descriptor = descriptors.get(candidate.source_id)
            if descriptor is not None:
                document = document.model_copy(
                    update={
                        "source_role": "primary"
                        if "primary" in descriptor.roles
                        else "unknown",
                        "publisher_id": descriptor.publisher_id,
                        "ownership_group": descriptor.ownership_group,
                    }
                )
            documents[document.document_id] = document
            ids.append(document.document_id)
        await self._save(
            facts,
            documents=documents,
            stage_artifact_ids={**facts.stage_artifact_ids, "normalize": tuple(ids)},
        )
        return ResearchStageUpdateV2(normalized_document_ids=tuple(ids))

    async def _claims(
        self, state: ResearchGraphState, facts: LocalResearchRunFactsV2
    ) -> ResearchStageUpdateV2:
        documents = _select(facts.documents, state.get("deduplicated_document_ids", []))
        events = _select(facts.events, state.get("event_ids", []))
        if not documents or not events:
            return ResearchStageUpdateV2(claim_ids=(), evidence_ids=())
        refs = tuple(
            build_evidence_ref(doc, start, min(start + 2_000, len(doc.text)))
            for doc in documents
            for start in range(0, len(doc.text), 2_000)
        )
        context = EvidenceContextV2(
            brief_digest=self.brief.canonical_digest(),
            documents=documents,
            evidence_refs=refs,
            source_families=SourceFamilyResolver().resolve(documents),
        )
        batch = await ClaimExtractor(ResearchClaimModelAdapter(self.decisions)).extract(
            events, context, self._lease()
        )
        claims = {
            item.claim_id: item
            for item in ConflictResolver().classify(batch.accepted).claims
        }
        evidence = {item.evidence_id: item for item in refs}
        await self._save(
            facts,
            claims={**facts.claims, **claims},
            evidence={**facts.evidence, **evidence},
            stage_artifact_ids={
                **facts.stage_artifact_ids,
                "claims": tuple(claims),
                "evidence": tuple(evidence),
            },
        )
        return ResearchStageUpdateV2(
            claim_ids=tuple(claims), evidence_ids=tuple(evidence)
        )

    async def _quality(
        self, state: ResearchGraphState, facts: LocalResearchRunFactsV2
    ) -> ResearchStageUpdateV2:
        documents = _select(facts.documents, state.get("normalized_document_ids", []))
        events = _select(facts.events, state.get("event_ids", []))
        claims = _select(facts.claims, state.get("claim_ids", []))
        evidence = _select(facts.evidence, state.get("evidence_ids", []))
        accepted = tuple(state.get("filtered_document_ids", []))
        _select(facts.documents, accepted)
        rejected = tuple(
            DocumentFilterRecordV2(
                document_id=item.document_id, stage="F2", reason_code="NOT_ACCEPTED"
            )
            for item in documents
            if item.document_id not in accepted
        )
        filters = FilterResultV2(
            accepted_document_ids=accepted,
            rejected=rejected,
            input_count=len(documents),
            accepted_count=len(accepted),
            rejected_count=len(rejected),
            uncertain_count=0,
        )
        available = {item.source_id for item in self._sources()}
        source_decisions = tuple(
            SourcePolicyDecisionV2(
                source_id=source_id,
                allowed=source_id in available,
                reason_codes=() if source_id in available else ("SOURCE_NOT_ALLOWED",),
            )
            for source_id in sorted({item.source_id for item in documents})
        )
        discovery_attempts = tuple(
            item
            for item in facts.attempts.values()
            if not item.attempt_id.startswith("content-attempt-")
        )
        plan_ids = {
            item.action_id for plan in facts.plans.values() for item in plan.actions
        }
        complete = bool(plan_ids) and plan_ids.issubset(
            facts.stage_artifact_ids.get("discovered_actions", ())
        )
        successful = bool(discovery_attempts) and all(
            item.status in {"success", "success_empty"} and item.coverage == "complete"
            for item in discovery_attempts
        )
        history_complete = (
            successful
            and not facts.stage_artifact_ids.get("incomplete_actions")
            and not facts.stage_artifact_ids.get("filter_uncertain")
            and all(
                candidate_id in {doc.candidate_id for doc in documents}
                for candidate_id in state.get("candidate_ids", [])
            )
            and all(item.admission.history_verified for item in self._sources())
        )
        result = evaluate_quality(
            self.brief,
            self.policy,
            documents,
            events,
            claims,
            evidence,
            filters,
            ConflictResolver().classify(claims),
            source_decisions,
            CollectionCoverageV2(
                plan_complete=complete,
                attempt_count=len(discovery_attempts),
                critical_failure=bool(discovery_attempts)
                and all(item.status == "failed" for item in discovery_attempts),
                truncated=bool(facts.stage_artifact_ids.get("incomplete_actions")),
                historical_coverage="complete" if history_complete else "unknown",
            ),
        )
        await self._save(
            facts,
            quality_reports={
                **facts.quality_reports,
                result.report.report_id: result.report,
            },
            stage_artifact_ids={
                **facts.stage_artifact_ids,
                "quality": (result.report.report_id,),
                "qualified_events": result.report.usable_event_ids,
                "qualified_claims": tuple(
                    item.claim_id
                    for item in claims
                    if item.event_id in result.report.usable_event_ids
                ),
                "qualified_evidence": tuple(
                    sorted(
                        {
                            ref_id
                            for item in claims
                            if item.event_id in result.report.usable_event_ids
                            for ref_id in item.support_refs
                        }
                    )
                ),
            },
        )
        return ResearchStageUpdateV2(
            qualified_event_ids=result.report.usable_event_ids,
            quality_report_id=result.report.report_id,
            hard_gap_ids=tuple(item.gap_id for item in result.report.gaps),
            complete_empty_plan=result.outcome == "NO_MATCHES",
        )


def _select[T](mapping: Mapping[str, T], identifiers: Sequence[str]) -> tuple[T, ...]:
    if len(set(identifiers)) != len(identifiers) or any(
        item not in mapping for item in identifiers
    ):
        raise ValueError("LOCAL_RESEARCH_STAGE_ID_UNKNOWN")
    return tuple(mapping[item] for item in identifiers)
