"""让既有 Supervisor Research Specialist 受控调用 ResearchServiceV2。"""

from __future__ import annotations

import asyncio
from collections.abc import Callable
from datetime import UTC, datetime, timedelta
from typing import Protocol, runtime_checkable

from efficiency_platform_agent.agents.operation.contracts.evidence import (
    EvidenceDuplicateStatus,
    EvidenceQualityStatus,
)
from efficiency_platform_agent.agents.operation.contracts.task import SourceScope
from efficiency_platform_agent.capabilities.research.contracts import (
    ResearchObservation,
    ResearchRequest,
    ResearchResult,
    ResearchStatus,
)
from efficiency_platform_agent.contracts.research_ports_v2 import ResearchServiceV2
from efficiency_platform_agent.contracts.research_v2 import (
    ResearchBriefV2,
    ResearchOutcomeV2,
    ResearchRuntimeContextV2,
)


@runtime_checkable
class ResearchBriefStoreV2(Protocol):
    async def get_brief(
        self, tenant_id: str, task_id: str, run_id: str | None = None
    ) -> ResearchBriefV2 | None: ...


class InMemoryResearchBriefStoreV2:
    """X03 离线交接存储；生产持久化与恢复仍由 X01 门禁。"""

    def __init__(self) -> None:
        self._briefs: dict[tuple[str, str, str], ResearchBriefV2] = {}
        self._lock = asyncio.Lock()

    async def put_brief(self, brief: ResearchBriefV2) -> None:
        if not isinstance(brief, ResearchBriefV2):
            raise TypeError("brief 必须是 ResearchBriefV2")
        key = (
            brief.trusted_context.tenant_id,
            brief.trusted_context.task_id,
            brief.trusted_context.run_id,
        )
        async with self._lock:
            current = self._briefs.get(key)
            if current is not None and current != brief:
                raise ValueError("RESEARCH_BRIEF_CONFLICT")
            self._briefs[key] = brief

    async def get_brief(
        self, tenant_id: str, task_id: str, run_id: str | None = None
    ) -> ResearchBriefV2 | None:
        async with self._lock:
            if run_id is not None:
                return self._briefs.get((tenant_id, task_id, run_id))
            matches = [
                brief
                for (tenant, task, _), brief in self._briefs.items()
                if (tenant, task) == (tenant_id, task_id)
            ]
            return matches[0] if len(matches) == 1 else None


class ResearchV2ProviderAdapter:
    def __init__(
        self,
        service: ResearchServiceV2,
        brief_store: ResearchBriefStoreV2,
        *,
        now=lambda: datetime.now(UTC),
        timeout: timedelta = timedelta(minutes=3),
        result_observer: Callable[[str, ResearchBriefV2, ResearchOutcomeV2], None]
        | None = None,
        run_id: str | None = None,
    ) -> None:
        if not isinstance(brief_store, ResearchBriefStoreV2):
            raise TypeError("brief_store 必须实现 ResearchBriefStoreV2")
        self.service = service
        self.brief_store = brief_store
        self.now = now
        self.timeout = timeout
        self.result_observer = result_observer
        self.run_id = run_id

    def for_run(
        self,
        run_id: str | None,
        observer: Callable[[str, ResearchBriefV2, ResearchOutcomeV2], None],
    ) -> ResearchV2ProviderAdapter:
        """创建独立运行适配器，共享 Service 但不共享结果槽或观察器。"""
        return ResearchV2ProviderAdapter(
            self.service,
            self.brief_store,
            now=self.now,
            timeout=self.timeout,
            result_observer=observer,
            run_id=run_id,
        )

    async def research(self, request: ResearchRequest) -> ResearchResult:
        try:
            if self.run_id is None:
                brief = await self.brief_store.get_brief(
                    request.tenant_id, request.task_id
                )
            else:
                brief = await self.brief_store.get_brief(
                    request.tenant_id, request.task_id, self.run_id
                )
        except Exception:  # noqa: BLE001 -- 旧边界不得泄漏存储故障或敏感正文。
            return _failed(request, "RESEARCH_UNAVAILABLE")
        if brief is None:
            return _failed(request, "RESEARCH_UNAVAILABLE")
        if (
            brief.trusted_context.tenant_id != request.tenant_id
            or brief.trusted_context.task_id != request.task_id
            or (self.run_id is not None and brief.trusted_context.run_id != self.run_id)
        ):
            return _failed(request, "EVIDENCE_INVALID")
        started = self.now()
        try:
            outcome = await self.service.research(
                brief,
                ResearchRuntimeContextV2(
                    request_id=request.request_id,
                    started_at=started,
                    deadline=started + self.timeout,
                ),
            )
        except Exception:  # noqa: BLE001 -- Provider 失败只能投影为稳定错误码。
            return _failed(request, "RESEARCH_UNAVAILABLE")
        if outcome.delivery is not None and (
            outcome.delivery.brief_digest != brief.canonical_digest()
            or outcome.delivery.outcome != outcome.outcome
        ):
            return _failed(request, "EVIDENCE_INVALID")
        if self.result_observer is not None:
            self.result_observer(request.request_id, brief, outcome)
        if outcome.outcome == "FAILED" or outcome.delivery is None:
            return _failed(request, "RESEARCH_INSUFFICIENT")
        if outcome.outcome == "NO_MATCHES":
            if outcome.delivery.events or outcome.usable_event_ids:
                return _failed(request, "EVIDENCE_INVALID")
            return ResearchResult(
                "research-result/1",
                request.request_id,
                request.task_id,
                request.tenant_id,
                ResearchStatus.EMPTY,
                (),
                ("RESEARCH_NO_MATCHES",),
                None,
            )
        observations: list[ResearchObservation] = []
        retrieved = int(started.timestamp() * 1000)
        for event in outcome.delivery.events:
            published = (
                int(event.event_time.timestamp() * 1000)
                if event.event_time is not None
                else None
            )
            for citation in event.citations:
                observations.append(
                    ResearchObservation(
                        observation_id=(
                            f"observation-{event.event_id}-{citation.evidence_id}"
                        ),
                        title=event.title,
                        publisher=citation.publisher_id,
                        source_url=citation.url,
                        published_at_epoch_ms=published,
                        retrieved_at_epoch_ms=retrieved,
                        source_scope=SourceScope.EXTERNAL_REFERENCE,
                        supported_conclusion_ids=frozenset(
                            request.expected_conclusion_ids
                        ),
                        within_time_window=True,
                        duplicate_status=EvidenceDuplicateStatus.UNIQUE,
                        quality_status=EvidenceQualityStatus.VALID,
                    )
                )
        if not observations:
            return _failed(request, "RESEARCH_INSUFFICIENT")
        return ResearchResult(
            "research-result/1",
            request.request_id,
            request.task_id,
            request.tenant_id,
            ResearchStatus.SUCCEEDED,
            tuple(observations),
            (
                ("RESEARCH_OUTCOME_PARTIAL", *outcome.delivery.gap_codes)
                if outcome.outcome == "PARTIAL"
                else ()
            ),
            None,
        )


def _failed(request: ResearchRequest, code: str) -> ResearchResult:
    return ResearchResult(
        "research-result/1",
        request.request_id,
        request.task_id,
        request.tenant_id,
        ResearchStatus.FAILED,
        (),
        (),
        code,
    )


__all__ = [
    "InMemoryResearchBriefStoreV2",
    "ResearchBriefStoreV2",
    "ResearchV2ProviderAdapter",
]
