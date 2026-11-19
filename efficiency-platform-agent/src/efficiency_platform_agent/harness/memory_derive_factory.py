"""原服务的派生组合；复用原HTTP守卫与SQLite总账，不初始化或授权费用。"""

import sqlite3
from contextlib import closing

from efficiency_platform_agent.capabilities.model.memory_derive import (
    DeriveDispatchAuthority,
    DeriveGateway,
)
from efficiency_platform_agent.capabilities.model.memory_derive_handler import (
    MemoryDeriveHandler,
)
from efficiency_platform_agent.context.controller import ContextController
from efficiency_platform_agent.context.dispatch import (
    ContextDispatch,
    ControlledModelProvider,
)
from efficiency_platform_agent.core.context_dispatch import bind_context_send_lease
from efficiency_platform_agent.persistence.context_manifest import (
    MySqlContextManifestStore,
)
from efficiency_platform_agent.persistence.context_stage import MySqlContextStageStore
from efficiency_platform_agent.persistence.derive_operation import (
    SqliteDeriveOperationStore,
)
from efficiency_platform_agent.providers.deepseek_stream import (
    DeepSeekStreamingProvider,
)

from .memory_derive_coordinator import MemoryDeriveCoordinator
from .memory_derive_runtime import LiveOriginalDeriveFrames


def build_memory_derive_coordinator(
    *,
    engine,
    client,
    ledger,
    cipher,
    hmac_key,
    metadata,
    execution_store,
    api_key,
    base_url,
    notify_waitasync,
    send_authority,
):
    if send_authority is None:
        raise ValueError("MEMORY_SEND_LEASE_REQUIRED")
    if (
        metadata.node_id != "memory.derive"
        or metadata.limits.output_reserve_tokens != 500
        or metadata.policy_version != "derive/1"
        or (metadata.prompt_version, metadata.output_schema_version)
        not in {
            ("derive-prompt/2", "derive-schema/2"),
            ("derive-prompt/3", "derive-schema/3"),
        }
        or not metadata.capacity.verified
    ):
        raise ValueError("MEMORY_DERIVE_PUBLICATION_REQUIRED")
    store = SqliteDeriveOperationStore(ledger)
    try:
        with closing(ledger._db()) as connection:
            connection.execute(
                "SELECT tenant,task,binding,fingerprint,state,result FROM derive_operations LIMIT 0"
            )
    except (sqlite3.Error, OSError):
        raise ValueError("MEMORY_DERIVE_SCHEMA_REQUIRED") from None
    stages = MySqlContextStageStore(engine, hmac_key)
    frames = LiveOriginalDeriveFrames(execution_store, stage_authority=stages)

    def gateway_factory(frame, authorizer, hydrator):
        if (
            frame.assets.model_ref != metadata.capacity.model_version
            or frame.assets.prompt_ref != metadata.prompt_version
            or frame.assets.schema_ref != metadata.output_schema_version
            or not frame.baseline.capacity.verified
        ):
            raise ValueError("DERIVE_PUBLISHED_ASSET_MISMATCH")
        dispatch_authority = DeriveDispatchAuthority()
        manifests = MySqlContextManifestStore(
            engine, memory_execution_store=send_authority.execution_store
        )
        manifests.install_result_authority(send_authority)
        controller = ContextController(
            frame.counter, manifests, hmac_key, validator=frames
        )
        dispatch = ContextDispatch(
            controller,
            manifests,
            dispatch_authority,
            stage_store=stages,
            hmac_key=hmac_key,
        )
        raw = DeepSeekStreamingProvider(
            client,
            metadata.capacity.model,
            api_key=api_key,
            base_url=base_url,
            max_retries=0,
        )
        provider = ControlledModelProvider(
            raw,
            dispatch,
            metadata.capacity.provider,
            metadata.capacity.model,
            paid_transport=True,
        )
        gateway = DeriveGateway(
            provider=provider,
            dispatch_authority=dispatch_authority,
            store=store,
            counter=frame.counter,
            capacity=metadata.capacity,
            limits=metadata.limits,
            cipher=cipher,
            hmac_key=hmac_key,
            authorizer=authorizer,
            hydrator=hydrator,
        )
        return _LeasedDeriveGateway(gateway, send_authority)

    handler = MemoryDeriveHandler(frames, gateway_factory, enabled=True)
    return MemoryDeriveCoordinator(
        frames, handler, ledger, metadata, execution_store, notify_waitasync
    )


class _LeasedDeriveGateway:
    def __init__(self, gateway, send_authority):
        self.gateway, self.send_authority = gateway, send_authority

    async def derive(self, scope, mode, sources, operation):
        with bind_context_send_lease(self.send_authority):
            return await self.gateway.derive(scope, mode, sources, operation)
