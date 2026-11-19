"""只从当前已鉴权原执行解封摘要快照；按原本机权威重核后供上下文选择。"""

import hashlib
import json

from efficiency_platform_agent.contracts.memory_summary_context import (
    MemorySummaryContextSnapshot,
)
from efficiency_platform_agent.core.context_ports import ContextOperation
from efficiency_platform_agent.core.run_context_binding import current_run_context
from efficiency_platform_agent.harness.memory_summary_context import (
    OriginalMessageProjection,
)
from efficiency_platform_agent.memory.execution_authority import (
    StoredMemoryPacketValidator,
)
from efficiency_platform_agent.memory.summary_selection import CommittedSummary


class BoundMemorySummaryContext:
    def __init__(self, execution_store):
        self.execution_store = execution_store

    async def _current(self, scope, packet):
        binding = current_run_context()
        if (
            binding is None
            or binding.memory_context is None
            or binding.memory_context.packet != packet
        ):
            raise PermissionError("MEMORY_SUMMARY_CONTEXT_INVALID")
        raw = binding.memory_context.summary_context_json
        if raw is None:
            return None
        snapshot = MemorySummaryContextSnapshot.model_validate_json(raw)
        if snapshot.scope.to_core() != scope.conversation:
            raise PermissionError("MEMORY_SUMMARY_SCOPE_MISMATCH")
        await StoredMemoryPacketValidator(self.execution_store).validate(
            scope,
            packet,
            packet.safety_dependencies,
            ContextOperation(
                "summary-context-read", 1, binding.deadline_epoch_seconds, False
            ),
        )
        return snapshot

    async def original_messages(self, scope, packet):
        snapshot = await self._current(scope, packet)
        if snapshot is None:
            return ()
        result = []
        for item in snapshot.original_messages:
            dependencies = tuple(dep.to_core() for dep in item.safety_dependencies)
            if not set(dependencies).issubset(packet.safety_dependencies) or not any(
                dep.source_type == "MESSAGE"
                and dep.source_id == item.message_id
                and dep.source_version == item.content_sha256
                for dep in dependencies
            ):
                raise PermissionError("MEMORY_SUMMARY_SOURCE_MISMATCH")
            result.append(
                OriginalMessageProjection(
                    item.message_id,
                    item.role,
                    item.content_sha256,
                    dependencies,
                    item.group_completed,
                )
            )
        return tuple(result)

    async def current(self, scope, packet):
        snapshot = await self._current(scope, packet)
        if snapshot is None:
            return ()
        result = []
        for item in snapshot.summaries:
            segment = item.segment
            dependency = item.summary_dependency.to_core()
            digest = hashlib.sha256(
                json.dumps(
                    segment.model_dump(mode="json"),
                    ensure_ascii=False,
                    sort_keys=True,
                    separators=(",", ":"),
                ).encode()
            ).hexdigest()
            if (
                segment.scope.to_core() != scope.conversation
                or dependency.source_type != "SUMMARY"
                or dependency.source_id != segment.segment_id
                or dependency.source_version != digest
                or not {dep.to_core() for dep in item.current_dependencies}.issubset(
                    packet.safety_dependencies
                )
            ):
                raise PermissionError("MEMORY_SUMMARY_SOURCE_MISMATCH")
            result.append(
                CommittedSummary(
                    segment,
                    item.sources,
                    item.basis_events,
                    item.source_revision,
                    item.authority_ref,
                    item.commit_ref,
                    item.status,
                    item.authorized,
                    tuple(dep.to_core() for dep in item.current_dependencies),
                    item.retention_ref,
                    item.expires_at,
                    dependency,
                    item.covered_message_ids,
                )
            )
        return tuple(result)
