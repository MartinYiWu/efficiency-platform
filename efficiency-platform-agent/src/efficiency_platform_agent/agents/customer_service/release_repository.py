"""智能客服 Release Bundle 幂等持久化。"""

from __future__ import annotations

import json
import time
from uuid import UUID

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncEngine

from .release_bundle import CustomerServiceReleaseBundle


class ReleaseConflictError(RuntimeError):
    code = "CS_AGENT_RELEASE_CONFLICT"


class InMemoryReleaseRepository:
    def __init__(self) -> None:
        self.values: dict[UUID, CustomerServiceReleaseBundle] = {}

    async def save(
        self, release_id: UUID, bundle: CustomerServiceReleaseBundle
    ) -> CustomerServiceReleaseBundle:
        current = self.values.get(release_id)
        if current is not None:
            if current.snapshot_checksum != bundle.snapshot_checksum:
                raise ReleaseConflictError("Release ID 已绑定其他 checksum")
            return current
        self.values[release_id] = bundle
        return bundle

    async def get(
        self, release_id: UUID
    ) -> CustomerServiceReleaseBundle | None:
        return self.values.get(release_id)

    async def get_active(self) -> tuple[UUID, CustomerServiceReleaseBundle] | None:
        if not self.values:
            return None
        release_id = next(reversed(self.values))
        return release_id, self.values[release_id]


class MySqlReleaseRepository:
    def __init__(self, engine: AsyncEngine) -> None:
        self.engine = engine

    async def save(
        self, release_id: UUID, bundle: CustomerServiceReleaseBundle
    ) -> CustomerServiceReleaseBundle:
        release_key = str(release_id)
        async with self.engine.begin() as connection:
            result = await connection.execute(
                text(
                    "SELECT checksum,snapshot_json FROM agent_release_bundle "
                    "WHERE release_id=:release_id FOR UPDATE"
                ),
                {"release_id": release_key},
            )
            row = result.first()
            if row is not None:
                if row.checksum != bundle.snapshot_checksum:
                    raise ReleaseConflictError("Release ID 已绑定其他 checksum")
                return CustomerServiceReleaseBundle.model_validate(row.snapshot_json)
            await connection.execute(
                text(
                    "INSERT INTO agent_release_bundle "
                    "(release_id,agent_key,agent_version,graph_version,environment,"
                    "snapshot_json,checksum,status,created_at_epoch_ms) VALUES "
                    "(:release_id,:agent_key,:agent_version,:graph_version,:environment,"
                    "CAST(:snapshot_json AS JSON),:checksum,'ACTIVE',:created_at)"
                ),
                {
                    "release_id": release_key,
                    "agent_key": bundle.agent_key,
                    "agent_version": bundle.agent_version,
                    "graph_version": bundle.graph_version,
                    "environment": bundle.environment,
                    "snapshot_json": json.dumps(
                        bundle.model_dump(mode="json"), ensure_ascii=False
                    ),
                    "checksum": bundle.snapshot_checksum,
                    "created_at": int(time.time() * 1000),
                },
            )
        return bundle

    async def get(
        self, release_id: UUID
    ) -> CustomerServiceReleaseBundle | None:
        async with self.engine.connect() as connection:
            result = await connection.execute(
                text(
                    "SELECT snapshot_json FROM agent_release_bundle "
                    "WHERE release_id=:release_id"
                ),
                {"release_id": str(release_id)},
            )
            value = result.scalar_one_or_none()
        return (
            None
            if value is None
            else CustomerServiceReleaseBundle.model_validate(value)
        )

    async def get_active(self) -> tuple[UUID, CustomerServiceReleaseBundle] | None:
        async with self.engine.connect() as connection:
            result = await connection.execute(
                text(
                    "SELECT release_id,snapshot_json FROM agent_release_bundle "
                    "WHERE agent_key='customer-service' AND status='ACTIVE' "
                    "ORDER BY created_at_epoch_ms DESC LIMIT 1"
                )
            )
            row = result.first()
        if row is None:
            return None
        return UUID(str(row.release_id)), CustomerServiceReleaseBundle.model_validate(row.snapshot_json)


__all__ = [
    "InMemoryReleaseRepository",
    "MySqlReleaseRepository",
    "ReleaseConflictError",
]
