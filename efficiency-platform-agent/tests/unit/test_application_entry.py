"""验证正式应用入口与兼容脚本。"""

from __future__ import annotations

import asyncio
import builtins
import runpy
import sys
from types import SimpleNamespace

import pytest


def test_parse_arguments_uses_local_defaults() -> None:
    """未传入参数时使用安全的本地监听默认值。"""
    from efficiency_platform_agent.main import parse_arguments

    arguments = parse_arguments([])

    assert arguments.env_file == ".env"
    assert arguments.host == "127.0.0.1"
    assert arguments.port == 8080


def test_main_builds_serves_and_closes_in_one_running_loop(monkeypatch):
    from efficiency_platform_agent import main as application_main

    seen = []

    async def close():
        seen.append(("close", asyncio.get_running_loop()))

    async def build_application(**kwargs):
        seen.append(("build", asyncio.get_running_loop()))
        return SimpleNamespace(app="application", close=close)

    def old_sync_build(**kwargs):
        asyncio.get_running_loop()
        return SimpleNamespace(app="application", close=close)

    class Server:
        def __init__(self, config):
            assert config.app == "application"

        async def serve(self):
            seen.append(("serve", asyncio.get_running_loop()))

    monkeypatch.setattr(
        application_main, "build_local_agent_application", old_sync_build, raising=False
    )
    monkeypatch.setattr(
        application_main,
        "build_async_local_agent_application",
        build_application,
        raising=False,
    )
    monkeypatch.setattr(application_main.uvicorn, "Server", Server)
    monkeypatch.setattr(application_main.uvicorn, "run", lambda *args, **kwargs: None)

    application_main.main([])

    assert [event for event, _ in seen] == ["build", "serve", "close"]
    assert len({id(loop) for _, loop in seen}) == 1


def test_main_builds_application_and_starts_uvicorn_without_reading_env(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """入口只转交 env 文件路径，不读取其内容。"""
    from efficiency_platform_agent import main as application_main

    calls: dict[str, object] = {}

    async def close() -> None:
        calls["closed"] = True

    async def build_application(*, env_file: str) -> SimpleNamespace:
        calls["env_file"] = env_file
        return SimpleNamespace(app="application", close=close)

    class Server:
        def __init__(self, config):
            calls["app"] = config.app
            calls["server"] = {
                "host": config.host,
                "port": config.port,
                "log_level": config.log_level,
            }

        async def serve(self):
            pass

    def fail_if_read(*args: object, **kwargs: object) -> object:
        raise AssertionError("正式入口不应读取 .env 内容")

    monkeypatch.setattr(
        application_main, "build_async_local_agent_application", build_application
    )
    monkeypatch.setattr(application_main.uvicorn, "Server", Server)
    monkeypatch.setattr(builtins, "open", fail_if_read)

    application_main.main(
        ["--env-file", "local.env", "--host", "0.0.0.0", "--port", "9090"]
    )

    expected_server: dict[str, object] = {
        "host": "0.0.0.0",
        "port": 9090,
        "log_level": "info",
    }
    assert calls == {
        "env_file": "local.env",
        "app": "application",
        "server": expected_server,
        "closed": True,
    }


def test_main_passes_psycopg_compatible_loop_to_uvicorn_on_windows(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Windows 服务入口必须使用 psycopg 异步连接支持的 Selector 循环。"""
    from efficiency_platform_agent import main as application_main

    selected: list[object] = []

    async def close():
        pass

    async def build_application(**kwargs):
        selected.append(asyncio.get_running_loop())
        return SimpleNamespace(app="application", close=close)

    class Server:
        def __init__(self, config):
            pass

        async def serve(self):
            pass

    monkeypatch.setattr(sys, "platform", "win32")
    monkeypatch.setattr(
        application_main,
        "build_async_local_agent_application",
        build_application,
    )
    monkeypatch.setattr(
        application_main.uvicorn,
        "Server",
        Server,
    )

    application_main.main([])

    assert len(selected) == 1
    assert isinstance(selected[0], asyncio.SelectorEventLoop)
    assert selected[0].is_closed()


def test_legacy_script_forwards_to_package_main(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """兼容脚本仅转调包内正式入口。"""
    from efficiency_platform_agent import main as application_main

    calls: list[object] = []
    monkeypatch.setattr(application_main, "main", lambda: calls.append("called"))

    runpy.run_path("scripts/local_agent_server.py", run_name="__main__")

    assert calls == ["called"]


@pytest.mark.parametrize("platform", ["win32", "linux"])
def test_local_live_script_selects_database_compatible_loop(
    monkeypatch: pytest.MonkeyPatch, platform: str
) -> None:
    """实时验收脚本与正式入口使用相同的数据库兼容事件循环。"""
    script = runpy.run_path("scripts/run_local_live_agent.py")
    entry = script["main"]
    selected: list[object] = []
    settings = SimpleNamespace(gates={}, model_copy=lambda **_: "settings")
    monkeypatch.setattr(
        script["S7IntegrationSettings"], "from_env_file", lambda _: settings
    )
    monkeypatch.setitem(entry.__globals__, "_runtime_database_url", lambda _: "unused")
    monkeypatch.setitem(
        entry.__globals__,
        "build_local_agent_application",
        lambda **_: SimpleNamespace(app="application"),
    )
    monkeypatch.setattr(
        script["uvicorn"],
        "run",
        lambda *_, **options: selected.append(options.get("loop", "auto")),
    )
    monkeypatch.setattr(sys, "argv", ["run_local_live_agent.py"])
    monkeypatch.setattr(sys, "platform", platform)

    entry()

    assert selected == [
        "efficiency_platform_agent.main:selector_loop_factory"
        if platform == "win32"
        else "auto"
    ]


def test_uvicorn_resolves_psycopg_compatible_loop_factory() -> None:
    """自定义导入路径必须能由实际Uvicorn解析为Selector循环工厂。"""
    import uvicorn

    factory = uvicorn.Config(
        app="unused", loop="efficiency_platform_agent.main:selector_loop_factory"
    ).get_loop_factory()

    assert factory is not None
    loop = factory()
    try:
        assert isinstance(loop, asyncio.SelectorEventLoop)
    finally:
        loop.close()
