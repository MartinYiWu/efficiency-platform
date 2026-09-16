"""Context Builder 的不可变契约。"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from enum import StrEnum

from efficiency_platform_agent.core.run import JsonValue


class TrustLevel(StrEnum):
    """上下文来源的信任等级。"""

    SYSTEM = "system"
    USER_UNTRUSTED = "user_untrusted"
    TOOL_UNTRUSTED = "tool_untrusted"


@dataclass(frozen=True, slots=True)
class ContextSource:
    """带来源和信任标签的上下文片段。"""

    source_id: str
    trust_level: TrustLevel
    content: JsonValue


@dataclass(frozen=True, slots=True)
class BuiltContext:
    """一次构建得到的最小上下文切片。"""

    run_id: str
    tenant_id: str
    user_id: str
    sources: Sequence[ContextSource]
    allowed_tools: frozenset[str]
    max_input_tokens: int
    estimated_input_tokens: int
