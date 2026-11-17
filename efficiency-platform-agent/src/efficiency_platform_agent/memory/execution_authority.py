"""每次发送从本机技术权威重读原授权；复用D13P全部包校验。"""

from efficiency_platform_agent.core.context_dispatch import current_model_stage
from efficiency_platform_agent.core.context_ports import ContextOperation
from efficiency_platform_agent.core.memory import (
    ExecutionScope,
    MemoryContextPacket,
    SourceDependency,
)
from efficiency_platform_agent.core.memory_execution import (
    MemoryExecutionRecord,
    MemoryExecutionStore,
)
from efficiency_platform_agent.core.run_context_binding import current_run_context
from efficiency_platform_agent.security.memory_packet import (
    AuthorizedMemoryPacketValidator,
    MemoryExecutionAuthorization,
    MemoryPacketBinding,
)


class _StoredAuthority:
    def __init__(
        self, record: MemoryExecutionRecord, authorization: MemoryExecutionAuthorization
    ):
        self.record = record
        self.authorization = authorization

    def current(
        self, authorization: MemoryExecutionAuthorization
    ) -> MemoryPacketBinding | None:
        record, packet = self.record, self.record.context.packet
        if authorization != self.authorization or record.state != "ACTIVE":
            return None
        return MemoryPacketBinding(
            packet.packet_id,
            packet.packet_revision,
            record.execution_revision,
            record.grant_epoch,
            record.source_epoch,
            record.deletion_epoch,
            record.context.packet_digest,
            packet.safety_dependencies,
        )


class StoredMemoryPacketValidator:
    def __init__(self, store: MemoryExecutionStore):
        self.store = store

    async def validator(self, scope: ExecutionScope) -> AuthorizedMemoryPacketValidator:
        binding = current_run_context()
        if binding is None or binding.memory_context is None:
            raise ValueError("MEMORY_RUN_BINDING_REQUIRED")
        record = await self.store.get(scope.conversation.tenant_id, scope.execution_id)
        if (
            record is None
            or record.context != binding.memory_context
            or record.deadline_epoch_seconds != binding.deadline_epoch_seconds
        ):
            raise ValueError("MEMORY_ACCESS_REVOKED")
        stage = current_model_stage()
        node_id = stage.node_id if stage is not None else scope.subtask_id
        if not any(
            (grant.node_id, grant.execution_agent_id, grant.purpose)
            == (node_id, scope.execution_agent_id, scope.purpose)
            for grant in record.context.execution_grants
        ):
            raise ValueError("MEMORY_EXECUTION_GRANT_DENIED")
        context, packet = record.context, record.context.packet
        authorization = MemoryExecutionAuthorization(
            scope,
            context.policy,
            packet.semantic_input_hash,
            packet.parent_authorization_ref,
            record.deadline_epoch_seconds,
            context.semantic_snapshot_digest,
        )
        return AuthorizedMemoryPacketValidator(
            authorization, _StoredAuthority(record, authorization)
        )

    async def validate(
        self,
        scope: ExecutionScope,
        packet: MemoryContextPacket | None,
        dependencies: tuple[SourceDependency, ...],
        operation: ContextOperation,
    ) -> None:
        validator = await self.validator(scope)
        await validator.validate(scope, packet, dependencies, operation)
