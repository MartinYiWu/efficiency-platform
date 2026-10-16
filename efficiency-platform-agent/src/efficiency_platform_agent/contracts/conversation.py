"""运营助手会话入口使用的版本化契约。"""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field

RunDisplayStatus = Literal[
    "queued",
    "running",
    "waiting_input",
    "succeeded",
    "failed",
    "cancelled",
    "degraded_succeeded",
]


class ConversationArtifactV1(BaseModel):
    """由 Java 按当前身份和会话授权的可引用制品。"""

    model_config = ConfigDict(extra="forbid", frozen=True)

    artifact_id: str = Field(min_length=1, max_length=128)
    root_artifact_id: str = Field(min_length=1, max_length=128)
    version: int = Field(ge=1)
    artifact_type: str = Field(min_length=1, max_length=128)
    scenario: str = Field(min_length=1, max_length=128)
    platform: str | None = Field(default=None, max_length=128)
    title: str = Field(min_length=1, max_length=500)
    content: dict[str, Any]
    body_markdown: str = Field(min_length=1, max_length=100_000)


class ConversationMessageV1(BaseModel):
    """用户向运营助手提交的一轮自然语言消息。"""

    model_config = ConfigDict(extra="forbid", frozen=True)

    contract_version: Literal["conversation/1"] = Field(
        default="conversation/1", description="会话契约版本。"
    )
    message: str = Field(
        min_length=1, max_length=20_000, description="用户自然语言消息。"
    )
    request_id: str = Field(min_length=1, max_length=128, description="请求幂等标识。")
    user_id: str = Field(min_length=1, max_length=128, description="用户标识。")
    attachments: list[dict[str, object]] = Field(
        default_factory=list,
        max_length=0,
        description="文件输入保留字段，本轮必须为空。",
    )
    artifacts: tuple[ConversationArtifactV1, ...] = Field(default=(), max_length=8)


class ConversationSubmitViewV1(BaseModel):
    """提交消息后立即返回的会话、轮次和 Run 标识。"""

    model_config = ConfigDict(extra="forbid", frozen=True)

    contract_version: Literal["conversation/1"] = Field(
        default="conversation/1", description="会话契约版本。"
    )
    conversation_id: str = Field(min_length=1, max_length=128, description="会话标识。")
    turn_id: str = Field(min_length=1, max_length=128, description="当前轮次标识。")
    run_id: str = Field(min_length=1, max_length=128, description="已创建 Run 标识。")
    status: Literal["queued"] = Field(
        default="queued", description="创建后固定为排队状态。"
    )


__all__ = [
    "ConversationArtifactV1",
    "ConversationMessageV1",
    "ConversationSubmitViewV1",
    "RunDisplayStatus",
]
