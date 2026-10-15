"""Agent 运行态 MySQL 配置边界。"""

from __future__ import annotations

from urllib.parse import urlsplit


def validate_runtime_database_url(value: str) -> str:
    """只接受指向独立 Agent 数据库的 SQLAlchemy async MySQL URL。"""
    if not isinstance(value, str) or not value.strip():
        raise ValueError("缺少本地真实运行配置: runtime_database_url")
    parsed = urlsplit(value)
    if parsed.scheme != "mysql+asyncmy":
        raise ValueError("AGENT_RUNTIME_DATABASE_URL 必须使用 mysql+asyncmy")
    if not parsed.hostname:
        raise ValueError("AGENT_RUNTIME_DATABASE_URL 缺少主机")
    if parsed.path.removeprefix("/") != "ai_efficiency_platform_agent":
        raise ValueError("AGENT_RUNTIME_DATABASE_URL 必须指向 ai_efficiency_platform_agent")
    return value


__all__ = ["validate_runtime_database_url"]
