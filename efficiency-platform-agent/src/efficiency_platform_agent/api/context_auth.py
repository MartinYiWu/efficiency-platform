"""只接纳已认证 Java 内部通道的作用域，不信任普通身份 Header。"""

from collections.abc import Awaitable, Callable

from fastapi import HTTPException, Request

from efficiency_platform_agent.contracts.memory_context import MemoryContextEnvelope
from efficiency_platform_agent.core.memory import ConversationScope
from efficiency_platform_agent.harness.memory_admission import validate_memory_request

InternalAuthorizer = Callable[[Request], Awaitable[str]]


async def authorize_memory_context(
    request: Request,
    envelope: MemoryContextEnvelope,
    authorize: InternalAuthorizer | None,
    *,
    tenant: str,
    user: str,
    domain: str,
    session_id: str | None,
    session_kind: str | None = None,
    memory_enabled: bool = False,
    body: dict | None = None,
) -> ConversationScope | None:
    if envelope.scope is None:
        return None
    if authorize is None:
        raise HTTPException(401, detail="CONTEXT_INTERNAL_AUTH_REQUIRED")
    try:
        authorized_tenant = await authorize(request)
    except PermissionError as error:
        raise HTTPException(401, detail="CONTEXT_INTERNAL_AUTH_REQUIRED") from error
    scope = envelope.scope.to_core()
    expected = (
        tenant,
        user,
        domain,
        domain,
        session_kind or ("TASK_ONLY" if domain == "hr" else "CONVERSATION"),
        session_id,
    )
    actual = (
        scope.tenant_id,
        scope.user_id,
        scope.domain,
        scope.top_level_agent_id,
        scope.session_kind,
        scope.session_id,
    )
    if authorized_tenant != tenant or actual != expected:
        raise HTTPException(403, detail="CONTEXT_SCOPE_MISMATCH")
    if envelope.memory_mode == "EXACT_ONLY":
        if not memory_enabled:
            raise HTTPException(422, detail="MEMORY_FEATURE_DISABLED")
        context = envelope.to_core()
        assert context is not None
        try:
            validate_memory_request(
                context, await request.json() if body is None else body
            )
        except ValueError as error:
            code = str(error)
            raise HTTPException(
                409 if code == "MEMORY_PACKET_EXPIRED_OR_NOT_YET_VALID" else 403,
                detail=code,
            ) from None
    return scope
