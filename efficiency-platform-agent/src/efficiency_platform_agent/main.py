"""提供正式的本地 Agent 应用启动入口。"""

from __future__ import annotations

import argparse
from collections.abc import Sequence

import uvicorn

from efficiency_platform_agent.harness.local_real_factory import (
    build_local_agent_application,
)


def parse_arguments(argv: Sequence[str] | None = None) -> argparse.Namespace:
    """解析本地服务启动参数，不读取 env 文件内容。"""
    parser = argparse.ArgumentParser(description="启动 Efficiency Platform Agent")
    parser.add_argument("--env-file", default=".env")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", default=8080, type=int)
    return parser.parse_args(argv)


def main(argv: Sequence[str] | None = None) -> None:
    """装配本地服务并交由 Uvicorn 启动。"""
    arguments = parse_arguments(argv)
    application = build_local_agent_application(env_file=arguments.env_file)
    uvicorn.run(
        application.app,
        host=arguments.host,
        port=arguments.port,
        log_level="info",
    )
