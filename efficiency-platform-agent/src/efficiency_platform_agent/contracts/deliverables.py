"""运营助手面向前端的结构化交付物契约。"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


class CitationV1(BaseModel):
    """交付物中可追溯的来源引用。"""

    model_config = ConfigDict(extra="forbid", frozen=True)

    url: str = Field(min_length=1, max_length=4_000, description="来源 URL。")
    title: str | None = Field(default=None, max_length=500, description="来源标题。")
    source: str | None = Field(default=None, max_length=500, description="来源名称。")


class DeliverableV1(BaseModel):
    """一个可直接展示或复制的单平台运营成品。"""

    model_config = ConfigDict(extra="forbid", frozen=True)

    contract_version: Literal["deliverable/1"] = Field(
        default="deliverable/1", description="交付物契约版本。"
    )
    platform: str = Field(min_length=1, max_length=128, description="目标平台。")
    title: str = Field(min_length=1, max_length=500, description="交付物标题。")
    body: str = Field(min_length=1, max_length=100_000, description="交付物正文。")
    hashtags: list[str] = Field(default_factory=list, description="平台标签。")
    format_notes: list[str] = Field(default_factory=list, description="平台格式说明。")
    citations: list[CitationV1] = Field(default_factory=list, description="来源引用。")
    warnings: list[str] = Field(default_factory=list, description="降级或质量提醒。")


class DeliverableSetV1(BaseModel):
    """一次运营任务的结构化交付物集合。"""

    model_config = ConfigDict(extra="forbid", frozen=True)

    contract_version: Literal["deliverable-set/1"] = Field(
        default="deliverable-set/1", description="交付物集合契约版本。"
    )
    deliverables: list[DeliverableV1] = Field(description="独立的平台交付物列表。")
    summary: str = Field(min_length=1, max_length=10_000, description="任务总结。")
    degraded: bool = Field(default=False, description="是否存在部分失败或降级。")


__all__ = ["CitationV1", "DeliverableSetV1", "DeliverableV1"]
