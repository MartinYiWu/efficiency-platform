"""运营助手自然语言会话 HTTP 路由。"""

from __future__ import annotations

from fastapi import APIRouter, Header, Request, status

from efficiency_platform_agent.contracts.conversation import (
    ConversationMessageV1,
    ConversationSubmitViewV1,
)
from efficiency_platform_agent.conversation.service import ConversationService
from efficiency_platform_agent.core.run_context_binding import bind_conversation_scope

from .context_auth import InternalAuthorizer, authorize_memory_context


def build_conversation_router(
    service: ConversationService,
    authorize: InternalAuthorizer | None = None,
    *,
    memory_enabled: bool = False,
) -> APIRouter:
    """构造只接受自然语言、身份与幂等标识的会话入口。"""
    router = APIRouter()

    @router.post(
        "/v1/conversations/{conversation_id}/messages",
        response_model=ConversationSubmitViewV1,
        status_code=status.HTTP_201_CREATED,
    )
    async def submit_message(
        conversation_id: str,
        request: Request,
        message: ConversationMessageV1,
        x_tenant_id: str = Header(..., alias="X-Tenant-ID"),
    ) -> ConversationSubmitViewV1:
        scope = await authorize_memory_context(
            request,
            message.memory_context,
            authorize,
            tenant=x_tenant_id,
            user=message.user_id,
            domain="operations",
            session_id=conversation_id,
            memory_enabled=memory_enabled,
        )
        with bind_conversation_scope(
            scope, memory_context=message.memory_context.to_core()
        ):
            return await service.submit(conversation_id, x_tenant_id, message)

    return router


__all__ = ["build_conversation_router"]
