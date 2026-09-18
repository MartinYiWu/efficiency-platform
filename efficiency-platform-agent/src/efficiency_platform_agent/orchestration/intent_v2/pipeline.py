"""Intent V2 会话协调、原子提交与 Run 生命周期决策。"""

from __future__ import annotations

import asyncio
import hashlib
from collections.abc import Mapping
from dataclasses import dataclass, replace
from types import MappingProxyType
from typing import Literal, Protocol

from efficiency_platform_agent.agents.operation.definition import (
    OperationSpecialistCapabilityId,
)
from efficiency_platform_agent.contracts.intent_v2 import (
    BudgetLeaseReferenceV2,
    CapabilityCatalogSnapshot,
    CapabilityPlanV2,
    IntentContextV2,
    IntentDecision,
    IntentFrameV2,
    PermissionSnapshotV2,
    TrustedMessageV2,
)
from efficiency_platform_agent.contracts.research_v2 import (
    ResearchBriefV2,
    ResearchPolicySnapshotV2,
    TrustedResearchContextV2,
)
from efficiency_platform_agent.core.runtime import UsageSnapshot

from .binding import CapabilityBinderV2
from .decision import IntentDecisionPolicyV2
from .interpreter import (
    ControlledIntentInterpreterV2,
    IntentInterpretationV2Error,
)
from .patch_validation import IntentPatchValidator, TrustedIntentScope
from .reducer import IntentReductionError, IntentStateReducer
from .research_bridge import ResearchBridgeError, ResearchBriefBuilderV2
from .scenario_adapter import ScenarioInputAdapter, ScenarioProjectionV2
from .temporal import TemporalResolutionError, TemporalResolver

type TaskVersion = Literal["intent-v1", "intent-v2"]
type RunLifecycleStatus = Literal[
    "queued",
    "running",
    "waiting_input",
    "succeeded",
    "failed",
    "cancelled",
]
type LifecycleAction = Literal[
    "START_NEW_RUN",
    "RESUME_RUN",
    "WAIT_FOR_INPUT",
    "SUPERSEDE_AT_SAFE_BOUNDARY",
    "CANCEL_EXISTING",
    "RESPOND_DIRECT",
    "NO_DISPATCH",
]


class IntentPipelineBypass(RuntimeError):
    def __init__(self, code: str) -> None:
        self.code = code
        super().__init__(code)


@dataclass(frozen=True, slots=True)
class IntentPipelineVersionsV2:
    catalog_version: str
    context_version: str
    permission_version: str
    lease_id: str
    lease_version: int
    policy_version: str
    prompt_versions: tuple[str, ...] = ()


@dataclass(frozen=True, slots=True)
class PreparedIntentV2:
    decision: IntentDecision
    frame: IntentFrameV2 | None
    brief: ResearchBriefV2 | None
    scenario_projection: ScenarioProjectionV2 | None
    usage: UsageSnapshot
    provider_calls: int
    versions: IntentPipelineVersionsV2
    lifecycle_action: LifecycleAction
    run_id: str | None
    replacement_run_id: str | None
    committed: bool
    replayed: bool
    dispatch_allowed: bool

    def __post_init__(self) -> None:
        if self.dispatch_allowed and (
            not self.committed
            or self.replayed
            or self.decision.outcome != "READY"
            or self.lifecycle_action not in {"START_NEW_RUN", "RESUME_RUN"}
        ):
            raise ValueError("INTENT_DISPATCH_NOT_ALLOWED")
        if self.brief is not None and self.decision.outcome != "READY":
            raise ValueError("INTENT_BRIEF_WITHOUT_READY")
        if (
            self.scenario_projection is not None
            and not self.scenario_projection.supported
        ):
            raise ValueError("INTENT_SCENARIO_NOT_SUPPORTED")


@dataclass(frozen=True, slots=True)
class IntentPipelineContextV2:
    intent_context: IntentContextV2
    visible_user_messages: Mapping[str, str]
    catalog: CapabilityCatalogSnapshot
    permissions: PermissionSnapshotV2
    lease: BudgetLeaseReferenceV2
    research_context: TrustedResearchContextV2
    research_policy: ResearchPolicySnapshotV2
    proposed_run_id: str
    allowed_default_policy_ids: frozenset[str] = frozenset()
    allowed_normalizer_versions: frozenset[str] = frozenset()
    allowed_intent_parameter_names: frozenset[str] = frozenset()

    def __post_init__(self) -> None:
        if not self.proposed_run_id.strip():
            raise ValueError("proposed_run_id 必须是非空字符串")
        if self.research_context.run_id != self.proposed_run_id:
            raise ValueError("INTENT_PROPOSED_RUN_MISMATCH")
        visible = dict(self.visible_user_messages)
        if set(visible) != set(self.intent_context.visible_message_ids):
            raise ValueError("INTENT_VISIBLE_MESSAGE_SCOPE_MISMATCH")
        if any(not text for text in visible.values()):
            raise ValueError("INTENT_VISIBLE_MESSAGE_EMPTY")
        object.__setattr__(self, "visible_user_messages", MappingProxyType(visible))


