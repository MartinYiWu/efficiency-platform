"""唯一 Skill 路由的摘要分支；不注册第二个 URL。"""

import json

from fastapi.responses import JSONResponse
from pydantic import ValidationError

from efficiency_platform_agent.capabilities.model.memory_derive_handler import (
    MemoryDeriveHandler,
)
from efficiency_platform_agent.contracts.memory_derive import (
    MemoryDeriveRequest,
    MemorySkillExecuteRequest,
)
from efficiency_platform_agent.core.paid_budget import PaidBudgetError


def _strict_json(raw: bytes | bytearray | str) -> object:
    def pairs(items: list[tuple[str, object]]) -> dict[str, object]:
        result: dict[str, object] = {}
        for key, value in items:
            if key in result:
                raise ValueError("MEMORY_DERIVE_CONTRACT_INVALID")
            result[key] = value
        return result

    def reject_constant(_: str) -> None:
        raise ValueError("MEMORY_DERIVE_CONTRACT_INVALID")

    return json.loads(raw, object_pairs_hook=pairs, parse_constant=reject_constant)


async def execute_memory_derive(
    raw: bytes | bytearray, tenant: str, endpoint: MemoryDeriveHandler | None
) -> JSONResponse:
    if len(raw) > 1048576:
        return JSONResponse(
            status_code=413, content={"code": "MEMORY_DERIVE_HTTP_SIZE_LIMIT"}
        )
    try:
        _strict_json(raw)
        envelope = MemorySkillExecuteRequest.model_validate_json(raw)
        _strict_json(envelope.input)
        payload = MemoryDeriveRequest.model_validate_json(envelope.input)
        scope = payload.execution_scope.conversation
        if tenant != scope.tenant_id or envelope.context.userId != scope.user_id:
            return JSONResponse(
                status_code=403, content={"code": "DERIVE_SCOPE_MISMATCH"}
            )
        if endpoint is None:
            raise ValueError("MEMORY_DERIVE_FEATURE_DISABLED")
        result = await endpoint.execute(tenant, payload)
        return JSONResponse(
            content={
                "content": json.dumps(result, ensure_ascii=False, separators=(",", ":"))
            }
        )
    except ValidationError:
        return JSONResponse(
            status_code=422, content={"code": "MEMORY_DERIVE_CONTRACT_INVALID"}
        )
    except (PaidBudgetError, ValueError, PermissionError) as error:
        code = (
            error.code
            if isinstance(error, PaidBudgetError)
            else str(error).split(":")[0]
        )
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
        return JSONResponse(
            status_code=(
                503
                if code == "MEMORY_DERIVE_FEATURE_DISABLED"
                else 422
                if code == "MEMORY_DERIVE_CONTRACT_INVALID"
                else 409
            ),
            content={"code": code},
        )
