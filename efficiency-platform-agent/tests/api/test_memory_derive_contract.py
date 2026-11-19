import hashlib
import json
import time
from contextlib import asynccontextmanager
from dataclasses import replace

import httpx
import pytest
from fastapi import FastAPI
from pydantic import ValidationError

from efficiency_platform_agent.api.hr_skill_routes import build_hr_skill_router
from efficiency_platform_agent.capabilities.model.memory_derive_handler import (
    MemoryDeriveHandler,
    OriginalDeriveFrame,
)
from efficiency_platform_agent.contracts.memory import (
    ExecutionScopeModel,
    MemoryProposalModel,
)
from efficiency_platform_agent.contracts.memory_derive import (
    DeriveAssetRefs,
    FrozenDeriveSource,
    MemoryDeriveRequest,
)
from efficiency_platform_agent.core.execution_control import RunControl, execution_scope
from efficiency_platform_agent.core.memory import MemoryContextPacket, MemoryPolicy
from efficiency_platform_agent.core.memory_execution import (
    MemoryExecutionContext,
    MemoryExecutionGrant,
)
from efficiency_platform_agent.core.run_context_binding import (
    RunContextBinding,
    bind_run_context,
)
from efficiency_platform_agent.memory.derive import DeriveCandidate
from tests.unit.context.test_compaction_benefit import setup


def fixture():
    _, baseline, validated, counter = setup(history_length=1000)
    now = int(time.time())
    scope = validated.segment.scope.model_copy(
        update={
            "domain": "operations",
            "top_level_agent_id": "operations",
            "user_id": "user-中文😀",
        }
    )
    execution = replace(
        baseline.window_policy.scope,
        conversation=scope.to_core(),
        execution_agent_id="operations",
    )
    source = validated.frozen_sources.sources[0].model_copy(
        update={"scope": scope, "expires_at": now + 200}
    )
    segment = validated.segment.model_copy(
        update={"scope": scope, "expires_at": now + 190}
    )
    baseline = replace(
        baseline,
        view=replace(
            baseline.view,
            pieces=tuple(replace(p, scope=execution) for p in baseline.view.pieces),
        ),
        window_policy=replace(baseline.window_policy, scope=execution),
    )
    state = replace(
        validated.task_state, scope=scope, current_sources=(source,), now=now
    )
    assets = DeriveAssetRefs(
        memory_policy_version="memory/2",
        window_policy_version="window/7",
        model_ref="model/1",
        prompt_ref="derive-prompt/1",
        schema_ref="derive-schema/1",
    )
    body = "原始历史" * 1000
    request = MemoryDeriveRequest(
        contract_version="memory-derive/1",
        plan_id="plan",
        plan_fingerprint="0" * 64,
        runtime_id="runtime",
        runtime_kind="OPERATIONS",
        run_id="run",
        operation_id="derive-op",
        authorization_ref="parent",
        budget_id="original-budget",
        deadline_epoch_seconds=now + 100,
        execution_scope=ExecutionScopeModel.from_core(execution),
        mode="SUMMARY",
        baseline_ref="baseline/1",
        assets=assets,
        sources=(
            FrozenDeriveSource(
                metadata=source,
                body=body,
                body_sha256=hashlib.sha256(body.encode()).hexdigest(),
            ),
        ),
        events=(),
        required_entries=(segment.goal,),
        session_revision=7,
        source_revision=4,
        authority_ref=state.authority_ref,
    )
    request = request.model_copy(update={"plan_fingerprint": request.fingerprint()})
    packet = MemoryContextPacket(
        "packet",
        1,
        scope.to_core(),
        "task",
        "execution",
        "memory/2",
        1,
        now,
        now + 100,
        1,
        2,
        3,
        "semantic",
        "parent",
        safety_dependencies=execution
        and tuple(d.to_core() for d in source.source_dependencies),
    )
    policy = MemoryPolicy("memory", "memory/2", "operations", frozenset({"operations"}))
    memory = MemoryExecutionContext(
        packet,
        policy,
        (MemoryExecutionGrant("subtask", "operations", "ANSWER"),),
        now + 100,
        "a" * 64,
        "b" * 64,
        "c" * 64,
    )

    class Checker:
        async def check(self, request, frame):
            return replace(state, now=int(time.time()))

    frame = OriginalDeriveFrame(
        request.operation(),
        RunContextBinding(scope.to_core(), "task", "execution", now + 100, memory),
        "runtime",
        "OPERATIONS",
        "baseline/1",
        baseline,
        assets,
        counter,
        Checker(),
    )

    class Frames:
        control = RunControl()
        bind_control = True
        bound_frame = frame

        @asynccontextmanager
        async def bind(self, request):
            with bind_run_context(self.bound_frame.binding):
                if self.bind_control:
                    with execution_scope(self.control):
                        yield self.bound_frame
                else:
                    yield self.bound_frame

    class Gateway:
        calls = 0

        async def derive(self, scope, mode, sources, operation):
            self.calls += 1
            return DeriveCandidate(mode="SUMMARY", summary=segment, proposals=())

    frames, gateway = Frames(), Gateway()
    return (
        request,
        frames,
        gateway,
        lambda: MemoryDeriveHandler(frames, lambda *_: gateway, enabled=True),
    )


