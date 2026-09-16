"""运营助手自然语言会话 HTTP 路由。"""

from __future__ import annotations

from fastapi import APIRouter, Header, status

from efficiency_platform_agent.contracts.conversation import (
    ConversationMessageV1,
    ConversationSubmitViewV1,
)
from efficiency_platform_agent.conversation.service import ConversationService


def build_conversation_router(service: ConversationService) -> APIRouter:
    """构造只接受自然语言、身份与幂等标识的会话入口。"""
    router = APIRouter()

    @router.post(
        "/v1/conversations/{conversation_id}/messages",
        response_model=ConversationSubmitViewV1,
        status_code=status.HTTP_201_CREATED,
    )
    async def submit_message(
        conversation_id: str,
        message: ConversationMessageV1,
        x_tenant_id: str = Header(..., alias="X-Tenant-ID"),
    ) -> ConversationSubmitViewV1:
        return await service.submit(conversation_id, x_tenant_id, message)

    return router


__all__ = ["build_conversation_router"]
