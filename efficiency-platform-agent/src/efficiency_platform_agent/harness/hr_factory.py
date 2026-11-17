"""HR受控执行装配：跨阶段共享固定账本，不自动创建付费授权。"""

from __future__ import annotations

import hashlib
import hmac
import time
from collections.abc import Awaitable, Callable, Mapping
from typing import TypeVar

from fastapi import Request

from efficiency_platform_agent.agents.hr.service import HrSkillService
from efficiency_platform_agent.api.hr_skill_routes import HrSkillEndpoint
from efficiency_platform_agent.contracts.hr import Block
from efficiency_platform_agent.core.execution_control import RunControl
from efficiency_platform_agent.core.memory import ConversationScope
from efficiency_platform_agent.core.paid_budget import PaidBudgetError, paid_scope
from efficiency_platform_agent.core.ports import ModelProvider
from efficiency_platform_agent.core.run import ProviderRequest, ProviderResult
from efficiency_platform_agent.core.run_context_binding import (
    current_conversation_scope,
)
from efficiency_platform_agent.persistence.paid_budget import SqlitePaidBudgetLedger
from efficiency_platform_agent.prompts.runtime import PromptAssembler

T = TypeVar("T")


class _PersistentControl(RunControl):
    def __init__(
        self,
        ledger: SqlitePaidBudgetLedger,
        tenant: str,
        run: str,
        deadline: int,
        context_scope: ConversationScope | None = None,
    ) -> None:
        super().__init__(timeout_ms=max(1, deadline - int(time.time() * 1000)))
        self.ledger, self.tenant, self.run = ledger, tenant, run
        self.deadline_epoch_ms = deadline
        self.context_scope = context_scope
        self.maximum_attempts = ledger.execution_attempt_limit(tenant, run)
        self.scope_id = (
            "hr-" + hashlib.sha256((tenant + ":" + run).encode()).hexdigest()
        )

    def stop(self, code: str = "AGENT_TASK_STOPPED") -> None:
        super().stop(code)
        self.ledger.stop_execution(
            self.tenant, self.run, code, context_scope=self.context_scope
        )

    def check(self) -> None:
        super().check()
        self.ledger.check_execution(self.tenant, self.run)

    def consume_attempt(self, operation_key: str | None) -> None:
        if operation_key is None:
            raise PaidBudgetError(
                "HR_OPERATION_REQUIRED", "HR request needs a logical operation"
            )
        self.ledger.consume_execution_attempt(self.tenant, self.run, operation_key)

    async def execute(
        self,
        key: str,
        work: Callable[[], Awaitable[T]],
        *,
        recoverable_codes: frozenset[str] = frozenset(),
    ) -> T:
        if key not in self.pending and key not in self.results:
            metadata = self.results.get("hr-input:" + key)
            digest = (
                str(metadata)
                if metadata is not None
                else hashlib.sha256(key.encode()).hexdigest()
            )
            if not self.ledger.claim_execution_operation(
                self.tenant, self.run, key, digest
            ):
                # 未知的前进程操作不得因重启再次收费；Java已持久产物可直接读回。
                raise PaidBudgetError(
                    "HR_OPERATION_ALREADY_SUBMITTED",
                    "operation already submitted; inspect persisted result",
                )
        with paid_scope(self.scope_id):
            return await super().execute(key, work, recoverable_codes=recoverable_codes)


class PersistentHrRunControlStore:
    def __init__(self, ledger: SqlitePaidBudgetLedger) -> None:
        self.ledger = ledger
        self.controls: dict[tuple[str, str], _PersistentControl] = {}

    async def get(
        self, tenant_id: str, run_id: str, maximum_attempts: int = 3
    ) -> RunControl:
        scope = current_conversation_scope()
        deadline = self.ledger.bind_execution(
            tenant_id,
            run_id,
            600000,
            maximum_attempts=maximum_attempts,
            context_scope=scope,
        )
        key = tenant_id, run_id
        if key not in self.controls:
            self.controls[key] = _PersistentControl(
                self.ledger, tenant_id, run_id, deadline, scope
            )
        self.controls[key].check()
        return self.controls[key]

    async def cancel(self, tenant_id: str, run_id: str) -> None:
        self.ledger.stop_execution(
            tenant_id, run_id, context_scope=current_conversation_scope()
        )
        control = self.controls.pop((tenant_id, run_id), None)
        if control is not None:
            await control.close()

    async def close(self) -> None:
        for control in tuple(self.controls.values()):
            await control.close()
        self.controls.clear()


