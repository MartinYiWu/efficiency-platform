"""已核验排名引用快照的 MySQL 持久化边界。"""

from __future__ import annotations

import hashlib
import json
import logging
import time
from collections.abc import Callable
from typing import Protocol

from sqlalchemy import text
from sqlalchemy.exc import IntegrityError, SQLAlchemyError
from sqlalchemy.ext.asyncio import AsyncEngine

from efficiency_platform_agent.contracts.research_local_runtime_v2 import (
    LocalResearchRunKeyV2,
)
from efficiency_platform_agent.contracts.research_v2 import DeliveryPackV2

logger = logging.getLogger(__name__)


class RankedReferencePersistenceError(ValueError):
    """引用快照无法安全保存或恢复。"""

    def __init__(self, code: str) -> None:
        self.code = code
        super().__init__(code)


class RankedReferenceRepository(Protocol):
    async def save_verified(
        self, key: LocalResearchRunKeyV2, delivery: DeliveryPackV2
    ) -> None: ...

    async def get_verified(
        self,
        tenant_id: str,
        user_id: str,
        conversation_id: str,
        source_run_id: str,
    ) -> DeliveryPackV2 | None: ...

    async def get_latest_source_run_id(
        self,
        tenant_id: str,
        user_id: str,
        conversation_id: str,
    ) -> str | None: ...


class MySqlRankedReferenceRepository:
    """按完整会话身份保存不可变、可校验的已核验引用快照。"""

    def __init__(
        self,
        engine: AsyncEngine,
        *,
        now_epoch_ms: Callable[[], int] = lambda: int(time.time() * 1000),
    ) -> None:
        self.engine = engine
        self.now_epoch_ms = now_epoch_ms

    async def save_verified(
        self, key: LocalResearchRunKeyV2, delivery: DeliveryPackV2
    ) -> None:
        payload, content_hash = _verified_payload(key, delivery)
        now = self.now_epoch_ms()
        parameters = {
            "tenant_id": key.tenant_id,
            "user_id": key.user_id,
            "conversation_id": key.conversation_id,
            "source_run_id": key.run_id,
        }
        try:
            async with self.engine.begin() as connection:
                existing = await connection.execute(
                    text(
                        "SELECT content_hash FROM agent_ranked_reference_snapshot "
                        "WHERE tenant_id=:tenant_id AND user_id=:user_id "
                        "AND conversation_id=:conversation_id "
                        "AND source_run_id=:source_run_id FOR UPDATE"
                    ),
                    parameters,
                )
                previous_hash = existing.scalar_one_or_none()
                if previous_hash is not None and previous_hash != content_hash:
                    raise RankedReferencePersistenceError(
                        "RANKED_REFERENCE_SNAPSHOT_CONFLICT"
                    )
                if previous_hash is None:
                    await connection.execute(
                        text(
                            "INSERT INTO agent_ranked_reference_snapshot "
                            "(tenant_id,user_id,conversation_id,source_run_id,"
                            "contract_version,deliverable_json,content_hash,"
                            "created_at_epoch_ms,expires_at_epoch_ms) VALUES "
                            "(:tenant_id,:user_id,:conversation_id,:source_run_id,"
                            ":contract_version,CAST(:deliverable_json AS JSON),"
                            ":content_hash,:created_at_epoch_ms,NULL)"
                        ),
                        {
                            **parameters,
                            "contract_version": delivery.schema_version,
                            "deliverable_json": payload,
                            "content_hash": content_hash,
                            "created_at_epoch_ms": now,
                        },
                    )
        except RankedReferencePersistenceError:
            raise
        except IntegrityError as exc:
            raise RankedReferencePersistenceError(
                "RANKED_REFERENCE_SNAPSHOT_CONFLICT"
            ) from exc
        except SQLAlchemyError as exc:
            raise RankedReferencePersistenceError(
                "RANKED_REFERENCE_DATABASE_UNAVAILABLE"
            ) from exc
        logger.info(
            "event=ranked_reference_snapshot_saved tenant_id=%s conversation_id=%s source_run_id=%s",
            key.tenant_id,
            key.conversation_id,
            key.run_id,
        )

    async def get_verified(
        self,
        tenant_id: str,
        user_id: str,
        conversation_id: str,
        source_run_id: str,
    ) -> DeliveryPackV2 | None:
        try:
            async with self.engine.connect() as connection:
                result = await connection.execute(
                    text(
                        "SELECT contract_version,deliverable_json,content_hash,"
                        "expires_at_epoch_ms FROM agent_ranked_reference_snapshot "
                        "WHERE tenant_id=:tenant_id AND user_id=:user_id "
                        "AND conversation_id=:conversation_id "
                        "AND source_run_id=:source_run_id"
                    ),
                    {
                        "tenant_id": tenant_id,
                        "user_id": user_id,
                        "conversation_id": conversation_id,
                        "source_run_id": source_run_id,
                    },
                )
                row = result.mappings().one_or_none()
        except SQLAlchemyError as exc:
            raise RankedReferencePersistenceError(
                "RANKED_REFERENCE_DATABASE_UNAVAILABLE"
            ) from exc
        if row is None:
            return None
        expires_at = row["expires_at_epoch_ms"]
        if expires_at is not None and int(expires_at) <= self.now_epoch_ms():
            return None
        try:
            raw = row["deliverable_json"]
            value = json.loads(raw) if isinstance(raw, str) else raw
            delivery = DeliveryPackV2.model_validate(value)
        except (TypeError, ValueError, json.JSONDecodeError) as exc:
            raise RankedReferencePersistenceError(
                "RANKED_REFERENCE_SNAPSHOT_INVALID"
            ) from exc
        payload, content_hash = _verified_payload(None, delivery)
        if (
            row["contract_version"] != delivery.schema_version
            or row["contract_version"] != "delivery-pack/2"
            or row["content_hash"] != content_hash
            or hashlib.sha256(payload.encode("utf-8")).hexdigest() != content_hash
        ):
            raise RankedReferencePersistenceError(
                "RANKED_REFERENCE_SNAPSHOT_INVALID"
            )
        logger.info(
            "event=ranked_reference_snapshot_loaded tenant_id=%s conversation_id=%s source_run_id=%s",
            tenant_id,
            conversation_id,
            source_run_id,
        )
        return delivery

    async def get_latest_source_run_id(
        self,
        tenant_id: str,
        user_id: str,
        conversation_id: str,
    ) -> str | None:
        try:
            async with self.engine.connect() as connection:
                result = await connection.execute(
                    text(
                        "SELECT source_run_id FROM agent_ranked_reference_snapshot "
                        "WHERE tenant_id=:tenant_id AND user_id=:user_id "
                        "AND conversation_id=:conversation_id "
                        "AND (expires_at_epoch_ms IS NULL OR expires_at_epoch_ms>:now) "
                        "ORDER BY created_at_epoch_ms DESC,id DESC LIMIT 1"
                    ),
                    {
                        "tenant_id": tenant_id,
                        "user_id": user_id,
                        "conversation_id": conversation_id,
                        "now": self.now_epoch_ms(),
                    },
                )
                source_run_id = result.scalar_one_or_none()
        except SQLAlchemyError as exc:
            raise RankedReferencePersistenceError(
                "RANKED_REFERENCE_DATABASE_UNAVAILABLE"
            ) from exc
        if source_run_id is None:
            return None
        delivery = await self.get_verified(
            tenant_id, user_id, conversation_id, str(source_run_id)
        )
        return str(source_run_id) if delivery is not None else None


