"""验证正式应用入口与兼容脚本。"""

from __future__ import annotations

import builtins
import runpy
from types import SimpleNamespace

import pytest


def test_parse_arguments_uses_local_defaults() -> None:
    """未传入参数时使用安全的本地监听默认值。"""
    from efficiency_platform_agent.main import parse_arguments

    arguments = parse_arguments([])

    assert arguments.env_file == ".env"
    assert arguments.host == "127.0.0.1"
    assert arguments.port == 8080


def test_main_builds_application_and_starts_uvicorn_without_reading_env(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """入口只转交 env 文件路径，不读取其内容。"""
    from efficiency_platform_agent import main as application_main

    calls: dict[str, object] = {}

    def build_application(*, env_file: str) -> SimpleNamespace:
        calls["env_file"] = env_file
        return SimpleNamespace(app="application")

    def run_server(app: object, **kwargs: object) -> None:
        calls["app"] = app
        calls["server"] = kwargs

    def fail_if_read(*args: object, **kwargs: object) -> object:
        raise AssertionError("正式入口不应读取 .env 内容")

    monkeypatch.setattr(application_main, "build_local_agent_application", build_application)
    monkeypatch.setattr(application_main.uvicorn, "run", run_server)
    monkeypatch.setattr(builtins, "open", fail_if_read)

    application_main.main(["--env-file", "local.env", "--host", "0.0.0.0", "--port", "9090"])

    assert calls == {
        "env_file": "local.env",
        "app": "application",
        "server": {"host": "0.0.0.0", "port": 9090, "log_level": "info"},
    }


def test_legacy_script_forwards_to_package_main(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """兼容脚本仅转调包内正式入口。"""
    from efficiency_platform_agent import main as application_main

    calls: list[object] = []
    monkeypatch.setattr(application_main, "main", lambda: calls.append("called"))

    runpy.run_path("scripts/local_agent_server.py", run_name="__main__")

    assert calls == ["called"]
