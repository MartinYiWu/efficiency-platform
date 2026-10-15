"""排名引用快照仓储的身份、校验与幂等边界。"""

from datetime import UTC, datetime

import pytest

from efficiency_platform_agent.capabilities.research.v2.delivery import (
    DeliveryPackBuilder,
)
from efficiency_platform_agent.contracts.research_local_runtime_v2 import (
    LocalResearchRunKeyV2,
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
        update={"output_verified": True, "quality_report_id": "quality-1"}
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