@dataclass(frozen=True, slots=True)
class IntentTaskSnapshotV2:
    tenant_id: str
    task_id: str
    task_version: TaskVersion
    frame: IntentFrameV2 | None
    run_id: str | None
    run_status: RunLifecycleStatus | None
    clarification_rounds: int = 0

    def __post_init__(self) -> None:
        if not self.tenant_id.strip():
            raise ValueError("tenant_id 必须是非空字符串")
        if not self.task_id.strip():
            raise ValueError("task_id 必须是非空字符串")
        if (
            self.task_version == "intent-v2"
            and self.frame is not None
            and self.frame.task_id != self.task_id
        ):
            raise ValueError("INTENT_TASK_SNAPSHOT_MISMATCH")
        if (self.run_id is None) != (self.run_status is None):
            raise ValueError("INTENT_RUN_SNAPSHOT_INCOMPLETE")
        if not 0 <= self.clarification_rounds <= 2:
            raise ValueError("INTENT_CLARIFICATION_ROUNDS_INVALID")


@dataclass(frozen=True, slots=True)
class _CommitResult:
    status: Literal["COMMITTED", "REPLAY", "CONFLICT", "MESSAGE_CONFLICT"]
    prepared: PreparedIntentV2 | None = None


@dataclass(frozen=True, slots=True)
class _StoredRecord:
    message_digest: str
    prepared: PreparedIntentV2


class IntentTaskRepositoryV2(Protocol):
    async def load(
        self, tenant_id: str, task_id: str
    ) -> IntentTaskSnapshotV2 | None: ...

    async def lookup(
        self,
        tenant_id: str,
        task_id: str,
        message_id: str,
        message_digest: str,
    ) -> _CommitResult | None: ...

    async def commit(
        self,
        *,
        tenant_id: str,
        task_id: str,
        expected_revision: int,
        message_id: str,
        message_digest: str,
        prepared: PreparedIntentV2,
    ) -> _CommitResult: ...


class InMemoryIntentTaskRepositoryV2:
    """I07 离线验收仓储；生产权威存储与恢复归 X01。"""

    def __init__(self) -> None:
        self._snapshots: dict[tuple[str, str], IntentTaskSnapshotV2] = {}
        self._records: dict[tuple[str, str, str], _StoredRecord] = {}
        self._lock = asyncio.Lock()

    async def seed(self, snapshot: IntentTaskSnapshotV2) -> None:
        async with self._lock:
            key = (snapshot.tenant_id, snapshot.task_id)
            if key in self._snapshots:
                raise ValueError("INTENT_TASK_ALREADY_EXISTS")
            self._snapshots[key] = snapshot

    async def load(self, tenant_id: str, task_id: str) -> IntentTaskSnapshotV2 | None:
        async with self._lock:
            return self._snapshots.get((tenant_id, task_id))

    async def lookup(
        self,
        tenant_id: str,
        task_id: str,
        message_id: str,
        message_digest: str,
    ) -> _CommitResult | None:
        async with self._lock:
            stored = self._records.get((tenant_id, task_id, message_id))
            if stored is None:
                return None
            if stored.message_digest != message_digest:
                return _CommitResult("MESSAGE_CONFLICT")
            return _CommitResult("REPLAY", stored.prepared)

    async def commit(
        self,
        *,
        tenant_id: str,
        task_id: str,
        expected_revision: int,
        message_id: str,
        message_digest: str,
        prepared: PreparedIntentV2,
    ) -> _CommitResult:
        async with self._lock:
            record_key = (tenant_id, task_id, message_id)
            stored = self._records.get(record_key)
            if stored is not None:
                if stored.message_digest != message_digest:
                    return _CommitResult("MESSAGE_CONFLICT")
                return _CommitResult("REPLAY", stored.prepared)
            snapshot_key = (tenant_id, task_id)
            current = self._snapshots.get(snapshot_key)
            current_revision = (
                current.frame.revision
                if current is not None and current.frame is not None
                else 0
            )
            if current_revision != expected_revision:
                return _CommitResult("CONFLICT")
            if (
                prepared.frame is None
                or prepared.frame.revision != expected_revision + 1
            ):
                return _CommitResult("CONFLICT")
            committed_prepared = replace(
                prepared,
                committed=True,
                dispatch_allowed=_dispatch_eligible(prepared),
            )
            next_run_id, next_status = _next_run_state(current, committed_prepared)
            next_rounds = (
                (current.clarification_rounds if current else 0) + 1
                if committed_prepared.decision.outcome == "CLARIFY"
                else 0
            )
            self._snapshots[snapshot_key] = IntentTaskSnapshotV2(
                tenant_id=tenant_id,
                task_id=task_id,
                task_version="intent-v2",
                frame=committed_prepared.frame,
                run_id=next_run_id,
                run_status=next_status,
                clarification_rounds=next_rounds,
            )
            self._records[record_key] = _StoredRecord(
                message_digest, committed_prepared
            )
            return _CommitResult("COMMITTED", committed_prepared)


