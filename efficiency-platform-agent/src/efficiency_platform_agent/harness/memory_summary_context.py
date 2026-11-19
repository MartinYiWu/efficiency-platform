"""可信Java摘要/真实消息投影端口与OPS精确消息拆分；不读取业务表。"""

import hashlib
import json
from dataclasses import dataclass
from typing import Protocol

from efficiency_platform_agent.context.policy import ContextPiece, JsonHistoryProjection
from efficiency_platform_agent.core.context_dispatch import current_model_stage
from efficiency_platform_agent.core.memory import (
    ExecutionScope,
    MemoryContextPacket,
    SourceDependency,
    require_bool,
    require_dependencies,
    require_id,
)
from efficiency_platform_agent.core.run import ProviderMessage, ProviderRequest
from efficiency_platform_agent.memory.summary_selection import CommittedSummary


@dataclass(frozen=True, slots=True)
class OriginalMessageProjection:
    message_id: str
    role: str
    content_sha256: str
    safety_dependencies: tuple[SourceDependency, ...]
    group_completed: bool = True

    def __post_init__(self) -> None:
        require_id(self.message_id)
        require_dependencies(self.safety_dependencies)
        require_bool(self.group_completed)
        if (
            self.role not in {"system", "developer", "user", "assistant"}
            or len(self.content_sha256) != 64
            or any(c not in "0123456789abcdef" for c in self.content_sha256)
        ):
            raise ValueError("MEMORY_ORIGINAL_PROJECTION_INVALID")


class MemorySummaryContextPort(Protocol):
    async def current(
        self, scope: ExecutionScope, packet: MemoryContextPacket
    ) -> tuple[CommittedSummary, ...]:
        """仅返回经过内部认证、当前来源重核的Java已提交投影。"""
        ...

    async def original_messages(
        self, scope: ExecutionScope, packet: MemoryContextPacket
    ) -> tuple[OriginalMessageProjection, ...]:
        """返回OPS direct全部visible_history的有序投影；不包含系统和当前用户。"""
        ...


def project_original_messages(
    request: ProviderRequest,
    scope: ExecutionScope,
    projections: tuple[OriginalMessageProjection, ...],
    *,
    required_dependencies: tuple[SourceDependency, ...] = (),
) -> tuple[ContextPiece, ...] | None:
    # OPS direct实际构造为(system, *visible_history, current_user)。
    # 只依靠这个已发布的完整消息边界，不搜索或裁剪正文。
    if (
        len(request.messages) < 2
        or request.messages[0].role != "system"
        or request.messages[-1].role != "user"
    ):
        return None
    history = request.messages[1:-1]
    if (
        not projections
        or len(projections) != len(history)
        or len({projection.message_id for projection in projections})
        != len(projections)
        or any(
            message.role != projection.role
            or not isinstance(message.content, str)
            or hashlib.sha256(message.content.encode("utf-8")).hexdigest()
            != projection.content_sha256
            or not projection.group_completed
            or not projection.safety_dependencies
            or message.tool_calls
            or message.role not in {"user", "assistant"}
            for message, projection in zip(history, projections, strict=True)
        )
    ):
        return None
    return (
        ContextPiece(
            "original-system",
            scope,
            (request.messages[0],),
            required_dependencies,
            required=True,
            kind="system",
        ),
        *tuple(
            ContextPiece(
                "original-message-" + str(index),
                scope,
                (message,),
                projection.safety_dependencies,
                priority=index,
                kind="history",
                covered_message_ids=(projection.message_id,),
            )
            for index, (message, projection) in enumerate(
                zip(history, projections, strict=True)
            )
        ),
        ContextPiece(
            "original-current",
            scope,
            (request.messages[-1],),
            required_dependencies,
            required=True,
            kind="current_request",
        ),
    )


def project_csr_original_messages(
    request: ProviderRequest,
    scope: ExecutionScope,
    projections: tuple[OriginalMessageProjection, ...],
    *,
    required_dependencies: tuple[SourceDependency, ...],
) -> tuple[tuple[ContextPiece, ...], JsonHistoryProjection] | None:
    """仅answer_general原stage的确切input JSON；按全值匹配，不搜索/切掉自由正文。"""
    stage = current_model_stage()
    if (
        stage is None
        or stage.node_id != "customer-service:answer_general"
        or scope.conversation.domain != "customer-service"
    ):
        return None
    try:
        semantic = json.loads(stage.semantic_input)
        if (
            set(semantic) != {"stage_key", "input_value"}
            or semantic["stage_key"] != "answer_general"
        ):
            return None
        value = semantic["input_value"]
        if (
            not isinstance(value, dict)
            or not isinstance(value.get("history"), list)
            or not projections
        ):
            return None
        if value.get("evidence") not in ([], {}, None) or value.get(
            "sufficiency"
        ) not in (None, {}):
            return None
        encoded = json.dumps(value, ensure_ascii=False, separators=(",", ":"))
        candidates = [
            (index, message)
            for index, message in enumerate(request.messages)
            if message.role == "user"
            and isinstance(message.content, str)
            and encoded in message.content
        ]
        if len(candidates) != 1:
            return None
        index, message = candidates[0]
        if not isinstance(message.content,str):return None
        if message.content.count(encoded) != 1:
            return None
        prefix, suffix = message.content.split(encoded)
        history = value["history"]
        if len(history) != len(projections) or len(
            {p.message_id for p in projections}
        ) != len(projections):
            return None
        for item, projection in zip(history, projections, strict=True):
            if (
                not isinstance(item, dict)
                or set(item) != {"role", "content"}
                or item["role"] != projection.role
                or not isinstance(item["content"], str)
                or hashlib.sha256(item["content"].encode()).hexdigest()
                != projection.content_sha256
                or not projection.group_completed
                or not projection.safety_dependencies
            ):
                return None
        renderer = JsonHistoryProjection(index, prefix, suffix, encoded, message)
        pieces: list[ContextPiece] = []
        for position, original in enumerate(request.messages):
            if position == index:
                pieces.extend(
                    ContextPiece(
                        "csr-history-" + str(i),
                        scope,
                        (ProviderMessage(item["role"], item["content"]),),
                        projection.safety_dependencies,
                        priority=i,
                        kind="history",
                        covered_message_ids=(projection.message_id,),
                    )
                    for i, (item, projection) in enumerate(
                        zip(history, projections, strict=True)
                    )
                )
                pieces.append(
                    ContextPiece(
                        "csr-json-body",
                        scope,
                        (original,),
                        required_dependencies,
                        required=True,
                        kind="current_request",
                    )
                )
            else:
                pieces.append(
                    ContextPiece(
                        "csr-fixed-" + str(position),
                        scope,
                        (original,),
                        required_dependencies,
                        required=True,
                        kind="system"
                        if original.role == "system"
                        else "current_request",
                    )
                )
        if renderer.render(tuple(pieces)) != request.messages:
            return None
        return tuple(pieces), renderer
    except (ValueError, TypeError, KeyError):
        return None
