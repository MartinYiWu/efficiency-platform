"""验证 pgvector 连接适配器使用 psycopg Cursor 批量执行。"""

from __future__ import annotations

from typing import Any

from efficiency_platform_agent.providers.database.psycopg_pool import (
    PsycopgPoolConnection,
)


class _CursorContext:
    def __init__(self, cursor: _Cursor) -> None:
        self.cursor = cursor

    async def __aenter__(self) -> _Cursor:
        return self.cursor

    async def __aexit__(self, *_: object) -> None:
        return None


class _Cursor:
    def __init__(self) -> None:
        self.calls: list[tuple[str, tuple[tuple[object, ...], ...]]] = []

    async def executemany(
        self, sql: str, params: tuple[tuple[object, ...], ...]
    ) -> None:
        self.calls.append((sql, params))


class _Connection:
    def __init__(self, cursor: _Cursor) -> None:
        self.value = cursor

    def cursor(self) -> Any:
        return _CursorContext(self.value)


async def test_executemany_uses_cursor_inside_transaction() -> None:
    adapter = PsycopgPoolConnection("postgresql://local/test")
    cursor = _Cursor()
    token = adapter._current.set(_Connection(cursor))
    try:
        await adapter.executemany("INSERT INTO value VALUES (%s)", (("one",),))
    finally:
        adapter._current.reset(token)

    assert cursor.calls == [("INSERT INTO value VALUES (%s)", (("one",),))]