class IntentPipelineV2:
    def __init__(
        self,
        *,
        repository: IntentTaskRepositoryV2,
        interpreter: ControlledIntentInterpreterV2,
        validator: IntentPatchValidator,
        reducer: IntentStateReducer,
        temporal_resolver: TemporalResolver,
        binder: CapabilityBinderV2,
        decision_policy: IntentDecisionPolicyV2,
        brief_builder: ResearchBriefBuilderV2,
        scenario_adapter: ScenarioInputAdapter,
    ) -> None:
        self.repository = repository
        self.interpreter = interpreter
        self.validator = validator
        self.reducer = reducer
        self.temporal_resolver = temporal_resolver
        self.binder = binder
        self.decision_policy = decision_policy
        self.brief_builder = brief_builder
        self.scenario_adapter = scenario_adapter

    async def prepare(
        self,
        message: TrustedMessageV2,
        trusted_context: IntentPipelineContextV2,
    ) -> PreparedIntentV2:
        self._validate_request(message, trusted_context)
        tenant_id = trusted_context.research_context.tenant_id
        digest = _message_digest(tenant_id, message)
        replay = await self.repository.lookup(
            tenant_id, message.task_id, message.message_id, digest
        )
        if replay is not None:
            if replay.status == "MESSAGE_CONFLICT":
                return self._failure(
                    "INTENT_MESSAGE_ID_CONFLICT", trusted_context, None
                )
            if replay.prepared is None:
                return self._failure("INTENT_REPLAY_INVALID", trusted_context, None)
            return replace(
                replay.prepared,
                replayed=True,
                dispatch_allowed=False,
            )

        snapshot = await self.repository.load(tenant_id, message.task_id)
        if snapshot is not None and snapshot.task_version == "intent-v1":
            raise IntentPipelineBypass("TASK_VERSION_V1")
        previous = snapshot.frame if snapshot is not None else None
        expected_revision = previous.revision if previous is not None else 0
        versions = _versions(trusted_context)
        try:
            execution = await self.interpreter.execute(
                message.text,
                trusted_context.intent_context,
                previous,
                trusted_context.catalog,
                trusted_context.lease,
            )
        except IntentInterpretationV2Error as exc:
            return self._failure(
                exc.code,
                trusted_context,
                previous,
                usage=exc.usage,
                provider_calls=exc.provider_calls,
                prompt_versions=exc.prompt_versions,
            )
        except Exception:  # noqa: BLE001 -- 边界必须把未知 Provider 故障收敛为安全错误。
            return self._failure(
                "INTENT_PROVIDER_UNAVAILABLE", trusted_context, previous
            )

        versions = replace(versions, prompt_versions=execution.prompt_versions)
        validated = self.validator.validate(
            execution.patch,
            trusted_context.visible_user_messages,
            TrustedIntentScope(
                task_id=message.task_id,
                current_message_id=message.message_id,
                user_message_ids=frozenset(trusted_context.visible_user_messages),
                visible_revisions=(
                    frozenset({previous.revision})
                    if previous is not None
                    else frozenset()
                ),
                allowed_default_policy_ids=trusted_context.allowed_default_policy_ids,
                allowed_normalizer_versions=trusted_context.allowed_normalizer_versions,
                allowed_intent_parameter_names=(
                    trusted_context.allowed_intent_parameter_names
                ),
            ),
        )
        if not validated.is_valid:
            return self._failure(
                validated.error_code or "INTENT_SCHEMA_INVALID",
                trusted_context,
                previous,
                usage=execution.usage,
                provider_calls=execution.provider_calls,
                versions=versions,
            )
        try:
            frame = self.reducer.apply(previous, validated, message)
            if frame.temporal is not None and frame.temporal.value is not None:
                self.temporal_resolver.resolve(
                    frame.temporal.value,
                    frame.anchor_time,
                    frame.timezone,
                )
        except (IntentReductionError, TemporalResolutionError) as exc:
            return self._failure(
                getattr(exc, "code", "INTENT_REDUCTION_FAILED"),
                trusted_context,
                previous,
                usage=execution.usage,
                provider_calls=execution.provider_calls,
                versions=versions,
            )

        plan = self.binder.bind(
            frame, trusted_context.catalog, trusted_context.permissions
        )
        decision = self.decision_policy.decide(frame, plan)
        if (
            decision.outcome == "CLARIFY"
            and snapshot is not None
            and snapshot.clarification_rounds >= 2
        ):
            return self._failure(
                "CLARIFICATION_LIMIT_EXCEEDED",
                trusted_context,
                previous,
                usage=execution.usage,
                provider_calls=execution.provider_calls,
                versions=versions,
            )
        if decision.outcome == "FAILED":
            return PreparedIntentV2(
                decision=decision,
                frame=frame,
                brief=None,
                scenario_projection=None,
                usage=execution.usage,
                provider_calls=execution.provider_calls,
                versions=versions,
                lifecycle_action="NO_DISPATCH",
                run_id=snapshot.run_id if snapshot else None,
                replacement_run_id=None,
                committed=False,
                replayed=False,
                dispatch_allowed=False,
            )

        lifecycle, run_id, replacement_run_id = _lifecycle(
            snapshot, frame, decision, trusted_context.proposed_run_id
        )
        target_run_id = replacement_run_id or run_id
        try:
            brief, projection = self._prepare_outputs(
                frame,
                plan,
                decision,
                trusted_context,
                target_run_id=target_run_id,
            )
        except ResearchBridgeError as exc:
            return self._failure(
                exc.code,
                trusted_context,
                previous,
                usage=execution.usage,
                provider_calls=execution.provider_calls,
                versions=versions,
            )
        optimistic = PreparedIntentV2(
            decision=decision,
            frame=frame,
            brief=brief,
            scenario_projection=projection,
            usage=execution.usage,
            provider_calls=execution.provider_calls,
            versions=versions,
            lifecycle_action=lifecycle,
            run_id=run_id,
            replacement_run_id=replacement_run_id,
            committed=False,
            replayed=False,
            dispatch_allowed=False,
        )
        committed = await self.repository.commit(
            tenant_id=tenant_id,
            task_id=message.task_id,
            expected_revision=expected_revision,
            message_id=message.message_id,
            message_digest=digest,
            prepared=optimistic,
        )
        if committed.status == "REPLAY" and committed.prepared is not None:
            return replace(
                committed.prepared,
                replayed=True,
                dispatch_allowed=False,
            )
        if committed.status == "MESSAGE_CONFLICT":
            return self._failure(
                "INTENT_MESSAGE_ID_CONFLICT",
                trusted_context,
                previous,
                usage=execution.usage,
                provider_calls=execution.provider_calls,
                versions=versions,
            )
        if committed.status != "COMMITTED":
            return self._failure(
                "INTENT_CAS_CONFLICT",
                trusted_context,
                previous,
                usage=execution.usage,
                provider_calls=execution.provider_calls,
                versions=versions,
            )
        if committed.prepared is None:
            return self._failure(
                "INTENT_COMMIT_RESULT_INVALID",
                trusted_context,
                previous,
                usage=execution.usage,
                provider_calls=execution.provider_calls,
                versions=versions,
            )
        return committed.prepared

    def _prepare_outputs(
        self,
        frame: IntentFrameV2,
        plan: CapabilityPlanV2,
        decision: IntentDecision,
        context: IntentPipelineContextV2,
        *,
        target_run_id: str | None,
    ) -> tuple[ResearchBriefV2 | None, ScenarioProjectionV2 | None]:
        if decision.outcome != "READY" or frame.dialog_act in {"chat", "cancel"}:
            return None, None
        projection = self.scenario_adapter.project(frame, plan)
        if not projection.supported:
            raise ResearchBridgeError("INTENT_NOT_READY")
        research_selected = any(
            step.capability_id == OperationSpecialistCapabilityId.RESEARCH_INSIGHT.value
            for step in plan.steps
        )
        if research_selected and target_run_id is None:
            raise ResearchBridgeError("INTENT_NOT_READY")
        brief = (
            self.brief_builder.build(
                frame,
                context.research_context.model_copy(update={"run_id": target_run_id}),
                context.research_policy,
            )
            if research_selected
            else None
        )
        return brief, projection

    @staticmethod
    def _validate_request(
        message: TrustedMessageV2,
        context: IntentPipelineContextV2,
    ) -> None:
        if message.task_id != context.research_context.task_id:
            raise ValueError("INTENT_TRUSTED_TASK_MISMATCH")
        if message.message_id != context.intent_context.current_message_id:
            raise ValueError("INTENT_CURRENT_MESSAGE_MISMATCH")
        if context.visible_user_messages.get(message.message_id) != message.text:
            raise ValueError("INTENT_CURRENT_TEXT_MISMATCH")

    @staticmethod
    def _failure(
        code: str,
        context: IntentPipelineContextV2,
        frame: IntentFrameV2 | None,
        *,
        usage: UsageSnapshot | None = None,
        provider_calls: int = 0,
        prompt_versions: tuple[str, ...] = (),
        versions: IntentPipelineVersionsV2 | None = None,
    ) -> PreparedIntentV2:
        resolved_versions = versions or _versions(context)
        if prompt_versions:
            resolved_versions = replace(
                resolved_versions, prompt_versions=prompt_versions
            )
        return PreparedIntentV2(
            decision=IntentDecision(outcome="FAILED", reason_codes=(code,)),
            frame=frame,
            brief=None,
            scenario_projection=None,
            usage=usage or UsageSnapshot(),
            provider_calls=provider_calls,
            versions=resolved_versions,
            lifecycle_action="NO_DISPATCH",
            run_id=None,
            replacement_run_id=None,
            committed=False,
            replayed=False,
            dispatch_allowed=False,
        )


