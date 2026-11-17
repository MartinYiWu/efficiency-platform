"""异步组合的资源所有权与失败清理；不创建数据库连接或外部请求。"""

import asyncio
import base64
from types import SimpleNamespace

import pytest
from pydantic import SecretStr

from efficiency_platform_agent.configuration.context_publication import (
    ContextPublication,
)
from efficiency_platform_agent.configuration.integration import S7IntegrationSettings
from efficiency_platform_agent.core.context_control import ModelCapacity, WindowLimits
from efficiency_platform_agent.core.context_ports import ContextMetadata
from efficiency_platform_agent.core.run import JsonObject
from efficiency_platform_agent.harness import async_factory


def settings(tmp_path, *, memory=True):
    publication = ContextPublication(
        schema_version="context-publication/1",
        metadata=(
            ContextMetadata(
                "direct",
                "window/1",
                "1",
                "1",
                "1",
                1,
                ModelCapacity(
                    "deepseek",
                    "synthetic",
                    "1",
                    10000,
                    8000,
                    1000,
                    "conservative-utf8/1",
                    "openai-chat/1",
                    "NO_REASONING",
                    True,
                    "fake-only",
                ),
                WindowLimits(10000, 8000, 1000, 1000, 8000),
                JsonObject((("max_tokens", 1000),)),
            ),
        ),
        execution_agents={"direct": ("operations", "assistant_response")},
    )
    path = tmp_path / "assets.json"
    path.write_text(publication.model_dump_json(), encoding="utf-8")
    return S7IntegrationSettings(
        context_enabled=True,
        context_internal_secret=SecretStr("i" * 32),
        context_hmac_key=SecretStr("h" * 32),
        context_publication_file=path,
        memory_enabled=memory,
        memory_encryption_key=SecretStr(base64.b64encode(b"m" * 32).decode()),
        memory_encryption_key_version="m1",
        memory_checkpoint_encryption_key=SecretStr(
            base64.b64encode(b"c" * 32).decode()
        ),
        memory_checkpoint_encryption_key_version="c1",
        memory_postgres_dsn=SecretStr("synthetic-dsn"),
        memory_registry_schema="agent_runtime_registry",
        memory_official_checkpoint_schema="agent_runtime_official",
        memory_owned_checkpoint_schema="agent_runtime_12345678",
        runtime_database_url=SecretStr("synthetic-db"),
    )


async def test_disabled_context_uses_existing_factory_without_opening_memory(
    monkeypatch,
):
    resolved = S7IntegrationSettings()
    sentinel = object()
    monkeypatch.setattr(
        async_factory,
        "MySqlRuntimeDatabase",
        lambda *_: pytest.fail("不得创建记忆连接"),
    )
    monkeypatch.setattr(
        async_factory,
        "build_local_agent_application",
        lambda **kw: (
            sentinel if kw == {"settings": resolved} else pytest.fail("配置变化")
        ),
    )
    assert await async_factory.build_async_local_agent_application(resolved) is sentinel


@pytest.mark.parametrize(
    "field,value",
    [
        ("memory_checkpoint_encryption_key", None),
        ("memory_registry_schema", ""),
        ("memory_postgres_dsn", None),
        ("memory_owned_checkpoint_schema", "agent_runtime_owned"),
    ],
)
async def test_incomplete_memory_configuration_fails_before_opening_database(
    tmp_path, monkeypatch, field, value
):
    resolved = settings(tmp_path).model_copy(update={field: value})
    monkeypatch.setattr(
        async_factory,
        "MySqlRuntimeDatabase",
        lambda *_: pytest.fail("配置不足不得连接"),
    )
    with pytest.raises(ValueError):
        await async_factory.build_async_local_agent_application(resolved)


@pytest.mark.parametrize("failure", [ValueError("synthetic"), asyncio.CancelledError()])
async def test_factory_failure_closes_owned_memory_and_database_in_same_loop(
    tmp_path, monkeypatch, failure
):
    events = []
    engine = object()
    loop = asyncio.get_running_loop()

    async def close_database():
        events.append(("database", asyncio.get_running_loop()))

    async def close_memory():
        events.append(("memory", asyncio.get_running_loop()))

    database = SimpleNamespace(engine=engine, close=close_database)
    memory = SimpleNamespace(close=close_memory)
    monkeypatch.setattr(async_factory, "MySqlRuntimeDatabase", lambda *_: database)

    async def build_memory(**kwargs):
        assert kwargs["engine"] is engine
        assert kwargs["checkpoint_key"] == b"c" * 32
        assert asyncio.get_running_loop() is loop
        return memory

    def build_application(**kwargs):
        assert kwargs["memory_runtime"] is memory
        assert kwargs["memory_database"] is database
        kwargs["context_dispatch"].authority.assert_ready()
        raise failure

    monkeypatch.setattr(async_factory, "build_memory_runtime", build_memory)
    monkeypatch.setattr(
        async_factory, "build_local_agent_application", build_application
    )
    with pytest.raises(type(failure)):
        await async_factory.build_async_local_agent_application(settings(tmp_path))
    assert events == [("memory", loop), ("database", loop)]


async def test_success_transfers_owned_resources_to_application(tmp_path, monkeypatch):
    events = []
    database = SimpleNamespace(engine=object())

    async def close():
        events.append("premature-close")

    database.close = close
    memory = SimpleNamespace(close=close)
    application = object()
    monkeypatch.setattr(async_factory, "MySqlRuntimeDatabase", lambda *_: database)

    async def build_memory(**kwargs):
        return memory

    monkeypatch.setattr(async_factory, "build_memory_runtime", build_memory)

    def build_application(**kwargs):
        assert kwargs["memory_runtime"] is memory
        assert kwargs["memory_database"] is database
        return application

    monkeypatch.setattr(
        async_factory, "build_local_agent_application", build_application
    )
    assert (
        await async_factory.build_async_local_agent_application(settings(tmp_path))
        is application
    )
    assert events == []