def internal_hr_authorizer(secret: str) -> Callable[[Request], Awaitable[str]]:
    if len(secret) < 32:
        raise ValueError("HR_INTERNAL_AUTH_CONFIG_REQUIRED")

    async def authorize(request: Request) -> str:
        supplied = request.headers.get("Authorization", "")
        if not hmac.compare_digest(supplied.encode(), ("Bearer " + secret).encode()):
            raise PermissionError
        tenant = request.headers.get("X-Tenant-ID", "")
        if not tenant.strip() or len(tenant) > 128:
            raise PermissionError
        return tenant

    return authorize


def build_hr_endpoint(
    assembler: PromptAssembler | None,
    provider: ModelProvider | None,
    ledger: SqlitePaidBudgetLedger,
    *,
    ocr: Callable[[bytes], list[Block]] | None = None,
) -> HrSkillEndpoint:
    return HrSkillEndpoint(
        HrSkillService(assembler, provider, ocr=ocr),
        PersistentHrRunControlStore(ledger),
    )


class HrPolicyModelProvider:
    def __init__(self, providers: Mapping[str, ModelProvider]) -> None:
        if not providers:
            raise ValueError("HR_CONFIG_MODEL_PROVIDER_MISSING")
        self.providers = dict(providers)
        self.descriptor = next(iter(providers.values())).descriptor

    def paid_identity(self, logical_model: str) -> tuple[str, str]:
        """价格身份来自服务器已绑定Provider，不接受业务请求自行指定供应商或模型。"""
        selected = self.providers.get(logical_model)
        if selected is None:
            raise ValueError("HR_CONFIG_MODEL_PROVIDER_MISSING")
        provider = selected.descriptor.name.split(".", 1)[0]
        model = getattr(selected, "model", None)
        if not isinstance(model, str) or not model:
            raise ValueError("HR_CONFIG_MODEL_PRICE_IDENTITY_MISSING")
        return provider, model

    async def complete(self, request: ProviderRequest) -> ProviderResult:
        logical_model = dict(request.options.items).get("logical_model")
        selected = (
            self.providers.get(logical_model)
            if isinstance(logical_model, str)
            else None
        )
        if selected is None:
            raise ValueError("HR_CONFIG_MODEL_PROVIDER_MISSING")
        return await selected.complete(request)


async def validate_hr_prompt_assets(repository: object, models: set[str]) -> None:
    from typing import cast

    from pydantic import BaseModel

    from efficiency_platform_agent.contracts.hr import (
        EvaluationOutput,
        ExplanationOutput,
        FactOutput,
        InterviewOutput,
        JdOutput,
    )
    from efficiency_platform_agent.prompts.repository import PromptRepository

    configured = cast(PromptRepository, repository)
    outputs: dict[str, type[BaseModel]] = {
        "hr.resume.structure": FactOutput,
        "hr.requirements.evaluate": EvaluationOutput,
        "hr.match.explain": ExplanationOutput,
        "hr.interview.generate": InterviewOutput,
        "hr.jd.draft": JdOutput,
    }
    for key, output in outputs.items():
        bundle = await configured.resolve(key, "dev")
        policy = bundle.model_policy
        if (
            bundle.version.status != "released"
            or policy.model_name not in models
            or policy.max_input_tokens < 131072
            or not 1 <= policy.max_output_tokens <= 4096
            or policy.max_retries > 2
            or dict(bundle.output_contract.json_schema) != output.model_json_schema()
        ):
            raise ValueError("HR_CONFIG_PUBLISHED_ASSETS_NOT_READY")