def _versions(context: IntentPipelineContextV2) -> IntentPipelineVersionsV2:
    return IntentPipelineVersionsV2(
        catalog_version=context.catalog.catalog_version,
        context_version=context.intent_context.context_version,
        permission_version=context.permissions.version,
        lease_id=context.lease.lease_id,
        lease_version=context.lease.version,
        policy_version=context.research_policy.policy_version,
    )


def _message_digest(tenant_id: str, message: TrustedMessageV2) -> str:
    canonical = (
        f"{tenant_id}\x00{message.task_id}\x00{message.message_id}\x00{message.text}"
    )
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def _lifecycle(
    snapshot: IntentTaskSnapshotV2 | None,
    frame: IntentFrameV2,
    decision: IntentDecision,
    proposed_run_id: str,
) -> tuple[LifecycleAction, str | None, str | None]:
    current_run_id = snapshot.run_id if snapshot is not None else None
    current_status = snapshot.run_status if snapshot is not None else None
    if frame.dialog_act == "cancel":
        return "CANCEL_EXISTING", current_run_id, None
    if frame.dialog_act == "chat":
        return "RESPOND_DIRECT", current_run_id, None
    if decision.outcome == "CLARIFY":
        return "WAIT_FOR_INPUT", current_run_id or proposed_run_id, None
    if decision.outcome == "UNSUPPORTED":
        return "NO_DISPATCH", current_run_id, None
    if current_status == "waiting_input" and current_run_id is not None:
        return "RESUME_RUN", current_run_id, None
    if current_status in {"queued", "running"} and current_run_id is not None:
        return (
            "SUPERSEDE_AT_SAFE_BOUNDARY",
            current_run_id,
            proposed_run_id,
        )
    return "START_NEW_RUN", proposed_run_id, None


