"""统一完整计数、元数据绑定及持久发送门禁；不执行网络。"""

import hashlib
import hmac
import json
import time
from collections.abc import Callable
from dataclasses import asdict, replace

from efficiency_platform_agent.context.policy import ContextPiece, ContextPolicy
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
from efficiency_platform_agent.core.run import ProviderRequest


class ContextController:
    def __init__(
        self,
        counter: TokenCounter,
        store: ContextManifestStore,
        hmac_key: bytes,
        *,
        validator: MemoryPacketValidator | None = None,
        clock: Callable[[], float] = time.time,
    ):
        if type(hmac_key) is not bytes or len(hmac_key) < 32:
            raise ValueError("CONTEXT_HMAC_KEY_INVALID")
        self._counter = counter
        self._store = store
        self._key = hmac_key
        self._validator = validator
        self._clock = clock

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
            if (
                operation.memory_disabled
                or not packet.issued_at <= self._clock() < packet.expires_at
            ):
                raise ValueError("CONTEXT_PACKET_INVALID")
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
            predicted_generation_tokens=limits.output_reserve_tokens,
            cpu_before_tokens=view.before_measurement.total_upper_bound,
            cpu_after_tokens=view.measurement.total_upper_bound,
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
