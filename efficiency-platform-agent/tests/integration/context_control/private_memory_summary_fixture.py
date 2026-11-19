"""真实M2自动主链：原Runtime/control/SQL/PG，唯一派生外部边界PaidHttp(MockTransport)。"""

import asyncio
import json
import sqlite3
import tempfile
import time
from contextlib import closing, contextmanager
from dataclasses import replace
from pathlib import Path

import httpx
from sqlalchemy import text

from efficiency_platform_agent.contracts.memory_derive_template import (
    MemoryDeriveTemplate,
)
from efficiency_platform_agent.core.context_control import ModelCapacity, WindowLimits
from efficiency_platform_agent.core.context_dispatch import current_model_stage
from efficiency_platform_agent.core.context_ports import ContextMetadata
from efficiency_platform_agent.core.enums import StrategyMode
from efficiency_platform_agent.core.paid_budget import PaidBudgetPlan, PaidPriceLimit
from efficiency_platform_agent.core.run import JsonObject, ProviderMessage
from efficiency_platform_agent.harness.bound_summary_context import (
    BoundMemorySummaryContext,
)
from efficiency_platform_agent.harness.memory_derive_factory import (
    build_memory_derive_coordinator,
)
from efficiency_platform_agent.harness.memory_runtime import (
    build_memory_binding_updater,
)
from efficiency_platform_agent.memory.summary_policy import SummaryPolicy
from efficiency_platform_agent.memory.summary_projection import render_summary
from efficiency_platform_agent.orchestration.context_gate import (
    FencedModelProvider,
    MemoryDirectContextGate,
)
from efficiency_platform_agent.orchestration.intent_interpreter import IntentInterpreter
from efficiency_platform_agent.persistence.derive_operation import (
    SqliteDeriveOperationStore,
)
from efficiency_platform_agent.persistence.paid_budget import SqlitePaidBudgetLedger
from efficiency_platform_agent.providers.llm.registry import ModelProviderRegistry
from efficiency_platform_agent.providers.paid_http import PaidHttpTransport
from tests.integration.context_control.private_memory_http_fixture import main


