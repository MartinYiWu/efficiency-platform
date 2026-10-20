"""为智能客服 pgvector 仓储提供惰性异步连接池。"""

from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from contextvars import ContextVar
from typing import Any

from pgvector.psycopg import register_vector_async
from psycopg_pool import AsyncConnectionPool


async def _configure(connection: Any) -> None:
    await register_vector_async(connection)


class PsycopgPoolConnection:
    """兼容仓储 connection 接口，并保证事务内复用同一连接。"""

    def __init__(self, database_url: str) -> None:
        self.pool = AsyncConnectionPool(
            database_url,
            min_size=1,
            max_size=8,
            open=False,
            configure=_configure,
        )
        self._current: ContextVar[Any | None] = ContextVar(
            "customer_service_pg", default=None
        )
        self._opened = False
        self._open_lock = asyncio.Lock()

    async def _open(self) -> None:
        if self._opened:
            return
        async with self._open_lock:
            if not self._opened:
                await self.pool.open()
                self._opened = True

    @asynccontextmanager
    async def transaction(self) -> AsyncIterator[None]:
        await self._open()
        async with self.pool.connection() as connection:
            token = self._current.set(connection)
            try:
                async with connection.transaction():
                    yield
            finally:
                self._current.reset(token)

    async def execute(self, sql: str, params: tuple[object, ...] = ()) -> Any:
        current = self._current.get()
        if current is not None:
            return await current.execute(sql, params)
        await self._open()
        async with self.pool.connection() as connection:
            cursor = await connection.execute(sql, params)
            if cursor.description is None:
                return cursor
            return tuple(await cursor.fetchall())

    async def executemany(
        self, sql: str, params: tuple[tuple[object, ...], ...]
    ) -> Any:
        current = self._current.get()
        if current is not None:
            return await current.executemany(sql, params)
        await self._open()
        async with self.pool.connection() as connection:
            return await connection.executemany(sql, params)

    async def ping(self) -> None:
        await self.execute("SELECT 1")

    async def close(self) -> None:
        if self._opened:
            await self.pool.close()


__all__ = ["PsycopgPoolConnection"]
