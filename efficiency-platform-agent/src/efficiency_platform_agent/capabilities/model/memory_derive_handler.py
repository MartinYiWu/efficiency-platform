"""原运行帧中的摘要生成与校验组合；不签发授权、不发布摘要。"""

import time
from collections.abc import Callable
from contextlib import AbstractAsyncContextManager
from dataclasses import dataclass, field
from typing import Protocol

from efficiency_platform_agent.context.compaction import (
    CompactionBaseline,
    propose_compaction,
)
from efficiency_platform_agent.context.policy import render_context_messages
from efficiency_platform_agent.context.selection import ContextView
from efficiency_platform_agent.contracts.memory import ConversationScopeModel
from efficiency_platform_agent.contracts.memory_derive import (
    DeriveAssetRefs,
    MemoryDeriveRequest,
)
from efficiency_platform_agent.core.context_control import (
    ContextFragmentCounter,
    TokenCounter,
)
from efficiency_platform_agent.core.derive_ports import DeriveOperation
from efficiency_platform_agent.core.execution_control import current_run_control
from efficiency_platform_agent.core.run_context_binding import (
    RunContextBinding,
    current_run_context,
)
from efficiency_platform_agent.memory.derive import (
    DeriveAuthorizer,
    DeriveCandidate,
    DeriveMode,
    DeriveSourceHydrator,
)
from efficiency_platform_agent.memory.proposals import (
    ProposalTaskState,
    evaluate_proposals,
)
from efficiency_platform_agent.memory.summary_contracts import SummaryInputSource
from efficiency_platform_agent.memory.summary_policy import SummaryPolicy
from efficiency_platform_agent.memory.summary_validation import (
    FrozenSummarySources,
    validate_summary,
)

from .memory_derive_sources import RequestDeriveSources, TrustedDeriveSourceChecker

MEMORY_DERIVE_SKILL_ID = 6201
MEMORY_SKILLS = {MEMORY_DERIVE_SKILL_ID: "memory.derive"}


@dataclass(frozen=True, slots=True)
class OriginalDeriveFrame:
    operation: DeriveOperation
    binding: RunContextBinding = field(repr=False)
    runtime_id: str
    runtime_kind: str
    baseline_ref: str
    baseline: CompactionBaseline = field(repr=False)
    assets: DeriveAssetRefs
    counter: TokenCounter = field(repr=False)
    source_checker: TrustedDeriveSourceChecker = field(repr=False)


class OriginalDeriveFramePort(Protocol):
    def bind(
        self, request: MemoryDeriveRequest
    ) -> AbstractAsyncContextManager[OriginalDeriveFrame]:
        """只绑定尚存活原帧/control/授权；缺失、停止或过期必须拒绝。"""
        ...


class DeriveGatewayPort(Protocol):
    async def derive(
        self,
        scope: ConversationScopeModel,
        mode: DeriveMode,
        sources: tuple[SummaryInputSource, ...],
        operation: DeriveOperation,
    ) -> DeriveCandidate: ...


GatewayFactory = Callable[
    [OriginalDeriveFrame, DeriveAuthorizer, DeriveSourceHydrator], DeriveGatewayPort
]