async def setup_summary(components, controller, dispatch, customer, provider, bundle):
    if components.send_authority is None:
        raise ValueError("MEMORY_SEND_LEASE_REQUIRED")
    folder = tempfile.TemporaryDirectory(prefix="aiep-m2-mock-ledger-")
    ledger = SqlitePaidBudgetLedger(Path(folder.name) / "mock-only.sqlite")
    SqliteDeriveOperationStore(ledger).initialize()
    deadline = int(time.time() * 1000) + 240000
    ledger.authorize(
        PaidBudgetPlan(
            "m2-mock-only",
            1,
            100000000,
            deadline,
            1,
            100000000,
            600000,
            1,
            2,
            1000000,
            1000000,
            1000000,
            1000000,
            1000000,
            1000000,
        ),
        (
            PaidPriceLimit(
                "deepseek",
                "synthetic-fast",
                1000000,
                500,
                1000000,
                "MockTransport fixture only",
                "synthetic/2",
                100000,
                1,
                0,
                1,
            ),
        ),
    )
    counters = {
        "derive_events": 0,
        "derive_gets": 0,
        "derive_posts": 0,
        "finish_committed": 0,
        "finish_rejected": 0,
        "mock_provider_posts": 0,
    }
    model_proofs = []

    async def upstream(request):
        counters["mock_provider_posts"] += 1
        body = json.loads((await request.aread()).decode())
        projected = json.loads(body["messages"][-1]["content"])
        stage = current_model_stage()
        if stage is None or stage.node_id != "memory.derive" or projected.get("v") != 2:
            raise ValueError("M2_MOCK_ORIGINAL_STAGE_REQUIRED")
        aliases = [item[0] for item in projected["sources"]]
        answer = {
            "v": 2,
            "goal": {"text": "Advice", "sources": aliases},
            "notes": [],
            "kept": [item["ref"] for item in projected["required"]],
        }
        model_proofs.append(
            {
                "source_alias_count": len(aliases),
                "required_count": len(answer["kept"]),
                "model_schema_v2": True,
                "stage_bound": True,
            }
        )
        data = {
            "choices": [
                {
                    "delta": {"content": json.dumps(answer, separators=(",", ":"))},
                    "finish_reason": "stop",
                    "index": 0,
                }
            ],
            "usage": {"prompt_tokens": 1, "completion_tokens": 1, "total_tokens": 2},
        }
        return httpx.Response(
            200,
            headers={"content-type": "text/event-stream"},
            content="data: " + json.dumps(data) + "\n\ndata: [DONE]\n\n",
        )

    transport = PaidHttpTransport(
        ledger,
        httpx.MockTransport(upstream),
        "deepseek",
        allowed_url="https://m2-fixture.invalid/chat/completions",
        require_context_guard=True,
    )
    client = httpx.AsyncClient(
        transport=transport, trust_env=False, follow_redirects=False
    )
    summary_context = BoundMemorySummaryContext(components.store)
    summary_sizes = {}
    original_summaries = summary_context.current

    async def current_summaries(scope, packet):
        current = await original_summaries(scope, packet)
        for item in current:
            rendered = render_summary(item.segment)
            summary_sizes[item.segment.segment_id] = (
                controller._counter.measure_messages(
                    (ProviderMessage("user", rendered.text),), cap
                ).total_upper_bound
            )
        return current

    summary_context.current = current_summaries
    controller._summary_context_port = summary_context
    dispatch.authority.summary_context_port = summary_context
    # 首次当前请求制造真实压力；后续八条近期历史与旧摘要也须完整计窗。
    for key, variants in tuple(dispatch.authority._published.items()):
        dispatch.authority._published[key] = tuple(
            replace(item, limits=replace(item.limits, node_input_limit=12000))
            if key[2] == "direct"
            else item
            for item in variants
        )
    cap = ModelCapacity(
        "deepseek",
        "synthetic-fast",
        "derive-model/2",
        200000,
        160000,
        500,
        "conservative-utf8/1",
        "openai-chat/1",
        "NO_REASONING",
        True,
        "explicit-mock-only",
    )
    metadata = ContextMetadata(
        "memory.derive",
        "derive/1",
        "derive-prompt/2",
        "none/1",
        "derive-schema/2",
        1,
        cap,
        WindowLimits(200000, 160000, 500, 100, 120000),
        JsonObject(),
    )

    async def notify(runtime_id, payload):
        counters["derive_events"] += 1
        await bundle.event_hub.publish_next(
            runtime_id, "memory_derive_required", payload
        )

    coordinator = build_memory_derive_coordinator(
        engine=components.store.store.engine,
        client=client,
        ledger=ledger,
        cipher=components.store.store.cipher,
        hmac_key=dispatch._key,
        metadata=metadata,
        execution_store=components.store,
        api_key="mock-only",
        base_url="https://m2-fixture.invalid",
        notify_waitasync=notify,
        send_authority=components.send_authority,
    )
    original_execute = coordinator.handler.execute

    async def execute(*args, **kwargs):
        try:
            return await original_execute(*args, **kwargs)
        except (PermissionError, ValueError) as error:
            code = str(error).split(":")[0]
            if (
                not code.replace("_", "").isalnum()
                or not code.isupper()
                or not code.startswith(
                    (
                        "MEMORY_",
                        "DERIVE_",
                        "SUMMARY_",
                        "CONTEXT_",
                        "PAID_",
                        "PROVIDER_",
                        "AGENT_",
                    )
                )
            ):
                code = "MEMORY_DERIVE_FAILED"
            trace = error.__traceback__
            location = None
            while trace is not None:
                source_file = Path(trace.tb_frame.f_code.co_filename)
                if "efficiency_platform_agent" in source_file.parts:
                    location = {"file": source_file.name, "line": trace.tb_lineno}
                trace = trace.tb_next
            print(
                "M2_DERIVE_FAILURE " + json.dumps({"code": code, **(location or {})}),
                flush=True,
            )
            raise

    coordinator.handler.execute = execute
    run_checks, budget_checks, baseline_checks = [], [], []
    original_budget = coordinator._budget

    def budget(expected=None):
        result = original_budget(expected)
        snapshot = ledger.snapshot()
        budget_checks.append(
            {
                "available": result is not None,
                "remaining_calls": snapshot.get("remaining_calls"),
                "remaining_cost_microunits": snapshot.get("remaining_cost_microunits"),
                "stopped": bool(snapshot.get("stopped")),
                "deadline_live": snapshot.get("deadline_epoch_ms", 0)
                > int(time.time() * 1000),
            }
        )
        return result

    coordinator._budget = budget
    original_for_run = coordinator.for_run

    @contextmanager
    def for_run(record):
        raw = record.context.derive_template_json
        check = {
            "handler_enabled": coordinator.handler.enabled,
            "max_paid_operations": record.context.policy.max_paid_operations,
            "template_available": raw is not None,
        }
        if raw is not None:
            try:
                template = MemoryDeriveTemplate.model_validate_json(raw)
                check.update(
                    template_valid=True,
                    source_count=len(template.sources),
                    required_count=len(template.required_entries),
                    dependencies_subset=set(
                        coordinator._dependencies(template)
                    ).issubset(record.context.packet.safety_dependencies),
                )
            except ValueError:
                check["template_valid"] = False
        with original_for_run(record):
            check["authorized_frame_scope"] = (
                coordinator.frames._factory.get() is not None
            )
            check["cpu_skip_code"] = (
                "ACTIVE"
                if check["authorized_frame_scope"]
                else "DERIVE_TEMPLATE_DISABLED"
                if not check["handler_enabled"]
                or check["max_paid_operations"] != 1
                or not check["template_available"]
                else "DERIVE_TEMPLATE_INVALID"
                if not check.get("template_valid")
                else "DERIVE_BUDGET_UNAVAILABLE"
                if budget_checks and not budget_checks[-1]["available"]
                else "DERIVE_TEMPLATE_BINDING_OR_DEADLINE"
            )
            run_checks.append(check)
            yield

    coordinator.for_run = for_run
    original_frame = coordinator._frame

    def frame(state, baseline, operation):
        template = state.template
        cap, total = (
            baseline.limits.input_cap(),
            baseline.view.measurement.total_upper_bound,
        )
        check = {
            "node_id": baseline.window_policy.scope.subtask_id,
            "T": total,
            "H_ctx": cap,
            "pressure_at_least_70": total * 100 >= cap * 70,
            "need_summary": getattr(baseline.window_policy, "need_summary", False)
            is True,
            "template_scope_equal": template is not None
            and baseline.window_policy.scope == template.scope.to_core(),
            "deadline_live": time.time() < state.deadline,
        }
        if template is not None:
            check["dependencies_subset"] = set(
                coordinator._dependencies(template)
            ).issubset(baseline.window_policy.authorized_dependencies)
            try:
                SummaryPolicy().admit(
                    template.mode,
                    tuple(source.metadata for source in template.sources),
                    template.scope.conversation,
                    now=int(time.time()),
                )
                check["source_admission"] = "ADMITTED"
            except ValueError as rejected:
                code = str(rejected)
                check["source_admission"] = (
                    code
                    if code.startswith("SUMMARY_") and code.replace("_", "").isalnum()
                    else "REJECTED"
                )
        result = original_frame(state, baseline, operation)
        check["frame_created"] = result is not None
        check["cpu_skip_code"] = (
            "FRAME_CREATED"
            if result is not None
            else "DERIVE_BASELINE_SCOPE_MISMATCH"
            if not check["template_scope_equal"]
            else "DERIVE_LOW_PRESSURE"
            if not check["pressure_at_least_70"] and not check["need_summary"]
            else "DERIVE_DEADLINE_EXCEEDED"
            if not check["deadline_live"]
            else check["source_admission"]
            if check.get("source_admission") != "ADMITTED"
            else "DERIVE_BASELINE_DEPENDENCIES_MISMATCH"
            if not check.get("dependencies_subset")
            else "DERIVE_OTHER_LIVE_GUARD"
        )
        baseline_checks.append(check)
        return result

    coordinator._frame = frame
    controller.install_derive_runtime(coordinator.frames)
    dispatch.derive_coordinator = coordinator
    bundle.runtime.memory_derive_coordinator = coordinator
    graph = bundle.runtime.graph_runtime
    bundle.runtime.memory_refresh_enabled = True
    model_runtime = graph.registry.get(StrategyMode.DIRECT).builder.agent.model_runtime
    model_runtime.diagnostic_recorder = bundle.runtime.diagnostic_recorder
    bundle.conversation.interpreter = IntentInterpreter(model_runtime, timeout_ms=15000)
    providers = ModelProviderRegistry()
    for name, controlled in model_runtime.registry.providers.items():
        providers.register(
            name,
            FencedModelProvider(
                controlled,
                components.registry,
                "official",
                send_authority=components.send_authority,
            ),
        )
    model_runtime.registry = providers
    gate = MemoryDirectContextGate(
        components.refresh_service,
        components.store,
        components.registry,
        components.send_authority,
        saver=components.saver,
        checkpoint_store=graph.checkpoints,
        dispatch=dispatch,
    )
    components.saver.install_context_checkpoint_authority(gate)
    graph.checkpoints.install_context_checkpoint_authority(gate)
    graph.registry.get(StrategyMode.DIRECT).builder.memory_gate = gate
    components.refresh_service.checkpoint_verifier = gate.verify_wait_checkpoint
    components.refresh_service.frame_verifier = gate.verify_wait_frame
    components.refresh_service.wait_task_resolver = gate.wait_frame_task
    components.refresh_service.binding_updater = build_memory_binding_updater(
        gate, customer
    )
    dispatch.install_refresh(components.refresh_service, components.store)
    original_audit = components.refresh_service.validate_execution_manifest

    async def audit(manifest, record):
        valid = await original_audit(manifest, record)
        if not valid:
            from dataclasses import fields

            from efficiency_platform_agent.contracts.context_control import (
                ContextManifestModel,
            )
            from efficiency_platform_agent.core.memory_execution import (
                memory_operation_deadline_matches,
            )

            packet = record.context.packet
            checks = {
                "scope_equal": (
                    manifest.scope.conversation,
                    manifest.scope.task_id,
                    manifest.scope.execution_id,
                )
                == (packet.scope, packet.task_id, packet.execution_id),
                "packet_id_equal": manifest.packet_id == packet.packet_id,
                "packet_revision_present": manifest.packet_revision is not None,
                "dependencies_subset": set(manifest.safety_dependencies).issubset(
                    packet.safety_dependencies
                ),
                "grant_present": any(
                    (g.node_id, g.execution_agent_id, g.purpose)
                    == (
                        manifest.scope.subtask_id,
                        manifest.scope.execution_agent_id,
                        manifest.scope.purpose,
                    )
                    for g in record.context.execution_grants
                ),
            }
            async with components.store.store.engine.begin() as connection:
                row = (
                    (
                        await connection.execute(
                            text(
                                "SELECT o.status,o.input_hash,o.latest_attempt,o.deadline,m.metadata_json FROM agent_context_operation o JOIN agent_context_manifest m USING(tenant_id,task_id,execution_id,operation_id) WHERE o.tenant_id=:tenant AND o.execution_id=:execution AND o.task_id=:task AND o.operation_id=:operation AND m.attempt=:attempt"
                            ),
                            {
                                "tenant": packet.scope.tenant_id.encode(),
                                "execution": packet.execution_id.encode(),
                                "task": packet.task_id.encode(),
                                "operation": manifest.operation_id.encode(),
                                "attempt": manifest.attempt,
                            },
                        )
                    )
                    .mappings()
                    .first()
                )
                owner = (
                    (
                        await connection.execute(
                            text(
                                "SELECT current_context_fingerprint FROM agent_memory_execution WHERE tenant_id=:tenant AND execution_id=:execution"
                            ),
                            {
                                "tenant": packet.scope.tenant_id.encode(),
                                "execution": packet.execution_id.encode(),
                            },
                        )
                    )
                    .mappings()
                    .first()
                )
                checks["operation_row_present"] = row is not None
                if row is not None:
                    saved = ContextManifestModel.model_validate_json(
                        row["metadata_json"]
                    ).to_core()
                    checks.update(
                        status_allowed=row["status"]
                        in {"SENT", "SUCCEEDED", "UNKNOWN"},
                        hash_equal=row["input_hash"] == manifest.canonical_request_hmac,
                        attempt_equal=row["latest_attempt"] == manifest.attempt,
                        deadline_equal=row["deadline"] == record.deadline_epoch_seconds,
                        deadline_allowed=memory_operation_deadline_matches(
                            manifest.node_id,
                            row["deadline"],
                            record.deadline_epoch_seconds,
                        ),
                        roundtrip_equal=saved == manifest,
                        operation_deadline=row["deadline"],
                        roundtrip_diff_fields=[
                            field.name
                            for field in fields(manifest)
                            if getattr(saved, field.name)
                            != getattr(manifest, field.name)
                        ],
                    )
                checks["revision_chain_valid"] = (
                    await components.refresh_service.journal._revision_chain_locked(
                        connection,
                        record,
                        manifest.packet_revision,
                        owner["current_context_fingerprint"],
                    )
                    if owner is not None
                    else False
                )
                fresh = await components.store.get(
                    packet.scope.tenant_id, packet.execution_id
                )
                checks["current_record_equal"] = fresh == record
            async with components.registry._transaction():
                row = await components.registry._one(
                    "SELECT state,packet_revision,current_context_fingerprint FROM {execution} WHERE tenant_id=%s AND execution_id=%s",
                    (packet.scope.tenant_id, packet.execution_id),
                )
                checks.update(
                    pg_row_present=row is not None,
                    pg_active=row is not None and row["state"] == "ACTIVE",
                    pg_revision_equal=row is not None
                    and row["packet_revision"] == packet.packet_revision,
                    pg_mysql_fp_equal=row is not None
                    and owner is not None
                    and row["current_context_fingerprint"]
                    == owner["current_context_fingerprint"],
                )
            print(
                "M2_MANIFEST_AUDIT "
                + json.dumps(
                    {
                        "code": "MEMORY_MANIFEST_BINDING_INVALID",
                        "derive": manifest.node_id == "memory.derive",
                        "intent": manifest.node_id == "intent",
                        "direct": manifest.node_id == "direct",
                        "packet_revision": manifest.packet_revision,
                        "original_deadline": record.deadline_epoch_seconds,
                        "aliases_present": bool(manifest.summary_projection_aliases),
                        **checks,
                    }
                ),
                flush=True,
            )
        return valid

    components.refresh_service.validate_execution_manifest = audit
    engine = components.store.store.engine

    async def proof():
        with closing(sqlite3.connect(ledger.path)) as db:
            derives = [
                {"state": row[0], "result_encrypted": row[1] is not None}
                for row in db.execute("SELECT state,result FROM derive_operations")
            ]
            attempts = sum(
                row[0]
                for row in db.execute("SELECT attempts FROM execution_operations")
            )
        async with engine.connect() as connection:
            records = (
                (
                    await connection.execute(
                        text("SELECT metadata_json FROM agent_context_manifest")
                    )
                )
                .scalars()
                .all()
            )
        manifests = [json.loads(v) if isinstance(v, str) else v for v in records]
        return {
            **counters,
            "derive_operations": derives,
            "attempts": attempts,
            "ledger_calls": ledger.snapshot()["calls"],
            "model_proofs": model_proofs,
            "run_checks": run_checks,
            "budget_checks": budget_checks,
            "baseline_checks": baseline_checks,
            "derive_manifests": [
                {
                    "node_id": m["node_id"],
                    "prompt_version": m["prompt_version"],
                    "output_schema_version": m["output_schema_version"],
                    "attempt": m["attempt"],
                    "aliases_present": bool(m.get("summary_projection_aliases")),
                    "measurement": m["measurement"]["total_upper_bound"],
                }
                for m in manifests
                if m["node_id"] == "memory.derive"
            ],
            "summary_adoptions": [
                {
                    "execution_id": m["scope"]["execution_id"],
                    "node_id": m["node_id"],
                    "status": m.get("summary_adoption_status"),
                    "aliases_present": bool(m.get("summary_projection_aliases")),
                    "before": m.get("summary_before_tokens"),
                    "after": m.get("summary_after_tokens"),
                    "measurement": m["measurement"]["total_upper_bound"],
                    "input_cap": m["decision"]["H_ctx"],
                    "prediction_basis": m.get("prediction_basis"),
                    "predicted_generation_tokens": m.get("predicted_generation_tokens"),
                    "exclusion_reasons": sorted(
                        {item[1] for item in m.get("exclusions", [])}
                    ),
                    "selected_summary_tokens": [
                        summary_sizes[alias[0]]
                        for alias in m.get("summary_projection_aliases", [])
                        if alias[0] in summary_sizes
                    ],
                }
                for m in manifests
                if m["node_id"] == "direct"
            ],
        }

    def observe(request):
        path = request.url.path
        if path.endswith("/derive-plan"):
            counters["derive_gets"] += 1
        if path == "/skill/execute":
            counters["derive_posts"] += 1
        if path.endswith("/derive-finish"):
            # 状态由正式coordinator核验，计数从其待结算快照/finish包装观察，不伪造放行。
            pass

    original_finish = coordinator.finish

    async def finish(*args, **kwargs):
        await original_finish(*args, **kwargs)
        status = kwargs.get("status") or args[-1]
        counters[
            "finish_committed" if status == "COMMITTED" else "finish_rejected"
        ] += 1

    coordinator.finish = finish

    async def close():
        await client.aclose()
        folder.cleanup()

    proof.observe_http = observe
    proof.close = close
    return proof


if __name__ == "__main__":
    asyncio.run(
        main(refresh_setup=setup_summary), loop_factory=asyncio.SelectorEventLoop
    )
