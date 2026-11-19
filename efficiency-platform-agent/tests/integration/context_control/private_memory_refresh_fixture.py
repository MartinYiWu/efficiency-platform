"""RF07复用正式客服/HTTP/MySQL/PG装配；唯一模型边界为固定Fake。"""

import asyncio
import json
import os
import time
from contextlib import asynccontextmanager

from sqlalchemy import text

from efficiency_platform_agent.core.context_dispatch import current_model_stage
from efficiency_platform_agent.core.enums import StrategyMode
from efficiency_platform_agent.core.execution_control import current_run_control
from efficiency_platform_agent.core.run_context_binding import current_run_context
from efficiency_platform_agent.harness.memory_runtime import (
    build_memory_binding_updater,
)
from tests.integration.context_control.private_memory_http_fixture import main


async def setup_refresh(components, controller, dispatch, customer, provider, bundle):
    service = components.refresh_service
    assert service is not None and components.send_authority is not None
    wait_node = os.environ.get("MEMORY_IT_REFRESH_NODE", "answer_general")
    if wait_node not in {"intent", "answer_general"}:
        raise ValueError("RF07_SYNTHETIC_WAIT_NODE_INVALID")
    domain = os.environ.get("MEMORY_IT_REFRESH_DOMAIN", "customer-service")
    if domain not in {"customer-service", "operations"}:
        raise ValueError("RF07_SYNTHETIC_WAIT_DOMAIN_INVALID")
    graph_waits = []
    counters = {
        "wait_events": 0,
        "delayed_finalizes": 0,
        "internal_wait_gets": 0,
        "internal_resume_posts": 0,
    }

    async def publish_wait(wait_id, execution_id, runtime_id):
        binding = current_run_context()
        if binding is None or binding.execution_id != execution_id:
            raise PermissionError("MEMORY_RUN_BINDING_REQUIRED")
        record = await components.store.get(
            binding.conversation.tenant_id, execution_id
        )
        wait = await service.get_wait(binding.conversation, execution_id)
        if (
            record is None
            or record.runtime_id != runtime_id
            or record.state != "ACTIVE"
            or wait is None
            or wait.wait_event_id != wait_id
            or wait.runtime_id != runtime_id
        ):
            raise PermissionError("MEMORY_REFRESH_CAPABILITY_UNSUPPORTED")
        if domain == "customer-service":
            if not await customer.notify_context_wait(record, wait_id):
                raise PermissionError("MEMORY_REFRESH_CAPABILITY_UNSUPPORTED")
        else:
            official = await components.saver._saver.conn.execute(
                "SELECT COUNT(*) AS n FROM checkpoints WHERE thread_id=%s AND checkpoint_ns='' AND checkpoint_id=%s",
                (runtime_id, wait.checkpoint_id),
            )
            official_present = (await official.fetchone())["n"] == 1
            owned = await components.owned.get(
                runtime_id, "s2:direct:1", binding.conversation.tenant_id
            )
            graph_waits.append(
                {
                    "checkpoint_mode": wait.checkpoint_mode.value,
                    "wait_phase": wait.wait_phase.value,
                    "checkpoint_id_present": bool(wait.checkpoint_id),
                    "official_checkpoint_present": official_present,
                    "owned_checkpoint_present": owned is not None
                    and owned.view.checkpoint_id == wait.checkpoint_id,
                }
            )
            await bundle.event_hub.publish_next(
                runtime_id, "context_refresh_required", {"wait_event_id": wait_id}
            )
        counters["wait_events"] += 1

    dispatch.install_refresh(service, components.store, on_wait=publish_wait)
    direct_gate = None
    if domain == "operations":
        bundle.runtime.memory_refresh_enabled = True
        from efficiency_platform_agent.orchestration.context_gate import (
            FencedModelProvider,
            MemoryDirectContextGate,
        )
        from efficiency_platform_agent.providers.llm.registry import (
            ModelProviderRegistry,
        )

        graph = bundle.runtime.graph_runtime
        builder = graph.registry.get(StrategyMode.DIRECT).builder
        model_runtime = builder.agent.model_runtime
        model_runtime.diagnostic_recorder = bundle.runtime.diagnostic_recorder
        from efficiency_platform_agent.orchestration.intent_interpreter import (
            IntentInterpreter,
        )

        bundle.conversation.interpreter = IntentInterpreter(
            model_runtime, timeout_ms=15000
        )
        providers = ModelProviderRegistry()
        for provider_id, controlled in model_runtime.registry.providers.items():
            providers.register(
                provider_id,
                FencedModelProvider(
                    controlled,
                    components.registry,
                    "official",
                    send_authority=components.send_authority,
                ),
            )
        model_runtime.registry = providers
        direct_gate = MemoryDirectContextGate(
            service,
            components.store,
            components.registry,
            components.send_authority,
            saver=components.saver,
            checkpoint_store=graph.checkpoints,
            dispatch=dispatch,
            on_wait=publish_wait,
        )
        components.saver.install_context_checkpoint_authority(direct_gate)
        graph.checkpoints.install_context_checkpoint_authority(direct_gate)
        builder.memory_gate = direct_gate
        service.checkpoint_verifier = direct_gate.verify_wait_checkpoint
        service.frame_verifier = direct_gate.verify_wait_frame
        service.wait_task_resolver = direct_gate.wait_frame_task
        original_wait_scope = components.registry.wait_checkpoint_scope

        @asynccontextmanager
        async def wait_scope(capability):
            issuer = service.wait_capability_task(capability)
            print(
                "RF07_OPS_WAIT_SCOPE "
                + json.dumps(
                    {
                        "capability_valid": service.validate_wait_capability(
                            capability
                        ),
                        "scope_task_valid": service.validate_wait_scope_task(
                            capability
                        ),
                        "existing_wait_context": components.registry._wait_checkpoint_context.get()
                        is not None,
                        "issuer_is_current": issuer is asyncio.current_task(),
                        "issuer_done": issuer is None or issuer.done(),
                        "control_present": current_run_control() is not None,
                        "registry_wait_authority_matches": components.registry._wait_authority
                        is service,
                    }
                ),
                flush=True,
            )
            async with original_wait_scope(capability) as owner:
                yield owner

        components.registry.wait_checkpoint_scope = wait_scope
        original_complete = provider.complete

        async def complete(request):
            result = await original_complete(request)
            stage, binding = current_model_stage(), current_run_context()
            if (
                stage is not None
                and stage.node_id == "intent"
                and counters["delayed_finalizes"] == 0
            ):
                delay = binding.memory_context.packet.expires_at - time.time() + 0.1
                if not 0 < delay <= 8:
                    raise ValueError("RF07_EXPECTED_SHORT_REAL_TTL")
                counters["delayed_finalizes"] += 1
                await asyncio.sleep(delay)
            return result

        provider.complete = complete
    else:
        service.frame_verifier = dispatch.verify_wait_frame
    service.binding_updater = build_memory_binding_updater(direct_gate, customer)
    original_finalize = controller.finalize

    async def finalize(*args, **kwargs):
        packet = kwargs.get("packet")
        if (
            domain == "customer-service"
            and args[1].subtask_id == "customer-service:" + wait_node
            and packet is not None
            and packet.packet_revision == 1
            and counters["delayed_finalizes"] == 0
        ):
            delay = packet.expires_at - time.time() + 0.1
            if not 0 < delay <= 8:
                raise ValueError("RF07_EXPECTED_SHORT_REAL_TTL")
            counters["delayed_finalizes"] += 1
            await asyncio.sleep(delay)
        return await original_finalize(*args, **kwargs)

    controller.finalize = finalize

    async def proof():
        executions = []
        async with components.store.store.engine.connect() as connection:
            records = (
                (
                    await connection.execute(
                        text(
                            "SELECT tenant_id,execution_id,context_fingerprint,current_context_fingerprint FROM agent_memory_execution WHERE runtime_kind=:kind"
                        ),
                        {
                            "kind": "OPERATIONS"
                            if domain == "operations"
                            else "CUSTOMER_SERVICE"
                        },
                    )
                )
                .mappings()
                .all()
            )
            journal = (
                (
                    await connection.execute(
                        text(
                            "SELECT record_kind,phase,dispatch_allowed,old_packet_revision,target_packet_revision,refresh_count,resume_start,body_ciphertext IS NOT NULL AS body_encrypted FROM agent_memory_context_refresh"
                        )
                    )
                )
                .mappings()
                .all()
            )
            operations = (
                await connection.execute(
                    text(
                        "SELECT m.metadata_json,o.status,r.sent_packet_revision FROM agent_context_manifest m JOIN agent_context_operation o USING(tenant_id,task_id,execution_id,operation_id) JOIN agent_memory_context_refresh r ON r.tenant_id=m.tenant_id AND r.execution_id=m.execution_id AND r.record_kind='RESULT' AND r.operation_id=m.operation_id AND r.attempt=m.attempt"
                    )
                )
            ).all()
        for row in records:
            tenant, execution = row["tenant_id"].decode(), row["execution_id"].decode()
            record = await components.store.get(tenant, execution)
            cursor = await components.registry.connection.execute(
                "SELECT current_context_fingerprint,refresh_count,state FROM agent_memory_thread_execution WHERE tenant_id=%s AND execution_id=%s",
                (tenant, execution),
            )
            pg = await cursor.fetchone()
            executions.append(
                {
                    "execution_id": execution,
                    "runtime_id": record.runtime_id,
                    "state": record.state,
                    "packet_revision": record.context.packet.packet_revision,
                    "execution_revision": record.execution_revision,
                    "original_deadline": record.deadline_epoch_seconds,
                    "original_context_fingerprint": row["context_fingerprint"],
                    "current_context_fingerprint": row["current_context_fingerprint"],
                    "pg_current_context_fingerprint": pg["current_context_fingerprint"],
                    "refresh_count": pg["refresh_count"],
                    "pg_state": pg["state"],
                }
            )
        actual_operations = []
        for raw, status, sent_revision in operations:
            manifest = json.loads(raw) if isinstance(raw, str) else raw
            actual_operations.append(
                {
                    "node_id": manifest["node_id"],
                    "packet_revision": manifest["packet_revision"],
                    "actual_sent_packet_revision": sent_revision,
                    "operation_id": manifest["operation_id"],
                    "attempt": manifest["attempt"],
                    "status": status,
                }
            )
        return counters | {
            "executions": executions,
            "operations": actual_operations,
            "refreshes": [
                {
                    key: bool(value)
                    if key in {"dispatch_allowed", "body_encrypted"}
                    else value
                    for key, value in row.items()
                    if key != "record_kind"
                }
                for row in journal
                if row["record_kind"] == "REFRESH"
            ],
            "results_count": sum(row["record_kind"] == "RESULT" for row in journal),
            "graph_waits": [
                item
                | {
                    "resume_start": next(
                        row["resume_start"]
                        for row in journal
                        if row["record_kind"] == "WAIT"
                    )
                }
                for item in graph_waits
            ],
        }

    def observe_http(request):
        path = request.url.path
        if path.startswith("/internal/v1/memory/executions/"):
            if request.method == "GET" and path.endswith("/wait"):
                counters["internal_wait_gets"] += 1
            elif request.method == "POST" and path.endswith("/resume"):
                counters["internal_resume_posts"] += 1

    proof.observe_http = observe_http
    return proof


if __name__ == "__main__":
    asyncio.run(
        main(refresh_setup=setup_refresh), loop_factory=asyncio.SelectorEventLoop
    )
