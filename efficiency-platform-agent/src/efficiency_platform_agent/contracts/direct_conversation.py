"""通用对话跨层传输使用的冻结值契约。"""

from __future__ import annotations

from dataclasses import dataclass

from efficiency_platform_agent.core.budget import RemainingBudget
from efficiency_platform_agent.core.model import ModelSelection
from efficiency_platform_agent.core.run import ProviderMessage, RunRequest
from efficiency_platform_agent.core.runtime import UsageSnapshot

DIRECT_CONVERSATION_CONTRACT_VERSION = "direct-conversation/1"
MAX_VISIBLE_HISTORY_MESSAGES = 8
MAX_VISIBLE_HISTORY_CHARACTERS = 12_000


@dataclass(frozen=True, slots=True)
class DirectConversationSubmission:
    """保存一次 DIRECT 对话所需的最小身份、历史与预算快照。"""

    contract_version: str
    request: RunRequest
    visible_history: tuple[ProviderMessage, ...]
    current_message: str
    local_response: str | None
    remaining_budget: RemainingBudget

    def __post_init__(self) -> None:
        if self.contract_version != DIRECT_CONVERSATION_CONTRACT_VERSION:
            raise ValueError("通用对话提交契约版本无效")
        if not isinstance(self.request, RunRequest):
            raise TypeError("request必须是RunRequest")
        if not isinstance(self.visible_history, tuple):
            raise TypeError("visible_history必须是不可变tuple")
        if len(self.visible_history) > MAX_VISIBLE_HISTORY_MESSAGES:
            raise ValueError("可见历史超过消息数量上限")
        character_count = 0
        for message in self.visible_history:
            if not isinstance(message, ProviderMessage):
                raise TypeError("可见历史必须只包含ProviderMessage")
            if message.role not in {"user", "assistant"} or not isinstance(
                message.content, str
            ):
                raise ValueError("可见历史只允许user或assistant可见正文")
            character_count += len(message.content)
        if character_count > MAX_VISIBLE_HISTORY_CHARACTERS:
            raise ValueError("可见历史超过字符上限")
        if (
            not isinstance(self.current_message, str)
            or not self.current_message.strip()
        ):
            raise ValueError("current_message必须是非空字符串")
        if self.current_message != self.request.input_text:
            raise ValueError("current_message必须与request.input_text一致")
        if self.local_response is not None and (
            not isinstance(self.local_response, str) or not self.local_response.strip()
        ):
            raise ValueError("local_response必须是非空字符串或None")
        if not isinstance(self.remaining_budget, RemainingBudget):
            raise TypeError("remaining_budget必须是RemainingBudget")
        if (
            self.remaining_budget.iterations < 1
            or self.remaining_budget.input_tokens < 1
            or self.remaining_budget.output_tokens < 1
            or self.remaining_budget.timeout_ms < 1
        ):
            raise ValueError("通用对话剩余预算不足")


@dataclass(frozen=True, slots=True)
class GeneralConversationExecution:
    """通用对话正文及可信用量、降级事实。"""

    content: str
    usage: UsageSnapshot
    degraded: bool
    attempts: tuple[ModelSelection, ...] = ()

    def __post_init__(self) -> None:
        if not isinstance(self.content, str) or not self.content.strip():
            raise ValueError("content必须是非空字符串")
        if not isinstance(self.usage, UsageSnapshot):
            raise TypeError("usage必须是UsageSnapshot")
        if not isinstance(self.degraded, bool):
            raise TypeError("degraded必须是bool")
        if not isinstance(self.attempts, tuple) or any(
            not isinstance(attempt, ModelSelection) for attempt in self.attempts
        ):
            raise TypeError("attempts必须是不可变模型尝试事实")


__all__ = [
    "DIRECT_CONVERSATION_CONTRACT_VERSION",
    "MAX_VISIBLE_HISTORY_CHARACTERS",
    "MAX_VISIBLE_HISTORY_MESSAGES",
    "DirectConversationSubmission",
    "GeneralConversationExecution",
]
