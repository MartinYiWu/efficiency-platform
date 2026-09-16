"""只保存可见消息的有界会话上下文。"""

from __future__ import annotations

from dataclasses import dataclass

from efficiency_platform_agent.core.run import ProviderMessage


@dataclass(frozen=True, slots=True)
class ConversationTurn:
    """一条允许进入下一轮 Prompt 的可见会话消息。"""

    role: str
    content: str

    def __post_init__(self) -> None:
        if self.role not in {"user", "assistant"}:
            raise ValueError("会话历史只允许user或assistant角色")
        if not isinstance(self.content, str) or not self.content.strip():
            raise ValueError("会话消息内容不能为空")


class ConversationContext:
    """按轮数和字符数裁剪历史，不接受思维链等附加字段。"""

    def __init__(self, *, max_turns: int = 8, max_characters: int = 12_000) -> None:
        if (
            not isinstance(max_turns, int)
            or isinstance(max_turns, bool)
            or max_turns <= 0
        ):
            raise ValueError("max_turns必须为正整数")
        if (
            not isinstance(max_characters, int)
            or isinstance(max_characters, bool)
            or max_characters <= 0
        ):
            raise ValueError("max_characters必须为正整数")
        self.max_turns = max_turns
        self.max_characters = max_characters
        self._turns: list[ConversationTurn] = []

    @property
    def turns(self) -> tuple[ConversationTurn, ...]:
        """返回不可变快照，调用方不能修改内部历史。"""
        return tuple(self._turns)

    @property
    def character_count(self) -> int:
        """返回当前可见消息的字符总数。"""
        return sum(len(turn.content) for turn in self._turns)

    def append(self, turn: ConversationTurn) -> None:
        """追加可见消息，并从最旧消息开始执行确定性裁剪。"""
        if not isinstance(turn, ConversationTurn):
            raise TypeError("turn必须是ConversationTurn")
        bounded = turn
        if len(turn.content) > self.max_characters:
            bounded = ConversationTurn(turn.role, turn.content[-self.max_characters :])
        self._turns.append(bounded)
        while len(self._turns) > self.max_turns:
            self._turns.pop(0)
        while self.character_count > self.max_characters and len(self._turns) > 1:
            self._turns.pop(0)

    def provider_messages(self) -> tuple[ProviderMessage, ...]:
        """只把已裁剪的角色和可见正文转换为 Provider 消息。"""
        return tuple(ProviderMessage(turn.role, turn.content) for turn in self._turns)


__all__ = ["ConversationContext", "ConversationTurn"]
