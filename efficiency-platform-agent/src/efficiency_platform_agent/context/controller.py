"""统一完整计数、元数据绑定及持久发送门禁；不执行网络。"""

import hashlib
import hmac
import json
import time
from collections.abc import Callable, Iterator
from contextlib import contextmanager
from contextvars import ContextVar
from dataclasses import asdict, dataclass, field, replace
from typing import Protocol

from efficiency_platform_agent.context.compaction import CompactionBaseline
from efficiency_platform_agent.context.growth import GrowthBound, evaluate_growth
from efficiency_platform_agent.context.policy import (
    ContextPiece,
    ContextPolicy,
    render_context_messages,
)
from efficiency_platform_agent.context.selection import select_context
from efficiency_platform_agent.core.context_control import (
    ContextManifest,
    ModelCapacity,
    PreparedContext,
    TokenCounter,
    WindowLimits,
)
from efficiency_platform_agent.core.context_ports import (
    ContextManifestStore,
    ContextMetadata,
    ContextOperation,
    MemoryPacketValidator,
)
from efficiency_platform_agent.core.memory import ExecutionScope, MemoryContextPacket
from efficiency_platform_agent.core.run import ProviderMessage, ProviderRequest
from efficiency_platform_agent.memory.summary_selection import (
    CommittedSummary,
    select_committed_summaries,
)
from efficiency_platform_agent.providers.llm.request_counter import (
    ConservativeRequestTokenCounter,
)


class SummaryContextReader(Protocol):
    async def current(
        self, scope: ExecutionScope, packet: MemoryContextPacket
    ) -> tuple[CommittedSummary, ...]: ...


class BaselineHandle(Protocol):
    def close(self) -> None: ...


class DeriveBaselineObserver(Protocol):
    def observe_baseline(
        self, baseline: CompactionBaseline, operation: ContextOperation
    ) -> BaselineHandle | None: ...


@dataclass(frozen=True, slots=True)
class OriginalHistorySnapshot:
    """服务端精确拆分完成后留下的原消息边界证明，不从HTTP构造。"""

    scope: ExecutionScope
    packet_id: str
    packet_revision: int
    original_messages: tuple[ProviderMessage, ...] = field(repr=False)
    message_ids: frozenset[str]


@dataclass(frozen=True, slots=True)
class ExactHistoryContextPolicy(ContextPolicy):
    original_history_snapshot: OriginalHistorySnapshot | None = None


@dataclass(slots=True)
class _BaselineScope:
    handles: list[BaselineHandle] = field(default_factory=list)
    active: bool = True