async def test_handler_validates_candidate_and_actual_baseline_benefit_without_commit():
    request, frames, gateway, handler = fixture()
    result = await handler().execute("tenant", request)
    assert gateway.calls == 1
    assert result["validation"]["free_text_quality"] == "UNVERIFIED"
    assert result["validation"]["commit_status"] == "NOT_COMMITTED"
    assert result["benefit"]["status"] == "BENEFICIAL"
    assert result["benefit"]["T_before"] > result["benefit"]["T_after"]
    assert frames.control.calls == 0


@pytest.mark.parametrize("mode", ["PROPOSALS", "BOTH"])
async def test_proposals_use_one_original_request_and_complete_source_closure(mode):
    request, frames, gateway, _ = fixture()
    source = request.sources[0].metadata
    source = source.model_copy(
        update={
            "allowed_purposes": frozenset({"SUMMARY", "PROPOSALS"}),
            "proposals_scope_ref": source.summary_scope_ref,
            "proposals_retention_ref": source.summary_retention_ref,
        }
    )
    request = request.model_copy(
        update={
            "mode": mode,
            "sources": (request.sources[0].model_copy(update={"metadata": source}),),
        }
    )
    request = request.model_copy(update={"plan_fingerprint": request.fingerprint()})
    frame = frames.bound_frame
    memory = replace(
        frame.binding.memory_context,
        policy=replace(
            frame.binding.memory_context.policy,
            auto_extract=True,
            writable_kinds=frozenset({"PREFERENCE"}),
            allowed_scopes=frozenset({"USER_PRIVATE"}),
            field_allowlist=frozenset({"response.language"}),
        ),
    )
    old_checker = frame.source_checker

    class Checker:
        async def check(self, incoming, frame):
            state = await old_checker.check(incoming, frame)
            return replace(state, current_sources=(source,), original_mode=mode)

    frames.bound_frame = replace(
        frame,
        binding=replace(frame.binding, memory_context=memory),
        source_checker=Checker(),
    )
    original = gateway.derive

    async def derive(scope, requested, sources, operation):
        result = await original(scope, requested, sources, operation)
        return DeriveCandidate(
            mode=mode,
            summary=None if mode == "PROPOSALS" else result.summary,
            proposals=(
                MemoryProposalModel(
                    kind="PREFERENCE", field_key="response.language", value="zh-CN"
                ),
            ),
        )

    gateway.derive = derive
    result = await MemoryDeriveHandler(
        frames, lambda *_: gateway, enabled=True
    ).execute("tenant", request)
    assert gateway.calls == 1
    proposal = result["validation"]["proposals_validated"][0]
    assert proposal["decision_status"] == "PROPOSED"
    assert proposal["index_status"] == "NOT_REQUESTED"
    assert proposal["source_dependencies"] == [
        d.model_dump(mode="json") for d in source.source_dependencies
    ]
    assert result["candidate"]["mode"] == mode
    if mode == "PROPOSALS":
        assert result["benefit"]["status"] == "NOT_REQUESTED"


async def test_default_off_missing_parent_and_changed_fingerprint_reject_before_gateway():
    request, frames, gateway, handler = fixture()
    with pytest.raises(ValueError, match="FEATURE_DISABLED"):
        await MemoryDeriveHandler(frames, lambda *_: gateway).execute("tenant", request)
    frames.bind_control = False
    with pytest.raises(ValueError, match="ORIGINAL_RUN_CONTROL_REQUIRED"):
        await handler().execute("tenant", request)
    frames.bind_control = True
    with pytest.raises(ValueError, match="BINDING_CONFLICT"):
        await handler().execute(
            "tenant", request.model_copy(update={"source_revision": 5})
        )
    original_frame = frames.bound_frame
    memory = original_frame.binding.memory_context
    altered_memory = replace(
        memory,
        execution_grants=(MemoryExecutionGrant("other-node", "operations", "ANSWER"),),
    )
    frames.bound_frame = replace(
        original_frame,
        binding=replace(original_frame.binding, memory_context=altered_memory),
    )
    with pytest.raises(ValueError, match="BINDING_CONFLICT"):
        await handler().execute("tenant", request)
    frames.bound_frame = original_frame
    frames.control.stop()
    with pytest.raises(Exception, match="任务已停止"):
        await handler().execute("tenant", request)
    assert gateway.calls == 0