def _next_run_state(
    current: IntentTaskSnapshotV2 | None,
    prepared: PreparedIntentV2,
) -> tuple[str | None, RunLifecycleStatus | None]:
    if prepared.lifecycle_action == "START_NEW_RUN":
        return prepared.run_id, "queued"
    if prepared.lifecycle_action == "RESUME_RUN":
        return prepared.run_id, "queued"
    if prepared.lifecycle_action == "WAIT_FOR_INPUT":
        return prepared.run_id, "waiting_input"
    if prepared.lifecycle_action == "SUPERSEDE_AT_SAFE_BOUNDARY":
        return (
            current.run_id if current else prepared.run_id,
            current.run_status if current else "running",
        )
    if current is None:
        return None, None
    return current.run_id, current.run_status


def _dispatch_eligible(prepared: PreparedIntentV2) -> bool:
    return prepared.decision.outcome == "READY" and prepared.lifecycle_action in {
        "START_NEW_RUN",
        "RESUME_RUN",
    }


__all__ = [
    "InMemoryIntentTaskRepositoryV2",
    "IntentPipelineBypass",
    "IntentPipelineContextV2",
    "IntentPipelineV2",
    "IntentPipelineVersionsV2",
    "IntentTaskRepositoryV2",
    "IntentTaskSnapshotV2",
    "PreparedIntentV2",
]
