"""排名引用必须回溯同身份、未过期的已交付研究事实；不接受模型文本。"""

from urllib.parse import urlsplit

from efficiency_platform_agent.contracts.deliverables import CitationV2, RankedItemV2
from efficiency_platform_agent.contracts.referenced_inputs import ReferencedRankedInput
from efficiency_platform_agent.contracts.research_v2 import DeliveryPackV2
from efficiency_platform_agent.persistence.mysql_ranked_references import (
    RankedReferencePersistenceError,
    RankedReferenceRepository,
)

from .referenced_inputs import reference_error


class LocalLiveRankedReferenceValidator:
    def __init__(self, repository: RankedReferenceRepository) -> None:
        self.repository = repository

    async def latest_source_run_id(
        self, tenant_id: str, user_id: str, conversation_id: str
    ) -> str | None:
        try:
            return await self.repository.get_latest_source_run_id(
                tenant_id, user_id, conversation_id
            )
        except RankedReferencePersistenceError as error:
            raise reference_error() from error

    async def resolve(
        self,
        tenant_id: str,
        user_id: str,
        conversation_id: str,
        source_run_id: str,
        *,
        rank: int | None,
        count: int | None,
    ) -> tuple[ReferencedRankedInput, ...]:
        """从已核验内部快照恢复有限引用，不依赖对外交付契约版本。"""
        if (rank is None) == (count is None):
            raise reference_error()
        try:
            delivery = await self.repository.get_verified(
                tenant_id, user_id, conversation_id, source_run_id
            )
        except RankedReferencePersistenceError as error:
            raise reference_error() from error
        if delivery is None or not delivery.output_verified:
            raise reference_error()
        if rank is not None:
            if not 1 <= rank <= len(delivery.events):
                raise reference_error()
            positions: tuple[int, ...] = (rank,)
        else:
            positions = tuple(range(1, min(count or 0, len(delivery.events)) + 1))
            if not positions:
                raise reference_error()
        values = tuple(
            _build_reference(
                delivery,
                position,
                tenant_id=tenant_id,
                user_id=user_id,
                conversation_id=conversation_id,
                source_run_id=source_run_id,
            )
            for position in positions
        )
        for value in values:
            await self(value)
        return values

    async def __call__(self, value: ReferencedRankedInput) -> None:
        try:
            delivery = await self.repository.get_verified(
                value.tenant_id,
                value.user_id,
                value.conversation_id,
                value.source_run_id,
            )
        except RankedReferencePersistenceError as error:
            raise reference_error() from error
        if delivery is None:
            raise reference_error()
        item = value.item
        if not delivery.output_verified or not 1 <= item.rank <= len(delivery.events):
            raise reference_error()
        event = delivery.events[item.rank - 1]
        if (
            item.item_id != event.event_id
            or item.title != event.title[:500]
            or item.summary != "\n".join(event.claim_texts)[:2000]
            or item.occurred_at
            != (event.event_time.isoformat() if event.event_time else None)
            or item.verification_status != "verified"
            or item.confidence != "low"
            or item.why_it_matters
            != "反映了近期 AI 产品或技术方向的公开变化，适合作为后续选题观察点。"
            or item.source_refs != [source.evidence_id for source in event.citations]
        ):
            raise reference_error()
        sources = {source.evidence_id: source for source in event.citations}
        for citation in value.citations:
            source = sources[citation.citation_id]
            if (
                citation.url != source.url
                or citation.title != source.title[:500]
                or citation.source != source.publisher_id
                or citation.source_type
                != (
                    "api"
                    if source.acquisition_method == "api"
                    else "rss"
                    if source.acquisition_method in {"rss", "atom"}
                    else "public_page"
                )
                or citation.source_tier
                != ("primary" if source.source_role == "primary" else "secondary")
                or citation.independent_source_group
                != (source.independent_source_group or urlsplit(source.url).hostname)
                or citation.published_at
                != (source.published_at.isoformat() if source.published_at else None)
                or citation.document_id != source.document_id
                or citation.excerpt != source.excerpt
                or citation.content_hash != source.content_hash
                or citation.content_scope != source.content_scope
                or citation.acquisition_method != source.acquisition_method
                or citation.verification_status != "verified"
                or source.verification_status != "verified"
            ):
                raise reference_error()


def _build_reference(
    delivery: DeliveryPackV2,
    position: int,
    *,
    tenant_id: str,
    user_id: str,
    conversation_id: str,
    source_run_id: str,
) -> ReferencedRankedInput:
    event = delivery.events[position - 1]
    item_id = event.event_id
    citations = tuple(
        CitationV2(
            citation_id=source.evidence_id,
            url=source.url,
            title=source.title[:500],
            source=source.publisher_id,
            published_at=(
                source.published_at.isoformat() if source.published_at else None
            ),
            source_type=(
                "api"
                if source.acquisition_method == "api"
                else "rss"
                if source.acquisition_method in {"rss", "atom"}
                else "public_page"
            ),
            source_tier=(
                "primary" if source.source_role == "primary" else "secondary"
            ),
            verification_status="verified",
            supports_item_ids=[item_id],
            independent_source_group=(
                source.independent_source_group or urlsplit(source.url).hostname
            ),
            document_id=source.document_id,
            excerpt=source.excerpt,
            content_scope=source.content_scope,
            content_hash=source.content_hash,
            acquisition_method=source.acquisition_method,
        )
        for source in event.citations
    )
    return ReferencedRankedInput(
        tenant_id=tenant_id,
        user_id=user_id,
        conversation_id=conversation_id,
        source_run_id=source_run_id,
        source_deliverable_id=delivery.delivery_id,
        item=RankedItemV2(
            item_id=item_id,
            rank=position,
            title=event.title[:500],
            occurred_at=event.event_time.isoformat() if event.event_time else None,
            summary="\n".join(event.claim_texts)[:2_000],
            why_it_matters=(
                "反映了近期 AI 产品或技术方向的公开变化，适合作为后续选题观察点。"
            ),
            content_angles=[],
            metrics=[],
            source_refs=[source.evidence_id for source in event.citations],
            confidence="low",
            verification_status="verified",
        ),
        citations=citations,
    )