def test_wire_rejects_changed_body_missing_epoch_unknown_and_boolean_revision():
    from efficiency_platform_agent.contracts.memory_summary import SummarySegment
    from efficiency_platform_agent.memory.summary_contracts import (
        SummarySegment as LegacySummarySegment,
    )

    assert SummarySegment is LegacySummarySegment
    request, *_ = fixture()
    data = json.loads(request.model_dump_json())
    data["sources"][0]["body"] += "changed"
    with pytest.raises(ValidationError):
        MemoryDeriveRequest.model_validate_json(json.dumps(data))
    for change in ("epoch", "unknown", "bool"):
        data = json.loads(request.model_dump_json())
        if change == "epoch":
            del data["sources"][0]["metadata"]["source_ref"]["source_epoch"]
        elif change == "unknown":
            data["maximum_attempts"] = 99
        else:
            data["source_revision"] = True
        with pytest.raises(ValidationError):
            MemoryDeriveRequest.model_validate_json(json.dumps(data))


async def test_unique_skill_route_internal_auth_string_identity_default_off_unknown():
    request, _, gateway, handler = fixture()

    async def authorize(inbound):
        if inbound.headers.get("Authorization") != "Bearer internal-fixture":
            raise PermissionError
        return inbound.headers.get("X-Tenant-ID")

    async def hr_authorize(inbound):
        if inbound.headers.get("Authorization") != "Bearer hr-fixture":
            raise PermissionError
        return inbound.headers.get("X-Tenant-ID")

    def app(endpoint, with_hr=False):
        application = FastAPI()
        router = build_hr_skill_router(
            None,
            hr_authorize if with_hr else None,
            memory_derive_endpoint=endpoint,
            memory_derive_authorize=authorize,
        )
        assert sum(route.path == "/skill/execute" for route in router.routes) == 1
        application.include_router(router)
        return application

    envelope = {
        "context": {
            "traceId": "trace",
            "userId": request.execution_scope.conversation.user_id,
            "sourceModule": "operations",
            "actionType": "memory.derive",
        },
        "skillId": 6201,
        "input": request.model_dump_json(),
    }
    headers = {"Authorization": "Bearer internal-fixture", "X-Tenant-ID": "tenant"}

    class RuntimeDenied:
        async def execute(self, *_):
            raise PermissionError("MEMORY_SEND_PERMIT_INVALID")

    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app(RuntimeDenied())), base_url="http://agent"
    ) as client:
        denied = await client.post("/skill/execute", json=envelope, headers=headers)
        assert denied.status_code == 409
        assert denied.json()["code"] == "MEMORY_SEND_PERMIT_INVALID"
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app(None)), base_url="http://agent"
    ) as client:
        assert (await client.post("/skill/execute", json=envelope)).status_code == 401
        assert (
            await client.post("/skill/execute", json=envelope, headers=headers)
        ).status_code == 503
        unknown = await client.post(
            "/skill/execute", json={**envelope, "skillId": 6299}, headers=headers
        )
        assert unknown.json()["code"] == "HR_CONFIG_SKILL_UNKNOWN"
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app(handler(), with_hr=True)),
        base_url="http://agent",
    ) as client:
        assert (
            await client.post(
                "/skill/execute", json={**envelope, "skillId": 6101}, headers=headers
            )
        ).status_code == 401
        assert (
            await client.post(
                "/skill/execute",
                json={**envelope, "skillId": 6101},
                headers={**headers, "Authorization": "Bearer hr-fixture"},
            )
        ).status_code == 503
        duplicate = {
            **envelope,
            "input": envelope["input"].replace(
                '"plan_id":"plan"', '"plan_id":"plan","plan_id":"other"'
            ),
        }
        assert (
            await client.post("/skill/execute", json=duplicate, headers=headers)
        ).status_code == 422
        response = await client.post("/skill/execute", json=envelope, headers=headers)
        assert response.status_code == 200
        assert (
            json.loads(response.json()["content"])["validation"]["commit_status"]
            == "NOT_COMMITTED"
        )
        assert (
            await client.post(
                "/skill/execute",
                json=envelope,
                headers={**headers, "X-Tenant-ID": "other"},
            )
        ).status_code == 403
    assert gateway.calls == 1
