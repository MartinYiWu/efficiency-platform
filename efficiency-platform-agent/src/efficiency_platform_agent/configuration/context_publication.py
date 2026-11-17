"""仅读取管理员显式发布的窗口资产；不推断模型容量或下载分词器。"""

from pathlib import Path
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from efficiency_platform_agent.core.context_ports import ContextMetadata
from efficiency_platform_agent.core.memory import require_id


class ContextPublication(BaseModel):
    model_config = ConfigDict(
        extra="forbid", frozen=True, strict=True, hide_input_in_errors=True
    )
    schema_version: Literal["context-publication/1"]
    metadata: tuple[ContextMetadata, ...] = Field(min_length=1, max_length=1024)
    execution_agents: dict[str, tuple[str, str]]

    def published(self) -> dict[tuple[str, str, str], tuple[ContextMetadata, ...]]:
        grouped: dict[tuple[str, str, str], list[ContextMetadata]] = {}
        for node, (agent, purpose) in self.execution_agents.items():
            for identifier in (node, agent, purpose):
                require_id(identifier)
        for value in self.metadata:
            key = (value.capacity.provider, value.capacity.model, value.node_id)
            grouped.setdefault(key, []).append(value)
        return {key: tuple(values) for key, values in grouped.items()}


def load_context_publication(path: Path | None) -> ContextPublication:
    if path is None:
        raise ValueError("CONTEXT_PUBLICATION_REQUIRED")
    try:
        if path.stat().st_size > 4_194_304:
            raise ValueError
        return ContextPublication.model_validate_json(path.read_bytes())
    except (OSError, ValueError, TypeError):
        raise ValueError("CONTEXT_PUBLICATION_INVALID") from None
