"""排名引用快照仓储的身份、校验与幂等边界。"""

from datetime import UTC, datetime

import pytest

from efficiency_platform_agent.capabilities.research.v2.delivery import (
    DeliveryPackBuilder,
)
from efficiency_platform_agent.contracts.research_local_runtime_v2 import (
    LocalResearchRunKeyV2,
)
from efficiency_platform_agent.harness.local_live_references import (
    LocalLiveRankedReferenceValidator,
)
from efficiency_platform_agent.persistence.mysql_ranked_references import (
    InMemoryRankedReferenceRepository,
    RankedReferencePersistenceError,
)
from tests.unit.capabilities.research_v2._delivery_support import (
    delivery_facts,
    research_outcome,
)


def _snapshot():
    brief, evidence, *_ = delivery_facts()
    delivery = DeliveryPackBuilder().build(brief, research_outcome(brief), evidence)
    delivery = delivery.model_copy(
        update={
            "output_verified": True,
            "quality_report_id": "quality-1",
            "events": tuple(
                event.model_copy(
                    update={
                        "citations": tuple(
                            citation.model_copy(
                                update={"verification_status": "verified"}
                            )
                            for citation in event.citations
                        )
                    }
                )
                for event in delivery.events
            ),
        }
    )
    key = LocalResearchRunKeyV2(
        tenant_id="tenant-1",
        user_id="user-1",
        conversation_id="conversation-1",
        run_id="run-1",
        task_id="task-1",
        revision=1,
    )
    return key, delivery


@pytest.mark.asyncio
async def test_verified_snapshot_round_trips_by_full_identity() -> None:
    repository = InMemoryRankedReferenceRepository(
        now_epoch_ms=lambda: int(datetime(2026, 10, 15, tzinfo=UTC).timestamp() * 1000)
    )
    key, delivery = _snapshot()

    await repository.save_verified(key, delivery)

    assert (
        await repository.get_verified(
            key.tenant_id, key.user_id, key.conversation_id, key.run_id
        )
        == delivery
    )
    assert (
        await repository.get_verified(
            key.tenant_id, "another-user", key.conversation_id, key.run_id
        )
        is None
    )
    assert (
        await repository.get_latest_source_run_id(
            key.tenant_id, key.user_id, key.conversation_id
        )
        == key.run_id
    )
    assert (
        await repository.get_latest_source_run_id(
            key.tenant_id, "another-user", key.conversation_id
        )
        is None
    )


@pytest.mark.asyncio
async def test_verified_snapshot_resolves_ranked_inputs_without_public_v2_output() -> None:
    repository = InMemoryRankedReferenceRepository()
    key, delivery = _snapshot()
    await repository.save_verified(key, delivery)
    resolver = LocalLiveRankedReferenceValidator(repository)

    values = await resolver.resolve(
        key.tenant_id,
        key.user_id,
        key.conversation_id,
        key.run_id,
        rank=None,
        count=20,
    )

    assert len(values) == len(delivery.events)
    assert values[0].item.item_id == delivery.events[0].event_id
    assert {item.citation_id for item in values[0].citations} == {
        item.evidence_id for item in delivery.events[0].citations
    }
    await resolver(values[0])


@pytest.mark.asyncio
async def test_unverified_or_conflicting_snapshot_is_rejected() -> None:
    repository = InMemoryRankedReferenceRepository()
    key, delivery = _snapshot()
    with pytest.raises(RankedReferencePersistenceError, match="UNVERIFIED"):
        await repository.save_verified(
            key, delivery.model_copy(update={"output_verified": False})
        )

    await repository.save_verified(key, delivery)
    with pytest.raises(RankedReferencePersistenceError, match="CONFLICT"):
        await repository.save_verified(
            key, delivery.model_copy(update={"summary": "被篡改的摘要"})
        )
