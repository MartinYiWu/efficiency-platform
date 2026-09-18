"""本地实时来源的显式配置加载；不从发现 URL 派生网络权限。"""

from __future__ import annotations

import tomllib
from pathlib import Path
from types import MappingProxyType

from efficiency_platform_agent.contracts.research_sources_v2 import SourceDescriptorV2

LOCAL_SOURCE_CONFIG_VERSION = "local-live-sources/1"

# 端点与域名单独冻结；文章链接不能扩大这些网络身份。
LOCAL_SOURCE_ENDPOINTS = MappingProxyType(
    {
        "google_blog_rss": "https://blog.google/rss/",
        "langgraph_releases_atom": "https://github.com/langchain-ai/langgraph/releases.atom",
        "hacker_news_api": "https://hacker-news.firebaseio.com/v0/topstories.json",
        "arxiv_api": "https://export.arxiv.org/api/query",
        "gdelt_doc_api": "https://api.gdeltproject.org/api/v2/doc/doc",
    }
)
_SOURCE_IDENTITIES = MappingProxyType(
    {
        "google_blog_rss": ("rss_atom", "rss", "google", ("blog.google",)),
        "langgraph_releases_atom": (
            "rss_atom",
            "atom",
            "langchain-ai/langgraph",
            ("github.com",),
        ),
        "hacker_news_api": (
            "hacker_news",
            "api",
            "hacker_news",
            ("hacker-news.firebaseio.com",),
        ),
        "arxiv_api": ("arxiv", "api", "arxiv", ("export.arxiv.org",)),
        "gdelt_doc_api": ("gdelt", "api", "gdelt", ("api.gdeltproject.org",)),
    }
)


def load_local_source_descriptors(path: Path) -> tuple[SourceDescriptorV2, ...]:
    """读取完整结构化策略；未知字段、重复身份或主机越权均失败关闭。"""
    with path.open("rb") as handle:
        raw = tomllib.load(handle)
    if (
        set(raw) != {"config_version", "sources"}
        or raw["config_version"] != LOCAL_SOURCE_CONFIG_VERSION
    ):
        raise ValueError("LOCAL_SOURCE_CONFIG_INVALID")
    records = raw["sources"]
    if not isinstance(records, list) or not records:
        raise ValueError("LOCAL_SOURCE_CONFIG_INVALID")
    descriptors = tuple(SourceDescriptorV2.model_validate(record) for record in records)
    return validate_local_source_descriptors(descriptors)


def validate_local_source_descriptors(
    descriptors: tuple[SourceDescriptorV2, ...],
) -> tuple[SourceDescriptorV2, ...]:
    """校验组合层传入的描述符，不实例化任何研究能力。"""
    # 重新校验 model_copy 的输入，避免未验证的副本绕过嵌套契约。
    validated = tuple(
        SourceDescriptorV2.model_validate(item.model_dump()) for item in descriptors
    )
    ids = [item.source_id for item in validated]
    if len(set(ids)) != len(ids):
        raise ValueError("SOURCE_ID_DUPLICATED")
    for item in validated:
        identity = _SOURCE_IDENTITIES.get(item.source_id)
        if identity is None:
            raise ValueError("LOCAL_SOURCE_ID_NOT_REGISTERED")
        adapter, access, publisher, hosts = identity
        if item.allowed_hosts != hosts:
            raise ValueError("LOCAL_SOURCE_HOST_NOT_REGISTERED")
        if (item.adapter_id, item.access_mode, item.publisher_id) != (
            adapter,
            access,
            publisher,
        ):
            raise ValueError("LOCAL_SOURCE_IDENTITY_MISMATCH")
        if item.config_version != LOCAL_SOURCE_CONFIG_VERSION:
            raise ValueError("LOCAL_SOURCE_CONFIG_INVALID")
        if (
            item.enabled
            and item.history_mode != "unknown"
            and (
                not item.admission.history_verified
                or item.freshness_sla is None
                or item.max_lookback is None
            )
        ):
            raise ValueError("SOURCE_HISTORY_UNSUPPORTED")
        if item.content_policy.storage_mode == "full":
            raise ValueError("LOCAL_SOURCE_FULL_CONTENT_NOT_APPROVED")
        for value in (item.cost_policy.verified_at, item.admission.last_verified_at):
            if value is not None and (
                value.tzinfo is None or value.utcoffset() is None
            ):
                raise ValueError("LOCAL_SOURCE_EVIDENCE_TIME_NAIVE")
    return validated


__all__ = [
    "LOCAL_SOURCE_ENDPOINTS",
    "load_local_source_descriptors",
    "validate_local_source_descriptors",
]
