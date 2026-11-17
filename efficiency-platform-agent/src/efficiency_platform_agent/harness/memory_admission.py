"""内部通道认证后的整个请求绑定校验；摘要不替代身份认证。"""

import hashlib
import json
import time

from efficiency_platform_agent.core.memory_execution import MemoryExecutionContext
from efficiency_platform_agent.security.memory_packet import (
    memory_packet_digest,
    memory_packet_semantic_digest,
)


def validate_memory_request(context: MemoryExecutionContext, body: dict) -> None:
    actual_body = dict(body)
    actual_body.pop("memory_context", None)
    digest = hashlib.sha256(
        json.dumps(
            actual_body, sort_keys=True, ensure_ascii=False, separators=(",", ":")
        ).encode()
    ).hexdigest()
    if (
        digest != context.request_digest
        or memory_packet_digest(context.packet) != context.packet_digest
        or memory_packet_semantic_digest(context.packet)
        != context.semantic_snapshot_digest
    ):
        raise ValueError("MEMORY_ENVELOPE_BINDING_INVALID")
    if (
        not context.packet.issued_at
        <= time.time()
        < min(context.packet.expires_at, context.deadline_epoch_seconds)
    ):
        raise ValueError("MEMORY_PACKET_EXPIRED_OR_NOT_YET_VALID")