class MemoryDeriveHandler:
    def __init__(
        self,
        frames: OriginalDeriveFramePort,
        gateway_factory: GatewayFactory,
        *,
        enabled: bool = False,
    ):
        self.frames, self.gateway_factory, self.enabled = (
            frames,
            gateway_factory,
            enabled,
        )

    async def execute(
        self, tenant_id: str, request: MemoryDeriveRequest
    ) -> dict[str, object]:
        if not self.enabled:
            raise ValueError("MEMORY_DERIVE_FEATURE_DISABLED")
        if tenant_id != request.execution_scope.conversation.tenant_id:
            raise ValueError("DERIVE_SCOPE_MISMATCH")
        if request.fingerprint() != request.plan_fingerprint:
            raise ValueError("DERIVE_BINDING_CONFLICT")
        if time.time() >= request.deadline_epoch_seconds:
            raise ValueError("DERIVE_DEADLINE_EXCEEDED")
        async with self.frames.bind(request) as frame:
            self._check_frame(request, frame)
            sources = RequestDeriveSources(request, frame)
            await sources.current()
            metadata = sources.sources
            SummaryPolicy().admit(
                request.mode,
                metadata,
                request.execution_scope.conversation,
                now=int(time.time()),
            )
            gateway = self.gateway_factory(frame, sources, sources)
            candidate = await gateway.derive(
                request.execution_scope.conversation,
                request.mode,
                metadata,
                frame.operation,
            )
            self._check_frame(request, frame)
            state = await sources.current()
            if (
                candidate.mode != request.mode
                or (
                    request.mode == "SUMMARY"
                    and (candidate.summary is None or candidate.proposals)
                )
                or (request.mode == "PROPOSALS" and candidate.summary is not None)
            ):
                raise ValueError("DERIVE_MODE_OUTPUT_MISMATCH")
            validated_proposals = []
            if request.mode in {"PROPOSALS", "BOTH"}:
                if not isinstance(frame.counter, ContextFragmentCounter):
                    raise ValueError("PROPOSAL_TOKEN_EVIDENCE_REQUIRED")
                memory = frame.binding.memory_context
                assert memory is not None
                proposals = evaluate_proposals(
                    candidate.proposals,
                    ProposalTaskState(
                        request.execution_scope.conversation,
                        request.execution_scope.task_id,
                        memory.policy,
                        metadata,
                        (),
                        frozenset(),
                        frozenset(),
                    ),
                    frame.counter,
                    frame.baseline.capacity,
                    now=int(time.time()),
                )
                validated_proposals = [
                    {
                        "kind": p.kind,
                        "field_key": p.field_key,
                        "value": p.value,
                        "decision_status": "PROPOSED",
                        "index_status": "NOT_REQUESTED",
                        "source_dependencies": [
                            d.model_dump(mode="json") for d in p.source_dependencies
                        ],
                    }
                    for p in proposals
                ]
            if request.mode == "PROPOSALS":
                dependencies = tuple(
                    dict.fromkeys(
                        d for source in metadata for d in source.source_dependencies
                    )
                )
                return self._result(
                    request,
                    candidate,
                    {
                        "free_text_quality": "UNVERIFIED",
                        "commit_status": "NOT_COMMITTED",
                        "session_revision": request.session_revision,
                        "source_revision": request.source_revision,
                        "source_watermark": None,
                        "frozen_critical_digest": request.plan_fingerprint,
                        "source_dependencies": [
                            d.model_dump(mode="json") for d in dependencies
                        ],
                        "expires_at": min(source.expires_at for source in metadata),
                        "proposals_validated": validated_proposals,
                    },
                    {
                        "status": "NOT_REQUESTED",
                        "reason": "DERIVE_PROPOSALS_ONLY",
                        "T_before": None,
                        "T_after": None,
                        "commit_status": "NOT_COMMITTED",
                    },
                )
            if candidate.summary is None:
                raise ValueError("DERIVE_SUMMARY_REQUIRED")
            frozen = FrozenSummarySources(
                metadata,
                request.events,
                request.required_entries,
                request.session_revision,
                request.source_revision,
                request.mode,
                request.assets.memory_policy_version,
                request.authority_ref,
            )
            validated = validate_summary(candidate.summary, frozen, state)
            benefit = propose_compaction(frame.baseline, validated, frame.counter)
            result: dict[str, object] = {
                "contract_version": "memory-derive-result/1",
                "skill": "memory.derive",
                "plan_id": request.plan_id,
                "plan_fingerprint": request.plan_fingerprint,
                "runtime_id": request.runtime_id,
                "run_id": request.run_id,
                "operation_id": request.operation_id,
                "execution_scope": request.execution_scope.model_dump(mode="json"),
                "assets": request.assets.model_dump(mode="json"),
                "baseline_ref": request.baseline_ref,
                "candidate": candidate.model_dump(mode="json"),
                "validation": {
                    "free_text_quality": validated.free_text_quality,
                    "commit_status": validated.commit_status,
                    "session_revision": validated.session_revision,
                    "source_revision": validated.source_revision,
                    "source_watermark": validated.watermark.model_dump(mode="json"),
                    "frozen_critical_digest": validated.frozen_critical_digest,
                    "source_dependencies": [
                        d.model_dump(mode="json") for d in validated.source_dependencies
                    ],
                    "expires_at": validated.expires_at,
                },
                "benefit": {
                    "status": benefit.status,
                    "reason": benefit.reason,
                    "T_before": benefit.T_before,
                    "T_after": benefit.T_after,
                    "commit_status": benefit.commit_status,
                },
            }
            if request.mode == "BOTH":
                validation = result["validation"]
                assert isinstance(validation, dict)
                validation["proposals_validated"] = validated_proposals
            return result

    @staticmethod
    def _result(request, candidate, validation, benefit):
        return {
            "contract_version": "memory-derive-result/1",
            "skill": "memory.derive",
            "plan_id": request.plan_id,
            "plan_fingerprint": request.plan_fingerprint,
            "runtime_id": request.runtime_id,
            "run_id": request.run_id,
            "operation_id": request.operation_id,
            "execution_scope": request.execution_scope.model_dump(mode="json"),
            "assets": request.assets.model_dump(mode="json"),
            "baseline_ref": request.baseline_ref,
            "candidate": candidate.model_dump(mode="json"),
            "validation": validation,
            "benefit": benefit,
        }

    @staticmethod
    def _check_frame(request: MemoryDeriveRequest, frame: OriginalDeriveFrame) -> None:
        control = current_run_control()
        if control is None:
            raise ValueError("DERIVE_ORIGINAL_RUN_CONTROL_REQUIRED")
        control.check()
        if (
            current_run_context() != frame.binding
            or frame.binding.memory_context is None
        ):
            raise ValueError("DERIVE_ORIGINAL_EXECUTION_REQUIRED")
        if (
            type(frame.baseline) is not CompactionBaseline
            or type(frame.baseline.view) is not ContextView
            or frame.baseline.view.messages != frame.baseline.view.request.messages
            or render_context_messages(frame.baseline.window_policy,frame.baseline.view.pieces)
            != frame.baseline.view.request.messages
        ):
            raise ValueError("SUMMARY_BASELINE_MISMATCH")
        operation, binding = frame.operation, frame.binding
        memory = binding.memory_context
        assert memory is not None
        memory.packet.validate_scope(
            operation.scope.conversation,
            operation.scope.task_id,
            operation.scope.execution_id,
        )
        dependencies = {
            dependency.to_core()
            for source in request.sources
            for dependency in source.metadata.source_dependencies
        }
        if (
            operation != request.operation()
            or (frame.runtime_id, frame.runtime_kind, frame.baseline_ref, frame.assets)
            != (
                request.runtime_id,
                request.runtime_kind,
                request.baseline_ref,
                request.assets,
            )
            or (binding.conversation, binding.task_id, binding.execution_id)
            != (
                operation.scope.conversation,
                operation.scope.task_id,
                operation.scope.execution_id,
            )
            or operation.deadline_epoch_seconds > binding.deadline_epoch_seconds
            or time.time() >= operation.deadline_epoch_seconds
            or memory.policy.version != frame.assets.memory_policy_version
            or frame.baseline.memory_policy_version
            != frame.assets.memory_policy_version
            or frame.baseline.window_policy_version
            != frame.assets.window_policy_version
            or frame.baseline.window_policy.scope != operation.scope
            or not frame.baseline.capacity.verified
            or memory.packet.parent_authorization_ref != operation.authorization_ref
            or time.time() >= memory.packet.expires_at
            or not any(
                grant.node_id == operation.scope.subtask_id
                and grant.execution_agent_id == operation.scope.execution_agent_id
                and grant.purpose == operation.scope.purpose
                for grant in memory.execution_grants
            )
            or not dependencies.issubset(
                frame.baseline.window_policy.authorized_dependencies
            )
        ):
            raise ValueError("DERIVE_BINDING_CONFLICT")
