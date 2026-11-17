"""提供正式的本地 Agent 应用启动入口。"""

from __future__ import annotations

import argparse
import asyncio
import sys
from collections.abc import Sequence

import uvicorn

from efficiency_platform_agent.harness.async_factory import (
    build_async_local_agent_application,
)


def parse_arguments(argv: Sequence[str] | None = None) -> argparse.Namespace:
    """解析本地服务启动参数，不读取 env 文件内容。"""
    parser = argparse.ArgumentParser(description="启动 Efficiency Platform Agent")
    parser.add_argument("--env-file", default=".env")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", default=8080, type=int)
    return parser.parse_args(argv)


def selector_loop_factory() -> asyncio.AbstractEventLoop:
    """为 Windows 上的 psycopg 异步连接创建 Selector 事件循环。"""
    return asyncio.SelectorEventLoop()


async def _serve(arguments: argparse.Namespace) -> None:
    application = await build_async_local_agent_application(env_file=arguments.env_file)
    try:
        server = uvicorn.Server(
            uvicorn.Config(
                application.app,
                host=arguments.host,
                port=arguments.port,
                log_level="info",
            )
        )
        await server.serve()
    finally:
        await application.close()


def main(argv: Sequence[str] | None = None) -> None:
    """连接初始化、服务与关闭始终使用同一个数据库兼容事件循环。"""
    arguments = parse_arguments(argv)
    with asyncio.Runner(
        loop_factory=selector_loop_factory if sys.platform == "win32" else None
    ) as runner:
        runner.run(_serve(arguments))
