"""PostgreSQL 真实适配边界；默认只接受注入的连接替身，不主动建立连接。"""

from __future__ import annotations

import inspect
from collections.abc import Mapping, Sequence
from typing import Any

from psycopg.types.json import Jsonb

from efficiency_platform_agent.core.postgres_schema import (
    AGENT_RUNTIME_SCHEMA_PATTERN,
    SCHEMA_PATTERN,
    InvalidPostgresSchema,
    validate_agent_owned_schema,
    validate_schema,
)


class PostgresConcurrencyError(RuntimeError):
    """PostgreSQL 乐观版本条件未命中。"""

    code = "RUN_VERSION_CONFLICT"


async def _execute(connection: Any, sql: str, params: tuple[object, ...] = ()) -> Any:
    """调用注入连接；兼容同步和异步替身，生产连接由上层显式创建。"""
    result = connection.execute(sql, params)
    if inspect.isawaitable(result):
        return await result
    return result


class PostgresProvider:
    """Agent 自有 PostgreSQL Schema 的参数化基础适配器。"""

    def __init__(
        self, connection: Any, schema: str, *, allow_runtime_schema: bool = False
    ) -> None:
        self.connection = connection
        self.schema = (
            validate_agent_owned_schema(schema)
            if allow_runtime_schema
            else validate_schema(schema)
        )

    async def save_run(
        self,
        run_id: str,
        tenant_id: str,
        payload: Mapping[str, object],
        version: int,
        request_id: str | None = None,
        expected_version: int | None = None,
    ) -> bool:
        sql = (
            f"INSERT INTO {self.schema}.runs "
            "(run_id, tenant_id, request_id, payload, version) "
            "VALUES (%s, %s, %s, %s, %s) ON CONFLICT (run_id) DO UPDATE SET "
            "payload = EXCLUDED.payload, version = EXCLUDED.version "
            "WHERE tenant_id = %s"
        )
        params: tuple[object, ...] = (
            run_id,
            tenant_id,
            request_id,
            Jsonb(dict(payload)),
            version,
            tenant_id,
        )
        if expected_version is not None:
            sql += " AND version = %s"
            params += (expected_version,)
        result = await _execute(
            self.connection,
            sql,
            params,
        )
        rowcount = getattr(result, "rowcount", None)
        return rowcount != 0 if isinstance(rowcount, int) else True

    async def append_event(
        self,
        event_id: str,
        run_id: str,
        tenant_id: str,
        sequence: int,
        payload: Mapping[str, object],
    ) -> None:
        await _execute(
            self.connection,
            f"INSERT INTO {self.schema}.run_events "
            "(event_id, run_id, tenant_id, sequence, payload) "
            "VALUES (%s, %s, %s, %s, %s) ON CONFLICT (event_id) DO UPDATE SET "
            "payload = EXCLUDED.payload WHERE tenant_id = %s",
            (event_id, run_id, tenant_id, sequence, Jsonb(dict(payload)), tenant_id),
        )

    async def list_events(
        self, run_id: str, tenant_id: str, after_sequence: int = 0
    ) -> Sequence[Mapping[str, object]]:
        result = await _execute(
            self.connection,
            f"SELECT event_id, run_id, tenant_id, sequence, payload "
            f"FROM {self.schema}.run_events WHERE run_id = %s AND tenant_id = %s "
            "AND sequence > %s ORDER BY sequence",
            (run_id, tenant_id, after_sequence),
        )
        return tuple(result or ())

    async def save_usage(
        self,
        run_id: str,
        tenant_id: str,
        input_tokens: int,
        output_tokens: int,
        cost_microunits: int,
    ) -> None:
        await _execute(
            self.connection,
            f"INSERT INTO {self.schema}.run_usage "
            "(run_id, tenant_id, input_tokens, output_tokens, cost_microunits) "
            "VALUES (%s, %s, %s, %s, %s) ON CONFLICT (run_id) DO UPDATE SET "
            "input_tokens = EXCLUDED.input_tokens, output_tokens = EXCLUDED.output_tokens, "
            "cost_microunits = EXCLUDED.cost_microunits WHERE tenant_id = %s",
            (
                run_id,
                tenant_id,
                input_tokens,
                output_tokens,
                cost_microunits,
                tenant_id,
            ),
        )

    async def save_checkpoint(
        self,
        thread_id: str,
        tenant_id: str,
        checkpoint_ns: str,
        checkpoint_id: str,
        state: Mapping[str, object],
    ) -> None:
        await _execute(
            self.connection,
            f"INSERT INTO {self.schema}.checkpoints "
            "(thread_id, tenant_id, checkpoint_ns, checkpoint_id, state) "
            "VALUES (%s, %s, %s, %s, %s) "
            "ON CONFLICT (tenant_id, thread_id, checkpoint_ns) "
            "DO UPDATE SET checkpoint_id = EXCLUDED.checkpoint_id, "
            "state = EXCLUDED.state",
            (
                thread_id,
                tenant_id,
                checkpoint_ns,
                checkpoint_id,
                Jsonb(dict(state)),
            ),
        )

    async def close(self) -> None:
        """关闭注入连接或连接池，不吞掉关闭异常。"""
        close = getattr(self.connection, "close", None)
        if close is not None:
            result = close()
            if inspect.isawaitable(result):
                await result


__all__ = [
    "AGENT_RUNTIME_SCHEMA_PATTERN",
    "SCHEMA_PATTERN",
    "InvalidPostgresSchema",
    "PostgresConcurrencyError",
    "PostgresProvider",
    "validate_agent_owned_schema",
    "validate_schema",
]
