"""排名引用必须回溯同身份、未过期的已交付研究事实；不接受模型文本。"""

from urllib.parse import urlsplit

from efficiency_platform_agent.contracts.referenced_inputs import ReferencedRankedInput
from efficiency_platform_agent.persistence.research_local_memory import (
    LocalResearchRunStore,
)

from .referenced_inputs import reference_error


class LocalLiveRankedReferenceValidator:
    def __init__(self, store: LocalResearchRunStore) -> None:
        self.store = store

    async def __call__(self, value: ReferencedRankedInput) -> None:
        keys = [
            key
            for key in await self.store.retained_keys()
            if (key.tenant_id, key.user_id, key.conversation_id, key.run_id)
            == (
                value.tenant_id,
                value.user_id,
                value.conversation_id,
                value.source_run_id,
            )
        ]
        if len(keys) != 1:
            raise reference_error()
        try:
            facts = await self.store.get(keys[0])
        except KeyError as error:
            raise reference_error() from error
        outcome = facts.outcome
        if facts.status != "completed" or outcome is None or outcome.delivery is None:
            raise reference_error()
        delivery = outcome.delivery
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
            != "符合已冻结研究范围；可据所列证据继续评估内容选题。"
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
