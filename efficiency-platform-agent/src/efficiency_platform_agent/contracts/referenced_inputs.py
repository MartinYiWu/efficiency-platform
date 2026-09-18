"""跨轮引用只传递一个已校验排名条目及其来源闭包。"""

from pydantic import BaseModel, ConfigDict, Field, model_validator

from efficiency_platform_agent.contracts.deliverables import CitationV2, RankedItemV2


class ReferencedRankedInput(BaseModel):
    """由会话边界授权的有限输入，不能携带完整历史或自由正文。"""

    model_config = ConfigDict(extra="forbid", frozen=True)

    tenant_id: str = Field(min_length=1)
    user_id: str = Field(min_length=1)
    conversation_id: str = Field(min_length=1)
    source_run_id: str = Field(min_length=1)
    source_deliverable_id: str = Field(min_length=1)
    item: RankedItemV2
    citations: tuple[CitationV2, ...]

    @model_validator(mode="after")
    def validate_closure(self):
        """来源必须恰好闭合，且不得暴露其他条目的关联信息。"""
        ids = [citation.citation_id for citation in self.citations]
        if len(ids) != len(set(ids)) or set(ids) != set(self.item.source_refs):
            raise ValueError("REFERENCE_CITATION_CLOSURE_INVALID")
        if any(c.supports_item_ids != [self.item.item_id] for c in self.citations):
            raise ValueError("REFERENCE_ITEM_CLOSURE_INVALID")
        return self
