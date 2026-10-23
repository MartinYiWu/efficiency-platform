"""智能客服运行、公开事件、取消与调试服务。"""

from __future__ import annotations

import asyncio
import logging
import traceback
from collections.abc import AsyncIterator, Callable
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Protocol
from uuid import UUID, uuid4

from .graph import CustomerServiceGraph, GraphResult
from .intent import StructuredStageGateway
from .release_bundle import CustomerServiceReleaseBundle
from .renderer import answer_deltas
from .retrieval_snapshot_repository import (
    InMemoryRetrievalSnapshotRepository,
    RetrievalSnapshotRepository,
    evidence_processing_facts,
)
from .state import (
    CustomerServiceRunRequest,
    DebugRequest,
    RunEvent,
    RunEventPayload,
    RunStatus,
    RunView,
)

logger = logging.getLogger("CustomerServiceRun")


class ReleaseRepositoryPort(Protocol):
    async def get(self, release_id: UUID) -> CustomerServiceReleaseBundle | None: ...
    async def get_active(self) -> tuple[UUID, CustomerServiceReleaseBundle] | None: ...


@dataclass(slots=True)
class _Run:
    request: CustomerServiceRunRequest
    view: RunView
    events: list[RunEvent] = field(default_factory=list)
    changed: asyncio.Event = field(default_factory=asyncio.Event)
    task: asyncio.Task[None] | None = None


class CustomerServiceNotFoundError(LookupError):
    pass


