"""Java既有Skill出口兼容层，缺内部认证与持久执行控制时关闭。"""

import asyncio
from collections.abc import Awaitable, Callable

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel, ConfigDict, Field, ValidationError

from efficiency_platform_agent.agents.hr.definition import SKILLS
from efficiency_platform_agent.agents.hr.service import (
    HrRunControlStore,
    HrSkillService,
)
from efficiency_platform_agent.capabilities.model.memory_derive_handler import (
    MEMORY_DERIVE_SKILL_ID,
    MemoryDeriveHandler,
)
from efficiency_platform_agent.contracts.hr import HrSkillRequest
from efficiency_platform_agent.core.memory_execution import MemoryExecutionStore
from efficiency_platform_agent.core.paid_budget import PaidBudgetError
from efficiency_platform_agent.core.run_context_binding import (
    RunContextBinding,
    bind_conversation_scope,
    bind_run_context,
    current_conversation_scope,
    current_memory_context,
)

from .context_auth import authorize_memory_context


class AiRequestContext(BaseModel):
    model_config = ConfigDict(extra="forbid")
    traceId: str = Field(min_length=1, max_length=100)
    userId: int
    sourceModule: str = Field(min_length=1, max_length=100)
    actionType: str = Field(min_length=1, max_length=100)


class SkillExecuteRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    context: AiRequestContext
    skillId: int
    input: str = Field(max_length=145000000)


class HrSkillEndpoint:
    def __init__(
        self,
        service: HrSkillService,
        controls: HrRunControlStore,
        *,
        memory_execution_store: MemoryExecutionStore | None = None,
    ) -> None:
        self.service, self.controls = service, controls
        self.memory_execution_store = memory_execution_store

    async def execute(
        self, tenant_id: str, skill_id: int, payload: HrSkillRequest
    ) -> dict[str, object]:
        skill = SKILLS.get(skill_id)
        if skill is None:
            raise ValueError("HR_CONFIG_SKILL_UNKNOWN")
        if skill == "hr.readiness":
            from efficiency_platform_agent.agents.hr.extraction import (
                dependency_readiness,
            )

            bindings = {}
            if self.service.assembler is not None and self.service.provider is not None:
                for key in (
                    "hr.resume.structure",
                    "hr.requirements.evaluate",
                    "hr.match.explain",
                    "hr.interview.generate",
                    "hr.jd.draft",
                ):
                    bindings[key] = await self.service.assembler.published_metadata(key)
            return {
                "contract_version": "hr-result/1",
                "skill": skill,
                "run_id": payload.run_id,
                "operation_id": payload.operation_id,
                "data": {
                    "formats": dependency_readiness(self.service.ocr),
                    "published_assets": len(bindings) == 5,
                    "bindings": bindings,
                },
            }
        if skill == "hr.workload.preflight":
            import hashlib

            from efficiency_platform_agent.core.paid_budget import PaidWorkloadItem

            ledger = getattr(self.controls, "ledger", None)
            identity = getattr(self.service.provider, "paid_identity", None)
            if ledger is None or identity is None or self.service.assembler is None:
                raise ValueError("HR_CONFIG_WORKLOAD_PREFLIGHT_UNAVAILABLE")
            requirements = []
            for operation in payload.workload:
                binding = await self.service.assembler.published_metadata(
                    operation.skill_key
                )
                provider, model = identity(str(binding["model_route"]))
                scope = (
                    "hr-"
                    + hashlib.sha256(
                        (tenant_id + ":" + operation.run_ref).encode()
                    ).hexdigest()
                )
                requirements.append(
                    PaidWorkloadItem(
                        scope,
                        provider,
                        model,
                        operation.attempts,
                        65536,
                        65536,
                        4096,
                        0,
                    )
                )
            checked = ledger.check_workload(
                requirements, payload.workload_budget_ref, payload.workload_plan_ref
            )
            return {
                "contract_version": "hr-result/1",
                "skill": skill,
                "run_id": payload.run_id,
                "operation_id": payload.operation_id,
                "data": checked,
            }
        if skill == "hr.run.cancel":
            await self.cancel(tenant_id, payload.run_id)
            return {
                "contract_version": "hr-result/1",
                "skill": skill,
                "run_id": payload.run_id,
                "operation_id": payload.operation_id,
                "data": {"cancelled": True},
            }
        if payload.workload_budget_ref is not None:
            ledger = getattr(self.controls, "ledger", None)
            if ledger is None:
                raise ValueError("HR_CONFIG_WORKLOAD_PREFLIGHT_UNAVAILABLE")
            ledger.check_workload([], payload.workload_budget_ref)
        if payload.workload_plan_ref is not None:
            import hashlib

            ledger = getattr(self.controls, "ledger", None)
            if ledger is None:
                raise ValueError("HR_CONFIG_WORKLOAD_PREFLIGHT_UNAVAILABLE")
            scope_id = (
                "hr-"
                + hashlib.sha256(
                    (tenant_id + ":" + payload.run_id).encode()
                ).hexdigest()
            )
            ledger.check_workload_plan(payload.workload_plan_ref, scope_id)
        control = await self.controls.get(
            tenant_id, payload.run_id, payload.maximum_attempts
        )
        conversation_scope = current_conversation_scope()
        context_binding = None
        if conversation_scope is not None:
            deadline = getattr(control, "deadline_epoch_ms", None)
            if type(deadline) is not int:
                raise ValueError("HR_CONTEXT_ORIGINAL_DEADLINE_REQUIRED")
            context_binding = RunContextBinding(
                conversation_scope, payload.run_id, payload.run_id, deadline // 1000
            )
            memory = current_memory_context()
            if memory is not None:
                if self.memory_execution_store is None:
                    raise ValueError("MEMORY_AUTHORITY_REQUIRED")
                original, _ = await self.memory_execution_store.claim(
                    memory,
                    payload.operation_id,
                    "HR",
                    memory.request_digest,
                    deadline // 1000,
                )
                context_binding = RunContextBinding(
                    conversation_scope,
                    memory.packet.task_id,
                    memory.packet.execution_id,
                    original.deadline_epoch_seconds,
                    original.context,
                )
        try:
            with bind_run_context(context_binding):
                async with asyncio.timeout_at(control.deadline):
                    return await self.service.execute(skill, payload, control)
        except TimeoutError:
            control.stop("AGENT_TASK_DEADLINE")
            await control.close()
            raise PaidBudgetError(
                "AGENT_TASK_DEADLINE", "任务截止时间已到，未继续执行"
            ) from None

    async def cancel(self, tenant_id: str, run_id: str) -> None:
        await self.controls.cancel(tenant_id, run_id)


