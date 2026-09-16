"""通用对话准备阶段到 DIRECT Graph 的一次性提交存储。"""

from __future__ import annotations

import asyncio
import time
from collections import OrderedDict
from collections.abc import Callable, Mapping
from dataclasses import dataclass

from efficiency_platform_agent.contracts.direct_conversation import (
    DirectConversationSubmission,
)
from efficiency_platform_agent.core.run import RunRequest


class DirectConversationSubmissionError(RuntimeError):
    """提交缺失或身份不一致时使用的稳定安全错误。"""

    def __init__(self, code: str, safe_message: str) -> None:
        self.code = code
        self.safe_message = safe_message
        super().__init__(f"{code}: {safe_message}")


@dataclass(frozen=True, slots=True)
class _SubmissionEntry:
    tenant_id: str
    user_id: str
    request_id: str
    submission: DirectConversationSubmission
    expires_at: float


class DirectConversationSubmissionStore:
    """按租户和请求标识暂存提交，并在身份校验通过后一次性消费。"""

    def __init__(
        self,
        *,
        max_entries: int = 1_024,
        ttl_seconds: float = 300,
        monotonic: Callable[[], float] = time.monotonic,
    ) -> None:
        if (
            not isinstance(max_entries, int)
            or isinstance(max_entries, bool)
            or max_entries < 1
        ):
            raise ValueError("max_entries必须为正整数")
        if (
            not isinstance(ttl_seconds, (int, float))
            or isinstance(ttl_seconds, bool)
            or ttl_seconds <= 0
        ):
            raise ValueError("ttl_seconds必须为正数")
        if not callable(monotonic):
            raise TypeError("monotonic必须可调用")
        self.max_entries = max_entries
        self.ttl_seconds = float(ttl_seconds)
        self.monotonic = monotonic
        self._entries: OrderedDict[tuple[str, str], _SubmissionEntry] = OrderedDict()
        self._lock = asyncio.Lock()

    async def put(self, submission: DirectConversationSubmission) -> None:
        """在图执行前保存冻结提交；同键重放只允许完全相同的值。"""
        if not isinstance(submission, DirectConversationSubmission):
            raise TypeError("submission必须是DirectConversationSubmission")
        request = submission.request
        key = (request.tenant_id, request.request_id)
        async with self._lock:
            now = self.monotonic()
            self._purge_expired(now)
            existing = self._entries.get(key)
            if existing is not None and existing.submission != submission:
                raise DirectConversationSubmissionError(
                    "DIRECT_CONVERSATION_SUBMISSION_CONFLICT",
                    "请求标识已用于其他通用对话提交",
                )
            if existing is None and len(self._entries) >= self.max_entries:
                raise DirectConversationSubmissionError(
                    "DIRECT_CONVERSATION_SUBMISSION_CAPACITY_EXCEEDED",
                    "通用对话提交暂存已达到容量上限",
                )
            self._entries[key] = _SubmissionEntry(
                request.tenant_id,
                request.user_id,
                request.request_id,
                submission,
                now + self.ttl_seconds,
            )
            self._entries.move_to_end(key)

    async def resolve(
        self, request: RunRequest, state: Mapping[str, object]
    ) -> DirectConversationSubmission:
        """校验请求与 Graph 身份后取回提交；校验失败不消费正确提交。"""
        if not isinstance(request, RunRequest):
            raise TypeError("request必须是RunRequest")
        if not isinstance(state, Mapping):
            raise TypeError("state必须是Mapping")
        key = (request.tenant_id, request.request_id)
        async with self._lock:
            self._purge_expired(self.monotonic())
            entry = self._entries.get(key)
            if entry is None:
                raise DirectConversationSubmissionError(
                    "DIRECT_CONVERSATION_SUBMISSION_NOT_FOUND",
                    "通用对话提交不存在或已经失效",
                )
            identity = (
                request.tenant_id,
                request.user_id,
                request.request_id,
                state.get("tenant_id"),
                state.get("user_id"),
                state.get("request_id"),
            )
            if identity != (
                entry.tenant_id,
                entry.user_id,
                entry.request_id,
                entry.tenant_id,
                entry.user_id,
                entry.request_id,
            ):
                raise DirectConversationSubmissionError(
                    "DIRECT_CONVERSATION_IDENTITY_MISMATCH",
                    "通用对话提交身份不一致",
                )
            self._entries.pop(key, None)
            return entry.submission

    async def discard(self, tenant_id: str, request_id: str) -> None:
        """终态、取消或提前失败时清除尚未消费的提交。"""
        if not isinstance(tenant_id, str) or not tenant_id.strip():
            raise ValueError("tenant_id必须是非空字符串")
        if not isinstance(request_id, str) or not request_id.strip():
            raise ValueError("request_id必须是非空字符串")
        async with self._lock:
            self._entries.pop((tenant_id, request_id), None)

    def _purge_expired(self, now: float) -> None:
        """删除超过短期交接窗口且尚未消费的提交。"""
        for key, entry in tuple(self._entries.items()):
            if entry.expires_at <= now:
                self._entries.pop(key, None)


__all__ = ["DirectConversationSubmissionError", "DirectConversationSubmissionStore"]