class InMemoryRankedReferenceRepository:
    """仅供显式测试组合使用，语义与 MySQL 仓储一致。"""

    def __init__(
        self,
        *,
        now_epoch_ms: Callable[[], int] = lambda: int(time.time() * 1000),
    ) -> None:
        self.now_epoch_ms = now_epoch_ms
        self._entries: dict[
            tuple[str, str, str, str], tuple[str, DeliveryPackV2]
        ] = {}

    async def save_verified(
        self, key: LocalResearchRunKeyV2, delivery: DeliveryPackV2
    ) -> None:
        _payload, content_hash = _verified_payload(key, delivery)
        identity = (key.tenant_id, key.user_id, key.conversation_id, key.run_id)
        existing = self._entries.get(identity)
        if existing is not None and existing[0] != content_hash:
            raise RankedReferencePersistenceError(
                "RANKED_REFERENCE_SNAPSHOT_CONFLICT"
            )
        self._entries[identity] = (content_hash, delivery.model_copy(deep=True))

    async def get_verified(
        self,
        tenant_id: str,
        user_id: str,
        conversation_id: str,
        source_run_id: str,
    ) -> DeliveryPackV2 | None:
        value = self._entries.get(
            (tenant_id, user_id, conversation_id, source_run_id)
        )
        if value is None:
            return None
        _verified_payload(None, value[1])
        return value[1].model_copy(deep=True)

    async def get_latest_source_run_id(
        self,
        tenant_id: str,
        user_id: str,
        conversation_id: str,
    ) -> str | None:
        matches = [
            source_run_id
            for entry_tenant, entry_user, entry_conversation, source_run_id in self._entries
            if (entry_tenant, entry_user, entry_conversation)
            == (tenant_id, user_id, conversation_id)
        ]
        return matches[-1] if matches else None


def _verified_payload(
    key: LocalResearchRunKeyV2 | None, delivery: DeliveryPackV2
) -> tuple[str, str]:
    if key is not None and any(
        len(value) > 64
        for value in (key.tenant_id, key.user_id, key.conversation_id, key.run_id)
    ):
        raise RankedReferencePersistenceError("RANKED_REFERENCE_IDENTITY_INVALID")
    if (
        delivery.schema_version != "delivery-pack/2"
        or not delivery.output_verified
        or delivery.quality_report_id is None
        or delivery.outcome not in {"COMPLETE", "PARTIAL"}
        or not delivery.events
    ):
        raise RankedReferencePersistenceError(
            "RANKED_REFERENCE_SNAPSHOT_UNVERIFIED"
        )
    payload = json.dumps(
        delivery.model_dump(mode="json"),
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    )
    return payload, hashlib.sha256(payload.encode("utf-8")).hexdigest()


__all__ = [
    "InMemoryRankedReferenceRepository",
    "MySqlRankedReferenceRepository",
    "RankedReferencePersistenceError",
    "RankedReferenceRepository",
]