class ContextController:
    def __init__(
        self,
        counter: TokenCounter,
        store: ContextManifestStore,
        hmac_key: bytes,
        *,
        validator: MemoryPacketValidator | None = None,
        clock: Callable[[], float] = time.time,
        summary_context_port: SummaryContextReader | None = None,
        derive_runtime: DeriveBaselineObserver | None = None,
        generation_bound: GrowthBound | None = None,
    ):
        if type(hmac_key) is not bytes or len(hmac_key) < 32:
            raise ValueError("CONTEXT_HMAC_KEY_INVALID")
        self._counter = counter
        self._store = store
        self._key = hmac_key
        self._validator = validator
        self._clock = clock
        self._manifest_authorization_validator = None
        self._summary_context_port = summary_context_port
        self._derive_runtime = derive_runtime
        self._generation_bound = generation_bound
        self._baseline_handles: ContextVar[_BaselineScope | None] = ContextVar(
            "context_baseline_handles", default=None
        )

    @contextmanager
    def baseline_scope(self) -> Iterator[None]:
        """正式Dispatch持有prepare到send结束的原节点窗口，退出撤销全部登记。"""
        scope = _BaselineScope()
        token = self._baseline_handles.set(scope)
        try:
            yield
        finally:
            scope.active = False
            for handle in reversed(scope.handles):
                handle.close()
            scope.handles.clear()
            self._baseline_handles.reset(token)

    def install_derive_runtime(self, runtime: DeriveBaselineObserver) -> None:
        if self._derive_runtime is not None:
            raise ValueError("DERIVE_RUNTIME_ALREADY_BOUND")
        self._derive_runtime = runtime

    def install_manifest_authorization_validator(self, validator) -> None:
        if self._manifest_authorization_validator is not None or not callable(
            validator
        ):
            raise ValueError("MEMORY_MANIFEST_AUTHORITY_ALREADY_BOUND")
        self._manifest_authorization_validator = validator

    def install_memory_validator(self, validator: MemoryPacketValidator) -> None:
        if self._validator is not None:
            raise ValueError("MEMORY_VALIDATOR_ALREADY_BOUND")
        self._validator = validator

    def _digest(self, scope: ExecutionScope, value: object) -> str:
        encoded = json.dumps(
            value, sort_keys=True, separators=(",", ":"), ensure_ascii=False
        ).encode()
        tenant_key = hmac.digest(
            self._key, scope.conversation.tenant_id.encode(), "sha256"
        )
        return hmac.new(tenant_key, encoded, hashlib.sha256).hexdigest()

    def check_deadline(self, operation: ContextOperation) -> None:
        """发送边界沿用原时钟复验绝对截止，不重建或延长授权。"""
        if self._clock() >= operation.deadline_epoch_seconds:
            raise ValueError("CONTEXT_DEADLINE_EXCEEDED")

    async def _authority(
        self,
        scope: ExecutionScope,
        packet: MemoryContextPacket | None,
        operation: ContextOperation,
        dependencies: tuple,
    ) -> None:
        self.check_deadline(operation)
        if packet is None:
            if not operation.memory_disabled:
                raise ValueError("CONTEXT_PACKET_REQUIRED")
        else:
            packet.validate_scope(scope.conversation, scope.task_id, scope.execution_id)
            if operation.memory_disabled or self._clock() < packet.issued_at:
                raise ValueError("CONTEXT_PACKET_INVALID")
            if self._clock() >= packet.expires_at:
                raise ValueError(
                    "CONTEXT_PACKET_EXPIRED"
                    if self._manifest_authorization_validator is not None
                    else "CONTEXT_PACKET_INVALID"
                )
            if not set(dependencies).issubset(packet.safety_dependencies):
                raise ValueError("CONTEXT_PACKET_DEPENDENCIES_INVALID")
        if packet is not None or dependencies:
            if self._validator is None:
                raise ValueError("CONTEXT_LIVE_VALIDATOR_REQUIRED")
            await self._validator.validate(scope, packet, dependencies, operation)

    async def prepare(
        self,
        request_template: ProviderRequest,
        scope: ExecutionScope,
        policy: ContextPolicy,
        pieces: tuple[ContextPiece, ...],
        capacity: ModelCapacity,
        limits: WindowLimits,
        metadata: ContextMetadata,
        packet: MemoryContextPacket | None = None,
        *,
        operation: ContextOperation,
    ) -> PreparedContext:
        if (
            metadata.node_id,
            metadata.policy_version,
            metadata.capacity,
            metadata.limits,
            metadata.options,
        ) != (
            policy.node_id,
            policy.version,
            capacity,
            limits,
            request_template.options,
        ):
            raise ValueError("CONTEXT_BINDING_MISMATCH")
        if (
            request_template.timeout_ms
            > max(0, operation.deadline_epoch_seconds - self._clock()) * 1000
        ):
            raise ValueError("CONTEXT_DEADLINE_EXCEEDED")
        await self._authority(scope, packet, operation, policy.authorized_dependencies)
        summary_before = summary_after = 0
        selected_summary_ids: tuple[str, ...] = ()
        if self._summary_context_port is not None and packet is not None:
            if type(self._counter) is not ConservativeRequestTokenCounter:
                raise ValueError("CONTEXT_CAPACITY_UNVERIFIED")
            committed = await self._summary_context_port.current(scope, packet)
            # 可信传输仍须在本次原packet下重核摘要自身及全部传递来源。
            current: list[CommittedSummary] = []
            blocked: set[str] = set()
            for item in committed:
                dependencies = tuple(
                    dict.fromkeys(
                        (
                            *(
                                dependency.to_core()
                                for dependency in item.segment.source_dependencies
                            ),
                            item.summary_dependency,
                        )
                    )
                )
                if (
                    item.status != "COMMITTED"
                    or not item.authorized
                    or item.expires_at <= self._clock()
                    or item.segment.scope.to_core() != scope.conversation
                    or not set(dependencies).issubset(policy.authorized_dependencies)
                    or not set(dependencies).issubset(item.current_dependencies)
                ):
                    blocked.add(item.segment.segment_id)
                    continue
                await self._authority(scope, packet, operation, dependencies)
                current.append(item)
            current = [
                item for item in current if item.segment.segment_id not in blocked
            ]
            if isinstance(policy, ExactHistoryContextPolicy):
                snapshot = policy.original_history_snapshot
                if snapshot is None or (
                    snapshot.scope != scope
                    or (snapshot.packet_id, snapshot.packet_revision)
                    != (packet.packet_id, packet.packet_revision)
                    or snapshot.message_ids != policy.allowed_message_ids
                    or snapshot.original_messages
                    != render_context_messages(policy,tuple(piece for piece in pieces if piece.kind!="memory"))
                ):
                    raise ValueError("CONTEXT_ORIGINAL_PROJECTION_CHANGED")
                policy = replace(
                    policy,
                    allowed_message_ids=policy.allowed_message_ids.union(
                        identifier
                        for item in current
                        for identifier in item.covered_message_ids
                    ),
                )
            selection = select_committed_summaries(
                pieces,
                tuple(current),
                policy,
                capacity,
                self._counter,
                now=int(self._clock()),
            )
            summary_before = self._counter.measure(
                request_template, capacity
            ).total_upper_bound
            selected_summary_ids = selection.selected_segments
            pieces = tuple(
                piece
                if isinstance(piece, ContextPiece)
                else ContextPiece(
                    piece.piece_id,
                    piece.scope,
                    piece.messages,
                    piece.safety_dependencies,
                    piece.required,
                    kind=piece.kind,
                    covered_message_ids=piece.covered_message_ids,
                    projection_aliases=getattr(piece, "projection_aliases", ()),
                )
                for piece in selection.pieces
            )
            request_template = replace(
                request_template,
                messages=render_context_messages(policy,pieces),
            )
            summary_after = self._counter.measure(
                request_template, capacity
            ).total_upper_bound
        view = select_context(
            scope,
            policy,
            pieces,
            limits,
            counter=self._counter,
            capacity=capacity,
            request_template=request_template,
        )
        if view.decision.status == "REJECT":
            raise ValueError("CONTEXT_REQUIRED_INPUT_TOO_LARGE")
        baseline_scope = self._baseline_handles.get()
        if (
            self._derive_runtime is not None
            and packet is not None
            and baseline_scope is not None
            and baseline_scope.active
        ):
            baseline = CompactionBaseline(
                view, capacity, limits, policy.version, packet.policy_version, policy
            )
            handle = self._derive_runtime.observe_baseline(baseline, operation)
            if handle is not None:
                baseline_scope.handles.append(handle)
        actual_summary_ids = {
            piece.piece_id.removeprefix("summary:")
            for piece in view.pieces
            if piece.kind == "summary"
        }.intersection(selected_summary_ids)
        if self._summary_context_port is not None:
            summary_after = (
                view.measurement.total_upper_bound
                if actual_summary_ids
                else summary_before
            )
        growth = evaluate_growth(
            limits, view.measurement, generation_bound=self._generation_bound
        )
        growth_enabled = (
            self._summary_context_port is not None or self._derive_runtime is not None
        )
        prediction_basis = "output-reserve"
        if growth_enabled:
            prediction_basis = (
                "context-growth/1:"
                + growth.actual_pressure
                + ":"
                + growth.predicted_pressure
            )
            if (
                growth.growth_source_ref is not None
                and growth.growth_version is not None
            ):
                prediction_basis += (
                    ":" + growth.growth_source_ref + ":" + growth.growth_version
                )
        aliases = tuple(
            alias
            for piece in view.pieces
            for alias in getattr(piece, "projection_aliases", ())
        )
        derive_binding = None
        if metadata.node_id == "memory.derive":
            binding_reader = getattr(self._validator, "derive_manifest_binding", None)
            if binding_reader is None:
                raise ValueError("DERIVE_ORIGINAL_FRAME_REQUIRED")
            derive_binding = await binding_reader(scope, operation)
        digest = self._digest(
            scope,
            {
                "request": asdict(view.request),
                "metadata": asdict(metadata),
                "operation": {
                    k: v for k, v in asdict(operation).items() if k != "attempt"
                },
                "scope": asdict(scope),
                "dependencies": [asdict(d) for d in view.selected_safety_dependencies],
                **({"summary_projection_aliases": aliases} if aliases else {}),
                **({"derive_binding_json": derive_binding} if derive_binding else {}),
            },
        )
        manifest = ContextManifest(
            digest[:32],
            scope,
            operation.operation_id,
            policy.node_id,
            operation.attempt,
            capacity.model_version,
            metadata.prompt_version,
            metadata.tool_version,
            metadata.output_schema_version,
            capacity.tokenizer_ref,
            capacity.serialization_ref,
            policy.version,
            packet.packet_id if packet else None,
            packet.packet_revision if packet else None,
            metadata.ctx_revision,
            view.selected_safety_dependencies,
            view.selected_safety_dependencies,
            view.exclusions,
            view.measurement,
            view.decision,
            limits.output_reserve_tokens,
            limits.safety_margin_tokens,
            digest,
            predicted_generation_tokens=(growth.G or 0)
            if growth_enabled
            else limits.output_reserve_tokens,
            prediction_basis=prediction_basis,
            cpu_before_tokens=view.before_measurement.total_upper_bound,
            cpu_after_tokens=view.measurement.total_upper_bound,
            summary_before_tokens=summary_before,
            summary_after_tokens=summary_after,
            summary_cas_status="COMMITTED" if actual_summary_ids else "not-applied",
            summary_adoption_status="ADOPTED" if actual_summary_ids else "not-applied",
            summary_projection_aliases=aliases,
            derive_binding_json=derive_binding,
        )
        saved = await self._store.save_manifest_once(manifest, operation)
        if saved != manifest:
            raise ValueError("CONTEXT_MANIFEST_CONFLICT_409")
        return PreparedContext(
            view.request, saved, packet.policy_version if packet else None
        )

    async def finalize(
        self,
        prepared: PreparedContext,
        scope: ExecutionScope,
        capacity: ModelCapacity,
        limits: WindowLimits,
        metadata: ContextMetadata,
        *,
        operation: ContextOperation,
        packet: MemoryContextPacket | None = None,
    ) -> PreparedContext:
        manifest = prepared.manifest
        if (
            manifest.model_version != capacity.model_version
            or manifest.tokenizer_ref != capacity.tokenizer_ref
            or manifest.serialization_ref != capacity.serialization_ref
            or manifest.output_reserve_tokens != limits.output_reserve_tokens
            or manifest.safety_margin_tokens != limits.safety_margin_tokens
            or manifest.decision.status == "REJECT"
        ):
            raise ValueError("CONTEXT_BINDING_MISMATCH")
        if (
            prepared.request.timeout_ms
            > max(0, operation.deadline_epoch_seconds - self._clock()) * 1000
        ):
            raise ValueError("CONTEXT_DEADLINE_EXCEEDED")
        if manifest.scope != scope or (manifest.operation_id, manifest.attempt) != (
            operation.operation_id,
            operation.attempt,
        ):
            raise ValueError("CONTEXT_BINDING_MISMATCH")
        if (
            metadata.node_id,
            metadata.policy_version,
            metadata.capacity,
            metadata.limits,
            metadata.options,
            metadata.ctx_revision,
            metadata.prompt_version,
            metadata.tool_version,
            metadata.output_schema_version,
        ) != (
            manifest.node_id,
            manifest.policy_version,
            capacity,
            limits,
            prepared.request.options,
            manifest.ctx_revision,
            manifest.prompt_version,
            manifest.tool_version,
            manifest.output_schema_version,
        ):
            raise ValueError("CONTEXT_BINDING_MISMATCH")
        if (manifest.packet_id, manifest.packet_revision) != (
            (packet.packet_id, packet.packet_revision) if packet else (None, None)
        ) and (
            packet is None
            or self._manifest_authorization_validator is None
            or not await self._manifest_authorization_validator(
                manifest, operation, packet
            )
        ):
            raise ValueError("CONTEXT_PACKET_INVALID")
        if (
            packet.policy_version if packet else None
        ) != prepared.memory_policy_version:
            raise ValueError("CONTEXT_POLICY_MISMATCH")
        await self._authority(scope, packet, operation, manifest.safety_dependencies)
        digest = self._digest(
            scope,
            {
                "request": asdict(prepared.request),
                "metadata": asdict(metadata),
                "operation": {
                    k: v for k, v in asdict(operation).items() if k != "attempt"
                },
                "scope": asdict(scope),
                "dependencies": [asdict(d) for d in manifest.selected_sources],
                **(
                    {"summary_projection_aliases": manifest.summary_projection_aliases}
                    if manifest.summary_projection_aliases
                    else {}
                ),
                **(
                    {"derive_binding_json": manifest.derive_binding_json}
                    if manifest.derive_binding_json
                    else {}
                ),
            },
        )
        if not hmac.compare_digest(digest, manifest.canonical_request_hmac):
            raise ValueError("CONTEXT_REQUEST_CHANGED")
        measurement = self._counter.measure(prepared.request, capacity)
        if (
            not measurement.verified
            or measurement.total_upper_bound > limits.input_cap()
        ):
            raise ValueError("CONTEXT_COUNT_DRIFT")
        receipt = await self._store.get_operation_receipt(scope, operation.operation_id)
        if (
            receipt is None
            or receipt.input_hash != digest
            or receipt.deadline_epoch_seconds != operation.deadline_epoch_seconds
            or receipt.status != "NOT_SENT"
            or receipt.latest_attempt != operation.attempt
        ):
            raise ValueError("CONTEXT_OPERATION_BLOCKED")
        self.check_deadline(operation)
        if not await self._store.mark_sending(manifest, operation):
            raise ValueError("CONTEXT_OPERATION_BLOCKED")
        return replace(prepared, manifest=replace(manifest, measurement=measurement))