def build_hr_skill_router(
    endpoint: HrSkillEndpoint | None,
    authorize: Callable[[Request], Awaitable[str]] | None,
    *,
    memory_enabled: bool = False,
    memory_derive_endpoint: MemoryDeriveHandler | None = None,
    memory_derive_authorize: Callable[[Request], Awaitable[str]] | None = None,
) -> APIRouter:
    import json

    router = APIRouter()

    @router.post("/skill/execute", response_model=None)
    async def execute(request: Request) -> JSONResponse:
        if authorize is None and memory_derive_authorize is None:
            return JSONResponse(
                status_code=503, content={"code": "HR_CONFIG_SERVICE_UNAVAILABLE"}
            )
        try:
            raw = bytearray()
            async for chunk in request.stream():
                if len(raw) + len(chunk) > 145000000:
                    return JSONResponse(
                        status_code=413, content={"code": "HR_FILE_HTTP_SIZE_LIMIT"}
                    )
                raw.extend(chunk)
            routing = json.loads(raw)
            if not isinstance(routing, dict) or type(routing.get("skillId")) is not int:
                raise ValueError("HR_CONFIG_SKILL_UNKNOWN")
            if routing["skillId"] == MEMORY_DERIVE_SKILL_ID:
                from .memory_derive_routes import execute_memory_derive

                if memory_derive_authorize is None:
                    return JSONResponse(
                        status_code=503,
                        content={"code": "MEMORY_DERIVE_FEATURE_DISABLED"},
                    )
                tenant = await memory_derive_authorize(request)
                if not tenant or tenant != request.headers.get("X-Tenant-ID"):
                    return JSONResponse(
                        status_code=403, content={"code": "DERIVE_SCOPE_MISMATCH"}
                    )
                return await execute_memory_derive(raw, tenant, memory_derive_endpoint)
            internal_authorize = authorize or memory_derive_authorize
            assert internal_authorize is not None
            tenant = await internal_authorize(request)
            if not tenant or tenant != request.headers.get("X-Tenant-ID"):
                return JSONResponse(
                    status_code=403, content={"code": "HR_PERMISSION_TENANT_MISMATCH"}
                )
            if routing["skillId"] not in SKILLS:
                raise ValueError("HR_CONFIG_SKILL_UNKNOWN")
            if endpoint is None or authorize is None:
                return JSONResponse(
                    status_code=503, content={"code": "HR_CONFIG_SERVICE_UNAVAILABLE"}
                )
            body = SkillExecuteRequest.model_validate_json(raw)
            payload = HrSkillRequest.model_validate_json(body.input)
            scope = await authorize_memory_context(
                request,
                payload.memory_context,
                authorize,
                tenant=tenant,
                user=str(body.context.userId),
                domain="hr",
                session_id=None,
                memory_enabled=memory_enabled,
                body=json.loads(body.input),
            )
            with bind_conversation_scope(
                scope, memory_context=payload.memory_context.to_core()
            ):
                result = await endpoint.execute(tenant, body.skillId, payload)
            return JSONResponse(
                content={
                    "content": json.dumps(
                        result, ensure_ascii=False, separators=(",", ":")
                    )
                }
            )
        except PermissionError:
            return JSONResponse(
                status_code=401,
                content={"code": "HR_PERMISSION_INTERNAL_CALL_REQUIRED"},
            )
        except PaidBudgetError as error:
            return JSONResponse(status_code=409, content={"code": error.code})
        except ValidationError:
            return JSONResponse(
                status_code=422, content={"code": "HR_EVALUATION_CONTRACT_INVALID"}
            )
        except ValueError as error:
            code = str(error).split(":")[0]
            if not code.startswith(
                ("HR_", "FORMAT_", "PAID_", "PROVIDER_", "PROMPT_", "AGENT_")
            ):
                code = "HR_EVALUATION_FAILED"
            return JSONResponse(status_code=422, content={"code": code})

    return router