class CustomerServiceRunService:
    def __init__(
        self,
        graph: CustomerServiceGraph,
        releases: ReleaseRepositoryPort,
        gateway_factory: Callable[
            [CustomerServiceReleaseBundle], StructuredStageGateway
        ],
        retrieval_snapshots: RetrievalSnapshotRepository | None = None,
    ) -> None:
        self.graph = graph
        self.releases = releases
        self.gateway_factory = gateway_factory
        self.retrieval_snapshots = (
            retrieval_snapshots or InMemoryRetrievalSnapshotRepository()
        )
        self._runs: dict[UUID, _Run] = {}
        self._requests: dict[tuple[str, str], UUID] = {}
        self._lock = asyncio.Lock()

    async def submit(self, request: CustomerServiceRunRequest) -> RunView:
        key = (request.tenant_id, request.request_id)
        async with self._lock:
            current = self._requests.get(key)
            if current is not None:
                return self._runs[current].view
            run_id = uuid4()
            run = _Run(
                request=request,
                view=RunView(
                    run_id=run_id,
                    request_id=request.request_id,
                    status=RunStatus.PENDING,
                ),
            )
            self._runs[run_id] = run
            self._requests[key] = run_id
            self._append(
                run,
                "run.accepted",
                RunStatus.PENDING,
                RunEventPayload(
                    stage="accepted", progress_percent=0, public_summary="请求已接收"
                ),
            )
            run.task = asyncio.create_task(self._execute(run))
            return run.view

    async def cancel(self, run_id: UUID) -> RunView:
        run = self._require(run_id)
        if run.view.status in {
            RunStatus.SUCCEEDED,
            RunStatus.FAILED,
            RunStatus.TIMED_OUT,
            RunStatus.CANCELLED,
        }:
            return run.view
        if run.task is not None:
            run.task.cancel()
        run.view = run.view.model_copy(update={"status": RunStatus.CANCELLED})
        self._append(
            run,
            "run.cancelled",
            RunStatus.CANCELLED,
            RunEventPayload(
                stage="cancelled", progress_percent=100, public_summary="运行已取消"
            ),
        )
        return run.view

    async def events(
        self, run_id: UUID, after_sequence: int = 0
    ) -> AsyncIterator[RunEvent]:
        run = self._require(run_id)
        cursor = after_sequence
        while True:
            pending = [item for item in run.events if item.sequence > cursor]
            for item in pending:
                cursor = item.sequence
                yield item
            if run.view.status in {
                RunStatus.SUCCEEDED,
                RunStatus.FAILED,
                RunStatus.TIMED_OUT,
                RunStatus.CANCELLED,
            }:
                return
            run.changed.clear()
            await run.changed.wait()

    async def debug(self, request: DebugRequest) -> dict[str, Any]:
        bundle = await self.releases.get(request.agent_release_id)
        if bundle is None:
            raise CustomerServiceNotFoundError("Release 不存在")
        release_id = request.agent_release_id
        requested_bindings = {
            (item.knowledge_base_id, item.index_release_id)
            for item in request.knowledge_bindings
        }
        frozen_bindings = {
            (item.knowledge_base_id, item.index_release_id)
            for item in bundle.knowledge_bindings
        }
        if requested_bindings != frozen_bindings:
            raise ValueError("CUSTOMER_SERVICE_DEBUG_BINDING_MISMATCH")
        run_request = CustomerServiceRunRequest(
            contract_version="customer-service-run/1",
            request_id=f"debug-{uuid4().hex}",
            conversation_id=uuid4(),
            tenant_id=request.tenant_id,
            user_id="debug",
            agent_release_id=release_id,
            message=request.question,
            history=(),
        )
        debug_run_id = uuid4()
        result = await self.graph.run(run_request, bundle, self.gateway_factory(bundle))
        await self.retrieval_snapshots.save(debug_run_id, result)
        facts = self._retrieval_facts(result)
        return {
            "contract_version": "customer-service-rag-debug-view/1",
            "debug_run_id": str(debug_run_id),
            "status": "SUCCEEDED",
            "stages": [
                {
                    "stage_key": key,
                    "status": "SUCCEEDED",
                    "public_summary": summary,
                    "evidence": [
                        {
                            "chunk_id": str(item.chunk_id),
                            "document_version_id": str(item.document_version_id),
                            "section_path": item.section_path or "",
                            "score": item.score,
                            "excerpt": item.content[:500],
                        }
                        for item in result.evidence
                    ]
                    if key == "retrieval"
                    else [],
                }
                for key, summary in result.stage_summaries
            ],
            **facts,
            "answer_mode": result.rendered.answer.answer_mode.value,
            "answer_markdown": result.rendered.markdown,
            "error_code": None,
            "error_message": None,
        }

    @staticmethod
    def _retrieval_facts(result: GraphResult) -> dict[str, Any]:
        trace = result.retrieval_trace
        assembly = trace.assembly if trace is not None else None
        return {
            **evidence_processing_facts(trace),
            "equivalence_decisions": [
                item.model_dump(mode="json")
                for item in (trace.equivalence_decisions if trace else ())
            ],
            "equivalence_errors": list(trace.equivalence_errors if trace else ()),
            "version_exclusions": [
                row | {"reason": "NOT_BOUND_INDEX_MEMBER"}
                for row in _candidate_rows(trace.version_exclusions if trace else ())
            ],
            "vector_candidates": _candidate_rows(
                trace.vector_candidates if trace else ()
            ),
            "fts_candidates": _candidate_rows(trace.fts_candidates if trace else ()),
            "fused_candidates": _candidate_rows(
                trace.fused_candidates if trace else ()
            ),
            "child_hits": _candidate_rows(trace.reranked_evidence if trace else ()),
            "parent_evidence": [
                {
                    "parent_id": str(item.parent_id),
                    "document_version_id": str(item.document_version_id),
                    "index_release_id": str(item.index_release_id),
                    "document_title": item.document_title,
                    "version_no": item.version_no,
                    "section_path": item.section_path,
                    "page_start": item.page_no,
                    "page_end": item.page_end,
                    "content": item.content,
                    "hit_chunk_ids": [
                        str(chunk_id)
                        for chunk_id in assembly.hit_chunk_ids[item.parent_id]
                    ],
                }
                for item in (assembly.selected_parents if assembly else ())
            ],
            "budget_usage": (
                {
                    "context_token_limit": assembly.context_token_limit,
                    "used_tokens": assembly.used_tokens,
                }
                if assembly is not None
                else None
            ),
            "sufficiency": (
                result.sufficiency.model_dump(mode="json")
                if result.sufficiency is not None
                else None
            ),
        }

    async def _execute(self, run: _Run) -> None:
        try:
            run.view = run.view.model_copy(update={"status": RunStatus.RUNNING})
            self._append(
                run,
                "run.started",
                RunStatus.RUNNING,
                RunEventPayload(
                    stage="intent", progress_percent=5, public_summary="正在理解问题"
                ),
            )
            bundle = await self.releases.get(run.request.agent_release_id)
            if bundle is None:
                raise CustomerServiceNotFoundError("Release 不存在")
            result = await self.graph.run(
                run.request, bundle, self.gateway_factory(bundle)
            )
            await self.retrieval_snapshots.save(run.view.run_id, result)
            self._publish_result(run, result)
        except asyncio.CancelledError:
            return
        except Exception as error:  # noqa: BLE001 - 运行边界必须转换为公开失败事件
            run.view = run.view.model_copy(update={"status": RunStatus.FAILED})
            code = str(getattr(error, "code", "CUSTOMER_SERVICE_RUN_FAILED"))
            message = str(getattr(error, "safe_message", "智能客服运行失败"))
            frames = " > ".join(
                f"{Path(frame.filename).name}:{frame.name}:{frame.lineno}"
                for frame in traceback.extract_tb(error.__traceback__)
            )
            logger.error(
                "event=customer_service_run_failed run_id=%s release_id=%s "
                "error_code=%s error_type=%s frames=%s",
                run.view.run_id,
                run.request.agent_release_id,
                code,
                type(error).__name__,
                frames,
            )
            self._append(
                run,
                "run.failed",
                RunStatus.FAILED,
                RunEventPayload(
                    stage="failed",
                    progress_percent=100,
                    error_code=code,
                    error_message=message,
                ),
            )

    def _publish_result(self, run: _Run, result: GraphResult) -> None:
        for key, summary in result.stage_summaries:
            self._append(
                run,
                "stage.completed",
                RunStatus.RUNNING,
                RunEventPayload(
                    stage=key,
                    public_summary=summary,
                    retrieval_facts=(
                        self._retrieval_facts(result) if key == "retrieval" else None
                    ),
                ),
            )
        for delta in answer_deltas(result.rendered):
            self._append(
                run,
                "answer.delta",
                RunStatus.RUNNING,
                RunEventPayload(
                    delta=delta, answer_mode=result.rendered.answer.answer_mode
                ),
            )
        for citation in result.rendered.citations:
            self._append(
                run,
                "citation.ready",
                RunStatus.RUNNING,
                RunEventPayload(
                    citation=citation, answer_mode=result.rendered.answer.answer_mode
                ),
            )
        run.view = run.view.model_copy(update={"status": RunStatus.SUCCEEDED})
        self._append(
            run,
            "answer.completed",
            RunStatus.SUCCEEDED,
            RunEventPayload(
                progress_percent=100,
                answer_mode=result.rendered.answer.answer_mode,
                public_summary="回答已完成",
            ),
        )

    def _append(
        self, run: _Run, event_type: str, status: RunStatus, payload: RunEventPayload
    ) -> None:
        run.events.append(
            RunEvent(
                run_id=run.view.run_id,
                sequence=len(run.events) + 1,
                event_type=event_type,
                status=status,
                payload=payload,
            )
        )
        run.changed.set()

    def _require(self, run_id: UUID) -> _Run:
        try:
            return self._runs[run_id]
        except KeyError as error:
            raise CustomerServiceNotFoundError("Run 不存在") from error


def _candidate_rows(values: tuple[Any, ...]) -> list[dict[str, Any]]:
    return [
        {
            "rank": item.rank or rank,
            "query_index": item.query_index,
            "chunk_id": str(item.chunk_id),
            "knowledge_base_id": str(item.knowledge_base_id),
            "document_id": str(item.document_id),
            "parent_id": str(item.parent_id) if item.parent_id else None,
            "document_version_id": str(item.document_version_id),
            "index_release_id": str(item.index_release_id),
            "score": item.score,
            "excerpt": item.content[:500],
        }
        for rank, item in enumerate(values, 1)
    ]


__all__ = ["CustomerServiceNotFoundError", "CustomerServiceRunService"]
